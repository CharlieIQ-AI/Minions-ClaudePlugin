"""Discover the Minions web endpoint from Claude Code configuration."""

from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


def _normalize_server(name: str) -> str:
    """Claude Code builds tool names from server names with non-word characters as underscores."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _server_url(servers: object, server: str) -> str | None:
    if not isinstance(servers, dict):
        return None
    wanted = _normalize_server(server)
    for key, config in servers.items():
        if isinstance(key, str) and _normalize_server(key) == wanted and isinstance(config, dict):
            url = config.get("url")
            return url if isinstance(url, str) else None
    return None


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _endpoint_from_url(value: str | None) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"https?://\S+", value):
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    # Plain http only reaches a server on this machine; anywhere else a secret would cross the network in clear.
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname or ""):
        return None
    endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    if endpoint.endswith("/api/mcp"):
        endpoint = endpoint[: -len("/api/mcp")].rstrip("/")
    return endpoint or None


def _read_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _same_path(left: str, right: str) -> bool:
    def norm(path: str) -> str:
        return path.replace("\\", "/").rstrip("/").lower()

    return norm(left) == norm(right)


def _project_entry(user_config: dict, cwd: str) -> dict:
    projects = user_config.get("projects")
    if isinstance(projects, dict):
        for path, project in projects.items():
            if isinstance(project, dict) and _same_path(path, cwd):
                return project
    return {}


def _names(value: object) -> set[str]:
    return {_normalize_server(item) for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _project_server_approved(project: dict, home: str, server: str) -> bool:
    """Approval lives only in the user's own files, which a cloned repository cannot write."""
    wanted = _normalize_server(server)
    if wanted in _names(project.get("disabledMcpjsonServers")):
        return False
    if wanted in _names(project.get("enabledMcpjsonServers")):
        return True
    return bool(home) and _read_json(Path(home) / ".claude" / "settings.json").get("enableAllProjectMcpServers") is True


def _candidate_urls(home: str, cwd: str, plugin_root: str, server: str, plugin_first: bool):
    """Yield configured URLs in Claude Code's precedence: local, project, user, then the plugin's own."""
    plugin_url = _server_url(_read_json(Path(plugin_root) / ".mcp.json").get("mcpServers"), server) if plugin_root else None
    if plugin_first:
        yield plugin_url
    user_config = _read_json(Path(home) / ".claude.json") if home else {}
    if cwd:
        project = _project_entry(user_config, cwd)
        yield _server_url(project.get("mcpServers"), server)
        # A repository's own .mcp.json is attacker-controlled until the user approves its server,
        # and Claude Code does not connect to an unapproved one, so neither may this.
        if _project_server_approved(project, home, server):
            yield _server_url(_read_json(Path(cwd) / ".mcp.json").get("mcpServers"), server)
    yield _server_url(user_config.get("mcpServers"), server)
    if not plugin_first:
        yield plugin_url


def discover_endpoint(
    fallback: str,
    home: str,
    cwd: str,
    plugin_root: str = "",
    server: str = "minions",
    plugin_first: bool = False,
) -> str:
    """Return the endpoint of the configured Minions MCP server, or the fallback.

    A secret staged on one server can only be redeemed on that server, so this must name the
    server the MCP call itself goes to. A plugin-provided server (plugin_first) reads the plugin's
    own .mcp.json; a server the user configured is found in local, approved project, then user scope.
    """
    for url in _candidate_urls(home, cwd, plugin_root, server, plugin_first):
        endpoint = _endpoint_from_url(url)
        if endpoint:
            return endpoint
    return fallback


if __name__ == "__main__":
    fallback, home, cwd, *plugin_root = sys.argv[1:]
    print(discover_endpoint(fallback, home, cwd, plugin_root[0] if plugin_root else ""))
