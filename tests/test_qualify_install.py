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
SKILLS_0_1_29 = ["coordinate-concurrent-tasks", "opl-flow"]
SKILLS_0_1_30 = [
    "coordinate-concurrent-tasks",
    "develop-and-deliver",
    "opl-fleet",
    "opl-flow",
    "recover-codex-tasks",
    "task-mode-gate",
]


def receipt(
    platform: str,
    mode: str,
    invocation: str = "not_run",
    *,
    version: str = VERSION,
    skills: list[str] | None = None,
) -> dict[str, object]:
    profile: dict[str, object] = {
        "initial_state": "absent" if mode == "fresh" else "existing",
        "target_after_sha256": "sha256:" + "c" * 64,
        "preserved_distinct_preferences": mode == "upgrade",
        "review_packet_status": "not_required",
        "rollback_available": mode == "upgrade",
    }
    value: dict[str, object] = {
        "schema": "opl_flow_install_qualification_receipt.v1",
        "status": "passed",
        "observed_at": "2026-07-31T12:00:00Z",
        "platform": {"family": platform, "install_mode": mode, "os_version": "test", "arch": "test"},
        "package": {"id": "opl-flow", "version": version, "owner_source_commit": SOURCE_COMMIT, "publication_digest": DIGEST},
        "carrier": {
            "owner_route": f"opl packages {'install' if mode == 'fresh' else 'update'} opl-flow",
            "installed_version": version,
            "installed_source_commit": SOURCE_COMMIT,
            "readback_status": "current",
        },
        "profile": profile,
        "core": {"status": "current", "linear_configured": False, "fleet_configured": False},
        "discovery": {
            "skills": SKILLS_0_1_30 if skills is None else skills,
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
        expected_version: str = VERSION,
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for index, value in enumerate(values):
                path = Path(temp_dir) / f"{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            args = argparse.Namespace(
                expected_version=expected_version,
                expected_predecessor_version=PREDECESSOR,
                expected_source_commit=SOURCE_COMMIT,
                expected_digest=DIGEST,
                receipt=paths,
                trigger=triggers or [],
            )
            if legacy_full_matrix:
                return verify_matrix(args)
            return verify_qualification(args)

    def matrix(
        self,
        *,
        version: str = VERSION,
        skills: list[str] | None = None,
    ) -> list[dict[str, object]]:
        return [
            receipt(
                platform,
                mode,
                "passed" if (platform, mode) == ("macos", "fresh") else "not_run",
                version=version,
                skills=skills,
            )
            for platform in ("macos", "linux", "windows-wsl")
            for mode in ("fresh", "upgrade")
        ]

    def test_complete_matrix_passes(self) -> None:
        result = self.verify(self.matrix(), legacy_full_matrix=True)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receipt_count"], 6)
        self.assertEqual(result["qualification_level"], "system-certification")

    def test_0_1_29_uses_its_release_bound_skill_set(self) -> None:
        values = self.matrix(version="0.1.29", skills=SKILLS_0_1_29)
        result = self.verify(
            values,
            triggers=["first-supported-release"],
            expected_version="0.1.29",
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receipt_count"], 6)

    def test_unknown_release_skill_set_fails_closed(self) -> None:
        values = [
            receipt("linux", mode, version="0.1.31")
            for mode in ("fresh", "upgrade")
        ]
        with self.assertRaisesRegex(QualificationError, "no declared core Skill set"):
            self.verify(values, expected_version="0.1.31")

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

    def test_upgrade_requires_profile_rollback(self) -> None:
        values = self.matrix()
        values[1]["profile"]["rollback_available"] = False  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "upgrade profile rollback must be available"):
            self.verify(values, legacy_full_matrix=True)

    def test_profile_rollback_availability_must_be_boolean(self) -> None:
        values = self.matrix()
        values[0]["profile"]["rollback_available"] = "unknown"  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "profile rollback availability must be boolean"):
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
