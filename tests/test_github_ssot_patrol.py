from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "skills" / "github-ssot-patrol" / "scripts" / "github_patrol.py"
)
SPEC = importlib.util.spec_from_file_location("github_patrol", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
github_patrol = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = github_patrol
SPEC.loader.exec_module(github_patrol)


class GitHubPatrolTests(unittest.TestCase):
    def test_auth_probe_requires_matching_rest_graphql_owner_and_actions_reads(self) -> None:
        def fake_run_json(argv: list[str]) -> object:
            joined = " ".join(argv)
            if joined == "gh api user":
                return {"login": "gaofeng21cn"}
            if "graphql" in argv:
                return {"data": {"viewer": {"login": "gaofeng21cn"}}}
            if "user/repos" in joined:
                return []
            if "actions/runs" in joined:
                return {"workflow_runs": []}
            self.fail(f"unexpected argv: {argv}")

        with patch.object(github_patrol, "run_json", side_effect=fake_run_json):
            result = github_patrol.auth_probe(
                "gaofeng21cn",
                "gaofeng21cn/one-person-lab",
                attempts=1,
                sleep_fn=lambda _seconds: None,
            )

        self.assertTrue(result["valid"])
        self.assertEqual(result["authenticated_login"], "gaofeng21cn")

    def test_latest_default_runs_keeps_latest_run_per_workflow(self) -> None:
        runs = [
            {
                "databaseId": 4,
                "workflowName": "Verify",
                "headBranch": "main",
                "event": "push",
            },
            {
                "databaseId": 3,
                "workflowName": "Verify",
                "headBranch": "main",
                "event": "push",
            },
            {
                "databaseId": 2,
                "workflowName": "PR",
                "headBranch": "feature",
                "event": "pull_request",
            },
            {
                "databaseId": 1,
                "workflowName": "Release",
                "headBranch": "main",
                "event": "workflow_dispatch",
            },
        ]

        folded = github_patrol.latest_default_runs(runs, "main")

        self.assertEqual(
            [(item["workflowName"], item["databaseId"]) for item in folded],
            [("Release", 1), ("Verify", 4)],
        )

    def test_compare_ignores_observation_time_but_detects_repository_drift(self) -> None:
        base = {
            "schema": github_patrol.SCHEMA,
            "owner": "gaofeng21cn",
            "observed_at": "first",
            "auth": {"valid": True, "authenticated_login": "gaofeng21cn", "attempts": [1]},
            "read_errors": [],
            "repositories": [
                {
                    "name": "gaofeng21cn/example",
                    "archived": False,
                    "private": False,
                    "issues_enabled": True,
                    "default_branch": "main",
                    "default_sha": "aaa",
                    "latest_default_runs": [],
                    "open_prs": [],
                    "open_issues": [],
                }
            ],
        }
        later = {**base, "observed_at": "second", "auth": {**base["auth"], "attempts": [1, 2]}}

        stable = github_patrol.compare_snapshots(base, later)
        self.assertTrue(stable["stable"])

        drifted = {
            **later,
            "repositories": [{**later["repositories"][0], "default_sha": "bbb"}],
        }
        changed = github_patrol.compare_snapshots(base, drifted)
        self.assertFalse(changed["stable"])
        self.assertEqual(changed["changed_repositories"], ["gaofeng21cn/example"])

    def test_error_classification_is_bounded_and_does_not_emit_credentials(self) -> None:
        self.assertEqual(github_patrol.error_class("HTTP 401: Bad credentials"), "auth_invalid")
        self.assertEqual(github_patrol.error_class("API rate limit exceeded"), "rate_limited")
        self.assertEqual(github_patrol.error_class("TLS handshake timed out"), "transport_error")


if __name__ == "__main__":
    unittest.main()
