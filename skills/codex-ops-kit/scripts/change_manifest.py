#!/usr/bin/env python3
"""Preflight and audit transaction manifests for multi-file changes."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]


TEMPLATE = {
    "purpose": "short human-readable change purpose",
    "forbidden_scope": ["paths or behaviors that must not change"],
    "targets": [
        {
            "path": "relative/path.ext",
            "expected_transform": "what will change in this file",
            "parse": "none|json|toml|python_ast",
            "must_contain": ["literal or regex:pattern expected before/after"],
            "must_not_contain": ["literal or regex:pattern forbidden before/after"],
            "validation": ["command to run after this file or batch"],
        }
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"manifest must be JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise SystemExit("manifest must contain an object with a targets list")
    return data


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def parse_file(path: Path, mode: str) -> str:
    if mode in {"", "none"}:
        return "skipped"
    text = read_text(path)
    if mode == "json":
        json.loads(text)
    elif mode == "toml":
        if tomllib is None:
            raise RuntimeError("tomllib is unavailable in this Python")
        tomllib.loads(text)
    elif mode == "python_ast":
        ast.parse(text, filename=str(path))
    else:
        raise RuntimeError(f"unknown parse mode: {mode}")
    return "ok"


def pattern_present(text: str, pattern: str) -> bool:
    if pattern.startswith("regex:"):
        return re.search(pattern[len("regex:") :], text, re.MULTILINE) is not None
    return pattern in text


def git_status(repo: Path, path: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "status", "--short", "--", path], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return f"git status failed: {proc.stderr.strip()}"
    return proc.stdout.strip()


def check_target(repo: Path, target: dict[str, Any]) -> dict[str, Any]:
    rel = target.get("path")
    if not rel:
        return {"error": "target missing path", "target": target}
    path = (repo / rel).resolve()
    try:
        path.relative_to(repo)
    except ValueError:
        return {"path": rel, "error": "target path escapes repo"}
    item: dict[str, Any] = {
        "path": rel,
        "exists": path.exists(),
        "expected_transform": target.get("expected_transform"),
        "parse": target.get("parse", "none"),
        "validation": target.get("validation", []),
    }
    if not path.exists() or not path.is_file():
        item["error"] = "missing file"
        return item
    text = read_text(path)
    item["sha256"] = sha256(path)
    item["line_count"] = text.count("\n") + (1 if text else 0)
    try:
        item["parse_result"] = parse_file(path, str(target.get("parse", "none")))
    except Exception as exc:
        item["parse_error"] = str(exc)
    missing = [str(p) for p in target.get("must_contain", []) if not pattern_present(text, str(p))]
    forbidden = [str(p) for p in target.get("must_not_contain", []) if pattern_present(text, str(p))]
    if missing:
        item["missing_required_patterns"] = missing
    if forbidden:
        item["forbidden_patterns_present"] = forbidden
    item["git_status"] = git_status(repo, str(rel))
    return item


def command_template(_args: argparse.Namespace) -> int:
    print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def command_check(args: argparse.Namespace) -> int:
    repo = Path(args.repo).expanduser().resolve()
    manifest = load_manifest(Path(args.manifest).expanduser())
    targets = [check_target(repo, target) for target in manifest["targets"]]
    report = {
        "mode": args.command,
        "repo": str(repo),
        "manifest": str(Path(args.manifest).expanduser().resolve()),
        "purpose": manifest.get("purpose"),
        "forbidden_scope": manifest.get("forbidden_scope", []),
        "targets": targets,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    failed = any(
        item.get("error")
        or item.get("parse_error")
        or item.get("missing_required_patterns")
        or item.get("forbidden_patterns_present")
        for item in targets
    )
    return 2 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Print a JSON manifest template.")
    template.set_defaults(func=command_template)
    for name in ("preflight", "status"):
        cmd = sub.add_parser(name, help=f"{name} current files against a manifest.")
        cmd.add_argument("--repo", default=".")
        cmd.add_argument("--manifest", required=True)
        cmd.set_defaults(func=command_check)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
