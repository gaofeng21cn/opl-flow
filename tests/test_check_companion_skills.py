from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import check_companion_skills


class CheckCompanionSkillsTests(unittest.TestCase):
    def write_skill(self, root: Path, skill: str) -> Path:
        path = root / skill
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {skill}\n---\n", encoding="utf-8")
        return path

    def configure_using_superpowers(self, codex_home: Path, superpowers_root: Path, disabled: bool) -> None:
        codex_home.mkdir(parents=True, exist_ok=True)
        enabled_line = "enabled = false" if disabled else "enabled = true"
        skill_path = superpowers_root / "skills" / "using-superpowers" / "SKILL.md"
        (codex_home / "config.toml").write_text(
            f'[[skills.config]]\npath = "{skill_path}"\n{enabled_line}\n',
            encoding="utf-8",
        )

    def test_detects_lite_profile_with_local_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / ".codex"
            superpowers_root = codex_home / "superpowers"
            agents_skills = home / ".agents" / "skills"
            overlay_root = home / ".skills-manager" / "skills" / "superpowers-local-profile"

            for skill in check_companion_skills.SUPERPOWERS_LITE_SELECTED:
                source_root = overlay_root if skill in {"systematic-debugging", "test-driven-development", "verification-before-completion"} else superpowers_root / "skills"
                source = self.write_skill(source_root, skill)
                agents_skills.mkdir(parents=True, exist_ok=True)
                (agents_skills / skill).symlink_to(source)
            lite = self.write_skill(home / ".skills-manager" / "skills", "superpowers-lite")
            (agents_skills / "superpowers-lite").symlink_to(lite)
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=True)

            status = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )

            self.assertEqual(status["profile"], "lite")
            self.assertTrue(status["using_superpowers_disabled"])
            self.assertEqual(
                status["local_overlay_skills"],
                ["systematic-debugging", "test-driven-development", "verification-before-completion"],
            )

    def test_detects_expanded_and_full_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / ".codex"
            superpowers_root = codex_home / "superpowers"
            agents_skills = home / ".agents" / "skills"
            agents_skills.mkdir(parents=True, exist_ok=True)

            for skill in check_companion_skills.SUPERPOWERS_EXPANDED_SELECTED:
                source = self.write_skill(superpowers_root / "skills", skill)
                (agents_skills / skill).symlink_to(source)
            lite = self.write_skill(home / ".skills-manager" / "skills", "superpowers-lite")
            (agents_skills / "superpowers-lite").symlink_to(lite)
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=True)

            expanded = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )
            self.assertEqual(expanded["profile"], "expanded")

            for path in agents_skills.iterdir():
                path.unlink()
            (agents_skills / "superpowers").symlink_to(superpowers_root / "skills")
            self.configure_using_superpowers(codex_home, superpowers_root, disabled=False)

            full = check_companion_skills.superpowers_profile_status(
                home,
                codex_home,
                home / "plugins",
                home / "repo",
                superpowers_root,
            )
            self.assertEqual(full["profile"], "full")
            self.assertFalse(full["using_superpowers_disabled"])


if __name__ == "__main__":
    unittest.main()
