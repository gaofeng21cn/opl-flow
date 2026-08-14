from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import worktree_lifecycle


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class WorktreeLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.remote = root / "remote.git"
        self.backup = root / "backup.git"
        self.lane = root / "lane"
        self.other_lane = root / "other-lane"
        self.ledger = root / "state" / "ledger.json"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "OPL Flow Tests")
        git(self.repo, "config", "user.email", "opl-flow-tests@example.invalid")
        (self.repo / ".gitignore").write_text(".codegraph/\n", encoding="utf-8")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", ".gitignore", "base.txt")
        git(self.repo, "commit", "-m", "base")
        git(root, "init", "--bare", str(self.remote))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        git(self.repo, "worktree", "add", "-b", "lane", str(self.lane), "main")

    def register(self, lane: Path | None = None, write_set: list[str] | None = None) -> dict[str, object]:
        return worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=lane or self.lane,
            thread_id="thread-1",
            objective_id="objective-1",
            owner="owner-1",
            execution_owner="owner-1",
            next_action="continue",
            write_set=write_set or ["lane.txt"],
        )

    def commit_lane(self) -> None:
        (self.lane / "lane.txt").write_text("lane\n", encoding="utf-8")
        git(self.lane, "add", "lane.txt")
        git(self.lane, "commit", "-m", "lane change")

    def absorb_lane(self) -> None:
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")

    def shared_codegraph_holder(self) -> tuple[dict[str, object], Path]:
        index_dir = self.lane / ".codegraph"
        index_dir.mkdir(exist_ok=True)
        database = index_dir / "codegraph.db"
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("CREATE TABLE symbols (name TEXT)")
        connection.execute("INSERT INTO symbols VALUES ('safe')")
        connection.commit()
        connection.close()
        shared_root = Path(self.temp.name) / "shared"
        external_database = shared_root / ".codegraph" / "codegraph.db"
        holder: dict[str, object] = {
            "pid": os.getpid(),
            "command": "node",
            "process_command": (
                "/opt/codegraph/node /opt/codegraph/lib/dist/bin/codegraph.js serve --mcp"
            ),
            "started_at": "Thu Jul 30 07:28:00 2026",
            "files": [
                {
                    "fd": "15",
                    "type": "REG",
                    "device": hex(database.stat().st_dev),
                    "inode": database.stat().st_ino,
                    "path": str(database),
                    "deleted": False,
                }
            ],
            "codegraph_indexes": [
                {
                    "path": str(database),
                    "device": hex(database.stat().st_dev),
                    "inode": database.stat().st_ino,
                },
                {
                    "path": str(external_database),
                    "device": "0x1",
                    "inode": 88,
                },
            ],
        }
        return holder, shared_root

    def shared_holder_scans(
        self,
        holder: dict[str, object],
        shared_root: Path,
        *,
        final_available: bool = True,
        restarted: bool = False,
        changed_inode: bool = False,
    ) -> list[tuple[dict[str, list[dict[str, object]]], bool]]:
        lane_holders = {str(self.lane.resolve()): [holder]}
        external_holder = {
            **holder,
            "started_at": holder["started_at"],
            "files": [
                {
                    "fd": "18",
                    "type": "REG",
                    "device": "0x1",
                    "inode": 88,
                    "path": str(shared_root / ".codegraph" / "codegraph.db"),
                    "deleted": False,
                }
            ],
            "codegraph_indexes": [
                {
                    **holder["codegraph_indexes"][1],
                    "inode": 88,
                }
            ],
        }
        external_holders = {str(shared_root.resolve()): [external_holder]}
        final_holder = {
            **external_holder,
            "started_at": (
                "Thu Jul 30 07:29:00 2026"
                if restarted
                else holder["started_at"]
            ),
            "files": [
                {
                    **external_holder["files"][0],
                    "inode": 89 if changed_inode else 88,
                }
            ],
            "codegraph_indexes": [
                {
                    **holder["codegraph_indexes"][1],
                    "inode": 89 if changed_inode else 88,
                }
            ],
        }
        final_holders = {str(shared_root.resolve()): [final_holder]}
        return [
            (lane_holders, True),
            (lane_holders, True),
            (external_holders, True),
            (external_holders, True),
            (final_holders if final_available else {}, final_available),
        ]

    def test_register_allows_overlap_and_records_integration_evidence(self) -> None:
        first = self.register()
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            "other-lane",
            str(self.other_lane),
            "main",
        )

        self.assertEqual(os.stat(self.ledger).st_mode & 0o777, 0o600)
        second = worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=self.other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue",
            write_set=["lane.txt"],
        )
        self.assertEqual(first["integration_overlaps"], [])
        self.assertEqual(second["integration_overlaps"][0]["owner"], "owner-1")
        self.assertEqual(second["integration_overlaps"][0]["paths"], ["lane.txt"])
        entries = json.loads(self.ledger.read_text())["entries"]
        self.assertEqual(len(entries), 2)

    def test_checkpoint_pushes_exact_commit_and_tree(self) -> None:
        self.register()
        self.commit_lane()

        receipt = worktree_lifecycle.checkpoint(
            self.ledger,
            worktree=self.lane,
            remote="origin",
        )

        self.assertEqual(receipt["commit"], git(self.lane, "rev-parse", "HEAD"))
        self.assertEqual(receipt["tree"], git(self.lane, "rev-parse", "HEAD^{tree}"))
        self.assertTrue(git(self.lane, "ls-remote", "--heads", "origin", "refs/heads/lane"))

    def test_transfer_owner_preserves_obligation_and_updates_overlap_identity(self) -> None:
        self.register()
        self.commit_lane()
        recovery = worktree_lifecycle.checkpoint(
            self.ledger,
            worktree=self.lane,
            remote="origin",
        )
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            "other-lane",
            str(self.other_lane),
            "main",
        )
        worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=self.other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue",
            write_set=["lane.txt"],
        )

        receipt = worktree_lifecycle.transfer_owner(
            self.ledger,
            repo_root=self.repo,
            worktree=self.lane,
            expected_thread_id="thread-1",
            expected_objective_id="objective-1",
            expected_owner="owner-1",
            expected_execution_owner="owner-1",
            new_thread_id="thread-recovery",
            new_owner="owner-recovery",
            new_execution_owner="executor-recovery",
            next_action="resume existing lane",
            reason="original execution owner is no longer reachable",
        )

        self.assertEqual(receipt["thread_id"], "thread-recovery")
        self.assertEqual(receipt["objective_id"], "objective-1")
        self.assertEqual(receipt["owner"], "owner-recovery")
        self.assertEqual(receipt["execution_owner"], "executor-recovery")
        self.assertEqual(receipt["write_set"], ["lane.txt"])
        self.assertEqual(receipt["remote_recovery"], recovery)
        transfer = receipt["ownership_transfers"][0]
        self.assertEqual(transfer["from"]["thread_id"], "thread-1")
        self.assertEqual(transfer["to"]["thread_id"], "thread-recovery")
        entries = json.loads(self.ledger.read_text())["entries"]
        other = next(
            item for item in entries if item["worktree"] == str(self.other_lane.resolve())
        )
        self.assertEqual(other["integration_overlaps"][0]["thread_id"], "thread-recovery")
        self.assertEqual(other["integration_overlaps"][0]["owner"], "owner-recovery")

    def test_transfer_owner_fails_closed_on_identity_drift(self) -> None:
        self.register()
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "identity changed"):
            worktree_lifecycle.transfer_owner(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="stale-owner",
                expected_execution_owner="owner-1",
                new_thread_id="thread-recovery",
                new_owner="owner-recovery",
                new_execution_owner="owner-recovery",
                next_action="resume existing lane",
                reason="original execution owner is no longer reachable",
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_preserves_source_custody_and_recovery(self) -> None:
        self.register()
        self.commit_lane()
        source_head = git(self.lane, "rev-parse", "HEAD")
        source_tree = git(self.lane, "rev-parse", "HEAD^{tree}")
        source_bytes = (self.lane / "lane.txt").read_bytes()
        recovery = worktree_lifecycle.checkpoint(
            self.ledger,
            worktree=self.lane,
            remote="origin",
        )
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            "other-lane",
            str(self.other_lane),
            "main",
        )
        worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=self.other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue",
            write_set=["lane.txt"],
        )
        before = self.register()

        with patch.object(
            worktree_lifecycle,
            "now",
            return_value="2026-07-31T01:02:03Z",
        ):
            receipt = worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-current",
                next_action="continue under current objective",
                reason="  user replaced the objective  ",
            )

        self.assertEqual(receipt["objective_id"], "objective-current")
        self.assertEqual(receipt["next_action"], "continue under current objective")
        self.assertEqual(receipt["updated_at"], "2026-07-31T01:02:03Z")
        self.assertEqual(receipt["thread_id"], before["thread_id"])
        self.assertEqual(receipt["owner"], before["owner"])
        self.assertEqual(receipt["execution_owner"], before["execution_owner"])
        self.assertEqual(receipt["worktree"], before["worktree"])
        self.assertEqual(receipt["repo_root"], before["repo_root"])
        self.assertEqual(receipt["status"], before["status"])
        self.assertEqual(receipt["write_set"], before["write_set"])
        self.assertEqual(receipt["integration_overlaps"], before["integration_overlaps"])
        self.assertEqual(receipt["remote_recovery"], recovery)
        self.assertEqual(
            set(receipt) - set(before),
            {"objective_amendments", "updated_at"},
        )
        amendment = receipt["objective_amendments"][0]
        self.assertEqual(amendment["recorded_at"], "2026-07-31T01:02:03Z")
        self.assertEqual(amendment["reason"], "user replaced the objective")
        self.assertEqual(
            amendment["actor"],
            {
                "thread_id": "thread-1",
                "owner": "owner-1",
                "execution_owner": "owner-1",
            },
        )
        self.assertEqual(
            amendment["from"],
            {
                "objective_id": "objective-1",
                "next_action": "continue",
            },
        )
        self.assertEqual(
            amendment["to"],
            {
                "objective_id": "objective-current",
                "next_action": "continue under current objective",
            },
        )
        entries = json.loads(self.ledger.read_text(encoding="utf-8"))["entries"]
        other = next(
            item for item in entries if item["worktree"] == str(self.other_lane.resolve())
        )
        self.assertEqual(
            other["integration_overlaps"][0]["objective_id"],
            "objective-current",
        )
        self.assertEqual(git(self.lane, "rev-parse", "HEAD"), source_head)
        self.assertEqual(git(self.lane, "rev-parse", "HEAD^{tree}"), source_tree)
        self.assertEqual((self.lane / "lane.txt").read_bytes(), source_bytes)

    def test_amend_objective_appends_deterministic_history(self) -> None:
        self.register()

        with patch.object(
            worktree_lifecycle,
            "now",
            side_effect=[
                "2026-07-31T01:02:03Z",
                "2026-07-31T01:02:03Z",
                "2026-07-31T02:03:04Z",
                "2026-07-31T02:03:04Z",
            ],
        ):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-2",
                next_action="continue objective 2",
                reason="first amendment",
            )
            receipt = worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-2",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-3",
                next_action="continue objective 3",
                reason="second amendment",
            )

        self.assertEqual(
            [
                (
                    item["recorded_at"],
                    item["from"]["objective_id"],
                    item["to"]["objective_id"],
                    item["reason"],
                )
                for item in receipt["objective_amendments"]
            ],
            [
                (
                    "2026-07-31T01:02:03Z",
                    "objective-1",
                    "objective-2",
                    "first amendment",
                ),
                (
                    "2026-07-31T02:03:04Z",
                    "objective-2",
                    "objective-3",
                    "second amendment",
                ),
            ],
        )

    def test_amend_objective_fails_closed_on_identity_drift(self) -> None:
        self.register()
        before = self.ledger.read_bytes()
        expected_identity = {
            "expected_thread_id": "thread-1",
            "expected_objective_id": "objective-1",
            "expected_owner": "owner-1",
            "expected_execution_owner": "owner-1",
        }

        for field in expected_identity:
            stale_identity = {**expected_identity, field: "stale"}
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    worktree_lifecycle.LifecycleError,
                    "identity changed",
                ):
                    worktree_lifecycle.amend_objective(
                        self.ledger,
                        repo_root=self.repo,
                        worktree=self.lane,
                        **stale_identity,
                        new_objective_id="objective-current",
                        next_action="continue under current objective",
                        reason="user replaced the objective",
                    )
                self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_rejects_empty_reason_without_mutation(self) -> None:
        self.register()
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "reason"):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-current",
                next_action="continue under current objective",
                reason=" \t ",
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_rejects_same_objective_without_mutation(self) -> None:
        self.register()
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "must change"):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-1",
                next_action="continue under current objective",
                reason="user replaced the objective",
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_rejects_invalid_history_without_mutation(self) -> None:
        self.register()
        payload = json.loads(self.ledger.read_text(encoding="utf-8"))
        payload["entries"][0]["objective_amendments"] = {}
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "history is invalid"):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-current",
                next_action="continue under current objective",
                reason="user replaced the objective",
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_fails_closed_without_active_receipt(self) -> None:
        self.register()
        payload = json.loads(self.ledger.read_text(encoding="utf-8"))
        payload["entries"][0]["status"] = "SAFE_TO_ARCHIVE"
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "ACTIVE receipt"):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-current",
                next_action="continue under current objective",
                reason="user replaced the objective",
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_amend_objective_fails_closed_without_receipt(self) -> None:
        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "ACTIVE receipt"):
            worktree_lifecycle.amend_objective(
                self.ledger,
                repo_root=self.repo,
                worktree=self.lane,
                expected_thread_id="thread-1",
                expected_objective_id="objective-1",
                expected_owner="owner-1",
                expected_execution_owner="owner-1",
                new_objective_id="objective-current",
                next_action="continue under current objective",
                reason="user replaced the objective",
            )

        self.assertFalse(self.ledger.exists())

    def test_parser_exposes_amend_objective_identity_guards(self) -> None:
        arguments = worktree_lifecycle.parser().parse_args(
            [
                "amend-objective",
                "--repo-root",
                str(self.repo),
                "--worktree",
                str(self.lane),
                "--expected-thread-id",
                "thread-1",
                "--expected-objective-id",
                "objective-1",
                "--expected-owner",
                "owner-1",
                "--expected-execution-owner",
                "owner-1",
                "--new-objective-id",
                "objective-current",
                "--next-action",
                "continue",
                "--reason",
                "user replaced the objective",
            ]
        )

        self.assertEqual(arguments.command, "amend-objective")
        self.assertEqual(arguments.reason, "user replaced the objective")
        self.assertIn("amend-objective", worktree_lifecycle.parser().format_help())

    def test_cli_amend_objective_records_reason(self) -> None:
        self.register()

        completed = subprocess.run(
            [
                "python3",
                "-B",
                str(Path(worktree_lifecycle.__file__).resolve()),
                "--ledger",
                str(self.ledger),
                "amend-objective",
                "--repo-root",
                str(self.repo),
                "--worktree",
                str(self.lane),
                "--expected-thread-id",
                "thread-1",
                "--expected-objective-id",
                "objective-1",
                "--expected-owner",
                "owner-1",
                "--expected-execution-owner",
                "owner-1",
                "--new-objective-id",
                "objective-current",
                "--next-action",
                "continue under current objective",
                "--reason",
                "user replaced the objective",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["objective_id"], "objective-current")
        self.assertEqual(
            receipt["objective_amendments"][0]["reason"],
            "user replaced the objective",
        )

    def test_checkpoint_rejects_noncanonical_remote(self) -> None:
        self.register()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "canonical upstream"):
            worktree_lifecycle.checkpoint(
                self.ledger,
                worktree=self.lane,
                remote="backup",
            )

    def test_status_is_read_only(self) -> None:
        receipt = self.register()
        before = self.ledger.read_bytes()

        result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(receipt["repo_root"], str(self.repo.resolve()))
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_status_ignores_other_repo_active_receipt(self) -> None:
        self.register()
        root = Path(self.temp.name)
        other_repo = root / "unrelated-repo"
        other_remote = root / "unrelated-remote.git"
        other_lane = root / "unrelated-lane"
        other_repo.mkdir()
        git(other_repo, "init", "-b", "main")
        git(other_repo, "config", "user.name", "OPL Flow Tests")
        git(other_repo, "config", "user.email", "opl-flow-tests@example.invalid")
        (other_repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(other_repo, "add", "base.txt")
        git(other_repo, "commit", "-m", "base")
        git(root, "init", "--bare", str(other_remote))
        git(other_repo, "remote", "add", "origin", str(other_remote))
        git(other_repo, "push", "-u", "origin", "main")
        git(
            other_repo,
            "worktree",
            "add",
            "-b",
            "unrelated-lane",
            str(other_lane),
            "main",
        )
        worktree_lifecycle.register(
            self.ledger,
            repo_root=other_repo,
            worktree=other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue unrelated work",
            write_set=["unrelated.txt"],
        )

        result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["stale_receipts"], [])
        self.assertEqual(len(result["repos"]), 1)
        self.assertEqual(result["repos"][0]["repo_root"], str(self.repo.resolve()))

        payload = json.loads(self.ledger.read_text())
        unrelated = next(
            item
            for item in payload["entries"]
            if item["worktree"] == str(other_lane.resolve())
        )
        unrelated.pop("repo_root")
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")

        legacy_result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(legacy_result["ok"])
        self.assertEqual(legacy_result["stale_receipts"], [])
        self.assertEqual(len(legacy_result["repos"]), 1)

        payload = json.loads(self.ledger.read_text())
        unrelated = next(
            item
            for item in payload["entries"]
            if item["worktree"] == str(other_lane.resolve())
        )
        unrelated["repo_root"] = str(self.repo.resolve())
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")

        mismatched_result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertFalse(mismatched_result["ok"])
        self.assertEqual(
            mismatched_result["stale_receipts"],
            [str(other_lane.resolve())],
        )

    def test_status_keeps_declared_repo_stale_receipt_fail_closed(self) -> None:
        self.register()
        payload = json.loads(self.ledger.read_text())
        missing = Path(self.temp.name) / "missing-lane"
        payload["entries"][0]["worktree"] = str(missing)
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")

        result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["stale_receipts"], [str(missing.resolve())])

    def test_status_keeps_absent_declared_repo_as_stale_receipt(self) -> None:
        self.register()
        payload = json.loads(self.ledger.read_text())
        missing_repo = Path(self.temp.name) / "retired-repo"
        missing_lane = Path(self.temp.name) / "retired-repo-lane"
        payload["entries"][0]["repo_root"] = str(missing_repo)
        payload["entries"][0]["worktree"] = str(missing_lane)
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        git(self.repo, "worktree", "remove", str(self.lane))

        result = worktree_lifecycle.status(
            self.ledger,
            holders={},
            holder_scan_available=True,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["repos"], [])
        self.assertEqual(result["stale_receipts"], [str(missing_lane.resolve())])

        scoped_result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(scoped_result["ok"])
        self.assertEqual(scoped_result["stale_receipts"], [])
        self.assertEqual(
            scoped_result["repos"][0]["repo_root"],
            str(self.repo.resolve()),
        )

    def test_close_refuses_dirty_or_unabsorbed_work(self) -> None:
        self.register()
        (self.lane / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "cleanup-ready"):
            worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
                holders={},
                holder_scan_available=True,
            )
        (self.lane / "dirty.txt").unlink()
        self.commit_lane()
        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "cleanup-ready"):
            worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
                holders={},
                holder_scan_available=True,
            )

    def test_close_removes_absorbed_lane_and_recovery_refs(self) -> None:
        self.register()
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            "other-lane",
            str(self.other_lane),
            "main",
        )
        worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=self.other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue",
            write_set=["lane.txt"],
        )
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")

        result = worktree_lifecycle.close(
            self.ledger,
            worktree=self.lane,
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["closed"])
        self.assertFalse(self.lane.exists())
        self.assertFalse(git(self.repo, "branch", "--list", "lane"))
        self.assertFalse(git(self.repo, "ls-remote", "--heads", "origin", "refs/heads/lane"))
        entries = json.loads(self.ledger.read_text())["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["worktree"], str(self.other_lane.resolve()))
        self.assertEqual(entries[0]["integration_overlaps"], [])

    def test_close_detaches_shared_codegraph_index_and_preserves_service(self) -> None:
        self.register()
        self.absorb_lane()
        holder, shared_root = self.shared_codegraph_holder()
        scans = self.shared_holder_scans(holder, shared_root)

        with patch.object(
            worktree_lifecycle.worktree_fleet_audit,
            "scan_holders",
            side_effect=scans,
        ) as scan_mock:
            result = worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
            )

        self.assertTrue(result["closed"])
        self.assertEqual(scan_mock.call_count, 5)
        self.assertFalse(self.lane.exists())
        self.assertEqual(
            result["index_detach"]["protocol"],
            "atomic_migrate_wal_checkpoint_unlink",
        )
        self.assertEqual(result["index_detach"]["wal_checkpoint"][0], 0)
        self.assertTrue(result["index_detach"]["target_holders_absent"])
        self.assertTrue(result["index_detach"]["external_indexes_preserved"])
        common_dir = Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        self.assertEqual(
            list(common_dir.glob("opl-flow-codegraph-detach-*")),
            [],
        )

    def test_close_restores_index_when_quiescence_cannot_be_proven(self) -> None:
        self.register()
        self.absorb_lane()
        holder, shared_root = self.shared_codegraph_holder()
        scans = self.shared_holder_scans(holder, shared_root)[:2]

        with (
            patch.object(
                worktree_lifecycle.worktree_fleet_audit,
                "scan_holders",
                side_effect=scans,
            ),
            patch.object(
                worktree_lifecycle,
                "checkpoint_codegraph_index",
                side_effect=worktree_lifecycle.LifecycleError("checkpoint busy"),
            ),
            self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "checkpoint busy"),
        ):
            worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
            )

        self.assertTrue((self.lane / ".codegraph" / "codegraph.db").is_file())
        self.assertTrue(self.lane.exists())
        self.assertEqual(json.loads(self.ledger.read_text())["entries"][0]["status"], "ACTIVE")
        common_dir = Path(
            git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        self.assertEqual(
            list(common_dir.glob("opl-flow-codegraph-detach-*")),
            [],
        )

    def test_close_restores_index_when_final_lsof_proof_is_unavailable(self) -> None:
        self.register()
        self.absorb_lane()
        holder, shared_root = self.shared_codegraph_holder()
        scans = self.shared_holder_scans(
            holder,
            shared_root,
            final_available=False,
        )

        with (
            patch.object(
                worktree_lifecycle.worktree_fleet_audit,
                "scan_holders",
                side_effect=scans,
            ),
            self.assertRaisesRegex(
                worktree_lifecycle.LifecycleError,
                "backup is preserved",
            ),
        ):
            worktree_lifecycle.close(self.ledger, worktree=self.lane)

        self.assertTrue((self.lane / ".codegraph" / "codegraph.db").is_file())
        self.assertTrue(self.lane.exists())
        self.assertEqual(json.loads(self.ledger.read_text())["entries"][0]["status"], "ACTIVE")

    def test_close_restores_index_when_codegraph_pid_identity_restarts(self) -> None:
        self.register()
        self.absorb_lane()
        holder, shared_root = self.shared_codegraph_holder()
        scans = self.shared_holder_scans(
            holder,
            shared_root,
            restarted=True,
        )

        with (
            patch.object(
                worktree_lifecycle.worktree_fleet_audit,
                "scan_holders",
                side_effect=scans,
            ),
            self.assertRaisesRegex(
                worktree_lifecycle.LifecycleError,
                "service or non-target index identity changed",
            ),
        ):
            worktree_lifecycle.close(self.ledger, worktree=self.lane)

        self.assertTrue((self.lane / ".codegraph" / "codegraph.db").is_file())
        self.assertTrue(self.lane.exists())

    def test_close_restores_index_when_shared_db_inode_changes(self) -> None:
        self.register()
        self.absorb_lane()
        holder, shared_root = self.shared_codegraph_holder()
        scans = self.shared_holder_scans(
            holder,
            shared_root,
            changed_inode=True,
        )

        with (
            patch.object(
                worktree_lifecycle.worktree_fleet_audit,
                "scan_holders",
                side_effect=scans,
            ),
            self.assertRaisesRegex(
                worktree_lifecycle.LifecycleError,
                "service or non-target index identity changed",
            ),
        ):
            worktree_lifecycle.close(self.ledger, worktree=self.lane)

        self.assertTrue((self.lane / ".codegraph" / "codegraph.db").is_file())
        self.assertTrue(self.lane.exists())

    def test_close_preserves_unrelated_dirty_and_behind_canonical_checkout(self) -> None:
        self.register()
        base_head = git(self.repo, "rev-parse", "HEAD")
        self.commit_lane()
        lane_head = git(self.lane, "rev-parse", "HEAD")
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        git(self.repo, "reset", "--hard", base_head)
        unrelated = self.repo / "unrelated.txt"
        unrelated.write_text("owner work\n", encoding="utf-8")

        result = worktree_lifecycle.close(
            self.ledger,
            worktree=self.lane,
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["closed"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), base_head)
        self.assertEqual(git(self.repo, "rev-parse", "origin/main"), lane_head)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "owner work\n")

    def test_close_uses_explicit_target_when_root_tracks_review_branch(self) -> None:
        self.register()
        base_head = git(self.repo, "rev-parse", "HEAD")
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        git(self.repo, "push", "origin", f"{base_head}:refs/heads/review")
        git(self.repo, "switch", "-c", "review", "--track", "origin/review")

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "cleanup-ready"):
            worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
                holders={},
                holder_scan_available=True,
            )

        result = worktree_lifecycle.close(
            self.ledger,
            worktree=self.lane,
            target="origin/main",
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["closed"])
        self.assertEqual(git(self.repo, "branch", "--show-current"), "review")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), base_head)
        self.assertFalse(git(self.repo, "ls-remote", "--heads", "origin", "refs/heads/lane"))

    def test_close_refuses_when_canonical_target_does_not_match_wire(self) -> None:
        self.register()
        base_head = git(self.repo, "rev-parse", "HEAD")
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        git(self.repo, "update-ref", "refs/remotes/origin/main", base_head)

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "canonical target"):
            worktree_lifecycle.close(
                self.ledger,
                worktree=self.lane,
                holders={},
                holder_scan_available=True,
            )

    def remove_lane_surfaces(self, *, delete_local_branch: bool = True) -> None:
        git(self.repo, "worktree", "remove", str(self.lane))
        if delete_local_branch:
            git(self.repo, "branch", "-D", "lane")

    def stale_close(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "repo_root": self.repo,
            "worktree": self.lane,
            "thread_id": "thread-1",
            "objective_id": "objective-1",
            "owner": "owner-1",
            "branch": "lane",
            "holders": {},
            "holder_scan_available": True,
        }
        arguments.update(overrides)
        return worktree_lifecycle.close_stale(self.ledger, **arguments)

    def create_lane_bundle(self, name: str = "recovery.bundle") -> tuple[Path, str]:
        bundle = Path(self.temp.name) / name
        git(self.repo, "bundle", "create", str(bundle), "lane")
        return bundle, hashlib.sha256(bundle.read_bytes()).hexdigest()

    def superseded_close(self, **overrides: object) -> dict[str, object]:
        entry = json.loads(self.ledger.read_text(encoding="utf-8"))["entries"][0]
        arguments: dict[str, object] = {
            "repo_root": Path(entry["repo_root"]),
            "worktree": Path(entry["worktree"]),
            "thread_id": "thread-1",
            "objective_id": "objective-1",
            "owner": "owner-1",
            "reason": "superseded by the current product SSOT",
            "holders": {},
            "holder_scan_available": True,
        }
        arguments.update(overrides)
        return worktree_lifecycle.close_superseded(self.ledger, **arguments)

    def test_superseded_close_archives_unabsorbed_recovery(self) -> None:
        self.register()
        self.commit_lane()
        recovery = worktree_lifecycle.checkpoint(
            self.ledger,
            worktree=self.lane,
            remote="origin",
        )
        bundle, digest = self.create_lane_bundle()
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        result = self.superseded_close(
            archive_bundle=bundle,
            archive_sha256=digest,
        )

        self.assertTrue(result["closed"])
        self.assertEqual(result["classification"], "superseded_archived")
        self.assertEqual(result["archive"]["sha256"], digest)
        self.assertEqual(result["archive"]["recovery"], recovery)
        self.assertEqual(result["remaining"], [])
        self.assertTrue(all(result["assertions"].values()))
        self.assertEqual(json.loads(self.ledger.read_text())["entries"], [])

    def test_superseded_close_supports_detached_receipt_without_recovery(self) -> None:
        self.register()
        git(self.lane, "switch", "--detach")
        git(self.repo, "branch", "-D", "lane")
        git(self.repo, "worktree", "remove", str(self.lane))

        result = self.superseded_close()

        self.assertTrue(result["closed"])
        self.assertEqual(result["classification"], "superseded_no_recovery")
        self.assertIsNone(result["branch"])
        self.assertIsNone(result["archive"])
        self.assertEqual(json.loads(self.ledger.read_text())["entries"], [])

    def test_superseded_close_refuses_identity_drift_without_writing_ledger(self) -> None:
        self.register()
        self.remove_lane_surfaces()
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "identity"):
            self.superseded_close(owner="other-owner")

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_superseded_close_requires_archive_for_recovery_without_writing_ledger(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "requires an archive"):
            self.superseded_close()

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_superseded_close_refuses_archive_digest_mismatch_without_writing_ledger(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        bundle, _ = self.create_lane_bundle()
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "SHA-256 does not match"):
            self.superseded_close(
                archive_bundle=bundle,
                archive_sha256="0" * 64,
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_superseded_close_refuses_bundle_without_recovery_without_writing_ledger(self) -> None:
        self.register()
        self.commit_lane()
        bundle = Path(self.temp.name) / "main-only.bundle"
        git(self.repo, "bundle", "create", str(bundle), "main")
        digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "does not preserve the recorded recovery",
        ):
            self.superseded_close(
                archive_bundle=bundle,
                archive_sha256=digest,
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_superseded_close_refuses_remaining_task_ref_without_writing_ledger(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        bundle, digest = self.create_lane_bundle()
        self.remove_lane_surfaces(delete_local_branch=False)
        before = self.ledger.read_bytes()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "local task ref"):
            self.superseded_close(
                archive_bundle=bundle,
                archive_sha256=digest,
            )

        self.assertEqual(self.ledger.read_bytes(), before)

    def test_stale_close_removes_exact_absent_receipt(self) -> None:
        self.register()
        self.remove_lane_surfaces()

        result = self.stale_close()

        self.assertTrue(result["closed"])
        self.assertEqual(result["classification"], "stale_receipt_only")
        self.assertEqual(result["remaining"], [])
        self.assertTrue(all(result["assertions"].values()))
        self.assertEqual(json.loads(self.ledger.read_text())["entries"], [])

    def test_stale_close_refuses_when_task_ref_remains(self) -> None:
        self.register()
        self.remove_lane_surfaces(delete_local_branch=False)

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "local task ref"):
            self.stale_close()

    def test_stale_close_refuses_task_ref_on_noncanonical_remote(self) -> None:
        self.register()
        git(self.temp.name, "init", "--bare", str(self.backup))
        git(self.repo, "remote", "add", "backup", str(self.backup))
        git(self.lane, "push", "backup", "lane")
        self.remove_lane_surfaces()

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "tracking task ref to be absent: refs/remotes/backup/lane",
        ):
            self.stale_close()

    def test_stale_close_refuses_identity_drift(self) -> None:
        self.register()
        self.remove_lane_surfaces()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "identity"):
            self.stale_close(owner="other-owner")

    def test_stale_close_refuses_deleted_path_holder(self) -> None:
        self.register()
        self.remove_lane_surfaces()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "holder0"):
            self.stale_close(
                holders={
                    str(self.lane.resolve()): [
                        {"pid": 123, "command": "codegraph"},
                    ]
                }
            )

    def test_stale_close_refuses_unabsorbed_recovery_checkpoint(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "recovery commit is not absorbed",
        ):
            self.stale_close()

    def test_stale_close_refuses_unknown_recovery_commit(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        payload = json.loads(self.ledger.read_text(encoding="utf-8"))
        payload["entries"][0]["remote_recovery"]["commit"] = "0" * 40
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "commit/tree cannot be verified",
        ):
            self.stale_close()

    def test_stale_close_refuses_recovery_tree_mismatch(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        payload = json.loads(self.ledger.read_text(encoding="utf-8"))
        payload["entries"][0]["remote_recovery"]["tree"] = "0" * 40
        self.ledger.write_text(json.dumps(payload), encoding="utf-8")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "commit/tree cannot be verified",
        ):
            self.stale_close()

    def test_stale_close_allows_absorbed_recovery_checkpoint(self) -> None:
        self.register()
        self.commit_lane()
        recovery = worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        result = self.stale_close()

        self.assertTrue(result["closed"])
        self.assertEqual(recovery["commit"], git(self.repo, "rev-parse", "origin/main"))
        self.assertEqual(result["recovery_absorption"], "exact_merged")
        self.assertTrue(result["assertions"]["recovery_absence_or_absorption_proven"])

    def test_stale_close_allows_patch_equivalent_recovery_checkpoint(self) -> None:
        self.register()
        self.commit_lane()
        recovery = worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        (self.repo / "lane.txt").write_text("lane\n", encoding="utf-8")
        git(self.repo, "add", "lane.txt")
        git(self.repo, "commit", "-m", "replay lane change")
        (self.repo / "main.txt").write_text("main only\n", encoding="utf-8")
        git(self.repo, "add", "main.txt")
        git(self.repo, "commit", "-m", "main only change")
        git(self.repo, "push", "origin", "main")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        result = self.stale_close()

        self.assertTrue(result["closed"])
        self.assertEqual(result["recovery_absorption"], "patch_equivalent")
        self.assertNotEqual(recovery["commit"], git(self.repo, "rev-parse", "origin/main"))
        self.assertEqual(
            result["recovery_absorption_proof"]["lane_head"],
            recovery["commit"],
        )
        self.assertEqual(result["recovery_absorption_proof"]["equivalent_commit_count"], 1)
        self.assertTrue(result["assertions"]["recovery_absence_or_absorption_proven"])

    def test_stale_close_refuses_tree_equivalent_recovery_checkpoint(self) -> None:
        self.register()
        self.commit_lane()
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        (self.repo / "lane.txt").write_text("lane\n", encoding="utf-8")
        git(self.repo, "add", "lane.txt")
        git(self.repo, "commit", "-m", "replay lane tree")
        git(self.repo, "push", "origin", "main")
        self.remove_lane_surfaces()
        git(self.repo, "push", "origin", "--delete", "lane")

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "classification=tree_equivalent",
        ):
            self.stale_close()

    def test_stale_close_refuses_patch_equivalent_merge_history(self) -> None:
        self.register()
        git(self.lane, "branch", "lane-side")
        self.commit_lane()
        git(self.lane, "checkout", "lane-side")
        (self.lane / "side.txt").write_text("side\n", encoding="utf-8")
        git(self.lane, "add", "side.txt")
        git(self.lane, "commit", "-m", "side change")
        git(self.lane, "checkout", "lane")
        git(self.lane, "merge", "--no-ff", "lane-side", "-m", "merge lane side")
        worktree_lifecycle.checkpoint(self.ledger, worktree=self.lane, remote="origin")
        (self.repo / "lane.txt").write_text("lane\n", encoding="utf-8")
        (self.repo / "side.txt").write_text("side\n", encoding="utf-8")
        (self.repo / "main.txt").write_text("main only\n", encoding="utf-8")
        git(self.repo, "add", "lane.txt", "side.txt", "main.txt")
        git(self.repo, "commit", "-m", "replay lane changes")
        git(self.repo, "push", "origin", "main")
        self.remove_lane_surfaces()
        git(self.repo, "branch", "-D", "lane-side")
        git(self.repo, "push", "origin", "--delete", "lane")

        with self.assertRaisesRegex(
            worktree_lifecycle.LifecycleError,
            "classification=owner_review",
        ):
            self.stale_close()

    def test_stale_close_preserves_other_receipts(self) -> None:
        self.register()
        git(
            self.repo,
            "worktree",
            "add",
            "-b",
            "other-lane",
            str(self.other_lane),
            "main",
        )
        worktree_lifecycle.register(
            self.ledger,
            repo_root=self.repo,
            worktree=self.other_lane,
            thread_id="thread-2",
            objective_id="objective-2",
            owner="owner-2",
            execution_owner="owner-2",
            next_action="continue",
            write_set=["lane.txt"],
        )
        self.remove_lane_surfaces()

        result = self.stale_close()

        self.assertEqual(result["remaining"], [])
        entries = json.loads(self.ledger.read_text())["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["worktree"], str(self.other_lane.resolve()))
        self.assertEqual(entries[0]["integration_overlaps"], [])


if __name__ == "__main__":
    unittest.main()
