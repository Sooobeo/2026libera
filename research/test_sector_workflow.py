"""Integration checks with fake responses only; no AI call or claimed AI result."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import run_sector_workflow as workflow
from run_sector_workflow import ROOT, MARKET, read, write, packets, run_case, verify_freeze, digest
from evaluate_sector_runs import evaluate


class WorkflowIntegration(unittest.TestCase):
    def setUp(self):
        self.market=read(MARKET)
        self.corpus=[p for p in packets() if p['split']=='pilot']
        self.golds={g['source_id']:g for g in [json.loads(x) for x in (ROOT/'data/sector_documents/evaluator_only/reference_annotations.jsonl').read_text(encoding='utf-8').splitlines()]}

    def fixture(self,packet):
        gold=self.golds[packet['source_id']]
        return {'source_id':packet['source_id'],
            'interpretations':[{'sector_code':c,'rating':v['rating'],'evidence_ids':v['evidence_ids'],'reason':'Synthetic integration fixture'} for c,v in gold['sector_ratings'].items()],
            'weights':[{'sector_code':c,'weight':v,'rationale':'Synthetic interface fixture only','evidence_ids':[]} for c,v in self.market['baseline_weights'].items()],
            'submitted_constraints':[]}

    def test_full_offline_connection_and_source_denominators(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder); write(out/'runtime.json',{'split':'pilot','synthetic':True})
            for packet in self.corpus:
                for arm in ('R1','R4'):
                    value=self.fixture(packet)
                    def adapter(messages):
                        return {'message':{'role':'assistant','content':json.dumps(value)},'synthetic':True}
                    run_case(packet,arm,self.market,adapter,out/(packet['source_id']+'__'+arm))
            result=evaluate(out)
            self.assertTrue(result['all_planned_runs_completed'])
            for arm in ('R1','R4'):self.assertEqual(result['predeclared_roster_by_arm'][arm],{'correct':22,'expected':22})
            self.assertTrue(result['distances']['four_valid_allocations'])

    def test_failure_retained_no_retry_and_unexecuted_not_observed_error(self):
        calls=[]
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);write(out/'runtime.json',{'split':'pilot','synthetic':True})
            packet=self.corpus[0];target=out/(packet['source_id']+'__R4')
            def adapter(messages):
                calls.append(messages)
                return {'message':{'role':'assistant','content':'{"weights":[],"weights":[]}'}}
            with self.assertRaises(ValueError):run_case(packet,'R4',self.market,adapter,target)
            self.assertEqual(len(calls),1)
            self.assertTrue((target/'stage1_response.json').exists())
            self.assertTrue((target/'failure.json').exists())
            result=evaluate(out)
            self.assertFalse(result['all_planned_runs_attempted'])
            self.assertEqual(sum(r['status']=='not_started' for r in result['records']),3)
            self.assertEqual(sum(r['status']=='attempted_without_valid_final' for r in result['records']),1)

    def test_online_has_no_gold_text_access_and_late_evidence_is_hidden(self):
        packet=self.corpus[0]; seen=[]; original=Path.read_text
        def guarded(path,*args,**kwargs):
            if 'evaluator_only' in str(path):raise AssertionError('Online accessed gold')
            return original(path,*args,**kwargs)
        def adapter(messages):
            seen.append(json.dumps(messages))
            return {'message':{'role':'assistant','content':'{"interpretations":[],"weights":[],"submitted_constraints":[]}'}}
        with tempfile.TemporaryDirectory() as folder,patch.object(Path,'read_text',guarded):
            run_case(packet,'R4',self.market,adapter,Path(folder)/'R4')
        self.assertTrue(all(packet['source_id'] not in x for x in seen[:3]))
        self.assertIn(packet['source_id'],seen[3])

    def test_frozen_file_mutation_is_detected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            p=Path(folder)/'fixture.txt';p.write_text('original',encoding='utf-8')
            frozen={'hashes':{str(p.relative_to(ROOT)):digest(p)}}
            verify_freeze(frozen)
            p.write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):verify_freeze(frozen)

    def test_length_failure_preserves_raw_response(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'long'
            def adapter(messages):return {'message':{'role':'assistant','content':'incomplete'},'done_reason':'length'}
            with self.assertRaises(RuntimeError):run_case(self.corpus[0],'R1',self.market,adapter,target)
            self.assertEqual(read(target/'stage1_response.json')['message']['content'],'incomplete')
            self.assertTrue((target/'failure.json').exists())

    def test_explicit_final_content_and_feedback_retained_but_thinking_only_archived(self):
        packet=self.corpus[0]; seen=[]; contents=[]
        def adapter(messages):
            seen.append(json.loads(json.dumps(messages)))
            content='  '+json.dumps({'interpretations':[], 'weights':[],
                                    'submitted_constraints':[], 'unresolved':[f'stage {len(seen)}']})+'\n'
            contents.append(content)
            return {'message':{'role':'assistant','content':content,'thinking':'private generated trace'}}
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'history'
            run_case(packet,'R4',self.market,adapter,target)
            for index,messages in enumerate(seen):
                previous=[m for m in messages if m['role']=='assistant']
                self.assertEqual([m['content'] for m in previous],contents[:index])
                self.assertTrue(all(set(m)=={'role','content'} for m in previous))
                self.assertEqual(messages[0],seen[0][0])
                self.assertEqual(messages[1],seen[0][1])
                feedback=[m for m in messages if 'calculator_feedback' in m['content']]
                self.assertEqual(len(feedback),index)
                self.assertEqual(read(target/f'stage{index+1}_request.json'),messages)
            self.assertEqual(read(target/'stage1_response.json')['message']['thinking'],'private generated trace')
            self.assertNotIn('private generated trace',json.dumps(seen))
            self.assertEqual(read(target/'stage4_record.json')['history_policy'],workflow.EXPLICIT_HISTORY)


class RuntimeProtocolTests(unittest.TestCase):
    def runtime(self):
        value=workflow.runtime_candidate_v43()
        value.update({'digest':'a'*64,'template_sha256':hashlib.sha256(b'pinned template').hexdigest(),
                      'engine_version':'0.35.1','base_url':'http://synthetic.invalid:11434'})
        return value

    def metadata_http(self,url,body=None,headers=None,timeout=30):
        if url.endswith('/api/tags'):
            return {'models':[{'name':'qwen3.5:4b-q4_K_M','digest':'a'*64},
                              {'name':'qwen3:1.7b','digest':'b'*64}]}
        if url.endswith('/api/version'):return {'version':'0.35.1'}
        if url.endswith('/api/show'):
            self.assertEqual(body,{'model':'qwen3.5:4b-q4_K_M'})
            return {'template':'pinned template','parameters':'synthetic metadata','capabilities':['completion']}
        raise AssertionError('Unexpected model request in metadata-only test: '+url)

    def test_v43_sends_explicit_model_sampling_context_and_history_without_fallback(self):
        runtime=self.runtime(); messages=[{'role':'user','content':'synthetic input'}]; calls=[]
        def fake_http(url,body=None,headers=None,timeout=30):
            if url.endswith('/api/chat'):
                calls.append((url,body,timeout))
                return {'message':{'role':'assistant','content':'{}'},'done_reason':'stop'}
            return self.metadata_http(url,body,headers,timeout)
        with patch.object(workflow,'http_json',side_effect=fake_http):
            adapter=workflow.ollama_adapter(runtime)
            # An outside mutation must not change the adapter's recorded selection.
            runtime['model']='qwen3:1.7b'
            result=adapter(messages)
        self.assertEqual(result['done_reason'],'stop')
        self.assertEqual(len(calls),1)
        body=calls[0][1]
        self.assertEqual(body['model'],'qwen3.5:4b-q4_K_M')
        self.assertIs(body['think'],False)
        self.assertEqual(body['options'],{'temperature':0,'num_predict':8192,'num_ctx':65536})
        self.assertEqual(body['messages'],messages)
        self.assertEqual((body['format'],body['stream'],body['keep_alive']),('json',False,0))

    def test_unapproved_protocol_changes_are_rejected_before_network_access(self):
        changes=[{'protocol_version':None},{'protocol_version':'4.4'},{'model':'qwen3.5:4b'},
                 {'model':'qwen3:1.7b'},{'temperature':0.7},{'temperature':False},{'thinking':True},
                 {'max_output_tokens':700},{'max_output_tokens':8192.0},{'history_policy':workflow.LEGACY_HISTORY},
                 {'context_tokens':8192},{'context_tokens':65536.0},{'context_basis':''}]
        for change in changes:
            with self.subTest(change=change),patch.object(workflow,'http_json') as http:
                value=self.runtime();value.update(change)
                with self.assertRaises(ValueError):workflow.ollama_adapter(value)
                http.assert_not_called()

    def test_all_three_pins_required_and_no_smaller_installed_model_fallback(self):
        with patch.object(workflow,'http_json',side_effect=self.metadata_http):
            self.assertTrue(workflow.preflight(self.runtime())['ready'])
            for key in ('digest','template_sha256','engine_version'):
                for replacement in (None,'wrong'):
                    with self.subTest(pin=key,replacement=replacement):
                        value=self.runtime();value[key]=replacement
                        self.assertFalse(workflow.preflight(value)['ready'])
                        with self.assertRaises(RuntimeError):workflow.ollama_adapter(value)
        def absent(url,body=None,headers=None,timeout=30):
            if url.endswith('/api/tags'):
                return {'models':[{'name':'qwen3:1.7b','digest':'b'*64}]}
            return self.metadata_http(url,body,headers,timeout)
        with patch.object(workflow,'http_json',side_effect=absent):
            status=workflow.preflight(self.runtime())
            self.assertFalse(status['ready'])
            self.assertFalse(status['installed'])
            with self.assertRaises(RuntimeError):workflow.ollama_adapter(self.runtime())

    def test_pin_change_between_stages_prevents_model_request(self):
        with patch.object(workflow,'preflight',side_effect=[{'ready':True},{'ready':False}]),patch.object(workflow,'http_json') as http:
            adapter=workflow.ollama_adapter(self.runtime())
            with self.assertRaisesRegex(RuntimeError,'Pinned runtime changed'):
                adapter([{'role':'user','content':'synthetic'}])
            http.assert_not_called()

    def test_context_screen_rejects_without_truncation_or_model_request(self):
        messages=[{'role':'user','content':'long synthetic input '*4000}]
        original=json.dumps(messages)
        with patch.object(workflow,'preflight',return_value={'ready':True}),patch.object(workflow,'http_json') as http:
            adapter=workflow.ollama_adapter(self.runtime())
            with self.assertRaisesRegex(RuntimeError,'not a tokenizer count'):adapter(messages)
            http.assert_not_called()
        self.assertEqual(json.dumps(messages),original)

    def test_recorded_context_revision_is_explicit_not_an_automatic_reduction(self):
        value=self.runtime();value['context_tokens']=32768
        value['context_basis']='Synthetic test of an explicitly recorded engineering revision.'
        self.assertEqual(workflow.validate_runtime(value),'4.3')
        legacy=self.runtime();legacy.update(workflow.PROTOCOLS['4.2']);legacy['protocol_version']='4.2'
        self.assertEqual(workflow.validate_runtime(legacy),'4.2')

    def test_prepare_keeps_historical_and_edited_runtime_candidates(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(workflow,'OUT',Path(folder)):
            old=Path(folder)/'runtime_candidate.json';old.write_bytes(b'historical snapshot')
            with self.assertRaises(ValueError):workflow.prepare('4.2')
            self.assertEqual(list(Path(folder).iterdir()),[old])
            result=workflow.prepare('4.3')
            self.assertEqual(result['AI_calls'],0)
            self.assertEqual(old.read_bytes(),b'historical snapshot')
            new=Path(folder)/'runtime_candidate_v43.json'
            self.assertEqual(read(new)['model'],'qwen3.5:4b-q4_K_M')
            self.assertEqual(read(new)['history_policy'],workflow.EXPLICIT_HISTORY)
            before=new.read_bytes();workflow.prepare('4.3')
            self.assertEqual(new.read_bytes(),before)
            modified=read(new);modified['digest']='locally pinned record';write(new,modified)
            with self.assertRaises(FileExistsError):workflow.prepare('4.3')
            self.assertEqual(read(new)['digest'],'locally pinned record')
            self.assertEqual(old.read_bytes(),b'historical snapshot')

if __name__=='__main__':unittest.main()
