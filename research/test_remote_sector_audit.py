"""Offline audit fixtures only: no model requests, remote actions or gold labels."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import audit_remote_sector_artifacts as audit
from run_sector_workflow import run_case, runtime_candidate_v43


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')


class ArtifactAuditTests(unittest.TestCase):
    def fixture(self, root, failed_first=False):
        folder = root/'pilot_v43'; base = folder/'pilot'
        runtime = runtime_candidate_v43()
        runtime.update(digest=audit.DIGEST, engine_version=audit.ENGINE,
                       template_sha256=audit.sha(b'fixture'), intended_split='pilot',
                       main_authorized_by_this_file=False)
        save(folder/'runtime_pinned.json', runtime)
        snapshot = {'ollama_version':{'status':'ok','value':{'version':audit.ENGINE}},
                    'ollama_tags':{'status':'ok','value':{'models':[{'name':audit.MODEL,'digest':audit.DIGEST}]}}}
        save(folder/'inventory_before.json', snapshot); save(folder/'inventory_after.json', snapshot)
        save(base/'runtime.json', {'settings':runtime,'split':'pilot'})
        save(base/'dependencies.json', {'fixture':True})
        hashes = {name:audit.sha(name.encode()) for name in audit.DEPLOYED}
        save(base/'input_hashes.json', dict(zip(
            ('coordinator_sha256','runner_sha256','engine_sha256','market_sha256','packets_sha256'),
            (hashes[x] for x in audit.DEPLOYED))))
        packets = [{'source_id':source,'split':'pilot','evidence_passages':[
            {'evidence_id':source+'_e1','text':'Synthetic evidence only'}]} for source in audit.SOURCES]
        # Invalid/empty allocations are permitted as observed proposals; this audit
        # must never upgrade arithmetic consistency to semantic approval.
        market = {'fixture':'no market recommendation'}
        rows = [{'case_id':source+'__'+arm,'source_id':source,'arm':arm,'status':'not_started'}
                for source in audit.SOURCES for arm in ('R1','R4')]
        save(base/'planned_cases.json', rows)
        calls = []
        for row in rows:
            if failed_first and calls:break
            before = len(calls)
            def adapter(messages):
                call_folder = folder/f'http_{len(calls)+1:04}_pilot'
                content = 'bad json' if failed_first else '  {"weights":[],"submitted_constraints":[],"unresolved":["synthetic"]}\n'
                event = {'model':audit.MODEL,'done':True,'done_reason':'stop',
                         'message':{'role':'assistant','content':content}}
                request = {'model':audit.MODEL,'messages':copy.deepcopy(messages),'stream':True,
                           'think':False,'format':'json','keep_alive':0,
                           'options':{'temperature':0,'num_predict':8192,'num_ctx':65536}}
                save(call_folder/'request.json', {'path':'/api/chat','body':request,'kind':'pilot'})
                save(call_folder/'response.json', event)
                (call_folder/'raw_stream.bin').write_bytes(json.dumps(event).encode()+b'\n')
                (call_folder/'events.jsonl').write_text(json.dumps({'elapsed_seconds':1,'event':event})+'\n', encoding='utf-8')
                result = {'kind':'pilot','folder':call_folder.name,'status':'completed','http_status':200,
                          'no_automatic_retry':True,'unexpected_thinking_with_disabled_request':False}
                save(call_folder/'result.json', result); calls.append(result)
                return event
            packet = next(p for p in packets if p['source_id'] == row['source_id'])
            try:
                run_case(packet,row['arm'],market,adapter,base/row['case_id'])
                row['status'] = 'completed'
            except ValueError:
                row['status'] = 'failed'
                save(base/(row['case_id']+'_coordinator_failure.json'), row)
            row['model_calls_attempted'] = len(calls)-before
            row['http_call_folders'] = [x['folder'] for x in calls[before:]]
        summary = {'split':'pilot','planned_runs':4,'attempted_runs':sum(x['status']!='not_started' for x in rows),
                   'completed_runs':sum(x['status']=='completed' for x in rows),'records':rows,
                   'pilot_model_calls':len(calls),'main_model_calls':0,
                   'status':'incomplete' if failed_first else 'completed'}
        save(base/'summary.json',summary); save(folder/'summary.json',{**summary,'calls':calls})
        return folder, packets, market, hashes, runtime

    def run_audit(self, root, fixture):
        state = audit.Audit(root)
        result = audit.pilot_check(state,*fixture)
        return state,result

    def test_four_cases_sixteen_calls_and_exact_history_without_semantic_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root)
            state,result = self.run_audit(root,fixture)
            self.assertEqual([x for x in state.checks if x['status']!='pass'], [])
            self.assertEqual((result['attempted_cases'],result['completed_cases'],result['not_started_cases']), (4,4,0))
            self.assertEqual((result['attempted_http_calls'],result['completed_stage_records']), (16,16))
            self.assertTrue(any('per-call observations were not persisted' in x for x in state.limitations))
            self.assertNotIn('human_semantic_pass', result)

    def test_failed_first_retained_and_unstarted_not_model_errors(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); state,result = self.run_audit(root,self.fixture(root,failed_first=True))
            self.assertEqual([x for x in state.checks if x['status']!='pass'], [])
            self.assertEqual((result['attempted_cases'],result['completed_cases'],result['not_started_cases'],result['failed_cases']), (1,0,3,1))
            self.assertEqual((result['attempted_http_calls'],result['completed_stage_records']), (1,0))

    def test_modified_past_content_and_document_timing_are_detected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root)
            path = fixture[0]/'pilot'/f'{audit.SOURCES[0]}__R4'/'stage2_request.json'
            messages = json.loads(path.read_text(encoding='utf-8'))
            messages[2]['content'] = 'changed prior final content'
            messages[-1]['content'] = json.dumps({'stage':2,'institution_document':fixture[1][0]})
            save(path,messages)
            state,_ = self.run_audit(root,fixture)
            failed = [x['check'] for x in state.checks if x['status']=='fail']
            self.assertTrue(any('exact_history_and_evidence_onset' in x for x in failed))
            self.assertTrue(any('HTTP_matches_saved_request' in x for x in failed))

    def test_missing_pilot_does_not_infer_remote_nonexecution(self):
        with tempfile.TemporaryDirectory() as name:
            state = audit.Audit(Path(name))
            result = audit.pilot_check(state,Path(name)/'absent',[],{}, {},None)
            self.assertIsNone(result['attempted_cases'])
            self.assertEqual(state.checks[0]['status'],'not_observed')

    def test_changed_request_setting_and_raw_response_are_detected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root)
            call = fixture[0]/'http_0001_pilot'
            path = call/'request.json'; value = json.loads(path.read_text(encoding='utf-8'))
            value['body']['options']['temperature'] = 0.7; save(path,value)
            path = call/'response.json'; value = json.loads(path.read_text(encoding='utf-8'))
            value['message']['content'] = '{}'; save(path,value)
            state,_ = self.run_audit(root,fixture)
            failed = [x['check'] for x in state.checks if x['status']=='fail']
            self.assertIn('pilot_call_settings',failed)
            self.assertIn('saved_response_is_assembled_raw_stream',failed)

    def test_changed_inventory_digest_is_detected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); fixture = self.fixture(root)
            path = fixture[0]/'inventory_after.json'; value = json.loads(path.read_text(encoding='utf-8'))
            value['ollama_tags']['value']['models'][0]['digest'] = '0'*64; save(path,value)
            state,_ = self.run_audit(root,fixture)
            self.assertIn('inventory_snapshot_engine_and_digest',
                          [x['check'] for x in state.checks if x['status']=='fail'])

    def test_deployment_filter_and_mutated_code_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); received = root/'received'
            corpus = [{'source_id':s,'split':'pilot','evidence_passages':[]} for s in audit.SOURCES]
            corpus.append({'source_id':'main_document','split':'main'})
            raw = b''.join(json.dumps(p).encode()+b'\n' for p in corpus)
            filtered = b''.join(json.dumps(p).encode()+b'\n' for p in corpus[:2])
            files = {}
            for relative in audit.DEPLOYED:
                path = root/relative; path.parent.mkdir(parents=True,exist_ok=True)
                value = raw if relative==audit.DEPLOYED[-1] else b'{}'
                path.write_bytes(value)
                files[relative] = audit.sha(filtered if relative==audit.DEPLOYED[-1] else value)
            save(received/'bundle_manifest.json',{'files':files,'source_packets_sha256':audit.sha(raw)})
            state = audit.Audit(root); audit.deployment(state,received,None)
            self.assertEqual([x for x in state.checks if x['status']!='pass'],[])
            (root/audit.DEPLOYED[0]).write_text('tampered',encoding='utf-8')
            state = audit.Audit(root); audit.deployment(state,received,None)
            self.assertIn('deployment_hash:'+audit.DEPLOYED[0],[x['check'] for x in state.checks if x['status']=='fail'])

    def test_tiny_roundoff_allowed_but_values_and_boolean_status_not_repaired(self):
        self.assertTrue(audit.calculator_equal({'metric':0.123456789}, {'metric':0.12345678900000001}))
        self.assertFalse(audit.calculator_equal({'metric':0.123}, {'metric':0.124}))
        self.assertFalse(audit.calculator_equal({'valid':True}, {'valid':1}))


if __name__=='__main__':
    unittest.main()
