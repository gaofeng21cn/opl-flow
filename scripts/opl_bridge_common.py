#!/usr/bin/env python3
"""Shared carrier-neutral prompt, schema, sandbox, and receipt helpers for OPL Flow bridges.

Zero Fleet imports.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Literal

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, field_validator


CONTROL_RECEIPT_SCHEMA_NAME = "opl_control_turn_receipt.v1"
SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")


class BridgeError(RuntimeError):
    """Raised when a bridge invocation violates schema, boundary, or runtime guarantees."""


def flow_root() -> Path:
    return Path(__file__).resolve().parents[1]


def control_receipt_schema_path() -> Path:
    return flow_root() / "contracts" / "control-turn-receipt.schema.json"


def resolve_sandbox_mode(
    handoff: dict[str, Any] | None = None,
    *,
    explicit_sandbox: str | None = None,
) -> str:
    """Resolve sandbox posture from explicit choice or handoff envelope without bypassing guards."""
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
    """Return a strict JSON schema matching opl_worker_result.v1."""
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


class _ControlTurnReceiptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["opl_control_turn_receipt.v1"] = ...
    root_objective_id: StrictStr | None
    status: Literal["completed", "dispatched", "waiting_user", "blocked", "noop"]
    actions_taken: list[StrictStr]
    dispatched_attempts: list[StrictStr]
    needs_human_action: StrictBool
    summary: StrictStr
    next_step: StrictStr

    @field_validator("summary", "next_step")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must be a non-empty string")
        return value


def validate_control_receipt(payload: Any) -> dict[str, Any]:
    """Validate control turn output against opl_control_turn_receipt.v1."""
    if not isinstance(payload, dict):
        raise BridgeError("control turn receipt schema or fields are invalid")
    data = dict(payload)
    if "schema" in data:
        data["schema_version"] = data.pop("schema")
    runtime.validate_model(
        _ControlTurnReceiptModel,
        data,
        error_cls=BridgeError,
        message="control turn receipt schema or fields are invalid",
    )
    return deepcopy(payload)


def strip_null_worker_optionals(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove explicit null optional budget_usage fields before opl_execution validation."""
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


def is_noop_control_plan(plan: dict[str, Any]) -> bool:
    """Return True when control turn requires zero LLM reasoning or actions."""
    return (
        not plan.get("needs_agent_reasoning")
        and not plan.get("fan_out_batch")
        and not plan.get("recommended_actions")
        and not plan.get("validation_errors")
    )


def noop_control_receipt(plan: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic zero-token receipt for idle control plans."""
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


def control_prompt(plan: dict[str, Any], *, instance_root: Path | None) -> str:
    """Build sanitized prompt for stateless Control Turn execution across supported adapters."""
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
        "   - 若切片 `requirements.adapter == \"local-antigravity\"`（或 `preferred_adapter == \"local-antigravity\"`），使用 `--adapter local-antigravity --use-antigravity-bridge`。\n"
        "   - 若切片 `requirements.adapter == \"local-dsh\"`（或 `preferred_adapter == \"local-dsh\"`），使用 `--adapter local-dsh --use-dsh-bridge`（可按需搭配 `--dsh-combination` 调度 OPL DSH 多模型编排，如 agy + Gemini）。\n"
        "   - 若切片 `requirements.adapter == \"local-codex\"` 或未指定，默认使用 `--adapter local-codex --use-codex-bridge`（或按配置路由远端节点）；支持在同一任务图中混合并发 Fan-Out。\n"
        "2. `integration_queue` 中的写集重叠或活跃本地对话撞车保护（`worktree_required_active_local_session`）切片只允许在独立 worktree 并行开发，吸收必须在主线短临界区串行；同一 attempt 严禁同时在 Codex、AntiGravity 或 DSH 多端并发写入。\n"
        "3. `needs_repair` 必须优先执行 owner 侧修复（Repair-Before-Proof），不得只重跑测试。\n"
        "4. 若遇需要用户拍板/登录/授权或外部阻塞，准确标记 status=`waiting_user`/`blocked` 与 `needs_human_action=true`。\n"
        "5. 最终输出必须严格符合输出 JSON Schema。\n\n"
        f"Instance 路径: {instance_hint}\n"
        f"Flow 仓库路径: {flow_root()}\n\n"
        "控制轮次输入 (opl_control_turn_plan.v1):\n"
        f"{json.dumps(sanitized_view, ensure_ascii=False, indent=2)}\n"
    )


def worker_prompt(
    handoff: dict[str, Any],
    binding: dict[str, str],
    context_manifest: dict[str, Any] | None = None,
) -> str:
    """Build sanitized prompt for bounded worker slice execution."""
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
        "请在授权写集与包络约束内完成下方 `scope`，验证交付证据，并严格按照输出 Schema 返回 `opl_worker_result.v1` JSON。\n"
        "硬性约束：\n"
        "1. 返回 JSON 的 `binding` 字段必须原样等于下方给定的 `binding`。\n"
        "2. 仅当全部工作完成且至少有一条可回读 `artifact_refs`、同时 `remaining=[]` 时，才可返回 `outcome=\"completed\"`。\n"
        "3. 若未全部完成但已留下可恢复进展，返回 `outcome=\"checkpoint\"` 并填写 `checkpoint_refs` 与 `remaining`。\n"
        "4. 若缺少权限、凭据或遇到外部阻塞，返回 `outcome=\"blocked\"`，切勿编造结果或绕过权限。\n\n"
        "Worker 交接单 (opl_worker_handoff.v1):\n"
        f"{json.dumps(details, ensure_ascii=False, indent=2)}\n"
    )


def load_json_arg(
    value: str | None,
    *,
    fallback_stdin: bool = False,
    env_var: str | None = None,
) -> Any:
    """Load a JSON argument from inline JSON, @file path, env var file, or stdin."""
    import sys

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
