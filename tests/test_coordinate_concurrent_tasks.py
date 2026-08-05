from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CoordinateConcurrentTasksTests(unittest.TestCase):
    def test_replacements_parallelize_cutover_without_dual_production_paths(self) -> None:
        skill = (
            REPO_ROOT / "skills" / "coordinate-concurrent-tasks" / "SKILL.md"
        ).read_text(encoding="utf-8")

        required_markers = (
            "successor 实现、真实 caller 切换、验收和 legacy 退役",
            "最小纵向链路证明 successor 可用并可回退",
            "在新路径上补强并批量删除旧实现",
            "不要把每个旧字段的清理串行化",
            "永久双写或 runtime fallback",
        )
        for marker in required_markers:
            self.assertIn(marker, skill)


if __name__ == "__main__":
    unittest.main()
