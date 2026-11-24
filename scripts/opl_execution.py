"""Carrier-neutral Worker handoffs and admission evidence. No I/O or task store."""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
import hashlib
import json
import re

try:
    from . import opl_runtime as runtime
except ImportError:  # Direct script execution.
    import opl_runtime as runtime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator


class ExecutionError(ValueError):
    pass


CREDENTIAL_REF_PATTERN = re.compile(r"^cred:[a-z0-9][a-z0-9._:/-]{0,127}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
RAW_SECRET_PATTERN = re.compile(
    r"(?:^|[\s=:'\"])(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{6,}|glpat-[A-Za-z0-9_-]{6,}|AKIA[0-9A-Z]{8,}|Bearer\s+\S{6,}|-----BEGIN\s+)"
)
FORBIDDEN_PRIVACY_KEYS = frozenset(
    {
        "prompt",
        "response",
        "content",
        "conversation_content",
        "raw_prompt",
        "raw_response",
        "raw_content",
        "session_id",
        "local_path",
        "interface",
        "interface_name",
        "address",
        "network_address",
        "credential",
        "secret",
        "raw_log",
    }
)


def _check_no_raw_secret(value: str, label: str) -> None:
    if RAW_SECRET_PATTERN.search(value):
        raise ExecutionError(f"{label} appears to contain a raw secret value")


def validate_relative_path(path_str: Any, label: str = "path") -> str:
    text = identity(path_str, label)
    if text.startswith("/") or "\\" in text:
        raise ExecutionError(f"{label} must be a repository-relative POSIX path")
    posix = PurePosixPath(text)
    if posix.is_absolute() or ".." in posix.parts or text in {".", "./"}:
        raise ExecutionError(f"{label} must not traverse outside the repository root")
    return posix.as_posix()


def identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512 or any(c in value for c in '\x00\r\n'):
        raise ExecutionError(f'{label} must be a non-empty bounded reference')
    return value


def references(value: Any, label: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ExecutionError(f'{label} must be a list of references')
    return [identity(item, label) for item in value]


StrictNum = StrictInt | StrictFloat
Sha256Str = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
CommitStr = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{40}$")]


class _EnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_write_paths: list[Any] | None = None
    allowed_tools: list[Any] | None = None
    allow_network: StrictBool | None = None
    allow_destructive: StrictBool | None = None
    max_duration_seconds: Annotated[StrictInt, Field(ge=1, le=86400)] | None = None
    max_tokens: Annotated[StrictInt, Field(ge=1)] | None = None
    max_cost_usd: Annotated[StrictNum, Field(ge=0)] | None = None
    credential_refs: list[StrictStr] | None = None

    @field_validator("allowed_write_paths")
    @classmethod
    def _check_paths(cls, paths: list[Any] | None) -> list[str] | None:
        if paths is None:
            return None
        normalized = [validate_relative_path(item, "allowed_write_paths") for item in paths]
        if len(normalized) != len(set(normalized)):
            raise ValueError("envelope allowed_write_paths must be unique")
        return normalized

    @field_validator("allowed_tools")
    @classmethod
    def _check_tools(cls, tools: list[Any] | None) -> list[str] | None:
        if tools is None:
            return None
        validated = references(tools, "allowed_tools")
        for tool in validated:
            if len(tool) > 128:
                raise ValueError("envelope allowed_tools entry exceeds length limit")
            _check_no_raw_secret(tool, "allowed_tools")
        if len(validated) != len(set(validated)):
            raise ValueError("envelope allowed_tools must be unique")
        return validated

    @field_validator("credential_refs")
    @classmethod
    def _check_creds(cls, refs: list[str] | None) -> list[str] | None:
        if refs is None:
            return None
        for item in refs:
            _check_no_raw_secret(item, "credential_refs")
            if not CREDENTIAL_REF_PATTERN.fullmatch(item):
                raise ValueError("envelope credential_refs must use opaque cred: references")
        if len(refs) != len(set(refs)):
            raise ValueError("envelope credential_refs must be unique")
        return refs


class _ResumabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpointable: StrictBool
    heartbeat_interval_seconds: Annotated[StrictInt, Field(ge=10, le=3600)] | None = None
    max_stale_seconds: Annotated[StrictInt, Field(ge=30, le=86400)] | None = None
    interruptible_phase: Literal["interruptible", "non-interruptible"] | None = None
    resume_command_ref: StrictStr | None = None

    @field_validator("resume_command_ref")
    @classmethod
    def _check_resume_ref(cls, value: str | None) -> str | None:
        return identity(value, "resume_command_ref") if value is not None else None

    @model_validator(mode="after")
    def _check_stale_ge_hb(self) -> "_ResumabilityModel":
        if self.heartbeat_interval_seconds is not None and self.max_stale_seconds is not None:
            if self.max_stale_seconds < self.heartbeat_interval_seconds:
                raise ValueError("resumability max_stale_seconds must be >= heartbeat_interval_seconds")
        return self


class _HandoffModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal["opl_worker_handoff.v1"] = Field(alias="schema")
    attempt_id: StrictStr
    objective_id: StrictStr
    owner_id: StrictStr
    scope: StrictStr
    input_refs: list[StrictStr]
    checkpoint_refs: list[StrictStr]
    expected_result: StrictStr
    objective_revision: Annotated[StrictInt, Field(ge=1)] | None = None
    write_set: list[StrictStr] | None = None
    envelope: _EnvelopeModel | None = None
    resumability: _ResumabilityModel | None = None

    @field_validator("attempt_id", "objective_id", "owner_id", "scope", "expected_result")
    @classmethod
    def _check_identities(cls, value: str, info: Any) -> str:
        return identity(value, info.field_name)

    @field_validator("input_refs", "checkpoint_refs")
    @classmethod
    def _check_refs(cls, value: list[str], info: Any) -> list[str]:
        return references(value, info.field_name)

    @field_validator("write_set")
    @classmethod
    def _check_write_set(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [validate_relative_path(item, "write_set") for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("write_set entries must be unique")
        return normalized


class _BudgetUsageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elapsed_seconds: Annotated[StrictNum, Field(ge=0)] | None = None
    tokens_used: Annotated[StrictInt, Field(ge=0)] | None = None
    estimated_cost_usd: Annotated[StrictNum, Field(ge=0)] | None = None


class _WorkerResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal["opl_worker_result.v1"] = Field(alias="schema")
    binding: dict[str, Any]
    outcome: Literal["checkpoint", "completed", "blocked", "unknown"]
    artifact_refs: list[StrictStr]
    checkpoint_refs: list[StrictStr]
    remaining: list[StrictStr]
    next_action: StrictStr
    budget_usage: _BudgetUsageModel | None = None
    checkpoint_digests: dict[StrictStr, Sha256Str] | None = None

    @field_validator("next_action")
    @classmethod
    def _check_next_action(cls, value: str) -> str:
        return identity(value, "next_action")

    @field_validator("artifact_refs", "remaining")
    @classmethod
    def _check_ref_lists(cls, value: list[str], info: Any) -> list[str]:
        return references(value, info.field_name)

    @field_validator("checkpoint_digests")
    @classmethod
    def _check_digest_keys(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is not None:
            for key in value:
                identity(key, "checkpoint_digests key")
        return value

    @model_validator(mode="after")
    def _check_outcome_invariants(self) -> "_WorkerResultModel":
        references(self.checkpoint_refs, "checkpoint_refs", required=self.outcome == "checkpoint")
        if self.outcome == "completed" and (self.remaining or not self.artifact_refs):
            raise ValueError("completed worker slice requires evidence and no remaining work")
        return self


def validate_envelope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("worker handoff envelope must be an object")
    runtime.validate_model(_EnvelopeModel, value, error_cls=ExecutionError)
    return deepcopy(value)


def validate_resumability(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("worker handoff resumability must be an object")
    runtime.validate_model(_ResumabilityModel, value, error_cls=ExecutionError)
    return deepcopy(value)


def validate_handoff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("worker handoff schema or fields are invalid")
    if len(json.dumps(value).encode()) > 32768:
        raise ExecutionError("worker handoff exceeds size limit")
    runtime.validate_model(_HandoffModel, value, error_cls=ExecutionError)
    return deepcopy(value)


def handoff_binding(value: Any) -> dict[str, str]:
    handoff = validate_handoff(value)
    return {
        'attempt_id': handoff['attempt_id'],
        'objective_id': handoff['objective_id'],
        'owner_id': handoff['owner_id'],
        'handoff_sha256': hashlib.sha256(json.dumps(handoff, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
    }


def _validate_budget_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("budget_usage must be an object")
    runtime.validate_model(_BudgetUsageModel, value, error_cls=ExecutionError)
    return deepcopy(value)


def validate_result(value: Any, handoff: Any) -> dict[str, Any]:
    expected = handoff_binding(handoff)
    if not isinstance(value, dict):
        raise ExecutionError("worker result schema or fields are invalid")
    if value.get("binding") != expected:
        raise ExecutionError("worker result does not match the handoff")
    runtime.validate_model(_WorkerResultModel, value, error_cls=ExecutionError)
    return deepcopy(value)


def _path_within_allowed(path_str: str, allowed_prefixes: list[str]) -> bool:
    norm = validate_relative_path(path_str, "write_set")
    norm_parts = PurePosixPath(norm).parts
    for prefix in allowed_prefixes:
        clean_prefix = validate_relative_path(prefix.rstrip("/") or ".", "allowed_write_paths")
        prefix_parts = PurePosixPath(clean_prefix).parts
        if len(norm_parts) >= len(prefix_parts) and norm_parts[: len(prefix_parts)] == prefix_parts:
            return True
    return False


def enforce_pre_execution_envelope(
    handoff: dict[str, Any],
    *,
    ttl_seconds: int | None = None,
    requested_tools: list[str] | tuple[str, ...] | None = None,
    requires_network: bool = False,
    destructive: bool = False,
) -> dict[str, Any]:
    validated = validate_handoff(handoff)
    envelope = validated.get("envelope") or {}
    if not envelope:
        return {"enforced": False, "reason": "no_envelope_declared"}

    if "allowed_write_paths" in envelope and "write_set" in validated:
        allowed_paths = envelope["allowed_write_paths"]
        for target in validated["write_set"]:
            if not _path_within_allowed(target, allowed_paths):
                raise ExecutionError(f"write_set path '{target}' is outside envelope allowed_write_paths")

    if ttl_seconds is not None and "max_duration_seconds" in envelope:
        if ttl_seconds > int(envelope["max_duration_seconds"]):
            raise ExecutionError(
                f"requested ttl_seconds ({ttl_seconds}) exceeds envelope max_duration_seconds ({envelope['max_duration_seconds']})"
            )

    if requested_tools and "allowed_tools" in envelope:
        allowed_tool_set = set(envelope["allowed_tools"])
        disallowed = [tool for tool in requested_tools if tool not in allowed_tool_set]
        if disallowed:
            raise ExecutionError(f"requested tools outside envelope allowed_tools: {', '.join(disallowed)}")

    if requires_network and envelope.get("allow_network") is False:
        raise ExecutionError("network access is forbidden by handoff envelope")

    if destructive and envelope.get("allow_destructive") is False:
        raise ExecutionError("destructive mutation is forbidden by handoff envelope")

    return {
        "enforced": True,
        "has_write_bounds": "allowed_write_paths" in envelope,
        "max_duration_seconds": envelope.get("max_duration_seconds"),
        "max_tokens": envelope.get("max_tokens"),
        "max_cost_usd": envelope.get("max_cost_usd"),
        "credential_ref_count": len(envelope.get("credential_refs", [])),
    }


def evaluate_budget_usage(handoff: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    validated_handoff = validate_handoff(handoff)
    validated_result = validate_result(result, validated_handoff)
    envelope = validated_handoff.get("envelope") or {}
    usage = validated_result.get("budget_usage") or {}
    violations: list[str] = []

    if "max_duration_seconds" in envelope and "elapsed_seconds" in usage:
        if float(usage["elapsed_seconds"]) > float(envelope["max_duration_seconds"]):
            violations.append(
                f"elapsed_seconds ({usage['elapsed_seconds']}) exceeded max_duration_seconds ({envelope['max_duration_seconds']})"
            )
    if "max_tokens" in envelope and "tokens_used" in usage:
        if int(usage["tokens_used"]) > int(envelope["max_tokens"]):
            violations.append(
                f"tokens_used ({usage['tokens_used']}) exceeded max_tokens ({envelope['max_tokens']})"
            )
    if "max_cost_usd" in envelope and "estimated_cost_usd" in usage:
        if float(usage["estimated_cost_usd"]) > float(envelope["max_cost_usd"]):
            violations.append(
                f"estimated_cost_usd ({usage['estimated_cost_usd']}) exceeded max_cost_usd ({envelope['max_cost_usd']})"
            )

    return {"within_budget": not violations, "violations": violations, "usage": usage}


def sanitize_check(
    payload: Any,
    *,
    forbidden_keys: frozenset[str] | set[str] | None = None,
    label: str = "payload",
) -> None:
    forbidden = FORBIDDEN_PRIVACY_KEYS if forbidden_keys is None else frozenset(forbidden_keys)

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                key_str = str(key)
                if key_str in forbidden or key_str.lower() in forbidden:
                    raise ExecutionError(f"{label} contains forbidden privacy field: {path}.{key_str}")
                _walk(value, f"{path}.{key_str}")
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, f"{path}[{idx}]")
        elif isinstance(node, str):
            _check_no_raw_secret(node, path)

    _walk(payload, label)


def workspace_evidence(value: Any, *, profile_id: str, node_id: str) -> dict[str, str]:
    if not isinstance(value, dict) or value.get('schema') != 'opl_execution_workspace.v1' or value.get('profile_id') != profile_id or value.get('node_id') != node_id or value.get('ready') is not True:
        raise ExecutionError('target workspace is not claim-ready')
    result = {field: value.get(field) for field in ('workspace_fingerprint', 'environment_fingerprint', 'repository_fingerprint')}
    if any(not isinstance(item, str) or not re.fullmatch('[0-9a-f]{64}', item) for item in result.values()):
        raise ExecutionError('target workspace fingerprints are invalid')
    return {'checked_at': identity(value.get('checked_at'), 'checked_at'), **result}


def node_evidence(value: Any, *, node_id: str, objective_id: str) -> dict[str, str]:
    if not isinstance(value, dict) or value.get('schema') != 'opl_execution_admission.v1' or value.get('node_id') != node_id or value.get('objective_id') != objective_id or value.get('ready') is not True:
        raise ExecutionError('target node is not admitted for owner migration')
    revision = value.get('control_commit')
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ExecutionError('target node control revision is invalid')
    return {'node_checked_at': identity(value.get('checked_at'), 'checked_at'), 'control_commit': revision}
