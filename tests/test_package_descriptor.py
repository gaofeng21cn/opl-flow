from __future__ import annotations

import json
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
        identity = self.manifest["identity"]
        self.assertEqual(self.manifest["schema_version"], "opl.package.v2")
        self.assertEqual(identity["id"], self.policy["package"]["id"])
        self.assertEqual(identity["intent"], "extension")
        self.assertEqual(identity["version"], self.policy["package"]["version"])
        self.assertEqual(identity["version"], self.plugin["version"])
        self.assertEqual(self.manifest["host_hints"]["codex"]["plugin_name"], self.plugin["name"])
        self.assertEqual(self.manifest["distribution"]["oci"].rsplit("/", 1)[-1], identity["id"])
        self.assertTrue(repository_file(identity["icon"]).is_file())

    def test_profile_and_three_router_skills_are_deliverable(self) -> None:
        skills = self.manifest["provides"]["skills"]
        self.assertCountEqual([skill["id"] for skill in skills], ["opl-flow", "software-development", "manage-codex-tasks"])
        for skill in skills:
            self.assertEqual(skill["exposure"], "default")
            self.assertTrue((repository_file(skill["path"]) / "SKILL.md").is_file())

        profile = load_json(REPO_ROOT / "profile" / "manifest.json")
        paths = [profile["runtime_profile"]["path"], profile["authoring_source"]["path"],
                 *(module["path"] for module in profile["modules"])]
        self.assertTrue(all(repository_file(item).is_file() for item in paths))
        self.assertTrue((REPO_ROOT / "contracts" / self.policy["$schema"]).is_file())

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
        self.assertEqual(self.manifest["dependencies"].get("packages", []), [])


if __name__ == "__main__":
    unittest.main()
