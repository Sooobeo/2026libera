"""Offline coordinator state-machine tests; synthetic responses, no HTTP/model."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import run_sector_v48 as runner
from sector_engine import SECTOR_CODES


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.market=runner.read(runner.ROOT/'data/sector_market/market_input.json')
        self.registry=runner.read(runner.ROOT/runner.DESIGN/'public_numeric_registry.json')
        self.contract=runner.read(runner.ROOT/runner.DESIGN/'prompt_contract.json')
        self.packet=runner.read(runner.ROOT/'data/sector_documents/packets/pilot/fidelity_q2_2026.json')
        self.prepared=self.root/'prepared';(self.prepared/'packets').mkdir(parents=True)
        runner.save(self.prepared/'packets/fidelity_q2_2026.json',self.packet)
        self.runtime=runner.transport.runtime_v48()
        self.case={'case_id':'fidelity_q2_2026__R4','source_id':'fidelity_q2_2026','arm':'R4','split':'pilot'}
        self.sent=[]
        self.pin_checks=0

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
                'http://127.0.0.1:11434',self.root/'CANCEL',self.root/'unused_server.log',pins)
        return result

    def test_R4_four_stages_no_source_leak_or_history_rewrite(self):
        result=self.execute()
        self.assertEqual(result['completed_core_stages'],4)
        self.assertEqual(result['core_calls_attempted'],4)
        self.assertEqual(result['auxiliary_calls_attempted'],0)
        self.assertEqual(self.pin_checks,4)
        for body in self.sent[:3]:
            text=json.dumps(body)
            self.assertNotIn(self.packet['source_id'],text)
            self.assertEqual(body['format']['properties']['interpretations']['maxItems'],0)
        self.assertIn(self.packet['source_id'],json.dumps(self.sent[3]))
        for left,right in zip(self.sent,self.sent[1:]): self.assertEqual(left['messages'],right['messages'][:len(left['messages'])])
        first=runner.read(self.root/'case/stage1/record.json')
        self.assertEqual(first['feedback']['status'],'not_yet_proposed')
        self.assertIsNone(first['feedback']['allocation']['raw_sum'])

    def test_raw_C0_preserved_and_two_revision_cap(self):
        result=self.execute({'C0':.965,'C1':.975,'C2':.98})
        self.assertEqual(result['core_calls_attempted'],4)
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

    def test_cancelled_transport_does_not_start_next_case(self):
        log=self.root/'server.log';log.write_text('fixture')
        manifest=self.root/'manifest.json';runner.save(manifest,{})
        registration=self.root/'registration.json';runner.save(registration,{})
        args=SimpleNamespace(manifest=str(manifest),registration=str(registration),base_url='http://127.0.0.1:11434',
                             server_log=str(log),output=str(self.root/'bundle'))
        result=runner.ROSTER[0]|{'status':'stopped_cancelled','system_integrity_incident':False,
                                'core_calls_attempted':1,'auxiliary_calls_attempted':0,'completed_core_stages':0}
        with patch.object(runner,'ROOT',self.root),patch.object(runner,'verify_manifest',return_value=({},self.runtime,self.contract,self.registry,self.market)),patch.object(runner,'verify_registration',return_value={}),patch.object(runner.remote,'api_json',return_value={'models':[]}),patch.object(runner,'run_case',return_value=result) as call,patch.object(runner,'emit'):
            self.assertEqual(runner.run(args),1)
        self.assertEqual(call.call_count,1)
        summary=runner.read(self.root/'bundle/summary.json')
        self.assertEqual(summary['status'],'cancelled')
        self.assertEqual(len(summary['cases_not_started']),3)

    def test_case_whitelist_and_pilot_budget(self):
        self.assertEqual(len(runner.ROSTER),4)
        self.assertEqual({c['split'] for c in runner.ROSTER},{'pilot'})
        self.assertEqual({c['source_id'] for c in runner.ROSTER},set(runner.SOURCES))
        self.assertNotIn('fidelity_q3_2026',str(runner.ROSTER))


if __name__=='__main__': unittest.main()
