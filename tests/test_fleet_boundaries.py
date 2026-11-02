from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.test_opl_fleet import fleet
from opl_fleet_parts import fleet_common as common
from opl_fleet_parts import fleet_cli as cli


class FleetBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (
            ("INSTANCE_POINTER_PATH", self.root / "instance.json"),
            ("CONFIG_PATH", self.root / "node.json"),
            ("CONTROL_ROOT", common.CONTROL_ROOT),
        ):
            patch = mock.patch.object(common, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def instance(self, name, repository="example/instance"):
        instance = self.root / name
        (instance / "fleet").mkdir(parents=True)
        (instance / "fleet/fleet.json").write_text(json.dumps({"repository": repository}))
        (instance / "fleet/nodes.json").write_text("{}")
        return instance

    def test_explicit_instance_cannot_override_existing_node_binding(self):
        first, second = self.instance("first"), self.instance("second")
        common.write_instance_pointer(first)
        before = common.INSTANCE_POINTER_PATH.read_bytes()
        with self.assertRaisesRegex(common.FleetError, "bound to another"):
            common.configure_instance(second)
        with self.assertRaisesRegex(common.FleetError, "bound to another"):
            common.write_instance_pointer(second)
        self.assertEqual(common.INSTANCE_POINTER_PATH.read_bytes(), before)
        self.assertEqual(common.configure_instance(first), first.resolve())

    def test_concurrent_first_bind_keeps_one_instance(self):
        first, second = self.instance("first"), self.instance("second")
        def bind(instance):
            try:
                common.write_instance_pointer(instance)
                return instance.resolve()
            except common.FleetError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(bind, (first, second)))
        winners = [value for value in outcomes if value is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(common.instance_pointer(), winners[0])

    def test_missing_pointer_does_not_erase_existing_enrollment_identity(self):
        instance = self.instance("different", "example/other")
        common.CONFIG_PATH.write_text(json.dumps({"repository": "example/original"}))
        with self.assertRaisesRegex(common.FleetError, "enrollment belongs"):
            common.configure_instance(instance)
        self.assertFalse(common.INSTANCE_POINTER_PATH.exists())

    def test_matching_legacy_enrollment_can_bind_without_moving_state(self):
        instance = self.instance("original")
        common.CONFIG_PATH.write_text(json.dumps({"repository": "example/instance"}))
        before = common.STATE_ROOT
        common.write_instance_pointer(instance)
        self.assertEqual(common.configure_instance(None), instance.resolve())
        self.assertEqual(common.STATE_ROOT, before)
        self.assertEqual(common.INSTANCE_POINTER_PATH.stat().st_mode & 0o777, 0o600)

    def test_invalid_explicit_pointer_is_not_bypassed(self):
        instance = self.instance("original")
        common.INSTANCE_POINTER_PATH.write_text(json.dumps({"schema": "invalid", "path": str(instance)}))
        common.INSTANCE_POINTER_PATH.chmod(0o600)
        with self.assertRaisesRegex(common.FleetError, "pointer is invalid"):
            common.configure_instance(instance)

    def test_first_capacity_write_binds_but_plain_status_does_not(self):
        instance = self.instance("original")
        with mock.patch.object(cli, "fleet_status", return_value=0):
            self.assertEqual(cli.main(["--instance", str(instance), "status"]), 0)
        self.assertFalse(common.INSTANCE_POINTER_PATH.exists())
        with mock.patch.object(cli, "fleet_dispatch_acquire", return_value=0):
            self.assertEqual(cli.main([
                "--instance", str(instance), "dispatch", "acquire",
                "--owner-task", "task-one", "--adapter", "lease-only",
            ]), 0)
        self.assertEqual(common.instance_pointer(), instance.resolve())
        second = self.instance("second")
        with mock.patch.object(cli, "fleet_dispatch_acquire") as execute:
            with self.assertRaisesRegex(common.FleetError, "bound to another"):
                cli.main([
                    "--instance", str(second), "dispatch", "acquire",
                    "--owner-task", "task-two", "--adapter", "lease-only",
                ])
            execute.assert_not_called()

    def test_all_fleet_module_dependencies_are_acyclic(self):
        root = Path(fleet.__file__).parent / "opl_fleet_parts"
        files = {path.stem: path for path in root.glob("*.py")}
        graph = {name: set() for name in files}
        for name, path in files.items():
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    targets = [node.module] if node.module else [alias.name for alias in node.names]
                    graph[name].update(target for target in targets if target in graph)
        def visit(name, stack):
            self.assertNotIn(name, stack, " -> ".join([*stack, name]))
            for dependency in graph[name]:
                visit(dependency, [*stack, name])
        for name in graph:
            visit(name, [])


if __name__ == "__main__":
    unittest.main()
