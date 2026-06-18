#!/usr/bin/env python3
"""Install OPL Flow as a local Codex plugin and optional user profile."""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_NAME = "opl-flow"
PROFILE_NAMES = ("AGENTS.md", "TASTE.md")
PROMPT_NAMES = ("planner.md", "executor.md", "debugger.md", "verifier.md")
PLUGIN_REQUIRED_FILES = (
    ".codex-plugin/plugin.json",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "skills/risk-based-development-flow/SKILL.md",
    "skills/risk-based-development-flow/agents/openai.yaml",
    "skills/codex-ops-kit/SKILL.md",
    "skills/codex-ops-kit/agents/openai.yaml",
    "skills/codex-ops-kit/scripts/codex_ops_gate.py",
    "skills/codex-ops-kit/scripts/rho_wrapper.py",
    "skills/codex-ops-kit/references/lane-closeout.md",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "templates/prompts/planner.md",
    "templates/prompts/executor.md",
    "templates/prompts/debugger.md",
    "templates/prompts/verifier.md",
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_tree(repo_root: Path, plugins_dir: Path) -> Path:
    target = plugins_dir / PLUGIN_NAME
    if target.exists():
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns(".git", ".worktrees", ".pytest_cache", "__pycache__", ".DS_Store")
    shutil.copytree(repo_root, target, ignore=ignore)
    return target


def register_marketplace(marketplace_path: Path) -> None:
    marketplace = load_json(marketplace_path)
    marketplace.setdefault("name", "personal")
    marketplace.setdefault("interface", {"displayName": "Personal"})
    plugins = marketplace.setdefault("plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("marketplace plugins must be a list")

    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    plugins[:] = [item for item in plugins if not (isinstance(item, dict) and item.get("name") == PLUGIN_NAME)]
    plugins.append(entry)
    write_json(marketplace_path, marketplace)


def backup_and_copy(source: Path, target: Path, backup_root: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and filecmp.cmp(source, target, shallow=False):
        return False
    if target.exists():
        backup_target = backup_root / target.relative_to(target.anchor)
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_target)
    shutil.copy2(source, target)
    return True


def install_profile(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    templates = repo_root / "templates"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = codex_home / "backups" / PLUGIN_NAME / timestamp
    changed: list[str] = []

    for name in PROFILE_NAMES:
        if backup_and_copy(templates / name, codex_home / name, backup_root):
            changed.append(str(codex_home / name))
    prompts_dir = codex_home / "prompts"
    for name in PROMPT_NAMES:
        if backup_and_copy(templates / "prompts" / name, prompts_dir / name, backup_root):
            changed.append(str(prompts_dir / name))

    return {
        "changed": changed,
        "backup_root": str(backup_root) if backup_root.exists() else None,
    }


def install(
    repo_root: Path,
    plugins_dir: Path,
    marketplace_path: Path,
    codex_home: Path,
    profile: bool,
) -> dict[str, Any]:
    plugin_path = copy_tree(repo_root, plugins_dir)
    register_marketplace(marketplace_path)
    profile_result = install_profile(repo_root, codex_home) if profile else {"changed": [], "backup_root": None}
    return {
        "plugin_path": str(plugin_path),
        "marketplace_path": str(marketplace_path),
        "profile": profile_result,
    }


def verify(repo_root: Path, plugins_dir: Path, marketplace_path: Path, codex_home: Path, profile: bool) -> dict[str, Any]:
    plugin_path = plugins_dir / PLUGIN_NAME
    missing: list[str] = []
    for rel in PLUGIN_REQUIRED_FILES:
        if not (plugin_path / rel).exists():
            missing.append(str(plugin_path / rel))

    marketplace = load_json(marketplace_path)
    plugins = marketplace.get("plugins", [])
    marketplace_ok = any(isinstance(item, dict) and item.get("name") == PLUGIN_NAME for item in plugins)

    profile_mismatches: list[str] = []
    if profile:
        checks = [(repo_root / "templates" / name, codex_home / name) for name in PROFILE_NAMES]
        checks.extend((repo_root / "templates" / "prompts" / name, codex_home / "prompts" / name) for name in PROMPT_NAMES)
        for source, target in checks:
            if not target.exists() or not filecmp.cmp(source, target, shallow=False):
                profile_mismatches.append(str(target))

    ok = not missing and marketplace_ok and not profile_mismatches
    return {
        "ok": ok,
        "plugin_path": str(plugin_path),
        "required_files": list(PLUGIN_REQUIRED_FILES),
        "marketplace_ok": marketplace_ok,
        "missing": missing,
        "profile_mismatches": profile_mismatches,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install OPL Flow as a local Codex plugin")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--plugins-dir", default=str(Path.home() / "plugins"))
    parser.add_argument("--marketplace-path", default=str(Path.home() / ".agents" / "plugins" / "marketplace.json"))
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--no-profile", action="store_true", help="Install the plugin without syncing AGENTS.md and prompts.")
    parser.add_argument("--verify-only", action="store_true", help="Only verify an existing install.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    plugins_dir = Path(args.plugins_dir).expanduser().resolve()
    marketplace_path = Path(args.marketplace_path).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    profile = not args.no_profile

    if args.verify_only:
        result = verify(repo_root, plugins_dir, marketplace_path, codex_home, profile)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    result = install(repo_root, plugins_dir, marketplace_path, codex_home, profile)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
