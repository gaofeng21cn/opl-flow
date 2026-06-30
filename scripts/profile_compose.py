#!/usr/bin/env python3
"""Compose the OPL Flow user AGENTS.md profile from profile modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path("profile/manifest.json")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def compose(repo_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> str:
    manifest_file = repo_root / manifest_path
    manifest = load_json(manifest_file)
    modules = manifest.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError(f"{manifest_file} must define a non-empty modules list")

    rendered: list[str] = []
    seen: set[str] = set()
    for module in modules:
        if not isinstance(module, dict):
            raise ValueError("profile modules must be objects")
        module_id = module.get("id")
        module_path = module.get("path")
        enabled = module.get("default", True)
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("profile module id is required")
        if module_id in seen:
            raise ValueError(f"duplicate profile module id: {module_id}")
        seen.add(module_id)
        if enabled is False:
            continue
        if not isinstance(module_path, str) or not module_path:
            raise ValueError(f"profile module {module_id} path is required")
        path = repo_root / module_path
        if not path.exists():
            raise FileNotFoundError(f"profile module missing: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if text:
            rendered.append(text)
    return "\n\n".join(rendered).rstrip() + "\n"


def rendered_path(repo_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> Path:
    manifest = load_json(repo_root / manifest_path)
    rendered = manifest.get("rendered", "templates/AGENTS.md")
    if not isinstance(rendered, str) or not rendered:
        raise ValueError("profile manifest rendered path must be a string")
    return repo_root / rendered


def check(repo_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    target = rendered_path(repo_root, manifest_path)
    expected = compose(repo_root, manifest_path)
    actual = target.read_text(encoding="utf-8") if target.exists() else None
    return {
        "ok": actual == expected,
        "target": str(target),
        "exists": target.exists(),
        "expected_bytes": len(expected.encode("utf-8")),
        "actual_bytes": len(actual.encode("utf-8")) if actual is not None else None,
    }


def write(repo_root: Path, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    target = rendered_path(repo_root, manifest_path)
    expected = compose(repo_root, manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    changed = target.read_text(encoding="utf-8") if target.exists() else None
    target.write_text(expected, encoding="utf-8")
    return {
        "ok": True,
        "target": str(target),
        "changed": changed != expected,
        "bytes": len(expected.encode("utf-8")),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compose OPL Flow AGENTS.md from profile modules")
    parser.add_argument("mode", choices=("check", "write"), nargs="?", default="check")
    parser.add_argument("--repo-root", default=str(repo_root_from_script()))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest = Path(args.manifest)
    result = write(repo_root, manifest) if args.mode == "write" else check(repo_root, manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
