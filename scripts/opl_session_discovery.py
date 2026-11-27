#!/usr/bin/env python3
"""Zero-token read-only discovery of active Codex, AntiGravity, and OPL DSH sessions.

Zero Fleet imports. Never reads chat prompts/content, credentials, or locks live SQLite.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

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


def _read_codex_rollout_meta(path: Path, *, max_lines: int = 16) -> tuple[dict[str, Any], str | None]:
    """Read session_meta payload and first turn_context model without reading prompt text."""
    meta_payload: dict[str, Any] = {}
    model_name: str | None = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for _ in range(max_lines):
                line = handle.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed, dict):
                    continue
                rec_type = parsed.get("type")
                payload = parsed.get("payload")
                if not isinstance(payload, dict):
                    continue
                if rec_type == "session_meta" and not meta_payload:
                    meta_payload = payload
                elif rec_type == "turn_context" and model_name is None:
                    raw_model = str(payload.get("model") or "").strip()
                    if raw_model:
                        model_name = raw_model
                elif "id" in payload and not meta_payload:
                    meta_payload = payload
                if meta_payload and model_name:
                    break
    except OSError:
        return {}, None
    return meta_payload, model_name


def _load_codex_session_titles(codex_home: Path) -> dict[str, str]:
    """Read Codex session_index.jsonl id -> thread_name map safely."""
    idx_path = codex_home / "session_index.jsonl"
    if not idx_path.is_file():
        return {}
    titles: dict[str, str] = {}
    try:
        with idx_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                sid = str(rec.get("id") or "").strip()
                raw_name = str(rec.get("thread_name") or rec.get("title") or "").replace("\r", " ").replace("\n", " ").strip()
                if sid and raw_name:
                    titles[sid] = raw_name[:120]
    except OSError:
        return {}
    return titles


def _parse_file_uri_path(uri: Any) -> str | None:
    if not isinstance(uri, str) or not uri.strip():
        return None
    raw = uri.strip()
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        path = unquote(parsed.path or "")
        return path or None
    if raw.startswith("/") or (len(raw) > 2 and raw[1] == ":"):
        return raw
    return None


def _load_antigravity_summary_index(gemini_home: Path) -> dict[str, dict[str, Any]]:
    """Read-only URI SQLite lookup of AntiGravity conversation metadata (never locks writer)."""
    db_path = gemini_home / "antigravity" / "conversation_summaries.db"
    if not db_path.is_file():
        return {}
    summaries: dict[str, dict[str, Any]] = {}
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
        rows = conn.execute(
            "SELECT conversation_id, title, workspace_uris, status, parent_conversation_id, nesting_depth, not_fully_idle, killed "
            "FROM conversation_summaries"
        ).fetchall()
        for conv_id, raw_title, raw_ws, raw_status, raw_parent, raw_depth, raw_active, raw_killed in rows:
            cid = str(conv_id or "").strip()
            if not cid:
                continue
            cwd = None
            if isinstance(raw_ws, str) and raw_ws.strip():
                try:
                    ws_list = json.loads(raw_ws)
                except json.JSONDecodeError:
                    ws_list = []
                if isinstance(ws_list, list):
                    for candidate_uri in ws_list:
                        parsed_path = _parse_file_uri_path(candidate_uri)
                        if parsed_path:
                            cwd = parsed_path
                            break
            clean_title = (
                str(raw_title or "").replace("\r", " ").replace("\n", " ").strip()[:120]
                or None
            )
            try:
                depth = int(raw_depth or 0)
            except (TypeError, ValueError):
                depth = 0
            summaries[cid] = {
                "title": clean_title,
                "cwd": cwd,
                "status": str(raw_status or "").strip(),
                "parent_conversation_id": str(raw_parent or "").strip() or None,
                "nesting_depth": depth,
                "not_fully_idle": bool(raw_active),
                "killed": bool(raw_killed),
            }
    except sqlite3.Error:
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
    return summaries


def _read_tail_json_metadata(path: Path, *, max_bytes: int = 65536) -> dict[str, Any] | None:
    """Read only metadata fields from the tail of transcript.jsonl (never content)."""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            chunk = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]
    latest_meta: dict[str, Any] | None = None
    latest_model: str | None = None
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        if latest_meta is None:
            latest_meta = {
                "type": parsed.get("type"),
                "status": parsed.get("status"),
                "created_at": parsed.get("created_at"),
            }
        raw_model = str(parsed.get("model") or "").strip()
        if raw_model and latest_model is None:
            latest_model = raw_model
        if latest_meta is not None and latest_model is not None:
            break
    if latest_meta is not None:
        latest_meta["model"] = latest_model
    return latest_meta


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

    codex_titles = _load_codex_session_titles(codex_home)
    discovered: list[dict[str, Any]] = []
    for mtime, path in candidates[:max_items]:
        payload, model_name = _read_codex_rollout_meta(path)
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
                "is_subagent": surface == "subagent",
                "session_id": sid,
                "session_ref": _short_ref("codex", sid),
                "session_title": codex_titles.get(sid),
                "harness": "codex",
                "model_label": model_name or model_provider or "codex",
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
    summary_index = _load_antigravity_summary_index(gemini_home)
    discovered: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for mtime, surface, conv_id, transcript in candidates:
        if conv_id in seen_ids:
            continue
        seen_ids.add(conv_id)
        tail = _read_tail_json_metadata(transcript) or {}
        tail_status = str(tail.get("status") or "").lower()
        tail_model = str(tail.get("model") or "").strip()
        summary = summary_index.get(conv_id, {})
        is_subagent = bool(summary.get("parent_conversation_id")) or int(summary.get("nesting_depth") or 0) > 0
        effective_surface = "subagent" if is_subagent else surface
        cwd = summary.get("cwd")
        db_status = str(summary.get("status") or "")
        is_active = (now_ts - mtime) <= active_window_seconds
        if summary.get("killed"):
            status = "idle"
        elif tail_status in {"error", "failed", "cancelled"}:
            status = "error"
        elif db_status == "CASCADE_RUN_STATUS_RUNNING" or is_active:
            status = "active"
        else:
            status = "idle"
        discovered.append(
            {
                "carrier": "antigravity",
                "surface": effective_surface,
                "is_subagent": is_subagent,
                "session_id": conv_id,
                "session_ref": _short_ref("antigravity", conv_id),
                "session_title": summary.get("title"),
                "harness": "antigravity",
                "model_label": tail_model or f"antigravity ({surface})",
                "cwd": cwd,
                "workspace_label": _workspace_label(cwd),
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
            raw_title = str(raw.get("title") or "").replace("\r", " ").replace("\n", " ").strip()[:120] or None
            discovered.append(
                {
                    "carrier": "dsh",
                    "surface": f"dsh-{origin_kind}",
                    "is_subagent": False,
                    "session_id": sid,
                    "session_ref": _short_ref("dsh", sid),
                    "session_title": raw_title,
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
                    "is_subagent": False,
                    "session_id": clean_sid,
                    "session_ref": _short_ref("dsh", clean_sid),
                    "session_title": None,
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
    seen_occupants: set[tuple[str, str]] = set()
    for entry in sessions:
        carrier = str(entry.get("carrier") or "")
        sid = str(entry.get("session_id") or "")
        is_sub = bool(entry.get("is_subagent")) or str(entry.get("surface") or "") == "subagent"
        bound_bead_id = (
            by_prefixed.get((carrier, sid))
            or by_exact.get(f"{carrier}:{sid}")
            or by_exact.get(sid)
        )
        enriched = {**entry, "is_subagent": is_sub, "bound_bead_id": bound_bead_id}
        correlated.append(enriched)
        ws_label = enriched.get("workspace_label")
        if enriched.get("status") == "active" and ws_label and not is_sub:
            occ_key = (str(ws_label), str(enriched["session_ref"]))
            if occ_key not in seen_occupants:
                seen_occupants.add(occ_key)
                occupants.append(
                    {
                        "workspace_label": ws_label,
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
    ws_occ_counts: dict[str, int] = {}
    for occ in occupants:
        wsl = str(occ.get("workspace_label") or "")
        if wsl:
            ws_occ_counts[wsl] = ws_occ_counts.get(wsl, 0) + 1
    for item in correlated:
        c_key = str(item.get("carrier") or "")
        if c_key in by_carrier:
            by_carrier[c_key] += 1

    primary_count = sum(1 for item in correlated if not item.get("is_subagent"))
    running_primary = sum(1 for item in correlated if item.get("status") == "active" and not item.get("is_subagent"))

    return {
        "schema": LOCAL_SESSIONS_SCHEMA,
        "observed_at": runtime.iso_utc(now_dt, drop_microseconds=True),
        "horizon_seconds": int(horizon_seconds),
        "active_window_seconds": int(active_window_seconds),
        "counts": {
            "total": len(correlated),
            "active": sum(1 for item in correlated if item.get("status") == "active"),
            "primary_total": primary_count,
            "running_primary": running_primary,
            "subagent_total": len(correlated) - primary_count,
            "unique_occupied_workspaces": len(ws_occ_counts),
            "collision_workspaces": sum(1 for n in ws_occ_counts.values() if n >= 2),
            "bound": sum(1 for item in correlated if item.get("bound_bead_id")),
            "by_carrier": by_carrier,
        },
        "sessions": correlated,
        "active_workspace_occupants": occupants,
        "dsh_catalog": dsh_catalog,
        "dsh_tasks": dsh_tasks,
    }


def _safe_session_title(item: dict[str, Any], bound_title: str | None = None) -> str:
    """Build a non-prompt display title from session index or metadata."""
    if isinstance(bound_title, str) and bound_title.strip():
        return bound_title.strip()[:120]
    raw_session_title = item.get("session_title")
    if isinstance(raw_session_title, str) and raw_session_title.strip():
        return raw_session_title.strip()[:120]
    model_label = str(item.get("model_label") or item.get("harness") or item.get("carrier") or "").strip()
    ws_label = str(item.get("workspace_label") or "").strip()
    if ws_label and model_label:
        return f"{ws_label} · {model_label}"[:120]
    return (model_label or ws_label or str(item.get("session_ref") or ""))[:120]


def sanitize_sessions_for_projection(
    discovery: dict[str, Any],
    *,
    include_local_navigation: bool = False,
    host_carrier: str | None = None,
    issue_titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a session projection, stripping paths/IDs unless trusted local navigation is explicitly requested."""
    normalized_host = host_carrier.strip().lower() if isinstance(host_carrier, str) and host_carrier.strip() else None
    if normalized_host not in {"codex", "antigravity", "dsh"}:
        normalized_host = None

    title_map = issue_titles or {}
    sanitized_items: list[dict[str, Any]] = []
    for item in discovery.get("sessions", []) or []:
        if not isinstance(item, dict):
            continue
        carrier = str(item.get("carrier") or "")
        bound_bead_id = item.get("bound_bead_id")
        is_sub = bool(item.get("is_subagent")) or str(item.get("surface") or "") == "subagent"
        entry: dict[str, Any] = {
            "session_ref": str(item.get("session_ref") or ""),
            "carrier": carrier,
            "surface": str(item.get("surface") or ""),
            "is_subagent": is_sub,
            "harness": str(item.get("harness") or ""),
            "model_label": str(item.get("model_label") or ""),
            "workspace_label": item.get("workspace_label"),
            "status": str(item.get("status") or "idle"),
            "updated_at": str(item.get("updated_at") or ""),
            "bound_bead_id": bound_bead_id,
        }
        if include_local_navigation:
            sid = str(item.get("session_id") or "").strip() or None
            cwd = str(item.get("cwd") or "").strip() or None
            bound_title = title_map.get(str(bound_bead_id)) if bound_bead_id else None
            entry["title"] = _safe_session_title(item, bound_title)
            entry["workspace_path"] = cwd
            entry["session_id"] = sid
            entry["thread_id"] = sid if carrier == "codex" and sid else None
            if normalized_host:
                entry["jump_mode"] = (
                    "native_switch" if (carrier == normalized_host and sid is not None) else "external_focus_only"
                )
        sanitized_items.append(entry)

    occupants_out: list[dict[str, Any]] = []
    for occ in discovery.get("active_workspace_occupants") or []:
        if not isinstance(occ, dict):
            continue
        occ_entry = dict(occ)
        if not include_local_navigation:
            occ_entry.pop("workspace_path", None)
            occ_entry.pop("session_id", None)
        occupants_out.append(occ_entry)

    return {
        "schema": LOCAL_SESSIONS_SCHEMA,
        "observed_at": discovery.get("observed_at"),
        "counts": dict(discovery.get("counts") or {}),
        "sessions": sanitized_items,
        "active_workspace_occupants": occupants_out,
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
