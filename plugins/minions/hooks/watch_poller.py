"""The Minions task watch's background poller, run by the plugin monitor (monitors/monitors.json).

Every poll it reads the computer's watch list for this session's Minions endpoint and org
(watch_state.py), asks Minions where each watched task or feature stands (GET
<endpoint>/api/mcp/watch with the session's read-only watch token), and prints one line per change
that matters. Each printed line reaches Claude as an event; the plugin skill says what to do with
each. Nothing is printed while nothing changes, so a quiet watch costs no model turns, and an empty
list costs no request.

Lines are `minions-watch <json>`, with "event" one of:
  needs_action      a watched task entered a state that needs the user, or its reason changed
  reminder          still needs the user, reminderMinutes after the last alert
  waiting           now held behind another task (no action)
  done              merged, Done or removed; the watch for it ends
  not_found         the key is no longer visible; the watch for it ends
  removed_elsewhere the user stopped watching it in another session; the watch for it ends here too
  token_expired     the watch token expired or was revoked; call watch_tasks with needToken true
  access_revoked    the account can no longer read the org's tasks; the watch stops
  unreachable / reachable   Minions could not be reached five polls running / is back

The list is shared (watch_list.py): a watch another session starts is checked here from the next
poll, and one another session stops, or that ends there, is dropped here with its own line. So is
the answer: a poller uses another session's answer for the same list from the last
POLL_SHARE_SECONDS instead of asking again, so the sessions checking one list send about one
request a minute between them.

Claude Code starts the monitor only when the minions:watch skill first runs in a session
(monitors/monitors.json: "when": "on-skill-invoke:minions:watch"), so nothing runs until someone
watches a task. From then it polls until its Claude Code process ends, and never exits early: a
monitor that exits is reported to Claude. It keeps watch_state.mark_monitor_running current, and
the hooks let a watch start only while it does.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch_list  # noqa: E402
import watch_state  # noqa: E402

DEFAULT_INTERVAL_SECONDS = 60
MIN_INTERVAL_SECONDS = 30
UNREACHABLE_AFTER = 5
SUMMARY_LIMIT = 300

# (status, body) — status 0 means the request never got an answer.
Fetch = Callable[[str, str], "tuple[int, object]"]


def http_fetch(url: str, token: str) -> tuple[int, object]:
    # The endpoint came from minions_endpoint.discover_endpoint, which yields https, or plain http
    # only to this machine; anything else is refused here too, so the token never travels in clear.
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        return 0, None
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})  # noqa: S310 - scheme checked above
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - scheme checked above
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None


def _event(name: str, **fields: object) -> str:
    payload = {"event": name, **{key: value for key, value in fields.items() if value is not None}}
    if isinstance(payload.get("summary"), str):
        payload["summary"] = payload["summary"][:SUMMARY_LIMIT]
    # ASCII only: on Windows a piped Python stdout uses the console code page, and Claude Code
    # reads the monitor's output as UTF-8, so an em dash in a summary would arrive garbled.
    return "minions-watch " + json.dumps(payload)


def _task_fields(task: dict) -> dict:
    return {
        "key": task.get("key"),
        "kind": task.get("kind"),
        "title": task.get("title"),
        "status": task.get("status"),
        "type": task.get("type"),
        "category": task.get("category"),
        "summary": task.get("summary"),
        "url": task.get("url"),
        # The key list_blockers files the reason under: for a feature, the task that needs the user.
        "blockerKey": task.get("blockerKey"),
    }


def follow_list(session_id: str, scope: str) -> list[str]:
    """Bring this session's keys in line with the computer's list; an event for each key that left it.

    A key another session added is tracked with no state yet, so the first poll alerts on it if it
    needs the user: this session has not shown it. A key that left the list is dropped with the
    reason another session recorded (watch_list.end_watches). A key this session stopped itself
    goes quietly: its hook drops it here and then from the list, and a poll between the two writes
    can put it back here, so the list's `by` is what tells the two cases apart.
    """
    listed = watch_list.watched(scope)
    gone = watch_list.ended(scope)
    events: list[str] = []
    with watch_state.update_state(session_id) as state:
        keys = state["keys"]
        for key in [key for key in keys if key not in listed]:
            entry = keys.pop(key)
            if not isinstance(entry, dict) or entry.get("state") == "done":
                continue
            why = gone.get(key) or {}
            title = why.get("title") or entry.get("title") or None
            if why.get("reason") == "removed" and why.get("by") == session_id:
                continue
            if why.get("reason") == "done":
                events.append(_event("done", key=key, title=title, summary=why.get("summary") or None))
            elif why.get("reason") == "not_found":
                events.append(_event("not_found", key=key))
            else:
                events.append(_event("removed_elsewhere", key=key, title=title))
        for key, entry in listed.items():
            if key not in keys:
                keys[key] = {"title": entry.get("title") or "", "state": None, "fingerprint": None, "lastAlertAt": None}
    return events


def poll_once(session_id: str, fetch: Fetch = http_fetch, now: float | None = None) -> list[str]:
    """One poll: returns the event lines to print, and records what was alerted."""
    current = time.time() if now is None else now
    path = watch_state.state_path(session_id)
    if path is None:
        return []
    snapshot = watch_state.read_state(path)
    if not snapshot:
        return []
    endpoint = str(snapshot.get("endpoint") or "").rstrip("/")
    scope = watch_list.list_scope(endpoint, snapshot.get("orgId"))
    if scope is None:
        # This session has never started a watch, so it has no token for any list.
        return []
    events = follow_list(session_id, scope)
    snapshot = watch_state.read_state(path) or snapshot
    keys = watch_state.open_keys(snapshot)
    if not keys:
        return events
    if not watch_state.token_valid(snapshot, current):
        with watch_state.update_state(session_id) as state:
            if not state["notices"].get("tokenExpired"):
                state["notices"]["tokenExpired"] = True
                events.append(_event("token_expired", keys=watch_state.open_keys(state)))
        return events

    poll_path = str(snapshot.get("pollPath") or "/api/mcp/watch")
    url = f"{endpoint}{poll_path}?keys={urllib.parse.quote(','.join(keys), safe=',')}"
    shared = watch_list.read_poll(scope, keys, current)
    if shared is not None:
        status, body = 200, shared
    else:
        status, body = fetch(url, str(snapshot.get("token")))
        if status == 200 and isinstance(body, dict):
            watch_list.write_poll(scope, keys, body, current)

    # Keys whose watch ended here: taken off this list once this session's file is written, so
    # the other sessions say why (follow_list) instead of only that they are gone. Only this
    # session's own list: a bare key can name a task in another org too.
    ended: dict[str, dict[str, str]] = {"done": {}, "not_found": {}}
    events.extend(_apply_poll(session_id, status, body, current, ended))
    for reason, summaries in ended.items():
        watch_list.end_watches(scope, list(summaries), reason, summaries, now=current)
    return events


def _apply_poll(session_id: str, status: int, body: object, current: float, ended: dict[str, dict[str, str]]) -> list[str]:
    events: list[str] = []
    with watch_state.update_state(session_id) as state:
        notices = state["notices"]
        if status == 401:
            state.pop("token", None)
            if not notices.get("tokenExpired"):
                notices["tokenExpired"] = True
                events.append(_event("token_expired", keys=watch_state.open_keys(state)))
            return events
        if status == 403:
            if not notices.get("accessRevoked"):
                notices["accessRevoked"] = True
                events.append(_event("access_revoked", keys=watch_state.open_keys(state)))
            # Nothing on this list can be read any more, from any session.
            ended["not_found"].update({key: "" for key in state["keys"]})
            state["keys"] = {}
            return events
        if status == 429:
            return events
        if status != 200 or not isinstance(body, dict):
            notices["failures"] = int(notices.get("failures") or 0) + 1
            if notices["failures"] >= UNREACHABLE_AFTER and not notices.get("unreachable"):
                notices["unreachable"] = True
                events.append(_event("unreachable", keys=watch_state.open_keys(state)))
            return events
        notices["failures"] = 0
        if notices.get("unreachable"):
            notices["unreachable"] = False
            events.append(_event("reachable"))

        reminder_seconds = int(state.get("reminderMinutes", watch_state.DEFAULT_REMINDER_MINUTES) or 0) * 60
        watched = state["keys"]
        for task in body.get("tasks") or []:
            if not isinstance(task, dict) or task.get("key") not in watched:
                continue
            key = task["key"]
            entry = watched[key]
            new_state = task.get("state")
            fingerprint = task.get("fingerprint")
            if new_state == "done":
                events.append(_event("done", **_task_fields(task)))
                watched.pop(key, None)
                ended["done"][key] = str(task.get("summary") or "")
                continue
            if new_state == "action":
                if fingerprint != entry.get("fingerprint") or entry.get("state") != "action":
                    events.append(_event("needs_action", **_task_fields(task)))
                    entry["lastAlertAt"] = current
                elif reminder_seconds > 0 and current - float(entry.get("lastAlertAt") or current) >= reminder_seconds:
                    events.append(_event("reminder", **_task_fields(task)))
                    entry["lastAlertAt"] = current
                entry["fingerprint"] = fingerprint
            else:
                if new_state == "waiting" and entry.get("state") != "waiting":
                    events.append(_event("waiting", **_task_fields(task)))
                # Cleared: the same blocker coming back later is a new alert.
                entry["fingerprint"] = None
            entry["state"] = new_state
            if task.get("title"):
                entry["title"] = task["title"]
        for key in body.get("notFound") or []:
            if key in watched:
                events.append(_event("not_found", key=key))
                watched.pop(key, None)
                ended["not_found"][key] = ""
    return events


def interval(session_id: str) -> int:
    path = watch_state.state_path(session_id)
    state = watch_state.read_state(path) if path else None
    try:
        seconds = int((state or {}).get("pollIntervalSeconds") or DEFAULT_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, seconds)


def main(
    argv: list[str],
    polls: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    fetch: Fetch = http_fetch,
    alive: Callable[[str | None], bool] = watch_state.process_alive,
) -> int:
    # A monitor is not given CLAUDE_PLUGIN_DATA in its environment, only substituted into its
    # command (monitors/monitors.json), so it arrives as the first argument. Without it the poller
    # would read a different folder from the one the hooks write.
    # Only an absolute path: a CLI that passed the placeholder through unfilled must not send the
    # poller to a relative folder of that name.
    if len(argv) > 1 and os.path.isabs(argv[1].strip()):
        os.environ["CLAUDE_PLUGIN_DATA"] = argv[1].strip()
    started_at = time.time()
    started_as = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    pid = os.environ.get("CLAUDE_PID") or ""
    # stderr is the monitor's log file, never an event Claude reads.
    if watch_state.monitor_running_path(pid) is None:
        # Without the process id it can neither find its session nor tell when the session ends.
        print("minions-watch: no Claude Code process id; not watching", file=sys.stderr, flush=True)
        return 0
    done = 0
    while polls is None or done < polls:
        if not alive(pid):
            watch_state.clear_monitor_running(pid, poller=str(os.getpid()))
            return 0
        done += 1
        # Rewritten every poll, so a week-long session's marker is never pruned as old.
        watch_state.mark_monitor_running(pid)
        # The process's current session, which /clear or /resume may have changed since start.
        session_id = watch_state.current_session(pid, started_as, not_before=started_at)
        try:
            for line in poll_once(session_id, fetch):
                print(line, flush=True)
        except Exception as error:  # noqa: BLE001 - one bad poll must not end the watch
            print(f"minions-watch poll failed: {error}", file=sys.stderr, flush=True)
        sleep(interval(session_id))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
