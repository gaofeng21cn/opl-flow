from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import TEST_CONTROL_COMMIT, admission
from fleet import fleet_attempts as attempts
from fleet import fleet_cli as cli
from fleet import fleet_common as common
from fleet import fleet_lease as lease_mod
from fleet import fleet_queue as queue
from scripts import opl_events as events
from scripts import opl_execution as execution


class FleetAttemptsAndQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state_root = self.root / "state"
        self.instance = self.root / "instance"
        (self.instance / "fleet").mkdir(parents=True)
        (self.instance / "fleet/fleet.json").write_text(json.dumps({"repository": "example/instance"}), encoding="utf-8")
        (self.instance / "fleet/nodes.json").write_text(json.dumps({"nodes": {}}), encoding="utf-8")

        for mod, attrs in (
            (common, {"STATE_ROOT": self.state_root, "INSTANCE_POINTER_PATH": self.root / "instance.json", "CONFIG_PATH": self.root / "node.json"}),
            (lease_mod, {"STATE_ROOT": self.state_root}),
        ):
            for attr, val in attrs.items():
                p = mock.patch.object(mod, attr, val)
                p.start()
                self.addCleanup(p.stop)

    def test_attempt_heartbeat_stale_suspend_preemption_and_sanitized_telemetry(self) -> None:
        adm = admission(common.utc_now())
        lease = lease_mod.acquire_lease_record(
            node_id="mac-mini",
            owner_task="opl-bg",
            owner_thread=None,
            owner_run=None,
            role=None,
            workload_class="background",
            priority=200,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=600,
            control_revision=TEST_CONTROL_COMMIT,
            admission=adm,
            state_root=self.state_root,
        )
        binding = {"attempt_id": "att-1", "objective_id": "opl-bg", "owner_id": "thread-bg", "handoff_sha256": "a" * 64}
        attempts.record_attempt_start(
            attempt_id="att-1",
            objective_id="opl-bg",
            owner_id="thread-bg",
            adapter="remote-codex",
            node_id="mac-mini",
            handoff_binding=binding,
            resumability={"checkpointable": True, "heartbeat_interval_seconds": 30, "max_stale_seconds": 120, "interruptible_phase": "interruptible"},
            envelope_summary={"enforced": True, "max_tokens": 1000},
            lease_id=lease["lease_id"],
            lease_generation=lease["generation"],
            lease_nonce=lease["nonce"],
            state_root=self.state_root,
            now="2026-11-24T00:00:00Z",
        )

        # Preemption check: lower priority denied, higher priority allowed
        no_preempt = attempts.plan_preemption("mac-mini", incoming_priority=150, state_root=self.state_root)
        self.assertFalse(no_preempt["preemption_possible"])
        yes_preempt = attempts.plan_preemption("mac-mini", incoming_priority=800, state_root=self.state_root)
        self.assertTrue(yes_preempt["preemption_possible"])

        # Heartbeat records budget usage and detects violation
        hb = attempts.heartbeat_attempt(
            "att-1",
            phase="testing",
            checkpoint_ref="git:repo@chk1",
            budget_usage={"tokens_used": 1200},
            state_root=self.state_root,
            now="2026-11-24T00:01:00Z",
        )
        self.assertFalse(hb["budget_within_limits"])

        # Telemetry output is strictly read-only, observation-only, and contains zero forbidden fields
        tel = attempts.observe_attempts(node_id="mac-mini", state_root=self.state_root)
        self.assertEqual(tel["schema"], "opl_fleet_attempt_telemetry.v1")
        self.assertEqual(tel["access"], "read_only")
        self.assertEqual(tel["authority"], "observation_only")
        execution.sanitize_check(tel)

        # Suspend gracefully releases lease
        susp = attempts.suspend_attempt(
            "att-1",
            checkpoint_ref="git:repo@chk2",
            reason="preempted_by_p0",
            state_root=self.state_root,
            now="2026-11-24T00:01:30Z",
        )
        self.assertTrue(susp["lease_released"])
        self.assertEqual(susp["attempt"]["state"], "suspended_checkpointed")
        self.assertEqual(lease_mod.read_lease_store(state_root=self.state_root)["leases"], {})

        # Non-interruptible attempt cannot be suspended
        attempts.record_attempt_start(
            attempt_id="att-locked",
            objective_id="opl-locked",
            owner_id="thread-2",
            adapter="local-codex",
            node_id="local",
            handoff_binding={**binding, "attempt_id": "att-locked", "objective_id": "opl-locked"},
            resumability={"checkpointable": True, "max_stale_seconds": 60, "interruptible_phase": "non-interruptible"},
            state_root=self.state_root,
            now="2026-11-24T00:00:00Z",
        )
        with self.assertRaisesRegex(common.FleetError, "non-interruptible"):
            attempts.suspend_attempt("att-locked", checkpoint_ref="git:repo@chk3", state_root=self.state_root)

        # Stale check transitions expired heartbeat to stale_unknown
        stale = attempts.check_stale_attempts(state_root=self.state_root, now="2026-11-24T00:05:00Z")
        self.assertEqual(stale["stale_count"], 1)
        self.assertEqual(stale["stale_attempts"][0]["attempt_id"], "att-locked")
        self.assertEqual(stale["stale_attempts"][0]["state"], "stale_unknown")

    def test_queue_ordering_node_capacity_and_preemption(self) -> None:
        adm = admission(common.utc_now())
        lease = lease_mod.acquire_lease_record(
            node_id="node-a",
            owner_task="opl-running",
            owner_thread=None,
            owner_run=None,
            role=None,
            workload_class="background",
            priority=200,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=600,
            control_revision=TEST_CONTROL_COMMIT,
            admission=adm,
            state_root=self.state_root,
        )
        self.assertIsNotNone(lease)
        items = [
            {"objective_id": "opl-low", "adapter": "ssh-session", "priority": 100, "unlocks_count": 0},
            {"objective_id": "opl-human", "adapter": "ssh-session", "priority": 200, "has_human_comment": True},
            {"objective_id": "opl-high", "adapter": "ssh-session", "priority": 900, "unlocks_count": 3},
            {"objective_id": "opl-wait", "adapter": "ssh-session", "priority": 50},
        ]
        cands = {
            "opl-human": [{"node_id": "node-b", "lease": None}],
            "opl-high": [{"node_id": "node-a", "lease": {"owner_task": "opl-running"}}],
            "opl-low": [{"node_id": "node-b", "lease": None}],
            "opl-wait": [{"node_id": "node-b", "lease": None}],
        }
        plan = queue.plan_queue(items, candidates_by_item=cands, state_root=self.state_root)
        # opl-human gets node-b; opl-low & opl-wait cannot double-book node-b; opl-high finds preemption on node-a
        self.assertEqual([a["objective_id"] for a in plan["admit_now"]], ["opl-human"])
        self.assertEqual(plan["preempt_candidates"][0]["incoming_objective_id"], "opl-high")
        self.assertEqual(plan["preempt_candidates"][0]["node_id"], "node-a")
        self.assertEqual(plan["summary"]["queued_backpressure"], 3)

    def test_writes_instance_state_classification_for_new_cli_commands(self) -> None:
        readonly_cases = [
            ["attempt", "status"],
            ["attempt", "observe"],
            ["attempt", "preempt-plan", "node-a", "--incoming-priority", "500"],
            ["queue", "plan", "--requests-json", "[]"],
            ["dispatch", "group", "plan", "--group-json", "{}"],
            ["dispatch", "group", "status", "grp-1"],
        ]
        mutating_cases = [
            ["attempt", "heartbeat", "att-1"],
            ["attempt", "suspend", "att-1", "--checkpoint-ref", "git:repo@1"],
            ["attempt", "stale-check"],
            ["dispatch", "run", "--owner-task", "opl-1", "--handoff-json", "{}"],
            ["dispatch", "complete", "--handoff-json", "{}", "--result-json", "{}"],
            ["dispatch", "group", "run", "--group-json", "{}"],
        ]
        for argv in readonly_cases:
            self.assertFalse(cli.writes_instance_state(cli.parse_args(argv)), argv)
        for argv in mutating_cases:
            self.assertTrue(cli.writes_instance_state(cli.parse_args(argv)), argv)


if __name__ == "__main__":
    unittest.main()
