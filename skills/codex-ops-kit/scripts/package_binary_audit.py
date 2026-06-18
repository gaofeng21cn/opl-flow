#!/usr/bin/env python3
"""Read-only JS package/CLI boundary audit for binary-backed packages."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run(cmd: list[str], limit: int = 12000) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
    except Exception as exc:  # noqa: BLE001 - audit should report, not crash
        return {"cmd": cmd, "error": str(exc)}
    return {"cmd": cmd, "returncode": proc.returncode, "stdout": proc.stdout[:limit], "stderr": proc.stderr[:limit]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", help="Directory containing package.json.")
    parser.add_argument("--symbols", default="", help="Comma-separated strings to search with strings(1).")
    parser.add_argument("--max-lines", type=int, default=80)
    args = parser.parse_args(argv)
    root = Path(args.package_root).expanduser()
    package_json = root / "package.json"
    data: dict[str, Any] = {}
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
    bins = data.get("bin", {})
    if isinstance(bins, str):
        bins = {data.get("name", "bin"): bins}
    optional = data.get("optionalDependencies", {}) if isinstance(data.get("optionalDependencies"), dict) else {}
    candidates: set[Path] = set()
    if isinstance(bins, dict):
        candidates.update(root / str(rel) for rel in bins.values())
    for folder in ("bin", "vendor"):
        path = root / folder
        if path.exists():
            candidates.update(item for item in path.rglob("*") if item.is_file())
    for package_name in optional:
        dep = root.parent / str(package_name)
        if dep.exists():
            candidates.update(item for item in dep.rglob("*") if item.is_file())
    file_cmd = shutil.which("file")
    strings_cmd = shutil.which("strings")
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    bin_paths = {root / str(rel) for rel in bins.values()} if isinstance(bins, dict) else set()
    report: dict[str, Any] = {
        "package_root": str(root),
        "name": data.get("name"),
        "version": data.get("version"),
        "bin": bins,
        "optionalDependencies": optional,
        "dependencies": data.get("dependencies", {}),
        "bin_files": [],
        "native_candidates": [],
    }
    for path in sorted(candidate for candidate in candidates if candidate.exists() and candidate.is_file()):
        entry: dict[str, Any] = {"path": str(path), "size": path.stat().st_size}
        if file_cmd:
            entry["file"] = run([file_cmd, str(path)], 4000)
        if strings_cmd and symbols:
            strings_out = run([strings_cmd, str(path)], 200000)
            hits: list[str] = []
            stdout = str(strings_out.get("stdout") or "")
            for line in stdout.splitlines():
                if any(symbol in line for symbol in symbols):
                    hits.append(line[:240])
                    if len(hits) >= args.max_lines:
                        break
            entry["symbol_hits"] = hits
            entry["strings_returncode"] = strings_out.get("returncode")
        if path in bin_paths:
            report["bin_files"].append(entry)
        else:
            report["native_candidates"].append(entry)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
