from __future__ import annotations

import json
import re
import unittest
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "opl-package.json"


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return value


def repository_file(reference: str) -> Path:
    relative = PurePosixPath(reference)
    if not reference or relative.is_absolute() or ".." in relative.parts or str(relative) == ".":
        raise AssertionError(f"unsafe repository-relative path: {reference!r}")
    resolved = (REPO_ROOT / relative).resolve()
    if REPO_ROOT not in (resolved, *resolved.parents):
        raise AssertionError(f"path escapes repository root: {reference!r}")
    return resolved


class PackageDescriptorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_json(MANIFEST_PATH)
        self.plugin = load_json(REPO_ROOT / ".codex-plugin" / "plugin.json")
        self.policy = load_json(REPO_ROOT / "contracts" / "workflow-policy.json")

    def test_descriptor_declares_the_workflow_profile_owner_boundary(self) -> None:
        codex_surface = self.manifest["codex_surface"]
        profile_surface = self.manifest["profile_surface"]
        managed_policy_surface = self.manifest["managed_policy_surface"]

        self.assertEqual(self.manifest["surface_kind"], "opl_workflow_profile_package_manifest.v1")
        self.assertEqual(self.manifest["package_id"], "opl-flow")
        self.assertEqual(self.manifest["package_role"], "workflow_profile")
        self.assertEqual(
            self.manifest["carrier_source_role"],
            "codex_plugin_default_carrier_not_package_truth",
        )
        self.assertIsInstance(codex_surface, dict)
        self.assertIsInstance(profile_surface, dict)
        self.assertIsInstance(managed_policy_surface, dict)
        self.assertEqual(codex_surface["plugin_id"], self.plugin["name"])
        self.assertEqual(
            codex_surface["required_skill_ids"],
            [
                "coordinate-concurrent-tasks",
                "develop-and-deliver",
                "opl-fleet",
                "opl-flow",
                "recover-codex-tasks",
                "task-mode-gate",
            ],
        )
        self.assertEqual(profile_surface["existing_profile_policy"], "semantic_merge_required")
        self.assertEqual(
            profile_surface["runtime_profile"],
            {"source_path": "templates/AGENTS.md", "target_id": "user_agents_profile"},
        )
        self.assertEqual(
            profile_surface["authoring_sources"],
            [{"source_path": "templates/TASTE.md", "target_id": "user_taste_source"}],
        )
        self.assertEqual(managed_policy_surface["policy_kind"], "opl_flow_workflow_policy")

    def test_descriptor_versions_and_paths_are_real(self) -> None:
        codex_surface = self.manifest["codex_surface"]
        profile_surface = self.manifest["profile_surface"]
        managed_policy_surface = self.manifest["managed_policy_surface"]
        self.assertIsInstance(codex_surface, dict)
        self.assertIsInstance(profile_surface, dict)
        self.assertIsInstance(managed_policy_surface, dict)

        package = self.policy["package"]
        self.assertIsInstance(package, dict)
        self.assertEqual(self.manifest["version"], self.plugin["version"])
        self.assertEqual(self.manifest["version"], package["version"])
        self.assertEqual(codex_surface["plugin_payload_manifest_url"], "opl-package.json")
        self.assertNotIn("source_commit", self.manifest)
        self.assertNotIn("carrier_source_commit", codex_surface)

        references = [
            str(codex_surface["plugin_payload_manifest_url"]),
            str(profile_surface["runtime_profile"]["source_path"]),
            *(str(entry["source_path"]) for entry in profile_surface["authoring_sources"]),
            *(str(entry) for entry in profile_surface["merge_context_paths"]),
            str(managed_policy_surface["source_path"]),
            str(managed_policy_surface["schema_path"]),
        ]
        self.assertTrue(all(repository_file(reference).is_file() for reference in references))

    def test_descriptor_does_not_recreate_private_lifecycle_authority(self) -> None:
        forbidden_fields = {
            "content_lock",
            "distribution_payload",
            "lifecycle_receipt",
            "package_lock_ref",
            "package_core",
            "rollback_ref",
            "transaction",
            "source_commit",
        }
        self.assertTrue(forbidden_fields.isdisjoint(self.manifest))
        self.assertNotIn("carrier_source_commit", self.manifest["codex_surface"])
        self.assertEqual(self.manifest["capability_dependencies"], [])


if __name__ == "__main__":
    unittest.main()
