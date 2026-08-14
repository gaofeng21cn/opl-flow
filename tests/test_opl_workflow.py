from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.opl_workflow import (
    PROGRAM_REF,
    WorkflowError,
    init_ledger,
    linear_probe,
    main,
    reconcile_operations,
    supervisor_snapshot,
    workflow_status,
)


class OplWorkflowTest(unittest.TestCase):
    def executable(self, path: Path, body: str) -> Path:
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def fixture(self, root: Path, existing: list[dict] | None = None) -> tuple[Path, Path, Path]:
        instance = root / "instance"
        (instance / "operations").mkdir(parents=True)
        (instance / ".beads").mkdir()
        (instance / ".beads" / "metadata.json").write_text("{}\n", encoding="utf-8")
        (instance / "operations" / "registry.json").write_text(
            json.dumps(
                {
                    "schema": "opl_operations_registry.v1",
                    "services": [{"id": "service-a", "name": "Service A", "maintenance": {"next_review_on": "2026-09-01"}}],
                    "domains": [{"id": "example-org", "fqdn": "example.org", "maintenance": {"next_review_on": "2026-08-10", "action_zh": "核实自动续费。"}}],
                    "platform_accounts": [],
                }
            ),
            encoding="utf-8",
        )
        log = root / "bd.log"
        data = root / "existing.json"
        data.write_text(json.dumps(existing or []), encoding="utf-8")
        bd = self.executable(
            root / "bd",
            """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["BD_TEST_LOG"]).open("a", encoding="utf-8") as out:
    out.write(json.dumps(args, ensure_ascii=False) + "\\n")
if args[:1] == ["list"]:
    print(Path(os.environ["BD_TEST_DATA"]).read_text(encoding="utf-8"))
elif args[:1] == ["create"]:
    ref = args[args.index("--external-ref") + 1]
    print(json.dumps({"id": "opl-created", "external_ref": ref, "status": "open"}))
elif args[:1] == ["init"]:
    Path(".beads").mkdir(exist_ok=True)
    Path(".beads/metadata.json").write_text("{}\\n", encoding="utf-8")
    print("initialized")
else:
    print("{}")
""",
        )
        return instance, bd, log

    def env(self, root: Path):
        return mock.patch.dict(os.environ, {"BD_TEST_LOG": str(root / "bd.log"), "BD_TEST_DATA": str(root / "existing.json")})

    def calls(self, log: Path) -> list[list[str]]:
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def test_reconcile_creates_program_and_dated_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance, bd, log = self.fixture(root)
            with self.env(root):
                result = reconcile_operations(instance, str(bd))
            calls = self.calls(log)
            refs = {call[call.index("--external-ref") + 1] for call in calls if call[:1] == ["create"]}
            self.assertEqual(result["counts"], {"scheduled_assets": 2, "created": 3, "unchanged": 0})
            self.assertIn(PROGRAM_REF, refs)
            self.assertIn("opl://operations/domain/example-org/review/2026-08-10", refs)

    def test_reconcile_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = [
                {"id": "opl-program", "external_ref": PROGRAM_REF, "status": "in_progress"},
                {"id": "opl-service", "external_ref": "opl://operations/service/service-a/review/2026-09-01"},
                {"id": "opl-domain", "external_ref": "opl://operations/domain/example-org/review/2026-08-10"},
            ]
            instance, bd, log = self.fixture(root, existing)
            with self.env(root):
                result = reconcile_operations(instance, str(bd))
            self.assertFalse(any(call[:1] == ["create"] for call in self.calls(log)))
            self.assertEqual(result["counts"], {"scheduled_assets": 2, "created": 0, "unchanged": 2})

    def test_reconcile_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance, bd, log = self.fixture(root, [{"id": "opl-program", "external_ref": PROGRAM_REF, "status": "open"}])
            with self.env(root):
                result = reconcile_operations(instance, str(bd), dry_run=True)
            self.assertFalse(any(call[:1] in (["create"], ["update"]) for call in self.calls(log)))
            self.assertEqual(result["counts"]["created"], 2)

    def test_registry_only_assets_do_not_create_a_program_or_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance, bd, log = self.fixture(root)
            (instance / "operations" / "registry.json").write_text(
                json.dumps(
                    {
                        "schema": "opl_operations_registry.v1",
                        "services": [{"id": "service-a", "maintenance": {}}],
                        "domains": [{"id": "example-org", "maintenance": {"renewal_owner": "registrar"}}],
                        "platform_accounts": [{"id": "account-a", "maintenance": {}}],
                    }
                ),
                encoding="utf-8",
            )
            with self.env(root):
                result = reconcile_operations(instance, str(bd))
            self.assertFalse(log.exists())
            self.assertEqual(result["counts"], {"scheduled_assets": 0, "created": 0, "unchanged": 0})

    def test_reconcile_mixes_registry_only_and_explicit_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance, bd, log = self.fixture(root)
            registry = json.loads((instance / "operations" / "registry.json").read_text(encoding="utf-8"))
            registry["services"][0]["maintenance"] = {}
            (instance / "operations" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            with self.env(root):
                result = reconcile_operations(instance, str(bd))
            refs = {
                call[call.index("--external-ref") + 1]
                for call in self.calls(log)
                if call[:1] == ["create"]
            }
            self.assertEqual(result["counts"], {"scheduled_assets": 1, "created": 2, "unchanged": 0})
            self.assertEqual(refs, {PROGRAM_REF, "opl://operations/domain/example-org/review/2026-08-10"})

    def test_reconcile_rejects_non_string_review_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instance, bd, log = self.fixture(root)
            registry = json.loads((instance / "operations" / "registry.json").read_text(encoding="utf-8"))
            registry["services"][0]["maintenance"]["next_review_on"] = 20260901
            (instance / "operations" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
            with self.env(root), self.assertRaisesRegex(WorkflowError, "invalid next_review_on"):
                reconcile_operations(instance, str(bd))
            self.assertFalse(log.exists())

    def test_supervisor_snapshot_compacts_owner_fields_and_ready_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            issue = {
                "id": "opl-1",
                "title": "Current objective",
                "status": "in_progress",
                "priority": 1,
                "issue_type": "task",
                "owner": "owner@example.com",
                "updated_at": "2026-08-04T00:00:00Z",
                "labels": ["opl"],
                "parent": "opl-root",
                "dependencies": [{"depends_on_id": "opl-0", "type": "blocks", "ignored": "value"}],
                "metadata": {
                    "execution_mode": "active",
                    "execution_thread": "thread-1",
                    "remaining": ["verify"],
                    "linear_issue_identifier": "FG-1",
                    "checkpoint": "must-not-leak",
                },
            }
            git_results = [
                subprocess.CompletedProcess([], 0, str(root) + "\n", ""),
                subprocess.CompletedProcess([], 0, "abc123\n", ""),
                subprocess.CompletedProcess([], 0, "main\n", ""),
                subprocess.CompletedProcess([], 0, "## main...origin/main\n", ""),
            ]
            with (
                mock.patch("scripts.opl_workflow.executable", return_value="/usr/bin/git"),
                mock.patch(
                    "scripts.opl_workflow.run",
                    side_effect=[
                        {"open": 1},
                        [{"id": "opl-1"}],
                        [issue],
                        {"mode": "embedded"},
                        *git_results,
                    ],
                ),
            ):
                result = supervisor_snapshot(root, "/tmp/bd")

            self.assertEqual(result["schema"], "opl_flow_supervisor_snapshot.v1")
            self.assertEqual(result["ready_ids"], ["opl-1"])
            self.assertEqual(result["counts"]["by_execution_mode"], {"active": 1})
            self.assertEqual(
                result["counts"]["semantic"],
                {
                    "unfinished_tasks": 1,
                    "active_objectives": 1,
                    "backlog": 0,
                    "live_executors": 1,
                    "monitoring": 0,
                    "on_demand": 0,
                    "aggregate_control_planes": 0,
                },
            )
            self.assertTrue(result["git"]["clean"])
            self.assertEqual(result["validation_errors"], [])
            self.assertNotIn("checkpoint", result["issues"][0]["metadata"])
            self.assertEqual(
                result["issues"][0]["dependencies"],
                [{"depends_on_id": "opl-0", "type": "blocks"}],
            )

    def test_supervisor_snapshot_reports_mode_remaining_and_mapping_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            issues = [
                {
                    "id": "opl-1",
                    "status": "in_progress",
                    "metadata": {
                        "execution_mode": "unknown",
                        "remaining": "not-json",
                        "linear_issue_identifier": "FG-1",
                    },
                },
                {
                    "id": "opl-2",
                    "status": "blocked",
                    "metadata": {
                        "execution_mode": "waiting_external",
                        "remaining": [],
                        "linear_issue_identifier": "FG-1",
                    },
                },
            ]
            git_results = [
                subprocess.CompletedProcess([], 0, str(root) + "\n", ""),
                subprocess.CompletedProcess([], 0, "abc123\n", ""),
                subprocess.CompletedProcess([], 0, "main\n", ""),
                subprocess.CompletedProcess([], 0, "## main...origin/main\n M local\n", ""),
            ]
            with (
                mock.patch("scripts.opl_workflow.executable", return_value="/usr/bin/git"),
                mock.patch(
                    "scripts.opl_workflow.run",
                    side_effect=[{}, [], issues, {"mode": "embedded"}, *git_results],
                ),
            ):
                result = supervisor_snapshot(root, "/tmp/bd")

            self.assertFalse(result["git"]["clean"])
            self.assertEqual(result["counts"]["semantic"]["unfinished_tasks"], 1)
            self.assertEqual(result["counts"]["semantic"]["live_executors"], 0)
            self.assertEqual(result["counts"]["validation_errors"], 3)
            self.assertTrue(
                any(
                    "unknown metadata.execution_mode" in item
                    for item in result["validation_errors"]
                )
            )
            self.assertTrue(
                any(
                    "remaining must be a JSON array" in item
                    for item in result["validation_errors"]
                )
            )
            self.assertTrue(
                any(
                    "duplicate linear_issue_identifier" in item
                    for item in result["validation_errors"]
                )
            )

    def test_supervisor_snapshot_separates_backlog_from_on_demand(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            issues = [
                {
                    "id": "opl-backlog",
                    "status": "deferred",
                    "metadata": {
                        "classification": "managed_objective",
                        "execution_mode": "backlog",
                        "execution_thread": None,
                        "remaining": ["planned implementation"],
                    },
                },
                {
                    "id": "opl-invalid-on-demand",
                    "status": "pinned",
                    "metadata": {
                        "classification": "managed_objective",
                        "execution_mode": "on_demand",
                        "execution_thread": None,
                        "remaining": ["queued implementation"],
                    },
                },
            ]
            git_results = [
                subprocess.CompletedProcess([], 0, str(root) + "\n", ""),
                subprocess.CompletedProcess([], 0, "abc123\n", ""),
                subprocess.CompletedProcess([], 0, "main\n", ""),
                subprocess.CompletedProcess([], 0, "## main...origin/main\n", ""),
            ]
            with (
                mock.patch("scripts.opl_workflow.executable", return_value="/usr/bin/git"),
                mock.patch(
                    "scripts.opl_workflow.run",
                    side_effect=[{}, [], issues, {"mode": "embedded"}, *git_results],
                ),
            ):
                result = supervisor_snapshot(root, "/tmp/bd")

            self.assertEqual(
                result["counts"]["by_execution_mode"],
                {"backlog": 1, "on_demand": 1},
            )
            self.assertEqual(result["counts"]["semantic"]["backlog"], 1)
            self.assertIn(
                "opl-invalid-on-demand: on_demand is reserved for interactive_longline",
                result["validation_errors"],
            )

    def test_init_rejects_linked_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.mkdir(exist_ok=True)
            with (
                mock.patch("scripts.opl_workflow.ledger_probe", return_value=None),
                mock.patch("scripts.opl_workflow.run") as run_mock,
            ):
                run_mock.side_effect = [mock.Mock(stdout=".git/worktrees/task\n"), mock.Mock(stdout=".git\n")]
                with self.assertRaisesRegex(WorkflowError, "primary checkout"):
                    init_ledger(root, "/usr/bin/true", "opl")

    def test_init_rejects_dirty_primary_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch("scripts.opl_workflow.ledger_probe", return_value=None),
                mock.patch("scripts.opl_workflow.run") as run_mock,
            ):
                run_mock.side_effect = [
                    mock.Mock(stdout=".git\n"),
                    mock.Mock(stdout=".git\n"),
                    mock.Mock(stdout="?? local.txt\n"),
                ]
                with self.assertRaisesRegex(WorkflowError, "clean Git checkout"):
                    init_ledger(root, "/usr/bin/true", "opl")

    def test_init_secures_existing_ledger_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".beads").mkdir()
            with (
                mock.patch("scripts.opl_workflow.ledger_probe", return_value={}),
                mock.patch("scripts.opl_workflow.os.chmod") as chmod,
            ):
                self.assertEqual(init_ledger(root, "/usr/bin/true", "opl")["state"], "already_initialized")
            chmod.assert_called_once_with(root / ".beads", 0o700)

    def test_fleet_is_an_argument_preserving_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "fleet.log"
            fleet = self.executable(root / "codex-fleet", f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {output}\n")
            self.assertEqual(main(["fleet", "--fleet-bin", str(fleet), "repos", "status", "--json"]), 0)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines(), ["repos", "status", "--json"])

    def test_fleet_uses_bundled_engine_for_an_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            instance = Path(temp) / "instance"
            (instance / "fleet").mkdir(parents=True)
            for name in ("fleet.json", "nodes.json"):
                (instance / "fleet" / name).write_text("{}\n", encoding="utf-8")
            with mock.patch("scripts.opl_workflow.subprocess.run") as command:
                command.return_value = subprocess.CompletedProcess([], 0, "", "")
                self.assertEqual(
                    main(
                        [
                            "fleet",
                            "--instance",
                            str(instance),
                            "nodes",
                            "--json",
                        ]
                    ),
                    0,
                )
            argv = command.call_args.args[0]
            self.assertEqual(argv[0], sys.executable)
            self.assertEqual(Path(argv[1]).name, "opl_fleet.py")
            self.assertEqual(argv[2:4], ["--instance", str(instance.resolve())])
            self.assertEqual(argv[4:], ["nodes", "--json"])
            self.assertEqual(
                command.call_args.kwargs["env"]["PYTHONDONTWRITEBYTECODE"],
                "1",
            )

    def test_linear_status_drops_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bd = self.executable(
                root / "bd",
                """#!/usr/bin/env python3
import json, sys
if sys.argv[1:3] == ["linear", "status"]:
    print(json.dumps({"configured": True, "auth_mode": "oauth", "api_key": "secret"}))
elif sys.argv[1:2] == ["list"]:
    print("[]")
""",
            )
            result = linear_probe(root, str(bd))
            self.assertTrue(result["configured"])
            self.assertEqual(result["configuration_sources"], ["legacy_adapter"])
            self.assertTrue(result["legacy_adapter_configured"])
            self.assertNotIn("api_key", result)
            self.assertNotIn("api_key", result["legacy_adapter"])

    def test_linear_status_reports_managed_projection_without_legacy_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bd = self.executable(
                root / "bd",
                """#!/usr/bin/env python3
import json, sys
if sys.argv[1:3] == ["linear", "status"]:
    print(json.dumps({
        "configured": False,
        "auth_mode": "none",
        "total_issues": 2,
        "with_linear_ref": 1,
    }))
elif sys.argv[1:2] == ["list"]:
    print(json.dumps({"schema_version": 1, "issues": [
        {"metadata": {
            "linear_projection": "managed",
            "linear_issue_identifier": "FG-1",
            "linear_issue_url": "https://linear.app/example/FG-1",
        }},
        {"metadata": {
            "linear_projection": "managed",
            "linear_issue_identifier": "FG-2",
            "linear_issue_url": "https://linear.app/example/FG-2",
        }},
    ]}))
""",
            )
            result = linear_probe(root, str(bd))
            self.assertEqual(result["state"], "current")
            self.assertTrue(result["configured"])
            self.assertEqual(result["configuration_sources"], ["managed_projection"])
            self.assertFalse(result["legacy_adapter_configured"])
            self.assertEqual(result["legacy_external_ref_count"], 1)
            self.assertEqual(
                result["projection"],
                {
                    "state": "current",
                    "total_issue_count": 2,
                    "managed_issue_count": 2,
                    "identifier_count": 2,
                    "url_count": 2,
                    "coverage_complete": True,
                },
            )

    def test_linear_status_degrades_when_projection_readback_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bd = self.executable(
                root / "bd",
                """#!/usr/bin/env python3
import json, sys
if sys.argv[1:3] == ["linear", "status"]:
    print(json.dumps({"configured": False, "auth_mode": "none"}))
elif sys.argv[1:2] == ["list"]:
    print("projection unavailable", file=sys.stderr)
    raise SystemExit(1)
""",
            )
            result = linear_probe(root, str(bd))
            self.assertEqual(result["state"], "degraded")
            self.assertFalse(result["configured"])
            self.assertEqual(result["projection"]["state"], "error")

    def test_status_separates_binary_and_ledger_failures(self) -> None:
        with (
            mock.patch("scripts.opl_workflow.cli_probe", return_value={"available": True}),
            mock.patch("scripts.opl_workflow.github_probe", return_value={"available": True, "authenticated": True}),
            mock.patch("scripts.opl_workflow.executable", side_effect=["/usr/bin/true", WorkflowError("no fleet")]),
            mock.patch("scripts.opl_workflow.run", return_value=subprocess.CompletedProcess([], 0, "bd version 1", "")),
            mock.patch("scripts.opl_workflow.ledger_probe", side_effect=WorkflowError("database unreadable")),
            mock.patch("scripts.opl_workflow.linear_probe", return_value={"state": "not_configured"}),
        ):
            result = workflow_status(Path("/tmp"), None, None)
        self.assertTrue(result["beads"]["available"])
        self.assertEqual(result["ledger"]["state"], "error")


if __name__ == "__main__":
    unittest.main()
