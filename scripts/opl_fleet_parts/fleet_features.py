"""Inventory freshness, memory/GPU parsing, and node feature classification."""

from __future__ import annotations

from typing import Any
import datetime as dt
import re
from .fleet_common import FleetError, GPU_APIS, LIVE_ONLY_POLICY_FEATURES, parse_utc, utc_now

def inventory_is_fresh(inventory: dict[str, Any], max_age_hours: int) -> bool:
    age = inventory_age_seconds(inventory)
    return 0 <= age <= max_age_hours * 3600

def inventory_age_seconds(
    inventory: dict[str, Any],
    *,
    now: dt.datetime | None = None,
) -> int:
    observed = parse_utc(inventory["observed_at"])
    age = (now or utc_now()).astimezone(dt.timezone.utc) - observed
    return int(age.total_seconds())

def parse_memory_bytes(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    text = str(value or "").strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb)?", text, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    multiplier = {
        "b": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        None: 1,
    }[match.group(2).lower() if match.group(2) else None]
    return int(amount * multiplier)

def gpu_profiles(entry: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = entry.get("inventory") or {}
    hardware = inventory.get("hardware") or {}
    host = inventory.get("host") or {}
    system = str(host.get("system") or "").lower()
    execution = inventory.get("execution") or {}
    profiles: list[dict[str, Any]] = []
    for raw in hardware.get("gpus") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("model") or "").strip()
        if not name:
            continue
        name_lower = name.casefold()
        apis: set[str] = set()
        if "nvidia" in name_lower or "rtx" in name_lower or "quadro" in name_lower:
            apis.add("cuda")
        if system == "darwin" or str(execution.get("kind")) == "macos":
            apis.add("metal")
        memory = parse_memory_bytes(raw.get("memory_bytes") or raw.get("memory"))
        # Apple reports unified memory at the host level rather than as VRAM.
        if memory is None and "metal" in apis:
            memory = parse_memory_bytes(hardware.get("memory_bytes"))
        profiles.append(
            {
                "name": name,
                "apis": sorted(apis),
                "memory_bytes": memory,
                "driver_version": raw.get("driver_version"),
            }
        )
    return profiles

def matching_gpus(
    entry: dict[str, Any],
    *,
    gpu_api: str = "any",
    min_gpu_memory_gb: int = 0,
    gpu_model: str | None = None,
) -> list[dict[str, Any]]:
    if gpu_api not in GPU_APIS:
        raise FleetError("GPU API must be any, cuda, or metal")
    if min_gpu_memory_gb < 0:
        raise FleetError("minimum GPU memory must not be negative")
    model = gpu_model.casefold() if gpu_model else None
    minimum = min_gpu_memory_gb * 1024**3
    return [
        gpu
        for gpu in gpu_profiles(entry)
        if (gpu_api == "any" or gpu_api in gpu["apis"])
        and (gpu["memory_bytes"] or 0) >= minimum
        and (not model or model in gpu["name"].casefold())
    ]

def node_features(
    entry: dict[str, Any],
    *,
    live_only_observed: bool = False,
) -> set[str]:
    policy = entry.get("policy") or {}
    inventory = entry.get("inventory") or {}
    execution = inventory.get("execution") or {}
    hardware = inventory.get("hardware") or {}
    baseline = inventory.get("baseline") or {}
    features = {
        str(item)
        for item in policy.get("labels", [])
        if str(item) not in LIVE_ONLY_POLICY_FEATURES
    }
    for key in ("kind", "architecture"):
        if execution.get(key):
            features.add(str(execution[key]))
    profiles = gpu_profiles(entry)
    if profiles:
        features.add("gpu")
        for profile in profiles:
            features.update(profile["apis"])
    for capability, detail in baseline.items():
        if detail.get("ready") or detail.get("online") or detail.get("installed"):
            features.add(str(capability))
    for tool, detail in (inventory.get("software") or {}).items():
        if detail.get("present"):
            features.add(str(tool))
    virtualization = (inventory.get("capabilities") or {}).get("virtualization") or {}
    hyper_v = virtualization.get("hyper_v") or {}
    broker = virtualization.get("hyper_v_broker") or {}
    if (
        live_only_observed
        and virtualization.get("hypervisor_ready") is True
        and hyper_v.get("present") is True
    ):
        features.add("hyperv")
        if (
            broker.get("available") is True
            and broker.get("system_owned") is True
        ):
            features.add("windows-clean-guest-reserve")
    return features
