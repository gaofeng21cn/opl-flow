from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scripts.qualify_install import QualificationError, verify_matrix


VERSION = "0.1.29"
PREDECESSOR = "0.1.28"
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
        "discovery": {"skills": ["opl-flow", "coordinate-concurrent-tasks"], "new_codex_session_invocation": invocation},
    }
    if mode == "upgrade":
        profile["target_before_sha256"] = "sha256:" + "d" * 64
        value["predecessor_version"] = PREDECESSOR
    return value


class QualificationTests(unittest.TestCase):
    def verify(self, values: list[dict[str, object]]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for index, value in enumerate(values):
                path = Path(temp_dir) / f"{index}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            return verify_matrix(argparse.Namespace(
                expected_version=VERSION,
                expected_predecessor_version=PREDECESSOR,
                expected_source_commit=SOURCE_COMMIT,
                expected_digest=DIGEST,
                receipt=paths,
            ))

    def matrix(self) -> list[dict[str, object]]:
        return [
            receipt(platform, mode, "passed" if (platform, mode) == ("macos", "fresh") else "not_run")
            for platform in ("macos", "linux", "windows-wsl")
            for mode in ("fresh", "upgrade")
        ]

    def test_complete_matrix_passes(self) -> None:
        result = self.verify(self.matrix())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["receipt_count"], 6)

    def test_missing_platform_mode_fails(self) -> None:
        with self.assertRaisesRegex(QualificationError, "matrix is incomplete"):
            self.verify(self.matrix()[:-1])

    def test_new_session_invocation_is_required(self) -> None:
        values = self.matrix()
        for value in values:
            value["discovery"]["new_codex_session_invocation"] = "not_run"  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "new Codex session"):
            self.verify(values)

    def test_upgrade_requires_profile_preservation(self) -> None:
        values = self.matrix()
        values[1]["profile"]["preserved_distinct_preferences"] = False  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "preserve distinct"):
            self.verify(values)

    def test_core_must_not_depend_on_optional_adapters(self) -> None:
        values = self.matrix()
        values[0]["core"]["linear_configured"] = True  # type: ignore[index]
        with self.assertRaisesRegex(QualificationError, "without Linear or Fleet"):
            self.verify(values)


if __name__ == "__main__":
    unittest.main()
