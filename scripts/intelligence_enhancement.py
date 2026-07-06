#!/usr/bin/env python3
"""CodexCont-backed OPL Flow intelligence enhancement mode."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODEXCONT_SOURCE = "git+https://github.com/ZhenHuangLab/CodexCont"
DEFAULT_UPSTREAM_BASE_URL = "https://gflabtoken.cn/v1"
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8787
PROXY_BASE_URL = f"http://{PROXY_HOST}:{PROXY_PORT}/v1"
SERVICE_LABEL = "org.onepersonlab.codexcont"
SERVICE_SCRIPT_FILE = "opl-flow-codexcont-foreground.sh"
RECEIPT_FILE = "opl-flow-intelligence-enhancement.json"
ACTION_IDS = {
    "status": "intelligence_enhancement_status",
    "enable": "intelligence_enhancement_enable",
    "disable": "intelligence_enhancement_disable",
    "repair": "intelligence_enhancement_repair",
    "uninstall": "intelligence_enhancement_uninstall",
}


def normalize(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def quote(value: str) -> str:
    return json.dumps(value)


def home_dir() -> Path:
    return Path(normalize(os.environ.get("HOME")) or str(Path.home()))


def codex_home() -> Path:
    return Path(normalize(os.environ.get("CODEX_HOME")) or str(home_dir() / ".codex"))


def codexcont_home() -> Path:
    return Path(normalize(os.environ.get("OPL_CODEXCONT_HOME")) or str(home_dir() / ".codexcont"))


def codex_config_path() -> Path:
    return codex_home() / "config.toml"


def codexcont_config_path() -> Path:
    return codexcont_home() / "config.toml"


def receipt_path() -> Path:
    return codexcont_home() / RECEIPT_FILE


def service_script_path() -> Path:
    return codexcont_home() / SERVICE_SCRIPT_FILE


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def strip_inline_comment(line: str) -> str:
    in_single = False
    in_double = False
    previous = ""
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].strip()
        previous = char
    return line.strip()


def parse_value(value: str) -> str:
    trimmed = value.strip()
    if trimmed.startswith('"') and trimmed.endswith('"'):
        parsed = json.loads(trimmed)
        return str(parsed)
    if trimmed.startswith("'") and trimmed.endswith("'"):
        return trimmed[1:-1]
    return trimmed


def section_range(lines: list[str], section: str | None) -> tuple[int, int] | None:
    if section is None:
        end = next((i for i, line in enumerate(lines) if strip_inline_comment(line).startswith("[")), len(lines))
        return 0, end
    header = f"[{section}]"
    start = next((i for i, line in enumerate(lines) if strip_inline_comment(line) == header), -1)
    if start == -1:
        return None
    end = next((i for i in range(start + 1, len(lines)) if strip_inline_comment(lines[i]).startswith("[")), len(lines))
    return start + 1, end


def read_toml_value(contents: str, section: str | None, key: str) -> str | None:
    lines = contents.splitlines()
    slot = section_range(lines, section)
    if slot is None:
        return None
    start, end = slot
    for line in lines[start:end]:
        clean = strip_inline_comment(line)
        if clean.startswith(f"{key}") and "=" in clean and clean.split("=", 1)[0].strip() == key:
            return parse_value(clean.split("=", 1)[1])
    return None


def upsert_toml_value(contents: str, section: str | None, key: str, raw_value: str) -> str:
    lines = contents.rstrip().splitlines() if contents.strip() else []
    slot = section_range(lines, section)
    if slot is None and section is not None:
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        slot = len(lines), len(lines)
    if slot is None:
        slot = 0, 0
    start, end = slot
    for index in range(start, end):
        clean = strip_inline_comment(lines[index])
        if clean.startswith(f"{key}") and "=" in clean and clean.split("=", 1)[0].strip() == key:
            lines[index] = f"{key} = {raw_value}"
            return "\n".join(lines) + "\n"
    lines.insert(end, f"{key} = {raw_value}")
    return "\n".join(lines) + "\n"


def normalize_base_url(value: str | None) -> str | None:
    return normalize(value).rstrip("/") if normalize(value) else None


def responses_url_from_base(base_url: str | None) -> str:
    normalized = normalize_base_url(base_url) or DEFAULT_UPSTREAM_BASE_URL
    return normalized if normalized.endswith("/responses") else f"{normalized}/responses"


def base_url_from_responses(url: str | None) -> str | None:
    normalized = normalize_base_url(url)
    return normalized[:-10] if normalized and normalized.endswith("/responses") else normalized


def codex_profile() -> dict[str, Any]:
    config_path = codex_config_path()
    contents = read_text(config_path)
    provider_id = read_toml_value(contents, None, "model_provider") or "gflab"
    provider_section = f"model_providers.{provider_id}"
    return {
        "config_path": str(config_path),
        "contents": contents,
        "provider_id": provider_id,
        "provider_section": provider_section,
        "provider_base_url": read_toml_value(contents, provider_section, "base_url"),
    }


def read_receipt() -> dict[str, Any] | None:
    if not receipt_path().is_file():
        return None
    try:
        parsed = json.loads(receipt_path().read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_codexcont_upstream_url() -> str | None:
    return read_toml_value(read_text(codexcont_config_path()), "upstream", "url")


def previous_provider_base_url(current_base_url: str | None, upstream_url: str | None, receipt: dict[str, Any] | None) -> str:
    receipt_base = normalize_base_url(normalize((receipt or {}).get("previous_provider_base_url")))
    if receipt_base and receipt_base != PROXY_BASE_URL:
        return receipt_base
    upstream_base = base_url_from_responses(upstream_url)
    if upstream_base and upstream_base != PROXY_BASE_URL:
        return upstream_base
    current = normalize_base_url(current_base_url)
    if current and current != PROXY_BASE_URL:
        return current
    return DEFAULT_UPSTREAM_BASE_URL


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def write_receipt(payload: dict[str, Any]) -> str:
    return write_json(receipt_path(), {
        "surface_kind": "opl_flow_intelligence_enhancement_receipt.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "codexcont",
        "proxy_base_url": PROXY_BASE_URL,
        **payload,
    })


def backup_current_files(action: str) -> str:
    backup_root = codexcont_home() / "backup" / f"{timestamp()}-{action}"
    backup_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for source, target in (
        (codex_config_path(), "codex.config.toml"),
        (codexcont_config_path(), "codexcont.config.toml"),
        (receipt_path(), RECEIPT_FILE),
    ):
        if source.exists():
            shutil.copy2(source, backup_root / target)
            copied.append(target)
    (backup_root / "RESTORE.md").write_text(
        f"# OPL Flow intelligence enhancement backup\n\naction: {action}\ncreated_at: {datetime.now(timezone.utc).isoformat()}\ncopied: {', '.join(copied) or 'none'}\n",
        encoding="utf-8",
    )
    return str(backup_root)


def write_codex_proxy_config(provider_base_url: str) -> None:
    profile = codex_profile()
    contents = profile["contents"]
    if not contents:
        contents = "\n".join([
            'model_provider = "gflab"',
            'model = "gpt-5.5"',
            "",
            "[model_providers.gflab]",
            'name = "gflab"',
            'wire_api = "responses"',
            "",
        ])
    contents = upsert_toml_value(contents, None, "model_provider", quote(profile["provider_id"]))
    contents = upsert_toml_value(contents, profile["provider_section"], "name", quote(profile["provider_id"]))
    contents = upsert_toml_value(contents, profile["provider_section"], "base_url", quote(provider_base_url))
    contents = upsert_toml_value(contents, profile["provider_section"], "wire_api", quote("responses"))
    path = Path(profile["config_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


def write_codexcont_config(upstream_responses_url: str) -> None:
    contents = read_text(codexcont_config_path())
    if not contents:
        contents = "\n".join([
            "[server]",
            f"host = {quote(PROXY_HOST)}",
            f"port = {PROXY_PORT}",
            'listen_paths = ["/v1/responses"]',
            "enable_websocket = true",
            "",
            "[upstream]",
            f"url = {quote(upstream_responses_url)}",
            'mode = "fixed"',
            "",
            "[auth]",
            'mode = "passthrough"',
            'access_token = ""',
            'chatgpt_account_id = ""',
            "",
            "[continue]",
            "enabled = true",
            "truncation_step = 518",
            "max_continue = 3",
            "min_n = 1",
            "max_n = 6",
            'method = "commentary"',
            'marker_text = "Continue thinking..."',
            "forward_marker = true",
            "",
        ])
    contents = upsert_toml_value(contents, "server", "host", quote(PROXY_HOST))
    contents = upsert_toml_value(contents, "server", "port", str(PROXY_PORT))
    contents = upsert_toml_value(contents, "server", "listen_paths", '["/v1/responses"]')
    contents = upsert_toml_value(contents, "upstream", "url", quote(upstream_responses_url))
    contents = upsert_toml_value(contents, "upstream", "mode", quote("fixed"))
    codexcont_config_path().parent.mkdir(parents=True, exist_ok=True)
    codexcont_config_path().write_text(contents, encoding="utf-8")
    codexcont_config_path().chmod(0o600)


def codexcont_command(args: list[str]) -> list[str]:
    return [normalize(os.environ.get("OPL_CODEXCONT_UVX")) or "uvx", "--from", CODEXCONT_SOURCE, "codexcont", *args]


def run_command(command: list[str], timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(json.dumps({"command": command, "exit_code": 127, "stderr": str(exc)}, ensure_ascii=False)) from exc
    stdout = (result.stdout or "").strip()
    if result.returncode != 0 and not (command[-2:] == ["install", "-y"] and "Install complete." in stdout):
        raise RuntimeError(json.dumps({"command": command, "exit_code": result.returncode, "stderr": (result.stderr or "").strip(), "stdout": stdout}, ensure_ascii=False))
    return {"command": command, "stdout": stdout, "stderr": (result.stderr or "").strip()}


def run_codexcont(args: list[str]) -> dict[str, Any]:
    result = run_command(codexcont_command(args))
    result["command"] = ["uvx", "--from", CODEXCONT_SOURCE, "codexcont", *args]
    return result


def service_mode() -> str:
    override = normalize(os.environ.get("OPL_CODEXCONT_SERVICE_MODE"))
    if override in {"manual", "launchd", "systemd", "container"}:
        return override
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith("linux"):
        return "container" if Path("/.dockerenv").exists() or normalize(os.environ.get("container")) else "systemd"
    return "manual"


def service_definition_path(mode: str | None = None) -> Path:
    actual = mode or service_mode()
    if actual == "launchd":
        return home_dir() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
    if actual == "systemd":
        return home_dir() / ".config" / "systemd" / "user" / f"{SERVICE_LABEL}.service"
    return codexcont_home() / "opl-flow-service.json"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def write_service_script() -> str:
    command = codexcont_command(["start", "-f"])
    script = "\n".join([
        "#!/bin/sh",
        "set -eu",
        f"export HOME={quote(str(home_dir()))}",
        f"export CODEX_HOME={quote(str(codex_home()))}",
        f"export OPL_CODEXCONT_HOME={quote(str(codexcont_home()))}",
        f"export PATH={quote(os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'))}",
        "exec " + " ".join(shell_quote(part) for part in command),
        "",
    ])
    service_script_path().parent.mkdir(parents=True, exist_ok=True)
    service_script_path().write_text(script, encoding="utf-8")
    service_script_path().chmod(0o755)
    return str(service_script_path())


def service_command(command: str, args: list[str]) -> dict[str, Any]:
    if os.environ.get("OPL_CODEXCONT_SERVICE_SKIP") == "1":
        return {"command": [command, *args], "skipped": True, "stdout": "", "stderr": ""}
    try:
        result = subprocess.run([command, *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except FileNotFoundError as exc:
        return {"command": [command, *args], "skipped": False, "status": 127, "stdout": "", "stderr": str(exc)}
    return {"command": [command, *args], "skipped": False, "status": result.returncode, "stdout": (result.stdout or "").strip(), "stderr": (result.stderr or "").strip()}


def install_service_definition() -> dict[str, Any]:
    mode = service_mode()
    script_path = write_service_script()
    definition_path = service_definition_path(mode)
    definition_path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "launchd":
        definition_path.write_text("\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
            '<plist version="1.0">',
            '<dict>',
            '  <key>Label</key>',
            f"  <string>{SERVICE_LABEL}</string>",
            '  <key>ProgramArguments</key>',
            '  <array>',
            '    <string>/bin/sh</string>',
            f"    <string>{script_path}</string>",
            '  </array>',
            '  <key>RunAtLoad</key>',
            '  <true/>',
            '  <key>KeepAlive</key>',
            '  <true/>',
            '  <key>StandardOutPath</key>',
            f"  <string>{codexcont_home() / 'launchd.out.log'}</string>",
            '  <key>StandardErrorPath</key>',
            f"  <string>{codexcont_home() / 'launchd.err.log'}</string>",
            '</dict>',
            '</plist>',
            "",
        ]), encoding="utf-8")
        domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else None
        return {
            "mode": mode,
            "script_path": script_path,
            "definition_path": str(definition_path),
            "commands": [] if domain is None else [
                service_command("launchctl", ["bootout", domain, str(definition_path)]),
                service_command("launchctl", ["bootstrap", domain, str(definition_path)]),
                service_command("launchctl", ["kickstart", "-k", f"{domain}/{SERVICE_LABEL}"]),
            ],
        }
    if mode == "systemd":
        definition_path.write_text("\n".join([
            "[Unit]",
            "Description=OPL Flow CodexCont local proxy",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart=/bin/sh {script_path}",
            "Restart=always",
            "RestartSec=3",
            f"Environment=HOME={home_dir()}",
            f"Environment=CODEX_HOME={codex_home()}",
            f"Environment=OPL_CODEXCONT_HOME={codexcont_home()}",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]), encoding="utf-8")
        return {
            "mode": mode,
            "script_path": script_path,
            "definition_path": str(definition_path),
            "commands": [
                service_command("systemctl", ["--user", "daemon-reload"]),
                service_command("systemctl", ["--user", "enable", "--now", f"{SERVICE_LABEL}.service"]),
            ],
        }
    write_json(definition_path, {
        "surface_kind": "opl_flow_codexcont_container_service_manifest.v1",
        "mode": mode,
        "service_label": SERVICE_LABEL,
        "script_path": script_path,
        "command": ["python3", str(Path(__file__).resolve()), "repair"],
        "startup_policy": "container_entrypoint_or_opl_system_startup_maintenance_must_call_repair" if mode == "container" else "manual_repair_action",
    })
    return {"mode": mode, "script_path": script_path, "definition_path": str(definition_path), "commands": []}


def stop_service_definition() -> dict[str, Any]:
    mode = service_mode()
    definition_path = service_definition_path(mode)
    if mode == "launchd":
        domain = f"gui/{os.getuid()}" if hasattr(os, "getuid") else None
        return {"mode": mode, "definition_path": str(definition_path), "commands": [] if domain is None else [service_command("launchctl", ["bootout", domain, str(definition_path)])]}
    if mode == "systemd":
        return {
            "mode": mode,
            "definition_path": str(definition_path),
            "commands": [
                service_command("systemctl", ["--user", "disable", "--now", f"{SERVICE_LABEL}.service"]),
                service_command("systemctl", ["--user", "daemon-reload"]),
            ],
        }
    return {"mode": mode, "definition_path": str(definition_path), "commands": []}


def service_status() -> dict[str, Any]:
    mode = service_mode()
    return {
        "service_label": SERVICE_LABEL,
        "mode": mode,
        "definition_path": str(service_definition_path(mode)),
        "script_path": str(service_script_path()),
        "definition_installed": service_definition_path(mode).exists(),
        "script_installed": service_script_path().exists(),
        "persistence_policy": "macos_launch_agent_run_at_load_keep_alive" if mode == "launchd" else "linux_systemd_user_enable_now_restart_always" if mode == "systemd" else "container_entrypoint_or_startup_maintenance_repair" if mode == "container" else "manual_start_only",
    }


def externally_supervised(mode: str) -> bool:
    return mode in {"launchd", "systemd"}


def pid_running() -> bool:
    pid_path = codexcont_home() / "codexcont.pid"
    if not pid_path.exists():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def tcp_reachable() -> bool:
    try:
        with socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def build_status() -> dict[str, Any]:
    profile = codex_profile()
    provider_base_url = normalize_base_url(profile["provider_base_url"])
    upstream_url = normalize_base_url(read_codexcont_upstream_url())
    reachable = tcp_reachable()
    enabled = provider_base_url == PROXY_BASE_URL
    return {
        "opl_flow_intelligence_enhancement": {
            "surface_kind": "opl_flow_intelligence_enhancement_status.v1",
            "provider": "codexcont",
            "status": "enabled_running" if enabled and reachable else "enabled_proxy_not_reachable" if enabled else "disabled",
            "enabled": enabled,
            "proxy_running": reachable,
            "pid_running": pid_running(),
            "proxy_base_url": PROXY_BASE_URL,
            "codex_config_path": profile["config_path"],
            "codex_model_provider": profile["provider_id"],
            "codex_provider_base_url": provider_base_url,
            "codexcont_home": str(codexcont_home()),
            "codexcont_config_path": str(codexcont_config_path()),
            "codexcont_configured": upstream_url is not None,
            "service": service_status(),
            "upstream_responses_url": upstream_url,
            "previous_provider_base_url": previous_provider_base_url(provider_base_url, upstream_url, read_receipt()),
            "receipt_path": str(receipt_path()) if receipt_path().exists() else None,
            "action_ids": ACTION_IDS,
            "authority_boundary": {
                "owner": "opl_flow",
                "app_shell_role": "switch_invokes_action_only",
                "mutates_codex_config": True,
                "mutates_codexcont_config": True,
                "writes_domain_truth": False,
            },
        }
    }


def dry_run_result(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "opl_flow_intelligence_enhancement_action": {
            "surface_kind": "opl_flow_intelligence_enhancement_action_preflight.v1",
            "action": action,
            "status": "dry_run",
            "requested": payload,
            "provider": "codexcont",
            "proxy_base_url": PROXY_BASE_URL,
            "command_preview": ["python3", str(Path(__file__).resolve()), action],
            "write_targets": [] if action == "status" else [str(codex_config_path()), str(codexcont_config_path()), str(receipt_path())],
            "authority_boundary": {
                "owner": "opl_flow",
                "can_write_domain_truth": False,
                "can_authorize_release_ready": False,
                "shell_must_not_edit_configs_directly": True,
            },
        }
    }


def enable_mode() -> dict[str, Any]:
    profile = codex_profile()
    previous = previous_provider_base_url(profile["provider_base_url"], read_codexcont_upstream_url(), read_receipt())
    backup = backup_current_files("enable")
    install = run_codexcont(["install", "-y"])
    write_codexcont_config(responses_url_from_base(previous))
    write_codex_proxy_config(PROXY_BASE_URL)
    mode = service_mode()
    stop_background = run_codexcont(["stop"]) if externally_supervised(mode) else None
    service = install_service_definition()
    receipt = write_receipt({"status": "enabled", "previous_provider_base_url": previous, "upstream_responses_url": responses_url_from_base(previous), "backup_path": backup, "service": service})
    start = None if externally_supervised(service["mode"]) else run_codexcont(["restart"])
    return {
        "opl_flow_intelligence_enhancement_action": {
            "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
            "action": "enable",
            "status": "completed",
            "backup_path": backup,
            "receipt_path": receipt,
            "commands": [install["command"], *([stop_background["command"]] if stop_background else []), *([start["command"]] if start else [])],
            "service": service,
            "status_readback": build_status()["opl_flow_intelligence_enhancement"],
        }
    }


def repair_mode() -> dict[str, Any]:
    before = build_status()["opl_flow_intelligence_enhancement"]
    upstream = responses_url_from_base(before["previous_provider_base_url"])
    install = run_codexcont(["install", "-y"])
    write_codexcont_config(upstream)
    if before["enabled"]:
        write_codex_proxy_config(PROXY_BASE_URL)
    mode = service_mode()
    stop_background = run_codexcont(["stop"]) if externally_supervised(mode) else None
    service = install_service_definition()
    start = None if externally_supervised(service["mode"]) else run_codexcont(["restart"])
    receipt = write_receipt({"status": "enabled" if before["enabled"] else "repaired_disabled", "previous_provider_base_url": before["previous_provider_base_url"], "upstream_responses_url": upstream, "service": service})
    return {
        "opl_flow_intelligence_enhancement_action": {
            "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
            "action": "repair",
            "status": "completed",
            "receipt_path": receipt,
            "commands": [install["command"], *([stop_background["command"]] if stop_background else []), *([start["command"]] if start else [])],
            "service": service,
            "status_readback": build_status()["opl_flow_intelligence_enhancement"],
        }
    }


def disable_mode() -> dict[str, Any]:
    profile = codex_profile()
    previous = previous_provider_base_url(profile["provider_base_url"], read_codexcont_upstream_url(), read_receipt())
    backup = backup_current_files("disable")
    service = stop_service_definition()
    stop = None if externally_supervised(service["mode"]) else run_codexcont(["stop"])
    write_codex_proxy_config(previous)
    receipt = write_receipt({"status": "disabled", "previous_provider_base_url": previous, "backup_path": backup, "service": service})
    return {
        "opl_flow_intelligence_enhancement_action": {
            "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
            "action": "disable",
            "status": "completed",
            "backup_path": backup,
            "receipt_path": receipt,
            "commands": [stop["command"]] if stop else [],
            "service": service,
            "status_readback": build_status()["opl_flow_intelligence_enhancement"],
        }
    }


def uninstall_mode(confirmation: str | None) -> dict[str, Any]:
    if confirmation != "uninstall_codexcont":
        raise ValueError("uninstall_requires_confirmation")
    disabled = disable_mode()
    archive = home_dir() / ".codexcont-uninstalled" / timestamp()
    if codexcont_home().exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        codexcont_home().rename(archive)
    return {
        "opl_flow_intelligence_enhancement_action": {
            "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
            "action": "uninstall",
            "status": "completed",
            "archive_path": str(archive) if archive.exists() else None,
            "disable_result": disabled["opl_flow_intelligence_enhancement_action"],
            "status_readback": build_status()["opl_flow_intelligence_enhancement"],
        }
    }


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    payload = json.loads(args.payload) if args.payload else {}
    if args.dry_run and args.action != "status":
        return 0, dry_run_result(args.action, payload)
    try:
        if args.action == "status":
            return 0, build_status()
        if args.action == "enable":
            return 0, enable_mode()
        if args.action == "repair":
            return 0, repair_mode()
        if args.action == "disable":
            return 0, disable_mode()
        return 0, uninstall_mode(args.confirmation or normalize(payload.get("confirmation")))
    except ValueError as exc:
        if str(exc) == "uninstall_requires_confirmation":
            return 2, {
                "opl_flow_intelligence_enhancement_action": {
                    "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
                    "action": "uninstall",
                    "status": "blocked",
                    "reason": "uninstall_requires_confirmation",
                    "required": {"confirmation": "uninstall_codexcont"},
                }
            }
        raise
    except RuntimeError as exc:
        return 1, {
            "opl_flow_intelligence_enhancement_action": {
                "surface_kind": "opl_flow_intelligence_enhancement_action_result.v1",
                "action": args.action,
                "status": "failed",
                "reason": "codexcont_command_failed",
                "error": json.loads(str(exc)),
            }
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enable, inspect, repair, disable, or uninstall OPL Flow intelligence enhancement mode.")
    parser.add_argument("action", choices=sorted(ACTION_IDS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--payload", default="")
    parser.add_argument("--confirmation")
    parser.add_argument("--bootstrap-opl", action="store_true", help="Accepted for compatibility; this script owns CodexCont directly and does not require OPL CLI.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    code, payload = run(parse_args(sys.argv[1:] if argv is None else argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
