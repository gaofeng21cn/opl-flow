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
    "docs/compatibility.md",
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


def check_skill_metadata(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for skill_id in ("opl-flow", "risk-based-development-flow", "codex-ops-kit"):
        metadata_path = repo_root / "skills" / skill_id / "agents" / "openai.yaml"
        text = metadata_path.read_text(encoding="utf-8")
        required = (
            "interface:",
            "display_name:",
            "short_description:",
            "default_prompt:",
            f"${skill_id}",
        )
        for needle in required:
            if needle not in text:
                errors.append(f"{metadata_path.relative_to(repo_root)} must contain {needle}")
    return errors


def check_profile_templates(repo_root: Path) -> list[str]:
    errors: list[str] = []
    agents = (repo_root / "templates" / "AGENTS.md").read_text(encoding="utf-8")
    debugger = (repo_root / "templates" / "prompts" / "debugger.md").read_text(encoding="utf-8")
    verifier = (repo_root / "templates" / "prompts" / "verifier.md").read_text(encoding="utf-8")
    taste = (repo_root / "templates" / "TASTE.md").read_text(encoding="utf-8")
    required_pairs = (
        (agents, "risk-based development flow", "AGENTS.md must route risk-based development flow"),
        (agents, "codex-ops-kit", "AGENTS.md must route high-risk Codex ops to codex-ops-kit"),
        (agents, "完成度审计", "AGENTS.md must require Chinese completion audits"),
        (agents, "本因诊断", "AGENTS.md must require root-cause-first supervision"),
        (agents, "Root-Cause Depth Gate", "AGENTS.md must require root-cause depth gate"),
        (agents, "blocker-to-owner map", "AGENTS.md must require blocker-to-owner maps for stalls"),
        (agents, "ponytail-review", "AGENTS.md must route diff complexity review through ponytail-review"),
        (agents, "ponytail-audit", "AGENTS.md must route cleanup discovery through ponytail-audit"),
        (debugger, "根因深度门", "debugger prompt must preserve root-cause depth gate"),
        (debugger, "跨面证据", "debugger prompt must require cross-surface evidence"),
        (agents, "<!-- CODEGRAPH_START -->", "AGENTS.md must preserve the CodeGraph marker block"),
        (verifier, "验收对象的优先级", "verifier prompt must preserve audit-object priority"),
        (verifier, "完成度审计", "verifier prompt must preserve Chinese completion audit"),
        (verifier, "根因深度检查", "verifier prompt must verify root-cause depth"),
        (verifier, "focused tests", "verifier prompt must reject focused-tests-as-readiness claims"),
        (taste, "AI 怎么干活", "TASTE.md must define general AI work principles"),
        (taste, "AI 先行，合同托底", "TASTE.md must prioritize AI execution over over-contracting"),
        (taste, "交付推进", "TASTE.md must prioritize delivery progress"),
        (taste, "简单优先", "TASTE.md must preserve simplicity preference"),
        (taste, "精准改动", "TASTE.md must preserve surgical-change preference"),
        (taste, "证据匹配风险", "TASTE.md must preserve risk-matched evidence preference"),
        (taste, "风险分层优先于测试仪式", "TASTE.md must preserve risk-over-ritual preference"),
        (taste, "逐项覆盖原始目标或已落盘计划", "TASTE.md must bind completion claims to plan coverage"),
        (taste, "OPL 怎么开发", "TASTE.md must route OPL-specific development rules back to project surfaces"),
    )
    for text, needle, message in required_pairs:
        if needle not in text:
            errors.append(message)
    compose_result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "profile_compose.py"), "check", "--repo-root", str(repo_root)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if compose_result.returncode != 0:
        errors.append(
            "templates/AGENTS.md must match profile modules: "
            + (compose_result.stdout or compose_result.stderr).strip()
        )
    return errors


def check_docs_describe_compatibility(repo_root: Path) -> list[str]:
    errors: list[str] = []
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    setup = (repo_root / "docs" / "new-machine-codex-setup.md").read_text(encoding="utf-8")
    compatibility = (repo_root / "docs" / "compatibility.md").read_text(encoding="utf-8")
    skill = (repo_root / "skills" / "opl-flow" / "SKILL.md").read_text(encoding="utf-8")
    lane_closeout = (repo_root / "skills" / "codex-ops-kit" / "references" / "lane-closeout.md").read_text(encoding="utf-8")
    required_pairs = (
        (readme, "Compatibility With OPL App Full", "README must document OPL App Full compatibility"),
        (readme, "python3 scripts/check_companion_skills.py", "README must document companion skill checker"),
        (setup, "OPL App Full / companion layers normally cover", "new-machine guide must describe Full companion layer coverage"),
        (setup, "Workflow Profile", "new-machine guide must classify OPL Flow as the Workflow Profile layer"),
        (setup, "python3 ~/opl-flow/scripts/check_companion_skills.py", "new-machine guide must include companion skill check"),
        (setup, "codex plugin add ponytail@ponytail", "new-machine guide must document optional Ponytail install"),
        (setup, "Use `ponytail-audit` for whole-repo or cross-repo cleanup candidate discovery", "new-machine guide must explain Ponytail audit vs review routing"),
        (skill, "compatible with One Person Lab App Full installs", "skill must describe OPL App Full compatibility"),
        (skill, "Workflow Profile layer only", "skill must classify OPL Flow as the Workflow Profile layer"),
        (skill, "risk-based-development-flow", "skill must name risk-based-development-flow as profile-native"),
        (skill, "codex-ops-kit", "skill must name codex-ops-kit as profile-native"),
        (skill, "Ponytail is compatible as an optional simplification lens", "skill must describe optional Ponytail boundary"),
        (skill, "Route Ponytail by surface", "skill must route Ponytail audit vs review by surface"),
        (skill, "Root-Cause Supervision", "skill must document root-cause-first supervision"),
        (skill, "Root-Cause Depth Gate", "skill must document root-cause depth gate"),
        (skill, "blocker-to-owner map", "skill must require blocker-to-owner maps for stalls"),
        (lane_closeout, "Root-Cause Depth Guard", "lane closeout must require root-cause depth guard"),
        (lane_closeout, "L2 cross-surface evidence", "lane closeout must require cross-surface evidence"),
        (lane_closeout, "Reports that only rename a symptom", "lane closeout must reject symptom-only closeout"),
        (lane_closeout, "Complexity Regression Gate", "lane closeout must require complexity regression gate"),
        (lane_closeout, "ponytail-review", "lane closeout must mention ponytail-review for lane diffs"),
        (compatibility, "Codex AGENTS.md / skills", "compatibility doc must cover Codex customization boundary"),
        (compatibility, "Superpowers", "compatibility doc must cover Superpowers boundary"),
        (compatibility, "Runtime Substrate", "compatibility doc must cover Runtime Substrate boundary"),
        (compatibility, "Capability Packages", "compatibility doc must cover Capability Packages boundary"),
        (compatibility, "Codex Surface sync", "compatibility doc must cover Codex Surface sync boundary"),
        (compatibility, "Ponytail", "compatibility doc must cover Ponytail boundary"),
        (compatibility, "Trellis", "compatibility doc must cover Trellis boundary"),
        (compatibility, "Claude Code", "compatibility doc must cover Claude Code practices"),
        (compatibility, "GitHub Agentic Workflows", "compatibility doc must cover GitHub Agentic Workflows practices"),
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
    for skill_id in ("risk-based-development-flow", "codex-ops-kit"):
        status = payload.get("skills", {}).get(skill_id, {})
        if "bundled_repo" not in status.get("sources", []):
            errors.append(f"companion skill check must classify {skill_id} as bundled_repo: {status}")
        if not status.get("match_details"):
            errors.append(f"companion skill check must include match_details for {skill_id}: {status}")
    compatibility = payload.get("compatibility", {})
    if compatibility.get("opl_flow_profile_ready") is not True:
        errors.append(f"companion skill check must keep core profile ready by default: {compatibility}")
    if compatibility.get("opl_flow_full_guardrails_ready") is not True:
        errors.append(f"companion skill check must report bundled full guardrails: {compatibility}")
    ponytail = payload.get("ponytail", {})
    if ponytail.get("boundary") != "optional_simplification_lens":
        errors.append(f"companion skill check must describe Ponytail as optional simplification lens: {ponytail}")
    if "ponytail" not in payload.get("plugins", {}):
        errors.append(f"companion skill check must include optional Ponytail plugin status: {payload.get('plugins')}")

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
        payload = json.loads(result.stdout)
        if payload.get("profile_status") != "current":
            errors.append(f"fresh install profile must verify current: {payload.get('profile_status')}")
        required_files = payload.get("required_files", [])
        for suffix in (
            "skills/risk-based-development-flow/SKILL.md",
            "skills/risk-based-development-flow/agents/openai.yaml",
            "skills/codex-ops-kit/SKILL.md",
            "skills/codex-ops-kit/agents/openai.yaml",
        ):
            if suffix not in required_files:
                errors.append(f"install verify required_files must include guardrail artifact: {suffix}")
            expected = str(tmp_path / "plugins" / "opl-flow" / suffix)
            if expected in payload.get("missing", []):
                errors.append(f"install verify must include guardrail artifact: {expected}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        codex_home = tmp_path / "codex"
        codex_home.mkdir()
        (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")
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
            str(codex_home),
        ]
        result = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            errors.append(f"existing profile install should create merge packet without failing: {result.stdout} {result.stderr}".strip())
            return errors
        payload = json.loads(result.stdout)
        profile = payload.get("profile", {})
        if profile.get("status") != "requires_codex_semantic_merge":
            errors.append(f"existing profile install must require semantic merge: {profile}")
        if (codex_home / "AGENTS.md").read_text(encoding="utf-8") != "custom user profile\n":
            errors.append("existing profile install must not overwrite user AGENTS.md")
        merge_packet = profile.get("merge_packet")
        if not merge_packet or not (Path(merge_packet) / "merge-plan.json").exists():
            errors.append(f"existing profile install must create merge packet: {profile}")
        verify_result = subprocess.run(cmd + ["--verify-only"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        verify_payload = json.loads(verify_result.stdout)
        if verify_result.returncode == 0 or verify_payload.get("profile_status") != "merge_required":
            errors.append(f"verify-only must report merge_required for existing user profile: {verify_result.stdout} {verify_result.stderr}".strip())
    return errors


def check_repo_profile(repo_root: Path) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "target-repo"
        repo.mkdir()
        (repo / "AGENTS.md").write_text("# Target\n\nLocal rule.\n", encoding="utf-8")
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
    errors.extend(check_skill_metadata(repo_root))
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
