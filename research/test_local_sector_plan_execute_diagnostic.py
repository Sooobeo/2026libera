"""Fake HTTP and offline verification only. No real model calls."""
from contextlib import redirect_stdout
import copy
import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import local_sector_plan_execute_diagnostic as diagnostic
from test_sector_structured_case import FakeServer


class PlanFakeServer(FakeServer):
    def send_json(self, value, status=200):
        if self.path == '/api/chat' and value.get('done') is True and value.get('message',{}).get('content'):
            stage = json.loads(self.server.generations[-1]['messages'][-1]['content'])['stage']
            if stage == 1 and self.server.forbidden_planner_weights:
                content = json.loads(value['message']['content'])
                content['weights'] = [{'sector_code':c,'weight':w,'rationale':'Fake final vector in plan', 'evidence_ids':[]}
                                      for c,w in self.server.market['baseline_weights'].items()]
                value = copy.deepcopy(value); value['message']['content'] = json.dumps(content)
            if stage == 4 and self.server.executor_length:
                value = copy.deepcopy(value); value['done_reason'] = 'length'; value['message']['content'] = '{'
        return super().send_json(value,status)


class PlanExecuteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.folder = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),PlanFakeServer)
        observation = diagnostic.remote.read(diagnostic.ROOT/'data/local_sector_runtime/laptop_latency_4b_20261018/4b_threads2/model_observation.json')
        self.server.template = observation['show']['template']; self.server.market = diagnostic.remote.read(diagnostic.workflow.MARKET)
        self.server.show_count=0; self.server.generations=[]; self.server.renders=[]; self.server.unloads=[]
        self.server.bad_render=None; self.server.bad_pin=False; self.server.bad_unload=False; self.server.response_model=None
        self.server.stall=False; self.server.generation_overflow=False; self.server.cancel_path=None
        self.server.echo=False; self.server.missing_key=False; self.server.extra_key=False; self.server.short_rows=False
        self.server.financial_error=False; self.server.invalid_json=False; self.server.thinking=False; self.server.length=False
        self.server.forbidden_planner_weights=False; self.server.executor_length=False
        self.server.release=threading.Event(); self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'; self.prepared=self.folder/'prepared'
        with redirect_stdout(io.StringIO()):
            diagnostic.prepare(SimpleNamespace(output=self.prepared,
                revision_evidence=diagnostic.ROOT/'research/v47_planner_executor_reference_20261018.json'))
        self.registration=self.folder/'registration.json'
        diagnostic.remote.save(self.registration,dict(protocol_version=diagnostic.PROTOCOL,diagnostic_id=diagnostic.DIAGNOSTIC_ID,
            registered_at_utc=diagnostic.remote.now(),manifest=diagnostic.prior.sha_record(self.prepared/'manifest.json'),
            planned_generation_attempts=2,automatic_retries=0,main_model_calls=0,main_freeze=False))
        self.log=self.folder/'fake_owned_server.log'; self.log.write_bytes(b'fake service only\n')

    def tearDown(self):
        self.server.release.set(); self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def args(self):
        return SimpleNamespace(manifest=self.prepared/'manifest.json',registration=self.registration,
            base_url=self.origin,server_log=self.log,output_root=self.folder,run_id='run')

    def run_fixture(self):
        with redirect_stdout(io.StringIO()): code=diagnostic.run(self.args())
        return code,diagnostic.remote.read(self.folder/'run/summary.json')

    def test_prespecified_actual_delta_no_target_and_exact_public_inputs(self):
        _,_,_,_,messages=diagnostic.verify_manifest(self.prepared/'manifest.json')
        values=diagnostic.original_inputs(); old=values[5]; delta=values[6]
        self.assertEqual(len(messages),5); self.assertEqual(messages[:2],values[3])
        self.assertEqual(messages[2]['content'],values[4]['message']['content'])
        self.assertEqual(json.loads(messages[3]['content'])['calculator_feedback'],old['calculator_result'])
        task=json.loads(messages[4]['content'])
        self.assertEqual(task['delta_feedback'],delta); self.assertEqual(task['calculator_feedback'],old['calculator_result'])
        self.assertEqual(len(delta['rows']),11)
        self.assertTrue(all(r['old_weight']==r['new_weight'] and r['delta']==0 for r in delta['rows']))
        self.assertEqual(delta['old_raw_sum'],.965); self.assertEqual(delta['new_raw_sum'],.965)
        self.assertNotIn('target_weights',task); self.assertNotIn('corrected_weights',task)
        self.assertEqual(task['required_planner_weights'],[])
        body=diagnostic.request_body(messages,'planner')
        projected=json.loads(body['messages'][1]['content'])
        projected['common_market']=diagnostic.base.restore_market(projected['common_market'])
        self.assertEqual(projected,json.loads(messages[1]['content']))
        self.assertEqual(body['messages'][2:],messages[2:])

    def test_two_model_calls_exact_history_and_plan_never_calculated(self):
        original_read=Path.read_text; original_calc=diagnostic.prior.calculate_portfolio; sizes=[]
        def guarded(path,*args,**kwargs):
            if 'evaluator_only' in str(path) or path.name=='model_packets.jsonl':raise AssertionError('Forbidden evaluator/main read')
            return original_read(path,*args,**kwargs)
        def calc(weights,*args,**kwargs):
            sizes.append(len(weights));return original_calc(weights,*args,**kwargs)
        with patch.object(Path,'read_text',guarded),patch.object(diagnostic.prior,'calculate_portfolio',calc):
            code,summary=self.run_fixture()
        self.assertEqual(code,0); self.assertEqual(summary['status'],'completed_plan_execute_diagnostic')
        self.assertEqual(summary['generation_requests_attempted'],2); self.assertEqual(summary['http_streams_completed'],2)
        self.assertEqual(summary['render_requests_attempted'],2); self.assertEqual(summary['diagnostic_generation_calls'],2)
        self.assertEqual(summary['main_model_calls'],0); self.assertEqual(summary['four_stage_pilot_calls'],0)
        self.assertEqual(summary['automatic_retries'],0); self.assertFalse(summary['priority1_solved'])
        self.assertTrue(summary['planner_completed']); self.assertTrue(summary['planner_contract_satisfied'])
        self.assertTrue(summary['executor_completed']); self.assertTrue(summary['numeric_acceptance'])
        self.assertTrue(summary['weight_vector_changed']); self.assertFalse(summary['executor_not_started'])
        self.assertNotIn(0,sizes)
        self.assertEqual(len(self.server.generations),2); self.assertEqual(len(self.server.unloads),2)
        planner,executor=self.server.generations
        self.assertEqual(len(planner['messages']),5); self.assertEqual(len(executor['messages']),7)
        self.assertEqual(executor['messages'][:5],planner['messages'])
        plan_response=diagnostic.remote.read(self.folder/'run/planner_transport/http_0001_generation/response.json')
        self.assertEqual(executor['messages'][5],{'role':'assistant','content':plan_response['message']['content']})
        for body,selector in [(planner,1),(executor,4)]:
            self.assertEqual(body['options'],diagnostic.base.OPTIONS)
            self.assertEqual(body['format'],diagnostic.transport.response_schema(selector))
        plan=diagnostic.remote.read(self.folder/'run/plan_record.json')
        self.assertEqual(plan['raw_proposal']['weights'],[]); self.assertFalse(plan['calculator_called'])
        self.assertIsNone(plan['financial_acceptance'])
        revision=diagnostic.remote.read(self.folder/'run/revision_record.json')
        response=diagnostic.remote.read(self.folder/'run/executor_transport/http_0001_generation/response.json')
        self.assertEqual(revision['raw_proposal'],json.loads(response['message']['content']))
        self.assertFalse(revision['repair_applied'])
        self.assertEqual(diagnostic.remote.sha(diagnostic.V46_MANIFEST),diagnostic.V46_MANIFEST_SHA)
        for name,digest in diagnostic.SOURCE_PINS.items():self.assertEqual(diagnostic.remote.sha(diagnostic.V46_RUN/name),digest)

    def test_planner_final_weights_stop_without_numeric_failure_or_executor(self):
        self.server.forbidden_planner_weights=True
        code,summary=self.run_fixture()
        self.assertEqual(code,1); self.assertEqual(summary['status'],'planner_contract_failed')
        self.assertTrue(summary['planner_completed']); self.assertFalse(summary['planner_contract_satisfied'])
        self.assertEqual(summary['generation_requests_attempted'],1); self.assertTrue(summary['executor_not_started'])
        self.assertEqual(len(self.server.generations),1); self.assertFalse((self.folder/'run/executor_transport').exists())
        record=diagnostic.remote.read(self.folder/'run/plan_record.json')
        self.assertEqual(len(record['raw_proposal']['weights']),11);self.assertFalse(record['calculator_called'])
        self.assertIsNone(record['financial_acceptance']);self.assertIsNone(summary['numeric_acceptance'])

    def test_executor_invalid_allocation_retained_not_retried(self):
        self.server.financial_error=True
        code,summary=self.run_fixture()
        self.assertEqual(code,0); self.assertTrue(summary['executor_completed']);self.assertFalse(summary['numeric_acceptance'])
        self.assertFalse(summary['priority1_solved']);self.assertEqual(len(self.server.generations),2)
        record=diagnostic.remote.read(self.folder/'run/revision_record.json')
        self.assertEqual(record['raw_proposal']['weights'][0]['weight'],-.25)

    def test_executor_output_cap_retained_without_complete_record(self):
        self.server.executor_length=True
        code,summary=self.run_fixture()
        self.assertEqual(code,1);self.assertEqual(summary['status'],'output_limit_reached')
        self.assertTrue(summary['planner_completed']);self.assertFalse(summary['executor_completed'])
        self.assertEqual(summary['generation_requests_attempted'],2);self.assertEqual(summary['failed_role'],'executor')
        self.assertFalse((self.folder/'run/revision_record.json').exists())
        self.assertTrue((self.folder/'run/executor_transport/http_0001_generation/response.json').is_file())

    def test_planner_schema_failure_stops_all_followups(self):
        self.server.echo=True
        code,summary=self.run_fixture()
        self.assertEqual(code,1);self.assertEqual(summary['generation_requests_attempted'],1)
        self.assertFalse(summary['planner_completed']);self.assertTrue(summary['executor_not_started'])
        self.assertEqual(len(self.server.generations),1)

    def test_render_and_pin_failures_prevent_any_generation(self):
        self.server.bad_render='missing'
        code,summary=self.run_fixture()
        self.assertEqual(code,1);self.assertEqual(summary['generation_requests_attempted'],0)
        self.assertTrue(summary['executor_not_started']);self.assertEqual(len(self.server.generations),0)

    def test_hard_deadline_preserves_partial_planner_and_never_executes(self):
        self.server.stall=True; supervise=diagnostic.transport.supervise
        def short(spec,deadline,cancel):return supervise(spec,2.5,cancel)
        with patch.object(diagnostic.transport,'supervise',short):code,summary=self.run_fixture()
        self.assertEqual(code,1);self.assertEqual(summary['status'],'hard_deadline')
        self.assertEqual(summary['generation_requests_attempted'],1);self.assertEqual(summary['http_streams_completed'],0)
        self.assertTrue(summary['executor_not_started']);self.assertEqual(len(self.server.generations),1)
        self.assertTrue((self.folder/'run/planner_transport/http_0001_generation/raw_stream.bin').is_file())

    def test_wrong_registration_budget_and_changed_delta_are_rejected(self):
        registration=diagnostic.remote.read(self.registration);registration['planned_generation_attempts']=3
        self.registration.write_text(json.dumps(registration),encoding='utf-8')
        with self.assertRaises(ValueError):self.run_fixture()
        self.assertEqual(self.server.show_count,0)
        path=self.prepared/'prior_delta_feedback.json';delta=diagnostic.remote.read(path)
        delta['rows'][0]['delta']=.035;path.write_text(json.dumps(delta),encoding='utf-8')
        with self.assertRaises(ValueError):diagnostic.verify_manifest(self.prepared/'manifest.json')


if __name__=='__main__':
    unittest.main()
