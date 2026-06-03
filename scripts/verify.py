#!/usr/bin/env python3
"""Repository smoke checks for OPL Flow."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_FILES = (
    ".codex-plugin/plugin.json",
    "README.md",
    "docs/new-machine-codex-setup.md",
    "LICENSE",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "templates/prompts/planner.md",
    "templates/prompts/executor.md",
    "templates/prompts/debugger.md",
    "templates/prompts/verifier.md",
    "scripts/install_local_plugin.py",
    "scripts/repo_profile.py",
)


def check_required_files(repo_root: Path) -> list[str]:
    return [rel for rel in REQUIRED_FILES if not (repo_root / rel).exists()]


def check_plugin_json(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "opl-flow":
        errors.append("plugin name must be opl-flow")
    if manifest.get("skills") != "./skills/":
        errors.append("plugin skills path must be ./skills/")
    if not manifest.get("interface", {}).get("defaultPrompt"):
        errors.append("interface.defaultPrompt is required")
    return errors


def check_install(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "install_local_plugin.py"),
            "--repo-root",
            str(repo_root),
            "--plugins-dir",
            str(tmp_path / "plugins"),
            "--marketplace-path",
            str(tmp_path / "marketplace.json"),
            "--codex-home",
            str(tmp_path / "codex"),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        verify_cmd = cmd + ["--verify-only"]
        result = subprocess.run(verify_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            errors.append(f"install verify failed: {result.stdout} {result.stderr}".strip())
    return errors


def check_repo_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "target-repo"
        repo.mkdir()
        (repo / "AGENTS.md").write_text("# Target\n\nLocal rule.\n", encoding="utf-8")
        (repo / "TASTE.md").write_text("# Taste\n\nLocal preference.\n", encoding="utf-8")
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "repo_profile.py"),
            "sync",
            "--repo-root",
            str(repo),
            "--apply",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        check_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "repo_profile.py"),
            "check",
            "--repo-root",
            str(repo),
        ]
        result = subprocess.run(check_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            errors.append(f"repo profile check failed: {result.stdout} {result.stderr}".strip())
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    errors.extend(f"missing {rel}" for rel in check_required_files(repo_root))
    errors.extend(check_plugin_json(repo_root))
    errors.extend(check_install(repo_root))
    errors.extend(check_repo_profile(repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OPL Flow verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
