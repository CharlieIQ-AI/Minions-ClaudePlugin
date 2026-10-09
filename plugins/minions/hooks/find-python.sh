# Sourced by the hook scripts. Sets PYTHON to the first interpreter that actually runs, or "".
#
# On Windows `python3` is often the Microsoft Store placeholder: it is on PATH but exits
# without running anything, so finding it is not enough.
# shellcheck shell=bash disable=SC2034  # PYTHON is read by the scripts that source this.
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
