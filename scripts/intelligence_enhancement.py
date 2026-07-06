#!/usr/bin/env python3
"""OPL Flow bridge for the CodexCont intelligence enhancement mode."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


INSTALLER_URL = "https://raw.githubusercontent.com/gaofeng21cn/one-person-lab-app/main/install.sh"
ACTION_IDS = {
    "status": "intelligence_enhancement_status",
    "enable": "intelligence_enhancement_enable",
    "disable": "intelligence_enhancement_disable",
    "repair": "intelligence_enhancement_repair",
    "uninstall": "intelligence_enhancement_uninstall",
}


def json_loads_or_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def command_result(command: list[str], result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": json_loads_or_text(result.stdout.strip()) if result.stdout.strip() else None,
        "stderr": result.stderr.strip() or None,
    }


def missing_command_result(command: list[str], exc: FileNotFoundError) -> dict[str, Any]:
    return {"command": command, "returncode": 127, "stdout": None, "stderr": str(exc)}


def default_opl_candidate() -> str | None:
    found = shutil.which("opl")
    if found:
        return found
    managed = Path.home() / ".opl" / "one-person-lab" / "bin" / "opl"
    if managed.exists() and os.access(managed, os.X_OK):
        return str(managed)
    return None


def opl_is_executable(opl: str) -> bool:
    if shutil.which(opl):
        return True
    return Path(opl).exists() and os.access(opl, os.X_OK)


def bootstrap_opl(installer_url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opl-flow-intelligence-") as tmp:
        installer = Path(tmp) / "install.sh"
        download_command = ["curl", "-fsSL", installer_url, "-o", str(installer)]
        install_command = ["bash", str(installer)]
        try:
            download = subprocess.run(
                download_command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            return {"status": "failed", "step": "download_installer", "result": missing_command_result(download_command, exc)}
        if download.returncode != 0:
            return {"status": "failed", "step": "download_installer", "result": command_result(download_command, download)}
        try:
            install = subprocess.run(
                install_command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            return {"status": "failed", "step": "run_installer", "result": missing_command_result(install_command, exc)}
        return {
            "status": "completed" if install.returncode == 0 else "failed",
            "step": "run_installer",
            "result": command_result(install_command, install),
        }


def run_opl_action(opl: str, action: str, confirmation: str | None) -> dict[str, Any]:
    command = [opl, "app", "action", "execute", "--action", ACTION_IDS[action], "--json"]
    if action == "uninstall":
        payload = {"confirmation": confirmation or ""}
        command.extend(["--payload", json.dumps(payload, separators=(",", ":"))])
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = command_result(command, result)
    if result.returncode != 0:
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    bootstrap_result = None
    opl = args.opl or default_opl_candidate()
    if not opl and args.bootstrap_opl:
        bootstrap_result = bootstrap_opl(args.installer_url)
        if bootstrap_result["status"] == "completed":
            opl = default_opl_candidate()
    if not opl:
        return 2, {
            "surface_kind": "opl_flow_intelligence_enhancement_bridge.v1",
            "status": "blocked",
            "reason": "opl_cli_missing",
            "action": args.action,
            "bootstrap": bootstrap_result,
            "required_command": f"curl -fsSL {args.installer_url} | bash",
            "retry_command": "python3 scripts/intelligence_enhancement.py enable --bootstrap-opl",
        }
    if not opl_is_executable(opl):
        return 2, {
            "surface_kind": "opl_flow_intelligence_enhancement_bridge.v1",
            "status": "blocked",
            "reason": "opl_cli_not_executable",
            "action": args.action,
            "opl_command": opl,
            "retry_command": "python3 scripts/intelligence_enhancement.py enable --bootstrap-opl",
        }

    try:
        action_result = run_opl_action(opl, args.action, args.confirmation)
        status_readback = action_result if args.action == "status" else run_opl_action(opl, "status", None)
    except RuntimeError as exc:
        return 1, {
            "surface_kind": "opl_flow_intelligence_enhancement_bridge.v1",
            "status": "failed",
            "reason": "opl_action_failed",
            "action": args.action,
            "opl_command": opl,
            "bootstrap": bootstrap_result,
            "error": json_loads_or_text(str(exc)),
        }

    return 0, {
        "surface_kind": "opl_flow_intelligence_enhancement_bridge.v1",
        "status": "completed",
        "action": args.action,
        "opl_command": opl,
        "bootstrap": bootstrap_result,
        "action_result": action_result,
        "status_readback": status_readback,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable, inspect, repair, disable, or uninstall OPL Flow intelligence enhancement mode."
    )
    parser.add_argument("action", choices=sorted(ACTION_IDS))
    parser.add_argument(
        "--bootstrap-opl",
        action="store_true",
        help="Install the OPL CLI through the canonical App installer if `opl` is missing.",
    )
    parser.add_argument("--installer-url", default=INSTALLER_URL)
    parser.add_argument("--opl", help="Path to an opl executable. Mainly useful for tests or managed runtimes.")
    parser.add_argument("--confirmation", help="Required value for uninstall: uninstall_codexcont")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.action == "uninstall" and args.confirmation != "uninstall_codexcont":
        payload = {
            "surface_kind": "opl_flow_intelligence_enhancement_bridge.v1",
            "status": "blocked",
            "reason": "uninstall_requires_confirmation",
            "required": {"confirmation": "uninstall_codexcont"},
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    code, payload = run(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
