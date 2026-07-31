from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.qualify_install import (
    QualificationError,
    qualification_plan,
    verify_matrix,
    verify_qualification,
)


VERSION = "0.1.30"
PREDECESSOR = "0.1.24"
SOURCE_COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def receipt(platform: str, mode: str, invocation: str = "not_run") -> dict[str, object]:
    profile: dict[str, object] = {
        "initial_state": "absent" if mode == "fresh" else "existing",
        "target_after_sha256": "sha256:" + "c" * 64,
        "preserved_distinct_preferences": mode == "upgrade",
        "review_packet_status": "not_required",
        "rollback_available": True,
    }
    value: dict[str, object] = {
        "schema": "opl_flow_install_qualification_receipt.v1",
        "status": "passed",
        "observed_at": "2026-07-31T12:00:00Z",
        "platform": {"family": platform, "install_mode": mode, "os_version": "test", "arch": "test"},
        "package": {"id": "opl-flow", "version": VERSION, "owner_source_commit": SOURCE_COMMIT, "publication_digest": DIGEST},
        "carrier": {
            "owner_route": f"opl packages {'install' if mode == 'fresh' else 'update'} opl-flow",
            "installed_version": VERSION,
            "installed_source_commit": SOURCE_COMMIT,
            "readback_status": "current",
        },
        "profile": profile,
        "core": {"status": "current", "linear_configured": False, "fleet_configured": False},
        "discovery": {
            "skills": [
                "coordinate-concurrent-tasks",
                "develop-and-deliver",
                "opl-flow",
                "recover-codex-tasks",
                "task-mode-gate",
            ],
            "new_codex_session_invocation": invocation,
        },
    }
    if mode == "upgrade":
        profile["target_before_sha256"] = "sha256:" + "d" * 64
        value["predecessor_version"] = PREDECESSOR
    return value


class QualificationTests(unittest.TestCase):
    def verify(
        self,
        values: list[dict[str, object]],
        triggers: list[str] | None = None,
        legacy_full_matrix: bool = False,
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for index, value in enumerate(values):
                path = Path(temp_dir) / f"{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            args = argparse.Namespace(
                expected_version=VERSION,
                expected_predecessor_version=PREDECESSOR,
                expected_source_commit=SOURCE_COMMIT,
                expected_digest=DIGEST,
                receipt=paths,
                trigger=triggers or [],
            )
            if legacy_full_matrix:
                return verify_matrix(args)
            return verify_qualification(args)

    def matrix(self) -> list[dict[str, object]]:
        return [
            receipt(platform, mode, "passed" if (platform, mode) == ("macos", "fresh") else "not_run")
            for platform in ("macos", "linux", "windows-wsl")
            for mode in ("fresh", "upgrade")
        ]

    def test_complete_matrix_passes(self) -> None:
        result = self.verify(self.matrix(), legacy_full_matrix=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receipt_count"], 6)
        self.assertEqual(result["qualification_level"], "system-certification")

    def test_routine_release_uses_one_reference_platform(self) -> None:
        values = [receipt("linux", "fresh"), receipt("linux", "upgrade")]
        result = self.verify(values)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receipt_count"], 2)
        self.assertEqual(result["new_codex_session_invocation_count"], 0)

    def test_routine_release_rejects_cross_platform_receipts(self) -> None:
        values = [receipt("linux", "fresh"), receipt("macos", "upgrade")]
        with self.assertRaisesRegex(QualificationError, "one reference platform"):
            self.verify(values)

    def test_routine_release_rejects_system_trigger(self) -> None:
        values = [receipt("linux", "fresh"), receipt("linux", "upgrade")]
        with self.assertRaisesRegex(QualificationError, "system-certification matrix is incomplete"):
            self.verify(values, ["carrier-contract-changed"])

    def test_missing_platform_mode_fails(self) -> None:
        with self.assertRaisesRegex(QualificationError, "system-certification matrix is incomplete"):
            self.verify(self.matrix()[:-1], legacy_full_matrix=True)

    def test_new_session_invocation_is_required(self) -> None:
        values = self.matrix()
        for value in values:
            value["discovery"]["new_codex_session_invocation"] = "not_run"  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "new Codex session"):
            self.verify(values, legacy_full_matrix=True)

    def test_upgrade_requires_profile_preservation(self) -> None:
        values = self.matrix()
        values[1]["profile"]["preserved_distinct_preferences"] = False  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "preserve distinct"):
            self.verify(values, legacy_full_matrix=True)

    def test_core_must_not_depend_on_optional_adapters(self) -> None:
        values = self.matrix()
        values[0]["core"]["linear_configured"] = True  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "without Linear or Fleet"):
            self.verify(values, legacy_full_matrix=True)

    def test_plan_defaults_to_routine_release(self) -> None:
        result = qualification_plan([])
        self.assertEqual(result["qualification_level"], "routine-release")
        self.assertEqual(result["requirements"]["platform_scope"], "one-reference-platform")

    def test_change_trigger_selects_system_certification(self) -> None:
        result = qualification_plan(["profile-mutation-contract-changed"])
        self.assertEqual(result["qualification_level"], "system-certification")
        self.assertEqual(result["requirements"]["platform_scope"], ["macos", "linux", "windows-wsl"])

    def test_unknown_trigger_fails_closed(self) -> None:
        with self.assertRaisesRegex(QualificationError, "unsupported"):
            qualification_plan(["ordinary-skill-content-changed"])


if __name__ == "__main__":
    unittest.main()
