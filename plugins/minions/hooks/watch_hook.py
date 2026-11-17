"""The Minions task watch's hooks (plugin README -> Watching tasks).

Nothing runs until someone watches something: Claude Code starts the watch monitor only when the
minions:watch skill first runs in a session (monitors/monitors.json). So every offer here tells
Claude to run that skill, never to call watch_tasks directly, and a watch_tasks call that starts a
watch is refused while no monitor is running for this process (watch_state.monitor_running,
waiting for one that is still starting): a watch nothing polls would never alert.

The watch list is the computer's, shared by every session (watch_list.py → watches.json), one
list per Minions endpoint and org.

PostToolUse after create_task / adopt_ticket / start_task / resume_task / create_feature: offer
to watch the task or feature (watch_mode "ask"), start watching it ("auto"), or stay quiet ("off").

PreToolUse before watch_tasks: turn `stop: ["all"]` into every key on this session's list, keep the
computer within MAX_WATCHES, and refuse a call that starts a watch while no monitor is running.

PostToolUse after watch_tasks: add the started keys to the computer's list and take the stopped
ones off it, record the poller's read-only token in this session's state file, then hand Claude the
result with the token removed. Order matters, because a poller can read between two writes: a key
goes on the list before this session's file names it, and comes off it after.

SessionStart: on a fresh start in a folder a watch was started from, offer to check the watches in
this session. After /clear, /resume or a fork, move this process's watch to the new session id
instead, without a word (watch_state.py → the session pointer).

Every path exits 0 and prints nothing it cannot stand behind: a hook failure must never break the
tool call it follows.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch_list  # noqa: E402
import watch_state  # noqa: E402
from minions_endpoint import discover_endpoint  # noqa: E402

DEFAULT_ENDPOINT = "https://minions.charlieiq.ai"
PLUGIN_SERVER_PREFIX = "plugin_minions_"
TOKEN_PLACEHOLDER = "[kept by the Minions plugin]"  # noqa: S105 - shown in place of the token, not a credential
TASK_TOOLS = ("create_task", "adopt_ticket", "start_task", "resume_task", "create_feature")
# The most keys one GET /api/mcp/watch takes (MAX_WATCH_KEYS in Minions' lib/task-attention.ts).
MAX_WATCHES = 25
STOP_ALL = "all"
_TOOL = re.compile(r"^mcp__(?P<server>.*minions.*)__(?P<tool>[a-z_]+)$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
MONITOR_NOT_RUNNING_REASON = (
    "No watch monitor is running in this session, so nothing would check the task or alert the user. "
    "Run the minions:watch skill (it starts the monitor), then call watch_tasks again."
)
NOTHING_WATCHED_REASON = "Nothing is being watched on this computer. Tell the user so in one line."
SEVERAL_ORGS_REASON = (
    "This computer watches tasks in more than one Minions organization, and this session has not watched "
    "anything yet, so it cannot tell which list to clear. Ask the user which keys to stop watching, and pass them as stop."
)


def _json_documents(value: object):
    """Yield every dict inside a tool response, including JSON objects carried as text."""
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _json_documents(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_documents(item)
    elif isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        yield from _json_documents(parsed)


def _is_error(response: object) -> bool:
    if isinstance(response, dict) and response.get("isError") is True:
        return True
    return any(isinstance(doc.get("error"), dict) and "code" in doc["error"] for doc in _json_documents(response))


def _find(response: object, required: str) -> dict | None:
    for doc in _json_documents(response):
        if required in doc:
            return doc
    return None


def _redact(value: object, secret: str) -> object:
    if isinstance(value, dict):
        return {key: (TOKEN_PLACEHOLDER if key == "token" and isinstance(item, str) else _redact(item, secret)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, str) and secret and secret in value:
        return value.replace(secret, TOKEN_PLACEHOLDER)
    return value


def _context(event: str, text: str, extra: dict | None = None) -> dict:
    output = {"hookEventName": event, "additionalContext": text}
    if extra:
        output.update(extra)
    return {"hookSpecificOutput": output}


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def _task_key(tool: str, payload: dict) -> str | None:
    if tool in ("start_task", "resume_task"):
        key = (payload.get("tool_input") or {}).get("key")
    elif tool == "create_feature":
        # The feature's own key; its stories carry "key" too, and they are not what was made.
        doc = _find(payload.get("tool_response"), "epicKey")
        key = doc.get("epicKey") if doc else None
    else:
        doc = _find(payload.get("tool_response"), "key")
        key = doc.get("key") if doc else None
    return key.strip() if isinstance(key, str) and _KEY.match(key.strip()) else None


def _skill_call(keys: list[str], has_token: bool) -> str:
    # commands/watch.md sets needToken unless the note says a token is held.
    note = " (a watch token is held)" if has_token else ""
    return f'the minions:watch skill with arguments "{" ".join(keys)}"{note}'


def _endpoint(server: str, cwd: str, plugin_root: str) -> str:
    """The Minions endpoint this MCP server talks to, the one its watch list is kept under."""
    plugin_first = server.startswith(PLUGIN_SERVER_PREFIX)
    return discover_endpoint(
        DEFAULT_ENDPOINT,
        os.environ.get("HOME") or os.path.expanduser("~"),
        cwd or os.getcwd(),
        plugin_root,
        server=server[len(PLUGIN_SERVER_PREFIX):] if plugin_first else server,
        plugin_first=plugin_first,
    ).rstrip("/")


def _session_scope(state: dict) -> str | None:
    return watch_list.list_scope(state.get("endpoint"), state.get("orgId"))


def _session_state(session_id: object) -> dict:
    path = watch_state.state_path(session_id)
    return (watch_state.read_state(path) if path else None) or {}


def after_task_tool(tool: str, payload: dict) -> dict | None:
    if _is_error(payload.get("tool_response")):
        return None
    mode = watch_state.configured_mode()
    key = _task_key(tool, payload)
    if mode == "off" or not key:
        return None
    state = _session_state(payload.get("session_id"))
    # Already on the computer's list: this session's org list when it has one, else any list.
    scope = _session_scope(state)
    if key in (watch_list.watched(scope) if scope else watch_list.all_keys()):
        return None
    noun = "feature" if tool == "create_feature" else "task"
    call = _skill_call([key], watch_state.token_valid(state))
    if mode == "auto":
        text = (
            f"Minions task watch (auto): run {call} now without asking, then tell the user in one line that "
            f"you are watching {key} and will alert them when it needs them. Change this with /plugin configure minions."
        )
    else:
        text = (
            f"Minions task watch: ask the user, in one short question, whether to watch {noun} {key} so you can alert "
            f"them (with a desktop notification) when it needs their action. If they agree, run {call}. "
            "If they decline, do nothing more."
        )
    return _context("PostToolUse", text)


def after_watch_tasks(server: str, payload: dict, plugin_root: str) -> dict | None:
    response = payload.get("tool_response")
    session_id = payload.get("session_id")
    if _is_error(response) or watch_state.state_path(session_id) is None:
        return None
    result = _find(response, "watching")
    if result is None:
        return None
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    endpoint = _endpoint(server, cwd, plugin_root)
    # A Minions older than interface 1.168 returns no orgId: its watches share one list per endpoint.
    org_id = result.get("orgId") if isinstance(result.get("orgId"), int) and not isinstance(result.get("orgId"), bool) else 0
    scope = watch_list.list_scope(endpoint, org_id)
    token = result.get("token") if isinstance(result.get("token"), str) else ""
    now = time.time()
    started = [task for task in result.get("watching") or [] if isinstance(task, dict) and isinstance(task.get("key"), str)]
    stopped = [key for key in result.get("stopped") or [] if isinstance(key, str)]
    open_started = [task for task in started if task.get("state") != "done"]

    # On the list first: a poller reading between the two writes would otherwise find a key in
    # this session's file that the list lacks, and report it removed in another session.
    if scope is not None and open_started:
        watch_list.add_watches(scope, open_started, cwd, now=now)

    with watch_state.update_state(session_id, cwd) as state:
        if _session_scope(state) not in (None, scope):
            # The connection moved to another org (switch_org). The token held reads the old org's
            # tasks only, and the keys here are that org's list: this session follows the new one.
            # With no new token the poller reports token_expired, and Claude asks for one.
            state["keys"] = {}
            if not token:
                state.pop("token", None)
                state.pop("expiresAt", None)
                state["notices"]["tokenExpired"] = False
        state["endpoint"] = endpoint
        state["orgId"] = org_id
        state["reminderMinutes"] = watch_state.configured_reminder_minutes()
        if isinstance(result.get("pollPath"), str) and result["pollPath"].startswith("/api/"):
            state["pollPath"] = result["pollPath"]
        if isinstance(result.get("pollIntervalSeconds"), int):
            state["pollIntervalSeconds"] = result["pollIntervalSeconds"]
        if token:
            state["token"] = token
            state["expiresAt"] = result.get("expiresAt")
            state["notices"]["tokenExpired"] = False
        keys = state["keys"]
        if started:
            # A watch started after a revocation is a new one: a later revocation is reported again.
            state["notices"]["accessRevoked"] = False
        for task in started:
            if task.get("state") == "done":
                keys.pop(task["key"], None)
                continue
            previous = keys.get(task["key"]) if isinstance(keys.get(task["key"]), dict) else {}
            # Claude reads this result now, so a state it already shows is not alerted again.
            keys[task["key"]] = {
                "title": task.get("title") or previous.get("title") or "",
                "state": task.get("state"),
                "fingerprint": task.get("fingerprint"),
                "lastAlertAt": now if task.get("state") == "action" else previous.get("lastAlertAt"),
            }
        for key in stopped:
            keys.pop(key, None)

    # Off the list last, for the same reason: this session's file no longer names them.
    finished = {task["key"]: str(task.get("summary") or "") for task in started if task.get("state") == "done"}
    watch_list.end_watches(scope, list(finished), "done", finished, now=now)
    watch_list.end_watches(scope, stopped, "removed", now=now, by=str(session_id))
    # The monitor finds this session through the process it runs in (watch_state.py).
    watch_state.point_process(os.environ.get("CLAUDE_PID"), session_id)
    if not token:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": _redact(copy.deepcopy(response), token),
        }
    }


def _stop_all_keys(payload: dict, server: str, plugin_root: str) -> list[str] | dict:
    """The keys `stop: ["all"]` means: this session's org list, or a refusal to send instead.

    A session that has watched knows its list. One that has not knows only the endpoint: with one
    org's list there it is that one, with several it cannot tell which, so it asks.
    """
    state = _session_state(payload.get("session_id"))
    scope = _session_scope(state)
    if scope is None:
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
        scopes = watch_list.scopes_on(_endpoint(server, cwd, plugin_root))
        if len(scopes) > 1:
            return _deny(SEVERAL_ORGS_REASON)
        scope = scopes[0] if scopes else None
    keys = sorted(watch_list.watched(scope))
    return keys if keys else _deny(NOTHING_WATCHED_REASON)


def before_watch_tasks(payload: dict, server: str = "", plugin_root: str = "") -> dict | None:
    """Expand `stop: ["all"]`, keep the computer within MAX_WATCHES, and refuse a watch nothing would poll.

    A call that only stops watches always goes through, so /unwatch works in any session.
    """
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    updated: dict | None = None
    stop = tool_input.get("stop")
    if isinstance(stop, list) and any(isinstance(key, str) and key.strip().lower() == STOP_ALL for key in stop):
        every = _stop_all_keys(payload, server, plugin_root)
        if isinstance(every, dict):
            return every
        named = [key for key in stop if isinstance(key, str) and key.strip().lower() != STOP_ALL]
        updated = {**tool_input, "stop": sorted(set(every) | set(named))[:MAX_WATCHES]}

    starting = tool_input.get("keys")
    if isinstance(starting, list) and starting:
        # The whole computer, not one list: a session about to start may not know its org yet.
        already = set(watch_list.all_keys())
        new = {key for key in starting if isinstance(key, str)} - already
        if len(already) + len(new) > MAX_WATCHES:
            return _deny(
                f"This computer already watches {len(already)} Minions tasks and features; the limit is {MAX_WATCHES}. "
                "Tell the user, and ask which to stop watching first (/unwatch)."
            )
        if not watch_state.monitor_running_or_starting(os.environ.get("CLAUDE_PID")):
            return _deny(MONITOR_NOT_RUNNING_REASON)

    if updated is None:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": updated}}


def session_start(payload: dict) -> dict | None:
    mode = watch_state.configured_mode()
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    pid = os.environ.get("CLAUDE_PID")
    source = payload.get("source") or "startup"
    if source == "startup":
        # A new process: a running marker under its id was left by an earlier one.
        watch_state.clear_monitor_running(pid)
        watch_state.prune_old_files()
    if watch_state.state_path(session_id) is None:
        return None
    # /clear, /resume and a fork keep the process (and its monitor) but change the session id:
    # the watch moves with the process, silently. Only a fresh start offers the folder's watches.
    previous = watch_state.current_session(pid)
    if source != "startup" and previous and previous != session_id:
        watch_state.carry_over(previous, session_id)
    watch_state.point_process(pid, session_id)
    if source != "startup" or mode == "off" or not cwd:
        return None
    keys, titles = watch_list.folder_keys(cwd)
    if not keys:
        return None
    listed = ", ".join(f"{key} ({titles[key]})" if titles.get(key) else key for key in keys)
    call = _skill_call(keys, False)
    if mode == "auto":
        text = (
            f"Minions task watch (auto): this computer is watching {listed}, started from this folder. "
            f"When the user's first request is handled, run {call} without asking, and tell them in one line "
            "that this session is checking their watched tasks."
        )
    else:
        text = (
            f"Minions task watch: this computer is watching {listed}, started from this folder. After the "
            "user's first request, ask in one short question whether this session should check them and alert "
            f"them when one needs them; if they agree, run {call}."
        )
    return _context("SessionStart", text)


def main(argv: list[str]) -> int:
    plugin_root = argv[1] if len(argv) > 1 else str(Path(__file__).resolve().parent.parent)
    try:
        # UTF-8 bytes, never sys.stdin's text decoding: on Windows that is the console code page,
        # and a hook that re-sends the tool result would turn an em dash into "â€”".
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        output = None
        if payload.get("hook_event_name") == "SessionStart":
            output = session_start(payload)
        elif payload.get("hook_event_name") == "PreToolUse":
            match = _TOOL.match(str(payload.get("tool_name") or ""))
            if match and match.group("tool") == "watch_tasks":
                output = before_watch_tasks(payload, match.group("server"), plugin_root)
        else:
            match = _TOOL.match(str(payload.get("tool_name") or ""))
            if match and match.group("tool") in TASK_TOOLS:
                output = after_task_tool(match.group("tool"), payload)
            elif match and match.group("tool") == "watch_tasks":
                output = after_watch_tasks(match.group("server"), payload, plugin_root)
    except Exception:  # noqa: BLE001 - a hook must never fail the call it follows
        return 0
    if output:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
