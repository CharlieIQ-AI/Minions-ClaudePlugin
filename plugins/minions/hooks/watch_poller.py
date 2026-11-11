"""The Minions task watch's background poller, run by the plugin monitor (monitors/monitors.json).

Every poll it reads this session's state file (watch_state.py), asks Minions where each watched
task stands (GET <endpoint>/api/mcp/watch with the session's read-only watch token), and prints
one line per change that matters. Each printed line reaches Claude as an event; the plugin skill
says what to do with each. Nothing is printed while nothing changes, so a quiet watch costs no
model turns.

Lines are `minions-watch <json>`, with "event" one of:
  needs_action   a watched task entered a state that needs the user, or its reason changed
  reminder       still needs the user, reminderMinutes after the last alert
  waiting        now held behind another task (no action)
  done           merged, Done or removed; the watch for it ends
  not_found      the key is no longer visible; the watch for it ends
  token_expired  the watch token expired or was revoked; call watch_tasks with needToken true
  access_revoked the account can no longer read the org's tasks; the watch stops
  unreachable / reachable   Minions could not be reached five polls running / is back
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
        "title": task.get("title"),
        "status": task.get("status"),
        "type": task.get("type"),
        "category": task.get("category"),
        "summary": task.get("summary"),
        "url": task.get("url"),
    }


def poll_once(session_id: str, fetch: Fetch = http_fetch, now: float | None = None) -> list[str]:
    """One poll: returns the event lines to print, and records what was alerted."""
    current = time.time() if now is None else now
    path = watch_state.state_path(session_id)
    if path is None:
        return []
    snapshot = watch_state.read_state(path)
    if not snapshot:
        return []
    keys = watch_state.open_keys(snapshot)
    if not keys:
        return []
    events: list[str] = []
    if not watch_state.token_valid(snapshot, current):
        with watch_state.update_state(session_id) as state:
            if not state["notices"].get("tokenExpired"):
                state["notices"]["tokenExpired"] = True
                events.append(_event("token_expired", keys=watch_state.open_keys(state)))
        return events

    endpoint = str(snapshot.get("endpoint") or "").rstrip("/")
    poll_path = str(snapshot.get("pollPath") or "/api/mcp/watch")
    url = f"{endpoint}{poll_path}?keys={urllib.parse.quote(','.join(keys), safe=',')}"
    status, body = fetch(url, str(snapshot.get("token")))

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
    return events


def interval(session_id: str) -> int:
    path = watch_state.state_path(session_id)
    state = watch_state.read_state(path) if path else None
    try:
        seconds = int((state or {}).get("pollIntervalSeconds") or DEFAULT_INTERVAL_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, seconds)


def process_alive(pid: str | None) -> bool:
    """Whether the Claude Code process `pid` still runs; True when it cannot be told.

    The poller checks this before every poll and exits once its session's process is gone. On
    Windows, ending a session stops the monitor's shell but not the Python under it, so without
    this a poller outlives its session and keeps polling.
    """
    if not pid or not pid.isdigit():
        return True
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_limited_information, still_active, access_denied = 0x1000, 259, 5
        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            # Access denied means it exists; any other failure means there is no such process.
            return ctypes.get_last_error() == access_denied
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        # Signal 0 only checks: on POSIX it never delivers anything (on Windows it would kill).
        os.kill(int(pid), 0)
    except (ProcessLookupError, OverflowError):
        return False
    except OSError:
        return True
    return True


def main(
    argv: list[str],
    polls: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    fetch: Fetch = http_fetch,
    alive: Callable[[str | None], bool] = process_alive,
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
    pid = os.environ.get("CLAUDE_PID")
    if watch_state.state_path(started_as) is None and watch_state.pointer_path(pid) is None:
        print("minions-watch: no session id or Claude Code process id; not watching", file=sys.stderr, flush=True)
        return 0
    done = 0
    while polls is None or done < polls:
        if not alive(pid):
            return 0
        # The process's current session, which /clear or /resume may have changed since start.
        session_id = watch_state.current_session(pid, started_as, not_before=started_at)
        try:
            for line in poll_once(session_id, fetch):
                print(line, flush=True)
        except Exception as error:  # noqa: BLE001 - one bad poll must not end the watch
            # stderr is the monitor's log file, never an event Claude reads.
            print(f"minions-watch poll failed: {error}", file=sys.stderr, flush=True)
        done += 1
        sleep(interval(session_id))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
