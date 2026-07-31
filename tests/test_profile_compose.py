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

    def test_runtime_profile_is_prioritized_and_dynamic_capacity(self) -> None:
        profile = (REPO_ROOT / "templates" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("按以下优先级工作：", profile)
        required_capabilities = (
            "终态与用户 SSOT",
            "最新直接用户指令决定",
            "冲突时标记为 `stale/derived/unknown`",
            "定位可验证根因或最深可证断点",
            "不以表象补丁冒充修复",
            "AI 负责开放判断",
            "$coordinate-concurrent-tasks",
            "$develop-and-deliver",
            "$task-mode-gate",
            "$architect-and-simplify` 已安装时使用",
            "否则由模型按相同边界直接完成",
            "不得因缺少可选增强而阻断",
            "子智能体不得再委派",
            "并发规模按 fresh execution graph",
            "不设全局固定上限",
            "worktree/branch 有明确 owner",
            "`.worktrees` 只放 Git worktree",
            "Shell 默认用 `rtk`",
            "codegraph init .",
            "无需询问",
            "字面检索用 `rg`",
            "浏览器按场景固定路由",
            "connector/API/CLI",
            "现有会话用 Chrome",
            "一次性网页用内置 Browser",
            "重复/回归用 Playwright",
            "CLI/远程/Electron 用 agent-browser",
            "桌面视觉用 Computer Use",
            "agent-reach",
        )
        for capability in required_capabilities:
            self.assertIn(capability, profile)
        instructions = [
            line
            for line in profile.splitlines()
            if line.startswith("- ")
            or (len(line) > 3 and line[0].isdigit() and line[1:3] == ". ")
        ]
        self.assertLessEqual(len(instructions), 8)

    def test_browser_routing_doc_covers_primary_scenarios_and_boundaries(self) -> None:
        routing = (REPO_ROOT / "docs" / "browser-tool-routing.md").read_text(encoding="utf-8")

        required_sections = (
            "# 浏览器工具路由",
            "## 总原则",
            "## 固定优先级",
            "## 表单与杂志编辑",
            "## 降级链",
            "## 快速决策表",
            "chrome:control-chrome",
            "browser:control-in-app-browser",
            "Playwright",
            "agent-browser",
            "Computer Use",
            "agent-reach",
            "凭据不迁移",
            "不可擅自替换",
            "不应默认使用",
        )
        for section in required_sections:
            self.assertIn(section, routing)

    def test_coordinate_skill_keeps_local_first_remote_last_boundary(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "coordinate-concurrent-tasks" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_capabilities = (
            "### 本地优先、远端最后",
            "push task ref、canonical main 或触发远端 Actions 前",
            "全部可复现的 build、test、lint、workflow validator 和 packaging dry-run",
            "本地无法等价验证的项目及原因",
            "不得用来进行第一轮试错或常规调试",
        )
        for capability in required_capabilities:
            self.assertIn(capability, skill)

    def test_coordinate_skill_preserves_latest_user_provenance_and_main_ssot(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "coordinate-concurrent-tasks" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_capabilities = (
            "### 用户所说的 SSOT",
            "远端 canonical `main`",
            "绝不是产物 SSOT",
            "### 把内容判定为偏差之前先追溯 provenance",
            "优先读取最新的用户直接指令",
            "不能单独证明谁作出了",
            "来自用户更晚的明确选择",
            "不得把 authority “修正”",
        )
        for capability in required_capabilities:
            self.assertIn(capability, skill)

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
