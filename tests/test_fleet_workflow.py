from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import fictional_registry, fleet, git
from opl_fleet_parts import fleet_common as common
from opl_fleet_parts import fleet_workflow as workflow


class FleetWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.flow = self.repository(root / "flow")
        self.instance = self.repository(root / "instance")
        self.control = self.instance / "fleet"
        self.control.mkdir()
        self.codex = root / "codex"
        self.codex.mkdir()
        self.agents = self.codex / "AGENTS.md"
        self.old = "Validated previous workflow.\n"
        self.current = "Validated new workflow.\n"
        (self.flow / "templates").mkdir()
        (self.flow / workflow.PROFILE_PATH).write_text(self.old)
        self.commit(self.flow)
        (self.flow / workflow.PROFILE_PATH).write_text(self.current)
        self.revision = self.commit(self.flow)
        self.registry = fictional_registry()
        self.registry["flagship_node_id"] = "fictional-gpu-a"
        self.spec = {
            "schema": "codex_fleet_control.v1", "repository": "example/instance",
            "repository_owner": "example", "runner": {},
            "schedule": {"service_id": "example.fleet"},
            "workflow_projection": {
                "flagship_node_id": "fictional-gpu-a",
                "source_agents_sha256": hashlib.sha256(self.current.encode()).hexdigest(),
                "flow_commit": self.revision,
            },
        }
        self.publish_control()
        self.agents.write_text(self.old)
        for name, value in (("FLOW_ROOT", self.flow), ("CONTROL_ROOT", self.control)):
            patch = mock.patch.object(common, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(common, "effective_codex_home", return_value=self.codex)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(common, "node_identity", return_value="fictional-gpu-b")
        self.identity = patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(workflow, "apply_profile", side_effect=self.apply)
        self.writer = patch.start()
        self.addCleanup(patch.stop)

    def repository(self, path):
        path.mkdir()
        git(path, "init", "-b", "main")
        git(path, "config", "user.name", "Fleet Fixture")
        git(path, "config", "user.email", "fleet@example.invalid")
        # Fetch resolves locally; no real remotes or machine state in tests.
        git(path, "remote", "add", "origin", str(path))
        return path

    def commit(self, path):
        git(path, "add", ".")
        git(path, "commit", "--allow-empty", "-m", "fixture")
        git(path, "fetch", "origin", "main")
        return git(path, "rev-parse", "HEAD")

    def publish_control(self):
        (self.control / "nodes.json").write_text(json.dumps(self.registry))
        (self.control / "fleet.json").write_text(json.dumps(self.spec))
        self.commit(self.instance)

    def apply(self, content, expected_sha256):
        actual = common.sha256_file(self.agents) if self.agents.exists() else None
        self.assertEqual(actual, expected_sha256)
        self.agents.write_text(content)
        return True

    def test_receiver_updates_old_template_once_through_framework(self):
        result = workflow.reconcile_workflow()
        self.assertEqual(result["state"], "CURRENT")
        self.assertTrue(result["changed"])
        self.assertEqual(self.agents.read_text(), self.current)
        second = workflow.reconcile_workflow()
        self.assertFalse(second["changed"])
        self.writer.assert_called_once_with(self.current, hashlib.sha256(self.old.encode()).hexdigest())

    def test_new_receiver_creates_one_global_file(self):
        self.agents.unlink()
        self.assertTrue(workflow.reconcile_workflow()["changed"])
        self.writer.assert_called_once_with(self.current, None)
        self.assertEqual(list(self.codex.iterdir()), [self.agents])

    def test_flagship_preserves_unprojected_edits_and_reports_them(self):
        self.identity.return_value = "fictional-gpu-a"
        self.agents.write_text(self.current + "Local improvement.\n")
        before = self.agents.read_bytes()
        self.assertEqual(workflow.reconcile_workflow()["state"], "PROJECTION_REQUIRED")
        self.assertEqual(self.agents.read_bytes(), before)
        self.writer.assert_not_called()

    def test_flagship_does_not_bootstrap_missing_instructions(self):
        self.identity.return_value = "fictional-gpu-a"
        self.agents.unlink()
        self.assertEqual(workflow.reconcile_workflow()["state"], "PROJECTION_REQUIRED")
        self.assertFalse(self.agents.exists())

    def test_custom_receiver_is_preserved_across_repeated_sync(self):
        self.agents.write_text(self.old + "Private authorization.\n")
        before = self.agents.read_bytes()
        for _ in range(2):
            self.assertEqual(workflow.reconcile_workflow()["state"], "LOCAL_CHANGES")
        self.assertEqual(self.agents.read_bytes(), before)
        self.writer.assert_not_called()

    def test_unpublished_template_is_not_an_automatic_merge_baseline(self):
        (self.flow / workflow.PROFILE_PATH).write_text("Unpublished edit.\n")
        git(self.flow, "add", ".")
        git(self.flow, "commit", "-m", "unpublished")
        self.agents.write_text("Unpublished edit.\n")
        self.assertEqual(workflow.reconcile_workflow()["state"], "LOCAL_CHANGES")
        self.writer.assert_not_called()

    def test_invalid_projection_never_writes(self):
        self.spec["workflow_projection"]["flow_commit"] = "f" * 40
        self.publish_control()
        with self.assertRaisesRegex(fleet.FleetError, "not published"):
            workflow.reconcile_workflow()
        self.writer.assert_not_called()

    def test_symlink_is_not_replaced_or_followed(self):
        other = self.codex / "private.md"
        self.agents.rename(other)
        self.agents.symlink_to(other)
        self.assertEqual(workflow.reconcile_workflow()["state"], "LOCAL_CHANGES")
        self.assertEqual(other.read_text(), self.old)
        self.writer.assert_not_called()

    def test_switch_moves_only_authoring_role_and_preserves_old_flagship(self):
        before = self.registry.copy()
        result = workflow.set_flagship("fictional-gpu-b", expected_current="fictional-gpu-a")
        self.assertEqual(result["state"], "PUBLISH_REQUIRED")
        changed = common.read_json(self.control / "nodes.json")
        self.assertEqual(changed["nodes"], before["nodes"])
        self.assertEqual(changed["runner_roles"], before["runner_roles"])
        self.registry = changed
        self.publish_control()
        self.assertEqual(workflow.workflow_status()["role"], "flagship")
        self.identity.return_value = "fictional-gpu-a"
        self.agents.write_text(self.old + "Old flagship private content.\n")
        self.assertEqual(workflow.reconcile_workflow()["state"], "LOCAL_CHANGES")
        with self.assertRaisesRegex(fleet.FleetError, "only the selected flagship"):
            workflow.record_projection(self.revision, source_sha256=common.sha256_file(self.agents))

    def test_switch_rejects_stale_selection_and_unapproved_node(self):
        with self.assertRaisesRegex(fleet.FleetError, "flagship changed"):
            workflow.set_flagship("fictional-gpu-b", expected_current="none")
        with self.assertRaisesRegex(fleet.FleetError, "approved"):
            workflow.set_flagship("unknown-node", expected_current="fictional-gpu-a")
        self.registry["nodes"]["fictional-gpu-b"]["approved"] = False
        self.publish_control()
        with self.assertRaisesRegex(fleet.FleetError, "approved"):
            workflow.set_flagship("fictional-gpu-b", expected_current="fictional-gpu-a")

    def test_review_accepts_private_difference_but_binds_exact_source(self):
        self.identity.return_value = "fictional-gpu-a"
        self.agents.write_text(self.current + "Private authorization stays local.\n")
        digest = common.sha256_file(self.agents)
        result = workflow.record_projection(self.revision, source_sha256=digest)
        self.assertEqual(result["state"], "PUBLISH_REQUIRED")
        self.spec = common.read_json(self.control / "fleet.json")
        self.assertNotIn("Private authorization", json.dumps(self.spec))
        with self.assertRaisesRegex(fleet.FleetError, "publish the Instance"):
            workflow.reconcile_workflow()
        self.publish_control()
        self.assertEqual(workflow.reconcile_workflow()["state"], "CURRENT")
        self.agents.write_text(self.agents.read_text() + "Next optimization.\n")
        with self.assertRaisesRegex(fleet.FleetError, "changed since semantic review"):
            workflow.record_projection(self.revision, source_sha256=digest)
        self.assertEqual(workflow.workflow_status()["state"], "PROJECTION_REQUIRED")

    def test_review_rejects_old_flagship_with_stale_local_registry(self):
        self.identity.return_value = "fictional-gpu-a"
        self.registry["flagship_node_id"] = "fictional-gpu-b"
        self.publish_control()
        self.registry["flagship_node_id"] = "fictional-gpu-a"
        (self.control / "nodes.json").write_text(json.dumps(self.registry))
        with self.assertRaisesRegex(fleet.FleetError, "not current on Instance main"):
            workflow.record_projection(self.revision, source_sha256=common.sha256_file(self.agents))

    def test_writer_failure_cannot_claim_delivery(self):
        self.writer.side_effect = lambda *_: False
        self.assertEqual(workflow.reconcile_workflow()["state"], "APPLY_FAILED")
        self.assertEqual(self.agents.read_text(), self.old)

    def test_unconfigured_legacy_instance_does_not_resume_overwrite(self):
        self.registry.pop("flagship_node_id")
        self.spec.pop("workflow_projection")
        self.publish_control()
        self.assertEqual(workflow.reconcile_workflow()["state"], "UNCONFIGURED")
        self.writer.assert_not_called()

    def test_cli_exposes_switch_and_review_without_implicit_sync(self):
        args = fleet.parse_args(["flagship", "set", "fictional-gpu-b", "--expected-current", "fictional-gpu-a"])
        self.assertEqual(args.flagship_action, "set")
        args = fleet.parse_args(["workflow", "record-projection", "--flow-commit", self.revision, "--source-sha256", "a" * 64])
        self.assertEqual(args.workflow_action, "record-projection")


if __name__ == "__main__":
    unittest.main()
