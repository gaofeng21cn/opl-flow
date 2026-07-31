#!/usr/bin/env python3
"""Plan and validate OPL Flow release qualification receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "opl_flow_install_qualification_receipt.v1"
PLATFORMS = ("macos", "linux", "windows-wsl")
INSTALL_MODES = ("fresh", "upgrade")
REQUIRED_SKILLS_BY_VERSION = {
    "0.1.29": (
        "coordinate-concurrent-tasks",
        "opl-flow",
    ),
    "0.1.30": (
        "coordinate-concurrent-tasks",
        "develop-and-deliver",
        "opl-flow",
        "recover-codex-tasks",
        "task-mode-gate",
    ),
}
ROUTINE_RELEASE = "routine-release"
SYSTEM_CERTIFICATION = "system-certification"
QUALIFICATION_LEVELS = (ROUTINE_RELEASE, SYSTEM_CERTIFICATION)
SYSTEM_CERTIFICATION_TRIGGERS = (
    "carrier-contract-changed",
    "executor-discovery-changed",
    "first-supported-release",
    "install-incident",
    "package-payload-contract-changed",
    "profile-mutation-contract-changed",
    "scheduled-recertification",
    "security-boundary-changed",
    "supported-platform-changed",
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class QualificationError(RuntimeError):
    pass


def require_object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualificationError(f"{field} must be an object")
    return value


def require(value: bool, message: str) -> None:
    if not value:
        raise QualificationError(message)


def read_receipt(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read receipt {path}: {exc}") from exc
    return require_object(value, str(path)), f"sha256:{hashlib.sha256(data).hexdigest()}"


def validate_timestamp(value: object) -> None:
    require(isinstance(value, str) and value.endswith("Z"), "observed_at must be RFC3339 UTC")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError("observed_at must be RFC3339 UTC") from exc


def normalize_triggers(values: object) -> list[str]:
    require(isinstance(values, list), "qualification triggers must be a list")
    triggers = sorted(set(values))
    unknown = sorted(set(triggers) - set(SYSTEM_CERTIFICATION_TRIGGERS))
    require(not unknown, f"unsupported system-certification triggers: {unknown}")
    return triggers


def qualification_plan(triggers: list[str]) -> dict[str, Any]:
    normalized = normalize_triggers(triggers)
    level = SYSTEM_CERTIFICATION if normalized else ROUTINE_RELEASE
    if level == ROUTINE_RELEASE:
        requirements = {
            "platform_scope": "one-reference-platform",
            "install_modes": list(INSTALL_MODES),
            "new_codex_session_invocation_required": False,
        }
    else:
        requirements = {
            "platform_scope": list(PLATFORMS),
            "install_modes": list(INSTALL_MODES),
            "new_codex_session_invocation_required": True,
        }
    return {
        "schema": "opl_flow_release_qualification_plan.v1",
        "qualification_level": level,
        "system_certification_triggers": normalized,
        "requirements": requirements,
    }


def validate_receipt(
    receipt: dict[str, Any],
    *,
    expected_version: str,
    expected_predecessor_version: str,
    expected_source_commit: str,
    expected_digest: str,
) -> tuple[str, str, bool]:
    require(receipt.get("schema") == SCHEMA, f"receipt schema must be {SCHEMA}")
    require(receipt.get("status") == "passed", "receipt status must be passed")
    validate_timestamp(receipt.get("observed_at"))

    platform = require_object(receipt.get("platform"), "platform")
    family = platform.get("family")
    mode = platform.get("install_mode")
    require(family in PLATFORMS, "platform.family is unsupported")
    require(mode in INSTALL_MODES, "platform.install_mode is unsupported")
    require(isinstance(platform.get("os_version"), str) and bool(platform["os_version"].strip()), "platform.os_version is required")
    require(isinstance(platform.get("arch"), str) and bool(platform["arch"].strip()), "platform.arch is required")

    package = require_object(receipt.get("package"), "package")
    require(package.get("id") == "opl-flow", "package.id must be opl-flow")
    require(package.get("version") == expected_version, "package.version differs from expected release")
    require(package.get("owner_source_commit") == expected_source_commit, "owner source commit differs from expected release")
    require(package.get("publication_digest") == expected_digest, "publication digest differs from expected release")

    carrier = require_object(receipt.get("carrier"), "carrier")
    expected_action = "install" if mode == "fresh" else "update"
    require(carrier.get("owner_route") == f"opl packages {expected_action} opl-flow", "carrier owner route does not match install mode")
    require(carrier.get("installed_version") == expected_version, "carrier installed version differs from expected release")
    require(carrier.get("installed_source_commit") == expected_source_commit, "carrier installed source differs from expected release")
    require(carrier.get("readback_status") == "current", "carrier readback must be current")

    profile = require_object(receipt.get("profile"), "profile")
    require(profile.get("initial_state") == ("absent" if mode == "fresh" else "existing"), "profile initial state does not match install mode")
    after = profile.get("target_after_sha256")
    require(isinstance(after, str) and SHA256.fullmatch(after) is not None, "profile target_after_sha256 is invalid")
    rollback_available = profile.get("rollback_available")
    require(isinstance(rollback_available, bool), "profile rollback availability must be boolean")
    require(profile.get("review_packet_status") in {"not_required", "produced_and_unapplied", "reviewed_and_applied"}, "profile review packet status is invalid")
    if mode == "upgrade":
        require(rollback_available is True, "upgrade profile rollback must be available")
        before = profile.get("target_before_sha256")
        require(isinstance(before, str) and SHA256.fullmatch(before) is not None, "upgrade profile target_before_sha256 is invalid")
        require(profile.get("preserved_distinct_preferences") is True, "upgrade must preserve distinct profile preferences")
        require(
            receipt.get("predecessor_version") == expected_predecessor_version,
            "upgrade predecessor is not the promoted latest-stable observed before candidate promotion",
        )

    core = require_object(receipt.get("core"), "core")
    require(core == {"status": "current", "linear_configured": False, "fleet_configured": False}, "Core qualification must be current without Linear or Fleet")

    discovery = require_object(receipt.get("discovery"), "discovery")
    required_skills = REQUIRED_SKILLS_BY_VERSION.get(expected_version)
    require(required_skills is not None, "expected version has no declared core Skill set")
    require(tuple(sorted(discovery.get("skills", []))) == required_skills, "all release-bundled core Skills must be discovered")
    invocation = discovery.get("new_codex_session_invocation")
    require(invocation in {"passed", "not_run"}, "new Codex session invocation status is invalid")
    return str(family), str(mode), invocation == "passed"


def verify_qualification(
    args: argparse.Namespace,
    *,
    qualification_level: str | None = None,
) -> dict[str, Any]:
    triggers = normalize_triggers(getattr(args, "trigger", []))
    planned_level = qualification_plan(triggers)["qualification_level"]
    level = qualification_level or planned_level
    require(level in QUALIFICATION_LEVELS, "qualification level is unsupported")
    require(
        not (triggers and level != SYSTEM_CERTIFICATION),
        "system-certification triggers cannot be satisfied by routine-release",
    )
    require(SEMVER.fullmatch(args.expected_version) is not None, "expected version must be SemVer")
    require(SEMVER.fullmatch(args.expected_predecessor_version) is not None, "expected predecessor version must be SemVer")
    require(COMMIT.fullmatch(args.expected_source_commit) is not None, "expected source commit must be exact")
    require(SHA256.fullmatch(args.expected_digest) is not None, "expected digest must be sha256")
    require(args.expected_predecessor_version != args.expected_version, "predecessor and release versions must differ")

    observed: dict[tuple[str, str], dict[str, str]] = {}
    invocation_count = 0
    for receipt_path in args.receipt:
        receipt, receipt_digest = read_receipt(receipt_path)
        family, mode, invoked = validate_receipt(
            receipt,
            expected_version=args.expected_version,
            expected_predecessor_version=args.expected_predecessor_version,
            expected_source_commit=args.expected_source_commit,
            expected_digest=args.expected_digest,
        )
        key = (family, mode)
        require(key not in observed, f"duplicate qualification receipt: {family}/{mode}")
        observed[key] = {"path": str(receipt_path.resolve()), "sha256": receipt_digest}
        invocation_count += int(invoked)

    require(bool(observed), "at least one qualification receipt is required")
    if level == ROUTINE_RELEASE:
        families = {family for family, _ in observed}
        require(len(families) == 1, "routine-release receipts must use one reference platform")
        family = next(iter(families))
        expected = {(family, mode) for mode in INSTALL_MODES}
        require(
            set(observed) == expected,
            "routine-release requires fresh and upgrade receipts on one reference platform",
        )
        schema = "opl_flow_routine_release_qualification.v1"
    else:
        expected = {(platform, mode) for platform in PLATFORMS for mode in INSTALL_MODES}
        missing = sorted(expected - set(observed))
        require(not missing, f"system-certification matrix is incomplete: {missing}")
        require(invocation_count >= 1, "system-certification must prove a new Codex session Skill invocation")
        schema = "opl_flow_install_qualification_matrix.v1"
    return {
        "schema": schema,
        "status": "passed",
        "qualification_level": level,
        "system_certification_triggers": triggers,
        "package": {
            "id": "opl-flow",
            "version": args.expected_version,
            "predecessor_version": args.expected_predecessor_version,
            "owner_source_commit": args.expected_source_commit,
            "publication_digest": args.expected_digest,
        },
        "receipt_count": len(observed),
        "new_codex_session_invocation_count": invocation_count,
        "receipts": [
            {"platform": family, "install_mode": mode, **observed[(family, mode)]}
            for family, mode in sorted(observed)
        ],
    }


def verify_matrix(args: argparse.Namespace) -> dict[str, Any]:
    """Compatibility entrypoint for the full cross-platform certification."""
    return verify_qualification(args, qualification_level=SYSTEM_CERTIFICATION)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="Print the required qualification level and exit")
    parser.add_argument("--trigger", action="append", default=[], choices=SYSTEM_CERTIFICATION_TRIGGERS)
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-predecessor-version")
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-digest")
    parser.add_argument("--receipt", action="append", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.plan:
            result = qualification_plan(args.trigger)
        else:
            require(args.expected_version is not None, "expected version is required")
            require(args.expected_predecessor_version is not None, "expected predecessor version is required")
            require(args.expected_source_commit is not None, "expected source commit is required")
            require(args.expected_digest is not None, "expected digest is required")
            require(bool(args.receipt), "at least one receipt is required")
            result = verify_qualification(args)
    except QualificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
