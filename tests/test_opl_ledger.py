from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import opl_ledger as ledger


class LedgerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        ledger.run(["git", "init", "-q"], self.root)
        self.beads = self.root / ".beads"
        self.beads.mkdir(mode=0o700)
        ledger.run(["git", "config", "beads.role", "maintainer"], self.root)
        self.state_path = self.root / "fake-state.json"
        self.log = self.root / "fake-calls.jsonl"
        self.bd = self.root / "fake-bd"
        self.bd.write_text(f"#!{sys.executable}\n" + '''import json, sys
from pathlib import Path
root = Path.cwd()
args = [a for a in sys.argv[1:] if a != "--readonly"]
state_path = root / "fake-state.json"
state = json.loads(state_path.read_text())
with (root / "fake-calls.jsonl").open("a") as output:
    output.write(json.dumps(args) + "\\n")
if args[0] == "status":
    print(json.dumps({"backend": "dolt"}))
elif args[0] == "list":
    if not state.get("initialized", True):
        print("not bootstrapped", file=sys.stderr)
        sys.exit(1)
    print("[]")
elif args[0] == "bootstrap":
    state["initialized"] = True
    state_path.write_text(json.dumps(state))
elif args[0] == "show":
    print(json.dumps([state["issue"]]))
elif args[0] == "update":
    if "--metadata" in args:
        state["issue"]["metadata"] = json.loads(args[args.index("--metadata") + 1])
    if "--status" in args:
        state["issue"]["status"] = args[args.index("--status") + 1]
    state_path.write_text(json.dumps(state))
    print(json.dumps(state["issue"]))
elif args[0] == "create":
    state["issue"] = {"id": "opl-created", "title": args[1], "metadata": json.loads(args[args.index("--metadata") + 1])}
    state_path.write_text(json.dumps(state))
    print(json.dumps(state["issue"]))
elif args[0] == "ready":
    print(json.dumps([state["issue"]]))
elif args[:2] == ["dolt", "status"]:
    print(json.dumps({"mode": "embedded"}))
elif args[0] == "version":
    print("fake-bd 1")
elif args[:2] == ["linear", "status"]:
    print(json.dumps({"configured": True, "has_api_key": True, "api_key": "private-value"}))
elif args[:2] == ["dolt", "push"] and state.get("fail_push"):
    print("transport lost", file=sys.stderr)
    sys.exit(1)
elif args[:2] == ["dolt", "pull"] and state.get("fail_pull"):
    print("remote unavailable", file=sys.stderr)
    sys.exit(1)
''')
        self.bd.chmod(0o700)
        self.state = {"initialized": True, "issue": {"id": "opl-1", "metadata": {"owner": "old"}}}
        self.save()

    def save(self):
        self.state_path.write_text(json.dumps(self.state))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_workspace_readback_and_sync_share_one_adapter(self):
        view = ledger.workspace_readback(self.root, "maintainer", fresh_pull=True, bd=str(self.bd))
        self.assertEqual(view, {"role": "maintainer", "fresh_pull": True, "readable": True, "state": "CURRENT"})
        ledger.sync_workspace_ledger(self.root, "maintainer", bd=str(self.bd))
        self.assertNotIn(["bootstrap", "--yes"], self.calls())
        self.assertEqual(self.calls().count(["dolt", "pull"]), 2)

    def test_sync_bootstraps_only_uninitialized_clone(self):
        self.state["initialized"] = False
        self.save()
        ledger.sync_workspace_ledger(self.root, "maintainer", bd=str(self.bd))
        ledger.sync_workspace_ledger(self.root, "maintainer", bd=str(self.bd))
        self.assertEqual(self.calls().count(["bootstrap", "--yes"]), 1)
        self.assertTrue(json.loads(self.state_path.read_text())["initialized"])

    def test_permissions_and_role_block_reads_before_database_access(self):
        self.beads.chmod(0o755)
        self.assertEqual(ledger.workspace_readback(self.root, "maintainer", fresh_pull=True, bd=str(self.bd))["state"], "PERMISSIONS")
        self.beads.chmod(0o700)
        self.assertEqual(ledger.workspace_readback(self.root, "contributor", fresh_pull=True, bd=str(self.bd))["state"], "ROLE_MISMATCH")
        self.assertEqual(self.calls(), [])

    def test_sync_rejects_symlink_without_changing_target_permissions(self):
        self.beads.rmdir()
        target = self.root / "external"
        target.mkdir(mode=0o755)
        self.beads.symlink_to(target)
        before = target.stat().st_mode
        with self.assertRaisesRegex(ledger.LedgerError, "unsafe"):
            ledger.sync_workspace_ledger(self.root, "maintainer", bd=str(self.bd))
        with self.assertRaisesRegex(ledger.LedgerError, "unsafe"):
            ledger.init(self.root, str(self.bd), "opl")
        self.assertEqual(target.stat().st_mode, before)

    def test_pull_failure_is_not_readable_or_current(self):
        self.state["fail_pull"] = True
        self.save()
        view = ledger.workspace_readback(self.root, "maintainer", fresh_pull=True, bd=str(self.bd))
        self.assertEqual(view["state"], "PULL_FAILED")
        self.assertFalse(view["fresh_pull"])
        self.assertFalse(view["readable"])
        self.assertEqual(self.calls(), [["dolt", "pull"]])
        with self.assertRaisesRegex(ledger.LedgerError, "pull failed"):
            ledger.sync_workspace_ledger(self.root, "maintainer", bd=str(self.bd))

    def test_metadata_mutation_reads_canonical_owner_after_push(self):
        result = ledger.apply_metadata(self.root, str(self.bd), self.state["issue"], {"owner": "new"})
        self.assertEqual(result["metadata"], {"owner": "new"})
        self.assertEqual([call[0] for call in self.calls()], ["update", "show", "dolt", "dolt", "show"])
        self.assertEqual(self.calls()[3], ["dolt", "pull"])

    def test_unknown_push_reconciles_without_second_mutation(self):
        self.state["fail_push"] = True
        self.save()
        result = ledger.apply_metadata(self.root, str(self.bd), self.state["issue"], {"owner": "new"})
        self.assertEqual(result["metadata"], {"owner": "new"})
        self.assertEqual(sum(call[0] == "update" for call in self.calls()), 1)
        self.assertEqual(self.calls().count(["dolt", "push"]), 1)

    def test_unknown_push_and_pull_stops_without_retry(self):
        self.state.update(fail_push=True, fail_pull=True)
        self.save()
        with self.assertRaisesRegex(ledger.LedgerError, "result is unknown"):
            ledger.apply_metadata(self.root, str(self.bd), self.state["issue"], {"owner": "new"})
        self.assertEqual(sum(call[0] == "update" for call in self.calls()), 1)
        self.assertEqual(self.calls().count(["dolt", "push"]), 1)

    def test_probe_distinguishes_absent_database_from_failure(self):
        execute = mock.Mock(return_value=subprocess.CompletedProcess([], 1, "", "No beads project found"))
        self.assertIsNone(ledger.probe(self.root, "bd", runner=execute))
        execute.return_value = subprocess.CompletedProcess([], 1, "", "database unavailable")
        with self.assertRaisesRegex(ledger.LedgerError, "database unavailable"):
            ledger.probe(self.root, "bd", runner=execute)
        execute.return_value = subprocess.CompletedProcess([], 0, "[]", "")
        with self.assertRaisesRegex(ledger.LedgerError, "invalid payload"):
            ledger.probe(self.root, "bd", runner=execute)

    def test_init_refuses_dirty_primary_checkout(self):
        with self.assertRaisesRegex(ledger.LedgerError, "clean Git checkout"):
            ledger.init(self.root, str(self.bd), "opl", probe_fn=lambda: None)
        self.assertEqual(self.calls(), [])


    def test_semantic_read_methods_use_the_storage_adapter(self):
        self.assertEqual(ledger.status(self.root, str(self.bd)), {"backend": "dolt"})
        self.assertEqual(ledger.ready(self.root, str(self.bd))[0]["id"], "opl-1")
        self.assertEqual(ledger.dolt_status(self.root, str(self.bd)), {"mode": "embedded"})
        self.assertEqual(ledger.version(self.root, str(self.bd)), "fake-bd 1")
        self.assertEqual(ledger.list_issues(self.root, str(self.bd), statuses=("open", "blocked"), skip_labels=True), [])
        self.assertIn(["list", "--status", "open,blocked", "--limit", "0", "--skip-labels", "--json"], self.calls())

    def test_create_and_status_update_preserve_identity(self):
        issue = ledger.create_issue(
            self.root, str(self.bd), title="Maintenance", issue_type="task",
            external_ref="opl://fixture", labels="opl,test", description="Review",
            metadata={"source": "fixture"}, due="2026-11-02", parent="opl-parent",
        )
        ledger.update_status(self.root, str(self.bd), issue["id"], "in_progress")
        canonical = ledger.read_issue(self.root, str(self.bd), issue["id"])
        self.assertEqual(canonical["id"], "opl-created")
        self.assertEqual(canonical["status"], "in_progress")
        self.assertEqual(canonical["metadata"], {"source": "fixture"})
        create = self.calls()[0]
        self.assertEqual(create[create.index("--defer") + 1], "2026-11-02")
        self.assertEqual(create[create.index("--due") + 1], "2026-11-02")
        self.assertEqual(create[create.index("--parent") + 1], "opl-parent")

    def test_legacy_linear_status_only_returns_approved_metadata(self):
        result = ledger.legacy_linear_status(self.root, str(self.bd))
        self.assertTrue(result["configured"])
        self.assertTrue(result["has_api_key"])
        self.assertNotIn("api_key", result)
        self.assertNotIn("private-value", json.dumps(result))

    def test_list_normalizes_envelope_and_rejects_invalid_shape(self):
        execute = mock.Mock(return_value={"issues": [{"id": "opl-1"}]})
        self.assertEqual(ledger.list_issues(self.root, "bd", runner=execute), [{"id": "opl-1"}])
        execute.return_value = {"issues": None}
        with self.assertRaisesRegex(ledger.LedgerError, "invalid payload"):
            ledger.list_issues(self.root, "bd", runner=execute)
