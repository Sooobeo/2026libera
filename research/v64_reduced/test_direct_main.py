"""Direct-main dispatch policy tests using fake HTTP; zero real inference."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from research.v63.campaign import runtime_identity
from research.v63.ollama_transport import OllamaTransport, packed, digest_bytes
from research.v63.start_direct_main import build_config
from research.v63.test_ollama_transport import server_fixture, freeze, request
from research.v63.transport_errors import InfraFailure
from research.v64_reduced import runtime
from research.v64_reduced.design import make_main_only_design, select_phase_schedule

ROOT=Path(__file__).resolve().parents[2]


class DirectMainTests(unittest.TestCase):
    def test_removes_only_duplicate_identity_requests_and_keeps_both_generation_checks(self):
        class Tokenizer:
            def receipt(self,text):
                return {'token_count':20,'text_sha256':digest_bytes(text.encode())}
        with server_fixture() as (origin,state), tempfile.TemporaryDirectory() as directory:
            frozen=freeze()
            frozen['skip_duplicate_render_identity']=True
            client=OllamaTransport(origin,frozen,directory)
            req=json.loads(request())
            self.assertEqual(client.render_and_count(req,Tokenizer()),20)
            self.assertEqual(state['tags_calls'],0)
            self.assertEqual(len(state['chats']),0)
            client(packed(req))
            self.assertEqual(state['tags_calls'],2)
            self.assertEqual(len(state['chats']),1)

    def test_uncertain_generation_failure_does_not_dispatch_a_retry(self):
        attempts=[]
        def client(raw):
            attempts.append(raw)
            raise InfraFailure('synthetic timeout',retryable=True,generation_attempted=True)
        events=[]
        with self.assertRaises(InfraFailure):
            runtime.call_model(client,b'fixed request',events,{'allow_infrastructure_retries':False})
        self.assertEqual(len(attempts),1)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['generation_requests'],1)

    def test_preliminary_waiver_does_not_hide_missing_model_or_artifact(self):
        frozen={'execution_phase':'B-main','direct_main_authorization':{
            'user_requested_no_preliminary_validation':True,'preliminary_phases_skipped':True}}
        errors=runtime.execution_gate_errors(frozen)
        self.assertNotIn('pilot_measurements',errors)
        self.assertNotIn('full_history_capacity',errors)
        self.assertIn('missing_model',errors)
        self.assertIn('frozen_artifacts_missing',errors)
        self.assertNotIn('gates',frozen)

    def test_config_and_identity_bind_four_arms_policy_and_no_preliminary_budget(self):
        base=ROOT/'data/v63_20261027/continuation/deployment/local_windows/candidate_005/campaign_config.json'
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            config=json.loads(build_config(base,Path(directory)).read_text(encoding='utf-8'))
            self.assertEqual(set(config['phase_budgets']),{'B-main'})
            self.assertEqual(config['main_direct_design']['arms'],['R0','R1','R2','R3'])
            self.assertFalse(config['allow_infrastructure_retries'])
            self.assertTrue(config['skip_duplicate_render_identity'])
            self.assertEqual(len(select_phase_schedule('B-main',None,design=make_main_only_design())),160)
            frozen=json.loads((ROOT/config['runtime_freeze_path']).read_text(encoding='utf-8-sig'))
            tokenizer={'sha256':'test-tokenizer'}
            amendment=config['execution_amendment']
            original,_=runtime_identity(ROOT,frozen,tokenizer,amendment,config)
            for field,value in [('skip_duplicate_render_identity',False),('allow_infrastructure_retries',True),
                                ('weight_policy','raw_only'),
                                ('main_direct_design',{'arms':['R0','R1','R2','R3','C-context']})]:
                changed=deepcopy(config)
                changed[field]=value
                different,_=runtime_identity(ROOT,frozen,tokenizer,amendment,changed)
                self.assertNotEqual(original,different)


if __name__=='__main__':
    unittest.main()
