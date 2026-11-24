"""Carrier-neutral Worker handoffs and admission evidence. No I/O or task store."""
from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any
import hashlib
import json
import re


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


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


def validate_envelope(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("worker handoff envelope must be an object")
    allowed = {
        "allowed_write_paths",
        "allowed_tools",
        "allow_network",
        "allow_destructive",
        "max_duration_seconds",
        "max_tokens",
        "max_cost_usd",
        "credential_refs",
    }
    if set(value) - allowed:
        raise ExecutionError("worker handoff envelope contains unsupported fields")
    if "allowed_write_paths" in value:
        paths = value["allowed_write_paths"]
        if not isinstance(paths, list):
            raise ExecutionError("envelope allowed_write_paths must be a list")
        normalized = [validate_relative_path(item, "allowed_write_paths") for item in paths]
        if len(normalized) != len(set(normalized)):
            raise ExecutionError("envelope allowed_write_paths must be unique")
    if "allowed_tools" in value:
        tools = references(value["allowed_tools"], "allowed_tools")
        for tool in tools:
            if len(tool) > 128:
                raise ExecutionError("envelope allowed_tools entry exceeds length limit")
            _check_no_raw_secret(tool, "allowed_tools")
        if len(tools) != len(set(tools)):
            raise ExecutionError("envelope allowed_tools must be unique")
    for bool_field in ("allow_network", "allow_destructive"):
        if bool_field in value and not isinstance(value[bool_field], bool):
            raise ExecutionError(f"envelope {bool_field} must be a boolean")
    if "max_duration_seconds" in value:
        dur = value["max_duration_seconds"]
        if not _is_int(dur) or not 1 <= dur <= 86400:
            raise ExecutionError("envelope max_duration_seconds is invalid")
    if "max_tokens" in value:
        tokens = value["max_tokens"]
        if not _is_int(tokens) or tokens < 1:
            raise ExecutionError("envelope max_tokens is invalid")
    if "max_cost_usd" in value:
        cost = value["max_cost_usd"]
        if not _is_number(cost) or cost < 0:
            raise ExecutionError("envelope max_cost_usd is invalid")
    if "credential_refs" in value:
        refs = value["credential_refs"]
        if not isinstance(refs, list):
            raise ExecutionError("envelope credential_refs must be a list")
        seen: set[str] = set()
        for item in refs:
            if not isinstance(item, str):
                raise ExecutionError("envelope credential_refs entry must be a string")
            _check_no_raw_secret(item, "credential_refs")
            if not CREDENTIAL_REF_PATTERN.fullmatch(item):
                raise ExecutionError("envelope credential_refs must use opaque cred: references")
            if item in seen:
                raise ExecutionError("envelope credential_refs must be unique")
            seen.add(item)
    return deepcopy(value)


def validate_resumability(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionError("worker handoff resumability must be an object")
    allowed = {
        "checkpointable",
        "heartbeat_interval_seconds",
        "max_stale_seconds",
        "interruptible_phase",
        "resume_command_ref",
    }
    if "checkpointable" not in value or set(value) - allowed:
        raise ExecutionError("worker handoff resumability schema or fields are invalid")
    if not isinstance(value["checkpointable"], bool):
        raise ExecutionError("resumability checkpointable must be a boolean")
    heartbeat = value.get("heartbeat_interval_seconds")
    stale = value.get("max_stale_seconds")
    if heartbeat is not None and (not _is_int(heartbeat) or not 10 <= heartbeat <= 3600):
        raise ExecutionError("resumability heartbeat_interval_seconds is invalid")
    if stale is not None and (not _is_int(stale) or not 30 <= stale <= 86400):
        raise ExecutionError("resumability max_stale_seconds is invalid")
    if heartbeat is not None and stale is not None and stale < heartbeat:
        raise ExecutionError("resumability max_stale_seconds must be >= heartbeat_interval_seconds")
    if "interruptible_phase" in value and value["interruptible_phase"] not in {
        "interruptible",
        "non-interruptible",
    }:
        raise ExecutionError("resumability interruptible_phase is invalid")
    if "resume_command_ref" in value:
        identity(value["resume_command_ref"], "resume_command_ref")
    return deepcopy(value)


def validate_handoff(value: Any) -> dict[str, Any]:
    required_fields = {
        'schema',
        'attempt_id',
        'objective_id',
        'owner_id',
        'scope',
        'input_refs',
        'checkpoint_refs',
        'expected_result',
    }
    optional_fields = {
        'objective_revision',
        'write_set',
        'envelope',
        'resumability',
    }
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or (set(value) - required_fields - optional_fields)
        or value.get('schema') != 'opl_worker_handoff.v1'
    ):
        raise ExecutionError('worker handoff schema or fields are invalid')
    if len(json.dumps(value).encode()) > 32768:
        raise ExecutionError('worker handoff exceeds size limit')
    for field in ('attempt_id', 'objective_id', 'owner_id', 'scope', 'expected_result'):
        identity(value[field], field)
    for field in ('input_refs', 'checkpoint_refs'):
        references(value[field], field)
    if 'objective_revision' in value:
        rev = value['objective_revision']
        if not _is_int(rev) or rev < 1:
            raise ExecutionError('objective_revision must be a positive integer')
    if 'write_set' in value:
        raw_write_set = value['write_set']
        if not isinstance(raw_write_set, list):
            raise ExecutionError('write_set must be a list of relative paths')
        normalized = [validate_relative_path(item, 'write_set') for item in raw_write_set]
        if len(normalized) != len(set(normalized)):
            raise ExecutionError('write_set entries must be unique')
    if 'envelope' in value:
        validate_envelope(value['envelope'])
    if 'resumability' in value:
        validate_resumability(value['resumability'])
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
    allowed = {"elapsed_seconds", "tokens_used", "estimated_cost_usd"}
    if set(value) - allowed:
        raise ExecutionError("budget_usage contains unsupported fields")
    if "elapsed_seconds" in value and (not _is_number(value["elapsed_seconds"]) or value["elapsed_seconds"] < 0):
        raise ExecutionError("budget_usage elapsed_seconds is invalid")
    if "tokens_used" in value and (not _is_int(value["tokens_used"]) or value["tokens_used"] < 0):
        raise ExecutionError("budget_usage tokens_used is invalid")
    if "estimated_cost_usd" in value and (
        not _is_number(value["estimated_cost_usd"]) or value["estimated_cost_usd"] < 0
    ):
        raise ExecutionError("budget_usage estimated_cost_usd is invalid")
    return deepcopy(value)


def validate_result(value: Any, handoff: Any) -> dict[str, Any]:
    expected = handoff_binding(handoff)
    required_fields = {'schema', 'binding', 'outcome', 'artifact_refs', 'checkpoint_refs', 'remaining', 'next_action'}
    optional_fields = {'budget_usage', 'checkpoint_digests'}
    if (
        not isinstance(value, dict)
        or not required_fields.issubset(value)
        or (set(value) - required_fields - optional_fields)
        or value.get('schema') != 'opl_worker_result.v1'
    ):
        raise ExecutionError('worker result schema or fields are invalid')
    if value['binding'] != expected:
        raise ExecutionError('worker result does not match the handoff')
    if not isinstance(value['outcome'], str) or value['outcome'] not in {'checkpoint', 'completed', 'blocked', 'unknown'}:
        raise ExecutionError('worker result outcome is invalid')
    references(value['artifact_refs'], 'artifact_refs')
    references(value['checkpoint_refs'], 'checkpoint_refs', required=value['outcome'] == 'checkpoint')
    references(value['remaining'], 'remaining')
    identity(value['next_action'], 'next_action')
    if value['outcome'] == 'completed' and (value['remaining'] or not value['artifact_refs']):
        raise ExecutionError('completed worker slice requires evidence and no remaining work')
    if 'budget_usage' in value:
        _validate_budget_usage(value['budget_usage'])
    if 'checkpoint_digests' in value:
        digests = value['checkpoint_digests']
        if not isinstance(digests, dict):
            raise ExecutionError('checkpoint_digests must be an object')
        for ref, digest_hex in digests.items():
            identity(ref, 'checkpoint_digests key')
            if not isinstance(digest_hex, str) or not SHA256_PATTERN.fullmatch(digest_hex):
                raise ExecutionError('checkpoint_digests values must be 64-hex sha256 strings')
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
