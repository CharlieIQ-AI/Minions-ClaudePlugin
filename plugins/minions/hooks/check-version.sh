#!/usr/bin/env bash

set -u

if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)" || exit 0
fi

DATA_DIR="${CLAUDE_PLUGIN_DATA:-${HOME:-$PLUGIN_ROOT}/.claude/plugins/minions}"
CACHE_FILE="$DATA_DIR/version-check.json"
DEFAULT_ENDPOINT="https://minions.charlieiq.ai"

command -v python3 >/dev/null 2>&1 || exit 0
command -v curl >/dev/null 2>&1 || exit 0

installed_version() {
  python3 - "$PLUGIN_ROOT/.claude-plugin/plugin.json" <<'PY' 2>/dev/null
import json
import re
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        version = json.load(handle).get("version")
    if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(version)
except Exception:
    pass
PY
}

discover_endpoint() {
  python3 - "$DEFAULT_ENDPOINT" "${HOME:-}" "$PWD" <<'PY' 2>/dev/null
import json
import re
import sys
from urllib.parse import urlsplit

fallback, home, cwd = sys.argv[1:]
for path in (f"{home}/.claude.json", f"{cwd}/.mcp.json"):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle).get("mcpServers", {}).get("minions", {}).get("url")
        if not isinstance(value, str) or not re.match(r"^https?://", value):
            continue
        if any(character.isspace() for character in value):
            continue
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if endpoint.endswith("/api/mcp"):
            endpoint = endpoint[: -len("/api/mcp")].rstrip("/")
        if endpoint:
            print(endpoint)
            break
    except Exception:
        continue
else:
    print(fallback)
PY
}

read_cache() {
  python3 - "$CACHE_FILE" <<'PY' 2>/dev/null
import json
import re
import sys
import time

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        cache = json.load(handle)
    checked_at = cache.get("checked_at")
    served_version = cache.get("served_version")
    now = int(time.time())
    if (
        isinstance(checked_at, int)
        and not isinstance(checked_at, bool)
        and now - checked_at < 86400
        and checked_at <= now + 60
        and isinstance(served_version, str)
        and re.fullmatch(r"\d+\.\d+\.\d+", served_version)
    ):
        print(served_version)
except Exception:
    pass
PY
}

write_cache() {
  mkdir -p "$DATA_DIR" 2>/dev/null || true
  python3 - "$CACHE_FILE" "$1" <<'PY' 2>/dev/null || true
import json
import sys
import time

try:
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump({"checked_at": int(time.time()), "served_version": sys.argv[2]}, handle)
except Exception:
    pass
PY
}

semver_lt() {
  python3 - "$1" "$2" <<'PY' 2>/dev/null
import sys

try:
    def version_tuple(value):
        core = value.split("-", 1)[0].split("+", 1)[0]
        return tuple(int(part) for part in core.split("."))

    raise SystemExit(0 if version_tuple(sys.argv[1]) < version_tuple(sys.argv[2]) else 1)
except Exception:
    raise SystemExit(1)
PY
}

installed="$(installed_version)"
[[ -n "$installed" ]] || exit 0

served="$(read_cache)"
if [[ -z "$served" ]]; then
  endpoint="$(discover_endpoint)"
  body="$(curl -fsS --connect-timeout 2 --max-time 2 -H 'Accept: application/json' "$endpoint/api/plugin/version" 2>/dev/null)" || exit 0
  served="$(BODY="$body" python3 - <<'PY' 2>/dev/null
import json
import os
import re

try:
    version = json.loads(os.environ["BODY"]).get("version")
    if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(version)
except Exception:
    pass
PY
)"
  [[ -n "$served" ]] || exit 0
  write_cache "$served"
fi

semver_lt "$installed" "$served" || exit 0

python3 - "$installed" "$served" <<'PY' 2>/dev/null
import json
import sys

installed, served = sys.argv[1:]
message = (
    f'Minions plugin {served} is available (you have {installed}). '
    'Run: claude plugin update minions@minions — then /reload-plugins. '
    'Or say "update the minions plugin" and I will run it for you.'
)
context = (
    f"Minions plugin version check: installed {installed}, available {served}. "
    'If the user asks to update the plugin or accepts this notice, run exactly: '
    'claude plugin update minions@minions — then tell them to run /reload-plugins '
    'or start a new session. Do not run it unasked.'
)
print(json.dumps({
    "systemMessage": message,
    "additionalContext": context,
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    },
}, ensure_ascii=False, separators=(",", ":")))
PY

exit 0
