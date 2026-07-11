from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import check_companion_skills


class CheckCompanionSkillsTests(unittest.TestCase):
    def write_skill(self, root: Path, skill: str) -> Path:
        path = root / skill
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {skill}\n---\n", encoding="utf-8")
        return path

    def configure_using_superpowers(self, codex_home: Path, superpowers_root: Path, disabled: bool) -> None:
        codex_home.mkdir(parents=True, exist_ok=True)
        enabled_line = "enabled = false" if disabled else "enabled = true"
        skill_path = superpowers_root / "skills" / "using-superpowers" / "SKILL.md"
        (codex_home / "config.toml").write_text(
            f'[[skills.config]]\npath = "{skill_path}"\n{enabled_line}\n',
            encoding="utf-8",
        )

    def write_fake_codex(self, root: Path, plugin_root: Path) -> Path:
        version = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        script = root / "bin" / "codex"
        script.parent.mkdir(parents=True)
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"root = {str(plugin_root)!r}\n"
            f"version = {version!r}\n"
            "args = sys.argv[1:]\n"
            "if args[:3] == ['plugin', 'marketplace', 'list']:\n"
            "    print(json.dumps({'marketplaces': [{'name': 'opl-flow-local', 'root': root}]}))\n"
            "elif args[:2] == ['plugin', 'list']:\n"
            "    print(json.dumps({'installed': [{'pluginId': 'opl-flow@opl-flow-local', 'name': 'opl-flow', "
            "'marketplaceName': 'opl-flow-local', 'version': version, 'installed': True, "
            "'enabled': True, 'source': {'source': 'local', 'path': root}, "
            "'marketplaceSource': {'sourceType': 'local', 'source': root}}], 'available': []}))\n"
            "else:\n"
            "    print('{}')\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return script

    def test_detects_lite_profile_with_local_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / ".codex"
            superpowers_root = codex_home / "superpowers"
            agents_skills = home / ".agents" / "skills"
            overlay_root = home / ".skills-manager" / "skills" / "superpowers-local-profile"

            for skill in check_companion_skills.SUPERPOWERS_LITE_SELECTED:
                source_root = overlay_root if skill in {"systematic-debugging", "test-driven-development", "verification-before-completion"} else superpowers_root / "skills"
                source = self.write_skill(source_root, skill)
                agents_skills.mkdir(parents=True, exist_ok=True)
                (agents_skills / skill).symlink_to(source)
            lite = self.write_skill(home / ".skills-manager" / "skills", "superpowers-lite")
            (agents_skills / "superpowers-lite").symlink_to(lite)
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=True)

            status = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )

            self.assertEqual(status["profile"], "lite")
            self.assertTrue(status["using_superpowers_disabled"])
            self.assertEqual(
                status["local_overlay_skills"],
                ["systematic-debugging", "test-driven-development", "verification-before-completion"],
            )
            self.assertNotIn("brainstorming", check_companion_skills.SUPERPOWERS_LITE_SELECTED)
            self.assertNotIn("using-git-worktrees", check_companion_skills.SUPERPOWERS_LITE_SELECTED)
            self.assertIn("brainstorming", check_companion_skills.SUPERPOWERS_EXPANDED_SELECTED)
            self.assertIn("using-git-worktrees", check_companion_skills.SUPERPOWERS_EXPANDED_SELECTED)

    def test_detects_expanded_and_full_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / ".codex"
            superpowers_root = codex_home / "superpowers"
            agents_skills = home / ".agents" / "skills"
            agents_skills.mkdir(parents=True, exist_ok=True)

            for skill in check_companion_skills.SUPERPOWERS_EXPANDED_SELECTED:
                source = self.write_skill(superpowers_root / "skills", skill)
                (agents_skills / skill).symlink_to(source)
            lite = self.write_skill(home / ".skills-manager" / "skills", "superpowers-lite")
            (agents_skills / "superpowers-lite").symlink_to(lite)
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=True)

            expanded = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )
            self.assertEqual(expanded["profile"], "expanded")

            for path in agents_skills.iterdir():
                path.unlink()
            (agents_skills / "superpowers").symlink_to(superpowers_root / "skills")
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=False)

            full = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )
            self.assertEqual(full["profile"], "full")
            self.assertFalse(full["using_superpowers_disabled"])

    def test_detects_optional_ponytail_plugin_and_safe_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / ".codex"
            repo = home / "repo"
            plugin_root = codex_home / "plugins" / "cache" / "ponytail-local" / "ponytail" / "4.8.3"
            (plugin_root / ".codex-plugin").mkdir(parents=True)
            (plugin_root / ".codex-plugin" / "plugin.json").write_text('{"name":"ponytail"}\n', encoding="utf-8")
            (plugin_root / "hooks").mkdir()
            (plugin_root / "hooks" / "claude-codex-hooks.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "SessionStart": [
                                {
                                    "matcher": "startup",
                                    "hooks": [{"command": "node hooks/ponytail-activate.js"}],
                                }
                            ],
                            "UserPromptSubmit": [
                                {"hooks": [{"command": "node hooks/ponytail-mode-tracker.js"}]}
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            (plugin_root / "hooks" / "ponytail-instructions.js").write_text(
                "module.exports.getPonytailInstructions=()=>['a','b','c','d','e'].join('\\n');\n",
                encoding="utf-8",
            )
            (home / ".config" / "ponytail").mkdir(parents=True)
            (home / ".config" / "ponytail" / "config.json").write_text(
                '{\n  "defaultMode": "lite"\n}\n',
                encoding="utf-8",
            )

            status = check_companion_skills.find_plugin(
                "ponytail",
                home,
                codex_home,
                home / "plugins",
                repo,
            )
            config = check_companion_skills.ponytail_config_status(home)
            hooks = check_companion_skills.ponytail_hook_status(
                codex_home,
                {
                    "installed": [
                        {
                            "pluginId": "ponytail@ponytail-local",
                            "name": "ponytail",
                            "marketplaceName": "ponytail-local",
                            "version": "4.8.3",
                            "installed": True,
                            "enabled": True,
                        }
                    ]
                },
            )

            self.assertTrue(status["ok"])
            self.assertEqual(status["sources"], ["plugin_cache"])
            self.assertEqual(config["default_mode"], "lite")
            self.assertEqual(config["auto_activation"], "on")
            self.assertEqual(config["recommended_default_mode"], "lite")
            self.assertTrue(config["matches_opl_default"])
            self.assertTrue(hooks["ok"])
            self.assertEqual(hooks["matches"][0]["lite_lines"], 5)
            self.assertEqual(hooks["binding"], "installed_enabled_plugin")

            empty_hooks = json.loads(
                (plugin_root / "hooks" / "claude-codex-hooks.json").read_text(encoding="utf-8")
            )
            empty_hooks["hooks"]["UserPromptSubmit"][0]["hooks"] = []
            (plugin_root / "hooks" / "claude-codex-hooks.json").write_text(
                json.dumps(empty_hooks), encoding="utf-8"
            )
            self.assertFalse(
                check_companion_skills.ponytail_hook_status(
                    codex_home,
                    {
                        "installed": [
                            {
                                "pluginId": "ponytail@ponytail-local",
                                "name": "ponytail",
                                "marketplaceName": "ponytail-local",
                                "version": "4.8.3",
                                "installed": True,
                                "enabled": True,
                            }
                        ]
                    },
                )["ok"]
            )

            empty_hooks["hooks"]["UserPromptSubmit"][0]["hooks"] = [
                {"command": "node hooks/ponytail-mode-tracker.js"}
            ]
            (plugin_root / "hooks" / "claude-codex-hooks.json").write_text(
                json.dumps(empty_hooks), encoding="utf-8"
            )

            duplicate_payload = {
                "installed": [
                    *[
                        {
                            "pluginId": plugin_id,
                            "name": "ponytail",
                            "marketplaceName": marketplace,
                            "version": "4.8.3",
                            "installed": True,
                            "enabled": True,
                        }
                        for plugin_id, marketplace in (
                            ("ponytail@ponytail-local", "ponytail-local"),
                            ("ponytail@ponytail", "ponytail"),
                        )
                    ]
                ]
            }
            self.assertFalse(
                check_companion_skills.ponytail_hook_status(codex_home, duplicate_payload)["ok"]
            )

    def test_runtime_guardrail_ready_rejects_source_and_staged_candidates(self) -> None:
        status = {
            "match_details": [
                {"source": "bundled_repo", "runtime_discoverable": False},
                {"source": "staged_local_plugin", "runtime_discoverable": False},
            ]
        }

        self.assertFalse(check_companion_skills.runtime_skill_ready(status))

        status["match_details"].append(
            {"source": "codex_home", "runtime_discoverable": True}
        )
        self.assertTrue(check_companion_skills.runtime_skill_ready(status))

    def test_strict_rejects_plugin_missing_one_native_guardrail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            codex_home = home / ".codex"
            plugins_dir = home / "plugins"
            plugin_root = plugins_dir / "opl-flow"
            shutil.copytree(Path(__file__).resolve().parents[1], plugin_root)
            shutil.rmtree(plugin_root / "skills" / "codex-ops-kit")

            version = json.loads(
                (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )["version"]
            cache_root = codex_home / "plugins" / "cache" / "opl-flow-local" / "opl-flow" / version
            shutil.copytree(plugin_root, cache_root)
            check_companion_skills.install_local_plugin.install_profile(
                Path(__file__).resolve().parents[1],
                codex_home,
            )
            codex_bin = self.write_fake_codex(root, plugin_root)
            args = argparse.Namespace(
                home=str(home),
                codex_home=str(codex_home),
                plugins_dir=str(plugins_dir),
                repo_root=str(Path(__file__).resolve().parents[1]),
                skill_root=[str(Path(__file__).resolve().parents[1] / "skills")],
                superpowers_root=str(codex_home / "superpowers"),
                codex_bin=str(codex_bin),
                strict=True,
            )

            result = check_companion_skills.check(args)

            self.assertFalse(result["ok"])
            self.assertEqual(result["blocking_missing"], ["codex-ops-kit"])
            self.assertFalse(result["compatibility"]["opl_flow_plugin_ready"])

    def test_strict_rejects_unapproved_profile_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            codex_home = home / ".codex"
            plugins_dir = home / "plugins"
            plugin_root = plugins_dir / "opl-flow"
            shutil.copytree(Path(__file__).resolve().parents[1], plugin_root)
            version = json.loads(
                (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )["version"]
            cache_root = codex_home / "plugins" / "cache" / "opl-flow-local" / "opl-flow" / version
            shutil.copytree(plugin_root, cache_root)
            check_companion_skills.install_local_plugin.install_profile(
                Path(__file__).resolve().parents[1],
                codex_home,
            )
            (codex_home / "AGENTS.md").write_text("custom only\n", encoding="utf-8")
            codex_bin = self.write_fake_codex(root, plugin_root)
            args = argparse.Namespace(
                home=str(home),
                codex_home=str(codex_home),
                plugins_dir=str(plugins_dir),
                repo_root=str(Path(__file__).resolve().parents[1]),
                skill_root=[str(Path(__file__).resolve().parents[1] / "skills")],
                superpowers_root=str(codex_home / "superpowers"),
                codex_bin=str(codex_bin),
                strict=True,
            )

            result = check_companion_skills.check(args)

            self.assertFalse(result["ok"])
            self.assertEqual(result["profile"]["status"], "merge_required")
            self.assertFalse(result["compatibility"]["opl_flow_profile_ready"])


if __name__ == "__main__":
    unittest.main()
