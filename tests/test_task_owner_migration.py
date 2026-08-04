from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/opl_task_owner.py"
SPEC = importlib.util.spec_from_file_location("opl_task_owner", SCRIPT)
assert SPEC and SPEC.loader
owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(owner)


class TaskOwnerMigrationTests(unittest.TestCase):
    def issue(self) -> dict[str, object]:
        return {
            "id": "opl-1",
            "title": "Deliver one feature",
            "description": "Finite managed objective",
            "acceptance_criteria": "Canonical and installed",
            "external_ref": "https://linear.app/example/FG-1",
            "parent": "opl-root",
            "metadata": {
                "execution_mode": "active",
                "execution_thread": "thread-source",
                "remaining": ["integrate"],
            },
        }

    def checkpoint(self) -> dict[str, object]:
        return {
            "write_set": ["scripts/tool.py"],
            "remaining": ["integrate"],
            "next_action": "resume from remote checkpoint",
            "git_recovery": [
                {
                    "repository": "example/project",
                    "ref": "refs/heads/codex/task",
                    "commit": "a" * 40,
                    "tree": "b" * 40,
                }
            ],
        }

    def prepared(self) -> tuple[dict[str, object], str, str]:
        issue = self.issue()
        metadata = owner.prepare(
            issue,
            source_owner_id="thread-source",
            source_node_id="source-node",
            source_executor_handle="thread-source",
            target_owner_id="thread-target",
            target_node_id="target-node",
            target_profile_id="target-profile",
            instruction_revision=2,
            instruction_summary="Move this objective to the target node.",
            checkpoint=self.checkpoint(),
            actor="coordinator",
            migration_id="12345678-1234-4234-8234-123456789abc",
        )
        issue["metadata"] = metadata
        receipt = metadata["opl_owner_migration"]
        return issue, receipt["migration_id"], receipt["instruction"]["fingerprint"]

    def workspace(self) -> dict[str, object]:
        return {
            "schema": "opl_fleet_workspace_readback.v1",
            "profile_id": "target-profile",
            "node_ids": ["target-node"],
            "observed_at": "2026-08-04T00:00:00Z",
            "state": "CURRENT",
            "claim_ready": True,
            "fresh_fetch": True,
            "fresh_github": True,
            "profile_fingerprint": "1" * 64,
            "environment_fingerprint": "2" * 64,
            "repository_fingerprint": "3" * 64,
        }

    def node(self) -> dict[str, object]:
        return {
            "schema": "codex_fleet_doctor.v1",
            "node_id": "target-node",
            "checked_at": "2026-08-04T00:00:00Z",
            "ready_for_dispatch": True,
            "admission_ready": True,
            "receipt_state": "CURRENT",
            "current_control_commit": "c" * 40,
            "control_current": True,
            "lease": None,
        }

    def test_full_transition_replaces_executor_but_preserves_objective(self) -> None:
        issue, migration_id, instruction = self.prepared()
        objective = issue["metadata"]["opl_owner_migration"]["objective"]
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        issue["metadata"] = owner.claim(
            issue,
            migration_id=migration_id,
            target_executor_handle="thread-target-new",
            expected_instruction_revision=2,
            expected_instruction_fingerprint=instruction,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        claim = issue["metadata"]["opl_owner_claim"]
        self.assertEqual(claim["generation"], 1)
        self.assertEqual(claim["node_id"], "target-node")
        self.assertEqual(issue["metadata"]["execution_thread"], "thread-target-new")
        self.assertEqual(issue["metadata"]["execution_owner"], "thread-target")
        self.assertEqual(issue["metadata"]["last_execution_thread"], "thread-source")
        issue["metadata"] = owner.verify_target(
            issue,
            migration_id=migration_id,
            target_executor_handle="thread-target-new",
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="target",
        )
        issue["metadata"] = owner.release_source(
            issue,
            migration_id=migration_id,
            actor="coordinator",
        )
        receipt = issue["metadata"]["opl_owner_migration"]
        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["objective"], objective)
        self.assertFalse(issue["metadata"]["owner_mutation_frozen"])

    def test_prepare_rejects_absolute_write_set(self) -> None:
        checkpoint = self.checkpoint()
        checkpoint["write_set"] = ["/Users/example/secret"]
        with self.assertRaisesRegex(owner.TaskOwnerError, "repository-relative"):
            owner.prepare(
                self.issue(),
                source_owner_id="thread-source",
                source_node_id="source-node",
                source_executor_handle="thread-source",
                target_owner_id="thread-target",
                target_node_id="target-node",
                target_profile_id="target-profile",
                instruction_revision=1,
                instruction_summary="Move objective.",
                checkpoint=checkpoint,
                actor="coordinator",
            )

    def test_preflight_rejects_nonfresh_workspace(self) -> None:
        issue, migration_id, _ = self.prepared()
        workspace = self.workspace()
        workspace["fresh_github"] = False
        with self.assertRaisesRegex(owner.TaskOwnerError, "not claim-ready"):
            owner.preflight(
                issue,
                migration_id=migration_id,
                workspace_readback=workspace,
                node_readback=self.node(),
                actor="coordinator",
            )

    def test_preflight_rejects_stale_node_control_receipt(self) -> None:
        issue, migration_id, _ = self.prepared()
        node = self.node()
        node["control_current"] = False
        node["ready_for_dispatch"] = False
        node["admission_ready"] = False
        with self.assertRaisesRegex(owner.TaskOwnerError, "not admitted"):
            owner.preflight(
                issue,
                migration_id=migration_id,
                workspace_readback=self.workspace(),
                node_readback=node,
                actor="coordinator",
            )

    def test_claim_rejects_workspace_drift_without_mutation(self) -> None:
        issue, migration_id, instruction = self.prepared()
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        before = copy.deepcopy(issue)
        workspace = self.workspace()
        workspace["repository_fingerprint"] = "4" * 64
        with self.assertRaisesRegex(owner.TaskOwnerError, "changed after preflight"):
            owner.claim(
                issue,
                migration_id=migration_id,
                target_executor_handle="thread-target",
                expected_instruction_revision=2,
                expected_instruction_fingerprint=instruction,
                workspace_readback=workspace,
                node_readback=self.node(),
                actor="coordinator",
            )
        self.assertEqual(issue, before)

    def test_claim_rejects_instruction_drift_without_mutation(self) -> None:
        issue, migration_id, instruction = self.prepared()
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        before = copy.deepcopy(issue)
        with self.assertRaisesRegex(owner.TaskOwnerError, "instruction"):
            owner.claim(
                issue,
                migration_id=migration_id,
                target_executor_handle="thread-target",
                expected_instruction_revision=3,
                expected_instruction_fingerprint=instruction,
                workspace_readback=self.workspace(),
                node_readback=self.node(),
                actor="coordinator",
            )
        self.assertEqual(issue, before)

    def test_second_target_cannot_replace_claim(self) -> None:
        issue, migration_id, instruction = self.prepared()
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        issue["metadata"] = owner.claim(
            issue,
            migration_id=migration_id,
            target_executor_handle="winner",
            expected_instruction_revision=2,
            expected_instruction_fingerprint=instruction,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        with self.assertRaisesRegex(owner.TaskOwnerError, "another executor"):
            owner.claim(
                issue,
                migration_id=migration_id,
                target_executor_handle="loser",
                expected_instruction_revision=2,
                expected_instruction_fingerprint=instruction,
                workspace_readback=self.workspace(),
                node_readback=self.node(),
                actor="coordinator",
            )

    def test_verify_rejects_workspace_drift_after_claim(self) -> None:
        issue, migration_id, instruction = self.prepared()
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        issue["metadata"] = owner.claim(
            issue,
            migration_id=migration_id,
            target_executor_handle="winner",
            expected_instruction_revision=2,
            expected_instruction_fingerprint=instruction,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        before = copy.deepcopy(issue)
        workspace = self.workspace()
        workspace["environment_fingerprint"] = "4" * 64
        with self.assertRaisesRegex(owner.TaskOwnerError, "changed after claim"):
            owner.verify_target(
                issue,
                migration_id=migration_id,
                target_executor_handle="winner",
                workspace_readback=workspace,
                node_readback=self.node(),
                actor="target",
            )
        self.assertEqual(issue, before)

    def test_rollback_is_allowed_only_before_target_claim(self) -> None:
        issue, migration_id, instruction = self.prepared()
        issue["metadata"] = owner.preflight(
            issue,
            migration_id=migration_id,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        issue["metadata"] = owner.claim(
            issue,
            migration_id=migration_id,
            target_executor_handle="winner",
            expected_instruction_revision=2,
            expected_instruction_fingerprint=instruction,
            workspace_readback=self.workspace(),
            node_readback=self.node(),
            actor="coordinator",
        )
        with self.assertRaisesRegex(owner.TaskOwnerError, "cannot roll back"):
            owner.rollback(issue, migration_id=migration_id, actor="coordinator")


if __name__ == "__main__":
    unittest.main()
