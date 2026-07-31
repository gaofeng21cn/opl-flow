from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills/task-mode-gate/SKILL.md"
AGENT_PATH = REPO_ROOT / "skills/task-mode-gate/agents/openai.yaml"
CANARIES_PATH = REPO_ROOT / "tests/fixtures/task_mode_gate_trigger_canaries.json"


class TaskModeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.agent = AGENT_PATH.read_text(encoding="utf-8")
        cls.canaries = json.loads(CANARIES_PATH.read_text(encoding="utf-8"))

    def test_frontmatter_has_narrow_trigger_and_explicit_exclusions(self) -> None:
        description = re.search(
            r"^description: (.+)$",
            self.skill,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(description)
        value = description.group(1)
        for required in (
            "current task will execute, authorize, or reconcile",
            "public or destructive mutation",
            "Do not trigger for read-only plans",
            "ordinary local development",
            "tests, or dry-runs",
            "unless that production gate itself is being validated",
        ):
            self.assertIn(required, value)

    def test_internal_checklist_is_exactly_five_fields(self) -> None:
        match = re.search(
            r"## Record Internally.*?```text\n(.*?)```",
            self.skill,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        fields = [
            line.split(":", 1)[0]
            for line in match.group(1).splitlines()
            if line.strip()
        ]
        self.assertEqual(
            fields,
            [
                "mode",
                "mutation_scope",
                "terminal_outcome",
                "keep_gates",
                "defer_gates",
            ],
        )

    def test_checklist_is_not_a_default_chat_artifact(self) -> None:
        normalized_skill = " ".join(self.skill.split())
        for required in (
            "control state, not a chat artifact",
            "Do not quote,",
            "Recompute it silently",
            "Default to quiet operation",
            "one natural clause",
            "at most one sentence",
            "ask a blocking question",
            "give a concise reconcile notice",
        ):
            self.assertIn(required, normalized_skill)
        self.assertNotIn("Declare the five-field boundary", self.skill)
        self.assertIn("Keep its five-field decision internal", self.agent)
        self.assertNotIn("Declare the five-field boundary", self.agent)

    def test_read_only_early_exit_and_reconcile_exception_are_explicit(self) -> None:
        self.assertIn("internal disposition `not_applicable`", self.skill)
        self.assertIn("unknown public-mutation result", self.skill)
        self.assertIn("For `read_only_reconcile`", self.skill)

    def test_breakpoint_strategy_is_not_duplicated(self) -> None:
        for removed in (
            "Handle The First Breakpoint",
            "first_action:",
            "repair_strategy:",
            "direct_fix",
            "delivery_bridge",
        ):
            self.assertNotIn(removed, self.skill)

    def test_trigger_canaries_cover_six_positive_and_six_negative_cases(self) -> None:
        self.assertEqual(
            self.canaries["schema"],
            "task-mode-gate.trigger-canaries.v2",
        )
        cases = self.canaries["cases"]
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({case["id"] for case in cases}), 12)
        self.assertEqual(
            [case["expected"] for case in cases].count("trigger"),
            6,
        )
        self.assertEqual(
            [case["expected"] for case in cases].count("skip"),
            6,
        )

    def test_trigger_canaries_have_valid_mode_and_scope(self) -> None:
        allowed_modes = {"development_validation", "production_release"}
        allowed_scopes = {
            "read_only_reconcile",
            "local_write",
            "public_mutation",
        }
        allowed_visibility = {
            "silent",
            "compact",
            "blocking",
            "reconcile_notice",
        }
        for case in self.canaries["cases"]:
            if case["expected"] == "trigger":
                self.assertIn(case["mode"], allowed_modes, case["id"])
                self.assertIn(case["mutation_scope"], allowed_scopes, case["id"])
                self.assertIn(case["visibility"], allowed_visibility, case["id"])
            else:
                self.assertNotIn("mode", case, case["id"])
                self.assertNotIn("mutation_scope", case, case["id"])
                self.assertNotIn("visibility", case, case["id"])

    def test_trigger_canaries_cover_output_visibility_modes(self) -> None:
        visibility = [
            case["visibility"]
            for case in self.canaries["cases"]
            if case["expected"] == "trigger"
        ]
        self.assertEqual(
            {name: visibility.count(name) for name in set(visibility)},
            {
                "silent": 3,
                "compact": 1,
                "blocking": 1,
                "reconcile_notice": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
