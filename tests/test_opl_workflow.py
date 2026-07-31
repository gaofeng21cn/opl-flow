from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.opl_workflow import PROGRAM_REF, WorkflowError, init_ledger, main, reconcile_operations


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

    def test_fleet_is_an_argument_preserving_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "fleet.log"
            fleet = self.executable(root / "codex-fleet", f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {output}\n")
            self.assertEqual(main(["fleet", "--fleet-bin", str(fleet), "repos", "status", "--json"]), 0)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines(), ["repos", "status", "--json"])


if __name__ == "__main__":
    unittest.main()
