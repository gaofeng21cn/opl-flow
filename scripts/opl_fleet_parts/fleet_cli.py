"""OPL Fleet CLI argument parsing and command dispatch."""

from __future__ import annotations

from pathlib import Path
import argparse
import datetime as dt
import json
import re
from fleet_inventory import collect_inventory
from .fleet_common import DISPATCH_ADAPTERS, FleetError, GPU_APIS, LEASE_PHASES, LEASE_WORKLOAD_CLASSES, configure_instance, install_fleet_command, node_identity, normalize_node_id, parse_requirements, run, utc_now, write_instance_pointer
from .fleet_reconcile import control_commit, fetch_state_file, fleet_repositories, join, manifest, node_registry, reconcile, record_receipt, remote_asset_catalog
from .fleet_lease import acquire_lease_record, active_lease_map, lease_lock, public_lease, read_lease_store, reap_expired_leases, release_lease_record, renew_lease_record, select_nodes, write_lease_store
from .fleet_runner import assert_lease_admission, assert_runner_role_node, assert_runner_role_workload, build_admission_receipt, controller_guard, doctor_result, fleet_runner_renew, fleet_runner_start, fleet_runner_status, fleet_runner_stop, verify_lease_record
from .fleet_dispatch import dispatch_adapter_from_args, fleet_dispatch_acquire, fleet_dispatch_execute, fleet_dispatch_plan, fleet_dispatch_release, fleet_dispatch_verify

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
        print(json.dumps(catalog, indent=2, sort_keys=True))
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

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OPL Fleet engine backed by one private OPL Instance."
    )
    parser.add_argument("--instance")
    subparsers = parser.add_subparsers(dest="action", required=True)
    join_parser = subparsers.add_parser("join")
    join_parser.add_argument("--node-id")
    join_parser.add_argument("--no-schedule", action="store_true")
    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--report", action="store_true")
    reconcile_parser.add_argument("--install-required", action="store_true")
    subparsers.add_parser("status")
    subparsers.add_parser("assets")
    repos_parser = subparsers.add_parser("repos")
    repos_subparsers = repos_parser.add_subparsers(
        dest="repos_action",
        required=True,
    )
    repos_subparsers.add_parser("status")
    repos_subparsers.add_parser("sync")
    nodes_parser = subparsers.add_parser("nodes")
    nodes_parser.add_argument("--json", action="store_true")
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--json", action="store_true")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("node_id")
    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--requires", default="")
    select_parser.add_argument("--min-memory-gb", type=int, default=0)
    select_parser.add_argument("--gpu-api", choices=sorted(GPU_APIS), default="any")
    select_parser.add_argument("--min-gpu-memory-gb", type=int, default=0)
    select_parser.add_argument("--gpu-model")
    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="plan, lease, verify, execute, or release task capacity",
    )
    dispatch_subparsers = dispatch_parser.add_subparsers(
        dest="dispatch_action",
        required=True,
    )

    def add_dispatch_request_arguments(
        command: argparse.ArgumentParser,
        *,
        owner: bool,
    ) -> None:
        command.add_argument("--requirements-json")
        command.add_argument(
            "--adapter",
            choices=sorted(DISPATCH_ADAPTERS),
            default=None,
        )
        command.add_argument("--node-id")
        command.add_argument("--role")
        command.add_argument("--requires", default=None)
        command.add_argument("--min-memory-gb", type=int, default=None)
        command.add_argument("--gpu-api", choices=sorted(GPU_APIS), default=None)
        command.add_argument("--min-gpu-memory-gb", type=int, default=None)
        command.add_argument("--gpu-model", default=None)
        command.add_argument(
            "--workload-class",
            choices=sorted(LEASE_WORKLOAD_CLASSES),
            default=None,
        )
        command.add_argument("--priority", type=int, default=None)
        command.add_argument(
            "--preemptible",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        command.add_argument(
            "--phase",
            choices=sorted(LEASE_PHASES),
            default=None,
        )
        command.add_argument("--ttl-seconds", type=int, default=None)
        if owner:
            command.add_argument("--owner-task", required=True)
            command.add_argument("--owner-thread")
            command.add_argument("--owner-run")
            command.add_argument("--preempt-lease-id")
            command.add_argument("--preempt-generation", type=int)
            command.add_argument("--preempt-nonce")

    dispatch_plan_parser = dispatch_subparsers.add_parser("plan")
    add_dispatch_request_arguments(dispatch_plan_parser, owner=False)
    dispatch_acquire_parser = dispatch_subparsers.add_parser("acquire")
    add_dispatch_request_arguments(dispatch_acquire_parser, owner=True)
    dispatch_verify_parser = dispatch_subparsers.add_parser("verify")
    dispatch_verify_parser.add_argument("dispatch_id")
    dispatch_verify_parser.add_argument("--min-ttl-seconds", type=int, default=300)
    dispatch_verify_parser.add_argument(
        "--max-admission-age-seconds",
        type=int,
        default=300,
    )
    dispatch_execute_parser = dispatch_subparsers.add_parser(
        "execute",
        help="execute only an ssh-session lease; native Codex tasks use the app",
    )
    dispatch_execute_parser.add_argument("dispatch_id")
    dispatch_execute_parser.add_argument("--owner-task", required=True)
    dispatch_execute_parser.add_argument("--owner-thread")
    dispatch_execute_parser.add_argument("--owner-run")
    dispatch_execute_parser.add_argument("--argv-json", required=True)
    dispatch_execute_parser.add_argument("--cwd")
    dispatch_execute_parser.add_argument("--timeout-seconds", type=int, default=900)
    dispatch_execute_parser.add_argument("--min-ttl-seconds", type=int, default=60)
    dispatch_execute_parser.add_argument(
        "--max-admission-age-seconds",
        type=int,
        default=300,
    )
    dispatch_release_parser = dispatch_subparsers.add_parser("release")
    dispatch_release_parser.add_argument("dispatch_id")
    dispatch_release_parser.add_argument("--owner-task", required=True)
    runner_parser = subparsers.add_parser("runner")
    runner_subparsers = runner_parser.add_subparsers(
        dest="runner_action",
        required=True,
    )
    runner_start = runner_subparsers.add_parser("start")
    runner_start.add_argument("role")
    runner_start.add_argument("--owner-task", required=True)
    runner_start.add_argument("--owner-thread")
    runner_start.add_argument("--owner-run")
    runner_start.add_argument(
        "--workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        default="background",
    )
    runner_start.add_argument("--priority", type=int, default=300)
    runner_start.add_argument("--preemptible", action="store_true")
    runner_start.add_argument(
        "--phase",
        choices=sorted(LEASE_PHASES),
        default="non-interruptible",
    )
    runner_start.add_argument("--ttl-seconds", type=int, default=3600)
    runner_start.add_argument("--min-ttl-seconds", type=int, default=300)
    runner_start.add_argument("--max-admission-age-seconds", type=int, default=300)
    runner_start.add_argument("--startup-timeout-seconds", type=int, default=60)
    runner_stop = runner_subparsers.add_parser("stop")
    runner_stop.add_argument("role")
    runner_stop.add_argument("--owner-task")
    runner_stop.add_argument("--shutdown-timeout-seconds", type=int, default=60)
    runner_renew = runner_subparsers.add_parser("renew")
    runner_renew.add_argument("role")
    runner_renew.add_argument("--owner-task")
    runner_renew.add_argument("--ttl-seconds", type=int)
    runner_status = runner_subparsers.add_parser("status")
    runner_status.add_argument("role")
    lease_parser = subparsers.add_parser("lease")
    lease_subparsers = lease_parser.add_subparsers(
        dest="lease_action",
        required=True,
    )
    lease_show = lease_subparsers.add_parser("show")
    lease_show.add_argument("node_id", nargs="?")
    lease_verify = lease_subparsers.add_parser("verify")
    lease_verify.add_argument("node_id")
    lease_verify.add_argument("--expect-role", required=True)
    lease_verify.add_argument("--expect-lease-id", required=True)
    lease_verify.add_argument("--expect-generation", type=int, required=True)
    lease_verify.add_argument("--expect-owner-task", required=True)
    lease_verify.add_argument("--expect-owner-thread")
    lease_verify.add_argument("--expect-owner-run")
    lease_verify.add_argument(
        "--expect-workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        required=True,
    )
    lease_verify.add_argument(
        "--expect-phase",
        choices=sorted(LEASE_PHASES),
        required=True,
    )
    lease_verify.add_argument(
        "--expect-preemptible",
        choices=("true", "false"),
        required=True,
    )
    lease_verify.add_argument("--min-ttl-seconds", type=int, required=True)
    lease_verify.add_argument("--expect-requires", required=True)
    lease_verify.add_argument("--expect-min-memory-gb", type=int, required=True)
    lease_verify.add_argument("--max-admission-age-seconds", type=int, default=300)
    lease_verify.add_argument("--expect-control-commit", required=True)
    lease_acquire = lease_subparsers.add_parser("acquire")
    lease_acquire.add_argument("node_id")
    lease_acquire.add_argument("--owner-task", required=True)
    lease_acquire.add_argument("--owner-thread")
    lease_acquire.add_argument("--owner-run")
    lease_acquire.add_argument("--role")
    lease_acquire.add_argument(
        "--workload-class",
        choices=sorted(LEASE_WORKLOAD_CLASSES),
        required=True,
    )
    lease_acquire.add_argument("--priority", type=int, required=True)
    lease_acquire.add_argument("--preemptible", action="store_true")
    lease_acquire.add_argument("--phase", choices=sorted(LEASE_PHASES), default="interruptible")
    lease_acquire.add_argument("--ttl-seconds", type=int, default=3600)
    lease_acquire.add_argument("--requires", default="")
    lease_acquire.add_argument("--min-memory-gb", type=int, default=0)
    lease_acquire.add_argument("--preempt-lease-id")
    lease_acquire.add_argument("--preempt-generation", type=int)
    lease_acquire.add_argument("--preempt-nonce")
    lease_renew = lease_subparsers.add_parser("renew")
    lease_renew.add_argument("node_id")
    lease_renew.add_argument("--lease-id", required=True)
    lease_renew.add_argument("--generation", type=int, required=True)
    lease_renew.add_argument("--nonce", required=True)
    lease_renew.add_argument("--owner-task", required=True)
    lease_renew.add_argument("--ttl-seconds", type=int, default=3600)
    lease_renew.add_argument("--phase", choices=sorted(LEASE_PHASES))
    lease_release = lease_subparsers.add_parser("release")
    lease_release.add_argument("node_id")
    lease_release.add_argument("--lease-id", required=True)
    lease_release.add_argument("--generation", type=int, required=True)
    lease_release.add_argument("--nonce", required=True)
    lease_release.add_argument("--owner-task", required=True)
    lease_reap = lease_subparsers.add_parser("reap")
    lease_reap.add_argument("node_id", nargs="?")
    record_parser = subparsers.add_parser("record", help=argparse.SUPPRESS)
    record_parser.add_argument("--state-root", type=Path, required=True)
    record_parser.add_argument("--payload-b64", required=True)
    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    local_dispatch = (
        args.action == "dispatch"
        and args.dispatch_action in {"plan", "acquire"}
        and dispatch_adapter_from_args(args) == "local-codex"
    )
    instance = None if local_dispatch else configure_instance(args.instance)
    if args.action in {"join", "reconcile"}:
        write_instance_pointer(instance)
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
    if args.action == "repos":
        return fleet_repositories(sync=args.repos_action == "sync")
    if args.action == "nodes":
        return fleet_nodes(json_output=args.json)
    if args.action == "inventory":
        inventory = collect_inventory(node_identity(), manifest(), node_registry())
        print(json.dumps(inventory, indent=2, sort_keys=True))
        return 0
    if args.action == "doctor":
        return fleet_doctor(args.node_id)
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
        return fleet_dispatch_release(args)
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
