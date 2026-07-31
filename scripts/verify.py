#!/usr/bin/env python3
"""Repository contract checks for OPL Flow."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "contracts/workflow-policy.json",
    "contracts/workflow-policy.schema.json",
    "contracts/worktree-ownership-ledger.schema.json",
    "README.md",
    "docs/compatibility.md",
    "docs/new-machine-codex-setup.md",
    "LICENSE",
    "skills/coordinate-concurrent-tasks/SKILL.md",
    "skills/coordinate-concurrent-tasks/agents/openai.yaml",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "scripts/install_local_plugin.py",
    "scripts/repo_profile.py",
    "scripts/profile_compose.py",
    "scripts/worktree_absorption_audit.py",
    "scripts/worktree_fleet_audit.py",
    "scripts/worktree_lifecycle.py",
    "scripts/opl_workflow.py",
    "scripts/qualify_install.py",
    "scripts/opl_fleet.py",
    "scripts/fleet_inventory.py",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
)

CORE_TEST_MODULES = (
    "tests/test_install_local_plugin.py",
    "tests/test_profile_compose.py",
    "tests/test_repo_profile.py",
    "tests/test_verify_lanes.py",
    "tests/test_worktree_absorption_audit.py",
    "tests/test_worktree_fleet_audit.py",
    "tests/test_worktree_lifecycle.py",
    "tests/test_opl_workflow.py",
    "tests/test_opl_fleet.py",
    "tests/test_fleet_inventory.py",
    "tests/test_package_descriptor.py",
    "tests/test_qualify_install.py",
)
VERIFY_LANES = ("core", "full")

def check_required_files(repo_root: Path) -> list[str]:
    return [f"missing {rel}" for rel in REQUIRED_FILES if not (repo_root / rel).exists()]


def check_plugin_json(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifest = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "opl-flow":
        errors.append("plugin name must be opl-flow")
    if manifest.get("skills") != "./skills/":
        errors.append("plugin skills path must be ./skills/")
    discoverable_skills = {
        path.name for path in (repo_root / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    }
    if discoverable_skills != {"coordinate-concurrent-tasks", "opl-flow"}:
        errors.append("default plugin must expose exactly the opl-flow and coordinate-concurrent-tasks skills")
    policy = json.loads((repo_root / "contracts" / "workflow-policy.json").read_text(encoding="utf-8"))
    if manifest.get("version") != policy.get("package", {}).get("version"):
        errors.append("plugin version must match contracts/workflow-policy.json package.version")
    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("plugin description must be a non-empty string")
    interface = manifest.get("interface", {})
    long_description = interface.get("longDescription")
    if not isinstance(long_description, str) or not long_description.strip():
        errors.append("interface.longDescription must be a non-empty string")
    default_prompt = interface.get("defaultPrompt")
    if not default_prompt or len(default_prompt) > 128:
        errors.append("interface.defaultPrompt must exist and be at most 128 characters")
    return errors


def check_workflow_policy(repo_root: Path) -> list[str]:
    errors: list[str] = []
    policy = json.loads((repo_root / "contracts" / "workflow-policy.json").read_text(encoding="utf-8"))
    schema = json.loads((repo_root / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"))
    if policy.get("$schema") != "./workflow-policy.schema.json":
        errors.append("workflow policy must point to ./workflow-policy.schema.json")
    if "$schema" not in schema.get("properties", {}):
        errors.append("workflow policy schema must admit the policy $schema pointer")
    if policy.get("schema") != "opl_flow_workflow_policy.v3":
        errors.append("workflow policy schema must be opl_flow_workflow_policy.v3")
    if policy.get("package", {}).get("id") != "opl-flow":
        errors.append("workflow policy package id must be opl-flow")
    required_sections = (
        "provides", "requires", "recommends", "compatible_optional",
        "conflicts", "retires", "codex_model_policy", "migration_policy",
        "historical_fingerprints",
    )
    for section in required_sections:
        if section not in policy:
            errors.append(f"workflow policy missing {section}")
    capabilities = [
        item
        for section in ("provides", "requires", "recommends", "compatible_optional")
        for item in policy.get(section, [])
    ]
    capability_keys = [(item.get("kind"), item.get("id")) for item in capabilities]
    if len(capability_keys) != len(set(capability_keys)):
        errors.append("workflow capability identity must be unique by (kind, id)")
    required_metadata = {"id", "kind", "online_install_default", "activation"}
    if any(not required_metadata.issubset(item) for item in capabilities):
        errors.append("workflow policy capabilities must declare identity and activation metadata")
    skill_capabilities = [
        item for item in capabilities if item.get("kind") == "codex_skill"
    ]
    if any(
        not isinstance(item.get("source"), str)
        or re.fullmatch(r"https://github\.com/[^/\s]+/[^/\s]+/?", item["source"]) is None
        or not isinstance(item.get("source_path"), str)
        or not item["source_path"].strip()
        or item["source_path"].startswith("/")
        or "\\" in item["source_path"]
        or ".." in PurePosixPath(item["source_path"]).parts
        for item in skill_capabilities
    ):
        errors.append(
            "all codex_skill capabilities must declare their original GitHub source "
            "and repository-relative source_path"
        )
    expected_provides = {
        ("codex_plugin", "opl-flow"),
        ("codex_skill", "opl-flow"),
        ("codex_skill", "coordinate-concurrent-tasks"),
    }
    provides = policy.get("provides", [])
    if {(item.get("kind"), item.get("id")) for item in provides} != expected_provides:
        errors.append("workflow policy provided Plugin and Skills must match the package payload")
    provided_skill_sources = {
        item.get("id"): (item.get("source"), item.get("source_path"))
        for item in provides
        if item.get("kind") == "codex_skill"
    }
    expected_provided_skill_sources = {
        "opl-flow": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/opl-flow",
        ),
        "coordinate-concurrent-tasks": (
            "https://github.com/gaofeng21cn/opl-flow",
            "skills/coordinate-concurrent-tasks",
        ),
    }
    if provided_skill_sources != expected_provided_skill_sources:
        errors.append("workflow policy provided Skills must use their canonical GitHub source and path")
    if any(item.get("online_install_default") is not True for item in provides):
        errors.append("provided capabilities must be enabled by default")
    schema_kind_enum = (
        schema.get("$defs", {}).get("capability", {}).get("properties", {})
        .get("kind", {}).get("enum", [])
    )
    if not {"codex_plugin", "mcp_server"}.issubset(schema_kind_enum):
        errors.append("workflow policy schema must admit codex_plugin and mcp_server capabilities")
    recommended_ids = {
        item.get("id") for item in policy.get("recommends", [])
        if item.get("kind") == "codex_skill"
    }
    expected = {
        "officecli", "officecli-docx", "officecli-pptx", "officecli-xlsx",
        "officecli-academic-paper", "officecli-data-dashboard",
        "officecli-financial-model", "officecli-pitch-deck",
        "mineru-document-extractor", "ui-ux-pro-max",
    }
    if recommended_ids != expected:
        errors.append("workflow policy recommended skill set is incomplete or contains duplicates")
    recommended_skill_sources = {
        item.get("id"): (item.get("source"), item.get("source_path"))
        for item in policy.get("recommends", [])
        if item.get("kind") == "codex_skill"
    }
    officecli_source = "https://github.com/iOfficeAI/OfficeCLI"
    expected_skill_sources = {
        "officecli": (officecli_source, "."),
        "officecli-docx": (officecli_source, "skills/officecli-docx"),
        "officecli-pptx": (officecli_source, "skills/officecli-pptx"),
        "officecli-xlsx": (officecli_source, "skills/officecli-xlsx"),
        "officecli-academic-paper": (officecli_source, "skills/officecli-academic-paper"),
        "officecli-data-dashboard": (officecli_source, "skills/officecli-data-dashboard"),
        "officecli-financial-model": (officecli_source, "skills/officecli-financial-model"),
        "officecli-pitch-deck": (officecli_source, "skills/officecli-pitch-deck"),
        "mineru-document-extractor": (
            "https://github.com/opendatalab/MinerU-Ecosystem",
            "skills",
        ),
        "ui-ux-pro-max": (
            "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
            ".claude/skills/ui-ux-pro-max",
        ),
    }
    if recommended_skill_sources != expected_skill_sources:
        errors.append("workflow policy external skills must use their canonical GitHub source and path")
    if any(not item.get("online_install_default") for item in policy.get("recommends", [])):
        errors.append("workflow policy recommendations must be resolved by default")
    agent_reach = next(
        (
            item for item in policy.get("requires", [])
            if item.get("kind") == "codex_skill" and item.get("id") == "agent-reach"
        ),
        None,
    )
    expected_agent_reach = {
        "id": "agent-reach",
        "kind": "codex_skill",
        "owner": "agent-reach",
        "online_install_default": True,
        "activation": "task_routed",
        "source": "https://github.com/Panniantong/Agent-Reach",
        "source_path": "agent_reach/skill",
    }
    if agent_reach is None or any(
        agent_reach.get(key) != value
        for key, value in expected_agent_reach.items()
    ):
        errors.append("workflow policy must require agent-reach from its canonical GitHub source")
    dependencies = [
        item
        for section in ("requires", "recommends")
        for item in policy.get(section, [])
    ]
    if any(
        item.get("version_requirement") == "release_lock_exact"
        or item.get("install_source") == "framework_managed_release_lock"
        for item in dependencies
    ):
        errors.append("workflow dependencies must not require a release lock")
    if "installation_convergence" in policy:
        errors.append("workflow policy must not bind composition to a delivery carrier")
    conflict_ids = {item.get("id") for item in policy.get("conflicts", [])}
    if not {"upstream-superpowers", "ponytail", "codexcont-intelligence-enhancement"}.issubset(conflict_ids):
        errors.append("workflow policy must retire the known legacy global workflow conflicts")
    migrations = [*policy.get("conflicts", []), *policy.get("retires", [])]
    ponytail_conflict = next(
        (item for item in policy.get("conflicts", []) if item.get("id") == "ponytail"),
        {},
    )
    expected_ponytail_conflicts = {"ponytail", "ponytail-local", "ponytail-ponytail"}
    if set(ponytail_conflict.get("discovery_ids", [])) != expected_ponytail_conflicts:
        errors.append("workflow policy must retire only Ponytail plugin and main-persona discovery aliases")
    retired_discovery_ids = {
        discovery_id
        for item in migrations
        for discovery_id in item.get("discovery_ids", [])
    }
    if {"ponytail-audit", "ponytail-review"} & retired_discovery_ids:
        errors.append("explicit Ponytail audit and review skills must remain outside workflow retirement")
    if any(not isinstance(item.get("config_markers"), list) or not isinstance(item.get("service_ids"), list) for item in migrations):
        errors.append("workflow migrations must declare config_markers and service_ids")
    migration_policy = policy.get("migration_policy", {})
    if not migration_policy.get("discovery_root_ids"):
        errors.append("workflow migration policy must declare bounded discovery roots")
    if migration_policy.get("profile_optimization", {}).get("default_mode") != "codex_semantic_merge":
        errors.append("workflow profile optimization must default to Codex semantic merge")
    fingerprints = policy.get("historical_fingerprints", {})
    if not fingerprints.get("agents_marker_pairs") or not fingerprints.get("agents_legacy_section_headings"):
        errors.append("workflow policy must declare historical AGENTS markers and section headings")
    precedence = policy.get("codex_model_policy", {}).get("override_precedence", [])
    expected_precedence = [
        "explicit_user_override",
        "opl_flow_recommendation",
        "fresh_codex_model_catalog",
        "app_fallback_when_flow_unavailable",
    ]
    if precedence != expected_precedence:
        errors.append("model precedence must be user, installed Flow, live Codex, then App fallback")
    dependency_ids = {
        item.get("id")
        for section in ("requires", "recommends", "compatible_optional")
        for item in policy.get(section, [])
    }
    if "codex-ops-kit" in dependency_ids:
        errors.append("retired codex-ops-kit must not remain in workflow dependencies")
    return errors


def check_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")

    instruction_count = sum(
        line.startswith("- ") or bool(re.match(r"^\d+\. ", line))
        for line in agents.splitlines()
    )
    if instruction_count > 8:
        errors.append("AGENTS.md must contain at most 8 prioritized instructions")

    profile_size = len(agents.encode("utf-8"))
    if profile_size > 2048:
        print(
            "WARNING: AGENTS.md exceeds the 2 KB focus target; "
            "keep reviewing clarity and move detail only when functionality is preserved",
            file=sys.stderr,
        )
    if profile_size > 4096:
        print(
            "WARNING: AGENTS.md exceeds 4 KB; this is a soft maintainability signal, not a gate",
            file=sys.stderr,
        )

    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "profile_compose.py"), "check", "--repo-root", str(repo_root)],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        errors.append("templates/AGENTS.md must match profile modules: " + (result.stdout or result.stderr).strip())
    return errors


def check_retired_skill(repo_root: Path) -> list[str]:
    retired = "risk-based-" + "development-flow"
    errors: list[str] = []
    if (repo_root / "skills" / retired).exists():
        errors.append(f"retired skill directory still exists: skills/{retired}")
    if (repo_root / "optional-skills" / "codex-ops-kit").exists():
        errors.append("retired skill directory still exists: optional-skills/codex-ops-kit")
    roots = ("README.md", "docs", "profile", "templates", "skills", "optional-skills", "scripts", "tests", ".codex-plugin")
    for root_name in roots:
        root = repo_root / root_name
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path == Path(__file__).resolve():
                continue
            try:
                if retired in path.read_text(encoding="utf-8"):
                    errors.append(f"retired skill reference remains: {path.relative_to(repo_root)}")
            except UnicodeDecodeError:
                continue
    return errors


def contract_test_modules(lane: str) -> tuple[str, ...]:
    if lane in {"core", "full"}:
        return CORE_TEST_MODULES
    raise ValueError(f"unknown verification lane: {lane}")


def check_contract_tests(repo_root: Path, lane: str) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-v",
            *contract_test_modules(lane),
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode == 0:
        return []
    return ["contract tests failed: " + (result.stdout + result.stderr).strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane", nargs="?", choices=VERIFY_LANES, default="core")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    errors.extend(check_required_files(repo_root))
    errors.extend(check_plugin_json(repo_root))
    errors.extend(check_workflow_policy(repo_root))
    errors.extend(check_profile(repo_root))
    errors.extend(check_retired_skill(repo_root))
    errors.extend(check_contract_tests(repo_root, args.lane))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OPL Flow {args.lane} verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
