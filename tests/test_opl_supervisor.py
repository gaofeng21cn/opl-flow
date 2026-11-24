from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import opl_supervisor as sup
from scripts import opl_workflow as workflow


class OplSupervisorTests(unittest.TestCase):
    def _issue(
        self,
        issue_id: str = "opl-1",
        *,
        status: str = "in_progress",
        mode: str = "active",
        thread: str | None = "thread-1",
        linear_id: str | None = "FG-1",
        remaining: list[str] | None = None,
        next_review_at: str | None = None,
        due_at: str | None = None,
        parent: str | None = None,
        classification: str = "managed_objective",
    ) -> dict:
        meta = {
            "classification": classification,
            "execution_mode": mode,
            "remaining": ["step"] if remaining is None else remaining,
        }
        if thread:
            meta["execution_thread"] = thread
        if linear_id:
            meta["linear_issue_identifier"] = linear_id
        if next_review_at:
            meta["next_review_at"] = next_review_at
        return {
            "id": issue_id,
            "title": f"Task {issue_id}",
            "status": status,
            "priority": 1,
            "owner": "owner@example.com",
            "updated_at": "2026-11-20T00:00:00Z",
            "due_at": due_at,
            "parent": parent,
            "metadata": meta,
        }

    def test_zero_change_fast_path_skips_agent_wake(self) -> None:
        issue = self._issue()
        snap = {"issues": [issue], "validation_errors": []}
        first = sup.detect_changes(
            snap,
            threads=[{"id": "thread-1", "updatedAt": "2026-11-20T00:00:00Z", "status": "idle", "hasUnreadTurn": False, "title": "ACTIVE | A"}],
            now="2026-11-24T00:00:00Z",
        )
        self.assertTrue(first["wake_agent"])

        # Title change alone with same (updatedAt, status, hasUnreadTurn) MUST be no_change!
        second = sup.detect_changes(
            snap,
            cursor=first["next_cursor"],
            threads=[{"id": "thread-1", "updatedAt": "2026-11-20T00:00:00Z", "status": "idle", "hasUnreadTurn": False, "title": "CHANGED TITLE ONLY"}],
            now="2026-11-24T01:00:00Z",
        )
        self.assertFalse(second["wake_agent"])
        self.assertEqual(second["notification"], "DONT_NOTIFY")
        self.assertEqual(second["reason"], "no_semantic_change")
        self.assertEqual(second["events"], [])

    def test_unread_thread_message_overrides_waiting_external_and_backoff(self) -> None:
        issue = self._issue(
            mode="waiting_external",
            status="blocked",
            next_review_at="2026-12-01T00:00:00Z",
        )
        snap = {"issues": [issue], "validation_errors": []}
        cursor = {
            "schema": sup.CURSOR_SCHEMA,
            "threads": {"thread-1": {"updatedAt": "2026-11-20T00:00:00Z", "status": "idle", "hasUnreadTurn": False}},
            "linear_projects": {},
            "linear_issue_comments": {},
            "processed_comment_ids": [],
            "obsidian_fingerprints": {
                "opl-1": sup._issue_fingerprint(issue),
            },
        }
        plan = sup.detect_changes(
            snap,
            cursor=cursor,
            threads=[{"id": "thread-1", "updatedAt": "2026-11-24T01:00:00Z", "status": "idle", "hasUnreadTurn": True}],
            now="2026-11-24T02:00:00Z",
        )
        self.assertTrue(plan["wake_agent"])
        self.assertEqual(plan["notification"], "NOTIFY")
        self.assertEqual(len(plan["events"]), 1)
        self.assertEqual(plan["events"][0]["event_type"], "human_comment")
        self.assertTrue(plan["events"][0]["payload"]["overrides_backoff"])

    def test_linear_comment_gate_blocks_waterline_and_filters_auto_reply(self) -> None:
        issue = self._issue()
        snap = {"issues": [issue], "validation_errors": []}
        cursor = sup.empty_cursor()
        cursor["obsidian_fingerprints"]["opl-1"] = sup._issue_fingerprint(issue)

        # Changed Linear issue WITHOUT linear_comments read -> blocks waterline!
        blocked_plan = sup.detect_changes(
            snap,
            cursor=cursor,
            linear_issues={"proj-1": [{"id": "FG-1", "identifier": "FG-1", "updatedAt": "2026-11-24T01:00:00Z", "status": "In Progress", "assignee": "alice"}]},
            linear_comments={},
            authorized_accounts=["alice"],
            now="2026-11-24T02:00:00Z",
        )
        self.assertTrue(blocked_plan["wake_agent"])
        self.assertTrue(any(a["action"] == "linear_comments_read_required" for a in blocked_plan["linear_actions"]))
        self.assertNotIn("proj-1", blocked_plan["next_cursor"]["linear_projects"])

        # With comments: auto-reply ignored, authorized human comment captured, assignee mismatch flagged
        comment_plan = sup.detect_changes(
            snap,
            cursor=cursor,
            linear_issues={"proj-1": [{"id": "FG-1", "identifier": "FG-1", "updatedAt": "2026-11-24T01:00:00Z", "status": "In Progress", "assignee": "bob"}]},
            linear_comments={
                "FG-1": [
                    {"id": "c-auto", "author": "alice", "body": f"{sup.AUTO_REPLY_MARKER}\nAutomated update"},
                    {"id": "c-human", "author": "alice", "body": "Please ship today", "createdAt": "2026-11-24T01:05:00Z"},
                ]
            },
            authorized_accounts=["alice"],
            now="2026-11-24T02:00:00Z",
        )
        human_events = [e for e in comment_plan["events"] if e["event_type"] == "human_comment"]
        self.assertEqual(len(human_events), 1)
        self.assertEqual(human_events[0]["idempotency_key"], "linear-comment:c-human")
        self.assertTrue(any(a["action"] == "repair_assignee" for a in comment_plan["linear_actions"]))
        # Waterline stays blocked until reply readback completes
        self.assertNotIn("proj-1", comment_plan["next_cursor"]["linear_projects"])

    def test_status_mapping_aggregate_rollup_and_fail_closed_cli_exit(self) -> None:
        parent = self._issue("epic-1", mode="aggregate", status="in_progress", linear_id="FG-10", thread=None)
        child1 = self._issue("c-1", mode="waiting_user", status="blocked", parent="epic-1", linear_id=None, thread=None)
        child2 = self._issue("c-2", mode="monitoring", status="in_progress", parent="epic-1", linear_id=None, thread=None)
        mapped, err = sup.map_bead_to_linear_status(parent, [child1, child2])
        self.assertIsNone(err)
        self.assertEqual(mapped, "Needs Action")

        bad = self._issue("bad-1", mode="unknown_mode")
        mapped_bad, err_bad = sup.map_bead_to_linear_status(bad)
        self.assertIsNone(mapped_bad)
        self.assertIn("unknown or missing execution_mode", str(err_bad))

        # Test supervisor plan CLI exit codes: 0 (no change), 2 (wake agent), 3 (drift)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "inst"
            instance.mkdir()
            cursor_file = root / "cursor.json"
            snap_clean = {
                "schema": "opl_flow_supervisor_snapshot.v1",
                "instance": str(instance),
                "issues": [],
                "validation_errors": [],
                "counts": {"unfinished": 0, "ready": 0, "by_status": {}, "by_execution_mode": {}, "semantic": {}, "validation_errors": 0},
            }
            with mock.patch.object(workflow, "executable", return_value="/usr/bin/bd"), mock.patch.object(workflow, "supervisor_snapshot", return_value=snap_clean):
                rc_idle = workflow.main(["supervisor", "plan", "--instance", str(instance), "--cursor-file", str(cursor_file), "--save-cursor"])
                self.assertEqual(rc_idle, 0)

            snap_wake = {**snap_clean, "issues": [self._issue("opl-9")]}
            with mock.patch.object(workflow, "executable", return_value="/usr/bin/bd"), mock.patch.object(workflow, "supervisor_snapshot", return_value=snap_wake):
                rc_wake = workflow.main(["supervisor", "plan", "--instance", str(instance), "--cursor-file", str(cursor_file)])
                self.assertEqual(rc_wake, 2)

            snap_drift = {**snap_clean, "validation_errors": ["opl-bad: missing execution_mode"]}
            with mock.patch.object(workflow, "executable", return_value="/usr/bin/bd"), mock.patch.object(workflow, "supervisor_snapshot", return_value=snap_drift):
                rc_drift = workflow.main(["supervisor", "plan", "--instance", str(instance), "--cursor-file", str(cursor_file)])
                self.assertEqual(rc_drift, 3)

    def test_obsidian_archive_sync_preserves_manual_notes_and_blocks_conflicts(self) -> None:
        issue = self._issue("opl-42", status="closed", remaining=[])
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()
            note_path = vault / "opl-42.md"
            initial = (
                "---\nbead_id: \"opl-42\"\n---\n\n"
                "## Human Context\nKeep my manual research prose intact.\n\n"
                f"{sup.MANAGED_START}\nold\n{sup.MANAGED_END}\n\n"
                "## Postscript\nAlso keep trailing human notes.\n"
            )
            note_path.write_text(initial, encoding="utf-8")
            initial_sha = hashlib.sha256(initial.encode("utf-8")).hexdigest()

            # Conflict check: wrong expected hash refuses overwrite
            conflict = sup.sync_obsidian_archive(vault, [issue], expected_hashes={"opl-42": "0" * 64})
            self.assertEqual(conflict["counts"]["conflict_skipped"], 1)
            self.assertEqual(note_path.read_text(encoding="utf-8"), initial)

            # Valid expected hash updates managed block while preserving manual notes
            updated = sup.sync_obsidian_archive(vault, [issue], expected_hashes={"opl-42": initial_sha})
            self.assertEqual(updated["counts"]["updated"], 1)
            self.assertTrue(updated["notes"][0]["readback_verified"])
            final_text = note_path.read_text(encoding="utf-8")
            self.assertIn("Keep my manual research prose intact.", final_text)
            self.assertIn("Also keep trailing human notes.", final_text)
            self.assertIn("remaining_count: 0", final_text)


if __name__ == "__main__":
    unittest.main()
