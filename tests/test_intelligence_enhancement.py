from __future__ import annotations

import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import intelligence_enhancement


class IntelligenceEnhancementTests(unittest.TestCase):
    def test_missing_opl_reports_bootstrap_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing-opl"
            args = intelligence_enhancement.parse_args(["enable", "--opl", str(missing)])

            code, payload = intelligence_enhancement.run(args)

            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["reason"], "opl_cli_not_executable")
            self.assertIn("--bootstrap-opl", payload["retry_command"])

    def test_enable_delegates_to_opl_and_reads_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "opl.log"
            fake_opl = root / "opl"
            fake_opl.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    printf '%s\\n' "$*" >> {str(log)!r}
                    if [[ "$*" == *"intelligence_enhancement_status"* ]]; then
                      printf '{{"result":{{"opl_flow_intelligence_enhancement":{{"status":"enabled_running"}}}}}}\\n'
                    else
                      printf '{{"result":{{"opl_flow_intelligence_enhancement_action":{{"status":"completed"}}}}}}\\n'
                    fi
                    """
                ),
                encoding="utf-8",
            )
            fake_opl.chmod(0o755)
            args = intelligence_enhancement.parse_args(["enable", "--opl", str(fake_opl)])

            code, payload = intelligence_enhancement.run(args)

            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["action_result"]["stdout"]["result"]["opl_flow_intelligence_enhancement_action"]["status"], "completed")
            self.assertEqual(payload["status_readback"]["stdout"]["result"]["opl_flow_intelligence_enhancement"]["status"], "enabled_running")
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertIn("app action execute --action intelligence_enhancement_enable --json", calls)
            self.assertIn("app action execute --action intelligence_enhancement_status --json", calls)

    def test_uninstall_requires_explicit_confirmation(self) -> None:
        with redirect_stdout(StringIO()):
            code = intelligence_enhancement.main(["uninstall", "--opl", "/bin/echo"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
