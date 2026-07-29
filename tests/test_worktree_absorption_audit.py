from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import worktree_absorption_audit


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class WorktreeAbsorptionAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.lane = root / "lane"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "OPL Flow Tests")
        git(self.repo, "config", "user.email", "opl-flow-tests@example.invalid")
        write(self.repo / "base.txt", "base\n")
        git(self.repo, "add", "base.txt")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "worktree", "add", "-b", "lane", str(self.lane), "main")

    def commit(self, cwd: Path, path: str, text: str, message: str) -> None:
        write(cwd / path, text)
        git(cwd, "add", path)
        git(cwd, "commit", "-m", message)

    def audit(self) -> dict[str, object]:
        return worktree_absorption_audit.audit(self.repo, self.lane, "main")

    def test_exact_merged_lane_allows_cleanup(self) -> None:
        self.commit(self.lane, "lane.txt", "absorbed\n", "lane change")
        git(self.repo, "merge", "--ff-only", "lane")

        result = self.audit()

        self.assertEqual(result["classification"], "exact_merged")
        self.assertTrue(result["cleanup_allowed"])

    def test_same_tree_with_distinct_commits_is_tree_equivalent(self) -> None:
        self.commit(self.lane, "base.txt", "same\n", "lane tree")
        self.commit(self.repo, "base.txt", "same\n", "target tree")

        result = self.audit()

        self.assertEqual(result["classification"], "tree_equivalent")
        self.assertTrue(result["cleanup_allowed"])

    def test_equivalent_patch_with_target_only_change_is_patch_equivalent(self) -> None:
        self.commit(self.lane, "lane.txt", "same patch\n", "lane patch")
        self.commit(self.repo, "lane.txt", "same patch\n", "target patch")
        self.commit(self.repo, "target.txt", "target only\n", "target only")

        result = self.audit()

        self.assertEqual(result["classification"], "patch_equivalent")
        self.assertEqual(result["equivalent_commit_count"], 1)
        self.assertTrue(result["cleanup_allowed"])

    def test_commit_identity_can_be_audited_without_live_worktree(self) -> None:
        self.commit(self.lane, "lane.txt", "same patch\n", "lane patch")
        lane_head = git(self.lane, "rev-parse", "HEAD")
        self.commit(self.repo, "lane.txt", "same patch\n", "target patch")
        self.commit(self.repo, "target.txt", "target only\n", "target only")

        result = worktree_absorption_audit.classify_commits(
            self.repo,
            lane_head,
            "main",
        )

        self.assertEqual(result["lane_head"], lane_head)
        self.assertEqual(result["classification"], "patch_equivalent")
        self.assertEqual(result["equivalent_commit_count"], 1)
        self.assertTrue(result["cleanup_allowed"])

    def test_commit_identity_audit_rejects_unknown_commit(self) -> None:
        with self.assertRaises(worktree_absorption_audit.AuditError):
            worktree_absorption_audit.classify_commits(
                self.repo,
                "0" * 40,
                "main",
            )

    def test_unique_lane_commit_is_not_absorbed(self) -> None:
        self.commit(self.lane, "lane.txt", "unique\n", "unique lane patch")

        result = self.audit()

        self.assertEqual(result["classification"], "ahead_not_absorbed")
        self.assertEqual(result["unabsorbed_commit_count"], 1)
        self.assertFalse(result["cleanup_allowed"])

    def test_dirty_lane_requires_owner_review(self) -> None:
        write(self.lane / "untracked.txt", "dirty\n")

        result = self.audit()

        self.assertEqual(result["classification"], "owner_review")
        self.assertTrue(result["dirty"])
        self.assertFalse(result["cleanup_allowed"])

    def test_unabsorbed_merge_resolution_requires_owner_review(self) -> None:
        git(self.lane, "branch", "side")
        self.commit(self.lane, "lane.txt", "lane\n", "lane side one")
        git(self.lane, "checkout", "side")
        self.commit(self.lane, "side.txt", "side\n", "lane side two")
        git(self.lane, "checkout", "lane")
        git(self.lane, "merge", "--no-ff", "side", "-m", "merge side")

        result = self.audit()

        self.assertEqual(result["classification"], "owner_review")
        self.assertEqual(result["merge_commit_count"], 1)
        self.assertFalse(result["cleanup_allowed"])


if __name__ == "__main__":
    unittest.main()
