#!/usr/bin/env python3
"""Check and sync an OPL Flow repo-local workflow profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PLUGIN_NAME = "opl-flow"
DEFAULT_FLOW_PROFILE = "opl_default"
PROFILE_PATH = Path("contracts/opl-native-profile.json")
AGENTS_PATH = Path("AGENTS.md")
LEGACY_MANAGED_START = "<!-- OPL_FLOW_MANAGED_START -->"
LEGACY_MANAGED_END = "<!-- OPL_FLOW_MANAGED_END -->"


def _load_flow_version() -> str:
    manifest_path = Path(__file__).resolve().parents[1] / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return "unknown"
    version = manifest.get("version")
    return version if isinstance(version, str) and version else "unknown"


FLOW_VERSION = _load_flow_version()


def managed_surfaces() -> list[dict[str, str]]:
    return []


def load_profile(repo_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = repo_root / PROFILE_PATH
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"{PROFILE_PATH} is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{PROFILE_PATH} must contain a JSON object"
    return payload, None


def desired_profile(existing: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(existing or {})
    payload.setdefault("schema", "opl_native_profile.v1")
    payload.setdefault("repo_id", "unknown")
    payload.setdefault("flow_profile", DEFAULT_FLOW_PROFILE)
    managed_by_plugins = dict(payload.get("managed_by_plugins") or {})
    managed_by_plugins[PLUGIN_NAME] = {
        "version": FLOW_VERSION,
        "management": "workflow_profile_pointer",
        "managed_surfaces": managed_surfaces(),
        "does_not_own": [
            "repo_specific_guidance",
            "contracts",
            "source",
            "tests",
            "runtime_outputs",
            "project_truth",
        ],
    }
    payload["managed_by_plugins"] = managed_by_plugins
    return payload


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def remove_legacy_managed_block(existing: str) -> str:
    start = existing.find(LEGACY_MANAGED_START)
    end = existing.find(LEGACY_MANAGED_END)
    if start == -1 or end == -1 or end < start:
        return existing
    end += len(LEGACY_MANAGED_END)
    prefix = existing[:start].rstrip()
    suffix = existing[end:].lstrip("\n")
    parts = [part for part in (prefix, suffix.rstrip()) if part]
    return "\n\n".join(parts) + ("\n" if parts else "")


def planned_changes(repo_root: Path) -> tuple[list[dict[str, str]], dict[Path, str], list[str]]:
    changes: list[dict[str, str]] = []
    writes: dict[Path, str] = {}
    errors: list[str] = []

    profile, profile_error = load_profile(repo_root)
    if profile_error:
        errors.append(profile_error)
    desired = desired_profile(profile)
    desired_text = render_json(desired)
    profile_file = repo_root / PROFILE_PATH
    current_profile_text = profile_file.read_text(encoding="utf-8") if profile_file.exists() else None
    if current_profile_text != desired_text:
        changes.append({"path": str(PROFILE_PATH), "action": "create" if current_profile_text is None else "update"})
        writes[PROFILE_PATH] = desired_text

    agents_file = repo_root / AGENTS_PATH
    if agents_file.exists():
        current_agents = agents_file.read_text(encoding="utf-8")
        desired_agents = remove_legacy_managed_block(current_agents)
        if current_agents != desired_agents:
            changes.append({"path": str(AGENTS_PATH), "action": "remove_legacy_managed_block"})
            writes[AGENTS_PATH] = desired_agents

    return changes, writes, errors


def write_changes(repo_root: Path, writes: dict[Path, str]) -> None:
    for rel_path, content in writes.items():
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check_repo(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    missing: list[str] = []
    errors: list[str] = []
    profile, profile_error = load_profile(repo_root)
    if profile_error:
        errors.append(profile_error)
    if profile is None:
        missing.append(str(PROFILE_PATH))
    else:
        managed = profile.get("managed_by_plugins")
        if not isinstance(managed, dict) or PLUGIN_NAME not in managed:
            errors.append(f"{PROFILE_PATH} managed_by_plugins.{PLUGIN_NAME} is required")
        else:
            flow_entry = managed[PLUGIN_NAME]
            if not isinstance(flow_entry, dict):
                errors.append(f"{PROFILE_PATH} managed_by_plugins.{PLUGIN_NAME} must be an object")
            else:
                if flow_entry.get("version") != FLOW_VERSION:
                    errors.append(f"{PROFILE_PATH} managed_by_plugins.{PLUGIN_NAME}.version must be {FLOW_VERSION}")
                if flow_entry.get("managed_surfaces") != managed_surfaces():
                    errors.append(f"{PROFILE_PATH} managed_by_plugins.{PLUGIN_NAME}.managed_surfaces are out of sync")

    agents_file = repo_root / AGENTS_PATH
    if agents_file.exists() and LEGACY_MANAGED_START in agents_file.read_text(encoding="utf-8"):
        errors.append(f"{AGENTS_PATH} contains a legacy OPL Flow managed block")

    ok = not missing and not errors
    return {
        "ok": ok,
        "mode": "check",
        "apply": False,
        "repo_root": str(repo_root),
        "plugin": PLUGIN_NAME,
        "flow_version": FLOW_VERSION,
        "profile_path": str(PROFILE_PATH),
        "missing": missing,
        "errors": errors,
    }


def sync_repo(repo_root: Path, apply: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    changes, writes, errors = planned_changes(repo_root)
    if apply and not errors:
        write_changes(repo_root, writes)
        check = check_repo(repo_root)
        return {
            **check,
            "mode": "sync",
            "apply": True,
            "planned_changes": changes,
            "errors": check["errors"],
        }
    check = check_repo(repo_root)
    return {
        **check,
        "mode": "sync",
        "apply": apply,
        "ok": check["ok"] if apply else check["ok"] and not changes,
        "planned_changes": changes,
        "errors": errors + check["errors"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check or sync an OPL Flow repo-local profile")
    parser.add_argument("mode", nargs="?", choices=("check", "sync"), default="check")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect or update.")
    parser.add_argument("--apply", action="store_true", help="Apply sync changes. Without this, sync is a dry-run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser()
    mode = "sync" if args.apply else args.mode
    result = sync_repo(repo_root, apply=args.apply) if mode == "sync" else check_repo(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
