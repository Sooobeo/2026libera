"""Local fake-HTTP tests; zero real model inference."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from research.v63.ollama_transport import OllamaTransport, packed, digest_bytes
from research.v63.runtime import response_schema, call_with_retries
from research.v63.transport_errors import InfraFailure, ProtocolViolation


@contextmanager
def server_fixture():
    state={'chats':[],'tags_calls':0,'chat_status':200,'drift_after_chat':False,'malformed':False,'partial':False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,value,status=200):
            body=packed(value)
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            if status==429:self.send_header('Retry-After','3')
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.path=='/api/version':self.respond({'version':state.get('version','0.35.1')})
            elif self.path=='/api/tags':
                state['tags_calls']+=1
                digest='drift' if state['drift_after_chat'] and state['chats'] else 'test-digest'
                self.respond({'models':[{'name':'test-model','digest':digest}]})
            else:self.respond({'error':'not_found'},404)
        def do_POST(self):
            body=self.rfile.read(int(self.headers.get('Content-Length',0)))
            if self.path=='/api/show':
                self.respond({'template':'TEST TEMPLATE','details':{'quantization_level':'Q4_K_M'},'capabilities':['completion','thinking']})
            elif self.path=='/api/chat':
                payload=json.loads(body)
                if payload.get('_debug_render_only'):
                    rendered='\n'.join(m['content'].strip() for m in payload['messages'])
                    if state.get('omit_render_history'):rendered='omitted'
                    self.respond({'model':'test-model','message':{'content':''},'eval_count':0,'prompt_eval_count':0,
                                  '_debug_info':{'rendered_template':rendered}})
                    return
                state['chats'].append(body)
                if state['partial']:
                    self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
                    self.wfile.write(b'{"model":');self.close_connection=True
                elif state['malformed']:
                    body=b'not json';self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                elif state['chat_status']!=200:self.respond({'error':'synthetic HTTP error'},state['chat_status'])
                else:self.respond({'model':'test-model','done':True,'done_reason':'stop',
                                    'message':{'content':'{"kind":"final","output":{}}'},'prompt_eval_count':20,'eval_count':8})
            else:self.respond({'error':'not_found'},404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.01),daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',state
    finally:server.shutdown();server.server_close();thread.join()


def freeze():
    return {'model':'test-model','model_sha256':'test-digest','engine_revision':'0.35.1',
            'chat_template_sha256':digest_bytes(b'TEST TEMPLATE'),'quantization_level':'Q4_K_M',
            'temperature':0,'output_tokens':128,'context_tokens':8192,'request_timeout':2,'think':False,
            'seed_support':'supported','seed':3407,
            'allowed_response_schema_sha256':[digest_bytes(packed(response_schema(i))) for i in (1,2,3)],
            'fixed_options':{'num_thread':4,'num_gpu':0}}


def request():
    return packed({'model':'test-model','messages':[{'role':'user','content':'synthetic engineering only'}],
                   'temperature':0,'max_output_tokens':128,'stream':False,'response_schema':response_schema(1),'seed':3407})


class OllamaTransportTests(unittest.TestCase):
    def test_exact_render_counter_keeps_history_and_performs_no_generation(self):
        class FakeNative:
            def receipt(self,text):return {'token_count':len(text.split()),'text_sha256':digest_bytes(text.encode())}
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            client=OllamaTransport(origin,freeze(),d);req=json.loads(request())
            count=client.render_and_count(req,FakeNative())
            self.assertEqual(count,3);self.assertEqual(state['chats'],[])
            self.assertTrue((Path(d)/'render_000001/tokenizer_receipt.json').is_file())
            state['omit_render_history']=True
            with self.assertRaises(ProtocolViolation):client.render_and_count(req,FakeNative())

    def test_provider_token_count_mismatch_is_protocol_violation_after_one_call(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            req=json.loads(request());req['expected_prompt_tokens']=999
            with self.assertRaises(ProtocolViolation) as ctx:OllamaTransport(origin,freeze(),d)(packed(req))
            self.assertTrue(ctx.exception.generation_attempted);self.assertEqual(len(state['chats']),1)
    def test_mapping_pins_and_raw_receipts(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            result=OllamaTransport(origin,freeze(),d)(request())
            self.assertEqual(result['usage']['prompt_eval_count'],20)
            self.assertEqual(result['model_sha256'],'test-digest')
            self.assertEqual(len(state['chats']),1)
            self.assertEqual(state['tags_calls'],2)
            wire=json.loads(state['chats'][0])
            self.assertFalse(wire['stream']);self.assertFalse(wire['think'])
            self.assertFalse(wire['truncate']);self.assertFalse(wire['shift'])
            self.assertEqual(wire['options']['num_predict'],128)
            self.assertEqual(wire['options']['num_ctx'],8192)
            self.assertEqual(wire['options']['seed'],3407)
            self.assertEqual(wire['format'],response_schema(1))
            folder=Path(d)/'attempt_000001'
            self.assertEqual((folder/'generation.request.bin').read_bytes(),state['chats'][0])
            self.assertTrue((folder/'generation.response.bin').is_file())

    def test_schema_or_sampler_drift_prevents_generation(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            client=OllamaTransport(origin,freeze(),d)
            raw=json.loads(request());raw['response_schema']={'type':'string'}
            with self.assertRaises(ProtocolViolation):client(packed(raw))
            raw=json.loads(request());raw['temperature']=1
            with self.assertRaises(ProtocolViolation):client(packed(raw))
            self.assertEqual(state['chats'],[])

    def test_before_version_drift_zero_generation_requests(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            state['version']='different'
            events=[]
            with self.assertRaises(ProtocolViolation):call_with_retries(OllamaTransport(origin,freeze(),d),request(),events)
            self.assertEqual(state['chats'],[])
            self.assertEqual(events[0]['generation_requests'],0)

    def test_after_digest_drift_preserves_generation_count(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            state['drift_after_chat']=True;events=[]
            with self.assertRaises(ProtocolViolation):call_with_retries(OllamaTransport(origin,freeze(),d),request(),events)
            self.assertEqual(len(state['chats']),1)
            self.assertEqual(events[0]['generation_requests'],1)
            self.assertTrue((Path(d)/'attempt_000001/generation.response.bin').is_file())

    def test_http_status_mapping_and_no_adapter_auto_retry(self):
        for status,retryable in [(429,True),(503,True),(400,False),(403,False)]:
            with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
                state['chat_status']=status
                with self.assertRaises(InfraFailure) as ctx:OllamaTransport(origin,freeze(),d)(request())
                self.assertEqual(ctx.exception.retryable,retryable)
                self.assertEqual(ctx.exception.retry_after,3 if status==429 else 0)
                self.assertEqual(len(state['chats']),1)

    def test_runtime_retries_identical_wire_bytes_and_respects_retry_after(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            state['chat_status']=429;events=[];sleeps=[]
            client=OllamaTransport(origin,freeze(),d)
            def sleep(seconds):sleeps.append(seconds);state['chat_status']=200
            call_with_retries(client,request(),events,sleep=sleep)
            self.assertEqual(len(state['chats']),2)
            self.assertEqual(state['chats'][0],state['chats'][1])
            self.assertEqual(sleeps,[3])
            self.assertEqual(sum(e['generation_requests'] for e in events),2)

    def test_partial_content_is_preserved_and_not_retried(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            state['partial']=True;events=[]
            result=call_with_retries(OllamaTransport(origin,freeze(),d),request(),events,sleep=lambda s:self.fail('must not retry'))
            self.assertEqual(result['finish_reason'],'incomplete')
            self.assertEqual(result['content'],'{"model":')
            self.assertEqual(len(state['chats']),1)
            self.assertEqual((Path(d)/'attempt_000001/generation.response.bin').read_bytes(),b'{"model":')

    def test_malformed_envelope_is_incomplete_not_regenerated(self):
        with server_fixture() as (origin,state),tempfile.TemporaryDirectory() as d:
            state['malformed']=True
            result=OllamaTransport(origin,freeze(),d)(request())
            self.assertEqual(result['finish_reason'],'incomplete')
            self.assertEqual(result['content'],'not json')
            self.assertEqual(len(state['chats']),1)


if __name__=='__main__':unittest.main()
