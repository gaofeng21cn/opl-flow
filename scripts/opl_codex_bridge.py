#!/usr/bin/env python3
"""Default Codex CLI (`codex exec`) bridge for stateless control turns and worker slices.

Zero Fleet imports. Never passes --dangerously-bypass-approvals-and-sandbox.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    from . import opl_execution
except ImportError:  # Direct script execution.
    import opl_execution


CONTROL_RECEIPT_SCHEMA_NAME = "opl_control_turn_receipt.v1"
SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")


class BridgeError(RuntimeError):
    pass


def flow_root() -> Path:
    return Path(__file__).resolve().parents[1]


def control_receipt_schema_path() -> Path:
    return flow_root() / "contracts" / "control-turn-receipt.schema.json"


def resolve_codex_bin(explicit: str | None = None) -> str:
    candidate = explicit or os.environ.get("OPL_CODEX_BIN") or shutil.which("codex")
    if not candidate:
        raise BridgeError("codex CLI is unavailable")
    path = Path(candidate).expanduser()
    if path.is_absolute() and not os.access(path, os.X_OK):
        raise BridgeError(f"codex CLI is not executable: {path}")
    return str(path)


def resolve_sandbox_mode(
    handoff: dict[str, Any] | None = None,
    *,
    explicit_sandbox: str | None = None,
) -> str:
    envelope = (handoff or {}).get("envelope") or {}
    if explicit_sandbox is not None:
        if explicit_sandbox not in SANDBOX_MODES:
            raise BridgeError(f"unsupported sandbox mode: {explicit_sandbox!r}")
        if explicit_sandbox == "danger-full-access" and envelope.get("allow_destructive") is False:
            raise BridgeError("danger-full-access sandbox is forbidden when allow_destructive=false")
        return explicit_sandbox
    if (
        handoff is not None
        and "allowed_write_paths" in envelope
        and envelope.get("allowed_write_paths") == []
        and not handoff.get("write_set")
    ):
        return "read-only"
    return "workspace-write"


def build_worker_output_schema() -> dict[str, Any]:
    """Return an OpenAI-strict JSON schema matching opl_worker_result.v1."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OPL Worker Result Strict Output",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "binding",
            "outcome",
            "artifact_refs",
            "checkpoint_refs",
            "remaining",
            "next_action",
            "budget_usage",
        ],
        "properties": {
            "schema": {"type": "string", "enum": ["opl_worker_result.v1"]},
            "binding": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "attempt_id",
                    "objective_id",
                    "owner_id",
                    "handoff_sha256",
                ],
                "properties": {
                    "attempt_id": {"type": "string", "minLength": 1},
                    "objective_id": {"type": "string", "minLength": 1},
                    "owner_id": {"type": "string", "minLength": 1},
                    "handoff_sha256": {
                        "type": "string",
                        "pattern": "^[0-9a-f]{64}$",
                    },
                },
            },
            "outcome": {
                "type": "string",
                "enum": ["checkpoint", "completed", "blocked", "unknown"],
            },
            "artifact_refs": {"type": "array", "items": {"type": "string"}},
            "checkpoint_refs": {"type": "array", "items": {"type": "string"}},
            "remaining": {"type": "array", "items": {"type": "string"}},
            "next_action": {"type": "string", "minLength": 1},
            "budget_usage": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": [
                    "elapsed_seconds",
                    "tokens_used",
                    "estimated_cost_usd",
                ],
                "properties": {
                    "elapsed_seconds": {"type": ["number", "null"]},
                    "tokens_used": {"type": ["integer", "null"]},
                    "estimated_cost_usd": {"type": ["number", "null"]},
                },
            },
        },
    }


def validate_control_receipt(payload: Any) -> dict[str, Any]:
    required_keys = {
        "schema",
        "root_objective_id",
        "status",
        "actions_taken",
        "dispatched_attempts",
        "needs_human_action",
        "summary",
        "next_step",
    }
    if not isinstance(payload, dict) or set(payload) != required_keys:
        raise BridgeError("control turn receipt schema or fields are invalid")
    if payload.get("schema") != CONTROL_RECEIPT_SCHEMA_NAME:
        raise BridgeError("control turn receipt schema version mismatch")
    if payload.get("root_objective_id") is not None and not isinstance(payload["root_objective_id"], str):
        raise BridgeError("control turn receipt root_objective_id is invalid")
    if payload.get("status") not in {"completed", "dispatched", "waiting_user", "blocked", "noop"}:
        raise BridgeError("control turn receipt status is invalid")
    for list_field in ("actions_taken", "dispatched_attempts"):
        val = payload.get(list_field)
        if not isinstance(val, list) or not all(isinstance(item, str) for item in val):
            raise BridgeError(f"control turn receipt {list_field} must be a list of strings")
    if not isinstance(payload.get("needs_human_action"), bool):
        raise BridgeError("control turn receipt needs_human_action must be boolean")
    for str_field in ("summary", "next_step"):
        val = payload.get(str_field)
        if not isinstance(val, str) or not val.strip():
            raise BridgeError(f"control turn receipt {str_field} must be a non-empty string")
    return deepcopy(payload)


def _control_prompt(plan: dict[str, Any], *, instance_root: Path | None) -> str:
    sanitized_view = {
        "root_objective_id": plan.get("root_objective_id"),
        "trigger_event_ids": plan.get("trigger_event_ids", []),
        "graph_summary": plan.get("graph_summary", {}),
        "callbacks_processed": plan.get("callbacks_processed", []),
        "fan_out_batch": plan.get("fan_out_batch", []),
        "integration_queue": plan.get("integration_queue", []),
        "needs_repair": plan.get("needs_repair", []),
        "blocked_or_waiting": plan.get("blocked_or_waiting", []),
        "recommended_actions": plan.get("recommended_actions", []),
        "validation_errors": plan.get("validation_errors", []),
    }
    instance_hint = str(instance_root) if instance_root is not None else "configured OPL Instance"
    return (
        "你是 OPL Flow 的无状态逻辑项目总控轮次（Control Turn）。\n"
        "目标：依据下方的控制面事件计划与 Beads 总账事实，执行当前轮次所需的验收、断点修复或并发派发，然后立即退出（不保留常驻对话）。\n"
        "硬性约束：\n"
        "1. Beads/Dolt 是唯一任务真相；优先调用 `python3 scripts/opl_fleet.py dispatch run/group` 派发就绪切片。\n"
        "2. `integration_queue` 中的写集重叠切片只允许在独立 worktree 并行开发，吸收必须在主线短临界区串行。\n"
        "3. `needs_repair` 必须优先执行 owner 侧修复（Repair-Before-Proof），不得只重跑测试。\n"
        "4. 若遇需要用户拍板/登录/授权或外部阻塞，准确标记 status=`waiting_user`/`blocked` 与 `needs_human_action=true`。\n"
        "5. 最终输出必须严格符合 `--output-schema` JSON。\n\n"
        f"Instance 路径: {instance_hint}\n"
        f"Flow 仓库路径: {flow_root()}\n\n"
        "控制轮次输入 (opl_control_turn_plan.v1):\n"
        f"{json.dumps(sanitized_view, ensure_ascii=False, indent=2)}\n"
    )


def _worker_prompt(
    handoff: dict[str, Any],
    binding: dict[str, str],
    context_manifest: dict[str, Any] | None = None,
) -> str:
    details = {
        "binding": binding,
        "objective_revision": handoff.get("objective_revision"),
        "scope": handoff["scope"],
        "expected_result": handoff["expected_result"],
        "write_set": handoff.get("write_set", []),
        "input_refs": handoff["input_refs"],
        "checkpoint_refs": handoff["checkpoint_refs"],
        "envelope": handoff.get("envelope"),
        "resumability": handoff.get("resumability"),
        "context_manifest_verified_refs": (context_manifest or {}).get("verified_refs", []),
    }
    return (
        "你是 OPL Flow 委派的有限切片 Worker。\n"
        "请在授权写集与包络约束内完成下方 `scope`，验证交付证据，并严格按照 `--output-schema` 返回 `opl_worker_result.v1` JSON。\n"
        "硬性约束：\n"
        "1. 返回 JSON 的 `binding` 字段必须原样等于下方给定的 `binding`。\n"
        "2. 仅当全部工作完成且至少有一条可回读 `artifact_refs`、同时 `remaining=[]` 时，才可返回 `outcome=\"completed\"`。\n"
        "3. 若未全部完成但已留下可恢复进展，返回 `outcome=\"checkpoint\"` 并填写 `checkpoint_refs` 与 `remaining`。\n"
        "4. 若缺少权限、凭据或遇到外部阻塞，返回 `outcome=\"blocked\"`，切勿编造结果或绕过权限。\n\n"
        "Worker 交接单 (opl_worker_handoff.v1):\n"
        f"{json.dumps(details, ensure_ascii=False, indent=2)}\n"
    )


def _run_codex_exec(
    argv: list[str],
    *,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
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
    if (
        not plan.get("needs_agent_reasoning")
        and not plan.get("fan_out_batch")
        and not plan.get("recommended_actions")
        and not plan.get("validation_errors")
    ):
        return {
            "schema": CONTROL_RECEIPT_SCHEMA_NAME,
            "root_objective_id": plan.get("root_objective_id"),
            "status": "noop",
            "actions_taken": [],
            "dispatched_attempts": [],
            "needs_human_action": False,
            "summary": "No actionable graph transitions or reasoning required.",
            "next_step": "Remain idle until next event.",
        }

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


def _strip_null_worker_optionals(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(payload)
    if "budget_usage" in cleaned:
        usage = cleaned["budget_usage"]
        if usage is None:
            cleaned.pop("budget_usage")
        elif isinstance(usage, dict):
            non_null = {k: v for k, v in usage.items() if v is not None}
            if non_null:
                cleaned["budget_usage"] = non_null
            else:
                cleaned.pop("budget_usage")
    return cleaned


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


def _load_json_arg(value: str | None, *, fallback_stdin: bool = False, env_var: str | None = None) -> Any:
    raw_text: str | None = None
    if value is not None:
        if value.startswith("@"):
            path = Path(value[1:]).expanduser()
            if not path.is_file():
                raise BridgeError(f"JSON input file not found: {path}")
            raw_text = path.read_text(encoding="utf-8")
        else:
            raw_text = value
    elif env_var and os.environ.get(env_var):
        path = Path(os.environ[env_var]).expanduser()
        if not path.is_file():
            raise BridgeError(f"JSON file from {env_var} not found: {path}")
        raw_text = path.read_text(encoding="utf-8")
    elif fallback_stdin:
        raw_text = sys.stdin.read()

    if raw_text is None or not raw_text.strip():
        raise BridgeError("missing JSON input payload")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BridgeError("input payload is not valid JSON") from exc


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
