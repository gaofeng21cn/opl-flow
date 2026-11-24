from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

from scripts import opl_events as events
from scripts import opl_workflow as workflow


class OplEventsTests(unittest.TestCase):
    def _mock_bd(self, root: Path) -> Path:
        bd = root / "bd"
        bd.write_text(
            """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
db_path = Path(os.environ["BD_STATE_FILE"])
db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else {"seq": 0, "issues": []}
cmd = args[0]

if cmd == "list":
    print(json.dumps(db["issues"]))
elif cmd == "ready":
    print(json.dumps([i for i in db["issues"] if i.get("status") != "closed"]))
elif cmd == "status":
    print(json.dumps({"open": len(db["issues"])}))
elif cmd == "dolt":
    if args[1:2] == ["status"]:
        print(json.dumps({"mode": "embedded"}))
    else:
        print("{}")
elif cmd == "show":
    target = args[1]
    match = next((i for i in db["issues"] if i["id"] == target), None)
    print(json.dumps(match or {}))
elif cmd == "create":
    db["seq"] += 1
    title = args[1]
    ext = args[args.index("--external-ref") + 1]
    meta = json.loads(args[args.index("--metadata") + 1])
    parent = args[args.index("--parent") + 1] if "--parent" in args else None
    issue = {
        "id": f"opl-{db['seq']}",
        "title": title,
        "status": "open",
        "priority": 2,
        "issue_type": args[args.index("--type") + 1],
        "external_ref": ext,
        "parent": parent,
        "metadata": meta,
        "dependencies": [],
    }
    db["issues"].append(issue)
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print(json.dumps(issue))
elif cmd == "update":
    target = args[1]
    for issue in db["issues"]:
        if issue["id"] == target and "--metadata" in args:
            issue["metadata"] = json.loads(args[args.index("--metadata") + 1])
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print("{}")
elif cmd == "dep" and args[1:2] == ["add"]:
    child_id, dep_id = args[2], args[3]
    for issue in db["issues"]:
        if issue["id"] == child_id:
            issue.setdefault("dependencies", []).append({"depends_on_id": dep_id, "type": "blocks"})
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print("{}")
else:
    print("{}")
""",
            encoding="utf-8",
        )
        bd.chmod(bd.stat().st_mode | stat.S_IXUSR)
        return bd

    def test_event_inbox_dedup_privacy_claim_ack_and_dead_letter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "events"
            first = events.emit_event(
                state_dir,
                event_type="human_intake",
                objective_id="opl-1",
                source="cli:intake",
                idempotency_key="intake:opl-1:v1",
                payload={"signal": "created"},
            )
            self.assertFalse(first["deduplicated"])
            dup = events.emit_event(
                state_dir,
                event_type="human_intake",
                objective_id="opl-1",
                source="cli:intake",
                idempotency_key="intake:opl-1:v1",
                payload={"signal": "created"},
            )
            self.assertTrue(dup["deduplicated"])
            self.assertEqual(len(events.list_events(state_dir)), 1)

            with self.assertRaisesRegex(events.EventControlError, "forbidden privacy"):
                events.emit_event(
                    state_dir,
                    event_type="human_comment",
                    objective_id="opl-1",
                    source="test",
                    idempotency_key="bad-key",
                    payload={"prompt": "must not leak"},
                )

            claimed = events.claim_events(state_dir, consumer_id="worker-a", lease_seconds=60, now="2026-11-24T00:00:00Z")
            self.assertEqual(len(claimed["events"]), 1)
            tok = claimed["claim_token"]
            ev_id = claimed["events"][0]["event_id"]

            # Wrong claim token fails closed
            with self.assertRaisesRegex(events.EventControlError, "mismatch"):
                events.ack_events(state_dir, event_ids=[ev_id], claim_token="wrong-token")

            # Retryable failure -> dead_letter after max_retries=2
            events.ack_events(state_dir, event_ids=[ev_id], claim_token=tok, outcome="failed_retryable", max_retries=2, now="2026-11-24T00:01:00Z")
            claimed2 = events.claim_events(state_dir, consumer_id="worker-b", now="2026-11-24T00:02:00Z")
            res2 = events.ack_events(state_dir, event_ids=[ev_id], claim_token=claimed2["claim_token"], outcome="failed_retryable", max_retries=2, now="2026-11-24T00:03:00Z")
            self.assertEqual(res2["updated"][0]["status"], "dead_letter")

    def test_intake_and_idempotent_graph_import_into_beads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            instance.mkdir()
            state_dir = root / "events"
            bd = self._mock_bd(root)
            db_file = root / "bd_state.json"

            with mock.patch.dict(os.environ, {"BD_STATE_FILE": str(db_file)}):
                intake_res = events.intake_objective(
                    instance,
                    str(bd),
                    title="Ship feature X",
                    scope="Implement module X",
                    write_set=["scripts/x.py"],
                    state_dir=state_dir,
                )
                self.assertEqual(intake_res["bead"]["id"], "opl-1")
                self.assertEqual(intake_res["event"]["event_type"], "human_intake")

                graph_spec = {
                    "graph_id": "proj-alpha",
                    "epic": {"title": "Project Alpha", "scope": "Deliver Alpha"},
                    "slices": [
                        {"key": "api", "title": "Build API", "scope": "API endpoints", "write_set": ["src/api.py"]},
                        {"key": "ui", "title": "Build UI", "scope": "UI views", "write_set": ["src/ui.tsx"]},
                        {"key": "docs", "title": "Write Docs", "scope": "Docs", "write_set": ["src/api.py"], "depends_on": ["api"]},
                    ],
                }
                imported1 = events.import_task_graph(instance, str(bd), graph_spec, state_dir=state_dir)
                self.assertEqual(imported1["counts"]["created_slices"], 3)
                self.assertEqual(imported1["counts"]["dependencies_added"], 1)

                # Re-import is idempotent (0 duplicates)
                imported2 = events.import_task_graph(instance, str(bd), graph_spec, state_dir=state_dir)
                self.assertEqual(imported2["counts"]["created_slices"], 0)
                self.assertEqual(imported2["counts"]["reused_slices"], 3)

    def test_evaluate_control_turn_fan_out_callback_unlock_cycle_and_repair_before_proof(self) -> None:
        snap = {
            "issues": [
                {"id": "epic-1", "title": "Epic", "status": "in_progress", "metadata": {"execution_mode": "aggregate"}},
                {"id": "s1", "title": "Slice 1", "status": "in_progress", "parent": "epic-1", "metadata": {"execution_mode": "active", "execution_thread": "t1", "write_set": ["src/a.py"]}},
                {"id": "s2", "title": "Slice 2", "status": "open", "parent": "epic-1", "dependencies": [{"depends_on_id": "s1", "type": "blocks"}], "metadata": {"execution_mode": "backlog", "write_set": ["src/b.py"], "next_action": "Build s2"}},
                {"id": "s3", "title": "Slice 3", "status": "open", "parent": "epic-1", "metadata": {"execution_mode": "backlog", "write_set": ["src/b.py"], "next_action": "Build s3"}},
                {"id": "s4", "title": "Slice 4", "status": "in_progress", "parent": "epic-1", "metadata": {"execution_mode": "active", "first_blocker": "broken import", "next_action": "rerun tests"}},
            ],
            "validation_errors": [],
        }
        callback_event = {
            "event_id": "ev-cb-1",
            "event_type": "worker_callback",
            "objective_id": "s1",
            "parent_objective_id": "epic-1",
            "attempt_id": "att-1",
            "payload": {"outcome": "completed", "artifact_refs": ["git:repo@abc"]},
        }
        turn = events.evaluate_control_turn(snap, root_objective_id="epic-1", pending_events=[callback_event])
        fan_ids = {item["objective_id"] for item in turn["fan_out_batch"]}
        self.assertEqual(fan_ids, {"s2", "s3"})
        self.assertEqual(len(turn["integration_queue"]), 1)
        self.assertEqual(turn["integration_queue"][0]["overlapping_paths"], ["src/b.py"])
        self.assertEqual(len(turn["needs_repair"]), 1)
        self.assertEqual(turn["needs_repair"][0]["objective_id"], "s4")
        self.assertEqual(turn["needs_repair"][0]["action"], "direct_fix")

        # Cycle detection fails closed
        cyclic_snap = {
            "issues": [
                {"id": "a", "status": "open", "dependencies": [{"depends_on_id": "b"}], "metadata": {"execution_mode": "backlog"}},
                {"id": "b", "status": "open", "dependencies": [{"depends_on_id": "a"}], "metadata": {"execution_mode": "backlog"}},
            ],
            "validation_errors": [],
        }
        cyclic_turn = events.evaluate_control_turn(cyclic_snap)
        self.assertTrue(any("cycle" in err for err in cyclic_turn["validation_errors"]))
        self.assertEqual(cyclic_turn["fan_out_batch"], [])

    def test_router_tick_watch_and_inbox_approve_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            instance.mkdir()
            state_dir = root / "events"
            cursor_file = root / "cursor.json"
            bd = self._mock_bd(root)
            db_file = root / "bd_state.json"

            snap_empty = {"issues": [], "validation_errors": []}
            # Idle tick wakes 0 agents
            idle = events.router_tick(instance, str(bd), state_dir=state_dir, cursor_path=cursor_file, snapshot=snap_empty)
            self.assertEqual(idle["status"], "idle")
            self.assertFalse(idle["wake_agent"])
            self.assertFalse(idle["hook_invoked"])

            # Emit an event and invoke failing hook -> failed_retryable, then succeeding hook -> acked
            events.emit_event(
                state_dir,
                event_type="human_intake",
                objective_id="opl-1",
                source="cli:intake",
                idempotency_key="tick-test-1",
            )
            snap_one = {
                "issues": [{"id": "opl-1", "title": "Task 1", "status": "open", "metadata": {"execution_mode": "backlog", "classification": "managed_objective", "remaining": ["do"]}}],
                "validation_errors": [],
            }
            fail_tick = events.router_tick(
                instance,
                str(bd),
                state_dir=state_dir,
                cursor_path=cursor_file,
                snapshot=snap_one,
                control_hook_argv=[sys.executable, "-c", "import sys; sys.exit(1)"],
            )
            self.assertEqual(fail_tick["hook_results"][0]["status"], "failed_retryable")

            ok_tick = events.router_tick(
                instance,
                str(bd),
                state_dir=state_dir,
                cursor_path=cursor_file,
                snapshot=snap_one,
                control_hook_argv=[sys.executable, "-c", "import json, sys; data=json.load(sys.stdin); assert data['schema']=='opl_control_turn_plan.v1'"],
            )
            self.assertEqual(ok_tick["hook_results"][0]["status"], "acked")

            watch_res = events.router_watch(
                instance,
                str(bd),
                interval_seconds=0.0,
                max_iterations=2,
                state_dir=state_dir,
                cursor_path=cursor_file,
                snapshot_fn=lambda: snap_one,
                sleep_fn=lambda _s: None,
            )
            self.assertEqual(watch_res["iterations"], 2)

            # Inbox list & approve-archive safety gate
            db_file.write_text(
                json.dumps(
                    {
                        "seq": 1,
                        "issues": [
                            {
                                "id": "opl-done",
                                "title": "Done task",
                                "status": "closed",
                                "metadata": {"classification": "managed_objective", "execution_mode": "active", "remaining": []},
                            },
                            {
                                "id": "opl-open",
                                "title": "Needs user",
                                "status": "blocked",
                                "metadata": {"classification": "managed_objective", "execution_mode": "waiting_user", "remaining": ["approve"]},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"BD_STATE_FILE": str(db_file)}):
                summary = events.list_inbox_summary(
                    {"issues": json.loads(db_file.read_text())["issues"]},
                    state_dir=state_dir,
                )
                self.assertEqual(len(summary["safe_to_archive"]), 1)
                self.assertFalse(summary["safe_to_archive"][0]["archive_performed"])
                self.assertEqual(len(summary["needs_action"]), 1)

                with self.assertRaisesRegex(events.EventControlError, "not closed"):
                    events.approve_archive(instance, str(bd), "opl-open", approved_by="gaofeng")

                receipt = events.approve_archive(instance, str(bd), "opl-done", approved_by="gaofeng")
                self.assertTrue(receipt["archive_approved"])
                self.assertEqual(receipt["approved_by"], "gaofeng")

            # Verify CLI entry point for inbox list
            with (
                mock.patch.dict(os.environ, {"BD_STATE_FILE": str(db_file)}),
                mock.patch.object(workflow, "executable", return_value=str(bd)),
            ):
                rc = workflow.main(["inbox", "list", "--instance", str(instance), "--event-state-dir", str(state_dir)])
                self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
