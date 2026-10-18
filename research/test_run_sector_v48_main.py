"""Offline coordinator state-machine tests; synthetic responses, no HTTP/model."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_sector_v48_main as runner
from sector_engine import SECTOR_CODES


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.market=runner.read(runner.ROOT/'data/sector_market/market_input.json')
        self.registry=runner.read(runner.ROOT/runner.DESIGN/'public_numeric_registry.json')
        self.contract=runner.read(runner.ROOT/runner.DESIGN/'prompt_contract.json')
        self.packet=runner.read(runner.ROOT/'data/sector_documents/packets/main/fidelity_q3_2026.json')
        self.prepared=self.root/'prepared';(self.prepared/'packets').mkdir(parents=True)
        runner.save(self.prepared/'packets/fidelity_q3_2026.json',self.packet)
        self.runtime=runner.transport.runtime_v48()
        self.case={'case_id':'fidelity_q3_2026__R4','source_id':'fidelity_q3_2026','arm':'R4','split':'main'}
        self.sent=[]
        self.pin_checks=0
        acquire_patch=patch.object(runner.awake,'acquire',return_value={'status':'active','synthetic_fixture':True})
        release_patch=patch.object(runner.awake,'release',return_value={'status':'released','synthetic_fixture':True})
        self.awake_acquire=acquire_patch.start();self.awake_release=release_patch.start()
        self.addCleanup(acquire_patch.stop);self.addCleanup(release_patch.stop)

    def tearDown(self): self.tmp.cleanup()

    def proposal(self,stage,visible,total):
        weights=[] if stage<3 else [{'sector_code':c,'weight':total if i==0 else 0.0,
                                    'rationale':'Synthetic fixture rationale','evidence_ids':[]}
                                   for i,c in enumerate(SECTOR_CODES)]
        return {'source_id':self.packet['source_id'] if visible else None,
            'interpretations':[{'sector_code':c,'rating':'fixture_label','reason':'fixture source interpretation',
                               'evidence_ids':[self.packet['evidence_passages'][0]['evidence_id']]} for c in SECTOR_CODES] if visible else [],
            'weights':weights,'alternatives':'fixture alternative','risk_discussion':'fixture historical-risk statement',
            'unresolved':[],'submitted_constraints':[]}

    def execute(self,totals=None,failure=None,post_call_exception=False):
        totals=totals or {}
        def fake_transport(**kw):
            self.sent.append(copy.deepcopy(kw['body']))
            endpoint=kw['target'].name
            folder=kw['target']/'http_0001_generation';folder.mkdir()
            runner.save(folder/'request.json',{'body':kw['body']})
            status='completed'
            text=json.dumps(self.proposal(kw['stage'],kw['institution_visible'],totals.get(endpoint,1.0)),ensure_ascii=False)
            if failure and endpoint==failure[0]:
                status=failure[1]
                if status=='model_contract_failure': text='{"weights":[]}'
                elif status=='nonfinite_fixture':
                    status='model_contract_failure'
                    value=self.proposal(kw['stage'],kw['institution_visible'],1.0)
                    value['weights'][0]['weight']='OVERFLOW_PLACEHOLDER'
                    text=json.dumps(value).replace('"OVERFLOW_PLACEHOLDER"','1e309')
                elif status=='hard_deadline':
                    runner.save(folder/'assembled_text.json',{'content':'{"unfinished":','complete':False})
                    return {'status':status,'system_integrity_incident':False}
            response={'model':self.runtime['model'],'done_reason':'stop','message':{'content':text}}
            runner.save(folder/'response.json',response)
            return {'status':status,'response':response,'system_integrity_incident':status=='pin_failure'}
        def pins(): self.pin_checks+=1
        original_calculator=runner.evaluate_proposal
        def calculate(*args,**kwargs):
            if post_call_exception: raise RuntimeError('Synthetic post-call calculation failure')
            return original_calculator(*args,**kwargs)
        with patch.object(runner,'ROOT',self.root),patch.object(runner.transport,'run_transport',side_effect=fake_transport),patch.object(runner,'emit'),patch.object(runner,'evaluate_proposal',side_effect=calculate):
            result=runner.run_case(self.case,self.prepared,self.root/'case',self.runtime,self.contract,self.registry,self.market,
                'http://127.0.0.1:11434',self.root/'CANCEL',self.root/'unused_server.log',pins,{'fixture':'not an actual execution gate'})
        return result

    def test_R4_four_stages_no_source_leak_or_history_rewrite(self):
        result=self.execute()
        self.assertEqual(result['completed_core_stages'],4)
        self.assertEqual(result['core_calls_attempted'],4)
        self.assertEqual(result['main_model_calls'],4+result['auxiliary_calls_attempted'])
        self.assertEqual(result['auxiliary_calls_attempted'],0)
        self.assertEqual(self.pin_checks,4)
        for body in self.sent[:3]:
            for msg in body['messages'][1:]:
                if msg['role']=='user': self.assertNotIn('institution_document',json.loads(msg['content']))
            self.assertEqual(body['format']['properties']['interpretations']['maxItems'],0)
        self.assertIn(self.packet['source_id'],json.dumps(self.sent[3]))
        for left,right in zip(self.sent,self.sent[1:]): self.assertEqual(left['messages'],right['messages'][:len(left['messages'])])
        first=runner.read(self.root/'case/stage1/record.json')
        self.assertEqual(first['feedback']['status'],'not_yet_proposed')
        self.assertIsNone(first['feedback']['allocation']['raw_sum'])

    def test_raw_C0_preserved_and_two_revision_cap(self):
        result=self.execute({'C0':.965,'C1':.975,'C2':.98})
        self.assertEqual(result['core_calls_attempted'],4)
        self.assertEqual(result['main_model_calls'],4+result['auxiliary_calls_attempted'])
        self.assertEqual(result['auxiliary_calls_attempted'],2)
        self.assertFalse(result['final_allocation_valid'])
        self.assertEqual(result['auxiliary_stop_reason'],'cap_C2_reached')
        self.assertEqual(runner.read(self.root/'case/C0/record.json')['feedback']['allocation']['raw_sum'],.965)
        self.assertEqual(runner.read(self.root/'case/C2/record.json')['feedback']['allocation']['raw_sum'],.98)
        self.assertTrue(result['primary_never_replaced'])
        self.assertFalse((self.root/'case/C3').exists())

    def test_valid_C1_stops_before_C2(self):
        result=self.execute({'C0':.965,'C1':1.0})
        self.assertEqual(result['auxiliary_calls_attempted'],1)
        self.assertEqual(result['auxiliary_stop_reason'],'arithmetic_valid')
        self.assertFalse(result['final_allocation_valid'])
        self.assertFalse((self.root/'case/C2').exists())

    def test_model_schema_failure_stops_case_not_instrument(self):
        result=self.execute(failure=('stage2','model_contract_failure'))
        self.assertEqual(result['core_calls_attempted'],2)
        self.assertEqual(result['completed_core_stages'],1)
        self.assertEqual(result['auxiliary_calls_attempted'],0)
        self.assertFalse(result['system_integrity_incident'])
        self.assertIsNone(result['primary_record'])
        self.assertEqual(runner.read(self.root/'case/stage2/record.json')['raw_response_text'],'{"weights":[]}')

    def test_timeout_retains_partial_and_later_stages_unstarted(self):
        result=self.execute(failure=('stage1','hard_deadline'))
        self.assertEqual(result['core_calls_attempted'],1)
        self.assertEqual(result['completed_core_stages'],0)
        self.assertEqual(result['auxiliary_calls_attempted'],0)
        record=runner.read(self.root/'case/stage1/record.json')
        self.assertEqual(record['raw_response_text'],'{"unfinished":')
        self.assertFalse(record['response_complete'])
        self.assertEqual(result['core_stage_states'],{'stage1':'attempted_failed','stage2':'not_started','stage3':'not_started','C0':'not_started'})

    def test_post_call_exception_still_counts_durable_request(self):
        result=self.execute(post_call_exception=True)
        self.assertEqual(result['core_calls_attempted'],1)
        self.assertTrue(result['system_integrity_incident'])
        self.assertEqual(result['core_stage_states']['stage1'],'attempted_failed')
        self.assertTrue((self.root/'case/stage1/http_0001_generation/response.json').is_file())

    def test_exponent_overflow_is_model_failure_with_raw_preserved(self):
        result=self.execute(failure=('C0','nonfinite_fixture'))
        self.assertFalse(result['system_integrity_incident'])
        self.assertEqual(result['status'],'stopped_model_contract_failure')
        self.assertEqual(result['core_calls_attempted'],4)
        self.assertEqual(result['main_model_calls'],4+result['auxiliary_calls_attempted'])
        self.assertEqual(result['auxiliary_calls_attempted'],0)
        record=runner.read(self.root/'case/C0/record.json')
        self.assertIn('1e309',record['raw_response_text'])
        self.assertIsNone(record['parsed_response'])
        self.assertIsNone(record['feedback'])

    def test_interrupted_json_envelopes_keep_flushed_stream_material(self):
        folder=self.root/'cancelled/http_0001_generation';folder.mkdir(parents=True)
        (folder/'response.json').write_text('{"message":',encoding='utf-8')
        (folder/'assembled_text.json').write_text('{',encoding='utf-8')
        (folder/'events.jsonl').write_text(json.dumps({'event':{'message':{'content':'{"source_id":'}}})+'\n'+ '{"event":',encoding='utf-8')
        raw,response=runner.get_raw(folder.parent,{})
        self.assertEqual(raw,'{"source_id":')
        self.assertIsNone(response)
        for envelope in ({'message':None},{'message':{'content':[]}}):
            runner.save(folder/'response.json',envelope)
            runner.save(folder/'assembled_text.json',{'content':[]})
            raw,response=runner.get_raw(folder.parent,{})
            self.assertEqual(raw,'{"source_id":')
            self.assertIsNone(response)

    def bundle_fixture(self):
        log=self.root/'server.log';log.write_text('synthetic fixture')
        manifest=self.root/'manifest.json';candidate={'roster':list(runner.ROSTER)};runner.save(manifest,candidate)
        gate_path=self.root/'gate.json'
        gate={'authorized_run_root':str(self.root/'bundle'),'main_execution_authorization':{'fixture':'authorization'},
              'human_source_review':{'fixture':'source review'}}
        runner.save(gate_path,gate)
        args=SimpleNamespace(manifest=str(manifest),gate=str(gate_path),base_url='http://127.0.0.1:11434',
                             server_log=str(log),output=str(self.root/'bundle'))
        verified=(candidate,self.runtime,self.contract,self.registry,self.market,gate,{'fixture':'human'}, {'fixture':'approval'})
        return args,verified

    def test_cancelled_transport_does_not_start_next_case_or_erase_calls(self):
        args,verified=self.bundle_fixture()
        def case_call(case,prepared,target,*unused):
            folder=target/'stage1/http_0001_generation';folder.mkdir(parents=True)
            runner.save(folder/'request.json',{'fixture':True})
            return case|{'status':'stopped_cancelled','system_integrity_incident':False,
                'core_calls_attempted':1,'auxiliary_calls_attempted':0,'main_model_calls':1,'completed_core_stages':0}
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json',return_value={'models':[]}),patch.object(runner,'run_case',side_effect=case_call) as call,patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        self.assertEqual(call.call_count,1)
        summary=runner.read(self.root/'bundle/summary.json')
        self.assertEqual(summary['status'],'cancelled');self.assertEqual(summary['main_model_calls'],1)
        self.assertEqual(len(summary['cases_not_started']),3)
        self.assertTrue(summary['human_review_completed']);self.assertFalse(summary['human_semantic_review_completed'])
        for name in ('manifest','main_execution_gate','main_execution_authorization','human_source_review'):
            self.assertTrue((self.root/'bundle'/f'{name}_snapshot.json').is_file())

    def test_missing_gate_rejected_before_output_or_network(self):
        args,_=self.bundle_fixture()
        with patch.object(runner,'verify_main_gate',side_effect=ValueError('Missing actual human source review')),patch.object(runner.remote,'api_json') as http:
            with self.assertRaises(ValueError):runner.run(args)
        self.assertFalse((self.root/'bundle').exists());http.assert_not_called()

    def test_wrong_run_root_rejected_before_network(self):
        args,verified=self.bundle_fixture();args.output=str(self.root/'different')
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json') as http:
            with self.assertRaises(ValueError):runner.run(args)
        self.assertFalse((self.root/'different').exists());http.assert_not_called()

    def test_model_failure_retains_all_fixed_cases_and_requests(self):
        args,verified=self.bundle_fixture()
        def case_call(case,prepared,target,*unused):
            folder=target/'stage1/http_0001_generation';folder.mkdir(parents=True)
            runner.save(folder/'request.json',{'fixture':True})
            return case|{'status':'stopped_model_contract_failure','system_integrity_incident':False,
                'core_calls_attempted':1,'auxiliary_calls_attempted':0,'main_model_calls':1,'completed_core_stages':0}
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json',return_value={'models':[]}),patch.object(runner,'run_case',side_effect=case_call),patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),0)
        summary=runner.read(self.root/'bundle/summary.json')
        self.assertEqual(summary['main_model_calls'],4);self.assertEqual(len(summary['cases']),4)
        self.assertEqual(summary['completed_core_cases'],0);self.assertEqual(summary['cases_not_started'],[])

    def test_generation_after_case_exception_still_in_bundle_count(self):
        args,verified=self.bundle_fixture()
        def case_call(case,prepared,target,*unused):
            folder=target/'stage1/http_0001_generation';folder.mkdir(parents=True)
            runner.save(folder/'request.json',{'fixture':True})
            raise RuntimeError('Synthetic exception after durable request')
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json',return_value={'models':[]}),patch.object(runner,'run_case',side_effect=case_call),patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        summary=runner.read(self.root/'bundle/summary.json')
        self.assertEqual(summary['main_model_calls'],1);self.assertTrue(summary['system_integrity_incident'])
        self.assertEqual(len(summary['planned_cases']),4)

    def test_pre_endpoint_cancel_is_no_call_without_instrument_failure(self):
        (self.root/'CANCEL').write_text('fixture cancel')
        result=self.execute()
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['main_model_calls'],0)
        self.assertFalse(result['system_integrity_incident']);self.assertEqual(self.sent,[])

    def test_case_whitelist_main_scope_and_unexpected_request_count(self):
        self.assertEqual(len(runner.ROSTER),4)
        self.assertEqual({c['split'] for c in runner.ROSTER},{'main'})
        self.assertEqual({c['source_id'] for c in runner.ROSTER},set(runner.SOURCES))
        self.assertNotIn('fidelity_q2_2026',str(runner.ROSTER))
        folder=self.root/'count'/runner.ROSTER[0]['case_id']/'C3/http_0001_generation';folder.mkdir(parents=True)
        runner.save(folder/'request.json',{'fixture':True})
        count=runner.durable_counts(self.root/'count')
        self.assertEqual(count['main_model_calls'],1);self.assertEqual(len(count['unexpected_generation_request_paths']),1)

    def history_spec(self,endpoint):
        for stage in range(1,5):
            runner.save(self.prepared/'previews'/self.case['case_id']/f'stage{stage}_payload.json',
                runner.stage_payload(stage,self.case['arm'],self.packet,self.market,self.registry))
        folder=self.root/'case'/endpoint
        body=runner.read(folder/'http_0001_generation/request.json')['body'] if (folder/'http_0001_generation/request.json').exists() else {'messages':[]}
        return {'target_path':str(folder),'execution_context':{'manifest_path':str(self.prepared/'manifest.json')},
                'body':body,'runtime':self.runtime}

    def validate_history(self,spec):
        return runner.transport.validate_authored_history(spec,self.case,self.contract,self.registry,self.market)

    def test_worker_history_reconstructed_from_frozen_previews_and_raw_records(self):
        self.execute()
        for endpoint in ('stage1','stage2','stage3','C0'):
            result=self.validate_history(self.history_spec(endpoint))
            self.assertEqual(result['status'],'frozen_tasks_and_literal_prior_history_match')

    def test_worker_rejects_pre_R4_document_injection_and_history_rewrite(self):
        self.execute()
        spec=self.history_spec('stage1')
        payload=json.loads(spec['body']['messages'][-1]['content']);payload['institution_document']=self.packet
        spec['body']['messages'][-1]['content']=runner.canonical(payload)
        with self.assertRaises(ValueError):self.validate_history(spec)
        spec=self.history_spec('stage2');spec['body']['messages'][2]['content']+=' '
        with self.assertRaises(ValueError):self.validate_history(spec)

    def test_worker_rejects_feedback_not_derived_from_retained_raw(self):
        self.execute()
        spec=self.history_spec('stage2');path=self.root/'case/stage1/record.json'
        record=runner.read(path);record['feedback']['status']='invented_feedback';runner.save(path,record)
        with self.assertRaisesRegex(ValueError,'feedback'):self.validate_history(spec)

    def test_worker_auxiliary_requires_actual_complete_invalid_predecessor(self):
        self.execute({'C0':.965,'C1':.975,'C2':.98})
        self.assertTrue(self.validate_history(self.history_spec('C1'))['auxiliary_predecessor_checked'])
        self.assertTrue(self.validate_history(self.history_spec('C2'))['auxiliary_predecessor_checked'])
        (self.root/'case/C0/record.json').unlink()
        with self.assertRaises(FileNotFoundError):self.validate_history(self.history_spec('C1'))

    def test_worker_valid_C0_does_not_authorize_auxiliary(self):
        self.execute()
        with self.assertRaisesRegex(ValueError,'eligible'):self.validate_history(self.history_spec('C1'))

    def test_main_awake_failure_prevents_network_and_generation(self):
        args,verified=self.bundle_fixture();self.awake_acquire.return_value={'status':'request_failed'}
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json') as http,patch.object(runner,'run_case') as cases,patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        http.assert_not_called();cases.assert_not_called();self.awake_release.assert_not_called()
        self.assertEqual(runner.read(self.root/'bundle/summary.json')['main_model_calls'],0)

    def test_main_active_awake_receipt_write_failure_still_releases(self):
        args,verified=self.bundle_fixture();real=runner.save
        def save(path,value):
            if Path(path).name=='awake_acquire.json':raise OSError('synthetic disk error')
            return real(path,value)
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner,'save',side_effect=save),patch.object(runner.remote,'api_json') as http,patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        self.awake_release.assert_called_once();http.assert_not_called()

    def test_main_awake_release_failure_is_operating_incident(self):
        args,verified=self.bundle_fixture();self.awake_release.return_value={'status':'release_failed'}
        with patch.object(runner,'verify_main_gate',return_value=verified),patch.object(runner.remote,'api_json',side_effect=ValueError('synthetic pre-generation incident')),patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        summary=runner.read(self.root/'bundle/summary.json')
        self.assertEqual(summary['status'],'awake_restoration_failed');self.assertTrue(summary['system_integrity_incident'])


if __name__=='__main__':unittest.main()
