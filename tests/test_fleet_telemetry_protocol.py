from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "fleet-telemetry-protocol.json"
SCHEMA = ROOT / "contracts" / "fleet-telemetry-protocol.schema.json"


class FleetTelemetryProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def test_contract_matches_the_declared_schema_shape(self) -> None:
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(set(self.contract), set(self.schema["required"]))
        self.assertEqual(self.contract["$schema"], self.schema["properties"]["$schema"]["const"])
        self.assertEqual(self.contract["schema"], self.schema["properties"]["schema"]["const"])
        self.assertEqual(
            set(self.contract["product_terms"]),
            set(self.schema["properties"]["product_terms"]["required"]),
        )
        self.assertEqual(
            set(self.contract["authority"]),
            set(self.schema["properties"]["authority"]["required"]),
        )

    def test_controller_remains_the_only_dispatch_authority(self) -> None:
        authority = self.contract["authority"]
        self.assertIn("dispatch_and_execution_adapter_selection", authority["controller"]["owns"])
        for role in ("node_agent", "telemetry_gateway", "cockpit"):
            self.assertIn("dispatch_authority", authority[role]["must_not_own"])

    def test_modes_and_compatibility_identities_are_stable(self) -> None:
        self.assertEqual({item["id"] for item in self.contract["modes"]}, {"local", "direct", "fleet"})
        compatibility = self.contract["compatibility"]
        self.assertEqual(compatibility["service_identifiers"]["direct"], "_codex-tps._tcp.local")
        self.assertEqual(compatibility["service_identifiers"]["gateway"], "_ambient-ops._tcp.local")
        self.assertTrue({"repository_urls", "bundle_identifiers", "android_package_names"}.issubset(compatibility["preserve"]))

    def test_privacy_denylist_is_explicit(self) -> None:
        forbidden = set(self.contract["telemetry_envelope"]["forbidden_fields"])
        self.assertTrue({
            "prompt",
            "response",
            "conversation_content",
            "session_id",
            "local_path",
            "interface_name",
            "network_address",
            "credential",
            "raw_log",
        }.issubset(forbidden))


if __name__ == "__main__":
    unittest.main()
