"""Synthetic local HTTP/fixture tests. No Ollama, model, pull or real inference."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import remote_sector_runtime as remote


@contextmanager
def fake_server():
    state = {'requests': [], 'digest': remote.EXPECTED_DIGEST, 'template': '{{ .Prompt }}',
             'chat': [], 'version': remote.EXPECTED_ENGINE, 'pause': 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def handle_request(self):
            size = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(size)) if size else None
            state['requests'].append((self.path, body))
            if self.path == '/api/version':
                value = {'version': state['version']}
            elif self.path == '/api/tags':
                value = {'models': [{'name': remote.MODEL, 'digest': state['digest'], 'details': {'quantization_level': 'Q4_K_M'}}]}
            elif self.path == '/api/show':
                value = {'template': state['template'], 'details': {'quantization_level': 'Q4_K_M'}, 'capabilities': ['completion', 'thinking']}
            elif self.path == '/api/ps':
                value = {'models': []}
            elif self.path == '/api/generate':
                value = {'done': True, 'done_reason': 'unload'}
            elif self.path == '/api/pull':
                value = [{'status': 'pulling manifest'}, {'status': 'success'}]
            elif self.path == '/api/chat':
                if state['chat']:
                    value = state['chat'].pop(0)
                else:
                    proposal = {'interpretations': [], 'weights': [{'sector_code': c, 'weight': 1 / 11,
                                 'rationale': 'Synthetic fixture only', 'evidence_ids': []}
                                 for c in ('10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60')],
                                'submitted_constraints': []}
                    value = events(json.dumps(proposal))
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson' if isinstance(value, list) else 'application/json')
            self.end_headers()
            try:
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        self.wfile.write(item if isinstance(item, bytes) else (json.dumps(item) + '\n').encode())
                        self.wfile.flush()
                        if index == 0 and state['pause']:
                            time.sleep(state['pause'])
                else:
                    self.wfile.write(json.dumps(value).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_address[1]), state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def events(content, reason='stop'):
    return [{'message': {'role': 'assistant', 'content': content}, 'done': False},
            {'message': {'role': 'assistant', 'content': ''}, 'done': True, 'done_reason': reason,
             'prompt_eval_count': 10, 'prompt_eval_duration': 2_000_000_000,
             'eval_count': 20, 'eval_duration': 4_000_000_000, 'load_duration': 1_000_000_000}]


class RemoteTests(unittest.TestCase):
    def test_exclusive_output_and_origin(self):
        self.assertEqual(remote.parser().parse_args(['inventory']).base_url, remote.DEFAULT_URL)
        for bad in ('file:///tmp', 'http://a:b@localhost', 'http://localhost/path', 'http://localhost?x=1'):
            with self.assertRaises(ValueError):
                remote.validate_origin(bad)
        with tempfile.TemporaryDirectory() as folder:
            remote.new_output(folder, 'inventory', 'one')
            with self.assertRaises(FileExistsError):
                remote.new_output(folder, 'inventory', 'one')
            with self.assertRaises(ValueError):
                remote.new_output(folder, 'inventory', '../escape')

    def test_linux_memory_only_allowlisted_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            proc, group = root / 'proc', root / 'cgroup'
            proc.mkdir(); group.mkdir()
            (proc / 'meminfo').write_text('MemTotal: 12582912 kB\nMemAvailable: 10000000 kB\nSwapFree: 100 kB\n')
            (group / 'memory.max').write_text('12884901888')
            for pid, name in [('10', 'ollama'), ('11', 'private-unrelated')]:
                item = proc / pid; item.mkdir()
                (item / 'comm').write_text(name)
                (item / 'status').write_text('VmRSS: 100 kB\nVmHWM: 120 kB\n')
            value = remote.memory_snapshot(proc, group)
            self.assertEqual(value['proc_meminfo']['MemTotal_bytes'], 12 * 1024 ** 3)
            self.assertEqual(value['rss_sum_bytes'], 102400)
            self.assertEqual([p['pid'] for p in value['processes']], [10])
            self.assertNotIn('private-unrelated', json.dumps(value))

    def test_pin_and_changed_digest_or_template(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            self.assertEqual(runtime['context_tokens'], 65536)
            self.assertIs(runtime['thinking'], False)
            self.assertEqual(runtime['timeout_seconds'], 1800)
            remote.verify_runtime(session, runtime)
            state['template'] = 'changed'
            with self.assertRaises(RuntimeError):
                remote.verify_runtime(session, runtime)
            state['digest'] = '0' * 64
            with self.assertRaises(RuntimeError):
                remote.observed_model(url)
            self.assertFalse(any(path == '/api/chat' for path, _ in state['requests']))

    def test_stream_timings_raw_and_health_counts(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            state['chat'] = [events('{"ready":true}')]
            result = remote.diagnose(session, runtime)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['pilot_model_calls'], 0)
            self.assertEqual(session.calls[0]['metrics']['eval_tokens_per_second'], 5)
            self.assertEqual(session.calls[0]['metrics']['prompt_eval_tokens_per_second'], 5)
            self.assertIsNotNone(session.calls[0]['metrics']['ttft_content_seconds'])
            raw = Path(folder) / session.calls[0]['folder'] / 'raw_stream.bin'
            self.assertIn(b'prompt_eval_count', raw.read_bytes())
            request = next(b for p, b in state['requests'] if p == '/api/chat')
            self.assertEqual(request['options']['num_predict'], 256)
            self.assertIs(request['think'], False)

    def test_missing_terminal_and_malformed_stream_preserve_raw_no_retry(self):
        for event_list in ([{'message': {'content': 'partial'}, 'done': False}], [b'{incomplete']):
            with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
                state['chat'] = [event_list]
                session = remote.Session(folder, url)
                with self.assertRaises(remote.RemoteCallError):
                    remote.stream_call(session, '/api/chat', {'model': remote.MODEL}, 'diagnose')
                self.assertEqual(len([p for p, _ in state['requests'] if p == '/api/chat']), 1)
                self.assertGreater((Path(folder) / session.calls[0]['raw_bytes_path']).stat().st_size, 0)
                self.assertTrue((Path(folder) / session.calls[0]['folder'] / 'result.json').exists())

    def test_absolute_deadline_retains_partial_output(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            state['chat'] = [events('partial')]
            state['pause'] = 1
            session = remote.Session(folder, url, timeout_seconds=0.25)
            start = time.monotonic()
            with self.assertRaises(remote.RemoteCallError):
                remote.stream_call(session, '/api/chat', {'model': remote.MODEL}, 'diagnose')
            self.assertLess(time.monotonic() - start, 0.9)
            self.assertEqual(session.calls[0]['status'], 'timeout')
            self.assertIn(b'partial', (Path(folder) / session.calls[0]['raw_bytes_path']).read_bytes())
            self.assertEqual(len(session.calls), 1)

    def test_cancel_file_stops_stream_and_future_calls(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            state['chat'] = [events('partial')]
            state['pause'] = 1
            session = remote.Session(folder, url)
            timer = threading.Timer(0.15, lambda: (Path(folder) / 'CANCEL').touch())
            timer.start()
            try:
                with self.assertRaises(remote.RemoteCallError):
                    remote.stream_call(session, '/api/chat', {'model': remote.MODEL}, 'diagnose')
                self.assertEqual(session.calls[0]['status'], 'cancelled')
                with self.assertRaises(remote.Cancelled):
                    remote.stream_call(session, '/api/chat', {'model': remote.MODEL}, 'diagnose')
                self.assertEqual(len(session.calls), 1)
            finally:
                timer.cancel()

    def test_complete_pilot_uses_real_runner_without_gold_and_preserves_onset(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if 'evaluator_only' in str(path):
                raise AssertionError('Gold read forbidden')
            return original(path, *args, **kwargs)
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder, patch.object(Path, 'read_text', guarded):
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            result = remote.pilot(session, runtime,
                                  remote.ROOT / 'data/sector_documents/model_packets.jsonl',
                                  remote.ROOT / 'data/sector_market/market_input.json')
            self.assertEqual(result['completed_runs'], 4)
            self.assertEqual(result['pilot_model_calls'], 16)
            self.assertEqual(result['main_model_calls'], 0)
            chats = [body for path, body in state['requests'] if path == '/api/chat']
            self.assertEqual(len(chats), 16)
            for body in chats[4:7]:
                self.assertNotIn('fidelity_q2_2026', json.dumps(body['messages']))
            self.assertIn('fidelity_q2_2026', json.dumps(chats[7]['messages']))
            self.assertTrue(all(body['options']['num_predict'] == 8192 for body in chats))
            self.assertTrue(all(body['think'] is False for body in chats))

    def test_length_failure_retained_without_retry_for_each_case(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            state['chat'] = [events('{"weights":[]}', 'length') for _ in range(4)]
            result = remote.pilot(session, runtime,
                                  remote.ROOT / 'data/sector_documents/model_packets.jsonl',
                                  remote.ROOT / 'data/sector_market/market_input.json')
            self.assertEqual(result['attempted_runs'], 4)
            self.assertEqual(result['completed_runs'], 0)
            self.assertEqual(result['pilot_model_calls'], 4)
            for row in result['records']:
                response = remote.read(Path(folder) / 'pilot' / row['case_id'] / 'stage1_response.json')
                self.assertEqual(response['done_reason'], 'length')

    def test_context_guard_prevents_request_without_truncation(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            with patch('run_sector_workflow.conservative_context_bound', return_value=65536):
                result = remote.pilot(session, runtime,
                                      remote.ROOT / 'data/sector_documents/model_packets.jsonl',
                                      remote.ROOT / 'data/sector_market/market_input.json')
            self.assertEqual(result['attempted_runs'], 4)
            self.assertEqual(result['pilot_model_calls'], 0)
            self.assertFalse(any(p == '/api/chat' for p, _ in state['requests']))

    def test_pull_cli_verifies_digest_and_creates_pin_without_generation(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            code = remote.main(['pull', '--base-url', url, '--output-root', folder, '--run-id', 'pull_fixture'])
            self.assertEqual(code, 0)
            target = Path(folder) / 'pull_fixture'
            self.assertTrue((target / 'runtime_pinned.json').exists())
            self.assertTrue((target / 'monitor.jsonl').exists())
            summary = remote.read(target / 'summary.json')
            self.assertEqual(summary['diagnostic_calls'], 0)
            self.assertEqual(summary['pilot_model_calls'], 0)
            self.assertFalse(any(path in ('/api/chat', '/api/generate') for path, _ in state['requests']))

    def test_diagnose_cli_pins_installed_model_and_unloads_without_server_kill(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            state['chat'] = [events('{"ready":true}')]
            code = remote.main(['diagnose', '--base-url', url, '--output-root', folder, '--run-id', 'health_fixture'])
            self.assertEqual(code, 0)
            summary = remote.read(Path(folder) / 'health_fixture' / 'summary.json')
            self.assertEqual(summary['diagnostic_calls'], 1)
            self.assertEqual(summary['pilot_model_calls'], 0)
            self.assertEqual(summary['main_model_calls'], 0)
            unloads = [body for path, body in state['requests'] if path == '/api/generate']
            self.assertEqual(unloads, [{'model': remote.MODEL, 'keep_alive': 0}])
            self.assertFalse(any(path == '/api/pull' for path, _ in state['requests']))

    def test_disabled_thinking_violation_stops_pilot_preserving_full_raw(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder:
            session = remote.Session(folder, url)
            runtime = remote.pin_runtime(session)
            response = events('{"interpretations":[],"weights":[]}')
            response[0]['message']['thinking'] = 'Unexpected provider reasoning'
            state['chat'] = [response]
            result = remote.pilot(session, runtime,
                                  remote.ROOT / 'data/sector_documents/model_packets.jsonl',
                                  remote.ROOT / 'data/sector_market/market_input.json')
            self.assertEqual(result['attempted_runs'], 1)
            self.assertEqual(result['completed_runs'], 0)
            self.assertEqual(result['pilot_model_calls'], 1)
            self.assertEqual(sum(r['status'] == 'not_started' for r in result['records']), 3)
            self.assertEqual(result['records'][0]['error_type'], 'ProtocolViolation')
            raw = remote.read(Path(folder) / session.calls[0]['folder'] / 'response.json')
            self.assertEqual(raw['message']['thinking'], 'Unexpected provider reasoning')

    def test_failed_diagnosis_returns_nonzero_and_never_starts_pilot(self):
        with fake_server() as (url, state), tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            state['chat'] = [events('{"ready":false}')]
            code = remote.main(['diagnose', '--base-url', url, '--output-root', folder, '--run-id', 'bad_health'])
            self.assertEqual(code, 1)
            summary = remote.read(Path(folder) / 'bad_health' / 'summary.json')
            self.assertEqual(summary['status'], 'diagnostic_response_failed')
            self.assertEqual(summary['pilot_model_calls'], 0)
            self.assertEqual(len([p for p, _ in state['requests'] if p == '/api/chat']), 1)

    def test_evaluator_path_rejected_before_file_read(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('Must not read evaluator file')):
            with self.assertRaises(ValueError):
                remote.load_pilot_inputs(Path('evaluator_only/reference_annotations.jsonl'), Path('market.json'))


if __name__ == '__main__':
    unittest.main()
