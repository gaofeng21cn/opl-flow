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
MERGE_PACKET_SCHEMA = "opl_flow_profile_merge_packet.v1"
PLUGIN_REQUIRED_FILES = (
    ".codex-plugin/plugin.json",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "skills/risk-based-development-flow/SKILL.md",
    "skills/risk-based-development-flow/agents/openai.yaml",
    "skills/codex-ops-kit/SKILL.md",
    "skills/codex-ops-kit/agents/openai.yaml",
    "skills/codex-ops-kit/scripts/codex_ops_gate.py",
    "skills/codex-ops-kit/scripts/worktree_absorption_audit.py",
    "skills/codex-ops-kit/scripts/release_url_audit.py",
    "skills/codex-ops-kit/references/lane-closeout.md",
    "skills/codex-ops-kit/references/release-currentness.md",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
    "profile/modules/02-role-baseline.md",
    "profile/modules/03-workflow-core.md",
    "profile/modules/04-guardrails.md",
    "profile/modules/05-ops-authority-core.md",
    "profile/modules/06-capability-adapters.md",
    "profile/modules/07-tool-preferences.md",
    "profile/modules/08-managed-block-policy.md",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "templates/prompts/planner.md",
    "templates/prompts/executor.md",
    "templates/prompts/debugger.md",
    "templates/prompts/verifier.md",
    "scripts/intelligence_enhancement.py",
    "scripts/profile_compose.py",
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


def profile_checks(repo_root: Path, codex_home: Path) -> list[tuple[Path, Path]]:
    templates = repo_root / "templates"
    checks = [(templates / name, codex_home / name) for name in PROFILE_NAMES]
    checks.extend((templates / "prompts" / name, codex_home / "prompts" / name) for name in PROMPT_NAMES)
    return checks


def profile_is_current(repo_root: Path, codex_home: Path) -> bool:
    for source, target in profile_checks(repo_root, codex_home):
        if not target.exists() or not filecmp.cmp(source, target, shallow=False):
            return False
    return True


def tree_mismatches(source: Path, target: Path, label: str) -> list[str]:
    source_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    target_files = {path.relative_to(target) for path in target.rglob("*") if path.is_file()} if target.exists() else set()
    mismatches = [f"missing:{label}/{path}" for path in sorted(source_files - target_files)]
    mismatches.extend(f"unexpected:{label}/{path}" for path in sorted(target_files - source_files))
    mismatches.extend(
        f"content:{label}/{path}"
        for path in sorted(source_files & target_files)
        if not filecmp.cmp(source / path, target / path, shallow=False)
    )
    return mismatches


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_candidate_profile(repo_root: Path, packet: Path) -> None:
    templates = repo_root / "templates"
    candidate = packet / "candidate"
    for name in PROFILE_NAMES:
        copy_if_exists(templates / name, candidate / name)
    for name in PROMPT_NAMES:
        copy_if_exists(templates / "prompts" / name, candidate / "prompts" / name)
    copy_if_exists(repo_root / "profile" / "manifest.json", candidate / "profile" / "manifest.json")
    modules_root = repo_root / "profile" / "modules"
    if modules_root.exists():
        shutil.copytree(modules_root, candidate / "profile" / "modules", dirs_exist_ok=True)


def copy_existing_profile(codex_home: Path, packet: Path) -> list[str]:
    copied: list[str] = []
    existing = packet / "existing"
    for name in PROFILE_NAMES:
        if copy_if_exists(codex_home / name, existing / name):
            copied.append(name)
    for name in PROMPT_NAMES:
        rel = f"prompts/{name}"
        if copy_if_exists(codex_home / "prompts" / name, existing / rel):
            copied.append(rel)
    return copied


def merge_prompt() -> str:
    return """# OPL Flow profile semantic merge

You are Codex performing a semantic merge for an OPL Flow user profile install.

Read these inputs:

- `existing/AGENTS.md` and any other files under `existing/`
- `candidate/AGENTS.md`
- `candidate/TASTE.md`
- `candidate/prompts/*.md`
- `candidate/profile/manifest.json`
- `candidate/profile/modules/*.md`

Rules:

1. Do not mechanically concatenate the files.
2. Preserve user-specific preferences and local machine rules unless they clearly conflict with higher-priority user instructions.
3. Keep `TASTE.md` as the principles layer, not as an optional preference sample.
4. Keep `AGENTS.md` focused on workflow, guardrails, capability adapters, tool preferences, and managed block policy.
5. Do not hardcode project/domain instance facts into the user-level `AGENTS.md`; route them to the owning repo `AGENTS.md`, docs, contracts, runtime/readback, or explicit context overlay.
6. Preserve official marker blocks and managed tool blocks unless the corresponding tool is confirmed retired.
7. Preserve OPL Flow's risk, verifier, fresh-evidence, root-cause, ops, and completion-audit guardrails.
8. Preserve capability adapters such as RTK, CodeGraph, MinerU, agent-browser, Superpowers, and Ponytail as adapters, not project facts.
9. Report any unresolved conflict instead of silently deleting or weakening behavior.

Write outputs under `output/`:

- `output/AGENTS.md`: merged user-level AGENTS profile
- `output/TASTE.md`: merged or selected TASTE principles file
- `output/prompts/*.md`: selected prompt files if changes are needed
- `output/merge-report.md`: what was preserved, changed, rejected, and why

Do not apply the merge directly to `~/.codex`. The installer or operator will
review and apply the output after this semantic merge is complete.
"""


def create_merge_packet(repo_root: Path, codex_home: Path, reason: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    packet = codex_home / "state" / PLUGIN_NAME / "profile-merge" / timestamp
    packet.mkdir(parents=True, exist_ok=False)
    copied_existing = copy_existing_profile(codex_home, packet)
    copy_candidate_profile(repo_root, packet)
    (packet / "output").mkdir()
    (packet / "prompt.md").write_text(merge_prompt(), encoding="utf-8")

    plan = {
        "schema": MERGE_PACKET_SCHEMA,
        "created_at": timestamp,
        "plugin": PLUGIN_NAME,
        "reason": reason,
        "status": "requires_codex_semantic_merge",
        "existing_files": copied_existing,
        "candidate_profile": "candidate/AGENTS.md",
        "candidate_manifest": "candidate/profile/manifest.json",
        "prompt": "prompt.md",
        "output_dir": "output",
        "apply_policy": "review_codex_output_then_apply_with_backup",
        "script_merge_policy": "disabled",
    }
    write_json(packet / "merge-plan.json", plan)
    return {
        "status": "requires_codex_semantic_merge",
        "changed": [],
        "backup_root": None,
        "merge_packet": str(packet),
        "reason": reason,
    }


def install_profile(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    templates = repo_root / "templates"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = codex_home / "backups" / PLUGIN_NAME / timestamp
    changed: list[str] = []

    agents_path = codex_home / "AGENTS.md"
    if agents_path.exists():
        if profile_is_current(repo_root, codex_home):
            return {
                "status": "current",
                "changed": [],
                "backup_root": None,
            }
        return create_merge_packet(
            repo_root,
            codex_home,
            "existing_user_agents_requires_codex_semantic_merge",
        )

    for name in PROFILE_NAMES:
        if backup_and_copy(templates / name, codex_home / name, backup_root):
            changed.append(str(codex_home / name))
    prompts_dir = codex_home / "prompts"
    for name in PROMPT_NAMES:
        if backup_and_copy(templates / "prompts" / name, prompts_dir / name, backup_root):
            changed.append(str(prompts_dir / name))

    return {
        "status": "installed",
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
    profile_result = install_profile(repo_root, codex_home) if profile else {"status": "skipped", "changed": [], "backup_root": None}
    return {
        "plugin_path": str(plugin_path),
        "marketplace_path": str(marketplace_path),
        "profile": profile_result,
    }


def latest_merge_packet(codex_home: Path) -> str | None:
    root = codex_home / "state" / PLUGIN_NAME / "profile-merge"
    if not root.exists():
        return None
    packets = sorted(path for path in root.iterdir() if path.is_dir())
    return str(packets[-1]) if packets else None


def verify_profile(repo_root: Path, codex_home: Path, profile: bool) -> dict[str, Any]:
    if not profile:
        return {
            "status": "skipped",
            "mismatches": [],
            "merge_packet": None,
        }
    agents_path = codex_home / "AGENTS.md"
    if agents_path.exists() and profile_is_current(repo_root, codex_home):
        return {
            "status": "current",
            "mismatches": [],
            "merge_packet": None,
        }
    if agents_path.exists():
        return {
            "status": "merge_required",
            "mismatches": [],
            "merge_packet": latest_merge_packet(codex_home),
        }

    mismatches: list[str] = []
    for source, target in profile_checks(repo_root, codex_home):
        if not target.exists() or not filecmp.cmp(source, target, shallow=False):
            mismatches.append(str(target))
    return {
        "status": "missing" if mismatches else "current",
        "mismatches": mismatches,
        "merge_packet": None,
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

    source_ops_skill = repo_root / "skills" / "codex-ops-kit"
    plugin_mismatches = tree_mismatches(
        source_ops_skill,
        plugin_path / "skills" / "codex-ops-kit",
        "skills/codex-ops-kit",
    )
    local_ops_skill = codex_home / "skills" / "codex-ops-kit"
    local_skill_mismatches = (
        tree_mismatches(source_ops_skill, local_ops_skill, "skills/codex-ops-kit")
        if local_ops_skill.exists()
        else []
    )

    profile_result = verify_profile(repo_root, codex_home, profile)
    profile_mismatches = list(profile_result["mismatches"])

    ok = (
        not missing
        and not plugin_mismatches
        and not local_skill_mismatches
        and marketplace_ok
        and not profile_mismatches
        and profile_result["status"] in {"current", "skipped"}
    )
    return {
        "ok": ok,
        "plugin_path": str(plugin_path),
        "required_files": list(PLUGIN_REQUIRED_FILES),
        "marketplace_ok": marketplace_ok,
        "missing": missing,
        "plugin_mismatches": plugin_mismatches,
        "local_skill_mismatches": local_skill_mismatches,
        "profile_status": profile_result["status"],
        "profile_mismatches": profile_mismatches,
        "profile_merge_packet": profile_result["merge_packet"],
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
