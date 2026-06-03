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
TASTE_PATH = Path("TASTE.md")
MANAGED_START = "<!-- OPL_FLOW_MANAGED_START -->"
MANAGED_END = "<!-- OPL_FLOW_MANAGED_END -->"
PROFILE_POINTER = "contracts/opl-native-profile.json"


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
    return [
        {"path": "AGENTS.md", "management": "managed_block", "kind": "repo_agent_instructions"},
        {"path": "TASTE.md", "management": "managed_block", "kind": "maintenance_preferences"},
    ]


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


def managed_block(kind: str) -> str:
    return (
        f"{MANAGED_START}\n"
        f"OPL Flow managed surface: {kind}\n"
        f"Plugin: {PLUGIN_NAME}\n"
        f"Plugin version: {FLOW_VERSION}\n"
        f"Profile pointer: {PROFILE_POINTER}\n"
        "本块只声明 OPL Flow 工作流 profile 指针；repo-specific 规则、项目事实、contracts、source、tests 和 runtime 输出继续归本仓既有 owner。\n"
        "请只通过 OPL Flow repo_profile sync 更新本块；本块外内容由目标 repo 自己维护。\n"
        f"{MANAGED_END}\n"
    )


def has_profile_pointer(text: str) -> bool:
    return (
        (MANAGED_START in text and MANAGED_END in text)
        or (PROFILE_POINTER in text and ("OPL Flow" in text or PLUGIN_NAME in text))
    )


def upsert_managed_block(existing: str | None, block: str) -> str:
    if existing is None or not existing:
        return block
    start = existing.find(MANAGED_START)
    end = existing.find(MANAGED_END)
    if start != -1 and end != -1 and end >= start:
        end += len(MANAGED_END)
        suffix = existing[end:]
        if suffix.startswith("\n"):
            suffix = suffix[1:]
        updated = existing[:start].rstrip() + "\n\n" + block
        if suffix:
            updated += "\n" + suffix.lstrip("\n")
        return updated
    return existing.rstrip() + "\n\n" + block


def surface_specs() -> list[tuple[Path, str]]:
    return [
        (AGENTS_PATH, "repo_agent_instructions"),
        (TASTE_PATH, "maintenance_preferences"),
    ]


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

    for rel_path, kind in surface_specs():
        path = repo_root / rel_path
        current = path.read_text(encoding="utf-8") if path.exists() else None
        desired_surface = upsert_managed_block(current, managed_block(kind))
        if current != desired_surface:
            changes.append({"path": str(rel_path), "action": "create" if current is None else "update"})
            writes[rel_path] = desired_surface

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

    for rel_path, _kind in surface_specs():
        path = repo_root / rel_path
        if not path.exists():
            missing.append(str(rel_path))
            continue
        if not has_profile_pointer(path.read_text(encoding="utf-8")):
            errors.append(f"{rel_path} must declare OPL Flow managed block or profile pointer")

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
