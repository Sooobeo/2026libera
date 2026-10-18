"""Local fake HTTP only; no model inference or research-output scoring."""
from contextlib import redirect_stdout
import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

import benchmark_sector_real_input as real
from test_benchmark_sector_latency import FakeOllama


class RealInputFake(FakeOllama):
    def do_POST(self):
        if self.path != '/api/chat':
            return super().do_POST()
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.chats.append(body)
        if self.server.stall:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            self.wfile.write((json.dumps({'model': body['model'], 'done': False,
                'message': {'content': '{'}}) + '\n').encode())
            self.wfile.flush()
            self.server.release.wait(8)
            return
        return self.send_json({'model': self.server.response_model or body['model'],
            'done': True, 'done_reason': 'length', 'message': {'role': 'assistant', 'content': '{'},
            'prompt_eval_count': 1234, 'eval_count': 32, 'load_duration': 1,
            'prompt_eval_duration': 100000000, 'eval_duration': 100000000,
            'total_duration': 200000001})


class RealInputTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), RealInputFake)
        self.server.chats = []; self.server.unloads = []; self.server.stall = False
        self.server.unload_failure = False; self.server.response_model = None
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.release.set(); self.server.shutdown(); self.server.server_close(); self.thread.join()

    def args(self, folder, deadline=5):
        return SimpleNamespace(base_url=self.origin, output_root=Path(folder), run_id='fixture',
            deadline_seconds=deadline, model='qwen3:1.7b', threads=2,
            packets=real.workflow.PACKETS, market=real.workflow.MARKET)

    def test_real_packet_round_trip_and_explicit_per_model_context(self):
        market = real.workflow.read(real.workflow.MARKET)
        packet = next(p for p in real.workflow.packets() if p['source_id'] == real.SOURCE)
        before = real.canonical({'packet': packet, 'market': market})
        for model, context in real.CONTEXTS.items():
            original, compact, checks = real.prepare_requests(model, 2, packet, market)
            self.assertEqual(compact['options']['num_ctx'], context)
            self.assertEqual(compact['options']['num_predict'], 32)
            self.assertEqual(compact['messages'][0]['content'], real.workflow.SYSTEM)
            self.assertTrue(checks['exact_original_field_value_roundtrip'])
            self.assertEqual(checks['sizes']['compact']['conservative_screening_bound'], 17275)
            self.assertEqual(checks['sizes']['original']['conservative_screening_bound'], 21035)
        self.assertEqual(real.canonical({'packet': packet, 'market': market}), before)

    def test_one_compact_request_cap_is_not_quality_failure(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            self.assertEqual(real.run(self.args(folder)), 0)
            target = Path(folder) / 'fixture'
            summary = real.remote.read(target / 'summary.json')
            self.assertEqual(summary['status'], 'output_limit_reached')
            self.assertTrue(summary['deadline_scope'].startswith('5-second maximum'))
            self.assertEqual(summary['supervisor']['deadline_seconds'], 5)
            self.assertEqual(len(self.server.chats), 1)
            self.assertEqual(summary['generation_request_envelopes_recorded'], 1)
            self.assertEqual((summary['pilot_model_calls'], summary['main_model_calls']), (0, 0))
            self.assertFalse(summary['response_quality_scored'])
            self.assertEqual(summary['provider_metrics']['prompt_eval_count'], 1234)
            self.assertIsNone(summary['supervisor']['worker']['expected_synthetic_json'])
            self.assertEqual(summary['supervisor']['worker']['assessment_scope'], 'not_graded_engineering_feasibility')
            sent = real.remote.read(target / 'compact_request_to_send.json')
            original = real.remote.read(target / 'original_request_not_sent.json')
            self.assertEqual(self.server.chats[0], sent)
            self.assertNotEqual(original['messages'], sent['messages'])
            self.assertTrue(all(item['model'] == 'qwen3:1.7b' for item in self.server.unloads))

    def test_failed_idle_confirmation_prevents_generation(self):
        self.server.unload_failure = True
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            self.assertEqual(real.run(self.args(folder)), 1)
            summary = real.remote.read(Path(folder) / 'fixture' / 'summary.json')
            self.assertEqual(summary['probe_invocations_attempted'], 0)
            self.assertEqual(self.server.chats, [])

    def test_timeout_keeps_partial_raw_and_never_retries(self):
        self.server.stall = True
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            started = time.monotonic()
            self.assertEqual(real.run(self.args(folder, deadline=2)), 1)
            self.assertLess(time.monotonic() - started, 4)
            target = Path(folder) / 'fixture'
            summary = real.remote.read(target / 'summary.json')
            self.assertEqual(summary['supervisor']['supervisor_status'], 'hard_deadline')
            self.assertTrue(summary['deadline_scope'].startswith('2-second maximum'))
            self.assertEqual(summary['supervisor']['deadline_seconds'], 2)
            self.assertEqual(len(self.server.chats), 1)
            self.assertTrue((target / 'compact_probe/http_0001_latency_probe/raw_stream.bin').read_bytes())

    def test_length_does_not_hide_wrong_model(self):
        self.server.response_model = 'unexpected_model'
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            self.assertEqual(real.run(self.args(folder)), 1)
            summary = real.remote.read(Path(folder) / 'fixture' / 'summary.json')
            self.assertEqual(summary['status'], 'response_protocol_anomaly')


if __name__ == '__main__':
    unittest.main()
