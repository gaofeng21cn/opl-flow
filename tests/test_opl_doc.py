from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "opl-doc" / "SKILL.md"


class OplDocSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")

    def test_live_truth_precedes_document_claims(self) -> None:
        self.assertIn("Treat prose as a claim", self.skill)
        self.assertIn("contracts and schemas, source and callers", self.skill)
        self.assertIn("runtime or external owner readback", self.skill)

    def test_governance_is_semantic_and_layout_independent(self) -> None:
        self.assertIn("Audit the relevant sections", self.skill)
        self.assertIn("one current owner", self.skill)
        self.assertIn("Do not require a fixed set of files", self.skill)

    def test_flow_does_not_take_consumer_truth_or_work_state(self) -> None:
        self.assertIn("Do not create a second ledger", self.skill)
        self.assertIn("Keep each repository's product and domain truth", self.skill)
        self.assertIn("For multiple repositories", self.skill)
        self.assertIn("`$coordinate-concurrent-tasks`", self.skill)

    def test_claims_and_retirement_require_real_evidence(self) -> None:
        self.assertIn("Match claim strength to evidence", self.skill)
        self.assertIn("first prove the successor and real caller cutover", self.skill)
        self.assertIn("Do not report documentation alignment as runtime", self.skill)


if __name__ == "__main__":
    unittest.main()
