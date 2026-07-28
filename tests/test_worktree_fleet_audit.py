from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import worktree_fleet_audit


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class WorktreeFleetAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.remote = root / "remote.git"
        self.lane = root / "lane"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "OPL Flow Tests")
        git(self.repo, "config", "user.email", "opl-flow-tests@example.invalid")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "base.txt")
        git(self.repo, "commit", "-m", "base")
        git(root, "init", "--bare", str(self.remote))
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-u", "origin", "main")
        git(self.repo, "worktree", "add", "-b", "lane", str(self.lane), "main")

    def commit_lane(self, text: str = "lane\n") -> None:
        (self.lane / "lane.txt").write_text(text, encoding="utf-8")
        git(self.lane, "add", "lane.txt")
        git(self.lane, "commit", "-m", "lane change")

    def active_receipt(self) -> dict[str, dict[str, object]]:
        return {
            str(self.lane.resolve()): {
                "worktree": str(self.lane.resolve()),
                "thread_id": "thread-1",
                "objective_id": "objective-1",
                "owner": "owner-1",
                "execution_owner": "owner-1",
                "status": "ACTIVE",
                "next_action": "continue focused verification",
                "write_set": ["lane.txt"],
                "remote_recovery": None,
            }
        }

    def audit(
        self,
        receipts: dict[str, dict[str, object]] | None = None,
        holders: dict[str, list[dict[str, object]]] | None = None,
    ) -> dict[str, object]:
        return worktree_fleet_audit.audit_fleet(
            [self.repo],
            receipts or {},
            check_remote=True,
            holders=holders or {},
            holder_scan_available=True,
        )

    def test_active_remote_recoverable_lane_is_retained(self) -> None:
        self.commit_lane()
        git(self.lane, "push", "-u", "origin", "lane")

        result = self.audit(self.active_receipt())
        lane = result["repos"][0]["worktrees"][0]

        self.assertTrue(result["ok"])
        self.assertEqual(lane["action"], "retain_active")
        self.assertEqual(lane["remote_branch_head"], git(self.lane, "rev-parse", "HEAD"))

    def test_active_overlapping_lanes_are_reported_without_blocking(self) -> None:
        other_lane = Path(self.temp.name) / "other-lane"
        git(self.repo, "worktree", "add", "-b", "other-lane", str(other_lane), "main")
        self.commit_lane()
        (other_lane / "other.txt").write_text("other\n", encoding="utf-8")
        git(other_lane, "add", "other.txt")
        git(other_lane, "commit", "-m", "other change")
        git(self.lane, "push", "-u", "origin", "lane")
        git(other_lane, "push", "-u", "origin", "other-lane")
        receipts = self.active_receipt()
        receipts[str(other_lane.resolve())] = {
            "worktree": str(other_lane.resolve()),
            "thread_id": "thread-2",
            "objective_id": "objective-2",
            "owner": "owner-2",
            "execution_owner": "owner-2",
            "status": "ACTIVE",
            "next_action": "continue focused verification",
            "write_set": ["lane.txt"],
            "remote_recovery": {
                "branch": "other-lane",
                "commit": git(other_lane, "rev-parse", "HEAD"),
                "tree": git(other_lane, "rev-parse", "HEAD^{tree}"),
            },
        }

        result = self.audit(receipts)
        lanes = {
            item["worktree"]: item
            for item in result["repos"][0]["worktrees"]
        }

        self.assertTrue(result["ok"])
        self.assertEqual(lanes[str(self.lane.resolve())]["action"], "retain_active")
        self.assertEqual(
            lanes[str(self.lane.resolve())]["integration_overlaps"][0]["owner"],
            "owner-2",
        )
        self.assertEqual(
            lanes[str(other_lane.resolve())]["integration_overlaps"][0]["owner"],
            "owner-1",
        )

    def test_absorbed_ownerless_lane_is_cleanup_ready(self) -> None:
        self.commit_lane()
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")

        result = self.audit()
        lane = result["repos"][0]["worktrees"][0]

        self.assertFalse(result["ok"])
        self.assertEqual(lane["classification"], "exact_merged")
        self.assertEqual(lane["action"], "cleanup_ready")

    def test_unabsorbed_ownerless_lane_requires_recovery_owner(self) -> None:
        self.commit_lane()

        result = self.audit()
        lane = result["repos"][0]["worktrees"][0]

        self.assertFalse(result["ok"])
        self.assertEqual(lane["action"], "recovery_owner_required")
        self.assertIn(
            "unabsorbed task branch is not recoverable from the remote",
            lane["blocking_issues"],
        )

    def test_holder_blocks_cleanup(self) -> None:
        self.commit_lane()
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        holders = {
            str(self.lane.resolve()): [{"pid": 123, "command": "test-holder"}]
        }

        result = self.audit(holders=holders)
        lane = result["repos"][0]["worktrees"][0]

        self.assertEqual(lane["action"], "holder_exit_required")

    def test_scan_holders_ignores_deleted_inode_but_keeps_existing_paths(self) -> None:
        lock_path = self.lane / "index.lock"
        lock_path.write_text("lock\n", encoding="utf-8")
        literal_deleted_path = self.lane / "metadata (deleted)"
        literal_deleted_path.write_text("real file\n", encoding="utf-8")
        deleted_codegraph_path = self.lane / ".codegraph" / "graph.sqlite"
        lsof = subprocess.CompletedProcess(
            args=["lsof"],
            returncode=0,
            stdout=(
                "p101\n"
                "ccodegraph\n"
                f"n{deleted_codegraph_path} (deleted)\n"
                "p102\n"
                "cshell\n"
                "fcwd\n"
                f"n{self.lane}\n"
                "p103\n"
                "cgit\n"
                "f4\n"
                f"n{lock_path}\n"
                "p104\n"
                "ctest\n"
                f"n{literal_deleted_path}\n"
            ),
            stderr="",
        )

        with patch.object(worktree_fleet_audit, "run", return_value=lsof):
            holders, available = worktree_fleet_audit.scan_holders([self.lane])

        self.assertTrue(available)
        self.assertEqual(
            holders,
            {
                str(self.lane.resolve()): [
                    {"pid": 102, "command": "shell"},
                    {"pid": 103, "command": "git"},
                    {"pid": 104, "command": "test"},
                ]
            },
        )

    def test_load_ledger_rejects_incomplete_active_receipt(self) -> None:
        path = Path(self.temp.name) / "ledger.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "opl_flow_worktree_ownership_ledger.v1",
                    "machine": "test",
                    "recorded_at": "2026-07-25T00:00:00Z",
                    "entries": [
                        {
                            "worktree": str(self.lane),
                            "thread_id": "thread-1",
                            "objective_id": "objective-1",
                            "owner": "owner-1",
                            "execution_owner": "owner-1",
                            "status": "ACTIVE",
                            "next_action": "",
                            "write_set": [],
                            "remote_recovery": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            worktree_fleet_audit.FleetAuditError,
            "next_action",
        ):
            worktree_fleet_audit.load_ledger(path)

    def test_stale_receipt_is_reported_at_fleet_scope(self) -> None:
        receipts = self.active_receipt()
        receipts[str(Path(self.temp.name) / "missing-lane")] = {
            **next(iter(receipts.values())),
            "worktree": str(Path(self.temp.name) / "missing-lane"),
        }

        result = self.audit(receipts)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["stale_receipts"],
            [str(Path(self.temp.name) / "missing-lane")],
        )


if __name__ == "__main__":
    unittest.main()
