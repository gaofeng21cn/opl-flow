from __future__ import annotations

import unittest

from scripts.verify import CORE_TEST_MODULES, OPS_KIT_TEST_MODULES, contract_test_modules


class VerifyLaneTests(unittest.TestCase):
    def test_default_lanes_keep_core_and_optional_tests_disjoint(self) -> None:
        core = contract_test_modules("core")
        ops_kit = contract_test_modules("ops-kit")

        self.assertEqual(core, CORE_TEST_MODULES)
        self.assertEqual(ops_kit, OPS_KIT_TEST_MODULES)
        self.assertFalse(set(core) & set(ops_kit))
        self.assertEqual(contract_test_modules("full"), (*core, *ops_kit))


if __name__ == "__main__":
    unittest.main()
