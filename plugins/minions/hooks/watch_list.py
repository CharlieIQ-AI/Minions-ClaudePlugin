"""The computer's watch list, shared by every Claude Code session (plugin README -> Watching tasks).

<plugin data>/watch/watches.json, read and written by every session's hooks and poller, so a watch
started in one session is checked by every session that is checking watches, and one removed in
any session is removed in all of them:

    {
      "lists": {"<endpoint>|<org id>": {"DEMO-42": {"title": "...", "folders": ["..."]}}},
      "ended": {"<endpoint>|<org id>": {"DEMO-41": {"reason": "removed", "title": "...", "summary": "...",
                                                     "at": 1731100000.0, "by": "<session id>"}}}
    }

A list is kept per Minions endpoint and org, because a watch token reads one org's tasks, and a
bare tracker key (APEX-12 on a board from before key prefixes) can name a task in two orgs: every
change names its list. `folders` are the folders the watch was started from: a fresh session in
one of them offers to check the watches. `ended` remembers, for ENDED_RETENTION_SECONDS, why a key
left a list ("removed" by /unwatch, "done", or "not_found"), so a session that still had it says
what happened rather than only that it is gone. `by` is the session that ended it, which says
nothing about it: it already told its user.

Beside it, poll-<scope hash>.json holds the last answer Minions gave for a list, so the sessions
checking one list share one request a minute instead of each sending its own (read_poll).

Every read goes through read_shared, every write through update_shared, so a malformed or missing
file reads as empty rather than failing a hook. Writers hold the file's lock and replace it
atomically (watch_state.locked / _write).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import watch_state

ENDED_RETENTION_SECONDS = 24 * 60 * 60
ENDED_REASONS = ("removed", "done", "not_found")
# A poll answer another session fetched this recently is used instead of fetching again. Below
# the 60 s poll interval, so the sessions checking a list send about one request a minute.
POLL_SHARE_SECONDS = 45.0


def shared_path() -> Path:
    return watch_state.data_dir() / watch_state.SHARED_FILE


def list_scope(endpoint: object, org_id: object) -> str | None:
    """The key a list is kept under: one per Minions endpoint and org; None without both."""
    if not isinstance(endpoint, str) or not endpoint or isinstance(org_id, bool) or not isinstance(org_id, int):
        return None
    return f"{endpoint.rstrip('/')}|{org_id}"


def scope_endpoint(scope: str) -> str:
    return scope.rsplit("|", 1)[0]


def _normalized(data: object) -> dict:
    shared = data if isinstance(data, dict) else {}
    for section in ("lists", "ended"):
        value = shared.get(section)
        shared[section] = {
            scope: {key: entry for key, entry in entries.items() if isinstance(key, str) and isinstance(entry, dict)}
            for scope, entries in (value.items() if isinstance(value, dict) else [])
            if isinstance(scope, str) and isinstance(entries, dict)
        }
    return shared


def read_shared() -> dict:
    try:
        with shared_path().open(encoding="utf-8") as handle:
            return _normalized(json.load(handle))
    except (OSError, ValueError):
        return _normalized({})


@contextmanager
def update_shared(now: float | None = None) -> Iterator[dict]:
    """Read-modify-write the watch list under its lock; ended entries past their retention are dropped."""
    path = shared_path()
    with watch_state.locked(path):
        shared = read_shared()
        yield shared
        current = time.time() if now is None else now
        shared["ended"] = {
            scope: kept
            for scope, entries in shared["ended"].items()
            if (kept := {key: entry for key, entry in entries.items()
                         if current - float(entry.get("at") or 0) < ENDED_RETENTION_SECONDS})}
        shared["lists"] = {scope: entries for scope, entries in shared["lists"].items() if entries}
        watch_state._write(path, shared)  # noqa: SLF001 - the one atomic, owner-only writer


def add_watches(scope: str, entries: list[dict], cwd: str = "", now: float | None = None) -> None:
    """Add (or refresh) watches on one list: each entry needs "key"; "title" is kept when given."""
    with update_shared(now) as shared:
        listed = shared["lists"].setdefault(scope, {})
        ended_here = shared["ended"].get(scope, {})
        for entry in entries:
            key = entry.get("key")
            if not isinstance(key, str) or not key:
                continue
            ended_here.pop(key, None)
            existing = listed.get(key) or {"folders": []}
            if entry.get("title"):
                existing["title"] = entry["title"]
            folders = [folder for folder in existing.get("folders") or [] if isinstance(folder, str)]
            if cwd and not any(same_folder(folder, cwd) for folder in folders):
                folders.append(cwd)
            existing["folders"] = folders
            listed[key] = existing


def end_watches(
    scope: str | None,
    keys: list[str],
    reason: str,
    summaries: dict[str, str] | None = None,
    now: float | None = None,
    by: str = "",
) -> None:
    """Take keys off one list, remembering why (ENDED_REASONS) and which session (`by`) for the others."""
    if scope is None or reason not in ENDED_REASONS or not keys:
        return
    current = time.time() if now is None else now
    with update_shared(current) as shared:
        listed = shared["lists"].get(scope, {})
        for key in set(keys) & set(listed):
            entry = listed.pop(key)
            shared["ended"].setdefault(scope, {})[key] = {
                "reason": reason,
                "title": entry.get("title") or "",
                "summary": (summaries or {}).get(key) or "",
                "at": current,
                "by": by,
            }


def watched(scope: str | None) -> dict[str, dict]:
    """The watches on one list, key → entry."""
    return dict(read_shared()["lists"].get(scope, {})) if scope else {}


def ended(scope: str | None) -> dict[str, dict]:
    """Why keys recently left one list, key → {"reason", "title", "summary", "at"}."""
    return dict(read_shared()["ended"].get(scope, {})) if scope else {}


def scopes_on(endpoint: str) -> list[str]:
    """The lists kept for `endpoint`, one per org."""
    return sorted(scope for scope in read_shared()["lists"] if scope_endpoint(scope) == endpoint.rstrip("/"))


def all_keys() -> list[str]:
    """Every watched key on every list."""
    return sorted({key for listed in read_shared()["lists"].values() for key in listed})


def folder_keys(cwd: str) -> tuple[list[str], dict[str, str]]:
    """The watched keys started from folder `cwd`, on any list, with their titles."""
    titles: dict[str, str] = {}
    for listed in read_shared()["lists"].values():
        for key, entry in listed.items():
            if any(same_folder(folder, cwd) for folder in entry.get("folders") or []):
                titles[key] = str(entry.get("title") or "")
    return sorted(titles), titles


def same_folder(left: object, right: object) -> bool:
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right:
        return False
    return left.replace("\\", "/").rstrip("/").lower() == right.replace("\\", "/").rstrip("/").lower()


# The last poll answer for a list, shared by the sessions checking it. Only a 200 answer is kept:
# a refused token (401/403) is that session's own to report.

def _poll_path(scope: str) -> Path:
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:16]
    return watch_state.data_dir() / f"poll-{digest}.json"


def read_poll(scope: str, keys: list[str], now: float) -> dict | None:
    """Another session's answer for these keys, if it is recent enough to use instead of fetching."""
    try:
        with _poll_path(scope).open(encoding="utf-8") as handle:
            cached = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(cached, dict) or cached.get("scope") != scope or not isinstance(cached.get("body"), dict):
        return None
    try:
        # A hand-edited file must not stop polling: it is read as no answer, and the next fetch replaces it.
        age = now - float(cached.get("at") or 0)
        covered = set(keys) <= set(cached.get("keys") or [])
    except (TypeError, ValueError):
        return None
    if not 0 <= age < POLL_SHARE_SECONDS or not covered:
        return None
    wanted = set(keys)
    body = cached["body"]
    return {
        "tasks": [task for task in body.get("tasks") or [] if isinstance(task, dict) and task.get("key") in wanted],
        "notFound": [key for key in body.get("notFound") or [] if key in wanted],
    }


def write_poll(scope: str, keys: list[str], body: dict, now: float) -> None:
    path = _poll_path(scope)
    with watch_state.locked(path):
        watch_state._write(path, {"scope": scope, "at": now, "keys": sorted(keys), "body": body})  # noqa: SLF001
