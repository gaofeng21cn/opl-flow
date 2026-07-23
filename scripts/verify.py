#!/usr/bin/env python3
"""Repository contract checks for OPL Flow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "contracts/workflow-policy.json",
    "contracts/workflow-policy.schema.json",
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
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
)

CORE_TEST_MODULES = (
    "tests/test_install_local_plugin.py",
    "tests/test_profile_compose.py",
    "tests/test_repo_profile.py",
    "tests/test_verify_lanes.py",
)
VERIFY_LANES = ("core", "full")

def require(text: str, needle: str, message: str, errors: list[str]) -> None:
    if needle not in text:
        errors.append(message)


def forbid(text: str, needle: str, message: str, errors: list[str]) -> None:
    if needle in text:
        errors.append(message)


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
    if not isinstance(description, str) or "minimal Codex preference profile" not in description:
        errors.append("plugin description must advertise the minimal preference profile")
    interface = manifest.get("interface", {})
    if "minimal AGENTS.md preference profile" not in interface.get("longDescription", ""):
        errors.append("interface.longDescription must identify the minimal preference profile")
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
    if policy.get("schema") != "opl_flow_workflow_policy.v1":
        errors.append("workflow policy schema must be opl_flow_workflow_policy.v1")
    if policy.get("package", {}).get("id") != "opl-flow":
        errors.append("workflow policy package id must be opl-flow")
    required_sections = (
        "requires", "recommends", "compatible_optional", "conflicts", "retires",
        "codex_model_policy", "migration_policy", "historical_fingerprints",
    )
    for section in required_sections:
        if section not in policy:
            errors.append(f"workflow policy missing {section}")
    recommended_ids = {
        item.get("id") for item in policy.get("recommends", [])
        if item.get("kind") == "codex_skill" and item.get("offline_bundle") == "full"
    }
    expected = {
        "officecli", "officecli-docx", "officecli-pptx", "officecli-xlsx",
        "officecli-academic-paper", "officecli-data-dashboard",
        "officecli-financial-model", "officecli-pitch-deck",
        "mineru-document-extractor", "ui-ux-pro-max",
    }
    if recommended_ids != expected:
        errors.append("workflow policy Full skill closure is incomplete or contains duplicates")
    recommended_skill_sources = {
        item.get("id"): item.get("source")
        for item in policy.get("recommends", [])
        if item.get("kind") == "codex_skill"
    }
    expected_skill_sources = {skill_id: f"skills-manager:{skill_id}" for skill_id in expected}
    if recommended_skill_sources != expected_skill_sources:
        errors.append("workflow policy managed skills must use their Skills Manager package authority")
    if any(
        not item.get("online_install_default") or item.get("offline_bundle") != "full"
        for item in policy.get("recommends", [])
    ):
        errors.append("workflow policy recommendations must remain default managed dependencies in the Full closure")
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
    if not precedence or precedence[0] != "explicit_user_override":
        errors.append("explicit user model override must have highest precedence")
    dependency_ids = {
        item.get("id")
        for section in ("requires", "recommends", "compatible_optional")
        for item in policy.get(section, [])
    }
    if "codex-ops-kit" in dependency_ids:
        errors.append("retired codex-ops-kit must not remain in workflow dependencies")
    return errors


def check_skill_metadata(repo_root: Path) -> list[str]:
    errors: list[str] = []
    skill_roots = {
        "coordinate-concurrent-tasks": repo_root / "skills" / "coordinate-concurrent-tasks",
        "opl-flow": repo_root / "skills" / "opl-flow",
    }
    for skill_id, skill_root in skill_roots.items():
        path = skill_root / "agents" / "openai.yaml"
        text = path.read_text(encoding="utf-8")
        for needle in ("interface:", "display_name:", "short_description:", "default_prompt:", f"${skill_id}"):
            require(text, needle, f"{path.relative_to(repo_root)} must contain {needle}", errors)
    coordination = (skill_roots["coordinate-concurrent-tasks"] / "SKILL.md").read_text(encoding="utf-8")
    for needle in (
        "parallel_work_serialized_integration",
        "SAFE_TO_ARCHIVE",
        "set_thread_archived(true)",
        "fresh 验收",
        "archive_performed=false",
        "user_approval_required=true",
    ):
        require(
            coordination,
            needle,
            f"skills/coordinate-concurrent-tasks/SKILL.md must preserve {needle}",
            errors,
        )
    return errors


def check_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    taste = (repo_root / "templates" / "TASTE.md").read_text(encoding="utf-8")

    required = (
        (agents, "你始终用中文回复", "AGENTS.md must preserve the language preference"),
        (agents, "先给结论", "AGENTS.md must preserve outcome-first communication"),
        (agents, "真实生效位置", "AGENTS.md must require current project context"),
        (agents, "repo-local `AGENTS.md`", "AGENTS.md must defer to repository context"),
        (agents, "默认直接完成", "AGENTS.md must default to direct execution"),
        (agents, "用户最高优先级目标及其可验收终态", "AGENTS.md must keep the primary outcome on the critical path"),
        (agents, "均不得替代终态", "AGENTS.md must not confuse intermediate work with completion"),
        (agents, "只处理关键路径、确定性阻断和必需验证", "AGENTS.md must defer non-critical expansion"),
        (agents, "阻断闭合即回主线", "AGENTS.md must return to the primary task after blockers close"),
        (agents, "超出预期时立即收缩范围", "AGENTS.md must contract scope when work overruns"),
        (agents, "已进入真实权威来源并实际生效", "AGENTS.md must require effective prerequisites"),
        (agents, "发现顺序倒置时", "AGENTS.md must repair inverted dependency order"),
        (agents, "并发默认 4", "AGENTS.md must bound default subagent concurrency"),
        (agents, "超过 8 须用户明确授权", "AGENTS.md must require approval above the concurrency ceiling"),
        (agents, "子智能体不得再委派", "AGENTS.md must prohibit recursive delegation"),
        (agents, "Shell 默认用 `rtk`", "AGENTS.md must preserve the RTK preference"),
        (agents, "codegraph init .", "AGENTS.md must bootstrap CodeGraph for development repositories"),
        (agents, "确保 Git ignore", "AGENTS.md must keep CodeGraph state untracked"),
        (taste, "AI 先行，合同托底", "TASTE.md must prioritize AI execution"),
        (taste, "证据匹配风险", "TASTE.md must preserve risk-matched evidence"),
        (taste, "简单优先", "TASTE.md must preserve simplicity"),
        (taste, "精准改动", "TASTE.md must preserve scoped changes"),
        (taste, "最高优先级目标及其可验收终态", "TASTE.md must preserve primary-outcome priority"),
        (taste, "真实权威来源并实际生效", "TASTE.md must preserve effective-prerequisite ordering"),
    )
    for text, needle, message in required:
        require(text, needle, message, errors)

    forbidden = (
        (agents, "## Guardrails", "AGENTS.md must not install a guardrail workflow"),
        (agents, "## Ops And Authority Core", "AGENTS.md must not install an ops workflow"),
        (agents, "## Capability Adapters", "AGENTS.md must not install capability routing"),
        (agents, "完成度审计", "AGENTS.md must not install a completion ceremony"),
        (agents, "Ponytail", "AGENTS.md must not route a coding persona"),
        (agents, "Superpowers", "AGENTS.md must not route a development methodology"),
        (agents, "## ", "AGENTS.md must remain an unsectioned flat profile"),
    )
    for text, needle, message in forbidden:
        forbid(text, needle, message, errors)

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


def check_docs(repo_root: Path) -> list[str]:
    errors: list[str] = []
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    setup = (repo_root / "docs" / "new-machine-codex-setup.md").read_text(encoding="utf-8")
    compatibility = (repo_root / "docs" / "compatibility.md").read_text(encoding="utf-8")
    skill = (repo_root / "skills" / "opl-flow" / "SKILL.md").read_text(encoding="utf-8")
    required = (
        (readme, "Compatibility With OPL App Full", "README must document OPL App Full compatibility"),
        (readme, "profile-apply opl-flow --packet", "README must document the semantic-merge fallback route"),
        (readme, "opl packages install opl-flow", "README must document the package install route"),
        (readme, "opl packages update opl-flow", "README must document the package update route"),
        (readme, "opl packages optimize opl-flow", "README must document the package optimize route"),
        (setup, "opl packages install opl-flow", "setup guide must document the package install route"),
        (setup, "rollback receipt", "setup guide must document migration recovery"),
        (setup, "returns the review/apply route", "setup guide must document the semantic-merge fallback route"),
        (setup, "opl-flow@opl-agent-opl-flow-local", "setup guide must document the normal package plugin identity"),
        (skill, "minimal Codex preference profile", "skill must define its minimal-profile boundary"),
        (skill, "review/apply fallback route returned by the package command", "skill must route semantic-merge fallback through the package lifecycle"),
        (skill, "managed dependencies, not advisory text", "skill must define recommendation dependency semantics"),
        (skill, "$coordinate-concurrent-tasks", "skill must route bounded multi-task coordination to the bundled coordination skill"),
        (readme, "generic Framework reconciliation", "README must document carrier-neutral App reconciliation"),
        (readme, "`coordinate-concurrent-tasks`", "README must document the bundled coordination skill"),
        (setup, "`coordinate-concurrent-tasks`", "setup guide must document the bundled coordination skill"),
        (compatibility, "model-native", "compatibility doc must cover model-native development"),
        (compatibility, "`skills/coordinate-concurrent-tasks`", "compatibility doc must identify the coordination skill owner"),
        (compatibility, "OPL Base", "compatibility doc must cover the Base boundary"),
        (compatibility, "Retired conflict", "compatibility doc must cover retired workflow conflicts"),
    )
    for text, needle, message in required:
        require(text, needle, message, errors)
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
    errors.extend(check_skill_metadata(repo_root))
    errors.extend(check_profile(repo_root))
    errors.extend(check_docs(repo_root))
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
