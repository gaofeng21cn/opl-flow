"""Common configuration, I/O helpers, time parsing, identity, and requirement parsing shared by OPL Fleet modules."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import tempfile

# Layout: scripts/opl_fleet_parts/fleet_common.py -> scripts/ -> repo root.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FLOW_ROOT = SCRIPTS_DIR.parent
FLEET_ENTRY_SCRIPT = SCRIPTS_DIR / "opl_fleet.py"

CONTROL_ROOT = FLOW_ROOT

CONFIG_PATH = Path.home() / ".config/codex-fleet/node.json"

ROUTES_PATH = Path.home() / ".config/codex-fleet/routes.json"

STATE_ROOT = Path.home() / ".local/state/codex-fleet"

INSTANCE_POINTER_PATH = Path.home() / ".config/opl-flow/instance.json"

RUNNER_PATH = Path.home() / ".codex/skills/codex-machine-sync/scripts/codex_machine_sync.py"

NODE_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

OWNER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")

ROLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

LEASE_WORKLOAD_CLASSES = {
    "p0-release",
    "foreground",
    "background",
    "experiment",
    "guest",
    "job",
    "vm",
}

LIVE_ONLY_POLICY_FEATURES = {"hyperv", "windows-clean-guest-reserve"}

PREEMPTIBLE_WORKLOAD_CLASSES = {"background", "experiment"}

PROTECTED_WORKLOAD_CLASSES = {"p0-release", "guest", "job", "vm"}

LEASE_PHASES = {"interruptible", "non-interruptible"}

AVAILABILITY_POLICIES = {"always_on", "on_demand", "maintenance"}

DISPATCH_ADAPTERS = {
    "local-codex": {
        "status": "supported",
        "requires_fleet": False,
        "execution": "current-codex-session",
    },
    "lease-only": {
        "status": "supported",
        "requires_fleet": True,
        "execution": "caller-controlled-after-lease",
    },
    "github-runner": {
        "status": "supported-via-runner-transaction",
        "requires_fleet": True,
        "execution": "existing-runner-transaction",
    },
    "ssh-session": {
        "status": "supported",
        "requires_fleet": True,
        "execution": "controlled-ssh-session",
    },
    "remote-codex": {
        "status": "supported-via-native-codex",
        "requires_fleet": True,
        "execution": "native-codex-thread-after-lease",
    },
}

ADMISSION_FIELDS = {
    "checked_at",
    "inventory_age_seconds",
    "requirements",
    "min_memory_gb",
    "power_ok",
    "storage_ok",
    "thermal_ok",
    "interactive_busy",
    "busy",
    "work_volume_ready",
}

ADMISSION_OPTIONAL_FIELDS = {
    "gpu_api",
    "min_gpu_memory_gb",
    "gpu_model",
}

GPU_APIS = {"any", "cuda", "metal"}

EXECUTION_REQUIREMENTS_SCHEMA = "opl_execution_requirements.v1"

SKILL_REFERENCE_SCHEMA = "codex_skill_reference.v2"

MAX_EXECUTION_REQUIREMENTS_BYTES = 16_384

MAX_EXECUTION_OUTPUT_BYTES = 64 * 1024

REMOTE_EXECUTION_TIMEOUT_SECONDS = 3_600

REMOTE_EXECUTOR = r'''
import datetime, json, subprocess, sys

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def bounded(value, limit):
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
    return text[:limit], len(text) > limit

payload = json.load(sys.stdin)
argv = payload["argv"]
stdin_text = payload.get("stdin_text")
started = now()
timed_out = False
try:
    completed = subprocess.run(
        argv,
        cwd=payload.get("cwd") or None,
        input=stdin_text.encode("utf-8") if isinstance(stdin_text, str) else None,
        capture_output=True,
        timeout=payload["timeout_seconds"],
        check=False,
    )
    exit_code = completed.returncode
    stdout, stdout_truncated = bounded(completed.stdout, payload["output_limit"])
    stderr, stderr_truncated = bounded(completed.stderr, payload["output_limit"])
except subprocess.TimeoutExpired as error:
    timed_out = True
    exit_code = None
    stdout, stdout_truncated = bounded(error.stdout or b"", payload["output_limit"])
    stderr, stderr_truncated = bounded(error.stderr or b"", payload["output_limit"])
except OSError as error:
    exit_code = 127
    stdout, stdout_truncated = "", False
    stderr, stderr_truncated = bounded(str(error), payload["output_limit"])
print(json.dumps({
    "schema": "codex_fleet_ssh_execution_result.v1",
    "started_at": started,
    "finished_at": now(),
    "exit_code": exit_code,
    "timed_out": timed_out,
    "stdout": stdout,
    "stderr": stderr,
    "stdout_truncated": stdout_truncated,
    "stderr_truncated": stderr_truncated,
}, ensure_ascii=False))
'''

LEASE_FIELDS = {
    "lease_id",
    "generation",
    "nonce",
    "node_id",
    "owner_task",
    "owner_thread",
    "owner_run",
    "role",
    "workload_class",
    "priority",
    "preemptible",
    "phase",
    "acquired_at",
    "expires_at",
    "control_commit",
    "admission",
}

LEASE_REQUIRED_FIELDS = LEASE_FIELDS

LEASE_OPTIONAL_FIELDS = {"dispatch_adapter"}

RECEIPT_FIELDS = {
    "schema",
    "node_id",
    "hostname_s",
    "platform",
    "architecture",
    "state",
    "drift",
    "owner_actions",
    "control_commit",
    "runner_commit",
    "updated_at",
}

PET_FILES = {"pet.json", "spritesheet.webp"}

REPORT_FIELDS = {"schema", "receipt", "inventory"}

REPOSITORY_FETCH_TIMEOUT_SECONDS = 30

_INSTANCE_OWNER = object()

class FleetError(RuntimeError):
    pass

def configure_instance(value: str | Path | None) -> Path:
    configured = value or os.environ.get("OPL_INSTANCE")
    if not configured and INSTANCE_POINTER_PATH.is_file():
        if INSTANCE_POINTER_PATH.stat().st_mode & 0o077:
            raise FleetError("OPL Instance pointer must have mode 0600")
        pointer = read_json(INSTANCE_POINTER_PATH)
        if set(pointer) != {"schema", "path"} or pointer.get("schema") != (
            "opl_flow_instance_pointer.v1"
        ):
            raise FleetError("OPL Instance pointer is invalid")
        configured = pointer.get("path")
    if not configured:
        raise FleetError("pass --instance or set OPL_INSTANCE")
    instance = Path(configured).expanduser().resolve()
    fleet_root = instance / "fleet"
    if not (fleet_root / "fleet.json").is_file() or not (
        fleet_root / "nodes.json"
    ).is_file():
        raise FleetError(f"OPL Instance has no Fleet configuration: {instance}")
    global CONTROL_ROOT
    CONTROL_ROOT = fleet_root
    return instance

def install_fleet_command() -> Path:
    source = FLEET_ENTRY_SCRIPT
    destination = Path.home() / ".local/bin/opl-fleet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(f".{destination.name}.stage-{os.getpid()}")
    if staged.exists() or staged.is_symlink():
        staged.unlink()
    staged.symlink_to(source)
    staged.replace(destination)
    return destination

def write_instance_pointer(instance: Path) -> Path:
    atomic_json(
        INSTANCE_POINTER_PATH,
        {"schema": "opl_flow_instance_pointer.v1", "path": str(instance)},
        mode=0o600,
    )
    return INSTANCE_POINTER_PATH

def run(
    command: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise FleetError(f"{shlex.join(command)} failed: {detail}")
    return result

def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FleetError(f"expected JSON object: {path}")
    return payload

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        staged = Path(handle.name)
    os.chmod(staged, mode)
    staged.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)

def effective_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise FleetError("CODEX_HOME must be absolute")
        return path
    if "microsoft" in platform.release().lower():
        cmd = Path("/mnt/c/Windows/System32/cmd.exe")
        if cmd.is_file() and shutil.which("wslpath"):
            profile = run(
                [str(cmd), "/d", "/c", "echo %USERPROFILE%"],
                check=False,
            )
            lines = [line.strip().rstrip("\r") for line in profile.stdout.splitlines()]
            windows_profile = next((line for line in reversed(lines) if line), "")
            if profile.returncode == 0 and windows_profile:
                converted = run(["wslpath", "-u", windows_profile], check=False)
                candidate = converted.stdout.strip()
                if converted.returncode == 0 and candidate:
                    return Path(candidate) / ".codex"
    return Path.home() / ".codex"

def normalize_node_id(value: str) -> str:
    if "/" in value or "\\" in value or ".." in value:
        raise FleetError(f"invalid node id: {value!r}")
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    normalized = normalized[:63].rstrip("-")
    if not NODE_ID_PATTERN.fullmatch(normalized):
        raise FleetError(f"invalid node id: {value!r}")
    return normalized

def node_identity(explicit: str | None = None) -> str:
    if explicit:
        return normalize_node_id(explicit)
    if CONFIG_PATH.is_file():
        configured = str(read_json(CONFIG_PATH).get("node_id", ""))
        if configured:
            return normalize_node_id(configured)
    return normalize_node_id(socket.gethostname().split(".")[0])

def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def parse_utc(value: Any) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FleetError("lease timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)

def dispatch_adapter(adapter: str) -> dict[str, Any]:
    try:
        return DISPATCH_ADAPTERS[adapter]
    except KeyError as exc:
        raise FleetError(f"unknown dispatch adapter: {adapter}") from exc

def parse_requirements(value: str) -> set[str]:
    required = {item.strip() for item in value.split(",") if item.strip()}
    if any(not re.fullmatch(r"[a-z0-9-]{1,40}", item) for item in required):
        raise FleetError("lease requirements are invalid")
    return required
