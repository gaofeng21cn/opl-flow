"""Runner admission, doctor diagnostics, routes/work-volume probes, runner transactions, and runner CLI commands."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import datetime as dt
import json
import plistlib
import re
import shlex
import shutil
import time
import uuid
from fleet_inventory import collect_inventory, validate_inventory
from .fleet_common import COMMIT_PATTERN, FleetError, GPU_APIS, LEASE_PHASES, LEASE_WORKLOAD_CLASSES, PREEMPTIBLE_WORKLOAD_CLASSES, ROUTES_PATH, STATE_ROOT, atomic_json, dispatch_adapter, node_identity, normalize_node_id, parse_utc, read_json, run, utc_now
from .fleet_features import gpu_profiles, inventory_age_seconds, node_features
from .fleet_reconcile import control_commit, manifest, node_registry, remote_asset_catalog
from .fleet_lease import acquire_lease_record, active_lease_map, public_lease, release_lease_record, renew_lease_record, validate_admission, validate_lease, validate_owner_id, validate_role, validate_ttl

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
    tailnet_online = tailscale_online(route.get("tailscale_host"))
    ssh_reachable: bool | None = True if local else None
    ssh_probe_attempts = 0
    ssh_transient_failure = False
    if ssh_alias:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", str(ssh_alias)):
            raise FleetError("SSH route alias is invalid")
        probe_timeouts = (6, 15) if tailnet_online is True else (6,)
        for timeout_seconds in probe_timeouts:
            ssh_probe_attempts += 1
            probe = run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    f"ConnectTimeout={timeout_seconds}",
                    str(ssh_alias),
                    "true",
                ],
                check=False,
            )
            ssh_reachable = probe.returncode == 0
            if ssh_reachable:
                ssh_transient_failure = ssh_probe_attempts > 1
                break
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
    receipt_control_commit = (entry.get("receipt") or {}).get("control_commit")
    current_control_commit = control_commit()
    control_current = bool(
        isinstance(receipt_control_commit, str)
        and COMMIT_PATTERN.fullmatch(receipt_control_commit)
        and receipt_control_commit == current_control_commit
    )
    if local or ssh_reachable is True:
        availability = "online"
    elif ssh_reachable is False:
        availability = (
            "transport_degraded"
            if tailnet_online is True
            else "offline_expected"
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
        and control_current
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
        "local": local,
        "receipt_state": (entry.get("receipt") or {}).get("state", "NO_RECEIPT"),
        "receipt_control_commit": receipt_control_commit,
        "current_control_commit": current_control_commit,
        "control_current": control_current,
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
            "probe_attempts": ssh_probe_attempts,
            "transient_failure": ssh_transient_failure,
        },
        "tailscale": {
            "configured": bool(route.get("tailscale_host")),
            "online": tailnet_online,
        },
        "work_volume": volume,
    }
    return result

def data_job_admission(
    node_id: str,
    *,
    catalog: dict[str, Any] | None = None,
    routes: dict[str, Any] | None = None,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    doctor = doctor_result(
        node_id,
        catalog=catalog,
        routes=routes,
        state_root=state_root,
        now=now,
    )
    route_ready = doctor["ssh"]["reachable"] is True
    python_ready = "python" in doctor["features"]
    failures: list[str] = []
    if not doctor["approved"]:
        failures.append("not_approved")
    if doctor["receipt_state"] != "CURRENT":
        failures.append("node_not_current")
    if not doctor["inventory_fresh"]:
        failures.append("inventory_not_fresh")
    if not python_ready:
        failures.append("python_not_ready")
    if not route_ready:
        failures.append("data_route_unavailable")
    return {
        "schema": "opl_fleet_data_job_admission.v1",
        "node_id": doctor["node_id"],
        "checked_at": doctor["checked_at"],
        "ready": not failures,
        "failures": failures,
        "approved": doctor["approved"],
        "receipt_state": doctor["receipt_state"],
        "inventory_fresh": doctor["inventory_fresh"],
        "python_ready": python_ready,
        "availability": doctor["availability"],
        "local": doctor.get("local") is True,
        "route_ready": route_ready,
        "ssh": doctor["ssh"],
        "tailscale": doctor["tailscale"],
        "scheduling_observed": doctor["scheduling"],
    }

def controller_guard() -> str:
    controller = node_identity()
    policy = node_registry()["nodes"].get(controller) or {}
    route = read_routes()["routes"].get(controller) or {}
    if "controller" not in policy.get("labels", []) or route.get("local") is not True:
        raise FleetError("lease commands must run on the configured Fleet controller")
    return controller

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
