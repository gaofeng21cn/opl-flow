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
        (self.repo / ".gitignore").write_text(".codegraph/\n", encoding="utf-8")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", ".gitignore", "base.txt")
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

    def shared_codegraph_holder(
        self,
        *,
        source_fd: bool = False,
        exclusive: bool = False,
        deleted: bool = False,
    ) -> dict[str, object]:
        index_dir = self.lane / ".codegraph"
        index_dir.mkdir(exist_ok=True)
        database = index_dir / "codegraph.db"
        database.write_bytes(b"index")
        files: list[dict[str, object]] = [
            {
                "fd": "15",
                "type": "REG",
                "device": hex(database.stat().st_dev),
                "inode": database.stat().st_ino,
                "path": str(database),
                "deleted": deleted,
            }
        ]
        if source_fd:
            files.append(
                {
                    "fd": "18",
                    "type": "REG",
                    "device": "0x1",
                    "inode": 77,
                    "path": str(self.lane / "base.txt"),
                    "deleted": False,
                }
            )
        indexes: list[dict[str, object]] = [
            {
                "path": str(database),
                "device": hex(database.stat().st_dev),
                "inode": database.stat().st_ino,
            }
        ]
        if not exclusive:
            indexes.append(
                {
                    "path": str(Path(self.temp.name) / "shared/.codegraph/codegraph.db"),
                    "device": "0x1",
                    "inode": 88,
                }
            )
        return {
            "pid": 123,
            "command": "node",
            "process_command": (
                "/opt/codegraph/node /opt/codegraph/lib/dist/bin/codegraph.js serve --mcp"
            ),
            "started_at": "Thu Jul 30 07:28:00 2026",
            "files": files,
            "codegraph_indexes": indexes,
        }

    def scan_lsof(
        self,
        stdout: str,
        worktrees: list[Path] | None = None,
    ) -> tuple[dict[str, list[dict[str, object]]], bool]:
        lsof = subprocess.CompletedProcess(
            args=["lsof"],
            returncode=0,
            stdout=stdout,
            stderr="",
        )

        def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if args[0] == "lsof":
                return lsof
            pid = args[2]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=(
                    f"{pid} Thu Jul 30 07:28:00 2026 "
                    f"/opt/codegraph/{pid}/codegraph.js serve --mcp\n"
                ),
                stderr="",
            )

        with patch.object(worktree_fleet_audit, "run", side_effect=fake_run):
            return worktree_fleet_audit.scan_holders(worktrees or [self.lane])

    def test_remote_heads_retry_transient_tls_failure(self) -> None:
        failure = subprocess.CompletedProcess(
            args=["git", "ls-remote"],
            returncode=128,
            stdout="",
            stderr="LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443",
        )
        success = subprocess.CompletedProcess(
            args=["git", "ls-remote"],
            returncode=0,
            stdout="abc123\trefs/heads/main\n",
            stderr="",
        )

        with (
            patch.object(worktree_fleet_audit, "run", side_effect=[failure, success]) as run_mock,
            patch.object(worktree_fleet_audit.time, "sleep") as sleep_mock,
        ):
            heads = worktree_fleet_audit.read_remote_heads(self.repo, "origin")

        self.assertEqual(heads, {"main": "abc123"})
        self.assertEqual(run_mock.call_count, 2)
        sleep_mock.assert_called_once_with(
            worktree_fleet_audit.REMOTE_PROBE_BACKOFF_SECONDS[0]
        )

    def test_remote_heads_do_not_retry_nontransient_failure(self) -> None:
        failure = subprocess.CompletedProcess(
            args=["git", "ls-remote"],
            returncode=128,
            stdout="",
            stderr="fatal: Authentication failed",
        )

        with (
            patch.object(worktree_fleet_audit, "run", return_value=failure) as run_mock,
            patch.object(worktree_fleet_audit.time, "sleep") as sleep_mock,
            self.assertRaisesRegex(worktree_fleet_audit.FleetAuditError, "Authentication failed"),
        ):
            worktree_fleet_audit.read_remote_heads(self.repo, "origin")

        self.assertEqual(run_mock.call_count, 1)
        sleep_mock.assert_not_called()

    def test_remote_heads_fail_closed_after_bounded_retries(self) -> None:
        failure = subprocess.CompletedProcess(
            args=["git", "ls-remote"],
            returncode=128,
            stdout="",
            stderr="fatal: TLS handshake timeout",
        )
        attempts = len(worktree_fleet_audit.REMOTE_PROBE_BACKOFF_SECONDS) + 1

        with (
            patch.object(worktree_fleet_audit, "run", return_value=failure) as run_mock,
            patch.object(worktree_fleet_audit.time, "sleep") as sleep_mock,
            self.assertRaisesRegex(worktree_fleet_audit.FleetAuditError, "TLS handshake timeout"),
        ):
            worktree_fleet_audit.read_remote_heads(self.repo, "origin")

        self.assertEqual(run_mock.call_count, attempts)
        self.assertEqual(sleep_mock.call_count, attempts - 1)

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

    def test_shared_codegraph_index_only_holder_is_detach_ready(self) -> None:
        self.commit_lane()
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        holders = {
            str(self.lane.resolve()): [self.shared_codegraph_holder()]
        }

        result = self.audit(holders=holders)
        lane = result["repos"][0]["worktrees"][0]

        self.assertEqual(lane["action"], "index_detach_ready")
        self.assertEqual(
            lane["holder_classification"]["kind"],
            "shared_codegraph_index_only",
        )

    def test_codegraph_mcp_command_accepts_supported_path_grammar(self) -> None:
        prefix = "/opt/codegraph/node /opt/codegraph/lib/dist/bin/codegraph.js serve --mcp"
        supported = (
            prefix,
            f"{prefix} --path {self.lane}",
            f"{prefix} --no-watch --path {self.lane}",
            f"{prefix} --path {self.lane} --no-watch",
        )

        for command in supported:
            with self.subTest(command=command):
                self.assertTrue(worktree_fleet_audit.is_codegraph_mcp_command(command))

    def test_codegraph_mcp_command_rejects_ambiguous_or_extra_arguments(self) -> None:
        prefix = "/opt/codegraph/node /opt/codegraph/lib/dist/bin/codegraph.js serve --mcp"
        unsupported = (
            f"{prefix} --path",
            f"{prefix} --path ''",
            f"{prefix} --path --no-watch",
            f"{prefix} --path {self.lane} --path {self.repo}",
            f"{prefix} --no-watch --no-watch",
            f"{prefix} --watch",
            f"{prefix} {self.lane}",
        )

        for command in unsupported:
            with self.subTest(command=command):
                self.assertFalse(worktree_fleet_audit.is_codegraph_mcp_command(command))

    def test_shared_codegraph_holder_with_path_is_detach_ready(self) -> None:
        holder = self.shared_codegraph_holder()
        holder["process_command"] = f"{holder['process_command']} --path {self.lane}"

        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            [holder],
        )

        self.assertEqual(classification["kind"], "shared_codegraph_index_only")
        self.assertEqual(classification["issues"], [])

    def test_codegraph_process_with_source_fd_still_blocks_cleanup(self) -> None:
        self.commit_lane()
        git(self.repo, "merge", "--ff-only", "lane")
        git(self.repo, "push", "origin", "main")
        holders = {
            str(self.lane.resolve()): [
                self.shared_codegraph_holder(source_fd=True)
            ]
        }

        result = self.audit(holders=holders)
        lane = result["repos"][0]["worktrees"][0]

        self.assertEqual(lane["action"], "holder_exit_required")
        self.assertEqual(lane["holder_classification"]["kind"], "blocking")
        self.assertIn(
            "PID 123 holds non-detachable target FD base.txt",
            lane["holder_classification"]["issues"],
        )

    def test_exclusive_codegraph_holder_is_not_treated_as_shared(self) -> None:
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            [self.shared_codegraph_holder(exclusive=True)],
        )

        self.assertEqual(classification["kind"], "blocking")
        self.assertIn(
            "PID 123 is not proven to serve another CodeGraph index",
            classification["issues"],
        )

    def test_deleted_codegraph_inode_is_not_detachable(self) -> None:
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            [self.shared_codegraph_holder(deleted=True)],
        )

        self.assertEqual(classification["kind"], "blocking")
        self.assertIn(
            "PID 123 holds non-detachable target FD .codegraph/codegraph.db",
            classification["issues"],
        )

    def test_codegraph_inode_without_link_count_proof_is_not_detachable(self) -> None:
        holder = self.shared_codegraph_holder()
        holder["files"][0]["deleted"] = None
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            [holder],
        )

        self.assertEqual(classification["kind"], "blocking")
        self.assertIn(
            "PID 123 holds non-detachable target FD .codegraph/codegraph.db",
            classification["issues"],
        )

    def test_scan_holders_fails_closed_when_lsof_is_unavailable(self) -> None:
        with patch.object(
            worktree_fleet_audit,
            "run",
            side_effect=FileNotFoundError("lsof"),
        ):
            holders, available = worktree_fleet_audit.scan_holders([self.lane])

        self.assertEqual(holders, {})
        self.assertFalse(available)

    def test_scan_holders_ignores_unrelated_path_vanished_after_lsof(self) -> None:
        vanished = Path(self.temp.name) / "unrelated-cache" / "vanished"
        output = (
            "p100\n"
            "cmeeting\n"
            "f9\n"
            "tDIR\n"
            "D0x1\n"
            "i100\n"
            "k1\n"
            f"n{vanished}\n"
        )

        with patch.object(worktree_fleet_audit.os.path, "lexists", return_value=True):
            holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        self.assertEqual(holders, {})

    def test_scan_holders_keeps_target_local_vanished_fd_fail_closed(self) -> None:
        vanished = self.lane / "build" / "gone.log"
        output = (
            "p105\n"
            "ctest\n"
            "f5\n"
            "tREG\n"
            "D0x1\n"
            "i105\n"
            "k1\n"
            f"n{vanished}\n"
        )

        with patch.object(worktree_fleet_audit.os.path, "lexists", return_value=True):
            holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        lane_holders = holders[str(self.lane.resolve())]
        opened_file = lane_holders[0]["files"][0]
        self.assertFalse(opened_file["path_exists"])
        self.assertIsNone(opened_file["path_resolution_error"])
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            lane_holders,
        )
        self.assertEqual(classification["kind"], "blocking")
        self.assertIn(
            "PID 105 holds vanished target FD build/gone.log",
            classification["issues"],
        )

    def test_scan_holders_ignores_unrelated_inaccessible_fd(self) -> None:
        inaccessible = Path(self.temp.name) / "unrelated-system" / "protected"
        output = (
            "p109\n"
            "canalyticsd\n"
            "f9\n"
            "tREG\n"
            "D0x1\n"
            "i109\n"
            "k1\n"
            f"n{inaccessible}\n"
        )

        with patch.object(
            Path,
            "exists",
            side_effect=PermissionError(13, "Permission denied", str(inaccessible)),
        ):
            holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        self.assertEqual(holders, {})

    def test_scan_holders_keeps_target_local_inaccessible_fd_fail_closed(self) -> None:
        inaccessible = self.lane / "protected" / "state.db"
        output = (
            "p110\n"
            "ctest\n"
            "f10\n"
            "tREG\n"
            "D0x1\n"
            "i110\n"
            "k1\n"
            f"n{inaccessible}\n"
        )

        with patch.object(
            Path,
            "exists",
            side_effect=PermissionError(13, "Permission denied", str(inaccessible)),
        ):
            holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        lane_holders = holders[str(self.lane.resolve())]
        opened_file = lane_holders[0]["files"][0]
        self.assertIsNone(opened_file["path_exists"])
        self.assertIn("PermissionError", opened_file["path_probe_error"])
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            lane_holders,
        )
        self.assertEqual(classification["kind"], "blocking")
        self.assertTrue(
            any(
                issue.startswith(
                    "PID 110 cannot verify target FD path protected/state.db"
                )
                for issue in classification["issues"]
            )
        )

    def test_scan_holders_resolves_symlink_alias_into_target(self) -> None:
        alias = Path(self.temp.name) / "lane-alias"
        alias.symlink_to(self.lane, target_is_directory=True)
        vanished = alias / "build" / "gone.log"
        output = (
            "p106\n"
            "ctest\n"
            "f6\n"
            "tREG\n"
            "D0x1\n"
            "i106\n"
            "k1\n"
            f"n{vanished}\n"
        )

        holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        opened_file = holders[str(self.lane.resolve())][0]["files"][0]
        self.assertEqual(
            opened_file["path"],
            str((self.lane / "build" / "gone.log").resolve(strict=False)),
        )
        self.assertFalse(opened_file["path_exists"])

    @unittest.skipUnless(
        Path("/var").resolve(strict=False) == Path("/private/var").resolve(strict=False),
        "requires the macOS /var to /private/var alias",
    )
    def test_scan_holders_normalizes_var_alias_to_private_var_target(self) -> None:
        lane = self.lane.resolve()
        if not lane.is_relative_to("/private/var"):
            self.skipTest("temporary directory is not under /private/var")
        raw_lane = Path("/var") / lane.relative_to("/private/var")
        vanished = raw_lane / "build" / "gone.log"
        output = (
            "p107\n"
            "ctest\n"
            "f7\n"
            "tREG\n"
            "D0x1\n"
            "i107\n"
            "k1\n"
            f"n{vanished}\n"
        )

        holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        opened_file = holders[str(lane)][0]["files"][0]
        self.assertEqual(
            opened_file["path"],
            str((lane / "build" / "gone.log").resolve(strict=False)),
        )
        self.assertFalse(opened_file["path_exists"])

    def test_scan_holders_keeps_unresolvable_path_fail_closed(self) -> None:
        unresolved = Path(self.temp.name) / "unresolved" / "gone.log"
        output = (
            "p108\n"
            "ctest\n"
            "f8\n"
            "tREG\n"
            "D0x1\n"
            "i108\n"
            "k1\n"
            f"n{unresolved}\n"
        )

        with patch.object(
            worktree_fleet_audit,
            "normalized_open_path",
            return_value=(unresolved, "RuntimeError: symlink loop"),
        ):
            holders, available = self.scan_lsof(output)

        self.assertTrue(available)
        lane_holders = holders[str(self.lane.resolve())]
        opened_file = lane_holders[0]["files"][0]
        self.assertIsNotNone(opened_file["path_resolution_error"])
        classification = worktree_fleet_audit.classify_cleanup_holders(
            self.lane,
            lane_holders,
        )
        self.assertEqual(classification["kind"], "blocking")
        self.assertTrue(
            any(
                issue.startswith("PID 108 has unresolvable FD path")
                for issue in classification["issues"]
            )
        )

    def test_normalized_open_path_evidences_resolution_failure(self) -> None:
        unresolved = Path(self.temp.name) / "unresolved" / "gone.log"

        with patch.object(Path, "resolve", side_effect=RuntimeError("symlink loop")):
            path, error = worktree_fleet_audit.normalized_open_path(
                str(unresolved),
                deleted=False,
            )

        self.assertEqual(path, unresolved.absolute())
        self.assertEqual(error, "RuntimeError: symlink loop")

    def test_scan_holders_keeps_deleted_inode_and_literal_deleted_filename(self) -> None:
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
                "f15\n"
                "tREG\n"
                "D0x1\n"
                "i101\n"
                "k0\n"
                f"n{deleted_codegraph_path} (deleted)\n"
                "p102\n"
                "cshell\n"
                "fcwd\n"
                "tDIR\n"
                "D0x1\n"
                "i102\n"
                "k1\n"
                f"n{self.lane}\n"
                "p103\n"
                "cgit\n"
                "f4\n"
                "tREG\n"
                "D0x1\n"
                "i103\n"
                "k1\n"
                f"n{lock_path}\n"
                "p104\n"
                "ctest\n"
                "f5\n"
                "tREG\n"
                "D0x1\n"
                "i104\n"
                "k1\n"
                f"n{literal_deleted_path}\n"
            ),
            stderr="",
        )

        def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if args[0] == "lsof":
                return lsof
            pid = args[2]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=(
                    f"{pid} Thu Jul 30 07:28:00 2026 "
                    f"/opt/codegraph/{pid}/codegraph.js serve --mcp\n"
                ),
                stderr="",
            )

        with patch.object(worktree_fleet_audit, "run", side_effect=fake_run):
            holders, available = worktree_fleet_audit.scan_holders([self.lane])

        self.assertTrue(available)
        lane_holders = holders[str(self.lane.resolve())]
        self.assertEqual([item["pid"] for item in lane_holders], [101, 102, 103, 104])
        deleted_holder = lane_holders[0]
        self.assertEqual(deleted_holder["command"], "codegraph")
        self.assertTrue(deleted_holder["files"][0]["deleted"])
        self.assertEqual(deleted_holder["files"][0]["link_count"], 0)
        self.assertFalse(deleted_holder["files"][0]["path_exists"])
        self.assertEqual(
            deleted_holder["process_command"],
            "/opt/codegraph/101/codegraph.js serve --mcp",
        )
        literal_holder = lane_holders[-1]
        self.assertFalse(literal_holder["files"][0]["deleted"])
        self.assertEqual(literal_holder["files"][0]["link_count"], 1)
        self.assertTrue(literal_holder["files"][0]["path_exists"])
        self.assertEqual(
            literal_holder["files"][0]["path"],
            str(literal_deleted_path.resolve()),
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
