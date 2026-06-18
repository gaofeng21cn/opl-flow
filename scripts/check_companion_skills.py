#!/usr/bin/env python3
"""Check companion skill availability for the OPL Flow profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


SUPERPOWERS_SKILLS = (
    "using-superpowers",
    "systematic-debugging",
    "verification-before-completion",
    "test-driven-development",
    "using-git-worktrees",
)

OPL_FLOW_NATIVE_SKILLS = (
    "risk-based-development-flow",
    "codex-ops-kit",
)

OPTIONAL_SKILLS = (
    "agent-browser",
    "mineru-document-extractor",
)


def default_skill_roots(home: Path, codex_home: Path, plugins_dir: Path) -> list[Path]:
    roots = [
        codex_home / "skills",
        home / ".agents" / "skills",
        home / ".skills-manager" / "skills",
    ]
    packaged_skills_root = os.environ.get("OPL_PACKAGED_SKILLS_ROOT", "").strip()
    if packaged_skills_root:
        roots.append(Path(packaged_skills_root).expanduser())
    full_runtime_home = os.environ.get("OPL_FULL_RUNTIME_HOME", "").strip()
    if full_runtime_home:
        roots.append(Path(full_runtime_home).expanduser() / "skills")
    plugins_root = plugins_dir.expanduser()
    if plugins_root.exists():
        roots.extend(plugin / "skills" for plugin in sorted(plugins_root.iterdir()) if plugin.is_dir())
    plugin_cache = codex_home / "plugins" / "cache"
    if plugin_cache.exists():
        roots.extend(sorted(path for path in plugin_cache.glob("*/*/*/skills") if path.is_dir()))
    seen: set[Path] = set()
    unique_roots: list[Path] = []
    for root in roots:
        normalized = root.expanduser()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_roots.append(normalized)
    return unique_roots


def skill_exists(root: Path, skill_id: str) -> bool:
    return (root / skill_id / "SKILL.md").exists()


def superpowers_bundle_status(root: Path) -> dict[str, Any]:
    skills_root = root / "skills"
    plugin_manifest = root / ".codex-plugin" / "plugin.json"
    present = [skill for skill in SUPERPOWERS_SKILLS if skill_exists(skills_root, skill)]
    return {
        "root": str(root),
        "plugin_manifest": plugin_manifest.exists(),
        "present_skills": present,
        "missing_skills": [skill for skill in SUPERPOWERS_SKILLS if skill not in present],
        "ok": plugin_manifest.exists() and len(present) == len(SUPERPOWERS_SKILLS),
    }


def find_skill(skill_id: str, skill_roots: list[Path]) -> list[str]:
    matches: list[str] = []
    for root in skill_roots:
        if skill_exists(root, skill_id):
            matches.append(str(root / skill_id))
    return matches


def check(args: argparse.Namespace) -> dict[str, Any]:
    codex_home = Path(args.codex_home).expanduser().resolve()
    skill_roots = [Path(item).expanduser().resolve() for item in args.skill_root]
    superpowers_root = Path(args.superpowers_root).expanduser().resolve()

    skill_status: dict[str, dict[str, Any]] = {}
    for skill_id in (*OPL_FLOW_NATIVE_SKILLS, *OPTIONAL_SKILLS):
        matches = find_skill(skill_id, skill_roots)
        skill_status[skill_id] = {
            "ok": bool(matches),
            "matches": matches,
        }

    superpowers = superpowers_bundle_status(superpowers_root)
    blocking_missing = [
        skill_id
        for skill_id in OPL_FLOW_NATIVE_SKILLS
        if not skill_status[skill_id]["ok"]
    ]
    optional_missing = [
        skill_id
        for skill_id in OPTIONAL_SKILLS
        if not skill_status[skill_id]["ok"]
    ]

    core_ready = True
    full_guardrails_ready = not blocking_missing
    ok = full_guardrails_ready if args.strict else core_ready

    return {
        "ok": ok,
        "strict": args.strict,
        "codex_home": str(codex_home),
        "skill_roots": [str(root) for root in skill_roots],
        "superpowers": superpowers,
        "skills": skill_status,
        "blocking_missing": blocking_missing,
        "optional_missing": optional_missing,
        "compatibility": {
            "opl_app_full_superpowers_compatible": superpowers["ok"],
            "opl_flow_core_ready": core_ready,
            "opl_flow_full_guardrails_ready": full_guardrails_ready,
            "opl_flow_profile_ready": core_ready,
            "degraded_guardrails": blocking_missing,
            "notes": [
                "OPL App Full Superpowers satisfies the Superpowers execution surface when superpowers.ok is true.",
                "OPL Flow core profile remains usable when OPL Flow-native guardrails are absent, but risk/evidence and high-risk ops behavior is degraded.",
                "Use --strict when this check is gating a full guardrail installation rather than core profile compatibility.",
                "Optional skills improve browser/document workflows but are not required for the core profile.",
            ],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check OPL Flow companion skill compatibility")
    home = Path.home()
    codex_home = os.environ.get("CODEX_HOME", "").strip() or str(home / ".codex")
    parser.add_argument("--codex-home", default=codex_home)
    parser.add_argument("--plugins-dir", default=str(home / "plugins"))
    parser.add_argument(
        "--skill-root",
        action="append",
        default=None,
        help="Skill root to scan. Can be repeated.",
    )
    parser.add_argument("--superpowers-root", default=str(home / ".codex" / "superpowers"))
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero unless OPL Flow-native guardrail skills are discoverable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.skill_root is None:
        home = Path.home()
        codex_home = Path(args.codex_home).expanduser()
        plugins_dir = Path(args.plugins_dir).expanduser()
        args.skill_root = [str(root) for root in default_skill_roots(home, codex_home, plugins_dir)]
    result = check(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
