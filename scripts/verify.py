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
    "scripts/install_local_plugin.py",
    "scripts/check_companion_skills.py",
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
    description = manifest.get("description")
    if not isinstance(description, str) or "bundled risk and ops guardrails" not in description:
        errors.append("plugin description must advertise bundled risk and ops guardrails")
    long_description = manifest.get("interface", {}).get("longDescription")
    if not isinstance(long_description, str) or "bundled high-risk Codex ops routing" not in long_description:
        errors.append("interface.longDescription must advertise bundled high-risk Codex ops routing")
    default_prompt = manifest.get("interface", {}).get("defaultPrompt")
    if not default_prompt:
        errors.append("interface.defaultPrompt is required")
    elif len(default_prompt) > 128:
        errors.append("interface.defaultPrompt must be at most 128 characters")
    return errors


def check_profile_templates(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    verifier = (repo_root / "templates" / "prompts" / "verifier.md").read_text(encoding="utf-8")
    taste = (repo_root / "templates" / "TASTE.md").read_text(encoding="utf-8")
    required_pairs = (
        (agents, "risk-based development flow", "AGENTS.md must route risk-based development flow"),
        (agents, "codex-ops-kit", "AGENTS.md must route high-risk Codex ops to codex-ops-kit"),
        (agents, "完成度审计", "AGENTS.md must require Chinese completion audits"),
        (agents, "<!-- CODEGRAPH_START -->", "AGENTS.md must preserve the CodeGraph marker block"),
        (verifier, "验收对象的优先级", "verifier prompt must preserve audit-object priority"),
        (verifier, "完成度审计", "verifier prompt must preserve Chinese completion audit"),
        (verifier, "focused tests", "verifier prompt must reject focused-tests-as-readiness claims"),
        (taste, "风险分层优先于测试仪式", "TASTE.md must preserve risk-over-ritual preference"),
    )
    for text, needle, message in required_pairs:
        if needle not in text:
            errors.append(message)
    return errors


def check_docs_describe_compatibility(repo_root: Path) -> list[str]:
    errors: list[str] = []
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    setup = (repo_root / "docs" / "new-machine-codex-setup.md").read_text(encoding="utf-8")
    skill = (repo_root / "skills" / "opl-flow" / "SKILL.md").read_text(encoding="utf-8")
    required_pairs = (
        (readme, "Compatibility With OPL App Full", "README must document OPL App Full compatibility"),
        (readme, "python3 scripts/check_companion_skills.py", "README must document companion skill checker"),
        (setup, "OPL App Full / Superpowers normally covers", "new-machine guide must describe Full/Superpowers coverage"),
        (setup, "python3 ~/opl-flow/scripts/check_companion_skills.py", "new-machine guide must include companion skill check"),
        (skill, "compatible with One Person Lab App Full installs", "skill must describe OPL App Full compatibility"),
        (skill, "risk-based-development-flow", "skill must name risk-based-development-flow as profile-native"),
        (skill, "codex-ops-kit", "skill must name codex-ops-kit as profile-native"),
    )
    for text, needle, message in required_pairs:
        if needle not in text:
            errors.append(message)
    return errors


def check_companion_script(repo_root: Path) -> list[str]:
    errors: list[str] = []
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "check_companion_skills.py"),
        "--codex-home",
        str(repo_root / ".tmp-codex-home"),
        "--superpowers-root",
        str(repo_root / ".tmp-codex-home" / "superpowers"),
    ]
    result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"companion skill check must emit JSON: {exc}: {result.stdout} {result.stderr}".strip())
        return errors
    if result.returncode != 0:
        errors.append(f"companion skill check default mode must allow core profile compatibility: {result.stdout} {result.stderr}".strip())
    if payload.get("blocking_missing") != []:
        errors.append(f"companion skill check missing set is unexpected: {payload.get('blocking_missing')}")
    compatibility = payload.get("compatibility", {})
    if compatibility.get("opl_flow_profile_ready") is not True:
        errors.append(f"companion skill check must keep core profile ready by default: {compatibility}")
    if compatibility.get("opl_flow_full_guardrails_ready") is not True:
        errors.append(f"companion skill check must report bundled full guardrails: {compatibility}")

    strict_result = subprocess.run(cmd + ["--strict"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        strict_payload = json.loads(strict_result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"strict companion skill check must emit JSON: {exc}: {strict_result.stdout} {strict_result.stderr}".strip())
        return errors
    if strict_result.returncode != 0:
        errors.append(f"strict companion skill check must pass with bundled OPL Flow-native guardrails: {strict_result.stdout} {strict_result.stderr}".strip())
    if strict_payload.get("blocking_missing") != []:
        errors.append(f"strict companion skill check missing set is unexpected: {strict_payload.get('blocking_missing')}")

    empty_root_cmd = cmd + ["--skill-root", str(repo_root / ".tmp-codex-home" / "skills"), "--strict"]
    empty_root_result = subprocess.run(empty_root_cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        empty_root_payload = json.loads(empty_root_result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"empty-root strict companion skill check must emit JSON: {exc}: {empty_root_result.stdout} {empty_root_result.stderr}".strip())
        return errors
    if empty_root_result.returncode == 0:
        errors.append("empty-root strict companion skill check must fail when OPL Flow-native guardrails are not discoverable")
    if empty_root_payload.get("blocking_missing") != ["risk-based-development-flow", "codex-ops-kit"]:
        errors.append(f"empty-root strict companion skill check missing set is unexpected: {empty_root_payload.get('blocking_missing')}")
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
    errors.extend(check_profile_templates(repo_root))
    errors.extend(check_docs_describe_compatibility(repo_root))
    errors.extend(check_companion_script(repo_root))
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
