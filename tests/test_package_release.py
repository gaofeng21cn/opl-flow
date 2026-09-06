from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "opl-flow" / "scripts" / "package_release.py"
SPEC = importlib.util.spec_from_file_location("package_release", SCRIPT_PATH)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
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
        for fault in ("projection", "disabled", "visible", "bytes"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                args, package, status, skill = self.installed_fixture(Path(temporary))
                if fault == "projection":
                    status.update(installed_package_count=0, installed_carrier_readback=None)
                elif fault == "disabled":
                    status["installed_readiness"]["projection_callability"] = "disabled"
                elif fault == "visible":
                    status["configured_carrier"]["enabled"] = True
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


if __name__ == "__main__":
    unittest.main()
