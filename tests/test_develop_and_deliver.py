from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DevelopAndDeliverTests(unittest.TestCase):
    def test_diagnosis_policy_keeps_narrow_and_deep_paths_distinct(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "develop-and-deliver" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_markers = (
            "## Diagnose Before Repair",
            "deepest verifiable breakpoint",
            "is evidence, not automatically",
            "Escalate to a deeper root-cause analysis only",
            "canonical owner surface",
            "Do not impose planner/debugger/executor/verifier role switching",
        )
        for marker in required_markers:
            self.assertIn(marker, skill)

    def test_latest_user_provenance_and_artifact_ssot_are_explicit(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "develop-and-deliver" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_markers = (
            "## User-Instruction Supersession",
            "### Provenance Before Calling Something A Deviation",
            "A commit author alone does not prove",
            "reflects the user's later explicit choice",
            "do not \"correct\" it back to an earlier design",
            "## Artifact SSOT And Delivery",
            "remote canonical `main`",
            "It is not artifact SSOT",
            "canonical absorption and remote",
        )
        for marker in required_markers:
            self.assertIn(marker, skill)

    def test_issue_and_pull_request_admission_checks_ssot_before_follow_up(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "develop-and-deliver" / "SKILL.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())

        required_markers = (
            "## Issue And Pull Request Admission",
            "a proposal, not as execution authority or product SSOT",
            "then decide whether the objective and",
            "solution are reasonable",
            "reject, rewrite, or shrink it before implementation",
            "does not justify blind follow-up",
        )
        for marker in required_markers:
            self.assertIn(marker, normalized_skill)

if __name__ == "__main__":
    unittest.main()
