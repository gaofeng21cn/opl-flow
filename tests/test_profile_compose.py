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

    def test_runtime_profile_is_bounded_and_routes_detailed_methods_to_skills(self) -> None:
        profile = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("用户可验收终态", profile)
        self.assertIn("开发默认 progress-first", profile)
        self.assertIn("首个真实断点", profile)
        self.assertIn("AI 负责开放判断", profile)
        self.assertIn("同一目标只设一个主控", profile)
        self.assertIn("单个主控任务内的子智能体并发默认 4", profile)
        self.assertIn("分批证明有益后可到 8", profile)
        self.assertIn("超过 8 须用户明确授权", profile)
        self.assertIn("子智能体不得再委派", profile)
        self.assertIn("完成或阻塞时立即回报并收拢", profile)
        self.assertIn("Git 写任务使用独立 worktree 和分支", profile)
        self.assertIn("按精确写集设唯一 owner", profile)
        self.assertIn("仅在真实依赖、写集重叠或 `main`/发布集成时串行", profile)
        self.assertIn("吸收后验证最终 `main`", profile)
        self.assertIn("$develop-and-deliver", profile)
        self.assertIn("$architect-and-simplify", profile)
        self.assertIn("$task-mode-gate", profile)
        self.assertIn("普通小改直接完成", profile)
        bullets = [line for line in profile.splitlines() if line.startswith("- ")]
        self.assertLessEqual(len(bullets), 8)
        self.assertLessEqual(len(profile.encode("utf-8")), 2048)
        for operational_detail in ("delivery_bridge", "CAS", "Latest", "cohort", "receipt"):
            self.assertNotIn(operational_detail, profile)

    def test_taste_v2_is_non_runtime_and_contains_six_value_principles(self) -> None:
        taste = (REPO_ROOT / "templates" / "TASTE.md").read_text(encoding="utf-8")

        self.assertIn("非运行时治理参考", taste)
        self.assertIn("不宣称被自动编译、自动注入或自动生效", taste)
        headings = [line for line in taste.splitlines() if line.startswith("## ")]
        self.assertEqual(
            headings,
            [
                "## 1. 可验收终态优先",
                "## 2. 开发与生产分离",
                "## 3. 进展优先",
                "## 4. AI 判断，机器守界",
                "## 5. 声明与证据同级",
                "## 6. 简单、精准、规则克制",
            ],
        )

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
