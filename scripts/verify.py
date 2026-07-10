#!/usr/bin/env python3
"""Repository contract checks for OPL Flow."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "README.md",
    "docs/compatibility.md",
    "docs/new-machine-codex-setup.md",
    "LICENSE",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "skills/codex-ops-kit/SKILL.md",
    "skills/codex-ops-kit/agents/openai.yaml",
    "skills/codex-ops-kit/scripts/codex_ops_gate.py",
    "skills/codex-ops-kit/scripts/worktree_absorption_audit.py",
    "skills/codex-ops-kit/scripts/release_url_audit.py",
    "skills/codex-ops-kit/references/lane-closeout.md",
    "skills/codex-ops-kit/references/release-currentness.md",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "templates/prompts/planner.md",
    "templates/prompts/executor.md",
    "templates/prompts/debugger.md",
    "templates/prompts/verifier.md",
    "scripts/install_local_plugin.py",
    "scripts/intelligence_enhancement.py",
    "scripts/check_companion_skills.py",
    "scripts/repo_profile.py",
    "scripts/profile_compose.py",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
    "profile/modules/02-role-baseline.md",
    "profile/modules/03-workflow-core.md",
    "profile/modules/04-guardrails.md",
    "profile/modules/05-ops-authority-core.md",
    "profile/modules/06-capability-adapters.md",
    "profile/modules/07-tool-preferences.md",
    "profile/modules/08-managed-block-policy.md",
)

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
    description = manifest.get("description")
    if not isinstance(description, str) or "decision lenses" not in description:
        errors.append("plugin description must advertise decision lenses")
    interface = manifest.get("interface", {})
    if "decision lenses" not in interface.get("longDescription", ""):
        errors.append("interface.longDescription must advertise decision lenses")
    default_prompt = interface.get("defaultPrompt")
    if not default_prompt or len(default_prompt) > 128:
        errors.append("interface.defaultPrompt must exist and be at most 128 characters")
    return errors


def check_skill_metadata(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for skill_id in ("opl-flow", "codex-ops-kit"):
        path = repo_root / "skills" / skill_id / "agents" / "openai.yaml"
        text = path.read_text(encoding="utf-8")
        for needle in ("interface:", "display_name:", "short_description:", "default_prompt:", f"${skill_id}"):
            require(text, needle, f"{path.relative_to(repo_root)} must contain {needle}", errors)
    return errors


def check_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    planner = (repo_root / "templates" / "prompts" / "planner.md").read_text(encoding="utf-8")
    executor = (repo_root / "templates" / "prompts" / "executor.md").read_text(encoding="utf-8")
    debugger = (repo_root / "templates" / "prompts" / "debugger.md").read_text(encoding="utf-8")
    verifier = (repo_root / "templates" / "prompts" / "verifier.md").read_text(encoding="utf-8")
    taste = (repo_root / "templates" / "TASTE.md").read_text(encoding="utf-8")

    required = (
        (agents, "验证强度匹配风险", "AGENTS.md must select evidence by risk"),
        (agents, "codex-ops-kit", "AGENTS.md must route Git/release mechanics to codex-ops-kit"),
        (agents, "完成度审计", "AGENTS.md must require Chinese completion audits"),
        (agents, "Root-Cause Depth Gate", "AGENTS.md must preserve root-cause depth"),
        (agents, "blocker-to-owner map", "AGENTS.md must preserve blocker-to-owner mapping"),
        (agents, "ponytail-review", "AGENTS.md must route concrete complexity review"),
        (agents, "ponytail-audit", "AGENTS.md must route cleanup discovery"),
        (agents, "decision lenses", "AGENTS.md must define decision lenses"),
        (agents, "fresh claim-appropriate evidence", "AGENTS.md must require claim-appropriate evidence"),
        (agents, "<!-- CODEGRAPH_START -->", "AGENTS.md must preserve the CodeGraph marker block"),
        (planner, "Planner 是 decision lens", "planner prompt must remain a lens"),
        (executor, "只有用户请求或明确 lane contract 授权", "executor must require Git authority"),
        (debugger, "根因深度门", "debugger must preserve the root-cause depth gate"),
        (debugger, "跨面证据", "debugger must require cross-surface evidence"),
        (verifier, "优先级依次为", "verifier must preserve acceptance priority"),
        (verifier, "完成度审计", "verifier must preserve completion audits"),
        (taste, "AI 先行，合同托底", "TASTE.md must prioritize AI execution"),
        (taste, "证据匹配风险", "TASTE.md must preserve risk-matched evidence"),
        (taste, "简单优先", "TASTE.md must preserve simplicity"),
        (taste, "精准改动", "TASTE.md must preserve scoped changes"),
    )
    for text, needle, message in required:
        require(text, needle, message, errors)

    combined_prompts = planner + executor + debugger + verifier
    forbidden = (
        (executor, "顺手验证、提交、推送", "executor must not absorb unrelated changes"),
        (planner, "给出 2-3 个可行方案", "planner must not force multiple options"),
        (combined_prompts, "## 输出格式", "decision lenses must not force output templates"),
        (agents, "自动提升到 `ponytail full`", "AGENTS.md must not claim mechanical Ponytail switching"),
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
        (readme, "--apply-merge-packet", "README must document semantic-merge apply"),
        (readme, "scripts/intelligence_enhancement.py enable --bootstrap-opl", "README must document CodexCont"),
        (setup, "OPL App Full / companion layers normally cover", "setup guide must document companion coverage"),
        (setup, "--apply-merge-packet", "setup guide must document semantic-merge apply"),
        (setup, "opl-flow@opl-flow-local", "setup guide must document exact plugin identity"),
        (skill, "compatible with One Person Lab App Full installs", "skill must describe App Full compatibility"),
        (skill, "Workflow Profile layer only", "skill must define its authority boundary"),
        (skill, "codex-ops-kit", "skill must name its mechanical guardrail"),
        (skill, "--apply-merge-packet", "skill must document semantic-merge apply"),
        (skill, "Route Ponytail by surface", "skill must route Ponytail by surface"),
        (compatibility, "Superpowers", "compatibility doc must cover Superpowers"),
        (compatibility, "Runtime Substrate", "compatibility doc must cover runtime boundary"),
        (compatibility, "Ponytail", "compatibility doc must cover Ponytail"),
    )
    for text, needle, message in required:
        require(text, needle, message, errors)
    return errors


def check_retired_skill(repo_root: Path) -> list[str]:
    retired = "risk-based-" + "development-flow"
    errors: list[str] = []
    if (repo_root / "skills" / retired).exists():
        errors.append(f"retired skill directory still exists: skills/{retired}")
    roots = ("README.md", "docs", "profile", "templates", "skills", "scripts", "tests", ".codex-plugin")
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


def check_contract_tests(repo_root: Path) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "*test*.py",
            "-v",
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


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors: list[str] = []
    errors.extend(check_required_files(repo_root))
    errors.extend(check_plugin_json(repo_root))
    errors.extend(check_skill_metadata(repo_root))
    errors.extend(check_profile(repo_root))
    errors.extend(check_docs(repo_root))
    errors.extend(check_retired_skill(repo_root))
    errors.extend(check_contract_tests(repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OPL Flow verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
