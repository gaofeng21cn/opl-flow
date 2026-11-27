from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import opl_antigravity  # noqa: E402


class OplAntigravityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="opl-flow-agy-test-")
        self.root = Path(self._tmp.name)
        self.gemini_home = self.root / ".gemini"
        self.agents_home = self.root / ".agents"
        self.gemini_home.mkdir(parents=True, exist_ok=True)
        self.agents_home.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_agy_fast_plugin(self, *, enabled: bool = True) -> Path:
        plugin_dir = self.gemini_home / "config" / "plugins" / "agy-fast"
        (plugin_dir / "rules").mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"name": "agy-fast", "version": "0.3.0"}), encoding="utf-8")
        (plugin_dir / "rules" / "AGENTS.md").write_text("# agy-fast rules\n", encoding="utf-8")
        cfg_path = self.gemini_home / "config" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
        cfg.setdefault("plugins", {})["agy-fast"] = {"enabled": enabled}
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return plugin_dir

    def test_baseline_manifest_and_templates_are_valid(self) -> None:
        manifest = opl_antigravity.load_baseline_manifest(REPO_ROOT)
        self.assertEqual(manifest["schema"], "opl_flow_antigravity_baseline.v1")
        plugins_by_id = {p["id"]: p for p in manifest["plugins"]}
        self.assertIn("codex-supervisor", plugins_by_id)
        self.assertFalse(plugins_by_id["codex-supervisor"]["required"])
        for rule in manifest["rules"]:
            tpl = REPO_ROOT / rule["template_path"]
            self.assertTrue(tpl.is_file(), f"missing template {tpl}")
            self.assertLess(tpl.stat().st_size, manifest["rule_budgets"]["warn_bytes"])
        gemini_tpl = (REPO_ROOT / "templates/antigravity/GEMINI.md").read_text(encoding="utf-8")
        self.assertIn("Antigravity 与 Codex Supervisor 派活与分工原则", gemini_tpl)
        self.assertIn("主动监督进度、超时止损拉回", gemini_tpl)
        for skill in manifest["skills"]:
            if skill["source"] == "bundled_template":
                self.assertTrue((REPO_ROOT / skill["template_path"]).is_file())

    def test_dry_run_makes_zero_mutations(self) -> None:
        self._seed_agy_fast_plugin()
        receipt = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=True,
            with_pretool_guard=True,
            with_weekly_audit=True,
            run_plugin_doctor=False,
        )
        self.assertTrue(receipt["dry_run"])
        self.assertIsNone(receipt["backup_dir"])
        self.assertFalse((self.gemini_home / "GEMINI.md").exists())
        self.assertFalse((self.gemini_home / "config/plugins/agy-fast/rules/AGENTS.local.md").exists())
        self.assertFalse((self.gemini_home / "config/skills/swarm-code-worker-brief/SKILL.md").exists())
        self.assertFalse((self.gemini_home / "config/skills/third-party-audit-triage/SKILL.md").exists())
        self.assertFalse((self.gemini_home / "config/skills/project-vision-and-gap-review/SKILL.md").exists())
        self.assertFalse((self.gemini_home / "config/skills/opl-flow-dual-carrier/SKILL.md").exists())
        self.assertFalse((self.gemini_home / "config/scripts/agy-pretool-guard.mjs").exists())
        self.assertFalse((self.gemini_home / "config/hooks.json").exists())
        self.assertFalse((self.gemini_home / "config/sidecars/weekly-agy-env-audit/sidecar.json").exists())

    def test_apply_fresh_home_is_idempotent_and_reaches_ready(self) -> None:
        self._seed_agy_fast_plugin()
        impeccable_src = self.agents_home / "skills" / "impeccable"
        impeccable_src.mkdir(parents=True, exist_ok=True)
        (impeccable_src / "SKILL.md").write_text("---\nname: impeccable\ndescription: ui\n---\n", encoding="utf-8")

        first = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            run_plugin_doctor=False,
        )
        self.assertEqual(first["doctor_readback"]["status"], "ready")
        gemini_md = (self.gemini_home / "GEMINI.md").read_text(encoding="utf-8")
        self.assertIn("<!-- OPL_FLOW_AGY_BASELINE_START -->", gemini_md)
        local_md = (self.gemini_home / "config/plugins/agy-fast/rules/AGENTS.local.md").read_text(encoding="utf-8")
        self.assertTrue(local_md.startswith("---\ntrigger: always_on\n---\n"))
        self.assertIn("<!-- OPL_FLOW_AGY_BASELINE_START -->", local_md)
        self.assertTrue((self.gemini_home / "config/skills/swarm-code-worker-brief/SKILL.md").is_file())
        self.assertTrue((self.gemini_home / "config/skills/third-party-audit-triage/SKILL.md").is_file())
        self.assertTrue((self.gemini_home / "config/skills/project-vision-and-gap-review/SKILL.md").is_file())
        self.assertTrue((self.gemini_home / "config/skills/opl-flow-dual-carrier/SKILL.md").is_file())
        impeccable_link = self.gemini_home / "config/skills/impeccable"
        self.assertTrue(impeccable_link.is_symlink())
        self.assertEqual(impeccable_link.resolve(), impeccable_src.resolve())

        second = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            run_plugin_doctor=False,
        )
        self.assertTrue(all(a["action"] == "unchanged" for a in second["actions"]))
        self.assertIsNone(second["backup_dir"])

    def test_apply_preserves_custom_user_rules_and_refuses_overlapping_duplication(self) -> None:
        self._seed_agy_fast_plugin()
        # Case 1: Existing distinct user GEMINI.md -> preserved + backed up + managed block appended
        custom_intro = "Always respond in 中文.\n\n## My Private Rule\n- Keep my custom preference intact.\n"
        gemini_path = self.gemini_home / "GEMINI.md"
        gemini_path.write_text(custom_intro, encoding="utf-8")

        # Case 2: Existing unmarked AGENTS.local.md with overlapping heading (different parenthetical suffix) -> merge_required, untouched!
        local_path = self.gemini_home / "config/plugins/agy-fast/rules/AGENTS.local.md"
        unmarked_overlap = "---\ntrigger: always_on\n---\n# Local agy-fast Overrides (Empirically Tuned)\nCustom text.\n"
        local_path.write_text(unmarked_overlap, encoding="utf-8")

        receipt = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            run_plugin_doctor=False,
        )
        actions = {a["target"]: a for a in receipt["actions"]}
        self.assertEqual(actions["rule:global_gemini_rules"]["action"], "append_managed_block")
        self.assertEqual(actions["rule:agy_fast_local_overrides"]["action"], "merge_required")
        self.assertTrue(receipt["backups"])
        self.assertTrue(Path(receipt["backups"][0]).is_file())

        updated_gemini = gemini_path.read_text(encoding="utf-8")
        self.assertIn("Keep my custom preference intact.", updated_gemini)
        self.assertIn("<!-- OPL_FLOW_AGY_BASELINE_START -->", updated_gemini)
        # Unmarked overlapping file must remain byte-for-byte untouched
        self.assertEqual(local_path.read_text(encoding="utf-8"), unmarked_overlap)

    def test_weekly_audit_sidecar_is_readonly_no_wildcards_and_never_auto_enabled(self) -> None:
        self._seed_agy_fast_plugin()
        cfg_before = (self.gemini_home / "config" / "config.json").read_text(encoding="utf-8")

        receipt = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            with_weekly_audit=True,
            cron_tz="Asia/Shanghai",
            schedule="0 9 * * 1",
            run_plugin_doctor=False,
        )
        self.assertEqual((self.gemini_home / "config" / "config.json").read_text(encoding="utf-8"), cfg_before)
        sidecar_path = self.gemini_home / "config/sidecars/weekly-agy-env-audit/sidecar.json"
        self.assertTrue(sidecar_path.is_file())
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(sidecar["builtin"], "schedule")
        self.assertEqual(sidecar["restart_policy"], "always")
        self.assertEqual(sidecar["args"][0], "CRON_TZ=Asia/Shanghai 0 9 * * 1")
        self.assertIn("--", sidecar["args"])
        grants = sidecar["agent_permissions"]["access_grants"]
        for bad in ("command(*)", "read_file(*)", "read_file(/)", "write_file(*)", "mcp(*)"):
            self.assertNotIn(bad, grants)
        self.assertFalse(any(g.startswith("write_file(") for g in grants))
        self.assertTrue(receipt["doctor_readback"]["planes"]["optional_enhancements"]["weekly_audit_sidecar_present"])

    def test_doctor_flags_duplicate_web_skill_and_parses_telemetry(self) -> None:
        self._seed_agy_fast_plugin()
        cfg_path = self.gemini_home / "config" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["plugins"]["modern-web-guidance-plugin"] = {"enabled": True}
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        dup_dir = self.gemini_home / "config/skills/modern-web-guidance"
        dup_dir.mkdir(parents=True, exist_ok=True)

        # Synthetic recent main session + swarm worker transcripts
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        main_log = self.gemini_home / "antigravity/brain/conv-main/.system_generated/logs/transcript_full.jsonl"
        main_log.parent.mkdir(parents=True, exist_ok=True)
        main_log.write_text(
            "\n".join(
                [
                    json.dumps({"type": "SYSTEM_MESSAGE", "created_at": now_iso, "content": "[agy-fast] snapshot"}),
                    json.dumps({"type": "USER_INPUT", "created_at": now_iso, "content": "hi"}),
                    json.dumps(
                        {
                            "type": "PLANNER_RESPONSE",
                            "created_at": now_iso,
                            "input_tokens": 100,
                            "cache_read_tokens": 900,
                            "tool_calls": [
                                {
                                    "name": "mcp_agy-fast_fast_run_checks",
                                    "args": {"commands": [{"command": "echo ok"}], "outputMode": "full"},
                                },
                                {
                                    "name": "run_command",
                                    "args": {"CommandLine": "python3 - <<'PY'\nprint('big')\nPY"},
                                },
                            ],
                        }
                    ),
                    json.dumps({"type": "GENERIC", "created_at": now_iso, "content": "Checks: 1/1 passed [truncated: 100B]"}),
                    json.dumps({"type": "GENERIC", "created_at": now_iso, "content": "output was truncated to output.txt"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        report = opl_antigravity.antigravity_doctor(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            days=7,
            run_plugin_doctor=False,
        )
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(len(report["planes"]["experience_baseline"]["duplicates"]), 1)
        self.assertEqual(report["telemetry"]["roles"]["main"]["cache_hit_rate"], 90.0)
        self.assertEqual(report["telemetry"]["top_spills"].get("cmd:python3"), 1)
        rc = report["telemetry"]["agy_fast"]["run_checks"]
        self.assertEqual(rc["calls"], 1)
        self.assertEqual(rc["single_command_calls"], 1)
        self.assertEqual(rc["full_mode_calls"], 1)
        self.assertEqual(rc["budget_truncated_calls"], 1)
        self.assertEqual(report["telemetry"]["agy_fast"]["session_start_new_main_hit"], 1)

    def test_with_pretool_guard_merges_safely_and_is_idempotent(self) -> None:
        self._seed_agy_fast_plugin()
        hooks_path = self.gemini_home / "config" / "hooks.json"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        existing_hooks = {"custom-user-hook": {"Stop": [{"command": "echo done"}]}}
        hooks_path.write_text(json.dumps(existing_hooks, indent=2) + "\n", encoding="utf-8")

        first = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            with_pretool_guard=True,
            run_plugin_doctor=False,
        )
        actions = {a["target"]: a["action"] for a in first["actions"]}
        self.assertEqual(actions["pretool_guard:script"], "create")
        self.assertEqual(actions["pretool_guard:hooks"], "merge_update")
        guard_script = self.gemini_home / "config/scripts/agy-pretool-guard.mjs"
        self.assertTrue(guard_script.is_file())
        self.assertTrue(os.access(guard_script, os.X_OK))
        merged = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(merged["custom-user-hook"], existing_hooks["custom-user-hook"])
        self.assertIn("agy-env-pretool-guard", merged)
        self.assertTrue(first["doctor_readback"]["planes"]["optional_enhancements"]["pretool_guard_present"])

        second = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            with_pretool_guard=True,
            run_plugin_doctor=False,
        )
        second_actions = {a["target"]: a["action"] for a in second["actions"]}
        self.assertEqual(second_actions["pretool_guard:script"], "unchanged")
        self.assertEqual(second_actions["pretool_guard:hooks"], "unchanged")
        self.assertTrue(all(a["action"] in ("unchanged", "absent_optional") for a in second["actions"]))
        self.assertIsNone(second["backup_dir"])

    def test_opl_workflow_cli_routes_antigravity_without_instance(self) -> None:
        self._seed_agy_fast_plugin()
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "opl_workflow.py"),
                "antigravity",
                "doctor",
                "--gemini-home",
                str(self.gemini_home),
                "--agents-home",
                str(self.agents_home),
                "--days",
                "0",
                "--skip-plugin-doctor",
                "--json",
            ],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "opl_flow_antigravity_doctor.v1")

    def test_doctor_and_dry_run_cover_codex_supervisor_plugin(self) -> None:
        self._seed_agy_fast_plugin()
        before = opl_antigravity.antigravity_doctor(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            days=0,
            run_plugin_doctor=False,
        )
        opt_before = before["planes"]["optional_enhancements"]
        self.assertFalse(opt_before["codex_supervisor_installed"])
        self.assertFalse(opt_before["codex_supervisor_enabled"])
        self.assertIsNone(opt_before["codex_supervisor_version"])
        self.assertFalse(opt_before["codex_supervisor_ctl_present"])

        dry = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=True,
            install_plugins=True,
            run_plugin_doctor=False,
        )
        dry_actions = {a["target"]: a["action"] for a in dry["actions"]}
        self.assertEqual(dry_actions["plugin:codex-supervisor"], "would_install")

        sup_dir = self.gemini_home / "config" / "plugins" / "codex-supervisor"
        ctl_path = sup_dir / "skills" / "codex-supervisor" / "scripts" / "codex-ctl.mjs"
        ctl_path.parent.mkdir(parents=True, exist_ok=True)
        ctl_path.write_text("// stub ctl\n", encoding="utf-8")
        (sup_dir / "plugin.json").write_text(
            json.dumps({"name": "codex-supervisor", "version": "1.4.0"}),
            encoding="utf-8",
        )

        applied = opl_antigravity.antigravity_apply(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            dry_run=False,
            install_plugins=True,
            run_plugin_doctor=False,
        )
        applied_actions = {a["target"]: a["action"] for a in applied["actions"]}
        self.assertEqual(applied_actions["plugin:codex-supervisor"], "unchanged")
        opt_after = applied["doctor_readback"]["planes"]["optional_enhancements"]
        self.assertTrue(opt_after["codex_supervisor_installed"])
        self.assertTrue(opt_after["codex_supervisor_enabled"])
        self.assertEqual(opt_after["codex_supervisor_version"], "1.4.0")
        self.assertTrue(opt_after["codex_supervisor_ctl_present"])
        self.assertEqual(applied["doctor_readback"]["status"], "ready")

        cfg_path = self.gemini_home / "config" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["plugins"]["codex-supervisor"] = {"enabled": False}
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        disabled_report = opl_antigravity.antigravity_doctor(
            gemini_home=self.gemini_home,
            agents_home=self.agents_home,
            root=REPO_ROOT,
            days=0,
            run_plugin_doctor=False,
        )
        self.assertEqual(disabled_report["status"], "ready")
        self.assertFalse(disabled_report["planes"]["optional_enhancements"]["codex_supervisor_enabled"])
        self.assertTrue(any("codex-supervisor" in f for f in disabled_report["findings"]))


if __name__ == "__main__":
    unittest.main()
