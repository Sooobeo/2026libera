"""Synthetic gate and loopback fake HTTP only; no real model/server request."""
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import sector_v48_main_transport as transport
from test_sector_v48_transport import FakeServer


class MainTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),FakeServer)
        prior=transport.remote.read(transport.base.ROOT/'data/local_sector_runtime/laptop_latency_4b_20261018/4b_threads2/model_observation.json')
        self.server.template=prior['show']['template'];self.server.mode=None;self.server.show_count=0
        self.server.source='ubs_july_2026';self.server.generations=[];self.server.renders=[];self.server.unloads=[]
        self.server.release=threading.Event();self.server.cancel_path=self.root/'CANCEL'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.log=self.root/'fake.log';self.log.write_bytes(b'synthetic fake server only')
        self.runtime=transport.runtime_v48();self.contract={'common_instructions':['Synthetic fixture instruction.']}
        self.manifest={'roster':[{'case_id':'ubs_july_2026__R4','source_id':'ubs_july_2026','arm':'R4','split':'main'}]}
        self.gate={'authorized_run_root':str(self.root/'run')}
        self.verified=(self.manifest,self.runtime,self.contract,{}, {},self.gate,{}, {})
        self.context={'manifest_path':str(self.root/'synthetic_manifest.json'),'gate_path':str(self.root/'synthetic_gate.json'),'run_root':str(self.root/'run')}
        (self.root/'run/ubs_july_2026__R4').mkdir(parents=True)
        self.history_patch=patch.object(transport,'validate_authored_history',return_value={'status':'mocked_history_for_transport_io_fixture'})
        self.history_patch.start()

    def tearDown(self):
        self.history_patch.stop()
        self.server.release.set();self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def kwargs(self,endpoint='C0'):
        stage=int(endpoint[-1]) if endpoint.startswith('stage') else 4;visible=stage==4
        system=transport.build_system(self.contract)
        body=transport.request_header(self.runtime,stage,visible)
        body['messages']=[{'role':'system','content':system},{'role':'user','content':json.dumps({'stage':stage,'task':'synthetic fixture'})}]
        return dict(body=body,target=self.root/'run/ubs_july_2026__R4'/endpoint,runtime=self.runtime,stage=stage,
            institution_visible=visible,expected_source_id=self.server.source if visible else None,expected_system=system,
            origin=self.origin,cancel_path=self.server.cancel_path,server_log=self.log,execution_context=self.context)

    def execute_sync_fake_http(self,**kwargs):
        def supervise(spec_path,deadline,cancel):
            exit_code=transport.worker(spec_path)
            return {'status':'worker_exited','worker_exit_code':exit_code,
                'worker':transport.remote.read(spec_path.parent/'worker_summary.json'),**transport.call_accounting(spec_path.parent)}
        with patch.object(transport,'verify_main_gate',return_value=self.verified),patch.object(transport,'supervise',side_effect=supervise),patch.object(transport.bench.ProbeSession,'start_monitor'):
            return transport.run_transport(**kwargs)

    def test_main_counts_in_worker_supervisor_and_result(self):
        result=self.execute_sync_fake_http(**self.kwargs())
        self.assertEqual(result['status'],'completed')
        for level in (result,result['supervisor'],result['supervisor']['worker']):
            self.assertEqual(level['main_model_calls'],1);self.assertEqual(level['generation_requests_attempted'],1)
            self.assertEqual(level['execution_scope'],'main')
        self.assertEqual(len(self.server.generations),1);self.assertEqual(len(self.server.renders),1)
        self.assertEqual(result['supervisor']['worker']['warmup_generation_calls'],0)

    def test_model_contract_failure_counts_and_keeps_raw(self):
        self.server.mode='schema_error'
        result=self.execute_sync_fake_http(**self.kwargs())
        self.assertEqual(result['status'],'model_contract_failure');self.assertFalse(result['system_integrity_incident'])
        self.assertEqual(result['main_model_calls'],1);self.assertTrue(Path(result['response_path']).is_file())

    def test_R4_preexposure_source_absent_and_no_fallback(self):
        result=self.execute_sync_fake_http(**self.kwargs('stage1'))
        self.assertEqual(result['status'],'completed');self.assertEqual(result['main_model_calls'],1)
        body=self.server.generations[0];self.assertFalse(body['truncate']);self.assertFalse(body['shift'])
        self.assertIsNone(json.loads(result['response']['message']['content'])['source_id'])

    def test_invalid_gate_prevents_any_http_or_artifact(self):
        args=self.kwargs()
        with patch.object(transport,'verify_main_gate',side_effect=ValueError('synthetic missing approval')):
            with self.assertRaises(ValueError):transport.run_transport(**args)
        self.assertEqual(self.server.generations,[]);self.assertEqual(self.server.renders,[]);self.assertEqual(self.server.unloads,[])
        self.assertFalse(args['target'].exists())

    def test_endpoint_scope_source_and_frozen_system_are_required(self):
        for field in ('outside','identity','stage','system','context'):
            args=self.kwargs('stage1')
            if field=='outside':args['target']=self.root/'unapproved/stage1'
            if field=='identity':args['expected_source_id']=self.server.source
            if field=='stage':args['stage']=4
            if field=='system':args['expected_system']='changed';args['body']['messages'][0]['content']='changed'
            if field=='context':args['execution_context']={}
            with patch.object(transport,'verify_main_gate',return_value=self.verified):
                with self.assertRaises(ValueError):transport.run_transport(**args)
        self.assertEqual(self.server.generations,[]);self.assertEqual(self.server.renders,[])

    def test_render_pin_and_cleanup_failures_are_system_incidents(self):
        for endpoint,mode in (('C0','drop_render'),('C1','pin_change'),('C2','bad_unload')):
            self.server.mode=mode;self.server.show_count=0
            result=self.execute_sync_fake_http(**self.kwargs(endpoint))
            self.assertTrue(result['system_integrity_incident'])
            self.assertEqual(result['main_model_calls'],1 if mode=='bad_unload' else 0)

    def test_partial_summary_supervisor_retains_cancel_and_count(self):
        args=self.kwargs();target=args['target'];target.mkdir()
        spec={k:copy.deepcopy(args[k]) for k in ('body','runtime','stage','institution_visible','expected_source_id','expected_system','origin','execution_context')}
        spec.update(target_path=str(target),cancel_path=str(args['cancel_path']),deadline_seconds=900)
        transport.remote.save(target/'worker_spec.json',spec)
        class KilledWriter:
            returncode=None
            def __init__(inner,*unused,**kwargs):
                call=target/'http_0001_generation';call.mkdir();transport.remote.save(call/'request.json',{'fixture':True})
                (target/'worker_summary.json').write_text('{',encoding='utf8');args['cancel_path'].write_text('synthetic cancel')
            def poll(inner):return inner.returncode
            def kill(inner):inner.returncode=-9
            def wait(inner,timeout=None):return inner.returncode
        with patch.object(transport,'verify_main_gate',return_value=self.verified),patch.object(transport.subprocess,'Popen',KilledWriter):
            result=transport.supervise(target/'worker_spec.json',900,args['cancel_path'])
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['main_model_calls'],1)
        self.assertIn('worker_summary_read_error',result)
        self.assertEqual(self.server.generations,[])

    def test_pre_generation_cancel_keeps_zero_main_count(self):
        self.server.cancel_path.write_text('synthetic cancel')
        result=self.execute_sync_fake_http(**self.kwargs())
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['main_model_calls'],0)
        self.assertFalse(result['system_integrity_incident']);self.assertEqual(self.server.generations,[])


if __name__=='__main__':unittest.main()
