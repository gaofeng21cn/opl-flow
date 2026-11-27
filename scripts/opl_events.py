"""Sanitized idempotent event inbox, unified intake, Beads task graph, and stateless logical controller.

Zero Fleet imports. Beads/Dolt remains the only durable task truth.
"""

from __future__ import annotations

import contextlib
from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Annotated, Any, Callable, Iterable, Iterator
import uuid

try:
    from . import opl_runtime as runtime, opl_state_store as state_store
    from . import opl_execution, opl_ledger, opl_session_discovery, opl_supervisor
except ImportError:  # Direct script execution.
    import opl_runtime as runtime
    import opl_state_store as state_store
    import opl_execution
    import opl_ledger
    import opl_session_discovery
    import opl_supervisor

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


EVENT_SCHEMA = "opl_workflow_event.v1"
INBOX_SCHEMA = "opl_workflow_event_inbox.v1"
CONTROL_TURN_SCHEMA = "opl_control_turn_plan.v1"

EVENT_TYPES = frozenset(
    {
        "human_intake",
        "human_comment",
        "worker_callback",
        "review_due",
        "external_unblocked",
        "owner_drift",
        "executor_lost",
        "write_set_conflict",
    }
)
EVENT_STATUSES = frozenset(
    {
        "pending",
        "claimed",
        "acked",
        "failed_retryable",
        "dead_letter",
    }
)
MAX_RETAINED_TERMINAL_EVENTS = 500
MAX_RETRIES = 5
CONTROL_BRIDGES = ("auto", "codex", "antigravity")
EXECUTOR_ADAPTER_MAP = {
    "codex": "local-codex",
    "antigravity": "local-antigravity",
    "dsh": "local-dsh",
}
TEST_OR_WAIT_ONLY_RE = re.compile(
    r"^\s*(?:re-?run\s+tests?|run\s+tests?|wait|poll|monitor\s+tests?|retest)\b",
    re.IGNORECASE,
)


class EventControlError(RuntimeError):
    pass


def _utc_now() -> dt.datetime:
    return runtime.utc_now()


def _parse_utc(value: Any) -> dt.datetime:
    parsed = runtime.parse_utc(value, error_cls=EventControlError)
    assert parsed is not None
    return parsed


def _iso_utc(value: dt.datetime) -> str:
    return runtime.iso_utc(value)


def default_event_state_dir(instance_root: Path) -> Path:
    digest = hashlib.sha256(str(instance_root.expanduser().resolve()).encode("utf-8")).hexdigest()[:16]
    return Path.home() / ".local/state/opl-flow/events" / digest


def inbox_paths(state_dir: Path) -> tuple[Path, Path]:
    db_path, lock_path, _ = state_store.inbox_db_paths(state_dir)
    return db_path, lock_path


def inbox_exists(state_dir: Path) -> bool:
    return state_store.inbox_exists(state_dir)


def _empty_inbox() -> dict[str, Any]:
    return {"schema": INBOX_SCHEMA, "events": []}


def _atomic_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    runtime.atomic_write_json(path, payload, mode=mode, ensure_ascii=False, private_dir=True)


@contextlib.contextmanager
def _inbox_lock(state_dir: Path) -> Iterator[None]:
    _, lock_path = inbox_paths(state_dir)
    with runtime.file_lock(lock_path, private_dir=True, mode=0o600):
        yield


def _read_inbox(state_dir: Path) -> dict[str, Any]:
    return state_store.read_inbox_store(state_dir, error_cls=EventControlError)


def _write_inbox(state_dir: Path, payload: dict[str, Any]) -> None:
    state_store.write_inbox_store(
        state_dir,
        payload,
        max_retained_terminal=MAX_RETAINED_TERMINAL_EVENTS,
        error_cls=EventControlError,
    )


def _validate_event_inputs(
    *,
    event_type: str,
    objective_id: str,
    source: str,
    idempotency_key: str,
    parent_objective_id: str | None,
    attempt_id: str | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise EventControlError(f"unsupported workflow event type: {event_type!r}")
    try:
        opl_execution.identity(objective_id, "objective_id")
        opl_execution.identity(source, "source")
        opl_execution.identity(idempotency_key, "idempotency_key")
        if parent_objective_id is not None:
            opl_execution.identity(parent_objective_id, "parent_objective_id")
        if attempt_id is not None:
            opl_execution.identity(attempt_id, "attempt_id")
        clean_payload = deepcopy(payload) if payload is not None else {}
        if not isinstance(clean_payload, dict):
            raise EventControlError("event payload must be a JSON object")
        opl_execution.sanitize_check(clean_payload, label="event_payload")
    except opl_execution.ExecutionError as exc:
        raise EventControlError(str(exc)) from exc
    return clean_payload


def emit_event(
    state_dir: Path,
    *,
    event_type: str,
    objective_id: str,
    source: str,
    idempotency_key: str,
    parent_objective_id: str | None = None,
    attempt_id: str | None = None,
    payload: dict[str, Any] | None = None,
    now: str | dt.datetime | None = None,
) -> dict[str, Any]:
    clean_payload = _validate_event_inputs(
        event_type=event_type,
        objective_id=objective_id,
        source=source,
        idempotency_key=idempotency_key,
        parent_objective_id=parent_objective_id,
        attempt_id=attempt_id,
        payload=payload,
    )
    now_dt = _parse_utc(now) if isinstance(now, str) else (now or _utc_now())
    now_iso = _iso_utc(now_dt)

    with _inbox_lock(state_dir):
        inbox = _read_inbox(state_dir)
        for existing in inbox["events"]:
            if existing.get("idempotency_key") == idempotency_key:
                return {"deduplicated": True, "event": deepcopy(existing)}
        record = {
            "schema": EVENT_SCHEMA,
            "event_id": f"ev-{uuid.uuid4().hex[:16]}",
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "objective_id": objective_id,
            "parent_objective_id": parent_objective_id,
            "attempt_id": attempt_id,
            "source": source,
            "created_at": now_iso,
            "updated_at": now_iso,
            "status": "pending",
            "claim_token": None,
            "claim_expires_at": None,
            "claimed_by": None,
            "retry_count": 0,
            "last_error": None,
            "payload": clean_payload,
        }
        inbox["events"].append(record)
        _write_inbox(state_dir, inbox)
        return {"deduplicated": False, "event": deepcopy(record)}


def list_events(
    state_dir: Path,
    *,
    status: str | None = None,
    objective_id: str | None = None,
    parent_objective_id: str | None = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in EVENT_STATUSES:
        raise EventControlError(f"invalid event status filter: {status!r}")
    inbox = _read_inbox(state_dir)
    results: list[dict[str, Any]] = []
    for item in inbox["events"]:
        if status is not None and item.get("status") != status:
            continue
        if objective_id is not None and item.get("objective_id") != objective_id:
            continue
        if parent_objective_id is not None and (item.get("parent_objective_id") or item.get("objective_id")) != parent_objective_id:
            continue
        results.append(deepcopy(item))
    return results


def claim_events(
    state_dir: Path,
    *,
    consumer_id: str,
    objective_id: str | None = None,
    objective_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    parent_objective_id: str | None = None,
    limit: int = 50,
    lease_seconds: int = 300,
    now: str | dt.datetime | None = None,
) -> dict[str, Any]:
    if not consumer_id or not str(consumer_id).strip():
        raise EventControlError("consumer_id is required")
    if limit < 1 or lease_seconds < 10:
        raise EventControlError("limit and lease_seconds must be positive")
    now_dt = _parse_utc(now) if isinstance(now, str) else (now or _utc_now())
    now_iso = _iso_utc(now_dt)
    expires_iso = _iso_utc(now_dt + dt.timedelta(seconds=lease_seconds))
    token = f"claim-{uuid.uuid4().hex}"
    allowed_objectives = set(objective_ids) if objective_ids is not None else None

    claimed: list[dict[str, Any]] = []
    with _inbox_lock(state_dir):
        inbox = _read_inbox(state_dir)
        for item in inbox["events"]:
            if len(claimed) >= limit:
                break
            if objective_id is not None and item.get("objective_id") != objective_id:
                continue
            if allowed_objectives is not None and item.get("objective_id") not in allowed_objectives:
                continue
            if parent_objective_id is not None and (item.get("parent_objective_id") or item.get("objective_id")) != parent_objective_id:
                continue
            status = item.get("status")
            eligible = status in {"pending", "failed_retryable"}
            if status == "claimed" and item.get("claim_expires_at"):
                if _parse_utc(item["claim_expires_at"]) <= now_dt:
                    eligible = True
            if not eligible:
                continue
            item["status"] = "claimed"
            item["claim_token"] = token
            item["claim_expires_at"] = expires_iso
            item["claimed_by"] = str(consumer_id).strip()
            item["updated_at"] = now_iso
            claimed.append(deepcopy(item))
        if claimed:
            _write_inbox(state_dir, inbox)
    return {
        "schema": "opl_workflow_event_claim.v1",
        "claim_token": token if claimed else None,
        "claim_expires_at": expires_iso if claimed else None,
        "events": claimed,
    }


def ack_events(
    state_dir: Path,
    *,
    event_ids: list[str] | tuple[str, ...],
    claim_token: str,
    outcome: str = "acked",
    error: str | None = None,
    max_retries: int = MAX_RETRIES,
    now: str | dt.datetime | None = None,
) -> dict[str, Any]:
    if outcome not in {"acked", "failed_retryable", "dead_letter"}:
        raise EventControlError(f"invalid ack outcome: {outcome!r}")
    if not claim_token or not str(claim_token).strip():
        raise EventControlError("claim_token is required")
    target_ids = {str(eid).strip() for eid in event_ids if str(eid).strip()}
    if not target_ids:
        raise EventControlError("at least one event_id is required")
    now_dt = _parse_utc(now) if isinstance(now, str) else (now or _utc_now())
    now_iso = _iso_utc(now_dt)

    updated: list[dict[str, Any]] = []
    with _inbox_lock(state_dir):
        inbox = _read_inbox(state_dir)
        by_id = {item["event_id"]: item for item in inbox["events"] if isinstance(item, dict) and "event_id" in item}
        missing = sorted(target_ids - set(by_id))
        if missing:
            raise EventControlError(f"unknown event_ids: {', '.join(missing)}")
        for eid in sorted(target_ids):
            item = by_id[eid]
            if item.get("status") != "claimed" or item.get("claim_token") != claim_token:
                raise EventControlError(f"event {eid} claim_token mismatch or not claimed")
        for eid in sorted(target_ids):
            item = by_id[eid]
            item["claim_token"] = None
            item["claim_expires_at"] = None
            item["claimed_by"] = None
            item["updated_at"] = now_iso
            if outcome == "acked":
                item["status"] = "acked"
                item["last_error"] = None
            elif outcome == "dead_letter":
                item["status"] = "dead_letter"
                item["last_error"] = str(error)[:256] if error else "explicit_dead_letter"
            else:
                retries = int(item.get("retry_count", 0)) + 1
                item["retry_count"] = retries
                item["last_error"] = str(error)[:256] if error else "transient_failure"
                item["status"] = "dead_letter" if retries >= max_retries else "failed_retryable"
            updated.append(deepcopy(item))
        _write_inbox(state_dir, inbox)
    return {"outcome": outcome, "updated": updated}


def _priority_label(priority: int | str) -> str:
    if isinstance(priority, str):
        text = priority.strip().upper()
        if text in {"P0", "P1", "P2", "P3", "P4"}:
            return text
        if text.isdigit():
            priority = int(text)
    if isinstance(priority, int):
        clamped = max(0, min(4, priority))
        return f"P{clamped}"
    return "P2"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "objective"


def intake_objective(
    instance_root: Path,
    bd: str,
    *,
    title: str,
    scope: str,
    parent: str | None = None,
    write_set: list[str] | tuple[str, ...] | None = None,
    priority: int | str = 2,
    execution_mode: str = "backlog",
    requirements: dict[str, Any] | None = None,
    depends_on: list[str] | tuple[str, ...] | None = None,
    execution_thread: str | None = None,
    execution_carrier: str | None = None,
    external_ref: str | None = None,
    state_dir: Path | None = None,
    runner: opl_ledger.Runner | None = None,
) -> dict[str, Any]:
    """Create a managed objective directly in Beads/Dolt and emit a unified intake event."""
    if not title or not title.strip():
        raise EventControlError("objective title is required")
    if not scope or not scope.strip():
        raise EventControlError("objective scope is required")
    if execution_mode not in {"backlog", "active"}:
        raise EventControlError("intake execution_mode must be backlog or active")

    try:
        clean_write_set = [
            opl_execution.validate_relative_path(path, "write_set")
            for path in (write_set or [])
        ]
    except opl_execution.ExecutionError as exc:
        raise EventControlError(str(exc)) from exc
    if len(clean_write_set) != len(set(clean_write_set)):
        raise EventControlError("intake write_set entries must be unique")

    if requirements is not None:
        if not isinstance(requirements, dict) or requirements.get("schema") != "opl_execution_requirements.v1":
            raise EventControlError("requirements must declare schema opl_execution_requirements.v1")
        try:
            opl_execution.sanitize_check(requirements, label="execution_requirements")
        except opl_execution.ExecutionError as exc:
            raise EventControlError(str(exc)) from exc

    clean_thread = execution_thread.strip() if isinstance(execution_thread, str) and execution_thread.strip() else None
    clean_carrier = execution_carrier.strip().lower() if isinstance(execution_carrier, str) and execution_carrier.strip() else None
    if clean_thread and not clean_carrier and ":" in clean_thread:
        prefix = clean_thread.split(":", 1)[0].strip().lower()
        if prefix in {"codex", "antigravity", "dsh"}:
            clean_carrier = prefix
    if clean_carrier is not None and clean_carrier not in {"codex", "antigravity", "dsh"}:
        raise EventControlError(f"unsupported execution_carrier: {clean_carrier!r}")

    ref_digest = hashlib.sha256(f"{title.strip()}\n{scope.strip()}".encode("utf-8")).hexdigest()[:12]
    resolved_ref = external_ref or f"opl://intake/{_slug(title)}-{ref_digest}"
    metadata: dict[str, Any] = {
        "classification": "managed_objective",
        "execution_mode": execution_mode,
        "write_set": clean_write_set,
        "remaining": [scope.strip()],
        "next_action": scope.strip(),
    }
    if requirements is not None:
        metadata["opl_execution_requirements"] = requirements
    if clean_thread is not None:
        metadata["execution_thread"] = clean_thread
    if clean_carrier is not None:
        metadata["execution_carrier"] = clean_carrier

    bead = opl_ledger.create_issue(
        instance_root,
        bd,
        title=title.strip(),
        issue_type="task",
        external_ref=resolved_ref,
        labels="opl,managed",
        description=scope.strip(),
        metadata=metadata,
        priority=_priority_label(priority),
        parent=parent,
        runner=runner,
    )
    bead_id = str(bead["id"])
    for dep_id in depends_on or []:
        opl_ledger.add_dependency(instance_root, bd, bead_id, str(dep_id), dep_type="blocks", runner=runner)

    inbox_dir = state_dir or default_event_state_dir(instance_root)
    emitted = emit_event(
        inbox_dir,
        event_type="human_intake",
        objective_id=bead_id,
        parent_objective_id=parent,
        source="cli:intake",
        idempotency_key=f"intake:{bead_id}:{resolved_ref}",
        payload={
            "signal": "manual_intake",
            "execution_mode": execution_mode,
            "write_set": clean_write_set,
            **({"execution_carrier": clean_carrier} if clean_carrier is not None else {}),
        },
    )
    return {"schema": "opl_intake_result.v1", "bead": bead, "event": emitted["event"], "deduplicated": emitted["deduplicated"]}


class _GraphSliceModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
    title: StrictStr
    scope: StrictStr
    write_set: list[Any] = Field(default_factory=list)
    depends_on: list[Any] = Field(default_factory=list)
    envelope: dict[str, Any] | None = None
    resumability: dict[str, Any] | None = None

    @field_validator("key", "title", "scope", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("graph slice requires non-empty key, title, and scope")
        return text


class _GraphSpecModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    graph_id: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]
    epic: dict[str, Any]
    slices: Annotated[list[_GraphSliceModel], Field(min_length=1)]

    @field_validator("graph_id", mode="before")
    @classmethod
    def _strip_graph_id(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("epic")
    @classmethod
    def _epic_title(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not str(value.get("title") or "").strip():
            raise ValueError("graph epic must declare a non-empty title")
        return value


def _validate_graph_spec(graph_spec: Any) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(graph_spec, dict):
        raise EventControlError("graph_spec must be a JSON object")
    parsed = runtime.validate_model(_GraphSpecModel, graph_spec, error_cls=EventControlError)
    assert isinstance(parsed, _GraphSpecModel)
    graph_id, epic = parsed.graph_id, parsed.epic
    by_key: dict[str, dict[str, Any]] = {}
    for raw_item, slice_model in zip(graph_spec["slices"], parsed.slices):
        key = slice_model.key
        if key in by_key:
            raise EventControlError(f"duplicate graph slice key: {key}")
        try:
            write_set = [opl_execution.validate_relative_path(p, f"{key}.write_set") for p in slice_model.write_set]
            if slice_model.envelope is not None:
                opl_execution.validate_envelope(slice_model.envelope)
            if slice_model.resumability is not None:
                opl_execution.validate_resumability(slice_model.resumability)
        except opl_execution.ExecutionError as exc:
            raise EventControlError(str(exc)) from exc
        normalized = deepcopy(raw_item)
        normalized["key"] = key
        normalized["write_set"] = write_set
        normalized["depends_on"] = [str(d).strip() for d in slice_model.depends_on if str(d).strip()]
        by_key[key] = normalized

    for key, item in by_key.items():
        for dep in item["depends_on"]:
            if dep not in by_key:
                raise EventControlError(f"slice {key} depends on unknown slice key {dep}")
            if dep == key:
                raise EventControlError(f"slice {key} cannot depend on itself")

    # Cycle detection (Kahn/DFS) before mutating Beads
    state: dict[str, int] = {}

    def _visit(node: str) -> None:
        mark = state.get(node, 0)
        if mark == 1:
            raise EventControlError(f"dependency cycle detected involving slice {node}")
        if mark == 2:
            return
        state[node] = 1
        for dep in by_key[node]["depends_on"]:
            _visit(dep)
        state[node] = 2

    for key in by_key:
        _visit(key)

    return graph_id, epic, [by_key[item.key] for item in parsed.slices]


def import_task_graph(
    instance_root: Path,
    bd: str,
    graph_spec: dict[str, Any],
    *,
    state_dir: Path | None = None,
    runner: opl_ledger.Runner | None = None,
) -> dict[str, Any]:
    """Idempotently materialize an Epic + concurrent child slices directly inside Beads/Dolt."""
    graph_id, epic_spec, slices = _validate_graph_spec(graph_spec)
    existing_issues = opl_ledger.list_issues(instance_root, bd, runner=runner)
    by_ref = {
        str(item["external_ref"]): item
        for item in existing_issues
        if isinstance(item, dict) and isinstance(item.get("external_ref"), str)
    }

    epic_ref = f"opl://graph/{graph_id}/epic"
    if epic_ref in by_ref:
        epic_bead = by_ref[epic_ref]
        epic_reused = True
    else:
        epic_meta = {
            "classification": "managed_objective",
            "execution_mode": "aggregate",
            "graph_id": graph_id,
            "remaining": [item["key"] for item in slices],
        }
        epic_bead = opl_ledger.create_issue(
            instance_root,
            bd,
            title=str(epic_spec["title"]).strip(),
            issue_type="epic",
            external_ref=epic_ref,
            labels="opl,graph,aggregate",
            description=str(epic_spec.get("scope") or epic_spec["title"]).strip(),
            metadata=epic_meta,
            priority=_priority_label(epic_spec.get("priority", 1)),
            runner=runner,
        )
        epic_reused = False
    epic_id = str(epic_bead["id"])

    slice_beads: dict[str, dict[str, Any]] = {}
    reused_count = 0
    created_count = 0
    for item in slices:
        key = item["key"]
        s_ref = f"opl://graph/{graph_id}/slice/{key}"
        if s_ref in by_ref:
            slice_beads[key] = by_ref[s_ref]
            reused_count += 1
            continue
        meta: dict[str, Any] = {
            "classification": "managed_objective",
            "execution_mode": str(item.get("execution_mode") or "backlog"),
            "graph_id": graph_id,
            "slice_key": key,
            "write_set": item["write_set"],
            "remaining": [str(item["scope"]).strip()],
            "next_action": str(item["scope"]).strip(),
        }
        if item.get("requirements") is not None:
            meta["opl_execution_requirements"] = item["requirements"]
        if item.get("envelope") is not None:
            meta["opl_execution_envelope"] = item["envelope"]
        if item.get("resumability") is not None:
            meta["opl_resumability"] = item["resumability"]

        created = opl_ledger.create_issue(
            instance_root,
            bd,
            title=str(item["title"]).strip(),
            issue_type="task",
            external_ref=s_ref,
            labels="opl,graph-slice",
            description=str(item["scope"]).strip(),
            metadata=meta,
            priority=_priority_label(item.get("priority", 2)),
            parent=epic_id,
            runner=runner,
        )
        slice_beads[key] = created
        created_count += 1

    dep_edges: list[dict[str, str]] = []
    for item in slices:
        child_bead = slice_beads[item["key"]]
        child_id = str(child_bead["id"])
        existing_deps = {
            str(d.get("depends_on_id"))
            for d in (child_bead.get("dependencies") or [])
            if isinstance(d, dict) and d.get("depends_on_id")
        }
        for dep_key in item["depends_on"]:
            dep_id = str(slice_beads[dep_key]["id"])
            if dep_id not in existing_deps:
                opl_ledger.add_dependency(instance_root, bd, child_id, dep_id, dep_type="blocks", runner=runner)
                dep_edges.append({"slice": child_id, "depends_on": dep_id})

    inbox_dir = state_dir or default_event_state_dir(instance_root)
    emitted = emit_event(
        inbox_dir,
        event_type="human_intake",
        objective_id=epic_id,
        parent_objective_id=epic_id,
        source="cli:graph-import",
        idempotency_key=f"graph-import:{graph_id}",
        payload={
            "signal": "graph_imported",
            "graph_id": graph_id,
            "slice_count": len(slices),
        },
    )
    return {
        "schema": "opl_graph_import_result.v1",
        "graph_id": graph_id,
        "epic": epic_bead,
        "epic_reused": epic_reused,
        "slices": {key: val["id"] for key, val in slice_beads.items()},
        "counts": {
            "total_slices": len(slices),
            "created_slices": created_count,
            "reused_slices": reused_count,
            "dependencies_added": len(dep_edges),
        },
        "dependencies_added": dep_edges,
        "event": emitted["event"],
    }


def _paths_overlap(path_a: str, path_b: str) -> bool:
    parts_a = PurePosixPath(path_a).parts
    parts_b = PurePosixPath(path_b).parts
    prefix_len = min(len(parts_a), len(parts_b))
    return prefix_len > 0 and parts_a[:prefix_len] == parts_b[:prefix_len]


def _write_sets_overlap(ws_a: list[str], ws_b: list[str]) -> list[str]:
    overlaps: list[str] = []
    for a in ws_a:
        for b in ws_b:
            if _paths_overlap(a, b):
                overlaps.append(a if len(a) <= len(b) else b)
    return sorted(set(overlaps))


def _detect_bead_cycles(issue_map: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    color: dict[str, int] = {}

    def _dfs(node_id: str, trail: list[str]) -> None:
        mark = color.get(node_id, 0)
        if mark == 1:
            cycle_start = trail.index(node_id) if node_id in trail else 0
            errors.append(f"dependency cycle detected: {' -> '.join([*trail[cycle_start:], node_id])}")
            return
        if mark == 2:
            return
        color[node_id] = 1
        issue = issue_map.get(node_id) or {}
        for dep in issue.get("dependencies") or []:
            if not isinstance(dep, dict):
                continue
            dep_id = str(dep.get("depends_on_id") or "")
            if dep_id and dep_id in issue_map:
                _dfs(dep_id, [*trail, node_id])
        color[node_id] = 2

    for bid in sorted(issue_map):
        if color.get(bid, 0) == 0:
            _dfs(bid, [])
    return errors


def evaluate_control_turn(
    snapshot: dict[str, Any],
    *,
    root_objective_id: str | None = None,
    pending_events: list[dict[str, Any]] | None = None,
    worktree_ledger: dict[str, Any] | None = None,
    active_leases: dict[str, Any] | None = None,
    local_sessions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stateless logical product controller evaluating one bounded control turn over Beads DAG."""
    issues = [item for item in snapshot.get("issues", []) if isinstance(item, dict) and item.get("id")]
    all_by_id = {str(item["id"]): item for item in issues}

    # Resolve subgraph scope
    if root_objective_id is not None:
        scoped_ids: set[str] = set()
        if root_objective_id in all_by_id:
            scoped_ids.add(root_objective_id)
        changed = True
        while changed:
            changed = False
            for bid, issue in all_by_id.items():
                if bid not in scoped_ids and issue.get("parent") in scoped_ids:
                    scoped_ids.add(bid)
                    changed = True
        scoped_issues = [all_by_id[bid] for bid in sorted(scoped_ids)]
    else:
        scoped_ids = set(all_by_id)
        scoped_issues = [all_by_id[bid] for bid in sorted(scoped_ids)]

    scoped_map = {str(item["id"]): item for item in scoped_issues}
    validation_errors = list(snapshot.get("validation_errors") or [])
    validation_errors.extend(_detect_bead_cycles(scoped_map))

    # Match events for this scope
    relevant_events: list[dict[str, Any]] = []
    for ev in pending_events or []:
        if not isinstance(ev, dict):
            continue
        ev_obj = str(ev.get("objective_id") or "")
        ev_parent = str(ev.get("parent_objective_id") or "")
        if root_objective_id is None or ev_obj in scoped_ids or ev_parent == root_objective_id or ev_obj == root_objective_id:
            relevant_events.append(ev)

    callbacks_processed: list[dict[str, Any]] = []
    completed_callback_ids: set[str] = set()
    blocked_callback_ids: dict[str, dict[str, Any]] = {}
    unknown_callback_ids: set[str] = set()
    needs_agent_reasoning = bool(validation_errors)

    for ev in relevant_events:
        etype = ev.get("event_type")
        obj_id = str(ev.get("objective_id") or "")
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        if etype in {"human_intake", "human_comment", "owner_drift", "executor_lost", "write_set_conflict"}:
            needs_agent_reasoning = True
        if etype == "worker_callback":
            outcome = str(payload.get("outcome") or payload.get("result", {}).get("outcome") or "").strip()
            if not outcome and payload.get("signal") == "thread_changed":
                outcome = "checkpoint"
            entry = {
                "event_id": ev.get("event_id"),
                "objective_id": obj_id,
                "attempt_id": ev.get("attempt_id") or payload.get("attempt_id"),
                "outcome": outcome or "unknown",
            }
            if outcome == "completed":
                completed_callback_ids.add(obj_id)
                entry["action"] = "accept_and_integrate"
                needs_agent_reasoning = True
            elif outcome == "checkpoint":
                entry["action"] = "record_checkpoint_and_continue"
            elif outcome == "blocked":
                blocked_callback_ids[obj_id] = payload
                entry["action"] = "triage_blocker"
                needs_agent_reasoning = True
            else:
                unknown_callback_ids.add(obj_id)
                entry["action"] = "reconcile_read_only"
                needs_agent_reasoning = True
            callbacks_processed.append(entry)

    # Classify each slice in DAG
    fan_out_batch: list[dict[str, Any]] = []
    needs_repair: list[dict[str, Any]] = []
    blocked_or_waiting: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []

    if unknown_callback_ids:
        for obj_id in sorted(unknown_callback_ids):
            recommended_actions.append(
                {
                    "action": "reconcile_read_only",
                    "objective_id": obj_id,
                    "reason": "unknown_worker_outcome_blocks_retry",
                }
            )

    for obj_id in sorted(completed_callback_ids):
        recommended_actions.append(
            {
                "action": "accept_and_integrate",
                "objective_id": obj_id,
                "reason": "worker_slice_completed_pending_canonical_readback",
            }
        )

    counts = {
        "total_nodes": len(scoped_issues),
        "ready_to_dispatch": 0,
        "running": 0,
        "blocked_by_dependency": 0,
        "waiting_user": 0,
        "waiting_external": 0,
        "needs_repair": 0,
        "ready_to_integrate": 0,
        "completed": 0,
    }

    lease_by_task = {
        str(lease.get("owner_task")): lease
        for lease in (active_leases or {}).values()
        if isinstance(lease, dict) and lease.get("owner_task")
    }

    ready_candidates: list[dict[str, Any]] = []
    running_slices: list[dict[str, Any]] = []

    for issue in scoped_issues:
        bid = str(issue["id"])
        meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
        mode = meta.get("execution_mode")
        status = str(issue.get("status") or "")
        write_set = [str(p) for p in (meta.get("write_set") or []) if isinstance(p, str)]

        if mode == "aggregate":
            continue
        if status == "closed":
            counts["completed"] += 1
            continue
        if bid in completed_callback_ids:
            counts["ready_to_integrate"] += 1
            continue
        if bid in unknown_callback_ids:
            counts["needs_repair"] += 1
            needs_repair.append({"objective_id": bid, "action": "reconcile_read_only", "reason": "unknown_outcome"})
            continue

        # Repair-before-proof invariant
        first_blocker = meta.get("first_blocker")
        next_action = str(meta.get("next_action") or "")
        if first_blocker and TEST_OR_WAIT_ONLY_RE.match(next_action):
            counts["needs_repair"] += 1
            needs_agent_reasoning = True
            item = {
                "objective_id": bid,
                "first_blocker": str(first_blocker),
                "action": "direct_fix",
                "reason": "repair_before_proof_invariant",
            }
            needs_repair.append(item)
            recommended_actions.append({"action": "direct_fix", **item})
            continue

        if mode == "waiting_user":
            counts["waiting_user"] += 1
            blocked_or_waiting.append({"objective_id": bid, "state": "waiting_user", "blocker": first_blocker})
            continue
        if mode == "waiting_external" or bid in blocked_callback_ids:
            counts["waiting_external"] += 1
            blocked_or_waiting.append(
                {
                    "objective_id": bid,
                    "state": "waiting_external",
                    "blocker": first_blocker or blocked_callback_ids.get(bid, {}).get("blocker"),
                }
            )
            continue

        live_thread = meta.get("execution_thread")
        if (isinstance(live_thread, str) and live_thread.strip()) or bid in lease_by_task:
            counts["running"] += 1
            carrier = meta.get("execution_carrier")
            if not carrier and isinstance(live_thread, str) and ":" in live_thread:
                prefix = live_thread.split(":", 1)[0].strip()
                if prefix in {"codex", "antigravity", "dsh"}:
                    carrier = prefix
            slice_info: dict[str, Any] = {
                "objective_id": bid,
                "write_set": write_set,
                "owner_id": live_thread or "leased",
            }
            if isinstance(carrier, str) and carrier.strip():
                slice_info["execution_carrier"] = carrier.strip()
            running_slices.append(slice_info)
            continue

        # Check DAG dependencies
        unmet_deps: list[str] = []
        unlocked_via_callback = False
        for dep in issue.get("dependencies") or []:
            if not isinstance(dep, dict):
                continue
            dep_id = str(dep.get("depends_on_id") or "")
            if not dep_id:
                continue
            dep_issue = all_by_id.get(dep_id)
            dep_closed = dep_issue is not None and str(dep_issue.get("status") or "") == "closed"
            if dep_id in completed_callback_ids:
                unlocked_via_callback = True
            elif not dep_closed:
                unmet_deps.append(dep_id)

        if unmet_deps:
            counts["blocked_by_dependency"] += 1
            blocked_or_waiting.append(
                {
                    "objective_id": bid,
                    "state": "blocked_by_dependency",
                    "depends_on": unmet_deps,
                }
            )
            continue

        if validation_errors:
            continue

        counts["ready_to_dispatch"] += 1
        handoff = {
            "schema": "opl_worker_handoff.v1",
            "attempt_id": f"att-{bid}-{uuid.uuid4().hex[:8]}",
            "objective_id": bid,
            "owner_id": str(issue.get("owner") or f"worker:{bid}"),
            "scope": str(meta.get("next_action") or issue.get("title") or bid),
            "input_refs": [f"bead:{bid}"],
            "checkpoint_refs": [],
            "expected_result": "Verified slice artifact or checkpoint with remaining work",
        }
        if write_set:
            handoff["write_set"] = sorted(set(write_set))
        if isinstance(meta.get("opl_execution_envelope"), dict):
            handoff["envelope"] = deepcopy(meta["opl_execution_envelope"])
        if isinstance(meta.get("opl_resumability"), dict):
            handoff["resumability"] = deepcopy(meta["opl_resumability"])
        opl_execution.validate_handoff(handoff)

        reqs = meta.get("opl_execution_requirements")
        preferred_adapter = (
            reqs.get("adapter")
            if isinstance(reqs, dict) and isinstance(reqs.get("adapter"), str)
            else None
        )
        ready_entry = {
            "objective_id": bid,
            "title": issue.get("title"),
            "priority": issue.get("priority", 2),
            "write_set": sorted(set(write_set)),
            "requirements": reqs,
            **({"preferred_adapter": preferred_adapter} if preferred_adapter else {}),
            "unlocked_by_callback": unlocked_via_callback,
            "handoff": handoff,
        }
        ready_candidates.append(ready_entry)
        fan_out_batch.append(ready_entry)
        recommended_actions.append({"action": "dispatch_slice", "objective_id": bid, "attempt_id": handoff["attempt_id"]})

    # Write-set overlap detection across ready + running slices -> integration_queue
    integration_queue: list[dict[str, Any]] = []
    all_parallel = [*ready_candidates, *running_slices]
    for idx, left in enumerate(all_parallel):
        for right in all_parallel[idx + 1 :]:
            overlaps = _write_sets_overlap(left["write_set"], right["write_set"])
            if overlaps:
                integration_queue.append(
                    {
                        "objectives": sorted([left["objective_id"], right["objective_id"]]),
                        "overlapping_paths": overlaps,
                        "integration_policy": "serialized_critical_section",
                    }
                )
    if isinstance(worktree_ledger, dict):
        for overlap in worktree_ledger.get("integration_overlaps", []) or []:
            if isinstance(overlap, dict):
                integration_queue.append(
                    {
                        "objectives": sorted(map(str, overlap.get("objectives") or [overlap.get("objective_id") or "unknown"])),
                        "overlapping_paths": list(overlap.get("paths") or []),
                        "integration_policy": "serialized_critical_section",
                    }
                )
    if isinstance(local_sessions, dict) and ready_candidates:
        instance_ws = snapshot.get("workspace_label") or (
            Path(str(snapshot["instance"])).name if snapshot.get("instance") else None
        )
        seen_guard: set[tuple[str, str]] = set()
        for occ in local_sessions.get("active_workspace_occupants", []) or []:
            if not isinstance(occ, dict):
                continue
            ws_label = str(occ.get("workspace_label") or "").strip()
            if not ws_label:
                continue
            if instance_ws and ws_label != str(instance_ws):
                continue
            occ_ref = str(occ.get("session_ref") or f"{occ.get('carrier') or 'local'}:active")
            occ_bead = occ.get("bound_bead_id")
            for cand in ready_candidates:
                if occ_bead and str(occ_bead) == cand["objective_id"]:
                    continue
                guard_key = (cand["objective_id"], occ_ref)
                if guard_key in seen_guard:
                    continue
                seen_guard.add(guard_key)
                integration_queue.append(
                    {
                        "objectives": [cand["objective_id"]],
                        "overlapping_paths": cand["write_set"] or [ws_label],
                        "integration_policy": "worktree_required_active_local_session",
                        "active_session": {
                            "session_ref": occ_ref,
                            "carrier": occ.get("carrier"),
                            "harness": occ.get("harness"),
                            "workspace_label": ws_label,
                            "bound_bead_id": occ_bead,
                        },
                    }
                )

    return {
        "schema": CONTROL_TURN_SCHEMA,
        "root_objective_id": root_objective_id,
        "trigger_event_ids": [str(ev.get("event_id")) for ev in relevant_events if ev.get("event_id")],
        "graph_summary": counts,
        "callbacks_processed": callbacks_processed,
        "fan_out_batch": fan_out_batch,
        "integration_queue": integration_queue,
        "needs_repair": needs_repair,
        "blocked_or_waiting": blocked_or_waiting,
        "needs_agent_reasoning": needs_agent_reasoning,
        "recommended_actions": recommended_actions,
        "validation_errors": validation_errors,
    }


def _collect_ledger_snapshot(
    instance_root: Path,
    bd: str,
    *,
    runner: opl_ledger.Runner | None = None,
) -> dict[str, Any]:
    ready = opl_ledger.ready(instance_root, bd, runner=runner)
    issues = opl_ledger.list_issues(
        instance_root,
        bd,
        statuses=("open", "in_progress", "blocked", "deferred"),
        runner=runner,
    )
    ready_ids = sorted(str(item["id"]) for item in ready if isinstance(item, dict) and item.get("id"))
    return {
        "schema": "opl_flow_supervisor_snapshot.v1",
        "instance": str(instance_root),
        "ready_ids": ready_ids,
        "issues": issues,
        "validation_errors": [],
    }


def _obs_item_key(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("thread_id") or item.get("conversationId") or item.get("session_id") or "").strip()


def _merge_discovered_observations(
    obs: dict[str, Any],
    bound: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    merged = dict(obs)
    for key in ("threads", "antigravity_conversations", "dsh_sessions"):
        existing = [item for item in (merged.get(key) or []) if isinstance(item, dict)]
        seen = {_obs_item_key(item) for item in existing if _obs_item_key(item)}
        combined = list(existing)
        for item in bound.get(key, []):
            item_key = _obs_item_key(item)
            if item_key and item_key in seen:
                continue
            if item_key:
                seen.add(item_key)
            combined.append(item)
        if combined:
            merged[key] = combined
    return merged


def router_tick(
    instance_root: Path,
    bd: str,
    *,
    state_dir: Path | None = None,
    cursor_path: Path | None = None,
    observations: dict[str, Any] | None = None,
    worktree_ledger: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    snapshot_fn: Callable[[], dict[str, Any]] | None = None,
    control_hook_argv: list[str] | None = None,
    control_hook_resolver: Callable[[dict[str, Any], str | None, list[dict[str, Any]], dict[str, Any]], tuple[str, list[str]]] | None = None,
    auto_discover_sessions: bool = False,
    discovery_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    local_sessions: dict[str, Any] | None = None,
    dry_run: bool = False,
    runner: opl_ledger.Runner | None = None,
) -> dict[str, Any]:
    """Execute one bounded event-driven Router tick. Exits idle with 0 agent turns if no events."""
    inbox_dir = state_dir or default_event_state_dir(instance_root)
    c_path = cursor_path or opl_supervisor.default_cursor_path(instance_root)
    cursor = opl_supervisor.load_cursor(c_path)
    snap = snapshot if snapshot is not None else (snapshot_fn() if snapshot_fn else _collect_ledger_snapshot(instance_root, bd, runner=runner))
    obs = dict(observations or {})

    discovered_sessions: dict[str, Any] | None = local_sessions
    if discovered_sessions is None and auto_discover_sessions:
        discovered_sessions = (
            discovery_fn(snap)
            if discovery_fn is not None
            else opl_session_discovery.discover_local_sessions(issues=snap.get("issues"))
        )
    if discovered_sessions is not None:
        obs = _merge_discovered_observations(obs, opl_session_discovery.build_bound_observations(discovered_sessions))

    existing_pending = list_events(inbox_dir, status="pending") + list_events(inbox_dir, status="failed_retryable")
    plan = opl_supervisor.detect_changes(
        snap,
        cursor=cursor,
        threads=obs.get("threads"),
        antigravity_conversations=obs.get("antigravity_conversations"),
        dsh_sessions=obs.get("dsh_sessions"),
        linear_issues=obs.get("linear_issues"),
        linear_comments=obs.get("linear_comments"),
        pending_events=existing_pending,
        worktree_ledger=worktree_ledger,
        authorized_accounts=obs.get("authorized_accounts"),
        now=obs.get("now"),
    )

    emitted_count = 0
    if not dry_run:
        for ev in plan["events"]:
            if "event_id" in ev and ev.get("status"):
                continue  # Already in inbox
            res = emit_event(
                inbox_dir,
                event_type=ev["event_type"],
                objective_id=ev["objective_id"],
                parent_objective_id=ev.get("parent_objective_id"),
                attempt_id=ev.get("attempt_id"),
                source=ev["source"],
                idempotency_key=ev["idempotency_key"],
                payload=ev.get("payload"),
                now=ev.get("created_at"),
            )
            if not res["deduplicated"]:
                emitted_count += 1
        opl_supervisor.save_cursor(c_path, plan["next_cursor"])

    pending_now = (
        plan["events"]
        if dry_run
        else list_events(inbox_dir, status="pending") + list_events(inbox_dir, status="failed_retryable")
    )

    sanitized_sessions = (
        opl_session_discovery.sanitize_sessions_for_projection(discovered_sessions)
        if discovered_sessions is not None
        else None
    )

    if not pending_now and not plan["validation_errors"] and not plan["linear_actions"] and not plan["obsidian_actions"]:
        return {
            "schema": "opl_router_tick.v1",
            "status": "idle",
            "wake_agent": False,
            "emitted_events": 0,
            "turns": [],
            "hook_invoked": False,
            **({"sessions": sanitized_sessions} if sanitized_sessions is not None else {}),
        }

    # Group events by root objective
    issue_parent = {
        str(item["id"]): str(item.get("parent") or item["id"])
        for item in snap.get("issues", [])
        if isinstance(item, dict) and item.get("id")
    }
    by_root: dict[str, list[dict[str, Any]]] = {}
    for ev in pending_now:
        obj = str(ev.get("objective_id") or "")
        root = str(ev.get("parent_objective_id") or issue_parent.get(obj) or obj or "global")
        by_root.setdefault(root, []).append(ev)

    turns: list[dict[str, Any]] = []
    hook_invoked = False
    hook_results: list[dict[str, Any]] = []

    if dry_run or (not control_hook_argv and control_hook_resolver is None):
        for root_id, root_events in sorted(by_root.items()):
            turns.append(
                evaluate_control_turn(
                    snap,
                    root_objective_id=root_id if root_id in issue_parent else None,
                    pending_events=root_events,
                    worktree_ledger=worktree_ledger,
                    local_sessions=discovered_sessions,
                )
            )
    else:
        for root_id in sorted(by_root):
            target_objectives = {str(ev.get("objective_id") or "") for ev in by_root[root_id]}
            claimed = claim_events(
                inbox_dir,
                consumer_id=f"router:{root_id}",
                objective_ids=target_objectives,
            )
            claimed_events = claimed["events"]
            if not claimed_events:
                continue
            scoped_root = root_id if root_id in issue_parent else None
            turn_plan = evaluate_control_turn(
                snap,
                root_objective_id=scoped_root,
                pending_events=claimed_events,
                worktree_ledger=worktree_ledger,
                local_sessions=discovered_sessions,
            )
            turns.append(turn_plan)
            if control_hook_resolver is not None:
                resolved_bridge, exec_argv = control_hook_resolver(snap, scoped_root, claimed_events, turn_plan)
            else:
                resolved_bridge, exec_argv = None, control_hook_argv
            assert exec_argv is not None
            hook_invoked = True
            proc = subprocess.run(
                exec_argv,
                input=json.dumps(turn_plan, ensure_ascii=False),
                capture_output=True,
                text=True,
                check=False,
            )
            event_ids = [ev["event_id"] for ev in claimed_events]
            if proc.returncode == 0:
                ack_events(inbox_dir, event_ids=event_ids, claim_token=claimed["claim_token"], outcome="acked")
                hook_results.append(
                    {
                        "root_objective_id": root_id,
                        "status": "acked",
                        "event_count": len(event_ids),
                        **({"bridge": resolved_bridge} if resolved_bridge is not None else {}),
                    }
                )
            else:
                ack_events(
                    inbox_dir,
                    event_ids=event_ids,
                    claim_token=claimed["claim_token"],
                    outcome="failed_retryable",
                    error=(proc.stderr or proc.stdout or f"hook exit {proc.returncode}").strip(),
                )
                hook_results.append(
                    {
                        "root_objective_id": root_id,
                        "status": "failed_retryable",
                        "returncode": proc.returncode,
                        **({"bridge": resolved_bridge} if resolved_bridge is not None else {}),
                    }
                )

    return {
        "schema": "opl_router_tick.v1",
        "status": "dispatched" if hook_invoked else "events_pending",
        "wake_agent": True,
        "emitted_events": emitted_count,
        "turns": turns,
        "hook_invoked": hook_invoked,
        "hook_results": hook_results,
        "supervisor_plan": plan,
        **({"sessions": sanitized_sessions} if sanitized_sessions is not None else {}),
    }


def router_watch(
    instance_root: Path,
    bd: str,
    *,
    interval_seconds: float = 15.0,
    max_iterations: int | None = None,
    state_dir: Path | None = None,
    cursor_path: Path | None = None,
    snapshot_fn: Callable[[], dict[str, Any]] | None = None,
    control_hook_argv: list[str] | None = None,
    control_hook_resolver: Callable[[dict[str, Any], str | None, list[dict[str, Any]], dict[str, Any]], tuple[str, list[str]]] | None = None,
    auto_discover_sessions: bool = True,
    discovery_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    runner: opl_ledger.Runner | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Bounded event-driven foreground watcher; zero LLM turns during idle ticks."""
    stop_requested = False

    def _handle_signal(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    old_sigint = signal.getsignal(signal.SIGINT)
    old_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    except ValueError:
        pass  # Non-main thread in tests

    ticks: list[dict[str, Any]] = []
    iteration = 0
    try:
        while not stop_requested:
            if max_iterations is not None and iteration >= max_iterations:
                break
            iteration += 1
            tick_result = router_tick(
                instance_root,
                bd,
                state_dir=state_dir,
                cursor_path=cursor_path,
                snapshot_fn=snapshot_fn,
                control_hook_argv=control_hook_argv,
                control_hook_resolver=control_hook_resolver,
                auto_discover_sessions=auto_discover_sessions,
                discovery_fn=discovery_fn,
                runner=runner,
            )
            ticks.append(
                {
                    "iteration": iteration,
                    "status": tick_result["status"],
                    "wake_agent": tick_result["wake_agent"],
                    "emitted_events": tick_result["emitted_events"],
                    "turn_count": len(tick_result["turns"]),
                }
            )
            if max_iterations is not None and iteration >= max_iterations:
                break
            if stop_requested:
                break
            sleep_fn(interval_seconds)
    finally:
        try:
            signal.signal(signal.SIGINT, old_sigint)
            signal.signal(signal.SIGTERM, old_sigterm)
        except ValueError:
            pass

    return {
        "schema": "opl_router_watch.v1",
        "iterations": iteration,
        "stopped_by_signal": stop_requested,
        "ticks": ticks,
    }


def list_inbox_summary(
    snapshot: dict[str, Any],
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Unified human decision & intake inbox view."""
    issues = [item for item in snapshot.get("issues", []) if isinstance(item, dict) and item.get("id")]
    needs_action: list[dict[str, Any]] = []
    safe_to_archive: list[dict[str, Any]] = []
    active_objectives: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []

    for issue in issues:
        meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
        mode = meta.get("execution_mode")
        status = str(issue.get("status") or "")
        remaining = meta.get("remaining") if isinstance(meta.get("remaining"), list) else []
        reqs = meta.get("opl_execution_requirements") if isinstance(meta.get("opl_execution_requirements"), dict) else {}
        preferred_adapter = reqs.get("adapter") if isinstance(reqs.get("adapter"), str) else None
        carrier = meta.get("execution_carrier")
        if not carrier and isinstance(meta.get("execution_thread"), str) and ":" in str(meta.get("execution_thread")):
            prefix = str(meta.get("execution_thread")).split(":", 1)[0].strip()
            if prefix in {"codex", "antigravity", "dsh"}:
                carrier = prefix
        entry = {
            "bead_id": issue["id"],
            "title": issue.get("title"),
            "status": status,
            "execution_mode": mode,
            "first_blocker": meta.get("first_blocker"),
            "next_action": meta.get("next_action"),
            "remaining": remaining,
            **({"execution_carrier": str(carrier).strip()} if isinstance(carrier, str) and carrier.strip() else {}),
            **({"preferred_adapter": preferred_adapter} if preferred_adapter else {}),
        }
        proj = opl_supervisor.project_title_prefix(issue)
        if proj["prefix"] == "SAFE_TO_ARCHIVE":
            safe_to_archive.append({**entry, "archive_performed": False, "user_approval_required": True})
        elif mode == "waiting_user":
            needs_action.append(entry)
        elif mode == "waiting_external":
            blocked.append(entry)
        elif mode == "backlog":
            backlog.append(entry)
        elif mode == "active" or meta.get("execution_thread"):
            active_objectives.append(entry)

    pending_events = list_events(state_dir, status="pending") if state_dir is not None else []
    return {
        "schema": "opl_human_inbox.v1",
        "needs_action": needs_action,
        "safe_to_archive": safe_to_archive,
        "active_objectives": active_objectives,
        "blocked": blocked,
        "backlog": backlog,
        "pending_events": pending_events,
    }


def approve_archive(
    instance_root: Path,
    bd: str,
    bead_id: str,
    *,
    approved_by: str,
    runner: opl_ledger.Runner | None = None,
) -> dict[str, Any]:
    """Record explicit fresh human archive approval only after terminal evidence & remaining=[] check."""
    if not approved_by or not str(approved_by).strip():
        raise EventControlError("approved_by is required for explicit archive approval")
    try:
        opl_ledger.pull(instance_root, bd, runner=runner)
        issue = opl_ledger.read_issue(instance_root, bd, bead_id, runner=runner)
    except opl_ledger.LedgerError as exc:
        raise EventControlError(str(exc)) from exc

    meta = deepcopy(issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {})
    classification = meta.get("classification") or meta.get("task_lifecycle_class")
    remaining = meta.get("remaining") if isinstance(meta.get("remaining"), list) else []
    if classification != "managed_objective":
        raise EventControlError(f"cannot approve archive for non-managed class: {classification!r}")
    if issue.get("status") != "closed":
        raise EventControlError(f"Bead {bead_id} is not closed (status={issue.get('status')!r})")
    if remaining:
        raise EventControlError(f"Bead {bead_id} still has remaining work")

    meta["archive_approved"] = True
    meta["archive_approved_by"] = str(approved_by).strip()
    meta["archive_approved_at"] = _iso_utc(_utc_now())
    try:
        updated = opl_ledger.apply_metadata(instance_root, bd, issue, meta, runner=runner)
    except opl_ledger.LedgerError as exc:
        raise EventControlError(str(exc)) from exc
    return {
        "schema": "opl_archive_approval_receipt.v1",
        "bead_id": bead_id,
        "archive_approved": True,
        "approved_by": meta["archive_approved_by"],
        "approved_at": meta["archive_approved_at"],
        "bead": updated,
    }


def default_codex_control_hook(
    *,
    instance_root: Path,
    flow_root: Path | None = None,
    codex_bin: str | None = None,
    model: str | None = None,
    sandbox: str = "workspace-write",
    dry_run: bool = False,
) -> list[str]:
    """Build the default subprocess hook invoking opl_codex_bridge.py in control mode."""
    resolved_flow = (flow_root or Path(__file__).resolve().parents[1]).expanduser().resolve()
    return [
        sys.executable,
        str(resolved_flow / "scripts/opl_codex_bridge.py"),
        "control",
        "--instance",
        str(instance_root.expanduser().resolve()),
        "--sandbox",
        sandbox,
        *(["--codex-bin", codex_bin] if codex_bin else []),
        *(["--model", model] if model else []),
        *(["--dry-run"] if dry_run else []),
    ]


def default_antigravity_control_hook(
    *,
    instance_root: Path,
    flow_root: Path | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str = "workspace-write",
    dry_run: bool = False,
) -> list[str]:
    """Build the subprocess hook invoking opl_antigravity_bridge.py in control mode."""
    resolved_flow = (flow_root or Path(__file__).resolve().parents[1]).expanduser().resolve()
    return [
        sys.executable,
        str(resolved_flow / "scripts/opl_antigravity_bridge.py"),
        "control",
        "--instance",
        str(instance_root.expanduser().resolve()),
        "--sandbox",
        sandbox,
        *(["--agy-bin", agy_bin] if agy_bin else []),
        *(["--model", model] if model else []),
        *(["--effort", effort] if effort else []),
        *(["--dry-run"] if dry_run else []),
    ]


def default_control_hook(
    *,
    bridge: str = "codex",
    instance_root: Path,
    flow_root: Path | None = None,
    codex_bin: str | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str = "workspace-write",
    dry_run: bool = False,
) -> list[str]:
    """Build the control-turn subprocess hook for the selected carrier bridge."""
    if bridge == "auto":
        raise EventControlError("bridge='auto' requires build_auto_control_hook_resolver() for per-turn dispatch")
    if bridge == "codex":
        return default_codex_control_hook(
            instance_root=instance_root,
            flow_root=flow_root,
            codex_bin=codex_bin,
            model=model,
            sandbox=sandbox,
            dry_run=dry_run,
        )
    if bridge == "antigravity":
        return default_antigravity_control_hook(
            instance_root=instance_root,
            flow_root=flow_root,
            agy_bin=agy_bin,
            model=model,
            effort=effort,
            sandbox=sandbox,
            dry_run=dry_run,
        )
    raise EventControlError(f"unsupported control bridge: {bridge!r}")


def _cli_available(binary_name: str, explicit: str | None) -> bool:
    candidate = explicit or binary_name
    path_candidate = Path(candidate).expanduser()
    if path_candidate.is_file():
        return True
    return shutil.which(candidate) is not None


def available_control_bridges(*, codex_bin: str | None = None, agy_bin: str | None = None) -> list[str]:
    """Return locally available control-turn bridges in preference order."""
    found: list[str] = []
    if _cli_available("codex", codex_bin):
        found.append("codex")
    if _cli_available("agy", agy_bin):
        found.append("antigravity")
    return found


def _carrier_from_issue(issue: dict[str, Any]) -> str | None:
    meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    carrier = str(meta.get("execution_carrier") or "").strip().lower()
    if carrier in {"codex", "antigravity"}:
        return carrier
    exec_thread = str(meta.get("execution_thread") or "").strip().lower()
    if exec_thread.startswith("antigravity:"):
        return "antigravity"
    if exec_thread.startswith("codex:"):
        return "codex"
    reqs = meta.get("opl_execution_requirements") if isinstance(meta.get("opl_execution_requirements"), dict) else {}
    adapter = str(reqs.get("adapter") or "").strip().lower()
    if adapter == "local-antigravity":
        return "antigravity"
    if adapter in {"local-codex", "remote-codex"}:
        return "codex"
    return None


def resolve_control_bridge_for_turn(
    snapshot: dict[str, Any],
    *,
    root_objective_id: str | None = None,
    events: list[dict[str, Any]] | None = None,
    turn_plan: dict[str, Any] | None = None,
    available_bridges: Iterable[str] | None = None,
    default_bridge: str = "codex",
) -> str:
    """Dynamically select the control-turn bridge ('codex' or 'antigravity') for one objective scope."""
    avail = [
        b
        for b in (available_bridges if available_bridges is not None else ("codex", "antigravity"))
        if b in {"codex", "antigravity"}
    ]
    if not avail:
        avail = [default_bridge] if default_bridge in {"codex", "antigravity"} else ["codex"]

    preferred: str | None = None
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        obj_id = str(ev.get("objective_id") or "").lower()
        src = str(ev.get("source") or "").lower()
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        ev_carrier = str(payload.get("execution_carrier") or payload.get("carrier") or "").strip().lower()
        if ev_carrier in {"codex", "antigravity"}:
            preferred = ev_carrier
            break
        if obj_id.startswith("antigravity:") or src.startswith("antigravity:"):
            preferred = "antigravity"
            break
        if obj_id.startswith(("thread:", "codex:")) or src.startswith("codex:"):
            preferred = "codex"
            break

    if preferred is None:
        issues = [item for item in snapshot.get("issues", []) if isinstance(item, dict) and item.get("id")]
        by_id = {str(item["id"]): item for item in issues}
        if root_objective_id and root_objective_id in by_id:
            preferred = _carrier_from_issue(by_id[root_objective_id])
            if preferred is None:
                scoped_ids = {root_objective_id}
                changed = True
                while changed:
                    changed = False
                    for bid, item in by_id.items():
                        if bid not in scoped_ids and str(item.get("parent") or "") in scoped_ids:
                            scoped_ids.add(bid)
                            changed = True
                child_carriers = {
                    c for bid in sorted(scoped_ids) if (c := _carrier_from_issue(by_id[bid])) is not None
                }
                if len(child_carriers) == 1:
                    preferred = next(iter(child_carriers))

    if preferred is None and isinstance(turn_plan, dict):
        batch_carriers: set[str] = set()
        for entry in turn_plan.get("fan_out_batch", []) or []:
            if not isinstance(entry, dict):
                continue
            adapter = str(entry.get("preferred_adapter") or "").strip().lower()
            if adapter == "local-antigravity":
                batch_carriers.add("antigravity")
            elif adapter in {"local-codex", "remote-codex"}:
                batch_carriers.add("codex")
        if len(batch_carriers) == 1:
            preferred = next(iter(batch_carriers))

    if preferred in avail:
        return str(preferred)
    if default_bridge in avail:
        return default_bridge
    return avail[0]


def build_auto_control_hook_resolver(
    *,
    instance_root: Path,
    flow_root: Path | None = None,
    codex_bin: str | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str = "workspace-write",
    dry_run: bool = False,
    available_bridges: Iterable[str] | None = None,
    default_bridge: str = "codex",
) -> Callable[[dict[str, Any], str | None, list[dict[str, Any]], dict[str, Any]], tuple[str, list[str]]]:
    """Create a per-turn resolver routing Codex & AntiGravity objectives within one Router process."""
    avail = (
        [b for b in available_bridges if b in {"codex", "antigravity"}]
        if available_bridges is not None
        else available_control_bridges(codex_bin=codex_bin, agy_bin=agy_bin)
    )
    if not avail:
        avail = ["codex", "antigravity"]

    hooks: dict[str, list[str]] = {}
    if "codex" in avail:
        hooks["codex"] = default_codex_control_hook(
            instance_root=instance_root,
            flow_root=flow_root,
            codex_bin=codex_bin,
            model=model,
            sandbox=sandbox,
            dry_run=dry_run,
        )
    if "antigravity" in avail:
        hooks["antigravity"] = default_antigravity_control_hook(
            instance_root=instance_root,
            flow_root=flow_root,
            agy_bin=agy_bin,
            model=model,
            effort=effort,
            sandbox=sandbox,
            dry_run=dry_run,
        )

    def _resolve(
        snapshot: dict[str, Any],
        root_objective_id: str | None,
        events: list[dict[str, Any]],
        turn_plan: dict[str, Any],
    ) -> tuple[str, list[str]]:
        chosen = resolve_control_bridge_for_turn(
            snapshot,
            root_objective_id=root_objective_id,
            events=events,
            turn_plan=turn_plan,
            available_bridges=avail,
            default_bridge=default_bridge,
        )
        return chosen, list(hooks[chosen])

    return _resolve


def format_inbox_human(
    summary: dict[str, Any],
    *,
    service_status: dict[str, Any] | None = None,
    local_sessions: dict[str, Any] | None = None,
) -> str:
    """Render a clean, human-centric Chinese status and decision dashboard."""
    lines: list[str] = []
    if service_status is not None:
        running = bool(service_status.get("running"))
        installed = bool(service_status.get("installed"))
        state_text = "运行中（无事件零消耗）" if running else ("已安装未启动" if installed else "未启用后台监听")
        bridge = service_status.get("bridge")
        bridge_label = {
            "auto": "Auto (Codex + AntiGravity + OPL DSH)",
            "codex": "Codex",
            "antigravity": "AntiGravity",
            "custom": "Custom",
        }.get(str(bridge or ""), "")
        bridge_hint = f" | 桥接: {bridge_label}" if bridge_label else ""
        lines.append(f"【事件引擎】{state_text}{bridge_hint} | 服务: {service_status.get('label', 'n/a')}")
        lines.append(f"  待处理事件: {len(summary.get('pending_events', []))} 条")
        lines.append("")

    needs_action = summary.get("needs_action") or []
    lines.append(f"【需要你拍板 (NEEDS_ACTION: {len(needs_action)})】")
    if not needs_action:
        lines.append("  暂无")
    else:
        for item in needs_action:
            blocker = item.get("first_blocker") or item.get("next_action") or "等待你的确认"
            lines.append(f"  - [{item['bead_id']}] {item.get('title')} ({blocker})")
            lines.append(f"    答复指示: opl-flow send --to {item['bead_id']} \"你的决定\"")
    lines.append("")

    safe = summary.get("safe_to_archive") or []
    lines.append(f"【已完成待你验收归档 (SAFE_TO_ARCHIVE: {len(safe)})】")
    if not safe:
        lines.append("  暂无")
    else:
        for item in safe:
            lines.append(f"  - [{item['bead_id']}] {item.get('title')} (remaining=[], 未自动归档)")
            lines.append(f"    确认归档: opl-flow approve {item['bead_id']}")
    lines.append("")

    active = summary.get("active_objectives") or []
    lines.append(f"【正在推进 (ACTIVE: {len(active)})】")
    if not active:
        lines.append("  暂无")
    else:
        for item in active:
            nxt = item.get("next_action") or "推进中"
            lines.append(f"  - [{item['bead_id']}] {item.get('title')} -> {nxt}")
    lines.append("")

    blocked = summary.get("blocked") or []
    backlog = summary.get("backlog") or []
    lines.append(f"【外部阻塞 / 待办队列 (BLOCKED: {len(blocked)} | BACKLOG: {len(backlog)})】")
    for item in blocked:
        lines.append(f"  - [BLOCKED] [{item['bead_id']}] {item.get('title')} ({item.get('first_blocker') or '外部依赖'})")
    for item in backlog:
        lines.append(f"  - [BACKLOG] [{item['bead_id']}] {item.get('title')}")
    if not blocked and not backlog:
        lines.append("  暂无")
    return "\n".join(lines)


def format_control_turn_human(plan: dict[str, Any]) -> str:
    """Render a human-readable summary of a logical controller evaluation turn."""
    gs = plan.get("graph_summary") or {}
    lines = [
        f"【控制面评估】目标根: {plan.get('root_objective_id') or '全局'}",
        f"  就绪可扇出: {gs.get('ready_to_dispatch', 0)} | 运行中: {gs.get('running', 0)} | "
        f"待修断点: {gs.get('needs_repair', 0)} | 阻塞/等待: {gs.get('blocked_by_dependency', 0) + gs.get('waiting_user', 0) + gs.get('waiting_external', 0)} | "
        f"已完成: {gs.get('completed', 0)}",
    ]
    if plan.get("fan_out_batch"):
        lines.append("  可立即并发切片:")
        for item in plan["fan_out_batch"]:
            lines.append(f"    - [{item['objective_id']}] {item.get('title')} (写集: {', '.join(item.get('write_set') or ['未限定'])})")
    if plan.get("integration_queue"):
        lines.append("  写集重叠（开发并行、合入串行）:")
        for overlap in plan["integration_queue"]:
            lines.append(f"    - {', '.join(overlap.get('objectives', []))} @ {', '.join(overlap.get('overlapping_paths', []))}")
    if plan.get("needs_repair"):
        lines.append("  优先修断点 (Repair-Before-Proof):")
        for rep in plan["needs_repair"]:
            lines.append(f"    - [{rep['objective_id']}] {rep.get('first_blocker')}")
    if plan.get("validation_errors"):
        lines.append("  控制面校验告警:")
        for err in plan["validation_errors"]:
            lines.append(f"    - {err}")
    return "\n".join(lines)
