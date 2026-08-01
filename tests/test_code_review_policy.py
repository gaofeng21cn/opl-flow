from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CodeReviewPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = json.loads(
            (REPO_ROOT / "contracts" / "code-review-policy.json").read_text(encoding="utf-8")
        )
        self.schema = json.loads(
            (REPO_ROOT / "contracts" / "code-review-policy.schema.json").read_text(encoding="utf-8")
        )

    def test_policy_is_opt_in_and_never_requires_pull_requests(self) -> None:
        self.assertEqual(self.policy["default_mode"], "off")
        self.assertEqual(set(self.policy["modes"]), {"off", "async-risk", "required"})
        self.assertEqual(self.policy["delivery"]["pr_policy"], "repository_owned")
        self.assertFalse(self.policy["delivery"]["pr_required_by_flow"])

    def test_async_risk_is_non_blocking(self) -> None:
        mode = self.policy["modes"]["async-risk"]
        self.assertEqual(mode["low_risk"], "skip")
        self.assertEqual(mode["medium_risk"], "async")
        self.assertEqual(mode["high_risk"], "async")
        self.assertFalse(mode["review_failure_blocks_delivery"])

    def test_schema_and_policy_identity_match(self) -> None:
        self.assertEqual(self.policy["$schema"], "./code-review-policy.schema.json")
        self.assertEqual(
            self.schema["properties"]["schema"]["const"],
            self.policy["schema"],
        )


if __name__ == "__main__":
    unittest.main()
