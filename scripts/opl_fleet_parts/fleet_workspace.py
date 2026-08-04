"""Declared workspace validation, bootstrap, currentness, and claim admission."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import re
import shutil
import tempfile

from . import fleet_common
from .fleet_common import FleetError, atomic_json, read_json, run, sha256_file, utc_now
from .fleet_reconcile import git_value, github_head, github_repository_from_remote, reconcile_repository


PROFILE_SCHEMA = "opl_fleet_workspace_profiles.v1"
PROFILE_PATH = "workspace-profiles.json"
SAFE_EXISTING_STATES = {"CURRENT", "BEHIND"}
CLAIM_READY_STATES = {"CURRENT"}
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
)
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
REMOTE_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$"
)


def canonical_json_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _relative_path(value: Any, label: str, *, single_component: bool = False) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
        or (single_component and len(path.parts) != 1)
    ):
        raise FleetError(f"workspace {label} is invalid")
    return text


def validate_workspace_profiles(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"$schema", "schema", "profiles"}
        or payload.get("$schema")
        != "https://one-person-lab.dev/schemas/opl-flow/fleet-workspace-profile.v1.json"
        or payload.get("schema") != PROFILE_SCHEMA
        or not isinstance(payload.get("profiles"), dict)
        or not payload["profiles"]
    ):
        raise FleetError("workspace profile catalog is invalid")

    seen_nodes: set[str] = set()
    for profile_id, profile in payload["profiles"].items():
        if not PROFILE_ID_PATTERN.fullmatch(str(profile_id)) or not isinstance(profile, dict):
            raise FleetError(f"workspace profile identity is invalid: {profile_id!r}")
        if set(profile) != {
            "node_ids",
            "workspace_root",
            "environment_contract",
            "repositories",
            "automation_placements",
        }:
            raise FleetError(f"workspace profile fields are not allowed: {profile_id}")
        node_ids = profile["node_ids"]
        if (
            not isinstance(node_ids, list)
            or not node_ids
            or node_ids != sorted(set(node_ids))
            or any(not fleet_common.NODE_ID_PATTERN.fullmatch(str(item)) for item in node_ids)
            or seen_nodes.intersection(node_ids)
        ):
            raise FleetError(f"workspace profile nodes are invalid: {profile_id}")
        seen_nodes.update(node_ids)
        workspace_root = str(profile["workspace_root"])
        if not workspace_root.startswith("~/") or ".." in PurePosixPath(workspace_root[2:]).parts:
            raise FleetError(f"workspace root is invalid: {profile_id}")
        _relative_path(profile["environment_contract"], "environment contract")
        repositories = profile["repositories"]
        if not isinstance(repositories, list) or not repositories:
            raise FleetError(f"workspace repositories are invalid: {profile_id}")
        seen_repositories: set[str] = set()
        seen_directories: set[str] = set()
        for repository in repositories:
            if not isinstance(repository, dict) or set(repository) != {
                "repository",
                "directory",
                "branch",
                "remote",
                "role",
                "required",
            }:
                raise FleetError(f"workspace repository fields are invalid: {profile_id}")
            slug = str(repository["repository"])
            directory = _relative_path(
                repository["directory"], "repository directory", single_component=True
            )
            branch = str(repository["branch"])
            remote = str(repository["remote"])
            if (
                not REPOSITORY_PATTERN.fullmatch(slug)
                or not BRANCH_PATTERN.fullmatch(branch)
                or branch.startswith("/")
                or ".." in PurePosixPath(branch).parts
                or not REMOTE_PATTERN.fullmatch(remote)
                or github_repository_from_remote(remote) != slug
                or repository["role"] not in {"authority", "implementation_dependency"}
                or not isinstance(repository["required"], bool)
                or slug in seen_repositories
                or directory in seen_directories
            ):
                raise FleetError(f"workspace repository is invalid: {profile_id}/{slug}")
            seen_repositories.add(slug)
            seen_directories.add(directory)
        placements = profile["automation_placements"]
        if not isinstance(placements, list):
            raise FleetError(f"workspace automation placements are invalid: {profile_id}")
        seen_automations: set[str] = set()
        seen_singletons: set[str] = set()
        for placement in placements:
            if not isinstance(placement, dict) or set(placement) != {
                "id",
                "singleton_key",
                "role",
                "migration_order",
                "desired_state",
            }:
                raise FleetError(f"workspace automation placement fields are invalid: {profile_id}")
            automation_id = str(placement["id"])
            singleton = str(placement["singleton_key"])
            if (
                not PROFILE_ID_PATTERN.fullmatch(automation_id)
                or not re.fullmatch(r"[a-z0-9][a-z0-9:.-]{0,127}", singleton)
                or placement["role"] not in {"ledger_supervisor", "github_patrol"}
                or not isinstance(placement["migration_order"], int)
                or placement["migration_order"] < 1
                or placement["desired_state"] not in {"disabled", "shadow", "active"}
                or automation_id in seen_automations
                or singleton in seen_singletons
            ):
                raise FleetError(f"workspace automation placement is invalid: {profile_id}")
            seen_automations.add(automation_id)
            seen_singletons.add(singleton)
    return payload


def workspace_profile_catalog(*, control_root: Path | None = None) -> dict[str, Any]:
    root = (control_root or fleet_common.CONTROL_ROOT).resolve()
    path = root / PROFILE_PATH
    if not path.is_file():
        raise FleetError(f"workspace profile catalog is missing: {PROFILE_PATH}")
    return validate_workspace_profiles(read_json(path))


def workspace_profile(profile_id: str) -> dict[str, Any]:
    if not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise FleetError("workspace profile id is invalid")
    profile = workspace_profile_catalog()["profiles"].get(profile_id)
    if not isinstance(profile, dict):
        raise FleetError(f"unknown workspace profile: {profile_id}")
    return profile


def profile_workspace_root(profile: dict[str, Any]) -> Path:
    return Path(str(profile["workspace_root"])).expanduser().resolve()


def profile_environment_contract(profile: dict[str, Any]) -> dict[str, Any]:
    relative = _relative_path(profile["environment_contract"], "environment contract")
    root = fleet_common.CONTROL_ROOT.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FleetError("workspace environment contract escapes the Instance") from exc
    if not path.is_file() or path.is_symlink():
        raise FleetError("workspace environment contract is missing or unsafe")
    payload = read_json(path)
    requirements = payload.get("runtime_requirements")
    commands = requirements.get("commands") if isinstance(requirements, dict) else None
    if (
        set(requirements or {}) != {"commands"}
        or not isinstance(commands, list)
        or not commands
        or commands != sorted(set(commands))
        or any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(command))
            is None
            for command in commands
        )
    ):
        raise FleetError("workspace environment runtime requirements are invalid")
    return payload


def profile_environment_fingerprint(profile: dict[str, Any]) -> str:
    relative = _relative_path(profile["environment_contract"], "environment contract")
    path = (fleet_common.CONTROL_ROOT.resolve() / relative).resolve()
    profile_environment_contract(profile)
    return sha256_file(path)


def _worktree_count(repository: Path) -> int:
    result = git_value(repository, ["worktree", "list", "--porcelain"])
    return sum(line.startswith("worktree ") for line in result.stdout.splitlines())


def _repository_entry(
    spec: dict[str, Any],
    *,
    root: Path,
    fetch: bool,
    fresh_github: bool,
) -> dict[str, Any]:
    path = root / str(spec["directory"])
    base = {
        "repository": spec["repository"],
        "directory": spec["directory"],
        "branch": spec["branch"],
        "required": spec["required"],
        "local_commit": None,
        "remote_commit": None,
        "github_commit": None,
        "worktree_count": 0,
    }
    if path.is_symlink():
        return {**base, "state": "PATH_UNSAFE"}
    if not path.exists():
        if fresh_github:
            try:
                base["github_commit"] = github_head(spec["repository"], spec["branch"])
            except Exception:
                return {**base, "state": "GITHUB_UNAVAILABLE"}
        return {**base, "state": "MISSING"}
    if not path.is_dir() or not (path / ".git").exists():
        return {**base, "state": "PATH_CONFLICT"}
    remote = git_value(path, ["remote", "get-url", "origin"], check=False)
    if remote.returncode or remote.stdout.strip() != spec["remote"]:
        return {**base, "state": "REMOTE_MISMATCH"}
    result = reconcile_repository(path, fetch=fetch, apply=False, expected_owner=None)
    if result is None or result["repository"] != spec["repository"]:
        return {**base, "state": "REMOTE_MISMATCH"}
    entry = {
        **base,
        **{
            key: result.get(key)
            for key in (
                "state",
                "dirty",
                "ahead",
                "behind",
                "local_commit",
                "remote_commit",
            )
        },
    }
    if result.get("branch") != spec["branch"] or result.get("default_branch") != spec["branch"]:
        entry["state"] = "BRANCH_MISMATCH"
    entry["worktree_count"] = _worktree_count(path)
    if entry["worktree_count"] > 1:
        entry["state"] = "ACTIVE_WORKTREE"
    if fresh_github:
        try:
            entry["github_commit"] = github_head(spec["repository"], spec["branch"])
        except Exception:
            if entry["state"] in SAFE_EXISTING_STATES:
                entry["state"] = "GITHUB_UNAVAILABLE"
        else:
            if (
                entry["state"] in SAFE_EXISTING_STATES
                and entry["remote_commit"] != entry["github_commit"]
            ):
                entry["state"] = "GITHUB_DRIFT"
    return entry


def _repository_fingerprint(entries: list[dict[str, Any]]) -> str:
    return canonical_json_digest(
        [
            {
                "repository": entry["repository"],
                "branch": entry["branch"],
                "commit": entry["local_commit"],
            }
            for entry in entries
        ]
    )


def workspace_readback(
    profile_id: str,
    *,
    fetch: bool,
    fresh_github: bool,
) -> dict[str, Any]:
    profile = workspace_profile(profile_id)
    root = profile_workspace_root(profile)
    entries = [
        _repository_entry(
            spec,
            root=root,
            fetch=fetch,
            fresh_github=fresh_github,
        )
        for spec in profile["repositories"]
    ]
    attention = [
        entry
        for entry in entries
        if entry["required"] and entry["state"] not in CLAIM_READY_STATES
    ]
    environment = profile_environment_contract(profile)
    commands = {
        command: shutil.which(command) is not None
        for command in environment["runtime_requirements"]["commands"]
    }
    missing_commands = sorted(
        command for command, available in commands.items() if not available
    )
    profile_fingerprint = canonical_json_digest(profile)
    environment_fingerprint = profile_environment_fingerprint(profile)
    return {
        "schema": "opl_fleet_workspace_readback.v1",
        "profile_id": profile_id,
        "node_ids": profile["node_ids"],
        "observed_at": utc_now().isoformat().replace("+00:00", "Z"),
        "state": "CURRENT" if not attention and not missing_commands else "ATTENTION",
        "profile_fingerprint": profile_fingerprint,
        "environment_fingerprint": environment_fingerprint,
        "repository_fingerprint": _repository_fingerprint(entries),
        "fresh_fetch": fetch,
        "fresh_github": fresh_github,
        "attention_count": len(attention) + len(missing_commands),
        "required_commands": commands,
        "missing_commands": missing_commands,
        "repositories": entries,
        "automation_placements": profile["automation_placements"],
    }


def _clone_missing(
    profile: dict[str, Any],
    entries: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    missing = {
        entry["repository"]: entry for entry in entries if entry["state"] == "MISSING"
    }
    if not missing:
        return
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".opl-workspace-stage-", dir=root.parent) as temp:
        stage_root = Path(temp)
        staged: list[tuple[Path, Path]] = []
        for spec in profile["repositories"]:
            if spec["repository"] not in missing:
                continue
            stage = stage_root / str(spec["directory"])
            completed = run(
                [
                    "git",
                    "clone",
                    "--origin",
                    "origin",
                    "--branch",
                    str(spec["branch"]),
                    "--single-branch",
                    str(spec["remote"]),
                    str(stage),
                ],
                check=False,
            )
            if completed.returncode:
                raise FleetError(f"workspace clone failed: {spec['repository']}")
            expected = missing[spec["repository"]].get("github_commit")
            actual = git_value(stage, ["rev-parse", "HEAD"]).stdout.strip()
            if expected and actual != expected:
                raise FleetError(f"workspace clone currentness changed: {spec['repository']}")
            staged.append((stage, root / str(spec["directory"])))
        root.mkdir(parents=True, exist_ok=True)
        if any(target.exists() or target.is_symlink() for _, target in staged):
            raise FleetError("workspace target appeared during bootstrap")
        for stage, target in staged:
            stage.replace(target)


def sync_workspace(profile_id: str) -> dict[str, Any]:
    profile = workspace_profile(profile_id)
    root = profile_workspace_root(profile)
    before = workspace_readback(profile_id, fetch=True, fresh_github=True)
    blockers = [
        entry
        for entry in before["repositories"]
        if entry["required"]
        and entry["state"] not in SAFE_EXISTING_STATES | {"MISSING"}
    ]
    if blockers:
        return {**before, "action": "sync", "applied": False}

    _clone_missing(profile, before["repositories"], root=root)
    before_by_slug = {entry["repository"]: entry for entry in before["repositories"]}
    for spec in profile["repositories"]:
        entry = before_by_slug[spec["repository"]]
        if entry["state"] != "BEHIND":
            continue
        repository = root / str(spec["directory"])
        current = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
        if current != entry["local_commit"]:
            raise FleetError(f"workspace checkout changed during sync: {spec['repository']}")
        expected = str(entry["github_commit"] or entry["remote_commit"])
        merged = git_value(repository, ["merge", "--ff-only", expected], check=False)
        if merged.returncode:
            raise FleetError(f"workspace fast-forward failed: {spec['repository']}")

    after = workspace_readback(profile_id, fetch=False, fresh_github=True)
    result = {**after, "action": "sync", "applied": True, "before": before}
    atomic_json(fleet_common.STATE_ROOT / "workspaces" / f"{profile_id}.json", result)
    return result


def workspace_command(profile_id: str, action: str) -> dict[str, Any]:
    if action == "validate":
        profile = workspace_profile(profile_id)
        return {
            "schema": "opl_fleet_workspace_validation.v1",
            "profile_id": profile_id,
            "valid": True,
            "profile_fingerprint": canonical_json_digest(profile),
        }
    if action == "plan":
        return workspace_readback(profile_id, fetch=False, fresh_github=False)
    if action == "status":
        return workspace_readback(profile_id, fetch=True, fresh_github=False)
    if action in {"bootstrap", "sync"}:
        return sync_workspace(profile_id)
    if action == "claim-check":
        result = workspace_readback(profile_id, fetch=True, fresh_github=True)
        return {
            **result,
            "claim_ready": result["state"] == "CURRENT",
        }
    raise FleetError(f"unknown workspace action: {action}")
