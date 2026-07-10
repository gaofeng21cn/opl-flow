from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import install_local_plugin


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallLocalPluginTests(unittest.TestCase):
    def write_fake_codex(self, root: Path, plugin_root: Path) -> Path:
        version = json.loads(
            (REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        script = root / "bin" / "codex"
        add_count = root / "plugin-add-count"
        script.parent.mkdir(parents=True)
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, shutil, sys\n"
            f"root = {str(plugin_root)!r}\n"
            f"version = {version!r}\n"
            f"add_count = pathlib.Path({str(add_count)!r})\n"
            f"cache = pathlib.Path({str(root / 'codex' / 'plugins' / 'cache' / 'opl-flow-local' / 'opl-flow')!r}) / version\n"
            "args = sys.argv[1:]\n"
            "if args[:3] == ['plugin', 'marketplace', 'list']:\n"
            "    print(json.dumps({'marketplaces': [{'name': 'opl-flow-local', 'root': root}]}))\n"
            "elif args[:2] == ['plugin', 'add']:\n"
            "    count = int(add_count.read_text()) + 1 if add_count.exists() else 1\n"
            "    add_count.write_text(str(count))\n"
            "    if cache.exists(): shutil.rmtree(cache)\n"
            "    cache.parent.mkdir(parents=True, exist_ok=True)\n"
            "    shutil.copytree(root, cache)\n"
            "    print('{}')\n"
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

    def write_merge_output(self, packet: Path, agents_suffix: str = "\napproved local overlay\n") -> None:
        output = packet / "output"
        shutil.copy2(packet / "candidate" / "AGENTS.md", output / "AGENTS.md")
        shutil.copy2(packet / "candidate" / "TASTE.md", output / "TASTE.md")
        shutil.copytree(packet / "candidate" / "prompts", output / "prompts", dirs_exist_ok=True)
        (output / "AGENTS.md").write_text(
            (output / "AGENTS.md").read_text(encoding="utf-8") + agents_suffix,
            encoding="utf-8",
        )
        (output / "merge-report.md").write_text("approved test merge\n", encoding="utf-8")

    def test_install_codex_plugin_refreshes_already_installed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = install_local_plugin.copy_tree(REPO_ROOT, root / "plugins")
            codex_bin = self.write_fake_codex(root, plugin_root)

            result = install_local_plugin.install_codex_plugin(str(codex_bin), plugin_root)

            self.assertTrue(result["plugin"]["ok"])
            self.assertEqual((root / "plugin-add-count").read_text(encoding="utf-8"), "1")

    def test_verify_rejects_stale_codex_plugin_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex"
            plugins_dir = root / "plugins"
            plugin_root = install_local_plugin.copy_tree(REPO_ROOT, plugins_dir)
            codex_bin = self.write_fake_codex(root, plugin_root)
            version = json.loads(
                (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )["version"]
            cache_root = codex_home / "plugins" / "cache" / "opl-flow-local" / "opl-flow" / version
            shutil.copytree(plugin_root, cache_root)
            (cache_root / "README.md").write_text("stale cache\n", encoding="utf-8")

            result = install_local_plugin.verify(
                REPO_ROOT,
                plugins_dir,
                codex_home,
                profile=False,
                codex_bin=str(codex_bin),
            )

            self.assertFalse(result["ok"])
            self.assertIn("content:cache/README.md", result["cache_mismatches"])

    def test_verify_rejects_unsynced_non_guardrail_source_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex"
            plugins_dir = root / "plugins"
            shutil.copytree(
                REPO_ROOT,
                repo,
                ignore=shutil.ignore_patterns(".git", ".worktrees", ".pytest_cache", "__pycache__", ".DS_Store"),
            )
            plugin_root = install_local_plugin.copy_tree(repo, plugins_dir)
            codex_bin = self.write_fake_codex(root, plugin_root)
            version = json.loads(
                (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )["version"]
            cache_root = codex_home / "plugins" / "cache" / "opl-flow-local" / "opl-flow" / version
            shutil.copytree(plugin_root, cache_root)
            skill = repo / "skills" / "opl-flow" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8")

            result = install_local_plugin.verify(
                repo,
                plugins_dir,
                codex_home,
                profile=False,
                codex_bin=str(codex_bin),
            )

            self.assertFalse(result["ok"])
            self.assertIn(
                "content:plugin/skills/opl-flow/SKILL.md",
                result["source_plugin_mismatches"],
            )

    def test_marketplace_manifest_uses_unique_opl_flow_identity(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["name"], "opl-flow-local")
        self.assertEqual([plugin["name"] for plugin in manifest["plugins"]], ["opl-flow"])
        self.assertEqual(manifest["plugins"][0]["source"]["path"], ".")

    def test_plugin_readback_requires_exact_installed_enabled_version(self) -> None:
        version = json.loads(
            (REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        plugin_root = Path("/tmp/opl-flow-test-root")
        entry = {
                "pluginId": "opl-flow@opl-flow-local",
                "name": "opl-flow",
                "marketplaceName": "opl-flow-local",
                "version": version,
                "installed": True,
                "enabled": True,
                "source": {"source": "local", "path": str(plugin_root)},
                "marketplaceSource": {"sourceType": "local", "source": str(plugin_root)},
            }
        payload = {"installed": [entry], "available": []}

        status = install_local_plugin.plugin_readback_status(
            payload,
            plugin_name="opl-flow",
            marketplace_name="opl-flow-local",
            version=version,
            expected_root=plugin_root,
        )

        self.assertTrue(status["ok"])
        self.assertEqual(status["plugin_id"], "opl-flow@opl-flow-local")

        entry["enabled"] = False
        disabled = install_local_plugin.plugin_readback_status(
            payload,
            plugin_name="opl-flow",
            marketplace_name="opl-flow-local",
            version=version,
            expected_root=plugin_root,
        )
        self.assertFalse(disabled["ok"])

        entry["enabled"] = True
        entry["marketplaceSource"]["source"] = "/tmp/wrong-marketplace"
        wrong_source = install_local_plugin.plugin_readback_status(
            payload,
            plugin_name="opl-flow",
            marketplace_name="opl-flow-local",
            version=version,
            expected_root=plugin_root,
        )
        self.assertFalse(wrong_source["ok"])

        entry["marketplaceSource"]["source"] = str(plugin_root)
        del entry["pluginId"]
        missing_exact_id = install_local_plugin.plugin_readback_status(
            payload,
            plugin_name="opl-flow",
            marketplace_name="opl-flow-local",
            version=version,
            expected_root=plugin_root,
        )
        self.assertFalse(missing_exact_id["ok"])

    def test_install_profile_writes_fresh_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"

            result = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(result["status"], "installed")
            self.assertTrue((codex_home / "AGENTS.md").exists())
            self.assertTrue((codex_home / "TASTE.md").exists())
            self.assertTrue((codex_home / "prompts" / "planner.md").exists())

    def test_install_profile_does_not_overwrite_existing_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"
            codex_home.mkdir()
            existing = "custom user profile\n"
            (codex_home / "AGENTS.md").write_text(existing, encoding="utf-8")

            result = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(result["status"], "requires_codex_semantic_merge")
            self.assertEqual((codex_home / "AGENTS.md").read_text(encoding="utf-8"), existing)
            self.assertEqual(result["changed"], [])
            packet = Path(result["merge_packet"])
            self.assertTrue((packet / "existing" / "AGENTS.md").exists())
            self.assertTrue((packet / "candidate" / "AGENTS.md").exists())
            self.assertTrue((packet / "candidate" / "profile" / "manifest.json").exists())
            self.assertTrue((packet / "prompt.md").exists())
            plan = json.loads((packet / "merge-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["script_merge_policy"], "disabled")
            self.assertEqual(plan["status"], "requires_codex_semantic_merge")

    def test_merge_packet_paths_are_unique_for_immediate_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")

            first = install_local_plugin.create_merge_packet(REPO_ROOT, codex_home, "first")
            second = install_local_plugin.create_merge_packet(REPO_ROOT, codex_home, "second")

            self.assertNotEqual(first["merge_packet"], second["merge_packet"])
            self.assertTrue(Path(first["merge_packet"]).exists())
            self.assertTrue(Path(second["merge_packet"]).exists())

    def test_install_profile_current_profile_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex"
            first = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            second = install_local_plugin.install_profile(REPO_ROOT, codex_home)

            self.assertEqual(first["status"], "installed")
            self.assertEqual(second["status"], "current")
            self.assertEqual(second["changed"], [])

    def test_unapproved_profile_change_requires_semantic_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex"
            shutil.copytree(REPO_ROOT / "templates", repo / "templates")

            install_local_plugin.install_profile(repo, codex_home)
            (codex_home / "AGENTS.md").write_text(
                (codex_home / "AGENTS.md").read_text(encoding="utf-8") + "\nlocal overlay\n",
                encoding="utf-8",
            )

            overlay = install_local_plugin.verify_profile(repo, codex_home, profile=True)
            self.assertEqual(overlay["status"], "merge_required")

    def test_apply_merge_packet_records_approved_local_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex"
            shutil.copytree(REPO_ROOT / "templates", repo / "templates")
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")

            pending = install_local_plugin.install_profile(repo, codex_home)
            packet = Path(pending["merge_packet"])
            self.write_merge_output(packet)
            applied = install_local_plugin.apply_merge_packet(repo, codex_home, packet)

            self.assertEqual(applied["status"], "applied")
            self.assertTrue(Path(applied["receipt"]).exists())
            self.assertIn("approved local overlay", (codex_home / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual(
                install_local_plugin.verify_profile(repo, codex_home, profile=True)["status"],
                "local_overlay",
            )

            (codex_home / "AGENTS.md").write_text("custom only\n", encoding="utf-8")
            self.assertEqual(
                install_local_plugin.verify_profile(repo, codex_home, profile=True)["status"],
                "merge_required",
            )

            (repo / "templates" / "AGENTS.md").write_text(
                (repo / "templates" / "AGENTS.md").read_text(encoding="utf-8") + "\nsource update\n",
                encoding="utf-8",
            )
            drift = install_local_plugin.verify_profile(repo, codex_home, profile=True)
            self.assertEqual(drift["status"], "merge_required")

    def test_profile_receipt_allows_safe_source_update_without_local_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex"
            shutil.copytree(REPO_ROOT / "templates", repo / "templates")
            install_local_plugin.install_profile(repo, codex_home)

            updated = (repo / "templates" / "AGENTS.md").read_text(encoding="utf-8") + "\nsource update\n"
            (repo / "templates" / "AGENTS.md").write_text(updated, encoding="utf-8")

            pending = install_local_plugin.verify_profile(repo, codex_home, profile=True)
            self.assertEqual(pending["status"], "source_update")

            result = install_local_plugin.install_profile(repo, codex_home)
            self.assertEqual(result["status"], "updated")
            self.assertEqual((codex_home / "AGENTS.md").read_text(encoding="utf-8"), updated)
            self.assertEqual(
                install_local_plugin.verify_profile(repo, codex_home, profile=True)["status"],
                "current",
            )

    def test_approved_local_overlay_does_not_rewrite_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            codex_home = root / "codex"
            shutil.copytree(REPO_ROOT / "templates", repo / "templates")
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")
            pending = install_local_plugin.install_profile(repo, codex_home)
            packet = Path(pending["merge_packet"])
            self.write_merge_output(packet)
            install_local_plugin.apply_merge_packet(repo, codex_home, packet)
            receipt_path = install_local_plugin.profile_receipt_path(codex_home)
            approved = receipt_path.read_text(encoding="utf-8")
            result = install_local_plugin.install_profile(repo, codex_home)

            self.assertEqual(result["status"], "local_overlay")
            self.assertEqual(receipt_path.read_text(encoding="utf-8"), approved)

    def test_verify_reports_merge_required_for_existing_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex"
            plugins_dir = root / "plugins"
            codex_bin = self.write_fake_codex(root, plugins_dir / "opl-flow")
            codex_home.mkdir()
            (codex_home / "AGENTS.md").write_text("custom user profile\n", encoding="utf-8")

            install_result = install_local_plugin.install(
                REPO_ROOT,
                plugins_dir,
                codex_home,
                profile=True,
                codex_bin=str(codex_bin),
            )
            verify_result = install_local_plugin.verify(
                REPO_ROOT,
                plugins_dir,
                codex_home,
                profile=True,
                codex_bin=str(codex_bin),
            )

            self.assertEqual(install_result["profile"]["status"], "requires_codex_semantic_merge")
            self.assertFalse(install_result["ok"])
            self.assertEqual(install_result["status"], "profile_merge_required")
            self.assertFalse(verify_result["ok"])
            self.assertEqual(verify_result["profile_status"], "merge_required")
            self.assertEqual(verify_result["profile_merge_packet"], install_result["profile"]["merge_packet"])
            self.assertEqual((codex_home / "AGENTS.md").read_text(encoding="utf-8"), "custom user profile\n")

    def test_main_returns_nonzero_when_profile_merge_is_pending(self) -> None:
        args = argparse.Namespace(
            repo_root=str(REPO_ROOT),
            plugins_dir="/tmp/plugins",
            codex_home="/tmp/codex",
            codex_bin="codex",
            no_profile=False,
            verify_only=False,
            apply_merge_packet=None,
        )
        with (
            mock.patch.object(install_local_plugin, "parse_args", return_value=args),
            mock.patch.object(
                install_local_plugin,
                "install",
                return_value={"ok": False, "status": "profile_merge_required"},
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(install_local_plugin.main(), 2)

    def test_verify_rejects_stale_or_extra_ops_skill_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex"
            plugins_dir = root / "plugins"
            codex_bin = self.write_fake_codex(root, plugins_dir / "opl-flow")
            codex_home.mkdir()
            install_local_plugin.install(
                REPO_ROOT,
                plugins_dir,
                codex_home,
                profile=False,
                codex_bin=str(codex_bin),
            )

            source_skill = REPO_ROOT / "skills" / "codex-ops-kit"
            plugin_skill = plugins_dir / "opl-flow" / "skills" / "codex-ops-kit"
            (plugin_skill / "SKILL.md").write_text("stale\n", encoding="utf-8")
            (plugin_skill / "scripts" / "rho_wrapper.py").write_text("retired\n", encoding="utf-8")

            local_skill = codex_home / "skills" / "codex-ops-kit"
            shutil.copytree(source_skill, local_skill)
            (local_skill / "SKILL.md").write_text("stale local\n", encoding="utf-8")

            result = install_local_plugin.verify(
                REPO_ROOT,
                plugins_dir,
                codex_home,
                profile=False,
                codex_bin=str(codex_bin),
            )

            self.assertFalse(result["ok"])
            self.assertIn("content:plugin/skills/codex-ops-kit/SKILL.md", result["source_plugin_mismatches"])
            self.assertIn("unexpected:plugin/skills/codex-ops-kit/scripts/rho_wrapper.py", result["source_plugin_mismatches"])
            self.assertIn("content:skills/codex-ops-kit/SKILL.md", result["local_skill_mismatches"])

if __name__ == "__main__":
    unittest.main()
