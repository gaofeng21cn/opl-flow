#!/usr/bin/env python3
"""Antigravity CLI (`agy --print`) bridge for stateless control turns and worker slices.

Zero Fleet imports. Never passes --dangerously-skip-permissions or --disable-slash-commands.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
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
AGY_MODES = ("plan", "accept-edits", "auto")
AGY_EFFORTS = ("low", "medium", "high", "xhigh", "max")
BridgeError = bridge_common.BridgeError
flow_root = bridge_common.flow_root
control_receipt_schema_path = bridge_common.control_receipt_schema_path
resolve_sandbox_mode = bridge_common.resolve_sandbox_mode
build_worker_output_schema = bridge_common.build_worker_output_schema
validate_control_receipt = bridge_common.validate_control_receipt


def resolve_agy_bin(explicit: str | None = None) -> str:
    """Resolve executable path for the Antigravity CLI (`agy`)."""
    candidate = explicit or os.environ.get("OPL_AGY_BIN") or shutil.which("agy")
    if not candidate:
        raise BridgeError("agy CLI is unavailable")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise BridgeError(f"agy CLI is not executable: {path}")
    return str(path)


def resolve_agy_mode(
    handoff: dict[str, Any] | None = None,
    *,
    explicit_sandbox: str | None = None,
    explicit_mode: str | None = None,
) -> tuple[str, str]:
    """Map handoff envelope & explicit flags into validated (sandbox, agy_mode)."""
    sandbox = resolve_sandbox_mode(handoff, explicit_sandbox=explicit_sandbox)
    envelope = (handoff or {}).get("envelope") or {}
    if explicit_mode is None:
        mapped = {
            "read-only": "plan",
            "workspace-write": "accept-edits",
            "danger-full-access": "auto",
        }[sandbox]
        return sandbox, mapped

    if explicit_mode not in AGY_MODES:
        raise BridgeError(f"unsupported agy mode: {explicit_mode!r}")
    if explicit_mode == "auto" and envelope.get("allow_destructive") is False:
        raise BridgeError("auto mode is forbidden when allow_destructive=false")
    if sandbox == "read-only" and explicit_mode != "plan":
        raise BridgeError("read-only sandbox requires agy --mode plan")
    return sandbox, explicit_mode


def parse_agy_json_envelope(raw_stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract structured_output and runtime telemetry from `agy --output-format json` stdout."""
    text = (raw_stdout or "").strip()
    if not text:
        raise BridgeError("agy produced empty output")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BridgeError("agy output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise BridgeError("agy JSON output must be an object")

    # Lightweight direct-payload compatibility when structured_output wrapper is absent
    if "structured_output" not in parsed and isinstance(parsed.get("schema"), str):
        return parsed, {}

    status = parsed.get("status")
    if status is not None and status != "SUCCESS":
        raise BridgeError(f"agy returned non-SUCCESS status: {status!r}")

    structured = parsed.get("structured_output")
    if not isinstance(structured, dict):
        raise BridgeError("agy output missing structured_output object")

    telemetry: dict[str, Any] = {}
    duration = parsed.get("duration_seconds")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
        telemetry["elapsed_seconds"] = float(duration)
    usage = parsed.get("usage")
    if isinstance(usage, dict):
        total_tokens = usage.get("total_tokens")
        if isinstance(total_tokens, int) and not isinstance(total_tokens, bool) and total_tokens >= 0:
            telemetry["tokens_used"] = int(total_tokens)
    return structured, telemetry


def merge_runtime_budget(cleaned_result: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
    """Backfill runtime elapsed_seconds / tokens_used without overwriting model-supplied values."""
    if not telemetry:
        return cleaned_result
    merged = deepcopy(cleaned_result)
    existing = merged.get("budget_usage")
    usage: dict[str, Any] = dict(existing) if isinstance(existing, dict) else {}
    for key in ("elapsed_seconds", "tokens_used"):
        if key not in usage and key in telemetry:
            usage[key] = telemetry[key]
    if usage:
        merged["budget_usage"] = usage
    return merged


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise BridgeError(f"git failed to start: {exc}") from exc


def _prepare_worktree(repo_cwd: Path, attempt_id: str) -> tuple[Path, Path, str]:
    """Create a detached temporary git worktree under a temp dir so agy runs isolated."""
    top_proc = _run_git(repo_cwd, "rev-parse", "--show-toplevel")
    if top_proc.returncode != 0:
        detail = (top_proc.stderr or top_proc.stdout or "not a git repository").strip()
        raise BridgeError(f"cannot prepare worktree from {repo_cwd}: {detail}")
    repo_root = Path(top_proc.stdout.strip()).resolve()
    head_proc = _run_git(repo_root, "rev-parse", "HEAD")
    if head_proc.returncode != 0:
        detail = (head_proc.stderr or head_proc.stdout or "missing HEAD").strip()
        raise BridgeError(f"cannot resolve HEAD for worktree in {repo_root}: {detail}")
    base_head = head_proc.stdout.strip()

    safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", attempt_id).strip("-")[:32] or "slice"
    parent_dir = Path(tempfile.mkdtemp(prefix=f"opl-agy-wt-{safe_slug}-"))
    wt_dir = parent_dir / "wt"
    add_proc = _run_git(repo_root, "worktree", "add", "--detach", str(wt_dir), base_head)
    if add_proc.returncode != 0:
        shutil.rmtree(parent_dir, ignore_errors=True)
        detail = (add_proc.stderr or add_proc.stdout or f"exit {add_proc.returncode}").strip()
        raise BridgeError(f"failed to create agy worktree: {detail}")
    return repo_root, wt_dir, base_head


def _cleanup_worktree_if_clean(repo_root: Path, wt_dir: Path, base_head: str) -> bool:
    """Remove temporary worktree only if clean and at base_head; preserve dirty/committed work."""
    status_proc = _run_git(wt_dir, "status", "--porcelain")
    head_proc = _run_git(wt_dir, "rev-parse", "HEAD")
    is_clean = (
        status_proc.returncode == 0
        and not status_proc.stdout.strip()
        and head_proc.returncode == 0
        and head_proc.stdout.strip() == base_head
    )
    if not is_clean:
        return False
    rm_proc = _run_git(repo_root, "worktree", "remove", "--force", str(wt_dir))
    if rm_proc.returncode == 0:
        shutil.rmtree(wt_dir.parent, ignore_errors=True)
        return True
    return False


def _run_agy_exec(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return runtime.run_with_retry(
            lambda: subprocess.run(
                argv,
                cwd=cwd,
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
        raise BridgeError(f"agy exec timed out after {timeout_seconds}s") from exc
    except OSError as exc:
        raise BridgeError(f"agy exec failed to start: {exc}") from exc


def _build_agy_argv(
    binary: str,
    *,
    schema_path: Path,
    agy_mode: str,
    prompt: str,
    timeout_seconds: int,
    model: str | None = None,
    effort: str | None = None,
) -> list[str]:
    if effort is not None and effort not in AGY_EFFORTS:
        raise BridgeError(f"unsupported agy effort level: {effort!r}")
    return [
        binary,
        "--output-format",
        "json",
        "--json-schema",
        str(schema_path),
        "--sandbox",
        "--mode",
        agy_mode,
        *(["--model", model] if model else []),
        *(["--effort", effort] if effort else []),
        "--print-timeout",
        f"{int(timeout_seconds)}s",
        f"--print={prompt}",
    ]


def run_control_turn(
    plan: dict[str, Any],
    *,
    instance_root: Path | None = None,
    cwd: Path | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    mode: str | None = None,
    timeout_seconds: int = 600,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute one stateless control turn through `agy --print`."""
    if not isinstance(plan, dict) or plan.get("schema") != "opl_control_turn_plan.v1":
        raise BridgeError("control mode expects opl_control_turn_plan.v1 input")

    try:
        opl_execution.sanitize_check(plan, label="control_turn_plan")
    except opl_execution.ExecutionError as exc:
        raise BridgeError(str(exc)) from exc

    if bridge_common.is_noop_control_plan(plan):
        return bridge_common.noop_control_receipt(plan)

    resolved_cwd = (cwd or instance_root or flow_root()).expanduser().resolve()
    resolved_sandbox, resolved_mode = resolve_agy_mode(None, explicit_sandbox=sandbox, explicit_mode=mode)
    prompt = bridge_common.control_prompt(plan, instance_root=instance_root)
    schema_path = control_receipt_schema_path()
    if not schema_path.is_file():
        raise BridgeError(f"control receipt schema is missing: {schema_path}")

    binary = agy_bin if dry_run and agy_bin else ("agy" if dry_run else resolve_agy_bin(agy_bin))
    argv = _build_agy_argv(
        binary,
        schema_path=schema_path,
        agy_mode=resolved_mode,
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        model=model,
        effort=effort,
    )
    if dry_run:
        return {
            "schema": "opl_antigravity_bridge_dry_run.v1",
            "mode": "control",
            "argv": argv,
            "cwd": str(resolved_cwd),
            "sandbox": resolved_sandbox,
            "agy_mode": resolved_mode,
            "prompt": prompt,
        }

    proc = _run_agy_exec(argv, cwd=resolved_cwd, timeout_seconds=timeout_seconds)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        raise BridgeError(f"agy control turn failed: {detail}")
    structured, _ = parse_agy_json_envelope(proc.stdout)
    return validate_control_receipt(structured)


def run_worker_slice(
    handoff: dict[str, Any],
    *,
    context_manifest: dict[str, Any] | None = None,
    cwd: Path | None = None,
    agy_bin: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    sandbox: str | None = None,
    mode: str | None = None,
    use_worktree: bool = False,
    timeout_seconds: int = 900,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute one bounded worker slice through `agy --print` with optional git worktree isolation."""
    try:
        validated_handoff = opl_execution.validate_handoff(handoff)
        opl_execution.enforce_pre_execution_envelope(validated_handoff)
        binding = opl_execution.handoff_binding(validated_handoff)
    except opl_execution.ExecutionError as exc:
        raise BridgeError(str(exc)) from exc

    resolved_sandbox, resolved_mode = resolve_agy_mode(
        validated_handoff,
        explicit_sandbox=sandbox,
        explicit_mode=mode,
    )
    envelope = validated_handoff.get("envelope") or {}
    effective_timeout = int(timeout_seconds)
    if "max_duration_seconds" in envelope:
        effective_timeout = min(effective_timeout, int(envelope["max_duration_seconds"]))

    resolved_cwd = (cwd or flow_root()).expanduser().resolve()
    prompt = bridge_common.worker_prompt(validated_handoff, binding, context_manifest)
    binary = agy_bin if dry_run and agy_bin else ("agy" if dry_run else resolve_agy_bin(agy_bin))

    with tempfile.TemporaryDirectory(prefix="opl-agy-worker-") as tmp:
        schema_path = Path(tmp) / "worker-output.schema.json"
        schema_path.write_text(
            json.dumps(build_worker_output_schema(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        argv = _build_agy_argv(
            binary,
            schema_path=schema_path,
            agy_mode=resolved_mode,
            prompt=prompt,
            timeout_seconds=effective_timeout,
            model=model,
            effort=effort,
        )
        if dry_run:
            return {
                "schema": "opl_antigravity_bridge_dry_run.v1",
                "mode": "worker",
                "argv": argv,
                "cwd": str(resolved_cwd),
                "sandbox": resolved_sandbox,
                "agy_mode": resolved_mode,
                "use_worktree": use_worktree,
                "binding": binding,
                "prompt": prompt,
            }

        exec_cwd = resolved_cwd
        wt_info: tuple[Path, Path, str] | None = None
        if use_worktree:
            wt_info = _prepare_worktree(resolved_cwd, validated_handoff["attempt_id"])
            exec_cwd = wt_info[1]

        try:
            proc = _run_agy_exec(argv, cwd=exec_cwd, timeout_seconds=effective_timeout)
        finally:
            if wt_info is not None:
                _cleanup_worktree_if_clean(*wt_info)

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            raise BridgeError(f"agy worker failed: {detail}")

        structured, telemetry = parse_agy_json_envelope(proc.stdout)
        cleaned = bridge_common.strip_null_worker_optionals(structured)
        with_budget = merge_runtime_budget(cleaned, telemetry)
        try:
            validated_result = opl_execution.validate_result(with_budget, validated_handoff)
            opl_execution.evaluate_budget_usage(validated_handoff, validated_result)
        except opl_execution.ExecutionError as exc:
            raise BridgeError(str(exc)) from exc
        return validated_result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode_name in ("control", "worker"):
        sub = subparsers.add_parser(mode_name)
        sub.add_argument("--agy-bin")
        sub.add_argument("--model")
        sub.add_argument("--effort", choices=AGY_EFFORTS)
        sub.add_argument("--sandbox", choices=SANDBOX_MODES)
        sub.add_argument("--agy-mode", dest="agy_mode", choices=AGY_MODES)
        sub.add_argument("--cwd", type=Path)
        sub.add_argument("--timeout-seconds", type=int, default=600 if mode_name == "control" else 900)
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
            plan = bridge_common.load_json_arg(args.plan_json, fallback_stdin=True)
            result = run_control_turn(
                plan,
                instance_root=args.instance,
                cwd=args.cwd,
                agy_bin=args.agy_bin,
                model=args.model,
                effort=args.effort,
                sandbox=args.sandbox,
                mode=args.agy_mode,
                timeout_seconds=args.timeout_seconds,
                dry_run=args.dry_run,
            )
        else:
            handoff = bridge_common.load_json_arg(args.handoff_json, env_var="OPL_HANDOFF_PATH")
            manifest = None
            if os.environ.get("OPL_CONTEXT_MANIFEST"):
                m_path = Path(os.environ["OPL_CONTEXT_MANIFEST"])
                if m_path.is_file():
                    manifest = json.loads(m_path.read_text(encoding="utf-8"))
            result = run_worker_slice(
                handoff,
                context_manifest=manifest,
                cwd=args.cwd,
                agy_bin=args.agy_bin,
                model=args.model,
                effort=args.effort,
                sandbox=args.sandbox,
                mode=args.agy_mode,
                use_worktree=args.worktree,
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
