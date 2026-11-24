"""ACID SQLite (WAL mode) state stores with automatic legacy JSON migration.

Zero Fleet imports. Backs OPL Flow event inbox, Fleet lease store, and Fleet
attempt store with busy_timeout, WAL journaling, 0600 file permissions,
tenacity lock-contention retries, and lossless legacy JSON migration.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterator

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime


BUSY_TIMEOUT_MS = 5_000


def _check_mode_0600(path: Path, *, error_cls: type[Exception], label: str) -> None:
    if os.name == "nt":
        return
    if path.stat().st_mode & 0o077:
        raise error_cls(f"{label} must have mode 0600")


def _enforce_sqlite_perms(db_path: Path) -> None:
    runtime.chmod_best_effort(db_path, 0o600)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            runtime.chmod_best_effort(sidecar, 0o600)


def _open_sqlite(db_path: Path, *, private_dir: bool = False) -> sqlite3.Connection:
    if private_dir:
        runtime.ensure_private_dir(db_path.parent)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-create with 0600 permissions before sqlite3 opens the file so there is
    # never a window where the database file is world- or group-readable.
    if not db_path.exists():
        fd = os.open(db_path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        runtime.chmod_best_effort(db_path, 0o600)
    conn = sqlite3.connect(
        str(db_path),
        timeout=BUSY_TIMEOUT_MS / 1000.0,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _enforce_sqlite_perms(db_path)
    return conn


@contextlib.contextmanager
def sqlite_transaction(
    db_path: Path,
    *,
    write: bool = False,
    private_dir: bool = False,
    init_schema: Callable[[sqlite3.Connection], None] | None = None,
) -> Iterator[sqlite3.Connection]:
    """Open a WAL SQLite connection and wrap work in an explicit transaction."""
    conn = _open_sqlite(db_path, private_dir=private_dir)
    try:
        if init_schema is not None:
            init_schema(conn)
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        _enforce_sqlite_perms(db_path)
    finally:
        conn.close()


def _archive_legacy_json(legacy_path: Path) -> None:
    migrated = legacy_path.with_name(f"{legacy_path.name}.migrated")
    try:
        os.replace(legacy_path, migrated)
        runtime.chmod_best_effort(migrated, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Event Inbox Store (inbox.sqlite3 <- legacy inbox.json)
# ---------------------------------------------------------------------------

INBOX_SCHEMA = "opl_workflow_event_inbox.v1"


def _init_inbox_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inbox_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            objective_id TEXT NOT NULL,
            parent_objective_id TEXT,
            record_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
        CREATE INDEX IF NOT EXISTS idx_events_objective ON events(objective_id);
        """
    )


def inbox_db_paths(state_dir: Path) -> tuple[Path, Path, Path]:
    root = state_dir.expanduser().resolve()
    return root / "inbox.sqlite3", root / "inbox.lock", root / "inbox.json"


def inbox_exists(state_dir: Path) -> bool:
    db_path, _, legacy_path = inbox_db_paths(state_dir)
    return db_path.is_file() or legacy_path.is_file()


def _migrate_legacy_inbox_if_needed(
    state_dir: Path,
    *,
    error_cls: type[Exception],
) -> None:
    db_path, _, legacy_path = inbox_db_paths(state_dir)
    if db_path.is_file() or not legacy_path.is_file():
        return
    try:
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise error_cls(f"event inbox is unreadable: {legacy_path}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != INBOX_SCHEMA
        or not isinstance(payload.get("events"), list)
    ):
        raise error_cls(f"event inbox schema is invalid: {legacy_path}")

    def _do_migrate() -> None:
        with sqlite_transaction(
            db_path,
            write=True,
            private_dir=True,
            init_schema=_init_inbox_schema,
        ) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO inbox_meta(key, value) VALUES('schema', ?)",
                (INBOX_SCHEMA,),
            )
            for item in payload["events"]:
                if not isinstance(item, dict) or not item.get("event_id") or not item.get("idempotency_key"):
                    raise error_cls(f"event inbox schema is invalid: {legacy_path}")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO events(
                        event_id, idempotency_key, status, objective_id, parent_objective_id, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item["event_id"]),
                        str(item["idempotency_key"]),
                        str(item.get("status") or "pending"),
                        str(item.get("objective_id") or ""),
                        item.get("parent_objective_id"),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                    ),
                )

    runtime.run_with_retry(_do_migrate)
    _archive_legacy_json(legacy_path)


def read_inbox_store(
    state_dir: Path,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    db_path, _, legacy_path = inbox_db_paths(state_dir)
    if not db_path.is_file() and legacy_path.is_file():
        _migrate_legacy_inbox_if_needed(state_dir, error_cls=error_cls)
    if not db_path.is_file():
        return {"schema": INBOX_SCHEMA, "events": []}

    def _do_read() -> dict[str, Any]:
        try:
            with sqlite_transaction(db_path, write=False, private_dir=True, init_schema=_init_inbox_schema) as conn:
                meta = conn.execute("SELECT value FROM inbox_meta WHERE key = 'schema'").fetchone()
                if meta is not None and meta["value"] != INBOX_SCHEMA:
                    raise error_cls(f"event inbox schema is invalid: {db_path}")
                rows = conn.execute("SELECT record_json FROM events ORDER BY seq ASC").fetchall()
                events = [json.loads(row["record_json"]) for row in rows]
                return {"schema": INBOX_SCHEMA, "events": events}
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
                raise
            raise error_cls(f"event inbox is unreadable: {db_path}") from exc

    return runtime.run_with_retry(_do_read)


def write_inbox_store(
    state_dir: Path,
    payload: dict[str, Any],
    *,
    max_retained_terminal: int,
    error_cls: type[Exception],
) -> None:
    db_path, _, legacy_path = inbox_db_paths(state_dir)
    if not db_path.is_file() and legacy_path.is_file():
        _migrate_legacy_inbox_if_needed(state_dir, error_cls=error_cls)

    events = list(payload.get("events") or [])
    active = [e for e in events if e.get("status") not in {"acked", "dead_letter"}]
    terminal = [e for e in events if e.get("status") in {"acked", "dead_letter"}][-max_retained_terminal:]
    retained = [*active, *terminal]

    def _do_write() -> None:
        with sqlite_transaction(db_path, write=True, private_dir=True, init_schema=_init_inbox_schema) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO inbox_meta(key, value) VALUES('schema', ?)",
                (INBOX_SCHEMA,),
            )
            conn.execute("DELETE FROM events")
            for item in retained:
                conn.execute(
                    """
                    INSERT INTO events(
                        event_id, idempotency_key, status, objective_id, parent_objective_id, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(item["event_id"]),
                        str(item["idempotency_key"]),
                        str(item.get("status") or "pending"),
                        str(item.get("objective_id") or ""),
                        item.get("parent_objective_id"),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                    ),
                )

    runtime.run_with_retry(_do_write)


# ---------------------------------------------------------------------------
# Fleet Lease Store (controller/leases.sqlite3 <- legacy controller/leases.json)
# ---------------------------------------------------------------------------

LEASE_SCHEMA_V2 = "codex_fleet_leases.v2"
LEASE_SCHEMA_V1 = "codex_fleet_leases.v1"


def _init_lease_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lease_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version TEXT NOT NULL,
            generation INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases (
            node_id TEXT PRIMARY KEY,
            lease_id TEXT NOT NULL,
            generation INTEGER NOT NULL,
            record_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lease_audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            record_json TEXT NOT NULL
        );
        """
    )


def lease_db_paths(state_root: Path) -> tuple[Path, Path, Path]:
    return (
        state_root / "controller/leases.sqlite3",
        state_root / "controller/leases.lock",
        state_root / "controller/leases.json",
    )


def _persist_lease_payload(db_path: Path, validated: dict[str, Any]) -> None:
    def _do_write() -> None:
        with sqlite_transaction(db_path, write=True, init_schema=_init_lease_schema) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO lease_meta(id, schema_version, generation) VALUES(1, ?, ?)",
                (str(validated["schema"]), int(validated["generation"])),
            )
            conn.execute("DELETE FROM leases")
            for node_id, lease in sorted(validated["leases"].items()):
                conn.execute(
                    "INSERT INTO leases(node_id, lease_id, generation, record_json) VALUES (?, ?, ?, ?)",
                    (
                        str(node_id),
                        str(lease["lease_id"]),
                        int(lease["generation"]),
                        json.dumps(lease, ensure_ascii=True, sort_keys=True),
                    ),
                )
            conn.execute("DELETE FROM lease_audit")
            for event in validated["audit"][-200:]:
                conn.execute(
                    "INSERT INTO lease_audit(record_json) VALUES (?)",
                    (json.dumps(event, ensure_ascii=True, sort_keys=True),),
                )

    runtime.run_with_retry(_do_write)


def _migrate_legacy_leases_if_needed(
    state_root: Path,
    *,
    validator: Callable[[dict[str, Any]], dict[str, Any]],
    error_cls: type[Exception],
) -> dict[str, Any] | None:
    db_path, _, legacy_path = lease_db_paths(state_root)
    if db_path.is_file() or not legacy_path.is_file():
        return None
    _check_mode_0600(legacy_path, error_cls=error_cls, label="lease store")
    payload = runtime.read_json_object(legacy_path, error_cls=error_cls, label="lease store")
    if payload.get("schema") == LEASE_SCHEMA_V1:
        if payload.get("leases"):
            raise error_cls("active lease v1 state requires explicit release before upgrade")
        payload["schema"] = LEASE_SCHEMA_V2
    validated = validator(payload)
    _persist_lease_payload(db_path, validated)
    _archive_legacy_json(legacy_path)
    return validated


def read_lease_sqlite_store(
    state_root: Path,
    *,
    empty_factory: Callable[[], dict[str, Any]],
    validator: Callable[[dict[str, Any]], dict[str, Any]],
    error_cls: type[Exception],
) -> dict[str, Any]:
    db_path, _, legacy_path = lease_db_paths(state_root)
    if not db_path.is_file():
        if legacy_path.is_file():
            migrated = _migrate_legacy_leases_if_needed(
                state_root, validator=validator, error_cls=error_cls
            )
            assert migrated is not None
            return migrated
        return empty_factory()

    _check_mode_0600(db_path, error_cls=error_cls, label="lease store")

    def _do_read() -> dict[str, Any]:
        try:
            with sqlite_transaction(db_path, write=False, init_schema=_init_lease_schema) as conn:
                meta = conn.execute(
                    "SELECT schema_version, generation FROM lease_meta WHERE id = 1"
                ).fetchone()
                if meta is None:
                    return empty_factory()
                leases: dict[str, Any] = {}
                for row in conn.execute("SELECT node_id, record_json FROM leases ORDER BY node_id ASC"):
                    leases[row["node_id"]] = json.loads(row["record_json"])
                audit = [
                    json.loads(row["record_json"])
                    for row in conn.execute("SELECT record_json FROM lease_audit ORDER BY seq ASC")
                ]
                return {
                    "schema": meta["schema_version"],
                    "generation": int(meta["generation"]),
                    "leases": leases,
                    "audit": audit,
                }
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
                raise
            raise error_cls(f"lease store is unreadable: {db_path}") from exc

    payload = runtime.run_with_retry(_do_read)
    return validator(payload)


def write_lease_sqlite_store(
    state_root: Path,
    payload: dict[str, Any],
    *,
    validator: Callable[[dict[str, Any]], dict[str, Any]],
    error_cls: type[Exception],
) -> None:
    db_path, _, legacy_path = lease_db_paths(state_root)
    validated = validator(payload)
    _persist_lease_payload(db_path, validated)
    if legacy_path.is_file():
        _archive_legacy_json(legacy_path)


# ---------------------------------------------------------------------------
# Fleet Attempt Store (controller/attempts.sqlite3 <- legacy controller/attempts.json)
# ---------------------------------------------------------------------------

ATTEMPTS_SCHEMA = "opl_fleet_attempts.v1"


def _init_attempts_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS attempts_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            objective_id TEXT NOT NULL,
            group_id TEXT,
            state TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            record_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_attempts_state ON attempts(state);
        CREATE INDEX IF NOT EXISTS idx_attempts_node ON attempts(node_id);
        """
    )


def attempt_db_paths(state_root: Path) -> tuple[Path, Path, Path]:
    return (
        state_root / "controller/attempts.sqlite3",
        state_root / "controller/attempts.lock",
        state_root / "controller/attempts.json",
    )


def _persist_attempts(db_path: Path, attempts: dict[str, Any]) -> None:
    def _do_write() -> None:
        with sqlite_transaction(db_path, write=True, private_dir=True, init_schema=_init_attempts_schema) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO attempts_meta(key, value) VALUES('schema', ?)",
                (ATTEMPTS_SCHEMA,),
            )
            conn.execute("DELETE FROM attempts")
            for attempt_id, record in sorted(attempts.items()):
                conn.execute(
                    """
                    INSERT INTO attempts(
                        attempt_id, node_id, objective_id, group_id, state, updated_at, record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(attempt_id),
                        str(record.get("node_id") or ""),
                        str(record.get("objective_id") or ""),
                        record.get("group_id"),
                        str(record.get("state") or ""),
                        str(record.get("updated_at") or ""),
                        json.dumps(record, ensure_ascii=True, sort_keys=True),
                    ),
                )

    runtime.run_with_retry(_do_write)


def _migrate_legacy_attempts_if_needed(
    state_root: Path,
    *,
    error_cls: type[Exception],
) -> dict[str, Any] | None:
    db_path, _, legacy_path = attempt_db_paths(state_root)
    if db_path.is_file() or not legacy_path.is_file():
        return None
    payload = runtime.read_json_object(legacy_path, error_cls=error_cls, label="attempt store")
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != ATTEMPTS_SCHEMA
        or not isinstance(payload.get("attempts"), dict)
    ):
        raise error_cls(f"attempt store schema is invalid: {legacy_path}")
    _persist_attempts(db_path, payload["attempts"])
    _archive_legacy_json(legacy_path)
    return {"schema": ATTEMPTS_SCHEMA, "attempts": dict(payload["attempts"])}


def read_attempt_sqlite_store(
    state_root: Path,
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    db_path, _, legacy_path = attempt_db_paths(state_root)
    if not db_path.is_file():
        if legacy_path.is_file():
            migrated = _migrate_legacy_attempts_if_needed(state_root, error_cls=error_cls)
            assert migrated is not None
            return migrated
        return {"schema": ATTEMPTS_SCHEMA, "attempts": {}}

    def _do_read() -> dict[str, Any]:
        try:
            with sqlite_transaction(db_path, write=False, private_dir=True, init_schema=_init_attempts_schema) as conn:
                meta = conn.execute("SELECT value FROM attempts_meta WHERE key = 'schema'").fetchone()
                if meta is not None and meta["value"] != ATTEMPTS_SCHEMA:
                    raise error_cls(f"attempt store schema is invalid: {db_path}")
                attempts = {
                    row["attempt_id"]: json.loads(row["record_json"])
                    for row in conn.execute("SELECT attempt_id, record_json FROM attempts ORDER BY attempt_id ASC")
                }
                return {"schema": ATTEMPTS_SCHEMA, "attempts": attempts}
        except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
            if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
                raise
            raise error_cls(f"attempt store is unreadable: {db_path}") from exc

    return runtime.run_with_retry(_do_read)


def write_attempt_sqlite_store(
    state_root: Path,
    payload: dict[str, Any],
    *,
    active_states: frozenset[str],
    max_retained_terminal: int,
    error_cls: type[Exception],
) -> None:
    db_path, _, legacy_path = attempt_db_paths(state_root)
    if not db_path.is_file() and legacy_path.is_file():
        _migrate_legacy_attempts_if_needed(state_root, error_cls=error_cls)

    attempts = dict(payload.get("attempts") or {})
    active = {k: v for k, v in attempts.items() if v.get("state") in active_states}
    terminal = [
        (k, v) for k, v in attempts.items() if v.get("state") not in active_states
    ]
    terminal.sort(key=lambda item: str(item[1].get("updated_at") or ""))
    merged = {**dict(terminal[-max_retained_terminal:]), **active}
    _persist_attempts(db_path, merged)
    if legacy_path.is_file():
        _archive_legacy_json(legacy_path)
