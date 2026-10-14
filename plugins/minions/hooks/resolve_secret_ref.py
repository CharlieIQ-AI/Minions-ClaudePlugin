"""Resolve and stage Claude Code repository- and organization-secret references."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

DEFAULT_ENDPOINT = "https://minions.charlieiq.ai"
REPO_TOOL_SUFFIX = "__set_repo_secret"
ORG_TOOL_SUFFIX = "__set_org_secret"
PLUGIN_SERVER_PREFIX = "plugin_minions_"

# Importing the sibling module must not leave bytecode in the user's plugin directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from minions_endpoint import discover_endpoint  # noqa: E402


def resolve(reference: str) -> str:
    """Resolve env:, file:, or keychain: reference and return its exact value."""
    kind, separator, name = reference.partition(":")
    if not separator or not name or any(char.isspace() for char in name):
        raise ValueError("reference must have a non-empty name")
    if kind == "env":
        value = os.environ.get(name)
        if value is None:
            raise ValueError("environment variable is unset")
        return value
    if kind == "file":
        try:
            # newline="" preserves CRLF and other line endings while decoding UTF-8.
            with Path(os.path.expanduser(name)).open("r", encoding="utf-8", newline="") as handle:
                return handle.read()
        except FileNotFoundError as error:
            raise ValueError("file was not found") from error
        except UnicodeDecodeError as error:
            raise ValueError("file is not UTF-8") from error
    if kind == "keychain":
        service, slash, account = name.partition("/")
        if not slash or not service or not account:
            raise ValueError("keychain reference must be SERVICE/ACCOUNT")
        if platform.system() == "Darwin":
            command = ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
        elif platform.system() == "Linux":
            command = ["secret-tool", "lookup", "service", service, "account", account]
        elif platform.system() == "Windows":
            return _read_windows_credential(name)
        else:
            raise ValueError("keychain is unsupported on this platform")
        try:
            result = subprocess.run(command, check=False, capture_output=True, timeout=5)  # noqa: S603
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise ValueError("keychain command is unavailable") from error
        if result.returncode != 0:
            raise ValueError("keychain entry was not found")
        try:
            value = result.stdout.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("keychain value is not UTF-8") from error
        # `security -w` always ends the password with a newline that is not part of it;
        # `secret-tool lookup` prints the secret exactly as stored.
        if platform.system() == "Darwin" and value.endswith("\n"):
            value = value[:-1]
        return value
    raise ValueError("unsupported reference kind")


def _read_windows_credential(target: str) -> str:
    """Read a Windows generic credential through CredReadW; the target is the literal SERVICE/ACCOUNT."""
    class Credential(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_uint32), ("type", ctypes.c_uint32),
            ("target", ctypes.c_wchar_p), ("comment", ctypes.c_wchar_p),
            ("last_written", ctypes.c_byte * 8), ("blob_size", ctypes.c_uint32),
            ("blob", ctypes.POINTER(ctypes.c_byte)), ("persist", ctypes.c_uint32),
            ("attribute_count", ctypes.c_uint32), ("attributes", ctypes.c_void_p),
            ("alias", ctypes.c_wchar_p), ("user_name", ctypes.c_wchar_p),
        ]

    credential = ctypes.POINTER(Credential)()
    advapi = ctypes.WinDLL("Advapi32.dll")
    if not advapi.CredReadW(target, 1, 0, ctypes.byref(credential)):
        raise ValueError("keychain entry was not found")
    try:
        return decode_credential_blob(ctypes.string_at(credential.contents.blob, credential.contents.blob_size))
    finally:
        advapi.CredFree(credential)


def decode_credential_blob(raw: bytes) -> str:
    """cmdkey and Control Panel store the password as UTF-16LE; other tools store UTF-8."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and "\0" not in text:
        return text
    try:
        return raw.decode("utf-16-le")
    except UnicodeDecodeError as error:
        raise ValueError("keychain value is neither UTF-8 nor UTF-16") from error


def staging_endpoint(plugin_root: str, tool_name: str, cwd: object, suffix: str) -> str:
    """Name the server the MCP call goes to, since only that server can redeem the handle."""
    server = tool_name[len("mcp__"):-len(suffix)]
    plugin_first = server.startswith(PLUGIN_SERVER_PREFIX)
    if plugin_first:
        server = server[len(PLUGIN_SERVER_PREFIX):]
    return discover_endpoint(
        DEFAULT_ENDPOINT,
        os.environ.get("HOME") or os.path.expanduser("~"),
        cwd if isinstance(cwd, str) and cwd else os.environ.get("PWD", os.getcwd()),
        plugin_root,
        server=server,
        plugin_first=plugin_first,
    )


def stage(endpoint: str, body: dict) -> str:
    """POST the value to the staging endpoint and return the handle, or raise with the server's reason."""
    result = subprocess.run(  # noqa: S603
        ["curl", "-sS", "--connect-timeout", "2", "--max-time", "10", "-H", "Content-Type: application/json", "-d", "@-", "-w", "\n%{http_code}", f"{endpoint}/api/secret-drops"],  # noqa: S607
        input=json.dumps(body).encode(),
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"could not reach {endpoint}")
    text, _, status = result.stdout.decode("utf-8", "replace").rpartition("\n")
    try:
        response = json.loads(text)
    except json.JSONDecodeError:
        response = {}
    if status != "200":
        # The server's validation messages name the problem (size, NUL byte) and never echo the value.
        message = response.get("error") if isinstance(response, dict) else None
        raise ValueError(f"Minions refused it: {message[:200]}" if isinstance(message, str) else f"staging request failed (HTTP {status})")
    handle = response.get("handle") if isinstance(response, dict) else None
    if not isinstance(handle, str):
        raise ValueError("staging response was invalid")
    return handle


def org_reach(tool_input: dict) -> str:
    """Which repositories an org secret will reach, as the confirmation prompt says it."""
    scope = tool_input.get("scope")
    if scope == "all":
        return "all repositories"
    if scope == "selected":
        labels = tool_input.get("repoLabels")
        count = len(set(labels)) if isinstance(labels, list) else 0
        return "1 repository" if count == 1 else f"{count} repositories"
    return "its current repositories"


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


def main(plugin_root: str) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    tool_name = payload.get("tool_name", payload.get("toolName", ""))
    tool_input = payload.get("tool_input", payload.get("toolInput", {}))
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict) or not tool_name.startswith("mcp__") or "minions" not in tool_name:
        return 0
    suffix = next((s for s in (REPO_TOOL_SUFFIX, ORG_TOOL_SUFFIX) if tool_name.endswith(s)), None)
    if suffix is None:
        return 0
    org = suffix == ORG_TOOL_SUFFIX
    repo_label = tool_input.get("repoLabel")
    kind = tool_input.get("kind")
    name = tool_input.get("name")
    if not isinstance(kind, str) or not isinstance(name, str) or (not org and not isinstance(repo_label, str)):
        deny(f"Could not resolve the secret reference: {'kind and name are' if org else 'repoLabel, kind, and name are'} required")
        return 0
    reference = tool_input.get("value")
    if not isinstance(reference, str) or not (reference.startswith(("env:", "file:", "keychain:"))):
        return 0
    # An org drop names no repository, and only set_org_secret can redeem it; a repo drop keeps
    # the body every earlier plugin version sent.
    body = {"target": "org", "kind": kind, "name": name} if org else {"repoLabel": repo_label, "kind": kind, "name": name}
    try:
        value = resolve(reference)
        endpoint = staging_endpoint(plugin_root, tool_name, payload.get("cwd"), suffix)
        handle = stage(endpoint, {**body, "value": value})
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        deny(f"Could not resolve {reference}: {error}")
        return 0
    # The prompt shows only the staged handle, so the reason is what tells the user which
    # local secret they are about to store, and where.
    if org:
        reason = f"Minions: store {reference} as {kind} org secret {name} ({org_reach(tool_input)}) at {endpoint}"
    else:
        reason = f"Minions: store {reference} as {kind} secret {name} on {repo_label} ({endpoint})"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask", "permissionDecisionReason": reason, "updatedInput": {**tool_input, "value": f"staged:{handle}"}}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
