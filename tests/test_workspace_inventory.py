from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from scripts.fleet.workspace_inventory import discover_checkouts, inventory, repository_identity


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True).stdout.strip()


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)

    def repo(self, name, remote="https://github.com/example/project.git"):
        path = self.root / name
        path.mkdir(parents=True)
        git(path, "init", "-q")
        git(path, "config", "user.name", "Inventory Test")
        git(path, "config", "user.email", "inventory@example.invalid")
        (path / "source.txt").write_text("source\n")
        git(path, "add", "source.txt")
        git(path, "-c", "commit.gpgsign=false", "commit", "-qm", "Initial source")
        git(path, "remote", "add", "origin", remote)
        return path

    def test_transport_identity_and_credentials_are_normalized(self):
        for remote in ["https://token@github.com/Example/Project.git?token=secret", "git@github.com:example/project.git", "ssh://git@ssh.github.com:443/example/project.git"]:
            self.assertEqual(repository_identity(remote), "github.com/example/project")
        self.assertNotEqual(repository_identity("https://other.example/example/project.git"), "github.com/example/project")
        self.assertIsNone(repository_identity("https://github.com:bad/example/project"))

    def test_linked_worktree_is_not_an_independent_clone(self):
        primary = self.repo("primary")
        linked = self.root / "linked"
        git(primary, "worktree", "add", "--detach", str(linked), "HEAD")
        index = primary / ".git/index"
        before = index.stat().st_mtime_ns
        result = inventory([self.root], managed={str(primary): "example/project"})
        self.assertEqual(result["summary"]["linked_worktrees"], 1)
        self.assertEqual(result["duplicate_clones"], [])
        self.assertEqual(index.stat().st_mtime_ns, before)
        self.assertTrue(result["complete"])
        self.assertEqual(git(primary, "status", "--porcelain"), "")

    def test_independent_clone_group_keeps_source_identity(self):
        first = self.repo("first")
        second = self.repo("second", "git@github.com:example/project.git")
        (second / "unique.txt").write_text("pending work")
        result = inventory([self.root], include_size=True)
        self.assertEqual(result["duplicate_clones"][0]["repository"], "github.com/example/project")
        self.assertEqual(set(result["duplicate_clones"][0]["checkouts"]), {str(first), str(second)})
        self.assertEqual(next(r for r in result["checkouts"] if r["path"] == str(second))["state"], "DIRTY")
        self.assertTrue(all(r["allocated_bytes"] > 0 for r in result["checkouts"]))
        self.assertEqual((second / "unique.txt").read_text(), "pending work")

    def test_scan_does_not_follow_redirects_or_dependency_trees(self):
        self.repo("node_modules/hidden")
        visible = self.repo("visible")
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        (self.root / "redirect").symlink_to(outside, target_is_directory=True)
        paths, _ = discover_checkouts([self.root])
        self.assertEqual(paths, [visible])
        paths, issues = discover_checkouts([self.root / "redirect"])
        self.assertFalse(paths)
        self.assertEqual(issues[0]["state"], "SKIPPED_SYMLINK")

    def test_overlapping_roots_and_missing_declarations(self):
        primary = self.repo("a/repo")
        result = inventory([self.root, self.root / "a"], managed={str(primary): "example/wrong", str(self.root / "missing"): "example/missing"})
        self.assertEqual(len(result["checkouts"]), 1)
        self.assertEqual(result["checkouts"][0]["state"], "REMOTE_MISMATCH")
        self.assertEqual(result["missing_declared"], [{"path": str(self.root / "missing"), "repository": "example/missing"}])

    def test_invalid_git_marker_is_a_read_failure(self):
        broken = self.root / "broken"
        broken.mkdir()
        (broken / ".git").write_text("gitdir: missing\n")
        result = inventory([self.root])
        self.assertFalse(result["complete"])
        self.assertEqual(result["checkouts"][0]["state"], "READ_FAILED")

    def test_shallow_and_selected_scans_do_not_report_existing_repos_as_missing(self):
        primary = self.repo("a/b/repo")
        result = inventory([self.root], max_depth=1, managed={str(primary): "example/project"})
        self.assertEqual(result["missing_declared"], [])
        self.assertEqual(result["unscanned_declared"][0]["path"], str(primary))
        paths, _ = discover_checkouts([self.root, self.root / "a/b"], max_depth=1)
        self.assertEqual(paths, [primary])


if __name__ == "__main__":
    unittest.main()
