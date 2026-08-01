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

    def test_review_mode_preserves_delivery_speed_and_repository_pr_policy(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "develop-and-deliver" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_markers = (
            "## Review Without Slowing Delivery",
            "continue the original",
            "without waiting for it",
            "Never create a pull request only to satisfy OPL Flow",
            "review queueing, failure, or\nunavailability is non-blocking",
            "Do not reduce or duplicate",
            "Linear Cloud Coding Sessions are not the",
        )
        for marker in required_markers:
            self.assertIn(marker, skill)


if __name__ == "__main__":
    unittest.main()
