"""OPL Fleet CLI argument parsing and command dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal
import argparse
import datetime as dt
import json
import re
import sys
import typer
from fleet_inventory import collect_inventory
from .fleet_common import FleetError, GPU_APIS, configure_instance, install_fleet_command, node_identity, normalize_node_id, parse_requirements, run, utc_now, write_instance_pointer
from .fleet_control import control_commit, manifest, node_registry
from .fleet_reconcile import fetch_state_file, fleet_repositories, join, reconcile, record_receipt, remote_asset_catalog
from .fleet_lease import acquire_lease_record, active_lease_map, lease_lock, public_lease, read_lease_store, reap_expired_leases, release_lease_record, renew_lease_record, select_nodes, write_lease_store
from .fleet_runner import assert_lease_admission, assert_runner_role_node, assert_runner_role_workload, build_admission_receipt, controller_guard, doctor_result, fleet_runner_renew, fleet_runner_start, fleet_runner_status, fleet_runner_stop, verify_lease_record
from .fleet_dispatch import dispatch_adapter_from_args, fleet_dispatch_acquire, fleet_dispatch_execute, fleet_dispatch_plan, fleet_dispatch_release, fleet_dispatch_verify, run_data_job, validate_execution_argv
from .fleet_attempts import check_stale_attempts, get_attempt, heartbeat_attempt, list_attempts, observe_attempts, plan_preemption, suspend_attempt
from .fleet_queue import plan_queue
from .fleet_adapter import dispatch_complete, dispatch_group_plan, dispatch_group_run, dispatch_group_status, dispatch_run

try:
    from .. import opl_events
except ImportError:  # Direct script execution.
    import opl_events
from .fleet_workspace import workspace_command
from .fleet_workflow import workflow_command, workflow_status, set_flagship

def fleet_status() -> int:
    spec = manifest()
    result = run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw+json",
            f"repos/{spec['repository']}/contents/STATUS.md?ref=state",
        ],
        check=False,
    )
    if result.returncode:
        print("No fleet receipts have been published yet.")
        return 1
    print(result.stdout.rstrip())
    try:
        controller_guard()
    except FleetError:
        return 0
    observed = utc_now()
    with lease_lock(exclusive=False):
        store = read_lease_store()
    print("\n## Controller Lease Authority\n")
    print("| Node | State | Workload | Priority | Owner Task | Expires (UTC) |")
    print("| --- | --- | --- | ---: | --- | --- |")
    for node_id in sorted(store["leases"]):
        lease = public_lease(store["leases"][node_id], now=observed)
        print(
            f"| {node_id} | {lease['state']} | {lease['workload_class']} "
            f"| {lease['priority']} | {lease['owner_task']} | {lease['expires_at']} |"
        )
    if not store["leases"]:
        print("| - | available | - | - | - | - |")
    return 0

def fleet_assets() -> int:
    print(fetch_state_file("ASSETS.md").rstrip())
    return 0

def fleet_nodes(*, json_output: bool) -> int:
    catalog = remote_asset_catalog()
    if json_output:
        # Data-job consumers need the controller identity to separate the
        # local aggregate owner from remote projection candidates.
        print(json.dumps({**catalog, "controller": controller_guard()}, indent=2, sort_keys=True))
        return 0
    print("NODE\tAPPROVED\tSTATE\tPLATFORM\tINVENTORY")
    for entry in catalog["nodes"]:
        policy = entry.get("policy") or {}
        receipt = entry.get("receipt") or {}
        inventory = entry.get("inventory") or {}
        execution = inventory.get("execution") or {}
        print(
            f"{entry.get('node_id')}\t"
            f"{'yes' if policy.get('approved') else 'no'}\t"
            f"{receipt.get('state', 'NO_RECEIPT')}\t"
            f"{execution.get('kind', '-')}/{execution.get('architecture', '-')}\t"
            f"{inventory.get('observed_at', 'PENDING')}"
        )
    return 0

def fleet_select(args: argparse.Namespace) -> int:
    if args.min_memory_gb < 0:
        raise FleetError("minimum memory must not be negative")
    required = {
        item.strip()
        for item in str(args.requires or "").split(",")
        if item.strip()
    }
    if any(not re.fullmatch(r"[a-z0-9-]{1,40}", item) for item in required):
        raise FleetError("select requirements are invalid")
    if args.gpu_api not in GPU_APIS or args.min_gpu_memory_gb < 0:
        raise FleetError("select GPU requirements are invalid")
    max_age = int((manifest().get("inventory") or {}).get("max_age_hours", 36))
    selected = select_nodes(
        remote_asset_catalog(),
        required=required,
        min_memory_gb=args.min_memory_gb,
        gpu_api=args.gpu_api,
        min_gpu_memory_gb=args.min_gpu_memory_gb,
        gpu_model=args.gpu_model,
        max_age_hours=max_age,
        leases=active_lease_map(),
    )
    result = {
        "schema": "codex_fleet_selection.v1",
        "scope": "catalog-plus-controller-lease-live-doctor-on-acquire",
        "requires": sorted(required),
        "min_memory_gb": args.min_memory_gb,
        "gpu_api": args.gpu_api,
        "min_gpu_memory_gb": args.min_gpu_memory_gb,
        "gpu_model": args.gpu_model,
        "nodes": selected,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if selected else 1

def fleet_doctor(node_id: str) -> int:
    result = doctor_result(node_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready_for_dispatch"] else 1

def fleet_data_job_run(args: argparse.Namespace) -> int:
    stdin_text = None
    if args.stdin_file:
        stdin_text = args.stdin_file.read_text(encoding="utf-8")
    payload = run_data_job(
        args.node_id,
        argv=validate_execution_argv(args.argv_json),
        stdin_text=stdin_text,
        cwd=args.cwd,
        timeout_seconds=args.timeout_seconds,
        artifact_path=args.artifact_path,
        artifact_destination=args.artifact_destination,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "completed" else 2 if payload["status"] == "skipped" else 1

def fleet_lease_show(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    with lease_lock(exclusive=False):
        store = read_lease_store()
    leases = store["leases"]
    if args.node_id:
        node_id = normalize_node_id(args.node_id)
        selected = [leases[node_id]] if node_id in leases else []
    else:
        selected = [leases[node_id] for node_id in sorted(leases)]
    result = {
        "schema": "codex_fleet_lease_readback.v2",
        "controller": node_identity(),
        "observed_at": observed.astimezone(dt.timezone.utc).isoformat(),
        "generation": store["generation"],
        "leases": [public_lease(lease, now=observed) for lease in selected],
        "audit": store["audit"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def fleet_lease_acquire(args: argparse.Namespace) -> int:
    controller_guard()
    required = parse_requirements(args.requires)
    registry = node_registry()
    role = (
        assert_runner_role_node(args.role, args.node_id, registry=registry)
        if args.role
        else None
    )
    if role:
        assert_runner_role_workload(
            role,
            args.workload_class,
            registry=registry,
        )
    doctor = doctor_result(args.node_id)
    assert_lease_admission(
        doctor,
        required=required,
        min_memory_gb=args.min_memory_gb,
    )
    admission = build_admission_receipt(
        doctor,
        required=required,
        min_memory_gb=args.min_memory_gb,
    )
    revision = control_commit()
    lease = acquire_lease_record(
        node_id=args.node_id,
        owner_task=args.owner_task,
        owner_thread=args.owner_thread,
        owner_run=args.owner_run,
        role=role,
        workload_class=args.workload_class,
        priority=args.priority,
        preemptible=args.preemptible,
        phase=args.phase,
        ttl_seconds=args.ttl_seconds,
        control_revision=revision,
        admission=admission,
        preempt_lease_id=args.preempt_lease_id,
        preempt_generation=args.preempt_generation,
        preempt_nonce=args.preempt_nonce,
    )
    result = {
        "schema": "codex_fleet_lease_transaction.v2",
        "action": "acquire",
        "controller": node_identity(),
        "lease": lease,
        "admission": admission,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def fleet_lease_verify(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    node_id = normalize_node_id(args.node_id)
    with lease_lock(exclusive=False):
        store = read_lease_store()
    lease = store["leases"].get(node_id)
    if not lease:
        raise FleetError(f"node has no active lease: {node_id}")
    result = verify_lease_record(
        lease,
        node_id=node_id,
        role=args.expect_role,
        lease_id=args.expect_lease_id,
        generation=args.expect_generation,
        owner_task=args.expect_owner_task,
        owner_thread=args.expect_owner_thread,
        owner_run=args.expect_owner_run,
        workload_class=args.expect_workload_class,
        phase=args.expect_phase,
        preemptible=args.expect_preemptible == "true",
        min_ttl_seconds=args.min_ttl_seconds,
        required=parse_requirements(args.expect_requires),
        min_memory_gb=args.expect_min_memory_gb,
        max_admission_age_seconds=args.max_admission_age_seconds,
        expected_control_commit=args.expect_control_commit,
        current_control_commit=control_commit(),
        registry=node_registry(),
        now=observed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def fleet_lease_renew(args: argparse.Namespace) -> int:
    controller_guard()
    lease = renew_lease_record(
        node_id=args.node_id,
        lease_id=args.lease_id,
        generation=args.generation,
        nonce=args.nonce,
        owner_task=args.owner_task,
        ttl_seconds=args.ttl_seconds,
        phase=args.phase,
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "renew",
                "controller": node_identity(),
                "lease": lease,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def fleet_lease_release(args: argparse.Namespace) -> int:
    controller_guard()
    lease = release_lease_record(
        node_id=args.node_id,
        lease_id=args.lease_id,
        generation=args.generation,
        nonce=args.nonce,
        owner_task=args.owner_task,
    )
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "release",
                "controller": node_identity(),
                "released": public_lease(lease, now=utc_now()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def fleet_lease_reap(args: argparse.Namespace) -> int:
    controller_guard()
    observed = utc_now()
    node_id = normalize_node_id(args.node_id) if args.node_id else None
    with lease_lock(exclusive=True):
        store = read_lease_store()
        reaped = reap_expired_leases(store, now=observed, node_id=node_id)
        if reaped:
            store["generation"] += 1
            write_lease_store(store)
    print(
        json.dumps(
            {
                "schema": "codex_fleet_lease_transaction.v2",
                "action": "reap",
                "controller": node_identity(),
                "reaped": [public_lease(lease, now=observed) for lease in reaped],
                "generation": store["generation"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

AdapterChoice = Literal["github-runner", "lease-only", "local-codex", "remote-codex", "ssh-session"]
GpuApiChoice = Literal["any", "cuda", "metal"]
WorkloadChoice = Literal["background", "experiment", "foreground", "guest", "job", "p0-release", "vm"]
PhaseChoice = Literal["interruptible", "non-interruptible"]
SandboxChoice = Literal["read-only", "workspace-write", "danger-full-access"]
DispatchModeChoice = Literal["execute", "envelope"]
BoolStrChoice = Literal["true", "false"]

ReqStr = Annotated[str, typer.Option()]
ReqInt = Annotated[int, typer.Option()]
ReqPath = Annotated[Path, typer.Option()]
OptPreempt = Annotated[bool | None, typer.Option("--preemptible/--no-preemptible")]


def _typer(help_text: str | None = None) -> typer.Typer:
    return typer.Typer(help=help_text, rich_markup_mode=None, add_completion=False, no_args_is_help=True)


cli_app = _typer("OPL Fleet engine backed by one private OPL Instance.")
flagship_app = _typer("inspect or explicitly switch the workflow authoring node")
workflow_app = _typer("inspect or receive the reviewed workflow Profile")
repos_app = _typer()
workspace_app = _typer("validate, materialize, synchronize, or admit a declared workspace")
data_job_app = _typer("run a lightweight structured task without reserving compute capacity")
dispatch_app = _typer("plan, lease, verify, execute, or release task capacity")
dispatch_group_app = _typer("plan, execute, or inspect fan-out/fan-in dispatch groups")
attempt_app = _typer("manage and observe sanitized execution attempts")
queue_app = _typer("priority queueing and backpressure planning")
runner_app = _typer()
lease_app = _typer()

dispatch_app.add_typer(dispatch_group_app, name="group")
for _name, _sub in (
    ("flagship", flagship_app), ("workflow", workflow_app), ("repos", repos_app),
    ("workspace", workspace_app), ("data-job", data_job_app), ("dispatch", dispatch_app),
    ("attempt", attempt_app), ("queue", queue_app), ("runner", runner_app), ("lease", lease_app),
):
    cli_app.add_typer(_sub, name=_name)


def _ns(ctx: typer.Context, action: str, **extra: Any) -> argparse.Namespace:
    params = dict(ctx.params)
    if "json_output" in params:
        params["json"] = params.pop("json_output")
    return argparse.Namespace(instance=(ctx.obj or {}).get("instance"), action=action, **params, **extra)


@cli_app.callback()
def _cli_root(ctx: typer.Context, instance: str | None = None) -> None:
    ctx.obj = {"instance": instance}


@cli_app.command("join")
def _cmd_join(ctx: typer.Context, node_id: str | None = None, no_schedule: Annotated[bool, typer.Option("--no-schedule")] = False) -> argparse.Namespace:
    return _ns(ctx, "join")


@cli_app.command("reconcile")
def _cmd_reconcile(
    ctx: typer.Context,
    report: Annotated[bool, typer.Option("--report")] = False,
    install_required: Annotated[bool, typer.Option("--install-required/--no-install-required", help="install missing required components from their declared owners (default)")] = True,
) -> argparse.Namespace:
    return _ns(ctx, "reconcile")


@cli_app.command("status")
def _cmd_status(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "status")


@cli_app.command("assets")
def _cmd_assets(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "assets")


@flagship_app.command("status")
def _cmd_flagship_status(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "flagship", flagship_action="status")


@flagship_app.command("set")
def _cmd_flagship_set(ctx: typer.Context, node_id: str, expected_current: Annotated[str, typer.Option(help="current node ID, or none for initial selection")]) -> argparse.Namespace:
    return _ns(ctx, "flagship", flagship_action="set")


@workflow_app.command("status")
def _cmd_workflow_status(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "workflow", workflow_action="status")


@workflow_app.command("sync")
def _cmd_workflow_sync(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "workflow", workflow_action="sync")


@workflow_app.command("record-projection", help="record completed semantic review after Flow main publication")
def _cmd_workflow_projection(
    ctx: typer.Context,
    flow_commit: ReqStr,
    source_sha256: Annotated[str, typer.Option(help="exact flagship AGENTS.md hash reviewed by the authoring task")],
) -> argparse.Namespace:
    return _ns(ctx, "workflow", workflow_action="record-projection")


@repos_app.command("status")
def _cmd_repos_status(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "repos", repos_action="status")


@repos_app.command("sync")
def _cmd_repos_sync(ctx: typer.Context) -> argparse.Namespace:
    return _ns(ctx, "repos", repos_action="sync")


def _register_workspace_action(name: str) -> None:
    @workspace_app.command(name)
    def _cmd(ctx: typer.Context, profile: ReqStr) -> argparse.Namespace:
        return _ns(ctx, "workspace", workspace_action=name)


for _ws_action in ("validate", "plan", "status", "bootstrap", "sync", "claim-check"):
    _register_workspace_action(_ws_action)


@cli_app.command("nodes")
def _cmd_nodes(ctx: typer.Context, json_output: Annotated[bool, typer.Option("--json")] = False) -> argparse.Namespace:
    return _ns(ctx, "nodes")


@cli_app.command("inventory")
def _cmd_inventory(ctx: typer.Context, json_output: Annotated[bool, typer.Option("--json")] = False) -> argparse.Namespace:
    return _ns(ctx, "inventory")


@cli_app.command("doctor")
def _cmd_doctor(ctx: typer.Context, node_id: str) -> argparse.Namespace:
    return _ns(ctx, "doctor")


@data_job_app.command("run")
def _cmd_data_job_run(
    ctx: typer.Context, node_id: str, argv_json: ReqStr, stdin_file: Path | None = None,
    cwd: str | None = None, timeout_seconds: int = 900, artifact_path: str | None = None,
    artifact_destination: Path | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "data-job", data_job_action="run")


@cli_app.command("select")
def _cmd_select(
    ctx: typer.Context, requires: str = "", min_memory_gb: int = 0,
    gpu_api: GpuApiChoice = "any", min_gpu_memory_gb: int = 0, gpu_model: str | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "select")


@dispatch_app.command("plan")
def _cmd_dispatch_plan(
    ctx: typer.Context, requirements_json: str | None = None,
    handoff_json: Annotated[str | None, typer.Option(help="carrier-neutral Worker handoff JSON or @file")] = None,
    adapter: AdapterChoice | None = None, node_id: str | None = None, role: str | None = None,
    requires: str | None = None, min_memory_gb: int | None = None, gpu_api: GpuApiChoice | None = None,
    min_gpu_memory_gb: int | None = None, gpu_model: str | None = None, workload_class: WorkloadChoice | None = None,
    priority: int | None = None, preemptible: OptPreempt = None, phase: PhaseChoice | None = None,
    ttl_seconds: int | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="plan")


@dispatch_app.command("acquire")
def _cmd_dispatch_acquire(
    ctx: typer.Context, owner_task: ReqStr, requirements_json: str | None = None,
    handoff_json: Annotated[str | None, typer.Option(help="carrier-neutral Worker handoff JSON or @file")] = None,
    adapter: AdapterChoice | None = None, node_id: str | None = None, role: str | None = None,
    requires: str | None = None, min_memory_gb: int | None = None, gpu_api: GpuApiChoice | None = None,
    min_gpu_memory_gb: int | None = None, gpu_model: str | None = None, workload_class: WorkloadChoice | None = None,
    priority: int | None = None, preemptible: OptPreempt = None, phase: PhaseChoice | None = None,
    ttl_seconds: int | None = None, owner_thread: str | None = None, owner_run: str | None = None,
    preempt_lease_id: str | None = None, preempt_generation: int | None = None, preempt_nonce: str | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="acquire")


@dispatch_app.command("verify")
def _cmd_dispatch_verify(ctx: typer.Context, dispatch_id: str, min_ttl_seconds: int = 300, max_admission_age_seconds: int = 300) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="verify")


@dispatch_app.command("execute", help="execute only an ssh-session lease; native Codex tasks use the app")
def _cmd_dispatch_execute(
    ctx: typer.Context, dispatch_id: str, owner_task: ReqStr, argv_json: ReqStr,
    owner_thread: str | None = None, owner_run: str | None = None, handoff_json: str | None = None,
    cwd: str | None = None, timeout_seconds: int = 900, min_ttl_seconds: int = 60, max_admission_age_seconds: int = 300,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="execute")


@dispatch_app.command("release")
def _cmd_dispatch_release(ctx: typer.Context, dispatch_id: str, owner_task: ReqStr) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="release")


@dispatch_app.command("run", help="run unified single-transaction dispatch across adapters")
def _cmd_dispatch_run(
    ctx: typer.Context, owner_task: ReqStr, requirements_json: str | None = None,
    handoff_json: Annotated[str | None, typer.Option(help="carrier-neutral Worker handoff JSON or @file")] = None,
    adapter: AdapterChoice | None = None, node_id: str | None = None, role: str | None = None,
    requires: str | None = None, min_memory_gb: int | None = None, gpu_api: GpuApiChoice | None = None,
    min_gpu_memory_gb: int | None = None, gpu_model: str | None = None, workload_class: WorkloadChoice | None = None,
    priority: int | None = None, preemptible: OptPreempt = None, phase: PhaseChoice | None = None,
    ttl_seconds: int | None = None, owner_thread: str | None = None, owner_run: str | None = None,
    preempt_lease_id: str | None = None, preempt_generation: int | None = None, preempt_nonce: str | None = None,
    argv_json: str | None = None, executor_cmd_json: str | None = None, mode: DispatchModeChoice = "execute",
    cwd: str | None = None, timeout_seconds: int = 900, workspace_root: Path | None = None,
    runtime_dir: Path | None = None, callback_state_dir: Path | None = None, group_id: str | None = None,
    verify_git: Annotated[bool, typer.Option("--verify-git")] = False,
    use_codex_bridge: Annotated[bool, typer.Option("--use-codex-bridge")] = False,
    codex_bin: str | None = None, model: str | None = None, sandbox: SandboxChoice | None = None,
    worktree: Annotated[bool, typer.Option("--worktree")] = False,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="run")


@dispatch_app.command("complete", help="validate worker result, release lease, and emit callback for async dispatch")
def _cmd_dispatch_complete(
    ctx: typer.Context, handoff_json: ReqStr, result_json: ReqStr,
    attempt_id: str | None = None, dispatch_id: str | None = None, callback_state_dir: Path | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="complete")


@dispatch_group_app.command("plan")
def _cmd_group_plan(ctx: typer.Context, group_json: ReqStr, max_concurrent: int | None = None, max_local_concurrent: int | None = None) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="group", group_action="plan")


@dispatch_group_app.command("run")
def _cmd_group_run(
    ctx: typer.Context, group_json: ReqStr, max_concurrent: int | None = None, max_local_concurrent: int | None = None,
    workspace_root: Path | None = None, runtime_dir: Path | None = None, callback_state_dir: Path | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="group", group_action="run")


@dispatch_group_app.command("status")
def _cmd_group_status(ctx: typer.Context, group_id: str) -> argparse.Namespace:
    return _ns(ctx, "dispatch", dispatch_action="group", group_action="status")


@attempt_app.command("status")
def _cmd_attempt_status(
    ctx: typer.Context, attempt_id: Annotated[str | None, typer.Argument()] = None,
    node_id: str | None = None, objective_id: str | None = None, group_id: str | None = None, state: str | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="status")


@attempt_app.command("observe")
def _cmd_attempt_observe(ctx: typer.Context, node_id: str | None = None) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="observe")


@attempt_app.command("heartbeat")
def _cmd_attempt_hb(
    ctx: typer.Context, attempt_id: str, phase: str | None = None, checkpoint_ref: str | None = None,
    budget_json: str | None = None, renew_lease: Annotated[bool, typer.Option("--renew-lease")] = False,
    lease_ttl_seconds: int | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="heartbeat")


@attempt_app.command("preempt-plan")
def _cmd_attempt_preempt(ctx: typer.Context, node_id: str, incoming_priority: ReqInt) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="preempt-plan")


@attempt_app.command("suspend")
def _cmd_attempt_suspend(
    ctx: typer.Context, attempt_id: str, checkpoint_ref: ReqStr, reason: str = "preempted",
    release_lease: Annotated[bool, typer.Option("--release-lease/--no-release-lease")] = True,
) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="suspend")


@attempt_app.command("stale-check")
def _cmd_attempt_stale(ctx: typer.Context, callback_state_dir: Path | None = None) -> argparse.Namespace:
    return _ns(ctx, "attempt", attempt_action="stale-check")


@queue_app.command("plan")
def _cmd_queue_plan(ctx: typer.Context, requests_json: ReqStr, max_concurrent: int | None = None, max_local_concurrent: int | None = None) -> argparse.Namespace:
    return _ns(ctx, "queue", queue_action="plan")


@runner_app.command("start")
def _cmd_runner_start(
    ctx: typer.Context, role: str, owner_task: ReqStr, owner_thread: str | None = None, owner_run: str | None = None,
    workload_class: WorkloadChoice = "background", priority: int = 300,
    preemptible: Annotated[bool, typer.Option("--preemptible")] = False,
    phase: PhaseChoice = "non-interruptible", ttl_seconds: int = 3600, min_ttl_seconds: int = 300,
    max_admission_age_seconds: int = 300, startup_timeout_seconds: int = 60,
) -> argparse.Namespace:
    return _ns(ctx, "runner", runner_action="start")


@runner_app.command("stop")
def _cmd_runner_stop(ctx: typer.Context, role: str, owner_task: str | None = None, shutdown_timeout_seconds: int = 60) -> argparse.Namespace:
    return _ns(ctx, "runner", runner_action="stop")


@runner_app.command("renew")
def _cmd_runner_renew(ctx: typer.Context, role: str, owner_task: str | None = None, ttl_seconds: int | None = None) -> argparse.Namespace:
    return _ns(ctx, "runner", runner_action="renew")


@runner_app.command("status")
def _cmd_runner_status(ctx: typer.Context, role: str) -> argparse.Namespace:
    return _ns(ctx, "runner", runner_action="status")


@lease_app.command("show")
def _cmd_lease_show(ctx: typer.Context, node_id: Annotated[str | None, typer.Argument()] = None) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="show")


@lease_app.command("verify")
def _cmd_lease_verify(
    ctx: typer.Context, node_id: str, expect_role: ReqStr, expect_lease_id: ReqStr, expect_generation: ReqInt,
    expect_owner_task: ReqStr, expect_workload_class: Annotated[WorkloadChoice, typer.Option()],
    expect_phase: Annotated[PhaseChoice, typer.Option()], expect_preemptible: Annotated[BoolStrChoice, typer.Option()],
    min_ttl_seconds: ReqInt, expect_requires: ReqStr, expect_min_memory_gb: ReqInt, expect_control_commit: ReqStr,
    expect_owner_thread: str | None = None, expect_owner_run: str | None = None, max_admission_age_seconds: int = 300,
) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="verify")


@lease_app.command("acquire")
def _cmd_lease_acquire(
    ctx: typer.Context, node_id: str, owner_task: ReqStr, workload_class: Annotated[WorkloadChoice, typer.Option()],
    priority: ReqInt, owner_thread: str | None = None, owner_run: str | None = None, role: str | None = None,
    preemptible: Annotated[bool, typer.Option("--preemptible")] = False, phase: PhaseChoice = "interruptible",
    ttl_seconds: int = 3600, requires: str = "", min_memory_gb: int = 0, preempt_lease_id: str | None = None,
    preempt_generation: int | None = None, preempt_nonce: str | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="acquire")


@lease_app.command("renew")
def _cmd_lease_renew(
    ctx: typer.Context, node_id: str, lease_id: ReqStr, generation: ReqInt, nonce: ReqStr, owner_task: ReqStr,
    ttl_seconds: int = 3600, phase: PhaseChoice | None = None,
) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="renew")


@lease_app.command("release")
def _cmd_lease_release(ctx: typer.Context, node_id: str, lease_id: ReqStr, generation: ReqInt, nonce: ReqStr, owner_task: ReqStr) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="release")


@lease_app.command("reap")
def _cmd_lease_reap(ctx: typer.Context, node_id: Annotated[str | None, typer.Argument()] = None) -> argparse.Namespace:
    return _ns(ctx, "lease", lease_action="reap")


@cli_app.command("record", hidden=True)
def _cmd_record(ctx: typer.Context, state_root: ReqPath, payload_b64: ReqStr) -> argparse.Namespace:
    return _ns(ctx, "record")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        parsed = cli_app(raw, prog_name="opl-fleet", standalone_mode=False)
    except typer.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except typer.TyperException as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(getattr(exc, "exit_code", 2)) from None
    if isinstance(parsed, argparse.Namespace):
        return parsed
    raise SystemExit(0 if parsed in (0, None) else int(parsed))

def _read_json_arg(value: str, label: str) -> Any:
    source = value
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        if not path.is_file():
            raise FleetError(f"{label} file does not exist: {path}")
        source = path.read_text(encoding="utf-8")
    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        raise FleetError(f"{label} must be valid JSON") from exc


def writes_instance_state(args: argparse.Namespace) -> bool:
    """Bind the shared node namespace before its first write, even without join."""
    if args.action == "dispatch" and getattr(args, "dispatch_action", None) == "group":
        return getattr(args, "group_action", None) == "run"
    mutations = {
        "workflow": ("workflow_action", {"sync", "record-projection"}),
        "flagship": ("flagship_action", {"set"}),
        "repos": ("repos_action", {"sync"}),
        "workspace": ("workspace_action", {"bootstrap", "sync", "claim-check"}),
        "dispatch": ("dispatch_action", {"acquire", "execute", "release", "run", "complete"}),
        "lease": ("lease_action", {"acquire", "renew", "release", "reap"}),
        "runner": ("runner_action", {"start", "stop", "renew"}),
        "attempt": ("attempt_action", {"heartbeat", "suspend", "stale-check"}),
    }
    if args.action in {"join", "reconcile", "record", "data-job"}:
        return True
    field, actions = mutations.get(args.action, ("", set()))
    return getattr(args, field, None) in actions


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    local_dispatch = (
        args.action == "dispatch"
        and args.dispatch_action in {"plan", "acquire", "run"}
        and dispatch_adapter_from_args(args) == "local-codex"
    )
    instance = None if local_dispatch else configure_instance(args.instance)
    if instance is not None and writes_instance_state(args):
        write_instance_pointer(instance)
    if args.action in {"join", "reconcile"}:
        install_fleet_command()
    if args.action == "join":
        return join(args)
    if args.action == "reconcile":
        receipt = reconcile(report=args.report, install_required=args.install_required)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["state"] == "CURRENT" else 1
    if args.action == "status":
        return fleet_status()
    if args.action == "assets":
        return fleet_assets()
    if args.action == "flagship":
        result = (set_flagship(args.node_id, expected_current=args.expected_current)
                  if args.flagship_action == "set" else workflow_status())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.action == "workflow":
        result = workflow_command(args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["state"] in {"CURRENT", "UNCONFIGURED", "PUBLISH_REQUIRED"} else 1
    if args.action == "repos":
        return fleet_repositories(sync=args.repos_action == "sync")
    if args.action == "workspace":
        result = workspace_command(args.profile, args.workspace_action)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.workspace_action == "validate":
            return 0
        if args.workspace_action in {"bootstrap", "sync"}:
            return 0 if result["state"] == "CURRENT" and result["applied"] else 1
        if args.workspace_action == "claim-check":
            return 0 if result["claim_ready"] else 1
        return 0 if result["state"] == "CURRENT" else 1
    if args.action == "nodes":
        return fleet_nodes(json_output=args.json)
    if args.action == "inventory":
        inventory = collect_inventory(node_identity(), manifest(), node_registry())
        print(json.dumps(inventory, indent=2, sort_keys=True))
        return 0
    if args.action == "doctor":
        return fleet_doctor(args.node_id)
    if args.action == "data-job" and args.data_job_action == "run":
        return fleet_data_job_run(args)
    if args.action == "select":
        return fleet_select(args)
    if args.action == "dispatch":
        if args.dispatch_action == "plan":
            return fleet_dispatch_plan(args)
        if args.dispatch_action == "acquire":
            return fleet_dispatch_acquire(args)
        if args.dispatch_action == "verify":
            return fleet_dispatch_verify(args)
        if args.dispatch_action == "execute":
            return fleet_dispatch_execute(args)
        if args.dispatch_action == "release":
            return fleet_dispatch_release(args)
        if args.dispatch_action == "run":
            handoff = _read_json_arg(args.handoff_json, "worker handoff") if args.handoff_json else None
            if handoff is None:
                raise FleetError("dispatch run requires --handoff-json")
            reqs = _read_json_arg(args.requirements_json, "execution requirements") if args.requirements_json else None
            argv_list = _read_json_arg(args.argv_json, "argv") if args.argv_json else None
            exec_cmd = _read_json_arg(args.executor_cmd_json, "executor_cmd") if args.executor_cmd_json else None
            result = dispatch_run(
                handoff=handoff,
                requirements=reqs,
                adapter=args.adapter,
                node_id=args.node_id,
                role=args.role,
                owner_task=args.owner_task,
                owner_thread=args.owner_thread,
                owner_run=args.owner_run,
                argv=argv_list,
                executor_cmd=exec_cmd,
                mode=args.mode,
                cwd=args.cwd,
                timeout_seconds=args.timeout_seconds,
                workspace_root=args.workspace_root,
                runtime_dir=args.runtime_dir,
                callback_state_dir=args.callback_state_dir,
                group_id=args.group_id,
                verify_git=args.verify_git,
                preempt_lease_id=args.preempt_lease_id,
                preempt_generation=args.preempt_generation,
                preempt_nonce=args.preempt_nonce,
                use_codex_bridge=args.use_codex_bridge,
                codex_bin=args.codex_bin,
                model=args.model,
                use_worktree=args.worktree,
                sandbox=args.sandbox,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1 if result.get("status") == "unknown" else 0
        if args.dispatch_action == "complete":
            handoff = _read_json_arg(args.handoff_json, "worker handoff")
            worker_res = _read_json_arg(args.result_json, "worker result")
            result = dispatch_complete(
                handoff=handoff,
                result=worker_res,
                attempt_id=args.attempt_id,
                dispatch_id=args.dispatch_id,
                callback_state_dir=args.callback_state_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 1 if result.get("status") == "unknown" else 0
        if args.dispatch_action == "group":
            if args.group_action == "status":
                result = dispatch_group_status(args.group_id)
            else:
                group_spec = _read_json_arg(args.group_json, "group dispatch spec")
                if args.group_action == "plan":
                    result = dispatch_group_plan(
                        group_spec,
                        max_concurrent=args.max_concurrent,
                        max_local_concurrent=args.max_local_concurrent,
                    )
                else:
                    result = dispatch_group_run(
                        group_spec,
                        max_concurrent=args.max_concurrent,
                        max_local_concurrent=args.max_local_concurrent,
                        workspace_root=args.workspace_root,
                        runtime_dir=args.runtime_dir,
                        callback_state_dir=args.callback_state_dir,
                    )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
    if args.action == "attempt":
        if args.attempt_action == "status":
            if args.attempt_id:
                rec = get_attempt(args.attempt_id)
                if rec is None:
                    raise FleetError(f"attempt not found: {args.attempt_id}")
                result: Any = rec
            else:
                result = {
                    "schema": "opl_fleet_attempts_list.v1",
                    "attempts": list_attempts(
                        node_id=args.node_id,
                        objective_id=args.objective_id,
                        group_id=args.group_id,
                        state=args.state,
                    ),
                }
        elif args.attempt_action == "observe":
            result = observe_attempts(node_id=args.node_id)
        elif args.attempt_action == "heartbeat":
            budget = _read_json_arg(args.budget_json, "budget usage") if args.budget_json else None
            result = heartbeat_attempt(
                args.attempt_id,
                phase=args.phase,
                checkpoint_ref=args.checkpoint_ref,
                budget_usage=budget,
                renew_lease=args.renew_lease,
                lease_ttl_seconds=args.lease_ttl_seconds,
            )
        elif args.attempt_action == "preempt-plan":
            result = plan_preemption(args.node_id, incoming_priority=args.incoming_priority)
        elif args.attempt_action == "suspend":
            result = suspend_attempt(
                args.attempt_id,
                checkpoint_ref=args.checkpoint_ref,
                reason=args.reason,
                release_lease=args.release_lease,
            )
        else:
            result = check_stale_attempts()
            if args.callback_state_dir is not None:
                for stale in result.get("stale_attempts", []):
                    opl_events.emit_event(
                        args.callback_state_dir,
                        event_type="executor_lost",
                        objective_id=stale["objective_id"],
                        attempt_id=stale["attempt_id"],
                        source="fleet:stale-check",
                        idempotency_key=f"stale:{stale['attempt_id']}:{stale['updated_at']}",
                        payload={"signal": "attempt_heartbeat_stale", "node_id": stale["node_id"]},
                    )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.action == "queue":
        items = _read_json_arg(args.requests_json, "queue requests")
        if not isinstance(items, list):
            raise FleetError("queue requests must be a JSON array")
        result = plan_queue(
            items,
            max_concurrent=args.max_concurrent,
            max_local_concurrent=args.max_local_concurrent,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.action == "runner":
        if args.runner_action == "start":
            return fleet_runner_start(args)
        if args.runner_action == "stop":
            return fleet_runner_stop(args)
        if args.runner_action == "renew":
            return fleet_runner_renew(args)
        return fleet_runner_status(args)
    if args.action == "lease":
        if args.lease_action == "show":
            return fleet_lease_show(args)
        if args.lease_action == "verify":
            return fleet_lease_verify(args)
        if args.lease_action == "acquire":
            return fleet_lease_acquire(args)
        if args.lease_action == "renew":
            return fleet_lease_renew(args)
        if args.lease_action == "release":
            return fleet_lease_release(args)
        return fleet_lease_reap(args)
    destination = record_receipt(args.state_root, args.payload_b64)
    print(destination)
    return 0
