from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import TEST_CONTROL_COMMIT, admission, fleet
from fleet import fleet_adapter as adapter
from fleet import fleet_attempts as attempts
from fleet import fleet_common as common
from fleet import fleet_lease as lease_mod
from scripts import opl_events as events
from scripts import opl_execution as execution


class FleetAdapterTests(unittest.TestCase):
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

    def _handoff(self, *, attempt_id: str = "att-1", objective_id: str = "opl-1", input_refs=None, write_set=None, envelope=None) -> dict:
        payload = {
            "schema": "opl_worker_handoff.v1",
            "attempt_id": attempt_id,
            "objective_id": objective_id,
            "owner_id": "thread-1",
            "scope": "Execute bounded slice",
            "input_refs": input_refs if input_refs is not None else [],
            "checkpoint_refs": [],
            "expected_result": "Validated worker result",
        }
        if write_set is not None:
            payload["write_set"] = write_set
        if envelope is not None:
            payload["envelope"] = envelope
        return payload

    def test_restore_handoff_context_verifies_digest_and_blocks_traversal(self) -> None:
        ws = self.root / "workspace"
        ws.mkdir()
        artifact = ws / "data/input.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"hello opl")
        good_sha = hashlib.sha256(b"hello opl").hexdigest()
        runtime_dir = self.root / "runtime"

        h_ok = self._handoff(input_refs=[f"file:data/input.txt#sha256={good_sha}"])
        res = adapter.restore_handoff_context(h_ok, workspace_root=ws, runtime_dir=runtime_dir)
        self.assertTrue(res["restored"])
        self.assertTrue(Path(res["manifest_path"]).is_file())

        h_bad_sha = self._handoff(input_refs=[f"file:data/input.txt#sha256={'0'*64}"])
        with self.assertRaisesRegex(common.FleetError, "digest mismatch"):
            adapter.restore_handoff_context(h_bad_sha, workspace_root=ws)

        h_escape = self._handoff(input_refs=["file:../secret.txt"])
        with self.assertRaisesRegex(common.FleetError, "traverse"):
            adapter.restore_handoff_context(h_escape, workspace_root=ws)

    def test_dispatch_run_local_codex_execute_and_envelope_modes(self) -> None:
        cb_dir = self.root / "callbacks"
        h = self._handoff(attempt_id="att-local-1", objective_id="opl-local-1")
        # Subprocess reads OPL_HANDOFF_PATH and outputs a valid opl_worker_result.v1
        worker_script = (
            "import json, os, hashlib; "
            "h = json.load(open(os.environ['OPL_HANDOFF_PATH'])); "
            "raw = json.dumps(h, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(); "
            "b = {'attempt_id': h['attempt_id'], 'objective_id': h['objective_id'], 'owner_id': h['owner_id'], 'handoff_sha256': hashlib.sha256(raw).hexdigest()}; "
            "print(json.dumps({'schema':'opl_worker_result.v1','binding':b,'outcome':'completed','artifact_refs':['git:repo@123'],'checkpoint_refs':[],'remaining':[],'next_action':'Accept'}))"
        )
        res = adapter.dispatch_run(
            handoff=h,
            adapter="local-codex",
            owner_task="opl-local-1",
            executor_cmd=[sys.executable, "-c", worker_script],
            callback_state_dir=cb_dir,
            state_root=self.state_root,
        )
        self.assertEqual(res["status"], "completed")
        self.assertFalse(res["lease_retained"])
        self.assertEqual(attempts.get_attempt("att-local-1", state_root=self.state_root)["state"], "completed")
        cb_events = events.list_events(cb_dir, objective_id="opl-local-1")
        self.assertEqual(len(cb_events), 1)
        self.assertEqual(cb_events[0]["event_type"], "worker_callback")

        # Envelope mode creates admitted attempt & launch envelope
        h_env = self._handoff(attempt_id="att-env-1", objective_id="opl-env-1")
        env_res = adapter.dispatch_run(
            handoff=h_env,
            adapter="local-codex",
            owner_task="opl-env-1",
            mode="envelope",
            state_root=self.state_root,
        )
        self.assertEqual(env_res["status"], "awaiting_completion")
        self.assertEqual(attempts.get_attempt("att-env-1", state_root=self.state_root)["state"], "admitted")

    def test_pre_execution_envelope_fails_before_lease_or_transport(self) -> None:
        h = self._handoff(
            attempt_id="att-fail-1",
            objective_id="opl-fail-1",
            write_set=["secrets/private.key"],
            envelope={"allowed_write_paths": ["scripts"], "max_duration_seconds": 120},
        )
        with (
            mock.patch.object(adapter, "_acquire_remote_lease") as acquire,
            mock.patch.object(adapter, "execute_ssh_session") as ssh_exec,
        ):
            with self.assertRaisesRegex(common.FleetError, "allowed_write_paths"):
                adapter.dispatch_run(
                    handoff=h,
                    adapter="ssh-session",
                    owner_task="opl-fail-1",
                    argv=["true"],
                    state_root=self.state_root,
                )
            acquire.assert_not_called()
            ssh_exec.assert_not_called()

    def test_ssh_session_known_releases_lease_and_unknown_retains_lease(self) -> None:
        cb_dir = self.root / "callbacks"
        candidate = [{"node_id": "gpu-node", "lease": None}]
        doc = {
            "schema": "codex_fleet_doctor.v1",
            "node_id": "gpu-node",
            "checked_at": fleet.utc_now().isoformat(),
            "admission_ready": True,
            "ready_for_dispatch": True,
            "receipt_state": "CURRENT",
            "control_current": True,
            "current_control_commit": TEST_CONTROL_COMMIT,
            "ssh": {"reachable": True},
            "tailscale": {"online": True},
            "admission": admission(fleet.utc_now()),
            "lease": None,
        }

        h1 = self._handoff(attempt_id="att-ssh-ok", objective_id="opl-ssh-ok")
        with (
            mock.patch.object(adapter, "controller_guard"),
            mock.patch.object(adapter, "dispatch_candidates", return_value=candidate),
            mock.patch.object(adapter, "doctor_result", return_value=doc),
            mock.patch.object(adapter, "assert_lease_admission"),
            mock.patch.object(adapter, "build_admission_receipt", return_value=admission(fleet.utc_now())),
            mock.patch.object(adapter, "control_commit", return_value=TEST_CONTROL_COMMIT),
            mock.patch.object(adapter, "node_registry", return_value={"nodes": {"gpu-node": {"roles": ["worker"]}}}),
            mock.patch.object(adapter, "verify_lease_record", return_value={"ok": True}),
            mock.patch.object(adapter, "execute_ssh_session", return_value={"known": True, "result": {"exit_code": 0, "timed_out": False}}),
        ):
            ok = adapter.dispatch_run(
                handoff=h1,
                adapter="ssh-session",
                owner_task="opl-ssh-ok",
                argv=["echo", "ok"],
                callback_state_dir=cb_dir,
                state_root=self.state_root,
            )
        self.assertEqual(ok["status"], "completed")
        self.assertTrue(ok["lease_released"])
        self.assertEqual(lease_mod.read_lease_store(state_root=self.state_root)["leases"], {})

        h2 = self._handoff(attempt_id="att-ssh-unk", objective_id="opl-ssh-unk")
        with (
            mock.patch.object(adapter, "controller_guard"),
            mock.patch.object(adapter, "dispatch_candidates", return_value=candidate),
            mock.patch.object(adapter, "doctor_result", return_value=doc),
            mock.patch.object(adapter, "assert_lease_admission"),
            mock.patch.object(adapter, "build_admission_receipt", return_value=admission(fleet.utc_now())),
            mock.patch.object(adapter, "control_commit", return_value=TEST_CONTROL_COMMIT),
            mock.patch.object(adapter, "node_registry", return_value={"nodes": {"gpu-node": {"roles": ["worker"]}}}),
            mock.patch.object(adapter, "verify_lease_record", return_value={"ok": True}),
            mock.patch.object(adapter, "execute_ssh_session", return_value={"known": False, "error": "ssh timeout"}),
        ):
            unk = adapter.dispatch_run(
                handoff=h2,
                adapter="ssh-session",
                owner_task="opl-ssh-unk",
                argv=["echo", "ok"],
                callback_state_dir=cb_dir,
                state_root=self.state_root,
            )
        self.assertEqual(unk["status"], "unknown")
        self.assertTrue(unk["lease_retained"])
        self.assertIn("gpu-node", lease_mod.read_lease_store(state_root=self.state_root)["leases"])

        # Explicit dispatch complete closes remote/async attempt & releases retained lease
        result_ok = {
            "schema": "opl_worker_result.v1",
            "binding": execution.handoff_binding(h2),
            "outcome": "completed",
            "artifact_refs": ["git:repo@fff"],
            "checkpoint_refs": [],
            "remaining": [],
            "next_action": "Close",
        }
        closed = adapter.dispatch_complete(
            handoff=h2,
            result=result_ok,
            attempt_id="att-ssh-unk",
            dispatch_id=unk["dispatch_id"],
            callback_state_dir=cb_dir,
            state_root=self.state_root,
        )
        self.assertTrue(closed["lease_released"])
        self.assertEqual(lease_mod.read_lease_store(state_root=self.state_root)["leases"], {})

    def test_group_dispatch_fan_out_backpressure_and_fan_in_status(self) -> None:
        h1 = self._handoff(attempt_id="att-g1", objective_id="opl-g1", write_set=["src/a.py"])
        h2 = self._handoff(attempt_id="att-g2", objective_id="opl-g2", write_set=["src/a.py"])
        h3 = self._handoff(attempt_id="att-g3", objective_id="opl-g3", write_set=["src/c.py"])
        spec = {
            "group_id": "grp-1",
            "parent_objective_id": "epic-1",
            "slices": [
                {"handoff": h1, "adapter": "local-codex", "mode": "envelope"},
                {"handoff": h2, "adapter": "local-codex", "mode": "envelope"},
                {"handoff": h3, "adapter": "local-codex", "mode": "envelope"},
            ],
        }
        receipt = adapter.dispatch_group_run(spec, max_concurrent=2, state_root=self.state_root)
        self.assertEqual(len(receipt["integration_overlaps"]), 1)
        self.assertEqual(receipt["fan_in_summary"]["awaiting_completion"], 2)
        self.assertEqual(receipt["fan_in_summary"]["queued_backpressure"], 1)
        self.assertFalse(receipt["fan_in_summary"]["all_terminal"])

        # Complete the two admitted attempts -> status reflects updated attempt states
        for h in (h1, h2):
            adapter.dispatch_complete(
                handoff=h,
                result={
                    "schema": "opl_worker_result.v1",
                    "binding": execution.handoff_binding(h),
                    "outcome": "completed",
                    "artifact_refs": ["git:repo@111"],
                    "checkpoint_refs": [],
                    "remaining": [],
                    "next_action": "Integrate",
                },
                state_root=self.state_root,
            )
        live = adapter.dispatch_group_status("grp-1", state_root=self.state_root)
        self.assertEqual(live["fan_in_summary"]["completed"], 2)
        self.assertEqual(live["fan_in_summary"]["awaiting_completion"], 0)
        self.assertEqual(live["fan_in_summary"]["queued_backpressure"], 1)


if __name__ == "__main__":
    unittest.main()
