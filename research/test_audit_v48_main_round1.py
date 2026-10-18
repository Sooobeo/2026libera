"""Pure artifact fixtures for the v4.8 main audit; no HTTP/model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import audit_v48_main_round1 as audit
from unittest.mock import patch


class AuditArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def save(self, name, value):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    def test_only_partial_final_line_is_accepted(self):
        path = self.folder / 'events.jsonl'
        path.write_text('{"event":{"done":false}}\n{"event":', encoding='utf-8')
        values, partial = audit.complete_lines(path, event_wrapper=True)
        self.assertEqual(values, [{'done': False}]); self.assertTrue(partial)
        path.write_text('{broken}\n{"event":{"done":true}}\n', encoding='utf-8')
        with self.assertRaises(ValueError): audit.complete_lines(path, event_wrapper=True)
    def test_complete_raw_response_text_is_verbatim(self):
        raw = ' { "weights": [] }\n'
        self.save('response.json', {'message': {'content': raw}, 'done_reason': 'stop'})
        text, response = audit.captured_text(self.folder)
        self.assertEqual(text, raw); self.assertEqual(response['done_reason'], 'stop')
    def test_broken_response_falls_back_without_claiming_completion(self):
        (self.folder / 'response.json').write_text('{', encoding='utf-8')
        self.save('assembled_text.json', {'content': []})
        (self.folder / 'events.jsonl').write_text('{"event":{"message":{"content":"partial"}}}\n{"event":', encoding='utf-8')
        text, response = audit.captured_text(self.folder)
        self.assertEqual(text, 'partial'); self.assertIsNone(response)
    def render_fixture(self):
        body = {'model': audit.runner.transport.MODEL, 'stream': True, 'truncate': False, 'shift': False,
                'messages': [{'role': 'system', 'content': 'fixture system'},
                             {'role': 'user', 'content': ' \t{ "fixture": true }\n'}]}
        request = copy.deepcopy(body); request.update(stream=False, _debug_render_only=True)
        rendered = 'fixture system\n<role>\n{ "fixture": true }'
        response = {'model': body['model'], '_debug_info': {'rendered_template': rendered, 'image_count': 0}}
        validation = audit.runner.transport.validate_render(response, body['messages'], 'fixture system')
        self.save('request.json', {'path': '/api/chat', 'body': request})
        (self.folder / 'request_body.bin').write_bytes(json.dumps(request).encode())
        self.save('response.json', response); self.save('validation.json', validation)
        self.save('result.json', {'status': 'validated', 'unexpected_generation_evidence': False})
        (self.folder / 'rendered_prompt.txt').write_bytes(rendered.encode())
        return body
    def test_renderer_checks_preserve_json_values_and_recorded_spans(self):
        body = self.render_fixture(); checks = audit.Checks()
        audit.audit_render(checks, self.folder, body, 'fixture')
        self.assertTrue(all(x['passed'] for x in checks.rows), checks.rows)
    def test_changed_rendered_prompt_is_detected(self):
        body = self.render_fixture()
        (self.folder / 'rendered_prompt.txt').write_text('omitted history', encoding='utf-8')
        checks = audit.Checks(); audit.audit_render(checks, self.folder, body, 'fixture')
        failed = [x['id'] for x in checks.rows if not x['passed']]
        self.assertIn('fixture:render_saved_text', failed)
    def test_generation_in_render_only_response_is_detected(self):
        body = self.render_fixture()
        value = audit.read(self.folder / 'response.json'); value['eval_count'] = 1
        self.save('response.json', value)
        checks = audit.Checks(); audit.audit_render(checks, self.folder, body, 'fixture')
        self.assertIn('fixture:render_no_generation', [x['id'] for x in checks.rows if not x['passed']])


class MainAuditScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
    def test_counts_all_transport_levels_and_rejects_legacy_zero(self):
        value={'main_model_calls':1,'generation_requests_attempted':1,'execution_scope':'main'}
        result=copy.deepcopy(value);result['supervisor']=copy.deepcopy(value);result['supervisor']['worker']=copy.deepcopy(value)
        checks=audit.Checks();audit.audit_transport_accounting(checks,result,1,'fixture')
        self.assertTrue(all(x['passed'] for x in checks.rows))
        result['supervisor']['worker']['main_model_calls']=0
        checks=audit.Checks();audit.audit_transport_accounting(checks,result,1,'fixture')
        self.assertIn('fixture:worker_main_request_count',[x['id'] for x in checks.rows if not x['passed']])
    def test_killed_worker_count_without_usable_worker_summary(self):
        value={'main_model_calls':1,'generation_requests_attempted':1,'execution_scope':'main'}
        result=copy.deepcopy(value);result['supervisor']=copy.deepcopy(value)
        checks=audit.Checks();audit.audit_transport_accounting(checks,result,1,'fixture')
        self.assertTrue(all(x['passed'] for x in checks.rows))
    def test_actual_elapsed_is_reported_without_clipping_or_sleep_inference(self):
        path=self.folder/'synthetic__R4/C0/supervisor_result.json'
        self.save(path,{'deadline_seconds':900,'elapsed_seconds':1482.5,'status':'hard_deadline',
            'failure_phase_last_observed':'generation','generation_requests_attempted':1})
        checks=audit.Checks();result=audit.timing_observations(checks,self.folder,{'deadline_seconds':900})
        self.assertTrue(all(x['passed'] for x in checks.rows));self.assertFalse(result['strict_wall_clock_bound_certified'])
        self.assertEqual(result['endpoint_observations'][0]['observed_supervisor_elapsed_seconds'],1482.5)
        self.assertEqual(result['endpoint_observations'][0]['elapsed_minus_configured_seconds'],582.5)
        self.assertIn('pending',result['environmental_interruption_review'])
    def test_wrong_configured_deadline_is_flagged(self):
        self.save(self.folder/'synthetic__R1/C0/supervisor_result.json',{'deadline_seconds':901,'elapsed_seconds':1})
        checks=audit.Checks();audit.timing_observations(checks,self.folder,{'deadline_seconds':900})
        self.assertFalse(all(x['passed'] for x in checks.rows))
    def test_awake_acceptance_is_not_uninterrupted_execution_proof(self):
        self.save(self.folder/'awake_acquire.json',{'status':'active','flags':audit.runner.awake.FLAGS,
            'platform':'win32','owner_thread_id':123,'previous_state':audit.runner.awake.ES_CONTINUOUS,'permanent_power_configuration_changed':False})
        self.save(self.folder/'awake_release.json',{'status':'released','owner_thread_id':123,
            'restore_flags':audit.runner.awake.ES_CONTINUOUS,'permanent_power_configuration_changed':False})
        checks=audit.Checks();result=audit.audit_awake(checks,self.folder)
        self.assertTrue(all(x['passed'] for x in checks.rows));self.assertFalse(result['uninterrupted_operation_proven'])
        changed=audit.read(self.folder/'awake_release.json');changed['owner_thread_id']=124
        self.save(self.folder/'awake_release.json',changed);checks=audit.Checks();audit.audit_awake(checks,self.folder)
        self.assertFalse(all(x['passed'] for x in checks.rows))
    def test_not_started_main_cases_stay_four_over_forty_four(self):
        prepared=self.folder/'prepared';run=self.folder/'run';run.mkdir()
        manifest={'roster':list(audit.runner.ROSTER)};gate={'authorized_run_root':str(run),
            'human_source_review':{'fixture':'human'},'main_execution_authorization':{'fixture':'authorization'}}
        self.save(prepared/'manifest.json',manifest);self.save(prepared/'gate.json',gate)
        runtime=audit.runner.transport.runtime_v48();contract={'common_instructions':['Synthetic fixture.']}
        for name,value in (('runtime.json',runtime),('prompt_contract.json',contract),('public_numeric_registry.json',{}),('market_input.json',{})):
            self.save(prepared/name,value)
        self.save(run/'summary.json',{'planned_cases':list(audit.runner.ROSTER),'cases':[],'cases_not_started':[c['case_id'] for c in audit.runner.ROSTER],
            'main_model_calls':0,'core_generation_calls':0,'auxiliary_generation_calls':0,'status':'stopped_before_or_between_cases',
            'main_frozen':True,'human_review_completed':True,'human_semantic_review_completed':False,'automatic_retries':0,'system_integrity_incident':True})
        with patch.object(audit.runner,'verify_main_gate',return_value=(manifest,runtime,contract,{}, {},gate,{},{})):
            result=audit.audit(prepared/'manifest.json',prepared/'gate.json',run)
        self.assertEqual(result['status'],'FAIL');self.assertEqual(result['planned_cases'],4);self.assertEqual(result['expected_sector_slots'],44)
        self.assertEqual(len(result['case_outcomes']),4);self.assertEqual(result['observed_main_generation_requests'],0)
        self.assertEqual(result['model_calls_by_audit'],0);self.assertFalse(result['new_execution_authorized_by_audit'])

    def material_fixture(self):
        values = {}
        for key in audit.EVALUATOR_MATERIAL_KEYS:
            path = self.folder / (key + '.json')
            self.save(path, {'synthetic_offline_only': key})
            values[key] = {'path': str(path.resolve()), 'sha256': audit.sha_bytes(path.read_bytes())}
        source = self.folder / 'source_verification.json'
        self.save(source, {'artifact_sha256': {'evaluator_only/reference_annotations.jsonl': values['reference_annotations']['sha256']}})
        values['source_verification']['sha256'] = audit.sha_bytes(source.read_bytes())
        handoff = self.folder / 'design_handoff.json'
        self.save(handoff, {'delivered_artifacts': [values[key] for key in ('evaluation_protocol', 'review_template', 'source_comparison')]})
        values['design_handoff']['sha256'] = audit.sha_bytes(handoff.read_bytes())
        return {'evaluator_material_refs': values}

    def test_evaluation_materials_and_original_hash_links_are_checked_offline(self):
        manifest = self.material_fixture(); checks = audit.Checks()
        self.assertEqual(audit.audit_evaluator_materials(checks, manifest), manifest['evaluator_material_refs'])
        self.assertTrue(all(row['passed'] for row in checks.rows), checks.rows)

    def test_changed_annotation_or_criterion_is_not_accepted(self):
        manifest = self.material_fixture()
        for key in ('reference_annotations', 'evaluation_protocol'):
            path = Path(manifest['evaluator_material_refs'][key]['path'])
            path.write_bytes(path.read_bytes() + b'\n')
        checks = audit.Checks(); audit.audit_evaluator_materials(checks, manifest)
        failed = {row['id'] for row in checks.rows if not row['passed']}
        self.assertIn('evaluator_material_bytes:reference_annotations', failed)
        self.assertIn('evaluator_material_bytes:evaluation_protocol', failed)

    def test_missing_or_null_evaluation_material_pin_is_rejected(self):
        manifest = self.material_fixture()
        manifest['evaluator_material_refs']['reference_annotations']['sha256'] = None
        checks = audit.Checks(); audit.audit_evaluator_materials(checks, manifest)
        self.assertIn('evaluator_material_reference:reference_annotations', {row['id'] for row in checks.rows if not row['passed']})
        manifest['evaluator_material_refs'].pop('review_template')
        checks = audit.Checks(); audit.audit_evaluator_materials(checks, manifest)
        self.assertFalse(checks.rows[0]['passed'])


if __name__=='__main__':unittest.main()
