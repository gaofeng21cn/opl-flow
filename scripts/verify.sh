#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

lane="${1:-core}"
case "$lane" in
  core|full) ;;
  *)
    printf 'Usage: scripts/verify.sh [core|full]\n' >&2
    exit 2
    ;;
esac

if [[ $# -gt 0 ]]; then shift; fi
if command -v uv >/dev/null 2>&1 && [[ -f "$repo_root/uv.lock" ]]; then
  exec uv run --frozen python scripts/verify.py "$lane" "$@"
elif [[ -x "$repo_root/.venv/bin/python" ]]; then
  exec "$repo_root/.venv/bin/python" scripts/verify.py "$lane" "$@"
else
  exec python3 scripts/verify.py "$lane" "$@"
fi
