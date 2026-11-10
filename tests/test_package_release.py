from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "opl-flow" / "scripts" / "package_release.py"
SPEC = importlib.util.spec_from_file_location("package_release", SCRIPT_PATH)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPT_PATH.parent), *sys.path]):
    SPEC.loader.exec_module(release)


class PackageReleaseTests(unittest.TestCase):
    def prepare_fixture(self, root: Path, *, capability: bool = False):
        package_id = "research-skills" if capability else "research-agent"
        owner_root = root / "owner"
        owner_root.mkdir()
        surface_kind = "opl_capability_package_manifest.v2" if capability else "opl_agent_package_manifest.v1"
        owner = {
            "surface_kind": surface_kind, "package_id": package_id, "version": "1.2.3",
            "source": "first_party_repo_local", "schema_ref": "owner/schema.json",
            "codex_surface": {
                "plugin_id": package_id,
                "configured_codex_plugin_carrier": {"plugin_selector": f"{package_id}@market"},
            },
            "capability_dependencies": [{"package_id": "provider", "required": True}],
        }
        if capability:
            owner["exports"] = {"core_skill_ids": ["core"], "all_skill_ids": ["core", "new-specialty"]}
            owner["consumer_profiles"] = {"research": {"required_export_ids": ["new-specialty"]}}
            owner["content_lock"] = {"paths": ["new-evidence.md"], "digest": "sha256:new"}
            owner["codex_surface"].update(interaction_mode="headless_internal", codex_default_exposure=False)
        else:
            owner["codex_surface"]["required_skill_ids"] = ["entry"]
            owner["domain_descriptor_ref"] = "domain.json"
            release.write_json(owner_root / "domain.json", {
                "domain_id": "current-domain",
                "standard_agent_interface": {
                    "runtime": {"runtime_domain_id": "current-runtime"},
                    "routing": {"explicit_aliases": ["current-alias"]},
                },
            })
        package_path = root / "framework/contracts/opl-framework/packages" / f"{package_id}.json"
        package_path.parent.mkdir(parents=True)
        previous = copy.deepcopy(owner)
        previous.update(
            version="1.2.2", source="first_party", schema_ref="framework/schema.json",
            source_repo=f"https://github.com/owner/{package_id}.git",
            capability_dependencies=[], retired_domain_field="stale",
            publication_source={"owner_package_manifest_ref": "contracts/package.json"},
        )
        previous["codex_surface"].update(required_skill_ids=["stale-skill"], carrier_source_commit="old")
        if capability:
            previous.update(
                exports={"core_skill_ids": ["old-core"]},
                consumer_profiles={"stale": {}}, content_lock={"paths": ["old.md"]},
                owner_package_descriptor_ref="opl-package.json",
                owner_package_manifest_ref="contracts/package.json",
            )
        else:
            previous["standard_agent_descriptor_projection"] = {
                "domain_id": "old", "runtime_domain_id": "old", "explicit_aliases": ["old"],
                "compatibility": {"registry_domain_id": "legacy", "owner_aliases": []},
            }
        release.write_json(package_path, previous)
        allowlist_path = root / "framework/contracts/opl-framework/package-payload-allowlists" / package_path.name
        allowlist_path.parent.mkdir(parents=True)
        release.write_json(allowlist_path, {
            "package_id": package_id, "plugin_id": package_id,
            "source_repo": previous["source_repo"], "source_root": ".", "paths": ["old.md", "opl-package.json"],
        })
        args = argparse.Namespace(package_id=package_id, owner_root=str(owner_root), framework_root=str(root / "framework"))
        return args, owner, package_path, allowlist_path

    @staticmethod
    def payload_command(argv: list[str], **_: object):
        manifest_path = Path(argv[argv.index("--manifest") + 1])
        manifest = release.read_json(manifest_path)
        surface = manifest["codex_surface"]
        output = manifest_path.parent / surface["plugin_payload_manifest_url"]
        output.parent.mkdir(exist_ok=True)
        release.write_json(output, {
            "package_id": manifest["package_id"], "package_version": manifest["version"],
            "source_commit": surface["carrier_source_commit"],
        })
        return subprocess.CompletedProcess(argv, 0, "", "")

    def initialize_framework_snapshot(self, args):
        root = Path(args.framework_root)
        for argv in (["init", "-q"], ["config", "user.name", "Fixture"],
                     ["config", "user.email", "fixture@example.com"], ["add", "."],
                     ["commit", "-qm", "Framework projection fixture"]):
            subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    def source_payload_command(self, argv, **kwargs):
        if argv[:2] == ["git", "archive"]:
            return subprocess.run(argv, **kwargs, check=True, capture_output=True, text=True)
        return self.payload_command(argv, **kwargs)

    def test_prepare_refreshes_owner_agent_and_headless_capability_fields(self) -> None:
        for capability in (False, True):
            with self.subTest(capability=capability), tempfile.TemporaryDirectory() as temporary:
                args, owner, path, allowlist_path = self.prepare_fixture(Path(temporary), capability=capability)
                with (
                    patch.object(release, "require_owner_release", return_value=(owner, "1.2.3", "a" * 40)),
                    patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                    patch.object(release, "command", side_effect=self.payload_command),
                ):
                    release.prepare(args)
                actual = release.read_json(path)
                self.assertEqual(actual["source"], "first_party")
                self.assertEqual(actual["schema_ref"], "framework/schema.json")
                self.assertEqual(actual["capability_dependencies"], owner["capability_dependencies"])
                self.assertNotIn("retired_domain_field", actual)
                if capability:
                    for field in ("exports", "consumer_profiles", "content_lock"):
                        self.assertEqual(actual[field], owner[field])
                    self.assertNotIn("required_skill_ids", actual["codex_surface"])
                    self.assertFalse(actual["codex_surface"]["codex_default_exposure"])
                    self.assertEqual(release.read_json(allowlist_path)["paths"], ["new-evidence.md", "opl-package.json"])
                else:
                    self.assertEqual(actual["standard_agent_descriptor_projection"]["domain_id"], "current-domain")
                    self.assertEqual(actual["standard_agent_descriptor_projection"]["explicit_aliases"], ["current-alias"])

    def test_prepare_keeps_repo_binding_and_does_not_write_failed_generation(self) -> None:
        for mismatch in ("owner", "projection", "allowlist", "plugin", "generator"):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temporary:
                args, owner, path, allowlist_path = self.prepare_fixture(Path(temporary))
                if mismatch == "owner":
                    owner["source_repo"] = "https://github.com/other/repo.git"
                elif mismatch in ("projection", "allowlist", "plugin"):
                    target = path if mismatch == "projection" else allowlist_path
                    data = release.read_json(target)
                    data["plugin_id" if mismatch == "plugin" else "source_repo"] = "wrong"
                    release.write_json(target, data)
                previous = path.read_bytes(), allowlist_path.read_bytes()
                with (
                    patch.object(release, "require_owner_release", return_value=(owner, "1.2.3", "a" * 40)),
                    patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                    patch.object(release, "command", side_effect=release.ReleaseError("generator failed")),
                    self.assertRaises(release.ReleaseError),
                ):
                    release.prepare(args)
                self.assertEqual(previous, (path.read_bytes(), allowlist_path.read_bytes()))

    def test_prepare_preserves_presentation_and_applies_explicit_owner_fields(self) -> None:
        central = {
            "software_type": "capability",
            "display_name_i18n": {"en-US": "Central name", "zh-CN": "中央名称"},
            "description_i18n": {"en-US": "Central description"},
            "home_shortcuts": [{"id": "open"}],
        }
        cases = (
            ({}, central),
            ({"presentation": {}}, central),
            ({"presentation": {"display_name_i18n": {"en-US": "Owner name"}}},
             {**central, "display_name_i18n": {"en-US": "Owner name"}}),
            ({"presentation": {"home_shortcuts": [], "description_i18n": {}}},
             {**central, "home_shortcuts": [], "description_i18n": {}}),
            ({"presentation": {"software_type": "", "display_name_i18n": None}},
             {**central, "software_type": "", "display_name_i18n": None}),
            ({"presentation": None}, None),
        )
        for capability in (False, True):
            for declared, expected in cases:
                with self.subTest(capability=capability, owner=declared), tempfile.TemporaryDirectory() as temporary:
                    args, owner, path, _ = self.prepare_fixture(Path(temporary), capability=capability)
                    previous = release.read_json(path)
                    previous["presentation"] = copy.deepcopy(central)
                    release.write_json(path, previous)
                    owner.update(copy.deepcopy(declared))

                    def generate(argv, **kwargs):
                        staged = release.read_json(Path(argv[argv.index("--manifest") + 1]))
                        self.assertEqual(staged["presentation"], expected)
                        return self.payload_command(argv, **kwargs)

                    with (
                        patch.object(release, "require_owner_release", return_value=(owner, "1.2.3", "a" * 40)),
                        patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                        patch.object(release, "command", side_effect=generate),
                    ):
                        release.prepare(args)
                    self.assertEqual(release.read_json(path)["presentation"], expected)
                    self.assertEqual(owner.get("presentation"), declared.get("presentation"))
                    self.assertEqual(previous["presentation"], central)

    def test_owner_projection_resolves_declared_json_pointer_and_locator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args, owner, path, _ = self.prepare_fixture(Path(temporary))
            owner_root = Path(args.owner_root).resolve()
            owner.pop("domain_descriptor_ref")
            previous = release.read_json(path)
            previous["standard_agent_descriptor_projection"]["source_ref"] = "domain.json"
            release.write_json(owner_root / "domain.json", {
                "domain_id": "new-domain",
                "standard_agent_interface": {"ref_kind": "repo_json_pointer", "ref": "interface.json#/interface"},
            })
            release.write_json(owner_root / "interface.json", {"interface": {
                "runtime": {"runtime_domain_id": "new-runtime"},
                "routing": {"explicit_aliases": ["new-alias"]},
            }})
            actual = release.owner_projection(owner, previous, owner_root)["standard_agent_descriptor_projection"]
            self.assertEqual(actual["runtime_domain_id"], "new-runtime")
            self.assertEqual(actual["explicit_aliases"], ["new-alias"])
            self.assertEqual(actual["interface_source_ref"], "interface.json#/interface")

    def test_prepare_source_isolated_output_preserves_identity_and_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            args, owner, package_path, allowlist_path = self.prepare_fixture(root)
            args.output_root = str(root / "source-projection")
            baseline = package_path.read_bytes(), allowlist_path.read_bytes()
            dependency = package_path.parent / "provider.json"
            dependency.write_text('{"package_id":"provider","version":"2.0.0"}')
            framework_commit = self.initialize_framework_snapshot(args)
            ignored = package_path.parent / "ignored-extra.json"
            ignored.write_text('{"package_id":"ignored-extra","version":"9.9.9"}')
            (Path(args.framework_root) / ".git/info/exclude").write_text("ignored-extra.json\n")
            with (
                patch.object(release, "require_canonical_checkout", return_value=framework_commit),
                patch.object(release, "require_owner_source", return_value=(owner, "1.2.3", "a" * 40)),
                patch.object(release, "require_owner_release", side_effect=AssertionError("release gate is not a source gate")),
                patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                patch.object(release, "command", side_effect=self.source_payload_command),
                patch.object(release, "git_value", side_effect=lambda repo, *argv: "" if argv[0] == "status" else "a" * 40 if repo == Path(args.owner_root) else framework_commit),
            ):
                result = release.prepare_source(args)
            output = Path(args.output_root)
            payload = output / "packages/payloads/research-agent-1.2.3.json"
            self.assertEqual(result["status"], "source_projection_ready")
            self.assertEqual(result["payload_sha256"], release.sha256_bytes(payload.read_bytes()))
            self.assertEqual(result["owner_source_commit"], "a" * 40)
            self.assertEqual(result["framework_source_commit"], framework_commit)
            self.assertEqual(result["plugin_selector"], "research-agent@market")
            self.assertFalse(result["publication_performed"])
            self.assertFalse(result["native_carrier_mutation"])
            self.assertEqual(result["installation_environment"]["OPL_MODULE_PATH_RESEARCHAGENT"], args.owner_root)
            self.assertEqual(result["package_projection_dir"], str(output / "packages"))
            self.assertEqual((output / "packages/provider.json").read_bytes(), dependency.read_bytes())
            self.assertFalse((output / "packages/ignored-extra.json").exists())
            self.assertEqual(baseline, (package_path.read_bytes(), allowlist_path.read_bytes()))
            self.assertTrue(all(Path(filename).is_file() for filename in result["updated_files"]))
            with self.assertRaisesRegex(release.ReleaseError, "must not already exist"):
                release.prepare_source(args)

    def test_prepare_source_rejects_checkout_output_and_keeps_failures_unpublished(self) -> None:
        for failure in ("owner-output", "framework-output", "generator", "source-drift", "framework-drift"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                args, owner, package_path, allowlist_path = self.prepare_fixture(root)
                output = root / "source-projection"
                if failure == "owner-output":
                    output = Path(args.owner_root) / "generated"
                if failure == "framework-output":
                    output = Path(args.framework_root) / "generated"
                args.output_root = str(output)
                baseline = package_path.read_bytes(), allowlist_path.read_bytes()
                framework_commit = self.initialize_framework_snapshot(args)
                def git_read(repo, *argv):
                    if argv[0] == "status":
                        return " M changed" if failure == "source-drift" or failure == "framework-drift" and repo == Path(args.framework_root) else ""
                    return "a" * 40 if repo == Path(args.owner_root) else framework_commit
                with (
                    patch.object(release, "require_canonical_checkout", return_value=framework_commit),
                    patch.object(release, "require_owner_source", return_value=(owner, "1.2.3", "a" * 40)),
                    patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                    patch.object(release, "command", side_effect=release.ReleaseError("generator failed") if failure == "generator" else self.source_payload_command),
                    patch.object(release, "git_value", side_effect=git_read),
                    self.assertRaises(release.ReleaseError),
                ):
                    release.prepare_source(args)
                self.assertFalse(output.exists())
                self.assertEqual(baseline, (package_path.read_bytes(), allowlist_path.read_bytes()))

    def test_source_gate_requires_fresh_clean_canonical_commit_without_tags(self) -> None:
        root = Path("/fixture/owner")
        manifest = {"package_id": "example", "version": "1.2.3", "codex_surface": {"plugin_id": "example"}}
        blobs = {"opl-package.json": manifest, ".codex-plugin/plugin.json": {"name": "example", "version": "1.2.3"}}
        for failure in (None, "dirty", "diverged"):
            with self.subTest(failure=failure):
                def git_read(_, *argv):
                    if argv[0] == "cat-file" or any("refs/tags" in arg for arg in argv):
                        self.fail("source preparation must not require a release tag")
                    if argv == ("status", "--porcelain"):
                        return " M changed" if failure == "dirty" else ""
                    if argv[0] == "show":
                        return release.json.dumps(blobs[argv[1].split(":", 1)[1]])
                    return ("b" if failure == "diverged" and argv[-1] == "origin/main" else "a") * 40
                with patch.object(release, "git_value", side_effect=git_read), patch.object(release, "command") as execute:
                    if failure:
                        with self.assertRaises(release.ReleaseError):
                            release.require_owner_source(root, "example", owner_manifest_ref="opl-package.json", source_root=".")
                    else:
                        self.assertEqual(release.require_owner_source(root, "example", owner_manifest_ref="opl-package.json", source_root="."), (manifest, "1.2.3", "a" * 40))
                        execute.assert_called_once_with(["git", "fetch", "origin", "main", "--tags", "--quiet"], cwd=root)

    def test_prepare_preserves_same_version_payload_bytes(self) -> None:
        for identical in (True, False):
            with self.subTest(identical=identical), tempfile.TemporaryDirectory() as temporary:
                args, owner, path, allowlist_path = self.prepare_fixture(Path(temporary))
                payload_path = path.parent / "payloads/research-agent-1.2.3.json"
                payload_path.parent.mkdir()
                release.write_json(payload_path, {
                    "package_id": args.package_id, "package_version": "1.2.3",
                    "source_commit": "a" * 40 if identical else "b" * 40,
                })
                previous = path.read_bytes(), allowlist_path.read_bytes(), payload_path.read_bytes()
                with (
                    patch.object(release, "require_owner_release", return_value=(owner, "1.2.3", "a" * 40)),
                    patch.object(release, "repo_slug", return_value=f"owner/{args.package_id}"),
                    patch.object(release, "command", side_effect=self.payload_command),
                ):
                    if identical:
                        release.prepare(args)
                    else:
                        with self.assertRaisesRegex(release.ReleaseError, "immutable payload"):
                            release.prepare(args)
                        self.assertEqual(previous[:2], (path.read_bytes(), allowlist_path.read_bytes()))
                self.assertEqual(previous[2], payload_path.read_bytes())

    def test_owner_release_uses_contract_and_carrier_paths_without_root_sidecar(self) -> None:
        root = Path("/fixture/owner")
        package_id = "obf"
        surface = {"plugin_id": "opl-bookforge", "configured_codex_plugin_carrier": {"plugin_selector": "opl-bookforge@market"}}
        manifest = {"package_id": package_id, "version": "1.2.3", "codex_surface": surface}
        blobs = {
            "contracts/opl_agent_package_manifest.json": manifest,
            "plugins/opl-bookforge/opl-package.json": manifest,
            "plugins/opl-bookforge/.codex-plugin/plugin.json": {"name": "opl-bookforge", "version": "1.2.3"},
        }
        def git_value(_: Path, *args: str):
            if args == ("status", "--porcelain"):
                return ""
            if args[0] == "cat-file":
                return "tag"
            if args[0] == "show":
                return release.json.dumps(blobs[args[1].split(":", 1)[1]])
            return "a" * 40
        with patch.object(release, "git_value", side_effect=git_value), patch.object(release, "command"):
            actual, version, commit = release.require_owner_release(
                root, package_id, owner_manifest_ref="contracts/opl_agent_package_manifest.json",
                source_root="plugins/opl-bookforge",
            )
            self.assertEqual((actual, version, commit), (manifest, "1.2.3", "a" * 40))
            blobs["plugins/opl-bookforge/.codex-plugin/plugin.json"]["version"] = "1.2.2"
            with self.assertRaisesRegex(release.ReleaseError, "plugin identity or version"):
                release.require_owner_release(
                    root, package_id, owner_manifest_ref="contracts/opl_agent_package_manifest.json",
                    source_root="plugins/opl-bookforge",
                )

    def test_repo_slug_accepts_https_scp_and_github_ssh_port(self) -> None:
        remotes = {
            "https://github.com/gaofeng21cn/opl-flow.git": "gaofeng21cn/opl-flow",
            "git@github.com:gaofeng21cn/opl-flow.git": "gaofeng21cn/opl-flow",
            "ssh://git@ssh.github.com:443/gaofeng21cn/one-person-lab.git": (
                "gaofeng21cn/one-person-lab"
            ),
        }
        for remote, expected in remotes.items():
            with self.subTest(remote=remote), patch.object(
                release, "git_value", return_value=remote
            ):
                self.assertEqual(release.repo_slug(Path("/fixture")), expected)

    def test_prepare_updates_current_framework_projection_without_legacy_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            owner_root = root / "owner"
            framework_root = root / "framework"
            owner_root.mkdir()
            package_path = (
                framework_root
                / "contracts/opl-framework/packages/opl-flow.json"
            )
            package_path.parent.mkdir(parents=True)
            release.write_json(
                package_path,
                {
                    "surface_kind": "opl_workflow_profile_package_manifest.v1",
                    "package_id": "opl-flow",
                    "version": "0.1.48",
                    "source_repo": "https://github.com/gaofeng21cn/opl-flow.git",
                    "publication_source": {"owner_package_manifest_ref": "contracts/workflow-policy.json"},
                    "codex_surface": {
                        "plugin_payload_manifest_url": "payloads/opl-flow-0.1.48.json",
                        "carrier_source_commit": "old-commit",
                    },
                },
            )
            allowlist_path = framework_root / "contracts/opl-framework/package-payload-allowlists/opl-flow.json"
            allowlist_path.parent.mkdir(parents=True)
            release.write_json(allowlist_path, {
                "package_id": "opl-flow", "plugin_id": "opl-flow",
                "source_repo": "https://github.com/gaofeng21cn/opl-flow.git",
                "source_root": ".",
            })
            payload_path = package_path.parent / "payloads/opl-flow-0.1.49.json"

            def generate_payload(
                argv: list[str], **_: object
            ) -> subprocess.CompletedProcess[str]:
                self.assertEqual(Path(argv[1]).name, "first-party-package-payload.mjs")
                # The current Framework CLI is strict and only accepts these inputs.
                parser = argparse.ArgumentParser()
                for flag in ("--manifest", "--allowlist", "--repo", "--source-commit"):
                    parser.add_argument(flag, required=True)
                parser.parse_args(argv[2:])
                staged_package = Path(argv[argv.index("--manifest") + 1])
                staged_payload = staged_package.parent / "payloads/opl-flow-0.1.49.json"
                staged_payload.parent.mkdir(parents=True)
                release.write_json(
                    staged_payload,
                    {
                        "package_id": "opl-flow",
                        "package_version": "0.1.49",
                        "source_commit": "new-commit",
                    },
                )
                return subprocess.CompletedProcess(argv, 0, "", "")

            args = argparse.Namespace(
                package_id="opl-flow",
                owner_root=str(owner_root),
                framework_root=str(framework_root),
            )
            owner_manifest = {
                "surface_kind": "opl_workflow_profile_package_manifest.v1",
                "package_id": "opl-flow",
                "version": "0.1.49",
                "source_repo": "https://github.com/gaofeng21cn/opl-flow.git",
                "codex_surface": {
                    "plugin_id": "opl-flow",
                    "configured_codex_plugin_carrier": {
                        "plugin_selector": "opl-flow@opl-flow",
                    },
                    "required_skill_ids": [
                        "opl-flow",
                        "software-development",
                        "manage-codex-tasks",
                    ],
                },
            }
            with (
                patch.object(
                    release,
                    "require_owner_release",
                    return_value=(owner_manifest, "0.1.49", "new-commit"),
                ),
                patch.object(release, "repo_slug", return_value="gaofeng21cn/opl-flow"),
                patch.object(release, "command", side_effect=generate_payload),
            ):
                result = release.prepare(args)

            package = release.read_json(package_path)
            self.assertEqual(package["version"], "0.1.49")
            self.assertEqual(
                package["codex_surface"]["plugin_payload_manifest_url"],
                "payloads/opl-flow-0.1.49.json",
            )
            self.assertEqual(
                package["codex_surface"]["carrier_source_commit"], "new-commit"
            )
            self.assertEqual(
                package["codex_surface"]["required_skill_ids"],
                ["opl-flow", "software-development", "manage-codex-tasks"],
            )
            self.assertEqual(
                package["codex_surface"]["configured_codex_plugin_carrier"],
                {"plugin_selector": "opl-flow@opl-flow"},
            )
            self.assertEqual(
                result["updated_files"], [str(package_path), str(payload_path)]
            )
            self.assertFalse(
                (
                    framework_root
                    / "contracts/opl-framework/bundled-full-runtime-package-catalog.json"
                ).exists()
            )

    def test_latest_stable_absence_is_distinct_from_registry_failure(self) -> None:
        missing = subprocess.CompletedProcess(
            ["oras"], 1, "", "Error response: manifest unknown"
        )
        with patch.object(release, "command", return_value=missing):
            self.assertEqual(release.latest_stable_predecessor("ghcr.io/x/y"), "none")

        failure = subprocess.CompletedProcess(["oras"], 1, "", "connection reset")
        with patch.object(release, "command", return_value=failure):
            with self.assertRaisesRegex(release.ReleaseError, "cannot read"):
                release.latest_stable_predecessor("ghcr.io/x/y")

    def test_registry_denial_requires_authenticated_publisher_resolution(self) -> None:
        denied = subprocess.CompletedProcess(["oras"], 1, "", "denied: requested access to the resource is denied")
        with patch.object(release, "command", return_value=denied):
            with self.assertRaisesRegex(release.ReleaseError, "cannot read"):
                release.latest_stable_predecessor("ghcr.io/owner/new-package")
            self.assertEqual(
                release.latest_stable_predecessor("ghcr.io/owner/new-package", resolve_in_publisher=True),
                "resolve-authenticated",
            )
        failed = subprocess.CompletedProcess(["oras"], 1, "", "connection reset")
        with patch.object(release, "command", return_value=failed):
            with self.assertRaisesRegex(release.ReleaseError, "cannot read"):
                release.latest_stable_predecessor("ghcr.io/owner/new-package", resolve_in_publisher=True)

    def test_publication_receipt_requires_resolved_matching_predecessor(self) -> None:
        digest = "sha256:" + "a" * 64
        receipt = {
            "status": "published_and_verified", "publication_request_id": "request",
            "package": {"package_id": "agent", "version": "1.0.0",
                        "owner_source_commit": "owner", "framework_source_commit": "framework"},
            "immutable": {"digest": digest},
            "latest_stable": {"digest": digest, "predecessor_digest": "none"},
            "attestations": {"status": "verified"},
        }
        args = dict(package_id="agent", version="1.0.0", owner_commit="owner",
                    framework_commit="framework", request_id="request")
        self.assertEqual(release.validate_receipt(receipt, expected_predecessor="resolve-authenticated", **args), digest)
        with self.assertRaisesRegex(release.ReleaseError, "predecessor differs"):
            release.validate_receipt(receipt, expected_predecessor=digest, **args)
        receipt["latest_stable"]["predecessor_digest"] = "resolve-authenticated"
        with self.assertRaisesRegex(release.ReleaseError, "no resolved predecessor"):
            release.validate_receipt(receipt, expected_predecessor="resolve-authenticated", **args)

    def test_profile_delta_reports_merge_without_writing_user_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            user_path = Path(temporary) / "AGENTS.md"
            user_path.write_text("user override\n", encoding="utf-8")
            result = release.profile_delta(
                ("old", b"old default\n"),
                ("new", b"new default\n"),
                user_path,
            )
            self.assertEqual(result["status"], "profile_merge_required")
            self.assertTrue(result["profile_merge_required"])
            self.assertIn("-old default", result["default_profile_diff"])
            self.assertEqual(user_path.read_text(encoding="utf-8"), "user override\n")
            self.assertFalse(result["automatic_write_performed"])

    def test_publish_approves_only_the_exact_release_environment(self) -> None:
        pending = [{
            "environment": {"id": 42, "name": "release-stable"},
            "current_user_can_approve": True,
        }]
        with patch.object(release, "command_json", side_effect=[pending, [{"id": 7}]]) as command:
            result = release.approve_release_environment("owner/repo", 123, "request-1")

        self.assertEqual(
            result,
            {"status": "approved", "environment": "release-stable", "environment_id": 42},
        )
        self.assertEqual(
            command.call_args_list[1].args[0],
            [
                "gh", "api", "--method", "POST",
                "repos/owner/repo/actions/runs/123/pending_deployments",
                "-F", "environment_ids[]=42",
                "-f", "state=approved",
                "-f", "comment=Authorized OPL Package publication request-1",
            ],
        )

    def test_activate_delegates_marketplace_refresh_to_one_framework_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "installed"
            for skill_id in ("opl-flow", "software-development", "manage-codex-tasks"):
                path = source / "skills" / skill_id
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text(f"# {skill_id}\n", encoding="utf-8")
            package_path = root / "contracts/opl-framework/packages/opl-flow.json"
            package_path.parent.mkdir(parents=True)
            release.write_json(
                package_path,
                {
                    "package_id": "opl-flow",
                    "version": "0.1.40",
                    "codex_surface": {
                        "required_skill_ids": [
                            "opl-flow",
                            "software-development",
                            "manage-codex-tasks",
                        ],
                        "configured_codex_plugin_carrier": {
                            "plugin_selector": "opl-flow@opl-flow"
                        },
                    },
                },
            )
            release.write_json(source / "opl-package.json", release.read_json(package_path))
            before = {
                "pluginId": "opl-flow@opl-flow",
                "version": "0.1.39",
                "enabled": True,
                "source": {"path": str(source)},
            }
            after = {**before, "version": "0.1.40"}
            calls: list[list[str]] = []

            def command_json(argv: list[str], **_: object) -> dict[str, object]:
                calls.append(argv)
                if argv[1:3] == ["packages", "update"]:
                    return {
                        "opl_agent_package_update": {
                            "status": "updated",
                            "target_version": "0.1.40",
                            "observed_version": "0.1.40",
                            "release_catalog_digest": "sha256:digest",
                        }
                    }
                return {
                    "opl_agent_package_status": {
                        "package_id": "opl-flow",
                        "configured_carrier": {
                            "package_id": "opl-flow", "status": "installed",
                            "installed_version": "0.1.40", "enabled": True,
                            "plugin_source_path": str(source),
                        },
                        "installed_readiness": {
                            "installed": True, "physical_status": "available", "callability": "callable",
                        },
                        "installed_carrier_readback": {
                            "lifecycle_authority": "carrier_owned", "version": "0.1.40",
                        },
                        "status": "available",
                        "installed_package_count": 1,
                        "operational_ready": True,
                        "launch_state": "ready",
                        "managed_policy_currentness": {"status": "current"},
                    }
                }

            args = argparse.Namespace(
                package_id="opl-flow",
                framework_root=str(root),
                codex_bin="codex",
                opl_bin="opl",
                user_profile=str(root / "AGENTS.md"),
                timeout=30,
            )
            with (
                patch.object(release, "plugin_entry", side_effect=[before, after]),
                patch.object(release, "installed_profile", return_value=(None, None)),
                patch.object(release, "command_json", side_effect=command_json),
            ):
                result = release.activate(args)

            self.assertEqual(
                calls,
                [
                    ["opl", "packages", "status", "--package-id", "opl-flow", "--json"],
                    ["opl", "packages", "update", "--package-id", "opl-flow", "--json"],
                    ["opl", "packages", "status", "--package-id", "opl-flow", "--json"],
                ],
            )
            self.assertEqual(result["status"], "installed_and_read_back")
            self.assertTrue(result["fresh_discovery_required"])
            self.assertEqual(result["missing_skill_ids"], [])
            self.assertEqual(result["package_status"]["operational_ready"], True)
            self.assertNotIn("opl_agent_package_status", result["package_status"])

    def installed_fixture(self, root: Path, package_id: str = "provider"):
        source = root / package_id
        skill = source / "skills/core/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_bytes(b"# Core\n")
        relative = "skills/core/SKILL.md"
        encoded = relative.encode()
        data = skill.read_bytes()
        digest = hashlib.sha256(len(encoded).to_bytes(8, "big") + encoded + len(data).to_bytes(8, "big") + data).hexdigest()
        package = {
            "package_id": package_id, "version": "1.2.3",
            "exports": {"core_skill_ids": ["core"]},
            "content_lock": {
                "algorithm": "sha256", "canonicalization": "ordered_path_length_file_length_bytes",
                "paths": [relative], "digest": f"sha256:{digest}",
            },
            "codex_surface": {
                "interaction_mode": "headless_internal", "codex_default_exposure": False,
                "configured_codex_plugin_carrier": {"plugin_selector": f"{package_id}@market"},
            },
        }
        release.write_json(source / "opl-package.json", package)
        status = {
            "package_id": package_id, "status": "available", "installed_package_count": 1,
            "operational_ready": True, "launch_state": "ready",
            "configured_carrier": {
                "package_id": package_id, "status": "installed", "installed_version": "1.2.3",
                "enabled": False, "plugin_source_path": str(source),
            },
            "installed_carrier_readback": {
                "kind": "codex_plugin", "identity": f"{package_id}@market", "version": "1.2.3",
                "enabled": False, "source_ref": str(source), "lifecycle_authority": "carrier_owned",
            },
            "installed_readiness": {
                "installed": True, "physical_status": "available",
                "callability": "disabled", "projection_callability": "callable",
            },
        }
        package_path = root / "contracts/opl-framework/packages" / f"{package_id}.json"
        package_path.parent.mkdir(parents=True, exist_ok=True)
        release.write_json(package_path, package)
        args = argparse.Namespace(
            package_id=package_id, framework_root=str(root), opl_bin="opl", codex_bin="codex",
            user_profile=str(root / "AGENTS.md"), timeout=30,
        )
        return args, package, status, skill

    def test_activate_installs_headless_carrier_instead_of_accepting_source_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args, _, status, _ = self.installed_fixture(Path(temporary))
            projected = copy.deepcopy(status)
            projected.update(status="not_installed", installed_package_count=0, operational_ready=False, installed_carrier_readback=None)
            with (
                patch.object(release, "plugin_entry") as plugin,
                patch.object(release, "command_json", side_effect=[
                    {"opl_agent_package_status": projected},
                    {"opl_agent_package_install": {"status": "installed"}},
                    {"opl_agent_package_status": status},
                ]) as commands,
            ):
                result = release.activate(args)
            self.assertEqual(commands.call_args_list[1].args[0], ["opl", "packages", "install", "--package-id", "provider", "--json"])
            self.assertEqual(result["status"], "installed_and_read_back")
            self.assertEqual(result["lifecycle_action"], "install")
            self.assertFalse(result["fresh_discovery_required"])
            self.assertEqual(result["installed_evidence"]["interaction_mode"], "headless_internal")
            plugin.assert_not_called()

    def test_activate_rejects_projection_only_uncallable_or_modified_headless_install(self) -> None:
        for fault in ("projection", "disabled", "visible", "bytes", "path_type"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                args, package, status, skill = self.installed_fixture(Path(temporary))
                if fault == "projection":
                    status.update(installed_package_count=0, installed_carrier_readback=None)
                elif fault == "disabled":
                    status["installed_readiness"]["projection_callability"] = "disabled"
                elif fault == "visible":
                    status["configured_carrier"]["enabled"] = True
                elif fault == "path_type":
                    package["content_lock"]["paths"] = [42]
                    release.write_json(skill.parents[2] / "opl-package.json", package)
                else:
                    skill.write_bytes(b"tampered\n")
                with self.assertRaises(release.ReleaseError):
                    release.installed_package_evidence(status, package)

    def test_activate_preserves_real_installed_readiness_debt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args, _, status, _ = self.installed_fixture(Path(temporary))
            status.update(status="attention_needed", operational_ready=False, launch_state="package_unavailable")
            with patch.object(release, "command_json", side_effect=[
                {"opl_agent_package_status": status},
                {"opl_agent_package_update": {"status": "updated"}},
                {"opl_agent_package_status": status},
            ]):
                result = release.activate(args)
            self.assertEqual(result["status"], "installed_with_readiness_debt")
            self.assertFalse(result["package_status"]["operational_ready"])

    def test_activate_installs_source_only_dependency_and_consumes_fresh_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args, package, status, _ = self.installed_fixture(root, "consumer")
            _, _, provider_status, _ = self.installed_fixture(root)
            package["capability_dependencies"] = [{"package_id": "provider", "required": True}]
            release.write_json(root / "contracts/opl-framework/packages/consumer.json", package)
            status["package_dependency_readiness"] = {"dependencies": [{
                "package_id": "provider", "required": True, "status": "current", "installed_version": "1.2.3",
            }]}
            projected = copy.deepcopy(provider_status)
            projected.update(installed_package_count=0, installed_carrier_readback=None, operational_ready=False)
            with patch.object(release, "command_json", side_effect=[
                {"opl_agent_package_status": status},
                {"opl_agent_package_update": {"status": "updated"}},
                {"opl_agent_package_status": status},
                {"opl_agent_package_status": projected},
                {"opl_agent_package_install": {"status": "installed"}},
                {"opl_agent_package_status": provider_status},
                {"opl_agent_package_status": status},
            ]) as commands:
                result = release.activate(args)
            self.assertEqual(commands.call_args_list[4].args[0], ["opl", "packages", "install", "--package-id", "provider", "--json"])
            self.assertEqual(result["installed_dependency_evidence"][0]["consumer_binding"]["status"], "current")
            self.assertIsNotNone(result["installed_dependency_evidence"][0]["content_digest"])


class PackagePublishTests(unittest.TestCase):
    framework_commit = "a" * 40
    caller_commit = "b" * 40
    source_commit = "c" * 40
    digest = "sha256:" + "d" * 64
    predecessor = "sha256:" + "e" * 64
    framework_repo = "gaofeng21cn/one-person-lab"
    private_repo = "gaofeng21cn/opl-capital-compass"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.calls: list[list[str]] = []
        self.private = False
        self.dispatched = False
        self.unknown_dispatch = False
        self.run_head = self.framework_commit
        self.receipt_error = None
        self.receipt_status = "verified"
        self.owner_private = True
        self.owner_identity = self.private_repo
        self.wrapper = ""
        self.registry_calls = []
        self.is_framework_ancestor = True
        self.pinned_package_drift = False
        self.pinned_presentation_drift = False
        self.pinned_payload_drift = False
        self.private_predecessor = "resolve-authenticated"

    def fixture(self, *, private: bool = False) -> argparse.Namespace:
        self.private = private
        self.dispatched = False
        package_id = "occ" if private else "research-agent"
        owner_repo = self.private_repo if private else "gaofeng21cn/research-agent"
        namespace = "one-person-lab-private-packages" if private else "one-person-lab-packages"
        self.image = f"ghcr.io/gaofeng21cn/{namespace}/{package_id}"
        self.run_repo = owner_repo if private else self.framework_repo
        self.run_head = self.caller_commit if private else self.framework_commit
        self.package = {
            "package_id": package_id, "version": "1.2.3",
            "source_repo": f"https://github.com/{owner_repo}.git",
            "visibility": "authorized_only" if private else "public",
            "codex_surface": {
                "carrier_source_commit": self.source_commit,
                "plugin_payload_manifest_url": f"payloads/{package_id}-1.2.3.json",
                "configured_codex_plugin_carrier": {"publication_ref": f"{self.image}:latest-stable"},
            },
        }
        if private:
            self.package.update(
                access_policy_ref=f"github-package:gaofeng21cn/{namespace}/{package_id}",
                credential_provider="github_packages",
            )
            self.wrapper = """name: Publish private OCC Package
run-name: OCC ${{ inputs.expected_package_version }} / ${{ inputs.publication_request_id }}
on:
  workflow_dispatch:
    inputs:
      expected_package_version:
        required: true
        type: string
      expected_owner_source_commit:
        required: true
        type: string
      expected_latest_stable_predecessor:
        required: true
        type: string
      publication_request_id:
        required: true
        type: string
permissions:
  contents: read
  packages: write
  id-token: write
jobs:
  publish-package:
    if: github.ref == 'refs/heads/main'
    uses: gaofeng21cn/one-person-lab/.github/workflows/publish-package.yml@FRAMEWORK_COMMIT
    with:
      package_id: occ
      expected_package_version: ${{ inputs.expected_package_version }}
      expected_owner_source_commit: ${{ inputs.expected_owner_source_commit }}
      expected_framework_source_commit: FRAMEWORK_COMMIT
      expected_latest_stable_predecessor: ${{ inputs.expected_latest_stable_predecessor }}
      publication_request_id: ${{ inputs.publication_request_id }}
    secrets: inherit
""".replace("FRAMEWORK_COMMIT", self.framework_commit)
        path = self.root / f"contracts/opl-framework/packages/{package_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        release.write_json(path, self.package)
        self.receipt = {
            "status": "published_and_verified", "publication_request_id": "test-publication",
            "package": {
                "package_id": package_id, "version": "1.2.3",
                "owner_source_commit": self.source_commit,
                "framework_source_commit": self.framework_commit,
            },
            "immutable": {"ref": f"{self.image}:1.2.3", "digest": self.digest},
            "latest_stable": {
                "ref": f"{self.image}:latest-stable", "digest": self.digest,
                "predecessor_digest": self.predecessor,
            },
            "attestations": {
                "status": "verified", "subject": f"{self.image}@{self.digest}",
                "certificate_identity": None if private else "https://github.com/gaofeng21cn/one-person-lab/.github/workflows/publish-package.yml@refs/heads/main",
            },
            "workflow": {"repository": self.run_repo, "run_id": "123", "run_attempt": "1"},
        }
        return argparse.Namespace(package_id=package_id, framework_root=str(self.root), request_id="test-publication")

    def command(self, argv, **kwargs):
        self.calls.append(list(argv))
        result = ""
        if argv[0] == "git":
            if argv[1:3] == ["rev-parse", "HEAD"] or argv[1:3] == ["rev-parse", "origin/main"]:
                result = self.framework_commit
            elif argv[1:4] == ["remote", "get-url", "origin"]:
                result = f"https://github.com/{self.framework_repo}.git"
            elif argv[1:3] == ["merge-base", "--is-ancestor"]:
                return subprocess.CompletedProcess(argv, 0 if self.is_framework_ancestor else 1, "", "")
            elif argv[1] == "show":
                commit, path = argv[2].split(":", 1)
                if path.endswith(f"packages/{self.package['package_id']}.json"):
                    result = copy.deepcopy(self.package)
                    if commit != self.framework_commit and self.pinned_package_drift:
                        result["version"] = "1.2.2"
                    if commit != self.framework_commit and self.pinned_presentation_drift:
                        result["presentation"] = {"display_name_i18n": {"en-US": "Previous catalog name"}}
                else:
                    self.assertIn("/payloads/", path)
                    result = {"source_commit": self.source_commit}
                    if commit != self.framework_commit and self.pinned_payload_drift:
                        result["source_commit"] = "f" * 40
            elif argv[1] not in ("fetch", "status"):
                self.fail(f"Unexpected git command: {argv}")
        elif argv[:4] == ["oras", "manifest", "fetch", "--descriptor"]:
            result = {"digest": self.digest if self.dispatched else self.predecessor}
        elif argv[:3] == ["gh", "workflow", "run"]:
            self.dispatched = True
            if self.unknown_dispatch:
                return subprocess.CompletedProcess(argv, 1, "", "dispatch outcome unknown")
            result = f"https://github.com/{self.run_repo}/actions/runs/123"
        elif argv[:3] == ["gh", "run", "list"]:
            result = [{"databaseId": 123, "displayTitle": "Publish test-publication", "headSha": self.run_head}]
        elif argv[:3] == ["gh", "run", "view"]:
            result = {
                "status": "completed", "conclusion": "success", "headSha": self.run_head,
                "url": f"https://github.com/{self.run_repo}/actions/runs/123", "jobs": [],
            }
        elif argv[:3] == ["gh", "run", "download"]:
            release.write_json(Path(argv[argv.index("--dir") + 1]) / "publication-receipt.json", self.receipt)
        elif argv[:2] == ["gh", "api"]:
            endpoint = argv[2]
            if endpoint.endswith("/pending_deployments"):
                result = []
            elif endpoint == f"repos/{self.private_repo}":
                result = {"private": self.owner_private, "default_branch": "main", "full_name": self.owner_identity}
            elif endpoint == f"repos/{self.private_repo}/git/ref/heads/main":
                result = {"object": {"sha": self.caller_commit}}
            elif endpoint == f"repos/{self.private_repo}/contents/.github/workflows/publish-package.yml?ref={self.caller_commit}":
                result = {"encoding": "base64", "content": base64.b64encode(self.wrapper.encode()).decode()}
            else:
                self.fail(f"Unexpected GitHub API request: {endpoint}")
        elif argv[0] != "cosign":
            self.fail(f"Unexpected external command: {argv}")
        if not isinstance(result, str):
            result = release.json.dumps(result)
        return subprocess.CompletedProcess(argv, 0, result, "")

    def publish(self, args):
        with ExitStack() as stack:
            stack.enter_context(patch.object(release, "command", side_effect=self.command))
            watch = stack.enter_context(patch.object(
                release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", ""),
            ))
            if self.private:
                stack.enter_context(patch.object(release, "private_registry_readback", side_effect=self.registry_readback))
            result = release.publish(args)
        self.watch_calls = [call.args[0] for call in watch.call_args_list]
        return result

    def registry_readback(self, framework_root, package, *, action, receipt_selector=None):
        self.assertEqual(framework_root, self.root)
        self.assertEqual(package, self.package)
        self.registry_calls.append(action)
        if action == "predecessor":
            return {"predecessor": self.private_predecessor}
        self.assertEqual(action, "receipt")
        self.assertEqual(receipt_selector, {
            "publicationRequestId": "test-publication",
            "workflowRepository": self.run_repo,
            "workflowRunId": "123",
        })
        if self.receipt_error:
            raise release.ReleaseError(self.receipt_error)
        return {"status": self.receipt_status, "subject": f"{self.image}@{self.digest}", "receipt": self.receipt}

    def dispatch(self):
        return next(call for call in self.calls if call[:3] == ["gh", "workflow", "run"])

    def test_public_publish_keeps_framework_dispatch_and_actions_receipt(self) -> None:
        result = self.publish(self.fixture())
        dispatch = self.dispatch()
        self.assertEqual(dispatch[dispatch.index("--repo") + 1], self.framework_repo)
        fields = {dispatch[index + 1].split("=", 1)[0]: dispatch[index + 1].split("=", 1)[1]
                  for index, value in enumerate(dispatch) if value == "-f"}
        self.assertEqual(fields["expected_framework_source_commit"], self.framework_commit)
        self.assertEqual(fields["expected_owner_source_commit"], self.source_commit)
        self.assertEqual(fields["package_id"], "research-agent")
        self.assertTrue(any(call[:3] == ["gh", "run", "download"] for call in self.calls))
        self.assertEqual(len([call for call in self.calls if call[:2] == ["cosign", "verify-attestation"]]), 2)
        self.assertEqual(result["status"], "published_and_verified")
        self.assertEqual(result["digest"], self.digest)

    def test_private_wrapper_must_bind_private_owner_package_and_framework_before_dispatch(self) -> None:
        for fault in ("owner_visibility", "owner_identity", "package_identity", "framework_pin", "framework_input", "missing_input"):
            with self.subTest(fault=fault):
                self.calls.clear()
                args = self.fixture(private=True)
                self.owner_private = fault != "owner_visibility"
                self.owner_identity = "gaofeng21cn/other-owner" if fault == "owner_identity" else self.private_repo
                if fault == "package_identity":
                    self.wrapper = self.wrapper.replace("package_id: occ", "package_id: other")
                elif fault == "framework_pin":
                    self.wrapper = self.wrapper.replace(f".yml@{self.framework_commit}", f".yml@{'f' * 40}")
                elif fault == "framework_input":
                    self.wrapper = self.wrapper.replace(f"expected_framework_source_commit: {self.framework_commit}",
                                                        f"expected_framework_source_commit: {'f' * 40}")
                elif fault == "missing_input":
                    self.wrapper = self.wrapper.replace("      publication_request_id:\n        required: true\n        type: string\n", "")
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)
                self.assertFalse(any(call[:3] == ["gh", "workflow", "run"] for call in self.calls))

    def test_public_receipt_must_match_request_framework_and_predecessor(self) -> None:
        for fault in ("request", "framework", "predecessor"):
            with self.subTest(fault=fault):
                args = self.fixture()
                if fault == "request":
                    self.receipt["publication_request_id"] = "different-request"
                elif fault == "framework":
                    self.receipt["package"]["framework_source_commit"] = "f" * 40
                else:
                    self.receipt["latest_stable"]["predecessor_digest"] = "sha256:" + "f" * 64
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)

    def test_private_publish_uses_owner_wrapper_and_shared_registry_receipt(self) -> None:
        result = self.publish(self.fixture(private=True))
        dispatch = self.dispatch()
        self.assertEqual(dispatch[dispatch.index("--repo") + 1], self.private_repo)
        self.assertEqual(dispatch[dispatch.index("--ref") + 1], "main")
        fields = {dispatch[index + 1].split("=", 1)[0]: dispatch[index + 1].split("=", 1)[1]
                  for index, value in enumerate(dispatch) if value == "-f"}
        self.assertEqual(fields, {
            "expected_package_version": "1.2.3", "expected_owner_source_commit": self.source_commit,
            "expected_latest_stable_predecessor": "resolve-authenticated",
            "publication_request_id": "test-publication",
        })
        self.assertIn([
            "gh", "api", f"repos/{self.private_repo}/contents/.github/workflows/publish-package.yml?ref={self.caller_commit}",
        ], self.calls)
        self.assertEqual(self.registry_calls, ["predecessor", "receipt"])
        self.assertFalse(any(call[:3] == ["gh", "run", "download"] for call in self.calls))
        self.assertFalse(any(call[0] in ("cosign", "oras") for call in self.calls))
        self.assertEqual(result["owner_source_commit"], self.source_commit)
        self.assertEqual(result["framework_source_commit"], self.framework_commit)
        self.assertEqual(result["publisher_source_commit"], self.caller_commit)
        self.assertEqual(result["publisher_repository"], self.private_repo)
        self.assertEqual(result["status"], "published_and_verified")

    def test_private_unknown_dispatch_reconciles_run_at_wrapper_caller_commit(self) -> None:
        args = self.fixture(private=True)
        self.unknown_dispatch = True
        result = self.publish(args)
        runs = [call for call in self.calls if call[:3] == ["gh", "run", "list"]]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0][runs[0].index("--repo") + 1], self.private_repo)
        self.assertEqual(len([call for call in self.calls if call[:3] == ["gh", "workflow", "run"]]), 1)
        self.assertEqual(result["run_id"], 123)

    def test_private_wrapper_may_pin_unchanged_package_at_canonical_framework_ancestor(self) -> None:
        for presentation_drift in (False, True):
            with self.subTest(presentation_drift=presentation_drift):
                args = self.fixture(private=True)
                pin = "f" * 40
                self.wrapper = self.wrapper.replace(self.framework_commit, pin)
                self.pinned_presentation_drift = presentation_drift
                self.receipt["package"]["framework_source_commit"] = pin
                result = self.publish(args)
                self.assertIn(["git", "merge-base", "--is-ancestor", pin, self.framework_commit], self.calls)
                self.assertEqual(result["framework_source_commit"], pin)
                self.assertEqual(result["publisher_source_commit"], self.caller_commit)
                self.assertEqual(result["owner_source_commit"], self.source_commit)

    def test_private_wrapper_rejects_unrelated_pin_or_changed_package_inputs(self) -> None:
        for fault in ("ancestry", "package", "payload"):
            with self.subTest(fault=fault):
                args = self.fixture(private=True)
                self.wrapper = self.wrapper.replace(self.framework_commit, "f" * 40)
                self.is_framework_ancestor = fault != "ancestry"
                self.pinned_package_drift = fault == "package"
                self.pinned_payload_drift = fault == "payload"
                self.calls.clear()
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)
                self.assertFalse(any(call[:3] == ["gh", "workflow", "run"] for call in self.calls))

    def test_run_head_must_match_public_framework_or_private_wrapper_caller(self) -> None:
        for private in (False, True):
            with self.subTest(private=private):
                args = self.fixture(private=private)
                self.run_head = self.source_commit
                self.registry_calls.clear()
                self.calls.clear()
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)
                self.assertNotIn("receipt", self.registry_calls)
                self.assertFalse(any(call[:3] == ["gh", "run", "download"] for call in self.calls))

    def test_private_receipt_must_bind_request_framework_predecessor_and_workflow(self) -> None:
        for fault in ("request", "framework", "predecessor", "workflow_repo", "workflow_run"):
            with self.subTest(fault=fault):
                args = self.fixture(private=True)
                if fault == "request":
                    self.receipt["publication_request_id"] = "different-request"
                elif fault == "framework":
                    self.receipt["package"]["framework_source_commit"] = "f" * 40
                elif fault == "predecessor":
                    self.private_predecessor = self.predecessor
                    self.receipt["latest_stable"]["predecessor_digest"] = "sha256:" + "f" * 64
                elif fault == "workflow_repo":
                    self.receipt["workflow"]["repository"] = self.framework_repo
                else:
                    self.receipt["workflow"]["run_id"] = "999"
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)

    def test_private_shared_verifier_failure_does_not_report_publication_success(self) -> None:
        for fault in ("error", "unverified"):
            with self.subTest(fault=fault):
                args = self.fixture(private=True)
                self.receipt_error = "private receipt signature verification failed" if fault == "error" else None
                self.receipt_status = "failed" if fault == "unverified" else "verified"
                with self.assertRaises(release.ReleaseError):
                    self.publish(args)
                self.assertFalse(any(call[:3] == ["gh", "run", "download"] for call in self.calls))


class PrivateRegistryAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "package.json").write_text('{"type":"module"}\n')
        source = self.root / "src/adapters/integration/software-sources.ts"
        source.parent.mkdir(parents=True)
        source.write_text("""export function resolvePackageSourceCredentialProvider() {
  const mode = process.env.OPL_TEST_SOURCE_MODE;
  if (mode === 'missing') return null;
  return { enabled: mode !== 'disabled', credential_handle: mode === 'no_handle' ? null : 'env:OPL_GITHUB_PACKAGES_TOKEN' };
}
""")
        provider = self.root / "src/adapters/integration/agent-package-registry-parts/package-registry-access-provider.ts"
        provider.parent.mkdir(parents=True)
        provider.write_text("""import fs from 'node:fs';
export function credentialForGithubPackages() {
  fs.writeFileSync(process.env.OPL_TEST_CREDENTIAL_LOG, 'called');
  return { username: 'fixture', token: 'synthetic-private-test-token' };
}
""")
        verifier = self.root / "scripts/oci-publication-receipt-readback.mjs"
        verifier.parent.mkdir()
        verifier.write_text("""export function verifyPrivatePackagePublication() {
  throw new Error('synthetic-private-test-token must stay inside the adapter');
}
""")
        bindir = self.root / "bin"
        bindir.mkdir()
        oras = bindir / "oras"
        oras.write_text("""#!/bin/sh
printf '%s\\n' "$DOCKER_CONFIG" >> "$OPL_TEST_REGISTRY_LOG"
printf '%s\\n' '{"digest":"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"}'
""")
        oras.chmod(0o755)
        self.credential_log = self.root / "credential-reader.log"
        self.registry_log = self.root / "registry.log"
        self.env = {
            **os.environ, "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", ""),
            "OPL_TEST_CREDENTIAL_LOG": str(self.credential_log),
            "OPL_TEST_REGISTRY_LOG": str(self.registry_log),
        }
        self.package = {
            "package_id": "occ", "version": "1.2.3", "source_repo": "https://github.com/gaofeng21cn/opl-capital-compass.git",
            "credential_provider": "github_packages",
            "access_policy_ref": "github-package:gaofeng21cn/one-person-lab-private-packages/occ",
            "codex_surface": {
                "carrier_source_commit": "c" * 40,
                "configured_codex_plugin_carrier": {
                    "publication_ref": "ghcr.io/gaofeng21cn/one-person-lab-private-packages/occ:latest-stable",
                },
            },
        }

    def run_adapter(self, *, action: str, mode: str = "enabled"):
        registry_config = self.root / "registry-config"
        registry_config.mkdir(mode=0o700, exist_ok=True)
        return subprocess.run(
            ["node", "--input-type=module", "-e", release.PRIVATE_REGISTRY_ADAPTER, str(self.root)],
            input=json.dumps({
                "action": action, "package": self.package, "registryConfigRoot": str(registry_config),
                "receiptSelector": {"publicationRequestId": "request-1", "workflowRepository": "owner/repo", "workflowRunId": "123"},
            }),
            capture_output=True, text=True, check=False,
            env={**self.env, "OPL_TEST_SOURCE_MODE": mode},
        )

    def test_disabled_or_missing_source_never_reads_credentials_or_registry(self) -> None:
        for mode in ("disabled", "missing", "no_handle"):
            with self.subTest(mode=mode):
                result = self.run_adapter(action="predecessor", mode=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.credential_log.exists())
                self.assertFalse(self.registry_log.exists())

    def test_predecessor_defers_authenticated_registry_read_to_publisher(self) -> None:
        result = self.run_adapter(action="predecessor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"predecessor": "resolve-authenticated"})
        self.assertTrue(self.credential_log.exists())
        self.assertFalse(self.registry_log.exists())

    def test_receipt_failure_redacts_provider_data_and_removes_temporary_config(self) -> None:
        result = self.run_adapter(action="receipt")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("synthetic-private-test-token", result.stdout + result.stderr)
        self.assertTrue(self.credential_log.exists())
        configs = self.registry_log.read_text().splitlines()
        self.assertTrue(configs)
        for config in configs:
            self.assertFalse(Path(config).exists(), config)

    def test_receipt_selects_the_requested_verified_run(self) -> None:
        (self.root / "scripts/oci-publication-receipt-readback.mjs").write_text("""import fs from 'node:fs';
export function verifyPrivatePackagePublication(input, env) {
  if (input.includeReceipt !== true || input.publicationRequestId !== 'request-1'
    || input.workflowRepository !== 'owner/repo' || input.workflowRunId !== '123') throw new Error('Missing request selection');
  if ((fs.statSync(env.DOCKER_CONFIG).mode & 0o777) !== 0o700
    || (fs.statSync(`${env.DOCKER_CONFIG}/config.json`).mode & 0o777) !== 0o600) throw new Error('Unsafe config permissions');
  return { status: 'verified', receipt: { publication_request_id: input.publicationRequestId } };
}
""")
        result = self.run_adapter(action="receipt")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["receipt"]["publication_request_id"], "request-1")
        self.assertNotIn("synthetic-private-test-token", result.stdout + result.stderr)
        for config in self.registry_log.read_text().splitlines():
            self.assertFalse(Path(config).exists(), config)

    def test_python_owner_removes_temporary_config_after_adapter_timeout(self) -> None:
        paths = []

        def timeout(argv, **kwargs):
            temporary = Path(json.loads(kwargs["input_text"])["registryConfigRoot"])
            self.assertTrue(temporary.is_dir())
            (temporary / "config.json").write_text("synthetic credential config")
            paths.append(temporary)
            raise release.ReleaseError("command timed out")

        with patch.object(release, "command", side_effect=timeout), self.assertRaisesRegex(release.ReleaseError, "timed out"):
            release.private_registry_readback(self.root, self.package, action="receipt")
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())


class EnvironmentApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = "owner/repo"
        self.pending_endpoint = f"repos/{self.repo}/actions/runs/123/pending_deployments"
        self.environment_endpoint = f"repos/{self.repo}/environments/release-stable"
        self.deployment = {
            "environment": {"id": 42, "name": "release-stable"},
            "current_user_can_approve": False,
        }
        self.environment = {"id": 42, "name": "release-stable", "protection_rules": [{"type": "branch_policy"}]}
        self.pending_states = [[self.deployment]]
        self.pending_reads = 0
        self.calls = []
        self.posts = []
        self.approval_error = None
        self.completed_conclusion = None

    def command_json(self, argv, **kwargs):
        self.calls.append(argv)
        if "POST" in argv:
            self.assertEqual(argv[:5], ["gh", "api", "--method", "POST", self.pending_endpoint])
            self.posts.append(argv)
            if self.approval_error:
                raise release.ReleaseError(self.approval_error)
            return [{"id": 7}]
        if argv == ["gh", "api", self.pending_endpoint]:
            state = self.pending_states[min(self.pending_reads, len(self.pending_states) - 1)]
            self.pending_reads += 1
            return state
        if argv == ["gh", "api", self.environment_endpoint]:
            return self.environment
        if argv[:4] == ["gh", "run", "view", "123"]:
            self.assertEqual(argv[argv.index("--repo") + 1], self.repo)
            if self.completed_conclusion:
                return {"status": "completed", "conclusion": self.completed_conclusion}
            pending = self.pending_states[min(self.pending_reads - 1, len(self.pending_states) - 1)]
            return {"status": "waiting" if pending else "in_progress", "conclusion": None}
        self.fail(f"unexpected publication operation: {argv}")

    def approve(self):
        with patch.object(release, "command_json", side_effect=self.command_json), patch.object(release.time, "sleep"):
            return release.approve_release_environment(self.repo, 123, "request-1")

    def test_automatic_environment_pending_continues_without_approval_post(self) -> None:
        for rules in ([], [{"type": "branch_policy"}]):
            with self.subTest(protection_rules=rules):
                self.setUp()
                self.environment["protection_rules"] = rules
                result = self.approve()
                self.assertEqual(result["status"], "automatic_pending")
                self.assertEqual(result["environment_id"], 42)
                self.assertIn(["gh", "api", self.environment_endpoint], self.calls)
                self.assertEqual(self.posts, [])

    def test_unapprovable_reviewers_and_unverified_environment_still_stop(self) -> None:
        for fault in ("reviewers", "wrong-id", "wrong-name", "missing-rules"):
            with self.subTest(fault=fault):
                self.setUp()
                if fault == "reviewers":
                    self.environment["protection_rules"] = [{
                        "type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {"id": 9}}],
                    }]
                elif fault == "wrong-id":
                    self.environment["id"] = 99
                elif fault == "wrong-name":
                    self.environment["name"] = "production"
                else:
                    self.environment.pop("protection_rules")
                with self.assertRaises(release.ReleaseError):
                    self.approve()
                self.assertEqual(self.posts, [])

    def test_unknown_approval_is_reconciled_by_readback_without_second_post(self) -> None:
        cases = (("command timed out", True, None), ("command returned invalid JSON", False, "success"))
        for failure, can_approve_after_write, conclusion in cases:
            with self.subTest(failure=failure):
                self.setUp()
                self.deployment["current_user_can_approve"] = True
                after_write = {**self.deployment, "current_user_can_approve": can_approve_after_write}
                self.pending_states = [[self.deployment], [after_write], []]
                self.approval_error = failure
                self.completed_conclusion = conclusion
                result = self.approve()
                self.assertEqual(result["status"], "approval_reconciled")
                self.assertEqual(result["environment_id"], 42)
                self.assertEqual(len(self.posts), 1)
                self.assertGreaterEqual(self.pending_reads, 3)

    def test_unresolved_approval_stops_without_reposting(self) -> None:
        self.deployment["current_user_can_approve"] = True
        self.approval_error = "command timed out"
        with self.assertRaises(release.ReleaseError):
            self.approve()
        self.assertEqual(len(self.posts), 1)
        self.assertGreater(self.pending_reads, 1)

    def test_failed_or_cancelled_run_cannot_confirm_unknown_approval(self) -> None:
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion):
                self.setUp()
                self.deployment["current_user_can_approve"] = True
                self.approval_error = "command timed out"
                self.pending_states = [[self.deployment], []]
                self.completed_conclusion = conclusion
                with self.assertRaises(release.ReleaseError):
                    self.approve()
                self.assertEqual(len(self.posts), 1)

    def test_other_pending_environment_is_never_approved(self) -> None:
        self.deployment["environment"]["name"] = "production"
        self.deployment["current_user_can_approve"] = True
        with self.assertRaisesRegex(release.ReleaseError, "unexpected pending deployment"):
            self.approve()
        self.assertEqual(self.posts, [])


if __name__ == "__main__":
    unittest.main()
