from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

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
        self.lane = root / "lane"
        self.other_lane = root / "other-lane"
        self.ledger = root / "state" / "ledger.json"
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

    def test_checkpoint_rejects_noncanonical_remote(self) -> None:
        self.register()

        with self.assertRaisesRegex(worktree_lifecycle.LifecycleError, "canonical upstream"):
            worktree_lifecycle.checkpoint(
                self.ledger,
                worktree=self.lane,
                remote="backup",
            )

    def test_status_is_read_only(self) -> None:
        self.register()
        before = self.ledger.read_bytes()

        result = worktree_lifecycle.status(
            self.ledger,
            repo_roots=[self.repo],
            holders={},
            holder_scan_available=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(self.ledger.read_bytes(), before)

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
        self.assertEqual(json.loads(self.ledger.read_text())["entries"], [])

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
            write_set=["other.txt"],
        )
        self.remove_lane_surfaces()

        result = self.stale_close()

        self.assertEqual(result["remaining"], [])
        entries = json.loads(self.ledger.read_text())["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["worktree"], str(self.other_lane.resolve()))


if __name__ == "__main__":
    unittest.main()
