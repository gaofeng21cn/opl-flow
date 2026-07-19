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

    def test_runtime_profile_prioritizes_terminal_outcome_and_bounds_delegation(self) -> None:
        profile = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("默认直接完成", profile)
        self.assertIn("用户最高优先级目标及其可验收终态", profile)
        self.assertIn("计划、审计、修复、测试和 handoff 均不得替代终态", profile)
        self.assertIn("只处理关键路径、确定性阻断和必需验证", profile)
        self.assertIn("其他发现延后，阻断闭合即回主线", profile)
        self.assertIn("超出预期时立即收缩范围，不得继续扩项", profile)
        self.assertIn("已进入真实权威来源并实际生效的前置成果", profile)
        self.assertIn("候选、handoff 或测试通过不算完成", profile)
        self.assertIn("发现顺序倒置时，先恢复正确依赖再回到主线", profile)
        self.assertIn("同一目标只设一个主控", profile)
        self.assertIn("仅在任务独立、可验收且能缩短关键路径时单层委派", profile)
        self.assertIn("并发默认 4", profile)
        self.assertIn("分批证明有益后可到 8", profile)
        self.assertIn("超过 8 须用户明确授权", profile)
        self.assertIn("子智能体不得再委派", profile)
        self.assertIn("完成或阻塞时立即回报并收拢", profile)
        self.assertNotIn("可独立任务积极并行", profile)
        self.assertNotIn("不因单个等待项停工", profile)
        self.assertIn("Git 写任务使用独立 worktree 和分支", profile)
        self.assertIn("按精确写集设唯一 owner", profile)
        self.assertIn("仅在依赖、写集重叠、`main` 或发布集成时串行", profile)
        self.assertIn("同步远端 `main` 并按当前 SSOT 解决冲突", profile)
        self.assertIn("吸收后验证最终 `main`", profile)
        self.assertIn("清理本任务的临时 Git 表面", profile)
        self.assertLessEqual(len(profile.splitlines()), 11)

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
