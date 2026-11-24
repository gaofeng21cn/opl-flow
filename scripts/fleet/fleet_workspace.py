"""Declared workspace validation, bootstrap, currentness, and claim admission."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
import hashlib
import json
import re
import shutil
import tempfile

from . import fleet_common
import opl_ledger
from .fleet_common import FleetError, atomic_json, read_json, run, sha256_file, utc_now
from .fleet_control import git_value, github_head, github_repository_from_remote
from .fleet_reconcile import reconcile_repository


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


def _relative_path(value: Any, label: str) -> str:
    text = str(value or "")
    parts = text.split("/")
    if (
        not text
        or text.startswith("/")
        or "\\" in text
        or any(part in {"", ".", "..", ".git"} for part in parts)
        or any(re.fullmatch(r"[A-Za-z0-9_.-]+", part) is None for part in parts)
    ):
        raise FleetError(f"workspace {label} is invalid")
    return text


class _WorkspaceRepoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: Annotated[StrictStr, Field(pattern=REPOSITORY_PATTERN.pattern)]
    directory: Any
    branch: Annotated[StrictStr, Field(pattern=BRANCH_PATTERN.pattern)]
    remote: Annotated[StrictStr, Field(pattern=REMOTE_PATTERN.pattern)]
    role: Literal["authority", "implementation_dependency"]
    required: StrictBool

    @field_validator("directory")
    @classmethod
    def _valid_dir(cls, value: Any) -> str:
        return _relative_path(value, "repository directory")

    @model_validator(mode="after")
    def _valid_repo(self) -> "_WorkspaceRepoModel":
        if self.branch.startswith("/") or ".." in PurePosixPath(self.branch).parts or github_repository_from_remote(self.remote) != self.repository:
            raise ValueError("workspace repository is invalid")
        return self


class _WorkspaceLedgerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_directory: Any
    role: Literal["maintainer"]

    @field_validator("repository_directory")
    @classmethod
    def _valid_dir(cls, value: Any) -> str:
        return _relative_path(value, "ledger repository directory")


class _AutomationPlacementModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[StrictStr, Field(pattern=PROFILE_ID_PATTERN.pattern)]
    singleton_key: Annotated[StrictStr, Field(pattern=r"^[a-z0-9][a-z0-9:.-]{0,127}$")]
    role: Literal["ledger_supervisor", "github_patrol"]
    migration_order: Annotated[StrictInt, Field(ge=1)]
    desired_state: Literal["disabled", "shadow", "active"]


class _WorkspaceProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_ids: Annotated[list[Annotated[StrictStr, Field(pattern=fleet_common.NODE_ID_PATTERN.pattern)]], Field(min_length=1)]
    workspace_root: StrictStr
    environment_contract: Any
    repositories: Annotated[list[_WorkspaceRepoModel], Field(min_length=1)]
    ledger: _WorkspaceLedgerModel
    automation_placements: list[_AutomationPlacementModel]

    @field_validator("node_ids")
    @classmethod
    def _sorted_nodes(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("workspace profile nodes are invalid")
        return value

    @field_validator("workspace_root")
    @classmethod
    def _home_root(cls, value: str) -> str:
        if not value.startswith("~/") or ".." in PurePosixPath(value[2:]).parts:
            raise ValueError("workspace root is invalid")
        return value

    @field_validator("environment_contract")
    @classmethod
    def _valid_env(cls, value: Any) -> str:
        return _relative_path(value, "environment contract")

    @model_validator(mode="after")
    def _check_uniqueness(self) -> "_WorkspaceProfileModel":
        seen_repos: set[str] = set()
        seen_dirs: set[str] = set()
        for repo in self.repositories:
            if repo.repository in seen_repos or repo.directory in seen_dirs:
                raise ValueError(f"workspace repository is invalid: {repo.repository}")
            if any(
                PurePosixPath(repo.directory).is_relative_to(PurePosixPath(other))
                or PurePosixPath(other).is_relative_to(PurePosixPath(repo.directory))
                for other in seen_dirs
            ):
                raise ValueError("workspace repository directories overlap")
            seen_repos.add(repo.repository)
            seen_dirs.add(repo.directory)
        if self.ledger.repository_directory not in seen_dirs:
            raise ValueError("workspace ledger is invalid")
        if (
            len({p.id for p in self.automation_placements}) != len(self.automation_placements)
            or len({p.singleton_key for p in self.automation_placements}) != len(self.automation_placements)
        ):
            raise ValueError("workspace automation placement is invalid")
        return self


def validate_workspace_profiles(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"$schema", "schema", "profiles"}
        or payload.get("$schema") != "https://one-person-lab.dev/schemas/opl-flow/fleet-workspace-profile.v1.json"
        or payload.get("schema") != PROFILE_SCHEMA
        or not isinstance(payload.get("profiles"), dict)
        or not payload["profiles"]
    ):
        raise FleetError("workspace profile catalog is invalid")
    seen_nodes: set[str] = set()
    for profile_id, profile in payload["profiles"].items():
        if not PROFILE_ID_PATTERN.fullmatch(str(profile_id)) or not isinstance(profile, dict):
            raise FleetError(f"workspace profile identity is invalid: {profile_id!r}")
        raw_nodes = profile.get("node_ids")
        if (
            not isinstance(raw_nodes, list)
            or not raw_nodes
            or any(not isinstance(item, str) for item in raw_nodes)
            or seen_nodes.intersection(raw_nodes)
        ):
            raise FleetError(f"workspace profile nodes are invalid: {profile_id}")
        parsed = fleet_common.runtime.validate_model(_WorkspaceProfileModel, profile, error_cls=FleetError)
        assert isinstance(parsed, _WorkspaceProfileModel)
        seen_nodes.update(parsed.node_ids)
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


def _repository_path(root: Path, directory: str) -> Path:
    """Reject redirected parents as well as a redirected checkout itself."""
    relative = _relative_path(directory, "repository directory")
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise FleetError("workspace repository path contains a symlink")
    return path


def _repository_entry(
    spec: dict[str, Any],
    *,
    root: Path,
    fetch: bool,
    fresh_github: bool,
) -> dict[str, Any]:
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
    try:
        path = _repository_path(root, str(spec["directory"]))
    except FleetError:
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
    if remote.returncode or github_repository_from_remote(remote.stdout.strip()) != spec["repository"]:
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


def ledger_readback(
    profile: dict[str, Any], *, root: Path, fresh_pull: bool,
) -> dict[str, Any]:
    ledger = profile["ledger"]
    directory = str(ledger["repository_directory"])
    try:
        result = opl_ledger.workspace_readback(
            root / directory, str(ledger["role"]), fresh_pull=fresh_pull,
        )
    except opl_ledger.LedgerError as exc:
        raise FleetError(str(exc)) from exc
    return {"repository_directory": directory, **result}


def sync_ledger(profile: dict[str, Any], *, root: Path) -> None:
    ledger = profile["ledger"]
    try:
        opl_ledger.sync_workspace_ledger(
            root / str(ledger["repository_directory"]), str(ledger["role"]),
        )
    except opl_ledger.LedgerError as exc:
        raise FleetError(str(exc)) from exc


def workspace_readback(
    profile_id: str,
    *,
    fetch: bool,
    fresh_github: bool,
    fresh_ledger: bool = False,
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
    ledger = ledger_readback(profile, root=root, fresh_pull=fresh_ledger)
    profile_fingerprint = canonical_json_digest(profile)
    environment_fingerprint = profile_environment_fingerprint(profile)
    return {
        "schema": "opl_fleet_workspace_readback.v1",
        "profile_id": profile_id,
        "node_ids": profile["node_ids"],
        "observed_at": utc_now().isoformat().replace("+00:00", "Z"),
        "state": (
            "CURRENT"
            if not attention and not missing_commands and ledger["state"] == "CURRENT"
            else "ATTENTION"
        ),
        "profile_fingerprint": profile_fingerprint,
        "environment_fingerprint": environment_fingerprint,
        "repository_fingerprint": _repository_fingerprint(entries),
        "fresh_fetch": fetch,
        "fresh_github": fresh_github,
        "attention_count": (
            len(attention)
            + len(missing_commands)
            + (0 if ledger["state"] == "CURRENT" else 1)
        ),
        "required_commands": commands,
        "missing_commands": missing_commands,
        "repositories": entries,
        "ledger": ledger,
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
            _repository_path(root, str(spec["directory"]))
            stage = stage_root / str(spec["directory"])
            stage.parent.mkdir(parents=True, exist_ok=True)
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
            staged.append((stage, _repository_path(root, str(spec["directory"]))))
        root.mkdir(parents=True, exist_ok=True)
        if any(target.exists() or target.is_symlink() for _, target in staged):
            raise FleetError("workspace target appeared during bootstrap")
        for stage, target in staged:
            _repository_path(root, target.relative_to(root).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
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
        repository = _repository_path(root, str(spec["directory"]))
        current = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
        if current != entry["local_commit"]:
            raise FleetError(f"workspace checkout changed during sync: {spec['repository']}")
        expected = str(entry["github_commit"] or entry["remote_commit"])
        merged = git_value(repository, ["merge", "--ff-only", expected], check=False)
        if merged.returncode:
            raise FleetError(f"workspace fast-forward failed: {spec['repository']}")

    sync_ledger(profile, root=root)

    after = workspace_readback(
        profile_id,
        fetch=False,
        fresh_github=True,
        fresh_ledger=True,
    )
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
        result = workspace_readback(
            profile_id,
            fetch=True,
            fresh_github=True,
            fresh_ledger=True,
        )
        return {
            **result,
            "claim_ready": result["state"] == "CURRENT",
        }
    raise FleetError(f"unknown workspace action: {action}")
