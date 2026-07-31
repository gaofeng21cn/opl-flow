#!/usr/bin/env python3
"""Read-only inspector for recovering missing Codex tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DB = Path.home() / ".codex" / "state_5.sqlite"
SEARCH_FIELDS = (
    "id",
    "title",
    "name",
    "first_user_message",
    "preview",
    "cwd",
    "agent_nickname",
    "agent_role",
)
THREAD_FIELDS = (
    "id",
    "rollout_path",
    "created_at",
    "updated_at",
    "cwd",
    "title",
    "name",
    "archived",
    "archived_at",
    "first_user_message",
    "preview",
    "agent_nickname",
    "agent_role",
    "thread_source",
    "source",
    "git_sha",
    "git_branch",
    "git_origin_url",
)
THREAD_SEARCH_RESULT_FIELDS = (
    "id",
    "archived",
    "cwd",
    "title",
    "name",
    "preview",
    "agent_nickname",
    "agent_role",
    "rollout_path",
    "created_at",
    "updated_at",
    "recency_at_ms",
)


def connect_read_only(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise FileNotFoundError(f"Codex state database not found: {database}")
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def compatible_select(columns: set[str], fields: Iterable[str]) -> str:
    return ", ".join(
        field if field in columns else f"NULL AS {field}"
        for field in fields
    )


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def find_rollout(thread_id: str, thread: dict[str, Any] | None) -> Path | None:
    if thread:
        declared = Path(thread["rollout_path"])
        if declared.is_file():
            return declared

    codex_home = Path.home() / ".codex"
    for root in (codex_home / "sessions", codex_home / "archived_sessions"):
        if not root.exists():
            continue
        matches = list(root.rglob(f"*{thread_id}.jsonl"))
        if matches:
            return sorted(matches)[-1]
    return None


def persistent_spawn_graph(
    connection: sqlite3.Connection,
    thread_id: str,
    max_depth: int,
    max_edges: int,
    excerpt_limit: int,
) -> dict[str, Any]:
    if not table_exists(connection, "thread_spawn_edges"):
        return {
            "table_found": False,
            "returned_count": 0,
            "truncated": False,
            "edges": [],
        }
    thread_columns = table_columns(connection, "threads")
    joined_fields = (
        ("archived", "threads.archived"),
        ("cwd", "threads.cwd"),
        ("title", "threads.title"),
        ("agent_nickname", "threads.agent_nickname"),
        ("agent_role", "threads.agent_role"),
        ("rollout_path", "threads.rollout_path"),
    )
    joined_select = ",\n               ".join(
        expression if field in thread_columns else f"NULL AS {field}"
        for field, expression in joined_fields
    )
    rows = connection.execute(
        f"""
        WITH RECURSIVE graph(parent_id, child_id, status, depth, visited) AS (
          SELECT parent_thread_id, child_thread_id, status, 1,
                 ',' || parent_thread_id || ',' || child_thread_id || ','
          FROM thread_spawn_edges
          WHERE parent_thread_id = ?
          UNION ALL
          SELECT edge.parent_thread_id, edge.child_thread_id, edge.status,
                 graph.depth + 1,
                 graph.visited || edge.child_thread_id || ','
          FROM thread_spawn_edges AS edge
          JOIN graph ON edge.parent_thread_id = graph.child_id
          WHERE graph.depth < ?
            AND instr(graph.visited, ',' || edge.child_thread_id || ',') = 0
        )
        SELECT graph.parent_id, graph.child_id, graph.status, graph.depth,
               {joined_select}
        FROM graph
        LEFT JOIN threads ON threads.id = graph.child_id
        ORDER BY graph.depth, graph.parent_id, graph.child_id
        LIMIT ?
        """,
        (thread_id, max_depth, max_edges + 1),
    ).fetchall()
    truncated = len(rows) > max_edges
    edges = [summarize_mapping(dict(row), ("title",), excerpt_limit) for row in rows[:max_edges]]
    return {
        "table_found": True,
        "returned_count": len(edges),
        "truncated": truncated,
        "edges": edges,
    }


def parse_json_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def parse_json_object(value: Any) -> dict[str, Any] | None:
    parsed = parse_json_value(value)
    return parsed if isinstance(parsed, dict) else None


def text_excerpt(value: str, limit: int) -> dict[str, Any]:
    compact = " ".join(value.split())
    return {
        "excerpt": compact[:limit],
        "truncated": len(compact) > limit,
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


def summarize_mapping(
    value: dict[str, Any] | None,
    text_fields: Iterable[str],
    limit: int,
) -> dict[str, Any] | None:
    if value is None:
        return None
    result = dict(value)
    for field in text_fields:
        text = result.get(field)
        if isinstance(text, str):
            result[field] = text_excerpt(text, limit)
    return result


def message_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in payload.get("content", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"input_text", "output_text", "text"}:
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def terms_match(text: str, terms: Iterable[str]) -> bool:
    lowered = text.casefold()
    return all(term.casefold() in lowered for term in terms)


def agent_status_entries(output: Any) -> list[dict[str, Any]]:
    parsed = parse_json_value(output)
    if isinstance(parsed, dict):
        agents = parsed.get("agents")
        return [item for item in agents if isinstance(item, dict)] if isinstance(agents, list) else []
    if not isinstance(parsed, list):
        return []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        agents = item.get("agents")
        if isinstance(agents, list):
            return [entry for entry in agents if isinstance(entry, dict)]
        text = item.get("text")
        if isinstance(text, str):
            nested = parse_json_object(text)
            agents = nested.get("agents") if nested else None
            if isinstance(agents, list):
                return [entry for entry in agents if isinstance(entry, dict)]
    return []


def bounded_events(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    returned = items[-limit:]
    return {
        "matched_count": len(items),
        "returned_count": len(returned),
        "truncated": len(items) > limit,
        "items": returned,
    }


def scan_rollout(
    rollout: Path,
    terms: list[str],
    excerpt_limit: int,
    event_limit: int,
) -> dict[str, Any]:
    spawn_calls: list[dict[str, Any]] = []
    task_statuses: dict[str, dict[str, Any]] = {}
    thread_calls: list[dict[str, Any]] = []
    matching_messages: list[dict[str, Any]] = []
    malformed_lines = 0

    with rollout.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                malformed_lines += 1
                continue
            if record.get("type") != "response_item":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue

            payload_type = payload.get("type")
            if payload_type == "function_call":
                name = payload.get("name")
                arguments = parse_json_object(payload.get("arguments")) or {}
                if name == "spawn_agent":
                    spawn_calls.append(
                        {
                            "line": line_number,
                            "call_id": payload.get("call_id"),
                            "task_name": arguments.get("task_name"),
                            "fork_turns": arguments.get("fork_turns"),
                        }
                    )
                elif name in {
                    "create_thread",
                    "read_thread",
                    "send_message_to_thread",
                    "set_thread_title",
                    "set_thread_pinned",
                    "set_thread_archived",
                }:
                    thread_calls.append(
                        {
                            "line": line_number,
                            "name": name,
                            "call_id": payload.get("call_id"),
                            "thread_id": arguments.get("threadId"),
                            "title": arguments.get("title"),
                            "pinned": arguments.get("pinned"),
                        }
                    )
            elif payload_type == "function_call_output":
                for agent in agent_status_entries(payload.get("output")):
                    name = agent.get("agent_name")
                    if not isinstance(name, str):
                        continue
                    status = agent.get("agent_status")
                    normalized: dict[str, Any] = {"status": status}
                    if isinstance(status, dict) and isinstance(status.get("completed"), str):
                        normalized = {
                            "status": "completed",
                            **text_excerpt(status["completed"], excerpt_limit),
                        }
                    task_statuses[name] = normalized
            elif payload_type in {"message", "agent_message"} and terms:
                text = message_text(payload)
                if text and terms_match(text, terms):
                    matching_messages.append(
                        {
                            "line": line_number,
                            "type": payload_type,
                            "role": payload.get("role"),
                            "author": payload.get("author"),
                            **text_excerpt(text, excerpt_limit),
                        }
                    )

    return {
        "path": str(rollout),
        "size_bytes": rollout.stat().st_size,
        "malformed_lines": malformed_lines,
        "ephemeral_spawn_calls": spawn_calls,
        "ephemeral_task_statuses": task_statuses,
        "thread_tool_calls": bounded_events(thread_calls, event_limit),
        "matching_messages": bounded_events(matching_messages, event_limit),
    }


def inspect_thread(args: argparse.Namespace) -> dict[str, Any]:
    database = Path(args.database).expanduser()
    with connect_read_only(database) as connection:
        if not table_exists(connection, "threads"):
            raise RuntimeError("Codex state database has no threads table")
        thread_columns = table_columns(connection, "threads")
        row = connection.execute(
            f"""
            SELECT {compatible_select(thread_columns, THREAD_FIELDS)}
            FROM threads
            WHERE id = ?
            """,
            (args.thread_id,),
        ).fetchone()
        thread = row_dict(row)
        graph = persistent_spawn_graph(
            connection,
            args.thread_id,
            args.depth,
            args.graph_limit,
            args.metadata_limit,
        )

    rollout = find_rollout(args.thread_id, thread)
    return {
        "schema_version": "recover_codex_tasks.inspect.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database),
        "database_mode": "read_only",
        "authority_note": "Evidence only; Codex task tools determine UI readability and live status.",
        "thread_id": args.thread_id,
        "thread_found": thread is not None,
        "thread": summarize_mapping(
            thread,
            ("title", "first_user_message", "preview"),
            args.metadata_limit,
        ),
        "persistent_spawn_graph": graph,
        "rollout": scan_rollout(
            rollout,
            args.term,
            args.excerpt_limit,
            args.event_limit,
        )
        if rollout
        else None,
    }


def search_threads(args: argparse.Namespace) -> dict[str, Any]:
    database = Path(args.database).expanduser()
    with connect_read_only(database) as connection:
        if not table_exists(connection, "threads"):
            raise RuntimeError("Codex state database has no threads table")
        thread_columns = table_columns(connection, "threads")
        search_fields = tuple(field for field in SEARCH_FIELDS if field in thread_columns)
        if not search_fields:
            raise RuntimeError("Codex threads table has no searchable metadata fields")
        clauses: list[str] = []
        parameters: list[Any] = []
        for term in args.terms:
            fields = " OR ".join(
                f"lower(coalesce({field}, '')) LIKE lower(?)" for field in search_fields
            )
            clauses.append(f"({fields})")
            parameters.extend([f"%{term}%"] * len(search_fields))
        parameters.append(args.limit)
        order_field = "recency_at_ms" if "recency_at_ms" in thread_columns else "updated_at"
        rows = connection.execute(
            f"""
            SELECT {compatible_select(thread_columns, THREAD_SEARCH_RESULT_FIELDS)}
            FROM threads
            WHERE {" AND ".join(clauses)}
            ORDER BY {order_field} DESC, id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    return {
        "schema_version": "recover_codex_tasks.search.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(database),
        "database_mode": "read_only",
        "authority_note": "Metadata candidates only; verify each task with Codex task tools.",
        "terms": args.terms,
        "count": len(rows),
        "threads": [
            summarize_mapping(dict(row), ("title", "preview"), args.metadata_limit)
            for row in rows
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect Codex task recovery evidence without modifying state."
    )
    parser.add_argument(
        "--database",
        default=str(DEFAULT_DB),
        help=f"Codex SQLite state database (default: {DEFAULT_DB})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect one thread, its spawn graph, and its rollout.",
    )
    inspect_parser.add_argument("--thread-id", required=True)
    inspect_parser.add_argument("--depth", type=int, default=6)
    inspect_parser.add_argument("--graph-limit", type=int, default=100)
    inspect_parser.add_argument("--term", action="append", default=[])
    inspect_parser.add_argument("--excerpt-limit", type=int, default=1200)
    inspect_parser.add_argument("--event-limit", type=int, default=60)
    inspect_parser.add_argument("--metadata-limit", type=int, default=500)
    inspect_parser.set_defaults(handler=inspect_thread)

    search_parser = subparsers.add_parser(
        "search",
        help="Search thread metadata for all supplied terms.",
    )
    search_parser.add_argument("terms", nargs="+")
    search_parser.add_argument("--limit", type=int, default=30)
    search_parser.add_argument("--metadata-limit", type=int, default=500)
    search_parser.set_defaults(handler=search_threads)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "depth") and args.depth < 1:
        parser.error("--depth must be positive")
    if hasattr(args, "graph_limit") and args.graph_limit < 1:
        parser.error("--graph-limit must be positive")
    if hasattr(args, "excerpt_limit") and args.excerpt_limit < 80:
        parser.error("--excerpt-limit must be at least 80")
    if hasattr(args, "event_limit") and args.event_limit < 1:
        parser.error("--event-limit must be positive")
    if hasattr(args, "metadata_limit") and args.metadata_limit < 80:
        parser.error("--metadata-limit must be at least 80")
    if hasattr(args, "limit") and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        result = args.handler(args)
    except (FileNotFoundError, RuntimeError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
