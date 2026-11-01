"""Resolve local attachment paths through the Minions upload-slot endpoint."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_ENDPOINT = "https://minions.charlieiq.ai"
PLUGIN_SERVER_PREFIX = "plugin_minions_"
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILE_COUNT = 5

MIME_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".zip": "application/zip",
}

# Importing the sibling module must not leave bytecode in the user's plugin directory.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from minions_endpoint import discover_endpoint  # noqa: E402


def attachment_endpoint(plugin_root: str, tool_name: str, cwd: object, suffix: str) -> str:
    """Find the endpoint for the MCP server named by the tool call."""
    server = tool_name[len("mcp__") : -len(suffix)]
    plugin_first = server.startswith(PLUGIN_SERVER_PREFIX)
    if plugin_first:
        server = server[len(PLUGIN_SERVER_PREFIX) :]
    return discover_endpoint(
        DEFAULT_ENDPOINT,
        os.environ.get("HOME") or os.path.expanduser("~"),
        cwd if isinstance(cwd, str) and cwd else os.environ.get("PWD", os.getcwd()),
        plugin_root,
        server=server,
        plugin_first=plugin_first,
    )


def curl_path() -> str:
    command = shutil.which("curl")
    if command is None:
        raise ValueError("curl is unavailable")
    return command


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def local_path(value: str, cwd: object) -> Path:
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded):
        return Path(expanded)
    base = cwd if isinstance(cwd, str) and cwd else os.environ.get("PWD", os.getcwd())
    return Path(base) / expanded


def upload_slot(endpoint: str, filename: str, mime_type: str, size_bytes: int, digest: str) -> tuple[str, str]:
    body = {"filename": filename, "mimeType": mime_type, "sizeBytes": size_bytes, "sha256": digest}
    result = subprocess.run(  # noqa: S603
        [
            curl_path(),
            "-sS",
            "--connect-timeout",
            "2",
            "--max-time",
            "10",
            "-H",
            "Content-Type: application/json",
            "-d",
            "@-",
            "-w",
            "\n%{http_code}",
            f"{endpoint}/api/mcp/uploads",
        ],
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
        if status == "429":
            raise ValueError("too many pending uploads from this address; wait a few minutes")
        message = response.get("error") if isinstance(response, dict) else None
        raise ValueError(
            f"Minions refused it: {message[:200]}"
            if isinstance(message, str)
            else f"upload slot request failed (HTTP {status})"
        )
    upload_id = response.get("uploadId") if isinstance(response, dict) else None
    upload_url = response.get("uploadUrl") if isinstance(response, dict) else None
    if not isinstance(upload_id, str) or not isinstance(upload_url, str):
        raise ValueError("upload slot response was invalid")
    return upload_id, upload_url


def put_bytes(upload_url: str, file_bytes: bytes, mime_type: str) -> None:
    result = subprocess.run(  # noqa: S603
        [
            curl_path(),
            "-sS",
            "-X",
            "PUT",
            "--connect-timeout",
            "2",
            "--max-time",
            "60",
            "--data-binary",
            "@-",
            "-H",
            f"Content-Type: {mime_type}",
            "-o",
            os.devnull,
            "-w",
            "%{http_code}",
            upload_url,
        ],
        input=file_bytes,
        capture_output=True,
        timeout=65,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("could not upload the file bytes")
    status = result.stdout.decode("ascii", "replace").strip()
    if not status.startswith("2"):
        raise ValueError(f"file upload failed (HTTP {status or 'unknown'})")


def rewrite_file(entry: dict, endpoint: str, cwd: object) -> tuple[dict, str]:
    path_value = entry.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("attachment path is required")
    path = local_path(path_value, cwd)
    try:
        file_bytes = path.read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError(f'could not read "{path_value}": {error}') from error
    if not file_bytes:
        raise ValueError(f'"{path_value}" is empty')
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f'"{path_value}" is over the 10 MB attachment limit')
    mime_type = MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise ValueError(f'"{path_value}" has an unsupported file type')
    filename = entry.get("filename") if isinstance(entry.get("filename"), str) else path.name
    digest = hashlib.sha256(file_bytes).hexdigest()
    upload_id, upload_url = upload_slot(endpoint, filename, mime_type, len(file_bytes), digest)
    put_bytes(upload_url, file_bytes, mime_type)
    rewritten = {"uploadId": upload_id, "filename": filename, "sha256": digest}
    if "agentAccess" in entry:
        rewritten["agentAccess"] = entry["agentAccess"]
    return rewritten, f"{filename} ({len(file_bytes) / 1024:.0f} KB)"


def main(plugin_root: str) -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    tool_name = payload.get("tool_name", payload.get("toolName", ""))
    tool_input = payload.get("tool_input", payload.get("toolInput", {}))
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return 0
    suffix = next(
        (candidate for candidate in ("__attach_files", "__create_task", "__create_feature") if tool_name.endswith(candidate)),
        None,
    )
    if suffix is None or re.fullmatch(r"mcp__.*minions.*__(attach_files|create_task|create_feature)", tool_name) is None:
        return 0
    files = tool_input.get("files")
    if not isinstance(files, list) or not any(isinstance(entry, dict) and "path" in entry for entry in files):
        return 0
    urls = tool_input.get("urls")
    source_count = len(files) + len(urls) if isinstance(urls, list) else len(files)
    if source_count > MAX_FILE_COUNT:
        sixth = files[MAX_FILE_COUNT] if len(files) > MAX_FILE_COUNT else next((entry for entry in files if isinstance(entry, dict) and isinstance(entry.get("path"), str)), None)
        name = sixth.get("path") if isinstance(sixth, dict) and isinstance(sixth.get("path"), str) else "the sixth file"
        deny(f'Cannot attach more than {MAX_FILE_COUNT} files in one call; check "{name}"')
        return 0

    cwd = payload.get("cwd")
    try:
        endpoint = attachment_endpoint(plugin_root, tool_name, cwd, suffix)
        rewritten_files = []
        descriptions = []
        for entry in files:
            if not isinstance(entry, dict) or "path" not in entry:
                rewritten_files.append(entry)
                continue
            rewritten, description = rewrite_file(entry, endpoint, cwd)
            rewritten_files.append(rewritten)
            descriptions.append(description)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        deny(f"Could not attach local file: {error}")
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": f"Minions: upload {len(descriptions)} file(s) to {endpoint}: {', '.join(descriptions)}",
                    "updatedInput": {**tool_input, "files": rewritten_files},
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
