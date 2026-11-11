"""The task watch's per-session state file, shared by the watch hook and the background poller.

One JSON file per Claude Code session under <plugin data>/watch/<session id>.json:

    {
      "sessionId": "...", "cwd": "...", "endpoint": "https://...", "pollPath": "/api/mcp/watch",
      "pollIntervalSeconds": 60, "token": "mcp_...", "expiresAt": "2026-...Z",
      "reminderMinutes": 60, "updatedAt": "...",
      "keys": {"DEMO-42": {"title": "...", "state": "action", "fingerprint": "...",
                           "lastAlertAt": 1731100000.0}},
      "notices": {"tokenExpired": false, "accessRevoked": false, "unreachable": false}
    }

`reminderMinutes` is copied from the plugin setting when a watch starts, because a monitor is not
given the plugin's settings; a changed setting applies from the next watch_tasks call.

Beside the state files, `pid-<CLAUDE_PID>.session` names the session a Claude Code process is
on now. The monitor is started once per process and keeps the session id it started with, but
/clear, /resume and a fork move the process to a new session id; the SessionStart hook moves
the watch to the new id and updates this pointer, and the poller follows it.

The token is a read-only watch token (Minions docs/mcp.md -> Watching tasks from Claude Code). The
file is written owner-only where the platform supports it. Writers hold a lock file and replace the
state atomically, so the hook and the poller never interleave half-written JSON.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STALE_LOCK_SECONDS = 10.0
POINTER_SLACK_SECONDS = 60.0
STATE_RETENTION_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MODE = "ask"
DEFAULT_REMINDER_MINUTES = 60
MODES = ("ask", "auto", "off")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PID = re.compile(r"^[0-9]{1,10}$")


def data_dir() -> Path:
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        os.environ.get("HOME") or os.path.expanduser("~"), ".claude", "plugins", "minions"
    )
    return Path(base) / "watch"


def state_path(session_id: str) -> Path | None:
    if not isinstance(session_id, str) or not _SESSION_ID.match(session_id):
        return None
    return data_dir() / f"{session_id}.json"


def pointer_path(pid: object) -> Path | None:
    if not isinstance(pid, str) or not _PID.match(pid):
        return None
    return data_dir() / f"pid-{pid}.session"


def current_session(pid: object, fallback: str = "", not_before: float | None = None) -> str:
    """The session the Claude Code process `pid` is on, else `fallback` (the monitor's own).

    `not_before`: ignore a pointer last written before this time. Windows reuses process ids
    quickly, so a pointer left by a dead process can name another session; the poller passes
    its own start time, less POINTER_SLACK_SECONDS because this process's SessionStart hook may
    write the pointer just before the monitor starts.
    """
    path = pointer_path(pid)
    if path is not None:
        try:
            if not_before is not None and path.stat().st_mtime < not_before - POINTER_SLACK_SECONDS:
                return fallback
            pointed = path.read_text(encoding="utf-8").strip()
        except OSError:
            pointed = ""
        if _SESSION_ID.match(pointed):
            return pointed
    return fallback


def point_process(pid: object, session_id: str) -> None:
    path = pointer_path(pid)
    if path is None or state_path(session_id) is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pid-", suffix=".session", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(session_id)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def carry_over(from_session: str, to_session: str) -> None:
    """Move a watch to the session id the process now has; keys already on the new id win.

    The new file is written before the old one is deleted: a hook killed between the two leaves
    the watch in both files, never in neither.
    """
    source_path = state_path(from_session)
    if source_path is None or state_path(to_session) is None or from_session == to_session:
        return
    with locked(source_path):
        source = read_state(source_path)
        if not source:
            return
        with update_state(to_session, str(source.get("cwd") or "")) as state:
            for key, entry in source["keys"].items():
                state["keys"].setdefault(key, entry)
            if not token_valid(state):
                for field in ("endpoint", "pollPath", "pollIntervalSeconds", "token", "expiresAt", "reminderMinutes"):
                    if field in source:
                        state[field] = source[field]
                state["notices"] = source["notices"]
        try:
            source_path.unlink()
        except OSError:
            pass


def configured_mode() -> str:
    mode = (os.environ.get("CLAUDE_PLUGIN_OPTION_WATCH_MODE") or "").strip().lower()
    return mode if mode in MODES else DEFAULT_MODE


def configured_reminder_minutes() -> int:
    raw = (os.environ.get("CLAUDE_PLUGIN_OPTION_WATCH_REMINDER_MINUTES") or "").strip()
    try:
        value = int(float(raw))
    except ValueError:
        return DEFAULT_REMINDER_MINUTES
    return max(0, min(value, 1440))


def empty_state(session_id: str, cwd: str = "") -> dict:
    return {"sessionId": session_id, "cwd": cwd, "keys": {}, "notices": {}}


def read_state(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("keys"), dict):
        data["keys"] = {}
    if not isinstance(data.get("notices"), dict):
        data["notices"] = {}
    return data


def _write(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    fd, tmp = tempfile.mkstemp(prefix=".watch-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextmanager
def locked(path: Path, timeout: float = 5.0) -> Iterator[None]:
    """Hold <state>.lock while reading and writing. A lock older than STALE_LOCK_SECONDS is taken over."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"could not lock {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


@contextmanager
def update_state(session_id: str, cwd: str = "") -> Iterator[dict]:
    """Read-modify-write the session's state under the lock; yields a dict to mutate."""
    path = state_path(session_id)
    if path is None:
        raise ValueError("invalid session id")
    with locked(path):
        state = read_state(path) or empty_state(session_id, cwd)
        if cwd and not state.get("cwd"):
            state["cwd"] = cwd
        yield state
        _write(path, state)


def token_valid(state: dict, now: float | None = None) -> bool:
    token = state.get("token")
    expires = parse_time(state.get("expiresAt"))
    if not isinstance(token, str) or not token or expires is None:
        return False
    # Treat a token as spent five minutes early, so a poll never races its expiry.
    return expires - 300 > (time.time() if now is None else now)


def parse_time(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def open_keys(state: dict) -> list[str]:
    return sorted(key for key, entry in state.get("keys", {}).items() if isinstance(entry, dict) and entry.get("state") != "done")


def previous_session_keys(session_id: str, cwd: str, now: float | None = None) -> tuple[list[str], dict[str, str]]:
    """The still-open keys of the newest earlier session in the same folder, with their titles.

    Also deletes state files untouched for STATE_RETENTION_SECONDS, so old sessions do not pile up.
    """
    current = time.time() if now is None else now
    newest: tuple[float, dict] | None = None
    directory = data_dir()
    try:
        entries = list(directory.glob("*.json"))
    except OSError:
        return [], {}
    for path in entries:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if current - mtime > STATE_RETENTION_SECONDS:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        if path.stem == session_id:
            continue
        state = read_state(path)
        if not state or not _same_folder(state.get("cwd"), cwd) or not open_keys(state):
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, state)
    for path in directory.glob("pid-*.session"):
        try:
            if current - path.stat().st_mtime > STATE_RETENTION_SECONDS:
                path.unlink()
        except OSError:
            pass
    if newest is None:
        return [], {}
    state = newest[1]
    keys = open_keys(state)
    titles = {key: str(state["keys"][key].get("title") or "") for key in keys}
    return keys, titles


def _same_folder(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    return left.replace("\\", "/").rstrip("/").lower() == right.replace("\\", "/").rstrip("/").lower()
