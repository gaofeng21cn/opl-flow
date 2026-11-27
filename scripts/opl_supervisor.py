"""Deterministic Supervisor Phase A diff engine, projections, and Obsidian sync.

Zero Fleet imports. Never makes LLM calls or guesses missing owner facts.
"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

try:
    from . import opl_execution, opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_execution
    import opl_runtime as runtime


AUTO_REPLY_MARKER = "【OPL Flow · Codex 自动回复】"
CURSOR_SCHEMA = "opl_supervisor_cursor.v1"
PLAN_SCHEMA = "opl_supervisor_episode_plan.v1"
MANAGED_START = "<!-- OPL_ARCHIVE_FACTS_START -->"
MANAGED_END = "<!-- OPL_ARCHIVE_FACTS_END -->"

SUPERVISOR_MODES = frozenset(
    {
        "active",
        "backlog",
        "waiting_user",
        "waiting_external",
        "monitoring",
        "on_demand",
        "aggregate",
    }
)

BEADS_TO_LINEAR_STATUS = {
    ("deferred", "backlog"): "Backlog",
    ("open", "backlog"): "Todo",
    ("open", "active"): "Todo",
    ("in_progress", "active"): "In Progress",
    ("waiting_user",): "Needs Action",
    ("waiting_external",): "Blocked",
    ("monitoring",): "Monitoring",
    ("on_demand",): "On Demand",
    ("closed",): "Done",
}

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SupervisorError(RuntimeError):
    pass


def _utc_now() -> dt.datetime:
    return runtime.utc_now()


def _parse_utc(value: Any) -> dt.datetime | None:
    return runtime.parse_utc(value, allow_none=True)


def _iso_utc(value: dt.datetime) -> str:
    return runtime.iso_utc(value)


def _atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    runtime.atomic_write_text(path, text, mode=mode)


def default_cursor_path(instance_root: Path) -> Path:
    digest = hashlib.sha256(str(instance_root.expanduser().resolve()).encode("utf-8")).hexdigest()[:16]
    return Path.home() / ".local/state/opl-flow/supervisor" / digest / "cursor.json"


def empty_cursor() -> dict[str, Any]:
    return {
        "schema": CURSOR_SCHEMA,
        "threads": {},
        "antigravity_conversations": {},
        "dsh_sessions": {},
        "linear_projects": {},
        "linear_issue_comments": {},
        "processed_comment_ids": [],
        "obsidian_fingerprints": {},
        "last_full_audit_at": None,
    }


def load_cursor(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_cursor()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupervisorError(f"supervisor cursor is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != CURSOR_SCHEMA:
        raise SupervisorError(f"supervisor cursor schema is invalid: {path}")
    cursor = empty_cursor()
    for key in ("threads", "antigravity_conversations", "dsh_sessions", "linear_projects", "linear_issue_comments", "obsidian_fingerprints"):
        if isinstance(payload.get(key), dict):
            cursor[key] = deepcopy(payload[key])
    if isinstance(payload.get("processed_comment_ids"), list):
        cursor["processed_comment_ids"] = [str(item) for item in payload["processed_comment_ids"]][-500:]
    if isinstance(payload.get("last_full_audit_at"), str):
        cursor["last_full_audit_at"] = payload["last_full_audit_at"]
    return cursor


def save_cursor(path: Path, cursor: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    normalized = empty_cursor()
    normalized.update({k: v for k, v in cursor.items() if k in normalized})
    normalized["schema"] = CURSOR_SCHEMA
    normalized["processed_comment_ids"] = list(normalized["processed_comment_ids"])[-500:]
    _atomic_write_text(path, json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", mode=0o600)


def map_bead_to_linear_status(
    issue: dict[str, Any],
    children: list[dict[str, Any]] | None = None,
) -> tuple[str | None, str | None]:
    """Map one Bead's lifecycle + execution_mode to its Linear status without guessing."""
    bead_status = str(issue.get("status") or "").strip()
    metadata = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    mode = metadata.get("execution_mode")

    if bead_status == "closed":
        return "Done", None
    if mode not in SUPERVISOR_MODES:
        return None, f"{issue.get('id', '?')}: unknown or missing execution_mode ({mode!r})"
    if mode == "waiting_user":
        return "Needs Action", None
    if mode == "waiting_external":
        return "Blocked", None
    if mode == "monitoring":
        return "Monitoring", None
    if mode == "on_demand":
        return "On Demand", None
    if mode == "backlog":
        if bead_status == "deferred":
            return "Backlog", None
        if bead_status == "open":
            return "Todo", None
        return None, f"{issue.get('id', '?')}: invalid status {bead_status!r} for backlog mode"
    if mode == "active":
        if bead_status == "in_progress":
            return "In Progress", None
        if bead_status == "open":
            return "Todo", None
        return None, f"{issue.get('id', '?')}: invalid status {bead_status!r} for active mode"

    # aggregate parent rollup
    unfinished = [child for child in (children or []) if str(child.get("status") or "") != "closed"]
    if not unfinished:
        return "Done", None
    child_modes = {
        (child.get("metadata") or {}).get("execution_mode")
        for child in unfinished
        if isinstance(child.get("metadata"), dict)
    }
    if "active" in child_modes:
        return "In Progress", None
    if "waiting_user" in child_modes:
        return "Needs Action", None
    if "waiting_external" in child_modes:
        return "Blocked", None
    if "monitoring" in child_modes:
        return "Monitoring", None
    return "Todo", None


def project_title_prefix(issue: dict[str, Any]) -> dict[str, Any]:
    """Compute human-visible title projection without authorizing archive mutation."""
    bead_id = str(issue.get("id") or "")
    metadata = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    classification = metadata.get("classification") or metadata.get("task_lifecycle_class")
    mode = metadata.get("execution_mode")
    status = str(issue.get("status") or "")
    remaining = metadata.get("remaining")
    remaining_list = remaining if isinstance(remaining, list) else []

    if classification == "managed_objective" and status == "closed" and not remaining_list:
        prefix = "SAFE_TO_ARCHIVE"
    elif mode == "waiting_user":
        prefix = "NEEDS_ACTION"
    elif mode == "waiting_external":
        prefix = "BLOCKED"
    elif mode in {"monitoring", "on_demand", "aggregate", "backlog"} and not metadata.get("execution_thread"):
        prefix = "MONITORING"
    else:
        prefix = "ACTIVE"

    return {
        "bead_id": bead_id,
        "prefix": prefix,
        "archive_performed": False,
        "user_approval_required": prefix == "SAFE_TO_ARCHIVE",
    }


def _thread_signature(thread: dict[str, Any]) -> dict[str, Any]:
    return {
        "updatedAt": thread.get("updatedAt") or thread.get("updated_at"),
        "status": thread.get("status"),
        "hasUnreadTurn": bool(thread.get("hasUnreadTurn", thread.get("has_unread_turn", False))),
    }


def _agy_conversation_signature(conv: dict[str, Any]) -> dict[str, Any]:
    state = conv.get("state") if isinstance(conv.get("state"), dict) else {}
    return {
        "updateTime": state.get("updateTime") or conv.get("updateTime") or conv.get("updatedAt") or conv.get("updated_at"),
        "runState": state.get("runState") or conv.get("runState") or conv.get("status"),
    }


def _dsh_session_signature(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "updatedAt": session.get("updated_at") or session.get("updatedAt"),
        "status": session.get("status"),
        "harness": session.get("harness"),
    }


def _extract_linear_issues(
    linear_issues: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None,
) -> dict[str, list[dict[str, Any]]]:
    if linear_issues is None:
        return {}
    if isinstance(linear_issues, dict):
        return {str(k): list(v or []) for k, v in linear_issues.items()}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in linear_issues:
        if not isinstance(item, dict):
            continue
        project_id = str(item.get("project_id") or item.get("projectId") or "default")
        grouped.setdefault(project_id, []).append(item)
    return grouped


def _extract_assignee(linear_issue: dict[str, Any]) -> str | None:
    assignee = linear_issue.get("assignee")
    if isinstance(assignee, str) and assignee.strip():
        return assignee.strip()
    if isinstance(assignee, dict):
        for key in ("id", "email", "name"):
            val = assignee.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    for key in ("assignee_id", "assigneeId"):
        val = linear_issue.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_comment_author(comment: dict[str, Any]) -> str | None:
    for key in ("author", "account", "user_id", "userId"):
        val = comment.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    user = comment.get("user")
    if isinstance(user, dict):
        for key in ("id", "email", "name"):
            val = user.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _is_auto_reply_comment(comment: dict[str, Any]) -> bool:
    body = str(comment.get("body") or comment.get("text") or "")
    lines = body.splitlines()
    return bool(lines) and lines[0].strip() == AUTO_REPLY_MARKER


def _issue_fingerprint(issue: dict[str, Any]) -> str:
    metadata = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    projected = {
        "id": issue.get("id"),
        "title": issue.get("title"),
        "status": issue.get("status"),
        "priority": issue.get("priority"),
        "due_at": issue.get("due_at"),
        "owner": issue.get("owner"),
        "execution_mode": metadata.get("execution_mode"),
        "classification": metadata.get("classification") or metadata.get("task_lifecycle_class"),
        "current_slice": metadata.get("current_slice"),
        "first_blocker": metadata.get("first_blocker"),
        "next_action": metadata.get("next_action"),
        "remaining": metadata.get("remaining"),
        "linear_issue_identifier": metadata.get("linear_issue_identifier"),
    }
    return hashlib.sha256(
        json.dumps(projected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def detect_changes(
    snapshot: dict[str, Any],
    *,
    cursor: dict[str, Any] | None = None,
    threads: list[dict[str, Any]] | None = None,
    antigravity_conversations: list[dict[str, Any]] | None = None,
    dsh_sessions: list[dict[str, Any]] | None = None,
    linear_issues: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None = None,
    linear_comments: dict[str, list[dict[str, Any]]] | None = None,
    pending_events: list[dict[str, Any]] | None = None,
    worktree_ledger: dict[str, Any] | None = None,
    authorized_accounts: list[str] | tuple[str, ...] | None = None,
    now: str | dt.datetime | None = None,
) -> dict[str, Any]:
    """Deterministic Phase A change detector. Zero LLM calls; fail-closed on ambiguity."""
    now_dt = _parse_utc(now) if isinstance(now, str) else (now or _utc_now())
    if now_dt is None:
        raise SupervisorError("invalid now timestamp")
    now_iso = _iso_utc(now_dt)

    base_cursor = deepcopy(cursor) if cursor is not None else empty_cursor()
    next_cursor = deepcopy(base_cursor)
    issues = [item for item in snapshot.get("issues", []) if isinstance(item, dict)]
    issue_by_id = {str(item["id"]): item for item in issues if item.get("id")}
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    issue_by_thread: dict[str, str] = {}
    issue_by_agy_conv: dict[str, str] = {}
    issue_by_dsh_session: dict[str, str] = {}
    issue_by_linear_id: dict[str, str] = {}
    for item in issues:
        bid = str(item["id"])
        parent = item.get("parent")
        if isinstance(parent, str) and parent:
            children_by_parent.setdefault(parent, []).append(item)
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        exec_thread = meta.get("execution_thread")
        carrier = str(meta.get("execution_carrier") or "").strip().lower()
        if isinstance(exec_thread, str) and exec_thread.strip():
            raw_thread = exec_thread.strip()
            if raw_thread.startswith("antigravity:"):
                raw_id = raw_thread.split(":", 1)[1].strip()
                if raw_id:
                    issue_by_agy_conv[raw_id] = bid
                issue_by_agy_conv[raw_thread] = bid
            elif raw_thread.startswith("codex:"):
                raw_id = raw_thread.split(":", 1)[1].strip()
                if raw_id:
                    issue_by_thread[raw_id] = bid
                issue_by_thread[raw_thread] = bid
            elif raw_thread.startswith("dsh:"):
                raw_id = raw_thread.split(":", 1)[1].strip()
                if raw_id:
                    issue_by_dsh_session[raw_id] = bid
                issue_by_dsh_session[raw_thread] = bid
            elif carrier == "antigravity":
                issue_by_agy_conv[raw_thread] = bid
            elif carrier == "dsh":
                issue_by_dsh_session[raw_thread] = bid
            else:
                issue_by_thread[raw_thread] = bid
        for lkey in ("linear_issue_identifier", "linear_issue_id"):
            lval = meta.get(lkey)
            if isinstance(lval, str) and lval.strip():
                issue_by_linear_id[lval.strip()] = bid

    validation_errors = list(snapshot.get("validation_errors") or [])
    events_by_key: dict[str, dict[str, Any]] = {}
    linear_actions: list[dict[str, Any]] = []
    obsidian_actions: list[dict[str, Any]] = []
    title_projections: list[dict[str, Any]] = []

    def _add_event(
        *,
        event_type: str,
        objective_id: str,
        source: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> None:
        opl_execution.sanitize_check(payload, label="supervisor_event_payload")
        if idempotency_key in events_by_key:
            return
        events_by_key[idempotency_key] = {
            "event_type": event_type,
            "objective_id": objective_id,
            "source": source,
            "idempotency_key": idempotency_key,
            "created_at": now_iso,
            "payload": payload,
        }

    # 1. Include existing pending events from Stage 2 inbox first
    for item in pending_events or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("idempotency_key") or item.get("event_id") or "")
        if key and key not in events_by_key:
            events_by_key[key] = deepcopy(item)

    # 2. Thread observation diff (updatedAt, status, hasUnreadTurn only — never title)
    thread_list = [t for t in (threads or []) if isinstance(t, dict)]
    prev_threads = base_cursor.get("threads", {})
    thread_summaries_changed = 0
    threads_read_needed: set[str] = set()
    unread_override_objectives: set[str] = set()

    for thread in thread_list:
        tid = str(thread.get("id") or thread.get("thread_id") or "").strip()
        if not tid:
            continue
        sig = _thread_signature(thread)
        old_sig = prev_threads.get(tid)
        next_cursor.setdefault("threads", {})[tid] = sig
        matched_bead = issue_by_thread.get(tid)

        if old_sig is None:
            thread_summaries_changed += 1
            threads_read_needed.add(tid)
            _add_event(
                event_type="human_intake" if matched_bead is None else "worker_callback",
                objective_id=matched_bead or f"thread:{tid}",
                source="codex:list_threads",
                idempotency_key=f"thread-new:{tid}:{sig['updatedAt'] or 'init'}",
                payload={"signal": "thread_new", "thread_id": tid, "thread_status": sig["status"]},
            )
            continue

        if sig != old_sig:
            thread_summaries_changed += 1
            threads_read_needed.add(tid)
            if sig["hasUnreadTurn"]:
                if matched_bead:
                    unread_override_objectives.add(matched_bead)
                _add_event(
                    event_type="human_comment",
                    objective_id=matched_bead or f"thread:{tid}",
                    source="codex:list_threads",
                    idempotency_key=f"thread-unread:{tid}:{sig['updatedAt'] or now_iso}",
                    payload={
                        "signal": "thread_unread_user_message",
                        "thread_id": tid,
                        "overrides_backoff": True,
                    },
                )
            else:
                ev_type = "executor_lost" if str(sig["status"] or "").lower() in {"error", "failed", "missing"} else "worker_callback"
                _add_event(
                    event_type=ev_type,
                    objective_id=matched_bead or f"thread:{tid}",
                    source="codex:list_threads",
                    idempotency_key=f"thread-change:{tid}:{sig['updatedAt']}:{sig['status']}",
                    payload={
                        "signal": "thread_changed",
                        "thread_id": tid,
                        "thread_status": sig["status"],
                    },
                )

    # 2b. Optional Antigravity conversation delta (updateTime, runState only — never title/summary)
    agy_list = [c for c in (antigravity_conversations or []) if isinstance(c, dict)]
    prev_agy = base_cursor.get("antigravity_conversations") or {}
    for conv in agy_list:
        cid = str(conv.get("id") or conv.get("conversationId") or "").strip()
        if not cid:
            continue
        sig = _agy_conversation_signature(conv)
        old_sig = prev_agy.get(cid)
        next_cursor.setdefault("antigravity_conversations", {})[cid] = sig
        matched_bead = issue_by_agy_conv.get(cid)
        run_state = str(sig.get("runState") or "")
        is_lost = run_state.lower() in {
            "error",
            "failed",
            "missing",
            "cancelled",
            "run_state_error",
            "run_state_cancelling",
            "run_state_failed",
        }
        if old_sig is None:
            thread_summaries_changed += 1
            threads_read_needed.add(f"antigravity:{cid}")
            ev_type = "executor_lost" if (matched_bead and is_lost) else ("human_intake" if matched_bead is None else "worker_callback")
            _add_event(
                event_type=ev_type,
                objective_id=matched_bead or f"antigravity:{cid}",
                source="antigravity:conversations",
                idempotency_key=f"agy-new:{cid}:{sig['updateTime'] or 'init'}",
                payload={
                    "signal": "antigravity_conversation_new",
                    "conversation_id": cid,
                    "run_state": run_state,
                },
            )
            continue

        if sig != old_sig:
            thread_summaries_changed += 1
            threads_read_needed.add(f"antigravity:{cid}")
            ev_type = "executor_lost" if is_lost else "worker_callback"
            _add_event(
                event_type=ev_type,
                objective_id=matched_bead or f"antigravity:{cid}",
                source="antigravity:conversations",
                idempotency_key=f"agy-change:{cid}:{sig['updateTime']}:{run_state}",
                payload={
                    "signal": "antigravity_conversation_changed",
                    "conversation_id": cid,
                    "run_state": run_state,
                },
            )

    # 2c. Optional OPL DSH session delta (updated_at, status, harness only — never prompts/turns)
    dsh_list = [s for s in (dsh_sessions or []) if isinstance(s, dict)]
    prev_dsh = base_cursor.get("dsh_sessions") or {}
    for sess in dsh_list:
        sid = str(sess.get("id") or sess.get("session_id") or "").strip()
        if not sid:
            continue
        sig = _dsh_session_signature(sess)
        old_sig = prev_dsh.get(sid)
        next_cursor.setdefault("dsh_sessions", {})[sid] = sig
        matched_bead = issue_by_dsh_session.get(sid) or (
            str(sess.get("bound_bead_id")) if sess.get("bound_bead_id") else None
        )
        sess_status = str(sig.get("status") or "")
        is_lost = sess_status.lower() in {"error", "failed", "missing", "cancelled"}
        if old_sig is None:
            thread_summaries_changed += 1
            threads_read_needed.add(f"dsh:{sid}")
            ev_type = "executor_lost" if (matched_bead and is_lost) else ("human_intake" if matched_bead is None else "worker_callback")
            _add_event(
                event_type=ev_type,
                objective_id=matched_bead or f"dsh:{sid}",
                source="dsh:sessions",
                idempotency_key=f"dsh-new:{sid}:{sig['updatedAt'] or 'init'}",
                payload={
                    "signal": "dsh_session_new",
                    "session_ref": f"dsh:{sid[:12]}",
                    "dsh_status": sess_status,
                    **({"harness": sig["harness"]} if sig.get("harness") else {}),
                },
            )
            continue

        if sig != old_sig:
            thread_summaries_changed += 1
            threads_read_needed.add(f"dsh:{sid}")
            ev_type = "executor_lost" if is_lost else "worker_callback"
            _add_event(
                event_type=ev_type,
                objective_id=matched_bead or f"dsh:{sid}",
                source="dsh:sessions",
                idempotency_key=f"dsh-change:{sid}:{sig['updatedAt']}:{sess_status}",
                payload={
                    "signal": "dsh_session_changed",
                    "session_ref": f"dsh:{sid[:12]}",
                    "dsh_status": sess_status,
                    **({"harness": sig["harness"]} if sig.get("harness") else {}),
                },
            )

    # 3. Linear delta + mandatory comment API gate + assignee audit
    grouped_linear = _extract_linear_issues(linear_issues)
    comments_map = linear_comments or {}
    processed_comment_ids = set(base_cursor.get("processed_comment_ids", []))
    linear_issues_changed = 0
    linear_comment_pages = 0
    auth_list = [str(a) for a in (authorized_accounts or []) if str(a).strip()]

    if len(auth_list) > 1:
        validation_errors.append("multiple authorized_human_accounts require explicit project mapping")

    for project_id, proj_issues in sorted(grouped_linear.items()):
        waterline_blocked = False
        max_updated: dt.datetime | None = _parse_utc(
            base_cursor.get("linear_projects", {}).get(project_id, {}).get("waterline_updated_at")
        )
        for l_issue in proj_issues:
            linear_issues_changed += 1
            lid = str(l_issue.get("identifier") or l_issue.get("id") or "").strip()
            alt_id = str(l_issue.get("id") or "").strip()
            bead_id = issue_by_linear_id.get(lid) or issue_by_linear_id.get(alt_id) or str(l_issue.get("bead_id") or "")
            updated_dt = _parse_utc(l_issue.get("updatedAt") or l_issue.get("updated_at"))
            if updated_dt and (max_updated is None or updated_dt > max_updated):
                max_updated = updated_dt

            # Single-account assignee projection check
            if len(auth_list) == 1:
                expected_assignee = auth_list[0]
                actual_assignee = _extract_assignee(l_issue)
                if actual_assignee != expected_assignee:
                    linear_actions.append(
                        {
                            "action": "repair_assignee",
                            "project_id": project_id,
                            "linear_issue_id": lid or alt_id,
                            "bead_id": bead_id or None,
                            "expected_assignee": expected_assignee,
                            "actual_assignee": actual_assignee,
                        }
                    )

            # Mandatory comment read gate: every changed issue MUST have linear_comments read
            issue_comments = None
            for candidate_key in (lid, alt_id):
                if candidate_key and candidate_key in comments_map:
                    issue_comments = comments_map[candidate_key]
                    break
            if issue_comments is None:
                waterline_blocked = True
                linear_actions.append(
                    {
                        "action": "linear_comments_read_required",
                        "project_id": project_id,
                        "linear_issue_id": lid or alt_id,
                        "bead_id": bead_id or None,
                        "reason": "changed_issue_requires_linear_list_comments",
                    }
                )
                continue

            linear_comment_pages += 1
            for comment in issue_comments:
                if not isinstance(comment, dict):
                    continue
                cid = str(comment.get("id") or "").strip()
                if not cid or cid in processed_comment_ids:
                    continue
                if _is_auto_reply_comment(comment):
                    continue
                author = _extract_comment_author(comment)
                if auth_list and author not in auth_list:
                    continue
                waterline_blocked = True  # Must close delivery/reply readback before advancing waterline
                _add_event(
                    event_type="human_comment",
                    objective_id=bead_id or f"linear:{lid or alt_id}",
                    source="linear:comments",
                    idempotency_key=f"linear-comment:{cid}",
                    payload={
                        "signal": "linear_human_comment",
                        "project_id": project_id,
                        "linear_issue_id": lid or alt_id,
                        "comment_id": cid,
                        "comment_created_at": comment.get("createdAt") or comment.get("created_at"),
                    },
                )

            # Status projection drift check for matched Bead
            if bead_id and bead_id in issue_by_id:
                bead = issue_by_id[bead_id]
                expected_status, status_err = map_bead_to_linear_status(bead, children_by_parent.get(bead_id))
                if status_err:
                    validation_errors.append(status_err)
                else:
                    actual_status = l_issue.get("status") or (l_issue.get("state") or {}).get("name")
                    if actual_status != expected_status:
                        linear_actions.append(
                            {
                                "action": "update_projection",
                                "project_id": project_id,
                                "linear_issue_id": lid or alt_id,
                                "bead_id": bead_id,
                                "fields": {
                                    "status": expected_status,
                                    "title": bead.get("title"),
                                },
                            }
                        )

        if not waterline_blocked and max_updated is not None:
            next_cursor.setdefault("linear_projects", {})[project_id] = {
                "waterline_updated_at": _iso_utc(max_updated),
            }

    # 4. Due dates, review backoff, status mapping & Obsidian/title projections across Beads
    for issue in issues:
        bid = str(issue["id"])
        meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
        mode = meta.get("execution_mode")
        classification = meta.get("classification") or meta.get("task_lifecycle_class")

        mapped_status, status_err = map_bead_to_linear_status(issue, children_by_parent.get(bid))
        if status_err:
            validation_errors.append(status_err)

        # Backoff / review due check
        backoff_dt = _parse_utc(meta.get("next_review_at"))
        due_dt = _parse_utc(issue.get("due_at"))
        backoff_active = backoff_dt is not None and backoff_dt > now_dt and bid not in unread_override_objectives
        if not backoff_active:
            if (backoff_dt is not None and backoff_dt <= now_dt) or (due_dt is not None and due_dt <= now_dt):
                marker = meta.get("next_review_at") or issue.get("due_at") or now_iso
                _add_event(
                    event_type="review_due",
                    objective_id=bid,
                    source="beads:schedule",
                    idempotency_key=f"review-due:{bid}:{marker}",
                    payload={
                        "signal": "review_due",
                        "execution_mode": mode,
                        "due_at": issue.get("due_at"),
                        "next_review_at": meta.get("next_review_at"),
                    },
                )

        # Title projection
        proj = project_title_prefix(issue)
        title_projections.append(proj)

        # Obsidian archive delta check for enrolled managed objectives
        if classification == "managed_objective" or mapped_status is not None:
            fp = _issue_fingerprint(issue)
            prev_fp = base_cursor.get("obsidian_fingerprints", {}).get(bid)
            if prev_fp != fp:
                obsidian_actions.append(
                    {
                        "action": "sync_obsidian_note",
                        "bead_id": bid,
                        "fingerprint": fp,
                    }
                )
                next_cursor.setdefault("obsidian_fingerprints", {})[bid] = fp

    # 5. Worktree ledger overlap / owner drift checks
    if isinstance(worktree_ledger, dict):
        for overlap in worktree_ledger.get("integration_overlaps", []) or []:
            if not isinstance(overlap, dict):
                continue
            obj_id = str(overlap.get("objective_id") or overlap.get("bead_id") or "worktree-overlap")
            paths = overlap.get("paths") or []
            _add_event(
                event_type="write_set_conflict",
                objective_id=obj_id,
                source="worktree:ledger",
                idempotency_key=f"write-set-conflict:{obj_id}:{','.join(sorted(map(str, paths)))}",
                payload={"signal": "integration_overlap", "paths": list(paths)},
            )
        for rec in worktree_ledger.get("worktrees", []) or []:
            if not isinstance(rec, dict):
                continue
            if not rec.get("objective") or not rec.get("thread_id"):
                wt_path = str(rec.get("worktree_name") or rec.get("branch") or "unknown")
                _add_event(
                    event_type="owner_drift",
                    objective_id=str(rec.get("objective") or f"worktree:{wt_path}"),
                    source="worktree:ledger",
                    idempotency_key=f"ownerless-worktree:{wt_path}",
                    payload={"signal": "ownerless_worktree", "branch": rec.get("branch")},
                )

    events = list(events_by_key.values())
    has_work = bool(events or linear_actions or obsidian_actions or validation_errors)
    notify_events = any(
        ev.get("event_type") in {"human_intake", "human_comment", "executor_lost", "write_set_conflict", "owner_drift"}
        for ev in events
    ) or bool(validation_errors)

    counters = {
        "threads_listed": len(thread_list),
        "thread_summaries_changed": thread_summaries_changed,
        "wait_targets": 0,
        "wait_cursors_changed": 0,
        "threads_read": len(threads_read_needed),
        "linear_projects_probed": len(grouped_linear),
        "linear_issues_changed": linear_issues_changed,
        "linear_comment_pages": linear_comment_pages,
        "authority_checks": len(validation_errors),
        "semantic_writes": 0,
        "retries": 0,
        "elapsed_seconds": 0,
        "full_audit_reason": None,
        "pending_events": len(pending_events or []),
        "actionable_events": len(events),
        "validation_errors": len(validation_errors),
    }

    return {
        "schema": PLAN_SCHEMA,
        "wake_agent": has_work,
        "notification": "NOTIFY" if (has_work and notify_events) else "DONT_NOTIFY",
        "reason": "actionable_changes_detected" if has_work else "no_semantic_change",
        "events": events,
        "linear_actions": linear_actions,
        "obsidian_actions": obsidian_actions,
        "title_projections": title_projections,
        "counters": counters,
        "validation_errors": validation_errors,
        "next_cursor": next_cursor,
    }


def _strip_frontmatter(text: str) -> str:
    return runtime.strip_frontmatter(text)


def _extract_manual_sections(body_without_fm: str) -> tuple[str, str]:
    start_idx = body_without_fm.find(MANAGED_START)
    end_idx = body_without_fm.find(MANAGED_END)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return "", body_without_fm.strip()
    before = body_without_fm[:start_idx].strip()
    after = body_without_fm[end_idx + len(MANAGED_END) :].strip()
    return before, after


def render_obsidian_archive_note(
    issue: dict[str, Any],
    *,
    existing_text: str | None = None,
) -> str:
    """Render Obsidian Markdown + Bases properties while preserving manual prose."""
    bead_id = str(issue.get("id") or "unknown")
    title = str(issue.get("title") or bead_id)
    status = str(issue.get("status") or "open")
    metadata = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    mode = str(metadata.get("execution_mode") or "unknown")
    classification = str(metadata.get("classification") or metadata.get("task_lifecycle_class") or "managed_objective")
    owner = str(issue.get("owner") or metadata.get("execution_owner") or "unassigned")
    linear_issue = metadata.get("linear_issue_identifier") or ""
    remaining = metadata.get("remaining")
    remaining_list = [str(item) for item in remaining] if isinstance(remaining, list) else []
    updated_at = str(issue.get("updated_at") or "")
    description = str(issue.get("description") or "").strip()

    frontmatter = "\n".join(
        [
            "---",
            f"bead_id: {json.dumps(bead_id, ensure_ascii=False)}",
            f"title: {json.dumps(title, ensure_ascii=False)}",
            f"status: {json.dumps(status, ensure_ascii=False)}",
            f"execution_mode: {json.dumps(mode, ensure_ascii=False)}",
            f"classification: {json.dumps(classification, ensure_ascii=False)}",
            f"owner: {json.dumps(owner, ensure_ascii=False)}",
            f"linear_issue: {json.dumps(str(linear_issue), ensure_ascii=False)}",
            f"remaining_count: {len(remaining_list)}",
            f"updated_at: {json.dumps(updated_at, ensure_ascii=False)}",
            "---",
        ]
    )

    facts_lines = [
        MANAGED_START,
        f"# {bead_id}: {title}",
        "",
        f"- **Status**: `{status}` (`{mode}`)",
        f"- **Owner**: `{owner}`",
        f"- **Linear**: `{linear_issue or 'unprojected'}`",
        f"- **Current Slice**: {metadata.get('current_slice') or 'n/a'}",
        f"- **First Blocker**: {metadata.get('first_blocker') or 'none'}",
        f"- **Next Action**: {metadata.get('next_action') or 'n/a'}",
    ]
    if description:
        facts_lines.extend(["", "## Motivation & Scope", "", description])
    facts_lines.extend(["", "## Remaining Work", ""])
    if remaining_list:
        facts_lines.extend(f"- [ ] {item}" for item in remaining_list)
    else:
        facts_lines.append("- None (`remaining=[]`)")
    facts_lines.append(MANAGED_END)
    managed_block = "\n".join(facts_lines)

    if existing_text is None:
        return f"{frontmatter}\n\n{managed_block}\n"

    before, after = _extract_manual_sections(_strip_frontmatter(existing_text))
    parts = [frontmatter]
    if before:
        parts.append(before)
    parts.append(managed_block)
    if after:
        parts.append(after)
    return "\n\n".join(parts) + "\n"


def sync_obsidian_archive(
    vault_dir: Path,
    issues: list[dict[str, Any]],
    *,
    expected_hashes: dict[str, str | None] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Read-before-write Obsidian archive sync with conflict detection and readback."""
    root = vault_dir.expanduser().resolve()
    if not root.exists():
        if dry_run:
            pass
        else:
            root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    counts = {"created": 0, "updated": 0, "unchanged": 0, "conflict_skipped": 0}

    for issue in issues:
        if not isinstance(issue, dict) or not issue.get("id"):
            continue
        bead_id = str(issue["id"])
        if not SAFE_ID_RE.fullmatch(bead_id):
            raise SupervisorError(f"invalid bead id for archive note: {bead_id!r}")
        note_path = root / f"{bead_id}.md"
        existing_text = note_path.read_text(encoding="utf-8") if note_path.is_file() else None
        before_sha = (
            hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
            if existing_text is not None
            else None
        )
        if expected_hashes is not None and bead_id in expected_hashes:
            if expected_hashes[bead_id] != before_sha:
                counts["conflict_skipped"] += 1
                results.append(
                    {
                        "bead_id": bead_id,
                        "status": "conflict_skipped",
                        "expected_sha256": expected_hashes[bead_id],
                        "actual_sha256": before_sha,
                    }
                )
                continue

        rendered = render_obsidian_archive_note(issue, existing_text=existing_text)
        if existing_text == rendered:
            counts["unchanged"] += 1
            results.append(
                {
                    "bead_id": bead_id,
                    "status": "unchanged",
                    "sha256": before_sha,
                    "readback_verified": True,
                }
            )
            continue

        action_status = "created" if existing_text is None else "updated"
        if dry_run:
            counts[action_status] += 1
            results.append(
                {
                    "bead_id": bead_id,
                    "status": f"dry_run_{action_status}",
                    "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                    "readback_verified": False,
                }
            )
            continue

        _atomic_write_text(note_path, rendered, mode=0o600)
        readback = note_path.read_text(encoding="utf-8")
        if readback != rendered:
            raise SupervisorError(f"Obsidian archive readback mismatch for {bead_id}")
        counts[action_status] += 1
        results.append(
            {
                "bead_id": bead_id,
                "status": action_status,
                "sha256": hashlib.sha256(readback.encode("utf-8")).hexdigest(),
                "readback_verified": True,
            }
        )

    return {
        "schema": "opl_obsidian_archive_sync.v1",
        "dry_run": dry_run,
        "counts": counts,
        "notes": results,
    }
