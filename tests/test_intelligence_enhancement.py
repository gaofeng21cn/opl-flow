from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import intelligence_enhancement


class IntelligenceEnhancementTests(unittest.TestCase):
    def test_status_reads_disabled_without_opl_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"HOME": tmp, "CODEX_HOME": str(Path(tmp) / ".codex")}
            with patch.dict(os.environ, env, clear=True):
                code, payload = intelligence_enhancement.run(intelligence_enhancement.parse_args(["status"]))

        self.assertEqual(code, 0)
        self.assertEqual(payload["opl_flow_intelligence_enhancement"]["status"], "disabled")
        self.assertEqual(payload["opl_flow_intelligence_enhancement"]["provider"], "codexcont")

    def test_enable_owns_codexcont_install_and_reads_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            codex_home = root / ".codex"
            codex_home.mkdir(parents=True)
            bin_dir.mkdir()
            uvx_log = root / "uvx.log"
            uvx = bin_dir / "uvx"
            uvx.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {str(uvx_log)!r}\nexit 0\n", encoding="utf-8")
            uvx.chmod(0o755)
            (codex_home / "config.toml").write_text(
                "\n".join([
                    'model_provider = "gflab"',
                    "",
                    "[model_providers.gflab]",
                    'name = "gflab"',
                    'base_url = "https://gflabtoken.cn/v1"',
                    'wire_api = "responses"',
                    "",
                ]),
                encoding="utf-8",
            )
            env = {
                "HOME": str(root),
                "CODEX_HOME": str(codex_home),
                "OPL_CODEXCONT_SERVICE_MODE": "manual",
                "OPL_CODEXCONT_SERVICE_SKIP": "1",
                "PATH": f"{bin_dir}:/usr/bin:/bin",
            }
            with patch.dict(os.environ, env, clear=True):
                code, payload = intelligence_enhancement.run(intelligence_enhancement.parse_args(["enable"]))

            self.assertEqual(code, 0)
            action = payload["opl_flow_intelligence_enhancement_action"]
            self.assertEqual(action["status"], "completed")
            self.assertEqual(action["status_readback"]["codex_provider_base_url"], "http://127.0.0.1:8787/v1")
            self.assertIn("codexcont install -y", uvx_log.read_text(encoding="utf-8"))
            self.assertIn("codexcont restart", uvx_log.read_text(encoding="utf-8"))
            self.assertIn('base_url = "http://127.0.0.1:8787/v1"', (codex_home / "config.toml").read_text(encoding="utf-8"))
            self.assertIn('url = "https://gflabtoken.cn/v1/responses"', (root / ".codexcont" / "config.toml").read_text(encoding="utf-8"))

    def test_uninstall_requires_explicit_confirmation(self) -> None:
        code, payload = intelligence_enhancement.run(intelligence_enhancement.parse_args(["uninstall"]))

        self.assertEqual(code, 2)
        self.assertEqual(
            payload["opl_flow_intelligence_enhancement_action"]["reason"],
            "uninstall_requires_confirmation",
        )


if __name__ == "__main__":
    unittest.main()
