from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "optional-skills" / "codex-ops-kit" / "scripts"


def run_script(name: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        check=False,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def init_repo(path: Path, *, remote: str | None = None) -> str:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Codex Ops Test")
    git(path, "config", "user.email", "codex-ops@example.test")
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(path, "add", "tracked.txt")
    git(path, "commit", "-m", "base")
    if remote:
        git(path, "remote", "add", "origin", remote)
    return git(path, "rev-parse", "HEAD")


def fake_gh_env(root: Path, assets: list[dict[str, str]]) -> dict[str, str]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    payload = {
        "tagName": "v1",
        "assets": assets,
        "url": "https://github.com/acme/demo/releases/tag/v1",
    }
    rendered = shlex.quote(json.dumps(payload, separators=(",", ":")))
    gh.write_text(f"#!/bin/sh\nprintf '%s\\n' {rendered}\n", encoding="utf-8")
    gh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    return env


class CodexOpsGateTests(unittest.TestCase):
    def test_non_git_repo_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script("codex_ops_gate.py", "status", "--repo", tmp)

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_only_declared_clean_worktree_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktree"
            init_repo(repo)
            git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
            (worktree / "dirty.txt").write_text("dirty\n", encoding="utf-8")

            visible = run_script(
                "codex_ops_gate.py",
                "status",
                "--repo",
                str(repo),
                "--target-ref",
                "main",
            )
            required = run_script(
                "codex_ops_gate.py",
                "status",
                "--repo",
                str(repo),
                "--target-ref",
                "main",
                "--require-clean-worktree",
                str(worktree),
            )

        self.assertEqual(visible.returncode, 0, visible.stderr)
        self.assertTrue(json.loads(visible.stdout)["ok"])
        self.assertEqual(required.returncode, 2)
        self.assertEqual(
            json.loads(required.stdout)["required_clean_worktree_failures"][0]["path"],
            str(worktree.resolve()),
        )

    def test_required_worktree_must_match_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktree"
            init_repo(repo)
            git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
            (repo / "tracked.txt").write_text("new target\n", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "advance target")

            result = run_script(
                "codex_ops_gate.py",
                "status",
                "--repo",
                str(repo),
                "--target-ref",
                "main",
                "--require-current-worktree",
                str(worktree),
            )

        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stdout, result.stderr)
        failure = json.loads(result.stdout)["required_current_worktree_failures"][0]
        self.assertEqual(failure["path"], str(worktree.resolve()))
        self.assertEqual(failure["target_relation"], "behind")

    def test_missing_registered_worktree_fails_required_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktree"
            init_repo(repo)
            git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
            shutil.rmtree(worktree)

            result = run_script(
                "codex_ops_gate.py",
                "status",
                "--repo",
                str(repo),
                "--target-ref",
                "main",
                "--require-clean-worktree",
                str(worktree),
                "--require-current-worktree",
                str(worktree),
            )

        self.assertEqual(result.returncode, 2, result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["required_clean_worktree_failures"][0]["status_error"], "worktree path does not exist")
        self.assertEqual(report["required_current_worktree_failures"][0]["status_error"], "worktree path does not exist")


class WorktreeAbsorptionAuditTests(unittest.TestCase):
    def test_cherry_picked_lane_is_patch_equivalent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "lane"
            base = init_repo(repo)
            git(repo, "worktree", "add", "-b", "lane", str(worktree), "HEAD")
            (worktree / "tracked.txt").write_text("lane change\n", encoding="utf-8")
            git(worktree, "add", "tracked.txt")
            git(worktree, "commit", "-m", "lane change")
            lane_head = git(worktree, "rev-parse", "HEAD")
            (repo / "main-only.txt").write_text("main only\n", encoding="utf-8")
            git(repo, "add", "main-only.txt")
            git(repo, "commit", "-m", "advance main independently")
            git(repo, "cherry-pick", lane_head)

            result = run_script(
                "worktree_absorption_audit.py",
                "--repo",
                str(repo),
                "--base-ref",
                base,
                "--target-ref",
                "main",
                str(worktree),
            )

        self.assertEqual(result.returncode, 0, result.stdout)
        item = json.loads(result.stdout)["results"][0]
        self.assertEqual(item["classification"], "patch-equivalent")
        self.assertEqual(item["unabsorbed_patches"], [])

    def test_different_merge_resolution_requires_owner_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            lane = root / "lane"
            side = root / "side"
            base = init_repo(repo)
            git(repo, "branch", "side", base)
            git(repo, "worktree", "add", "-b", "lane", str(lane), base)
            git(repo, "worktree", "add", str(side), "side")

            (lane / "tracked.txt").write_text("lane parent\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane parent")
            lane_parent = git(lane, "rev-parse", "HEAD")

            (side / "tracked.txt").write_text("side parent\n", encoding="utf-8")
            git(side, "add", "tracked.txt")
            git(side, "commit", "-m", "side parent")
            side_parent = git(side, "rev-parse", "HEAD")

            git(repo, "merge", "--no-ff", lane_parent, "-m", "merge lane parent")
            with self.assertRaises(subprocess.CalledProcessError):
                git(repo, "merge", "--no-ff", side_parent, "-m", "merge side parent")
            (repo / "tracked.txt").write_text("target resolution\n", encoding="utf-8")
            git(repo, "add", "tracked.txt")
            git(repo, "commit", "-m", "target resolution")

            with self.assertRaises(subprocess.CalledProcessError):
                git(lane, "merge", "--no-ff", side_parent, "-m", "merge side parent")
            (lane / "tracked.txt").write_text("lane resolution\n", encoding="utf-8")
            git(lane, "add", "tracked.txt")
            git(lane, "commit", "-m", "lane resolution")

            result = run_script(
                "worktree_absorption_audit.py",
                "--repo",
                str(repo),
                "--base-ref",
                base,
                "--target-ref",
                "main",
                str(lane),
            )

        self.assertEqual(result.returncode, 2, result.stdout)
        item = json.loads(result.stdout)["results"][0]
        self.assertEqual(item["classification"], "needs-owner-review")
        self.assertGreater(item["lane_merge_commit_count"], 0)

    def test_plain_subdirectory_is_not_a_registered_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            init_repo(repo)
            subdirectory = repo / "nested"
            subdirectory.mkdir()

            result = run_script(
                "worktree_absorption_audit.py",
                "--repo",
                str(repo),
                "--target-ref",
                "main",
                str(subdirectory),
            )

        self.assertEqual(result.returncode, 2, result.stdout)
        item = json.loads(result.stdout)["results"][0]
        self.assertEqual(item["classification"], "needs-owner-review")
        self.assertIn("path is not a registered worktree root", item["errors"])


class ReleaseUrlAuditTests(unittest.TestCase):
    def test_missing_github_readback_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            init_repo(repo, remote="https://github.com/acme/demo.git")
            (repo / "README.md").write_text(
                "https://github.com/acme/demo/releases/download/v1/demo.zip\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PATH"] = "/usr/bin:/bin"

            result = run_script("release_url_audit.py", "--repo", str(repo), env=env)

        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_matching_release_readback_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            init_repo(repo, remote="https://github.com/acme/demo.git")
            (repo / "README.md").write_text(
                "https://github.com/acme/demo/releases/download/v1/demo.zip\n",
                encoding="utf-8",
            )
            env = fake_gh_env(root, [{"name": "demo.zip"}])

            result = run_script("release_url_audit.py", "--repo", str(repo), env=env)

        self.assertEqual(result.returncode, 0, result.stdout)
        report = json.loads(result.stdout)
        self.assertIn("ok", report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])

    def test_explicit_missing_scan_path_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            init_repo(repo, remote="https://github.com/acme/demo.git")
            env = fake_gh_env(root, [])

            result = run_script(
                "release_url_audit.py",
                "--repo",
                str(repo),
                "--paths",
                "docs/install.md",
                env=env,
            )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("scan path is not a file", "\n".join(json.loads(result.stdout)["errors"]))

    def test_install_command_must_be_executed_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            init_repo(repo, remote="https://github.com/acme/demo.git")
            env = fake_gh_env(root, [])

            result = run_script(
                "release_url_audit.py",
                "--repo",
                str(repo),
                "--command",
                "true",
                env=env,
            )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("--command requires --run-command", "\n".join(json.loads(result.stdout)["errors"]))


if __name__ == "__main__":
    unittest.main()
