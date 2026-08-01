from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import plistlib
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/opl_fleet.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("opl_fleet", SCRIPT)
assert SPEC and SPEC.loader
fleet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fleet
SPEC.loader.exec_module(fleet)

TEST_CONTROL_COMMIT = "c" * 40


def receipt(node_id: str = "studio-primary") -> dict[str, object]:
    return {
        "schema": "codex_fleet_receipt.v1",
        "node_id": node_id,
        "hostname_s": node_id,
        "platform": "darwin",
        "architecture": "arm64",
        "state": "CURRENT",
        "drift": [],
        "owner_actions": [],
        "control_commit": "a" * 40,
        "runner_commit": "b" * 40,
        "updated_at": "2026-07-26T00:00:00+00:00",
    }


def inventory(node_id: str = "studio-primary") -> dict[str, object]:
    return {
        "schema": "codex_fleet_inventory.v1",
        "node_id": node_id,
        "observed_at": "2026-07-27T00:00:00+00:00",
        "host": {
            "system": "windows",
            "os_name": "Windows 11 Pro",
            "os_version": "10.0.26200",
            "build": "26200",
            "manufacturer": "Example",
            "model": "Compute Box",
            "model_identifier": None,
        },
        "execution": {
            "kind": "wsl",
            "os_name": "Ubuntu",
            "os_version": "24.04",
            "kernel": "6.6.0-microsoft",
            "architecture": "x86_64",
        },
        "hardware": {
            "cpu_model": "Example CPU",
            "logical_cores": 16,
            "memory_bytes": 64 * 1024**3,
            "gpus": [
                {
                    "name": "Example GPU",
                    "memory_bytes": 24 * 1024**3,
                    "driver_version": "32.0.16.1074",
                }
            ],
        },
        "storage": {
            "scope": "execution-home",
            "total_bytes": 1024**4,
            "free_bytes": 512 * 1024**3,
        },
        "baseline": {
            "codex": {
                "ready": True,
                "kind": "windows_app_wsl",
                "version": "1.2.3",
            },
            "ssh": {"installed": True, "listening": True},
            "tailscale": {
                "installed": True,
                "online": True,
                "version": "1.84.0",
                "owner": "windows",
            },
        },
        "software": {
            "git": {"present": True, "version": "git version 2.50.0"},
            "docker": {"present": True, "version": "Docker version 28.0.0"},
        },
        "specialized_software": [
            {
                "id": "gpu-fan-management",
                "purpose": "GPU fan and thermal management",
                "name": "Fan Control",
                "version": "V230",
            }
        ],
    }


def dispatchable_inventory(node_id: str) -> dict[str, object]:
    payload = inventory(node_id)
    payload["observed_at"] = (
        fleet.dt.datetime.now(fleet.dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )
    payload["capabilities"] = {
        "power": {"source": "ac"},
        "gui": {"interactive_session": False, "idle_seconds": None},
        "workload": {"busy": False, "thermal_state": "nominal"},
    }
    payload["scheduling"] = {
        "requires_ac": False,
        "power_ok": True,
        "preferred_for": ["gpu-compute"],
        "occupancy_required": True,
        "idle_threshold_seconds": 900,
        "interactive_session": False,
        "interactive_busy": False,
        "idle_seconds": None,
        "busy": False,
        "storage_ok": True,
        "thermal_ok": True,
        "eligible": True,
    }
    return payload


def admission(
    now: fleet.dt.datetime,
    *,
    required: list[str] | None = None,
    min_memory_gb: int = 0,
) -> dict[str, object]:
    return {
        "checked_at": now.astimezone(fleet.dt.timezone.utc).isoformat(),
        "inventory_age_seconds": 0,
        "requirements": sorted(required or []),
        "min_memory_gb": min_memory_gb,
        "power_ok": True,
        "storage_ok": True,
        "thermal_ok": True,
        "interactive_busy": False,
        "busy": False,
        "work_volume_ready": True,
    }


def lease_binding(
    now: fleet.dt.datetime,
    *,
    role: str | None = None,
    required: list[str] | None = None,
    min_memory_gb: int = 0,
) -> dict[str, object]:
    return {
        "role": role,
        "control_revision": TEST_CONTROL_COMMIT,
        "admission": admission(
            now,
            required=required,
            min_memory_gb=min_memory_gb,
        ),
    }


def fictional_node_policy(labels: list[str]) -> dict[str, object]:
    return {
        "approved": True,
        "display_name": "Fictional Windows Node",
        "availability_policy": "on_demand",
        "labels": labels,
        "notes": [],
        "scheduling": {
            "requires_ac": False,
            "min_free_gb": 100,
            "occupancy_required": True,
            "idle_threshold_seconds": 900,
            "preferred_for": ["test-workload"],
            "work_volume_required": False,
        },
    }


def fictional_registry() -> dict[str, object]:
    return {
        "schema": "codex_fleet_nodes.v1",
        "nodes": {
            "fictional-gpu-a": fictional_node_policy(
                [
                    "gpu",
                    "hyperv",
                    "windows",
                    "windows-clean-guest-reserve",
                    "wsl",
                ]
            ),
            "fictional-gpu-b": fictional_node_policy(
                ["gpu", "windows", "wsl"]
            ),
        },
        "specialized_software": [],
        "runner_roles": {
            "fictional-gpu-role": ["fictional-gpu-a", "fictional-gpu-b"],
            "fictional-reserve-role": ["fictional-gpu-a"],
            "fictional-runner-role": ["fictional-gpu-a"],
        },
        "runner_role_workloads": {
            "fictional-reserve-role": ["guest", "vm"],
        },
        "runner_bindings": {
            "fictional-runner-role": {
                "launch_mode": "windows-session-task",
                "min_memory_gb": 32,
                "node_id": "fictional-gpu-a",
                "repository": "example/fleet-fixture",
                "required_features": ["windows", "wsl"],
                "runner_name": "fictional-windows-runner",
            },
        },
        "desired_unregistered": [],
    }


def write_pet_source(root: Path) -> tuple[dict[str, object], dict[str, str]]:
    source = root / "assets/pets/fixture-pet"
    source.mkdir(parents=True)
    metadata = {
        "id": "fixture-pet",
        "displayName": "Fixture Pet",
        "description": "test pet",
        "spriteVersionNumber": 2,
        "spritesheetPath": "spritesheet.webp",
    }
    (source / "pet.json").write_text(json.dumps(metadata), encoding="utf-8")
    (source / "spritesheet.webp").write_bytes(b"test-webp")
    digests = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in fleet.PET_FILES
    }
    manifest = {
        "schema": "codex_fleet_pet_manifest.v1",
        "pets": [{"id": "fixture-pet", "files": digests}],
    }
    (root / "assets/pets/manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    spec = {"user_assets": {"pets_manifest": "assets/pets/manifest.json"}}
    return spec, digests


def git(repository: Path, *arguments: str) -> str:
    return fleet.run(["git", "-C", str(repository), *arguments]).stdout.strip()


def commit_file(repository: Path, content: str, message: str) -> str:
    (repository / "tracked.txt").write_text(content, encoding="utf-8")
    git(repository, "add", "tracked.txt")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def repository_fixture(
    root: Path,
    *,
    default_branch: str = "main",
) -> tuple[Path, Path, Path]:
    remote = root / "demo.git"
    fleet.run(
        ["git", "init", "--bare", f"--initial-branch={default_branch}", str(remote)]
    )
    seed = root / "seed"
    fleet.run(["git", "init", f"--initial-branch={default_branch}", str(seed)])
    git(seed, "config", "user.name", "Fleet Test")
    git(seed, "config", "user.email", "fleet@example.invalid")
    commit_file(seed, "one\n", "initial")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", default_branch)
    workspace = root / "workspace"
    workspace.mkdir()
    checkout = workspace / "demo"
    fleet.run(["git", "clone", str(remote), str(checkout)])
    git(checkout, "config", "user.name", "Fleet Test")
    git(checkout, "config", "user.email", "fleet@example.invalid")
    return seed, workspace, checkout


class CodexFleetTests(unittest.TestCase):
    def test_repository_remote_parser_accepts_only_configured_owner(self) -> None:
        self.assertEqual(
            fleet.github_repository_from_remote(
                "git@github.com:example/opl-flow.git",
                expected_owner="example",
            ),
            "example/opl-flow",
        )
        self.assertIsNone(
            fleet.github_repository_from_remote(
                "https://github.com/another/opl-flow.git",
                expected_owner="example",
            )
        )

    def test_repository_sync_fast_forwards_clean_main(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed, workspace, checkout = repository_fixture(root)
            expected = commit_file(seed, "two\n", "second")
            git(seed, "push", "origin", "main")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
            actual = git(checkout, "rev-parse", "HEAD")
        self.assertEqual(report["state"], "CURRENT")
        self.assertEqual(report["repositories"][0]["state"], "UPDATED")
        self.assertEqual(report["repositories"][0]["local_commit"], expected)
        self.assertEqual(actual, expected)

    def test_repository_sync_accepts_remote_default_master(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, workspace, checkout = repository_fixture(root, default_branch="master")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
        entry = report["repositories"][0]
        self.assertEqual(entry["default_branch"], "master")
        self.assertEqual(entry["branch"], "master")
        self.assertEqual(entry["state"], "CURRENT")
        self.assertEqual(checkout, workspace / "demo")

    def test_repository_sync_prefers_branch_upstream_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, workspace, checkout = repository_fixture(root)
            git(checkout, "remote", "rename", "origin", "gh-https")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=False,
                    apply=False,
                    expected_owner=None,
                )
        entry = report["repositories"][0]
        self.assertEqual(entry["state"], "CURRENT")
        self.assertEqual(entry["remote"], "gh-https")

    def test_repository_sync_preserves_dirty_main(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed, workspace, checkout = repository_fixture(root)
            original = git(checkout, "rev-parse", "HEAD")
            commit_file(seed, "two\n", "second")
            git(seed, "push", "origin", "main")
            (checkout / "tracked.txt").write_text("local edit\n", encoding="utf-8")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
            actual = git(checkout, "rev-parse", "HEAD")
            content = (checkout / "tracked.txt").read_text()
        entry = report["repositories"][0]
        self.assertEqual(entry["state"], "DIRTY")
        self.assertEqual(entry["behind"], 1)
        self.assertEqual(actual, original)
        self.assertEqual(content, "local edit\n")

    def test_repository_sync_preserves_task_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, workspace, checkout = repository_fixture(root)
            git(checkout, "remote", "rename", "origin", "gh-https")
            git(checkout, "checkout", "-b", "task/example")
            task_head = commit_file(checkout, "task\n", "task")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
            actual = git(checkout, "rev-parse", "HEAD")
        entry = report["repositories"][0]
        self.assertEqual(entry["state"], "TASK_BRANCH")
        self.assertEqual(entry["remote"], "gh-https")
        self.assertEqual(entry["branch"], "task/example")
        self.assertEqual(actual, task_head)

    def test_repository_sync_preserves_diverged_main(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed, workspace, checkout = repository_fixture(root)
            local_head = commit_file(checkout, "local\n", "local")
            commit_file(seed, "remote\n", "remote")
            git(seed, "push", "origin", "main")
            with mock.patch.object(fleet, "STATE_ROOT", root / "state"):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
            actual = git(checkout, "rev-parse", "HEAD")
        entry = report["repositories"][0]
        self.assertEqual(entry["state"], "DIVERGED")
        self.assertEqual(entry["ahead"], 1)
        self.assertEqual(entry["behind"], 1)
        self.assertEqual(actual, local_head)

    def test_repository_sync_reports_fetch_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, workspace, checkout = repository_fixture(root)
            expected = git(checkout, "rev-parse", "HEAD")
            original = fleet.git_value

            def timeout_fetch(
                repository: Path,
                arguments: list[str],
                **kwargs: object,
            ) -> object:
                if arguments[:2] == ["fetch", "--prune"]:
                    raise fleet.subprocess.TimeoutExpired(arguments, 1)
                return original(repository, arguments, **kwargs)

            with mock.patch.object(fleet, "git_value", side_effect=timeout_fetch):
                report = fleet.reconcile_workspace_repositories(
                    root=workspace,
                    fetch=True,
                    apply=True,
                    expected_owner=None,
                )
            actual = git(checkout, "rev-parse", "HEAD")
        self.assertEqual(report["state"], "ATTENTION")
        self.assertEqual(report["repositories"][0]["state"], "FETCH_TIMEOUT")
        self.assertEqual(actual, expected)

    def test_repository_apply_requires_fresh_fetch(self) -> None:
        with self.assertRaisesRegex(fleet.FleetError, "requires a fresh fetch"):
            fleet.reconcile_workspace_repositories(fetch=False, apply=True)

    def test_reconcile_marks_repository_attention_without_leaking_names(self) -> None:
        expected = receipt()
        with (
            mock.patch.object(fleet, "run"),
            mock.patch.object(fleet, "control_commit", return_value="a" * 40),
            mock.patch.object(fleet, "checkout_commit", return_value="c" * 40),
            mock.patch.object(fleet, "update_flow", return_value="c" * 40),
            mock.patch.object(fleet, "update_control", return_value="a" * 40),
            mock.patch.object(fleet, "restart_after_flow_update"),
            mock.patch.object(
                fleet,
                "manifest",
                return_value={
                    "repository": "example/fleet",
                    "runner": {},
                    "receipt_workflow": "receipt.yml",
                },
            ),
            mock.patch.object(fleet, "reconcile_pets"),
            mock.patch.object(fleet, "install_runner", return_value="b" * 40),
            mock.patch.object(
                fleet,
                "runner_call",
                return_value={"ok": True, "result": {"ok": True, "drift": []}},
            ),
            mock.patch.object(fleet, "build_receipt", return_value=expected),
            mock.patch.object(
                fleet,
                "reconcile_workspace_repositories",
                return_value={
                    "state": "ATTENTION",
                    "repositories": [{"repository": "private/name"}],
                },
            ),
            mock.patch.object(fleet, "collect_inventory", return_value={}),
            mock.patch.object(fleet, "node_registry", return_value={}),
            mock.patch.object(fleet, "atomic_json"),
        ):
            result = fleet.reconcile(report=False, install_required=False)
        self.assertEqual(result["state"], "UPDATE_REQUIRED")
        self.assertEqual(
            result["drift"],
            ["development-repositories.attention"],
        )
        self.assertNotIn("private/name", json.dumps(result))

    def test_effective_codex_home_uses_windows_profile_in_wsl(self) -> None:
        def fake_run(command: list[str], **_: object) -> object:
            if command[0].endswith("cmd.exe"):
                return fleet.subprocess.CompletedProcess(
                    command, 0, "C:\\Users\\owner\r\n", ""
                )
            return fleet.subprocess.CompletedProcess(
                command, 0, "/mnt/c/Users/owner\n", ""
            )

        with (
            mock.patch.dict(fleet.os.environ, {}, clear=True),
            mock.patch.object(fleet.platform, "release", return_value="WSL2-microsoft"),
            mock.patch.object(fleet.Path, "is_file", return_value=True),
            mock.patch.object(fleet.shutil, "which", return_value="/usr/bin/wslpath"),
            mock.patch.object(fleet, "run", side_effect=fake_run),
        ):
            result = fleet.effective_codex_home()
        self.assertEqual(result, Path("/mnt/c/Users/owner/.codex"))

    def test_reconcile_pets_backs_up_replaces_and_reaches_fixed_point(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            control = root / "control"
            control.mkdir()
            spec, digests = write_pet_source(control)
            codex_home = root / "codex"
            old = codex_home / "pets/fixture-pet"
            old.mkdir(parents=True)
            (old / "pet.json").write_text("old", encoding="utf-8")
            (old / "spritesheet.webp").write_bytes(b"old")
            state = root / "state"

            first = fleet.reconcile_pets(
                spec,
                codex_home=codex_home,
                control_root=control,
                state_root=state,
            )
            backup_count = len(list((state / "backups/pets").iterdir()))
            second = fleet.reconcile_pets(
                spec,
                codex_home=codex_home,
                control_root=control,
                state_root=state,
            )

            self.assertEqual(first, ["fixture-pet"])
            self.assertEqual(second, [])
            self.assertEqual(backup_count, 1)
            self.assertTrue(fleet.pet_files_match(old, digests))

    def test_reconcile_pets_rolls_back_failed_install_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            control = root / "control"
            control.mkdir()
            spec, _ = write_pet_source(control)
            codex_home = root / "codex"
            target = codex_home / "pets/fixture-pet"
            target.mkdir(parents=True)
            (target / "pet.json").write_text("old", encoding="utf-8")
            (target / "spritesheet.webp").write_bytes(b"old")
            original = {path.name: path.read_bytes() for path in target.iterdir()}
            real_match = fleet.pet_files_match
            calls = 0

            def fail_installed(path: Path, expected: dict[str, str]) -> bool:
                nonlocal calls
                calls += 1
                if calls == 3:
                    return False
                return real_match(path, expected)

            with mock.patch.object(fleet, "pet_files_match", side_effect=fail_installed):
                with self.assertRaisesRegex(fleet.FleetError, "installed pet"):
                    fleet.reconcile_pets(
                        spec,
                        codex_home=codex_home,
                        control_root=control,
                        state_root=root / "state",
                    )

            restored = {path.name: path.read_bytes() for path in target.iterdir()}
        self.assertEqual(restored, original)

    def test_pet_manifest_rejects_changed_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec, _ = write_pet_source(root)
            (root / "assets/pets/fixture-pet/spritesheet.webp").write_bytes(b"changed")
            with self.assertRaisesRegex(fleet.FleetError, "digest changed"):
                fleet.pet_manifest(spec, control_root=root)

    def test_node_id_is_stable_and_path_safe(self) -> None:
        self.assertEqual(fleet.normalize_node_id("Studio Primary.local"), "studio-primary-local")
        with self.assertRaises(fleet.FleetError):
            fleet.normalize_node_id("../../owner")

    def test_run_tolerates_non_utf8_owner_output(self) -> None:
        result = fleet.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(bytes([0xb3]))",
            ]
        )
        self.assertEqual(result.stdout, "\ufffd")

    def test_flow_update_restarts_into_new_script_bytes(self) -> None:
        with mock.patch.object(fleet.os, "execv") as restart:
            fleet.restart_after_flow_update("a" * 40, "b" * 40)
        restart.assert_called_once_with(
            sys.executable,
            [sys.executable, str(SCRIPT.resolve()), *sys.argv[1:]],
        )

        with mock.patch.object(fleet.os, "execv") as restart:
            fleet.restart_after_flow_update("a" * 40, "a" * 40)
        restart.assert_not_called()

    def test_receipt_rejects_unapproved_fields(self) -> None:
        payload = receipt()
        payload["local_path"] = "should-not-be-accepted"
        with self.assertRaisesRegex(fleet.FleetError, "fields"):
            fleet.validate_receipt(payload)

    def test_record_receipt_generates_status_without_payload_bytes(self) -> None:
        payload = receipt()
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(
                fleet, "node_registry", return_value=fictional_registry()
            ):
                destination = fleet.record_receipt(root, encoded)
            status = (root / "STATUS.md").read_text(encoding="utf-8")
            stored = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(stored, payload)
        self.assertIn("studio-primary", status)
        self.assertNotIn("should-not-be-accepted", status)

    def test_record_report_writes_inventory_and_human_assets(self) -> None:
        payload = {
            "schema": "codex_fleet_report.v1",
            "receipt": receipt("fictional-render-node"),
            "inventory": inventory("fictional-render-node"),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii")
        registry = fictional_registry()
        render_policy = fictional_node_policy(["gpu", "windows", "wsl"])
        render_policy["display_name"] = "Fictional Render Node"
        render_policy["notes"] = [
            {
                "category": "hardware-control",
                "summary": "GPU 风扇由专用 Windows 控制软件管理",
            }
        ]
        registry["nodes"]["fictional-render-node"] = render_policy
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(fleet, "node_registry", return_value=registry):
                destination = fleet.record_receipt(root, encoded)
            stored = json.loads(
                destination.with_name("inventory.json").read_text(encoding="utf-8")
            )
            assets = (root / "ASSETS.md").read_text(encoding="utf-8")
            catalog = json.loads((root / "ASSETS.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["hardware"]["gpus"][0]["name"], "Example GPU")
        self.assertIn("Fan Control", assets)
        self.assertIn("# OPL Fleet 资产清单", assets)
        self.assertIn("## 设备总览", assets)
        self.assertIn("GPU 风扇由专用 Windows 控制软件管理", assets)
        self.assertIn("#### 运维注意事项", assets)
        self.assertEqual(catalog["schema"], "codex_fleet_assets.v1")

    def test_select_nodes_filters_capability_memory_and_freshness(self) -> None:
        item = {
            "node_id": "fictional-gpu-node",
            "policy": {
                "approved": True,
                "display_name": "Windows NUC",
                "labels": ["windows", "wsl", "gpu"],
                "notes": [],
            },
            "receipt": receipt("fictional-gpu-node"),
            "inventory": inventory("fictional-gpu-node"),
        }
        item["inventory"]["observed_at"] = (
            fleet.dt.datetime.now(fleet.dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )
        selected = fleet.select_nodes(
            {"nodes": [item]},
            required={"gpu", "docker"},
            min_memory_gb=32,
            max_age_hours=36,
        )
        rejected = fleet.select_nodes(
            {"nodes": [item]},
            required={"apple-silicon"},
            min_memory_gb=32,
            max_age_hours=36,
        )
        self.assertEqual(
            [entry["node_id"] for entry in selected],
            ["fictional-gpu-node"],
        )
        self.assertEqual(rejected, [])

    def test_execution_requirements_json_normalizes_gpu_intent(self) -> None:
        request = fleet.dispatch_request(
            fleet.argparse.Namespace(
                requirements_json=json.dumps(
                    {
                        "schema": "opl_execution_requirements.v1",
                        "adapter": "ssh-session",
                        "requires": ["windows", "wsl"],
                        "min_memory_gb": 32,
                        "gpu_api": "cuda",
                        "min_gpu_memory_gb": 20,
                        "gpu_model": "RTX 4090",
                        "workload_class": "background",
                        "priority": 300,
                        "preemptible": True,
                        "phase": "interruptible",
                        "ttl_seconds": 3600,
                    }
                ),
                adapter=None,
                node_id=None,
                role=None,
                requires=None,
                min_memory_gb=None,
                gpu_api=None,
                min_gpu_memory_gb=None,
                gpu_model=None,
                workload_class=None,
                priority=None,
                preemptible=None,
                phase=None,
                ttl_seconds=None,
            )
        )
        self.assertEqual(request["adapter"], "ssh-session")
        self.assertEqual(request["gpu_api"], "cuda")
        self.assertEqual(request["min_gpu_memory_gb"], 20)
        self.assertEqual(request["gpu_model"], "RTX 4090")
        self.assertEqual(request["requires"], ["cuda", "gpu", "windows", "wsl"])

    def test_cuda_metal_model_and_gpu_memory_filter_the_same_gpu(self) -> None:
        cuda_inventory = dispatchable_inventory("fictional-cuda")
        cuda_inventory["hardware"]["gpus"] = [
            {
                "name": "NVIDIA GeForce RTX 4090",
                "memory_bytes": 24 * 1024**3,
                "driver_version": "999.1",
            }
        ]
        metal_inventory = dispatchable_inventory("fictional-metal")
        metal_inventory["host"]["system"] = "darwin"
        metal_inventory["execution"] = {
            "kind": "native",
            "os_name": "macOS",
            "os_version": "26.0",
            "kernel": "25.0",
            "architecture": "arm64",
        }
        metal_inventory["hardware"]["memory_bytes"] = 64 * 1024**3
        metal_inventory["hardware"]["gpus"] = [{"name": "Apple M4 Max"}]
        catalog = {
            "nodes": [
                {
                    "node_id": "fictional-cuda",
                    "policy": fictional_node_policy(["windows", "wsl", "gpu"]),
                    "receipt": receipt("fictional-cuda"),
                    "inventory": cuda_inventory,
                },
                {
                    "node_id": "fictional-metal",
                    "policy": fictional_node_policy(["macos", "apple-silicon"]),
                    "receipt": receipt("fictional-metal"),
                    "inventory": metal_inventory,
                },
            ]
        }
        cuda = fleet.select_nodes(
            catalog,
            required={"gpu", "cuda"},
            min_memory_gb=16,
            max_age_hours=36,
            gpu_api="cuda",
            min_gpu_memory_gb=20,
            gpu_model="RTX 4090",
        )
        metal = fleet.select_nodes(
            catalog,
            required={"gpu", "metal"},
            min_memory_gb=16,
            max_age_hours=36,
            gpu_api="metal",
            min_gpu_memory_gb=32,
            gpu_model="M4 Max",
        )
        rejected = fleet.select_nodes(
            catalog,
            required={"gpu", "cuda"},
            min_memory_gb=16,
            max_age_hours=36,
            gpu_api="cuda",
            min_gpu_memory_gb=25,
            gpu_model="RTX 4090",
        )
        self.assertEqual([item["node_id"] for item in cuda], ["fictional-cuda"])
        self.assertEqual([item["node_id"] for item in metal], ["fictional-metal"])
        self.assertEqual(rejected, [])

    def test_windows_gpu_peers_have_equal_policy_and_selection_weight(self) -> None:
        registry = fictional_registry()
        entries = []
        for node_id in ("fictional-gpu-a", "fictional-gpu-b"):
            entries.append(
                {
                    "node_id": node_id,
                    "policy": registry["nodes"][node_id],
                    "receipt": receipt(node_id),
                    "inventory": dispatchable_inventory(node_id),
                }
            )
        selected = fleet.select_nodes(
            {"nodes": list(reversed(entries))},
            required={"windows", "wsl", "gpu", "docker"},
            min_memory_gb=32,
            max_age_hours=36,
        )
        self.assertEqual(
            [entry["node_id"] for entry in selected],
            ["fictional-gpu-a", "fictional-gpu-b"],
        )
        self.assertEqual(
            registry["nodes"]["fictional-gpu-a"]["scheduling"],
            registry["nodes"]["fictional-gpu-b"]["scheduling"],
        )

    def test_reserve_capabilities_require_live_hyperv_and_system_broker(self) -> None:
        registry = fictional_registry()
        entries = []
        for node_id in ("fictional-gpu-a", "fictional-gpu-b"):
            live_inventory = dispatchable_inventory(node_id)
            if node_id == "fictional-gpu-a":
                live_inventory["capabilities"]["virtualization"] = {
                    "hypervisor_ready": True,
                    "hyper_v": {"present": True},
                    "hyper_v_broker": {
                        "available": True,
                        "system_owned": True,
                    },
                }
            entries.append(
                {
                    "node_id": node_id,
                    "policy": registry["nodes"][node_id],
                    "receipt": receipt(node_id),
                    "inventory": live_inventory,
                }
            )
        self.assertNotIn(
            "windows-clean-guest-reserve",
            fleet.node_features(entries[0]),
        )
        self.assertEqual(
            fleet.node_features(entries[0], live_only_observed=True)
            & {"hyperv", "windows-clean-guest-reserve"},
            {"hyperv", "windows-clean-guest-reserve"},
        )
        selected = fleet.select_nodes(
            {"nodes": entries},
            required={
                "windows",
                "wsl",
                "hyperv",
                "windows-clean-guest-reserve",
            },
            min_memory_gb=32,
            max_age_hours=36,
        )
        self.assertEqual(selected, [])
        self.assertEqual(
            registry["runner_roles"]["fictional-reserve-role"],
            ["fictional-gpu-a"],
        )
        fleet.assert_runner_role_workload(
            "fictional-reserve-role",
            "guest",
            registry=registry,
        )
        with self.assertRaisesRegex(fleet.FleetError, "does not allow workload"):
            fleet.assert_runner_role_workload(
                "fictional-reserve-role",
                "background",
                registry=registry,
            )

    def test_fictional_registry_validates_without_production_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "nodes.json").write_text(
                json.dumps(fictional_registry()),
                encoding="utf-8",
            )
            registry = fleet.node_registry(control_root=root)
        self.assertEqual(
            registry["runner_bindings"]["fictional-runner-role"]["repository"],
            "example/fleet-fixture",
        )

    def test_instance_configuration_owns_the_registry(self) -> None:
        previous = fleet.CONTROL_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            instance = Path(temp_dir)
            control = instance / "fleet"
            control.mkdir()
            (control / "nodes.json").write_text(
                json.dumps(fictional_registry()), encoding="utf-8"
            )
            (control / "fleet.json").write_text("{}\n", encoding="utf-8")
            try:
                fleet.configure_instance(instance)
                registry = fleet.node_registry()
                self.assertEqual(fleet.CONTROL_ROOT, control.resolve())
            finally:
                fleet.CONTROL_ROOT = previous
        self.assertEqual(registry["schema"], "codex_fleet_nodes.v1")

    def test_instance_configuration_is_required(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            mock.patch.dict(fleet.os.environ, {}, clear=True),
            mock.patch.object(
                fleet, "INSTANCE_POINTER_PATH", Path(temp_dir) / "missing.json"
            ),
        ):
            with self.assertRaisesRegex(fleet.FleetError, "pass --instance"):
                fleet.configure_instance(None)

    def test_instance_pointer_is_private_and_resolves_fleet_root(self) -> None:
        previous = fleet.CONTROL_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instance = root / "instance"
            (instance / "fleet").mkdir(parents=True)
            for name in ("fleet.json", "nodes.json"):
                (instance / "fleet" / name).write_text("{}\n", encoding="utf-8")
            pointer = root / "instance.json"
            pointer.write_text(
                json.dumps(
                    {
                        "schema": "opl_flow_instance_pointer.v1",
                        "path": str(instance),
                    }
                ),
                encoding="utf-8",
            )
            pointer.chmod(0o600)
            try:
                with (
                    mock.patch.dict(fleet.os.environ, {}, clear=True),
                    mock.patch.object(fleet, "INSTANCE_POINTER_PATH", pointer),
                ):
                    self.assertEqual(fleet.configure_instance(None), instance.resolve())
            finally:
                fleet.CONTROL_ROOT = previous

    def test_install_fleet_command_creates_stable_owner_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with mock.patch.object(fleet.Path, "home", return_value=home):
                destination = fleet.install_fleet_command()
            self.assertEqual(destination, home / ".local/bin/opl-fleet")
            self.assertEqual(destination.resolve(), SCRIPT.resolve())

    def test_reconcile_updates_flow_before_instance_control(self) -> None:
        order: list[str] = []

        def update_flow() -> str:
            order.append("flow")
            return "b" * 40

        def restart(previous: str, current: str) -> None:
            order.append(f"restart:{previous}:{current}")

        def update_control() -> str:
            order.append("instance")
            raise fleet.FleetError("stop after update ordering proof")

        with (
            mock.patch.object(fleet, "run"),
            mock.patch.object(fleet, "checkout_commit", return_value="a" * 40),
            mock.patch.object(fleet, "update_flow", side_effect=update_flow),
            mock.patch.object(
                fleet,
                "restart_after_flow_update",
                side_effect=restart,
            ),
            mock.patch.object(fleet, "update_control", side_effect=update_control),
            self.assertRaisesRegex(fleet.FleetError, "ordering proof"),
        ):
            fleet.reconcile(report=False, install_required=False)

        self.assertEqual(
            order,
            ["flow", f"restart:{'a' * 40}:{'b' * 40}", "instance"],
        )

    def test_lease_lifecycle_enforces_owner_and_compare_and_swap(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            lease = fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-a",
                owner_thread="thread-a",
                owner_run="run-a",
                workload_class="background",
                priority=100,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=300,
                **lease_binding(now),
                state_root=state_root,
                now=now,
            )
            self.assertEqual(
                (state_root / "controller/leases.json").stat().st_mode & 0o777,
                0o600,
            )
            with self.assertRaisesRegex(fleet.FleetError, "already has"):
                fleet.acquire_lease_record(
                    node_id="fictional-node",
                    owner_task="task-b",
                    owner_thread=None,
                    owner_run=None,
                    workload_class="background",
                    priority=101,
                    preemptible=True,
                    phase="interruptible",
                    ttl_seconds=300,
                    **lease_binding(now),
                    state_root=state_root,
                    now=now,
                )
            with self.assertRaisesRegex(fleet.FleetError, "owner mismatch"):
                fleet.renew_lease_record(
                    node_id="fictional-node",
                    lease_id=lease["lease_id"],
                    generation=lease["generation"],
                    nonce=lease["nonce"],
                    owner_task="task-b",
                    ttl_seconds=300,
                    state_root=state_root,
                    now=now,
                )
            renewed = fleet.renew_lease_record(
                node_id="fictional-node",
                lease_id=lease["lease_id"],
                generation=lease["generation"],
                nonce=lease["nonce"],
                owner_task="task-a",
                ttl_seconds=300,
                phase="non-interruptible",
                state_root=state_root,
                now=now,
            )
            with self.assertRaisesRegex(fleet.FleetError, "safely preemptible"):
                fleet.acquire_lease_record(
                    node_id="fictional-node",
                    owner_task="task-b",
                    owner_thread=None,
                    owner_run=None,
                    workload_class="foreground",
                    priority=1000,
                    preemptible=False,
                    phase="interruptible",
                    ttl_seconds=300,
                    **lease_binding(now),
                    preempt_lease_id=renewed["lease_id"],
                    preempt_generation=renewed["generation"],
                    preempt_nonce=renewed["nonce"],
                    state_root=state_root,
                    now=now,
                )
            with self.assertRaisesRegex(fleet.FleetError, "compare-and-swap"):
                fleet.release_lease_record(
                    node_id="fictional-node",
                    lease_id=lease["lease_id"],
                    generation=lease["generation"],
                    nonce=lease["nonce"],
                    owner_task="task-a",
                    state_root=state_root,
                    now=now,
                )
            released = fleet.release_lease_record(
                node_id="fictional-node",
                lease_id=renewed["lease_id"],
                generation=renewed["generation"],
                nonce=renewed["nonce"],
                owner_task="task-a",
                state_root=state_root,
                now=now,
            )
            store = fleet.read_lease_store(state_root=state_root)
        self.assertEqual(released["phase"], "non-interruptible")
        self.assertEqual(store["leases"], {})
        self.assertEqual(
            [event["event"] for event in store["audit"]],
            ["acquire", "renew", "release"],
        )

    def test_local_dispatch_is_explicitly_local_without_a_fleet_instance(self) -> None:
        result = fleet.main(
            [
                "dispatch",
                "plan",
                "--adapter",
                "local-codex",
            ]
        )
        self.assertEqual(result, 0)

    def test_dispatch_plan_marks_remote_codex_as_unimplemented(self) -> None:
        request = fleet.argparse.Namespace(
            adapter="remote-codex",
            node_id=None,
            role=None,
            requires="gpu",
            min_memory_gb=24,
            workload_class="job",
            priority=500,
            preemptible=False,
            phase="non-interruptible",
            ttl_seconds=3600,
        )
        catalog = {
            "nodes": [
                {
                    "node_id": "fictional-gpu-a",
                    "policy": {"approved": True, "display_name": "GPU A"},
                    "receipt": {"state": "CURRENT"},
                    "inventory": dispatchable_inventory("fictional-gpu-a"),
                }
            ]
        }
        with (
            mock.patch.object(fleet, "remote_asset_catalog", return_value=catalog),
            mock.patch.object(
                fleet,
                "manifest",
                return_value={"inventory": {"max_age_hours": 36}},
            ),
            mock.patch.object(fleet, "active_lease_map", return_value={}),
        ):
            normalized = fleet.dispatch_request(request)
            result = fleet.dispatch_plan_payload(normalized)
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["selection"]["candidate_count"], 1)
        self.assertIn("not implemented", result["next_action"])

    def test_dispatch_lease_only_acquire_verify_release(self) -> None:
        now = fleet.dt.datetime(2026, 7, 30, tzinfo=fleet.dt.timezone.utc)
        catalog = {
            "nodes": [
                {
                    "node_id": "fictional-gpu-a",
                    "policy": {"approved": True, "display_name": "GPU A"},
                    "receipt": {"state": "CURRENT"},
                    "inventory": dispatchable_inventory("fictional-gpu-a"),
                }
            ]
        }
        catalog["nodes"][0]["inventory"]["observed_at"] = now.isoformat()
        doctor = {
            "approved": True,
            "receipt_state": "CURRENT",
            "inventory_fresh": True,
            "codex_ready": True,
            "ssh": {"reachable": True},
            "tailscale": {"online": True},
            "scheduling": {
                "power_ok": True,
                "storage_ok": True,
                "thermal_ok": True,
                "interactive_busy": False,
                "busy": False,
            },
            "work_volume": {"ready": True},
            "features": ["gpu", "windows", "wsl"],
            "memory_bytes": 64 * 1024**3,
            "inventory_age_seconds": 0,
            "checked_at": now.isoformat(),
            "admission_ready": True,
        }
        args = fleet.argparse.Namespace(
            adapter="lease-only",
            node_id=None,
            role=None,
            requires="gpu",
            min_memory_gb=24,
            workload_class="background",
            priority=300,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=3600,
            owner_task="dispatch-task",
            owner_thread="dispatch-thread",
            owner_run="dispatch-run",
            preempt_lease_id=None,
            preempt_generation=None,
            preempt_nonce=None,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            previous_state_root = fleet.STATE_ROOT
            try:
                fleet.STATE_ROOT = state_root
                with (
                    mock.patch.object(fleet, "controller_guard", return_value="controller"),
                    mock.patch.object(fleet, "node_registry", return_value=fictional_registry()),
                    mock.patch.object(fleet, "remote_asset_catalog", return_value=catalog),
                    mock.patch.object(
                        fleet,
                        "manifest",
                        return_value={"inventory": {"max_age_hours": 36}},
                    ),
                    mock.patch.object(fleet, "doctor_result", return_value=doctor),
                    mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
                    mock.patch.object(fleet, "utc_now", return_value=now),
                ):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(fleet.fleet_dispatch_acquire(args), 0)
                    acquired = json.loads(output.getvalue())
                    dispatch_id = acquired["dispatch_id"]
                    self.assertEqual(acquired["status"], "leased")
                    self.assertEqual(acquired["lease"]["node_id"], "fictional-gpu-a")

                    verify_args = fleet.argparse.Namespace(
                        dispatch_id=dispatch_id,
                        min_ttl_seconds=300,
                        max_admission_age_seconds=300,
                    )
                    with contextlib.redirect_stdout(io.StringIO()) as verify_output:
                        self.assertEqual(fleet.fleet_dispatch_verify(verify_args), 0)
                    verified = json.loads(verify_output.getvalue())
                    self.assertTrue(verified["verification"]["verified"])

                    release_args = fleet.argparse.Namespace(
                        dispatch_id=dispatch_id,
                        owner_task="dispatch-task",
                    )
                    with contextlib.redirect_stdout(io.StringIO()) as release_output:
                        self.assertEqual(fleet.fleet_dispatch_release(release_args), 0)
                    released = json.loads(release_output.getvalue())
                    self.assertEqual(released["status"], "released")
                    self.assertEqual(fleet.active_lease_map(), {})
            finally:
                fleet.STATE_ROOT = previous_state_root

    def test_dispatch_acquire_skips_offline_candidate_after_fresh_doctor(self) -> None:
        now = fleet.dt.datetime(2026, 8, 1, tzinfo=fleet.dt.timezone.utc)
        healthy = {
            "approved": True,
            "receipt_state": "CURRENT",
            "inventory_fresh": True,
            "codex_ready": True,
            "ssh": {"reachable": True},
            "tailscale": {"online": True},
            "scheduling": {
                "power_ok": True,
                "storage_ok": True,
                "thermal_ok": True,
                "interactive_busy": False,
                "busy": False,
            },
            "work_volume": {"ready": True},
            "features": ["cuda", "gpu", "windows", "wsl"],
            "memory_bytes": 64 * 1024**3,
            "gpus": [
                {
                    "name": "NVIDIA GeForce RTX 4090",
                    "apis": ["cuda"],
                    "memory_bytes": 24 * 1024**3,
                    "driver_version": "999.1",
                }
            ],
            "inventory_age_seconds": 0,
            "checked_at": now.isoformat(),
            "admission_ready": True,
        }
        offline = json.loads(json.dumps(healthy))
        offline["ssh"]["reachable"] = False
        offline["tailscale"]["online"] = False
        offline["admission_ready"] = False
        args = fleet.argparse.Namespace(
            adapter="ssh-session",
            requirements_json=None,
            node_id=None,
            role=None,
            requires="cuda,windows,wsl",
            min_memory_gb=32,
            gpu_api="cuda",
            min_gpu_memory_gb=20,
            gpu_model=None,
            workload_class="background",
            priority=300,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=3600,
            owner_task="dispatch-task",
            owner_thread="dispatch-thread",
            owner_run="dispatch-run",
            preempt_lease_id=None,
            preempt_generation=None,
            preempt_nonce=None,
        )
        candidates = [
            {"node_id": "fictional-gpu-a"},
            {"node_id": "fictional-gpu-b"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            previous_state_root = fleet.STATE_ROOT
            try:
                fleet.STATE_ROOT = Path(temp_dir)
                with (
                    mock.patch.object(fleet, "controller_guard"),
                    mock.patch.object(fleet, "dispatch_candidates", return_value=candidates),
                    mock.patch.object(fleet, "node_registry", return_value=fictional_registry()),
                    mock.patch.object(fleet, "doctor_result", side_effect=[offline, healthy]),
                    mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
                    mock.patch.object(fleet, "utc_now", return_value=now),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    self.assertEqual(fleet.fleet_dispatch_acquire(args), 0)
                payload = json.loads(output.getvalue())
            finally:
                fleet.STATE_ROOT = previous_state_root
        self.assertEqual(payload["lease"]["node_id"], "fictional-gpu-b")
        self.assertEqual(payload["lease"]["dispatch_adapter"], "ssh-session")

    def test_ssh_session_uses_structured_argv_without_shell_interpolation(self) -> None:
        remote_result = {
            "schema": "codex_fleet_ssh_execution_result.v1",
            "started_at": "2026-08-01T00:00:00+00:00",
            "finished_at": "2026-08-01T00:00:01+00:00",
            "exit_code": 0,
            "timed_out": False,
            "stdout": "ok\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        argument = "value; touch /tmp/must-not-run"
        with (
            mock.patch.object(
                fleet,
                "read_routes",
                return_value={
                    "schema": "codex_fleet_routes.v1",
                    "routes": {"fictional-gpu-a": {"ssh": "fictional-gpu-a"}},
                },
            ),
            mock.patch.object(
                fleet,
                "run",
                return_value=mock.Mock(
                    returncode=0,
                    stdout=json.dumps(remote_result),
                    stderr="",
                ),
            ) as run_mock,
        ):
            result = fleet.execute_ssh_session(
                "fictional-gpu-a",
                argv=["printf", "%s", argument],
                cwd=None,
                timeout_seconds=60,
            )
        invocation = run_mock.call_args.args[0]
        input_payload = json.loads(run_mock.call_args.kwargs["input_text"])
        self.assertTrue(result["known"])
        self.assertNotIn(argument, " ".join(invocation))
        self.assertEqual(input_payload["argv"], ["printf", "%s", argument])

    def test_unknown_ssh_result_retains_lease_and_blocks_retry_claim(self) -> None:
        now = fleet.dt.datetime(2026, 8, 1, tzinfo=fleet.dt.timezone.utc)
        lease = fleet.build_lease(
            node_id="fictional-gpu-a",
            generation=1,
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            role=None,
            workload_class="background",
            priority=300,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=3600,
            control_revision=TEST_CONTROL_COMMIT,
            admission=admission(now),
            now=now,
            dispatch_adapter_name="ssh-session",
        )
        args = fleet.argparse.Namespace(
            dispatch_id=lease["lease_id"],
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            argv_json='["true"]',
            cwd=None,
            timeout_seconds=60,
            min_ttl_seconds=30,
            max_admission_age_seconds=300,
        )
        with (
            mock.patch.object(fleet, "controller_guard"),
            mock.patch.object(fleet, "dispatch_lease", return_value=lease),
            mock.patch.object(fleet, "verify_lease_record", return_value={"verified": True}),
            mock.patch.object(
                fleet,
                "execute_ssh_session",
                return_value={
                    "known": False,
                    "reason": "ssh-transport-failed",
                    "transport_returncode": 255,
                },
            ),
            mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
            mock.patch.object(fleet, "node_registry", return_value=fictional_registry()),
            mock.patch.object(fleet, "utc_now", return_value=now),
            mock.patch.object(fleet, "release_lease_record") as release_mock,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(fleet.fleet_dispatch_execute(args), 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "unknown")
        self.assertTrue(payload["lease_retained"])
        self.assertTrue(payload["release_required"])
        release_mock.assert_not_called()

    def test_completed_ssh_result_requires_explicit_release(self) -> None:
        now = fleet.dt.datetime(2026, 8, 1, tzinfo=fleet.dt.timezone.utc)
        lease = fleet.build_lease(
            node_id="fictional-gpu-a",
            generation=1,
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            role=None,
            workload_class="background",
            priority=300,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=3600,
            control_revision=TEST_CONTROL_COMMIT,
            admission=admission(now),
            now=now,
            dispatch_adapter_name="ssh-session",
        )
        result = {
            "schema": "codex_fleet_ssh_execution_result.v1",
            "started_at": now.isoformat(),
            "finished_at": (now + fleet.dt.timedelta(seconds=1)).isoformat(),
            "exit_code": 0,
            "timed_out": False,
            "stdout": "done\n",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
        args = fleet.argparse.Namespace(
            dispatch_id=lease["lease_id"],
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            argv_json='["true"]',
            cwd=None,
            timeout_seconds=60,
            min_ttl_seconds=30,
            max_admission_age_seconds=300,
        )
        with (
            mock.patch.object(fleet, "controller_guard"),
            mock.patch.object(fleet, "dispatch_lease", return_value=lease),
            mock.patch.object(fleet, "verify_lease_record", return_value={"verified": True}),
            mock.patch.object(
                fleet,
                "execute_ssh_session",
                return_value={"known": True, "result": result},
            ),
            mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
            mock.patch.object(fleet, "node_registry", return_value=fictional_registry()),
            mock.patch.object(fleet, "utc_now", return_value=now),
            mock.patch.object(fleet, "release_lease_record") as release_mock,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(fleet.fleet_dispatch_execute(args), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["release_required"])
        self.assertEqual(payload["result"]["stdout"], "done\n")
        release_mock.assert_not_called()

    def test_expired_lease_is_reaped_before_reacquire(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        later = now + fleet.dt.timedelta(seconds=61)
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            first = fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-a",
                owner_thread=None,
                owner_run=None,
                workload_class="experiment",
                priority=1,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=60,
                **lease_binding(now),
                state_root=state_root,
                now=now,
            )
            self.assertEqual(
                fleet.active_lease_map(state_root=state_root, now=later),
                {},
            )
            second = fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-b",
                owner_thread=None,
                owner_run=None,
                workload_class="background",
                priority=2,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=60,
                **lease_binding(later),
                state_root=state_root,
                now=later,
            )
            store = fleet.read_lease_store(state_root=state_root)
        self.assertNotEqual(first["lease_id"], second["lease_id"])
        self.assertEqual(
            [event["event"] for event in store["audit"]],
            ["acquire", "reap", "acquire"],
        )

    def test_concurrent_acquire_has_one_winner(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)

            def attempt(owner: str) -> str:
                try:
                    fleet.acquire_lease_record(
                        node_id="fictional-node",
                        owner_task=owner,
                        owner_thread=None,
                        owner_run=None,
                        workload_class="background",
                        priority=10,
                        preemptible=True,
                        phase="interruptible",
                        ttl_seconds=300,
                        **lease_binding(now),
                        state_root=state_root,
                        now=now,
                    )
                    return "acquired"
                except fleet.FleetError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(attempt, ("task-a", "task-b")))
            store = fleet.read_lease_store(state_root=state_root)
        self.assertEqual(sorted(outcomes), ["acquired", "rejected"])
        self.assertEqual(len(store["leases"]), 1)

    def test_preemption_requires_safe_incumbent_and_higher_priority(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            lease = fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-a",
                owner_thread=None,
                owner_run=None,
                workload_class="background",
                priority=100,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=300,
                **lease_binding(now),
                state_root=state_root,
                now=now,
            )
            with self.assertRaisesRegex(fleet.FleetError, "safely preemptible"):
                fleet.acquire_lease_record(
                    node_id="fictional-node",
                    owner_task="task-b",
                    owner_thread=None,
                    owner_run=None,
                    workload_class="foreground",
                    priority=100,
                    preemptible=False,
                    phase="interruptible",
                    ttl_seconds=300,
                    **lease_binding(now),
                    preempt_lease_id=lease["lease_id"],
                    preempt_generation=lease["generation"],
                    preempt_nonce=lease["nonce"],
                    state_root=state_root,
                    now=now,
                )
            successor = fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-b",
                owner_thread=None,
                owner_run=None,
                workload_class="foreground",
                priority=101,
                preemptible=False,
                phase="interruptible",
                ttl_seconds=300,
                **lease_binding(now),
                preempt_lease_id=lease["lease_id"],
                preempt_generation=lease["generation"],
                preempt_nonce=lease["nonce"],
                state_root=state_root,
                now=now,
            )
        self.assertEqual(successor["owner_task"], "task-b")
        self.assertFalse(successor["preemptible"])
        for workload_class in ("p0-release", "foreground", "guest", "job", "vm"):
            with self.subTest(workload_class=workload_class):
                with self.assertRaisesRegex(fleet.FleetError, "workload policy"):
                    fleet.build_lease(
                        node_id="fictional-node",
                        generation=1,
                        owner_task="task-protected",
                        owner_thread=None,
                        owner_run=None,
                        workload_class=workload_class,
                        priority=1000,
                        preemptible=True,
                        phase="interruptible",
                        ttl_seconds=300,
                        **lease_binding(now),
                        now=now,
                    )

    def test_protected_lease_requires_thread_and_run_identity(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        with self.assertRaisesRegex(
            fleet.FleetError,
            "requires owner thread and owner run",
        ):
            fleet.build_lease(
                node_id="fictional-node",
                generation=1,
                owner_task="task-protected",
                owner_thread=None,
                owner_run=None,
                workload_class="job",
                priority=1000,
                preemptible=False,
                phase="interruptible",
                ttl_seconds=300,
                **lease_binding(now, role="fictional-role"),
                now=now,
            )

    def test_admission_rejects_power_interactive_busy_and_thermal_drift(self) -> None:
        doctor = {
            "approved": True,
            "receipt_state": "CURRENT",
            "inventory_fresh": True,
            "codex_ready": True,
            "ssh": {"reachable": True},
            "tailscale": {"online": True},
            "scheduling": {
                "power_ok": False,
                "storage_ok": True,
                "thermal_ok": False,
                "interactive_busy": True,
                "busy": True,
            },
            "work_volume": {"ready": True},
            "features": ["gpu"],
            "memory_bytes": 64 * 1024**3,
            "admission_ready": False,
        }
        with self.assertRaisesRegex(
            fleet.FleetError,
            "ac-required.*thermal-gate.*interactive-busy.*busy",
        ):
            fleet.assert_lease_admission(
                doctor,
                required={"gpu"},
                min_memory_gb=32,
            )
        doctor["scheduling"] = {
            **doctor["scheduling"],
            "power_ok": True,
            "thermal_ok": True,
            "interactive_busy": None,
            "busy": False,
        }
        with self.assertRaisesRegex(fleet.FleetError, "occupancy-unknown"):
            fleet.assert_lease_admission(
                doctor,
                required={"gpu"},
                min_memory_gb=32,
            )

    def test_required_work_volume_is_fail_closed(self) -> None:
        result = fleet.work_volume_status(
            node_id="fictional-macos-node",
            route={},
            local=False,
            ssh_alias="fictional-macos-node",
            required=True,
        )
        self.assertEqual(
            result,
            {"required": True, "configured": False, "ready": False},
        )

    def test_required_work_volume_accepts_matching_writable_apfs_space(self) -> None:
        volume_uuid = "12345678-1234-1234-1234-123456789abc"
        volume = fleet.subprocess.CompletedProcess(
            ["diskutil"],
            0,
            plistlib.dumps(
                {
                    "VolumeUUID": volume_uuid.upper(),
                    "FilesystemType": "apfs",
                    "MountPoint": "/Volumes/Fictional",
                }
            ).decode("utf-8"),
            "",
        )
        usage = fleet.subprocess.CompletedProcess(
            ["python3"],
            0,
            json.dumps(
                {
                    "exists": True,
                    "writable": True,
                    "free_bytes": 200 * 1024**3,
                }
            ),
            "",
        )
        with mock.patch.object(fleet, "run", side_effect=[volume, usage]):
            result = fleet.work_volume_status(
                node_id="fictional-macos-node",
                route={
                    "work_volume": {
                        "volume_uuid": volume_uuid,
                        "filesystem": "apfs",
                        "min_free_gb": 100,
                        "probe_subpath": "Fictional Work",
                    }
                },
                local=False,
                ssh_alias="fictional-macos-node",
                required=True,
            )
        self.assertTrue(result["identity_match"])
        self.assertTrue(result["probe_exists"])
        self.assertTrue(result["writable"])
        self.assertTrue(result["ready"])

    def test_work_volume_route_rejects_path_escape(self) -> None:
        with self.assertRaisesRegex(fleet.FleetError, "route is invalid"):
            fleet.validate_work_volume_route(
                {
                    "volume_uuid": "12345678-1234-1234-1234-123456789abc",
                    "filesystem": "apfs",
                    "min_free_gb": 100,
                    "probe_subpath": "../private",
                }
            )

    def test_runner_control_route_uses_stdin_for_remote_shell_script(self) -> None:
        route = {
            "fictional-workstation": {
                "ssh": "fictional-workstation",
                "runner_control": {
                    "shell": "posix",
                    "start": "echo start",
                    "stop": "echo stop",
                    "status": "printf '{\"enabled\":false,\"online\":false,\"processes\":0}'",
                },
            }
        }
        completed = fleet.subprocess.CompletedProcess(
            ["ssh"],
            0,
            '{"enabled":false,"online":false,"processes":0}',
            "",
        )
        with (
            mock.patch.object(
                fleet,
                "read_routes",
                return_value={"schema": "codex_fleet_routes.v1", "routes": route},
            ),
            mock.patch.object(fleet, "run", return_value=completed) as command,
        ):
            result = fleet.runner_control_call("fictional-workstation", "status")
        self.assertEqual(result["processes"], 0)
        self.assertEqual(
            command.call_args.kwargs["input_text"],
            route["fictional-workstation"]["runner_control"]["status"],
        )
        self.assertEqual(command.call_args.args[0][-1], "-s")

    def test_runner_transaction_start_and_stop_release_controller_lease(self) -> None:
        test_now = fleet.dt.datetime.now(fleet.dt.timezone.utc).replace(microsecond=0)
        checked_at = test_now.isoformat()
        binding = {
            "launch_mode": "windows-session-task",
            "min_memory_gb": 60,
            "node_id": "fictional-workstation",
            "repository": "example/fixture-app",
            "required_features": ["docker", "windows", "wsl"],
            "runner_name": "fictional-windows-runner",
        }
        registry = {
            "runner_roles": {"fictional-runner": ["fictional-workstation"]},
            "runner_bindings": {"fictional-runner": binding},
        }
        doctor = {
            "approved": True,
            "receipt_state": "CURRENT",
            "inventory_fresh": True,
            "codex_ready": True,
            "ssh": {"reachable": True},
            "tailscale": {"online": True},
            "scheduling": {
                "power_ok": True,
                "storage_ok": True,
                "thermal_ok": True,
                "interactive_busy": False,
                "busy": False,
            },
            "work_volume": {"ready": True},
            "features": ["docker", "windows", "wsl"],
            "memory_bytes": 60 * 1024**3,
            "checked_at": checked_at,
            "inventory_age_seconds": 0,
        }
        start_args = mock.Mock(
            role="fictional-runner",
            owner_task="runner-task",
            owner_thread="runner-thread",
            owner_run="runner-run",
            workload_class="background",
            priority=300,
            preemptible=True,
            phase="interruptible",
            ttl_seconds=600,
            min_ttl_seconds=60,
            max_admission_age_seconds=300,
            startup_timeout_seconds=1,
        )
        stop_args = mock.Mock(
            role="fictional-runner",
            owner_task="runner-task",
            shutdown_timeout_seconds=1,
        )
        control_statuses = iter(
            [
                {"enabled": False, "online": False, "processes": 0},
                {"enabled": True, "online": True, "processes": 1},
                {"enabled": False, "online": False, "processes": 0},
            ]
        )

        def runner_control(
            _node_id: str,
            action: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            if action == "status":
                return next(control_statuses)
            return {"ok": True, "action": action}
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(fleet, "STATE_ROOT", Path(temp_dir)),
                mock.patch.object(fleet, "controller_guard", return_value="controller"),
                mock.patch.object(fleet, "node_registry", return_value=registry),
                mock.patch.object(fleet, "runner_binding", return_value=binding),
                mock.patch.object(fleet, "doctor_result", return_value=doctor),
                mock.patch.object(fleet, "assert_lease_admission"),
                mock.patch.object(
                    fleet,
                    "build_admission_receipt",
                    return_value={
                        "checked_at": checked_at,
                        "inventory_age_seconds": 0,
                        "requirements": ["docker", "windows", "wsl"],
                        "min_memory_gb": 60,
                        "power_ok": True,
                        "storage_ok": True,
                        "thermal_ok": True,
                        "interactive_busy": False,
                        "busy": False,
                        "work_volume_ready": True,
                    },
                ),
                mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
                mock.patch.object(fleet, "utc_now", return_value=test_now),
                mock.patch.object(
                    fleet,
                    "runner_control_call",
                    side_effect=runner_control,
                ),
                mock.patch.object(
                    fleet,
                    "github_runner_state",
                    side_effect=[
                        {"registered": True, "online": False, "busy": False},
                    ],
                ),
                mock.patch.object(
                    fleet,
                    "wait_runner_state",
                    side_effect=[
                        {"registered": True, "online": True, "busy": False},
                        {"registered": True, "online": False, "busy": False},
                    ],
                ),
            ):
                self.assertEqual(fleet.fleet_runner_start(start_args), 0)
                self.assertIsNotNone(fleet.read_runner_transaction("fictional-runner"))
                self.assertEqual(fleet.fleet_runner_stop(stop_args), 0)
                self.assertIsNone(fleet.read_runner_transaction("fictional-runner"))
                self.assertEqual(fleet.active_lease_map(state_root=Path(temp_dir)), {})

    def test_runner_renew_persists_new_generation_and_nonce(self) -> None:
        test_now = fleet.dt.datetime(2026, 7, 29, tzinfo=fleet.dt.timezone.utc)
        binding = {
            "repository": "example/fleet-fixture",
            "runner_name": "fictional-windows-runner",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            lease = fleet.acquire_lease_record(
                node_id="fictional-workstation",
                owner_task="runner-task",
                owner_thread="runner-thread",
                owner_run="runner-run",
                role="fictional-runner",
                workload_class="job",
                priority=300,
                preemptible=False,
                phase="non-interruptible",
                ttl_seconds=600,
                control_revision=TEST_CONTROL_COMMIT,
                admission=admission(test_now),
                state_root=state_root,
                now=test_now,
            )
            transaction = fleet.runner_transaction_from_lease(
                role="fictional-runner",
                binding=binding,
                lease=lease,
                ttl_seconds=600,
            )
            with (
                mock.patch.object(fleet, "STATE_ROOT", state_root),
                mock.patch.object(fleet, "controller_guard", return_value="controller"),
                mock.patch.object(
                    fleet,
                    "runner_control_call",
                    return_value={"enabled": True, "online": True, "processes": 1},
                ),
                mock.patch.object(
                    fleet,
                    "github_runner_state",
                    return_value={"registered": True, "online": True, "busy": False},
                ),
                mock.patch.object(fleet, "utc_now", return_value=test_now),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                fleet.atomic_json(
                    fleet.runner_transaction_path("fictional-runner"),
                    transaction,
                )
                self.assertEqual(
                    fleet.fleet_runner_renew(
                        mock.Mock(
                            role="fictional-runner",
                            owner_task="runner-task",
                            ttl_seconds=900,
                        )
                    ),
                    0,
                )
                renewed_transaction = fleet.read_runner_transaction(
                    "fictional-runner"
                )
                active = fleet.active_lease_map(
                    state_root=state_root,
                    now=test_now,
                )["fictional-workstation"]
        self.assertNotEqual(renewed_transaction["nonce"], lease["nonce"])
        self.assertGreater(renewed_transaction["generation"], lease["generation"])
        self.assertEqual(
            renewed_transaction["generation"],
            active["generation"],
        )
        self.assertEqual(renewed_transaction["nonce"], active["nonce"])
        self.assertEqual(renewed_transaction["ttl_seconds"], 900)

    def test_start_failure_retains_recovery_and_lease_when_shutdown_is_unconfirmed(
        self,
    ) -> None:
        test_now = fleet.dt.datetime.now(fleet.dt.timezone.utc).replace(microsecond=0)
        checked_at = test_now.isoformat()
        binding = {
            "launch_mode": "windows-session-task",
            "min_memory_gb": 32,
            "node_id": "fictional-workstation",
            "repository": "example/fleet-fixture",
            "required_features": ["windows", "wsl"],
            "runner_name": "fictional-windows-runner",
        }
        registry = {
            "runner_roles": {"fictional-runner": ["fictional-workstation"]},
            "runner_role_workloads": {},
            "runner_bindings": {"fictional-runner": binding},
        }
        runner_args = mock.Mock(
            role="fictional-runner",
            owner_task="runner-task",
            owner_thread="runner-thread",
            owner_run="runner-run",
            workload_class="job",
            priority=300,
            preemptible=False,
            phase="non-interruptible",
            ttl_seconds=600,
            min_ttl_seconds=60,
            max_admission_age_seconds=300,
            startup_timeout_seconds=1,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            with (
                mock.patch.object(fleet, "STATE_ROOT", state_root),
                mock.patch.object(fleet, "controller_guard", return_value="controller"),
                mock.patch.object(fleet, "node_registry", return_value=registry),
                mock.patch.object(fleet, "runner_binding", return_value=binding),
                mock.patch.object(
                    fleet,
                    "runner_control_call",
                    side_effect=lambda _node, action, **_kwargs: (
                        {"enabled": False, "online": False, "processes": 0}
                        if action == "status"
                        else {"ok": True, "action": action}
                    ),
                ),
                mock.patch.object(
                    fleet,
                    "github_runner_state",
                    return_value={"registered": True, "online": False, "busy": False},
                ),
                mock.patch.object(fleet, "doctor_result", return_value={}),
                mock.patch.object(fleet, "assert_lease_admission"),
                mock.patch.object(
                    fleet,
                    "build_admission_receipt",
                    return_value={
                        "checked_at": checked_at,
                        "inventory_age_seconds": 0,
                        "requirements": ["windows", "wsl"],
                        "min_memory_gb": 32,
                        "power_ok": True,
                        "storage_ok": True,
                        "thermal_ok": True,
                        "interactive_busy": False,
                        "busy": False,
                        "work_volume_ready": True,
                    },
                ),
                mock.patch.object(fleet, "verify_lease_record"),
                mock.patch.object(fleet, "control_commit", return_value=TEST_CONTROL_COMMIT),
                mock.patch.object(fleet, "utc_now", return_value=test_now),
                mock.patch.object(
                    fleet,
                    "wait_runner_processes",
                    side_effect=[
                        {"enabled": True, "online": False, "processes": 0},
                        {"enabled": True, "online": True, "processes": 1},
                    ],
                ) as wait_processes,
                mock.patch.object(
                    fleet,
                    "wait_runner_state",
                    return_value={"registered": True, "online": True, "busy": False},
                ),
            ):
                with self.assertRaisesRegex(
                    fleet.FleetError,
                    "cleanup failed",
                ):
                    fleet.fleet_runner_start(runner_args)
                transaction = fleet.read_runner_transaction("fictional-runner")
                active = fleet.active_lease_map(
                    state_root=state_root,
                    now=test_now,
                )
        self.assertIsNotNone(transaction)
        self.assertIn("fictional-workstation", active)
        self.assertFalse(wait_processes.call_args_list[0].kwargs["expect_zero"])

    def test_runner_stop_uses_transaction_identity_and_disables_enabled_service(
        self,
    ) -> None:
        test_now = fleet.dt.datetime(2026, 7, 29, tzinfo=fleet.dt.timezone.utc)
        binding = {
            "repository": "example/original-fixture",
            "runner_name": "fictional-original-runner",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            lease = fleet.acquire_lease_record(
                node_id="fictional-workstation",
                owner_task="runner-task",
                owner_thread="runner-thread",
                owner_run="runner-run",
                role="fictional-runner",
                workload_class="job",
                priority=300,
                preemptible=False,
                phase="non-interruptible",
                ttl_seconds=600,
                control_revision=TEST_CONTROL_COMMIT,
                admission=admission(test_now),
                state_root=state_root,
                now=test_now,
            )
            transaction = fleet.runner_transaction_from_lease(
                role="fictional-runner",
                binding=binding,
                lease=lease,
                ttl_seconds=600,
            )
            with (
                mock.patch.object(fleet, "STATE_ROOT", state_root),
                mock.patch.object(fleet, "controller_guard", return_value="controller"),
                mock.patch.object(fleet, "utc_now", return_value=test_now),
                mock.patch.object(
                    fleet,
                    "runner_control_call",
                    return_value={"ok": True, "action": "stop"},
                ) as control,
                mock.patch.object(
                    fleet,
                    "wait_runner_processes",
                    return_value={"enabled": False, "online": False, "processes": 0},
                ),
                mock.patch.object(
                    fleet,
                    "wait_runner_state",
                    return_value={"registered": True, "online": False, "busy": False},
                ) as wait_state,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                fleet.atomic_json(
                    fleet.runner_transaction_path("fictional-runner"),
                    transaction,
                )
                self.assertEqual(
                    fleet.fleet_runner_stop(
                        mock.Mock(
                            role="fictional-runner",
                            owner_task="runner-task",
                            shutdown_timeout_seconds=1,
                        )
                    ),
                    0,
                )
        control.assert_called_once_with(
            "fictional-workstation",
            "stop",
            check=False,
        )
        wait_state.assert_called_once_with(
            "example/original-fixture",
            "fictional-original-runner",
            expect_online=False,
            timeout_seconds=1,
        )

    def test_doctor_uses_live_inventory_for_capabilities(self) -> None:
        node_id = "fictional-node"
        stale = dispatchable_inventory(node_id)
        stale["software"] = {}
        live = dispatchable_inventory(node_id)
        started = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        finished = started + fleet.dt.timedelta(seconds=10)
        live["observed_at"] = (started + fleet.dt.timedelta(seconds=5)).isoformat()
        collected = False

        def collect_live(*_args: object) -> dict[str, object]:
            nonlocal collected
            collected = True
            return live

        def clock() -> fleet.dt.datetime:
            return finished if collected else started

        catalog = {
            "schema": "codex_fleet_assets.v1",
            "nodes": [
                {
                    "node_id": node_id,
                    "policy": {
                        "approved": True,
                        "display_name": "Fictional",
                        "labels": ["development"],
                        "notes": [],
                        "scheduling": {
                            "requires_ac": False,
                            "min_free_gb": 1,
                            "preferred_for": [],
                        },
                    },
                    "receipt": receipt(node_id),
                    "inventory": stale,
                }
            ],
        }
        routes = {
            node_id: {
                "local": True,
                "tailscale_host": "fictional-node",
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(fleet, "collect_inventory", side_effect=collect_live),
                mock.patch.object(fleet, "utc_now", side_effect=clock),
                mock.patch.object(
                    fleet,
                    "manifest",
                    return_value={"inventory": {"max_age_hours": 36}},
                ),
                mock.patch.object(fleet, "node_registry", return_value={"nodes": {}}),
                mock.patch.object(fleet, "tailscale_online", return_value=True),
                mock.patch.object(
                    fleet,
                    "work_volume_status",
                    return_value={"required": False, "configured": False, "ready": True},
                ),
            ):
                result = fleet.doctor_result(
                    node_id,
                    catalog=catalog,
                    routes=routes,
                    state_root=Path(temp_dir),
                )
        self.assertIn("docker", result["features"])
        self.assertTrue(result["live_inventory"])
        self.assertTrue(result["inventory_fresh"])
        self.assertEqual(result["inventory_age_seconds"], 5)

    def test_doctor_classifies_on_demand_unreachable_separately(self) -> None:
        node_id = "fictional-node"
        catalog = {
            "schema": "codex_fleet_assets.v1",
            "nodes": [
                {
                    "node_id": node_id,
                    "policy": {
                        "approved": True,
                        "display_name": "Fictional",
                        "availability_policy": "on_demand",
                        "labels": ["development"],
                        "notes": [],
                    },
                    "receipt": receipt(node_id),
                    "inventory": inventory(node_id),
                }
            ],
        }
        timeout = fleet.subprocess.CompletedProcess(
            ["ssh"], 255, "", "connection timed out"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(fleet, "run", return_value=timeout),
                mock.patch.object(fleet, "tailscale_online", return_value=False),
                mock.patch.object(
                    fleet,
                    "work_volume_status",
                    return_value={"required": False, "configured": False, "ready": True},
                ),
                mock.patch.object(
                    fleet,
                    "manifest",
                    return_value={"inventory": {"max_age_hours": 36}},
                ),
            ):
                result = fleet.doctor_result(
                    node_id,
                    catalog=catalog,
                    routes={node_id: {"ssh": "fictional-node"}},
                    state_root=Path(temp_dir),
                )
        self.assertEqual(result["availability_policy"], "on_demand")
        self.assertEqual(result["availability"], "offline_expected")
        self.assertFalse(result["ready_for_dispatch"])

    def test_doctor_keeps_always_on_unreachable_as_unreachable(self) -> None:
        node_id = "fictional-node"
        catalog = {
            "schema": "codex_fleet_assets.v1",
            "nodes": [
                {
                    "node_id": node_id,
                    "policy": {
                        "approved": True,
                        "display_name": "Fictional",
                        "availability_policy": "always_on",
                        "labels": ["development"],
                        "notes": [],
                    },
                    "receipt": receipt(node_id),
                    "inventory": inventory(node_id),
                }
            ],
        }
        timeout = fleet.subprocess.CompletedProcess(
            ["ssh"], 255, "", "connection timed out"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch.object(fleet, "run", return_value=timeout),
                mock.patch.object(fleet, "tailscale_online", return_value=False),
                mock.patch.object(
                    fleet,
                    "work_volume_status",
                    return_value={"required": False, "configured": False, "ready": True},
                ),
                mock.patch.object(
                    fleet,
                    "manifest",
                    return_value={"inventory": {"max_age_hours": 36}},
                ),
            ):
                result = fleet.doctor_result(
                    node_id,
                    catalog=catalog,
                    routes={node_id: {"ssh": "fictional-node"}},
                    state_root=Path(temp_dir),
                )
        self.assertEqual(result["availability"], "unreachable")

    def test_lease_show_hides_nonce(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            fleet.acquire_lease_record(
                node_id="fictional-node",
                owner_task="task-a",
                owner_thread=None,
                owner_run=None,
                workload_class="background",
                priority=100,
                preemptible=True,
                phase="interruptible",
                ttl_seconds=300,
                **lease_binding(now),
                state_root=state_root,
                now=now,
            )
            output = io.StringIO()
            with (
                mock.patch.object(fleet, "STATE_ROOT", state_root),
                mock.patch.object(fleet, "controller_guard", return_value="controller"),
                mock.patch.object(fleet, "node_identity", return_value="controller"),
                mock.patch.object(fleet, "utc_now", return_value=now),
                contextlib.redirect_stdout(output),
            ):
                fleet.fleet_lease_show(mock.Mock(node_id=None))
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema"], "codex_fleet_lease_readback.v2")
        self.assertEqual(payload["observed_at"], now.isoformat())
        self.assertEqual(payload["leases"][0]["state"], "leased")
        self.assertEqual(payload["leases"][0]["ttl_remaining_seconds"], 300)
        self.assertNotIn("nonce", payload["leases"][0])

    def test_lease_verify_binds_role_owner_admission_and_control(self) -> None:
        now = fleet.dt.datetime(2026, 7, 27, tzinfo=fleet.dt.timezone.utc)
        lease = fleet.build_lease(
            node_id="fictional-node",
            generation=7,
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            workload_class="job",
            priority=500,
            preemptible=False,
            phase="interruptible",
            ttl_seconds=600,
            **lease_binding(
                now,
                role="fictional-runner",
                required=["docker", "gpu"],
                min_memory_gb=32,
            ),
            now=now,
        )
        registry = {
            "runner_roles": {"fictional-runner": ["fictional-node"]},
        }
        result = fleet.verify_lease_record(
            lease,
            node_id="fictional-node",
            role="fictional-runner",
            lease_id=lease["lease_id"],
            generation=7,
            owner_task="task-a",
            owner_thread="thread-a",
            owner_run="run-a",
            workload_class="job",
            phase="interruptible",
            preemptible=False,
            min_ttl_seconds=300,
            required={"docker", "gpu"},
            min_memory_gb=32,
            max_admission_age_seconds=300,
            expected_control_commit=TEST_CONTROL_COMMIT,
            current_control_commit=TEST_CONTROL_COMMIT,
            registry=registry,
            now=now,
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["control_commit"], TEST_CONTROL_COMMIT)
        self.assertEqual(result["lease"]["role"], "fictional-runner")
        self.assertFalse(result["lease"]["preemptible"])
        self.assertEqual(result["lease"]["admission"]["checked_at"], now.isoformat())
        self.assertNotIn("nonce", result["lease"])
        with self.assertRaisesRegex(fleet.FleetError, "preemptible"):
            fleet.verify_lease_record(
                lease,
                node_id="fictional-node",
                role="fictional-runner",
                lease_id=lease["lease_id"],
                generation=7,
                owner_task="task-a",
                owner_thread="thread-a",
                owner_run="run-a",
                workload_class="job",
                phase="interruptible",
                preemptible=True,
                min_ttl_seconds=300,
                required={"docker", "gpu"},
                min_memory_gb=32,
                max_admission_age_seconds=300,
                expected_control_commit=TEST_CONTROL_COMMIT,
                current_control_commit=TEST_CONTROL_COMMIT,
                registry=registry,
                now=now,
            )
        with self.assertRaisesRegex(fleet.FleetError, "admission-freshness"):
            fleet.verify_lease_record(
                lease,
                node_id="fictional-node",
                role="fictional-runner",
                lease_id=lease["lease_id"],
                generation=7,
                owner_task="task-a",
                owner_thread="thread-a",
                owner_run="run-a",
                workload_class="job",
                phase="interruptible",
                preemptible=False,
                min_ttl_seconds=1,
                required={"docker", "gpu"},
                min_memory_gb=32,
                max_admission_age_seconds=300,
                expected_control_commit=TEST_CONTROL_COMMIT,
                current_control_commit=TEST_CONTROL_COMMIT,
                registry=registry,
                now=now + fleet.dt.timedelta(seconds=301),
            )
        with self.assertRaisesRegex(
            fleet.FleetError,
            "controller-currentness",
        ):
            fleet.verify_lease_record(
                lease,
                node_id="fictional-node",
                role="fictional-runner",
                lease_id=lease["lease_id"],
                generation=7,
                owner_task="task-a",
                owner_thread="thread-a",
                owner_run="run-a",
                workload_class="job",
                phase="interruptible",
                preemptible=False,
                min_ttl_seconds=1,
                required={"docker", "gpu"},
                min_memory_gb=32,
                max_admission_age_seconds=300,
                expected_control_commit=TEST_CONTROL_COMMIT,
                current_control_commit="d" * 40,
                registry=registry,
                now=now,
            )

    def test_empty_v1_lease_store_migrates_without_fabricating_leases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_root = Path(temp_dir)
            path, _ = fleet.lease_paths(state_root)
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": "codex_fleet_leases.v1",
                        "generation": 0,
                        "leases": {},
                        "audit": [],
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            store = fleet.read_lease_store(state_root=state_root)
        self.assertEqual(store["schema"], "codex_fleet_leases.v2")
        self.assertEqual(store["leases"], {})

    def test_install_missing_skills_never_mutates_codex_owner(self) -> None:
        reference = {
            "discovery_roots": [".agents/skills"],
            "packages": {
                "codex-bundled": {
                    "required": True,
                    "ownership": "codex",
                    "install": {"kind": "codex-owned"},
                    "skills": ["pet"],
                },
                "owner-skill": {
                    "required": True,
                    "ownership": "external",
                    "install": {
                        "command": "npx skills add example/skills -g -a codex -s helper -y"
                    },
                    "skills": ["helper"],
                },
            },
        }
        with (
            mock.patch.object(fleet, "skill_present", side_effect=[False, False, True]),
            mock.patch.object(fleet, "run") as command,
        ):
            actions = fleet.install_missing_owner_skills(reference)
        self.assertEqual(actions, ["codex-bundled"])
        command.assert_called_once()
        self.assertEqual(command.call_args.args[0][:3], ["npx", "skills", "add"])

    def test_fetch_skill_reference_accepts_current_schema(self) -> None:
        payload = {
            "schema": fleet.SKILL_REFERENCE_SCHEMA,
            "discovery_roots": [".agents/skills"],
            "packages": {},
        }
        completed = fleet.subprocess.CompletedProcess(
            ["gh", "api"], 0, json.dumps(payload), ""
        )
        with mock.patch.object(fleet, "run", return_value=completed):
            reference = fleet.fetch_skill_reference(
                {
                    "repository": "example/instance",
                    "skill_reference": "contracts/skill-reference.json",
                },
                "a" * 40,
            )
        self.assertEqual(reference["schema"], "codex_skill_reference.v2")

    def test_fetch_skill_reference_rejects_legacy_schema(self) -> None:
        completed = fleet.subprocess.CompletedProcess(
            ["gh", "api"],
            0,
            json.dumps({"schema": "codex_skill_reference.v1"}),
            "",
        )
        with (
            mock.patch.object(fleet, "run", return_value=completed),
            self.assertRaisesRegex(fleet.FleetError, "owner skill reference"),
        ):
            fleet.fetch_skill_reference(
                {
                    "repository": "example/instance",
                    "skill_reference": "contracts/skill-reference.json",
                },
                "a" * 40,
            )

    def test_install_missing_skills_uses_owner_native_opl_route(self) -> None:
        reference = {
            "discovery_roots": [".agents/skills"],
            "packages": {
                "opl-flow": {
                    "required": True,
                    "ownership": "external",
                    "install": {
                        "command": "opl packages install opl-flow --json",
                    },
                    "skills": ["opl-flow"],
                },
            },
        }
        with (
            mock.patch.object(fleet, "skill_present", side_effect=[False, True]),
            mock.patch.object(fleet, "codex_plugin_skill_roots", return_value=()),
            mock.patch.object(fleet, "run") as command,
        ):
            actions = fleet.install_missing_owner_skills(reference)
        self.assertEqual(actions, [])
        command.assert_called_once_with(
            ["opl", "packages", "install", "opl-flow", "--json"]
        )

    def test_codex_plugin_skill_roots_reads_enabled_native_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "opl-flow"
            skill_root = plugin_root / "skills"
            (skill_root / "opl-flow").mkdir(parents=True)
            (skill_root / "opl-flow" / "SKILL.md").write_text(
                "# OPL Flow\n", encoding="utf-8"
            )
            completed = fleet.subprocess.CompletedProcess(
                ["codex", "plugin", "list", "--json"],
                0,
                json.dumps(
                    {
                        "installed": [
                            {
                                "pluginId": "opl-flow@opl-agent-opl-flow-local",
                                "installed": True,
                                "enabled": True,
                                "source": {"path": str(plugin_root)},
                            },
                            {
                                "pluginId": "disabled@example",
                                "installed": True,
                                "enabled": False,
                                "source": {"path": str(plugin_root / "disabled")},
                            },
                        ]
                    }
                ),
                "",
            )
            with mock.patch.object(fleet, "run", return_value=completed):
                roots = fleet.codex_plugin_skill_roots()
        self.assertEqual(roots, (skill_root,))

    def test_owner_native_install_accepts_plugin_managed_skills(self) -> None:
        reference = {
            "discovery_roots": [".agents/skills"],
            "packages": {
                "opl-flow": {
                    "required": True,
                    "ownership": "external",
                    "install": {
                        "command": "opl packages install opl-flow --json",
                    },
                    "skills": ["opl-flow"],
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            plugin_skills = Path(temp_dir) / "plugin" / "skills"
            (plugin_skills / "opl-flow").mkdir(parents=True)
            (plugin_skills / "opl-flow" / "SKILL.md").write_text(
                "# OPL Flow\n", encoding="utf-8"
            )
            with (
                mock.patch.object(fleet.Path, "home", return_value=home),
                mock.patch.object(
                    fleet,
                    "codex_plugin_skill_roots",
                    side_effect=[(), (plugin_skills,)],
                ),
                mock.patch.object(fleet, "run") as command,
            ):
                actions = fleet.install_missing_owner_skills(reference)
        self.assertEqual(actions, [])
        command.assert_called_once_with(
            ["opl", "packages", "install", "opl-flow", "--json"]
        )

    def test_macos_schedule_has_owner_tool_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            with (
                mock.patch.object(fleet.Path, "home", return_value=home),
                mock.patch.object(
                    fleet, "STATE_ROOT", home / ".local/state/codex-fleet"
                ),
                mock.patch.object(fleet.os, "getuid", return_value=501),
                mock.patch.object(fleet, "run") as command,
            ):
                fleet.install_macos_schedule(3, 15)
            plist_path = home / "Library/LaunchAgents/dev.one-person-lab.opl-fleet.plist"
            payload = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(
            payload["ProgramArguments"],
            [str(home / ".local/bin/opl-fleet"), "reconcile", "--report"],
        )
        self.assertEqual(
            payload["EnvironmentVariables"]["PATH"].split(":"),
            [
                str(home / ".local/bin"),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            ],
        )
        self.assertEqual(command.call_count, 2)

    def test_wsl_schedule_uses_absolute_windows_launcher(self) -> None:
        def fake_run(command: list[str], **_: object) -> object:
            stdout = ""
            if command[:2] == ["wslpath", "-w"]:
                stdout = f"C:\\Windows\\System32\\{Path(command[2]).name}\n"
            return fleet.subprocess.CompletedProcess(command, 0, stdout, "")

        with (
            mock.patch.dict(fleet.os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}),
            mock.patch.object(fleet.Path, "is_file", return_value=True),
            mock.patch.object(fleet, "run", side_effect=fake_run) as command,
        ):
            fleet.install_wsl_schedule(3, 15)
        task_command = command.call_args_list[-1].args[0]
        action = task_command[task_command.index("/TR") + 1]
        self.assertEqual(
            action,
            "C:\\Windows\\System32\\cmd.exe /d /c "
            "C:\\Windows\\System32\\wsl.exe -d Ubuntu -- "
            f"{Path.home() / '.local/bin/opl-fleet'} reconcile --report "
            "1>>%TEMP%\\opl-fleet-reconcile.stdout.log "
            "2>>%TEMP%\\opl-fleet-reconcile.stderr.log",
        )
        self.assertLessEqual(len(action), 261)

    def test_wsl_schedule_rejects_unsafe_distro_name(self) -> None:
        with mock.patch.dict(
            fleet.os.environ, {"WSL_DISTRO_NAME": "Ubuntu & whoami"}
        ):
            with self.assertRaisesRegex(fleet.FleetError, "task-safe"):
                fleet.install_wsl_schedule(3, 15)

    def test_receipt_contains_only_sanitized_node_state(self) -> None:
        payload = {
            "ok": True,
            "result": {
                "ok": True,
                "drift": [],
                "private_path": "should-not-leak",
                "logs": ["secret"],
            },
        }
        with mock.patch.object(fleet.socket, "gethostname", return_value="Studio"):
            result = fleet.build_receipt(
                "Studio",
                payload,
                owner_actions=[],
                control_revision="a" * 40,
                runner_revision="b" * 40,
            )
        self.assertEqual(set(result), fleet.RECEIPT_FIELDS)
        self.assertNotIn("private_path", result)
        self.assertNotIn("should-not-leak", json.dumps(result))
        self.assertEqual(result["state"], "CURRENT")


if __name__ == "__main__":
    unittest.main()
