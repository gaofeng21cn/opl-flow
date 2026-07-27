from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import profile_compose


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProfileComposeTests(unittest.TestCase):
    def test_manifest_separates_runtime_and_authoring_surfaces(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / "profile" / "manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["schema"], "opl_flow_profile_manifest.v2")
        self.assertEqual(manifest["runtime_profile"], {"path": "templates/AGENTS.md", "required": True})
        self.assertFalse(manifest["authoring_source"]["runtime_required"])
        self.assertNotIn("explicit_compatibility_surfaces", manifest)

    def test_repo_template_matches_profile_modules(self) -> None:
        result = profile_compose.check(REPO_ROOT)

        self.assertTrue(result["ok"], result)

    def test_runtime_profile_is_prioritized_and_bounded(self) -> None:
        profile = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("按以下优先级工作：", profile)
        instructions = [
            line
            for line in profile.splitlines()
            if line.startswith("- ")
            or (len(line) > 3 and line[0].isdigit() and line[1:3] == ". ")
        ]
        self.assertLessEqual(len(instructions), 8)
        self.assertLessEqual(len(profile.encode("utf-8")), 4096)

    def test_taste_v2_keeps_six_principle_sections(self) -> None:
        taste = (REPO_ROOT / "templates" / "TASTE.md").read_text(encoding="utf-8")

        headings = [line for line in taste.splitlines() if line.startswith("## ")]
        self.assertEqual(len(headings), 6)

    def test_compose_validates_duplicate_module_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "profile" / "modules").mkdir(parents=True)
            (repo / "profile" / "modules" / "a.md").write_text("A\n", encoding="utf-8")
            (repo / "profile" / "manifest.json").write_text(
                json.dumps(
                    {
                        "rendered": "templates/AGENTS.md",
                        "modules": [
                            {"id": "same", "path": "profile/modules/a.md"},
                            {"id": "same", "path": "profile/modules/a.md"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                profile_compose.compose(repo)

    def test_write_updates_rendered_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "profile" / "modules").mkdir(parents=True)
            (repo / "profile" / "modules" / "a.md").write_text("A\n", encoding="utf-8")
            (repo / "profile" / "modules" / "b.md").write_text("B\n", encoding="utf-8")
            (repo / "profile" / "manifest.json").write_text(
                json.dumps(
                    {
                        "rendered": "templates/AGENTS.md",
                        "modules": [
                            {"id": "a", "path": "profile/modules/a.md"},
                            {"id": "b", "path": "profile/modules/b.md"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = profile_compose.write(repo)

            self.assertTrue(result["changed"])
            self.assertEqual((repo / "templates" / "AGENTS.md").read_text(encoding="utf-8"), "A\n\nB\n")


if __name__ == "__main__":
    unittest.main()
