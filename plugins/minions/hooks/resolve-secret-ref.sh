#!/usr/bin/env bash

set -u

# A parameter expansion rather than dirname: the hook must not depend on more of PATH than it needs.
HOOKS_DIR="${BASH_SOURCE[0]%[/\\]*}"  # either separator: Windows passes backslash paths
[[ "$HOOKS_DIR" != "${BASH_SOURCE[0]}" ]] || HOOKS_DIR=.
# shellcheck source=find-python.sh
source "$HOOKS_DIR/find-python.sh" 2>/dev/null || exit 0
[[ -n "${PYTHON:-}" ]] || exit 0
command -v curl >/dev/null 2>&1 || exit 0

if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)" || exit 0
fi

exec "$PYTHON" "$PLUGIN_ROOT/hooks/resolve_secret_ref.py" "$PLUGIN_ROOT"
