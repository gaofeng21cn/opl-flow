#!/usr/bin/env python3
"""Zero-token read-only discovery of active Codex, AntiGravity, and OPL DSH sessions.

Zero Fleet imports. Never reads chat prompts/content, credentials, or locks live SQLite.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime


LOCAL_SESSIONS_SCHEMA = "opl_local_sessions_snapshot.v1"
DEFAULT_HORIZON_SECONDS = 3600
DEFAULT_ACTIVE_WINDOW_SECONDS = 120
MAX_SCAN_PER_CARRIER = 50


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser()


def default_gemini_home() -> Path:
    return Path(os.environ.get("GEMINI_HOME") or (Path.home() / ".gemini")).expanduser()


def default_dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh")).expanduser()


def _iso_from_ts(ts: float) -> str:
    return runtime.iso_utc(dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc), drop_microseconds=True)


def _parse_ts(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return runtime.parse_utc(value).timestamp()
    except Exception:
        return None


def _short_ref(carrier: str, raw_id: str) -> str:
    cleaned = raw_id.strip()
    if len(cleaned) <= 18:
        return f"{carrier}:{cleaned}"
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:6]
    return f"{carrier}:{cleaned[:10]}..{digest}"


def _workspace_label(cwd: str | None) -> str | None:
    if not isinstance(cwd, str) or not cwd.strip():
        return None
    cleaned = cwd.strip().rstrip("/\\")
    if not cleaned:
        return None
    name = Path(cleaned).name
    return name or cleaned


def _workspace_label_from_dsh_slug(slug: str) -> str | None:
    stripped = slug.strip("-")
    if not stripped:
        return None
    if ".dsh-tasks-session-" in stripped:
        return "dsh-task"
    parts = [part for part in stripped.split("-") if part]
    if "workspace" in parts:
        idx = parts.index("workspace")
        tail = parts[idx + 1 :]
        if tail:
            if tail[0] == "app" and len(tail) > 1:
                return "-".join(tail[1:])
            return "-".join(tail)
    return parts[-1] if parts else stripped


def _read_first_json_line(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            line = handle.readline()
    except OSError:
        return None
    if not line.strip():
        return None
    try:
        parsed = json.loads(line)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _read_tail_json_metadata(path: Path, *, max_bytes: int = 4096) -> dict[str, Any] | None:
    """Read only metadata fields from the last line of transcript.jsonl (never content)."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            chunk = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return {
                "type": parsed.get("type"),
                "status": parsed.get("status"),
                "created_at": parsed.get("created_at"),
            }
    return None


def discover_dsh_catalog(*, dsh_home: Path | None = None) -> dict[str, Any]:
    """Read sanitized harness and model combination inventory from OPL DSH."""
    base = (dsh_home or default_dsh_home()).expanduser()
    cat_path = base / "profiles" / "desktop" / "execution-catalog.json"
    if not cat_path.is_file():
        return {"present": False, "harnesses": [], "combinations": []}
    try:
        raw = json.loads(cat_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"present": False, "harnesses": [], "combinations": []}
    if not isinstance(raw, dict):
        return {"present": False, "harnesses": [], "combinations": []}

    harnesses = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or item.get("id") or ""),
            "kind": str(item.get("kind") or ""),
        }
        for item in (raw.get("harnesses") or [])
        if isinstance(item, dict) and item.get("id")
    ]
    combinations = [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or item.get("label") or item.get("id") or ""),
            "enabled": bool(item.get("enabled", True)),
        }
        for item in (raw.get("combinations") or [])
        if isinstance(item, dict) and item.get("id")
    ]
    return {
        "present": True,
        "harnesses": harnesses,
        "combinations": combinations,
    }


def discover_dsh_tasks(*, dsh_home: Path | None = None) -> list[dict[str, Any]]:
    """Read sanitized task_feedback task metadata from OPL DSH (never summary/evidence)."""
    base = (dsh_home or default_dsh_home()).expanduser()
    tf_path = base / "storages" / "task_feedback.json"
    if not tf_path.is_file():
        return []
    try:
        raw = json.loads(tf_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    tables = raw.get("tables") if isinstance(raw, dict) else None
    tasks_obj = tables.get("tasks") if isinstance(tables, dict) else None
    if isinstance(tasks_obj, dict):
        rows = list(tasks_obj.values())
    elif isinstance(tasks_obj, list):
        rows = tasks_obj
    else:
        return []

    results: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("taskId") or row.get("id") or "").strip()
        if not task_id:
            continue
        results.append(
            {
                "task_id": task_id,
                "state": str(row.get("state") or row.get("status") or "unknown"),
                "session_id": str(row.get("sessionId")) if row.get("sessionId") else None,
                "needs_input": bool(row.get("needsInput", False)),
                "updated_at": str(row.get("updatedAt") or ""),
            }
        )
    results.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return results


def _scan_codex_sessions(
    codex_home: Path,
    *,
    now_ts: float,
    horizon_seconds: int,
    active_window_seconds: int,
    max_items: int = MAX_SCAN_PER_CARRIER,
) -> list[dict[str, Any]]:
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.is_dir():
        return []
    candidates: list[tuple[float, Path]] = []
    for path in sessions_dir.rglob("rollout-*.jsonl"):
        try:
            st = path.stat()
        except OSError:
            continue
        if (now_ts - st.st_mtime) <= horizon_seconds:
            candidates.append((st.st_mtime, path))
    candidates.sort(key=lambda pair: pair[0], reverse=True)

    discovered: list[dict[str, Any]] = []
    for mtime, path in candidates[:max_items]:
        header = _read_first_json_line(path) or {}
        payload = header.get("payload") if isinstance(header.get("payload"), dict) else {}
        sid = str(payload.get("id") or payload.get("session_id") or path.stem).strip()
        if not sid:
            continue
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
        source_val = payload.get("source")
        originator = str(payload.get("originator") or "")
        if isinstance(source_val, dict) and "subagent" in source_val:
            surface = "subagent"
        elif "desktop" in originator.lower():
            surface = "desktop"
        else:
            surface = "cli"
        model_provider = str(payload.get("model_provider") or "").strip()
        is_active = (now_ts - mtime) <= active_window_seconds
        discovered.append(
            {
                "carrier": "codex",
                "surface": surface,
                "session_id": sid,
                "session_ref": _short_ref("codex", sid),
                "harness": "codex",
                "model_label": model_provider or "codex",
                "cwd": cwd,
                "workspace_label": _workspace_label(cwd),
                "status": "active" if is_active else "idle",
                "updated_at": _iso_from_ts(mtime),
                "updated_ts": mtime,
            }
        )
    return discovered


def _scan_antigravity_sessions(
    gemini_home: Path,
    dsh_home: Path,
    *,
    now_ts: float,
    horizon_seconds: int,
    active_window_seconds: int,
    max_items: int = MAX_SCAN_PER_CARRIER,
) -> list[dict[str, Any]]:
    brain_roots: list[tuple[str, Path]] = [
        ("desktop", gemini_home / "antigravity" / "brain"),
        ("cli", gemini_home / "antigravity-cli" / "brain"),
    ]
    dsh_agy_root = dsh_home / "antigravity"
    if dsh_agy_root.is_dir():
        for brain in dsh_agy_root.glob("*/.gemini/*/brain"):
            if brain.is_dir():
                brain_roots.append(("dsh-agy", brain))

    candidates: list[tuple[float, str, str, Path]] = []
    for surface, root in brain_roots:
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for conv_dir in entries:
            if not conv_dir.is_dir():
                continue
            transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            if not transcript.is_file():
                continue
            try:
                st = transcript.stat()
            except OSError:
                continue
            if (now_ts - st.st_mtime) <= horizon_seconds:
                candidates.append((st.st_mtime, surface, conv_dir.name, transcript))

    candidates.sort(key=lambda item: item[0], reverse=True)
    discovered: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for mtime, surface, conv_id, transcript in candidates:
        if conv_id in seen_ids:
            continue
        seen_ids.add(conv_id)
        tail = _read_tail_json_metadata(transcript) or {}
        tail_status = str(tail.get("status") or "").lower()
        is_active = (now_ts - mtime) <= active_window_seconds
        if tail_status in {"error", "failed", "cancelled"}:
            status = "error"
        elif is_active:
            status = "active"
        else:
            status = "idle"
        discovered.append(
            {
                "carrier": "antigravity",
                "surface": surface,
                "session_id": conv_id,
                "session_ref": _short_ref("antigravity", conv_id),
                "harness": "antigravity",
                "model_label": f"antigravity ({surface})",
                "cwd": None,
                "workspace_label": None,
                "status": status,
                "updated_at": _iso_from_ts(mtime),
                "updated_ts": mtime,
            }
        )
        if len(discovered) >= max_items:
            break
    return discovered


def _format_dsh_model_label(
    harness_ref: str,
    combination: Any,
    model_ref: Any,
    combo_names: dict[str, str],
) -> str:
    if isinstance(combination, str) and combination in combo_names:
        return combo_names[combination]
    model_name = ""
    if isinstance(model_ref, dict):
        raw_model = str(model_ref.get("model") or "").strip()
        if "::" in raw_model:
            raw_model = raw_model.split("::", 1)[1]
        model_name = raw_model
    if harness_ref and model_name:
        return f"{harness_ref} · {model_name}"
    return harness_ref or model_name or "dsh"


def _scan_dsh_sessions(
    dsh_home: Path,
    catalog: dict[str, Any],
    *,
    now_ts: float,
    horizon_seconds: int,
    active_window_seconds: int,
    max_items: int = MAX_SCAN_PER_CARRIER,
) -> list[dict[str, Any]]:
    combo_names = {
        str(c["id"]): str(c["name"])
        for c in (catalog.get("combinations") or [])
        if isinstance(c, dict) and c.get("id") and c.get("name")
    }
    discovered: list[dict[str, Any]] = []
    seen_harness_ids: set[str] = set()

    hs_dir = dsh_home / "profiles" / "desktop" / "harness-sessions"
    if hs_dir.is_dir():
        hs_candidates: list[tuple[float, Path]] = []
        for path in hs_dir.glob("*.json"):
            try:
                st = path.stat()
            except OSError:
                continue
            if (now_ts - st.st_mtime) <= horizon_seconds:
                hs_candidates.append((st.st_mtime, path))
        hs_candidates.sort(key=lambda pair: pair[0], reverse=True)

        for mtime, path in hs_candidates[:max_items]:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("id") or path.stem).strip()
            if not sid:
                continue
            seen_harness_ids.add(sid)
            # Release turns immediately; only metadata is retained
            raw.pop("turns", None)
            updated_ts = _parse_ts(raw.get("updatedAt")) or mtime
            if (now_ts - updated_ts) > horizon_seconds:
                continue
            harness_ref = str(raw.get("harnessRef") or "dsh").strip()
            cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else None
            origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
            origin_kind = str(origin.get("kind") or "desktop")
            is_active = (now_ts - updated_ts) <= active_window_seconds
            discovered.append(
                {
                    "carrier": "dsh",
                    "surface": f"dsh-{origin_kind}",
                    "session_id": sid,
                    "session_ref": _short_ref("dsh", sid),
                    "harness": harness_ref,
                    "model_label": _format_dsh_model_label(
                        harness_ref,
                        raw.get("combination"),
                        raw.get("modelRef"),
                        combo_names,
                    ),
                    "cwd": cwd,
                    "workspace_label": _workspace_label(cwd),
                    "status": "active" if is_active else "idle",
                    "updated_at": _iso_from_ts(updated_ts),
                    "updated_ts": updated_ts,
                }
            )

    native_dir = dsh_home / "sessions"
    if native_dir.is_dir() and len(discovered) < max_items:
        native_candidates: list[tuple[float, str, Path]] = []
        try:
            slug_dirs = list(native_dir.iterdir())
        except OSError:
            slug_dirs = []
        for slug_dir in slug_dirs:
            if not slug_dir.is_dir():
                continue
            try:
                children = list(slug_dir.iterdir())
            except OSError:
                continue
            for sess_dir in children:
                if not sess_dir.name.startswith("session-"):
                    continue
                try:
                    st = sess_dir.stat()
                except OSError:
                    continue
                if (now_ts - st.st_mtime) <= horizon_seconds:
                    native_candidates.append((st.st_mtime, slug_dir.name, sess_dir))
        native_candidates.sort(key=lambda item: item[0], reverse=True)
        for mtime, slug_name, sess_dir in native_candidates:
            raw_name = sess_dir.name
            clean_sid = raw_name[len("session-") :] if raw_name.startswith("session-") else raw_name
            if clean_sid in seen_harness_ids:
                continue
            seen_harness_ids.add(clean_sid)
            is_active = (now_ts - mtime) <= active_window_seconds
            discovered.append(
                {
                    "carrier": "dsh",
                    "surface": "dsh-native",
                    "session_id": clean_sid,
                    "session_ref": _short_ref("dsh", clean_sid),
                    "harness": "dsh",
                    "model_label": "dsh",
                    "cwd": None,
                    "workspace_label": _workspace_label_from_dsh_slug(slug_name),
                    "status": "active" if is_active else "idle",
                    "updated_at": _iso_from_ts(mtime),
                    "updated_ts": mtime,
                }
            )
            if len(discovered) >= max_items:
                break

    return discovered


def correlate_sessions_with_issues(
    sessions: list[dict[str, Any]],
    issues: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach bound_bead_id from Beads execution_thread and list active workspace occupants."""
    by_exact: dict[str, str] = {}
    by_prefixed: dict[tuple[str, str], str] = {}
    for issue in issues or []:
        if not isinstance(issue, dict) or not issue.get("id"):
            continue
        bid = str(issue["id"])
        meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
        exec_thread = meta.get("execution_thread")
        carrier_hint = str(meta.get("execution_carrier") or "").strip().lower()
        if isinstance(exec_thread, str) and exec_thread.strip():
            raw = exec_thread.strip()
            by_exact[raw] = bid
            if ":" in raw:
                prefix, bare = raw.split(":", 1)
                prefix = prefix.strip().lower()
                bare = bare.strip()
                if prefix in {"codex", "antigravity", "dsh"} and bare:
                    by_prefixed[(prefix, bare)] = bid
            elif carrier_hint in {"codex", "antigravity", "dsh"}:
                by_prefixed[(carrier_hint, raw)] = bid

    correlated: list[dict[str, Any]] = []
    occupants: list[dict[str, Any]] = []
    for entry in sessions:
        carrier = str(entry.get("carrier") or "")
        sid = str(entry.get("session_id") or "")
        bound_bead_id = (
            by_prefixed.get((carrier, sid))
            or by_exact.get(f"{carrier}:{sid}")
            or by_exact.get(sid)
        )
        enriched = {**entry, "bound_bead_id": bound_bead_id}
        correlated.append(enriched)
        if enriched.get("status") == "active" and enriched.get("workspace_label"):
            occupants.append(
                {
                    "workspace_label": enriched["workspace_label"],
                    "carrier": carrier,
                    "harness": enriched.get("harness"),
                    "session_ref": enriched["session_ref"],
                    "bound_bead_id": bound_bead_id,
                }
            )
    return correlated, occupants


def discover_local_sessions(
    *,
    codex_home: Path | None = None,
    gemini_home: Path | None = None,
    dsh_home: Path | None = None,
    issues: list[dict[str, Any]] | None = None,
    horizon_seconds: int = DEFAULT_HORIZON_SECONDS,
    active_window_seconds: int = DEFAULT_ACTIVE_WINDOW_SECONDS,
    active_only: bool = False,
    now: str | dt.datetime | None = None,
) -> dict[str, Any]:
    """Discover local Codex, AntiGravity, and OPL DSH sessions without reading chat contents."""
    now_dt = runtime.parse_utc(now) if isinstance(now, str) else (now or runtime.utc_now())
    assert now_dt is not None
    now_ts = now_dt.timestamp()

    c_home = (codex_home or default_codex_home()).expanduser()
    g_home = (gemini_home or default_gemini_home()).expanduser()
    d_home = (dsh_home or default_dsh_home()).expanduser()

    dsh_catalog = discover_dsh_catalog(dsh_home=d_home)
    dsh_tasks = discover_dsh_tasks(dsh_home=d_home)

    all_sessions = [
        *_scan_codex_sessions(
            c_home,
            now_ts=now_ts,
            horizon_seconds=horizon_seconds,
            active_window_seconds=active_window_seconds,
        ),
        *_scan_antigravity_sessions(
            g_home,
            d_home,
            now_ts=now_ts,
            horizon_seconds=horizon_seconds,
            active_window_seconds=active_window_seconds,
        ),
        *_scan_dsh_sessions(
            d_home,
            dsh_catalog,
            now_ts=now_ts,
            horizon_seconds=horizon_seconds,
            active_window_seconds=active_window_seconds,
        ),
    ]
    all_sessions.sort(key=lambda item: float(item.get("updated_ts") or 0.0), reverse=True)
    if active_only:
        all_sessions = [item for item in all_sessions if item.get("status") == "active"]

    correlated, occupants = correlate_sessions_with_issues(all_sessions, issues)
    by_carrier = {"codex": 0, "antigravity": 0, "dsh": 0}
    for item in correlated:
        c_key = str(item.get("carrier") or "")
        if c_key in by_carrier:
            by_carrier[c_key] += 1

    return {
        "schema": LOCAL_SESSIONS_SCHEMA,
        "observed_at": runtime.iso_utc(now_dt, drop_microseconds=True),
        "horizon_seconds": int(horizon_seconds),
        "active_window_seconds": int(active_window_seconds),
        "counts": {
            "total": len(correlated),
            "active": sum(1 for item in correlated if item.get("status") == "active"),
            "bound": sum(1 for item in correlated if item.get("bound_bead_id")),
            "by_carrier": by_carrier,
        },
        "sessions": correlated,
        "active_workspace_occupants": occupants,
        "dsh_catalog": dsh_catalog,
        "dsh_tasks": dsh_tasks,
    }


def sanitize_sessions_for_projection(discovery: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized session projection excluding local paths, full session IDs, and content."""
    sanitized_items: list[dict[str, Any]] = []
    for item in discovery.get("sessions", []) or []:
        if not isinstance(item, dict):
            continue
        sanitized_items.append(
            {
                "session_ref": str(item.get("session_ref") or ""),
                "carrier": str(item.get("carrier") or ""),
                "surface": str(item.get("surface") or ""),
                "harness": str(item.get("harness") or ""),
                "model_label": str(item.get("model_label") or ""),
                "workspace_label": item.get("workspace_label"),
                "status": str(item.get("status") or "idle"),
                "updated_at": str(item.get("updated_at") or ""),
                "bound_bead_id": item.get("bound_bead_id"),
            }
        )
    return {
        "schema": LOCAL_SESSIONS_SCHEMA,
        "observed_at": discovery.get("observed_at"),
        "counts": dict(discovery.get("counts") or {}),
        "sessions": sanitized_items,
        "active_workspace_occupants": list(discovery.get("active_workspace_occupants") or []),
    }


def build_bound_observations(discovery: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Convert only Bead-bound discovered sessions into Supervisor observation inputs.

    Unbound free chats are intentionally excluded so they never auto-create Beads or wake LLMs.
    """
    threads: list[dict[str, Any]] = []
    antigravity_conversations: list[dict[str, Any]] = []
    dsh_sessions: list[dict[str, Any]] = []

    for item in discovery.get("sessions", []) or []:
        if not isinstance(item, dict) or not item.get("bound_bead_id"):
            continue
        carrier = item.get("carrier")
        sid = str(item.get("session_id") or "")
        updated_at = str(item.get("updated_at") or "")
        status = str(item.get("status") or "idle")
        if not sid:
            continue
        if carrier == "codex":
            threads.append(
                {
                    "id": sid,
                    "updatedAt": updated_at,
                    "status": status,
                    "hasUnreadTurn": False,
                }
            )
        elif carrier == "antigravity":
            run_state = (
                "RUN_STATE_ERROR"
                if status == "error"
                else ("RUN_STATE_RUNNING" if status == "active" else "RUN_STATE_IDLE")
            )
            antigravity_conversations.append(
                {
                    "id": sid,
                    "state": {
                        "updateTime": updated_at,
                        "runState": run_state,
                    },
                }
            )
        elif carrier == "dsh":
            dsh_sessions.append(
                {
                    "id": sid,
                    "updated_at": updated_at,
                    "status": status,
                    "harness": item.get("harness"),
                    "bound_bead_id": item.get("bound_bead_id"),
                }
            )

    return {
        "threads": threads,
        "antigravity_conversations": antigravity_conversations,
        "dsh_sessions": dsh_sessions,
    }


def format_sessions_human(discovery: dict[str, Any], *, max_rows: int = 20) -> str:
    """Format discovered multi-carrier sessions in crisp human-readable Chinese."""
    counts = discovery.get("counts") or {}
    by_c = counts.get("by_carrier") or {}
    sessions = list(discovery.get("sessions") or [])
    lines = [
        (
            f"【本机活跃对话】共 {counts.get('total', 0)} 个"
            f"（运行中 {counts.get('active', 0)} | Codex {by_c.get('codex', 0)}"
            f" | AntiGravity {by_c.get('antigravity', 0)} | OPL DSH {by_c.get('dsh', 0)}"
            f" | 已纳管 {counts.get('bound', 0)}）"
        )
    ]
    if not sessions:
        lines.append("  近期窗口内无活跃或刚更新的对话")
        return "\n".join(lines)

    for item in sessions[:max_rows]:
        st_icon = "●" if item.get("status") == "active" else ("!" if item.get("status") == "error" else "○")
        ws = item.get("workspace_label") or "全局/未标注"
        bead_hint = f" [Bead: {item['bound_bead_id']}]" if item.get("bound_bead_id") else " [未纳管·只防撞车]"
        model_label = item.get("model_label") or item.get("harness") or item.get("carrier")
        lines.append(
            f"  {st_icon} [{item.get('session_ref')}] {model_label} · 目录: {ws} · {item.get('status')}{bead_hint}"
        )
    if len(sessions) > max_rows:
        lines.append(f"  … 其余 {len(sessions) - max_rows} 个对话可用 --json 查看")
    return "\n".join(lines)
