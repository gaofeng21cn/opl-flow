from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import opl_app_contribution as adapter
from scripts import opl_events
from scripts import opl_workflow

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample_snapshot() -> dict:
    return {
        "schema": "opl_ledger_supervisor_snapshot.v1",
        "issues": [
            {
                "id": "opl-1",
                "title": "NEEDS_ACTION｜确认发布窗口",
                "status": "open",
                "metadata": {
                    "classification": "managed_objective",
                    "execution_mode": "waiting_user",
                    "first_blocker": "等待确认是否包含实验开关",
                    "next_action": "给出是/否结论",
                    "remaining": ["确认发布窗口"],
                },
            },
            {
                "id": "opl-2",
                "title": "SAFE_TO_ARCHIVE｜补齐单元测试",
                "status": "closed",
                "metadata": {
                    "classification": "managed_objective",
                    "execution_mode": "active",
                    "remaining": [],
                    "archive_approved": False,
                },
            },
            {
                "id": "opl-3",
                "title": "进行中的重构任务",
                "status": "in_progress",
                "metadata": {
                    "classification": "managed_objective",
                    "execution_mode": "active",
                    "next_action": "完成 API 适配",
                    "remaining": ["API 适配", "回归测试"],
                },
            },
        ],
        "validation_errors": [],
    }


class OplAppContributionTests(unittest.TestCase):
    def test_framework_cli_routes_app_and_sdk_requests_to_the_same_owner(self) -> None:
        def invoke(request: dict) -> dict:
            run = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/opl_app_contribution.py")],
                input=json.dumps({
                    "schema_version": "opl-package-app-contribution-request.v1",
                    "package_id": "opl-flow", **request,
                }), text=True, capture_output=True, check=True,
            )
            return json.loads(run.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            unavailable = invoke({
                "operation": "read", "ref": adapter.DASHBOARD_REF,
                "input": {"instance_path": str(Path(tmp) / "missing")},
            })
            self.assertEqual((unavailable["ref"], unavailable["state"]), (adapter.DASHBOARD_REF, "unavailable"))
            action_ref = "opl-flow.decision.v1#approve"
            unconfirmed = {"instance_path": tmp, "bead_id": "demo-1", "confirmed": False}
            for action in ({"ref": action_ref, "input": unconfirmed}, {"action_id": action_ref, "payload": unconfirmed}):
                response = invoke({"operation": "execute", **action})
                self.assertEqual(response["schema_version"], "opl-package-app-contribution-response.v1")
                self.assertEqual(response["ref"], action_ref)
                self.assertEqual(response["error"]["code"], "confirmation_required")
            for blocked in (
                {"operation": "read", "ref": action_ref, "input": unconfirmed},
                {"operation": "execute", "ref": "opl-flow.decision.v1#service", "input": {}},
                {"operation": "execute", "package_id": "other", "ref": action_ref, "input": {}},
                {"operation": "execute", "dry_run": True, "ref": action_ref, "input": {}},
            ):
                response = invoke(blocked)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "invalid_request")
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_dashboard_sanitizes_service_paths_and_projects_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            instance = Path(tmp) / "opl-instance-demo"
            instance.mkdir()
            ev_dir = opl_events.default_event_state_dir(instance)
            opl_events.emit_event(
                ev_dir,
                event_type="human_comment",
                objective_id="opl-1",
                source="test:suite",
                idempotency_key="demo-ev-1",
                payload={"signal": "demo", "summary": "测试事件摘要"},
            )
            fake_svc = {
                "schema": "opl_router_service_status.v1",
                "platform": "Darwin",
                "label": "com.opl.flow.router.demo",
                "installed": True,
                "running": True,
                "service_path": "/Users/secret/Library/LaunchAgents/demo.plist",
                "log_dir": "/Users/secret/logs",
            }
            with (
                mock.patch.object(opl_workflow, "executable", return_value="bd"),
                mock.patch.object(opl_workflow, "supervisor_snapshot", return_value=_sample_snapshot()),
                mock.patch.object(adapter.opl_service, "router_service_status", return_value=fake_svc),
            ):
                resp = adapter.build_dashboard({"instance_path": str(instance)})

            self.assertTrue(resp["ok"])
            self.assertEqual(resp["state"], "ready")
            data = resp["data"]
            self.assertEqual(data["instance_name"], "opl-instance-demo")
            self.assertEqual(data["counts"]["needs_action"], 1)
            self.assertEqual(data["counts"]["safe_to_archive"], 1)
            self.assertEqual(data["counts"]["active_objectives"], 1)
            self.assertEqual(data["counts"]["pending_events"], 1)
            self.assertNotIn("service_path", data["service"])
            self.assertNotIn("log_dir", data["service"])
            self.assertNotIn("/Users/secret", json.dumps(resp, ensure_ascii=False))
            self.assertEqual(len(data["items"]), 3)

    def test_send_reply_and_create_and_confirmation_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            instance = Path(tmp) / "opl-instance-demo"
            instance.mkdir()
            with mock.patch.object(opl_workflow, "executable", return_value="bd"):
                reply = adapter.action_send(
                    {
                        "instance_path": str(instance),
                        "objective_id": "opl-1",
                        "message": "按方案 A 继续推进",
                        "request_id": "req-001",
                    }
                )
            self.assertTrue(reply["ok"])
            self.assertEqual(reply["result"]["action"], "reply")
            self.assertEqual(reply["result"]["bead_id"], "opl-1")
            self.assertEqual(reply["readback"]["data_ref"], "opl-flow.decision.v1#dashboard")

            # Archive approval MUST reject missing/false confirmation
            denied_approve = adapter.action_approve(
                {"instance_path": str(instance), "bead_id": "opl-2", "approved_by": "owner", "confirmed": False}
            )
            self.assertFalse(denied_approve["ok"])
            self.assertEqual(denied_approve["error"]["code"], "confirmation_required")

            # Service start/stop MUST reject missing/false confirmation
            denied_svc = adapter.action_service(
                {"instance_path": str(instance), "action": "up", "confirmed": False}
            )
            self.assertFalse(denied_svc["ok"])
            self.assertEqual(denied_svc["error"]["code"], "confirmation_required")

            # Confirmed archive delegates to opl_events.approve_archive
            fake_receipt = {
                "schema": "opl_archive_approval_receipt.v1",
                "bead_id": "opl-2",
                "archive_approved": True,
                "approved_by": "gaofeng",
                "approved_at": "2026-11-24T12:00:00Z",
                "bead": {"id": "opl-2"},
            }
            with (
                mock.patch.object(opl_workflow, "executable", return_value="bd"),
                mock.patch.object(opl_events, "approve_archive", return_value=fake_receipt) as mocked_approve,
            ):
                approved = adapter.action_approve(
                    {"instance_path": str(instance), "bead_id": "opl-2", "approved_by": "gaofeng", "confirmed": True}
                )
            self.assertTrue(approved["ok"])
            self.assertTrue(approved["result"]["archive_approved"])
            mocked_approve.assert_called_once()

    def test_instance_pointer_resolution_enforces_0600_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = root / "inst"
            inst.mkdir()
            pointer = root / "instance.json"
            pointer.write_text(
                json.dumps({"schema": "opl_flow_instance_pointer.v1", "path": str(inst)}),
                encoding="utf-8",
            )
            pointer.chmod(0o600)
            self.assertEqual(opl_workflow.instance_pointer(pointer), inst.resolve())
            pointer.chmod(0o644)
            with self.assertRaisesRegex(opl_workflow.WorkflowError, "0600"):
                opl_workflow.instance_pointer(pointer)

    def test_manifests_adapter_and_html_visual_contract(self) -> None:
        pkg = json.loads((REPO_ROOT / "opl-package.json").read_text(encoding="utf-8"))
        codex_plugin = json.loads((REPO_ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        mcp = json.loads((REPO_ROOT / "mcp.json").read_text(encoding="utf-8"))
        contrib_adapter = json.loads((REPO_ROOT / "app-contribution-adapter.json").read_text(encoding="utf-8"))

        self.assertEqual(codex_plugin.get("mcpServers"), "./mcp.json")
        self.assertEqual(
            mcp["mcpServers"]["decision-dashboard"]["args"],
            ["${PLUGIN_ROOT}/decision-dashboard/server.bundle.mjs"],
        )
        app = pkg["ui"]["mcp_apps"][0]
        self.assertEqual(app["resource_uri"], "ui://opl-flow/decision-dashboard.html")
        self.assertEqual(app["mcp_server_id"], pkg["provides"]["mcp_servers"][0]["id"])
        self.assertEqual(pkg["provides"]["contribution_handler"]["argv"], ["python3", "./scripts/opl_app_contribution.py"])
        self.assertIn("opl-flow.decision.v1#dashboard", contrib_adapter["reads"])
        self.assertIn("opl-flow.decision.v1#approve", contrib_adapter["actions"])

        html = (REPO_ROOT / "decision-dashboard/index.html").read_text(encoding="utf-8")
        self.assertLess(len(html.encode("utf-8")), 8 * 1024 * 1024)
        self.assertIn('data-opl-family="opl-apps"', html)
        self.assertIn("OPL Apps · OPL Flow", html)
        self.assertIn('<meta name="color-scheme" content="light dark">', html)
        self.assertIn("overscroll-behavior: contain", html)
        self.assertIn("MIT License", html)

    def test_bundled_mcp_server_stdio_jsonrpc_handshake_and_tools(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not available")
        bundle = REPO_ROOT / "decision-dashboard/server.bundle.mjs"
        self.assertTrue(bundle.is_file())

        proc = subprocess.Popen(
            [node, str(bundle)],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None and proc.stdout is not None
        try:
            def rpc(payload: dict) -> dict:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                if not line:
                    err = proc.stderr.read() if proc.stderr else ""
                    self.fail(f"MCP server exited prematurely: {err}")
                return json.loads(line)

            init = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {
                            "extensions": {
                                "io.modelcontextprotocol/ui": {
                                    "mimeTypes": ["text/html;profile=mcp-app"],
                                }
                            }
                        },
                        "clientInfo": {"name": "opl-flow-test", "version": "1.0.0"},
                    },
                }
            )
            pkg_version = json.loads((REPO_ROOT / "opl-package.json").read_text(encoding="utf-8"))["identity"]["version"]
            self.assertEqual(init["result"]["serverInfo"]["name"], "opl-flow-decision-dashboard")
            self.assertEqual(init["result"]["serverInfo"]["version"], pkg_version)
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            proc.stdin.flush()

            tools = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            by_name = {tool["name"]: tool for tool in tools["result"]["tools"]}
            self.assertIn("open_opl_flow_dashboard", by_name)
            launcher = by_name["open_opl_flow_dashboard"]
            self.assertEqual(launcher["_meta"]["ui"]["resourceUri"], "ui://opl-flow/decision-dashboard.html")
            self.assertTrue(launcher["annotations"]["readOnlyHint"])
            self.assertIn("com.google.antigravity/ui", launcher["_meta"])
            for app_tool in ("opl_flow_send", "opl_flow_approve_archive", "opl_flow_router_tick", "opl_flow_router_service"):
                self.assertIn(app_tool, by_name)
                self.assertEqual(by_name[app_tool]["_meta"]["ui"]["visibility"], ["app"])

            resource = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/read",
                    "params": {"uri": "ui://opl-flow/decision-dashboard.html"},
                }
            )
            content = resource["result"]["contents"][0]
            self.assertEqual(content["mimeType"], "text/html;profile=mcp-app")
            self.assertNotIn("__OPL_FLOW_INSTALLED_VERSION__", content["text"])
            self.assertIn(f'version:"{pkg_version}"', content["text"])
            self.assertIn('data-opl-family="opl-apps"', content["text"])
            self.assertEqual(content["_meta"]["ui"]["csp"], {"connectDomains": [], "resourceDomains": []})

            # Missing/nonexistent instance path should gracefully return unavailable state (not crash)
            call_missing = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "open_opl_flow_dashboard",
                        "arguments": {"instance_path": "/nonexistent-opl-flow-test-instance"},
                    },
                }
            )
            self.assertFalse(call_missing["result"].get("isError", False))
            self.assertEqual(call_missing["result"]["structuredContent"]["data"]["state"], "unavailable")
            self.assertEqual(call_missing["result"]["structuredContent"]["presentation"]["mode"], "mcp-app")

            # Unconfirmed archive call must be rejected at schema boundary
            bad_approve = rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "opl_flow_approve_archive",
                        "arguments": {"bead_id": "opl-2", "approved_by": "owner", "confirmed": False},
                    },
                }
            )
            self.assertTrue("error" in bad_approve or bad_approve["result"].get("isError"))
        finally:
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
