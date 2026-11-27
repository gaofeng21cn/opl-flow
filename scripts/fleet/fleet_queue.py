"""Deterministic priority queueing and backpressure admission planner over Beads slices & Fleet leases."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from . import fleet_common
from .fleet_attempts import plan_preemption
from .fleet_common import FleetError, parse_utc, utc_now
from .fleet_dispatch import dispatch_candidates, read_execution_requirements
from .fleet_lease import active_lease_map, read_lease_store


QUEUE_PLAN_SCHEMA = "opl_fleet_queue_plan.v1"


def _resolve_priority(item: dict[str, Any]) -> int:
    reqs = item.get("requirements")
    if isinstance(reqs, dict) and isinstance(reqs.get("priority"), int) and not isinstance(reqs["priority"], bool):
        return int(reqs["priority"])
    if isinstance(item.get("dispatch_priority"), int) and not isinstance(item["dispatch_priority"], bool):
        return int(item["dispatch_priority"])
    raw = item.get("priority")
    if isinstance(raw, str) and raw.strip().upper() in {"P0", "P1", "P2", "P3", "P4"}:
        rank = int(raw.strip()[1])
        return (4 - rank) * 200 + 100
    if isinstance(raw, int) and not isinstance(raw, bool):
        if item.get("is_bead_priority") or "issue_type" in item:
            return (4 - max(0, min(4, raw))) * 200 + 100
        return raw
    return 300


def score_queue_item(
    item: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> tuple[int, int, int, float, int, str, str]:
    """Deterministic priority sort key (smaller tuple = admitted earlier)."""
    now_dt = now or utc_now()
    human_rank = 0 if item.get("has_human_comment") else 1
    priority = _resolve_priority(item)

    due_raw = item.get("due_at")
    due_rank = 1
    due_ts = float("inf")
    if isinstance(due_raw, str) and due_raw.strip():
        due_dt = parse_utc(due_raw)
        due_rank = 0 if due_dt <= now_dt else 1
        due_ts = due_dt.timestamp()

    unlocks = int(item.get("unlocks_count", 0))
    created_at = str(item.get("created_at") or "9999-12-31T23:59:59Z")
    objective_id = str(item.get("objective_id") or "")
    return (human_rank, -priority, due_rank, due_ts, -unlocks, created_at, objective_id)


def plan_queue(
    items: list[dict[str, Any]],
    *,
    active_leases: dict[str, dict[str, Any]] | None = None,
    candidates_by_item: dict[str, list[dict[str, Any]]] | None = None,
    max_concurrent: int | None = None,
    max_local_concurrent: int | None = None,
    state_root: Path | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Plan admission, preemption candidates, and explicit backpressure without creating a second task store."""
    resolved_root = state_root or fleet_common.STATE_ROOT
    now_dt = now or utc_now()
    if max_concurrent is not None and max_concurrent < 0:
        raise FleetError("max_concurrent must be >= 0")
    if max_local_concurrent is not None and max_local_concurrent < 0:
        raise FleetError("max_local_concurrent must be >= 0")

    leases = active_leases
    if leases is None:
        leases = active_lease_map(state_root=resolved_root, now=now_dt)

    busy_nodes = set(leases.keys())
    ranked = sorted(items, key=lambda entry: score_queue_item(entry, now=now_dt))

    admit_now: list[dict[str, Any]] = []
    preempt_candidates: list[dict[str, Any]] = []
    queued_backpressure: list[dict[str, Any]] = []
    admitted_count = 0
    local_admitted = 0

    for rank, item in enumerate(ranked, start=1):
        objective_id = str(item.get("objective_id") or "")
        if not objective_id:
            raise FleetError("queue item is missing objective_id")
        reqs_raw = item.get("requirements")
        if isinstance(reqs_raw, dict):
            cleaned_reqs = {k: v for k, v in reqs_raw.items() if v is not None}
            reqs = read_execution_requirements(__import__("json").dumps(cleaned_reqs))
        else:
            reqs = read_execution_requirements(None)
        adapter = str(item.get("adapter") or reqs["adapter"])
        priority = _resolve_priority(item)

        if max_concurrent is not None and admitted_count >= max_concurrent:
            queued_backpressure.append(
                {
                    "rank": rank,
                    "objective_id": objective_id,
                    "adapter": adapter,
                    "priority": priority,
                    "wait_reason": "max_concurrent_reached",
                }
            )
            continue

        if adapter in fleet_common.LOCAL_DISPATCH_ADAPTERS:
            if max_local_concurrent is not None and local_admitted >= max_local_concurrent:
                queued_backpressure.append(
                    {
                        "rank": rank,
                        "objective_id": objective_id,
                        "adapter": adapter,
                        "priority": priority,
                        "wait_reason": "local_concurrency_limit",
                    }
                )
                continue
            admit_now.append(
                {
                    "rank": rank,
                    "objective_id": objective_id,
                    "adapter": adapter,
                    "node_id": "local",
                    "priority": priority,
                }
            )
            admitted_count += 1
            local_admitted += 1
            continue

        # Remote / Fleet-leased adapter
        if candidates_by_item is not None and objective_id in candidates_by_item:
            candidates = list(candidates_by_item[objective_id])
        else:
            request = {
                "adapter": adapter,
                "requires": reqs["requires"],
                "min_memory_gb": reqs["min_memory_gb"],
                "gpu_api": reqs["gpu_api"],
                "min_gpu_memory_gb": reqs["min_gpu_memory_gb"],
                "gpu_model": reqs["gpu_model"],
                "workload_class": reqs["workload_class"],
                "priority": priority,
                "preemptible": reqs["preemptible"],
                "phase": reqs["phase"],
                "ttl_seconds": reqs["ttl_seconds"],
                "node_id": item.get("node_id"),
                "role": item.get("role"),
            }
            candidates = dispatch_candidates(request)

        chosen_node: str | None = None
        for cand in candidates:
            cid = str(cand.get("node_id") or "")
            if cid and cid not in busy_nodes and not cand.get("lease"):
                chosen_node = cid
                break

        if chosen_node is not None:
            busy_nodes.add(chosen_node)
            admit_now.append(
                {
                    "rank": rank,
                    "objective_id": objective_id,
                    "adapter": adapter,
                    "node_id": chosen_node,
                    "priority": priority,
                }
            )
            admitted_count += 1
            continue

        if not candidates:
            queued_backpressure.append(
                {
                    "rank": rank,
                    "objective_id": objective_id,
                    "adapter": adapter,
                    "priority": priority,
                    "wait_reason": "no_eligible_node",
                }
            )
            continue

        # Evaluate preemption on busy candidate nodes
        preemptible_match = None
        for cand in candidates:
            cid = str(cand.get("node_id") or "")
            if not cid:
                continue
            plan = plan_preemption(cid, incoming_priority=priority, state_root=resolved_root, now=now_dt)
            if plan["preemption_possible"]:
                preemptible_match = plan
                preempt_candidates.append(
                    {
                        "incoming_objective_id": objective_id,
                        "incoming_priority": priority,
                        **plan,
                    }
                )
                break

        queued_backpressure.append(
            {
                "rank": rank,
                "objective_id": objective_id,
                "adapter": adapter,
                "priority": priority,
                "wait_reason": "preemption_available" if preemptible_match else "all_eligible_nodes_busy",
            }
        )

    return {
        "schema": QUEUE_PLAN_SCHEMA,
        "admit_now": admit_now,
        "preempt_candidates": preempt_candidates,
        "queued_backpressure": queued_backpressure,
        "summary": {
            "total": len(ranked),
            "admitted": len(admit_now),
            "preempt_candidates": len(preempt_candidates),
            "queued_backpressure": len(queued_backpressure),
        },
    }
