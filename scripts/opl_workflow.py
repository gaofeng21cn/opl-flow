#!/usr/bin/env python3
"""Small OPL entry for Beads-backed ledger setup and reconciliation."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


PROGRAM_REF = "opl://program/operations-maintenance"
REGISTRY_SECTIONS = (
    ("services", "service"),
    ("domains", "domain"),
    ("platform_accounts", "platform-account"),
)
REVIEW_MODES = ("off", "async-risk", "required")
REVIEW_STATES = ("available", "unavailable", "failed")


class WorkflowError(RuntimeError):
    pass


def review_policy() -> dict[str, Any]:
    path = flow_root() / "contracts" / "code-review-policy.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read code review policy: {path}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "opl_flow_code_review_policy.v1"
        or set(payload.get("modes", {})) != set(REVIEW_MODES)
    ):
        raise WorkflowError("code review policy is invalid")
    return payload


def review_config_path(value: Path | None = None) -> Path:
    configured = value or os.environ.get("OPL_FLOW_REVIEW_CONFIG")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".config" / "opl-flow" / "code-review.json"


def review_status(config: Path | None = None) -> dict[str, Any]:
    policy = review_policy()
    path = review_config_path(config)
    configured = path.is_file()
    if configured:
        try:
            local = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError(f"cannot read code review config: {path}") from exc
        if not isinstance(local, dict):
            raise WorkflowError(f"code review config is invalid: {path}")
        mode = local.get("mode")
        if local.get("schema") != "opl_flow_code_review_config.v1" or mode not in REVIEW_MODES:
            raise WorkflowError(f"code review config is invalid: {path}")
    else:
        mode = policy["default_mode"]
    return {
        "schema": "opl_flow_code_review_status.v1",
        "configured": configured,
        "config": str(path),
        "mode": mode,
        "source": "user" if configured else "policy_default",
        **policy["delivery"],
    }


def configure_review(mode: str, config: Path | None = None) -> dict[str, Any]:
    policy = review_policy()
    if mode not in policy["modes"]:
        raise WorkflowError(f"unsupported code review mode: {mode}")
    path = review_config_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload = {
        "schema": "opl_flow_code_review_config.v1",
        "mode": mode,
    }
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            os.chmod(temp_path, 0o600)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise WorkflowError(f"cannot write code review config: {path}") from exc
    return review_status(path)


def assess_review(
    risk: str,
    config: Path | None = None,
    *,
    explicit_required: bool = False,
    repository_required: bool = False,
    review_state: str = "available",
) -> dict[str, Any]:
    status = review_status(config)
    mode = status["mode"]
    if explicit_required:
        action, blocked, reason = "blocking", True, "explicit_user_requirement"
    elif repository_required:
        action, blocked, reason = "blocking", True, "repository_policy"
    elif mode == "required":
        action, blocked, reason = "blocking", True, "required_mode"
    elif mode == "off":
        action, blocked, reason = "skip", False, "mode_off"
    elif risk == "low":
        action, blocked, reason = "skip", False, "low_risk"
    elif review_state == "available":
        action, blocked, reason = "async", False, f"{risk}_risk_async"
    else:
        action, blocked, reason = "skip", False, f"review_{review_state}_nonblocking"
    return {
        "schema": "opl_flow_code_review_assessment.v1",
        "mode": mode,
        "risk": risk,
        "review_state": review_state,
        "review_action": action,
        "delivery_blocked": blocked,
        "pr_required_by_flow": False,
        "baseline_gates": status["baseline_gates"],
        "linear_cloud_coding_sessions": False,
        "reason": reason,
    }


def flow_root() -> Path:
    return Path(__file__).resolve().parents[1]


def profile_owner():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if __package__:
            from scripts import install_local_plugin
        else:
            import install_local_plugin
    finally:
        sys.dont_write_bytecode = previous

    return install_local_plugin


def executable(name: str, explicit: str | None = None, env: str | None = None) -> str:
    candidate = explicit or (os.environ.get(env) if env else None) or shutil.which(name)
    if not candidate:
        raise WorkflowError(f"owner CLI is unavailable: {name}")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise WorkflowError(f"owner CLI is not executable: {path}")
    return str(path)


def cli_probe(
    name: str,
    cwd: Path,
    explicit: str | None = None,
    *,
    version_args: tuple[str, ...] = ("--version",),
) -> dict[str, Any]:
    try:
        command = executable(name, explicit)
        result = run([command, *version_args], cwd)
        assert isinstance(result, subprocess.CompletedProcess)
        version = (result.stdout or result.stderr).strip()
        resolved = shutil.which(command) or command
        return {
            "available": True,
            "path": str(Path(resolved).resolve()),
            "version": version,
        }
    except WorkflowError as exc:
        return {"available": False, "error": str(exc)}


def github_probe(cwd: Path, explicit: str | None = None) -> dict[str, Any]:
    tool = cli_probe("gh", cwd, explicit)
    if not tool["available"]:
        return tool
    auth = run(
        [str(tool["path"]), "auth", "status", "--hostname", "github.com"],
        cwd,
        check=False,
    )
    assert isinstance(auth, subprocess.CompletedProcess)
    tool["authenticated"] = auth.returncode == 0
    return tool


def profile_action(
    action: str,
    codex_home: Path,
    *,
    packet: Path | None = None,
) -> dict[str, Any]:
    owner = profile_owner()
    try:
        if action == "status":
            result = owner.verify_profile(flow_root(), codex_home, True)
        elif action == "prepare":
            result = owner.install_profile(flow_root(), codex_home)
        elif action == "apply":
            if packet is None:
                raise WorkflowError("profile apply requires --packet")
            result = owner.apply_merge_packet(flow_root(), codex_home, packet)
        else:
            raise WorkflowError(f"unsupported profile action: {action}")
    except (OSError, ValueError) as exc:
        raise WorkflowError(str(exc)) from exc
    return {
        "schema": "opl_flow_profile_action.v1",
        "action": action,
        "codex_home": str(codex_home),
        **result,
    }


def run(
    argv: list[str],
    cwd: Path,
    *,
    check: bool = True,
    json_output: bool = False,
) -> subprocess.CompletedProcess[str] | Any:
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode:
        raise WorkflowError((result.stderr or result.stdout).strip())
    if not json_output:
        return result
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"{argv[0]} returned invalid JSON") from exc


def instance_root(value: str | Path | None, *, required: bool = True) -> Path | None:
    configured = value or os.environ.get("OPL_INSTANCE")
    if not configured:
        if required:
            raise WorkflowError("pass --instance or set OPL_INSTANCE")
        return None
    root = Path(configured).expanduser().resolve()
    if not root.is_dir():
        raise WorkflowError(f"OPL Instance does not exist: {root}")
    return root


def fleet_command(instance: Path | None, explicit: str | None) -> tuple[list[str], str]:
    bundled = flow_root() / "scripts" / "opl_fleet.py"
    if instance and (instance / "fleet/fleet.json").is_file() and (
        instance / "fleet/nodes.json"
    ).is_file():
        return (
            [sys.executable, str(bundled), "--instance", str(instance)],
            "opl-flow",
        )
    fleet = executable("codex-fleet", explicit, "OPL_FLEET_BIN")
    return ([fleet], "codex-fleet-compatibility")


def ledger_probe(root: Path, bd: str) -> dict[str, Any] | None:
    result = run([bd, "status", "--no-activity", "--json"], root, check=False)
    assert isinstance(result, subprocess.CompletedProcess)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if "no beads project found" in detail.lower():
            return None
        raise WorkflowError(f"bd status failed: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError("bd status returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise WorkflowError("bd status returned an invalid payload")
    return payload


def linear_probe(root: Path, bd: str) -> dict[str, Any]:
    result = run([bd, "linear", "status", "--json"], root, check=False)
    assert isinstance(result, subprocess.CompletedProcess)
    if result.returncode:
        return {"state": "error", "error": (result.stderr or result.stdout).strip()}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"state": "error", "error": "bd linear status returned invalid JSON"}
    if not isinstance(payload, dict):
        return {"state": "error", "error": "bd linear status returned an invalid payload"}
    allowed = (
        "auth_mode",
        "configured",
        "has_api_key",
        "has_oauth",
        "last_sync",
        "pending_push",
        "team_id",
        "team_ids",
        "total_issues",
        "with_linear_ref",
    )
    return {"state": "current", **{key: payload.get(key) for key in allowed}}


def secure_ledger_dir(root: Path) -> None:
    try:
        os.chmod(root / ".beads", 0o700)
    except OSError as exc:
        raise WorkflowError(f"cannot secure {root / '.beads'}: {exc}") from exc


def init_ledger(root: Path, bd: str, prefix: str) -> dict[str, str]:
    if ledger_probe(root, bd) is not None:
        secure_ledger_dir(root)
        return {"state": "already_initialized", "instance": str(root)}
    git_dir = str(run(["git", "rev-parse", "--git-dir"], root).stdout).strip()
    common_dir = str(run(["git", "rev-parse", "--git-common-dir"], root).stdout).strip()

    def git_path(value: str) -> Path:
        path = Path(value)
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    if git_path(git_dir) != git_path(common_dir):
        raise WorkflowError("first bd init requires a primary checkout or standalone clone")
    if str(run(["git", "status", "--porcelain", "--untracked-files=all"], root).stdout).strip():
        raise WorkflowError("bd init creates a commit and requires a clean Git checkout")
    run(
        [
            bd,
            "init",
            "--prefix",
            prefix,
            "--skip-agents",
            "--skip-hooks",
            "--non-interactive",
        ],
        root,
    )
    if ledger_probe(root, bd) is None:
        raise WorkflowError("bd init completed without a readable ledger")
    secure_ledger_dir(root)
    return {"state": "initialized", "instance": str(root), "prefix": prefix}


def registry_items(registry_path: Path) -> Iterable[dict[str, str]]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read Operations Registry: {registry_path}") from exc
    if not isinstance(registry, dict) or registry.get("schema") != "opl_operations_registry.v1":
        raise WorkflowError("Operations Registry must use opl_operations_registry.v1")
    for section, kind in REGISTRY_SECTIONS:
        entries = registry.get(section, [])
        if not isinstance(entries, list):
            raise WorkflowError(f"Operations Registry {section} must be an array")
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise WorkflowError(f"Operations Registry {section} entry lacks id")
            maintenance = entry.get("maintenance")
            if maintenance is None:
                continue
            if not isinstance(maintenance, dict):
                raise WorkflowError(f"Operations Registry {section} entry has invalid maintenance")
            review_on = maintenance.get("next_review_on")
            if review_on is None:
                continue
            if not isinstance(review_on, str):
                raise WorkflowError(f"Operations Registry {section} entry has invalid next_review_on")
            asset_id = entry["id"]
            yield {
                "asset_id": asset_id,
                "kind": kind,
                "display": str(entry.get("name") or entry.get("fqdn") or entry.get("provider") or asset_id),
                "review_on": review_on,
                "action": str(maintenance.get("action_zh") or "按 owner 路径核对状态并更新复核日期。"),
            }


def create_bead(
    root: Path,
    bd: str,
    *,
    title: str,
    issue_type: str,
    external_ref: str,
    labels: str,
    description: str,
    metadata: dict[str, str],
    due: str | None = None,
    parent: str | None = None,
) -> dict[str, Any]:
    argv = [
        bd,
        "create",
        title,
        "--type",
        issue_type,
        "--priority",
        "P2",
        "--external-ref",
        external_ref,
        "--labels",
        labels,
        "--description",
        description,
        "--metadata",
        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    ]
    if due:
        argv += ["--defer", due, "--due", due]
    if parent:
        argv += ["--parent", parent]
    payload = run([*argv, "--json"], root, json_output=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise WorkflowError("bd create returned an invalid payload")
    return payload


def reconcile_operations(
    root: Path,
    bd: str,
    registry_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    registry = (registry_path or root / "operations" / "registry.json").expanduser().resolve()
    items = list(registry_items(registry))
    if not items:
        return {
            "schema": "opl_flow_operations_reconcile.v1",
            "instance": str(root),
            "registry": str(registry),
            "dry_run": dry_run,
            "created": [],
            "unchanged": [],
            "counts": {
                "scheduled_assets": 0,
                "created": 0,
                "unchanged": 0,
            },
        }
    listed = run([bd, "list", "--all", "--limit", "0", "--json"], root, json_output=True)
    if not isinstance(listed, list):
        raise WorkflowError("bd list returned an invalid payload")
    existing = {
        item["external_ref"]: item
        for item in listed
        if isinstance(item, dict) and isinstance(item.get("external_ref"), str)
    }
    created: list[dict[str, str]] = []
    unchanged: list[dict[str, str]] = []
    program = existing.get(PROGRAM_REF)
    program_id = str(program["id"]) if program else None
    if program and program.get("status") == "open" and not dry_run:
        run([bd, "update", program_id, "--status", "in_progress", "--json"], root)
    if not program_id:
        created.append({"kind": "program", "external_ref": PROGRAM_REF})
        if not dry_run:
            program = create_bead(
                root,
                bd,
                title="OPL Operations maintenance",
                issue_type="epic",
                external_ref=PROGRAM_REF,
                labels="opl,operations",
                description="Operations Registry 到期复核的持久总账；凭据和 live state 仍由各 owner 管理。",
                metadata={"source": "operations/registry.json"},
            )
            program_id = str(program["id"])
            run([bd, "update", program_id, "--status", "in_progress", "--json"], root)

    for item in items:
        external_ref = f"opl://operations/{item['kind']}/{item['asset_id']}/review/{item['review_on']}"
        summary = {key: item[key] for key in ("kind", "asset_id", "review_on")}
        summary["external_ref"] = external_ref
        if external_ref in existing:
            unchanged.append(summary)
            continue
        created.append(summary)
        if not dry_run:
            create_bead(
                root,
                bd,
                title=f"复核运维资产：{item['display']}",
                issue_type="task",
                external_ref=external_ref,
                labels=f"opl,operations-review,{item['kind']}",
                description=(
                    f"资产：{item['kind']}/{item['asset_id']}\n"
                    f"计划日期：{item['review_on']}\n维护动作：{item['action']}\n"
                    "完成后更新 Registry 的 verified_on/next_review_on；不得记录 secret。"
                ),
                metadata={
                    "asset_id": item["asset_id"],
                    "asset_kind": item["kind"],
                    "source": "operations/registry.json",
                },
                due=item["review_on"],
                parent=program_id,
            )
    return {
        "schema": "opl_flow_operations_reconcile.v1",
        "instance": str(root),
        "registry": str(registry),
        "dry_run": dry_run,
        "created": created,
        "unchanged": unchanged,
        "counts": {
            "scheduled_assets": len(items),
            "created": len(created),
            "unchanged": len(unchanged),
        },
    }


def workflow_status(
    instance: Path | None,
    bd_arg: str | None,
    fleet_arg: str | None,
    *,
    git_arg: str | None = None,
    gh_arg: str | None = None,
    codex_arg: str | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema": "opl_flow_workflow_status.v1", "instance": str(instance) if instance else None}
    cwd = instance or Path.cwd()
    payload["git"] = cli_probe("git", cwd, git_arg)
    payload["github"] = github_probe(cwd, gh_arg)
    payload["codex"] = cli_probe("codex", cwd, codex_arg)
    try:
        payload["profile"] = profile_action(
            "status",
            (codex_home or Path.home() / ".codex").expanduser().resolve(),
        )
    except WorkflowError as exc:
        payload["profile"] = {"status": "error", "error": str(exc)}
    try:
        payload["code_review"] = review_status()
    except WorkflowError as exc:
        payload["code_review"] = {"status": "error", "error": str(exc)}
    try:
        bd = executable("bd", bd_arg)
        version = run([bd, "version"], cwd)
        assert isinstance(version, subprocess.CompletedProcess)
        payload["beads"] = {"available": True, "path": str(Path(bd).resolve()), "version": version.stdout.strip()}
    except WorkflowError as exc:
        payload["beads"] = {"available": False, "error": str(exc)}
        payload["ledger"] = {"state": "unknown" if instance else "not_configured"}
        payload["linear"] = {"state": "unknown" if instance else "not_configured"}
    else:
        try:
            payload["ledger"] = ledger_probe(instance, bd) if instance else {"state": "not_configured"}
        except WorkflowError as exc:
            payload["ledger"] = {"state": "error", "error": str(exc)}
        payload["linear"] = linear_probe(instance, bd) if instance else {"state": "not_configured"}
    try:
        fleet, owner = fleet_command(instance, fleet_arg)
        executable_path = Path(fleet[1] if fleet[0] == sys.executable else fleet[0])
        payload["fleet"] = {
            "available": True,
            "path": str(executable_path.resolve()),
            "owner": owner,
        }
    except WorkflowError as exc:
        payload["fleet"] = {
            "available": False,
            "error": str(exc),
            "owner": "opl-flow",
        }
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--instance")
    status.add_argument("--bd-bin")
    status.add_argument("--fleet-bin")
    status.add_argument("--git-bin")
    status.add_argument("--gh-bin")
    status.add_argument("--codex-bin")
    status.add_argument("--codex-home", type=Path)
    profile = commands.add_parser("profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    for name in ("status", "prepare"):
        command = profile_commands.add_parser(name)
        command.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    apply_profile = profile_commands.add_parser("apply")
    apply_profile.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    apply_profile.add_argument("--packet", required=True, type=Path)
    review = commands.add_parser("review")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    review_status_command = review_commands.add_parser("status")
    review_status_command.add_argument("--config", type=Path)
    configure = review_commands.add_parser("configure")
    configure.add_argument("--mode", choices=REVIEW_MODES, required=True)
    configure.add_argument("--config", type=Path)
    assess = review_commands.add_parser("assess")
    assess.add_argument("--risk", choices=("low", "medium", "high"), required=True)
    assess.add_argument("--config", type=Path)
    assess.add_argument("--explicit-required", action="store_true")
    assess.add_argument("--repository-required", action="store_true")
    assess.add_argument("--review-state", choices=REVIEW_STATES, default="available")
    ledger = commands.add_parser("ledger")
    ledger_commands = ledger.add_subparsers(dest="ledger_command", required=True)
    init = ledger_commands.add_parser("init")
    init.add_argument("--instance", required=True)
    init.add_argument("--prefix", default="opl")
    init.add_argument("--bd-bin")
    reconcile = ledger_commands.add_parser("reconcile-operations")
    reconcile.add_argument("--instance")
    reconcile.add_argument("--registry", type=Path)
    reconcile.add_argument("--dry-run", action="store_true")
    reconcile.add_argument("--bd-bin")
    fleet = commands.add_parser("fleet", add_help=False)
    fleet.add_argument("--instance")
    fleet.add_argument("--fleet-bin")
    fleet.add_argument("fleet_args", nargs=argparse.REMAINDER)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            print(
                json.dumps(
                    workflow_status(
                        instance_root(args.instance, required=False),
                        args.bd_bin,
                        args.fleet_bin,
                        git_arg=args.git_bin,
                        gh_arg=args.gh_bin,
                        codex_arg=args.codex_bin,
                        codex_home=args.codex_home,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "profile":
            result = profile_action(
                args.profile_command,
                args.codex_home.expanduser().resolve(),
                packet=getattr(args, "packet", None),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 2 if result.get("status") == "requires_codex_semantic_merge" else 0
        if args.command == "review":
            if args.review_command == "configure":
                result = configure_review(args.mode, args.config)
            elif args.review_command == "assess":
                result = assess_review(
                    args.risk,
                    args.config,
                    explicit_required=args.explicit_required,
                    repository_required=args.repository_required,
                    review_state=args.review_state,
                )
            else:
                result = review_status(args.config)
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "fleet":
            instance = instance_root(args.instance, required=False)
            fleet, _ = fleet_command(instance, args.fleet_bin)
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            return subprocess.run(
                [*fleet, *(args.fleet_args or ["status"])],
                check=False,
                env=environment,
            ).returncode
        root = instance_root(args.instance)
        assert root is not None
        bd = executable("bd", args.bd_bin)
        result = (
            init_ledger(root, bd, args.prefix)
            if args.ledger_command == "init"
            else reconcile_operations(root, bd, args.registry, dry_run=args.dry_run)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
