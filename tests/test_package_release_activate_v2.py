import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_package_release import release


class ExactReleaseActivationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.catalog = self.root / "catalog"
        self.packages = self.catalog / "packages"
        (self.packages / "extensions").mkdir(parents=True)
        (self.packages / "payloads").mkdir()
        self.args = argparse.Namespace(package_id="example", framework_root=str(self.root / "framework"),
                                       catalog_root=str(self.catalog), opl_bin="opl", timeout=60,
                                       user_profile=str(self.root / "user-profile"))
        self.commit = "a" * 40
        self.digest = "sha256:" + "b" * 64
        self.version = "1.2.3"
        rel = "payloads/example-1.2.3.json"
        self.payload = self.packages / rel
        release.write_json(self.payload, {"package_format": "v2", "package_id": "example", "package_version": self.version,
            "source_commit": self.commit, "content_lock": {"digest": self.digest}})
        release.write_json(self.packages / "extensions/example.json", {
            "package_id": "example", "version": "1.0.0",
            "v2_release": {"version": self.version, "source_commit": self.commit, "payload_manifest_ref": rel,
                           "payload_sha256": release.sha256_bytes(self.payload.read_bytes())},
        })
        self.installed = {"package_id": "example", "version": self.version, "content_digest": self.digest,
                          "enabled": True, "install_path": str(self.root / "installed"), "origin": "opl",
                          "install_mode": "release", "carrier_synced": True}
        self.features = ["pack.ensure.exact-release"]
        self.disk_digest = self.digest
        self.calls = []
        canonical = patch.object(release, "canonical_catalog_commit", return_value="c" * 40)
        canonical.start()
        self.addCleanup(canonical.stop)

    def execute(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[1] == "--version":
            return {"api_version": "2.0", "features": self.features}
        if argv[1:3] == ["pack", "ensure"]:
            self.assertEqual(argv[3:], ["example", "--release-version", self.version, "--release-commit", self.commit,
                                        "--release-digest", self.digest, "--json"])
            return {"status": "reconciled", "package_id": "example", "changed": True}
        if argv[1:4] == ["pack", "inspect", "example"]:
            return {"installed": self.installed}
        if argv[1:4] == ["pack", "inspect", self.installed["install_path"]]:
            return {"lock": {"digest": self.disk_digest, "lock": {"git_commit": self.commit}},
                    "manifest": {"identity": {"id": "example"}}}
        self.fail(f"unexpected {argv}")

    def test_exact_release_requires_new_cli_and_verified_disk_bytes(self):
        with patch.object(release, "command_json", side_effect=self.execute):
            self.assertEqual(release.activate(self.args)["version"], "1.2.3")
            self.features.clear()
            self.calls.clear()
            with self.assertRaisesRegex(release.ReleaseError, "pack.ensure.exact-release"):
                release.activate(self.args)
            self.assertEqual(len(self.calls), 1)
            self.features.append("pack.ensure.exact-release")
            self.disk_digest = "sha256:" + "d" * 64
            with self.assertRaisesRegex(release.ReleaseError, "Installed Package files differ"):
                release.activate(self.args)

    def test_changed_catalog_payload_stops_before_pack_mutation(self):
        self.payload.write_bytes(self.payload.read_bytes() + b" ")
        with patch.object(release, "command_json", side_effect=self.execute):
            with self.assertRaisesRegex(release.ReleaseError, "payload differs"):
                release.activate(self.args)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
