from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "fleet-telemetry-protocol.json"
SCHEMA = ROOT / "contracts" / "fleet-telemetry-protocol.schema.json"
PROVIDER_SCHEMA = ROOT / "contracts" / "fleet-agent-provider.schema.json"


class FleetTelemetryProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.provider_schema = json.loads(PROVIDER_SCHEMA.read_text(encoding="utf-8"))

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

    def test_provider_abi_is_read_only_and_observation_only(self) -> None:
        provider = self.contract["provider_abi"]
        self.assertEqual(provider["schema_ref"], "./fleet-agent-provider.schema.json")
        self.assertEqual(provider["schema"], "opl_fleet_agent_provider.v1")
        self.assertEqual(
            provider["capability_abi"],
            {"id": "opl-fleet-agent.capabilities", "version": "1.0.0"},
        )
        self.assertEqual(provider["access"], "read_only")
        self.assertEqual(provider["authority"], "observation_only")
        self.assertEqual(set(provider["operations"]), {"telemetry.read", "doctor.read"})
        self.assertEqual(
            provider["read_refs"],
            {
                "telemetry": "fleet.agent.telemetry.v1#local",
                "doctor": "fleet.agent.doctor.v1#current",
            },
        )
        self.assertEqual(
            provider["projection_status"],
            {
                "telemetry": "projected",
                "doctor": "projected",
                "execution_constraints": "not_projected",
                "execution_receipts": "deferred",
            },
        )

    def test_provider_payload_requires_explicit_freshness(self) -> None:
        properties = self.provider_schema["properties"]
        self.assertEqual(properties["schema"]["const"], "opl_fleet_agent_provider.v1")
        capability_abi = properties["capability_abi"]
        self.assertEqual(capability_abi["properties"]["id"]["const"], "opl-fleet-agent.capabilities")
        self.assertEqual(capability_abi["properties"]["version"]["const"], "1.0.0")
        self.assertEqual(properties["access"]["const"], "read_only")
        self.assertEqual(properties["authority"]["const"], "observation_only")
        freshness = self.provider_schema["$defs"]["freshness"]
        self.assertTrue({"state", "last_observed_at", "last_known"}.issubset(freshness["required"]))
        self.assertEqual(
            set(freshness["properties"]["state"]["enum"]),
            {"fresh", "stale", "unavailable"},
        )
        stale_rule = freshness["allOf"][0]
        self.assertEqual(stale_rule["if"]["properties"]["state"]["const"], "stale")
        self.assertEqual(stale_rule["then"]["properties"]["last_known"]["const"], True)

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
            "content",
            "conversation_content",
            "raw_prompt",
            "raw_response",
            "raw_content",
            "session_id",
            "local_path",
            "interface",
            "interface_name",
            "address",
            "network_address",
            "credential",
            "secret",
            "raw_log",
        }.issubset(forbidden))
        self.assertEqual(
            forbidden,
            set(self.contract["provider_abi"]["forbidden_fields"]),
        )


if __name__ == "__main__":
    unittest.main()
