from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import fleet
from fleet import fleet_adapter as adapter
from fleet import fleet_attempts as attempts
from fleet import fleet_common as common
from fleet import fleet_lease as lease_mod
from scripts import opl_antigravity_bridge as agy_bridge
from scripts import opl_events as events


ROOT = Path(__file__).resolve().parents[1]


class OplAntigravityBridgeTests(unittest.TestCase):
    def _mock_agy(self, root: Path, *, mode: str, variant: str = "ok") -> Path:
        script = root / f"agy-{mode}-{variant}"
        if mode == "control":
            receipt = {
                "schema": "opl_control_turn_receipt.v1",
                "root_objective_id": "epic-1",
                "status": "dispatched",
                "actions_taken": ["dispatched s1 via antigravity"],
                "dispatched_attempts": ["att-s1"],
                "needs_human_action": False,
                "summary": "Dispatched slice",
                "next_step": "Await worker callback",
            }
            if variant == "empty":
                out_expr = "''"
            elif variant == "error_status":
                out_expr = "json.dumps({'status': 'ERROR', 'structured_output': None})"
            else:
                out_expr = f"json.dumps({{'status': 'SUCCESS', 'duration_seconds': 2.5, 'usage': {{'total_tokens': 321}}, 'structured_output': {repr(receipt)}}})"
            body = (
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "Path(os.environ['MOCK_AGY_LOG']).write_text(json.dumps({'args': args, 'cwd': os.getcwd()}), encoding='utf-8')\n"
                f"print({out_expr})\n"
            )
        else:
            body = (
                "#!/usr/bin/env python3\n"
                "import hashlib, json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "Path(os.environ['MOCK_AGY_LOG']).write_text(json.dumps({'args': args, 'cwd': os.getcwd()}), encoding='utf-8')\n"
                "h = json.loads(Path(os.environ['MOCK_HANDOFF_FILE']).read_text(encoding='utf-8'))\n"
                "raw = json.dumps(h, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')\n"
                "binding = {'attempt_id': h['attempt_id'], 'objective_id': h['objective_id'], 'owner_id': h['owner_id'], 'handoff_sha256': hashlib.sha256(raw).hexdigest()}\n"
                + ("binding['attempt_id'] = 'wrong-attempt'\n" if variant == "bad_binding" else "")
                + ("Path('slice_output.txt').write_text('dirty worktree artifact\\n', encoding='utf-8')\n" if variant == "dirty_wt" else "")
                + "res = {'schema':'opl_worker_result.v1','binding':binding,'outcome':'completed','artifact_refs':['git:repo@abc'],'checkpoint_refs':[],'remaining':[],'next_action':'Accept slice','budget_usage':None}\n"
                + "print(json.dumps({'status': 'SUCCESS', 'duration_seconds': 4.2, 'usage': {'total_tokens': 450}, 'structured_output': res}))\n"
            )
        script.write_text(body, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        return script

    def test_parse_agy_json_envelope_and_budget_backfill(self) -> None:
        raw = json.dumps(
            {
                "conversation_id": "conv-1",
                "status": "SUCCESS",
                "duration_seconds": 3.75,
                "usage": {"total_tokens": 512},
                "structured_output": {"schema": "opl_worker_result.v1", "outcome": "completed"},
            }
        )
        structured, telemetry = agy_bridge.parse_agy_json_envelope(raw)
        self.assertEqual(structured["outcome"], "completed")
        self.assertEqual(telemetry, {"elapsed_seconds": 3.75, "tokens_used": 512})

        merged = agy_bridge.merge_runtime_budget({"budget_usage": {"tokens_used": 999}}, telemetry)
        self.assertEqual(merged["budget_usage"]["tokens_used"], 999)
        self.assertEqual(merged["budget_usage"]["elapsed_seconds"], 3.75)

        with self.assertRaisesRegex(agy_bridge.BridgeError, "non-SUCCESS"):
            agy_bridge.parse_agy_json_envelope(json.dumps({"status": "FAILED", "structured_output": {}}))
        with self.assertRaisesRegex(agy_bridge.BridgeError, "missing structured_output"):
            agy_bridge.parse_agy_json_envelope(json.dumps({"status": "SUCCESS"}))

    def test_resolve_agy_mode_and_safety_flags(self) -> None:
        handoff_ro = {
            "schema": "opl_worker_handoff.v1",
            "attempt_id": "att-ro",
            "objective_id": "opl-ro",
            "owner_id": "agy:conv-ro",
            "scope": "Read-only audit",
            "input_refs": [],
            "checkpoint_refs": [],
            "expected_result": "Audit summary",
            "envelope": {"allowed_write_paths": [], "allow_destructive": False},
        }
        self.assertEqual(agy_bridge.resolve_agy_mode(handoff_ro), ("read-only", "plan"))
        with self.assertRaisesRegex(agy_bridge.BridgeError, "allow_destructive=false"):
            agy_bridge.resolve_agy_mode(handoff_ro, explicit_mode="auto")
        with self.assertRaisesRegex(agy_bridge.BridgeError, "allow_destructive=false"):
            agy_bridge.resolve_agy_mode(handoff_ro, explicit_sandbox="danger-full-access")
        with self.assertRaisesRegex(agy_bridge.BridgeError, "read-only sandbox"):
            agy_bridge.resolve_agy_mode(handoff_ro, explicit_mode="accept-edits")

        dry = agy_bridge.run_worker_slice(
            {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-dry",
                "objective_id": "opl-dry",
                "owner_id": "agy:conv-dry",
                "scope": "Edit file",
                "input_refs": [],
                "checkpoint_refs": [],
                "expected_result": "Updated file",
                "write_set": ["scripts/x.py"],
            },
            agy_bin="/usr/bin/agy",
            model="gemini-3.8-flash-low",
            effort="medium",
            dry_run=True,
        )
        self.assertEqual(dry["schema"], "opl_antigravity_bridge_dry_run.v1")
        self.assertEqual(dry["agy_mode"], "accept-edits")
        self.assertIn("--sandbox", dry["argv"])
        self.assertIn("accept-edits", dry["argv"])
        self.assertNotIn("--dangerously-skip-permissions", dry["argv"])
        self.assertNotIn("--disable-slash-commands", dry["argv"])
        self.assertTrue(any(arg.startswith("--print=") for arg in dry["argv"]))

    def test_control_mode_noop_short_circuit_and_agy_exec(self) -> None:
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
        with mock.patch.object(agy_bridge, "_run_agy_exec") as runner:
            noop_res = agy_bridge.run_control_turn(noop_plan)
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
            log_file = root / "agy.log"
            mock_agy = self._mock_agy(root, mode="control")
            with mock.patch.dict(os.environ, {"MOCK_AGY_LOG": str(log_file)}):
                receipt = agy_bridge.run_control_turn(
                    active_plan,
                    instance_root=root,
                    cwd=root,
                    agy_bin=str(mock_agy),
                    model="gemini-4-neon-high",
                    effort="high",
                )
            self.assertEqual(receipt["status"], "dispatched")
            recorded = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertIn("--json-schema", recorded["args"])
            self.assertIn("--sandbox", recorded["args"])
            self.assertIn("accept-edits", recorded["args"])
            self.assertNotIn("--dangerously-skip-permissions", recorded["args"])
            self.assertNotIn("--disable-slash-commands", recorded["args"])

            bad_agy = self._mock_agy(root, mode="control", variant="error_status")
            with mock.patch.dict(os.environ, {"MOCK_AGY_LOG": str(log_file)}):
                with self.assertRaisesRegex(agy_bridge.BridgeError, "non-SUCCESS"):
                    agy_bridge.run_control_turn(active_plan, cwd=root, agy_bin=str(bad_agy))

    def test_worker_mode_worktree_isolation_and_end_to_end_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True, capture_output=True)
            (repo / "README.md").write_text("init\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

            state_root = root / "state"
            cb_dir = root / "callbacks"
            log_file = root / "worker.log"
            handoff_file = root / "handoff.json"
            handoff_rw = {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-agy-rw-1",
                "objective_id": "opl-agy-1",
                "owner_id": "antigravity:conv-1",
                "scope": "Edit module",
                "input_refs": [],
                "checkpoint_refs": [],
                "expected_result": "Updated file",
                "write_set": ["scripts/x.py"],
                "envelope": {"allowed_write_paths": ["scripts"], "max_duration_seconds": 300},
            }
            handoff_file.write_text(json.dumps(handoff_rw), encoding="utf-8")

            bad_agy = self._mock_agy(root, mode="worker", variant="bad_binding")
            with mock.patch.dict(os.environ, {"MOCK_AGY_LOG": str(log_file), "MOCK_HANDOFF_FILE": str(handoff_file)}):
                with self.assertRaisesRegex(agy_bridge.BridgeError, "match"):
                    agy_bridge.run_worker_slice(handoff_rw, cwd=repo, agy_bin=str(bad_agy), use_worktree=True)

            # Clean worktree is auto-cleaned after execution
            ok_agy = self._mock_agy(root, mode="worker", variant="ok")
            with (
                mock.patch.object(common, "STATE_ROOT", state_root),
                mock.patch.object(lease_mod, "STATE_ROOT", state_root),
                mock.patch.dict(os.environ, {"MOCK_AGY_LOG": str(log_file), "MOCK_HANDOFF_FILE": str(handoff_file)}),
            ):
                res = adapter.dispatch_run(
                    handoff=handoff_rw,
                    requirements={"schema": "opl_execution_requirements.v1", "ttl_seconds": 300},
                    adapter="local-antigravity",
                    owner_task="opl-agy-1",
                    workspace_root=repo,
                    callback_state_dir=cb_dir,
                    use_antigravity_bridge=True,
                    agy_bin=str(ok_agy),
                    effort="high",
                    use_worktree=True,
                    state_root=state_root,
                )
            self.assertEqual(res["status"], "completed")
            self.assertEqual(res["worker_result"]["budget_usage"]["tokens_used"], 450)
            self.assertEqual(res["worker_result"]["budget_usage"]["elapsed_seconds"], 4.2)
            self.assertEqual(attempts.get_attempt("att-agy-rw-1", state_root=state_root)["state"], "completed")
            cb_events = events.list_events(cb_dir, objective_id="opl-agy-1")
            self.assertEqual(len(cb_events), 1)
            self.assertEqual(cb_events[0]["event_type"], "worker_callback")
            recorded = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertNotEqual(Path(recorded["cwd"]).resolve(), repo.resolve())
            wt_list = subprocess.run(["git", "worktree", "list"], cwd=repo, check=True, capture_output=True, text=True).stdout
            self.assertNotIn("opl-agy-wt-", wt_list)

            # Dirty worktree must be preserved so worker edits are never discarded
            dirty_agy = self._mock_agy(root, mode="worker", variant="dirty_wt")
            handoff_dirty = {**handoff_rw, "attempt_id": "att-agy-dirty"}
            handoff_file.write_text(json.dumps(handoff_dirty), encoding="utf-8")
            with mock.patch.dict(os.environ, {"MOCK_AGY_LOG": str(log_file), "MOCK_HANDOFF_FILE": str(handoff_file)}):
                agy_bridge.run_worker_slice(handoff_dirty, cwd=repo, agy_bin=str(dirty_agy), use_worktree=True)
            dirty_recorded = json.loads(log_file.read_text(encoding="utf-8"))
            preserved_wt = Path(dirty_recorded["cwd"])
            try:
                self.assertTrue((preserved_wt / "slice_output.txt").is_file())
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(preserved_wt)], cwd=repo, check=False)

    def test_mixed_group_dispatch_codex_and_antigravity_fan_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_root = root / "state"
            cb_dir = root / "callbacks"

            worker_script = (
                "import json, os, hashlib; "
                "h = json.load(open(os.environ['OPL_HANDOFF_PATH'])); "
                "raw = json.dumps(h, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode(); "
                "b = {'attempt_id': h['attempt_id'], 'objective_id': h['objective_id'], 'owner_id': h['owner_id'], 'handoff_sha256': hashlib.sha256(raw).hexdigest()}; "
                "print(json.dumps({'schema':'opl_worker_result.v1','binding':b,'outcome':'completed','artifact_refs':['git:repo@123'],'checkpoint_refs':[],'remaining':[],'next_action':'Accept'}))"
            )
            h_codex = {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-mix-codex",
                "objective_id": "opl-mix-codex",
                "owner_id": "codex:t1",
                "scope": "Backend slice",
                "input_refs": [],
                "checkpoint_refs": [],
                "expected_result": "Backend verified",
                "write_set": ["scripts/backend.py"],
            }
            h_agy = {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-mix-agy",
                "objective_id": "opl-mix-agy",
                "owner_id": "antigravity:c1",
                "scope": "Frontend slice",
                "input_refs": [],
                "checkpoint_refs": [],
                "expected_result": "Frontend verified",
                "write_set": ["decision-dashboard/app.js"],
            }
            spec = {
                "group_id": "grp-mixed",
                "parent_objective_id": "epic-mix",
                "slices": [
                    {
                        "handoff": h_codex,
                        "adapter": "local-codex",
                        "executor_cmd": [sys.executable, "-c", worker_script],
                    },
                    {
                        "handoff": h_agy,
                        "adapter": "local-antigravity",
                        "executor_cmd": [sys.executable, "-c", worker_script],
                    },
                ],
            }
            with (
                mock.patch.object(common, "STATE_ROOT", state_root),
                mock.patch.object(lease_mod, "STATE_ROOT", state_root),
            ):
                receipt = adapter.dispatch_group_run(
                    spec,
                    max_concurrent=2,
                    max_local_concurrent=2,
                    callback_state_dir=cb_dir,
                    state_root=state_root,
                )
            self.assertEqual(receipt["fan_in_summary"]["completed"], 2)
            self.assertTrue(receipt["fan_in_summary"]["ready_for_integration"])
            adapters = {item["objective_id"]: item["adapter"] for item in receipt["dispatched"]}
            self.assertEqual(adapters, {"opl-mix-codex": "local-codex", "opl-mix-agy": "local-antigravity"})


if __name__ == "__main__":
    unittest.main()
