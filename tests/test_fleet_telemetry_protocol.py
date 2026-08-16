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
        self.assertEqual(properties["native_carrier"]["$ref"], "#/$defs/nativeCarrier")
        self.assertEqual(
            properties["node"]["oneOf"],
            [{"$ref": "#/$defs/nodeIdentity"}, {"type": "null"}],
        )
        freshness = self.provider_schema["$defs"]["freshness"]
        self.assertTrue({"state", "last_observed_at", "last_known"}.issubset(freshness["required"]))
        self.assertEqual(
            set(freshness["properties"]["state"]["enum"]),
            {"fresh", "stale", "unavailable"},
        )
        stale_rule = freshness["allOf"][0]
        self.assertEqual(stale_rule["if"]["properties"]["state"]["const"], "stale")
        self.assertEqual(stale_rule["then"]["properties"]["last_known"]["const"], True)

    def test_provider_telemetry_has_fixed_one_and_five_minute_rates(self) -> None:
        telemetry = self.provider_schema["$defs"]["telemetryPayload"]
        self.assertEqual(
            set(telemetry["required"]),
            {
                "collection_status",
                "windows",
                "active_conversation_count",
                "host_cpu_percent",
                "host_network_receive_bytes_per_second",
                "host_network_transmit_bytes_per_second",
                "host_capability_flags",
            },
        )
        windows = telemetry["properties"]["windows"]
        self.assertEqual(set(windows["required"]), {"one_minute", "five_minutes"})
        self.assertEqual(
            windows["properties"],
            {
                "one_minute": {"$ref": "#/$defs/oneMinuteRateWindow"},
                "five_minutes": {"$ref": "#/$defs/fiveMinuteRateWindow"},
            },
        )
        for definition, seconds in (("oneMinuteRateWindow", 60), ("fiveMinuteRateWindow", 300)):
            window = self.provider_schema["$defs"][definition]
            self.assertEqual(window["properties"]["window_seconds"]["const"], seconds)
            self.assertTrue(
                {"window_seconds", "token_rate_per_second", "request_rate_per_minute"}.issubset(
                    window["required"]
                )
            )

    def test_unavailable_carrier_does_not_require_sentinel_identity(self) -> None:
        carrier = self.provider_schema["$defs"]["nativeCarrier"]
        self.assertEqual(
            set(carrier["properties"]["availability"]["enum"]),
            {"available", "unavailable"},
        )
        unavailable_rule = next(
            rule
            for rule in self.provider_schema["allOf"]
            if rule.get("if", {}).get("properties", {}).get("native_carrier")
        )
        self.assertEqual(
            unavailable_rule["if"]["properties"]["native_carrier"]
            ["properties"]["availability"]["const"],
            "unavailable",
        )
        self.assertEqual(
            unavailable_rule["then"]["properties"]["freshness"]["properties"]["state"]["const"],
            "unavailable",
        )
        available_rule = next(
            rule
            for rule in self.provider_schema["allOf"]
            if rule.get("if", {})
            .get("properties", {})
            .get("native_carrier", {})
            .get("properties", {})
            .get("availability", {})
            .get("const")
            == "available"
        )
        self.assertEqual(
            available_rule["then"]["properties"]["node"],
            {"$ref": "#/$defs/nodeIdentity"},
        )
        no_observation_rule = next(
            rule
            for rule in self.provider_schema["allOf"]
            if rule.get("if", {})
            .get("properties", {})
            .get("freshness", {})
            .get("properties", {})
            .get("last_known", {})
            .get("const")
            is False
        )
        self.assertEqual(no_observation_rule["then"]["properties"]["node"], {"type": "null"})

    def test_no_last_known_observation_uses_null_metrics_and_unavailable_doctor(self) -> None:
        telemetry = self.provider_schema["$defs"]["unavailableTelemetryPayload"]
        telemetry_properties = telemetry["allOf"][1]["properties"]
        self.assertEqual(telemetry_properties["collection_status"]["const"], "unavailable")
        for window in ("one_minute", "five_minutes"):
            rate_properties = telemetry_properties["windows"]["properties"][window]["properties"]
            self.assertEqual(rate_properties["token_rate_per_second"], {"type": "null"})
            self.assertEqual(rate_properties["request_rate_per_minute"], {"type": "null"})
        for field in (
            "active_conversation_count",
            "host_cpu_percent",
            "host_network_receive_bytes_per_second",
            "host_network_transmit_bytes_per_second",
        ):
            self.assertEqual(telemetry_properties[field], {"type": "null"})

        doctor = self.provider_schema["$defs"]["unavailableDoctorPayload"]
        doctor_properties = doctor["allOf"][1]["properties"]
        self.assertEqual(doctor_properties["doctor_state"]["const"], "unavailable")
        self.assertEqual(doctor_properties["capability_currentness"]["const"], "unavailable")
        self.assertEqual(doctor_properties["checks"], {"maxItems": 0})

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
