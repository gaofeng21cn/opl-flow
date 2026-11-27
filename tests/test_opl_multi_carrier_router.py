from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import opl_dsh_bridge
from scripts import opl_events
from scripts import opl_execution
from scripts import opl_ledger
from scripts import opl_session_discovery
from scripts import opl_workflow
from scripts.fleet import fleet_adapter


def _write_fake_dsh_tree(
    tmp: Path,
    *,
    now_ts: float,
    bound_dsh_id: str = "hs-bound-1",
    bound_codex_id: str = "thread-bound-1",
    ws_path: str = "/tmp/ws-alpha",
) -> tuple[Path, Path, Path, Path]:
    codex_home = tmp / "codex_home"
    gemini_home = tmp / "gemini_home"
    dsh_home = tmp / "dsh_home"

    # 1. Codex active bound session
    c_sess = codex_home / "sessions" / "2026" / "11" / "27"
    c_sess.mkdir(parents=True)
    rollout = c_sess / "rollout-2026-11-27T14-00-00-thread-bound-1.jsonl"
    rollout.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {
                    "id": bound_codex_id,
                    "cwd": ws_path,
                    "originator": "codex_cli_rs",
                    "model_provider": "openai",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    os.utime(rollout, (now_ts - 15, now_ts - 15))

    # 2. AntiGravity active unbound free chat
    agy_log = gemini_home / "antigravity" / "brain" / "agy-free-1" / ".system_generated" / "logs" / "transcript.jsonl"
    agy_log.parent.mkdir(parents=True)
    agy_log.write_text(
        json.dumps({"type": "turn", "status": "running", "prompt": "PRIVATE USER PROMPT"}) + "\n",
        encoding="utf-8",
    )
    os.utime(agy_log, (now_ts - 10, now_ts - 10))

    # 3. DSH catalog + harness session (with agy + gemini combination) + duplicate native dir + native-only dir
    cat_path = dsh_home / "profiles" / "desktop" / "execution-catalog.json"
    cat_path.parent.mkdir(parents=True)
    cat_path.write_text(
        json.dumps(
            {
                "harnesses": [
                    {"id": "agy", "name": "AntiGravity", "transport": "cli", "enabled": True},
                    {"id": "codex", "name": "Codex", "transport": "app-server", "enabled": True},
                ],
                "combinations": [
                    {
                        "id": "agy-gemini-pro",
                        "name": "AntiGravity · Gemini 3 Pro",
                        "harnessRef": "agy",
                        "enabled": True,
                    },
                    {"id": "disabled-combo", "name": "Disabled", "enabled": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    hs_dir = dsh_home / "profiles" / "desktop" / "harness-sessions"
    hs_dir.mkdir(parents=True)
    hs_file = hs_dir / f"{bound_dsh_id}.json"
    hs_file.write_text(
        json.dumps(
            {
                "id": bound_dsh_id,
                "harnessRef": "agy",
                "combination": "agy-gemini-pro",
                "modelRef": {"model": "gemini-3-pro"},
                "cwd": "/Users/private-secret/ws-alpha",
                "origin": "desktop",
                "turns": [{"prompt": "SECRET PROMPT NEVER PROJECT"}],
            }
        ),
        encoding="utf-8",
    )
    os.utime(hs_file, (now_ts - 5, now_ts - 5))

    # Same ID inside sessions/<slug>/session-<id> should deduplicate in favor of harness-sessions
    dup_native = dsh_home / "sessions" / "--Users-private-secret-ws-alpha--" / f"session-{bound_dsh_id}"
    dup_native.mkdir(parents=True)
    os.utime(dup_native, (now_ts - 4, now_ts - 4))

    # Native-only active DSH session occupying ws-alpha
    native_only = dsh_home / "sessions" / "--Users-private-secret-ws-alpha--" / "session-dsh-free-2"
    native_only.mkdir(parents=True)
    os.utime(native_only, (now_ts - 3, now_ts - 3))

    # Fake node binary + control.mjs for isolated DSH bridge tests
    fake_control = tmp / "control.mjs"
    fake_control.write_text("// mock dsh control script\n", encoding="utf-8")

    return codex_home, gemini_home, dsh_home, fake_control


class MultiCarrierRouterTests(unittest.TestCase):
    def test_multi_carrier_session_discovery_sanitization_and_dsh_dedup(self) -> None:
        now_ts = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            codex_home, gemini_home, dsh_home, _ = _write_fake_dsh_tree(Path(tmp), now_ts=now_ts)
            issues = [
                {
                    "id": "bd-codex-1",
                    "status": "in_progress",
                    "metadata": {"execution_carrier": "codex", "execution_thread": "codex:thread-bound-1"},
                },
                {
                    "id": "bd-dsh-1",
                    "status": "in_progress",
                    "metadata": {"execution_carrier": "dsh", "execution_thread": "dsh:hs-bound-1"},
                },
            ]
            discovery = opl_session_discovery.discover_local_sessions(
                codex_home=codex_home,
                gemini_home=gemini_home,
                dsh_home=dsh_home,
                issues=issues,
            )

        self.assertEqual(discovery["counts"]["total"], 4)
        self.assertEqual(discovery["counts"]["active"], 4)
        self.assertEqual(discovery["counts"]["bound"], 2)
        self.assertEqual(discovery["counts"]["by_carrier"], {"codex": 1, "antigravity": 1, "dsh": 2})

        dsh_entries = [item for item in discovery["sessions"] if item["carrier"] == "dsh"]
        # hs-bound-1 appears once (deduplicated against native session-hs-bound-1)
        bound_dsh = [item for item in dsh_entries if item["session_id"] == "hs-bound-1"]
        self.assertEqual(len(bound_dsh), 1)
        self.assertEqual(bound_dsh[0]["model_label"], "AntiGravity · Gemini 3 Pro")
        self.assertEqual(bound_dsh[0]["bound_bead_id"], "bd-dsh-1")

        # Sanitized projection excludes local paths, prompts, and raw session_id keys
        sanitized = opl_session_discovery.sanitize_sessions_for_projection(discovery)
        opl_execution.sanitize_check(sanitized, label="multi_carrier_sessions")
        dumped = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn("/Users/private-secret", dumped)
        self.assertNotIn("SECRET PROMPT", dumped)
        self.assertNotIn("PRIVATE USER PROMPT", dumped)
        self.assertNotIn("session_id", dumped)

        # Bound observations exclude unbound AntiGravity and unbound native DSH free chats
        bound_obs = opl_session_discovery.build_bound_observations(discovery)
        self.assertEqual([t["id"] for t in bound_obs["threads"]], ["thread-bound-1"])
        self.assertEqual(bound_obs["antigravity_conversations"], [])
        self.assertEqual([d["id"] for d in bound_obs["dsh_sessions"]], ["hs-bound-1"])

    def test_unbound_active_session_guards_workspace_without_waking_router(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ws-alpha"
            root.mkdir()
            ev_dir = Path(tmp) / "events"
            cursor = Path(tmp) / "cursor.json"

            fake_discovery = {
                "schema": opl_session_discovery.LOCAL_SESSIONS_SCHEMA,
                "observed_at": "2026-11-27T06:00:00Z",
                "counts": {"total": 2, "active": 2, "bound": 0, "by_carrier": {"codex": 1, "antigravity": 0, "dsh": 1}},
                "sessions": [
                    {
                        "session_id": "free-dsh-1",
                        "session_ref": "dsh:free-dsh-1",
                        "carrier": "dsh",
                        "surface": "dsh-harness",
                        "harness": "agy",
                        "model_label": "AntiGravity · Gemini 3 Pro",
                        "workspace_label": "ws-alpha",
                        "status": "active",
                        "updated_at": "2026-11-27T06:00:00Z",
                        "bound_bead_id": None,
                    },
                    {
                        "session_id": "free-codex-other",
                        "session_ref": "codex:free-other",
                        "carrier": "codex",
                        "surface": "codex",
                        "harness": "codex",
                        "model_label": "codex",
                        "workspace_label": "ws-beta",
                        "status": "active",
                        "updated_at": "2026-11-27T06:00:00Z",
                        "bound_bead_id": None,
                    },
                ],
                "active_workspace_occupants": [
                    {
                        "workspace_label": "ws-alpha",
                        "carrier": "dsh",
                        "harness": "agy",
                        "session_ref": "dsh:free-dsh-1",
                        "bound_bead_id": None,
                    },
                    {
                        "workspace_label": "ws-beta",
                        "carrier": "codex",
                        "harness": "codex",
                        "session_ref": "codex:free-other",
                        "bound_bead_id": None,
                    },
                ],
            }

            idle_snap = {"schema": "opl_flow_supervisor_snapshot.v1", "instance": str(root), "issues": [], "validation_errors": []}
            idle_tick = opl_events.router_tick(
                root,
                "bd",
                state_dir=ev_dir,
                cursor_path=cursor,
                snapshot=idle_snap,
                auto_discover_sessions=True,
                discovery_fn=lambda _snap: fake_discovery,
            )
            self.assertEqual(idle_tick["status"], "idle")
            self.assertFalse(idle_tick["wake_agent"])
            self.assertFalse(idle_tick["hook_invoked"])
            self.assertEqual(idle_tick["emitted_events"], 0)
            self.assertEqual(idle_tick["sessions"]["counts"]["total"], 2)

            # Ready slice on ws-alpha triggers worktree protection; ws-beta occupant is ignored
            ready_snap = {
                "schema": "opl_flow_supervisor_snapshot.v1",
                "instance": str(root),
                "issues": [
                    {
                        "id": "bd-ready-1",
                        "title": "Edit shared UI",
                        "status": "open",
                        "metadata": {
                            "classification": "managed_objective",
                            "execution_mode": "active",
                            "write_set": ["decision-dashboard/app.js"],
                            "next_action": "Polish detail panel",
                        },
                    }
                ],
                "validation_errors": [],
            }
            turn = opl_events.evaluate_control_turn(ready_snap, local_sessions=fake_discovery)
            self.assertEqual(len(turn["integration_queue"]), 1)
            guard = turn["integration_queue"][0]
            self.assertEqual(guard["integration_policy"], "worktree_required_active_local_session")
            self.assertEqual(guard["objectives"], ["bd-ready-1"])
            self.assertEqual(guard["active_session"]["session_ref"], "dsh:free-dsh-1")

    def test_unified_auto_router_dispatches_antigravity_and_codex_in_one_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "inst"
            root.mkdir()
            ev_dir = Path(tmp) / "events"
            cursor = Path(tmp) / "cursor.json"

            snap = {
                "schema": "opl_flow_supervisor_snapshot.v1",
                "instance": str(root),
                "issues": [
                    {
                        "id": "bd-agy",
                        "title": "AGY root objective",
                        "status": "open",
                        "metadata": {
                            "classification": "managed_objective",
                            "execution_mode": "active",
                            "execution_carrier": "antigravity",
                            "execution_thread": "antigravity:conv-1",
                            "next_action": "Run in AntiGravity",
                            "opl_execution_requirements": {"schema": "opl_execution_requirements.v1", "adapter": "local-antigravity"},
                        },
                    },
                    {
                        "id": "bd-codex",
                        "title": "Codex root objective",
                        "status": "open",
                        "metadata": {
                            "classification": "managed_objective",
                            "execution_mode": "active",
                            "execution_carrier": "codex",
                            "execution_thread": "codex:thread-1",
                            "next_action": "Run in Codex",
                            "opl_execution_requirements": {"schema": "opl_execution_requirements.v1", "adapter": "local-codex"},
                        },
                    },
                ],
                "validation_errors": [],
            }

            opl_events.emit_event(
                ev_dir,
                event_type="human_intake",
                objective_id="bd-agy",
                source="test:suite",
                idempotency_key="auto-agy-1",
                payload={"execution_carrier": "antigravity"},
            )
            opl_events.emit_event(
                ev_dir,
                event_type="human_intake",
                objective_id="bd-codex",
                source="test:suite",
                idempotency_key="auto-codex-1",
                payload={"execution_carrier": "codex"},
            )

            resolver = opl_events.build_auto_control_hook_resolver(
                instance_root=root,
                available_bridges=("codex", "antigravity"),
                dry_run=True,
            )
            invoked_cmds: list[list[str]] = []

            def fake_subproc(argv, **kwargs):
                invoked_cmds.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, '{"status":"noop"}', "")

            with mock.patch("scripts.opl_events.subprocess.run", side_effect=fake_subproc):
                tick = opl_events.router_tick(
                    root,
                    "bd",
                    state_dir=ev_dir,
                    cursor_path=cursor,
                    snapshot=snap,
                    control_hook_resolver=resolver,
                )

            self.assertEqual(tick["status"], "dispatched")
            self.assertTrue(tick["hook_invoked"])
            by_obj = {item["root_objective_id"]: item for item in tick["hook_results"]}
            self.assertEqual(by_obj["bd-agy"]["bridge"], "antigravity")
            self.assertEqual(by_obj["bd-codex"]["bridge"], "codex")
            self.assertTrue(any("opl_antigravity_bridge.py" in " ".join(cmd) for cmd in invoked_cmds))
            self.assertTrue(any("opl_codex_bridge.py" in " ".join(cmd) for cmd in invoked_cmds))

            # Fallback when only AntiGravity CLI is available
            chosen = opl_events.resolve_control_bridge_for_turn(
                snap,
                root_objective_id="bd-codex",
                available_bridges=("antigravity",),
            )
            self.assertEqual(chosen, "antigravity")

    def test_dsh_bridge_catalog_dry_run_and_node_wrapper_execution(self) -> None:
        now_ts = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _, _, dsh_home, fake_control = _write_fake_dsh_tree(tmp_path, now_ts=now_ts)
            probe = opl_dsh_bridge.probe_dsh_surface(
                dsh_control=str(fake_control),
                dsh_home=dsh_home,
                node_bin=sys.executable,
            )
            self.assertTrue(probe["available"])
            self.assertEqual(probe["harnesses"], ["agy", "codex"])
            self.assertEqual(probe["enabled_combinations"], 1)
            self.assertEqual(probe["combinations"][0]["id"], "agy-gemini-pro")

            handoff = {
                "schema": "opl_worker_handoff.v1",
                "attempt_id": "att-dsh-1",
                "objective_id": "bd-dsh-1",
                "owner_id": "worker:bd-dsh-1",
                "scope": "Execute DSH multi-model check",
                "input_refs": ["bead:bd-dsh-1"],
                "checkpoint_refs": [],
                "expected_result": "Completed verification",
                "write_set": ["src/ui.js"],
            }

            dry = opl_dsh_bridge.run_worker_slice(
                handoff,
                cwd=tmp_path,
                dsh_control=str(fake_control),
                combination="agy-gemini-pro",
                model="gemini-3-pro",
                node_bin="/usr/bin/node",
                dry_run=True,
            )
            self.assertEqual(dry["schema"], "opl_dsh_bridge_dry_run.v1")
            self.assertEqual(dry["subcommand"], "delegate")
            self.assertIn("--combination", dry["argv"])
            self.assertIn("agy-gemini-pro", dry["argv"])

            dry_dispatch = opl_dsh_bridge.run_worker_slice(
                handoff,
                cwd=tmp_path,
                dsh_control=str(fake_control),
                node_bin="/usr/bin/node",
                dry_run=True,
            )
            self.assertEqual(dry_dispatch["subcommand"], "dispatch")

            # Executable python shim acting as node_bin to verify temp prompt file handoff & JSON parsing
            shim = tmp_path / "fake_node.py"
            shim.write_text(
                (
                    "#!/usr/bin/env python3\n"
                    "import json, pathlib, sys\n"
                    "argv = sys.argv[1:]\n"
                    "pf = pathlib.Path(argv[argv.index('--prompt-file') + 1])\n"
                    "assert 'bd-dsh-1' in pf.read_text(encoding='utf-8')\n"
                    "print(json.dumps({'status': 'ok', 'task': 'bd-dsh-1', 'sessionId': 'dsh-s1', 'combination': 'agy-gemini-pro', 'exitCode': 0, 'outputText': 'Done via DSH'}))\n"
                ),
                encoding="utf-8",
            )
            shim.chmod(0o755)
            ok_res = opl_dsh_bridge.run_worker_slice(
                handoff,
                cwd=tmp_path,
                dsh_control=str(fake_control),
                combination="agy-gemini-pro",
                node_bin=str(shim),
            )
            self.assertEqual(ok_res["schema"], "opl_worker_result.v1")
            self.assertEqual(ok_res["outcome"], "checkpoint")
            self.assertIn("dsh:session:dsh-s1", ok_res["checkpoint_refs"])

            fail_shim = tmp_path / "fail_node.py"
            fail_shim.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(2)\n", encoding="utf-8")
            fail_shim.chmod(0o755)
            with self.assertRaises(opl_dsh_bridge.BridgeError):
                opl_dsh_bridge.run_worker_slice(
                    handoff,
                    cwd=tmp_path,
                    dsh_control=str(fake_control),
                    node_bin=str(fail_shim),
                )

    def test_fleet_local_dsh_and_three_way_mixed_group_fanout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "repo"
            ws.mkdir()
            (ws / "a.txt").write_text("a\n", encoding="utf-8")
            (ws / "b.txt").write_text("b\n", encoding="utf-8")
            (ws / "c.txt").write_text("c\n", encoding="utf-8")
            state_root = Path(tmp) / "fleet-state"
            cb_dir = Path(tmp) / "callbacks"

            def _mk_handoff(idx: int, path: str) -> dict:
                return {
                    "schema": "opl_worker_handoff.v1",
                    "attempt_id": f"att-mix-{idx}",
                    "objective_id": f"obj-mix-{idx}",
                    "owner_id": f"worker:mix-{idx}",
                    "scope": f"Work slice {idx}",
                    "input_refs": [f"bead:obj-mix-{idx}"],
                    "checkpoint_refs": [],
                    "expected_result": "Completed slice",
                    "write_set": [path],
                }

            flow_path = str(opl_workflow.flow_root())
            worker_script = (
                f"import json, os, sys; sys.path.insert(0, {flow_path!r}); "
                "from scripts import opl_execution; "
                "h=json.loads(open(os.environ['OPL_HANDOFF_PATH'], encoding='utf-8').read()); "
                "binding=opl_execution.handoff_binding(h); "
                "print(json.dumps({'schema':'opl_worker_result.v1','binding':binding,"
                "'outcome':'completed','artifact_refs':['artifact:ok'],'checkpoint_refs':[],'remaining':[],'next_action':'Accept'}))"
            )
            group_spec = {
                "group_id": "grp-mix-3way",
                "parent_objective_id": "epic-mix",
                "slices": [
                    {
                        "handoff": _mk_handoff(1, "a.txt"),
                        "adapter": "local-codex",
                        "executor_cmd": [sys.executable, "-c", worker_script],
                    },
                    {
                        "handoff": _mk_handoff(2, "b.txt"),
                        "adapter": "local-antigravity",
                        "executor_cmd": [sys.executable, "-c", worker_script],
                    },
                    {
                        "handoff": _mk_handoff(3, "c.txt"),
                        "adapter": "local-dsh",
                        "use_dsh_bridge": True,
                        "dsh_combination": "agy-gemini-pro",
                        "executor_cmd": [sys.executable, "-c", worker_script],
                    },
                ],
            }
            receipt = fleet_adapter.dispatch_group_run(
                group_spec,
                workspace_root=ws,
                callback_state_dir=cb_dir,
                state_root=state_root,
            )
            self.assertEqual([item["adapter"] for item in receipt["dispatched"]], ["local-codex", "local-antigravity", "local-dsh"])
            self.assertTrue(receipt["fan_in_summary"]["all_terminal"])
            self.assertTrue(receipt["fan_in_summary"]["ready_for_integration"])

            cmd = fleet_adapter._local_bridge_command(
                "local-dsh",
                use_codex_bridge=False,
                use_antigravity_bridge=False,
                use_dsh_bridge=True,
                codex_bin=None,
                agy_bin=None,
                dsh_control="/tmp/control.mjs",
                dsh_combination="agy-gemini-pro",
                model="gemini-3-pro",
                effort=None,
                sandbox="workspace-write",
                use_worktree=False,
                workspace_root=ws,
            )
            self.assertIsNotNone(cmd)
            assert cmd is not None
            self.assertIn("opl_dsh_bridge.py", cmd[1])
            self.assertIn("--combination", cmd)

    def test_cli_sessions_and_send_with_dsh_session_binding(self) -> None:
        now_ts = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            codex_home, gemini_home, dsh_home, _ = _write_fake_dsh_tree(tmp_path, now_ts=now_ts)
            instance = tmp_path / "inst"
            instance.mkdir()
            (instance / ".beads").mkdir()
            db_file = instance / ".beads/fake.json"
            db_file.write_text(json.dumps({"seq": 0, "issues": []}), encoding="utf-8")
            bd = opl_workflow.flow_root() / "tests" / "test_opl_ledger.py"  # unused dummy when mocked
            _ = bd
            ev_dir = tmp_path / "events"

            # sessions --json cleanly reads mocked local homes without private path leaks
            with mock.patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(codex_home),
                    "GEMINI_HOME": str(gemini_home),
                    "DSH_HOME": str(dsh_home),
                },
            ):
                buf = __import__("io").StringIO()
                with mock.patch("sys.stdout", buf), mock.patch.object(opl_workflow, "instance_root", return_value=None):
                    rc = opl_workflow.main(["sessions", "--json"])
                self.assertEqual(rc, 0)
                sess_payload = json.loads(buf.getvalue())
                self.assertEqual(sess_payload["counts"]["total"], 4)
                self.assertTrue(sess_payload["dsh_catalog"]["present"])
                self.assertEqual(
                    [c["id"] for c in sess_payload["dsh_catalog"]["combinations"] if c.get("enabled")],
                    ["agy-gemini-pro"],
                )
                self.assertNotIn("/Users/private-secret", buf.getvalue())

            # send --executor dsh --session dsh:hs-bound-1 stores execution_thread + carrier + adapter
            created_beads: list[dict] = []

            def fake_create(_root, _bd, **kwargs):
                rec = {"id": "opl-dsh-9", **{k: v for k, v in kwargs.items() if k != "runner"}}
                created_beads.append(rec)
                return rec

            buf_send = __import__("io").StringIO()
            with (
                mock.patch("sys.stdout", buf_send),
                mock.patch.object(opl_workflow, "executable", return_value="bd"),
                mock.patch.object(opl_ledger, "create_issue", side_effect=fake_create),
            ):
                rc_send = opl_workflow.main(
                    [
                        "send",
                        "Verify DSH route",
                        "--executor",
                        "dsh",
                        "--session",
                        "dsh:hs-bound-1",
                        "--instance",
                        str(instance),
                        "--state-dir",
                        str(ev_dir),
                        "--json",
                    ]
                )
            self.assertEqual(rc_send, 0)
            sent_meta = json.loads(buf_send.getvalue())["send"]["bead"]["metadata"]
            self.assertEqual(sent_meta["execution_thread"], "dsh:hs-bound-1")
            self.assertEqual(sent_meta["execution_carrier"], "dsh")
            self.assertEqual(sent_meta["opl_execution_requirements"]["adapter"], "local-dsh")


if __name__ == "__main__":
    unittest.main()
