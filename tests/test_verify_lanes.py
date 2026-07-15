from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify import (
    CORE_TEST_MODULES,
    OPS_KIT_TEST_MODULES,
    check_workflow_policy,
    contract_test_modules,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class VerifyLaneTests(unittest.TestCase):
    def test_default_lanes_keep_core_and_optional_tests_disjoint(self) -> None:
        core = contract_test_modules("core")
        ops_kit = contract_test_modules("ops-kit")

        self.assertEqual(core, CORE_TEST_MODULES)
        self.assertEqual(ops_kit, OPS_KIT_TEST_MODULES)
        self.assertFalse(set(core) & set(ops_kit))
        self.assertEqual(contract_test_modules("full"), (*core, *ops_kit))

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

    def test_workflow_policy_requires_skills_manager_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            contracts = repo_root / "contracts"
            contracts.mkdir()
            policy = json.loads(
                (REPO_ROOT / "contracts" / "workflow-policy.json").read_text(encoding="utf-8")
            )
            ui_ux = next(item for item in policy["recommends"] if item["id"] == "ui-ux-pro-max")
            ui_ux["source"] = "github:nextlevelbuilder/ui-ux-pro-max-skill"
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
            "workflow policy managed skills must use their Skills Manager package authority",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
