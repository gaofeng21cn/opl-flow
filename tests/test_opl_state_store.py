from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import unittest

from tests.test_opl_fleet import TEST_CONTROL_COMMIT, admission
from fleet import fleet_attempts as attempts
from fleet import fleet_common as common
from fleet import fleet_lease as lease_mod
from scripts import opl_antigravity as antigravity
from scripts import opl_events as events
from scripts import opl_runtime as runtime
from scripts import opl_service as service
from scripts import opl_state_store as state_store
from scripts import opl_supervisor as supervisor


REPO_ROOT = Path(__file__).resolve().parents[1]


class OplStateStoreAndRuntimeTests(unittest.TestCase):
    def _journal_mode(self, db_path: Path) -> str:
        conn = sqlite3.connect(str(db_path))
        try:
            return str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        finally:
            conn.close()

    def test_legacy_inbox_json_migrates_losslessly_to_wal_sqlite_with_0600(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "events"
            state_dir.mkdir(parents=True)
            legacy_path = state_dir / "inbox.json"
            legacy_event = {
                "schema": events.EVENT_SCHEMA,
                "event_id": "ev-legacy001",
                "idempotency_key": "legacy-key-1",
                "event_type": "human_intake",
                "objective_id": "opl-legacy-1",
                "parent_objective_id": None,
                "attempt_id": None,
                "source": "cli:legacy",
                "created_at": "2026-11-24T00:00:00Z",
                "updated_at": "2026-11-24T00:00:00Z",
                "status": "pending",
                "claim_token": None,
                "claim_expires_at": None,
                "claimed_by": None,
                "retry_count": 0,
                "last_error": None,
                "payload": {"signal": "migrated_from_json"},
            }
            legacy_path.write_text(
                json.dumps({"schema": events.INBOX_SCHEMA, "events": [legacy_event]}),
                encoding="utf-8",
            )
            legacy_path.chmod(0o600)

            self.assertTrue(events.inbox_exists(state_dir))
            listed = events.list_events(state_dir)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["event_id"], "ev-legacy001")
            self.assertEqual(listed[0]["payload"]["signal"], "migrated_from_json")

            db_path, _ = events.inbox_paths(state_dir)
            self.assertTrue(db_path.is_file())
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self._journal_mode(db_path), "wal")
            self.assertFalse(legacy_path.exists())
            self.assertTrue((state_dir / "inbox.json.migrated").is_file())

            # Idempotency preserved after migration
            dup = events.emit_event(
                state_dir,
                event_type="human_intake",
                objective_id="opl-legacy-1",
                source="cli:legacy",
                idempotency_key="legacy-key-1",
                payload={"signal": "duplicate"},
            )
            self.assertTrue(dup["deduplicated"])
            self.assertEqual(dup["event"]["event_id"], "ev-legacy001")

    def test_legacy_leases_json_migrates_with_0600_and_enforces_mode_check(self) -> None:
        now = common.utc_now()
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            legacy_path = state_root / "controller/leases.json"
            legacy_path.parent.mkdir(parents=True)
            built = lease_mod.build_lease(
                node_id="mac-mini",
                generation=3,
                owner_task="opl-legacy-lease",
                owner_thread=None,
                owner_run=None,
                role=None,
                workload_class="background",
                priority=250,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=600,
                control_revision=TEST_CONTROL_COMMIT,
                admission=admission(now),
                now=now,
            )
            legacy_payload = {
                "schema": "codex_fleet_leases.v2",
                "generation": 3,
                "leases": {"mac-mini": built},
                "audit": [
                    {
                        "event": "acquire",
                        "at": now.isoformat(),
                        "node_id": "mac-mini",
                        "lease_id": built["lease_id"],
                        "generation": 3,
                        "reason": "legacy",
                    }
                ],
            }
            legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
            legacy_path.chmod(0o644)

            with self.assertRaisesRegex(common.FleetError, "mode 0600"):
                lease_mod.read_lease_store(state_root=state_root)

            legacy_path.chmod(0o600)
            migrated = lease_mod.read_lease_store(state_root=state_root)
            self.assertEqual(migrated["generation"], 3)
            self.assertEqual(migrated["leases"]["mac-mini"]["owner_task"], "opl-legacy-lease")
            self.assertEqual(len(migrated["audit"]), 1)

            db_path, _ = lease_mod.lease_paths(state_root)
            self.assertTrue(db_path.is_file())
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self._journal_mode(db_path), "wal")
            self.assertFalse(legacy_path.exists())
            self.assertTrue((state_root / "controller/leases.json.migrated").is_file())

            # Non-0600 SQLite database also fails closed
            db_path.chmod(0o644)
            with self.assertRaisesRegex(common.FleetError, "mode 0600"):
                lease_mod.read_lease_store(state_root=state_root)

    def test_legacy_attempts_json_migrates_to_wal_sqlite_with_0600(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            legacy_path = state_root / "controller/attempts.json"
            legacy_path.parent.mkdir(parents=True)
            legacy_record = {
                "attempt_id": "att-legacy-1",
                "objective_id": "opl-9",
                "owner_id": "thread-9",
                "adapter": "local-codex",
                "node_id": "local",
                "phase": "executing",
                "state": "running",
                "started_at": "2026-11-24T00:00:00Z",
                "last_heartbeat_at": "2026-11-24T00:00:00Z",
                "updated_at": "2026-11-24T00:00:00Z",
                "resumable": True,
                "interruptible": True,
                "heartbeat_interval_seconds": 60,
                "max_stale_seconds": 300,
                "resume_command_ref": None,
                "handoff_sha256": "a" * 64,
                "lease_id": None,
                "lease_generation": None,
                "lease_nonce": None,
                "lease_active": False,
                "group_id": None,
                "envelope_summary": None,
                "checkpoint_refs": [],
                "result_class": None,
                "blocker_code": None,
                "budget_usage": None,
                "budget_violations": [],
            }
            legacy_path.write_text(
                json.dumps({"schema": attempts.ATTEMPTS_SCHEMA, "attempts": {"att-legacy-1": legacy_record}}),
                encoding="utf-8",
            )
            legacy_path.chmod(0o600)

            rec = attempts.get_attempt("att-legacy-1", state_root=state_root)
            self.assertIsNotNone(rec)
            assert rec is not None
            self.assertEqual(rec["objective_id"], "opl-9")

            db_path, _ = attempts.attempt_paths(state_root)
            self.assertTrue(db_path.is_file())
            self.assertEqual(db_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self._journal_mode(db_path), "wal")
            self.assertFalse(legacy_path.exists())
            self.assertTrue((state_root / "controller/attempts.json.migrated").is_file())

    def test_concurrent_sqlite_writes_and_crash_rollback_safety(self) -> None:
        now = common.utc_now()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ev_dir = root / "events"
            state_root = root / "state"

            # Concurrent event emissions (12 distinct + 4 duplicates)
            def _emit(idx: int) -> dict:
                key = f"conc-key-{idx % 12}"
                return events.emit_event(
                    ev_dir,
                    event_type="human_comment",
                    objective_id=f"opl-{idx % 4}",
                    source="test:concurrent",
                    idempotency_key=key,
                    payload={"signal": f"s-{idx}"},
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(_emit, range(16)))
            created = [r for r in results if not r["deduplicated"]]
            self.assertEqual(len(created), 12)
            self.assertEqual(len(events.list_events(ev_dir)), 12)

            # Concurrent lease acquisition on same node -> exactly 1 winner
            def _acquire(idx: int) -> str | None:
                try:
                    rec = lease_mod.acquire_lease_record(
                        node_id="gpu-node",
                        owner_task=f"task-{idx}",
                        owner_thread=None,
                        owner_run=None,
                        role=None,
                        workload_class="background",
                        priority=200,
                        preemptible=True,
                        phase="interruptible",
                        ttl_seconds=600,
                        control_revision=TEST_CONTROL_COMMIT,
                        admission=admission(now),
                        state_root=state_root,
                        now=now,
                    )
                    return str(rec["owner_task"])
                except common.FleetError:
                    return None

            with ThreadPoolExecutor(max_workers=6) as pool:
                winners = [w for w in pool.map(_acquire, range(6)) if w is not None]
            self.assertEqual(len(winners), 1)
            self.assertEqual(lease_mod.read_lease_store(state_root=state_root)["leases"]["gpu-node"]["owner_task"], winners[0])

            # Crash safety: exception mid-transaction rolls back cleanly
            db_path, _ = events.inbox_paths(ev_dir)
            with self.assertRaises(RuntimeError):
                with state_store.sqlite_transaction(db_path, write=True) as conn:
                    conn.execute("DELETE FROM events")
                    raise RuntimeError("simulated crash before commit")
            self.assertEqual(len(events.list_events(ev_dir)), 12)

    def test_plistlib_xml_escaping_frontmatter_and_tenacity_retry(self) -> None:
        # XML special chars handled cleanly by plistlib
        rendered = service.render_macos_plist(
            "dev.one-person-lab.test",
            ["/usr/bin/env", "arg&with<special>\"chars'"],
            log_dir=Path("/tmp/opl & <logs>"),
            home_dir=Path("/tmp/home & user"),
        )
        parsed = plistlib.loads(rendered.encode("utf-8"))
        self.assertEqual(parsed["ProgramArguments"][1], "arg&with<special>\"chars'")
        self.assertEqual(parsed["EnvironmentVariables"]["HOME"], str(Path("/tmp/home & user").resolve()))

        # Frontmatter edge cases via python-frontmatter
        fm, body = antigravity.split_frontmatter("---\ntrigger: always_on\n---\n# Heading\nBody\n")
        self.assertEqual(fm, "---\ntrigger: always_on\n---\n")
        self.assertEqual(body, "# Heading\nBody\n")
        self.assertEqual(antigravity.split_frontmatter("plain markdown\n"), ("", "plain markdown\n"))
        self.assertEqual(antigravity.split_frontmatter("---\nunclosed\n"), ("", "---\nunclosed\n"))
        self.assertEqual(supervisor._strip_frontmatter("---\nbead_id: \"opl-1\"\n---\n\nBody\n").strip(), "Body")

        # Tenacity retry wrapper recovers from transient OperationalError
        calls = {"count": 0}

        def _flaky() -> str:
            calls["count"] += 1
            if calls["count"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "recovered"

        self.assertEqual(runtime.run_with_retry(_flaky, attempts=4, min_wait=0.001, max_wait=0.01), "recovered")
        self.assertEqual(calls["count"], 3)

    def test_no_fcntl_or_raw_plist_xml_concatenation_in_scripts(self) -> None:
        for script in sorted((REPO_ROOT / "scripts").rglob("*.py")):
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("import fcntl", text, f"Unix-only fcntl found in {script}")
            self.assertNotIn("<plist", text, f"Raw XML plist concatenation found in {script}")

    def test_cached_uv_venv_hydrates_for_installed_plugin_layout(self) -> None:
        import hashlib
        import os
        import subprocess
        import sys
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "installed-plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "pyproject.toml").write_text((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
            lock_bytes = (REPO_ROOT / "uv.lock").read_bytes()
            (plugin_dir / "uv.lock").write_bytes(lock_bytes)
            lock_hash = hashlib.sha256(lock_bytes).hexdigest()[:12]
            cache_dir = root / "venv-cache"

            with (
                patch.dict(os.environ, {"OPL_FLOW_VENV_CACHE_DIR": str(cache_dir)}),
                patch.object(runtime, "_find_uv_binary", return_value="/fake/uv"),
                patch.object(subprocess, "run") as run_mock,
            ):
                def _fake_sync(cmd, **kwargs):
                    env = kwargs["env"]
                    venv_path = Path(env["UV_PROJECT_ENVIRONMENT"])
                    ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
                    site_dir = venv_path / "lib" / ver / "site-packages"
                    site_dir.mkdir(parents=True, exist_ok=True)
                    return subprocess.CompletedProcess(cmd, 0)

                run_mock.side_effect = _fake_sync
                site_dir = runtime._ensure_cached_uv_venv(plugin_dir)
                self.assertIsNotNone(site_dir)
                expected_venv = cache_dir / f"py{sys.version_info.major}.{sys.version_info.minor}-{lock_hash}"
                self.assertTrue(expected_venv.is_dir())
                self.assertEqual(run_mock.call_count, 1)

                # Second call hits existing cached venv without re-invoking uv
                site_dir_2 = runtime._ensure_cached_uv_venv(plugin_dir)
                self.assertEqual(site_dir_2, site_dir)
                self.assertEqual(run_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
