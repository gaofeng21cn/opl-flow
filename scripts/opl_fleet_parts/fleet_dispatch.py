"""Dispatch planning, execution requirements, SSH execution, and dispatch CLI commands."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import json
import re
import shlex
import subprocess
import uuid
from .fleet_common import EXECUTION_REQUIREMENTS_SCHEMA, FleetError, GPU_APIS, LEASE_PHASES, LEASE_WORKLOAD_CLASSES, MAX_EXECUTION_OUTPUT_BYTES, MAX_EXECUTION_REQUIREMENTS_BYTES, PREEMPTIBLE_WORKLOAD_CLASSES, REMOTE_EXECUTION_TIMEOUT_SECONDS, REMOTE_EXECUTOR, dispatch_adapter, normalize_node_id, parse_requirements, parse_utc, run, utc_now
from .fleet_reconcile import control_commit, manifest, node_registry, remote_asset_catalog
from .fleet_lease import acquire_lease_record, active_lease_map, lease_lock, public_lease, read_lease_store, release_lease_record, select_nodes, validate_owner_id, validate_role, validate_ttl
from .fleet_runner import assert_lease_admission, assert_runner_role_node, assert_runner_role_workload, build_admission_receipt, controller_guard, doctor_result, read_routes, runner_role_nodes, verify_lease_record

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
