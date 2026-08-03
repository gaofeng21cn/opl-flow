from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class LedgerSupervisorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        ledger_start = (
            REPO_ROOT / "skills" / "opl-flow" / "references" / "ledger-start.md"
        ).read_text(encoding="utf-8")
        terminal_readback = (
            REPO_ROOT / "skills" / "opl-flow" / "references" / "terminal-readback.md"
        ).read_text(encoding="utf-8")
        self.ledger_start = " ".join(ledger_start.split())
        self.terminal_readback = " ".join(terminal_readback.split())

    def test_native_owner_failures_remain_distinct_and_bounded(self) -> None:
        required_markers = (
            "never pass a `limit` greater than `50`",
            "`invalid_arguments` is a caller defect",
            "`permission_denied` requires owner authorization",
            "`timeout_unknown` requires",
            "`unavailable` is reserved",
            "Never collapse these states into a generic tool blocker",
        )
        for marker in required_markers:
            self.assertIn(marker, self.ledger_start)

        for state in (
            "`invalid_arguments`",
            "`permission_denied`",
            "`timeout_unknown`",
            "`unavailable`",
        ):
            self.assertIn(state, self.terminal_readback)

    def test_linear_comment_loop_requires_answer_reply_and_provenance(self) -> None:
        required_markers = (
            "observed -> delivery_pending -> delivered -> owner_answered ->",
            "`linear_comment_id=<comment_id>`",
            "do not retry until a fresh destination read proves the marker absent",
            "`mcp__codex_apps__linear_save_comment`",
            "🤖 **Automated Codex reply | OPL Flow Supervisor**",
            "A footer-only attribution is insufficient",
            "Treat this marker as non-user provenance",
            "Advance the cursor only after destination receipt, owner answer",
        )
        for marker in required_markers:
            self.assertIn(marker, self.ledger_start)


if __name__ == "__main__":
    unittest.main()
