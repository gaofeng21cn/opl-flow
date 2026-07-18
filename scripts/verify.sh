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

python3 scripts/verify.py "$lane"
