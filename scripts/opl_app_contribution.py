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
    from . import opl_events, opl_ledger, opl_service, opl_session_discovery, opl_workflow
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import opl_runtime as runtime
    import opl_events
    import opl_ledger
    import opl_service
    import opl_session_discovery
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
    raw_bridge = svc.get("bridge")
    bridge = raw_bridge if raw_bridge in ("auto", "codex", "antigravity", "custom") else None
    return {
        "schema": svc.get("schema", "opl_router_service_status.v1"),
        "platform": str(svc.get("platform") or ""),
        "label": str(svc.get("label") or ""),
        "installed": bool(svc.get("installed")),
        "running": bool(svc.get("running")),
        "bridge": bridge,
    }


def _sanitize_entry(
    entry: dict[str, Any],
    *,
    category: str,
    include_local_navigation: bool = False,
    host_carrier: str | None = None,
    bound_session: dict[str, Any] | None = None,
    issue_workspace_path: str | None = None,
) -> dict[str, Any]:
    remaining = entry.get("remaining") if isinstance(entry.get("remaining"), list) else []
    sanitized_remaining = [_clean_text(str(item), max_len=300) for item in remaining if str(item).strip()][:20]
    bead_id = _clean_text(str(entry.get("bead_id") or ""), max_len=128)
    title = _clean_text(str(entry.get("title") or bead_id), max_len=240)
    first_blocker = _clean_text(str(entry.get("first_blocker") or ""), max_len=500) or None
    next_action = _clean_text(str(entry.get("next_action") or ""), max_len=500) or None
    carrier = _clean_text(str(entry.get("execution_carrier") or ""), max_len=32) or None
    if not carrier and bound_session:
        carrier = _clean_text(str(bound_session.get("carrier") or ""), max_len=32) or None
    preferred_adapter = _clean_text(str(entry.get("preferred_adapter") or ""), max_len=64) or None
    bound_session_ref = (
        _clean_text(str(bound_session.get("session_ref") or ""), max_len=128) or None
        if bound_session
        else None
    )
    out: dict[str, Any] = {
        "bead_id": bead_id,
        "title": title,
        "status": _clean_text(str(entry.get("status") or ""), max_len=64),
        "execution_mode": _clean_text(str(entry.get("execution_mode") or ""), max_len=64) or None,
        "execution_carrier": carrier,
        "preferred_adapter": preferred_adapter,
        "bound_session_ref": bound_session_ref,
        "category": category,
        "first_blocker": first_blocker,
        "next_action": next_action,
        "remaining": sanitized_remaining,
        "remaining_count": len(sanitized_remaining),
        "archive_performed": bool(entry.get("archive_performed", False)),
        "user_approval_required": bool(entry.get("user_approval_required", category == "safe_to_archive")),
    }
    if include_local_navigation:
        ws_path = (
            _clean_text(str((bound_session or {}).get("cwd") or ""), max_len=500)
            or _clean_text(str(issue_workspace_path or ""), max_len=500)
            or None
        )
        raw_sid = _clean_text(str((bound_session or {}).get("session_id") or ""), max_len=160) or None
        sess_carrier = _clean_text(str((bound_session or {}).get("carrier") or ""), max_len=32).lower() or None
        out["workspace_path"] = ws_path
        out["session_id"] = raw_sid
        out["thread_id"] = raw_sid if sess_carrier == "codex" and raw_sid else None
        if host_carrier:
            if bound_session and sess_carrier == host_carrier and raw_sid:
                out["jump_mode"] = "native_switch"
            elif (bound_session and sess_carrier and sess_carrier != host_carrier) or (
                carrier and carrier != host_carrier and ws_path is None
            ):
                out["jump_mode"] = "external_focus_only"
            else:
                out["jump_mode"] = "launch_new"
    return out


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
        "active_sessions": "活跃对话",
        "blocked": "外部阻塞",
        "backlog": "待排期",
    }
    return labels.get(category, category)


def _extract_issue_hints(snap: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    issue_titles: dict[str, str] = {}
    issue_workspaces: dict[str, str] = {}
    for issue in snap.get("issues", []) or []:
        if not isinstance(issue, dict) or not issue.get("id"):
            continue
        bid = str(issue["id"])
        title = _clean_text(str(issue.get("title") or ""), max_len=240)
        if title:
            issue_titles[bid] = title
        meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
        for key in ("workspace_path", "cwd", "repo_root"):
            candidate = meta.get(key)
            if isinstance(candidate, str) and candidate.strip():
                issue_workspaces[bid] = candidate.strip()[:500]
                break
    return issue_titles, issue_workspaces


def build_dashboard(input_data: dict[str, Any]) -> dict[str, Any]:
    root, err = _resolve_instance(input_data)
    if root is None:
        return {"ok": True, "state": "unavailable", "reason": err}
    include_local_navigation = bool(input_data.get("include_local_navigation", False))
    raw_host = _clean_text(input_data.get("host_carrier"), max_len=32).lower()
    host_carrier = raw_host if raw_host in ("codex", "antigravity", "dsh") else None
    try:
        bd = opl_workflow.executable("bd", None)
        snap = opl_workflow.supervisor_snapshot(root, bd, "git")
        ev_dir = opl_events.default_event_state_dir(root)
        active_dir = ev_dir if opl_events.inbox_exists(ev_dir) else None
        raw_inbox = opl_events.list_inbox_summary(snap, state_dir=active_dir)
        svc = _sanitize_service(opl_service.router_service_status(root))
        discovery = opl_session_discovery.discover_local_sessions(issues=snap.get("issues"))
        issue_titles, issue_workspaces = _extract_issue_hints(snap)
        sanitized_sessions = opl_session_discovery.sanitize_sessions_for_projection(
            discovery,
            include_local_navigation=include_local_navigation,
            host_carrier=host_carrier,
            issue_titles=issue_titles,
        )
    except (
        opl_workflow.WorkflowError,
        opl_events.EventControlError,
        opl_ledger.LedgerError,
        opl_service.ServiceError,
    ) as exc:
        return {"ok": True, "state": "unavailable", "reason": str(exc)}

    bound_sessions_by_bead: dict[str, dict[str, Any]] = {}
    for sess in discovery.get("sessions", []) or []:
        if isinstance(sess, dict) and sess.get("bound_bead_id") and str(sess["bound_bead_id"]) not in bound_sessions_by_bead:
            bound_sessions_by_bead[str(sess["bound_bead_id"])] = sess

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
        entries = []
        for item in raw_inbox.get(cat, []):
            if not isinstance(item, dict) or not item.get("bead_id"):
                continue
            bid = str(item["bead_id"])
            entries.append(
                _sanitize_entry(
                    item,
                    category=cat,
                    include_local_navigation=include_local_navigation,
                    host_carrier=host_carrier,
                    bound_session=bound_sessions_by_bead.get(bid),
                    issue_workspace_path=issue_workspaces.get(bid),
                )
            )
        sanitized_inbox[cat] = entries
        for entry in entries:
            detail_parts = [_category_label(cat)]
            if entry["first_blocker"]:
                detail_parts.append(f"阻塞：{entry['first_blocker']}")
            elif entry["next_action"]:
                detail_parts.append(f"下一步：{entry['next_action']}")
            elif entry["remaining_count"]:
                detail_parts.append(f"剩余 {entry['remaining_count']} 项")
            board_row: dict[str, Any] = {
                "id": entry["bead_id"],
                "bead_id": entry["bead_id"],
                "title": entry["title"],
                "status": cat if cat in ("needs_action", "safe_to_archive", "blocked", "backlog") else (entry["status"] or "active"),
                "category": cat,
                "summary": " · ".join(detail_parts),
                "first_blocker": entry["first_blocker"],
                "next_action": entry["next_action"],
                "remaining_count": entry["remaining_count"],
                "execution_carrier": entry["execution_carrier"],
                "preferred_adapter": entry["preferred_adapter"],
                "bound_session_ref": entry["bound_session_ref"],
            }
            if include_local_navigation:
                board_row["workspace_path"] = entry.get("workspace_path")
                board_row["session_id"] = entry.get("session_id")
                board_row["thread_id"] = entry.get("thread_id")
                if "jump_mode" in entry:
                    board_row["jump_mode"] = entry["jump_mode"]
            board_items.append(board_row)

    pending_events = [
        _sanitize_event(item)
        for item in raw_inbox.get("pending_events", [])
        if isinstance(item, dict) and item.get("event_id")
    ]
    sanitized_inbox["pending_events"] = pending_events
    active_session_list = list(sanitized_sessions.get("sessions") or [])
    sanitized_inbox["active_sessions"] = active_session_list

    counts = {
        "needs_action": len(sanitized_inbox["needs_action"]),
        "safe_to_archive": len(sanitized_inbox["safe_to_archive"]),
        "active_objectives": len(sanitized_inbox["active_objectives"]),
        "active_sessions": len(active_session_list),
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
            "active_sessions": sanitized_sessions,
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
    raw_executor = _clean_text(input_data.get("executor"), max_len=32).lower()
    executor = raw_executor if raw_executor in opl_events.EXECUTOR_ADAPTER_MAP else None
    raw_session_ref = _clean_text(input_data.get("session_ref"), max_len=160) or None
    exec_thread, exec_carrier = opl_workflow._resolve_execution_binding(executor, raw_session_ref)
    if exec_carrier in opl_events.EXECUTOR_ADAPTER_MAP and executor is None:
        executor = exec_carrier
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
            reqs = (
                {
                    "schema": "opl_execution_requirements.v1",
                    "adapter": opl_events.EXECUTOR_ADAPTER_MAP[executor],
                }
                if executor
                else None
            )
            extra_kwargs: dict[str, Any] = {}
            if exec_thread is not None:
                extra_kwargs["execution_thread"] = exec_thread
            if exec_carrier is not None:
                extra_kwargs["execution_carrier"] = exec_carrier
            res = opl_events.intake_objective(
                root,
                bd,
                title=auto_title,
                scope=message,
                priority=priority,
                execution_mode=execution_mode,
                requirements=reqs,
                state_dir=ev_dir,
                runner=opl_workflow.run,
                **extra_kwargs,
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
            raw_bridge = _clean_text(input_data.get("bridge"), max_len=32).lower()
            if raw_bridge in ("auto", "codex", "antigravity"):
                bridge = raw_bridge
                use_codex = bridge == "codex"
            elif "use_codex_bridge" in input_data:
                bridge = None
                use_codex = bool(input_data.get("use_codex_bridge"))
            else:
                bridge = "auto"
                use_codex = False
            res = opl_service.install_router_service(
                root,
                flow_root=opl_workflow.flow_root(),
                interval_seconds=interval,
                use_codex_bridge=use_codex,
                bridge=bridge,
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


def framework_contribution(request: dict[str, Any]) -> dict[str, Any]:
    operation = request.get("operation")
    ref = request.get("ref", request.get("action_id"))
    receipt = {
        "schema_version": "opl-package-app-contribution-response.v1",
        "package_id": "opl-flow",
        "operation": operation,
        "ref": ref,
    }
    try:
        if request.get("schema_version") != "opl-package-app-contribution-request.v1" or request.get("package_id") != "opl-flow":
            raise ValueError("请求未绑定 OPL Flow Package。")
        if "ref" in request and "action_id" in request and request["ref"] != request["action_id"]:
            raise ValueError("请求包含不一致的动作标识。")
        if operation == "read" and ref == DASHBOARD_REF:
            handler = build_dashboard
        elif operation == "execute" and isinstance(ref, str):
            handler = {
                "opl-flow.decision.v1#send": action_send,
                "opl-flow.decision.v1#approve": action_approve,
                "opl-flow.decision.v1#tick": action_tick,
                "opl-flow.decision.v1#service": action_service,
            }.get(ref)
            if handler is None or request.get("dry_run", False) is not False:
                raise ValueError("请求未指定可执行的看板动作。")
        else:
            raise ValueError("请求未指定已声明的看板视图或动作。")
        field = "input" if "ref" in request else "payload"
        data = request.get(field)
        if not isinstance(data, dict):
            raise ValueError("看板输入必须为 JSON 对象。")
    except ValueError as exc:
        return {**receipt, "ok": False, "state": "error", "error": {"code": "invalid_request", "message": str(exc)}}
    return {**receipt, **handler(data)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", nargs="?", choices=("dashboard", "send", "approve", "tick", "service"))
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

    if args.operation is None:
        print(json.dumps(framework_contribution(payload), ensure_ascii=False))
        return 0
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
