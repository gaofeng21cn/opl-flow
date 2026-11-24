#!/usr/bin/env python3
"""Sanitized OPL App contribution and MCP App backend adapter for OPL Flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

if __package__:
    from . import opl_runtime as runtime
    from . import opl_events, opl_ledger, opl_service, opl_workflow
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import opl_runtime as runtime
    import opl_events
    import opl_ledger
    import opl_service
    import opl_workflow


SCHEMA_DASHBOARD = "opl_flow_decision_dashboard.v1"
DASHBOARD_REF = "opl-flow.decision.v1#dashboard"
MAX_MESSAGE_CHARS = 4000
MAX_TITLE_CHARS = 120
MAX_APPROVER_CHARS = 120


def _utc_now_iso() -> str:
    return runtime.iso_utc(runtime.utc_now(), drop_microseconds=True)


def _clean_text(value: Any, *, max_len: int = MAX_MESSAGE_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = "".join(ch for ch in cleaned if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return cleaned[:max_len]


def _resolve_instance(input_data: dict[str, Any]) -> tuple[Path | None, str | None]:
    explicit = input_data.get("instance_path")
    if isinstance(explicit, str) and explicit.strip():
        candidate = Path(explicit.strip()).expanduser().resolve()
        if not candidate.is_dir():
            return None, "指定的 OPL Flow 实例目录不存在或不可读取。"
        return candidate, None
    try:
        resolved = opl_workflow.instance_root(None)
    except opl_workflow.WorkflowError:
        return None, "尚未绑定 OPL Flow 实例目录，请先运行 $opl-flow start 或设置 ~/.config/opl-flow/instance.json。"
    if not resolved.is_dir():
        return None, "已绑定的 OPL Flow 实例目录不存在，请先运行 $opl-flow start 重新核对。"
    return resolved, None


def _sanitize_service(svc: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": svc.get("schema", "opl_router_service_status.v1"),
        "platform": str(svc.get("platform") or ""),
        "label": str(svc.get("label") or ""),
        "installed": bool(svc.get("installed")),
        "running": bool(svc.get("running")),
    }


def _sanitize_entry(entry: dict[str, Any], *, category: str) -> dict[str, Any]:
    remaining = entry.get("remaining") if isinstance(entry.get("remaining"), list) else []
    sanitized_remaining = [_clean_text(str(item), max_len=300) for item in remaining if str(item).strip()][:20]
    bead_id = _clean_text(str(entry.get("bead_id") or ""), max_len=128)
    title = _clean_text(str(entry.get("title") or bead_id), max_len=240)
    first_blocker = _clean_text(str(entry.get("first_blocker") or ""), max_len=500) or None
    next_action = _clean_text(str(entry.get("next_action") or ""), max_len=500) or None
    return {
        "bead_id": bead_id,
        "title": title,
        "status": _clean_text(str(entry.get("status") or ""), max_len=64),
        "execution_mode": _clean_text(str(entry.get("execution_mode") or ""), max_len=64) or None,
        "category": category,
        "first_blocker": first_blocker,
        "next_action": next_action,
        "remaining": sanitized_remaining,
        "remaining_count": len(sanitized_remaining),
        "archive_performed": bool(entry.get("archive_performed", False)),
        "user_approval_required": bool(entry.get("user_approval_required", category == "safe_to_archive")),
    }


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    summary = _clean_text(str(payload.get("summary") or payload.get("signal") or ""), max_len=300)
    return {
        "event_id": _clean_text(str(event.get("event_id") or ""), max_len=128),
        "event_type": _clean_text(str(event.get("event_type") or ""), max_len=64),
        "objective_id": _clean_text(str(event.get("objective_id") or ""), max_len=128),
        "parent_objective_id": _clean_text(str(event.get("parent_objective_id") or ""), max_len=128) or None,
        "source": _clean_text(str(event.get("source") or ""), max_len=128),
        "status": _clean_text(str(event.get("status") or ""), max_len=64),
        "created_at": _clean_text(str(event.get("created_at") or ""), max_len=64),
        "summary": summary,
    }


def _category_label(category: str) -> str:
    labels = {
        "needs_action": "需你拍板",
        "safe_to_archive": "待批归档",
        "active_objectives": "进行中",
        "blocked": "外部阻塞",
        "backlog": "待排期",
    }
    return labels.get(category, category)


def build_dashboard(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": True, "state": "unavailable", "reason": err}
    try:
        bd = opl_workflow.executable("bd", None)
        snap = opl_workflow.supervisor_snapshot(root, bd, "git")
        ev_dir = opl_events.default_event_state_dir(root)
        active_dir = ev_dir if opl_events.inbox_exists(ev_dir) else None
        raw_inbox = opl_events.list_inbox_summary(snap, state_dir=active_dir)
        svc = _sanitize_service(opl_service.router_service_status(root))
    except (
        opl_workflow.WorkflowError,
        opl_events.EventControlError,
        opl_ledger.LedgerError,
        opl_service.ServiceError,
    ) as exc:
        return {"ok": True, "state": "unavailable", "reason": str(exc)}

    categories = (
        "needs_action",
        "safe_to_archive",
        "active_objectives",
        "blocked",
        "backlog",
    )
    sanitized_inbox: dict[str, list[dict[str, Any]]] = {}
    board_items: list[dict[str, Any]] = []
    for cat in categories:
        entries = [
            _sanitize_entry(item, category=cat)
            for item in raw_inbox.get(cat, [])
            if isinstance(item, dict) and item.get("bead_id")
        ]
        sanitized_inbox[cat] = entries
        for entry in entries:
            detail_parts = [_category_label(cat)]
            if entry["first_blocker"]:
                detail_parts.append(f"阻塞：{entry['first_blocker']}")
            elif entry["next_action"]:
                detail_parts.append(f"下一步：{entry['next_action']}")
            elif entry["remaining_count"]:
                detail_parts.append(f"剩余 {entry['remaining_count']} 项")
            board_items.append(
                {
                    "id": entry["bead_id"],
                    "bead_id": entry["bead_id"],
                    "title": entry["title"],
                    "status": cat if cat in ("needs_action", "safe_to_archive", "blocked", "backlog") else (entry["status"] or "active"),
                    "category": cat,
                    "summary": " · ".join(detail_parts),
                    "first_blocker": entry["first_blocker"],
                    "next_action": entry["next_action"],
                    "remaining_count": entry["remaining_count"],
                }
            )

    pending_events = [
        _sanitize_event(item)
        for item in raw_inbox.get("pending_events", [])
        if isinstance(item, dict) and item.get("event_id")
    ]
    sanitized_inbox["pending_events"] = pending_events

    counts = {
        "needs_action": len(sanitized_inbox["needs_action"]),
        "safe_to_archive": len(sanitized_inbox["safe_to_archive"]),
        "active_objectives": len(sanitized_inbox["active_objectives"]),
        "blocked": len(sanitized_inbox["blocked"]),
        "backlog": len(sanitized_inbox["backlog"]),
        "pending_events": len(pending_events),
        "total_objectives": sum(len(sanitized_inbox[cat]) for cat in categories),
    }

    return {
        "ok": True,
        "state": "ready",
        "data": {
            "schema": SCHEMA_DASHBOARD,
            "instance_name": root.name,
            "fetched_at": _utc_now_iso(),
            "service": svc,
            "counts": counts,
            "inbox": sanitized_inbox,
            "items": board_items,
            "validation_errors": list(snap.get("validation_errors") or [])[:10],
        },
    }


def action_send(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": False, "state": "unavailable", "error": {"code": "instance_unavailable", "message": err}}
    message = _clean_text(input_data.get("message"), max_len=MAX_MESSAGE_CHARS)
    if not message:
        return {
            "ok": False,
            "state": "error",
            "error": {"code": "invalid_input", "message": "请输入任务内容或回复意见。"},
        }
    objective_id = _clean_text(input_data.get("objective_id"), max_len=128)
    title = _clean_text(input_data.get("title"), max_len=MAX_TITLE_CHARS)
    execution_mode = str(input_data.get("execution_mode") or "active").strip()
    if execution_mode not in ("active", "backlog"):
        execution_mode = "active"
    raw_priority = input_data.get("priority", 2)
    try:
        priority = max(0, min(4, int(raw_priority)))
    except (TypeError, ValueError):
        priority = 2
    run_now = bool(input_data.get("now", False))
    request_id = _clean_text(input_data.get("request_id"), max_len=100) or uuid.uuid4().hex[:12]

    try:
        bd = opl_workflow.executable("bd", None)
        ev_dir = opl_events.default_event_state_dir(root)
        if objective_id:
            digest = hashlib.sha256(f"{objective_id}:{request_id}:{message}".encode("utf-8")).hexdigest()[:12]
            res = opl_events.emit_event(
                ev_dir,
                event_type="human_comment",
                objective_id=objective_id,
                source="miniapp:decision-dashboard",
                idempotency_key=f"miniapp-comment:{objective_id}:{digest}",
                payload={"signal": "miniapp_human_comment", "summary": message[:200]},
            )
            action_kind = "reply"
            bead_id = objective_id
            event_id = str(res["event"]["event_id"])
            summary_text = f"已向目标 {bead_id} 投递回复指示。"
        else:
            auto_title = title or message.splitlines()[0][:60]
            res = opl_events.intake_objective(
                root,
                bd,
                title=auto_title,
                scope=message,
                priority=priority,
                execution_mode=execution_mode,
                state_dir=ev_dir,
                runner=opl_workflow.run,
            )
            action_kind = "create"
            bead_id = str(res["bead"]["id"])
            event_id = str(res["event"]["event"]["event_id"])
            summary_text = f"已创建目标 {bead_id}《{auto_title}》并进入事件队列。"

        tick_summary = None
        if run_now:
            tick = opl_events.router_tick(
                root,
                bd,
                state_dir=ev_dir,
                snapshot_fn=lambda: opl_workflow.supervisor_snapshot(root, bd, "git"),
                control_hook_argv=None,
                runner=opl_workflow.run,
            )
            tick_summary = {
                "status": str(tick.get("status") or ""),
                "wake_agent": bool(tick.get("wake_agent")),
                "emitted_events": int(tick.get("emitted_events", 0)),
                "turn_count": len(tick.get("turns") or []),
            }
    except (
        opl_workflow.WorkflowError,
        opl_events.EventControlError,
        opl_ledger.LedgerError,
    ) as exc:
        return {"ok": False, "state": "error", "error": {"code": "send_failed", "message": str(exc)}}

    return {
        "ok": True,
        "state": "ready",
        "result": {
            "action": action_kind,
            "bead_id": bead_id,
            "event_id": event_id,
            "message": summary_text,
            "router_tick": tick_summary,
        },
        "readback": {"data_ref": DASHBOARD_REF, "input": {}},
    }


def action_approve(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": False, "state": "unavailable", "error": {"code": "instance_unavailable", "message": err}}
    if input_data.get("confirmed") is not True:
        return {
            "ok": False,
            "state": "error",
            "error": {"code": "confirmation_required", "message": "批准归档必须经过明确的人工确认。"},
        }
    bead_id = _clean_text(input_data.get("bead_id"), max_len=128)
    approved_by = _clean_text(input_data.get("approved_by"), max_len=MAX_APPROVER_CHARS) or "owner"
    if not bead_id:
        return {
            "ok": False,
            "state": "error",
            "error": {"code": "invalid_input", "message": "缺少待批准归档的目标编号 bead_id。"},
        }
    try:
        bd = opl_workflow.executable("bd", None)
        receipt = opl_events.approve_archive(
            root,
            bd,
            bead_id,
            approved_by=approved_by,
            runner=opl_workflow.run,
        )
    except (
        opl_workflow.WorkflowError,
        opl_events.EventControlError,
        opl_ledger.LedgerError,
    ) as exc:
        return {"ok": False, "state": "error", "error": {"code": "approve_failed", "message": str(exc)}}

    return {
        "ok": True,
        "state": "ready",
        "result": {
            "action": "approve_archive",
            "bead_id": receipt["bead_id"],
            "archive_approved": bool(receipt["archive_approved"]),
            "approved_by": receipt["approved_by"],
            "approved_at": receipt["approved_at"],
            "message": f"已记录人工归档批准：{receipt['bead_id']}（批准人：{receipt['approved_by']}）。",
        },
        "readback": {"data_ref": DASHBOARD_REF, "input": {}},
    }


def action_tick(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": False, "state": "unavailable", "error": {"code": "instance_unavailable", "message": err}}
    dry_run = bool(input_data.get("dry_run", False))
    try:
        bd = opl_workflow.executable("bd", None)
        ev_dir = opl_events.default_event_state_dir(root)
        tick = opl_events.router_tick(
            root,
            bd,
            state_dir=ev_dir,
            snapshot_fn=lambda: opl_workflow.supervisor_snapshot(root, bd, "git"),
            control_hook_argv=None,
            dry_run=dry_run,
            runner=opl_workflow.run,
        )
    except (
        opl_workflow.WorkflowError,
        opl_events.EventControlError,
        opl_ledger.LedgerError,
    ) as exc:
        return {"ok": False, "state": "error", "error": {"code": "tick_failed", "message": str(exc)}}

    return {
        "ok": True,
        "state": "ready",
        "result": {
            "action": "router_tick",
            "dry_run": dry_run,
            "status": str(tick.get("status") or ""),
            "wake_agent": bool(tick.get("wake_agent")),
            "emitted_events": int(tick.get("emitted_events", 0)),
            "turn_count": len(tick.get("turns") or []),
            "message": "已完成一轮确定性状态对齐与事件评估。",
        },
        "readback": {"data_ref": DASHBOARD_REF, "input": {}},
    }


def action_service(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": False, "state": "unavailable", "error": {"code": "instance_unavailable", "message": err}}
    if input_data.get("confirmed") is not True:
        return {
            "ok": False,
            "state": "error",
            "error": {"code": "confirmation_required", "message": "启停后台事件引擎必须经过明确的人工确认。"},
        }
    action = str(input_data.get("action") or "").strip().lower()
    if action not in ("up", "down"):
        return {
            "ok": False,
            "state": "error",
            "error": {"code": "invalid_input", "message": "action 必须为 up 或 down。"},
        }
    dry_run = bool(input_data.get("dry_run", False))
    try:
        if action == "up":
            raw_interval = input_data.get("interval_seconds", 15.0)
            try:
                interval = max(5.0, min(3600.0, float(raw_interval)))
            except (TypeError, ValueError):
                interval = 15.0
            res = opl_service.install_router_service(
                root,
                flow_root=opl_workflow.flow_root(),
                interval_seconds=interval,
                use_codex_bridge=bool(input_data.get("use_codex_bridge", True)),
                dry_run=dry_run,
            )
            msg = "后台事件驱动引擎已启动。" if not dry_run else "已生成启动预览（dry-run）。"
        else:
            res = opl_service.uninstall_router_service(root, dry_run=dry_run)
            msg = "后台事件驱动引擎已停止。" if not dry_run else "已生成停止预览（dry-run）。"
        status = _sanitize_service(opl_service.router_service_status(root))
    except opl_service.ServiceError as exc:
        return {"ok": False, "state": "error", "error": {"code": "service_failed", "message": str(exc)}}

    return {
        "ok": True,
        "state": "ready",
        "result": {
            "action": action,
            "dry_run": dry_run,
            "service": status,
            "installed": bool(res.get("installed", status["installed"])),
            "running": bool(res.get("running", status["running"])),
            "message": msg,
        },
        "readback": {"data_ref": DASHBOARD_REF, "input": {}},
    }


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("input payload must be a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("dashboard", "send", "approve", "tick", "service"))
    args = parser.parse_args(argv)
    try:
        payload = _read_stdin_json()
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "state": "error", "error": {"code": "invalid_json", "message": str(exc)}},
                ensure_ascii=False,
            )
        )
        return 1

    handlers = {
        "dashboard": build_dashboard,
        "send": action_send,
        "approve": action_approve,
        "tick": action_tick,
        "service": action_service,
    }
    response = handlers[args.operation](payload)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
