"""Lease store validation, locking, acquire/renew/release records, and node selection."""

from __future__ import annotations

from typing import Annotated, Any, Iterator, Literal
from pathlib import Path
import contextlib
import datetime as dt
import secrets
import uuid
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
from . import fleet_common
from .fleet_common import ADMISSION_FIELDS, ADMISSION_OPTIONAL_FIELDS, COMMIT_PATTERN, FleetError, LEASE_OPTIONAL_FIELDS, LEASE_PHASES, LEASE_REQUIRED_FIELDS, LEASE_WORKLOAD_CLASSES, OWNER_ID_PATTERN, PREEMPTIBLE_WORKLOAD_CLASSES, PROTECTED_WORKLOAD_CLASSES, ROLE_PATTERN, STATE_ROOT, dispatch_adapter, normalize_node_id, parse_utc, utc_now
from .fleet_features import gpu_profiles, inventory_is_fresh, matching_gpus, node_features

try:
    from .. import opl_state_store as state_store
except (ImportError, ValueError):  # Direct script execution.
    import opl_state_store as state_store


def lease_paths(state_root: Path | None = None) -> tuple[Path, Path]:
    root = state_root or STATE_ROOT
    db_path, lock_path, _ = state_store.lease_db_paths(root)
    return db_path, lock_path

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

class _AdmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checked_at: Any
    inventory_age_seconds: Annotated[StrictInt, Field(ge=0)]
    requirements: list[Annotated[StrictStr, Field(pattern=r"^[a-z0-9-]{1,40}$")]]
    min_memory_gb: Annotated[StrictInt, Field(ge=0)]
    power_ok: StrictBool
    storage_ok: StrictBool
    thermal_ok: StrictBool
    interactive_busy: StrictBool
    busy: StrictBool
    work_volume_ready: StrictBool
    gpu_api: Literal["any", "cuda", "metal"] = "any"
    min_gpu_memory_gb: Annotated[StrictInt, Field(ge=0)] = 0
    gpu_model: Annotated[StrictStr, Field(min_length=1, max_length=120, pattern=r"^[^\x00\r\n]+$")] | None = None

    @field_validator("checked_at")
    @classmethod
    def _check_ts(cls, value: Any) -> Any:
        parse_utc(value)
        return value

    @field_validator("requirements")
    @classmethod
    def _sorted_unique(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("lease admission is invalid")
        return value


class _WorkerBindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: StrictStr
    objective_id: StrictStr
    owner_id: StrictStr
    handoff_sha256: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]

    @field_validator("attempt_id", "objective_id", "owner_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lease worker binding is invalid")
        return value


class _LeaseAuditEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["acquire", "renew", "release", "reap", "preempt"]
    at: Any
    node_id: StrictStr
    lease_id: Any
    generation: Annotated[StrictInt, Field(ge=1)]
    reason: Annotated[StrictStr, Field(max_length=120)]

    @field_validator("node_id")
    @classmethod
    def _valid_node(cls, value: str) -> str:
        if normalize_node_id(value) != value:
            raise ValueError("lease audit event is invalid")
        return value

    @field_validator("at")
    @classmethod
    def _valid_at(cls, value: Any) -> Any:
        parse_utc(value)
        return value


class _LeaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: Any
    generation: Annotated[StrictInt, Field(ge=1)]
    nonce: Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{32}$")]
    node_id: StrictStr
    owner_task: Any
    owner_thread: Any
    owner_run: Any
    role: Any
    workload_class: str
    priority: Any
    preemptible: Any
    phase: str
    acquired_at: Any
    expires_at: Any
    control_commit: Annotated[StrictStr, Field(pattern=COMMIT_PATTERN.pattern)]
    admission: _AdmissionModel
    dispatch_adapter: StrictStr = "lease-only"
    worker_binding: _WorkerBindingModel | None = None

    @model_validator(mode="after")
    def _check_policy(self) -> "_LeaseModel":
        if self.worker_binding is not None and self.worker_binding.objective_id != self.owner_task:
            raise ValueError("lease worker binding is invalid")
        dispatch_adapter(self.dispatch_adapter)
        try:
            uuid.UUID(str(self.lease_id))
        except ValueError as exc:
            raise ValueError("lease id is invalid") from exc
        if normalize_node_id(self.node_id) != self.node_id:
            raise ValueError("lease identity is invalid")
        validate_owner_id(self.owner_task, "owner task", required=True)
        validate_owner_id(self.owner_thread, "owner thread")
        validate_owner_id(self.owner_run, "owner run")
        validate_role(self.role)
        if (
            self.workload_class not in LEASE_WORKLOAD_CLASSES
            or self.phase not in LEASE_PHASES
            or not isinstance(self.priority, int)
            or isinstance(self.priority, bool)
            or not 0 <= self.priority <= 1000
            or not isinstance(self.preemptible, bool)
            or (self.preemptible and self.workload_class not in PREEMPTIBLE_WORKLOAD_CLASSES)
        ):
            raise ValueError("lease workload policy is invalid")
        if self.workload_class in PROTECTED_WORKLOAD_CLASSES and (not self.owner_thread or not self.owner_run):
            raise ValueError("protected lease requires owner thread and owner run")
        if parse_utc(self.expires_at) <= parse_utc(self.acquired_at):
            raise ValueError("lease expiry is invalid")
        return self


def validate_admission(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not ADMISSION_FIELDS.issubset(payload) or set(payload) - ADMISSION_FIELDS - ADMISSION_OPTIONAL_FIELDS:
        raise FleetError("lease admission fields are invalid")
    payload.setdefault("gpu_api", "any")
    payload.setdefault("min_gpu_memory_gb", 0)
    payload.setdefault("gpu_model", None)
    fleet_common.runtime.validate_model(_AdmissionModel, payload, error_cls=FleetError, message="lease admission is invalid")
    return payload


def validate_lease(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not LEASE_REQUIRED_FIELDS.issubset(payload) or set(payload) - LEASE_REQUIRED_FIELDS - LEASE_OPTIONAL_FIELDS:
        raise FleetError("lease fields are invalid")
    payload.setdefault("dispatch_adapter", "lease-only")
    if "worker_binding" in payload and payload["worker_binding"] is None:
        raise FleetError("lease worker binding is invalid")
    fleet_common.runtime.validate_model(_LeaseModel, payload, error_cls=FleetError)
    validate_admission(payload["admission"])
    return payload


def validate_lease_store(payload: dict[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "generation", "leases", "audit"}
        or payload.get("schema") != "codex_fleet_leases.v2"
        or not isinstance(payload.get("generation"), int)
        or isinstance(payload.get("generation"), bool)
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
        fleet_common.runtime.validate_model(_LeaseAuditEventModel, event, error_cls=FleetError, message="lease audit event is invalid")
    return payload


@contextlib.contextmanager
def lease_lock(
    *,
    state_root: Path | None = None,
    exclusive: bool,
) -> Iterator[None]:
    _, lock_path = lease_paths(state_root)
    with fleet_common.runtime.file_lock(lock_path, mode=0o600):
        yield


def read_lease_store(*, state_root: Path | None = None) -> dict[str, Any]:
    root = state_root or STATE_ROOT
    return state_store.read_lease_sqlite_store(
        root,
        empty_factory=empty_lease_store,
        validator=validate_lease_store,
        error_cls=FleetError,
    )


def write_lease_store(
    payload: dict[str, Any],
    *,
    state_root: Path | None = None,
) -> None:
    root = state_root or STATE_ROOT
    state_store.write_lease_sqlite_store(
        root,
        payload,
        validator=validate_lease_store,
        error_cls=FleetError,
    )

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
    worker_binding: dict[str, str] | None = None,
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
        **({"worker_binding": dict(worker_binding)} if worker_binding else {}),
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
    worker_binding: dict[str, str] | None = None,
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
            worker_binding=worker_binding,
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
