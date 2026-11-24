from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import fleet
from fleet import fleet_adapter as adapter
from fleet import fleet_attempts as attempts
from fleet import fleet_common as common
from fleet import fleet_lease as lease_mod
from scripts import opl_codex_bridge as bridge
from scripts import opl_events as events
from scripts import opl_execution as execution


ROOT = Path(__file__).resolve().parents[1]


def _assert_openai_strict_schema(testcase: unittest.TestCase, node: dict) -> None:
    if node.get("type") == "object" or "properties" in node:
        testcase.assertFalse(node.get("additionalProperties", True))
        props = set(node.get("properties", {}))
        testcase.assertEqual(set(node.get("required", [])), props)
        for forbidden in ("if", "then", "else", "allOf"):
            testcase.assertNotIn(forbidden, node)
        for prop_schema in node.get("properties", {}).values():
            if isinstance(prop_schema, dict):
                _assert_openai_strict_schema(testcase, prop_schema)


class OplCodexBridgeTests(unittest.TestCase):
    def _mock_codex(self, root: Path, *, mode: str, fail_empty: bool = False) -> Path:
        script = root / f"codex-{mode}{'-bad' if fail_empty else ''}"
        if mode == "control":
            body = (
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "out = Path(args[args.index('-o') + 1])\n"
                "Path(os.environ['MOCK_CODEX_LOG']).write_text(json.dumps({'args': args, 'stdin': sys.stdin.read()}), encoding='utf-8')\n"
                + ("out.write_text('', encoding='utf-8')\n" if fail_empty else
                   "out.write_text(json.dumps({'schema':'opl_control_turn_receipt.v1','root_objective_id':'epic-1','status':'dispatched','actions_taken':['dispatched s1'],'dispatched_attempts':['att-s1'],'needs_human_action':False,'summary':'Dispatched ready slice','next_step':'Await worker callback'}), encoding='utf-8')\n")
            )
        else:
            body = (
                "#!/usr/bin/env python3\n"
                "import hashlib, json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "out = Path(args[args.index('-o') + 1])\n"
                "Path(os.environ['MOCK_CODEX_LOG']).write_text(json.dumps({'args': args, 'stdin': sys.stdin.read()}), encoding='utf-8')\n"
                "h = json.loads(Path(os.environ['MOCK_HANDOFF_FILE']).read_text(encoding='utf-8'))\n"
                "raw = json.dumps(h, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')\n"
                "binding = {'attempt_id': h['attempt_id'], 'objective_id': h['objective_id'], 'owner_id': h['owner_id'], 'handoff_sha256': hashlib.sha256(raw).hexdigest()}\n"
                + ("binding['attempt_id'] = 'wrong-attempt'\n" if fail_empty else "")
                + "out.write_text(json.dumps({'schema':'opl_worker_result.v1','binding':binding,'outcome':'completed','artifact_refs':['git:repo@abc'],'checkpoint_refs':[],'remaining':[],'next_action':'Accept slice','budget_usage':None}), encoding='utf-8')\n"
            )
        script.write_text(body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return script

    def test_schemas_are_openai_strict_output_compatible(self) -> None:
        ctrl_schema = json.loads((ROOT / "contracts/control-turn-receipt.schema.json").read_text(encoding="utf-8"))
        _assert_openai_strict_schema(self, ctrl_schema)
        worker_schema = bridge.build_worker_output_schema()
        _assert_openai_strict_schema(self, worker_schema)

    def test_control_mode_noop_short_circuit_and_codex_exec(self) -> None:
        noop_plan = {
            "schema": "opl_control_turn_plan.v1",
            "root_objective_id": "epic-1",
            "trigger_event_ids": [],
            "graph_summary": {},
            "callbacks_processed": [],
            "fan_out_batch": [],
            "integration_queue": [],
            "needs_repair": [],
            "blocked_or_waiting": [],
            "needs_agent_reasoning": False,
            "recommended_actions": [],
            "validation_errors": [],
        }
        with mock.patch.object(bridge, "_run_codex_exec") as runner:
            noop_res = bridge.run_control_turn(noop_plan)
            runner.assert_not_called()
        self.assertEqual(noop_res["status"], "noop")

        active_plan = {
            **noop_plan,
            "trigger_event_ids": ["ev-1"],
            "needs_agent_reasoning": True,
            "recommended_actions": [{"action": "dispatch_slice", "objective_id": "s1"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_file = root / "codex.log"
            mock_codex = self._mock_codex(root, mode="control")
            with mock.patch.dict(os.environ, {"MOCK_CODEX_LOG": str(log_file)}):
                receipt = bridge.run_control_turn(
                    active_plan,
                    instance_root=root,
                    cwd=root,
                    codex_bin=str(mock_codex),
                    model="gpt-5",
                )
            self.assertEqual(receipt["status"], "dispatched")
            recorded = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertIn("--ephemeral", recorded["args"])
            self.assertIn("--output-schema", recorded["args"])
            self.assertIn("workspace-write", recorded["args"])
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", recorded["args"])

            # Empty output fails closed
            bad_codex = self._mock_codex(root, mode="control", fail_empty=True)
            with mock.patch.dict(os.environ, {"MOCK_CODEX_LOG": str(log_file)}):
                with self.assertRaisesRegex(bridge.BridgeError, "empty output"):
                    bridge.run_control_turn(active_plan, cwd=root, codex_bin=str(bad_codex))

    def test_worker_mode_sandbox_selection_and_end_to_end_adapter_dispatch(self) -> None:
        handoff_ro = {
            "schema": "opl_worker_handoff.v1",
            "attempt_id": "att-ro",
            "objective_id": "opl-ro",
            "owner_id": "thread-ro",
            "scope": "Read-only audit",
            "input_refs": [],
            "checkpoint_refs": [],
            "expected_result": "Audit summary",
            "envelope": {"allowed_write_paths": [], "allow_destructive": False},
        }
        self.assertEqual(bridge.resolve_sandbox_mode(handoff_ro), "read-only")
        with self.assertRaisesRegex(bridge.BridgeError, "allow_destructive=false"):
            bridge.resolve_sandbox_mode(handoff_ro, explicit_sandbox="danger-full-access")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_root = root / "state"
            cb_dir = root / "callbacks"
            log_file = root / "worker.log"
            handoff_file = root / "handoff.json"
            handoff_rw = {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-rw-1",
                "objective_id": "opl-rw-1",
                "owner_id": "thread-rw",
                "scope": "Edit module",
                "input_refs": [],
                "checkpoint_refs": [],
                "expected_result": "Updated file",
                "write_set": ["scripts/x.py"],
                "envelope": {"allowed_write_paths": ["scripts"], "max_duration_seconds": 300},
            }
            handoff_file.write_text(json.dumps(handoff_rw), encoding="utf-8")
            mock_codex = self._mock_codex(root, mode="worker")

            # Mismatched binding fails closed
            bad_codex = self._mock_codex(root, mode="worker", fail_empty=True)
            with mock.patch.dict(os.environ, {"MOCK_CODEX_LOG": str(log_file), "MOCK_HANDOFF_FILE": str(handoff_file)}):
                with self.assertRaisesRegex(bridge.BridgeError, "match"):
                    bridge.run_worker_slice(handoff_rw, cwd=root, codex_bin=str(bad_codex), use_worktree=True)

            # End-to-end fleet_adapter.dispatch_run(..., use_codex_bridge=True)
            with (
                mock.patch.object(common, "STATE_ROOT", state_root),
                mock.patch.object(lease_mod, "STATE_ROOT", state_root),
                mock.patch.dict(os.environ, {"MOCK_CODEX_LOG": str(log_file), "MOCK_HANDOFF_FILE": str(handoff_file)}),
            ):
                res = adapter.dispatch_run(
                    handoff=handoff_rw,
                    requirements={"schema": "opl_execution_requirements.v1", "ttl_seconds": 300},
                    adapter="local-codex",
                    owner_task="opl-rw-1",
                    workspace_root=root,
                    callback_state_dir=cb_dir,
                    use_codex_bridge=True,
                    codex_bin=str(mock_codex),
                    use_worktree=True,
                    state_root=state_root,
                )
            self.assertEqual(res["status"], "completed")
            self.assertEqual(attempts.get_attempt("att-rw-1", state_root=state_root)["state"], "completed")
            cb_events = events.list_events(cb_dir, objective_id="opl-rw-1")
            self.assertEqual(len(cb_events), 1)
            self.assertEqual(cb_events[0]["event_type"], "worker_callback")
            recorded = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertIn("--worktree", recorded["args"])


if __name__ == "__main__":
    unittest.main()
