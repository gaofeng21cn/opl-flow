#!/usr/bin/env python3
"""Default Codex CLI (`codex exec`) bridge for stateless control turns and worker slices.

Zero Fleet imports. Never passes --dangerously-bypass-approvals-and-sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    from . import opl_runtime as runtime
    from . import opl_execution
    from . import opl_bridge_common as bridge_common
except ImportError:  # Direct script execution.
    import opl_runtime as runtime
    import opl_execution
    import opl_bridge_common as bridge_common


CONTROL_RECEIPT_SCHEMA_NAME = bridge_common.CONTROL_RECEIPT_SCHEMA_NAME
SANDBOX_MODES = bridge_common.SANDBOX_MODES
BridgeError = bridge_common.BridgeError
flow_root = bridge_common.flow_root
control_receipt_schema_path = bridge_common.control_receipt_schema_path
resolve_sandbox_mode = bridge_common.resolve_sandbox_mode
build_worker_output_schema = bridge_common.build_worker_output_schema
validate_control_receipt = bridge_common.validate_control_receipt
_control_prompt = bridge_common.control_prompt
_worker_prompt = bridge_common.worker_prompt
_strip_null_worker_optionals = bridge_common.strip_null_worker_optionals
_load_json_arg = bridge_common.load_json_arg


def resolve_codex_bin(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("OPL_CODEX_BIN") or shutil.which("codex")
    if not candidate:
        raise BridgeError("codex CLI is unavailable")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise BridgeError(f"codex CLI is not executable: {path}")
    return str(path)


def _run_codex_exec(
    argv: list[str],
    *,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return runtime.run_with_retry(
            lambda: subprocess.run(
                argv,
                cwd=cwd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            ),
            attempts=3,
            min_wait=0.05,
            max_wait=0.25,
            retry_on=(BlockingIOError, InterruptedError),
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeError(f"codex exec timed out after {timeout_seconds}s") from exc
    except OSError as exc:
        raise BridgeError(f"codex exec failed to start: {exc}") from exc


def run_control_turn(
    plan: dict[str, Any],
    *,
    instance_root: Path | None = None,
    cwd: Path | None = None,
    codex_bin: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    ephemeral: bool = True,
    skip_git_repo_check: bool = False,
    timeout_seconds: int = 600,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema") != "opl_control_turn_plan.v1":
        raise BridgeError("control mode expects opl_control_turn_plan.v1 input")

    try:
        opl_execution.sanitize_check(plan, label="control_turn_plan")
    except opl_execution.ExecutionError as exc:
        raise BridgeError(str(exc)) from exc

    # Zero-token fast path when no reasoning or action is required
    if bridge_common.is_noop_control_plan(plan):
        return bridge_common.noop_control_receipt(plan)

    resolved_cwd = (cwd or instance_root or flow_root()).expanduser().resolve()
    resolved_sandbox = resolve_sandbox_mode(None, explicit_sandbox=sandbox)
    prompt = _control_prompt(plan, instance_root=instance_root)
    schema_path = control_receipt_schema_path()
    if not schema_path.is_file():
        raise BridgeError(f"control receipt schema is missing: {schema_path}")

    binary = codex_bin if dry_run and codex_bin else ("codex" if dry_run else resolve_codex_bin(codex_bin))
    with tempfile.TemporaryDirectory(prefix="opl-codex-ctrl-") as tmp:
        out_path = Path(tmp) / "control-receipt.json"
        argv = [
            binary,
            "exec",
            *(["--ephemeral"] if ephemeral else []),
            *(["--skip-git-repo-check"] if skip_git_repo_check else []),
            "-s",
            resolved_sandbox,
            "-C",
            str(resolved_cwd),
            "--output-schema",
            str(schema_path),
            "-o",
            str(out_path),
            *(["-m", model] if model else []),
            "-",
        ]
        if dry_run:
            return {
                "schema": "opl_codex_bridge_dry_run.v1",
                "mode": "control",
                "argv": argv,
                "cwd": str(resolved_cwd),
                "sandbox": resolved_sandbox,
                "prompt": prompt,
            }

        proc = _run_codex_exec(argv, prompt=prompt, cwd=resolved_cwd, timeout_seconds=timeout_seconds)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            raise BridgeError(f"codex exec control turn failed: {detail}")
        if not out_path.is_file():
            raise BridgeError("codex exec control turn produced no output file")
        raw_out = out_path.read_text(encoding="utf-8").strip()
        if not raw_out:
            raise BridgeError("codex exec control turn produced empty output")
        try:
            parsed = json.loads(raw_out)
        except json.JSONDecodeError as exc:
            raise BridgeError("codex exec control turn output is not valid JSON") from exc
        return validate_control_receipt(parsed)


def run_worker_slice(
    handoff: dict[str, Any],
    *,
    context_manifest: dict[str, Any] | None = None,
    cwd: Path | None = None,
    codex_bin: str | None = None,
    model: str | None = None,
    sandbox: str | None = None,
    ephemeral: bool = True,
    use_worktree: bool = False,
    skip_git_repo_check: bool = False,
    timeout_seconds: int = 900,
    dry_run: bool = False,
) -> dict[str, Any]:
    try:
        validated_handoff = opl_execution.validate_handoff(handoff)
        opl_execution.enforce_pre_execution_envelope(validated_handoff)
        binding = opl_execution.handoff_binding(validated_handoff)
    except opl_execution.ExecutionError as exc:
        raise BridgeError(str(exc)) from exc

    resolved_sandbox = resolve_sandbox_mode(validated_handoff, explicit_sandbox=sandbox)
    envelope = validated_handoff.get("envelope") or {}
    effective_timeout = int(timeout_seconds)
    if "max_duration_seconds" in envelope:
        effective_timeout = min(effective_timeout, int(envelope["max_duration_seconds"]))

    resolved_cwd = (cwd or flow_root()).expanduser().resolve()
    prompt = _worker_prompt(validated_handoff, binding, context_manifest)
    binary = codex_bin if dry_run and codex_bin else ("codex" if dry_run else resolve_codex_bin(codex_bin))

    with tempfile.TemporaryDirectory(prefix="opl-codex-worker-") as tmp:
        tmp_dir = Path(tmp)
        schema_path = tmp_dir / "worker-output.schema.json"
        out_path = tmp_dir / "worker-result.json"
        schema_path.write_text(
            json.dumps(build_worker_output_schema(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        argv = [
            binary,
            "exec",
            *(["--ephemeral"] if ephemeral else []),
            *(["--worktree"] if use_worktree else []),
            *(["--skip-git-repo-check"] if skip_git_repo_check else []),
            "-s",
            resolved_sandbox,
            "-C",
            str(resolved_cwd),
            "--output-schema",
            str(schema_path),
            "-o",
            str(out_path),
            *(["-m", model] if model else []),
            "-",
        ]
        if dry_run:
            return {
                "schema": "opl_codex_bridge_dry_run.v1",
                "mode": "worker",
                "argv": argv,
                "cwd": str(resolved_cwd),
                "sandbox": resolved_sandbox,
                "binding": binding,
                "prompt": prompt,
            }

        proc = _run_codex_exec(argv, prompt=prompt, cwd=resolved_cwd, timeout_seconds=effective_timeout)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            raise BridgeError(f"codex exec worker failed: {detail}")
        if not out_path.is_file():
            raise BridgeError("codex exec worker produced no output file")
        raw_out = out_path.read_text(encoding="utf-8").strip()
        if not raw_out:
            raise BridgeError("codex exec worker produced empty output")
        try:
            parsed = json.loads(raw_out)
        except json.JSONDecodeError as exc:
            raise BridgeError("codex exec worker output is not valid JSON") from exc

        cleaned = _strip_null_worker_optionals(parsed)
        try:
            validated_result = opl_execution.validate_result(cleaned, validated_handoff)
            opl_execution.evaluate_budget_usage(validated_handoff, validated_result)
        except opl_execution.ExecutionError as exc:
            raise BridgeError(str(exc)) from exc
        return validated_result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode_name in ("control", "worker"):
        sub = subparsers.add_parser(mode_name)
        sub.add_argument("--codex-bin")
        sub.add_argument("--model")
        sub.add_argument("--sandbox", choices=SANDBOX_MODES)
        sub.add_argument("--cwd", type=Path)
        sub.add_argument("--timeout-seconds", type=int, default=600 if mode_name == "control" else 900)
        sub.add_argument("--persist-session", action="store_true")
        sub.add_argument("--skip-git-repo-check", action="store_true")
        sub.add_argument("--dry-run", action="store_true")
        if mode_name == "control":
            sub.add_argument("--plan-json")
            sub.add_argument("--instance", type=Path)
        else:
            sub.add_argument("--handoff-json")
            sub.add_argument("--worktree", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.mode == "control":
            plan = _load_json_arg(args.plan_json, fallback_stdin=True)
            result = run_control_turn(
                plan,
                instance_root=args.instance,
                cwd=args.cwd,
                codex_bin=args.codex_bin,
                model=args.model,
                sandbox=args.sandbox,
                ephemeral=not args.persist_session,
                skip_git_repo_check=args.skip_git_repo_check,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        else:
            handoff = _load_json_arg(args.handoff_json, env_var="OPL_HANDOFF_PATH")
            manifest = None
            if os.environ.get("OPL_CONTEXT_MANIFEST"):
                m_path = Path(os.environ["OPL_CONTEXT_MANIFEST"])
                if m_path.is_file():
                    manifest = json.loads(m_path.read_text(encoding="utf-8"))
            result = run_worker_slice(
                handoff,
                context_manifest=manifest,
                cwd=args.cwd,
                codex_bin=args.codex_bin,
                model=args.model,
                sandbox=args.sandbox,
                ephemeral=not args.persist_session,
                use_worktree=args.worktree,
                skip_git_repo_check=args.skip_git_repo_check,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
