from __future__ import annotations
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import opl_execution as execution
from scripts.opl_fleet_parts import fleet_execution
from tests.test_opl_fleet import fleet, patch_fleet

ROOT = Path(__file__).resolve().parents[1]


def handoff():
    return {'schema': 'opl_worker_handoff.v1', 'attempt_id': 'attempt-1', 'objective_id': 'opl-1',
            'owner_id': 'thread-1', 'scope': 'Validate the prepared source change',
            'input_refs': ['git:example/project@abc'], 'checkpoint_refs': [],
            'expected_result': 'Validation evidence or a concrete blocker'}


class ExecutionBoundaryTests(unittest.TestCase):
    def test_native_worker_cli_needs_neither_ledger_nor_fleet(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'handoff.json'; path.write_text(json.dumps(handoff()))
            run = subprocess.run([sys.executable, str(ROOT/'scripts/opl_workflow.py'), 'worker', 'handoff', '--handoff-json', str(path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['binding'], execution.handoff_binding(handoff()))

    def test_result_rejects_wrong_attempt_and_unfinished_completion(self):
        item = handoff()
        result = {'schema': 'opl_worker_result.v1', 'binding': execution.handoff_binding(item),
                  'outcome': 'completed', 'artifact_refs': ['git:example/project@def'],
                  'checkpoint_refs': [], 'remaining': [], 'next_action': 'Owner verifies task acceptance'}
        self.assertEqual(execution.validate_result(result, item), result)
        wrong = copy.deepcopy(result); wrong['binding']['attempt_id'] = 'attempt-2'
        with self.assertRaisesRegex(execution.ExecutionError, 'match'):
            execution.validate_result(wrong, item)
        result['remaining'] = ['still running']
        with self.assertRaisesRegex(execution.ExecutionError, 'remaining'):
            execution.validate_result(result, item)

    def test_fleet_translation_checks_real_carrier_guards(self):
        workspace = {'schema': 'opl_fleet_workspace_readback.v1', 'profile_id': 'p', 'node_ids': ['n'],
                     'state': 'CURRENT', 'claim_ready': True, 'fresh_fetch': True, 'fresh_github': False}
        translated = fleet_execution.workspace_evidence(workspace, node_id='n')
        with self.assertRaisesRegex(execution.ExecutionError, 'claim-ready'):
            execution.workspace_evidence(translated, profile_id='p', node_id='n')
        node = {'schema': 'codex_fleet_doctor.v1', 'node_id': 'n', 'admission_ready': True,
                'ready_for_dispatch': False, 'receipt_state': 'CURRENT', 'control_current': True,
                'lease': {'owner_task': 'other'}}
        self.assertFalse(fleet_execution.node_evidence(node, objective_id='opl-1')['ready'])

    def test_local_dispatch_binds_handoff_and_rejects_wrong_objective(self):
        args = fleet.parse_args(['dispatch', 'acquire', '--adapter', 'local-codex', '--owner-task', 'opl-1', '--handoff-json', json.dumps(handoff())])
        request = fleet.dispatch_request(args)
        self.assertEqual(request['worker_binding'], execution.handoff_binding(handoff()))
        args.owner_task = 'different'
        with self.assertRaisesRegex(fleet.FleetError, 'does not match'):
            fleet.dispatch_request(args)

    def test_ssh_execute_rejects_changed_handoff_before_transport(self):
        binding = execution.handoff_binding(handoff())
        # Existing lease validation remains responsible for identity and admission.
        lease = {'lease_id':'lease-1', 'node_id':'n', 'generation':1, 'nonce':'n',
                 'owner_task':'opl-1', 'owner_thread':None, 'owner_run':None,
                 'role':None, 'dispatch_adapter':'ssh-session', 'worker_binding':binding,
                 'admission':{'requirements':[], 'min_memory_gb':0, 'gpu_api':'any', 'min_gpu_memory_gb':0, 'gpu_model':None}}
        altered = handoff(); altered['scope'] = 'Different work'
        args = fleet.parse_args(['dispatch','execute','lease-1','--owner-task','opl-1','--argv-json','["true"]','--handoff-json',json.dumps(altered)])
        with patch_fleet('controller_guard'), patch_fleet('dispatch_lease',return_value=lease), patch_fleet('verify_lease_record',return_value={}), patch_fleet('execute_ssh_session') as transport:
            with self.assertRaisesRegex(fleet.FleetError,'handoff does not match'):
                fleet.fleet_dispatch_execute(args)
        transport.assert_not_called()

    def test_owner_cli_translates_existing_fleet_receipts(self):
        from scripts import opl_workflow as workflow
        from tests.test_task_owner_migration import TaskOwnerMigrationTests
        fixture = TaskOwnerMigrationTests()
        issue, migration_id, _ = fixture.prepared()
        workspace = {'schema':'opl_fleet_workspace_readback.v1','profile_id':'target-profile',
                     'node_ids':['target-node'],'observed_at':'2026-11-02T00:00:00Z',
                     'state':'CURRENT','claim_ready':True,'fresh_fetch':True,'fresh_github':True,
                     'profile_fingerprint':'1'*64,'environment_fingerprint':'2'*64,'repository_fingerprint':'3'*64}
        node = {'schema':'codex_fleet_doctor.v1','node_id':'target-node','checked_at':'2026-11-02T00:00:00Z',
                'ready_for_dispatch':True,'admission_ready':True,'receipt_state':'CURRENT',
                'control_current':True,'current_control_commit':'c'*40,'lease':None}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, value in [('workspace',workspace),('node',node)]:
                (root/f'{name}.json').write_text(json.dumps(value))
            args = workflow.parser().parse_args(['ledger','owner','preflight','opl-1','--migration-id',migration_id,
                       '--workspace-readback-json',str(root/'workspace.json'),'--node-readback-json',str(root/'node.json')])
            def save(root, bd, previous, metadata):
                return {**previous, 'metadata':metadata}
            with mock.patch.object(workflow,'dolt_pull'), mock.patch.object(workflow,'bead_issue',return_value=issue), mock.patch.object(workflow,'apply_bead_metadata',side_effect=save):
                result = workflow.owner_migration_command(root,'bd',args)
        self.assertEqual(result['migration']['state'],'target_preflighted')

    def test_handoff_binding_survives_lease_roundtrip_without_context(self):
        from tests.test_opl_fleet import admission, TEST_CONTROL_COMMIT
        binding = execution.handoff_binding(handoff())
        with tempfile.TemporaryDirectory() as temp:
            lease = fleet.acquire_lease_record(node_id='n',owner_task='opl-1',owner_thread=None,owner_run=None,
                    role=None,workload_class='background',priority=300,preemptible=False,phase='interruptible',
                    ttl_seconds=600,control_revision=TEST_CONTROL_COMMIT,admission=admission(fleet.utc_now()),
                    worker_binding=binding,state_root=Path(temp))
            stored = fleet.read_lease_store(state_root=Path(temp))['leases']['n']
        self.assertEqual(stored['worker_binding'],binding)
        self.assertNotIn('scope',json.dumps(stored))
        self.assertNotIn('input_refs',json.dumps(stored))

    def test_ledger_and_owner_core_do_not_import_fleet(self):
        for filename in ('opl_ledger.py','opl_task_owner.py','opl_execution.py'):
            tree = ast.parse((ROOT/'scripts'/filename).read_text())
            imports = [node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
            self.assertFalse(any('fleet' in name for name in imports), filename)
