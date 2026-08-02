#!/usr/bin/env python3
"""OPL Fleet engine backed by one private OPL Instance.

Facade that preserves the original module surface and CLI entry point while
the implementation lives in medium-grained domain modules under
scripts/opl_fleet_parts/.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import plistlib
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from fleet_inventory import collect_inventory, validate_inventory

from opl_fleet_parts import (
    fleet_cli,
    fleet_common,
    fleet_dispatch,
    fleet_features,
    fleet_lease,
    fleet_reconcile,
    fleet_runner,
)

FLOW_ROOT = fleet_common.FLOW_ROOT
CONFIG_PATH = fleet_common.CONFIG_PATH
ROUTES_PATH = fleet_common.ROUTES_PATH
STATE_ROOT = fleet_common.STATE_ROOT
INSTANCE_POINTER_PATH = fleet_common.INSTANCE_POINTER_PATH
RUNNER_PATH = fleet_common.RUNNER_PATH
NODE_ID_PATTERN = fleet_common.NODE_ID_PATTERN
OWNER_ID_PATTERN = fleet_common.OWNER_ID_PATTERN
ROLE_PATTERN = fleet_common.ROLE_PATTERN
COMMIT_PATTERN = fleet_common.COMMIT_PATTERN
LEASE_WORKLOAD_CLASSES = fleet_common.LEASE_WORKLOAD_CLASSES
LIVE_ONLY_POLICY_FEATURES = fleet_common.LIVE_ONLY_POLICY_FEATURES
PREEMPTIBLE_WORKLOAD_CLASSES = fleet_common.PREEMPTIBLE_WORKLOAD_CLASSES
PROTECTED_WORKLOAD_CLASSES = fleet_common.PROTECTED_WORKLOAD_CLASSES
LEASE_PHASES = fleet_common.LEASE_PHASES
AVAILABILITY_POLICIES = fleet_common.AVAILABILITY_POLICIES
DISPATCH_ADAPTERS = fleet_common.DISPATCH_ADAPTERS
ADMISSION_FIELDS = fleet_common.ADMISSION_FIELDS
ADMISSION_OPTIONAL_FIELDS = fleet_common.ADMISSION_OPTIONAL_FIELDS
GPU_APIS = fleet_common.GPU_APIS
EXECUTION_REQUIREMENTS_SCHEMA = fleet_common.EXECUTION_REQUIREMENTS_SCHEMA
SKILL_REFERENCE_SCHEMA = fleet_common.SKILL_REFERENCE_SCHEMA
MAX_EXECUTION_REQUIREMENTS_BYTES = fleet_common.MAX_EXECUTION_REQUIREMENTS_BYTES
MAX_EXECUTION_OUTPUT_BYTES = fleet_common.MAX_EXECUTION_OUTPUT_BYTES
REMOTE_EXECUTION_TIMEOUT_SECONDS = fleet_common.REMOTE_EXECUTION_TIMEOUT_SECONDS
REMOTE_EXECUTOR = fleet_common.REMOTE_EXECUTOR
LEASE_FIELDS = fleet_common.LEASE_FIELDS
LEASE_REQUIRED_FIELDS = fleet_common.LEASE_REQUIRED_FIELDS
LEASE_OPTIONAL_FIELDS = fleet_common.LEASE_OPTIONAL_FIELDS
RECEIPT_FIELDS = fleet_common.RECEIPT_FIELDS
PET_FILES = fleet_common.PET_FILES
REPORT_FIELDS = fleet_common.REPORT_FIELDS
REPOSITORY_FETCH_TIMEOUT_SECONDS = fleet_common.REPOSITORY_FETCH_TIMEOUT_SECONDS
_INSTANCE_OWNER = fleet_common._INSTANCE_OWNER
FleetError = fleet_common.FleetError

from opl_fleet_parts.fleet_common import (
    configure_instance, install_fleet_command, write_instance_pointer, run, read_json, sha256_file, atomic_json, effective_codex_home,
    normalize_node_id, node_identity, utc_now, parse_utc, parse_requirements, dispatch_adapter,
)

from opl_fleet_parts.fleet_reconcile import (
    manifest, managed_repository_owner, node_registry, pet_manifest, pet_files_match, reconcile_pets, control_commit, checkout_commit,
    update_checkout, update_flow, update_control, workspace_root, github_repository_from_remote, git_value, reconcile_repository, reconcile_workspace_repositories,
    fleet_repositories, restart_after_flow_update, github_head, install_runner, fetch_skill_reference, codex_plugin_skill_roots, skill_present, install_missing_owner_skills,
    runner_call, build_receipt, validate_receipt, render_status, format_bytes, markdown_text, build_asset_catalog, render_assets,
    write_asset_catalog, record_receipt, report_receipt, install_macos_schedule, install_wsl_schedule, install_linux_schedule, install_schedule, reconcile,
    join, fetch_state_file, remote_asset_catalog,
)

from opl_fleet_parts.fleet_features import (
    inventory_is_fresh, inventory_age_seconds, parse_memory_bytes, gpu_profiles, matching_gpus, node_features,
)

from opl_fleet_parts.fleet_lease import (
    lease_paths, empty_lease_store, validate_owner_id, validate_role, validate_admission, validate_lease, validate_lease_store, lease_lock,
    read_lease_store, write_lease_store, lease_is_expired, audit_lease, reap_expired_leases, public_lease, active_lease_map, validate_ttl,
    build_lease, acquire_lease_record, assert_lease_cas, renew_lease_record, release_lease_record, select_nodes,
)

from opl_fleet_parts.fleet_runner import (
    validate_work_volume_route, read_routes, validate_runner_control, tailscale_online, work_volume_status, doctor_result, controller_guard, runner_role_nodes,
    assert_runner_role_node, assert_runner_role_workload, assert_lease_admission, build_admission_receipt, verify_lease_record, runner_transaction_path, runner_binding, runner_control_route,
    runner_control_call, github_runner_state, wait_runner_state, wait_runner_processes, read_runner_transaction, runner_transaction_from_lease, confirm_runner_shutdown, fleet_runner_start,
    fleet_runner_stop, fleet_runner_renew, fleet_runner_status,
)

from opl_fleet_parts.fleet_dispatch import (
    validate_execution_requirements, read_execution_requirements, request_value, dispatch_adapter_from_args, dispatch_request, dispatch_candidates, dispatch_plan_payload, dispatch_lease,
    fleet_dispatch_plan, fleet_dispatch_acquire, fleet_dispatch_verify, validate_execution_argv, validate_execution_result, execute_ssh_session, fleet_dispatch_execute, fleet_dispatch_release,
)

from opl_fleet_parts.fleet_cli import (
    fleet_status, fleet_assets, fleet_nodes, fleet_select, fleet_doctor, fleet_lease_show, fleet_lease_acquire, fleet_lease_verify,
    fleet_lease_renew, fleet_lease_release, fleet_lease_reap, parse_args, main,
)


def __getattr__(name: str) -> Any:
    # CONTROL_ROOT is mutable at runtime (configure_instance owns it in
    # fleet_common); proxy it dynamically instead of copying the binding.
    if name == "CONTROL_ROOT":
        return fleet_common.CONTROL_ROOT
    raise AttributeError(name)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"opl-fleet failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
