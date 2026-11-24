"""Sanitized attempt lifecycle, heartbeat, resumability/preemption, and telemetry."""

from __future__ import annotations

import contextlib
from copy import deepcopy
import fcntl
import os
from pathlib import Path
from typing import Any, Iterator

from . import fleet_common
from .fleet_common import FleetError, atomic_json, normalize_node_id, parse_utc, read_json, utc_now
from .fleet_lease import read_lease_store, release_lease_record, renew_lease_record

try:
    from .. import opl_execution
except ImportError:  # Direct script execution.
    import opl_execution


ATTEMPTS_SCHEMA = "opl_fleet_attempts.v1"
TELEMETRY_SCHEMA = "opl_fleet_attempt_telemetry.v1"
ATTEMPT_STATES = frozenset(
    {
        "admitted",
        "running",
        "checkpointed",
        "suspended_checkpointed",
        "completed",
        "blocked",
        "stale_unknown",
        "unknown",
    }
)
ACTIVE_ATTEMPT_STATES = frozenset({"admitted", "running", "checkpointed"})
HEARTBEAT_REQUIRED_STATES = frozenset({"admitted", "running"})
MAX_RETAINED_TERMINAL_ATTEMPTS = 500
FORBIDDEN_TELEMETRY_FIELDS = [
    "prompt",
    "response",
    "content",
    "conversation_content",
    "raw_prompt",
    "raw_response",
    "raw_content",
    "session_id",
    "local_path",
    "interface",
    "interface_name",
    "address",
    "network_address",
    "credential",
    "secret",
    "raw_log",
]


def _resolve_state_root(state_root: Path | None) -> Path:
    return state_root or fleet_common.STATE_ROOT


def attempt_paths(state_root: Path | None = None) -> tuple[Path, Path]:
    root = _resolve_state_root(state_root)
    return root / "controller/attempts.json", root / "controller/attempts.lock"


@contextlib.contextmanager
def _attempts_lock(*, state_root: Path | None = None) -> Iterator[None]:
    _, lock_path = attempt_paths(state_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(lock_path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _empty_store() -> dict[str, Any]:
    return {"schema": ATTEMPTS_SCHEMA, "attempts": {}}


def read_attempt_store(*, state_root: Path | None = None) -> dict[str, Any]:
    path, _ = attempt_paths(state_root)
    if not path.exists():
        return _empty_store()
    payload = read_json(path)
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != ATTEMPTS_SCHEMA
        or not isinstance(payload.get("attempts"), dict)
    ):
        raise FleetError(f"attempt store schema is invalid: {path}")
    return payload


def _write_attempt_store(payload: dict[str, Any], *, state_root: Path | None = None) -> None:
    path, _ = attempt_paths(state_root)
    attempts = dict(payload.get("attempts") or {})
    active = {k: v for k, v in attempts.items() if v.get("state") in ACTIVE_ATTEMPT_STATES}
    terminal = [
        (k, v)
        for k, v in attempts.items()
        if v.get("state") not in ACTIVE_ATTEMPT_STATES
    ]
    terminal.sort(key=lambda item: str(item[1].get("updated_at") or ""))
    kept_terminal = dict(terminal[-MAX_RETAINED_TERMINAL_ATTEMPTS:])
    merged = {**kept_terminal, **active}
    atomic_json(path, {"schema": ATTEMPTS_SCHEMA, "attempts": merged})


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        opl_execution.sanitize_check(record, label="attempt_record")
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc
    return record


def _check_budget_against_summary(
    envelope_summary: dict[str, Any] | None,
    budget_usage: dict[str, Any] | None,
) -> list[str]:
    if not envelope_summary or not budget_usage:
        return []
    violations: list[str] = []
    if envelope_summary.get("max_duration_seconds") is not None and "elapsed_seconds" in budget_usage:
        if float(budget_usage["elapsed_seconds"]) > float(envelope_summary["max_duration_seconds"]):
            violations.append("elapsed_seconds exceeded envelope max_duration_seconds")
    if envelope_summary.get("max_tokens") is not None and "tokens_used" in budget_usage:
        if int(budget_usage["tokens_used"]) > int(envelope_summary["max_tokens"]):
            violations.append("tokens_used exceeded envelope max_tokens")
    if envelope_summary.get("max_cost_usd") is not None and "estimated_cost_usd" in budget_usage:
        if float(budget_usage["estimated_cost_usd"]) > float(envelope_summary["max_cost_usd"]):
            violations.append("estimated_cost_usd exceeded envelope max_cost_usd")
    return violations


def record_attempt_start(
    *,
    attempt_id: str,
    objective_id: str,
    owner_id: str,
    adapter: str,
    node_id: str,
    handoff_binding: dict[str, str],
    resumability: dict[str, Any] | None = None,
    envelope_summary: dict[str, Any] | None = None,
    lease_id: str | None = None,
    lease_generation: int | None = None,
    lease_nonce: str | None = None,
    group_id: str | None = None,
    initial_state: str = "running",
    phase: str = "executing",
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    if initial_state not in {"admitted", "running"}:
        raise FleetError(f"invalid initial attempt state: {initial_state!r}")
    if node_id != "local" and normalize_node_id(node_id) != node_id:
        raise FleetError(f"invalid attempt node_id: {node_id!r}")
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()

    res_cfg = resumability or {}
    resumable = bool(res_cfg.get("checkpointable", False))
    interruptible = str(res_cfg.get("interruptible_phase", "interruptible")) == "interruptible"
    hb_interval = int(res_cfg.get("heartbeat_interval_seconds", 60))
    max_stale = int(res_cfg.get("max_stale_seconds", 300))

    clean_envelope = None
    if isinstance(envelope_summary, dict):
        clean_envelope = {
            key: envelope_summary[key]
            for key in (
                "enforced",
                "has_write_bounds",
                "max_duration_seconds",
                "max_tokens",
                "max_cost_usd",
                "credential_ref_count",
            )
            if key in envelope_summary
        }

    record = _sanitize_record(
        {
            "attempt_id": str(attempt_id),
            "objective_id": str(objective_id),
            "owner_id": str(owner_id),
            "adapter": str(adapter),
            "node_id": str(node_id),
            "phase": str(phase),
            "state": initial_state,
            "started_at": now_iso,
            "last_heartbeat_at": now_iso,
            "updated_at": now_iso,
            "resumable": resumable,
            "interruptible": interruptible,
            "heartbeat_interval_seconds": hb_interval,
            "max_stale_seconds": max_stale,
            "resume_command_ref": res_cfg.get("resume_command_ref"),
            "handoff_sha256": handoff_binding.get("handoff_sha256"),
            "lease_id": lease_id,
            "lease_generation": lease_generation,
            "lease_nonce": lease_nonce,
            "lease_active": bool(lease_id),
            "group_id": group_id,
            "envelope_summary": clean_envelope,
            "checkpoint_refs": [],
            "result_class": None,
            "blocker_code": None,
            "budget_usage": None,
            "budget_violations": [],
        }
    )

    with _attempts_lock(state_root=state_root):
        store = read_attempt_store(state_root=state_root)
        store["attempts"][str(attempt_id)] = record
        _write_attempt_store(store, state_root=state_root)
    return deepcopy(record)


def get_attempt(attempt_id: str, *, state_root: Path | None = None) -> dict[str, Any] | None:
    store = read_attempt_store(state_root=state_root)
    rec = store["attempts"].get(attempt_id)
    return deepcopy(rec) if isinstance(rec, dict) else None


def list_attempts(
    *,
    node_id: str | None = None,
    objective_id: str | None = None,
    group_id: str | None = None,
    state: str | None = None,
    state_root: Path | None = None,
) -> list[dict[str, Any]]:
    store = read_attempt_store(state_root=state_root)
    results: list[dict[str, Any]] = []
    for rec in store["attempts"].values():
        if not isinstance(rec, dict):
            continue
        if node_id is not None and rec.get("node_id") != node_id:
            continue
        if objective_id is not None and rec.get("objective_id") != objective_id:
            continue
        if group_id is not None and rec.get("group_id") != group_id:
            continue
        if state is not None and rec.get("state") != state:
            continue
        results.append(deepcopy(rec))
    results.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return results


def heartbeat_attempt(
    attempt_id: str,
    *,
    phase: str | None = None,
    checkpoint_ref: str | None = None,
    budget_usage: dict[str, Any] | None = None,
    renew_lease: bool = False,
    lease_ttl_seconds: int | None = None,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()

    if checkpoint_ref is not None:
        try:
            opl_execution.identity(checkpoint_ref, "checkpoint_ref")
        except opl_execution.ExecutionError as exc:
            raise FleetError(str(exc)) from exc
    if budget_usage is not None:
        try:
            opl_execution._validate_budget_usage(budget_usage)
        except opl_execution.ExecutionError as exc:
            raise FleetError(str(exc)) from exc

    with _attempts_lock(state_root=state_root):
        store = read_attempt_store(state_root=state_root)
        rec = store["attempts"].get(attempt_id)
        if not isinstance(rec, dict):
            raise FleetError(f"attempt not found: {attempt_id}")
        if rec.get("state") not in ACTIVE_ATTEMPT_STATES:
            raise FleetError(f"cannot heartbeat attempt in state {rec.get('state')!r}")

        rec["state"] = "running"
        rec["last_heartbeat_at"] = now_iso
        rec["updated_at"] = now_iso
        if phase is not None:
            rec["phase"] = str(phase)
        if checkpoint_ref is not None:
            refs = list(rec.get("checkpoint_refs") or [])
            if checkpoint_ref not in refs:
                refs.append(checkpoint_ref)
            rec["checkpoint_refs"] = refs[-20:]
        if budget_usage is not None:
            rec["budget_usage"] = deepcopy(budget_usage)
            rec["budget_violations"] = _check_budget_against_summary(
                rec.get("envelope_summary"), budget_usage
            )

        if renew_lease and rec.get("lease_active") and rec.get("lease_id") and rec.get("node_id") != "local":
            renewed = renew_lease_record(
                node_id=rec["node_id"],
                lease_id=rec["lease_id"],
                generation=int(rec["lease_generation"]),
                nonce=rec["lease_nonce"],
                owner_task=rec["objective_id"],
                ttl_seconds=lease_ttl_seconds or 3600,
                state_root=_resolve_state_root(state_root),
            )
            rec["lease_generation"] = renewed.get("generation", rec["lease_generation"])

        _sanitize_record(rec)
        _write_attempt_store(store, state_root=state_root)
        result_rec = deepcopy(rec)

    violations = list(result_rec.get("budget_violations") or [])
    return {
        "schema": "opl_attempt_heartbeat.v1",
        "attempt": result_rec,
        "budget_within_limits": not violations,
        "budget_violations": violations,
    }


def finish_attempt(
    attempt_id: str,
    *,
    outcome: str,
    result_class: str | None = None,
    blocker_code: str | None = None,
    budget_usage: dict[str, Any] | None = None,
    checkpoint_refs: list[str] | None = None,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    state_map = {
        "completed": "completed",
        "checkpoint": "checkpointed",
        "checkpointed": "checkpointed",
        "blocked": "blocked",
        "unknown": "unknown",
        "suspended_checkpointed": "suspended_checkpointed",
        "stale_unknown": "stale_unknown",
    }
    if outcome not in state_map:
        raise FleetError(f"invalid attempt outcome: {outcome!r}")
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()

    if budget_usage is not None:
        try:
            opl_execution._validate_budget_usage(budget_usage)
        except opl_execution.ExecutionError as exc:
            raise FleetError(str(exc)) from exc

    with _attempts_lock(state_root=state_root):
        store = read_attempt_store(state_root=state_root)
        rec = store["attempts"].get(attempt_id)
        if not isinstance(rec, dict):
            raise FleetError(f"attempt not found: {attempt_id}")
        target_state = state_map[outcome]
        rec["state"] = target_state
        rec["result_class"] = result_class or outcome
        rec["blocker_code"] = blocker_code
        rec["updated_at"] = now_iso
        if target_state not in {"unknown", "stale_unknown"}:
            rec["lease_active"] = False
        if checkpoint_refs:
            existing_refs = list(rec.get("checkpoint_refs") or [])
            for ref in checkpoint_refs:
                if ref not in existing_refs:
                    existing_refs.append(ref)
            rec["checkpoint_refs"] = existing_refs[-20:]
        if budget_usage is not None:
            rec["budget_usage"] = deepcopy(budget_usage)
            rec["budget_violations"] = _check_budget_against_summary(
                rec.get("envelope_summary"), budget_usage
            )
        _sanitize_record(rec)
        _write_attempt_store(store, state_root=state_root)
        return deepcopy(rec)


def plan_preemption(
    node_id: str,
    *,
    incoming_priority: int,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    resolved_root = _resolve_state_root(state_root)
    leases = read_lease_store(state_root=resolved_root).get("leases", {})
    lease = leases.get(node_id)
    if not isinstance(lease, dict):
        return {
            "schema": "opl_fleet_preemption_plan.v1",
            "node_id": node_id,
            "preemption_possible": False,
            "reason": "node_idle",
            "steps": [],
        }

    store = read_attempt_store(state_root=resolved_root)
    matching_attempt = next(
        (
            rec
            for rec in store["attempts"].values()
            if isinstance(rec, dict)
            and rec.get("lease_id") == lease.get("lease_id")
            and rec.get("state") in ACTIVE_ATTEMPT_STATES
        ),
        None,
    )

    if not lease.get("preemptible"):
        return {
            "schema": "opl_fleet_preemption_plan.v1",
            "node_id": node_id,
            "preemption_possible": False,
            "reason": "lease_not_preemptible",
            "lease_id": lease.get("lease_id"),
            "steps": [],
        }
    if lease.get("phase") != "interruptible":
        return {
            "schema": "opl_fleet_preemption_plan.v1",
            "node_id": node_id,
            "preemption_possible": False,
            "reason": "lease_non_interruptible",
            "lease_id": lease.get("lease_id"),
            "steps": [],
        }
    if int(incoming_priority) <= int(lease.get("priority", 0)):
        return {
            "schema": "opl_fleet_preemption_plan.v1",
            "node_id": node_id,
            "preemption_possible": False,
            "reason": "incoming_priority_not_higher",
            "lease_id": lease.get("lease_id"),
            "steps": [],
        }
    if matching_attempt is not None:
        if not matching_attempt.get("resumable"):
            return {
                "schema": "opl_fleet_preemption_plan.v1",
                "node_id": node_id,
                "preemption_possible": False,
                "reason": "attempt_not_resumable",
                "lease_id": lease.get("lease_id"),
                "target_attempt_id": matching_attempt.get("attempt_id"),
                "steps": [],
            }
        if not matching_attempt.get("interruptible"):
            return {
                "schema": "opl_fleet_preemption_plan.v1",
                "node_id": node_id,
                "preemption_possible": False,
                "reason": "attempt_non_interruptible",
                "lease_id": lease.get("lease_id"),
                "target_attempt_id": matching_attempt.get("attempt_id"),
                "steps": [],
            }

    return {
        "schema": "opl_fleet_preemption_plan.v1",
        "node_id": node_id,
        "preemption_possible": True,
        "reason": "eligible_for_graceful_preemption",
        "lease_id": lease.get("lease_id"),
        "lease_generation": lease.get("generation"),
        "lease_nonce": lease.get("nonce"),
        "current_priority": lease.get("priority"),
        "incoming_priority": int(incoming_priority),
        "target_attempt_id": matching_attempt.get("attempt_id") if matching_attempt else None,
        "steps": [
            "checkpoint_and_suspend_attempt" if matching_attempt else "checkpoint_caller_workload",
            "release_or_preempt_lease",
            "acquire_incoming_lease",
        ],
    }


def suspend_attempt(
    attempt_id: str,
    *,
    checkpoint_ref: str,
    reason: str = "preempted",
    release_lease: bool = True,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    try:
        opl_execution.identity(checkpoint_ref, "checkpoint_ref")
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()
    resolved_root = _resolve_state_root(state_root)

    with _attempts_lock(state_root=resolved_root):
        store = read_attempt_store(state_root=resolved_root)
        rec = store["attempts"].get(attempt_id)
        if not isinstance(rec, dict):
            raise FleetError(f"attempt not found: {attempt_id}")
        if rec.get("state") not in ACTIVE_ATTEMPT_STATES:
            raise FleetError(f"cannot suspend attempt in state {rec.get('state')!r}")
        if not rec.get("resumable"):
            raise FleetError("cannot suspend non-resumable attempt")
        if not rec.get("interruptible"):
            raise FleetError("cannot suspend attempt in non-interruptible phase")

        lease_released = False
        if release_lease and rec.get("lease_active") and rec.get("lease_id") and rec.get("node_id") != "local":
            leases = read_lease_store(state_root=resolved_root).get("leases", {})
            active_lease = leases.get(rec["node_id"])
            if isinstance(active_lease, dict) and active_lease.get("lease_id") == rec["lease_id"]:
                release_lease_record(
                    node_id=rec["node_id"],
                    lease_id=rec["lease_id"],
                    generation=int(active_lease["generation"]),
                    nonce=active_lease["nonce"],
                    owner_task=rec["objective_id"],
                    state_root=resolved_root,
                )
                lease_released = True

        refs = list(rec.get("checkpoint_refs") or [])
        if checkpoint_ref not in refs:
            refs.append(checkpoint_ref)
        rec["checkpoint_refs"] = refs[-20:]
        rec["state"] = "suspended_checkpointed"
        rec["result_class"] = "checkpointed"
        rec["blocker_code"] = str(reason)
        rec["lease_active"] = False
        rec["updated_at"] = now_iso
        _sanitize_record(rec)
        _write_attempt_store(store, state_root=resolved_root)
        updated = deepcopy(rec)

    return {
        "schema": "opl_attempt_suspend.v1",
        "attempt": updated,
        "lease_released": lease_released,
    }


def check_stale_attempts(
    *,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()
    resolved_root = _resolve_state_root(state_root)

    stale_records: list[dict[str, Any]] = []
    with _attempts_lock(state_root=resolved_root):
        store = read_attempt_store(state_root=resolved_root)
        for rec in store["attempts"].values():
            if not isinstance(rec, dict) or rec.get("state") not in HEARTBEAT_REQUIRED_STATES:
                continue
            hb = parse_utc(rec["last_heartbeat_at"])
            max_stale = int(rec.get("max_stale_seconds", 300))
            if (now_dt - hb).total_seconds() > max_stale:
                rec["state"] = "stale_unknown"
                rec["result_class"] = "stale_unknown"
                rec["blocker_code"] = "heartbeat_stale"
                rec["updated_at"] = now_iso
                _sanitize_record(rec)
                stale_records.append(deepcopy(rec))
        if stale_records:
            _write_attempt_store(store, state_root=resolved_root)

    return {
        "schema": "opl_fleet_stale_check.v1",
        "checked_at": now_iso,
        "stale_count": len(stale_records),
        "stale_attempts": stale_records,
    }


def observe_attempts(
    *,
    node_id: str | None = None,
    state_root: Path | None = None,
    now: Any = None,
) -> dict[str, Any]:
    if node_id is not None and node_id != "local" and normalize_node_id(node_id) != node_id:
        raise FleetError(f"invalid node_id filter: {node_id!r}")
    now_dt = now if now is not None else utc_now()
    if isinstance(now_dt, str):
        now_dt = parse_utc(now_dt)
    now_iso = now_dt.isoformat()

    records = list_attempts(node_id=node_id, state_root=state_root)
    projected: list[dict[str, Any]] = []
    for rec in records:
        projected.append(
            {
                "attempt_id": rec["attempt_id"],
                "objective_id": rec["objective_id"],
                "owner_id": rec["owner_id"],
                "adapter": rec["adapter"],
                "node_id": rec["node_id"],
                "phase": rec["phase"],
                "state": rec["state"],
                "started_at": rec["started_at"],
                "last_heartbeat_at": rec["last_heartbeat_at"],
                "updated_at": rec["updated_at"],
                "resumable": bool(rec.get("resumable", False)),
                "interruptible": bool(rec.get("interruptible", True)),
                "result_class": rec.get("result_class"),
                **({"blocker_code": rec["blocker_code"]} if rec.get("blocker_code") is not None else {}),
                **({"budget_usage": rec["budget_usage"]} if rec.get("budget_usage") is not None else {}),
            }
        )

    payload = {
        "schema": TELEMETRY_SCHEMA,
        "access": "read_only",
        "authority": "observation_only",
        "observed_at": now_iso,
        "node_id": node_id,
        "attempts": projected,
        "forbidden_fields": list(FORBIDDEN_TELEMETRY_FIELDS),
    }
    try:
        opl_execution.sanitize_check(payload, label="attempt_telemetry")
    except opl_execution.ExecutionError as exc:
        raise FleetError(str(exc)) from exc
    return payload
