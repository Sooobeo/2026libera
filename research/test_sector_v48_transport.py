"""Offline/fake HTTP checks only; no installed model is invoked."""
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import sector_v48_transport as transport


class FakeServer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/version': return self.send_json({'version': transport.ENGINE})
        if self.path == '/api/tags': return self.send_json({'models': [{'name': transport.MODEL, 'digest': transport.DIGEST}]})
        if self.path == '/api/ps': return self.send_json({'models': []})
        self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/show':
            self.server.show_count += 1
            suffix = ' changed' if self.server.mode == 'pin_change' and self.server.show_count >= 2 else ''
            return self.send_json({'template': self.server.template + suffix})
        if self.path == '/api/generate':
            self.server.unloads.append(body)
            return self.send_json({'error': 'fake failure'}, 503) if self.server.mode == 'bad_unload' else self.send_json({'done': True})
        if self.path != '/api/chat': return self.send_error(404)
        if body.get('_debug_render_only'):
            self.server.renders.append(body)
            contents = [m['content'].strip(' \t\r\n') for m in body['messages']]
            if self.server.mode == 'drop_render': contents = contents[1:]
            value = {'model': transport.MODEL, '_debug_info': {'rendered_template': '\n<role>\n'.join(contents)}}
            if self.server.mode == 'render_generation': value['message'] = {'content': 'unexpected inference'}
            return self.send_json(value)
        self.server.generations.append(body)
        if self.server.mode == 'cancel_partial':
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            self.wfile.write((json.dumps({'model': transport.MODEL, 'done': False, 'message': {'content': '{'}}) + '\n').encode())
            self.wfile.flush()
            self.server.cancel_path.write_text('fake cancellation', encoding='utf-8')
            self.server.release.wait(3)
            return
        visible = body['format']['properties']['interpretations']['maxItems'] > 0
        stage = json.loads(body['messages'][-1]['content'])['stage']
        codes = ['10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60']
        value = {'source_id': self.server.source if visible else None,
            'interpretations': [{'sector_code': c, 'rating': 'fixture', 'evidence_ids': [], 'reason': 'fixture'} for c in codes] if visible else [],
            'weights': [{'sector_code': c, 'weight': 0.1 if i < 10 else 0, 'rationale': 'fixture', 'evidence_ids': []} for i, c in enumerate(codes)] if stage >= 3 else [],
            'alternatives': 'fixture', 'risk_discussion': 'fixture', 'unresolved': [], 'submitted_constraints': []}
        if self.server.mode == 'numeric_error': value['weights'][0]['weight'] = -0.3
        if self.server.mode == 'schema_error': value.pop('risk_discussion')
        reason = 'length' if self.server.mode == 'length' else 'stop'
        content = '{' if self.server.mode in ('invalid_json', 'length') else json.dumps(value) + '\n'
        return self.send_json({'model': transport.MODEL, 'message': {'role': 'assistant', 'content': content},
                              'done': True, 'done_reason': reason, 'eval_count': 1, 'prompt_eval_count': 1})


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeServer)
        prior = transport.remote.read(transport.base.ROOT / 'data/local_sector_runtime/laptop_latency_4b_20261018/4b_threads2/model_observation.json')
        self.server.template = prior['show']['template']
        self.server.mode = None
        self.server.show_count = 0
        self.server.source = 'ubs_june_2026'
        self.server.generations, self.server.renders, self.server.unloads = [], [], []
        self.server.release = threading.Event()
        self.server.cancel_path = self.folder / 'CANCEL'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.log = self.folder / 'fake.log'
        self.log.write_bytes(b'fake service only\n')

    def tearDown(self):
        self.server.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.tmp.cleanup()

    def kwargs(self, stage=4, visible=True, name='call'):
        runtime = transport.runtime_v48()
        system = 'A declared v4.8 test system; no actual financial instruction.'
        body = transport.request_header(runtime, stage, visible)
        body['messages'] = [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': json.dumps({'stage': stage, 'task': 'Synthetic fixture'})}]
        return dict(body=body, target=self.folder / name, runtime=runtime, stage=stage,
            institution_visible=visible, expected_source_id=self.server.source if visible else None,
            expected_system=system, origin=self.origin, cancel_path=self.server.cancel_path, server_log=self.log)

    def test_R4_preexposure_generic_system_and_schema(self):
        args = self.kwargs(stage=1, visible=False)
        args['target'].mkdir()
        result = transport.run_transport(**args)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(result['system_integrity_incident'])
        value = json.loads(result['response']['message']['content'])
        self.assertIsNone(value['source_id']); self.assertEqual(value['interpretations'], [])
        self.assertEqual(value['weights'], [])
        self.assertEqual(len(self.server.generations), 1); self.assertEqual(len(self.server.renders), 1)
        self.assertEqual(self.server.generations[0], args['body'])
        self.assertFalse(args['body']['truncate']); self.assertFalse(args['body']['shift'])
        validation = transport.remote.read(args['target'] / 'response_contract_validation.json')
        self.assertTrue(validation['source_identity_matches_visible_metadata'])
        self.assertEqual(result['generation_requests_attempted'], 1)
        self.assertEqual(result['supervisor']['worker']['warmup_generation_calls'], 0)

    def test_visible_UBS_and_numeric_errors_not_semantic_gate(self):
        self.server.mode = 'numeric_error'
        args = self.kwargs()
        result = transport.run_transport(**args)
        self.assertEqual(result['status'], 'completed')
        value = json.loads(result['response']['message']['content'])
        self.assertEqual(value['source_id'], 'ubs_june_2026')
        self.assertEqual(value['weights'][0]['weight'], -0.3)
        self.assertEqual(len(self.server.generations), 1)

    def test_schema_and_json_failure_keep_raw_without_retry(self):
        for mode in ('schema_error', 'invalid_json'):
            self.server.mode = mode
            result = transport.run_transport(**self.kwargs(name=mode))
            self.assertEqual(result['status'], 'model_contract_failure')
            self.assertFalse(result['system_integrity_incident'])
            self.assertIsNotNone(result['response'])
            self.assertTrue(Path(result['response_path']).is_file())
            self.assertEqual(result['supervisor']['worker']['failure_class'], 'model_contract_failure')
            self.assertEqual(result['generation_requests_attempted'], 1)
        self.assertEqual(len(self.server.generations), 2)

    def test_render_failures_prevent_generation_and_classify_instrument(self):
        for mode in ('drop_render', 'render_generation'):
            self.server.mode = mode
            result = transport.run_transport(**self.kwargs(name=mode))
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['system_integrity_incident'])
            self.assertEqual(result['generation_requests_attempted'], 0)
            self.assertEqual(result['supervisor']['worker']['failure_class'], 'execution_or_instrument_failure')
            if mode == 'render_generation': self.assertTrue(result['unexpected_generation_evidence_in_render'])
        self.assertEqual(self.server.generations, [])

    def test_pin_change_after_render_prevents_generation(self):
        self.server.mode = 'pin_change'
        result = transport.run_transport(**self.kwargs())
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['system_integrity_incident'])
        self.assertEqual(len(self.server.renders), 1)
        self.assertEqual(self.server.generations, [])

    def test_truncation_kept_and_separate_from_schema_failure(self):
        self.server.mode = 'length'
        result = transport.run_transport(**self.kwargs())
        self.assertEqual(result['status'], 'output_limit_reached')
        self.assertFalse(result['system_integrity_incident'])
        self.assertEqual(result['response']['message']['content'], '{')
        self.assertEqual(result['supervisor']['worker']['failure_class'], 'model_output_truncation')

    def test_partial_cancel_count_survives_killed_worker(self):
        self.server.mode = 'cancel_partial'
        result = transport.run_transport(**self.kwargs())
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['system_integrity_incident'])
        self.assertEqual(result['generation_requests_attempted'], 1)
        self.assertTrue(result['raw_stream_present'])
        self.assertEqual(result['http_streams_completed'], 0)
        self.assertEqual(len(self.server.generations), 1)

    def test_unload_failure_blocks_next_call_and_retains_response(self):
        self.server.mode = 'bad_unload'
        result = transport.run_transport(**self.kwargs())
        self.assertEqual(result['status'], 'cleanup_not_confirmed')
        self.assertTrue(result['system_integrity_incident'])
        self.assertIsNotNone(result['response'])
        self.assertEqual(len(self.server.generations), 1)

    def test_hidden_source_metadata_and_header_mutation_rejected_offline(self):
        for field in ('identity', 'header', 'system'):
            args = self.kwargs(stage=1, visible=False, name=field)
            if field == 'identity': args['expected_source_id'] = 'fidelity_q2_2026'
            if field == 'header': args['body']['options']['num_predict'] = 123
            if field == 'system': args['body']['messages'][0]['content'] = 'changed'
            with self.assertRaises(ValueError): transport.run_transport(**args)
        self.assertEqual(self.server.generations, []); self.assertEqual(self.server.renders, [])

    def test_renderer_only_ascii_boundary_whitespace(self):
        messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': ' \t{ "a": 1 }\r\n'}]
        response = {'model': transport.MODEL, '_debug_info': {'rendered_template': 'system\n{ "a": 1 }'}}
        value = transport.validate_render(response, messages, 'system')
        self.assertEqual(value['message_count'], 2)
        changed = copy.deepcopy(response)
        changed['_debug_info']['rendered_template'] = 'system\n{"a":1}'
        with self.assertRaises(ValueError): transport.validate_render(changed, messages, 'system')
        messages[1]['content'] = '\v{ "a": 1 }'
        with self.assertRaises(ValueError): transport.validate_render(response, messages, 'system')

    def test_generation_timeout_is_case_failure_other_provider_error_is_instrument(self):
        for failure_status, expected_incident in (('timeout', False), ('failed', True)):
            args = self.kwargs(name=failure_status)
            args['target'].mkdir()
            spec = {k: args[k] for k in ('body', 'runtime', 'stage', 'institution_visible', 'expected_source_id', 'expected_system', 'origin')}
            spec.update(cancel_path=str(args['cancel_path']), deadline_seconds=900)
            path = args['target'] / 'worker_spec.json'
            transport.remote.save(path, spec)
            with patch.object(transport.remote, 'stream_call', side_effect=transport.remote.RemoteCallError({'status': failure_status})), patch.object(transport.bench.ProbeSession, 'start_monitor'), patch.object(transport, 'render_call'):
                self.assertEqual(transport.worker(path), 1)
            summary = transport.remote.read(args['target'] / 'worker_summary.json')
            self.assertEqual(summary['system_integrity_incident'], expected_incident)
            self.assertEqual(summary['failure_phase'], 'generation')

    def test_partial_result_artifact_keeps_request_denominator(self):
        target = self.folder / 'partial'
        call = target / 'http_0001_generation'
        call.mkdir(parents=True)
        (call / 'request.json').write_text('{}', encoding='utf-8')
        (call / 'result.json').write_text('{', encoding='utf-8')
        result = transport.call_accounting(target)
        self.assertEqual(result['generation_requests_attempted'], 1)
        self.assertEqual(result['http_streams_completed'], 0)
        self.assertIn('http_0001_generation/result.json', result['accounting_artifact_errors'])

    def test_cancelled_partial_worker_summary_preserves_cancellation(self):
        args = self.kwargs(name='interrupted_summary')
        class InterruptedWriter:
            returncode = None
            def __init__(self, *unused, **kwargs):
                (args['target'] / 'worker_summary.json').write_text('{"status":', encoding='utf-8')
                args['cancel_path'].write_text('deterministic fake cancellation', encoding='utf-8')
            def poll(self): return self.returncode
            def kill(self): self.returncode = -1
            def wait(self, timeout=None): return self.returncode
        with patch.object(transport.subprocess, 'Popen', InterruptedWriter):
            result = transport.run_transport(**args)
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['system_integrity_incident'])
        self.assertIn('worker_summary_read_error', result['supervisor'])

    def test_uninterrupted_partial_worker_summary_remains_instrument_failure(self):
        args = self.kwargs(name='unexpected_partial_summary')
        class CompletedWriter:
            returncode = 0
            def __init__(self, *unused, **kwargs):
                (args['target'] / 'worker_summary.json').write_text('{"status":', encoding='utf-8')
            def poll(self): return self.returncode
            def wait(self, timeout=None): return self.returncode
        with patch.object(transport.subprocess, 'Popen', CompletedWriter):
            result = transport.run_transport(**args)
        self.assertEqual(result['status'], 'worker_summary_missing')
        self.assertTrue(result['system_integrity_incident'])
        self.assertIn('worker_summary_read_error', result['supervisor'])

    def test_cancelled_partial_response_kept_without_completed_response_claim(self):
        args = self.kwargs(name='interrupted_response')
        def interrupted_supervisor(spec_path, deadline, cancel_path):
            call = Path(spec_path).parent / 'http_0001_generation'
            call.mkdir()
            (call / 'request.json').write_text('{}', encoding='utf-8')
            (call / 'response.json').write_text('{"message":', encoding='utf-8')
            Path(cancel_path).write_text('deterministic fake cancellation', encoding='utf-8')
            return {'status': 'cancelled', 'failure_phase_last_observed': 'generation'}
        with patch.object(transport, 'supervise', side_effect=interrupted_supervisor):
            result = transport.run_transport(**args)
        self.assertEqual(result['status'], 'cancelled')
        self.assertIsNone(result['response'])
        self.assertFalse(result['system_integrity_incident'])
        self.assertIsNotNone(result['artifact_preservation_error'])
        self.assertEqual(result['generation_requests_attempted'], 1)


if __name__ == '__main__':
    unittest.main()
