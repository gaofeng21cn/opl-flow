#!/usr/bin/env python3
"""Check companion skill availability for the OPL Flow profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    from scripts import install_local_plugin
except ImportError:
    import install_local_plugin  # type: ignore[no-redef]


SUPERPOWERS_SKILLS = (
    "using-superpowers",
    "systematic-debugging",
    "verification-before-completion",
    "test-driven-development",
    "using-git-worktrees",
)

SUPERPOWERS_LITE_SELECTED = (
    "systematic-debugging",
    "test-driven-development",
    "verification-before-completion",
)

SUPERPOWERS_EXPANDED_SELECTED = (
    *SUPERPOWERS_LITE_SELECTED,
    "brainstorming",
    "using-git-worktrees",
    "writing-plans",
    "subagent-driven-development",
    "executing-plans",
    "dispatching-parallel-agents",
    "requesting-code-review",
    "receiving-code-review",
    "finishing-a-development-branch",
)

OPL_FLOW_NATIVE_SKILLS = install_local_plugin.GUARDRAIL_SKILLS

OPTIONAL_SKILLS = (
    "agent-browser",
    "mineru-document-extractor",
)

OPTIONAL_PLUGINS = (
    "ponytail",
)

PONYTAIL_VALID_MODES = {"off", "lite", "full", "ultra", "review"}


def default_skill_roots(home: Path, codex_home: Path, plugins_dir: Path, repo_root: Path) -> list[Path]:
    roots = [
        repo_root / "skills",
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


def runtime_discovery_root(root: Path, home: Path, codex_home: Path) -> bool:
    absolute = Path(os.path.abspath(root.expanduser()))
    return _relative_to(absolute, codex_home / "skills") or _relative_to(absolute, home / ".agents" / "skills")


def skill_exists(root: Path, skill_id: str) -> bool:
    return (root / skill_id / "SKILL.md").exists()


def plugin_manifest_exists(root: Path) -> bool:
    return (root / ".codex-plugin" / "plugin.json").exists()


def plugin_cache_roots(codex_home: Path, plugin_id: str) -> list[Path]:
    cache_root = codex_home / "plugins" / "cache" / plugin_id / plugin_id
    if not cache_root.exists():
        return []
    return sorted(path for path in cache_root.iterdir() if path.is_dir())


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


def _relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def using_superpowers_disabled(codex_home: Path, superpowers_root: Path) -> bool:
    config = codex_home / "config.toml"
    if not config.exists():
        return False
    text = config.read_text(encoding="utf-8")
    using_skill = str(superpowers_root / "skills" / "using-superpowers" / "SKILL.md")
    start = text.find(using_skill)
    if start == -1:
        return False
    return "enabled = false" in text[start : start + 300]


def _link_info(path: Path, home: Path, codex_home: Path, plugins_dir: Path, repo_root: Path) -> dict[str, Any]:
    exists = path.exists() or path.is_symlink()
    target = path.resolve(strict=False) if exists else None
    return {
        "exists": exists,
        "path": str(path),
        "target": str(target) if target else None,
        "source": classify_source(target if target else path, home, codex_home, plugins_dir, repo_root) if exists else "missing",
    }


def superpowers_profile_status(
    home: Path,
    codex_home: Path,
    plugins_dir: Path,
    repo_root: Path,
    superpowers_root: Path,
) -> dict[str, Any]:
    agents_skills = home / ".agents" / "skills"
    disabled = using_superpowers_disabled(codex_home, superpowers_root)
    full_link = agents_skills / "superpowers"
    full_target = full_link.resolve(strict=False) if full_link.exists() or full_link.is_symlink() else None

    lite_links = {
        skill: _link_info(agents_skills / skill, home, codex_home, plugins_dir, repo_root)
        for skill in SUPERPOWERS_LITE_SELECTED
    }
    expanded_extra_links = {
        skill: _link_info(agents_skills / skill, home, codex_home, plugins_dir, repo_root)
        for skill in SUPERPOWERS_EXPANDED_SELECTED
        if skill not in SUPERPOWERS_LITE_SELECTED
    }
    umbrella = _link_info(agents_skills / "superpowers-lite", home, codex_home, plugins_dir, repo_root)

    lite_ready = all(item["exists"] for item in lite_links.values()) and umbrella["exists"] and disabled
    expanded_ready = lite_ready and all(item["exists"] for item in expanded_extra_links.values())
    full_ready = full_target == (superpowers_root / "skills").resolve(strict=False) and not disabled

    if full_ready:
        profile = "full"
    elif expanded_ready:
        profile = "expanded"
    elif lite_ready:
        profile = "lite"
    elif any(item["exists"] for item in (*lite_links.values(), *expanded_extra_links.values())) or umbrella["exists"] or full_target:
        profile = "custom"
    else:
        profile = "not_configured"

    local_overlay_root = (home / ".skills-manager" / "skills" / "superpowers-local-profile").resolve(strict=False)
    local_overlay_skills = sorted(
        skill
        for skill, item in {**lite_links, **expanded_extra_links}.items()
        if item["target"] and _relative_to(Path(item["target"]), local_overlay_root)
    )

    return {
        "profile": profile,
        "agents_skills": str(agents_skills),
        "using_superpowers_disabled": disabled,
        "full_link": str(full_link),
        "full_link_target": str(full_target) if full_target else None,
        "lite_selected": lite_links,
        "expanded_extra": expanded_extra_links,
        "umbrella": umbrella,
        "local_overlay_skills": local_overlay_skills,
        "notes": [
            "lite and expanded preserve the local routing profile and keep upstream using-superpowers disabled.",
            "full enables the official Superpowers bootstrap by linking the full skills directory.",
        ],
    }


def classify_source(skill_path: Path, home: Path, codex_home: Path, plugins_dir: Path, repo_root: Path) -> str:
    root = skill_path.parent
    packaged_root = Path(os.environ.get("OPL_PACKAGED_SKILLS_ROOT", "")).expanduser()
    full_runtime_home = Path(os.environ.get("OPL_FULL_RUNTIME_HOME", "")).expanduser()
    if _relative_to(skill_path, plugins_dir / "opl-flow" / "skills"):
        return "staged_local_plugin"
    if _relative_to(skill_path, repo_root / "skills"):
        return "bundled_repo"
    if _relative_to(skill_path, plugins_dir):
        return "local_plugin"
    if _relative_to(skill_path, codex_home / "skills"):
        return "codex_home"
    if _relative_to(skill_path, home / ".agents" / "skills"):
        return "agents_home"
    if _relative_to(skill_path, home / ".skills-manager" / "skills"):
        return "skills_manager"
    if _relative_to(skill_path, codex_home / "plugins" / "cache"):
        return "plugin_cache"
    if str(packaged_root) != "." and _relative_to(skill_path, packaged_root):
        return "packaged_skills"
    if str(full_runtime_home) != "." and _relative_to(skill_path, full_runtime_home / "skills"):
        return "full_runtime"
    return "custom_root"


def find_skill(
    skill_id: str,
    skill_roots: list[Path],
    home: Path,
    codex_home: Path,
    plugins_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    details_by_path: dict[str, dict[str, Any]] = {}
    for root in skill_roots:
        if skill_exists(root, skill_id):
            skill_path = (root / skill_id).resolve()
            key = str(skill_path)
            detail = details_by_path.setdefault(
                key,
                {
                    "path": key,
                    "root": str(root),
                    "discovery_roots": [],
                    "source": classify_source(skill_path, home, codex_home, plugins_dir, repo_root),
                    "runtime_discoverable": False,
                },
            )
            detail["discovery_roots"].append(str(root))
            detail["runtime_discoverable"] = detail["runtime_discoverable"] or runtime_discovery_root(
                root,
                home,
                codex_home,
            )
    details = list(details_by_path.values())
    matches = list(details_by_path)
    sources = sorted({item["source"] for item in details})
    return {
        "ok": bool(matches),
        "matches": matches,
        "match_details": details,
        "sources": sources,
    }


def runtime_skill_ready(status: dict[str, Any], source: Path | None = None) -> bool:
    for item in status.get("match_details", []):
        if item.get("runtime_discoverable") is not True:
            continue
        if source is None or not install_local_plugin.tree_mismatches(
            source,
            Path(item["path"]),
            f"skills/{source.name}",
        ):
            return True
    return False


def find_plugin(
    plugin_id: str,
    home: Path,
    codex_home: Path,
    plugins_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    home = home.expanduser().resolve()
    codex_home = codex_home.expanduser().resolve()
    plugins_dir = plugins_dir.expanduser().resolve()
    repo_root = repo_root.expanduser().resolve()
    roots = [
        plugins_dir / plugin_id,
        repo_root / "plugins" / plugin_id,
        *(plugin_cache_roots(codex_home, plugin_id)),
    ]
    matches: list[str] = []
    details: list[dict[str, str]] = []
    for root in roots:
        if not plugin_manifest_exists(root):
            continue
        plugin_path = root.resolve()
        matches.append(str(plugin_path))
        details.append(
            {
                "path": str(plugin_path),
                "root": str(root.parent),
                "source": classify_source(plugin_path, home, codex_home, plugins_dir, repo_root),
            }
        )
    sources = sorted({item["source"] for item in details})
    return {
        "ok": bool(matches),
        "matches": matches,
        "match_details": details,
        "sources": sources,
    }


def ponytail_config_status(home: Path) -> dict[str, Any]:
    config_path = home / ".config" / "ponytail" / "config.json"
    if not config_path.exists():
        return {
            "path": str(config_path),
            "exists": False,
            "default_mode": "full",
            "source": "upstream_default",
            "auto_activation": "on",
            "recommended_default_mode": "lite",
            "matches_opl_default": False,
            "notes": [
                "Ponytail upstream defaults to full mode when no config or PONYTAIL_DEFAULT_MODE override exists.",
                "OPL Flow recommends an explicit lite default for automatic low-intensity activation.",
            ],
        }
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(config_path),
            "exists": True,
            "ok": False,
            "error": str(exc),
            "default_mode": None,
            "source": "invalid_config",
            "auto_activation": "unknown",
        }
    mode = str(data.get("defaultMode", "")).strip().lower()
    valid = mode in PONYTAIL_VALID_MODES
    return {
        "path": str(config_path),
        "exists": True,
        "ok": valid,
        "default_mode": mode if valid else None,
        "source": "config_file",
        "auto_activation": "off" if mode == "off" else "on",
        "recommended_default_mode": "lite",
        "matches_opl_default": valid and mode == "lite",
        "notes": [
            "OPL Flow keeps Ponytail lite as the default simplification lens.",
            "Ponytail must not override risk-based evidence, codex-ops-kit, verifier, or completion audits.",
        ],
    }


def check(args: argparse.Namespace) -> dict[str, Any]:
    home = Path(args.home).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    plugins_dir = Path(args.plugins_dir).expanduser().resolve()
    repo_root = Path(args.repo_root).expanduser().resolve()
    skill_roots = [Path(item).expanduser().resolve() for item in args.skill_root]
    superpowers_root = Path(args.superpowers_root).expanduser().resolve()

    skill_status: dict[str, dict[str, Any]] = {}
    for skill_id in (*OPL_FLOW_NATIVE_SKILLS, *OPTIONAL_SKILLS):
        skill_status[skill_id] = find_skill(skill_id, skill_roots, home, codex_home, plugins_dir, repo_root)
    plugin_status: dict[str, dict[str, Any]] = {}
    for plugin_id in OPTIONAL_PLUGINS:
        plugin_status[plugin_id] = find_plugin(plugin_id, home, codex_home, plugins_dir, repo_root)

    superpowers = superpowers_bundle_status(superpowers_root)
    superpowers_profile = superpowers_profile_status(home, codex_home, plugins_dir, repo_root, superpowers_root)
    profile_status = install_local_plugin.verify_profile(repo_root, codex_home, profile=True)
    profile_ready = profile_status["status"] in {"current", "local_overlay"}
    staged_plugin = plugins_dir / install_local_plugin.PLUGIN_NAME
    try:
        plugin_verification = (
            install_local_plugin.verify(
                repo_root,
                plugins_dir,
                codex_home,
                profile=False,
                codex_bin=args.codex_bin,
            )
            if staged_plugin.exists()
            else {"ok": False, "reason": "staged_plugin_missing"}
        )
    except (RuntimeError, ValueError) as exc:
        plugin_verification = {"ok": False, "error": str(exc)}
    plugin_readback = plugin_verification.get("plugin_readback", {"ok": False})
    plugin_ready = plugin_verification.get("ok") is True
    payload_mismatches = (
        *plugin_verification.get("source_plugin_mismatches", []),
        *plugin_verification.get("cache_mismatches", []),
    )
    plugin_guardrails = {
        skill_id: (
            plugin_readback.get("ok") is True
            and not any(f"/skills/{skill_id}/" in mismatch for mismatch in payload_mismatches)
        )
        for skill_id in OPL_FLOW_NATIVE_SKILLS
    }
    runtime_guardrails = {
        skill_id: plugin_guardrails[skill_id]
        or runtime_skill_ready(skill_status[skill_id], repo_root / "skills" / skill_id)
        for skill_id in OPL_FLOW_NATIVE_SKILLS
    }
    blocking_missing = [
        skill_id
        for skill_id in OPL_FLOW_NATIVE_SKILLS
        if not runtime_guardrails[skill_id]
    ]
    optional_missing = [
        skill_id
        for skill_id in OPTIONAL_SKILLS
        if not skill_status[skill_id]["ok"]
    ]
    optional_plugins_missing = [
        plugin_id
        for plugin_id in OPTIONAL_PLUGINS
        if not plugin_status[plugin_id]["ok"]
    ]
    native_guardrail_sources = {
        skill_id: sorted(
            set(skill_status[skill_id]["sources"])
            | ({"installed_opl_flow_plugin"} if plugin_guardrails[skill_id] else set())
        )
        for skill_id in OPL_FLOW_NATIVE_SKILLS
    }

    core_ready = profile_ready and not blocking_missing
    full_guardrails_ready = not blocking_missing
    full_ready = core_ready and plugin_ready
    ok = full_ready if args.strict else True

    return {
        "ok": ok,
        "strict": args.strict,
        "codex_home": str(codex_home),
        "repo_root": str(repo_root),
        "skill_roots": [str(root) for root in skill_roots],
        "superpowers": superpowers,
        "superpowers_profile": superpowers_profile,
        "profile": profile_status,
        "opl_flow_plugin": plugin_readback,
        "opl_flow_install": plugin_verification,
        "skills": skill_status,
        "plugins": plugin_status,
        "ponytail": {
            "plugin": plugin_status["ponytail"],
            "config": ponytail_config_status(home),
            "boundary": "optional_simplification_lens",
        },
        "blocking_missing": blocking_missing,
        "optional_missing": optional_missing,
        "optional_plugins_missing": optional_plugins_missing,
        "compatibility": {
            "opl_app_full_superpowers_compatible": superpowers["ok"],
            "opl_flow_core_ready": core_ready,
            "opl_flow_full_guardrails_ready": full_guardrails_ready,
            "opl_flow_profile_ready": profile_ready,
            "opl_flow_plugin_ready": plugin_ready,
            "opl_flow_full_ready": full_ready,
            "missing_guardrails": blocking_missing,
            "native_guardrail_sources": native_guardrail_sources,
            "notes": [
                "OPL Flow bundles codex-ops-kit as its profile-native mechanical guardrail.",
                "OPL App Full Superpowers satisfies the Superpowers execution surface when superpowers.ok is true.",
                "OPL Flow preserves the current local Superpowers profile unless the user explicitly asks for full Superpowers.",
                "Use --strict to fail closed unless the profile, exact installed/cache payload, and runtime guardrails are ready.",
                "Optional skills improve browser/document workflows but are not required for the core profile.",
                "Ponytail is optional and should stay an explicit simplification lens; it must not override OPL Flow evidence, ops, verifier, or completion-audit rules.",
            ],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check OPL Flow companion skill compatibility")
    home = Path.home()
    codex_home = os.environ.get("CODEX_HOME", "").strip() or str(home / ".codex")
    parser.add_argument("--home", default=str(home), help="Home directory used for source classification.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--codex-home", default=codex_home)
    parser.add_argument("--plugins-dir", default=str(home / "plugins"))
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    parser.add_argument(
        "--skill-root",
        action="append",
        default=None,
        help="Skill root to scan. Can be repeated.",
    )
    parser.add_argument("--superpowers-root", default=str(Path(codex_home) / "superpowers"))
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero unless the OPL Flow profile, exact installed/cache payload, and native guardrails are ready.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.skill_root is None:
        home = Path(args.home).expanduser()
        repo_root = Path(args.repo_root).expanduser()
        codex_home = Path(args.codex_home).expanduser()
        plugins_dir = Path(args.plugins_dir).expanduser()
        args.skill_root = [str(root) for root in default_skill_roots(home, codex_home, plugins_dir, repo_root)]
    result = check(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
