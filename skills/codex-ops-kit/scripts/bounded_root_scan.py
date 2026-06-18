#!/usr/bin/env python3
"""Read-only bounded root budget before broad search or cleanup."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    "__pycache__",
    ".cache",
    "archived_sessions",
    "build",
    "dist",
    "node_modules",
    "sessions",
    "shell_snapshots",
}


def scan(root: Path, max_depth: int, max_entries: int, excludes: set[str], top: int) -> dict[str, object]:
    root = root.expanduser()
    base_depth = len(root.parts)
    total_bytes = 0
    files = 0
    dirs = 0
    entries = 0
    skipped: list[dict[str, str]] = []
    largest: list[tuple[int, str]] = []
    if not root.exists():
        return {"root": str(root), "exists": False, "files_seen": 0, "dirs_seen": 0, "bytes_seen": 0, "largest_files": [], "skipped_sample": []}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        entries += 1
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        if entries >= max_entries:
            skipped.append({"path": str(current_path), "reason": "max_entries"})
            dirnames[:] = []
            continue
        pruned = [name for name in dirnames if name in excludes or depth >= max_depth]
        skipped.extend({"path": str(current_path / name), "reason": "exclude_or_depth"} for name in pruned[:50])
        dirnames[:] = [name for name in dirnames if name not in excludes and depth < max_depth]
        dirs += len(dirnames)
        for filename in filenames:
            path = current_path / filename
            try:
                stat = path.lstat()
            except OSError:
                continue
            files += 1
            total_bytes += stat.st_size
            largest.append((stat.st_size, str(path)))
            if len(largest) > max(top * 5, 100):
                largest = sorted(largest, reverse=True)[: max(top * 2, 50)]
    largest = sorted(largest, reverse=True)[:top]
    return {
        "root": str(root),
        "exists": True,
        "files_seen": files,
        "dirs_seen": dirs,
        "bytes_seen": total_bytes,
        "largest_files": [{"bytes": size, "path": path} for size, path in largest],
        "skipped_sample": skipped[:50],
        "truncated": entries >= max_entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-entries", type=int, default=20000)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    excludes = DEFAULT_EXCLUDES | set(args.exclude)
    result = [scan(Path(root), args.max_depth, args.max_entries, excludes, args.top) for root in args.roots]
    print(json.dumps({"excludes": sorted(excludes), "roots": result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
