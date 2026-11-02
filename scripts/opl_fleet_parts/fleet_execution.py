"""Translate Fleet receipts to carrier-neutral execution evidence."""
from __future__ import annotations
from typing import Any


def workspace_evidence(value: Any, *, node_id: str) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        'schema': 'opl_execution_workspace.v1',
        'profile_id': value.get('profile_id'), 'node_id': node_id,
        'ready': (value.get('schema') == 'opl_fleet_workspace_readback.v1'
                  and isinstance(value.get('node_ids'), list) and node_id in value['node_ids']
                  and value.get('state') == 'CURRENT' and value.get('claim_ready') is True
                  and value.get('fresh_fetch') is True and value.get('fresh_github') is True),
        'checked_at': value.get('observed_at'),
        'workspace_fingerprint': value.get('profile_fingerprint'),
        'environment_fingerprint': value.get('environment_fingerprint'),
        'repository_fingerprint': value.get('repository_fingerprint'),
    }


def node_evidence(value: Any, *, objective_id: str) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    lease = value.get('lease')
    capacity_owned = isinstance(lease, dict) and lease.get('owner_task') == objective_id
    return {
        'schema': 'opl_execution_admission.v1',
        'node_id': value.get('node_id'), 'objective_id': objective_id,
        'ready': (value.get('schema') == 'codex_fleet_doctor.v1'
                  and value.get('admission_ready') is True
                  and (value.get('ready_for_dispatch') is True or capacity_owned)
                  and value.get('receipt_state') == 'CURRENT' and value.get('control_current') is True),
        'checked_at': value.get('checked_at'), 'control_commit': value.get('current_control_commit'),
    }
