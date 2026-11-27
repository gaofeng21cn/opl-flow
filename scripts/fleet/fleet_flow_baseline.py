"""Read a Framework v2 Flow registration and its active Codex experience baseline."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any

from .fleet_common import effective_codex_home, run


def _json_record(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _probe(args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return run(args, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _failure_code(result: subprocess.CompletedProcess) -> str | None:
    for stream in (result.stdout, result.stderr):
        error = _json_record(stream).get("error")
        if isinstance(error, dict):
            return error.get("code")
    return None


_VERSION_COMMANDS = {
    "officecli": ("officecli", "--version"),
    "mineru-open-api": ("mineru-open-api", "version"),
    "ffmpeg": ("ffmpeg", "-version"),
    "gh-stack": ("gh", "stack", "--version"),
}


def _capability_ready(member: dict, skill_roots: tuple[Path, ...]) -> bool:
    name = member.get("id")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        return False
    adapter = member.get("readiness_adapter")
    if member.get("kind") == "codex_skill" and adapter == "codex_skill_payload":
        return any((root / name / "SKILL.md").is_file() for root in skill_roots)
    if member.get("kind") != "cli":
        return False
    if adapter == "binary_version" and name in _VERSION_COMMANDS:
        result = _probe(list(_VERSION_COMMANDS[name]))
        return bool(result and result.returncode == 0 and (result.stdout or result.stderr).strip())
    if adapter == "agent_reach_doctor" and name == "agent-reach":
        result = _probe(["agent-reach", "doctor"])
        if result and result.returncode == 0:
            payload = _json_record(result.stdout)
            doctor = payload.get("result")
            if (payload.get("ok") is True and payload.get("action") == "doctor"
                    and isinstance(doctor, dict) and doctor.get("version")
                    and isinstance(doctor.get("channels"), list)):
                return True
        legacy = _probe(["agent-reach", "doctor", "--json"])
        channels = _json_record(legacy.stdout) if legacy and legacy.returncode == 0 else {}
        return bool(channels) and all(isinstance(channel, dict) and isinstance(channel.get("status"), str)
                                      for channel in channels.values())
    return False


def _installed_policy(plugin: dict, installed: dict) -> dict:
    version = plugin.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[\w.+-]+", version):
        return {}
    marketplace = plugin["pluginId"].split("@")[1]
    candidates = [effective_codex_home() / "plugins" / "cache" / marketplace / "opl-flow" / version]
    source = plugin.get("source")
    for raw in (installed.get("install_path"), source.get("path") if isinstance(source, dict) else None):
        if isinstance(raw, str) and Path(raw).is_absolute():
            candidates.append(Path(raw))
    for root in candidates:
        try:
            policy = _json_record((root / "contracts/workflow-policy.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        package = policy.get("package")
        if (policy.get("schema") == "opl_flow_workflow_policy.v4"
                and isinstance(package, dict) and package.get("id") == "opl-flow"
                and package.get("version") == version):
            return policy
    return {}


def read_v2_baseline(opl: str, receipt: dict[str, Any], plugin_skill_roots) -> dict[str, Any]:
    inspected = _probe([opl, "pack", "inspect", "opl-flow", "--json"])
    if inspected is None:
        return {**receipt, "reason": "pack_inspect_unavailable"}
    if inspected.returncode:
        if _failure_code(inspected) != "PACK_NOT_FOUND":
            return {**receipt, "reason": "pack_inspect_unavailable"}
        installed = {}
    else:
        installed = _json_record(inspected.stdout).get("installed")
        if (not isinstance(installed, dict) or installed.get("package_id") != "opl-flow"
                or not isinstance(installed.get("enabled"), bool)):
            return {**receipt, "reason": "invalid_pack_readback"}
    managed = installed.get("origin") == "opl"
    receipt = {**receipt, "framework_registered": bool(installed), "framework_managed": managed}
    if installed and not installed["enabled"]:
        return {**receipt, "reason": "framework_package_disabled"}

    native = _probe(["codex", "plugin", "list", "--json"])
    plugins = _json_record(native.stdout) if native and native.returncode == 0 else {}
    if not isinstance(plugins.get("installed"), list):
        return {**receipt, "reason": "codex_plugin_readback_unavailable"}
    allowed = {"opl-flow@opl-local"} if managed else {"opl-flow@opl-flow", "opl-flow@opl-local"}
    matches = [entry for entry in plugins["installed"] if isinstance(entry, dict)
               and entry.get("pluginId") in allowed and entry.get("installed") is True
               and entry.get("enabled") is True]
    if len(matches) != 1:
        return {**receipt, "reason": "codex_plugin_missing_or_disabled" if not matches else "ambiguous_codex_plugin"}
    plugin = matches[0]
    receipt = {**receipt, "carrier_id": plugin["pluginId"], "carrier_version": plugin.get("version")}
    if installed and installed.get("version") != plugin.get("version"):
        return {**receipt, "reason": "carrier_version_mismatch"}
    members = _installed_policy(plugin, installed).get("experience_baseline")
    if not isinstance(members, list) or not members:
        return {**receipt, "reason": "installed_flow_policy_unavailable"}
    if any(not isinstance(member, dict) or not isinstance(member.get("id"), str) for member in members):
        return {**receipt, "reason": "invalid_experience_baseline"}
    skill_roots = (effective_codex_home() / "skills", Path.home() / ".agents/skills", *plugin_skill_roots(plugins))
    failures = sorted({member["id"] for member in members if not _capability_ready(member, skill_roots)})
    return {**receipt, "status": "degraded" if failures else "current", "failure_ids": failures,
            "reason": "baseline_capabilities_unavailable" if failures else None}
