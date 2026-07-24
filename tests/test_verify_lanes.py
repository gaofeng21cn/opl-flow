from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from scripts.verify import (
    CORE_TEST_MODULES,
    check_plugin_json,
    check_skill_metadata,
    check_workflow_policy,
    contract_test_modules,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyLaneTests(unittest.TestCase):
    def test_plugin_exposes_the_two_bounded_flow_skills(self) -> None:
        self.assertEqual(check_plugin_json(REPO_ROOT), [])
        self.assertEqual(check_skill_metadata(REPO_ROOT), [])

        discoverable = {
            path.name
            for path in (REPO_ROOT / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").exists()
        }
        self.assertEqual(discoverable, {"coordinate-concurrent-tasks", "opl-flow"})

        coordination = (REPO_ROOT / "skills" / "coordinate-concurrent-tasks" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("set_thread_archived(true)", coordination)
        self.assertIn("archive_performed=false", coordination)
        self.assertIn("user_approval_required=true", coordination)

    def test_full_lane_runs_the_complete_current_suite(self) -> None:
        core = contract_test_modules("core")

        self.assertEqual(core, CORE_TEST_MODULES)
        self.assertEqual(contract_test_modules("full"), core)
        with self.assertRaisesRegex(ValueError, "unknown verification lane: ops-kit"):
            contract_test_modules("ops-kit")

    def test_workflow_policy_rejects_retired_codex_ops_kit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            policy["compatible_optional"].append(
                {
                    "id": "codex-ops-kit",
                    "kind": "codex_skill",
                    "offline_bundle": "full",
                    "online_install_default": False,
                    "activation": "explicit",
                    "source": "opl-flow:optional-skills/codex-ops-kit",
                }
            )
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn("retired codex-ops-kit must not remain in workflow dependencies", errors)

    def test_workflow_policy_preserves_explicit_ponytail_skills(self) -> None:
        self.assertEqual(check_workflow_policy(REPO_ROOT), [])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ponytail = next(item for item in policy["conflicts"] if item["id"] == "ponytail")
            ponytail["discovery_ids"].append("ponytail-audit")
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn(
            "explicit Ponytail audit and review skills must remain outside workflow retirement",
            errors,
        )

    def test_workflow_policy_requires_canonical_github_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ui_ux = next(item for item in policy["recommends"] if item["id"] == "ui-ux-pro-max")
            ui_ux["source"] = "https://github.com/example/ui-ux-pro-max-skill"
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            errors = check_workflow_policy(repo_root)

        self.assertIn(
            "workflow policy external skills must use their canonical GitHub source and path",
            errors,
        )

    def workflow_policy_errors_after(self, mutate) -> list[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            provided = next(
                item
                for item in policy["provides"]
                if item["kind"] == "codex_skill" and item["id"] == "opl-flow"
            )
            mutate(provided)
            (contracts / "workflow-policy.json").write_text(
                f"{json.dumps(policy, indent=2)}\n",
                encoding="utf-8",
            )
            (contracts / "workflow-policy.schema.json").write_text(
                (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            return check_workflow_policy(repo_root)

    def test_every_skill_requires_original_github_source(self) -> None:
        errors = self.workflow_policy_errors_after(
            lambda item: item.update(source="package:opl-flow/skills/opl-flow")
        )
        self.assertIn(
            "all codex_skill capabilities must declare their original GitHub source "
            "and repository-relative source_path",
            errors,
        )

    def test_every_skill_requires_safe_repository_relative_source_path(self) -> None:
        for invalid_path in ("../skills/opl-flow", "/skills/opl-flow", r"skills\opl-flow"):
            with self.subTest(source_path=invalid_path):
                errors = self.workflow_policy_errors_after(
                    lambda item, value=invalid_path: item.update(source_path=value)
                )
                self.assertIn(
                    "all codex_skill capabilities must declare their original GitHub source "
                    "and repository-relative source_path",
                    errors,
                )

    def test_skill_source_schema_patterns_reject_non_github_and_unsafe_paths(self) -> None:
        schema = json.loads(
            (REPO_ROOT / "contracts" / "workflow-policy.schema.json").read_text(encoding="utf-8")
        )
        properties = (
            schema["$defs"]["capability"]["allOf"][0]["then"]["properties"]
        )
        source_pattern = properties["source"]["pattern"]
        path_pattern = properties["source_path"]["pattern"]

        self.assertIsNotNone(
            re.fullmatch(source_pattern, "https://github.com/Panniantong/Agent-Reach")
        )
        self.assertIsNone(re.fullmatch(source_pattern, "skills-manager:agent-reach"))
        self.assertIsNotNone(re.fullmatch(path_pattern, "agent_reach/skill"))
        self.assertIsNotNone(re.fullmatch(path_pattern, "."))
        for invalid_path in ("../skill", "/skill", r"skills\agent-reach"):
            with self.subTest(schema_source_path=invalid_path):
                self.assertIsNone(re.fullmatch(path_pattern, invalid_path))


if __name__ == "__main__":
    unittest.main()
