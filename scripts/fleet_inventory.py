#!/usr/bin/env python3
"""Collect and validate a sanitized Codex fleet node inventory."""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


INVENTORY_REQUIRED_FIELDS = {
    "schema",
    "node_id",
    "observed_at",
    "host",
    "execution",
    "hardware",
    "storage",
    "baseline",
    "software",
    "specialized_software",
}
INVENTORY_OPTIONAL_FIELDS = {"capabilities", "scheduling"}
NODE_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
SENSITIVE_TEXT = (
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE),
)
VERSION_COMMANDS = {
    "git": ["git", "--version"],
    "gh": ["gh", "--version"],
    "python": ["python3", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "pnpm": ["pnpm", "--version"],
    "uv": ["uv", "--version"],
    "docker": ["docker", "--version"],
    "codegraph": ["codegraph", "--version"],
    "rtk": ["rtk", "--version"],
    "opl": ["opl", "--version"],
}


class InventoryError(RuntimeError):
    pass


def run(
    command: list[str],
    *,
    timeout_seconds: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def command_succeeds(command: list[str], *, timeout_seconds: float) -> bool:
    try:
        return run(command, timeout_seconds=timeout_seconds).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def clean_text(value: Any, limit: int = 180) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    for pattern in SENSITIVE_TEXT[:3]:
        text = pattern.sub("$HOME", text)
    return text[:limit]


def first_line(result: subprocess.CompletedProcess[str]) -> str | None:
    if result.returncode:
        return None
    line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "")
    return clean_text(line) or None


def read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def sysctl_value(name: str) -> str | None:
    return first_line(run(["sysctl", "-n", name]))


def memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        value = sysctl_value("hw.memsize")
        return int(value) if value and value.isdigit() else None
    path = Path("/proc/meminfo")
    if path.is_file():
        match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", path.read_text(), re.MULTILINE)
        if match:
            return int(match.group(1)) * 1024
    return None


def linux_cpu_model() -> str | None:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return None
    match = re.search(r"^model name\s*:\s*(.+)$", path.read_text(), re.MULTILINE)
    return clean_text(match.group(1)) if match else None


def mac_hardware() -> tuple[dict[str, Any], dict[str, Any]]:
    result = run(["system_profiler", "SPHardwareDataType", "SPDisplaysDataType", "-json"])
    payload = json.loads(result.stdout) if result.returncode == 0 else {}
    overview = (payload.get("SPHardwareDataType") or [{}])[0]
    displays = payload.get("SPDisplaysDataType") or []
    gpus = []
    for item in displays:
        name = clean_text(item.get("sppci_model") or item.get("_name"))
        if name and name not in {entry["name"] for entry in gpus}:
            gpu: dict[str, Any] = {"name": name}
            vram = clean_text(item.get("spdisplays_vram"))
            if vram:
                gpu["memory"] = vram
            gpus.append(gpu)
    host = {
        "system": "darwin",
        "os_name": "macOS",
        "os_version": first_line(run(["sw_vers", "-productVersion"])),
        "build": first_line(run(["sw_vers", "-buildVersion"])),
        "manufacturer": "Apple",
        "model": clean_text(overview.get("machine_name")) or None,
        "model_identifier": clean_text(overview.get("machine_model")) or None,
    }
    hardware = {
        "cpu_model": clean_text(
            overview.get("chip_type")
            or sysctl_value("machdep.cpu.brand_string")
            or platform.processor()
        ),
        "logical_cores": os.cpu_count(),
        "memory_bytes": memory_bytes(),
        "gpus": gpus,
    }
    return host, hardware


def powershell_json(script: str) -> Any:
    executable = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    if not executable.is_file():
        return None
    prefix = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$ErrorActionPreference='SilentlyContinue';"
    )
    result = run(
        [
            str(executable),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            prefix + script,
        ]
    )
    if result.returncode or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def nvidia_gpus() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    wsl_executable = Path("/usr/lib/wsl/lib/nvidia-smi")
    if not executable and wsl_executable.is_file():
        executable = str(wsl_executable)
    if not executable:
        return []
    result = run(
        [
            executable,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if result.returncode:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        parts = [clean_text(item) for item in line.split(",", 2)]
        if len(parts) != 3:
            continue
        memory_mib = int(parts[1]) if parts[1].isdigit() else None
        gpus.append(
            {
                "name": parts[0],
                "memory_bytes": memory_mib * 1024 * 1024 if memory_mib else None,
                "driver_version": parts[2],
            }
        )
    return gpus


def nvidia_runtime() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    wsl_executable = Path("/usr/lib/wsl/lib/nvidia-smi")
    if not executable and wsl_executable.is_file():
        executable = str(wsl_executable)
    if not executable:
        return {"utilization_percent": None, "temperature_c": None}
    result = run(
        [
            executable,
            "--query-gpu=utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    if result.returncode:
        return {"utilization_percent": None, "temperature_c": None}
    values = []
    for line in result.stdout.splitlines():
        parts = [item.strip() for item in line.split(",", 1)]
        if len(parts) == 2 and all(item.isdigit() for item in parts):
            values.append((int(parts[0]), int(parts[1])))
    return {
        "utilization_percent": max((item[0] for item in values), default=None),
        "temperature_c": max((item[1] for item in values), default=None),
    }


def wsl_hardware() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    windows = powershell_json(
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "$gpu=@(Get-CimInstance Win32_VideoController | ForEach-Object {"
        "[pscustomobject]@{name=$_.Name;driver_version=$_.DriverVersion}});"
        "[pscustomobject]@{manufacturer=$cs.Manufacturer;model=$cs.Model;"
        "memory=[uint64]$cs.TotalPhysicalMemory;os_name=$os.Caption;"
        "os_version=$os.Version;build=$os.BuildNumber;cpu=$cpu.Name;"
        "logical=$cs.NumberOfLogicalProcessors;gpu=$gpu}|"
        "ConvertTo-Json -Compress -Depth 4"
    )
    windows = windows if isinstance(windows, dict) else {}
    fallback_gpus = windows.get("gpu") or []
    if isinstance(fallback_gpus, dict):
        fallback_gpus = [fallback_gpus]
    gpus = nvidia_gpus()
    known = {str(item.get("name", "")).casefold() for item in gpus}
    for item in fallback_gpus:
        name = clean_text(item.get("name"))
        if not name or name.casefold() in known or "virtual display" in name.casefold():
            continue
        gpus.append(
            {
                "name": name,
                "driver_version": clean_text(item.get("driver_version")) or None,
            }
        )
    release = read_os_release()
    host = {
        "system": "windows",
        "os_name": clean_text(windows.get("os_name")) or "Windows",
        "os_version": clean_text(windows.get("os_version")) or None,
        "build": clean_text(windows.get("build")) or None,
        "manufacturer": clean_text(windows.get("manufacturer")) or None,
        "model": clean_text(windows.get("model")) or None,
        "model_identifier": None,
    }
    hardware = {
        "cpu_model": clean_text(windows.get("cpu") or linux_cpu_model()),
        "logical_cores": windows.get("logical") or os.cpu_count(),
        "memory_bytes": windows.get("memory") or memory_bytes(),
        "gpus": gpus,
    }
    execution = {
        "kind": "wsl",
        "os_name": clean_text(release.get("PRETTY_NAME")) or "Linux",
        "os_version": clean_text(release.get("VERSION_ID")) or None,
        "kernel": clean_text(platform.release()),
        "architecture": clean_text(platform.machine()).lower(),
    }
    return host, hardware, execution


def codex_status(is_wsl: bool) -> dict[str, Any]:
    if is_wsl:
        app = powershell_json(
            "$p=Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1;"
            "if($p){[pscustomobject]@{name=$p.Name;version=$p.Version}|"
            "ConvertTo-Json -Compress}"
        )
        return {
            "ready": isinstance(app, dict),
            "kind": "windows_app_wsl",
            "version": clean_text(app.get("version")) if isinstance(app, dict) else None,
        }
    app = Path("/Applications/ChatGPT.app")
    version = None
    if app.is_dir():
        version = first_line(
            run(
                [
                    "defaults",
                    "read",
                    str(app / "Contents/Info.plist"),
                    "CFBundleShortVersionString",
                ]
            )
        )
    cli = first_line(run(["codex", "--version"])) if shutil.which("codex") else None
    return {
        "ready": bool(app.is_dir() or cli),
        "kind": "mac_app" if app.is_dir() else "cli",
        "version": version or cli,
    }


def ssh_status(is_wsl: bool) -> dict[str, Any]:
    installed = bool(shutil.which("sshd") or Path("/usr/sbin/sshd").is_file())
    listening: bool | None = None
    if is_wsl and shutil.which("ss"):
        result = run(["ss", "-ltn"])
        listening = result.returncode == 0 and bool(
            re.search(r"(?:^|\s)(?:\[::\]|0\.0\.0\.0|\*):22(?:\s|$)", result.stdout)
        )
    return {"installed": installed, "listening": listening}


def tailscale_status(is_wsl: bool) -> dict[str, Any]:
    candidates: list[list[str]] = []
    if shutil.which("tailscale"):
        candidates.append(["tailscale"])
    windows = Path("/mnt/c/Program Files/Tailscale/tailscale.exe")
    if is_wsl and windows.is_file():
        candidates.append([str(windows)])
    for command in candidates:
        status = run([*command, "status", "--json"])
        if status.returncode:
            continue
        try:
            payload = json.loads(status.stdout)
        except json.JSONDecodeError:
            continue
        version = first_line(run([*command, "version"]))
        self_state = payload.get("Self") if isinstance(payload, dict) else {}
        return {
            "installed": True,
            "online": bool(
                isinstance(self_state, dict)
                and self_state.get("Online")
                and payload.get("BackendState") == "Running"
            ),
            "version": version,
            "owner": "windows" if command[0].endswith(".exe") else "native",
        }
    return {"installed": False, "online": False, "version": None, "owner": None}


def software_versions(allowlist: list[str]) -> dict[str, dict[str, Any]]:
    software: dict[str, dict[str, Any]] = {}
    for software_id in allowlist:
        command = VERSION_COMMANDS.get(software_id)
        if not command:
            raise InventoryError(f"unsupported software inventory id: {software_id}")
        executable = shutil.which(command[0])
        if not executable:
            for directory in (
                Path.home() / ".local/bin",
                Path.home() / ".local/share/pnpm",
            ):
                candidate = directory / command[0]
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    executable = str(candidate)
                    break
        version = first_line(run([executable, *command[1:]])) if executable else None
        software[software_id] = {"present": bool(executable), "version": version}
    return software


def specialized_software(definitions: list[dict[str, Any]], is_wsl: bool) -> list[dict[str, Any]]:
    if not is_wsl or not definitions:
        return []
    installed = powershell_json(
        "$paths=@('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
        "@(Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
        "Where-Object {$_.DisplayName} | ForEach-Object {"
        "[pscustomobject]@{name=$_.DisplayName;version=$_.DisplayVersion}})|"
        "ConvertTo-Json -Compress"
    )
    if isinstance(installed, dict):
        installed = [installed]
    installed = installed if isinstance(installed, list) else []
    found: list[dict[str, Any]] = []
    for definition in definitions:
        patterns = [
            str(item).casefold()
            for item in definition.get("windows_display_name_patterns", [])
        ]
        for app in installed:
            name = clean_text(app.get("name"))
            if name and any(pattern in name.casefold() for pattern in patterns):
                found.append(
                    {
                        "id": clean_text(definition.get("id"), 80),
                        "purpose": clean_text(definition.get("purpose")),
                        "name": name,
                        "version": clean_text(app.get("version")) or None,
                    }
                )
    return found


def mac_power() -> dict[str, Any]:
    result = run(["pmset", "-g", "batt"])
    output = result.stdout if result.returncode == 0 else ""
    battery_present = "InternalBattery" in output
    percent_match = re.search(r"(\d+)%", output)
    source = (
        "ac"
        if "AC Power" in output
        else "battery"
        if "Battery Power" in output
        else "unknown"
    )
    charging = None
    if battery_present:
        charging = "charging" in output.lower() and "not charging" not in output.lower()
    return {
        "source": source,
        "battery_present": battery_present,
        "charging": charging,
        "percent": int(percent_match.group(1)) if percent_match else None,
    }


def mac_hid_idle_seconds() -> int | None:
    result = run(["pmset", "-g", "assertions"])
    if result.returncode:
        return None
    match = re.search(
        r"(\d+):(\d+):(\d+)\s+UserIsActive\s+named:",
        result.stdout,
    )
    if match:
        hours, minutes, seconds = (int(value) for value in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    status = re.search(r"^\s*UserIsActive\s+([01])\s*$", result.stdout, re.MULTILINE)
    return 1800 if status and status.group(1) == "0" else None


def mac_capabilities() -> dict[str, Any]:
    tart = shutil.which("tart")
    tart_version = first_line(run([tart, "--version"])) if tart else None
    vmware = Path("/Applications/VMware Fusion.app").is_dir() or bool(
        shutil.which("vmrun")
    )
    hypervisor = sysctl_value("kern.hv_support") == "1"
    console_user = first_line(run(["stat", "-f", "%Su", "/dev/console"]))
    interactive = bool(console_user and console_user not in {"root", "loginwindow"})
    idle_seconds = mac_hid_idle_seconds() if interactive else None
    identities = run(["security", "find-identity", "-v", "-p", "codesigning"])
    identity_match = re.search(r"(\d+) valid identities found", identities.stdout)
    thermal = run(["pmset", "-g", "therm"])
    thermal_text = f"{thermal.stdout}\n{thermal.stderr}"
    limited = any(
        int(value) < 100
        for value in re.findall(
            r"(?:CPU_Scheduler_Limit|CPU_Speed_Limit)\s*=\s*(\d+)",
            thermal_text,
        )
    )
    load_per_core = round(os.getloadavg()[0] / max(os.cpu_count() or 1, 1), 3)
    return {
        "power": mac_power(),
        "virtualization": {
            "hypervisor_ready": hypervisor,
            "tart": {"present": bool(tart), "version": tart_version},
            "vmware": {"present": vmware},
            "wsl": {"present": False},
        },
        "gui": {
            "available": interactive,
            "interactive_session": interactive,
            "idle_seconds": idle_seconds,
            "code_signing_identities": (
                int(identity_match.group(1)) if identity_match else 0
            ),
        },
        "workload": {
            "load_1_per_core": load_per_core,
            "busy": load_per_core >= 0.75,
            "gpu_utilization_percent": None,
            "gpu_temperature_c": None,
            "thermal_state": "warning" if limited else "nominal",
        },
        "rollback": {
            "kind": "time-machine",
            "available": command_succeeds(
                ["tmutil", "latestbackup"],
                timeout_seconds=5,
            ),
        },
    }


def wsl_capabilities() -> dict[str, Any]:
    windows = powershell_json(
        "$idleType='using System;using System.Runtime.InteropServices;"
        "public static class FleetIdle{[StructLayout(LayoutKind.Sequential)]"
        "public struct LASTINPUTINFO{public uint cbSize;public uint dwTime;}"
        "[DllImport(\"user32.dll\")]public static extern bool "
        "GetLastInputInfo(ref LASTINPUTINFO value);}';"
        "Add-Type -TypeDefinition $idleType;"
        "$last=New-Object FleetIdle+LASTINPUTINFO;"
        "$last.cbSize=[Runtime.InteropServices.Marshal]::SizeOf($last);"
        "$idleSeconds=if([FleetIdle]::GetLastInputInfo([ref]$last)){"
        "[math]::Max(0,[math]::Floor(([Environment]::TickCount-$last.dwTime)/1000))"
        "}else{$null};"
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "$battery=@(Get-CimInstance Win32_Battery);"
        "$paths=@('HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
        "$vmware=@(Get-ItemProperty $paths -ErrorAction SilentlyContinue | "
        "Where-Object {$_.DisplayName -match '^VMware'});"
        "$brokerName=[Environment]::GetEnvironmentVariable("
        "'OPL_HYPERV_BROKER_TASK','Machine');"
        "$brokerTasks=if($brokerName){"
        "@(Get-ScheduledTask -TaskName $brokerName -ErrorAction SilentlyContinue)"
        "}else{@()};"
        "$broker=if($brokerTasks.Count -eq 1){$brokerTasks[0]}else{$null};"
        "[pscustomobject]@{hypervisor=[bool]$cs.HypervisorPresent;"
        "interactive=[bool]$cs.UserName;battery_present=($battery.Count -gt 0);"
        "idle_seconds=$idleSeconds;"
        "battery_percent=if($battery.Count){$battery[0].EstimatedChargeRemaining}else{$null};"
        "battery_status=if($battery.Count){$battery[0].BatteryStatus}else{$null};"
        "vmware_present=($vmware.Count -gt 0);"
        "broker_available=[bool]($broker -and "
        "$broker.State -in @('Ready','Running'));"
        "broker_system=[bool]($broker -and "
        "$broker.Principal.UserId -eq 'SYSTEM')}|ConvertTo-Json -Compress"
    )
    windows = windows if isinstance(windows, dict) else {}
    battery_present = bool(windows.get("battery_present"))
    battery_status = windows.get("battery_status")
    source = "ac" if not battery_present or battery_status in {2, 3, 6, 7, 8, 9, 11} else "battery"
    gpu = nvidia_runtime()
    load_per_core = round(os.getloadavg()[0] / max(os.cpu_count() or 1, 1), 3)
    gpu_busy = int(gpu.get("utilization_percent") or 0) >= 80
    gpu_hot = int(gpu.get("temperature_c") or 0) >= 85
    return {
        "power": {
            "source": source if windows else "unknown",
            "battery_present": battery_present,
            "charging": battery_status in {6, 7, 8, 9, 11} if battery_present else None,
            "percent": windows.get("battery_percent"),
        },
        "virtualization": {
            "hypervisor_ready": bool(windows.get("hypervisor")),
            "hyper_v": {"present": bool(windows.get("hypervisor"))},
            "hyper_v_broker": {
                "available": bool(windows.get("broker_available")),
                "system_owned": bool(windows.get("broker_system")),
            },
            "tart": {"present": False, "version": None},
            "vmware": {"present": bool(windows.get("vmware_present"))},
            "wsl": {"present": True},
        },
        "gui": {
            "available": bool(windows.get("interactive")),
            "interactive_session": bool(windows.get("interactive")),
            "idle_seconds": windows.get("idle_seconds"),
            "code_signing_identities": None,
        },
        "workload": {
            "load_1_per_core": load_per_core,
            "busy": load_per_core >= 0.75 or gpu_busy,
            "gpu_utilization_percent": gpu.get("utilization_percent"),
            "gpu_temperature_c": gpu.get("temperature_c"),
            "thermal_state": "warning" if gpu_hot else "nominal",
        },
        "rollback": {
            "kind": "wsl-export",
            "available": None,
        },
    }


def scheduling_status(
    node_id: str,
    registry: dict[str, Any],
    capabilities: dict[str, Any],
    free_bytes: int,
) -> dict[str, Any]:
    policy = (registry.get("nodes", {}).get(node_id) or {}).get("scheduling") or {}
    requires_ac = bool(policy.get("requires_ac"))
    power_ok = not requires_ac or capabilities["power"].get("source") == "ac"
    minimum = int(policy.get("min_free_gb") or 0) * 1024**3
    storage_ok = free_bytes >= minimum
    busy = bool(capabilities["workload"].get("busy"))
    gui = capabilities["gui"]
    interactive_session = bool(gui.get("interactive_session"))
    idle_seconds = gui.get("idle_seconds")
    occupancy_required = policy.get("occupancy_required") is True
    idle_threshold = int(policy.get("idle_threshold_seconds") or 900)
    if not interactive_session:
        interactive_busy: bool | None = False
    elif isinstance(idle_seconds, int) and idle_seconds >= 0:
        interactive_busy = idle_seconds < idle_threshold
    else:
        interactive_busy = None
    occupancy_ok = (
        interactive_busy is False
        if occupancy_required
        else interactive_busy is not True
    )
    thermal_ok = capabilities["workload"].get("thermal_state") == "nominal"
    return {
        "requires_ac": requires_ac,
        "power_ok": power_ok,
        "preferred_for": list(policy.get("preferred_for") or []),
        "occupancy_required": occupancy_required,
        "idle_threshold_seconds": idle_threshold,
        "interactive_session": interactive_session,
        "interactive_busy": interactive_busy,
        "idle_seconds": idle_seconds if isinstance(idle_seconds, int) else None,
        "busy": busy,
        "storage_ok": storage_ok,
        "thermal_ok": thermal_ok,
        "eligible": (
            power_ok
            and storage_ok
            and thermal_ok
            and occupancy_ok
            and not busy
        ),
    }


def collect_inventory(
    node_id: str,
    control: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not NODE_ID_PATTERN.fullmatch(node_id):
        raise InventoryError("invalid node id")
    is_wsl = "microsoft" in platform.release().lower()
    if is_wsl:
        host, hardware, execution = wsl_hardware()
    else:
        host, hardware = mac_hardware() if platform.system() == "Darwin" else (
            {
                "system": platform.system().lower(),
                "os_name": platform.system(),
                "os_version": clean_text(platform.version()),
                "build": None,
                "manufacturer": None,
                "model": None,
                "model_identifier": None,
            },
            {
                "cpu_model": linux_cpu_model() or clean_text(platform.processor()),
                "logical_cores": os.cpu_count(),
                "memory_bytes": memory_bytes(),
                "gpus": nvidia_gpus(),
            },
        )
        release = read_os_release()
        execution = {
            "kind": "native",
            "os_name": host["os_name"] if platform.system() == "Darwin" else clean_text(
                release.get("PRETTY_NAME") or platform.system()
            ),
            "os_version": host["os_version"] if platform.system() == "Darwin" else clean_text(
                release.get("VERSION_ID")
            ) or None,
            "kernel": clean_text(platform.release()),
            "architecture": clean_text(platform.machine()).lower(),
        }
    disk = shutil.disk_usage(Path.home())
    inventory_spec = control.get("inventory") or {}
    allowlist = [str(item) for item in inventory_spec.get("software_allowlist", [])]
    capabilities = wsl_capabilities() if is_wsl else mac_capabilities()
    payload = {
        "schema": "codex_fleet_inventory.v1",
        "node_id": node_id,
        "observed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "host": host,
        "execution": execution,
        "hardware": hardware,
        "storage": {
            "scope": "execution-home",
            "total_bytes": disk.total,
            "free_bytes": disk.free,
        },
        "baseline": {
            "codex": codex_status(is_wsl),
            "ssh": ssh_status(is_wsl),
            "tailscale": tailscale_status(is_wsl),
        },
        "software": software_versions(allowlist),
        "specialized_software": specialized_software(
            registry.get("specialized_software", []),
            is_wsl,
        ),
        "capabilities": capabilities,
        "scheduling": scheduling_status(node_id, registry, capabilities, disk.free),
    }
    return validate_inventory(payload)


def validate_inventory(payload: dict[str, Any]) -> dict[str, Any]:
    fields = set(payload)
    if (
        not INVENTORY_REQUIRED_FIELDS.issubset(fields)
        or fields - INVENTORY_REQUIRED_FIELDS - INVENTORY_OPTIONAL_FIELDS
    ):
        raise InventoryError("inventory fields are not allowed")
    if payload.get("schema") != "codex_fleet_inventory.v1":
        raise InventoryError("unsupported inventory")
    node_id = str(payload.get("node_id", ""))
    if not NODE_ID_PATTERN.fullmatch(node_id):
        raise InventoryError("invalid inventory node id")
    dt.datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > 48_000:
        raise InventoryError("inventory exceeds size limit")
    if any(pattern.search(encoded) for pattern in SENSITIVE_TEXT):
        raise InventoryError("inventory contains a sensitive path or address")
    forbidden_keys = {"serial", "serial_number", "ip", "ip_address", "mac_address"}

    def inspect(value: Any, depth: int = 0) -> None:
        if depth > 8:
            raise InventoryError("inventory nesting is too deep")
        if isinstance(value, dict):
            if any(str(key).lower() in forbidden_keys for key in value):
                raise InventoryError("inventory contains a forbidden identity field")
            for key, item in value.items():
                if not isinstance(key, str) or len(key) > 80:
                    raise InventoryError("inventory key is invalid")
                inspect(item, depth + 1)
        elif isinstance(value, list):
            if len(value) > 64:
                raise InventoryError("inventory list is too large")
            for item in value:
                inspect(item, depth + 1)
        elif isinstance(value, str) and len(value) > 240:
            raise InventoryError("inventory string is too long")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise InventoryError("inventory value type is invalid")

    inspect(payload)
    return payload
