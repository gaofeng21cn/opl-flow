from __future__ import annotations

import io
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import opl_service as svc
from scripts import opl_workflow as workflow


class OplServiceAndUxTests(unittest.TestCase):
    def _mock_bd(self, root: Path) -> Path:
        bd = root / "bd"
        bd.write_text(
            """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
db_path = Path(os.environ["BD_STATE_FILE"])
db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else {"seq": 0, "issues": []}
cmd = args[0]

if cmd == "list":
    print(json.dumps(db["issues"]))
elif cmd == "ready":
    print(json.dumps([i for i in db["issues"] if i.get("status") != "closed"]))
elif cmd == "status":
    print(json.dumps({"open": len(db["issues"])}))
elif cmd == "dolt":
    if args[1:2] == ["status"]:
        print(json.dumps({"mode": "embedded"}))
    else:
        print("{}")
elif cmd == "show":
    target = args[1]
    match = next((i for i in db["issues"] if i["id"] == target), None)
    print(json.dumps(match or {}))
elif cmd == "create":
    db["seq"] += 1
    title = args[1]
    ext = args[args.index("--external-ref") + 1]
    meta = json.loads(args[args.index("--metadata") + 1])
    issue = {
        "id": f"opl-{db['seq']}",
        "title": title,
        "status": "open",
        "priority": 2,
        "issue_type": args[args.index("--type") + 1],
        "external_ref": ext,
        "metadata": meta,
        "dependencies": [],
    }
    db["issues"].append(issue)
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print(json.dumps(issue))
elif cmd == "update":
    target = args[1]
    for issue in db["issues"]:
        if issue["id"] == target and "--metadata" in args:
            issue["metadata"] = json.loads(args[args.index("--metadata") + 1])
    db_path.write_text(json.dumps(db), encoding="utf-8")
    print("{}")
else:
    print("{}")
""",
            encoding="utf-8",
        )
        bd.chmod(bd.stat().st_mode | stat.S_IXUSR)
        return bd

    def test_macos_plist_linux_systemd_and_cli_wrapper_in_isolated_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            instance.mkdir()
            flow = root / "flow"
            flow.mkdir()
            launch_dir = root / "LaunchAgents"
            systemd_dir = root / "systemd"
            log_dir = root / "logs"
            bin_dir = root / "bin"

            # dry_run generates valid XML plist without touching filesystem
            dry_mac = svc.install_router_service(
                instance,
                flow_root=flow,
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                dry_run=True,
            )
            self.assertFalse(launch_dir.exists())
            parsed_plist = plistlib.loads(dry_mac["definition"].encode("utf-8"))
            self.assertTrue(parsed_plist["KeepAlive"])
            self.assertTrue(parsed_plist["RunAtLoad"])
            self.assertIn("--use-codex-bridge", parsed_plist["ProgramArguments"])

            # Real write into temp LaunchAgents dir with mocked launchctl runner
            calls: list[list[str]] = []

            def fake_run(argv, *, check=True):
                calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, "active\n", "")

            inst_mac = svc.install_router_service(
                instance,
                flow_root=flow,
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                runner=fake_run,
                uid=501,
            )
            self.assertTrue(Path(inst_mac["service_path"]).is_file())
            self.assertEqual(calls[0][:2], ["launchctl", "bootout"])
            self.assertEqual(calls[1][:2], ["launchctl", "bootstrap"])

            status_mac = svc.router_service_status(
                instance,
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                runner=fake_run,
                uid=501,
            )
            self.assertTrue(status_mac["installed"])
            self.assertTrue(status_mac["running"])

            uninst_mac = svc.uninstall_router_service(
                instance,
                launch_agents_dir=launch_dir,
                platform_name="Darwin",
                runner=fake_run,
                uid=501,
            )
            self.assertTrue(uninst_mac["removed"])
            self.assertFalse(Path(inst_mac["service_path"]).exists())

            # Linux systemd unit dry-run and isolated write
            inst_linux = svc.install_router_service(
                instance,
                flow_root=flow,
                systemd_dir=systemd_dir,
                log_dir=log_dir,
                platform_name="Linux",
                runner=fake_run,
            )
            unit_text = Path(inst_linux["service_path"]).read_text(encoding="utf-8")
            self.assertIn("Type=simple", unit_text)
            self.assertIn("Restart=on-failure", unit_text)

            # CLI wrapper install
            wrap = svc.install_cli_wrapper(flow_root=flow, bin_dir=bin_dir)
            wrap_path = Path(wrap["path"])
            self.assertTrue(wrap_path.is_file())
            self.assertTrue(os.access(wrap_path, os.X_OK))
            self.assertIn("scripts/opl_workflow.py", wrap_path.read_text(encoding="utf-8"))

            # Antigravity bridge dry-run plist + real write + bridge detection
            dry_agy = svc.install_router_service(
                instance,
                flow_root=flow,
                bridge="antigravity",
                agy_bin="/usr/local/bin/agy",
                model="gemini-4-neon-high",
                effort="medium",
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                dry_run=True,
            )
            self.assertEqual(dry_agy["bridge"], "antigravity")
            agy_plist = plistlib.loads(dry_agy["definition"].encode("utf-8"))
            self.assertIn("--bridge", agy_plist["ProgramArguments"])
            self.assertIn("antigravity", agy_plist["ProgramArguments"])
            self.assertIn("--effort", agy_plist["ProgramArguments"])
            self.assertNotIn("--use-codex-bridge", agy_plist["ProgramArguments"])

            svc.install_router_service(
                instance,
                flow_root=flow,
                bridge="antigravity",
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                runner=fake_run,
                uid=501,
            )
            agy_status = svc.router_service_status(
                instance,
                launch_agents_dir=launch_dir,
                log_dir=log_dir,
                platform_name="Darwin",
                runner=fake_run,
                uid=501,
            )
            self.assertEqual(agy_status["bridge"], "antigravity")

            agy_linux = svc.install_router_service(
                instance,
                flow_root=flow,
                bridge="antigravity",
                systemd_dir=systemd_dir,
                log_dir=log_dir,
                platform_name="Linux",
                runner=fake_run,
            )
            self.assertIn("--bridge antigravity", Path(agy_linux["service_path"]).read_text(encoding="utf-8"))
            agy_linux_status = svc.router_service_status(
                instance,
                systemd_dir=systemd_dir,
                log_dir=log_dir,
                platform_name="Linux",
                runner=fake_run,
            )
            self.assertEqual(agy_linux_status["bridge"], "antigravity")

    def test_human_first_cli_verbs_up_down_ps_send_approve_and_inbox_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            instance = root / "instance"
            instance.mkdir()
            state_dir = root / "events"
            bd = self._mock_bd(root)
            db_file = root / "bd_state.json"
            db_file.write_text(
                json.dumps(
                    {
                        "seq": 2,
                        "issues": [
                            {
                                "id": "opl-1",
                                "title": "需要拍板选择数据库",
                                "status": "blocked",
                                "metadata": {"classification": "managed_objective", "execution_mode": "waiting_user", "first_blocker": "选择 Postgres 或 SQLite", "remaining": ["confirm"]},
                            },
                            {
                                "id": "opl-2",
                                "title": "修复日志轮转",
                                "status": "closed",
                                "metadata": {"classification": "managed_objective", "execution_mode": "active", "remaining": []},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            # up --dry-run and down --dry-run work cleanly with crisp Chinese output
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc_up = workflow.main(["up", "--instance", str(instance), "--dry-run"])
            self.assertEqual(rc_up, 0)
            self.assertIn("dry-run", buf.getvalue())

            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc_down = workflow.main(["down", "--instance", str(instance), "--dry-run"])
            self.assertEqual(rc_down, 0)
            self.assertIn("已停止", buf.getvalue())

            fake_snap = {
                "schema": "opl_flow_supervisor_snapshot.v1",
                "instance": str(instance),
                "issues": json.loads(db_file.read_text())["issues"],
                "validation_errors": [],
            }
            fake_svc = {"installed": True, "running": True, "label": "dev.one-person-lab.opl-flow-router.test"}

            with (
                mock.patch.dict(os.environ, {"BD_STATE_FILE": str(db_file)}),
                mock.patch.object(workflow, "executable", return_value=str(bd)),
                mock.patch.object(workflow, "supervisor_snapshot", return_value=fake_snap),
                mock.patch.object(workflow.opl_service, "router_service_status", return_value=fake_svc),
            ):
                # ps human view: Chinese headers, actionable hints, zero raw JSON
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_ps = workflow.main(["ps", "--instance", str(instance), "--event-state-dir", str(state_dir)])
                self.assertEqual(rc_ps, 0)
                out_ps = buf.getvalue()
                self.assertIn("【事件引擎】运行中", out_ps)
                self.assertIn("【需要你拍板 (NEEDS_ACTION: 1)】", out_ps)
                self.assertIn('opl-flow send --to opl-1 "你的决定"', out_ps)
                self.assertIn("【已完成待你验收归档 (SAFE_TO_ARCHIVE: 1)】", out_ps)
                self.assertIn("opl-flow approve opl-2", out_ps)
                self.assertNotIn('"schema":', out_ps)

                # inbox list --human matches clean view
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_inbox = workflow.main(["inbox", "list", "--instance", str(instance), "--event-state-dir", str(state_dir), "--human"])
                self.assertEqual(rc_inbox, 0)
                self.assertIn("【需要你拍板", buf.getvalue())

                # send new task (auto-derived title) & send with --executor antigravity
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_send1 = workflow.main(["send", "修复夜间定时任务超时问题", "--instance", str(instance), "--state-dir", str(state_dir)])
                self.assertEqual(rc_send1, 0)
                self.assertIn("已创建目标 [opl-3]", buf.getvalue())

                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_send_agy = workflow.main(
                        ["send", "调整看板展示", "--executor", "antigravity", "--instance", str(instance), "--state-dir", str(state_dir), "--json"]
                    )
                self.assertEqual(rc_send_agy, 0)
                agy_payload = json.loads(buf.getvalue())
                self.assertEqual(
                    agy_payload["send"]["bead"]["metadata"]["opl_execution_requirements"]["adapter"],
                    "local-antigravity",
                )

                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_send2 = workflow.main(["send", "选用 Postgres", "--to", "opl-1", "--instance", str(instance), "--state-dir", str(state_dir)])
                self.assertEqual(rc_send2, 0)
                self.assertIn("已向目标 [opl-1] 投递后续指示", buf.getvalue())

                # up default --dry-run --json defaults to bridge=auto with --bridge auto arg
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_up_default = workflow.main(["up", "--instance", str(instance), "--dry-run", "--json"])
                self.assertEqual(rc_up_default, 0)
                up_default_payload = json.loads(buf.getvalue())
                self.assertEqual(up_default_payload["bridge"], "auto")
                default_plist = plistlib.loads(up_default_payload["definition"].encode("utf-8"))
                self.assertIn("--bridge", default_plist["ProgramArguments"])
                self.assertIn("auto", default_plist["ProgramArguments"])

                # up --bridge antigravity --dry-run --json prints bridge=antigravity
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_up_agy = workflow.main(["up", "--instance", str(instance), "--bridge", "antigravity", "--dry-run", "--json"])
                self.assertEqual(rc_up_agy, 0)
                self.assertEqual(json.loads(buf.getvalue())["bridge"], "antigravity")

                # approve opl-2 explicitly
                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc_app = workflow.main(["approve", "opl-2", "--instance", str(instance), "--by", "gaofeng"])
                self.assertEqual(rc_app, 0)
                self.assertIn("已确认归档授权：[opl-2]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
