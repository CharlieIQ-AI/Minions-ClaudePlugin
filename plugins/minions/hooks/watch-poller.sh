#!/usr/bin/env bash
# Runs hooks/watch_poller.py with the first Python that works (find-python.sh); silent and exit 0 without one.
# The monitor passes the plugin data folder as $1 (monitors/monitors.json).

set -u

# A parameter expansion rather than dirname: the hook must not depend on more of PATH than it needs.
HOOKS_DIR="${BASH_SOURCE[0]%[/\\]*}"  # either separator: Windows passes backslash paths
[[ "$HOOKS_DIR" != "${BASH_SOURCE[0]}" ]] || HOOKS_DIR=.
# shellcheck source=find-python.sh
source "$HOOKS_DIR/find-python.sh" 2>/dev/null || exit 0
[[ -n "${PYTHON:-}" ]] || exit 0

if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)" || exit 0
fi

exec "$PYTHON" "$PLUGIN_ROOT/hooks/watch_poller.py" "$@"
