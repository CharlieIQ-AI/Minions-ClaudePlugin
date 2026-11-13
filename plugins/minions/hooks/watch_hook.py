"""The Minions task watch's hooks (plugin README -> Watching tasks).

Nothing is offered or started unless this process's monitor is polling (watch_state.monitor_running,
waiting for one that is still starting):
with the Background watch monitor setting (watch_monitor) off, the default, it never polls, and a
setting turned on mid-session reaches no monitor until the next session. A watch nothing polls
would never alert.

PostToolUse after create_task / adopt_ticket / start_task / resume_task: offer to watch the task
(watch_mode "ask"), start watching it ("auto"), or stay quiet ("off").

PreToolUse before watch_tasks: refuse a call that starts a watch while no monitor is polling.

PostToolUse after watch_tasks: record the watched keys and the poller's read-only token in this
session's state file (watch_state.py), then hand Claude the result with the token removed.

SessionStart: on a fresh start, offer to keep watching the still-open tasks the last session in
this folder watched. After /clear, /resume or a fork, move this process's watch to the new
session id instead, without a word (watch_state.py → the session pointer).

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
import watch_state  # noqa: E402
from minions_endpoint import discover_endpoint  # noqa: E402

DEFAULT_ENDPOINT = "https://minions.charlieiq.ai"
PLUGIN_SERVER_PREFIX = "plugin_minions_"
TOKEN_PLACEHOLDER = "[kept by the Minions plugin]"  # noqa: S105 - shown in place of the token, not a credential
TASK_TOOLS = ("create_task", "adopt_ticket", "start_task", "resume_task")
_TOOL = re.compile(r"^mcp__(?P<server>.*minions.*)__(?P<tool>[a-z_]+)$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
MONITOR_OFF_REASON = (
    "Watching is not available in this session: the Minions plugin's background watch monitor is not "
    "running, so nothing would check the task or alert the user. Tell the user in one line that watching "
    "needs the Background watch monitor setting on (/plugin configure minions) and that a change applies "
    "from their next session. Do not retry."
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


def _task_key(tool: str, payload: dict) -> str | None:
    if tool in ("start_task", "resume_task"):
        key = (payload.get("tool_input") or {}).get("key")
    else:
        doc = _find(payload.get("tool_response"), "key")
        key = doc.get("key") if doc else None
    return key.strip() if isinstance(key, str) and _KEY.match(key.strip()) else None


def after_task_tool(tool: str, payload: dict) -> dict | None:
    if _is_error(payload.get("tool_response")):
        return None
    mode = watch_state.configured_mode()
    key = _task_key(tool, payload)
    session_id = payload.get("session_id")
    if (mode == "off" or not key or watch_state.state_path(session_id) is None
            or not watch_state.monitor_running_or_starting(os.environ.get("CLAUDE_PID"))):
        return None
    path = watch_state.state_path(session_id)
    state = watch_state.read_state(path) or {}
    entry = state.get("keys", {}).get(key)
    if isinstance(entry, dict) and entry.get("state") != "done":
        return None
    has_token = watch_state.token_valid(state)
    call = f'watch_tasks with keys ["{key}"]' + ("" if has_token else " and needToken true")
    if mode == "auto":
        text = (
            f"Minions task watch (auto): call {call} now without asking, then tell the user in one line that "
            f"you are watching {key} and will alert them when it needs them. Change this with /plugin configure minions."
        )
    else:
        text = (
            f"Minions task watch: ask the user, in one short question, whether to watch {key} in this session "
            f"so you can alert them (with a desktop notification) when it needs their action. If they agree, call {call}. "
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
    plugin_first = server.startswith(PLUGIN_SERVER_PREFIX)
    endpoint = discover_endpoint(
        DEFAULT_ENDPOINT,
        os.environ.get("HOME") or os.path.expanduser("~"),
        cwd or os.getcwd(),
        plugin_root,
        server=server[len(PLUGIN_SERVER_PREFIX):] if plugin_first else server,
        plugin_first=plugin_first,
    )
    token = result.get("token") if isinstance(result.get("token"), str) else ""
    now = time.time()
    with watch_state.update_state(session_id, cwd) as state:
        state["endpoint"] = endpoint
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
        if result.get("watching"):
            # A watch started after a revocation is a new one: a later revocation is reported again.
            state["notices"]["accessRevoked"] = False
        for task in result.get("watching") or []:
            if not isinstance(task, dict) or not isinstance(task.get("key"), str):
                continue
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
        for key in result.get("stopped") or []:
            if isinstance(key, str):
                keys.pop(key, None)
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


def before_watch_tasks(payload: dict) -> dict | None:
    """Refuse to start a watch while no monitor polls for this process: it would never alert.

    A call that only stops watches is let through, so /unwatch still clears old ones.
    """
    if watch_state.monitor_running_or_starting(os.environ.get("CLAUDE_PID")):
        return None
    tool_input = payload.get("tool_input")
    keys = tool_input.get("keys") if isinstance(tool_input, dict) else None
    if not keys:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": MONITOR_OFF_REASON,
        }
    }


def session_start(payload: dict) -> dict | None:
    mode = watch_state.configured_mode()
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    pid = os.environ.get("CLAUDE_PID")
    source = payload.get("source") or "startup"
    if source == "startup":
        # A new process: a running marker under its id was left by an earlier one. Cleared before
        # the setting is recorded, so this process's monitor cannot have written its own yet.
        watch_state.clear_monitor_running(pid)
    # Then at once: this process's monitor is waiting for it to decide whether to poll.
    setting = watch_state.record_monitor_setting(pid)
    if source == "startup":
        watch_state.prune_old_files()
    if watch_state.state_path(session_id) is None:
        return None
    # /clear, /resume and a fork keep the process (and its monitor) but change the session id:
    # the watch moves with the process, silently. Only a fresh start offers last session's watches.
    previous = watch_state.current_session(pid)
    if source != "startup" and previous and previous != session_id:
        watch_state.carry_over(previous, session_id)
    watch_state.point_process(pid, session_id)
    # The monitor starts polling just after this hook, so a fresh start goes by the setting it records.
    if source != "startup" or mode == "off" or setting != "on" or not cwd:
        return None
    keys, titles = watch_state.previous_session_keys(session_id, cwd)
    path = watch_state.state_path(session_id)
    already = set(watch_state.open_keys(watch_state.read_state(path) or {})) if path else set()
    keys = [key for key in keys if key not in already]
    if not keys:
        return None
    listed = ", ".join(f"{key} ({titles[key]})" if titles.get(key) else key for key in keys)
    call = "watch_tasks with keys [" + ", ".join(f'"{key}"' for key in keys) + "] and needToken true"
    if mode == "auto":
        text = (
            f"Minions task watch (auto): the last session in this folder was watching {listed}. "
            f"Call {call} when the user's first request is handled, without asking, and tell them in one line."
        )
    else:
        text = (
            f"Minions task watch: the last session in this folder was watching {listed}. After the user's first "
            f"request, ask in one short question whether to keep watching them here; if they agree, call {call}."
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
                output = before_watch_tasks(payload)
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
