"""Local fake HTTP only. These tests never contact or invoke a language model."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark_sector_latency as bench


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send_json(self,value):
        raw=json.dumps(value).encode(); self.send_response(200)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/api/version':return self.send_json({'version':bench.ENGINE})
        if self.path=='/api/tags':return self.send_json({'models':[{'name':name,'digest':digest} for name,digest in bench.MODELS.items()]})
        if self.path=='/api/ps':return self.send_json({'models':[]})
        self.send_error(404)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/api/show':return self.send_json({'template':'synthetic renderer only'})
        if self.path=='/api/generate':
            self.server.unloads.append(body)
            if self.server.unload_failure:return self.send_error(503)
            return self.send_json({'done':True})
        if self.path!='/api/chat':return self.send_error(404)
        self.server.chats.append(body)
        event={'model':body['model'],'done':True,'done_reason':'stop',
               'message':{'role':'assistant','content':'{"ready":true}'},
               'prompt_eval_count':222,'eval_count':6,'load_duration':1,
               'prompt_eval_duration':100000000,'eval_duration':100000000,'total_duration':200000001}
        if self.server.stall:
            self.send_response(200);self.send_header('Content-Type','application/x-ndjson');self.end_headers()
            self.wfile.write((json.dumps({'model':body['model'],'done':False,'message':{'content':'{'}})+'\n').encode());self.wfile.flush()
            self.server.release.wait(8)
            return
        return self.send_json(event)


class LatencyProbeTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),FakeOllama)
        self.server.chats=[];self.server.unloads=[];self.server.stall=False
        self.server.unload_failure=False
        self.server.release=threading.Event()
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.release.set();self.server.shutdown();self.server.server_close();self.thread.join()

    def test_three_exact_serial_synthetic_probes_and_selected_model_unload(self):
        with tempfile.TemporaryDirectory() as name,redirect_stdout(io.StringIO()):
            args=SimpleNamespace(base_url=self.origin,output_root=Path(name),run_id='fake',deadline_seconds=5)
            self.assertEqual(bench.run(args),0)
            report=json.loads((Path(name)/'fake'/'summary.json').read_text())
            self.assertEqual(report['completed_probes'],3)
            self.assertEqual(report['generation_request_envelopes_recorded'],3)
            self.assertEqual([x['model'] for x in self.server.chats],[x[1] for x in bench.PROBES])
            self.assertEqual([x['model'] for x in self.server.unloads],[x[1] for x in bench.PROBES])
            self.assertEqual([x['options']['num_thread'] for x in self.server.chats],[2,4,2])
            self.assertTrue(all(x['messages'][0]['content']==bench.PROMPT for x in self.server.chats))
            self.assertTrue(all(x['prompt_eval_count']==222 for x in report['records']))
            self.assertEqual((report['pilot_model_calls'],report['main_model_calls']),(0,0))

    def test_deadline_bounds_stalled_stream_and_preserves_partial_bytes(self):
        self.server.stall=True
        with tempfile.TemporaryDirectory() as name:
            target=Path(name);spec=target/'worker_spec.json'
            bench.remote.save(spec,{'origin':self.origin,'deadline_seconds':2,'body':bench.body_for(bench.PROBES[0][1],2)})
            started=time.monotonic();result=bench.supervised_worker(spec,2,target/'CANCEL')
            self.assertLess(time.monotonic()-started,3.5)
            self.assertEqual(result['supervisor_status'],'hard_deadline')
            self.assertTrue((target/'http_0001_latency_probe'/'raw_stream.bin').read_bytes())
            self.assertEqual(len(self.server.chats),1)

    def test_manifest_mismatch_stops_before_generation(self):
        def api(origin,path,body=None):
            if path=='/api/version':return {'version':bench.ENGINE}
            return {'models':[{'name':bench.PROBES[0][1],'digest':'0'*64}]}
        with patch.object(bench.remote,'api_json',side_effect=api):
            with self.assertRaises(RuntimeError):bench.observe(self.origin,bench.PROBES[0][1])
        self.assertEqual(self.server.chats,[])

    def test_probe_settings_are_explicit_and_not_research_context(self):
        self.assertTrue(1000<=len(bench.PROMPT)<=1200)
        for _,model,threads in bench.PROBES:
            body=bench.body_for(model,threads)
            self.assertIs(body['think'],False)
            self.assertEqual(body['options'],{'temperature':0,'num_ctx':8192,'num_predict':32,'num_thread':threads,
                'num_batch':512,'repeat_penalty':1.0,'presence_penalty':0.0,'frequency_penalty':0.0,'seed':3407})

    def test_failed_unload_blocks_later_probes_even_when_ps_is_empty(self):
        self.server.unload_failure=True
        with tempfile.TemporaryDirectory() as name,redirect_stdout(io.StringIO()):
            args=SimpleNamespace(base_url=self.origin,output_root=Path(name),run_id='failed_unload',deadline_seconds=5)
            self.assertEqual(bench.run(args),1)
            report=json.loads((Path(name)/'failed_unload'/'summary.json').read_text())
            self.assertEqual(report['status'],'stopped_idle_not_confirmed')
            self.assertEqual((report['completed_probes'],report['not_started_probes']),(1,2))
            self.assertEqual(len(self.server.chats),1)

    def test_unload_requires_explicit_done_and_ps_requires_models_array(self):
        for unload in ({'status':'unavailable','error':'timeout'},
                       {'status':'ok','value':{}}, {'status':'ok','value':{'done':False}}):
            with self.subTest(unload=unload),patch.object(bench.remote,'optional_api',side_effect=[
                unload,{'status':'ok','value':{'models':[]}}]):
                self.assertEqual(bench.unload_and_confirm(self.origin,bench.PROBES[0][1])['status'],'idle_not_confirmed')
        with patch.object(bench.remote,'optional_api',side_effect=[
                {'status':'ok','value':{'done':True}}]+[{'status':'ok','value':{}}]*3),patch.object(bench.time,'sleep'):
            self.assertEqual(bench.unload_and_confirm(self.origin,bench.PROBES[0][1])['status'],'idle_not_confirmed')

    def test_resource_only_worker_never_grades_against_synthetic_ready_answer(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);spec=folder/'worker_spec.json'
            bench.remote.save(spec,{'origin':self.origin,'deadline_seconds':5,
                'body':bench.body_for(bench.PROBES[0][1],2),'assessment_policy':'resource_only'})
            self.assertEqual(bench.worker(spec),0)
            summary=bench.remote.read(folder/'worker_summary.json')
            self.assertIsNone(summary['expected_synthetic_json'])
            self.assertEqual(summary['assessment_scope'],'not_graded_engineering_feasibility')
            self.assertEqual((summary['pilot_model_calls'],summary['main_model_calls']),(0,0))

    def test_single_probe_cli_runs_only_selected_model_with_same_request(self):
        with tempfile.TemporaryDirectory() as name,redirect_stdout(io.StringIO()):
            self.assertEqual(bench.main(['--base-url',self.origin,'--output-root',name,
                '--run-id','single','--deadline-seconds','5','--probe','1p7b_threads2']),0)
            report=bench.remote.read(Path(name)/'single'/'summary.json')
            invocation=bench.remote.read(Path(name)/'single'/'invocation.json')
            self.assertEqual(report['probe_invocations_attempted'],1)
            self.assertEqual(invocation['selected_probe_ids'],['1p7b_threads2'])
            self.assertEqual(self.server.chats,[bench.body_for('qwen3:1.7b',2)])

    def test_repeat_probe_options_preserve_selection_order_and_reject_duplicates(self):
        selected=bench.selected_probes(['1p7b_threads2','4b_threads4'])
        self.assertEqual([p[0] for p in selected],['1p7b_threads2','4b_threads4'])
        with self.assertRaises(ValueError):bench.selected_probes(['1p7b_threads2','1p7b_threads2'])
        self.assertEqual(self.server.chats,[])

    def test_missing_windows_memory_is_null_and_keeps_ps_monitor(self):
        with patch('probe_ollama_runtime.memory_snapshot',side_effect=OSError('collector unavailable')):
            value=bench.windows_memory_snapshot()
        self.assertIsNone(value['working_set_sum_bytes'])
        self.assertIsNone(value['available_physical_bytes'])
        self.assertEqual(value['memory_observation_status'],'not_observed')
        self.assertNotIn('rss_sum_bytes',value)
        with tempfile.TemporaryDirectory() as name,patch.object(bench.sys,'platform','win32'),patch.object(bench,'windows_memory_snapshot',return_value=value):
            session=bench.ProbeSession(Path(name),self.origin,timeout_seconds=5,monitor_seconds=0.05)
            session.start_monitor()
            deadline=time.monotonic()+2
            path=Path(name)/'monitor.jsonl'
            while time.monotonic()<deadline and (not path.exists() or not path.stat().st_size):time.sleep(0.01)
            session.stop_monitor()
            sample=json.loads(path.read_text().splitlines()[0])
            self.assertEqual(sample['ollama_ps']['status'],'ok')
            self.assertIsNone(sample['memory']['working_set_sum_bytes'])

    def test_windows_native_working_set_and_available_ram_are_distinct(self):
        snapshot={'global_memory_status_ex':{'available_physical_bytes':123456},
                  'ollama_process_memory':[{'memory_info':{'working_set_bytes':100,'private_bytes':900}},
                                           {'memory_info':{'rss':200}}, {'status':'open_failed'}]}
        with patch('probe_ollama_runtime.memory_snapshot',return_value=snapshot):value=bench.windows_memory_snapshot()
        self.assertEqual(value['working_set_sum_bytes'],300)
        self.assertEqual(value['working_set_observed_process_count'],2)
        self.assertEqual(value['available_physical_bytes'],123456)


if __name__=='__main__':unittest.main()
