#!/usr/bin/env python3
"""OPL Fleet engine backed by one private OPL Instance."""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import plistlib
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from fleet_inventory import collect_inventory, validate_inventory


FLOW_ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOT = FLOW_ROOT
CONFIG_PATH = Path.home() / ".config/codex-fleet/node.json"
ROUTES_PATH = Path.home() / ".config/codex-fleet/routes.json"
STATE_ROOT = Path.home() / ".local/state/codex-fleet"
INSTANCE_POINTER_PATH = Path.home() / ".config/opl-flow/instance.json"
RUNNER_PATH = Path.home() / ".agents/skills/codex-machine-sync/scripts/codex_machine_sync.py"
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
        "status": "planned",
        "requires_fleet": True,
        "execution": "remote-codex-adapter-not-implemented",
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
started = now()
timed_out = False
try:
    completed = subprocess.run(
        argv,
        cwd=payload.get("cwd") or None,
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
    source = Path(__file__).resolve()
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


def manifest() -> dict[str, Any]:
    payload = read_json(CONTROL_ROOT / "fleet.json")
    if payload.get("schema") != "codex_fleet_control.v1":
        raise FleetError("unsupported fleet manifest")
    runner = payload.get("runner")
    schedule = payload.get("schedule")
    if not isinstance(runner, dict) or not isinstance(runner.get("install_command"), list):
        raise FleetError("fleet runner definition is incomplete")
    repository_owner = payload.get("repository_owner")
    if not isinstance(repository_owner, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", repository_owner
    ):
        raise FleetError("fleet repository owner is invalid")
    if not isinstance(schedule, dict) or not isinstance(
        schedule.get("service_id"), str
    ):
        raise FleetError("fleet schedule is incomplete")
    return payload


def managed_repository_owner() -> str:
    return str(manifest()["repository_owner"])


def node_registry(*, control_root: Path | None = None) -> dict[str, Any]:
    root = control_root or CONTROL_ROOT
    payload = read_json(root / "nodes.json")
    if set(payload) != {
        "schema",
        "nodes",
        "specialized_software",
        "runner_bindings",
        "runner_roles",
        "runner_role_workloads",
        "desired_unregistered",
    }:
        raise FleetError("node registry fields are not allowed")
    if payload.get("schema") != "codex_fleet_nodes.v1":
        raise FleetError("unsupported node registry")
    nodes = payload.get("nodes")
    definitions = payload.get("specialized_software")
    runner_bindings = payload.get("runner_bindings")
    runner_roles = payload.get("runner_roles")
    runner_role_workloads = payload.get("runner_role_workloads")
    desired_unregistered = payload.get("desired_unregistered")
    if (
        not isinstance(nodes, dict)
        or not isinstance(definitions, list)
        or not isinstance(runner_bindings, dict)
        or not isinstance(runner_roles, dict)
        or not isinstance(runner_role_workloads, dict)
        or not isinstance(desired_unregistered, list)
    ):
        raise FleetError("node registry is incomplete")
    for node_id, policy in nodes.items():
        if normalize_node_id(str(node_id)) != node_id or not isinstance(policy, dict):
            raise FleetError(f"invalid node registry entry: {node_id!r}")
        if set(policy) != {
            "approved",
            "display_name",
            "availability_policy",
            "labels",
            "notes",
            "scheduling",
        }:
            raise FleetError(f"node policy fields are not allowed: {node_id}")
        if not isinstance(policy["approved"], bool):
            raise FleetError(f"node approval is invalid: {node_id}")
        if not isinstance(policy["display_name"], str) or len(policy["display_name"]) > 80:
            raise FleetError(f"node display name is invalid: {node_id}")
        if policy["availability_policy"] not in AVAILABILITY_POLICIES:
            raise FleetError(f"node availability policy is invalid: {node_id}")
        labels = policy["labels"]
        notes = policy["notes"]
        if (
            not isinstance(labels, list)
            or any(not re.fullmatch(r"[a-z0-9-]{1,40}", str(item)) for item in labels)
            or not isinstance(notes, list)
        ):
            raise FleetError(f"node labels or notes are invalid: {node_id}")
        for note in notes:
            if (
                not isinstance(note, dict)
                or set(note) != {"category", "summary"}
                or not re.fullmatch(r"[a-z0-9-]{1,40}", str(note["category"]))
                or not isinstance(note["summary"], str)
                or len(note["summary"]) > 300
            ):
                raise FleetError(f"node note is invalid: {node_id}")
        scheduling = policy["scheduling"]
        if (
            not isinstance(scheduling, dict)
            or set(scheduling)
            != {
                "requires_ac",
                "min_free_gb",
                "occupancy_required",
                "idle_threshold_seconds",
                "preferred_for",
                "work_volume_required",
            }
            or not isinstance(scheduling["requires_ac"], bool)
            or not isinstance(scheduling["min_free_gb"], int)
            or not 0 <= scheduling["min_free_gb"] <= 10_000
            or not isinstance(scheduling["occupancy_required"], bool)
            or not isinstance(scheduling["work_volume_required"], bool)
            or not isinstance(scheduling["idle_threshold_seconds"], int)
            or not 60 <= scheduling["idle_threshold_seconds"] <= 86_400
            or not isinstance(scheduling["preferred_for"], list)
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in scheduling["preferred_for"]
            )
        ):
            raise FleetError(f"node scheduling policy is invalid: {node_id}")
    for definition in definitions:
        if (
            not isinstance(definition, dict)
            or set(definition)
            != {"id", "purpose", "windows_display_name_patterns"}
            or not re.fullmatch(r"[a-z0-9-]{1,60}", str(definition["id"]))
            or not isinstance(definition["purpose"], str)
            or len(definition["purpose"]) > 160
            or not isinstance(definition["windows_display_name_patterns"], list)
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 80
                for item in definition["windows_display_name_patterns"]
            )
        ):
            raise FleetError("specialized software definition is invalid")
    for role, node_ids in runner_roles.items():
        if (
            not ROLE_PATTERN.fullmatch(str(role))
            or not isinstance(node_ids, list)
            or not node_ids
            or node_ids != sorted(set(node_ids))
            or any(node_id not in nodes for node_id in node_ids)
        ):
            raise FleetError(f"runner role is invalid: {role}")
    for role, workload_classes in runner_role_workloads.items():
        if (
            role not in runner_roles
            or not isinstance(workload_classes, list)
            or not workload_classes
            or workload_classes != sorted(set(workload_classes))
            or any(item not in LEASE_WORKLOAD_CLASSES for item in workload_classes)
        ):
            raise FleetError(f"runner role workload policy is invalid: {role}")
    for role, binding in runner_bindings.items():
        if (
            role not in runner_roles
            or not isinstance(binding, dict)
            or set(binding)
            != {
                "launch_mode",
                "min_memory_gb",
                "node_id",
                "repository",
                "required_features",
                "runner_name",
            }
            or binding["launch_mode"] not in {
                "ssh-session",
                "launchagent",
                "windows-session-task",
            }
            or binding["node_id"] not in runner_roles[role]
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
                str(binding["repository"]),
            )
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}",
                str(binding["runner_name"]),
            )
            or not isinstance(binding["required_features"], list)
            or binding["required_features"]
            != sorted(set(binding["required_features"]))
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in binding["required_features"]
            )
            or not isinstance(binding["min_memory_gb"], int)
            or not 0 <= binding["min_memory_gb"] <= 10_000
            or (
                binding["launch_mode"] == "windows-session-task"
                and "windows" not in nodes[binding["node_id"]]["labels"]
            )
        ):
            raise FleetError(f"runner binding is invalid: {role}")
    if (
        desired_unregistered != sorted(set(desired_unregistered))
        or any(node_id not in nodes for node_id in desired_unregistered)
        or set(desired_unregistered).intersection(
            node_id
            for node_ids in runner_roles.values()
            for node_id in node_ids
        )
    ):
        raise FleetError("desired-unregistered nodes are invalid")
    return payload


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


def pet_manifest(
    spec: dict[str, Any],
    *,
    control_root: Path | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    root = (control_root or CONTROL_ROOT).resolve()
    assets = spec.get("user_assets")
    relative = assets.get("pets_manifest") if isinstance(assets, dict) else None
    if not isinstance(relative, str) or not relative:
        return root, []
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FleetError("pet manifest escapes the control checkout") from exc
    payload = read_json(path)
    if payload.get("schema") != "codex_fleet_pet_manifest.v1":
        raise FleetError("unsupported pet manifest")
    pets = payload.get("pets")
    if not isinstance(pets, list):
        raise FleetError("pet manifest entries are invalid")
    seen: set[str] = set()
    for entry in pets:
        if not isinstance(entry, dict):
            raise FleetError("pet manifest entry must be an object")
        pet_id = str(entry.get("id", ""))
        if not NODE_ID_PATTERN.fullmatch(pet_id) or pet_id in seen:
            raise FleetError(f"invalid or duplicate pet id: {pet_id!r}")
        seen.add(pet_id)
        files = entry.get("files")
        if not isinstance(files, dict) or set(files) != PET_FILES:
            raise FleetError(f"pet files are incomplete: {pet_id}")
        for name, digest in files.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                raise FleetError(f"invalid pet digest: {pet_id}/{name}")
        source = path.parent / pet_id
        for name, digest in files.items():
            source_file = source / name
            if not source_file.is_file() or source_file.is_symlink():
                raise FleetError(f"pet source is missing or unsafe: {pet_id}/{name}")
            if sha256_file(source_file) != digest:
                raise FleetError(f"pet source digest changed: {pet_id}/{name}")
        metadata = read_json(source / "pet.json")
        if (
            metadata.get("id") != pet_id
            or metadata.get("spriteVersionNumber") != 2
            or metadata.get("spritesheetPath") != "spritesheet.webp"
        ):
            raise FleetError(f"pet metadata is not Codex v2: {pet_id}")
    return path.parent, pets


def pet_files_match(path: Path, expected: dict[str, str]) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    return all(
        (path / name).is_file()
        and not (path / name).is_symlink()
        and sha256_file(path / name) == digest
        for name, digest in expected.items()
    )


def reconcile_pets(
    spec: dict[str, Any],
    *,
    codex_home: Path | None = None,
    control_root: Path | None = None,
    state_root: Path | None = None,
) -> list[str]:
    source_root, pets = pet_manifest(spec, control_root=control_root)
    if not pets:
        return []
    destination_root = (codex_home or effective_codex_home()) / "pets"
    backup_root = (state_root or STATE_ROOT) / "backups/pets"
    destination_root.mkdir(parents=True, exist_ok=True)
    updated: list[str] = []
    for entry in pets:
        pet_id = str(entry["id"])
        expected = {str(key): str(value) for key, value in entry["files"].items()}
        target = destination_root / pet_id
        if pet_files_match(target, expected):
            continue
        if target.is_symlink():
            raise FleetError(f"refusing to replace symlinked pet: {pet_id}")
        stage = Path(tempfile.mkdtemp(prefix=f".{pet_id}.stage-", dir=destination_root))
        previous = destination_root / f".{pet_id}.previous-{os.getpid()}"
        if previous.exists() or previous.is_symlink():
            shutil.rmtree(stage)
            raise FleetError(f"stale pet transaction path exists: {previous}")
        had_target = target.exists()
        try:
            for name in sorted(PET_FILES):
                shutil.copy2(source_root / pet_id / name, stage / name)
            if not pet_files_match(stage, expected):
                raise FleetError(f"staged pet verification failed: {pet_id}")
            if had_target:
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = backup_root / f"{pet_id}-{stamp}"
                backup.parent.mkdir(parents=True, exist_ok=True)
                if backup.exists():
                    raise FleetError(f"pet backup already exists: {backup}")
                shutil.copytree(target, backup, symlinks=True)
                target.replace(previous)
            stage.replace(target)
            if not pet_files_match(target, expected):
                raise FleetError(f"installed pet verification failed: {pet_id}")
            if previous.exists():
                shutil.rmtree(previous)
            updated.append(pet_id)
        except Exception:
            if previous.exists():
                if target.exists():
                    shutil.rmtree(target)
                previous.replace(target)
            elif not had_target and target.exists():
                shutil.rmtree(target)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return updated


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


def control_commit() -> str:
    return run(["git", "-C", str(CONTROL_ROOT), "rev-parse", "HEAD"]).stdout.strip()


def checkout_commit(root: Path) -> str:
    return run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()


def update_checkout(root: Path, *, label: str) -> str:
    if run(["git", "-C", str(root), "status", "--porcelain"]).stdout.strip():
        raise FleetError(f"{label} checkout is dirty")
    run(["git", "-C", str(root), "fetch", "origin", "main"])
    run(["git", "-C", str(root), "checkout", "main"])
    run(["git", "-C", str(root), "merge", "--ff-only", "origin/main"])
    return checkout_commit(root)


def update_flow() -> str:
    return update_checkout(FLOW_ROOT, label="OPL Flow")


def update_control() -> str:
    return update_checkout(CONTROL_ROOT, label="OPL Instance")


def workspace_root() -> Path:
    configured = os.environ.get("OPL_WORKSPACE")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise FleetError("OPL_WORKSPACE must be absolute")
        return root
    return Path.home() / "workspace"


def github_repository_from_remote(
    remote: str,
    *,
    expected_owner: str | None = None,
) -> str | None:
    match = re.fullmatch(
        r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        remote.strip(),
    )
    if match:
        owner = match.group("owner")
        if expected_owner is not None and owner.casefold() != expected_owner.casefold():
            return None
        return f"{owner}/{match.group('repo')}"
    if expected_owner is None:
        repo = Path(remote.removesuffix("/")).name.removesuffix(".git")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            return repo
    return None


def git_value(
    repository: Path,
    arguments: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return run(
        ["git", "-C", str(repository), *arguments],
        check=check,
        timeout=timeout,
    )


def reconcile_repository(
    repository: Path,
    *,
    fetch: bool,
    apply: bool,
    expected_owner: str | None = None,
) -> dict[str, Any] | None:
    branch_result = git_value(
        repository,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    upstream_result = git_value(
        repository,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else ""
    if "/" in upstream:
        remote_name, upstream_branch = upstream.split("/", 1)
    else:
        main_remote = git_value(
            repository,
            ["config", "--get", "branch.main.remote"],
            check=False,
        ).stdout.strip()
        remote_name, upstream_branch = main_remote or "origin", None
    remote_result = git_value(
        repository,
        ["remote", "get-url", remote_name],
        check=False,
    )
    if remote_result.returncode:
        return None
    slug = github_repository_from_remote(
        remote_result.stdout.strip(),
        expected_owner=expected_owner,
    )
    if slug is None:
        return None

    default_ref_result = git_value(
        repository,
        [
            "symbolic-ref",
            "--quiet",
            "--short",
            f"refs/remotes/{remote_name}/HEAD",
        ],
        check=False,
    )
    default_ref = default_ref_result.stdout.strip()
    default_branch = (
        default_ref.removeprefix(f"{remote_name}/")
        if default_ref.startswith(f"{remote_name}/")
        else ""
    )

    base: dict[str, Any] = {
        "repository": slug,
        "remote": remote_name,
        "branch": branch,
        "default_branch": default_branch or upstream_branch,
        "dirty": None,
        "ahead": None,
        "behind": None,
        "local_commit": None,
        "remote_commit": None,
    }
    if branch is None:
        return {**base, "state": "DETACHED"}
    if not default_branch:
        return {**base, "state": "UPSTREAM_UNKNOWN"}

    if branch != default_branch:
        return {**base, "state": "TASK_BRANCH"}

    if fetch:
        try:
            fetched = git_value(
                repository,
                ["fetch", "--prune", remote_name],
                check=False,
                timeout=REPOSITORY_FETCH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {**base, "state": "FETCH_TIMEOUT"}
        if fetched.returncode:
            return {**base, "state": "FETCH_FAILED"}

    dirty = bool(git_value(repository, ["status", "--porcelain"]).stdout.strip())
    local_commit = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
    remote_ref = f"refs/remotes/{remote_name}/{default_branch}"
    remote_commit = git_value(repository, ["rev-parse", remote_ref]).stdout.strip()
    counts = git_value(
        repository,
        ["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"],
    ).stdout.split()
    if len(counts) != 2 or any(not value.isdigit() for value in counts):
        raise FleetError(f"invalid repository divergence readback: {slug}")
    ahead, behind = (int(value) for value in counts)

    if branch != default_branch:
        state = "TASK_BRANCH"
    elif dirty:
        state = "DIRTY"
    elif ahead and behind:
        state = "DIVERGED"
    elif ahead:
        state = "LOCAL_AHEAD"
    elif behind and apply:
        merged = git_value(repository, ["merge", "--ff-only", remote_ref], check=False)
        if merged.returncode:
            state = "UPDATE_FAILED"
        else:
            state = "UPDATED"
            local_commit = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
            ahead = 0
            behind = 0
    elif behind:
        state = "BEHIND"
    else:
        state = "CURRENT"

    return {
        "repository": slug,
        "remote": remote_name,
        "branch": branch,
        "default_branch": default_branch,
        "state": state,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "local_commit": local_commit,
        "remote_commit": remote_commit,
    }


def reconcile_workspace_repositories(
    *,
    root: Path | None = None,
    fetch: bool,
    apply: bool,
    expected_owner: str | None | object = _INSTANCE_OWNER,
) -> dict[str, Any]:
    if apply and not fetch:
        raise FleetError("repository apply requires a fresh fetch")
    root = root or workspace_root()
    if expected_owner is _INSTANCE_OWNER:
        expected_owner = managed_repository_owner()
    entries: list[dict[str, Any]] = []
    if root.is_dir():
        for candidate in sorted(root.iterdir(), key=lambda path: path.name):
            if (
                candidate.name.startswith(".")
                or candidate.is_symlink()
                or not candidate.is_dir()
                or not (candidate / ".git").exists()
            ):
                continue
            result = reconcile_repository(
                candidate,
                fetch=fetch,
                apply=apply,
                expected_owner=expected_owner,
            )
            if result is not None:
                entries.append(result)
    attention_count = sum(
        entry["state"] not in {"CURRENT", "UPDATED"} for entry in entries
    )
    return {
        "schema": "opl_fleet_repository_readback.v1",
        "observed_at": utc_now().isoformat().replace("+00:00", "Z"),
        "state": "CURRENT" if not attention_count else "ATTENTION",
        "attention_count": attention_count,
        "repositories": entries,
    }


def fleet_repositories(*, sync: bool) -> int:
    report = reconcile_workspace_repositories(fetch=sync, apply=sync)
    atomic_json(STATE_ROOT / "repositories.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["state"] == "CURRENT" else 1


def restart_after_flow_update(previous: str, current: str) -> None:
    if previous == current:
        return
    script = Path(__file__).resolve()
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[1:]])


def github_head(repository: str, branch: str) -> str:
    return run(
        ["gh", "api", f"repos/{repository}/commits/{branch}", "--jq", ".sha"]
    ).stdout.strip()


def install_runner(spec: dict[str, Any]) -> str:
    repository = str(spec["repository"])
    branch = str(spec.get("branch", "main"))
    head = github_head(repository, branch)
    state_path = STATE_ROOT / "runner.json"
    previous = read_json(state_path) if state_path.is_file() else {}
    if not RUNNER_PATH.is_file() or previous.get("commit") != head:
        command = [str(item) for item in spec["install_command"]]
        if command[:3] != ["npx", "skills", "add"]:
            raise FleetError("runner install command is not owner-supported")
        run(command)
        help_text = run([sys.executable, str(RUNNER_PATH), "--help"]).stdout
        if "node-status" not in help_text or "node-sync" not in help_text:
            raise FleetError("installed runner does not expose pull-node commands")
        atomic_json(state_path, {"repository": repository, "commit": head})
    return head


def fetch_skill_reference(spec: dict[str, Any], revision: str) -> dict[str, Any]:
    relative = str(spec["skill_reference"])
    repository = str(spec["repository"])
    result = run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{repository}/contents/{relative}?ref={revision}",
        ]
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or payload.get("schema") != SKILL_REFERENCE_SCHEMA:
        raise FleetError("owner skill reference is invalid")
    return payload


def skill_present(reference: dict[str, Any], skill: str) -> bool:
    return any(
        (Path.home() / str(relative) / skill / "SKILL.md").is_file()
        for relative in reference["discovery_roots"]
    )


def install_missing_owner_skills(
    reference: dict[str, Any],
) -> list[str]:
    owner_actions: list[str] = []
    for package, entry in reference["packages"].items():
        if not entry.get("required"):
            continue
        missing = [name for name in entry["skills"] if not skill_present(reference, name)]
        if not missing:
            continue
        if entry["ownership"] == "codex":
            owner_actions.append(str(package))
            continue
        command = shlex.split(str(entry["install"]["command"]))
        owner_native_opl = command == [
            "opl",
            "packages",
            "install",
            str(package),
            "--json",
        ]
        if command[:3] != ["npx", "skills", "add"] and not owner_native_opl:
            raise FleetError(f"unsafe owner install route: {package}")
        run(command)
        remaining = [name for name in missing if not skill_present(reference, name)]
        if remaining:
            raise FleetError(f"owner install did not provide {package}: {remaining}")
    return sorted(owner_actions)


def runner_call(action: str) -> dict[str, Any]:
    result = run(
        [sys.executable, str(RUNNER_PATH), action, "--json"],
        check=False,
    )
    for line in reversed(result.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise FleetError(f"runner returned no JSON for {action}")


def build_receipt(
    node_id: str,
    node_payload: dict[str, Any],
    *,
    owner_actions: list[str],
    control_revision: str,
    runner_revision: str,
) -> dict[str, Any]:
    result = node_payload.get("result") if node_payload.get("ok") else {}
    result = result if isinstance(result, dict) else {}
    drift = [
        str(item)
        for item in result.get("drift", [])
        if isinstance(item, str) and len(item) <= 120
    ]
    if not node_payload.get("ok"):
        drift.append("node.command-failed")
    ok = bool(node_payload.get("ok") and result.get("ok") and not owner_actions)
    return {
        "schema": "codex_fleet_receipt.v1",
        "node_id": normalize_node_id(node_id),
        "hostname_s": normalize_node_id(socket.gethostname().split(".")[0]),
        "platform": "wsl" if "microsoft" in platform.release().lower() else platform.system().lower(),
        "architecture": platform.machine().lower(),
        "state": "CURRENT" if ok else "UPDATE_REQUIRED",
        "drift": sorted(set(drift)),
        "owner_actions": sorted(set(owner_actions)),
        "control_commit": control_revision,
        "runner_commit": runner_revision,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }


def validate_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != RECEIPT_FIELDS:
        raise FleetError("receipt fields are not allowed")
    if payload.get("schema") != "codex_fleet_receipt.v1":
        raise FleetError("unsupported receipt")
    payload["node_id"] = normalize_node_id(str(payload["node_id"]))
    payload["hostname_s"] = normalize_node_id(str(payload["hostname_s"]))
    if payload.get("state") not in {"CURRENT", "UPDATE_REQUIRED", "EXTERNAL_BLOCKER"}:
        raise FleetError("invalid receipt state")
    for key in ("drift", "owner_actions"):
        values = payload.get(key)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or len(item) > 120 for item in values)
        ):
            raise FleetError(f"invalid receipt {key}")
    for key in ("control_commit", "runner_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get(key, ""))):
            raise FleetError(f"invalid receipt {key}")
    dt.datetime.fromisoformat(str(payload["updated_at"]).replace("Z", "+00:00"))
    return payload


def render_status(state_root: Path) -> str:
    receipts: list[dict[str, Any]] = []
    for path in sorted((state_root / "nodes").glob("*/receipt.json")):
        receipts.append(validate_receipt(read_json(path)))
    lines = [
        "# OPL Fleet Status",
        "",
        "| Node | State | Platform | Last Seen (UTC) | Drift | Control | Runner |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(receipts, key=lambda row: row["node_id"]):
        drift = ",".join([*item["drift"], *item["owner_actions"]]) or "-"
        lines.append(
            f"| {item['node_id']} | {item['state']} | {item['platform']}/{item['architecture']} "
            f"| {item['updated_at']} | {drift} | {item['control_commit'][:12]} "
            f"| {item['runner_commit'][:12]} |"
        )
    if not receipts:
        lines.append("| - | NO_NODES | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def format_bytes(value: Any) -> str:
    if not isinstance(value, int) or value < 0:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024
    return f"{amount:.1f} {unit}"


def markdown_text(value: Any) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")


def build_asset_catalog(
    state_root: Path,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or node_registry()
    registered = registry["nodes"]
    discovered = {
        path.parent.name
        for path in (state_root / "nodes").glob("*/receipt.json")
    } | {
        path.parent.name
        for path in (state_root / "nodes").glob("*/inventory.json")
    }
    node_ids = sorted(set(registered) | discovered)
    entries: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for node_id in node_ids:
        receipt_path = state_root / "nodes" / node_id / "receipt.json"
        inventory_path = state_root / "nodes" / node_id / "inventory.json"
        receipt = validate_receipt(read_json(receipt_path)) if receipt_path.is_file() else None
        inventory = (
            validate_inventory(read_json(inventory_path))
            if inventory_path.is_file()
            else None
        )
        if receipt:
            timestamps.append(str(receipt["updated_at"]))
        if inventory:
            timestamps.append(str(inventory["observed_at"]))
        policy = registered.get(
            node_id,
            {
                "approved": False,
                "display_name": node_id,
                "labels": [],
                "notes": [],
            },
        )
        entries.append(
            {
                "node_id": node_id,
                "policy": policy,
                "receipt": receipt,
                "inventory": inventory,
            }
        )
    return {
        "schema": "codex_fleet_assets.v1",
        "generated_at": max(timestamps) if timestamps else None,
        "nodes": entries,
    }


def render_assets(catalog: dict[str, Any]) -> str:
    receipt_states = {
        "CURRENT": "当前",
        "UPDATE_REQUIRED": "需要更新",
        "NO_RECEIPT": "尚无回报",
    }
    note_categories = {
        "cooling": "散热",
        "codex": "Codex",
        "os-lifecycle": "系统生命周期",
        "ssh": "SSH",
        "storage": "存储",
        "virtualization": "虚拟化",
    }
    lines = [
        "# OPL Fleet 资产清单",
        "",
        f"根据脱敏节点报告生成：`{catalog.get('generated_at') or '尚无报告'}`。",
        "",
        "## 设备总览",
        "",
        "| 节点 | 已批准 | 状态 | 设备 | CPU | 内存 | GPU | 可用磁盘 | Codex | SSH | Tailscale | 资产采集时间 |",
        "| --- | --- | --- | --- | --- | ---: | --- | ---: | --- | --- | --- | --- |",
    ]
    for entry in catalog["nodes"]:
        policy = entry["policy"]
        receipt = entry["receipt"] or {}
        inventory = entry["inventory"] or {}
        host = inventory.get("host") or {}
        hardware = inventory.get("hardware") or {}
        storage = inventory.get("storage") or {}
        baseline = inventory.get("baseline") or {}
        codex = baseline.get("codex") or {}
        ssh = baseline.get("ssh") or {}
        tailscale = baseline.get("tailscale") or {}
        gpu_names = ", ".join(
            str(item.get("name"))
            for item in hardware.get("gpus", [])
            if item.get("name")
        ) or "-"
        ssh_state = "待采集"
        codex_state = "待采集"
        tailscale_state = "待采集"
        if inventory:
            ssh_state = (
                "监听中"
                if ssh.get("listening") is True
                else "已安装"
                if ssh.get("installed")
                else "缺失"
            )
            codex_state = "就绪" if codex.get("ready") else "缺失"
            tailscale_state = "在线" if tailscale.get("online") else "离线或缺失"
        receipt_state = receipt.get("state", "NO_RECEIPT")
        scheduling = inventory.get("scheduling") or {}
        dispatch_state = (
            "可调度"
            if scheduling.get("eligible")
            else "暂不可调度"
            if inventory
            else "待采集"
        )
        lines.append(
            f"| `{entry['node_id']}` | {'是' if policy['approved'] else '否'} "
            f"| {receipt_states.get(receipt_state, receipt_state)} "
            f"| {markdown_text(host.get('model') or host.get('os_name'))} "
            f"| {markdown_text(hardware.get('cpu_model'))} "
            f"| {format_bytes(hardware.get('memory_bytes'))} "
            f"| {markdown_text(gpu_names)} "
            f"| {format_bytes(storage.get('free_bytes'))} "
            f"| {codex_state} "
            f"| {ssh_state} "
            f"| {tailscale_state} "
            f"| {inventory.get('observed_at', '待采集')} |"
        )
    lines.extend(["", "## 节点详情", ""])
    for entry in catalog["nodes"]:
        node_id = entry["node_id"]
        policy = entry["policy"]
        receipt = entry["receipt"] or {}
        inventory = entry["inventory"]
        receipt_state = receipt.get("state", "NO_RECEIPT")
        lines.extend(
            [
                f"### {markdown_text(policy['display_name'])} (`{node_id}`)",
                "",
                f"- 批准状态：`{'已批准' if policy['approved'] else '未批准'}`",
                f"- 标签：{', '.join(f'`{item}`' for item in policy['labels']) or '-'}",
                f"- Fleet 状态：`{receipt_states.get(receipt_state, receipt_state)}`",
                f"- 最近回报：`{receipt.get('updated_at', '-')}`",
                f"- 调度快照：`{dispatch_state}`",
            ]
        )
        if not inventory:
            lines.extend(["- 资产采集：`待处理`", ""])
        else:
            host = inventory["host"]
            execution = inventory["execution"]
            hardware = inventory["hardware"]
            storage = inventory["storage"]
            baseline = inventory["baseline"]
            capabilities = inventory.get("capabilities") or {}
            power = capabilities.get("power") or {}
            virtualization = capabilities.get("virtualization") or {}
            gui = capabilities.get("gui") or {}
            workload = capabilities.get("workload") or {}
            rollback = capabilities.get("rollback") or {}
            scheduling = inventory.get("scheduling") or {}
            ssh_listening = baseline["ssh"].get("listening")
            ssh_listening_text = (
                "是"
                if ssh_listening is True
                else "否"
                if ssh_listening is False
                else "未采集"
            )
            lines.extend(
                [
                    f"- 主机：{markdown_text(host.get('manufacturer'))} "
                    f"{markdown_text(host.get('model'))}；"
                    f"{markdown_text(host.get('os_name'))} "
                    f"{markdown_text(host.get('os_version'))} "
                    f"（构建 {markdown_text(host.get('build'))}）",
                    f"- 执行环境：`{markdown_text(execution.get('kind'))}`；"
                    f"{markdown_text(execution.get('os_name'))} "
                    f"{markdown_text(execution.get('os_version'))}；"
                    f"`{markdown_text(execution.get('architecture'))}`；"
                    f"内核 `{markdown_text(execution.get('kernel'))}`",
                    f"- CPU：{markdown_text(hardware.get('cpu_model'))}；"
                    f"{hardware.get('logical_cores') or '-'} 个逻辑核心",
                    f"- 内存：{format_bytes(hardware.get('memory_bytes'))}",
                    f"- 执行环境存储：可用 {format_bytes(storage.get('free_bytes'))}，"
                    f"总计 {format_bytes(storage.get('total_bytes'))}",
                    f"- Codex：`{markdown_text(baseline['codex'].get('kind'))}` "
                    f"`{markdown_text(baseline['codex'].get('version'))}`；"
                    f"{'就绪' if baseline['codex'].get('ready') else '缺失'}",
                    f"- SSH：{'已安装' if baseline['ssh'].get('installed') else '未安装'}；"
                    f"监听状态：{ssh_listening_text}",
                    f"- Tailscale：{'已安装' if baseline['tailscale'].get('installed') else '未安装'}；"
                    f"{'在线' if baseline['tailscale'].get('online') else '离线'}；"
                    f"版本：{markdown_text(baseline['tailscale'].get('version'))}",
                    f"- 电源：`{markdown_text(power.get('source'))}`；"
                    f"电池：{'有' if power.get('battery_present') else '无'}；"
                    f"电量：{markdown_text(power.get('percent'))}",
                    f"- 虚拟化：Hypervisor {'就绪' if virtualization.get('hypervisor_ready') else '未就绪'}；"
                    f"Tart {'已安装' if (virtualization.get('tart') or {}).get('present') else '未安装'}；"
                    f"VMware {'已安装' if (virtualization.get('vmware') or {}).get('present') else '未安装'}",
                    f"- GUI/签名：GUI {'可用' if gui.get('available') else '不可用'}；"
                    f"交互会话 {'存在' if gui.get('interactive_session') else '无'}；"
                    f"签名身份 {markdown_text(gui.get('code_signing_identities'))}",
                    f"- 当前负载：每核心 `{markdown_text(workload.get('load_1_per_core'))}`；"
                    f"{'繁忙' if workload.get('busy') else '空闲'}；"
                    f"热状态 `{markdown_text(workload.get('thermal_state'))}`",
                    f"- 回滚：`{markdown_text(rollback.get('kind'))}`；"
                    f"{'已验证可用' if rollback.get('available') is True else '未验证' if rollback.get('available') is None else '不可用'}",
                    f"- 调度：AC 门禁 {'启用' if scheduling.get('requires_ac') else '不适用'}；"
                    f"电源 {'通过' if scheduling.get('power_ok') else '不通过'}；"
                    f"磁盘 {'通过' if scheduling.get('storage_ok') else '不通过'}；"
                    f"温度 {'通过' if scheduling.get('thermal_ok') else '不通过'}；"
                    f"交互占用 "
                    f"{'是' if scheduling.get('interactive_busy') is True else '否' if scheduling.get('interactive_busy') is False else '未知'}；"
                    f"{'繁忙' if scheduling.get('busy') else '空闲'}",
                    "- 租约：由主控实时管理，不写入资产快照；"
                    "使用 `opl-fleet lease show` 回读。",
                    f"- 优先角色：{', '.join(f'`{item}`' for item in scheduling.get('preferred_for', [])) or '-'}",
                    f"- 资产采集时间：`{inventory['observed_at']}`",
                    "",
                    "#### GPU",
                    "",
                ]
            )
            if hardware["gpus"]:
                for gpu in hardware["gpus"]:
                    detail = []
                    if gpu.get("memory_bytes"):
                        detail.append(format_bytes(gpu["memory_bytes"]))
                    if gpu.get("memory"):
                        detail.append(str(gpu["memory"]))
                    if gpu.get("driver_version"):
                        detail.append(f"驱动 {gpu['driver_version']}")
                    lines.append(
                        f"- {markdown_text(gpu.get('name'))}"
                        f"{'：' + '，'.join(detail) if detail else ''}"
                    )
            else:
                lines.append("- 未报告")
            lines.extend(["", "#### 开发软件", "", "| 工具 | 已安装 | 版本 |", "| --- | --- | --- |"])
            for tool, detail in sorted(inventory["software"].items()):
                lines.append(
                    f"| `{tool}` | {'是' if detail.get('present') else '否'} "
                    f"| {markdown_text(detail.get('version'))} |"
                )
            lines.extend(["", "#### 专用软件", ""])
            if inventory["specialized_software"]:
                for item in inventory["specialized_software"]:
                    lines.append(
                        f"- **{markdown_text(item.get('name'))}** "
                        f"`{markdown_text(item.get('version'))}`："
                        f"{markdown_text(item.get('purpose'))}"
                    )
            else:
                lines.append("- 经批准的探测未发现专用软件")
            lines.append("")
        lines.extend(["#### 运维注意事项", ""])
        if policy["notes"]:
            for note in policy["notes"]:
                category = note_categories.get(note["category"], note["category"])
                lines.append(
                    f"- **{markdown_text(category)}：**"
                    f"{markdown_text(note['summary'])}"
                )
        else:
            lines.append("- 无")
        lines.append("")
    lines.extend(
        [
            "## 调度边界",
            "",
            "本文档是持久化的脱敏资产清单，不代表节点当前一定可用。"
            "分配任务前必须运行 `opl-fleet doctor <node-id>` 做实时检查。",
            "",
        ]
    )
    return "\n".join(lines)


def write_asset_catalog(
    state_root: Path,
    *,
    registry: dict[str, Any] | None = None,
) -> None:
    catalog = build_asset_catalog(state_root, registry=registry)
    atomic_json(state_root / "ASSETS.json", catalog, mode=0o644)
    (state_root / "ASSETS.md").write_text(render_assets(catalog), encoding="utf-8")


def record_receipt(state_root: Path, encoded: str) -> Path:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:
        raise FleetError("receipt payload is not valid base64 JSON") from exc
    if not isinstance(payload, dict):
        raise FleetError("receipt payload must be an object")
    inventory = None
    if payload.get("schema") == "codex_fleet_report.v1":
        if set(payload) != REPORT_FIELDS:
            raise FleetError("node report fields are not allowed")
        receipt = validate_receipt(payload["receipt"])
        inventory = validate_inventory(payload["inventory"])
        if inventory["node_id"] != receipt["node_id"]:
            raise FleetError("node report identities do not match")
    else:
        receipt = validate_receipt(payload)
    destination = state_root / "nodes" / receipt["node_id"] / "receipt.json"
    atomic_json(destination, receipt, mode=0o644)
    if inventory:
        atomic_json(destination.with_name("inventory.json"), inventory, mode=0o644)
    status_path = state_root / "STATUS.md"
    status_path.write_text(render_status(state_root), encoding="utf-8")
    write_asset_catalog(state_root)
    return destination


def report_receipt(
    repo: str,
    workflow: str,
    receipt: dict[str, Any],
    inventory: dict[str, Any],
) -> None:
    report = {
        "schema": "codex_fleet_report.v1",
        "receipt": receipt,
        "inventory": inventory,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(report, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    run(
        [
            "gh",
            "workflow",
            "run",
            workflow,
            "--repo",
            repo,
            "--ref",
            "main",
            "-f",
            f"payload={encoded}",
        ]
    )


def install_macos_schedule(
    hour: int,
    minute: int,
    service_id: str = "dev.one-person-lab.opl-fleet",
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", service_id):
        raise FleetError("invalid Fleet service id")
    label = service_id
    path = Path.home() / f"Library/LaunchAgents/{label}.plist"
    log_root = STATE_ROOT / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    command = Path.home() / ".local/bin/opl-fleet"
    launchd_path = ":".join(
        [
            str(Path.home() / ".local/bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{label}</string>
<key>EnvironmentVariables</key><dict>
<key>PATH</key><string>{launchd_path}</string>
</dict>
<key>ProgramArguments</key><array>
<string>{command}</string><string>reconcile</string><string>--report</string>
</array>
<key>StartCalendarInterval</key><dict>
<key>Hour</key><integer>{hour}</integer>
<key>Minute</key><integer>{minute}</integer>
</dict>
<key>StandardOutPath</key><string>{log_root / 'stdout.log'}</string>
<key>StandardErrorPath</key><string>{log_root / 'stderr.log'}</string>
</dict></plist>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.stage-{os.getpid()}")
    staged.write_text(content, encoding="utf-8")
    os.chmod(staged, 0o600)
    staged.replace(path)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(path)], check=False)
    run(["launchctl", "bootstrap", domain, str(path)])


def install_wsl_schedule(hour: int, minute: int) -> None:
    distro = os.environ.get("WSL_DISTRO_NAME")
    if not distro:
        raise FleetError("WSL_DISTRO_NAME is missing")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", distro):
        raise FleetError("WSL_DISTRO_NAME is not task-safe")
    scheduler = Path("/mnt/c/Windows/System32/schtasks.exe")
    if not scheduler.is_file():
        raise FleetError("Windows Task Scheduler is unavailable")
    windows_cmd = run(
        ["wslpath", "-w", str(scheduler.with_name("cmd.exe"))]
    ).stdout.strip()
    windows_wsl = run(
        ["wslpath", "-w", str(scheduler.with_name("wsl.exe"))]
    ).stdout.strip()
    if not windows_cmd or not windows_wsl:
        raise FleetError("Windows scheduler launcher paths are unavailable")
    command = (
        f"{windows_cmd} /d /c {windows_wsl} -d {distro} -- "
        f'{Path.home() / ".local/bin/opl-fleet"} '
        "reconcile --report "
        "1>>%TEMP%\\opl-fleet-reconcile.stdout.log "
        "2>>%TEMP%\\opl-fleet-reconcile.stderr.log"
    )
    if len(command) > 261:
        raise FleetError("Windows Task Scheduler command exceeds 261 characters")
    run(
        [
            str(scheduler),
            "/Create",
            "/F",
            "/SC",
            "DAILY",
            "/ST",
            f"{hour:02d}:{minute:02d}",
            "/TN",
            "OPLFleet-Reconcile",
            "/TR",
            command,
        ]
    )


def install_linux_schedule(hour: int, minute: int) -> None:
    unit_root = Path.home() / ".config/systemd/user"
    unit_root.mkdir(parents=True, exist_ok=True)
    command = Path.home() / ".local/bin/opl-fleet"
    (unit_root / "opl-fleet.service").write_text(
        "[Unit]\nDescription=Reconcile OPL Fleet node\n"
        "[Service]\nType=oneshot\n"
        f"ExecStart={command} reconcile --report\n",
        encoding="utf-8",
    )
    (unit_root / "opl-fleet.timer").write_text(
        "[Unit]\nDescription=Daily OPL Fleet reconciliation\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\n"
        "Persistent=true\nRandomizedDelaySec=900\n"
        "[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "--now", "opl-fleet.timer"])


def install_schedule(spec: dict[str, Any]) -> None:
    hour = int(spec["hour"])
    minute = int(spec["minute"])
    service_id = str(spec["service_id"])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise FleetError("invalid fleet schedule")
    if "microsoft" in platform.release().lower():
        install_wsl_schedule(hour, minute)
    elif platform.system() == "Darwin":
        install_macos_schedule(hour, minute, service_id)
    else:
        install_linux_schedule(hour, minute)


def reconcile(*, report: bool, install_required: bool) -> dict[str, Any]:
    run(["gh", "auth", "status"])
    previous_flow_revision = checkout_commit(FLOW_ROOT)
    flow_revision = update_flow()
    restart_after_flow_update(previous_flow_revision, flow_revision)
    control_revision = update_control()
    spec = manifest()
    reconcile_pets(spec)
    runner_revision = install_runner(spec["runner"])
    owner_actions: list[str] = []
    if install_required:
        reference = fetch_skill_reference(spec["runner"], runner_revision)
        owner_actions = install_missing_owner_skills(reference)
    apply = runner_call("node-sync")
    verify = runner_call("node-status")
    payload = verify if verify.get("ok") else apply
    node_id = node_identity()
    receipt = build_receipt(
        node_id,
        payload,
        owner_actions=owner_actions,
        control_revision=control_revision,
        runner_revision=runner_revision,
    )
    repository_report = reconcile_workspace_repositories(fetch=True, apply=True)
    atomic_json(STATE_ROOT / "repositories.json", repository_report)
    if repository_report["state"] != "CURRENT":
        receipt["drift"].append("development-repositories.attention")
        receipt["state"] = "UPDATE_REQUIRED"
    inventory = collect_inventory(node_id, spec, node_registry())
    atomic_json(STATE_ROOT / "receipt.json", receipt)
    atomic_json(STATE_ROOT / "inventory.json", inventory)
    if report:
        report_receipt(
            str(spec["repository"]),
            str(spec["receipt_workflow"]),
            receipt,
            inventory,
        )
    return receipt


def join(args: argparse.Namespace) -> int:
    node_id = node_identity(args.node_id)
    atomic_json(
        CONFIG_PATH,
        {
            "schema": "codex_fleet_node.v1",
            "node_id": node_id,
            "repository": str(manifest()["repository"]),
        },
    )
    if not args.no_schedule:
        install_schedule(manifest()["schedule"])
    receipt = reconcile(report=True, install_required=True)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["state"] == "CURRENT" else 1


def fleet_status() -> int:
    spec = manifest()
    result = run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{spec['repository']}/contents/STATUS.md?ref=state",
        ],
        check=False,
    )
    if result.returncode:
        print("No fleet receipts have been published yet.")
        return 1
    print(result.stdout.rstrip())
    try:
        controller_guard()
    except FleetError:
        return 0
    observed = utc_now()
    with lease_lock(exclusive=False):
        store = read_lease_store()
    print("\n## Controller Lease Authority\n")
    print("| Node | State | Workload | Priority | Owner Task | Expires (UTC) |")
    print("| --- | --- | --- | ---: | --- | --- |")
    for node_id in sorted(store["leases"]):
        lease = public_lease(store["leases"][node_id], now=observed)
        print(
            f"| {node_id} | {lease['state']} | {lease['workload_class']} "
            f"| {lease['priority']} | {lease['owner_task']} | {lease['expires_at']} |"
        )
    if not store["leases"]:
        print("| - | available | - | - | - | - |")
    return 0


def fetch_state_file(relative: str) -> str:
    spec = manifest()
    result = run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{spec['repository']}/contents/{relative}?ref=state",
        ],
        check=False,
    )
    if result.returncode:
        raise FleetError(f"fleet state file is unavailable: {relative}")
    return result.stdout


def remote_asset_catalog() -> dict[str, Any]:
    payload = json.loads(fetch_state_file("ASSETS.json"))
    if not isinstance(payload, dict) or payload.get("schema") != "codex_fleet_assets.v1":
        raise FleetError("fleet asset catalog is invalid")
    if not isinstance(payload.get("nodes"), list):
        raise FleetError("fleet asset nodes are invalid")
    return payload


def fleet_assets() -> int:
    print(fetch_state_file("ASSETS.md").rstrip())
    return 0


def fleet_nodes(*, json_output: bool) -> int:
    catalog = remote_asset_catalog()
    if json_output:
        print(json.dumps(catalog, indent=2, sort_keys=True))
        return 0
    print("NODE\tAPPROVED\tSTATE\tPLATFORM\tINVENTORY")
    for entry in catalog["nodes"]:
        policy = entry.get("policy") or {}
        receipt = entry.get("receipt") or {}
        inventory = entry.get("inventory") or {}
        execution = inventory.get("execution") or {}
        print(
            f"{entry.get('node_id')}\t"
            f"{'yes' if policy.get('approved') else 'no'}\t"
            f"{receipt.get('state', 'NO_RECEIPT')}\t"
            f"{execution.get('kind', '-')}/{execution.get('architecture', '-')}\t"
            f"{inventory.get('observed_at', 'PENDING')}"
        )
    return 0


def inventory_is_fresh(inventory: dict[str, Any], max_age_hours: int) -> bool:
    age = inventory_age_seconds(inventory)
    return 0 <= age <= max_age_hours * 3600


def inventory_age_seconds(
    inventory: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> int:
    observed = parse_utc(inventory["observed_at"])
    age = (now or utc_now()).astimezone(dt.timezone.utc) - observed
    return int(age.total_seconds())


def parse_memory_bytes(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    text = str(value or "").strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb)?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    multiplier = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        None: 1,
    }[match.group(2).lower() if match.group(2) else None]
    return int(amount * multiplier)


def gpu_profiles(entry: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = entry.get("inventory") or {}
    hardware = inventory.get("hardware") or {}
    host = inventory.get("host") or {}
    system = str(host.get("system") or "").lower()
    execution = inventory.get("execution") or {}
    profiles: list[dict[str, Any]] = []
    for raw in hardware.get("gpus") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("model") or "").strip()
        if not name:
            continue
        name_lower = name.casefold()
        apis: set[str] = set()
        if "nvidia" in name_lower or "rtx" in name_lower or "quadro" in name_lower:
            apis.add("cuda")
        if system == "darwin" or str(execution.get("kind")) == "macos":
            apis.add("metal")
        memory = parse_memory_bytes(raw.get("memory_bytes") or raw.get("memory"))
        # Apple reports unified memory at the host level rather than as VRAM.
        if memory is None and "metal" in apis:
            memory = parse_memory_bytes(hardware.get("memory_bytes"))
        profiles.append(
            {
                "name": name,
                "apis": sorted(apis),
                "memory_bytes": memory,
                "driver_version": raw.get("driver_version"),
            }
        )
    return profiles


def matching_gpus(
    entry: dict[str, Any],
    *,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
) -> list[dict[str, Any]]:
    if gpu_api not in GPU_APIS:
        raise FleetError("GPU API must be any, cuda, or metal")
    if min_gpu_memory_gb < 0:
        raise FleetError("minimum GPU memory must not be negative")
    model = gpu_model.casefold() if gpu_model else None
    minimum = min_gpu_memory_gb * 1024**3
    return [
        gpu
        for gpu in gpu_profiles(entry)
        if (gpu_api == "any" or gpu_api in gpu["apis"])
        and (gpu["memory_bytes"] or 0) >= minimum
        and (not model or model in gpu["name"].casefold())
    ]


def node_features(
    entry: dict[str, Any],
    *,
    live_only_observed: bool = False,
) -> set[str]:
    policy = entry.get("policy") or {}
    inventory = entry.get("inventory") or {}
    execution = inventory.get("execution") or {}
    hardware = inventory.get("hardware") or {}
    baseline = inventory.get("baseline") or {}
    features = {
        str(item)
        for item in policy.get("labels", [])
        if str(item) not in LIVE_ONLY_POLICY_FEATURES
    }
    for key in ("kind", "architecture"):
        if execution.get(key):
            features.add(str(execution[key]))
    profiles = gpu_profiles(entry)
    if profiles:
        features.add("gpu")
        for profile in profiles:
            features.update(profile["apis"])
    for capability, detail in baseline.items():
        if detail.get("ready") or detail.get("online") or detail.get("installed"):
            features.add(str(capability))
    for tool, detail in (inventory.get("software") or {}).items():
        if detail.get("present"):
            features.add(str(tool))
    virtualization = (inventory.get("capabilities") or {}).get("virtualization") or {}
    hyper_v = virtualization.get("hyper_v") or {}
    broker = virtualization.get("hyper_v_broker") or {}
    if (
        live_only_observed
        and virtualization.get("hypervisor_ready") is True
        and hyper_v.get("present") is True
    ):
        features.add("hyperv")
        if (
            broker.get("available") is True
            and broker.get("system_owned") is True
        ):
            features.add("windows-clean-guest-reserve")
    return features


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_utc(value: Any) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise FleetError("lease timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def lease_paths(state_root: Path | None = None) -> tuple[Path, Path]:
    root = state_root or STATE_ROOT
    return root / "controller/leases.json", root / "controller/leases.lock"


def empty_lease_store() -> dict[str, Any]:
    return {
        "schema": "codex_fleet_leases.v2",
        "generation": 0,
        "leases": {},
        "audit": [],
    }


def validate_owner_id(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise FleetError(f"{field} is required")
        return None
    normalized = str(value)
    if not OWNER_ID_PATTERN.fullmatch(normalized):
        raise FleetError(f"{field} is invalid")
    return normalized


def validate_role(value: Any, *, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise FleetError("runner role is required")
        return None
    normalized = str(value)
    if not ROLE_PATTERN.fullmatch(normalized):
        raise FleetError("runner role is invalid")
    return normalized


def validate_admission(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or not ADMISSION_FIELDS.issubset(payload)
        or set(payload) - ADMISSION_FIELDS - ADMISSION_OPTIONAL_FIELDS
    ):
        raise FleetError("lease admission fields are invalid")
    payload.setdefault("gpu_api", "any")
    payload.setdefault("min_gpu_memory_gb", 0)
    payload.setdefault("gpu_model", None)
    parse_utc(payload["checked_at"])
    requirements = payload["requirements"]
    if (
        not isinstance(payload["inventory_age_seconds"], int)
        or payload["inventory_age_seconds"] < 0
        or not isinstance(requirements, list)
        or any(not isinstance(item, str) for item in requirements)
        or requirements != sorted(set(requirements))
        or any(not re.fullmatch(r"[a-z0-9-]{1,40}", item) for item in requirements)
        or not isinstance(payload["min_memory_gb"], int)
        or payload["min_memory_gb"] < 0
        or payload["gpu_api"] not in GPU_APIS
        or not isinstance(payload["min_gpu_memory_gb"], int)
        or payload["min_gpu_memory_gb"] < 0
        or (
            payload["gpu_model"] is not None
            and (
                not isinstance(payload["gpu_model"], str)
                or not 1 <= len(payload["gpu_model"]) <= 120
                or any(
                    character in payload["gpu_model"]
                    for character in ("\x00", "\r", "\n")
                )
            )
        )
        or any(
            not isinstance(payload[field], bool)
            for field in (
                "power_ok",
                "storage_ok",
                "thermal_ok",
                "interactive_busy",
                "busy",
                "work_volume_ready",
            )
        )
    ):
        raise FleetError("lease admission is invalid")
    return payload


def validate_lease(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or not LEASE_REQUIRED_FIELDS.issubset(payload)
        or set(payload) - LEASE_REQUIRED_FIELDS - LEASE_OPTIONAL_FIELDS
    ):
        raise FleetError("lease fields are invalid")
    payload.setdefault("dispatch_adapter", "lease-only")
    dispatch_adapter(str(payload["dispatch_adapter"]))
    try:
        uuid.UUID(str(payload["lease_id"]))
    except ValueError as exc:
        raise FleetError("lease id is invalid") from exc
    if (
        not isinstance(payload["generation"], int)
        or payload["generation"] < 1
        or not re.fullmatch(r"[0-9a-f]{32}", str(payload["nonce"]))
        or normalize_node_id(str(payload["node_id"])) != payload["node_id"]
    ):
        raise FleetError("lease identity is invalid")
    validate_owner_id(payload["owner_task"], "owner task", required=True)
    validate_owner_id(payload["owner_thread"], "owner thread")
    validate_owner_id(payload["owner_run"], "owner run")
    validate_role(payload["role"])
    workload_class = str(payload["workload_class"])
    phase = str(payload["phase"])
    if (
        workload_class not in LEASE_WORKLOAD_CLASSES
        or phase not in LEASE_PHASES
        or not isinstance(payload["priority"], int)
        or not 0 <= payload["priority"] <= 1000
        or not isinstance(payload["preemptible"], bool)
        or (
            payload["preemptible"]
            and workload_class not in PREEMPTIBLE_WORKLOAD_CLASSES
        )
    ):
        raise FleetError("lease workload policy is invalid")
    if workload_class in PROTECTED_WORKLOAD_CLASSES and (
        not payload["owner_thread"] or not payload["owner_run"]
    ):
        raise FleetError("protected lease requires owner thread and owner run")
    acquired = parse_utc(payload["acquired_at"])
    expires = parse_utc(payload["expires_at"])
    if expires <= acquired:
        raise FleetError("lease expiry is invalid")
    if not COMMIT_PATTERN.fullmatch(str(payload["control_commit"])):
        raise FleetError("lease control commit is invalid")
    validate_admission(payload["admission"])
    return payload


def validate_lease_store(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "generation", "leases", "audit"}
        or payload.get("schema") != "codex_fleet_leases.v2"
        or not isinstance(payload.get("generation"), int)
        or payload["generation"] < 0
        or not isinstance(payload.get("leases"), dict)
        or not isinstance(payload.get("audit"), list)
        or len(payload["audit"]) > 200
    ):
        raise FleetError("lease store is invalid")
    maximum = 0
    for node_id, lease in payload["leases"].items():
        if normalize_node_id(str(node_id)) != node_id:
            raise FleetError("lease store node id is invalid")
        validated = validate_lease(lease)
        payload["leases"][node_id] = validated
        if validated["node_id"] != node_id:
            raise FleetError("lease store node identity mismatch")
        maximum = max(maximum, int(validated["generation"]))
    if payload["generation"] < maximum:
        raise FleetError("lease store generation moved backward")
    for event in payload["audit"]:
        if (
            not isinstance(event, dict)
            or set(event)
            != {"event", "at", "node_id", "lease_id", "generation", "reason"}
            or event["event"] not in {"acquire", "renew", "release", "reap", "preempt"}
            or normalize_node_id(str(event["node_id"])) != event["node_id"]
            or not isinstance(event["generation"], int)
            or event["generation"] < 1
            or not isinstance(event["reason"], str)
            or len(event["reason"]) > 120
        ):
            raise FleetError("lease audit event is invalid")
        parse_utc(event["at"])
    return payload


@contextlib.contextmanager
def lease_lock(
    *,
    state_root: Path | None = None,
    exclusive: bool,
) -> Iterator[None]:
    _, lock_path = lease_paths(state_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_lease_store(*, state_root: Path | None = None) -> dict[str, Any]:
    path, _ = lease_paths(state_root)
    if not path.is_file():
        return empty_lease_store()
    if path.stat().st_mode & 0o077:
        raise FleetError("lease store must have mode 0600")
    payload = read_json(path)
    if payload.get("schema") == "codex_fleet_leases.v1":
        if payload.get("leases"):
            raise FleetError("active lease v1 state requires explicit release before upgrade")
        payload["schema"] = "codex_fleet_leases.v2"
    return validate_lease_store(payload)


def write_lease_store(
    payload: dict[str, Any],
    *,
    state_root: Path | None = None,
) -> None:
    path, _ = lease_paths(state_root)
    atomic_json(path, validate_lease_store(payload), mode=0o600)


def lease_is_expired(lease: dict[str, Any], *, now: dt.datetime) -> bool:
    return parse_utc(lease["expires_at"]) <= now.astimezone(dt.timezone.utc)


def audit_lease(
    store: dict[str, Any],
    *,
    event: str,
    lease: dict[str, Any],
    now: dt.datetime,
    reason: str,
) -> None:
    store["audit"].append(
        {
            "event": event,
            "at": now.astimezone(dt.timezone.utc).isoformat(),
            "node_id": lease["node_id"],
            "lease_id": lease["lease_id"],
            "generation": lease["generation"],
            "reason": reason[:120],
        }
    )
    store["audit"] = store["audit"][-200:]


def reap_expired_leases(
    store: dict[str, Any],
    *,
    now: dt.datetime,
    node_id: str | None = None,
) -> list[dict[str, Any]]:
    reaped: list[dict[str, Any]] = []
    for candidate, lease in list(store["leases"].items()):
        if node_id and candidate != node_id:
            continue
        if lease_is_expired(lease, now=now):
            del store["leases"][candidate]
            audit_lease(
                store,
                event="reap",
                lease=lease,
                now=now,
                reason="ttl-expired",
            )
            reaped.append(lease)
    return reaped


def public_lease(lease: dict[str, Any] | None, *, now: dt.datetime) -> dict[str, Any]:
    observed = now.astimezone(dt.timezone.utc)
    if not lease:
        return {
            "state": "available",
            "observed_at": observed.isoformat(),
            "ttl_remaining_seconds": 0,
        }
    ttl_remaining = max(0, int((parse_utc(lease["expires_at"]) - observed).total_seconds()))
    return {
        key: value
        for key, value in lease.items()
        if key != "nonce"
    } | {
        "state": "expired" if lease_is_expired(lease, now=now) else "leased",
        "observed_at": observed.isoformat(),
        "ttl_remaining_seconds": ttl_remaining,
    }


def active_lease_map(
    *,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, dict[str, Any]]:
    observed = now or utc_now()
    with lease_lock(state_root=state_root, exclusive=False):
        store = read_lease_store(state_root=state_root)
    return {
        node_id: lease
        for node_id, lease in store["leases"].items()
        if not lease_is_expired(lease, now=observed)
    }


def validate_ttl(ttl_seconds: int) -> int:
    if not 60 <= ttl_seconds <= 86_400:
        raise FleetError("lease ttl must be between 60 and 86400 seconds")
    return ttl_seconds


def build_lease(
    *,
    node_id: str,
    generation: int,
    owner_task: str,
    owner_thread: str | None,
    owner_run: str | None,
    role: str | None,
    workload_class: str,
    priority: int,
    preemptible: bool,
    phase: str,
    ttl_seconds: int,
    control_revision: str,
    admission: dict[str, Any],
    now: dt.datetime,
    dispatch_adapter_name: str = "lease-only",
) -> dict[str, Any]:
    lease = {
        "lease_id": str(uuid.uuid4()),
        "generation": generation,
        "nonce": secrets.token_hex(16),
        "node_id": normalize_node_id(node_id),
        "owner_task": validate_owner_id(owner_task, "owner task", required=True),
        "owner_thread": validate_owner_id(owner_thread, "owner thread"),
        "owner_run": validate_owner_id(owner_run, "owner run"),
        "role": validate_role(role),
        "workload_class": workload_class,
        "priority": priority,
        "preemptible": preemptible,
        "phase": phase,
        "acquired_at": now.astimezone(dt.timezone.utc).isoformat(),
        "expires_at": (
            now.astimezone(dt.timezone.utc) + dt.timedelta(seconds=validate_ttl(ttl_seconds))
        ).isoformat(),
        "control_commit": control_revision,
        "admission": admission,
        "dispatch_adapter": dispatch_adapter_name,
    }
    return validate_lease(lease)


def acquire_lease_record(
    *,
    node_id: str,
    owner_task: str,
    owner_thread: str | None,
    owner_run: str | None,
    role: str | None,
    workload_class: str,
    priority: int,
    preemptible: bool,
    phase: str,
    ttl_seconds: int,
    control_revision: str,
    admission: dict[str, Any],
    preempt_lease_id: str | None = None,
    preempt_generation: int | None = None,
    preempt_nonce: str | None = None,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
    dispatch_adapter_name: str = "lease-only",
) -> dict[str, Any]:
    observed = now or utc_now()
    node_id = normalize_node_id(node_id)
    if priority < 0 or priority > 1000:
        raise FleetError("lease priority must be between 0 and 1000")
    with lease_lock(state_root=state_root, exclusive=True):
        store = read_lease_store(state_root=state_root)
        reap_expired_leases(store, now=observed, node_id=node_id)
        current = store["leases"].get(node_id)
        if current:
            if not all(
                value is not None
                for value in (preempt_lease_id, preempt_generation, preempt_nonce)
            ):
                raise FleetError(f"node already has an active lease: {node_id}")
            if (
                current["lease_id"] != preempt_lease_id
                or current["generation"] != preempt_generation
                or not secrets.compare_digest(current["nonce"], str(preempt_nonce))
            ):
                raise FleetError("lease compare-and-swap mismatch")
            if (
                not current["preemptible"]
                or current["workload_class"] not in PREEMPTIBLE_WORKLOAD_CLASSES
                or current["phase"] != "interruptible"
                or priority <= current["priority"]
            ):
                raise FleetError("active lease is not safely preemptible")
            del store["leases"][node_id]
            audit_lease(
                store,
                event="preempt",
                lease=current,
                now=observed,
                reason=f"higher-priority-{priority}",
            )
        elif any(
            value is not None
            for value in (preempt_lease_id, preempt_generation, preempt_nonce)
        ):
            raise FleetError("lease compare-and-swap mismatch")
        store["generation"] += 1
        lease = build_lease(
            node_id=node_id,
            generation=store["generation"],
            owner_task=owner_task,
            owner_thread=owner_thread,
            owner_run=owner_run,
            role=role,
            workload_class=workload_class,
            priority=priority,
            preemptible=preemptible,
            phase=phase,
            ttl_seconds=ttl_seconds,
            control_revision=control_revision,
            admission=admission,
            now=observed,
            dispatch_adapter_name=dispatch_adapter_name,
        )
        store["leases"][node_id] = lease
        audit_lease(
            store,
            event="acquire",
            lease=lease,
            now=observed,
            reason="controller-admitted",
        )
        write_lease_store(store, state_root=state_root)
    return lease


def assert_lease_cas(
    current: dict[str, Any] | None,
    *,
    node_id: str,
    lease_id: str,
    generation: int,
    nonce: str,
    owner_task: str,
    now: dt.datetime,
) -> dict[str, Any]:
    if not current:
        raise FleetError(f"node has no active lease: {node_id}")
    if lease_is_expired(current, now=now):
        raise FleetError("lease expired; run lease reap")
    if current["owner_task"] != validate_owner_id(
        owner_task, "owner task", required=True
    ):
        raise FleetError("lease owner mismatch")
    if (
        current["lease_id"] != lease_id
        or current["generation"] != generation
        or not secrets.compare_digest(current["nonce"], nonce)
    ):
        raise FleetError("lease compare-and-swap mismatch")
    return current


def renew_lease_record(
    *,
    node_id: str,
    lease_id: str,
    generation: int,
    nonce: str,
    owner_task: str,
    ttl_seconds: int,
    phase: str | None = None,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    observed = now or utc_now()
    node_id = normalize_node_id(node_id)
    with lease_lock(state_root=state_root, exclusive=True):
        store = read_lease_store(state_root=state_root)
        current = assert_lease_cas(
            store["leases"].get(node_id),
            node_id=node_id,
            lease_id=lease_id,
            generation=generation,
            nonce=nonce,
            owner_task=owner_task,
            now=observed,
        )
        next_phase = phase or current["phase"]
        if (
            next_phase not in LEASE_PHASES
            or (
                current["phase"] == "non-interruptible"
                and next_phase != "non-interruptible"
            )
        ):
            raise FleetError("lease phase transition is invalid")
        store["generation"] += 1
        renewed = {
            **current,
            "generation": store["generation"],
            "nonce": secrets.token_hex(16),
            "phase": next_phase,
            "expires_at": (
                observed.astimezone(dt.timezone.utc)
                + dt.timedelta(seconds=validate_ttl(ttl_seconds))
            ).isoformat(),
        }
        store["leases"][node_id] = validate_lease(renewed)
        audit_lease(
            store,
            event="renew",
            lease=renewed,
            now=observed,
            reason="owner-renewed",
        )
        write_lease_store(store, state_root=state_root)
    return renewed


def release_lease_record(
    *,
    node_id: str,
    lease_id: str,
    generation: int,
    nonce: str,
    owner_task: str,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    observed = now or utc_now()
    node_id = normalize_node_id(node_id)
    with lease_lock(state_root=state_root, exclusive=True):
        store = read_lease_store(state_root=state_root)
        current = assert_lease_cas(
            store["leases"].get(node_id),
            node_id=node_id,
            lease_id=lease_id,
            generation=generation,
            nonce=nonce,
            owner_task=owner_task,
            now=observed,
        )
        del store["leases"][node_id]
        store["generation"] += 1
        audit_lease(
            store,
            event="release",
            lease=current,
            now=observed,
            reason="owner-released",
        )
        write_lease_store(store, state_root=state_root)
    return current


def select_nodes(
    catalog: dict[str, Any],
    *,
    required: set[str],
    min_memory_gb: int,
    max_age_hours: int,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
    leases: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected = []
    leases = leases or {}
    minimum = min_memory_gb * 1024**3
    for entry in catalog["nodes"]:
        policy = entry.get("policy") or {}
        receipt = entry.get("receipt") or {}
        inventory = entry.get("inventory")
        if (
            not policy.get("approved")
            or receipt.get("state") != "CURRENT"
            or not isinstance(inventory, dict)
            or not inventory_is_fresh(inventory, max_age_hours)
            or int((inventory.get("hardware") or {}).get("memory_bytes") or 0) < minimum
            or not required.issubset(node_features(entry))
            or (
                (gpu_api != "any" or min_gpu_memory_gb or gpu_model)
                and not matching_gpus(
                    entry,
                    gpu_api=gpu_api,
                    min_gpu_memory_gb=min_gpu_memory_gb,
                    gpu_model=gpu_model,
                )
            )
            or entry["node_id"] in leases
        ):
            continue
        selected.append(
            {
                "node_id": entry["node_id"],
                "display_name": policy.get("display_name"),
                "features": sorted(node_features(entry)),
                "memory_bytes": inventory["hardware"].get("memory_bytes"),
                "gpus": gpu_profiles(entry),
                "inventory_observed_at": inventory["observed_at"],
                "scheduling": inventory.get("scheduling"),
                "lease": {"state": "available"},
            }
        )
    return sorted(selected, key=lambda item: item["node_id"])


def fleet_select(args: argparse.Namespace) -> int:
    if args.min_memory_gb < 0:
        raise FleetError("minimum memory must not be negative")
    required = {
        item.strip()
        for item in str(args.requires or "").split(",")
        if item.strip()
    }
    if any(not re.fullmatch(r"[a-z0-9-]{1,40}", item) for item in required):
        raise FleetError("select requirements are invalid")
    if args.gpu_api not in GPU_APIS or args.min_gpu_memory_gb < 0:
        raise FleetError("select GPU requirements are invalid")
    max_age = int((manifest().get("inventory") or {}).get("max_age_hours", 36))
    selected = select_nodes(
        remote_asset_catalog(),
        required=required,
        min_memory_gb=args.min_memory_gb,
        gpu_api=args.gpu_api,
        min_gpu_memory_gb=args.min_gpu_memory_gb,
        gpu_model=args.gpu_model,
        max_age_hours=max_age,
        leases=active_lease_map(),
    )
    result = {
        "schema": "codex_fleet_selection.v1",
        "scope": "catalog-plus-controller-lease-live-doctor-on-acquire",
        "requires": sorted(required),
        "min_memory_gb": args.min_memory_gb,
        "gpu_api": args.gpu_api,
        "min_gpu_memory_gb": args.min_gpu_memory_gb,
        "gpu_model": args.gpu_model,
        "nodes": selected,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if selected else 1


def dispatch_adapter(adapter: str) -> dict[str, Any]:
    try:
        return DISPATCH_ADAPTERS[adapter]
    except KeyError as exc:
        raise FleetError(f"unknown dispatch adapter: {adapter}") from exc


def validate_execution_requirements(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FleetError("execution requirements must be a JSON object")
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_EXECUTION_REQUIREMENTS_BYTES:
        raise FleetError("execution requirements exceed size limit")
    allowed = {
        "schema",
        "adapter",
        "requires",
        "min_memory_gb",
        "gpu_api",
        "min_gpu_memory_gb",
        "gpu_model",
        "workload_class",
        "priority",
        "preemptible",
        "phase",
        "ttl_seconds",
    }
    if set(value) - allowed or value.get("schema") != EXECUTION_REQUIREMENTS_SCHEMA:
        raise FleetError("execution requirements schema or fields are invalid")
    requires = value.get("requires", [])
    if (
        not isinstance(requires, list)
        or any(not isinstance(item, str) for item in requires)
        or len(requires) != len(set(requires))
    ):
        raise FleetError("execution requirements list is invalid")
    parse_requirements(",".join(requires))
    for field in ("adapter", "gpu_api", "workload_class", "phase"):
        if field in value and not isinstance(value[field], str):
            raise FleetError(f"execution requirements {field} is invalid")
    adapter = str(value.get("adapter", "lease-only"))
    dispatch_adapter(adapter)
    gpu_api = str(value.get("gpu_api", "any"))
    if gpu_api not in GPU_APIS:
        raise FleetError("execution requirements GPU API is invalid")
    for field in ("min_memory_gb", "min_gpu_memory_gb", "priority", "ttl_seconds"):
        if field in value and (
            not isinstance(value[field], int)
            or isinstance(value[field], bool)
            or value[field] < 0
        ):
            raise FleetError(f"execution requirements {field} is invalid")
    if "priority" in value and value["priority"] > 1000:
        raise FleetError("execution requirements priority is invalid")
    if "ttl_seconds" in value and not 60 <= value["ttl_seconds"] <= 86_400:
        raise FleetError("execution requirements TTL is invalid")
    if "gpu_model" in value:
        model = value["gpu_model"]
        if (
            not isinstance(model, str)
            or not 1 <= len(model) <= 120
            or any(character in model for character in ("\x00", "\r", "\n"))
        ):
            raise FleetError("execution requirements GPU model is invalid")
    workload = str(value.get("workload_class", "background"))
    if workload not in LEASE_WORKLOAD_CLASSES:
        raise FleetError("execution requirements workload class is invalid")
    phase = str(value.get("phase", "interruptible"))
    if phase not in LEASE_PHASES:
        raise FleetError("execution requirements phase is invalid")
    if "preemptible" in value and not isinstance(value["preemptible"], bool):
        raise FleetError("execution requirements preemptible is invalid")
    preemptible = bool(value.get("preemptible", False))
    if preemptible and workload not in PREEMPTIBLE_WORKLOAD_CLASSES:
        raise FleetError("execution requirements workload cannot be preemptible")
    normalized = {
        "schema": EXECUTION_REQUIREMENTS_SCHEMA,
        "adapter": adapter,
        "requires": sorted(set(requires)),
        "min_memory_gb": int(value.get("min_memory_gb", 0)),
        "gpu_api": gpu_api,
        "min_gpu_memory_gb": int(value.get("min_gpu_memory_gb", 0)),
        "gpu_model": value.get("gpu_model"),
        "workload_class": workload,
        "priority": int(value.get("priority", 300)),
        "preemptible": preemptible,
        "phase": phase,
        "ttl_seconds": int(value.get("ttl_seconds", 3600)),
    }
    if normalized["gpu_api"] != "any":
        normalized["requires"] = sorted(
            set(normalized["requires"]) | {normalized["gpu_api"], "gpu"}
        )
    elif normalized["min_gpu_memory_gb"] or normalized["gpu_model"]:
        normalized["requires"] = sorted(set(normalized["requires"]) | {"gpu"})
    return normalized


def read_execution_requirements(value: str | None) -> dict[str, Any]:
    if not value:
        return validate_execution_requirements(
            {"schema": EXECUTION_REQUIREMENTS_SCHEMA}
        )
    source = value
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        if not path.is_file() or path.stat().st_size > MAX_EXECUTION_REQUIREMENTS_BYTES:
            raise FleetError("execution requirements file is unavailable or too large")
        source = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as exc:
        raise FleetError("execution requirements must be valid JSON") from exc
    return validate_execution_requirements(payload)


def request_value(
    args: argparse.Namespace,
    requirements: dict[str, Any],
    name: str,
    default: Any,
) -> Any:
    explicit = getattr(args, name, None)
    return requirements.get(name, default) if explicit is None else explicit


def dispatch_adapter_from_args(args: argparse.Namespace) -> str:
    requirements = read_execution_requirements(getattr(args, "requirements_json", None))
    explicit = getattr(args, "adapter", None)
    return str(explicit if explicit is not None else requirements["adapter"])


def dispatch_request(args: argparse.Namespace) -> dict[str, Any]:
    requirements = read_execution_requirements(getattr(args, "requirements_json", None))
    adapter = str(request_value(args, requirements, "adapter", "lease-only"))
    metadata = dispatch_adapter(adapter)
    explicit_requires = getattr(args, "requires", None)
    required = parse_requirements(
        str(explicit_requires)
    ) if explicit_requires is not None else set(requirements["requires"])
    min_memory_gb = int(request_value(args, requirements, "min_memory_gb", 0))
    gpu_api = str(request_value(args, requirements, "gpu_api", "any"))
    min_gpu_memory_gb = int(
        request_value(args, requirements, "min_gpu_memory_gb", 0)
    )
    gpu_model = request_value(args, requirements, "gpu_model", None)
    if gpu_api not in GPU_APIS:
        raise FleetError("dispatch GPU API is invalid")
    if gpu_api != "any":
        required.update({gpu_api, "gpu"})
    elif min_gpu_memory_gb or gpu_model:
        required.add("gpu")
    if min_memory_gb < 0:
        raise FleetError("minimum memory must not be negative")
    if min_gpu_memory_gb < 0:
        raise FleetError("minimum GPU memory must not be negative")
    if gpu_model is not None and (
        not isinstance(gpu_model, str)
        or not 1 <= len(gpu_model) <= 120
        or any(character in gpu_model for character in ("\x00", "\r", "\n"))
    ):
        raise FleetError("dispatch GPU model is invalid")
    priority = int(request_value(args, requirements, "priority", 300))
    if not 0 <= priority <= 1000:
        raise FleetError("dispatch priority must be between 0 and 1000")
    workload_class = str(
        request_value(args, requirements, "workload_class", "background")
    )
    if workload_class not in LEASE_WORKLOAD_CLASSES:
        raise FleetError("dispatch workload class is invalid")
    phase = str(request_value(args, requirements, "phase", "interruptible"))
    if phase not in LEASE_PHASES:
        raise FleetError("dispatch phase is invalid")
    ttl_seconds = validate_ttl(
        int(request_value(args, requirements, "ttl_seconds", 3600))
    )
    preemptible = bool(request_value(args, requirements, "preemptible", False))
    if preemptible and workload_class not in PREEMPTIBLE_WORKLOAD_CLASSES:
        raise FleetError("dispatch workload cannot be preemptible")
    role = validate_role(getattr(args, "role", None))
    node_id = (
        normalize_node_id(args.node_id)
        if getattr(args, "node_id", None)
        else None
    )
    if adapter == "github-runner" and not role:
        raise FleetError("github-runner dispatch requires --role")
    if role and adapter == "github-runner":
        # The runner transaction already owns its role binding.  Dispatch
        # planning may inspect it, but start/stop remains that transaction's
        # explicit safety boundary.
        runner_role_nodes(role)
    if adapter == "local-codex" and node_id:
        raise FleetError("local-codex does not accept a Fleet node")
    return {
        "adapter": adapter,
        "adapter_status": metadata["status"],
        "requires_fleet": metadata["requires_fleet"],
        "execution": metadata["execution"],
        "requires": sorted(required),
        "min_memory_gb": min_memory_gb,
        "gpu_api": gpu_api,
        "min_gpu_memory_gb": min_gpu_memory_gb,
        "gpu_model": gpu_model,
        "workload_class": workload_class,
        "priority": priority,
        "preemptible": preemptible,
        "phase": phase,
        "ttl_seconds": ttl_seconds,
        "role": role,
        "node_id": node_id,
    }


def dispatch_candidates(request: dict[str, Any]) -> list[dict[str, Any]]:
    if not request["requires_fleet"]:
        return []
    catalog = remote_asset_catalog()
    max_age = int((manifest().get("inventory") or {}).get("max_age_hours", 36))
    selected = select_nodes(
        catalog,
        required=set(request["requires"]),
        min_memory_gb=int(request["min_memory_gb"]),
        max_age_hours=max_age,
        gpu_api=str(request.get("gpu_api", "any")),
        min_gpu_memory_gb=int(request.get("min_gpu_memory_gb", 0)),
        gpu_model=request.get("gpu_model"),
        leases=active_lease_map(),
    )
    role = request.get("role")
    if role:
        allowed = set(runner_role_nodes(str(role)))
        selected = [item for item in selected if item["node_id"] in allowed]
    node_id = request.get("node_id")
    if node_id:
        selected = [item for item in selected if item["node_id"] == node_id]
    return selected


def dispatch_plan_payload(request: dict[str, Any]) -> dict[str, Any]:
    metadata = dispatch_adapter(str(request["adapter"]))
    if not request["requires_fleet"]:
        return {
            "schema": "codex_fleet_dispatch_plan.v1",
            "status": "local",
            "request": request,
            "selection": {
                "candidate_count": 0,
                "candidates": [],
                "fresh_doctor_before_acquire": False,
            },
            "next_action": "execute in the current Codex session",
        }
    candidates = dispatch_candidates(request)
    supported = metadata["status"] in {
        "supported",
        "supported-via-runner-transaction",
    }
    if not supported:
        status = "unsupported"
        next_action = (
            f"adapter {request['adapter']} is planned; execution adapter is not implemented"
        )
    elif not candidates:
        status = "unavailable"
        next_action = "wait for a candidate node or change explicit requirements"
    elif request["adapter"] == "github-runner":
        status = "available-via-runner-transaction"
        next_action = "use runner start/stop for the bound role; dispatch does not submit a GitHub job"
    else:
        status = "ready-to-acquire"
        next_action = "run dispatch acquire; acquire performs fresh doctor before leasing"
    return {
        "schema": "codex_fleet_dispatch_plan.v1",
        "status": status,
        "request": request,
        "selection": {
            "candidate_count": len(candidates),
            "candidates": candidates,
            "fresh_doctor_before_acquire": True,
        },
        "next_action": next_action,
    }


def dispatch_lease(dispatch_id: str) -> dict[str, Any]:
    try:
        normalized_id = str(uuid.UUID(dispatch_id))
    except ValueError as exc:
        raise FleetError("dispatch id is invalid") from exc
    with lease_lock(exclusive=False):
        store = read_lease_store()
    for lease in store["leases"].values():
        if lease["lease_id"] == normalized_id:
            return lease
    raise FleetError(f"dispatch lease is unavailable: {normalized_id}")


def fleet_dispatch_plan(args: argparse.Namespace) -> int:
    request = dispatch_request(args)
    result = dispatch_plan_payload(request)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] not in {"unavailable", "unsupported"} else 1


def fleet_dispatch_acquire(args: argparse.Namespace) -> int:
    request = dispatch_request(args)
    if request["adapter"] == "local-codex":
        print(
            json.dumps(
                {
                    "schema": "codex_fleet_dispatch_readback.v1",
                    "action": "acquire",
                    "status": "local",
                    "request": request,
                    "lease": None,
                    "next_action": "execute in the current Codex session",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    controller_guard()
    if request["adapter"] not in {"lease-only", "ssh-session"}:
        if request["adapter"] == "github-runner":
            raise FleetError(
                "github-runner uses the existing runner start/stop transaction; "
                "dispatch does not submit a GitHub job"
            )
        raise FleetError(
            f"adapter {request['adapter']} has no dispatch acquire route"
        )
    candidates = dispatch_candidates(request)
    if not candidates:
        raise FleetError("no dispatch candidate is available")
    registry = node_registry()
    required = set(request["requires"])
    node_id: str | None = None
    role: str | None = None
    admission: dict[str, Any] | None = None
    rejected: list[str] = []
    for candidate in candidates:
        candidate_id = str(candidate["node_id"])
        try:
            candidate_role = request.get("role")
            if candidate_role:
                candidate_role = assert_runner_role_node(
                    str(candidate_role), candidate_id, registry=registry
                )
                assert_runner_role_workload(
                    candidate_role,
                    str(request["workload_class"]),
                    registry=registry,
                )
            doctor = doctor_result(candidate_id)
            assert_lease_admission(
                doctor,
                required=required,
                min_memory_gb=int(request["min_memory_gb"]),
                gpu_api=str(request["gpu_api"]),
                min_gpu_memory_gb=int(request["min_gpu_memory_gb"]),
                gpu_model=request["gpu_model"],
            )
            admission = build_admission_receipt(
                doctor,
                required=required,
                min_memory_gb=int(request["min_memory_gb"]),
                gpu_api=str(request["gpu_api"]),
                min_gpu_memory_gb=int(request["min_gpu_memory_gb"]),
                gpu_model=request["gpu_model"],
            )
            node_id = candidate_id
            role = candidate_role
            break
        except FleetError as exc:
            rejected.append(f"{candidate_id}:{str(exc)[:120]}")
    if node_id is None or admission is None:
        detail = ";".join(rejected) or "no-fresh-admission"
        raise FleetError(f"no dispatch candidate passed fresh doctor: {detail}")
    revision = control_commit()
    lease = acquire_lease_record(
        node_id=node_id,
        owner_task=args.owner_task,
        owner_thread=args.owner_thread,
        owner_run=args.owner_run,
        role=role,
        workload_class=str(request["workload_class"]),
        priority=int(request["priority"]),
        preemptible=bool(request["preemptible"]),
        phase=str(request["phase"]),
        ttl_seconds=int(request["ttl_seconds"]),
        control_revision=revision,
        admission=admission,
        preempt_lease_id=args.preempt_lease_id,
        preempt_generation=args.preempt_generation,
        preempt_nonce=args.preempt_nonce,
        dispatch_adapter_name=str(request["adapter"]),
    )
    dispatch_id = lease["lease_id"]
    print(
        json.dumps(
            {
                "schema": "codex_fleet_dispatch_readback.v1",
                "action": "acquire",
                "status": "leased",
                "dispatch_id": dispatch_id,
                "request": request,
                "lease": public_lease(lease, now=utc_now()),
                "execution": request["execution"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_dispatch_verify(args: argparse.Namespace) -> int:
    controller_guard()
    lease = dispatch_lease(args.dispatch_id)
    result = verify_lease_record(
        lease,
        node_id=lease["node_id"],
        role=lease["role"],
        lease_id=lease["lease_id"],
        generation=int(lease["generation"]),
        owner_task=lease["owner_task"],
        owner_thread=lease["owner_thread"],
        owner_run=lease["owner_run"],
        workload_class=lease["workload_class"],
        phase=lease["phase"],
        preemptible=bool(lease["preemptible"]),
        min_ttl_seconds=int(args.min_ttl_seconds),
        required=set(lease["admission"]["requirements"]),
        min_memory_gb=int(lease["admission"]["min_memory_gb"]),
        gpu_api=str(lease["admission"]["gpu_api"]),
        min_gpu_memory_gb=int(lease["admission"]["min_gpu_memory_gb"]),
        gpu_model=lease["admission"]["gpu_model"],
        expected_dispatch_adapter=str(lease["dispatch_adapter"]),
        max_admission_age_seconds=int(args.max_admission_age_seconds),
        expected_control_commit=lease["control_commit"],
        current_control_commit=control_commit(),
        registry=node_registry(),
        now=utc_now(),
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_dispatch_readback.v1",
                "action": "verify",
                "dispatch_id": lease["lease_id"],
                "verification": result,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def validate_execution_argv(value: str) -> list[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise FleetError("dispatch argv must be valid JSON") from exc
    if (
        not isinstance(payload, list)
        or not 1 <= len(payload) <= 128
        or any(
            not isinstance(item, str)
            or not item
            or len(item.encode("utf-8")) > 4096
            or "\x00" in item
            for item in payload
        )
        or len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 32_768
    ):
        raise FleetError("dispatch argv is invalid")
    return payload


def validate_execution_result(value: Any) -> dict[str, Any]:
    fields = {
        "schema",
        "started_at",
        "finished_at",
        "exit_code",
        "timed_out",
        "stdout",
        "stderr",
        "stdout_truncated",
        "stderr_truncated",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("schema") != "codex_fleet_ssh_execution_result.v1"
        or not isinstance(value.get("timed_out"), bool)
        or not isinstance(value.get("stdout"), str)
        or not isinstance(value.get("stderr"), str)
        or not isinstance(value.get("stdout_truncated"), bool)
        or not isinstance(value.get("stderr_truncated"), bool)
        or (
            value.get("exit_code") is not None
            and not isinstance(value.get("exit_code"), int)
        )
        or len(value["stdout"].encode("utf-8")) > MAX_EXECUTION_OUTPUT_BYTES * 4
        or len(value["stderr"].encode("utf-8")) > MAX_EXECUTION_OUTPUT_BYTES * 4
    ):
        raise FleetError("SSH execution result is invalid")
    parse_utc(value["started_at"])
    parse_utc(value["finished_at"])
    return value


def execute_ssh_session(
    node_id: str,
    *,
    argv: list[str],
    cwd: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    if not 1 <= timeout_seconds <= REMOTE_EXECUTION_TIMEOUT_SECONDS:
        raise FleetError("SSH execution timeout is invalid")
    if cwd is not None and (
        not cwd
        or len(cwd.encode("utf-8")) > 1024
        or any(character in cwd for character in ("\x00", "\r", "\n"))
    ):
        raise FleetError("SSH execution cwd is invalid")
    route = read_routes()["routes"].get(normalize_node_id(node_id)) or {}
    ssh_alias = route.get("ssh")
    if route.get("local") is True or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,120}", str(ssh_alias or "")
    ):
        raise FleetError(f"controlled SSH route is unavailable: {node_id}")
    payload = {
        "argv": argv,
        "cwd": cwd,
        "timeout_seconds": timeout_seconds,
        "output_limit": MAX_EXECUTION_OUTPUT_BYTES,
    }
    command = f"python3 -c {shlex.quote(REMOTE_EXECUTOR)}"
    try:
        completed = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                str(ssh_alias),
                command,
            ],
            check=False,
            input_text=json.dumps(payload, ensure_ascii=False),
            timeout=timeout_seconds + 15,
        )
    except subprocess.TimeoutExpired:
        return {
            "known": False,
            "reason": "ssh-controller-timeout",
            "transport_returncode": None,
        }
    if completed.returncode:
        return {
            "known": False,
            "reason": "ssh-transport-failed",
            "transport_returncode": completed.returncode,
        }
    try:
        result = validate_execution_result(json.loads(completed.stdout))
    except (json.JSONDecodeError, FleetError):
        return {
            "known": False,
            "reason": "ssh-result-invalid",
            "transport_returncode": completed.returncode,
        }
    return {"known": True, "result": result}


def fleet_dispatch_execute(args: argparse.Namespace) -> int:
    controller_guard()
    lease = dispatch_lease(args.dispatch_id)
    if lease["dispatch_adapter"] != "ssh-session":
        raise FleetError("dispatch execute requires an ssh-session lease")
    expected_owners = {
        "owner_task": validate_owner_id(args.owner_task, "owner task", required=True),
        "owner_thread": validate_owner_id(args.owner_thread, "owner thread"),
        "owner_run": validate_owner_id(args.owner_run, "owner run"),
    }
    for field, expected in expected_owners.items():
        if lease[field] != expected:
            raise FleetError(f"dispatch {field.replace('_', ' ')} mismatch")
    minimum_ttl = max(int(args.min_ttl_seconds), int(args.timeout_seconds) + 30)
    admission = lease["admission"]
    verification = verify_lease_record(
        lease,
        node_id=lease["node_id"],
        role=lease["role"],
        lease_id=lease["lease_id"],
        generation=int(lease["generation"]),
        owner_task=lease["owner_task"],
        owner_thread=lease["owner_thread"],
        owner_run=lease["owner_run"],
        workload_class=lease["workload_class"],
        phase=lease["phase"],
        preemptible=bool(lease["preemptible"]),
        min_ttl_seconds=minimum_ttl,
        required=set(admission["requirements"]),
        min_memory_gb=int(admission["min_memory_gb"]),
        max_admission_age_seconds=int(args.max_admission_age_seconds),
        expected_control_commit=lease["control_commit"],
        current_control_commit=control_commit(),
        registry=node_registry(),
        now=utc_now(),
        gpu_api=str(admission["gpu_api"]),
        min_gpu_memory_gb=int(admission["min_gpu_memory_gb"]),
        gpu_model=admission["gpu_model"],
        expected_dispatch_adapter="ssh-session",
    )
    execution = execute_ssh_session(
        lease["node_id"],
        argv=validate_execution_argv(args.argv_json),
        cwd=args.cwd,
        timeout_seconds=int(args.timeout_seconds),
    )
    if not execution["known"]:
        payload = {
            "schema": "codex_fleet_dispatch_readback.v1",
            "action": "execute",
            "status": "unknown",
            "dispatch_id": lease["lease_id"],
            "node_id": lease["node_id"],
            "verification": verification,
            "transport": execution,
            "release_required": True,
            "lease_retained": True,
            "next_action": "reconcile the remote workload read-only; retain the lease before retry",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    result = execution["result"]
    payload = {
        "schema": "codex_fleet_dispatch_readback.v1",
        "action": "execute",
        "status": "timed-out" if result["timed_out"] else "completed",
        "dispatch_id": lease["lease_id"],
        "node_id": lease["node_id"],
        "verification": verification,
        "result": result,
        "release_required": True,
        "next_action": "record task evidence, then explicitly release the dispatch lease",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def fleet_dispatch_release(args: argparse.Namespace) -> int:
    controller_guard()
    lease = dispatch_lease(args.dispatch_id)
    if args.owner_task != lease["owner_task"]:
        raise FleetError("dispatch owner mismatch")
    released = release_lease_record(
        node_id=lease["node_id"],
        lease_id=lease["lease_id"],
        generation=int(lease["generation"]),
        nonce=lease["nonce"],
        owner_task=lease["owner_task"],
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_dispatch_readback.v1",
                "action": "release",
                "status": "released",
                "dispatch_id": lease["lease_id"],
                "released": public_lease(released, now=utc_now()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def validate_work_volume_route(value: Any) -> dict[str, Any]:
    subpath = str(value.get("probe_subpath", "")) if isinstance(value, dict) else ""
    if (
        not isinstance(value, dict)
        or set(value)
        != {"volume_uuid", "filesystem", "min_free_gb", "probe_subpath"}
        or str(value.get("filesystem", "")).lower() != "apfs"
        or not isinstance(value.get("min_free_gb"), int)
        or not 1 <= value["min_free_gb"] <= 10_000
        or not 1 <= len(subpath) <= 240
        or "\\" in subpath
        or any(part in {"", ".", ".."} for part in subpath.split("/"))
    ):
        raise FleetError("fleet work volume route is invalid")
    try:
        uuid.UUID(str(value["volume_uuid"]))
    except ValueError as exc:
        raise FleetError("fleet work volume UUID is invalid") from exc
    return value


def read_routes() -> dict[str, Any]:
    if not ROUTES_PATH.is_file():
        return {"schema": "codex_fleet_routes.v1", "routes": {}}
    if ROUTES_PATH.stat().st_mode & 0o077:
        raise FleetError("fleet routes file must have mode 0600")
    payload = read_json(ROUTES_PATH)
    if set(payload) != {"schema", "routes"} or payload.get("schema") != "codex_fleet_routes.v1":
        raise FleetError("fleet routes file is invalid")
    routes = payload.get("routes")
    if not isinstance(routes, dict):
        raise FleetError("fleet routes are invalid")
    for node_id, route in routes.items():
        if (
            normalize_node_id(str(node_id)) != node_id
            or not isinstance(route, dict)
            or set(route)
            - {"local", "ssh", "tailscale_host", "work_volume", "runner_control"}
            or ("local" in route and not isinstance(route["local"], bool))
            or (
                "ssh" in route
                and not isinstance(route["ssh"], str)
            )
            or (
                "tailscale_host" in route
                and not isinstance(route["tailscale_host"], str)
            )
        ):
            raise FleetError(f"fleet route is invalid: {node_id}")
        if "work_volume" in route:
            validate_work_volume_route(route["work_volume"])
        if "runner_control" in route:
            validate_runner_control(route["runner_control"])
    return payload


def validate_runner_control(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != {"shell", "start", "stop", "status"}
        or value.get("shell") not in {"posix", "powershell"}
    ):
        raise FleetError("runner control route is invalid")
    for action in ("start", "stop", "status"):
        command = value.get(action)
        if (
            not isinstance(command, str)
            or not 1 <= len(command) <= 4000
            or any(character in command for character in ("\x00", "\r", "\n"))
        ):
            raise FleetError(f"runner control {action} command is invalid")
    return value


def tailscale_online(host: str | None) -> bool | None:
    if not host or not shutil.which("tailscale"):
        return None
    result = run(["tailscale", "status", "--json"], check=False)
    if result.returncode:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    candidates = [payload.get("Self"), *(payload.get("Peer") or {}).values()]
    expected = host.casefold().rstrip(".")
    for item in candidates:
        if not isinstance(item, dict):
            continue
        names = {
            str(item.get("HostName", "")).casefold().rstrip("."),
            str(item.get("DNSName", "")).casefold().rstrip("."),
        }
        if expected in names:
            return bool(item.get("Online"))
    return False


def work_volume_status(
    *,
    node_id: str,
    route: dict[str, Any],
    local: bool,
    ssh_alias: str | None,
    required: bool = False,
) -> dict[str, Any]:
    configured = route.get("work_volume")
    if not required and not configured:
        return {"required": False, "configured": False, "ready": True}
    if not configured:
        return {"required": required, "configured": False, "ready": False}
    spec = validate_work_volume_route(configured)
    if not local and not ssh_alias:
        return {"required": required, "configured": True, "ready": False}
    prefix = [] if local else [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        str(ssh_alias),
    ]
    diskutil_command = [
        "diskutil",
        "info",
        "-plist",
        str(spec["volume_uuid"]),
    ]
    info_result = run(
        [*prefix, *diskutil_command]
        if local
        else [*prefix, shlex.join(diskutil_command)],
        check=False,
    )
    if info_result.returncode:
        return {"required": required, "configured": True, "ready": False}
    try:
        info = plistlib.loads(info_result.stdout.encode("utf-8"))
    except Exception:
        return {"required": required, "configured": True, "ready": False}
    mount_point = info.get("MountPoint")
    identity_match = (
        str(info.get("VolumeUUID", "")).casefold()
        == str(spec["volume_uuid"]).casefold()
    )
    filesystem = str(
        info.get("FilesystemType")
        or info.get("FileSystemPersonality")
        or ""
    ).lower()
    if not mount_point or not identity_match:
        return {
            "required": required,
            "configured": True,
            "identity_match": identity_match,
            "mounted": bool(mount_point),
            "filesystem": filesystem or None,
            "ready": False,
        }
    script = (
        "import json,os,shutil,sys;"
        "path=sys.argv[1];exists=os.path.isdir(path);"
        "usage=shutil.disk_usage(path) if exists else None;"
        "print(json.dumps({'exists':exists,"
        "'writable':exists and os.access(path,os.W_OK),"
        "'free_bytes':usage.free if usage else 0}))"
    )
    probe_command = [
        "python3",
        "-c",
        script,
        str(Path(str(mount_point)) / str(spec["probe_subpath"])),
    ]
    probe = run(
        probe_command
        if local
        else [*prefix, shlex.join(probe_command)],
        check=False,
    )
    try:
        usage = json.loads(probe.stdout) if probe.returncode == 0 else {}
    except json.JSONDecodeError:
        usage = {}
    free_bytes = int(usage.get("free_bytes") or 0)
    exists = usage.get("exists") is True
    writable = usage.get("writable") is True
    minimum = int(spec["min_free_gb"]) * 1024**3
    ready = bool(
        identity_match
        and filesystem == "apfs"
        and exists
        and writable
        and free_bytes >= minimum
    )
    return {
        "required": required,
        "configured": True,
        "identity_match": identity_match,
        "mounted": True,
        "filesystem": filesystem or None,
        "probe_exists": exists,
        "writable": writable,
        "free_bytes": free_bytes,
        "min_free_bytes": minimum,
        "ready": ready,
    }


def doctor_result(
    node_id: str,
    *,
    catalog: dict[str, Any] | None = None,
    routes: dict[str, Any] | None = None,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    node_id = normalize_node_id(node_id)
    catalog = catalog or remote_asset_catalog()
    entry = next(
        (item for item in catalog["nodes"] if item.get("node_id") == node_id),
        None,
    )
    if not entry:
        raise FleetError(f"unknown fleet node: {node_id}")
    route_map = routes if routes is not None else read_routes()["routes"]
    route = route_map.get(node_id) or {}
    local = bool(route.get("local"))
    ssh_alias = route.get("ssh")
    ssh_reachable: bool | None = True if local else None
    if ssh_alias:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", str(ssh_alias)):
            raise FleetError("SSH route alias is invalid")
        probe = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=6",
                str(ssh_alias),
                "true",
            ],
            check=False,
        )
        ssh_reachable = probe.returncode == 0
    inventory = entry.get("inventory")
    live_inventory = None
    if local:
        live_inventory = collect_inventory(node_id, manifest(), node_registry())
    elif ssh_alias and ssh_reachable:
        probe = run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                str(ssh_alias),
                "bash",
                "-lc",
                shlex.quote(
                    "if command -v opl-fleet >/dev/null 2>&1; then "
                    "opl-fleet inventory --json; else codex-fleet inventory --json; fi"
                ),
            ],
            check=False,
        )
        if probe.returncode == 0:
            try:
                live_inventory = validate_inventory(json.loads(probe.stdout))
            except Exception:
                live_inventory = None
    if live_inventory:
        inventory = live_inventory
    observed = now or utc_now()
    effective_entry = {**entry, "inventory": inventory}
    max_age = int((manifest().get("inventory") or {}).get("max_age_hours", 36))
    inventory_age = (
        inventory_age_seconds(inventory, now=observed)
        if isinstance(inventory, dict)
        else None
    )
    fresh = bool(
        isinstance(inventory, dict)
        and inventory_age is not None
        and 0 <= inventory_age <= max_age * 3600
    )
    tailnet_online = tailscale_online(route.get("tailscale_host"))
    codex_ready = bool(
        isinstance(inventory, dict)
        and (inventory.get("baseline") or {}).get("codex", {}).get("ready")
    )
    scheduling = (
        (inventory.get("scheduling") or {})
        if isinstance(inventory, dict)
        else {}
    )
    dispatch_eligible = scheduling.get("eligible") is True
    scheduling_gates_ready = bool(
        scheduling.get("power_ok") is True
        and scheduling.get("storage_ok") is True
        and scheduling.get("thermal_ok") is True
        and scheduling.get("interactive_busy") is False
        and scheduling.get("busy") is False
    )
    volume = work_volume_status(
        node_id=node_id,
        route=route,
        local=local,
        ssh_alias=str(ssh_alias) if ssh_alias else None,
        required=bool(
            ((entry.get("policy") or {}).get("scheduling") or {}).get(
                "work_volume_required"
            )
        ),
    )
    availability_policy = str(
        (entry.get("policy") or {}).get("availability_policy", "always_on")
    )
    if local or ssh_reachable is True:
        availability = "online"
    elif ssh_reachable is False:
        availability = (
            "offline_expected"
            if availability_policy == "on_demand"
            else "maintenance"
            if availability_policy == "maintenance"
            else "unreachable"
        )
    else:
        availability = "unknown"
    admission_ready = bool(
        (entry.get("policy") or {}).get("approved")
        and (entry.get("receipt") or {}).get("state") == "CURRENT"
        and fresh
        and codex_ready
        and ssh_reachable is True
        and tailnet_online is True
        and dispatch_eligible
        and scheduling_gates_ready
        and volume["ready"] is True
    )
    leases = active_lease_map(state_root=state_root, now=observed)
    lease = leases.get(node_id)
    result = {
        "schema": "codex_fleet_doctor.v1",
        "node_id": node_id,
        "checked_at": observed.astimezone(dt.timezone.utc).isoformat(),
        "inventory_age_seconds": inventory_age,
        "ready_for_dispatch": admission_ready and lease is None,
        "admission_ready": admission_ready,
        "approved": bool((entry.get("policy") or {}).get("approved")),
        "availability_policy": availability_policy,
        "availability": availability,
        "receipt_state": (entry.get("receipt") or {}).get("state", "NO_RECEIPT"),
        "inventory_fresh": fresh,
        "codex_ready": codex_ready,
        "live_inventory": bool(live_inventory),
        "features": sorted(
            node_features(
                effective_entry,
                live_only_observed=live_inventory is not None,
            )
        ),
        "memory_bytes": (
            (inventory.get("hardware") or {}).get("memory_bytes")
            if isinstance(inventory, dict)
            else None
        ),
        "gpus": gpu_profiles(effective_entry),
        "lease": public_lease(lease, now=observed),
        "scheduling": scheduling,
        "ssh": {
            "configured": bool(local or ssh_alias),
            "reachable": ssh_reachable,
        },
        "tailscale": {
            "configured": bool(route.get("tailscale_host")),
            "online": tailnet_online,
        },
        "work_volume": volume,
    }
    return result


def fleet_doctor(node_id: str) -> int:
    result = doctor_result(node_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_for_dispatch"] else 1


def controller_guard() -> str:
    controller = node_identity()
    policy = node_registry()["nodes"].get(controller) or {}
    route = read_routes()["routes"].get(controller) or {}
    if "controller" not in policy.get("labels", []) or route.get("local") is not True:
        raise FleetError("lease commands must run on the configured Fleet controller")
    return controller


def parse_requirements(value: str) -> set[str]:
    required = {item.strip() for item in value.split(",") if item.strip()}
    if any(not re.fullmatch(r"[a-z0-9-]{1,40}", item) for item in required):
        raise FleetError("lease requirements are invalid")
    return required


def runner_role_nodes(
    role: str,
    *,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    normalized = validate_role(role, required=True)
    mapping = (registry or node_registry())["runner_roles"]
    nodes = mapping.get(normalized)
    if not nodes:
        raise FleetError(f"unknown runner role: {normalized}")
    return list(nodes)


def assert_runner_role_node(
    role: str,
    node_id: str,
    *,
    registry: dict[str, Any] | None = None,
) -> str:
    normalized_node = normalize_node_id(node_id)
    normalized_role = validate_role(role, required=True)
    if normalized_node not in runner_role_nodes(normalized_role, registry=registry):
        raise FleetError(
            f"runner role does not allow node: {normalized_role}/{normalized_node}"
        )
    return normalized_role


def assert_runner_role_workload(
    role: str,
    workload_class: str,
    *,
    registry: dict[str, Any] | None = None,
) -> None:
    payload = registry or node_registry()
    normalized_role = validate_role(role, required=True)
    allowed = (payload.get("runner_role_workloads") or {}).get(normalized_role)
    if allowed is not None and workload_class not in allowed:
        raise FleetError(
            "runner role does not allow workload: "
            f"{normalized_role}/{workload_class}"
        )


def assert_lease_admission(
    doctor: dict[str, Any],
    *,
    required: set[str],
    min_memory_gb: int,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
) -> None:
    if min_memory_gb < 0:
        raise FleetError("minimum memory must not be negative")
    if gpu_api not in GPU_APIS or min_gpu_memory_gb < 0:
        raise FleetError("GPU admission requirement is invalid")
    scheduling = doctor.get("scheduling") or {}
    failures: list[str] = []
    if not doctor.get("approved"):
        failures.append("not-approved")
    if doctor.get("receipt_state") != "CURRENT":
        failures.append("not-current")
    if not doctor.get("inventory_fresh"):
        failures.append("inventory-stale")
    if not doctor.get("codex_ready"):
        failures.append("codex-not-ready")
    if (doctor.get("ssh") or {}).get("reachable") is not True:
        failures.append("ssh-unreachable")
    if (doctor.get("tailscale") or {}).get("online") is not True:
        failures.append("tailscale-offline")
    if scheduling.get("power_ok") is not True:
        failures.append("ac-required")
    if scheduling.get("storage_ok") is not True:
        failures.append("storage-gate")
    if scheduling.get("thermal_ok") is not True:
        failures.append("thermal-gate")
    if scheduling.get("interactive_busy") is True:
        failures.append("interactive-busy")
    elif scheduling.get("interactive_busy") is not False:
        failures.append("occupancy-unknown")
    if scheduling.get("busy") is True:
        failures.append("busy")
    if (doctor.get("work_volume") or {}).get("ready") is not True:
        failures.append("work-volume")
    available = {str(item) for item in doctor.get("features") or []}
    if not required.issubset(available):
        failures.append("capability")
    minimum = min_memory_gb * 1024**3
    if int(doctor.get("memory_bytes") or 0) < minimum:
        failures.append("memory")
    # doctor GPU profiles are already normalized; match them directly here.
    model = gpu_model.casefold() if gpu_model else None
    minimum_gpu = min_gpu_memory_gb * 1024**3
    matching = [
        gpu
        for gpu in doctor.get("gpus") or []
        if (gpu_api == "any" or gpu_api in (gpu.get("apis") or []))
        and int(gpu.get("memory_bytes") or 0) >= minimum_gpu
        and (not model or model in str(gpu.get("name") or "").casefold())
    ]
    if (gpu_api != "any" or min_gpu_memory_gb or gpu_model) and not matching:
        failures.append("gpu")
    if failures or not doctor.get("admission_ready"):
        detail = ",".join(dict.fromkeys(failures or ["doctor-not-ready"]))
        raise FleetError(f"lease admission rejected: {detail}")


def build_admission_receipt(
    doctor: dict[str, Any],
    *,
    required: set[str],
    min_memory_gb: int,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
) -> dict[str, Any]:
    scheduling = doctor.get("scheduling") or {}
    return validate_admission(
        {
            "checked_at": doctor["checked_at"],
            "inventory_age_seconds": int(doctor["inventory_age_seconds"]),
            "requirements": sorted(required),
            "min_memory_gb": min_memory_gb,
            "gpu_api": gpu_api,
            "min_gpu_memory_gb": min_gpu_memory_gb,
            "gpu_model": gpu_model,
            "power_ok": scheduling.get("power_ok") is True,
            "storage_ok": scheduling.get("storage_ok") is True,
            "thermal_ok": scheduling.get("thermal_ok") is True,
            "interactive_busy": scheduling.get("interactive_busy") is True,
            "busy": scheduling.get("busy") is True,
            "work_volume_ready": (doctor.get("work_volume") or {}).get("ready") is True,
        }
    )


def verify_lease_record(
    lease: dict[str, Any],
    *,
    node_id: str,
    role: str | None,
    lease_id: str,
    generation: int,
    owner_task: str,
    owner_thread: str | None,
    owner_run: str | None,
    workload_class: str,
    phase: str,
    preemptible: bool,
    min_ttl_seconds: int,
    required: set[str],
    min_memory_gb: int,
    max_admission_age_seconds: int,
    expected_control_commit: str,
    current_control_commit: str,
    registry: dict[str, Any],
    now: dt.datetime,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
    expected_dispatch_adapter: str = "lease-only",
) -> dict[str, Any]:
    validated = validate_lease(lease)
    normalized_node = normalize_node_id(node_id)
    normalized_role = validate_role(role)
    if normalized_role:
        normalized_role = assert_runner_role_node(
            normalized_role,
            normalized_node,
            registry=registry,
        )
    expected_owner_task = validate_owner_id(
        owner_task, "owner task", required=True
    )
    expected_owner_thread = validate_owner_id(owner_thread, "owner thread")
    expected_owner_run = validate_owner_id(owner_run, "owner run")
    if (
        workload_class not in LEASE_WORKLOAD_CLASSES
        or phase not in LEASE_PHASES
        or not isinstance(preemptible, bool)
    ):
        raise FleetError("lease verification expectation is invalid")
    if (
        not 1 <= min_ttl_seconds <= 86_400
        or not 1 <= max_admission_age_seconds <= 86_400
        or min_memory_gb < 0
    ):
        raise FleetError("lease verification freshness requirement is invalid")
    if gpu_api not in GPU_APIS or min_gpu_memory_gb < 0:
        raise FleetError("lease verification GPU requirement is invalid")
    dispatch_adapter(expected_dispatch_adapter)
    if (
        not COMMIT_PATTERN.fullmatch(expected_control_commit)
        or not COMMIT_PATTERN.fullmatch(current_control_commit)
    ):
        raise FleetError("lease verification control commit is invalid")

    failures: list[str] = []
    expected = {
        "node_id": normalized_node,
        "role": normalized_role,
        "lease_id": lease_id,
        "generation": generation,
        "owner_task": expected_owner_task,
        "owner_thread": expected_owner_thread,
        "owner_run": expected_owner_run,
        "workload_class": workload_class,
        "phase": phase,
        "preemptible": preemptible,
        "control_commit": expected_control_commit,
        "dispatch_adapter": expected_dispatch_adapter,
    }
    for field, value in expected.items():
        if validated[field] != value:
            failures.append(field)
    if current_control_commit != expected_control_commit:
        failures.append("controller-currentness")

    observed = now.astimezone(dt.timezone.utc)
    ttl_remaining = int((parse_utc(validated["expires_at"]) - observed).total_seconds())
    if ttl_remaining < min_ttl_seconds:
        failures.append("ttl")

    admission = validated["admission"]
    admission_age = int((observed - parse_utc(admission["checked_at"])).total_seconds())
    if not 0 <= admission_age <= max_admission_age_seconds:
        failures.append("admission-freshness")
    if admission["requirements"] != sorted(required):
        failures.append("requirements")
    if admission["min_memory_gb"] != min_memory_gb:
        failures.append("memory")
    if admission["gpu_api"] != gpu_api:
        failures.append("gpu-api")
    if admission["min_gpu_memory_gb"] != min_gpu_memory_gb:
        failures.append("gpu-memory")
    if admission["gpu_model"] != gpu_model:
        failures.append("gpu-model")
    if not all(
        admission[field]
        for field in (
            "power_ok",
            "storage_ok",
            "thermal_ok",
            "work_volume_ready",
        )
    ):
        failures.append("admission-conclusions")
    if admission["interactive_busy"] or admission["busy"]:
        failures.append("admission-occupancy")
    if failures:
        raise FleetError(
            "lease verification failed: " + ",".join(dict.fromkeys(failures))
        )
    return {
        "schema": "codex_fleet_lease_verification.v1",
        "verified": True,
        "observed_at": observed.isoformat(),
        "control_commit": current_control_commit,
        "lease": public_lease(validated, now=observed),
    }


def runner_transaction_path(role: str) -> Path:
    normalized = validate_role(role, required=True)
    return STATE_ROOT / "controller/runner-transactions" / f"{normalized}.json"


def runner_binding(
    role: str,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = registry or node_registry()
    binding = (payload.get("runner_bindings") or {}).get(
        validate_role(role, required=True)
    )
    if not isinstance(binding, dict):
        raise FleetError(f"runner binding is unavailable: {role}")
    return binding


def runner_control_route(node_id: str) -> dict[str, Any]:
    route = read_routes()["routes"].get(normalize_node_id(node_id)) or {}
    control = route.get("runner_control")
    if not isinstance(control, dict):
        raise FleetError(f"runner control route is unavailable: {node_id}")
    return validate_runner_control(control)


def runner_control_call(
    node_id: str,
    action: str,
    *,
    check: bool = True,
) -> dict[str, Any]:
    if action not in {"start", "stop", "status"}:
        raise FleetError(f"unsupported runner control action: {action}")
    node_id = normalize_node_id(node_id)
    route = read_routes()["routes"].get(node_id) or {}
    control = runner_control_route(node_id)
    command = str(control[action])
    local = bool(route.get("local"))
    ssh_alias = route.get("ssh")
    if not local and not ssh_alias:
        raise FleetError(f"runner control route has no transport: {node_id}")
    if local:
        invocation = (
            ["bash", "-lc", command]
            if control["shell"] == "posix"
            else ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        )
        input_text = None
    else:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", str(ssh_alias)):
            raise FleetError("SSH route alias is invalid")
        if control["shell"] == "powershell":
            invocation = [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                str(ssh_alias),
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ]
            input_text = None
        else:
            invocation = [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                str(ssh_alias),
                "bash",
                "-s",
            ]
            input_text = command
    result = run(invocation, check=False, input_text=input_text)
    if result.returncode and check:
        detail = (result.stderr or result.stdout).strip() or "runner control failed"
        raise FleetError(f"runner {action} failed: {detail[:240]}")
    if result.returncode:
        return {"ok": False, "action": action, "returncode": result.returncode}
    if action != "status":
        return {"ok": True, "action": action}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FleetError("runner status did not return JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"enabled", "online", "processes"}
        or not isinstance(payload["enabled"], bool)
        or not isinstance(payload["online"], bool)
        or not isinstance(payload["processes"], int)
        or payload["processes"] < 0
    ):
        raise FleetError("runner status payload is invalid")
    return payload


def github_runner_state(repository: str, runner_name: str) -> dict[str, Any]:
    result = run(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repository}/actions/runners?per_page=100",
        ],
        check=False,
    )
    if result.returncode:
        raise FleetError("GitHub runner inventory is unavailable")
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FleetError("GitHub runner inventory is not JSON") from exc
    runners = [
        item
        for page in pages
        if isinstance(page, dict)
        for item in page.get("runners", [])
        if isinstance(item, dict)
    ]
    matches = [item for item in runners if item.get("name") == runner_name]
    if len(matches) > 1:
        raise FleetError(f"GitHub runner name is not unique: {runner_name}")
    if not matches:
        return {"registered": False, "online": False, "busy": False}
    runner = matches[0]
    return {
        "registered": True,
        "online": runner.get("status") == "online",
        "busy": runner.get("busy") is True,
        "id": runner.get("id"),
    }


def wait_runner_state(
    repository: str,
    runner_name: str,
    *,
    expect_online: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, timeout_seconds)
    last: dict[str, Any] | None = None
    while True:
        last = github_runner_state(repository, runner_name)
        if bool(last["online"]) is expect_online:
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(2)


def wait_runner_processes(
    node_id: str,
    *,
    expect_zero: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0, timeout_seconds)
    last: dict[str, Any] | None = None
    while True:
        last = runner_control_call(node_id, "status")
        if (last["processes"] == 0) is expect_zero:
            return last
        if time.monotonic() >= deadline:
            return last
        time.sleep(2)


def read_runner_transaction(role: str) -> dict[str, Any] | None:
    path = runner_transaction_path(role)
    if not path.is_file():
        return None
    if path.stat().st_mode & 0o077:
        raise FleetError("runner transaction must have mode 0600")
    payload = read_json(path)
    v1_fields = {
        "schema",
        "role",
        "node_id",
        "repository",
        "runner_name",
        "lease_id",
        "generation",
        "nonce",
        "owner_task",
        "owner_thread",
        "owner_run",
        "workload_class",
        "phase",
        "started_at",
    }
    v2_fields = v1_fields | {
        "ttl_seconds",
        "renewed_at",
        "lease_expires_at",
    }
    schema = payload.get("schema")
    if (
        schema not in {
            "codex_fleet_runner_transaction.v1",
            "codex_fleet_runner_transaction.v2",
        }
        or (schema == "codex_fleet_runner_transaction.v1" and set(payload) != v1_fields)
        or (schema == "codex_fleet_runner_transaction.v2" and set(payload) != v2_fields)
    ):
        raise FleetError("runner transaction is invalid")
    validate_role(payload["role"], required=True)
    validate_lease(
        {
            "lease_id": payload["lease_id"],
            "generation": payload["generation"],
            "nonce": payload["nonce"],
            "node_id": payload["node_id"],
            "owner_task": payload["owner_task"],
            "owner_thread": payload["owner_thread"],
            "owner_run": payload["owner_run"],
            "role": payload["role"],
            "workload_class": payload["workload_class"],
            "priority": 0,
            "preemptible": payload["workload_class"] in PREEMPTIBLE_WORKLOAD_CLASSES,
            "phase": payload["phase"],
            "acquired_at": payload["started_at"],
            "expires_at": (utc_now() + dt.timedelta(seconds=60)).isoformat(),
            "control_commit": control_commit(),
            "admission": {
                "checked_at": payload["started_at"],
                "inventory_age_seconds": 0,
                "requirements": [],
                "min_memory_gb": 0,
                "power_ok": True,
                "storage_ok": True,
                "thermal_ok": True,
                "interactive_busy": False,
                "busy": False,
                "work_volume_ready": True,
            },
        }
    )
    parse_utc(payload["started_at"])
    if schema == "codex_fleet_runner_transaction.v1":
        started_at = parse_utc(payload["started_at"])
        payload = {
            **payload,
            "schema": "codex_fleet_runner_transaction.v2",
            "ttl_seconds": 3600,
            "renewed_at": payload["started_at"],
            "lease_expires_at": (
                started_at + dt.timedelta(seconds=3600)
            ).isoformat(),
        }
    else:
        validate_ttl(int(payload["ttl_seconds"]))
        parse_utc(payload["renewed_at"])
        parse_utc(payload["lease_expires_at"])
    return payload


def runner_transaction_from_lease(
    *,
    role: str,
    binding: dict[str, Any],
    lease: dict[str, Any],
    ttl_seconds: int,
) -> dict[str, Any]:
    return {
        "schema": "codex_fleet_runner_transaction.v2",
        "role": role,
        "node_id": lease["node_id"],
        "repository": binding["repository"],
        "runner_name": binding["runner_name"],
        "lease_id": lease["lease_id"],
        "generation": lease["generation"],
        "nonce": lease["nonce"],
        "owner_task": lease["owner_task"],
        "owner_thread": lease["owner_thread"],
        "owner_run": lease["owner_run"],
        "workload_class": lease["workload_class"],
        "phase": lease["phase"],
        "ttl_seconds": validate_ttl(ttl_seconds),
        "started_at": lease["acquired_at"],
        "renewed_at": lease["acquired_at"],
        "lease_expires_at": lease["expires_at"],
    }


def confirm_runner_shutdown(
    transaction: dict[str, Any],
    *,
    timeout_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    node_id = str(transaction["node_id"])
    runner_control_call(node_id, "stop", check=False)
    after = wait_runner_processes(
        node_id,
        expect_zero=True,
        timeout_seconds=timeout_seconds,
    )
    observed = wait_runner_state(
        str(transaction["repository"]),
        str(transaction["runner_name"]),
        expect_online=False,
        timeout_seconds=timeout_seconds,
    )
    if (
        after["enabled"]
        or after["online"]
        or after["processes"] != 0
        or observed["online"]
    ):
        raise FleetError(
            "runner shutdown is unconfirmed; retaining transaction and lease"
        )
    return after, observed


def fleet_runner_start(args: argparse.Namespace) -> int:
    controller_guard()
    registry = node_registry()
    binding = runner_binding(args.role, registry=registry)
    node_id = str(binding["node_id"])
    existing = read_runner_transaction(args.role)
    if existing:
        raise FleetError(f"runner transaction already active: {args.role}")
    before = runner_control_call(node_id, "status")
    if before["enabled"] or before["processes"] != 0 or before["online"]:
        raise FleetError("runner is already active; refusing to acquire a second lease")
    runner_name = str(binding["runner_name"])
    registered = github_runner_state(str(binding["repository"]), runner_name)
    if registered.get("online"):
        raise FleetError("GitHub runner is online before lease acquisition")
    doctor = doctor_result(node_id)
    required = {str(item) for item in binding["required_features"]}
    assert_lease_admission(
        doctor,
        required=required,
        min_memory_gb=int(binding["min_memory_gb"]),
    )
    admission = build_admission_receipt(
        doctor,
        required=required,
        min_memory_gb=int(binding["min_memory_gb"]),
    )
    revision = control_commit()
    assert_runner_role_workload(
        args.role,
        args.workload_class,
        registry=registry,
    )
    lease = acquire_lease_record(
        node_id=node_id,
        owner_task=args.owner_task,
        owner_thread=args.owner_thread,
        owner_run=args.owner_run,
        role=args.role,
        workload_class=args.workload_class,
        priority=args.priority,
        preemptible=args.preemptible,
        phase=args.phase,
        ttl_seconds=args.ttl_seconds,
        control_revision=revision,
        admission=admission,
        dispatch_adapter_name="github-runner",
    )
    try:
        verify_lease_record(
            lease,
            node_id=node_id,
            role=args.role,
            lease_id=lease["lease_id"],
            generation=lease["generation"],
            owner_task=args.owner_task,
            owner_thread=args.owner_thread,
            owner_run=args.owner_run,
            workload_class=args.workload_class,
            phase=args.phase,
            preemptible=args.preemptible,
            min_ttl_seconds=args.min_ttl_seconds,
            required=required,
            min_memory_gb=int(binding["min_memory_gb"]),
            max_admission_age_seconds=args.max_admission_age_seconds,
            expected_control_commit=revision,
            current_control_commit=revision,
            registry=registry,
            now=utc_now(),
            expected_dispatch_adapter="github-runner",
        )
    except Exception:
        release_lease_record(
            node_id=node_id,
            lease_id=lease["lease_id"],
            generation=lease["generation"],
            nonce=lease["nonce"],
            owner_task=args.owner_task,
        )
        raise
    transaction = runner_transaction_from_lease(
        role=args.role,
        binding=binding,
        lease=lease,
        ttl_seconds=args.ttl_seconds,
    )
    atomic_json(runner_transaction_path(args.role), transaction)
    try:
        runner_control_call(node_id, "start")
        remote = wait_runner_processes(
            node_id,
            expect_zero=False,
            timeout_seconds=args.startup_timeout_seconds,
        )
        if remote["processes"] < 1:
            raise FleetError("runner process did not start")
        observed = wait_runner_state(
            str(binding["repository"]),
            runner_name,
            expect_online=True,
            timeout_seconds=args.startup_timeout_seconds,
        )
        if not observed["online"]:
            raise FleetError("GitHub runner did not become online")
    except Exception as startup_error:
        try:
            confirm_runner_shutdown(
                transaction,
                timeout_seconds=args.startup_timeout_seconds,
            )
        except Exception as cleanup_error:
            raise FleetError(
                f"{startup_error}; cleanup failed: {cleanup_error}"
            ) from startup_error
        release_lease_record(
            node_id=node_id,
            lease_id=lease["lease_id"],
            generation=lease["generation"],
            nonce=lease["nonce"],
            owner_task=args.owner_task,
        )
        runner_transaction_path(args.role).unlink()
        raise
    print(
        json.dumps(
            {
                "schema": "codex_fleet_runner_transaction_readback.v1",
                "action": "start",
                "role": args.role,
                "node_id": node_id,
                "runner_name": runner_name,
                "lease": public_lease(lease, now=utc_now()),
                "runner": observed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_runner_stop(args: argparse.Namespace) -> int:
    controller_guard()
    transaction = read_runner_transaction(args.role)
    if not transaction:
        raise FleetError(f"runner transaction is unavailable: {args.role}")
    if args.owner_task and args.owner_task != transaction["owner_task"]:
        raise FleetError("runner transaction owner mismatch")
    node_id = str(transaction["node_id"])
    after, observed = confirm_runner_shutdown(
        transaction,
        timeout_seconds=args.shutdown_timeout_seconds,
    )
    released = release_lease_record(
        node_id=node_id,
        lease_id=str(transaction["lease_id"]),
        generation=int(transaction["generation"]),
        nonce=str(transaction["nonce"]),
        owner_task=str(transaction["owner_task"]),
    )
    runner_transaction_path(args.role).unlink()
    print(
        json.dumps(
            {
                "schema": "codex_fleet_runner_transaction_readback.v1",
                "action": "stop",
                "role": args.role,
                "node_id": node_id,
                "runner_name": transaction["runner_name"],
                "released": public_lease(released, now=utc_now()),
                "runner": observed,
                "control": after,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_runner_renew(args: argparse.Namespace) -> int:
    controller_guard()
    transaction = read_runner_transaction(args.role)
    if not transaction:
        raise FleetError(f"runner transaction is unavailable: {args.role}")
    if args.owner_task and args.owner_task != transaction["owner_task"]:
        raise FleetError("runner transaction owner mismatch")
    node_id = str(transaction["node_id"])
    control = runner_control_call(node_id, "status")
    observed = github_runner_state(
        str(transaction["repository"]),
        str(transaction["runner_name"]),
    )
    if (
        not control["enabled"]
        or control["processes"] < 1
        or not observed["online"]
    ):
        raise FleetError("runner is not active; refusing to renew its lease")
    ttl_seconds = args.ttl_seconds or int(transaction["ttl_seconds"])
    renewed = renew_lease_record(
        node_id=node_id,
        lease_id=str(transaction["lease_id"]),
        generation=int(transaction["generation"]),
        nonce=str(transaction["nonce"]),
        owner_task=str(transaction["owner_task"]),
        ttl_seconds=ttl_seconds,
        phase=str(transaction["phase"]),
    )
    renewed_at = utc_now().astimezone(dt.timezone.utc).isoformat()
    transaction = {
        **transaction,
        "schema": "codex_fleet_runner_transaction.v2",
        "generation": renewed["generation"],
        "nonce": renewed["nonce"],
        "ttl_seconds": ttl_seconds,
        "renewed_at": renewed_at,
        "lease_expires_at": renewed["expires_at"],
    }
    atomic_json(runner_transaction_path(args.role), transaction)
    print(
        json.dumps(
            {
                "schema": "codex_fleet_runner_transaction_readback.v1",
                "action": "renew",
                "role": args.role,
                "node_id": node_id,
                "runner_name": transaction["runner_name"],
                "lease": public_lease(renewed, now=utc_now()),
                "runner": observed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_runner_status(args: argparse.Namespace) -> int:
    controller_guard()
    binding = runner_binding(args.role)
    node_id = str(binding["node_id"])
    transaction = read_runner_transaction(args.role)
    print(
        json.dumps(
            {
                "schema": "codex_fleet_runner_status.v1",
                "role": args.role,
                "node_id": node_id,
                "runner_name": binding["runner_name"],
                "transaction": (
                    {
                        key: value
                        for key, value in transaction.items()
                        if key != "nonce"
                    }
                    if transaction
                    else None
                ),
                "runner": runner_control_call(node_id, "status"),
                "github": github_runner_state(
                    str(binding["repository"]),
                    str(binding["runner_name"]),
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_lease_show(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    with lease_lock(exclusive=False):
        store = read_lease_store()
    leases = store["leases"]
    if args.node_id:
        node_id = normalize_node_id(args.node_id)
        selected = [leases[node_id]] if node_id in leases else []
    else:
        selected = [leases[node_id] for node_id in sorted(leases)]
    result = {
        "schema": "codex_fleet_lease_readback.v2",
        "controller": node_identity(),
        "observed_at": observed.astimezone(dt.timezone.utc).isoformat(),
        "generation": store["generation"],
        "leases": [public_lease(lease, now=observed) for lease in selected],
        "audit": store["audit"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def fleet_lease_acquire(args: argparse.Namespace) -> int:
    controller_guard()
    required = parse_requirements(args.requires)
    registry = node_registry()
    role = (
        assert_runner_role_node(args.role, args.node_id, registry=registry)
        if args.role
        else None
    )
    if role:
        assert_runner_role_workload(
            role,
            args.workload_class,
            registry=registry,
        )
    doctor = doctor_result(args.node_id)
    assert_lease_admission(
        doctor,
        required=required,
        min_memory_gb=args.min_memory_gb,
    )
    admission = build_admission_receipt(
        doctor,
        required=required,
        min_memory_gb=args.min_memory_gb,
    )
    revision = control_commit()
    lease = acquire_lease_record(
        node_id=args.node_id,
        owner_task=args.owner_task,
        owner_thread=args.owner_thread,
        owner_run=args.owner_run,
        role=role,
        workload_class=args.workload_class,
        priority=args.priority,
        preemptible=args.preemptible,
        phase=args.phase,
        ttl_seconds=args.ttl_seconds,
        control_revision=revision,
        admission=admission,
        preempt_lease_id=args.preempt_lease_id,
        preempt_generation=args.preempt_generation,
        preempt_nonce=args.preempt_nonce,
    )
    result = {
        "schema": "codex_fleet_lease_transaction.v2",
        "action": "acquire",
        "controller": node_identity(),
        "lease": lease,
        "admission": admission,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def fleet_lease_verify(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    node_id = normalize_node_id(args.node_id)
    with lease_lock(exclusive=False):
        store = read_lease_store()
    lease = store["leases"].get(node_id)
    if not lease:
        raise FleetError(f"node has no active lease: {node_id}")
    result = verify_lease_record(
        lease,
        node_id=node_id,
        role=args.expect_role,
        lease_id=args.expect_lease_id,
        generation=args.expect_generation,
        owner_task=args.expect_owner_task,
        owner_thread=args.expect_owner_thread,
        owner_run=args.expect_owner_run,
        workload_class=args.expect_workload_class,
        phase=args.expect_phase,
        preemptible=args.expect_preemptible == "true",
        min_ttl_seconds=args.min_ttl_seconds,
        required=parse_requirements(args.expect_requires),
        min_memory_gb=args.expect_min_memory_gb,
        max_admission_age_seconds=args.max_admission_age_seconds,
        expected_control_commit=args.expect_control_commit,
        current_control_commit=control_commit(),
        registry=node_registry(),
        now=observed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def fleet_lease_renew(args: argparse.Namespace) -> int:
    controller_guard()
    lease = renew_lease_record(
        node_id=args.node_id,
        lease_id=args.lease_id,
        generation=args.generation,
        nonce=args.nonce,
        owner_task=args.owner_task,
        ttl_seconds=args.ttl_seconds,
        phase=args.phase,
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "renew",
                "controller": node_identity(),
                "lease": lease,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_lease_release(args: argparse.Namespace) -> int:
    controller_guard()
    lease = release_lease_record(
        node_id=args.node_id,
        lease_id=args.lease_id,
        generation=args.generation,
        nonce=args.nonce,
        owner_task=args.owner_task,
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "release",
                "controller": node_identity(),
                "released": public_lease(lease, now=utc_now()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def fleet_lease_reap(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    node_id = normalize_node_id(args.node_id) if args.node_id else None
    with lease_lock(exclusive=True):
        store = read_lease_store()
        reaped = reap_expired_leases(store, now=observed, node_id=node_id)
        if reaped:
            store["generation"] += 1
            write_lease_store(store)
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "reap",
                "controller": node_identity(),
                "reaped": [public_lease(lease, now=observed) for lease in reaped],
                "generation": store["generation"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance")
    subparsers = parser.add_subparsers(dest="action", required=True)
    join_parser = subparsers.add_parser("join")
    join_parser.add_argument("--node-id")
    join_parser.add_argument("--no-schedule", action="store_true")
    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--report", action="store_true")
    reconcile_parser.add_argument("--install-required", action="store_true")
    subparsers.add_parser("status")
    subparsers.add_parser("assets")
    repos_parser = subparsers.add_parser("repos")
    repos_subparsers = repos_parser.add_subparsers(
        dest="repos_action",
        required=True,
    )
    repos_subparsers.add_parser("status")
    repos_subparsers.add_parser("sync")
    nodes_parser = subparsers.add_parser("nodes")
    nodes_parser.add_argument("--json", action="store_true")
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--json", action="store_true")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("node_id")
    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--requires", default="")
    select_parser.add_argument("--min-memory-gb", type=int, default=0)
    select_parser.add_argument("--gpu-api", choices=sorted(GPU_APIS), default="any")
    select_parser.add_argument("--min-gpu-memory-gb", type=int, default=0)
    select_parser.add_argument("--gpu-model")
    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="plan or lease task execution capacity",
    )
    dispatch_subparsers = dispatch_parser.add_subparsers(
        dest="dispatch_action",
        required=True,
    )

    def add_dispatch_request_arguments(
        command: argparse.ArgumentParser,
        *,
        owner: bool,
    ) -> None:
        command.add_argument("--requirements-json")
        command.add_argument(
            "--adapter",
            choices=sorted(DISPATCH_ADAPTERS),
            default=None,
        )
        command.add_argument("--node-id")
        command.add_argument("--role")
        command.add_argument("--requires", default=None)
        command.add_argument("--min-memory-gb", type=int, default=None)
        command.add_argument("--gpu-api", choices=sorted(GPU_APIS), default=None)
        command.add_argument("--min-gpu-memory-gb", type=int, default=None)
        command.add_argument("--gpu-model", default=None)
        command.add_argument(
            "--workload-class",
            choices=sorted(LEASE_WORKLOAD_CLASSES),
            default=None,
        )
        command.add_argument("--priority", type=int, default=None)
        command.add_argument(
            "--preemptible",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        command.add_argument(
            "--phase",
            choices=sorted(LEASE_PHASES),
            default=None,
        )
        command.add_argument("--ttl-seconds", type=int, default=None)
        if owner:
            command.add_argument("--owner-task", required=True)
            command.add_argument("--owner-thread")
            command.add_argument("--owner-run")
            command.add_argument("--preempt-lease-id")
            command.add_argument("--preempt-generation", type=int)
            command.add_argument("--preempt-nonce")

    dispatch_plan_parser = dispatch_subparsers.add_parser("plan")
    add_dispatch_request_arguments(dispatch_plan_parser, owner=False)
    dispatch_acquire_parser = dispatch_subparsers.add_parser("acquire")
    add_dispatch_request_arguments(dispatch_acquire_parser, owner=True)
    dispatch_verify_parser = dispatch_subparsers.add_parser("verify")
    dispatch_verify_parser.add_argument("dispatch_id")
    dispatch_verify_parser.add_argument("--min-ttl-seconds", type=int, default=300)
    dispatch_verify_parser.add_argument(
        "--max-admission-age-seconds",
        type=int,
        default=300,
    )
    dispatch_execute_parser = dispatch_subparsers.add_parser("execute")
    dispatch_execute_parser.add_argument("dispatch_id")
    dispatch_execute_parser.add_argument("--owner-task", required=True)
    dispatch_execute_parser.add_argument("--owner-thread")
    dispatch_execute_parser.add_argument("--owner-run")
    dispatch_execute_parser.add_argument("--argv-json", required=True)
    dispatch_execute_parser.add_argument("--cwd")
    dispatch_execute_parser.add_argument("--timeout-seconds", type=int, default=900)
    dispatch_execute_parser.add_argument("--min-ttl-seconds", type=int, default=60)
    dispatch_execute_parser.add_argument(
        "--max-admission-age-seconds",
        type=int,
        default=300,
    )
    dispatch_release_parser = dispatch_subparsers.add_parser("release")
    dispatch_release_parser.add_argument("dispatch_id")
    dispatch_release_parser.add_argument("--owner-task", required=True)
    runner_parser = subparsers.add_parser("runner")
    runner_subparsers = runner_parser.add_subparsers(
        dest="runner_action",
        required=True,
    )
    runner_start = runner_subparsers.add_parser("start")
    runner_start.add_argument("role")
    runner_start.add_argument("--owner-task", required=True)
    runner_start.add_argument("--owner-thread")
    runner_start.add_argument("--owner-run")
    runner_start.add_argument(
        "--workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        default="background",
    )
    runner_start.add_argument("--priority", type=int, default=300)
    runner_start.add_argument("--preemptible", action="store_true")
    runner_start.add_argument(
        "--phase",
        choices=sorted(LEASE_PHASES),
        default="non-interruptible",
    )
    runner_start.add_argument("--ttl-seconds", type=int, default=3600)
    runner_start.add_argument("--min-ttl-seconds", type=int, default=300)
    runner_start.add_argument("--max-admission-age-seconds", type=int, default=300)
    runner_start.add_argument("--startup-timeout-seconds", type=int, default=60)
    runner_stop = runner_subparsers.add_parser("stop")
    runner_stop.add_argument("role")
    runner_stop.add_argument("--owner-task")
    runner_stop.add_argument("--shutdown-timeout-seconds", type=int, default=60)
    runner_renew = runner_subparsers.add_parser("renew")
    runner_renew.add_argument("role")
    runner_renew.add_argument("--owner-task")
    runner_renew.add_argument("--ttl-seconds", type=int)
    runner_status = runner_subparsers.add_parser("status")
    runner_status.add_argument("role")
    lease_parser = subparsers.add_parser("lease")
    lease_subparsers = lease_parser.add_subparsers(
        dest="lease_action",
        required=True,
    )
    lease_show = lease_subparsers.add_parser("show")
    lease_show.add_argument("node_id", nargs="?")
    lease_verify = lease_subparsers.add_parser("verify")
    lease_verify.add_argument("node_id")
    lease_verify.add_argument("--expect-role", required=True)
    lease_verify.add_argument("--expect-lease-id", required=True)
    lease_verify.add_argument("--expect-generation", type=int, required=True)
    lease_verify.add_argument("--expect-owner-task", required=True)
    lease_verify.add_argument("--expect-owner-thread")
    lease_verify.add_argument("--expect-owner-run")
    lease_verify.add_argument(
        "--expect-workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        required=True,
    )
    lease_verify.add_argument(
        "--expect-phase",
        choices=sorted(LEASE_PHASES),
        required=True,
    )
    lease_verify.add_argument(
        "--expect-preemptible",
        choices=("true", "false"),
        required=True,
    )
    lease_verify.add_argument("--min-ttl-seconds", type=int, required=True)
    lease_verify.add_argument("--expect-requires", required=True)
    lease_verify.add_argument("--expect-min-memory-gb", type=int, required=True)
    lease_verify.add_argument("--max-admission-age-seconds", type=int, default=300)
    lease_verify.add_argument("--expect-control-commit", required=True)
    lease_acquire = lease_subparsers.add_parser("acquire")
    lease_acquire.add_argument("node_id")
    lease_acquire.add_argument("--owner-task", required=True)
    lease_acquire.add_argument("--owner-thread")
    lease_acquire.add_argument("--owner-run")
    lease_acquire.add_argument("--role")
    lease_acquire.add_argument(
        "--workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        required=True,
    )
    lease_acquire.add_argument("--priority", type=int, required=True)
    lease_acquire.add_argument("--preemptible", action="store_true")
    lease_acquire.add_argument("--phase", choices=sorted(LEASE_PHASES), default="interruptible")
    lease_acquire.add_argument("--ttl-seconds", type=int, default=3600)
    lease_acquire.add_argument("--requires", default="")
    lease_acquire.add_argument("--min-memory-gb", type=int, default=0)
    lease_acquire.add_argument("--preempt-lease-id")
    lease_acquire.add_argument("--preempt-generation", type=int)
    lease_acquire.add_argument("--preempt-nonce")
    lease_renew = lease_subparsers.add_parser("renew")
    lease_renew.add_argument("node_id")
    lease_renew.add_argument("--lease-id", required=True)
    lease_renew.add_argument("--generation", type=int, required=True)
    lease_renew.add_argument("--nonce", required=True)
    lease_renew.add_argument("--owner-task", required=True)
    lease_renew.add_argument("--ttl-seconds", type=int, default=3600)
    lease_renew.add_argument("--phase", choices=sorted(LEASE_PHASES))
    lease_release = lease_subparsers.add_parser("release")
    lease_release.add_argument("node_id")
    lease_release.add_argument("--lease-id", required=True)
    lease_release.add_argument("--generation", type=int, required=True)
    lease_release.add_argument("--nonce", required=True)
    lease_release.add_argument("--owner-task", required=True)
    lease_reap = lease_subparsers.add_parser("reap")
    lease_reap.add_argument("node_id", nargs="?")
    record_parser = subparsers.add_parser("record", help=argparse.SUPPRESS)
    record_parser.add_argument("--state-root", type=Path, required=True)
    record_parser.add_argument("--payload-b64", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    local_dispatch = (
        args.action == "dispatch"
        and args.dispatch_action in {"plan", "acquire"}
        and dispatch_adapter_from_args(args) == "local-codex"
    )
    instance = None if local_dispatch else configure_instance(args.instance)
    if args.action in {"join", "reconcile"}:
        write_instance_pointer(instance)
        install_fleet_command()
    if args.action == "join":
        return join(args)
    if args.action == "reconcile":
        receipt = reconcile(report=args.report, install_required=args.install_required)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["state"] == "CURRENT" else 1
    if args.action == "status":
        return fleet_status()
    if args.action == "assets":
        return fleet_assets()
    if args.action == "repos":
        return fleet_repositories(sync=args.repos_action == "sync")
    if args.action == "nodes":
        return fleet_nodes(json_output=args.json)
    if args.action == "inventory":
        inventory = collect_inventory(node_identity(), manifest(), node_registry())
        print(json.dumps(inventory, indent=2, sort_keys=True))
        return 0
    if args.action == "doctor":
        return fleet_doctor(args.node_id)
    if args.action == "select":
        return fleet_select(args)
    if args.action == "dispatch":
        if args.dispatch_action == "plan":
            return fleet_dispatch_plan(args)
        if args.dispatch_action == "acquire":
            return fleet_dispatch_acquire(args)
        if args.dispatch_action == "verify":
            return fleet_dispatch_verify(args)
        if args.dispatch_action == "execute":
            return fleet_dispatch_execute(args)
        return fleet_dispatch_release(args)
    if args.action == "runner":
        if args.runner_action == "start":
            return fleet_runner_start(args)
        if args.runner_action == "stop":
            return fleet_runner_stop(args)
        if args.runner_action == "renew":
            return fleet_runner_renew(args)
        return fleet_runner_status(args)
    if args.action == "lease":
        if args.lease_action == "show":
            return fleet_lease_show(args)
        if args.lease_action == "verify":
            return fleet_lease_verify(args)
        if args.lease_action == "acquire":
            return fleet_lease_acquire(args)
        if args.lease_action == "renew":
            return fleet_lease_renew(args)
        if args.lease_action == "release":
            return fleet_lease_release(args)
        return fleet_lease_reap(args)
    destination = record_receipt(args.state_root, args.payload_b64)
    print(destination)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"opl-fleet failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
