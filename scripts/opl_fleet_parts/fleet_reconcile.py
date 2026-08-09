"""Fleet reconciliation: manifests, node registry, pets, git sync, runner installation, receipts, asset catalogs, schedules, and join."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import base64
import datetime as dt
import json
import os
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 degrades safely.
    tomllib = None
from fleet_inventory import collect_inventory, validate_inventory
from . import fleet_common
from .fleet_common import AVAILABILITY_POLICIES, CONFIG_PATH, FLOW_ROOT, FleetError, LEASE_WORKLOAD_CLASSES, NODE_ID_PATTERN, PET_FILES, RECEIPT_FIELDS, REPORT_FIELDS, REPOSITORY_FETCH_TIMEOUT_SECONDS, ROLE_PATTERN, RUNNER_PATH, SKILL_REFERENCE_SCHEMA, STATE_ROOT, _INSTANCE_OWNER, atomic_json, effective_codex_home, node_identity, normalize_node_id, read_json, run, sha256_file, utc_now

def manifest() -> dict[str, Any]:
    payload = read_json(fleet_common.CONTROL_ROOT / "fleet.json")
    if payload.get("schema") != "codex_fleet_control.v1":
        raise FleetError("unsupported fleet manifest")
    runner = payload.get("runner")
    schedule = payload.get("schedule")
    if not isinstance(runner, dict) or not isinstance(runner.get("install_command"), list):
        raise FleetError("fleet runner definition is incomplete")
    repository_owner = payload.get("repository_owner")
    if not isinstance(repository_owner, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,100}", repository_owner
    ):
        raise FleetError("fleet repository owner is invalid")
    if not isinstance(schedule, dict) or not isinstance(
        schedule.get("service_id"), str
    ):
        raise FleetError("fleet schedule is incomplete")
    return payload

def managed_repository_owner() -> str:
    return str(manifest()["repository_owner"])

def node_registry(*, control_root: Path | None = None) -> dict[str, Any]:
    root = control_root or fleet_common.CONTROL_ROOT
    payload = read_json(root / "nodes.json")
    if set(payload) != {
        "schema",
        "nodes",
        "specialized_software",
        "runner_bindings",
        "runner_roles",
        "runner_role_workloads",
        "desired_unregistered",
    }:
        raise FleetError("node registry fields are not allowed")
    if payload.get("schema") != "codex_fleet_nodes.v1":
        raise FleetError("unsupported node registry")
    nodes = payload.get("nodes")
    definitions = payload.get("specialized_software")
    runner_bindings = payload.get("runner_bindings")
    runner_roles = payload.get("runner_roles")
    runner_role_workloads = payload.get("runner_role_workloads")
    desired_unregistered = payload.get("desired_unregistered")
    if (
        not isinstance(nodes, dict)
        or not isinstance(definitions, list)
        or not isinstance(runner_bindings, dict)
        or not isinstance(runner_roles, dict)
        or not isinstance(runner_role_workloads, dict)
        or not isinstance(desired_unregistered, list)
    ):
        raise FleetError("node registry is incomplete")
    for node_id, policy in nodes.items():
        if normalize_node_id(str(node_id)) != node_id or not isinstance(policy, dict):
            raise FleetError(f"invalid node registry entry: {node_id!r}")
        if set(policy) != {
            "approved",
            "display_name",
            "availability_policy",
            "labels",
            "notes",
            "scheduling",
        }:
            raise FleetError(f"node policy fields are not allowed: {node_id}")
        if not isinstance(policy["approved"], bool):
            raise FleetError(f"node approval is invalid: {node_id}")
        if not isinstance(policy["display_name"], str) or len(policy["display_name"]) > 80:
            raise FleetError(f"node display name is invalid: {node_id}")
        if policy["availability_policy"] not in AVAILABILITY_POLICIES:
            raise FleetError(f"node availability policy is invalid: {node_id}")
        labels = policy["labels"]
        notes = policy["notes"]
        if (
            not isinstance(labels, list)
            or any(not re.fullmatch(r"[a-z0-9-]{1,40}", str(item)) for item in labels)
            or not isinstance(notes, list)
        ):
            raise FleetError(f"node labels or notes are invalid: {node_id}")
        for note in notes:
            if (
                not isinstance(note, dict)
                or set(note) != {"category", "summary"}
                or not re.fullmatch(r"[a-z0-9-]{1,40}", str(note["category"]))
                or not isinstance(note["summary"], str)
                or len(note["summary"]) > 300
            ):
                raise FleetError(f"node note is invalid: {node_id}")
        scheduling = policy["scheduling"]
        if (
            not isinstance(scheduling, dict)
            or set(scheduling)
            != {
                "requires_ac",
                "min_free_gb",
                "occupancy_required",
                "idle_threshold_seconds",
                "preferred_for",
                "work_volume_required",
            }
            or not isinstance(scheduling["requires_ac"], bool)
            or not isinstance(scheduling["min_free_gb"], int)
            or not 0 <= scheduling["min_free_gb"] <= 10_000
            or not isinstance(scheduling["occupancy_required"], bool)
            or not isinstance(scheduling["work_volume_required"], bool)
            or not isinstance(scheduling["idle_threshold_seconds"], int)
            or not 60 <= scheduling["idle_threshold_seconds"] <= 86_400
            or not isinstance(scheduling["preferred_for"], list)
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in scheduling["preferred_for"]
            )
        ):
            raise FleetError(f"node scheduling policy is invalid: {node_id}")
    for definition in definitions:
        if (
            not isinstance(definition, dict)
            or set(definition)
            != {"id", "purpose", "windows_display_name_patterns"}
            or not re.fullmatch(r"[a-z0-9-]{1,60}", str(definition["id"]))
            or not isinstance(definition["purpose"], str)
            or len(definition["purpose"]) > 160
            or not isinstance(definition["windows_display_name_patterns"], list)
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 80
                for item in definition["windows_display_name_patterns"]
            )
        ):
            raise FleetError("specialized software definition is invalid")
    for role, node_ids in runner_roles.items():
        if (
            not ROLE_PATTERN.fullmatch(str(role))
            or not isinstance(node_ids, list)
            or not node_ids
            or node_ids != sorted(set(node_ids))
            or any(node_id not in nodes for node_id in node_ids)
        ):
            raise FleetError(f"runner role is invalid: {role}")
    for role, workload_classes in runner_role_workloads.items():
        if (
            role not in runner_roles
            or not isinstance(workload_classes, list)
            or not workload_classes
            or workload_classes != sorted(set(workload_classes))
            or any(item not in LEASE_WORKLOAD_CLASSES for item in workload_classes)
        ):
            raise FleetError(f"runner role workload policy is invalid: {role}")
    for role, binding in runner_bindings.items():
        if (
            role not in runner_roles
            or not isinstance(binding, dict)
            or set(binding)
            != {
                "launch_mode",
                "min_memory_gb",
                "node_id",
                "repository",
                "required_features",
                "runner_name",
            }
            or binding["launch_mode"] not in {
                "ssh-session",
                "launchagent",
                "windows-session-task",
            }
            or binding["node_id"] not in runner_roles[role]
            or not re.fullmatch(
                r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
                str(binding["repository"]),
            )
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}",
                str(binding["runner_name"]),
            )
            or not isinstance(binding["required_features"], list)
            or binding["required_features"]
            != sorted(set(binding["required_features"]))
            or any(
                not re.fullmatch(r"[a-z0-9-]{1,40}", str(item))
                for item in binding["required_features"]
            )
            or not isinstance(binding["min_memory_gb"], int)
            or not 0 <= binding["min_memory_gb"] <= 10_000
            or (
                binding["launch_mode"] == "windows-session-task"
                and "windows" not in nodes[binding["node_id"]]["labels"]
            )
        ):
            raise FleetError(f"runner binding is invalid: {role}")
    if (
        desired_unregistered != sorted(set(desired_unregistered))
        or any(node_id not in nodes for node_id in desired_unregistered)
        or set(desired_unregistered).intersection(
            node_id
            for node_ids in runner_roles.values()
            for node_id in node_ids
        )
    ):
        raise FleetError("desired-unregistered nodes are invalid")
    return payload

def pet_manifest(
    spec: dict[str, Any],
    *,
    control_root: Path | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    root = (control_root or fleet_common.CONTROL_ROOT).resolve()
    assets = spec.get("user_assets")
    relative = assets.get("pets_manifest") if isinstance(assets, dict) else None
    if not isinstance(relative, str) or not relative:
        return root, []
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FleetError("pet manifest escapes the control checkout") from exc
    payload = read_json(path)
    if payload.get("schema") != "codex_fleet_pet_manifest.v1":
        raise FleetError("unsupported pet manifest")
    pets = payload.get("pets")
    if not isinstance(pets, list):
        raise FleetError("pet manifest entries are invalid")
    seen: set[str] = set()
    for entry in pets:
        if not isinstance(entry, dict):
            raise FleetError("pet manifest entry must be an object")
        pet_id = str(entry.get("id", ""))
        if not NODE_ID_PATTERN.fullmatch(pet_id) or pet_id in seen:
            raise FleetError(f"invalid or duplicate pet id: {pet_id!r}")
        seen.add(pet_id)
        files = entry.get("files")
        if not isinstance(files, dict) or set(files) != PET_FILES:
            raise FleetError(f"pet files are incomplete: {pet_id}")
        for name, digest in files.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
                raise FleetError(f"invalid pet digest: {pet_id}/{name}")
        source = path.parent / pet_id
        for name, digest in files.items():
            source_file = source / name
            if not source_file.is_file() or source_file.is_symlink():
                raise FleetError(f"pet source is missing or unsafe: {pet_id}/{name}")
            if sha256_file(source_file) != digest:
                raise FleetError(f"pet source digest changed: {pet_id}/{name}")
        metadata = read_json(source / "pet.json")
        if (
            metadata.get("id") != pet_id
            or metadata.get("spriteVersionNumber") != 2
            or metadata.get("spritesheetPath") != "spritesheet.webp"
        ):
            raise FleetError(f"pet metadata is not Codex v2: {pet_id}")
    return path.parent, pets

def pet_files_match(path: Path, expected: dict[str, str]) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    return all(
        (path / name).is_file()
        and not (path / name).is_symlink()
        and sha256_file(path / name) == digest
        for name, digest in expected.items()
    )

def reconcile_pets(
    spec: dict[str, Any],
    *,
    codex_home: Path | None = None,
    control_root: Path | None = None,
    state_root: Path | None = None,
) -> list[str]:
    source_root, pets = pet_manifest(spec, control_root=control_root)
    if not pets:
        return []
    destination_root = (codex_home or effective_codex_home()) / "pets"
    backup_root = (state_root or STATE_ROOT) / "backups/pets"
    destination_root.mkdir(parents=True, exist_ok=True)
    updated: list[str] = []
    for entry in pets:
        pet_id = str(entry["id"])
        expected = {str(key): str(value) for key, value in entry["files"].items()}
        target = destination_root / pet_id
        if pet_files_match(target, expected):
            continue
        if target.is_symlink():
            raise FleetError(f"refusing to replace symlinked pet: {pet_id}")
        stage = Path(tempfile.mkdtemp(prefix=f".{pet_id}.stage-", dir=destination_root))
        previous = destination_root / f".{pet_id}.previous-{os.getpid()}"
        if previous.exists() or previous.is_symlink():
            shutil.rmtree(stage)
            raise FleetError(f"stale pet transaction path exists: {previous}")
        had_target = target.exists()
        try:
            for name in sorted(PET_FILES):
                shutil.copy2(source_root / pet_id / name, stage / name)
            if not pet_files_match(stage, expected):
                raise FleetError(f"staged pet verification failed: {pet_id}")
            if had_target:
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = backup_root / f"{pet_id}-{stamp}"
                backup.parent.mkdir(parents=True, exist_ok=True)
                if backup.exists():
                    raise FleetError(f"pet backup already exists: {backup}")
                shutil.copytree(target, backup, symlinks=True)
                target.replace(previous)
            stage.replace(target)
            if not pet_files_match(target, expected):
                raise FleetError(f"installed pet verification failed: {pet_id}")
            if previous.exists():
                shutil.rmtree(previous)
            updated.append(pet_id)
        except Exception:
            if previous.exists():
                if target.exists():
                    shutil.rmtree(target)
                previous.replace(target)
            elif not had_target and target.exists():
                shutil.rmtree(target)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return updated

def control_commit() -> str:
    return run(["git", "-C", str(fleet_common.CONTROL_ROOT), "rev-parse", "HEAD"]).stdout.strip()

def checkout_commit(root: Path) -> str:
    return run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()

def update_checkout(root: Path, *, label: str) -> str:
    if run(["git", "-C", str(root), "status", "--porcelain"]).stdout.strip():
        raise FleetError(f"{label} checkout is dirty")
    run(["git", "-C", str(root), "fetch", "origin", "main"])
    run(["git", "-C", str(root), "checkout", "main"])
    run(["git", "-C", str(root), "merge", "--ff-only", "origin/main"])
    return checkout_commit(root)

def update_flow() -> str:
    return update_checkout(FLOW_ROOT, label="OPL Flow")

def update_control() -> str:
    return update_checkout(fleet_common.CONTROL_ROOT, label="OPL Instance")

def workspace_root() -> Path:
    configured = os.environ.get("OPL_WORKSPACE")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise FleetError("OPL_WORKSPACE must be absolute")
        return root
    return Path.home() / "workspace"

def github_repository_from_remote(
    remote: str,
    *,
    expected_owner: str | None = None,
) -> str | None:
    match = re.fullmatch(
        r"(?:https?://github\.com/|git@github\.com:|ssh://git@github\.com/|"
        r"ssh://git@ssh\.github\.com:443/)"
        r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?",
        remote.strip(),
    )
    if match:
        owner = match.group("owner")
        if expected_owner is not None and owner.casefold() != expected_owner.casefold():
            return None
        return f"{owner}/{match.group('repo')}"
    if expected_owner is None:
        repo = Path(remote.removesuffix("/")).name.removesuffix(".git")
        if re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
            return repo
    return None

def git_value(
    repository: Path,
    arguments: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return run(
        ["git", "-C", str(repository), *arguments],
        check=check,
        timeout=timeout,
    )

def reconcile_repository(
    repository: Path,
    *,
    fetch: bool,
    apply: bool,
    expected_owner: str | None = None,
) -> dict[str, Any] | None:
    branch_result = git_value(
        repository,
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    upstream_result = git_value(
        repository,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        check=False,
    )
    upstream = upstream_result.stdout.strip() if upstream_result.returncode == 0 else ""
    if "/" in upstream:
        remote_name, upstream_branch = upstream.split("/", 1)
    else:
        main_remote = git_value(
            repository,
            ["config", "--get", "branch.main.remote"],
            check=False,
        ).stdout.strip()
        remote_name, upstream_branch = main_remote or "origin", None
    remote_result = git_value(
        repository,
        ["remote", "get-url", remote_name],
        check=False,
    )
    if remote_result.returncode:
        return None
    slug = github_repository_from_remote(
        remote_result.stdout.strip(),
        expected_owner=expected_owner,
    )
    if slug is None:
        return None

    default_ref_result = git_value(
        repository,
        [
            "symbolic-ref",
            "--quiet",
            "--short",
            f"refs/remotes/{remote_name}/HEAD",
        ],
        check=False,
    )
    default_ref = default_ref_result.stdout.strip()
    remote_default_branch = (
        default_ref.removeprefix(f"{remote_name}/")
        if default_ref.startswith(f"{remote_name}/")
        else ""
    )
    default_branch = remote_default_branch or upstream_branch or ""

    base: dict[str, Any] = {
        "repository": slug,
        "remote": remote_name,
        "branch": branch,
        "default_branch": default_branch,
        "dirty": None,
        "ahead": None,
        "behind": None,
        "local_commit": None,
        "remote_commit": None,
    }
    if branch is None:
        return {**base, "state": "DETACHED"}
    if not default_branch:
        return {**base, "state": "UPSTREAM_UNKNOWN"}

    if branch != default_branch:
        return {**base, "state": "TASK_BRANCH"}

    if fetch:
        try:
            fetched = git_value(
                repository,
                ["fetch", "--prune", remote_name],
                check=False,
                timeout=REPOSITORY_FETCH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {**base, "state": "FETCH_TIMEOUT"}
        if fetched.returncode:
            return {**base, "state": "FETCH_FAILED"}

    dirty = bool(git_value(repository, ["status", "--porcelain"]).stdout.strip())
    local_commit = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
    remote_ref = f"refs/remotes/{remote_name}/{default_branch}"
    remote_commit = git_value(repository, ["rev-parse", remote_ref]).stdout.strip()
    counts = git_value(
        repository,
        ["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"],
    ).stdout.split()
    if len(counts) != 2 or any(not value.isdigit() for value in counts):
        raise FleetError(f"invalid repository divergence readback: {slug}")
    ahead, behind = (int(value) for value in counts)

    if branch != default_branch:
        state = "TASK_BRANCH"
    elif dirty:
        state = "DIRTY"
    elif ahead and behind:
        state = "DIVERGED"
    elif ahead:
        state = "LOCAL_AHEAD"
    elif behind and apply:
        merged = git_value(repository, ["merge", "--ff-only", remote_ref], check=False)
        if merged.returncode:
            state = "UPDATE_FAILED"
        else:
            state = "UPDATED"
            local_commit = git_value(repository, ["rev-parse", "HEAD"]).stdout.strip()
            ahead = 0
            behind = 0
    elif behind:
        state = "BEHIND"
    else:
        state = "CURRENT"

    return {
        "repository": slug,
        "remote": remote_name,
        "branch": branch,
        "default_branch": default_branch,
        "state": state,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "local_commit": local_commit,
        "remote_commit": remote_commit,
    }

def reconcile_workspace_repositories(
    *,
    root: Path | None = None,
    fetch: bool,
    apply: bool,
    expected_owner: str | None | object = _INSTANCE_OWNER,
) -> dict[str, Any]:
    if apply and not fetch:
        raise FleetError("repository apply requires a fresh fetch")
    root = root or workspace_root()
    if expected_owner is _INSTANCE_OWNER:
        expected_owner = managed_repository_owner()
    entries: list[dict[str, Any]] = []
    if root.is_dir():
        for candidate in sorted(root.iterdir(), key=lambda path: path.name):
            if (
                candidate.name.startswith(".")
                or candidate.is_symlink()
                or not candidate.is_dir()
                or not (candidate / ".git").exists()
            ):
                continue
            result = reconcile_repository(
                candidate,
                fetch=fetch,
                apply=apply,
                expected_owner=expected_owner,
            )
            if result is not None:
                entries.append(result)
    attention_count = sum(
        entry["state"] not in {"CURRENT", "UPDATED"} for entry in entries
    )
    return {
        "schema": "opl_fleet_repository_readback.v1",
        "observed_at": utc_now().isoformat().replace("+00:00", "Z"),
        "state": "CURRENT" if not attention_count else "ATTENTION",
        "attention_count": attention_count,
        "repositories": entries,
    }

def fleet_repositories(*, sync: bool) -> int:
    report = reconcile_workspace_repositories(fetch=sync, apply=sync)
    atomic_json(STATE_ROOT / "repositories.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["state"] == "CURRENT" else 1

def restart_after_flow_update(previous: str, current: str) -> None:
    if previous == current:
        return
    script = fleet_common.FLEET_ENTRY_SCRIPT
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[1:]])

def github_head(repository: str, branch: str) -> str:
    return run(
        ["gh", "api", f"repos/{repository}/commits/{branch}", "--jq", ".sha"]
    ).stdout.strip()

def validated_control_checkout(repository: str, revision: str) -> Path:
    control_root = fleet_common.CONTROL_ROOT.resolve()
    root = Path(
        git_value(control_root, ["rev-parse", "--show-toplevel"]).stdout.strip()
    ).resolve()
    remote = git_value(root, ["remote", "get-url", "origin"]).stdout.strip()
    if github_repository_from_remote(remote) != repository:
        raise FleetError("fleet runner owner does not match the Instance checkout")
    if checkout_commit(root) != revision:
        raise FleetError("Instance checkout revision changed during reconciliation")
    return root

def install_runner(spec: dict[str, Any], revision: str) -> str:
    repository = str(spec["repository"])
    validated_control_checkout(repository, revision)
    state_path = STATE_ROOT / "runner.json"
    previous = read_json(state_path) if state_path.is_file() else {}
    if not RUNNER_PATH.is_file() or previous.get("commit") != revision:
        command = [str(item) for item in spec["install_command"]]
        if command[:3] != ["npx", "skills", "add"]:
            raise FleetError("runner install command is not owner-supported")
        run(command)
        help_text = run([sys.executable, str(RUNNER_PATH), "--help"]).stdout
        if "node-status" not in help_text or "node-sync" not in help_text:
            raise FleetError("installed runner does not expose pull-node commands")
        atomic_json(state_path, {"repository": repository, "commit": revision})
    return revision

def fetch_skill_reference(spec: dict[str, Any], revision: str) -> dict[str, Any]:
    relative = str(spec["skill_reference"])
    repository = str(spec["repository"])
    root = validated_control_checkout(repository, revision).resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise FleetError("owner skill reference escapes the Instance checkout") from exc
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema") != SKILL_REFERENCE_SCHEMA:
        raise FleetError("owner skill reference is invalid")
    return payload

def protected_discovery_root_paths(
    reference: dict[str, Any],
    *,
    home: Path | None = None,
) -> tuple[tuple[str, Path], ...]:
    discovery_roots = reference.get("discovery_roots")
    protected_roots = reference.get("protected_discovery_roots", [])
    if not isinstance(discovery_roots, list) or not isinstance(protected_roots, list):
        raise FleetError("owner skill discovery root policy is invalid")
    declared = {str(root) for root in discovery_roots}
    owner_home = home or Path.home()
    resolved: list[tuple[str, Path]] = []
    for raw in protected_roots:
        if not isinstance(raw, str) or not raw:
            raise FleetError("protected skill root must be a home-relative path")
        relative = Path(raw)
        if (
            raw not in declared
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in raw
        ):
            raise FleetError(f"unsafe protected skill root: {raw}")
        resolved.append((raw, owner_home / relative))
    return tuple(resolved)

def repair_protected_discovery_roots(
    reference: dict[str, Any],
    *,
    home: Path | None = None,
) -> list[str]:
    repaired: list[str] = []
    for relative, root in protected_discovery_root_paths(reference, home=home):
        root.parent.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            try:
                target = root.resolve(strict=True)
            except OSError as exc:
                raise FleetError(f"protected skill root target is unavailable: {relative}") from exc
            if not target.is_dir():
                raise FleetError(f"protected skill root target is not a directory: {relative}")
            transaction = Path(tempfile.mkdtemp(
                prefix=f".{root.name}.opl-root-recovery-",
                dir=root.parent,
            ))
            staged = transaction / "restored"
            displaced = transaction / "displaced-link"
            try:
                shutil.copytree(target, staged, symlinks=True)
                if not root.is_symlink() or root.resolve(strict=True) != target:
                    raise FleetError(f"protected skill root changed during recovery: {relative}")
                root.replace(displaced)
                try:
                    staged.replace(root)
                except Exception:
                    displaced.replace(root)
                    raise
            finally:
                if root.exists() or root.is_symlink():
                    shutil.rmtree(transaction, ignore_errors=True)
            repaired.append(relative)
            continue
        if root.exists():
            if not root.is_dir():
                raise FleetError(f"protected skill root is not a directory: {relative}")
            continue
        root.mkdir(parents=True)
        repaired.append(relative)
    return repaired

def _flow_package_status(opl_command: str) -> dict[str, Any] | None:
    result = run(
        [opl_command, "packages", "status", "--package-id", "opl-flow", "--json"],
        check=False,
        timeout=60,
    )
    if result.returncode:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    status = payload.get("opl_agent_package_status") if isinstance(payload, dict) else None
    return status if isinstance(status, dict) else None

def reconcile_flow_experience_baseline(*, opl_command: str | None = None) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "surface_kind": "opl_flow_experience_baseline_reconcile.v1",
        "status": "unavailable",
        "repair_attempted": False,
        "failure_ids": [],
        "reason": "opl_command_unavailable",
    }
    resolved_opl_command = opl_command or shutil.which("opl")
    if not resolved_opl_command:
        return receipt
    status = _flow_package_status(resolved_opl_command)
    if status is None:
        return {**receipt, "reason": "package_status_unavailable"}
    baseline = status.get("experience_baseline")
    if not isinstance(baseline, dict):
        return {**receipt, "reason": "experience_baseline_readback_missing"}
    failure_ids = sorted({
        str(item)
        for item in baseline.get("failure_ids", [])
        if isinstance(item, str) and item
    })
    baseline_status = baseline.get("status")
    if baseline_status == "current":
        return {
            **receipt,
            "status": "current",
            "failure_ids": failure_ids,
            "reason": None,
        }
    if baseline_status != "degraded":
        return {
            **receipt,
            "failure_ids": failure_ids,
            "reason": "experience_baseline_not_actionable",
        }

    repair_command = baseline.get("repair_command")
    try:
        repair_parts = shlex.split(repair_command) if isinstance(repair_command, str) else []
    except ValueError:
        repair_parts = []
    if repair_parts != ["opl", "packages", "repair", "--package-id", "opl-flow"]:
        return {
            **receipt,
            "status": "repair_failed",
            "failure_ids": failure_ids,
            "reason": "repair_command_not_authorized",
        }
    repair = run(
        [resolved_opl_command, *repair_parts[1:], "--json"],
        check=False,
        timeout=300,
    )
    if repair.returncode:
        return {
            **receipt,
            "status": "repair_failed",
            "repair_attempted": True,
            "failure_ids": failure_ids,
            "reason": "repair_command_failed",
        }
    repaired_status = _flow_package_status(resolved_opl_command)
    repaired_baseline = (
        repaired_status.get("experience_baseline")
        if isinstance(repaired_status, dict)
        else None
    )
    if not isinstance(repaired_baseline, dict) or repaired_baseline.get("status") != "current":
        return {
            **receipt,
            "status": "repair_failed",
            "repair_attempted": True,
            "failure_ids": failure_ids,
            "reason": "repair_readback_not_current",
        }
    return {
        **receipt,
        "status": "repaired",
        "repair_attempted": True,
        "failure_ids": failure_ids,
        "reason": None,
    }

def _plugin_skill_roots_from_payload(payload: object) -> tuple[Path, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("installed"), list):
        return ()
    try:
        entries = payload["installed"]
    except KeyError:
        return ()
    roots: set[Path] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or entry.get("installed") is not True
            or entry.get("enabled") is not True
        ):
            continue
        source = entry.get("source")
        source_path = source.get("path") if isinstance(source, dict) else None
        if not isinstance(source_path, str):
            continue
        plugin_root = Path(source_path).expanduser()
        skill_root = plugin_root / "skills"
        if plugin_root.is_absolute() and skill_root.is_dir():
            roots.add(skill_root)
    return tuple(sorted(roots))

def _real_directory(
    path: Path,
    *,
    owner_root: Path | None = None,
    allow_owner_root: bool = False,
) -> Path | None:
    try:
        if path.is_symlink() or not path.is_dir():
            return None
        resolved = path.resolve(strict=True)
        if owner_root is not None:
            owner = owner_root.resolve(strict=True)
            if (
                (resolved == owner and not allow_owner_root)
                or (resolved != owner and owner not in resolved.parents)
            ):
                return None
        return resolved
    except OSError:
        return None

def _safe_json_record(path: Path, owner_root: Path) -> dict[str, Any] | None:
    try:
        owner = owner_root.resolve(strict=True)
        if path.is_symlink() or not path.is_file():
            return None
        resolved = path.resolve(strict=True)
        if owner not in resolved.parents:
            return None
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

def _safe_local_plugin_root(marketplace_root: Path, relative_source: str) -> Path | None:
    relative = Path(relative_source)
    if relative.is_absolute():
        return None
    plugin_root = _real_directory(
        marketplace_root / relative,
        owner_root=marketplace_root,
        allow_owner_root=True,
    )
    if plugin_root is None:
        return None
    try:
        if any(
            entry.is_symlink() or not (entry.is_dir() or entry.is_file())
            for entry in plugin_root.rglob("*")
        ):
            return None
    except OSError:
        return None
    return plugin_root

def _configured_local_plugin_skill_roots() -> tuple[Path, ...]:
    if tomllib is None:
        return ()
    config_path = effective_codex_home() / "config.toml"
    try:
        if config_path.is_symlink() or not config_path.is_file():
            return ()
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return ()
    marketplaces = config.get("marketplaces")
    plugins = config.get("plugins")
    if not isinstance(marketplaces, dict) or not isinstance(plugins, dict):
        return ()
    roots: set[Path] = set()
    for plugin_id, plugin_config in plugins.items():
        if (
            not isinstance(plugin_id, str)
            or "@" not in plugin_id
            or not isinstance(plugin_config, dict)
            or plugin_config.get("enabled") is not True
        ):
            continue
        plugin_name, marketplace_id = plugin_id.rsplit("@", 1)
        marketplace = marketplaces.get(marketplace_id)
        if (
            not plugin_name
            or not marketplace_id
            or not isinstance(marketplace, dict)
            or marketplace.get("source_type") != "local"
            or not isinstance(marketplace.get("source"), str)
        ):
            continue
        marketplace_root = Path(marketplace["source"]).expanduser()
        if not marketplace_root.is_absolute():
            continue
        marketplace_root = _real_directory(marketplace_root)
        if marketplace_root is None:
            continue
        manifest = _safe_json_record(
            marketplace_root / ".agents/plugins/marketplace.json",
            marketplace_root,
        )
        entries = manifest.get("plugins") if manifest else None
        if not isinstance(entries, list):
            continue
        matches = [
            entry for entry in entries
            if isinstance(entry, dict) and entry.get("name") == plugin_name
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("source"), dict):
            continue
        source = matches[0]["source"]
        relative_source = source.get("path")
        if source.get("source") != "local" or not isinstance(relative_source, str):
            continue
        plugin_root = _safe_local_plugin_root(marketplace_root, relative_source)
        if plugin_root is None:
            continue
        plugin_manifest = _safe_json_record(
            plugin_root / ".codex-plugin/plugin.json",
            plugin_root,
        )
        skill_root = _real_directory(plugin_root / "skills", owner_root=plugin_root)
        if plugin_manifest and plugin_manifest.get("name") == plugin_name and skill_root:
            roots.add(skill_root)
    return tuple(sorted(roots))

def codex_plugin_skill_roots() -> tuple[Path, ...]:
    if shutil.which("codex"):
        result = run(["codex", "plugin", "list", "--json"], check=False)
        if result.returncode:
            return ()
        try:
            return _plugin_skill_roots_from_payload(json.loads(result.stdout))
        except json.JSONDecodeError:
            return ()
    return _configured_local_plugin_skill_roots()

def skill_present(
    reference: dict[str, Any],
    skill: str,
    plugin_skill_roots: tuple[Path, ...] = (),
) -> bool:
    discovery_roots = [
        Path.home() / str(relative) for relative in reference["discovery_roots"]
    ]
    return any(
        (root / skill / "SKILL.md").is_file()
        for root in [*discovery_roots, *plugin_skill_roots]
    )

def install_missing_owner_skills(
    reference: dict[str, Any],
) -> list[str]:
    owner_actions: list[str] = []
    for package, entry in reference["packages"].items():
        if not entry.get("required"):
            continue
        command: list[str] = []
        owner_native_opl = False
        plugin_skill_roots: tuple[Path, ...] = ()
        if entry["ownership"] != "codex":
            command = shlex.split(str(entry["install"]["command"]))
            owner_native_opl = command == [
                "opl",
                "packages",
                "install",
                str(package),
                "--json",
            ]
            if owner_native_opl:
                plugin_skill_roots = codex_plugin_skill_roots()
        missing = [
            name
            for name in entry["skills"]
            if not skill_present(reference, name, plugin_skill_roots)
        ]
        if not missing:
            continue
        if entry["ownership"] == "codex":
            owner_actions.append(str(package))
            continue
        if command[:3] != ["npx", "skills", "add"] and not owner_native_opl:
            raise FleetError(f"unsafe owner install route: {package}")
        run(command)
        if owner_native_opl:
            plugin_skill_roots = codex_plugin_skill_roots()
        remaining = [
            name
            for name in missing
            if not skill_present(reference, name, plugin_skill_roots)
        ]
        if remaining:
            raise FleetError(f"owner install did not provide {package}: {remaining}")
    return sorted(owner_actions)

def runner_call(action: str) -> dict[str, Any]:
    result = run(
        [sys.executable, str(RUNNER_PATH), action, "--json"],
        check=False,
    )
    for line in reversed(result.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise FleetError(f"runner returned no JSON for {action}")

def build_receipt(
    node_id: str,
    node_payload: dict[str, Any],
    *,
    owner_actions: list[str],
    control_revision: str,
    runner_revision: str,
) -> dict[str, Any]:
    result = node_payload.get("result") if node_payload.get("ok") else {}
    result = result if isinstance(result, dict) else {}
    drift = [
        str(item)
        for item in result.get("drift", [])
        if isinstance(item, str) and len(item) <= 120
    ]
    if not node_payload.get("ok"):
        drift.append("node.command-failed")
    ok = bool(node_payload.get("ok") and result.get("ok") and not owner_actions)
    return {
        "schema": "codex_fleet_receipt.v1",
        "node_id": normalize_node_id(node_id),
        "hostname_s": normalize_node_id(socket.gethostname().split(".")[0]),
        "platform": "wsl" if "microsoft" in platform.release().lower() else platform.system().lower(),
        "architecture": platform.machine().lower(),
        "state": "CURRENT" if ok else "UPDATE_REQUIRED",
        "drift": sorted(set(drift)),
        "owner_actions": sorted(set(owner_actions)),
        "control_commit": control_revision,
        "runner_commit": runner_revision,
        "updated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }

def validate_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != RECEIPT_FIELDS:
        raise FleetError("receipt fields are not allowed")
    if payload.get("schema") != "codex_fleet_receipt.v1":
        raise FleetError("unsupported receipt")
    payload["node_id"] = normalize_node_id(str(payload["node_id"]))
    payload["hostname_s"] = normalize_node_id(str(payload["hostname_s"]))
    if payload.get("state") not in {"CURRENT", "UPDATE_REQUIRED", "EXTERNAL_BLOCKER"}:
        raise FleetError("invalid receipt state")
    for key in ("drift", "owner_actions"):
        values = payload.get(key)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or len(item) > 120 for item in values)
        ):
            raise FleetError(f"invalid receipt {key}")
    for key in ("control_commit", "runner_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get(key, ""))):
            raise FleetError(f"invalid receipt {key}")
    dt.datetime.fromisoformat(str(payload["updated_at"]).replace("Z", "+00:00"))
    return payload

def render_status(state_root: Path) -> str:
    receipts: list[dict[str, Any]] = []
    for path in sorted((state_root / "nodes").glob("*/receipt.json")):
        receipts.append(validate_receipt(read_json(path)))
    lines = [
        "# OPL Fleet Status",
        "",
        "| Node | State | Platform | Last Seen (UTC) | Drift | Control | Runner |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(receipts, key=lambda row: row["node_id"]):
        drift = ",".join([*item["drift"], *item["owner_actions"]]) or "-"
        lines.append(
            f"| {item['node_id']} | {item['state']} | {item['platform']}/{item['architecture']} "
            f"| {item['updated_at']} | {drift} | {item['control_commit'][:12]} "
            f"| {item['runner_commit'][:12]} |"
        )
    if not receipts:
        lines.append("| - | NO_NODES | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)

def format_bytes(value: Any) -> str:
    if not isinstance(value, int) or value < 0:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024
    return f"{amount:.1f} {unit}"

def markdown_text(value: Any) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")

def build_asset_catalog(
    state_root: Path,
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or node_registry()
    registered = registry["nodes"]
    discovered = {
        path.parent.name
        for path in (state_root / "nodes").glob("*/receipt.json")
    } | {
        path.parent.name
        for path in (state_root / "nodes").glob("*/inventory.json")
    }
    node_ids = sorted(set(registered) | discovered)
    entries: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for node_id in node_ids:
        receipt_path = state_root / "nodes" / node_id / "receipt.json"
        inventory_path = state_root / "nodes" / node_id / "inventory.json"
        receipt = validate_receipt(read_json(receipt_path)) if receipt_path.is_file() else None
        inventory = (
            validate_inventory(read_json(inventory_path))
            if inventory_path.is_file()
            else None
        )
        if receipt:
            timestamps.append(str(receipt["updated_at"]))
        if inventory:
            timestamps.append(str(inventory["observed_at"]))
        policy = registered.get(
            node_id,
            {
                "approved": False,
                "display_name": node_id,
                "labels": [],
                "notes": [],
            },
        )
        entries.append(
            {
                "node_id": node_id,
                "policy": policy,
                "receipt": receipt,
                "inventory": inventory,
            }
        )
    return {
        "schema": "codex_fleet_assets.v1",
        "generated_at": max(timestamps) if timestamps else None,
        "nodes": entries,
    }

def render_assets(catalog: dict[str, Any]) -> str:
    receipt_states = {
        "CURRENT": "当前",
        "UPDATE_REQUIRED": "需要更新",
        "NO_RECEIPT": "尚无回报",
    }
    note_categories = {
        "cooling": "散热",
        "codex": "Codex",
        "os-lifecycle": "系统生命周期",
        "ssh": "SSH",
        "storage": "存储",
        "virtualization": "虚拟化",
    }
    lines = [
        "# OPL Fleet 资产清单",
        "",
        f"根据脱敏节点报告生成：`{catalog.get('generated_at') or '尚无报告'}`。",
        "",
        "## 设备总览",
        "",
        "| 节点 | 已批准 | 状态 | 设备 | CPU | 内存 | GPU | 可用磁盘 | Codex | SSH | Tailscale | 资产采集时间 |",
        "| --- | --- | --- | --- | --- | ---: | --- | ---: | --- | --- | --- | --- |",
    ]
    for entry in catalog["nodes"]:
        policy = entry["policy"]
        receipt = entry["receipt"] or {}
        inventory = entry["inventory"] or {}
        host = inventory.get("host") or {}
        hardware = inventory.get("hardware") or {}
        storage = inventory.get("storage") or {}
        baseline = inventory.get("baseline") or {}
        codex = baseline.get("codex") or {}
        ssh = baseline.get("ssh") or {}
        tailscale = baseline.get("tailscale") or {}
        gpu_names = ", ".join(
            str(item.get("name"))
            for item in hardware.get("gpus", [])
            if item.get("name")
        ) or "-"
        ssh_state = "待采集"
        codex_state = "待采集"
        tailscale_state = "待采集"
        if inventory:
            ssh_state = (
                "监听中"
                if ssh.get("listening") is True
                else "已安装"
                if ssh.get("installed")
                else "缺失"
            )
            codex_state = "就绪" if codex.get("ready") else "缺失"
            tailscale_state = "在线" if tailscale.get("online") else "离线或缺失"
        receipt_state = receipt.get("state", "NO_RECEIPT")
        scheduling = inventory.get("scheduling") or {}
        dispatch_state = (
            "可调度"
            if scheduling.get("eligible")
            else "暂不可调度"
            if inventory
            else "待采集"
        )
        lines.append(
            f"| `{entry['node_id']}` | {'是' if policy['approved'] else '否'} "
            f"| {receipt_states.get(receipt_state, receipt_state)} "
            f"| {markdown_text(host.get('model') or host.get('os_name'))} "
            f"| {markdown_text(hardware.get('cpu_model'))} "
            f"| {format_bytes(hardware.get('memory_bytes'))} "
            f"| {markdown_text(gpu_names)} "
            f"| {format_bytes(storage.get('free_bytes'))} "
            f"| {codex_state} "
            f"| {ssh_state} "
            f"| {tailscale_state} "
            f"| {inventory.get('observed_at', '待采集')} |"
        )
    lines.extend(["", "## 节点详情", ""])
    for entry in catalog["nodes"]:
        node_id = entry["node_id"]
        policy = entry["policy"]
        receipt = entry["receipt"] or {}
        inventory = entry["inventory"]
        receipt_state = receipt.get("state", "NO_RECEIPT")
        lines.extend(
            [
                f"### {markdown_text(policy['display_name'])} (`{node_id}`)",
                "",
                f"- 批准状态：`{'已批准' if policy['approved'] else '未批准'}`",
                f"- 标签：{', '.join(f'`{item}`' for item in policy['labels']) or '-'}",
                f"- Fleet 状态：`{receipt_states.get(receipt_state, receipt_state)}`",
                f"- 最近回报：`{receipt.get('updated_at', '-')}`",
                f"- 调度快照：`{dispatch_state}`",
            ]
        )
        if not inventory:
            lines.extend(["- 资产采集：`待处理`", ""])
        else:
            host = inventory["host"]
            execution = inventory["execution"]
            hardware = inventory["hardware"]
            storage = inventory["storage"]
            baseline = inventory["baseline"]
            capabilities = inventory.get("capabilities") or {}
            power = capabilities.get("power") or {}
            virtualization = capabilities.get("virtualization") or {}
            gui = capabilities.get("gui") or {}
            workload = capabilities.get("workload") or {}
            rollback = capabilities.get("rollback") or {}
            scheduling = inventory.get("scheduling") or {}
            ssh_listening = baseline["ssh"].get("listening")
            ssh_listening_text = (
                "是"
                if ssh_listening is True
                else "否"
                if ssh_listening is False
                else "未采集"
            )
            lines.extend(
                [
                    f"- 主机：{markdown_text(host.get('manufacturer'))} "
                    f"{markdown_text(host.get('model'))}；"
                    f"{markdown_text(host.get('os_name'))} "
                    f"{markdown_text(host.get('os_version'))} "
                    f"（构建 {markdown_text(host.get('build'))}）",
                    f"- 执行环境：`{markdown_text(execution.get('kind'))}`；"
                    f"{markdown_text(execution.get('os_name'))} "
                    f"{markdown_text(execution.get('os_version'))}；"
                    f"`{markdown_text(execution.get('architecture'))}`；"
                    f"内核 `{markdown_text(execution.get('kernel'))}`",
                    f"- CPU：{markdown_text(hardware.get('cpu_model'))}；"
                    f"{hardware.get('logical_cores') or '-'} 个逻辑核心",
                    f"- 内存：{format_bytes(hardware.get('memory_bytes'))}",
                    f"- 执行环境存储：可用 {format_bytes(storage.get('free_bytes'))}，"
                    f"总计 {format_bytes(storage.get('total_bytes'))}",
                    f"- Codex：`{markdown_text(baseline['codex'].get('kind'))}` "
                    f"`{markdown_text(baseline['codex'].get('version'))}`；"
                    f"{'就绪' if baseline['codex'].get('ready') else '缺失'}",
                    f"- SSH：{'已安装' if baseline['ssh'].get('installed') else '未安装'}；"
                    f"监听状态：{ssh_listening_text}",
                    f"- Tailscale：{'已安装' if baseline['tailscale'].get('installed') else '未安装'}；"
                    f"{'在线' if baseline['tailscale'].get('online') else '离线'}；"
                    f"版本：{markdown_text(baseline['tailscale'].get('version'))}",
                    f"- 电源：`{markdown_text(power.get('source'))}`；"
                    f"电池：{'有' if power.get('battery_present') else '无'}；"
                    f"电量：{markdown_text(power.get('percent'))}",
                    f"- 虚拟化：Hypervisor {'就绪' if virtualization.get('hypervisor_ready') else '未就绪'}；"
                    f"Tart {'已安装' if (virtualization.get('tart') or {}).get('present') else '未安装'}；"
                    f"VMware {'已安装' if (virtualization.get('vmware') or {}).get('present') else '未安装'}",
                    f"- GUI/签名：GUI {'可用' if gui.get('available') else '不可用'}；"
                    f"交互会话 {'存在' if gui.get('interactive_session') else '无'}；"
                    f"签名身份 {markdown_text(gui.get('code_signing_identities'))}",
                    f"- 当前负载：每核心 `{markdown_text(workload.get('load_1_per_core'))}`；"
                    f"{'繁忙' if workload.get('busy') else '空闲'}；"
                    f"热状态 `{markdown_text(workload.get('thermal_state'))}`",
                    f"- 回滚：`{markdown_text(rollback.get('kind'))}`；"
                    f"{'已验证可用' if rollback.get('available') is True else '未验证' if rollback.get('available') is None else '不可用'}",
                    f"- 调度：AC 门禁 {'启用' if scheduling.get('requires_ac') else '不适用'}；"
                    f"电源 {'通过' if scheduling.get('power_ok') else '不通过'}；"
                    f"磁盘 {'通过' if scheduling.get('storage_ok') else '不通过'}；"
                    f"温度 {'通过' if scheduling.get('thermal_ok') else '不通过'}；"
                    f"交互占用 "
                    f"{'是' if scheduling.get('interactive_busy') is True else '否' if scheduling.get('interactive_busy') is False else '未知'}；"
                    f"{'繁忙' if scheduling.get('busy') else '空闲'}",
                    "- 租约：由主控实时管理，不写入资产快照；"
                    "使用 `opl-fleet lease show` 回读。",
                    f"- 优先角色：{', '.join(f'`{item}`' for item in scheduling.get('preferred_for', [])) or '-'}",
                    f"- 资产采集时间：`{inventory['observed_at']}`",
                    "",
                    "#### GPU",
                    "",
                ]
            )
            if hardware["gpus"]:
                for gpu in hardware["gpus"]:
                    detail = []
                    if gpu.get("memory_bytes"):
                        detail.append(format_bytes(gpu["memory_bytes"]))
                    if gpu.get("memory"):
                        detail.append(str(gpu["memory"]))
                    if gpu.get("driver_version"):
                        detail.append(f"驱动 {gpu['driver_version']}")
                    lines.append(
                        f"- {markdown_text(gpu.get('name'))}"
                        f"{'：' + '，'.join(detail) if detail else ''}"
                    )
            else:
                lines.append("- 未报告")
            lines.extend(["", "#### 开发软件", "", "| 工具 | 已安装 | 版本 |", "| --- | --- | --- |"])
            for tool, detail in sorted(inventory["software"].items()):
                lines.append(
                    f"| `{tool}` | {'是' if detail.get('present') else '否'} "
                    f"| {markdown_text(detail.get('version'))} |"
                )
            lines.extend(["", "#### 专用软件", ""])
            if inventory["specialized_software"]:
                for item in inventory["specialized_software"]:
                    lines.append(
                        f"- **{markdown_text(item.get('name'))}** "
                        f"`{markdown_text(item.get('version'))}`："
                        f"{markdown_text(item.get('purpose'))}"
                    )
            else:
                lines.append("- 经批准的探测未发现专用软件")
            lines.append("")
        lines.extend(["#### 运维注意事项", ""])
        if policy["notes"]:
            for note in policy["notes"]:
                category = note_categories.get(note["category"], note["category"])
                lines.append(
                    f"- **{markdown_text(category)}：**"
                    f"{markdown_text(note['summary'])}"
                )
        else:
            lines.append("- 无")
        lines.append("")
    lines.extend(
        [
            "## 调度边界",
            "",
            "本文档是持久化的脱敏资产清单，不代表节点当前一定可用。"
            "分配任务前必须运行 `opl-fleet doctor <node-id>` 做实时检查。",
            "",
        ]
    )
    return "\n".join(lines)

def write_asset_catalog(
    state_root: Path,
    *,
    registry: dict[str, Any] | None = None,
) -> None:
    catalog = build_asset_catalog(state_root, registry=registry)
    atomic_json(state_root / "ASSETS.json", catalog, mode=0o644)
    (state_root / "ASSETS.md").write_text(render_assets(catalog), encoding="utf-8")

def record_receipt(state_root: Path, encoded: str) -> Path:
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:
        raise FleetError("receipt payload is not valid base64 JSON") from exc
    if not isinstance(payload, dict):
        raise FleetError("receipt payload must be an object")
    inventory = None
    if payload.get("schema") == "codex_fleet_report.v1":
        if set(payload) != REPORT_FIELDS:
            raise FleetError("node report fields are not allowed")
        receipt = validate_receipt(payload["receipt"])
        inventory = validate_inventory(payload["inventory"])
        if inventory["node_id"] != receipt["node_id"]:
            raise FleetError("node report identities do not match")
    else:
        receipt = validate_receipt(payload)
    destination = state_root / "nodes" / receipt["node_id"] / "receipt.json"
    atomic_json(destination, receipt, mode=0o644)
    if inventory:
        atomic_json(destination.with_name("inventory.json"), inventory, mode=0o644)
    status_path = state_root / "STATUS.md"
    status_path.write_text(render_status(state_root), encoding="utf-8")
    write_asset_catalog(state_root)
    return destination

def report_receipt(
    repo: str,
    workflow: str,
    receipt: dict[str, Any],
    inventory: dict[str, Any],
) -> None:
    report = {
        "schema": "codex_fleet_report.v1",
        "receipt": receipt,
        "inventory": inventory,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(report, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    run(
        [
            "gh",
            "workflow",
            "run",
            workflow,
            "--repo",
            repo,
            "--ref",
            "main",
            "-f",
            f"payload={encoded}",
        ]
    )

def install_macos_schedule(
    hour: int,
    minute: int,
    service_id: str = "dev.one-person-lab.opl-fleet",
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", service_id):
        raise FleetError("invalid Fleet service id")
    label = service_id
    path = Path.home() / f"Library/LaunchAgents/{label}.plist"
    log_root = STATE_ROOT / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    command = Path.home() / ".local/bin/opl-fleet"
    launchd_path = ":".join(
        [
            str(Path.home() / ".local/bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
        ]
    )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{label}</string>
<key>EnvironmentVariables</key><dict>
<key>HOME</key><string>{Path.home()}</string>
<key>PATH</key><string>{launchd_path}</string>
</dict>
<key>ProgramArguments</key><array>
<string>{command}</string><string>reconcile</string><string>--report</string>
</array>
<key>StartCalendarInterval</key><dict>
<key>Hour</key><integer>{hour}</integer>
<key>Minute</key><integer>{minute}</integer>
</dict>
<key>StandardOutPath</key><string>{log_root / 'stdout.log'}</string>
<key>StandardErrorPath</key><string>{log_root / 'stderr.log'}</string>
</dict></plist>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.stage-{os.getpid()}")
    staged.write_text(content, encoding="utf-8")
    os.chmod(staged, 0o600)
    staged.replace(path)
    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", domain, str(path)], check=False)
    run(["launchctl", "bootstrap", domain, str(path)])

def install_wsl_schedule(hour: int, minute: int) -> None:
    distro = os.environ.get("WSL_DISTRO_NAME")
    if not distro:
        raise FleetError("WSL_DISTRO_NAME is missing")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", distro):
        raise FleetError("WSL_DISTRO_NAME is not task-safe")
    scheduler = Path("/mnt/c/Windows/System32/schtasks.exe")
    if not scheduler.is_file():
        raise FleetError("Windows Task Scheduler is unavailable")
    windows_cmd = run(
        ["wslpath", "-w", str(scheduler.with_name("cmd.exe"))]
    ).stdout.strip()
    windows_wsl = run(
        ["wslpath", "-w", str(scheduler.with_name("wsl.exe"))]
    ).stdout.strip()
    if not windows_cmd or not windows_wsl:
        raise FleetError("Windows scheduler launcher paths are unavailable")
    command = (
        f"{windows_cmd} /d /c {windows_wsl} -d {distro} -- "
        f'{Path.home() / ".local/bin/opl-fleet"} '
        "reconcile --report "
        "1>>%TEMP%\\opl-fleet-reconcile.stdout.log "
        "2>>%TEMP%\\opl-fleet-reconcile.stderr.log"
    )
    if len(command) > 261:
        raise FleetError("Windows Task Scheduler command exceeds 261 characters")
    run(
        [
            str(scheduler),
            "/Create",
            "/F",
            "/SC",
            "DAILY",
            "/ST",
            f"{hour:02d}:{minute:02d}",
            "/TN",
            "OPLFleet-Reconcile",
            "/TR",
            command,
        ]
    )

def install_linux_schedule(hour: int, minute: int) -> None:
    unit_root = Path.home() / ".config/systemd/user"
    unit_root.mkdir(parents=True, exist_ok=True)
    command = Path.home() / ".local/bin/opl-fleet"
    (unit_root / "opl-fleet.service").write_text(
        "[Unit]\nDescription=Reconcile OPL Fleet node\n"
        "[Service]\nType=oneshot\n"
        f"ExecStart={command} reconcile --report\n",
        encoding="utf-8",
    )
    (unit_root / "opl-fleet.timer").write_text(
        "[Unit]\nDescription=Daily OPL Fleet reconciliation\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\n"
        "Persistent=true\nRandomizedDelaySec=900\n"
        "[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "--now", "opl-fleet.timer"])

def install_schedule(spec: dict[str, Any]) -> None:
    hour = int(spec["hour"])
    minute = int(spec["minute"])
    service_id = str(spec["service_id"])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise FleetError("invalid fleet schedule")
    if "microsoft" in platform.release().lower():
        install_wsl_schedule(hour, minute)
    elif platform.system() == "Darwin":
        install_macos_schedule(hour, minute, service_id)
    else:
        install_linux_schedule(hour, minute)

def reconcile(*, report: bool, install_required: bool) -> dict[str, Any]:
    if report:
        run(["gh", "auth", "status"])
    previous_flow_revision = checkout_commit(FLOW_ROOT)
    flow_revision = update_flow()
    restart_after_flow_update(previous_flow_revision, flow_revision)
    control_revision = update_control()
    spec = manifest()
    reconcile_pets(spec)
    runner_revision = install_runner(spec["runner"], control_revision)
    reference = fetch_skill_reference(spec["runner"], runner_revision)
    repaired_roots = repair_protected_discovery_roots(reference)
    atomic_json(
        STATE_ROOT / "protected-skill-roots.json",
        {
            "surface_kind": "opl_protected_skill_roots_reconcile.v1",
            "status": "repaired" if repaired_roots else "current",
            "protected_roots": list(reference.get("protected_discovery_roots", [])),
            "repaired_roots": repaired_roots,
        },
    )
    baseline_reconcile = reconcile_flow_experience_baseline()
    atomic_json(STATE_ROOT / "flow-experience-baseline.json", baseline_reconcile)
    owner_actions: list[str] = []
    if install_required:
        owner_actions = install_missing_owner_skills(reference)
    apply = runner_call("node-sync")
    verify = runner_call("node-status")
    payload = verify if verify.get("ok") else apply
    node_id = node_identity()
    receipt = build_receipt(
        node_id,
        payload,
        owner_actions=owner_actions,
        control_revision=control_revision,
        runner_revision=runner_revision,
    )
    repository_report = reconcile_workspace_repositories(fetch=True, apply=True)
    atomic_json(STATE_ROOT / "repositories.json", repository_report)
    if repository_report["state"] != "CURRENT":
        receipt["drift"].append("development-repositories.attention")
        receipt["state"] = "UPDATE_REQUIRED"
    inventory = collect_inventory(node_id, spec, node_registry())
    atomic_json(STATE_ROOT / "receipt.json", receipt)
    atomic_json(STATE_ROOT / "inventory.json", inventory)
    if report:
        report_receipt(
            str(spec["repository"]),
            str(spec["receipt_workflow"]),
            receipt,
            inventory,
        )
    return receipt

def join(args: argparse.Namespace) -> int:
    node_id = node_identity(args.node_id)
    atomic_json(
        CONFIG_PATH,
        {
            "schema": "codex_fleet_node.v1",
            "node_id": node_id,
            "repository": str(manifest()["repository"]),
        },
    )
    if not args.no_schedule:
        install_schedule(manifest()["schedule"])
    receipt = reconcile(report=True, install_required=True)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["state"] == "CURRENT" else 1

def fetch_state_file(relative: str) -> str:
    spec = manifest()
    result = run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{spec['repository']}/contents/{relative}?ref=state",
        ],
        check=False,
    )
    if result.returncode:
        raise FleetError(f"fleet state file is unavailable: {relative}")
    return result.stdout

def remote_asset_catalog() -> dict[str, Any]:
    payload = json.loads(fetch_state_file("ASSETS.json"))
    if not isinstance(payload, dict) or payload.get("schema") != "codex_fleet_assets.v1":
        raise FleetError("fleet asset catalog is invalid")
    if not isinstance(payload.get("nodes"), list):
        raise FleetError("fleet asset nodes are invalid")
    return payload
