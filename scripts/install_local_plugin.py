#!/usr/bin/env python3
"""Install OPL Flow as a local Codex plugin and optional user profile."""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_NAME = "opl-flow"
MARKETPLACE_NAME = "opl-flow-local"
MARKETPLACE_MANIFEST = Path(".agents/plugins/marketplace.json")
RUNTIME_PROFILE_NAMES = ("AGENTS.md",)
AUTHORING_SOURCE_NAMES = ("TASTE.md",)
MERGE_PACKET_SCHEMA = "opl_flow_profile_merge_packet.v2"
PROFILE_RECEIPT_SCHEMA = "opl_flow_profile_install_receipt.v2"
COPY_IGNORE_NAMES = (".git", ".worktrees", ".codegraph", ".pytest_cache", "__pycache__", ".DS_Store")
PLUGIN_REQUIRED_FILES = (
    ".agents/plugins/marketplace.json",
    ".codex-plugin/plugin.json",
    "skills/opl-flow/SKILL.md",
    "skills/opl-flow/agents/openai.yaml",
    "profile/manifest.json",
    "profile/modules/01-user-preferences.md",
    "templates/AGENTS.md",
    "templates/TASTE.md",
    "scripts/profile_compose.py",
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_tree(repo_root: Path, plugins_dir: Path) -> Path:
    target = plugins_dir / PLUGIN_NAME
    if target.exists():
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns(*COPY_IGNORE_NAMES)
    shutil.copytree(repo_root, target, ignore=ignore)
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_receipt_path(codex_home: Path) -> Path:
    return codex_home / "state" / PLUGIN_NAME / "profile-install-receipt.json"


def profile_hashes(repo_root: Path, codex_home: Path) -> tuple[dict[str, str], dict[str, str], list[str]]:
    source_hashes: dict[str, str] = {}
    target_hashes: dict[str, str] = {}
    missing: list[str] = []
    for source, target in profile_checks(repo_root, codex_home):
        rel = str(target.relative_to(codex_home))
        source_hashes[rel] = sha256_file(source)
        if target.exists():
            target_hashes[rel] = sha256_file(target)
        else:
            missing.append(rel)
    return source_hashes, target_hashes, missing


def support_hashes(repo_root: Path, codex_home: Path) -> tuple[dict[str, str], dict[str, str], list[str]]:
    source_hashes: dict[str, str] = {}
    target_hashes: dict[str, str] = {}
    missing: list[str] = []
    for source, target in support_checks(repo_root, codex_home):
        rel = str(target.relative_to(codex_home))
        source_hashes[rel] = sha256_file(source)
        if target.exists():
            target_hashes[rel] = sha256_file(target)
        else:
            missing.append(rel)
    return source_hashes, target_hashes, missing


def support_surface_status(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    source_hashes, target_hashes, missing = support_hashes(repo_root, codex_home)
    states = {
        rel: (
            "missing"
            if rel in missing
            else "current"
            if target_hashes.get(rel) == source_hash
            else "local_or_source_drift"
        )
        for rel, source_hash in source_hashes.items()
    }
    return {
        "runtime_required": False,
        "states": states,
        "missing": missing,
        "drift": sorted(rel for rel, state in states.items() if state == "local_or_source_drift"),
    }


def write_profile_receipt(repo_root: Path, codex_home: Path) -> Path:
    source_hashes, target_hashes, missing = profile_hashes(repo_root, codex_home)
    if missing:
        raise ValueError(f"cannot record incomplete profile receipt: {missing}")
    support_source_hashes, support_target_hashes, support_missing = support_hashes(repo_root, codex_home)
    path = profile_receipt_path(codex_home)
    write_json(
        path,
        {
            "schema": PROFILE_RECEIPT_SCHEMA,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "runtime_source_hashes": source_hashes,
            "runtime_target_hashes": target_hashes,
            "support_source_hashes": support_source_hashes,
            "support_target_hashes": support_target_hashes,
            "support_missing": support_missing,
        },
    )
    return path


def profile_state(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    source_hashes, target_hashes, missing = profile_hashes(repo_root, codex_home)
    support = support_surface_status(repo_root, codex_home)
    if missing:
        status = "merge_required" if (codex_home / "AGENTS.md").exists() else "missing"
        return {"status": status, "missing": missing, "receipt": None, "support": support}
    if source_hashes == target_hashes:
        return {
            "status": "current",
            "missing": [],
            "receipt": str(profile_receipt_path(codex_home)),
            "support": support,
        }

    receipt_path = profile_receipt_path(codex_home)
    receipt = load_json(receipt_path)
    if receipt.get("schema") != PROFILE_RECEIPT_SCHEMA:
        return {"status": "merge_required", "missing": [], "receipt": None, "support": support}

    approved_source = receipt.get("runtime_source_hashes")
    approved_target = receipt.get("runtime_target_hashes")
    if source_hashes == approved_source and target_hashes == approved_target:
        return {
            "status": "local_overlay",
            "missing": [],
            "receipt": str(receipt_path),
            "support": support,
        }
    if target_hashes == approved_target and approved_target == approved_source:
        return {
            "status": "source_update",
            "missing": [],
            "receipt": str(receipt_path),
            "support": support,
        }
    return {
        "status": "merge_required",
        "missing": [],
        "receipt": str(receipt_path),
        "support": support,
    }


def backup_and_copy(source: Path, target: Path, backup_root: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and filecmp.cmp(source, target, shallow=False):
        return False
    if target.exists():
        backup_target = backup_root / target.relative_to(target.anchor)
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_target)
    shutil.copy2(source, target)
    return True


def profile_checks(repo_root: Path, codex_home: Path) -> list[tuple[Path, Path]]:
    templates = repo_root / "templates"
    return [(templates / name, codex_home / name) for name in RUNTIME_PROFILE_NAMES]


def support_checks(repo_root: Path, codex_home: Path) -> list[tuple[Path, Path]]:
    templates = repo_root / "templates"
    return [(templates / name, codex_home / name) for name in AUTHORING_SOURCE_NAMES]


def install_missing_support_surfaces(repo_root: Path, codex_home: Path) -> list[str]:
    changed: list[str] = []
    for source, target in support_checks(repo_root, codex_home):
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changed.append(str(target))
    return changed


def tree_mismatches(
    source: Path,
    target: Path,
    label: str,
    ignored_names: tuple[str, ...] = (),
) -> list[str]:
    ignored = set(ignored_names)
    source_files = {
        path.relative_to(source)
        for path in source.rglob("*")
        if path.is_file() and not ignored.intersection(path.relative_to(source).parts)
    }
    target_files = (
        {
            path.relative_to(target)
            for path in target.rglob("*")
            if path.is_file() and not ignored.intersection(path.relative_to(target).parts)
        }
        if target.exists()
        else set()
    )
    mismatches = [f"missing:{label}/{path}" for path in sorted(source_files - target_files)]
    mismatches.extend(f"unexpected:{label}/{path}" for path in sorted(target_files - source_files))
    mismatches.extend(
        f"content:{label}/{path}"
        for path in sorted(source_files & target_files)
        if not filecmp.cmp(source / path, target / path, shallow=False)
    )
    return mismatches


def plugin_version(plugin_path: Path) -> str:
    manifest = load_json(plugin_path / ".codex-plugin" / "plugin.json")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("plugin manifest version is required")
    return version


def plugin_cache_path(codex_home: Path, plugin_path: Path) -> Path:
    return codex_home / "plugins" / "cache" / MARKETPLACE_NAME / PLUGIN_NAME / plugin_version(plugin_path)


def json_entries(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if key == "plugins":
        entries: list[dict[str, Any]] = []
        for section in ("installed", "available"):
            items = payload.get(section)
            if isinstance(items, list):
                entries.extend(item for item in items if isinstance(item, dict))
        return entries
    items = payload.get(key)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def normalized_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return str(Path(value).expanduser().resolve(strict=False))


def plugin_readback_status(
    payload: Any,
    *,
    plugin_name: str,
    marketplace_name: str,
    version: str,
    expected_root: Path | None = None,
) -> dict[str, Any]:
    plugin_id = f"{plugin_name}@{marketplace_name}"
    matches = [
        item
        for item in json_entries(payload, "plugins")
        if item.get("pluginId") == plugin_id
    ]
    if len(matches) != 1:
        return {"ok": False, "plugin_id": plugin_id, "reason": "exact_plugin_match_required", "matches": matches}

    item = matches[0]
    expected = str(expected_root.resolve()) if expected_root else None
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    marketplace_source = item.get("marketplaceSource") if isinstance(item.get("marketplaceSource"), dict) else {}
    source_path = normalized_path(source.get("path"))
    marketplace_path = normalized_path(marketplace_source.get("source"))
    checks = {
        "installed": item.get("installed") is True,
        "enabled": item.get("enabled") is True,
        "version": item.get("version") == version,
        "source": source.get("source") == "local" if source else True,
        "source_path": expected is None or source_path == expected,
        "marketplace_path": expected is None or marketplace_path == expected,
    }
    return {
        "ok": all(checks.values()),
        "plugin_id": plugin_id,
        "version": item.get("version"),
        "installed": item.get("installed"),
        "enabled": item.get("enabled"),
        "source_path": source_path,
        "marketplace_path": marketplace_path,
        "checks": checks,
    }


def marketplace_readback_status(payload: Any, marketplace_name: str, expected_root: Path) -> dict[str, Any]:
    matches = [item for item in json_entries(payload, "marketplaces") if item.get("name") == marketplace_name]
    expected = str(expected_root.resolve())
    exact = [item for item in matches if normalized_path(item.get("root")) == expected]
    return {
        "ok": len(matches) == 1 and len(exact) == 1,
        "name": marketplace_name,
        "root": expected,
        "matches": matches,
    }


def run_codex_json(codex_bin: str, *args: str) -> Any:
    result = subprocess.run(
        [codex_bin, *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"codex {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"codex {' '.join(args)} returned invalid JSON: {result.stdout}") from exc


def ensure_marketplace(codex_bin: str, marketplace_root: Path) -> dict[str, Any]:
    payload = run_codex_json(codex_bin, "plugin", "marketplace", "list", "--json")
    status = marketplace_readback_status(payload, MARKETPLACE_NAME, marketplace_root)
    if status["ok"]:
        return status
    if status["matches"]:
        raise RuntimeError(f"marketplace {MARKETPLACE_NAME} is already bound to another root: {status['matches']}")
    run_codex_json(codex_bin, "plugin", "marketplace", "add", str(marketplace_root), "--json")
    payload = run_codex_json(codex_bin, "plugin", "marketplace", "list", "--json")
    status = marketplace_readback_status(payload, MARKETPLACE_NAME, marketplace_root)
    if not status["ok"]:
        raise RuntimeError(f"marketplace readback failed: {status}")
    return status


def read_plugin_status(codex_bin: str, plugin_path: Path) -> dict[str, Any]:
    payload = run_codex_json(
        codex_bin,
        "plugin",
        "list",
        "--available",
        "--json",
        "--marketplace",
        MARKETPLACE_NAME,
    )
    return plugin_readback_status(
        payload,
        plugin_name=PLUGIN_NAME,
        marketplace_name=MARKETPLACE_NAME,
        version=plugin_version(plugin_path),
        expected_root=plugin_path,
    )


def install_codex_plugin(codex_bin: str, plugin_path: Path) -> dict[str, Any]:
    marketplace = ensure_marketplace(codex_bin, plugin_path)
    install_result = run_codex_json(
        codex_bin,
        "plugin",
        "add",
        f"{PLUGIN_NAME}@{MARKETPLACE_NAME}",
        "--json",
    )
    status = read_plugin_status(codex_bin, plugin_path)
    if not status["ok"]:
        raise RuntimeError(f"plugin installed/enabled readback failed: {status}")
    return {"marketplace": marketplace, "install": install_result, "plugin": status}


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_candidate_profile(repo_root: Path, packet: Path) -> None:
    templates = repo_root / "templates"
    candidate = packet / "candidate"
    for name in (*RUNTIME_PROFILE_NAMES, *AUTHORING_SOURCE_NAMES):
        copy_if_exists(templates / name, candidate / name)
    copy_if_exists(repo_root / "profile" / "manifest.json", candidate / "profile" / "manifest.json")
    modules_root = repo_root / "profile" / "modules"
    if modules_root.exists():
        shutil.copytree(modules_root, candidate / "profile" / "modules", dirs_exist_ok=True)


def copy_existing_profile(codex_home: Path, packet: Path) -> list[str]:
    copied: list[str] = []
    existing = packet / "existing"
    for name in (*RUNTIME_PROFILE_NAMES, *AUTHORING_SOURCE_NAMES):
        if copy_if_exists(codex_home / name, existing / name):
            copied.append(name)
    return copied


def merge_prompt() -> str:
    return """# OPL Flow profile semantic merge

You are Codex performing a semantic merge for an OPL Flow user profile install.

Read these inputs:

- `existing/AGENTS.md` and any other files under `existing/`
- `candidate/AGENTS.md`
- `candidate/TASTE.md` (non-runtime authoring source)
- `candidate/profile/manifest.json`
- `candidate/profile/modules/*.md`

Rules:

1. Do not mechanically concatenate the files.
2. Preserve user-specific preferences and local machine rules unless they clearly conflict with higher-priority user instructions.
3. Treat `AGENTS.md` as the only runtime profile. Preserve user-specific runtime rules there.
4. Treat `TASTE.md` as a non-runtime authoring source.
5. Do not hardcode project/domain instance facts into the user-level `AGENTS.md`; route them to the owning repo `AGENTS.md`, docs, contracts, runtime/readback, or explicit context overlay.
6. Preserve official marker blocks and managed tool blocks unless the corresponding tool is confirmed retired.
7. Preserve concise user tool preferences such as RTK and CodeGraph without adding a development methodology.
8. Report any unresolved conflict instead of silently choosing one side.

Write outputs under `output/`:

- `output/AGENTS.md`: merged user-level AGENTS profile
- `output/TASTE.md` (optional): intentionally updated authoring source
- `output/merge-report.md`: what was preserved, changed, rejected, and why

Do not apply the merge directly to `~/.codex`. The installer or operator will
review and apply the output after this semantic merge is complete.
"""


def create_merge_packet(repo_root: Path, codex_home: Path, reason: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    packet = codex_home / "state" / PLUGIN_NAME / "profile-merge" / timestamp
    packet.mkdir(parents=True, exist_ok=False)
    candidate_source_hashes, existing_target_hashes, existing_missing = profile_hashes(
        repo_root,
        codex_home,
    )
    support_source_hashes, support_target_hashes, support_missing = support_hashes(
        repo_root,
        codex_home,
    )
    copied_existing = copy_existing_profile(codex_home, packet)
    copy_candidate_profile(repo_root, packet)
    (packet / "output").mkdir()
    (packet / "prompt.md").write_text(merge_prompt(), encoding="utf-8")

    plan = {
        "schema": MERGE_PACKET_SCHEMA,
        "created_at": timestamp,
        "plugin": PLUGIN_NAME,
        "reason": reason,
        "status": "requires_codex_semantic_merge",
        "existing_files": copied_existing,
        "candidate_profile": "candidate/AGENTS.md",
        "candidate_manifest": "candidate/profile/manifest.json",
        "candidate_source_hashes": candidate_source_hashes,
        "existing_target_hashes": existing_target_hashes,
        "existing_missing": existing_missing,
        "support_candidate_source_hashes": support_source_hashes,
        "support_existing_target_hashes": support_target_hashes,
        "support_existing_missing": support_missing,
        "prompt": "prompt.md",
        "output_dir": "output",
        "apply_policy": "review_codex_output_then_apply_with_backup",
        "apply_command": f"python3 scripts/install_local_plugin.py --apply-merge-packet {packet}",
        "script_merge_policy": "disabled",
    }
    write_json(packet / "merge-plan.json", plan)
    return {
        "status": "requires_codex_semantic_merge",
        "changed": [],
        "backup_root": None,
        "merge_packet": str(packet),
        "reason": reason,
    }


def apply_merge_packet(repo_root: Path, codex_home: Path, packet: Path) -> dict[str, Any]:
    packet = packet.expanduser().resolve()
    merge_root = (codex_home / "state" / PLUGIN_NAME / "profile-merge").resolve()
    if packet.parent != merge_root:
        raise ValueError(f"merge packet must be directly under {merge_root}: {packet}")

    plan_path = packet / "merge-plan.json"
    plan = load_json(plan_path)
    if plan.get("schema") != MERGE_PACKET_SCHEMA or plan.get("plugin") != PLUGIN_NAME:
        raise ValueError(f"invalid OPL Flow merge packet: {packet}")
    if plan.get("status") != "requires_codex_semantic_merge":
        raise ValueError(f"merge packet is not pending: {plan.get('status')}")

    current_source_hashes, current_target_hashes, current_missing = profile_hashes(
        repo_root,
        codex_home,
    )
    if current_source_hashes != plan.get("candidate_source_hashes"):
        raise ValueError("profile source changed after packet creation; create a new merge packet")
    if (
        current_target_hashes != plan.get("existing_target_hashes")
        or current_missing != plan.get("existing_missing")
    ):
        raise ValueError("profile target changed after packet creation; create a new merge packet")

    output = packet / "output"
    output_files = [(output / name, codex_home / name) for name in RUNTIME_PROFILE_NAMES]
    optional_output_files = [
        (output / name, codex_home / name) for name in AUTHORING_SOURCE_NAMES
    ]
    if any(source.is_file() for source, _ in optional_output_files):
        support_source_hashes, support_target_hashes, support_missing = support_hashes(
            repo_root,
            codex_home,
        )
        if support_source_hashes != plan.get("support_candidate_source_hashes"):
            raise ValueError("support source changed after packet creation; create a new merge packet")
        if (
            support_target_hashes != plan.get("support_existing_target_hashes")
            or support_missing != plan.get("support_existing_missing")
        ):
            raise ValueError("support target changed after packet creation; create a new merge packet")
    required = [source for source, _ in output_files] + [output / "merge-report.md"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"merge packet output is incomplete: {missing}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = codex_home / "backups" / PLUGIN_NAME / timestamp
    changed: list[str] = []
    for source, target in output_files:
        if backup_and_copy(source, target, backup_root):
            changed.append(str(target))
    for source, target in optional_output_files:
        if source.is_file() and backup_and_copy(source, target, backup_root):
            changed.append(str(target))

    changed.extend(install_missing_support_surfaces(repo_root, codex_home))

    receipt = write_profile_receipt(repo_root, codex_home)
    plan.update(
        {
            "status": "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "receipt": str(receipt),
            "backup_root": str(backup_root) if backup_root.exists() else None,
        }
    )
    write_json(plan_path, plan)
    return {
        "status": "applied",
        "changed": changed,
        "backup_root": str(backup_root) if backup_root.exists() else None,
        "merge_packet": str(packet),
        "receipt": str(receipt),
    }


def install_profile(repo_root: Path, codex_home: Path) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_root = codex_home / "backups" / PLUGIN_NAME / timestamp
    changed: list[str] = []

    agents_path = codex_home / "AGENTS.md"
    if agents_path.exists():
        state = profile_state(repo_root, codex_home)
        if state["status"] == "current":
            changed.extend(install_missing_support_surfaces(repo_root, codex_home))
            receipt = write_profile_receipt(repo_root, codex_home)
            return {
                "status": "current",
                "changed": changed,
                "backup_root": None,
                "receipt": str(receipt),
                "support": support_surface_status(repo_root, codex_home),
            }
        if state["status"] == "local_overlay":
            changed.extend(install_missing_support_surfaces(repo_root, codex_home))
            return {
                "status": "local_overlay",
                "changed": changed,
                "backup_root": None,
                "receipt": state["receipt"],
                "support": support_surface_status(repo_root, codex_home),
            }
        if state["status"] == "source_update":
            for source, target in profile_checks(repo_root, codex_home):
                if backup_and_copy(source, target, backup_root):
                    changed.append(str(target))
            changed.extend(install_missing_support_surfaces(repo_root, codex_home))
            receipt = write_profile_receipt(repo_root, codex_home)
            return {
                "status": "updated",
                "changed": changed,
                "backup_root": str(backup_root) if backup_root.exists() else None,
                "receipt": str(receipt),
                "support": support_surface_status(repo_root, codex_home),
            }
        return create_merge_packet(
            repo_root,
            codex_home,
            "existing_user_agents_requires_codex_semantic_merge",
        )

    for source, target in profile_checks(repo_root, codex_home):
        if backup_and_copy(source, target, backup_root):
            changed.append(str(target))
    changed.extend(install_missing_support_surfaces(repo_root, codex_home))

    receipt = write_profile_receipt(repo_root, codex_home)

    return {
        "status": "installed",
        "changed": changed,
        "backup_root": str(backup_root) if backup_root.exists() else None,
        "receipt": str(receipt),
        "support": support_surface_status(repo_root, codex_home),
    }


def install(
    repo_root: Path,
    plugins_dir: Path,
    codex_home: Path,
    profile: bool,
    codex_bin: str,
) -> dict[str, Any]:
    plugin_path = copy_tree(repo_root, plugins_dir)
    marketplace_path = plugin_path / MARKETPLACE_MANIFEST
    plugin_result = install_codex_plugin(codex_bin, plugin_path)
    profile_result = install_profile(repo_root, codex_home) if profile else {"status": "skipped", "changed": [], "backup_root": None}
    pending_merge = profile_result["status"] == "requires_codex_semantic_merge"
    return {
        "ok": not pending_merge,
        "status": "profile_merge_required" if pending_merge else "installed",
        "plugin_path": str(plugin_path),
        "marketplace_path": str(marketplace_path),
        "codex": plugin_result,
        "profile": profile_result,
    }


def latest_merge_packet(codex_home: Path) -> str | None:
    root = codex_home / "state" / PLUGIN_NAME / "profile-merge"
    if not root.exists():
        return None
    packets = sorted(path for path in root.iterdir() if path.is_dir())
    return str(packets[-1]) if packets else None


def verify_profile(repo_root: Path, codex_home: Path, profile: bool) -> dict[str, Any]:
    if not profile:
        return {
            "status": "skipped",
            "mismatches": [],
            "merge_packet": None,
            "support": {"runtime_required": False, "states": {}, "missing": [], "drift": []},
        }
    state = profile_state(repo_root, codex_home)
    if state["status"] in {"current", "local_overlay"}:
        return {
            "status": state["status"],
            "mismatches": [],
            "merge_packet": None,
            "receipt": state["receipt"],
            "support": state["support"],
        }
    if state["status"] in {"source_update", "merge_required"}:
        return {
            "status": state["status"],
            "mismatches": [],
            "merge_packet": latest_merge_packet(codex_home),
            "receipt": state["receipt"],
            "support": state["support"],
        }
    return {
        "status": "missing",
        "mismatches": state["missing"],
        "merge_packet": None,
        "receipt": state["receipt"],
        "support": state["support"],
    }


def verify(
    repo_root: Path,
    plugins_dir: Path,
    codex_home: Path,
    profile: bool,
    codex_bin: str,
) -> dict[str, Any]:
    plugin_path = plugins_dir / PLUGIN_NAME
    missing: list[str] = []
    for rel in PLUGIN_REQUIRED_FILES:
        if not (plugin_path / rel).exists():
            missing.append(str(plugin_path / rel))

    marketplace_path = plugin_path / MARKETPLACE_MANIFEST
    marketplace = load_json(marketplace_path)
    marketplace_plugins = marketplace.get("plugins")
    marketplace_plugin = (
        marketplace_plugins[0]
        if isinstance(marketplace_plugins, list) and len(marketplace_plugins) == 1
        else {}
    )
    marketplace_manifest_ok = (
        marketplace.get("name") == MARKETPLACE_NAME
        and marketplace_plugin.get("name") == PLUGIN_NAME
        and marketplace_plugin.get("source") == {"source": "local", "path": "."}
        and marketplace_plugin.get("policy")
        == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
    )
    source_plugin_mismatches = tree_mismatches(
        repo_root,
        plugin_path,
        "plugin",
        COPY_IGNORE_NAMES,
    )
    cache_path = plugin_cache_path(codex_home, plugin_path)
    cache_mismatches = tree_mismatches(plugin_path, cache_path, "cache")

    try:
        marketplace_readback = marketplace_readback_status(
            run_codex_json(codex_bin, "plugin", "marketplace", "list", "--json"),
            MARKETPLACE_NAME,
            plugin_path,
        )
        plugin_readback = read_plugin_status(codex_bin, plugin_path)
    except (RuntimeError, ValueError) as exc:
        marketplace_readback = {"ok": False, "error": str(exc)}
        plugin_readback = {"ok": False, "error": str(exc)}

    profile_result = verify_profile(repo_root, codex_home, profile)
    profile_mismatches = list(profile_result["mismatches"])

    ok = (
        not missing
        and not source_plugin_mismatches
        and not cache_mismatches
        and marketplace_manifest_ok
        and marketplace_readback["ok"]
        and plugin_readback["ok"]
        and not profile_mismatches
        and profile_result["status"] in {"current", "local_overlay", "skipped"}
    )
    return {
        "ok": ok,
        "plugin_path": str(plugin_path),
        "cache_path": str(cache_path),
        "required_files": list(PLUGIN_REQUIRED_FILES),
        "marketplace_path": str(marketplace_path),
        "marketplace_manifest_ok": marketplace_manifest_ok,
        "marketplace_readback": marketplace_readback,
        "plugin_readback": plugin_readback,
        "missing": missing,
        "source_plugin_mismatches": source_plugin_mismatches,
        "cache_mismatches": cache_mismatches,
        "profile_status": profile_result["status"],
        "profile_mismatches": profile_mismatches,
        "profile_merge_packet": profile_result["merge_packet"],
        "profile_receipt": profile_result.get("receipt"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install OPL Flow as a local Codex plugin")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--plugins-dir", default=str(Path.home() / "plugins"))
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "codex")
    parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Install the plugin without syncing the AGENTS.md runtime profile or optional support surfaces.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="Only verify an existing install.")
    mode.add_argument(
        "--apply-merge-packet",
        help="Apply a reviewed semantic-merge packet output and record its profile receipt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    plugins_dir = Path(args.plugins_dir).expanduser().resolve()
    codex_home = Path(args.codex_home).expanduser().resolve()
    codex_bin = str(Path(args.codex_bin).expanduser()) if "/" in args.codex_bin else args.codex_bin
    profile = not args.no_profile

    if args.apply_merge_packet:
        if args.no_profile:
            raise ValueError("--apply-merge-packet cannot be combined with --no-profile")
        result = apply_merge_packet(repo_root, codex_home, Path(args.apply_merge_packet))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.verify_only:
        result = verify(repo_root, plugins_dir, codex_home, profile, codex_bin)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    result = install(repo_root, plugins_dir, codex_home, profile, codex_bin)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
