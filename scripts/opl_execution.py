"""Carrier-neutral Worker handoffs and admission evidence. No I/O or task store."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import hashlib
import json
import re


class ExecutionError(ValueError):
    pass


def identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 512 or any(c in value for c in '\x00\r\n'):
        raise ExecutionError(f'{label} must be a non-empty bounded reference')
    return value


def references(value: Any, label: str, *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise ExecutionError(f'{label} must be a list of references')
    return [identity(item, label) for item in value]


def validate_handoff(value: Any) -> dict[str, Any]:
    fields = {'schema', 'attempt_id', 'objective_id', 'owner_id', 'scope', 'input_refs', 'checkpoint_refs', 'expected_result'}
    if not isinstance(value, dict) or set(value) != fields or value.get('schema') != 'opl_worker_handoff.v1':
        raise ExecutionError('worker handoff schema or fields are invalid')
    if len(json.dumps(value).encode()) > 32768:
        raise ExecutionError('worker handoff exceeds size limit')
    for field in ('attempt_id', 'objective_id', 'owner_id', 'scope', 'expected_result'):
        identity(value[field], field)
    for field in ('input_refs', 'checkpoint_refs'):
        references(value[field], field)
    return deepcopy(value)


def handoff_binding(value: Any) -> dict[str, str]:
    handoff = validate_handoff(value)
    return {
        'attempt_id': handoff['attempt_id'],
        'objective_id': handoff['objective_id'],
        'owner_id': handoff['owner_id'],
        'handoff_sha256': hashlib.sha256(json.dumps(handoff, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
    }


def validate_result(value: Any, handoff: Any) -> dict[str, Any]:
    expected = handoff_binding(handoff)
    fields = {'schema', 'binding', 'outcome', 'artifact_refs', 'checkpoint_refs', 'remaining', 'next_action'}
    if not isinstance(value, dict) or set(value) != fields or value.get('schema') != 'opl_worker_result.v1':
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
    return deepcopy(value)


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
