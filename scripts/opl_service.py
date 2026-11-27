"""Cross-platform background event-router service manager and CLI wrapper.

Zero Fleet imports. Never runs external side effects when dry_run=True.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import subprocess
import sys
from typing import Any, Callable

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime


SERVICE_PREFIX = "dev.one-person-lab.opl-flow-router"
WRAPPER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CONTROL_BRIDGES = ("auto", "codex", "antigravity")


class ServiceError(RuntimeError):
    pass


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _default_run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise ServiceError((proc.stderr or proc.stdout or f"{argv[0]} exited {proc.returncode}").strip())
    return proc


def _atomic_write_text(path: Path, text: str, *, mode: int) -> None:
    runtime.atomic_write_text(path, text, mode=mode)


def instance_hash(instance_root: Path) -> str:
    return hashlib.sha256(str(instance_root.expanduser().resolve()).encode("utf-8")).hexdigest()


def service_label(instance_root: Path) -> str:
    return f"{SERVICE_PREFIX}.{instance_hash(instance_root)[:12]}"


def default_service_log_dir(instance_root: Path) -> Path:
    return Path.home() / ".local/state/opl-flow/router" / instance_hash(instance_root)[:16] / "logs"


def _resolve_bridge(
    *,
    bridge: str | None,
    use_codex_bridge: bool,
    control_hook_argv: list[str] | None,
) -> str | None:
    if control_hook_argv is not None:
        return "custom"
    if bridge is not None:
        if bridge not in CONTROL_BRIDGES:
            raise ServiceError(f"unsupported control bridge: {bridge!r}")
        return bridge
    return "codex" if use_codex_bridge else None


def _detect_bridge_from_argv(argv: list[str]) -> str | None:
    if "--control-hook-json" in argv:
        return "custom"
    if "--bridge" in argv:
        idx = argv.index("--bridge")
        if idx + 1 < len(argv) and argv[idx + 1] in CONTROL_BRIDGES:
            return argv[idx + 1]
    if "--use-codex-bridge" in argv:
        return "codex"
    return None


def _detect_service_bridge(service_path: Path, target_platform: str) -> str | None:
    if not service_path.is_file():
        return None
    try:
        if target_platform == "Darwin":
            parsed = plistlib.loads(service_path.read_bytes())
            argv = parsed.get("ProgramArguments") if isinstance(parsed, dict) else None
            if isinstance(argv, list):
                return _detect_bridge_from_argv([str(item) for item in argv])
        elif target_platform == "Linux":
            text = service_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("ExecStart="):
                    return _detect_bridge_from_argv(shlex.split(line[len("ExecStart=") :]))
    except Exception:
        return None
    return None


def default_router_argv(
    instance_root: Path,
    *,
    flow_root: Path,
    interval_seconds: float = 15.0,
    use_codex_bridge: bool = True,
    bridge: str | None = None,
    codex_bin: str | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    control_hook_argv: list[str] | None = None,
    event_state_dir: Path | None = None,
    cursor_file: Path | None = None,
    python_bin: str | None = None,
) -> list[str]:
    resolved_instance = instance_root.expanduser().resolve()
    resolved_flow = flow_root.expanduser().resolve()
    resolved_bridge = _resolve_bridge(
        bridge=bridge,
        use_codex_bridge=use_codex_bridge,
        control_hook_argv=control_hook_argv,
    )
    argv = [
        python_bin or sys.executable,
        str(resolved_flow / "scripts/opl_workflow.py"),
        "router",
        "watch",
        "--instance",
        str(resolved_instance),
        "--interval",
        str(interval_seconds),
    ]
    if event_state_dir is not None:
        argv.extend(["--event-state-dir", str(event_state_dir.expanduser().resolve())])
    if cursor_file is not None:
        argv.extend(["--cursor-file", str(cursor_file.expanduser().resolve())])
    if control_hook_argv is not None:
        argv.extend(["--control-hook-json", json.dumps(list(control_hook_argv), ensure_ascii=False)])
    elif resolved_bridge == "auto":
        argv.extend(["--bridge", "auto"])
        if codex_bin:
            argv.extend(["--codex-bin", codex_bin])
        if agy_bin:
            argv.extend(["--agy-bin", agy_bin])
        if model:
            argv.extend(["--model", model])
        if effort:
            argv.extend(["--effort", effort])
    elif resolved_bridge == "antigravity":
        argv.extend(["--bridge", "antigravity"])
        if agy_bin:
            argv.extend(["--agy-bin", agy_bin])
        if model:
            argv.extend(["--model", model])
        if effort:
            argv.extend(["--effort", effort])
    elif resolved_bridge == "codex":
        argv.append("--use-codex-bridge")
        if codex_bin:
            argv.extend(["--codex-bin", codex_bin])
        if model:
            argv.extend(["--model", model])
    return argv


def render_macos_plist(
    label: str,
    argv: list[str],
    *,
    log_dir: Path,
    home_dir: Path | None = None,
    path_env: str | None = None,
) -> str:
    resolved_home = (home_dir or Path.home()).expanduser().resolve()
    resolved_logs = log_dir.expanduser().resolve()
    default_path = ":".join(
        [
            str(resolved_home / ".local/bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    return runtime.render_plist_xml(
        {
            "Label": label,
            "EnvironmentVariables": {
                "HOME": str(resolved_home),
                "PATH": path_env or default_path,
            },
            "ProgramArguments": list(argv),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "StandardOutPath": str(resolved_logs / "router.stdout.log"),
            "StandardErrorPath": str(resolved_logs / "router.stderr.log"),
        }
    )


def render_systemd_unit(
    label: str,
    argv: list[str],
    *,
    log_dir: Path,
    instance_root: Path,
) -> str:
    resolved_logs = log_dir.expanduser().resolve()
    exec_start = " ".join(shlex.quote(arg) for arg in argv)
    return (
        "[Unit]\n"
        f"Description=OPL Flow Event Router ({instance_root.name})\n"
        "After=default.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={instance_root.expanduser().resolve()}\n"
        f"ExecStart={exec_start}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        f"StandardOutput=append:{resolved_logs / 'router.stdout.log'}\n"
        f"StandardError=append:{resolved_logs / 'router.stderr.log'}\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _macos_plist_path(label: str, launch_agents_dir: Path | None) -> Path:
    base = launch_agents_dir or (Path.home() / "Library/LaunchAgents")
    return base.expanduser().resolve() / f"{label}.plist"


def _systemd_unit_path(label: str, systemd_dir: Path | None) -> Path:
    base = systemd_dir or (Path.home() / ".config/systemd/user")
    return base.expanduser().resolve() / f"{label}.service"


def install_macos_service(
    instance_root: Path,
    argv: list[str],
    *,
    log_dir: Path | None = None,
    launch_agents_dir: Path | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    label = service_label(instance_root)
    logs = (log_dir or default_service_log_dir(instance_root)).expanduser().resolve()
    plist_path = _macos_plist_path(label, launch_agents_dir)
    content = render_macos_plist(label, argv, log_dir=logs)
    if dry_run:
        return {
            "schema": "opl_router_service_install.v1",
            "platform": "Darwin",
            "dry_run": True,
            "installed": False,
            "running": False,
            "label": label,
            "service_path": str(plist_path),
            "log_dir": str(logs),
            "program_arguments": argv,
            "definition": content,
        }
    logs.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(plist_path, content, mode=0o600)
    exec_fn = runner or _default_run
    domain = f"gui/{os.getuid() if uid is None else uid}"
    exec_fn(["launchctl", "bootout", domain, str(plist_path)], check=False)
    exec_fn(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
    return {
        "schema": "opl_router_service_install.v1",
        "platform": "Darwin",
        "dry_run": False,
        "installed": True,
        "running": True,
        "label": label,
        "service_path": str(plist_path),
        "log_dir": str(logs),
        "program_arguments": argv,
    }


def uninstall_macos_service(
    instance_root: Path,
    *,
    launch_agents_dir: Path | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    label = service_label(instance_root)
    plist_path = _macos_plist_path(label, launch_agents_dir)
    existed = plist_path.exists()
    if dry_run:
        return {
            "schema": "opl_router_service_uninstall.v1",
            "platform": "Darwin",
            "dry_run": True,
            "removed": existed,
            "label": label,
            "service_path": str(plist_path),
        }
    exec_fn = runner or _default_run
    domain = f"gui/{os.getuid() if uid is None else uid}"
    exec_fn(["launchctl", "bootout", domain, str(plist_path)], check=False)
    plist_path.unlink(missing_ok=True)
    return {
        "schema": "opl_router_service_uninstall.v1",
        "platform": "Darwin",
        "dry_run": False,
        "removed": existed,
        "label": label,
        "service_path": str(plist_path),
    }


def install_linux_service(
    instance_root: Path,
    argv: list[str],
    *,
    log_dir: Path | None = None,
    systemd_dir: Path | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    label = service_label(instance_root)
    logs = (log_dir or default_service_log_dir(instance_root)).expanduser().resolve()
    unit_path = _systemd_unit_path(label, systemd_dir)
    content = render_systemd_unit(label, argv, log_dir=logs, instance_root=instance_root)
    if dry_run:
        return {
            "schema": "opl_router_service_install.v1",
            "platform": "Linux",
            "dry_run": True,
            "installed": False,
            "running": False,
            "label": label,
            "service_path": str(unit_path),
            "log_dir": str(logs),
            "program_arguments": argv,
            "definition": content,
        }
    logs.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(unit_path, content, mode=0o644)
    exec_fn = runner or _default_run
    exec_fn(["systemctl", "--user", "daemon-reload"], check=True)
    exec_fn(["systemctl", "--user", "enable", "--now", unit_path.name], check=True)
    return {
        "schema": "opl_router_service_install.v1",
        "platform": "Linux",
        "dry_run": False,
        "installed": True,
        "running": True,
        "label": label,
        "service_path": str(unit_path),
        "log_dir": str(logs),
        "program_arguments": argv,
    }


def uninstall_linux_service(
    instance_root: Path,
    *,
    systemd_dir: Path | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    label = service_label(instance_root)
    unit_path = _systemd_unit_path(label, systemd_dir)
    existed = unit_path.exists()
    if dry_run:
        return {
            "schema": "opl_router_service_uninstall.v1",
            "platform": "Linux",
            "dry_run": True,
            "removed": existed,
            "label": label,
            "service_path": str(unit_path),
        }
    exec_fn = runner or _default_run
    exec_fn(["systemctl", "--user", "disable", "--now", unit_path.name], check=False)
    unit_path.unlink(missing_ok=True)
    exec_fn(["systemctl", "--user", "daemon-reload"], check=False)
    return {
        "schema": "opl_router_service_uninstall.v1",
        "platform": "Linux",
        "dry_run": False,
        "removed": existed,
        "label": label,
        "service_path": str(unit_path),
    }


def install_router_service(
    instance_root: Path,
    *,
    flow_root: Path,
    interval_seconds: float = 15.0,
    use_codex_bridge: bool = True,
    bridge: str | None = None,
    codex_bin: str | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    control_hook_argv: list[str] | None = None,
    event_state_dir: Path | None = None,
    cursor_file: Path | None = None,
    log_dir: Path | None = None,
    launch_agents_dir: Path | None = None,
    systemd_dir: Path | None = None,
    platform_name: str | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    resolved_bridge = _resolve_bridge(
        bridge=bridge,
        use_codex_bridge=use_codex_bridge,
        control_hook_argv=control_hook_argv,
    )
    argv = default_router_argv(
        instance_root,
        flow_root=flow_root,
        interval_seconds=interval_seconds,
        use_codex_bridge=use_codex_bridge,
        bridge=bridge,
        codex_bin=codex_bin,
        agy_bin=agy_bin,
        model=model,
        effort=effort,
        control_hook_argv=control_hook_argv,
        event_state_dir=event_state_dir,
        cursor_file=cursor_file,
    )
    target_platform = platform_name or platform.system()
    if target_platform == "Darwin":
        receipt = install_macos_service(
            instance_root,
            argv,
            log_dir=log_dir,
            launch_agents_dir=launch_agents_dir,
            dry_run=dry_run,
            runner=runner,
            uid=uid,
        )
        return {**receipt, "bridge": resolved_bridge}
    if target_platform == "Linux":
        receipt = install_linux_service(
            instance_root,
            argv,
            log_dir=log_dir,
            systemd_dir=systemd_dir,
            dry_run=dry_run,
            runner=runner,
        )
        return {**receipt, "bridge": resolved_bridge}
    raise ServiceError(f"unsupported platform for router background service: {target_platform}")


def uninstall_router_service(
    instance_root: Path,
    *,
    launch_agents_dir: Path | None = None,
    systemd_dir: Path | None = None,
    platform_name: str | None = None,
    dry_run: bool = False,
    runner: Runner | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    target_platform = platform_name or platform.system()
    if target_platform == "Darwin":
        return uninstall_macos_service(
            instance_root,
            launch_agents_dir=launch_agents_dir,
            dry_run=dry_run,
            runner=runner,
            uid=uid,
        )
    if target_platform == "Linux":
        return uninstall_linux_service(
            instance_root,
            systemd_dir=systemd_dir,
            dry_run=dry_run,
            runner=runner,
        )
    raise ServiceError(f"unsupported platform for router background service: {target_platform}")


def router_service_status(
    instance_root: Path,
    *,
    log_dir: Path | None = None,
    launch_agents_dir: Path | None = None,
    systemd_dir: Path | None = None,
    platform_name: str | None = None,
    runner: Runner | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    target_platform = platform_name or platform.system()
    label = service_label(instance_root)
    logs = (log_dir or default_service_log_dir(instance_root)).expanduser().resolve()
    exec_fn = runner or _default_run

    if target_platform == "Darwin":
        service_path = _macos_plist_path(label, launch_agents_dir)
        installed = service_path.is_file()
        running = False
        if installed:
            domain = f"gui/{os.getuid() if uid is None else uid}"
            try:
                proc = exec_fn(["launchctl", "print", f"{domain}/{label}"], check=False)
                running = proc.returncode == 0
            except (OSError, ServiceError):
                running = False
    elif target_platform == "Linux":
        service_path = _systemd_unit_path(label, systemd_dir)
        installed = service_path.is_file()
        running = False
        if installed:
            try:
                proc = exec_fn(["systemctl", "--user", "is-active", service_path.name], check=False)
                running = proc.returncode == 0 and proc.stdout.strip() == "active"
            except (OSError, ServiceError):
                running = False
    else:
        service_path = Path()
        installed = False
        running = False

    bridge = _detect_service_bridge(service_path, target_platform) if installed else None
    return {
        "schema": "opl_router_service_status.v1",
        "platform": target_platform,
        "label": label,
        "installed": installed,
        "running": running,
        "bridge": bridge,
        "service_path": str(service_path) if service_path != Path() else None,
        "log_dir": str(logs),
    }


def install_cli_wrapper(
    *,
    flow_root: Path,
    bin_dir: Path | None = None,
    name: str = "opl-flow",
    python_bin: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not WRAPPER_NAME_RE.fullmatch(name):
        raise ServiceError(f"invalid wrapper binary name: {name!r}")
    resolved_flow = flow_root.expanduser().resolve()
    target_dir = (bin_dir or (Path.home() / ".local/bin")).expanduser().resolve()
    wrapper_path = target_dir / name
    py = python_bin or sys.executable
    script_body = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'exec {shlex.quote(py)} {shlex.quote(str(resolved_flow / "scripts/opl_workflow.py"))} "$@"\n'
    )
    if dry_run:
        return {
            "schema": "opl_cli_wrapper.v1",
            "dry_run": True,
            "installed": False,
            "path": str(wrapper_path),
            "content": script_body,
        }
    _atomic_write_text(wrapper_path, script_body, mode=0o755)
    return {
        "schema": "opl_cli_wrapper.v1",
        "dry_run": False,
        "installed": True,
        "path": str(wrapper_path),
    }
