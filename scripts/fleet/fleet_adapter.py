"""Unified single-transaction dispatch, context restoration, and fan-out/fan-in group orchestration."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from typing import Any

from . import fleet_common
from .fleet_attempts import finish_attempt, get_attempt, record_attempt_start
from .fleet_common import FleetError, atomic_json, parse_utc, read_json, utc_now
from .fleet_control import control_commit, node_registry
from .fleet_dispatch import (
    dispatch_candidates,
    execute_ssh_session,
    read_execution_requirements,
    validate_execution_argv,
)
from .fleet_lease import acquire_lease_record, public_lease, read_lease_store, release_lease_record
from .fleet_queue import plan_queue
from .fleet_reconcile import remote_asset_catalog
from .fleet_runner import (
    assert_lease_admission,
    assert_runner_role_node,
    assert_runner_role_workload,
    build_admission_receipt,
    controller_guard,
    doctor_result,
    verify_lease_record,
)

try:
    from .. import opl_events, opl_execution
except ImportError:  # Direct script execution.
    import opl_events, opl_execution


CONTEXT_SCHEMA = "opl_context_restoration.v1"
LAUNCH_ENVELOPE_SCHEMA = "opl_codex_launch_envelope.v1"
GROUP_RECEIPT_SCHEMA = "opl_fleet_group_receipt.v1"


def _resolve_state_root(state_root: Path | None) -> Path:
    return state_root or fleet_common.STATE_ROOT


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _safe_under_root(root: Path, rel_path: str) -> Path:
    clean = opl_execution.validate_relative_path(rel_path, "context_ref_path")
    resolved_root = root.expanduser().resolve()
    target = (resolved_root / clean).resolve()
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise FleetError(f"context reference escapes workspace_root: {rel_path}") from exc
    return target


def restore_handoff_context(
    handoff: dict[str, Any],
    *,
    workspace_root: Path | None = None,
    runtime_dir: Path | None = None,
    verify_git: bool = False,
) -> dict[str, Any]:
    """Validate and restore bounded context/artifact references without touching Git history."""
    try:
        validated = opl_execution.validate_handoff(handoff)
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc

    verified_refs: list[dict[str, Any]] = []
    all_refs = [
        *[("input", ref) for ref in validated["input_refs"]],
        *[("checkpoint", ref) for ref in validated["checkpoint_refs"]],
    ]

    for kind, ref in all_refs:
        if ref.startswith("file:"):
            body = ref[len("file:") :]
            expected_digest: str | None = None
            if "#sha256=" in body:
                rel_part, expected_digest = body.split("#sha256=", 1)
                if len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest):
                    raise FleetError(f"invalid sha256 digest in context reference: {ref}")
            else:
                rel_part = body
            try:
                clean_rel = opl_execution.validate_relative_path(rel_part, "file_ref")
            except opl_execution.ExecutionError as exc:
                raise FleetError(str(exc)) from exc
            entry: dict[str, Any] = {"kind": kind, "ref": ref, "type": "file", "path": clean_rel, "verified": False}
            if workspace_root is not None:
                target = _safe_under_root(workspace_root, clean_rel)
                if not target.is_file():
                    raise FleetError(f"referenced context file is missing: {clean_rel}")
                actual_digest = _sha256_file(target)
                if expected_digest is not None and actual_digest != expected_digest:
                    raise FleetError(f"artifact digest mismatch for {clean_rel}")
                entry["sha256"] = actual_digest
                entry["verified"] = True
            verified_refs.append(entry)
        elif ref.startswith("worktree:"):
            rel_part = ref[len("worktree:") :]
            try:
                clean_rel = opl_execution.validate_relative_path(rel_part, "worktree_ref")
            except opl_execution.ExecutionError as exc:
                raise FleetError(str(exc)) from exc
            verified_refs.append({"kind": kind, "ref": ref, "type": "worktree", "path": clean_rel, "verified": workspace_root is None or _safe_under_root(workspace_root, clean_rel).exists()})
        elif ref.startswith("git:"):
            entry = {"kind": kind, "ref": ref, "type": "git", "verified": not verify_git}
            if verify_git and workspace_root is not None and "@" in ref:
                rev = ref.rsplit("@", 1)[1]
                res = subprocess.run(
                    ["git", "rev-parse", "--verify", f"{rev}^{{commit}}"],
                    cwd=workspace_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode != 0:
                    raise FleetError(f"referenced git commit is missing in workspace: {rev}")
                entry["verified"] = True
            verified_refs.append(entry)
        else:
            verified_refs.append({"kind": kind, "ref": ref, "type": "opaque", "verified": True})

    manifest_path: Path | None = None
    if runtime_dir is not None:
        r_dir = runtime_dir.expanduser().resolve()
        if workspace_root is not None:
            git_dir = (workspace_root.expanduser().resolve() / ".git").resolve()
            try:
                r_dir.relative_to(git_dir)
                raise FleetError("runtime_dir must not be inside .git")
            except ValueError:
                pass
        r_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = r_dir / ".opl-handoff-context.json"
        manifest = {
            "schema": "opl_handoff_context_manifest.v1",
            "binding": opl_execution.handoff_binding(validated),
            "objective_revision": validated.get("objective_revision"),
            "scope": validated["scope"],
            "expected_result": validated["expected_result"],
            "write_set": validated.get("write_set", []),
            "verified_refs": verified_refs,
            "envelope": validated.get("envelope"),
            "resumability": validated.get("resumability"),
        }
        atomic_json(manifest_path, manifest)

    return {
        "schema": CONTEXT_SCHEMA,
        "restored": True,
        "verified_refs": verified_refs,
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
    }


def _emit_worker_callback(
    callback_state_dir: Path | None,
    *,
    attempt_id: str,
    objective_id: str,
    outcome: str,
    worker_result: dict[str, Any] | None = None,
    blocker_code: str | None = None,
) -> dict[str, Any] | None:
    if callback_state_dir is None:
        return None
    payload: dict[str, Any] = {
        "signal": "adapter_worker_callback",
        "attempt_id": attempt_id,
        "outcome": outcome,
    }
    if worker_result is not None:
        payload["artifact_refs"] = worker_result.get("artifact_refs", [])
        payload["checkpoint_refs"] = worker_result.get("checkpoint_refs", [])
        payload["remaining"] = worker_result.get("remaining", [])
        payload["next_action"] = worker_result.get("next_action")
        if "budget_usage" in worker_result:
            payload["budget_usage"] = worker_result["budget_usage"]
    if blocker_code:
        payload["blocker_code"] = blocker_code
    try:
        return opl_events.emit_event(
            callback_state_dir,
            event_type="worker_callback",
            objective_id=objective_id,
            attempt_id=attempt_id,
            source="fleet:adapter",
            idempotency_key=f"callback:{attempt_id}:{outcome}",
            payload=payload,
        )
    except opl_events.EventControlError as exc:
        raise FleetError(str(exc)) from exc


def _acquire_remote_lease(
    *,
    request: dict[str, Any],
    owner_task: str,
    owner_thread: str | None,
    owner_run: str | None,
    binding: dict[str, str],
    preempt_lease_id: str | None = None,
    preempt_generation: int | None = None,
    preempt_nonce: str | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    controller_guard()
    adapter = str(request["adapter"])
    catalog = remote_asset_catalog() if adapter == "remote-codex" else None
    candidates = dispatch_candidates(request, catalog=catalog)
    if not candidates:
        raise FleetError("no dispatch candidate is available")
    registry = node_registry()
    required = set(request["requires"])
    selected_node: str | None = None
    selected_role: str | None = None
    selected_admission: dict[str, Any] | None = None
    rejected: list[str] = []

    for candidate in candidates:
        candidate_id = str(candidate["node_id"])
        try:
            candidate_role = request.get("role")
            if candidate_role:
                candidate_role = assert_runner_role_node(str(candidate_role), candidate_id, registry=registry)
                assert_runner_role_workload(candidate_role, str(request["workload_class"]), registry=registry)
            doctor = doctor_result(candidate_id, catalog=catalog) if catalog is not None else doctor_result(candidate_id)
            admission_view = doctor
            if adapter == "remote-codex":
                remote_control = candidate.get("remote_control") or {}
                if remote_control.get("startup_configured") is not True or remote_control.get("running") is not True:
                    raise FleetError("remote Codex is not ready")
                admission_view = {
                    **doctor,
                    "admission_ready": True,
                    "ssh": {"reachable": True},
                    "tailscale": {"online": True},
                }
            assert_lease_admission(
                admission_view,
                required=required,
                min_memory_gb=int(request["min_memory_gb"]),
                gpu_api=str(request["gpu_api"]),
                min_gpu_memory_gb=int(request["min_gpu_memory_gb"]),
                gpu_model=request["gpu_model"],
            )
            selected_admission = build_admission_receipt(
                admission_view,
                required=required,
                min_memory_gb=int(request["min_memory_gb"]),
                gpu_api=str(request["gpu_api"]),
                min_gpu_memory_gb=int(request["min_gpu_memory_gb"]),
                gpu_model=request["gpu_model"],
            )
            selected_node = candidate_id
            selected_role = candidate_role
            break
        except FleetError as exc:
            rejected.append(f"{candidate_id}:{str(exc)[:120]}")

    if selected_node is None or selected_admission is None:
        detail = ";".join(rejected) or "no-fresh-admission"
        raise FleetError(f"no dispatch candidate passed fresh doctor: {detail}")

    return acquire_lease_record(
        node_id=selected_node,
        owner_task=owner_task,
        owner_thread=owner_thread,
        owner_run=owner_run,
        role=selected_role,
        workload_class=str(request["workload_class"]),
        priority=int(request["priority"]),
        preemptible=bool(request["preemptible"]),
        phase=str(request["phase"]),
        ttl_seconds=int(request["ttl_seconds"]),
        control_revision=control_commit(),
        admission=selected_admission,
        preempt_lease_id=preempt_lease_id,
        preempt_generation=preempt_generation,
        preempt_nonce=preempt_nonce,
        dispatch_adapter_name=adapter,
        worker_binding=binding,
        state_root=_resolve_state_root(state_root),
    )


def _local_bridge_command(
    adapter_name: str,
    *,
    use_codex_bridge: bool,
    use_antigravity_bridge: bool,
    use_dsh_bridge: bool = False,
    codex_bin: str | None,
    agy_bin: str | None,
    dsh_control: str | None = None,
    dsh_combination: str | None = None,
    model: str | None,
    effort: str | None,
    sandbox: str | None,
    use_worktree: bool,
    workspace_root: Path | None,
) -> list[str] | None:
    if adapter_name == "local-codex" and use_codex_bridge:
        bridge_path = fleet_common.FLOW_ROOT / "scripts" / "opl_codex_bridge.py"
        return [
            sys.executable,
            str(bridge_path),
            "worker",
            *(["--codex-bin", codex_bin] if codex_bin else []),
            *(["--model", model] if model else []),
            *(["--sandbox", sandbox] if sandbox else []),
            *(["--worktree"] if use_worktree else []),
            *(["--cwd", str(workspace_root)] if workspace_root else []),
        ]
    if adapter_name == "local-antigravity" and use_antigravity_bridge:
        bridge_path = fleet_common.FLOW_ROOT / "scripts" / "opl_antigravity_bridge.py"
        return [
            sys.executable,
            str(bridge_path),
            "worker",
            *(["--agy-bin", agy_bin] if agy_bin else []),
            *(["--model", model] if model else []),
            *(["--effort", effort] if effort else []),
            *(["--sandbox", sandbox] if sandbox else []),
            *(["--worktree"] if use_worktree else []),
            *(["--cwd", str(workspace_root)] if workspace_root else []),
        ]
    if adapter_name == "local-dsh" and use_dsh_bridge:
        bridge_path = fleet_common.FLOW_ROOT / "scripts" / "opl_dsh_bridge.py"
        return [
            sys.executable,
            str(bridge_path),
            "worker",
            *(["--dsh-control", dsh_control] if dsh_control else []),
            *(["--combination", dsh_combination] if dsh_combination else []),
            *(["--model", model] if model else []),
            *(["--sandbox", sandbox] if sandbox else []),
            *(["--cwd", str(workspace_root)] if workspace_root else []),
        ]
    return None


def dispatch_run(
    *,
    handoff: dict[str, Any],
    requirements: dict[str, Any] | None = None,
    adapter: str | None = None,
    node_id: str | None = None,
    role: str | None = None,
    owner_task: str,
    owner_thread: str | None = None,
    owner_run: str | None = None,
    argv: list[str] | None = None,
    executor_cmd: list[str] | None = None,
    mode: str = "execute",
    cwd: str | None = None,
    timeout_seconds: int = 900,
    workspace_root: Path | None = None,
    runtime_dir: Path | None = None,
    callback_state_dir: Path | None = None,
    group_id: str | None = None,
    verify_git: bool = False,
    requested_tools: list[str] | None = None,
    requires_network: bool = False,
    destructive: bool = False,
    preempt_lease_id: str | None = None,
    preempt_generation: int | None = None,
    preempt_nonce: str | None = None,
    use_codex_bridge: bool = False,
    use_antigravity_bridge: bool = False,
    use_dsh_bridge: bool = False,
    codex_bin: str | None = None,
    agy_bin: str | None = None,
    dsh_control: str | None = None,
    dsh_combination: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    use_worktree: bool = False,
    sandbox: str | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Unified single-transaction dispatch across local-codex, local-antigravity, local-dsh, ssh-session, remote-codex, and lease-only."""
    if mode not in {"execute", "envelope"}:
        raise FleetError(f"unsupported dispatch run mode: {mode!r}")

    try:
        validated_handoff = opl_execution.validate_handoff(handoff)
        binding = opl_execution.handoff_binding(validated_handoff)
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc

    if owner_task != validated_handoff["objective_id"]:
        raise FleetError("dispatch owner task does not match worker handoff")

    reqs = read_execution_requirements(json.dumps(requirements) if requirements is not None else None)
    effective_adapter = str(adapter or reqs["adapter"])
    if effective_adapter not in {"local-codex", "local-antigravity", "local-dsh", "ssh-session", "remote-codex", "lease-only"}:
        raise FleetError(f"adapter {effective_adapter} does not support dispatch run")
    if effective_adapter in fleet_common.LOCAL_DISPATCH_ADAPTERS and node_id:
        raise FleetError(f"{effective_adapter} does not accept a Fleet node")

    # Stage 4 Pre-Execution Envelope Gate — MUST fail closed BEFORE acquiring lease or calling transport!
    try:
        envelope_summary = opl_execution.enforce_pre_execution_envelope(
            validated_handoff,
            ttl_seconds=int(reqs["ttl_seconds"]),
            requested_tools=requested_tools,
            requires_network=requires_network,
            destructive=destructive,
        )
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc

    envelope = validated_handoff.get("envelope") or {}
    effective_timeout = int(timeout_seconds)
    if "max_duration_seconds" in envelope:
        effective_timeout = min(effective_timeout, int(envelope["max_duration_seconds"]))

    resolved_root = _resolve_state_root(state_root)
    request_payload = {
        "adapter": effective_adapter,
        "requires": reqs["requires"],
        "min_memory_gb": reqs["min_memory_gb"],
        "gpu_api": reqs["gpu_api"],
        "min_gpu_memory_gb": reqs["min_gpu_memory_gb"],
        "gpu_model": reqs["gpu_model"],
        "workload_class": reqs["workload_class"],
        "priority": reqs["priority"],
        "preemptible": reqs["preemptible"],
        "phase": reqs["phase"],
        "ttl_seconds": reqs["ttl_seconds"],
        "role": role,
        "node_id": node_id,
    }

    lease: dict[str, Any] | None = None
    if effective_adapter not in fleet_common.LOCAL_DISPATCH_ADAPTERS:
        lease = _acquire_remote_lease(
            request=request_payload,
            owner_task=owner_task,
            owner_thread=owner_thread,
            owner_run=owner_run,
            binding=binding,
            preempt_lease_id=preempt_lease_id,
            preempt_generation=preempt_generation,
            preempt_nonce=preempt_nonce,
            state_root=resolved_root,
        )
        selected_node = str(lease["node_id"])
    else:
        selected_node = "local"

    attempt_id = validated_handoff["attempt_id"]
    is_async_envelope = mode == "envelope" or effective_adapter in {"remote-codex", "lease-only"}
    record_attempt_start(
        attempt_id=attempt_id,
        objective_id=owner_task,
        owner_id=validated_handoff["owner_id"],
        adapter=effective_adapter,
        node_id=selected_node,
        handoff_binding=binding,
        resumability=validated_handoff.get("resumability"),
        envelope_summary=envelope_summary,
        lease_id=lease["lease_id"] if lease else None,
        lease_generation=int(lease["generation"]) if lease else None,
        lease_nonce=lease["nonce"] if lease else None,
        group_id=group_id,
        initial_state="admitted" if is_async_envelope else "running",
        phase="admitted" if is_async_envelope else "executing",
        state_root=resolved_root,
    )

    try:
        restoration = restore_handoff_context(
            validated_handoff,
            workspace_root=workspace_root,
            runtime_dir=runtime_dir,
            verify_git=verify_git,
        )
    except Exception as exc:
        finish_attempt(
            attempt_id,
            outcome="blocked",
            result_class="blocked",
            blocker_code="context_restoration_failed",
            state_root=resolved_root,
        )
        if lease is not None:
            release_lease_record(
                node_id=lease["node_id"],
                lease_id=lease["lease_id"],
                generation=int(lease["generation"]),
                nonce=lease["nonce"],
                owner_task=owner_task,
                state_root=resolved_root,
            )
        if isinstance(exc, FleetError):
            raise
        raise FleetError(str(exc)) from exc

    # Asynchronous / App-owned Codex / lease-only launch envelope
    if is_async_envelope:
        if lease is not None:
            verify_lease_record(
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
                min_ttl_seconds=min(60, int(reqs["ttl_seconds"])),
                required=set(lease["admission"]["requirements"]),
                min_memory_gb=int(lease["admission"]["min_memory_gb"]),
                gpu_api=str(lease["admission"]["gpu_api"]),
                min_gpu_memory_gb=int(lease["admission"]["min_gpu_memory_gb"]),
                gpu_model=lease["admission"]["gpu_model"],
                expected_dispatch_adapter=effective_adapter,
                max_admission_age_seconds=300,
                expected_control_commit=lease["control_commit"],
                current_control_commit=control_commit(),
                registry=node_registry(),
                now=utc_now(),
            )
        complete_cmd = [
            "python3",
            "scripts/opl_fleet.py",
            "dispatch",
            "complete",
            "--attempt-id",
            attempt_id,
            *(["--dispatch-id", lease["lease_id"]] if lease else []),
        ]
        return {
            "schema": LAUNCH_ENVELOPE_SCHEMA,
            "action": "run",
            "status": "awaiting_completion",
            "attempt_id": attempt_id,
            "adapter": effective_adapter,
            "node_id": selected_node,
            "dispatch_id": lease["lease_id"] if lease else None,
            "lease": public_lease(lease, now=utc_now()) if lease else None,
            "lease_held": lease is not None,
            "worker_binding": binding,
            "envelope_summary": envelope_summary,
            "context_restoration": restoration,
            "complete_command": complete_cmd,
        }

    # Synchronous local-codex or ssh-session execution
    outcome = "unknown"
    worker_result: dict[str, Any] | None = None
    budget_evaluation: dict[str, Any] | None = None

    if effective_adapter in fleet_common.LOCAL_DISPATCH_ADAPTERS:
        effective_cmd = list(executor_cmd) if executor_cmd else _local_bridge_command(
            effective_adapter,
            use_codex_bridge=use_codex_bridge,
            use_antigravity_bridge=use_antigravity_bridge,
            use_dsh_bridge=use_dsh_bridge,
            codex_bin=codex_bin,
            agy_bin=agy_bin,
            dsh_control=dsh_control,
            dsh_combination=dsh_combination,
            model=model,
            effort=effort,
            sandbox=sandbox,
            use_worktree=use_worktree,
            workspace_root=workspace_root,
        )
        if not effective_cmd:
            bridge_flag = {
                "local-antigravity": "--use-antigravity-bridge",
                "local-dsh": "--use-dsh-bridge",
            }.get(effective_adapter, "--use-codex-bridge")
            raise FleetError(f"{effective_adapter} execute mode requires executor_cmd or {bridge_flag} or --mode envelope")
        with tempfile.TemporaryDirectory(prefix="opl-local-run-") as tmp:
            handoff_file = Path(tmp) / "handoff.json"
            handoff_file.write_text(json.dumps(validated_handoff, ensure_ascii=False), encoding="utf-8")
            env = os.environ.copy()
            env["OPL_HANDOFF_PATH"] = str(handoff_file)
            env["OPL_ATTEMPT_ID"] = attempt_id
            env["OPL_OBJECTIVE_ID"] = owner_task
            if restoration.get("manifest_path"):
                env["OPL_CONTEXT_MANIFEST"] = str(restoration["manifest_path"])
            try:
                proc = subprocess.run(
                    effective_cmd,
                    cwd=workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                    env=env,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    parsed = json.loads(proc.stdout)
                    worker_result = opl_execution.validate_result(parsed, validated_handoff)
                    outcome = worker_result["outcome"]
                    budget_evaluation = opl_execution.evaluate_budget_usage(validated_handoff, worker_result)
                elif proc.returncode != 0 and proc.stdout.strip():
                    try:
                        parsed = json.loads(proc.stdout)
                        worker_result = opl_execution.validate_result(parsed, validated_handoff)
                        outcome = worker_result["outcome"]
                        budget_evaluation = opl_execution.evaluate_budget_usage(validated_handoff, worker_result)
                    except (json.JSONDecodeError, opl_execution.ExecutionError):
                        outcome = "unknown"
                else:
                    outcome = "unknown"
            except (subprocess.TimeoutExpired, json.JSONDecodeError, opl_execution.ExecutionError, OSError):
                outcome = "unknown"
    elif effective_adapter == "ssh-session":
        assert lease is not None
        if not argv:
            release_lease_record(
                node_id=lease["node_id"],
                lease_id=lease["lease_id"],
                generation=int(lease["generation"]),
                nonce=lease["nonce"],
                owner_task=owner_task,
                state_root=resolved_root,
            )
            raise FleetError("ssh-session execute requires --argv-json")
        minimum_ttl = max(60, effective_timeout + 30)
        verify_lease_record(
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
            required=set(lease["admission"]["requirements"]),
            min_memory_gb=int(lease["admission"]["min_memory_gb"]),
            gpu_api=str(lease["admission"]["gpu_api"]),
            min_gpu_memory_gb=int(lease["admission"]["min_gpu_memory_gb"]),
            gpu_model=lease["admission"]["gpu_model"],
            expected_dispatch_adapter="ssh-session",
            max_admission_age_seconds=300,
            expected_control_commit=lease["control_commit"],
            current_control_commit=control_commit(),
            registry=node_registry(),
            now=utc_now(),
        )
        execution = execute_ssh_session(
            lease["node_id"],
            argv=argv,
            cwd=cwd,
            timeout_seconds=effective_timeout,
        )
        if execution.get("known"):
            ssh_res = execution["result"]
            if ssh_res["exit_code"] == 0 and not ssh_res["timed_out"]:
                outcome = "completed"
                candidate_result = {
                    "schema": "opl_worker_result.v1",
                    "binding": binding,
                    "outcome": "completed",
                    "artifact_refs": [f"dispatch:{lease['lease_id']}#exit=0"],
                    "checkpoint_refs": [],
                    "remaining": [],
                    "next_action": "Owner verifies remote slice evidence",
                }
            else:
                outcome = "blocked"
                candidate_result = {
                    "schema": "opl_worker_result.v1",
                    "binding": binding,
                    "outcome": "blocked",
                    "artifact_refs": [],
                    "checkpoint_refs": [],
                    "remaining": [validated_handoff["scope"]],
                    "next_action": "Repair remote ssh-session failure before retry",
                }
            worker_result = opl_execution.validate_result(candidate_result, validated_handoff)
            budget_evaluation = opl_execution.evaluate_budget_usage(validated_handoff, worker_result)
        else:
            outcome = "unknown"

    if outcome == "unknown":
        finish_attempt(
            attempt_id,
            outcome="unknown",
            result_class="unknown",
            blocker_code="transport_or_result_unknown",
            state_root=resolved_root,
        )
        callback_receipt = _emit_worker_callback(
            callback_state_dir,
            attempt_id=attempt_id,
            objective_id=owner_task,
            outcome="unknown",
            blocker_code="transport_or_result_unknown",
        )
        return {
            "schema": "codex_fleet_dispatch_readback.v1",
            "action": "run",
            "status": "unknown",
            "attempt_id": attempt_id,
            "adapter": effective_adapter,
            "node_id": selected_node,
            "dispatch_id": lease["lease_id"] if lease else None,
            "worker_binding": binding,
            "envelope_summary": envelope_summary,
            "context_restoration": restoration,
            "lease_retained": lease is not None,
            "lease_released": False,
            "callback": callback_receipt,
            "next_action": "reconcile the remote or local workload read-only; retain any lease before retry",
        }

    finish_attempt(
        attempt_id,
        outcome=outcome,
        result_class=outcome,
        blocker_code="execution_blocked" if outcome == "blocked" else None,
        budget_usage=(worker_result or {}).get("budget_usage"),
        checkpoint_refs=(worker_result or {}).get("checkpoint_refs"),
        state_root=resolved_root,
    )
    callback_receipt = _emit_worker_callback(
        callback_state_dir,
        attempt_id=attempt_id,
        objective_id=owner_task,
        outcome=outcome,
        worker_result=worker_result,
        blocker_code="execution_blocked" if outcome == "blocked" else None,
    )
    lease_released = False
    if lease is not None:
        release_lease_record(
            node_id=lease["node_id"],
            lease_id=lease["lease_id"],
            generation=int(lease["generation"]),
            nonce=lease["nonce"],
            owner_task=owner_task,
            state_root=resolved_root,
        )
        lease_released = True

    return {
        "schema": "codex_fleet_dispatch_readback.v1",
        "action": "run",
        "status": outcome,
        "attempt_id": attempt_id,
        "adapter": effective_adapter,
        "node_id": selected_node,
        "dispatch_id": lease["lease_id"] if lease else None,
        "worker_binding": binding,
        "worker_result": worker_result,
        "budget_evaluation": budget_evaluation,
        "envelope_summary": envelope_summary,
        "context_restoration": restoration,
        "lease_released": lease_released,
        "lease_retained": False,
        "callback": callback_receipt,
    }


def dispatch_complete(
    *,
    handoff: dict[str, Any],
    result: dict[str, Any],
    attempt_id: str | None = None,
    dispatch_id: str | None = None,
    callback_state_dir: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Close an async/envelope execution attempt after validating worker result and releasing capacity."""
    try:
        validated_handoff = opl_execution.validate_handoff(handoff)
        validated_result = opl_execution.validate_result(result, validated_handoff)
        budget_eval = opl_execution.evaluate_budget_usage(validated_handoff, validated_result)
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc

    resolved_root = _resolve_state_root(state_root)
    target_attempt_id = attempt_id or validated_handoff["attempt_id"]
    if target_attempt_id != validated_handoff["attempt_id"]:
        raise FleetError("attempt_id does not match handoff")

    outcome = validated_result["outcome"]
    existing_attempt = get_attempt(target_attempt_id, state_root=resolved_root)
    if existing_attempt is not None:
        finish_attempt(
            target_attempt_id,
            outcome=outcome,
            result_class=outcome,
            blocker_code="execution_blocked" if outcome == "blocked" else ("result_unknown" if outcome == "unknown" else None),
            budget_usage=validated_result.get("budget_usage"),
            checkpoint_refs=validated_result.get("checkpoint_refs"),
            state_root=resolved_root,
        )

    target_lease_id = dispatch_id or (existing_attempt.get("lease_id") if existing_attempt else None)
    lease_released = False
    lease_retained = False
    if target_lease_id:
        leases = read_lease_store(state_root=resolved_root).get("leases", {})
        matching_lease = next(
            (item for item in leases.values() if isinstance(item, dict) and item.get("lease_id") == target_lease_id),
            None,
        )
        if matching_lease is not None:
            if outcome == "unknown":
                lease_retained = True
            else:
                release_lease_record(
                    node_id=matching_lease["node_id"],
                    lease_id=matching_lease["lease_id"],
                    generation=int(matching_lease["generation"]),
                    nonce=matching_lease["nonce"],
                    owner_task=validated_handoff["objective_id"],
                    state_root=resolved_root,
                )
                lease_released = True

    callback_receipt = _emit_worker_callback(
        callback_state_dir,
        attempt_id=target_attempt_id,
        objective_id=validated_handoff["objective_id"],
        outcome=outcome,
        worker_result=validated_result,
    )
    return {
        "schema": "codex_fleet_dispatch_readback.v1",
        "action": "complete",
        "status": outcome,
        "attempt_id": target_attempt_id,
        "dispatch_id": target_lease_id,
        "worker_result": validated_result,
        "budget_evaluation": budget_eval,
        "lease_released": lease_released,
        "lease_retained": lease_retained,
        "callback": callback_receipt,
    }


def _paths_overlap(path_a: str, path_b: str) -> bool:
    pa = PurePosixPath(path_a).parts
    pb = PurePosixPath(path_b).parts
    n = min(len(pa), len(pb))
    return n > 0 and pa[:n] == pb[:n]


def _group_receipt_path(group_id: str, *, state_root: Path | None = None) -> Path:
    return _resolve_state_root(state_root) / "controller/groups" / f"{group_id}.json"


def dispatch_group_plan(
    group_spec: dict[str, Any],
    *,
    max_concurrent: int | None = None,
    max_local_concurrent: int | None = None,
    candidates_by_item: dict[str, list[dict[str, Any]]] | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Validate group slices, annotate write-set integration overlaps, and compute queue admission."""
    if not isinstance(group_spec, dict) or not group_spec.get("group_id") or not isinstance(group_spec.get("slices"), list):
        raise FleetError("group_spec must include group_id and non-empty slices")

    slices = group_spec["slices"]
    if not slices:
        raise FleetError("group_spec slices must not be empty")

    validated_slices: list[dict[str, Any]] = []
    queue_items: list[dict[str, Any]] = []
    for entry in slices:
        if not isinstance(entry, dict) or not isinstance(entry.get("handoff"), dict):
            raise FleetError("each group slice must declare a handoff object")
        try:
            handoff = opl_execution.validate_handoff(entry["handoff"])
            reqs = read_execution_requirements(
                json.dumps(entry["requirements"]) if entry.get("requirements") is not None else None
            )
            opl_execution.enforce_pre_execution_envelope(handoff, ttl_seconds=int(reqs["ttl_seconds"]))
        except opl_execution.ExecutionError as exc:
            raise FleetError(str(exc)) from exc
        validated_slices.append({**entry, "handoff": handoff, "requirements": reqs})
        queue_items.append(
            {
                "objective_id": handoff["objective_id"],
                "adapter": entry.get("adapter") or reqs["adapter"],
                "requirements": reqs,
                "priority": reqs["priority"],
                "due_at": entry.get("due_at"),
                "has_human_comment": bool(entry.get("has_human_comment", False)),
                "unlocks_count": int(entry.get("unlocks_count", 0)),
                "node_id": entry.get("node_id"),
                "role": entry.get("role"),
            }
        )

    overlaps: list[dict[str, Any]] = []
    for idx, left in enumerate(validated_slices):
        ws_l = left["handoff"].get("write_set") or []
        for right in validated_slices[idx + 1 :]:
            ws_r = right["handoff"].get("write_set") or []
            shared = sorted(
                {
                    a if len(a) <= len(b) else b
                    for a in ws_l
                    for b in ws_r
                    if _paths_overlap(a, b)
                }
            )
            if shared:
                overlaps.append(
                    {
                        "objectives": sorted([left["handoff"]["objective_id"], right["handoff"]["objective_id"]]),
                        "overlapping_paths": shared,
                        "integration_policy": "serialized_critical_section",
                    }
                )

    queue_plan = plan_queue(
        queue_items,
        candidates_by_item=candidates_by_item,
        max_concurrent=max_concurrent,
        max_local_concurrent=max_local_concurrent,
        state_root=state_root,
    )
    return {
        "schema": "opl_fleet_group_plan.v1",
        "group_id": str(group_spec["group_id"]),
        "parent_objective_id": group_spec.get("parent_objective_id"),
        "slice_count": len(validated_slices),
        "integration_overlaps": overlaps,
        "queue_plan": queue_plan,
    }


def _summarize_fan_in(results: list[dict[str, Any]], queued: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "total": len(results) + len(queued),
        "completed": 0,
        "checkpointed": 0,
        "awaiting_completion": 0,
        "blocked": 0,
        "unknown": 0,
        "queued_backpressure": len(queued),
    }
    for item in results:
        st = item.get("status")
        if st == "completed":
            counts["completed"] += 1
        elif st in {"checkpoint", "checkpointed", "suspended_checkpointed"}:
            counts["checkpointed"] += 1
        elif st in {"awaiting_completion", "admitted", "running"}:
            counts["awaiting_completion"] += 1
        elif st == "blocked":
            counts["blocked"] += 1
        else:
            counts["unknown"] += 1
    counts["all_terminal"] = (
        counts["awaiting_completion"] == 0
        and counts["queued_backpressure"] == 0
        and counts["unknown"] == 0
    )
    counts["ready_for_integration"] = (
        counts["all_terminal"]
        and counts["blocked"] == 0
        and counts["completed"] == counts["total"]
    )
    return counts


def dispatch_group_run(
    group_spec: dict[str, Any],
    *,
    max_concurrent: int | None = None,
    max_local_concurrent: int | None = None,
    candidates_by_item: dict[str, list[dict[str, Any]]] | None = None,
    workspace_root: Path | None = None,
    runtime_dir: Path | None = None,
    callback_state_dir: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Fan-out eligible slices over admitted nodes/local slots and persist sanitized group receipt."""
    resolved_root = _resolve_state_root(state_root)
    plan = dispatch_group_plan(
        group_spec,
        max_concurrent=max_concurrent,
        max_local_concurrent=max_local_concurrent,
        candidates_by_item=candidates_by_item,
        state_root=resolved_root,
    )
    group_id = plan["group_id"]
    admitted_by_obj = {item["objective_id"]: item for item in plan["queue_plan"]["admit_now"]}
    slice_by_obj = {entry["handoff"]["objective_id"]: entry for entry in group_spec["slices"]}

    dispatched_results: list[dict[str, Any]] = []
    for obj_id, adm in admitted_by_obj.items():
        entry = slice_by_obj[obj_id]
        handoff = entry["handoff"]
        slice_runtime = (runtime_dir / handoff["attempt_id"]) if runtime_dir is not None else None
        res = dispatch_run(
            handoff=handoff,
            requirements=entry.get("requirements"),
            adapter=adm["adapter"],
            node_id=None if adm["node_id"] == "local" else adm["node_id"],
            role=entry.get("role"),
            owner_task=obj_id,
            owner_thread=entry.get("owner_thread"),
            owner_run=entry.get("owner_run"),
            argv=entry.get("argv"),
            executor_cmd=entry.get("executor_cmd"),
            mode=str(entry.get("mode") or ("envelope" if adm["adapter"] in {"remote-codex", "lease-only"} else "execute")),
            workspace_root=workspace_root,
            runtime_dir=slice_runtime,
            callback_state_dir=callback_state_dir,
            group_id=group_id,
            use_codex_bridge=bool(entry.get("use_codex_bridge", False)),
            use_antigravity_bridge=bool(entry.get("use_antigravity_bridge", False)),
            use_dsh_bridge=bool(entry.get("use_dsh_bridge", False)),
            codex_bin=entry.get("codex_bin"),
            agy_bin=entry.get("agy_bin"),
            dsh_control=entry.get("dsh_control"),
            dsh_combination=entry.get("dsh_combination"),
            model=entry.get("model"),
            effort=entry.get("effort"),
            use_worktree=bool(entry.get("use_worktree", False)),
            sandbox=entry.get("sandbox"),
            state_root=resolved_root,
        )
        dispatched_results.append(
            {
                "objective_id": obj_id,
                "attempt_id": res["attempt_id"],
                "adapter": res["adapter"],
                "node_id": res["node_id"],
                "dispatch_id": res.get("dispatch_id"),
                "status": res["status"],
            }
        )

    queued = list(plan["queue_plan"]["queued_backpressure"])
    summary = _summarize_fan_in(dispatched_results, queued)
    receipt = {
        "schema": GROUP_RECEIPT_SCHEMA,
        "group_id": group_id,
        "parent_objective_id": group_spec.get("parent_objective_id"),
        "integration_overlaps": plan["integration_overlaps"],
        "dispatched": dispatched_results,
        "queued_backpressure": queued,
        "preempt_candidates": plan["queue_plan"]["preempt_candidates"],
        "fan_in_summary": summary,
    }
    atomic_json(_group_receipt_path(group_id, state_root=resolved_root), receipt)
    return receipt


def dispatch_group_status(group_id: str, *, state_root: Path | None = None) -> dict[str, Any]:
    """Recompute live fan-in readiness for a stored group receipt from fresh attempt states."""
    resolved_root = _resolve_state_root(state_root)
    path = _group_receipt_path(group_id, state_root=resolved_root)
    if not path.is_file():
        raise FleetError(f"group receipt not found: {group_id}")
    receipt = read_json(path)
    refreshed: list[dict[str, Any]] = []
    for item in receipt.get("dispatched", []):
        attempt = get_attempt(item["attempt_id"], state_root=resolved_root)
        live_status = attempt["state"] if attempt else item["status"]
        refreshed.append({**item, "status": live_status})
    queued = list(receipt.get("queued_backpressure", []))
    receipt["dispatched"] = refreshed
    receipt["fan_in_summary"] = _summarize_fan_in(refreshed, queued)
    return receipt
