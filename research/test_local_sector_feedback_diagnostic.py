"""Offline and fake loopback HTTP tests only; no real model service is used."""
from contextlib import redirect_stdout
import copy
import io
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import local_sector_feedback_diagnostic as diagnostic
from test_sector_structured_case import FakeServer


class FeedbackDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeServer)
        observed = diagnostic.remote.read(diagnostic.ROOT / 'data/local_sector_runtime/laptop_latency_4b_20261018/4b_threads2/model_observation.json')
        self.server.template = observed['show']['template']
        self.server.market = diagnostic.remote.read(diagnostic.workflow.MARKET)
        self.server.show_count = 0
        self.server.generations = []; self.server.renders = []; self.server.unloads = []
        self.server.bad_render = None; self.server.bad_pin = False; self.server.bad_unload = False
        self.server.response_model = None; self.server.stall = False; self.server.generation_overflow = False
        self.server.cancel_path = None
        self.server.echo = False; self.server.missing_key = False; self.server.extra_key = False
        self.server.short_rows = False; self.server.financial_error = False
        self.server.invalid_json = False; self.server.thinking = False; self.server.length = False
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.prepared = self.folder / 'prepared'
        with redirect_stdout(io.StringIO()):
            diagnostic.prepare(SimpleNamespace(output=self.prepared,
                revision_evidence=diagnostic.ROOT / 'research/v46_single_revision_basis_addendum_20261018.json'))
        self.registration = self.folder / 'registration.json'
        self.record_registration()
        self.log = self.folder / 'owned_fake_server.log'; self.log.write_bytes(b'fake service only\n')

    def record_registration(self):
        self.registration.write_text(json.dumps(dict(protocol_version=diagnostic.PROTOCOL,
            diagnostic_id=diagnostic.DIAGNOSTIC_ID, registered_at_utc=diagnostic.remote.now(),
            manifest=diagnostic.sha_record(self.prepared / 'manifest.json'),
            planned_generation_attempts=1, automatic_retries=0, main_model_calls=0, main_freeze=False)), encoding='utf-8')

    def tearDown(self):
        self.server.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.tmp.cleanup()

    def args(self, run_id='run'):
        return SimpleNamespace(manifest=self.prepared / 'manifest.json', registration=self.registration,
            base_url=self.origin, server_log=self.log, output_root=self.folder, run_id=run_id)

    def run_fixture(self, run_id='run'):
        with redirect_stdout(io.StringIO()): result = diagnostic.run(self.args(run_id))
        return result, diagnostic.remote.read(self.folder / run_id / 'summary.json')

    def test_preserves_five_messages_feedback_and_request_controls(self):
        _, runtime, packet, market, messages = diagnostic.verify_manifest(self.prepared / 'manifest.json')
        original = diagnostic.remote.read(diagnostic.V45_RUN / 'fidelity_q2_2026__R1/stage1_request.json')
        old = diagnostic.remote.read(self.prepared / 'prior_response.json')
        feedback = diagnostic.remote.read(self.prepared / 'prior_calculator_result.json')
        self.assertEqual(len(messages), 5); self.assertEqual(messages[:2], original)
        self.assertEqual(messages[2], {'role': 'assistant', 'content': old['message']['content']})
        self.assertEqual(json.loads(messages[3]['content']), {'calculator_feedback': feedback})
        task = json.loads(messages[4]['content'])
        self.assertEqual(task['calculator_feedback'], feedback)
        self.assertIn('not included', task['task']); self.assertEqual(task['stage'], 4)
        body = diagnostic.request_body(messages)
        self.assertEqual(body['messages'][2:], messages[2:])
        restored = json.loads(body['messages'][1]['content'])
        restored['common_market'] = diagnostic.base.restore_market(restored['common_market'])
        self.assertEqual(restored, json.loads(original[1]['content']))
        self.assertEqual(body['options'], diagnostic.base.OPTIONS)
        self.assertEqual(body['format'], diagnostic.transport.response_schema(4))
        self.assertEqual(task['response_schema'], body['format'])
        self.assertEqual(set(body['format']['required']), set(diagnostic.transport.response_schema(4)['required']))

    def test_single_call_valid_raw_result_counts_and_hash_chain(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if 'evaluator_only' in str(path) or path.name == 'model_packets.jsonl':
                raise AssertionError('Forbidden evaluator or main-packet access')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            code, summary = self.run_fixture()
        self.assertEqual(code, 0); self.assertEqual(summary['status'], 'completed_one_diagnostic')
        self.assertEqual(summary['diagnostic_generation_calls'], 1)
        self.assertEqual(summary['render_requests_attempted'], 1)
        self.assertEqual(summary['http_streams_completed'], 1)
        self.assertEqual(summary['main_model_calls'], 0); self.assertEqual(summary['four_stage_pilot_calls'], 0)
        self.assertEqual(summary['automatic_retries'], 0)
        self.assertTrue(summary['numeric_acceptance']); self.assertTrue(summary['weight_vector_changed'])
        self.assertFalse(summary['priority1_solved']); self.assertFalse(summary['human_semantic_pass'])
        self.assertEqual(summary['independent_reviews_completed'], 0)
        self.assertEqual(len(self.server.generations), 1); self.assertEqual(len(self.server.renders), 1)
        self.assertEqual(self.server.generations[0], diagnostic.remote.read(self.prepared / 'authoritative_body.json'))
        render = copy.deepcopy(self.server.renders[0]); render.pop('_debug_render_only'); render['stream'] = True
        self.assertEqual(render, self.server.generations[0])
        record = diagnostic.remote.read(self.folder / 'run/revision_record.json')
        raw = diagnostic.remote.read(self.folder / 'run/revision_transport/http_0001_generation/response.json')
        self.assertEqual(record['raw_proposal'], json.loads(raw['message']['content']))
        self.assertFalse(record['repair_applied'])
        chain = [json.loads(s) for s in (self.folder / 'run/events.jsonl').read_text().splitlines()]
        previous = None
        for number, row in enumerate(chain, 1):
            digest = row.pop('event_sha256')
            self.assertEqual(row['sequence'], number); self.assertEqual(row['previous_event_sha256'], previous)
            self.assertEqual(digest, diagnostic.base.value_sha(row)); previous = digest
        self.assertEqual(diagnostic.remote.sha(diagnostic.V45_MANIFEST), diagnostic.V45_MANIFEST_SHA)
        for name, sha in diagnostic.SOURCE_PINS.items(): self.assertEqual(diagnostic.remote.sha(diagnostic.V45_RUN/name), sha)

    def test_invalid_financial_result_is_not_repaired_or_retried(self):
        self.server.financial_error = True
        code, summary = self.run_fixture()
        self.assertEqual(code, 0); self.assertEqual(summary['status'], 'completed_one_diagnostic')
        self.assertFalse(summary['numeric_acceptance']); self.assertFalse(summary['priority1_solved'])
        self.assertEqual(len(self.server.generations), 1)
        record = diagnostic.remote.read(self.folder / 'run/revision_record.json')
        self.assertEqual(record['raw_proposal']['weights'][0]['weight'], -0.25)
        self.assertTrue(record['calculator_result']['allocation']['duplicate_codes'])

    def test_constraints_need_actual_satisfaction_not_top_level_ok(self):
        previous = diagnostic.remote.read(self.prepared/'prior_record.json')['raw_proposal']
        proposal = copy.deepcopy(previous)
        calc = {'ok': True, 'allocation': {'valid': True, 'raw_sum': 1, 'raw_budget_residual': 0},
                'submitted_constraint_checks': {'valid_request': True, 'checks': [{'evaluable': True, 'violation': .1}]},
                'market_diagnostics': {'status': 'ok'}}
        self.assertFalse(diagnostic.numeric_assessment(calc, previous, proposal)['numeric_acceptance'])
        calc['submitted_constraint_checks']['checks'][0] = {'evaluable': False, 'violation': None}
        self.assertFalse(diagnostic.numeric_assessment(calc, previous, proposal)['numeric_acceptance'])

    def test_render_failure_prevents_generation(self):
        self.server.bad_render = 'missing'
        code, summary = self.run_fixture()
        self.assertEqual(code, 1); self.assertEqual(summary['generation_requests_attempted'], 0)
        self.assertIsNone(summary['numeric_acceptance']); self.assertEqual(len(self.server.generations), 0)
        self.assertEqual(len(self.server.unloads), 1)

    def test_pin_change_prevents_generation(self):
        self.server.bad_pin = True
        code, summary = self.run_fixture()
        self.assertEqual(code, 1); self.assertEqual(len(self.server.generations), 0)
        self.assertEqual(summary['generation_requests_attempted'], 0)

    def test_schema_failure_retains_one_raw_attempt(self):
        self.server.echo = True
        code, summary = self.run_fixture()
        self.assertEqual(code, 1); self.assertEqual(summary['generation_requests_attempted'], 1)
        self.assertEqual(summary['http_streams_completed'], 1); self.assertFalse(summary['complete_revision_record'])
        self.assertTrue((self.folder/'run/revision_transport/http_0001_generation/response.json').is_file())
        self.assertEqual(len(self.server.generations), 1)

    def test_output_cap_is_not_a_complete_revision(self):
        self.server.length = True
        code, summary = self.run_fixture()
        self.assertEqual(code, 1); self.assertEqual(summary['status'], 'output_limit_reached')
        self.assertEqual(summary['generation_requests_attempted'], 1); self.assertFalse(summary['complete_revision_record'])

    def test_deadline_kills_only_child_and_preserves_partial_bytes(self):
        self.server.stall = True
        supervise = diagnostic.transport.supervise
        def short(spec, deadline, cancel): return supervise(spec, 2.5, cancel)
        started = time.monotonic()
        with patch.object(diagnostic.transport, 'supervise', short): code, summary = self.run_fixture()
        self.assertEqual(code, 1); self.assertEqual(summary['status'], 'hard_deadline')
        self.assertLess(time.monotonic()-started, 8)
        self.assertEqual(summary['generation_requests_attempted'], 1); self.assertEqual(summary['http_streams_completed'], 0)
        self.assertEqual(len(self.server.generations), 1)
        clean = diagnostic.remote.read(self.folder/'run/revision_transport/unload_and_residency.json')
        self.assertEqual(clean['status'], 'no_resident_models_observed')

    def test_registration_and_input_tamper_prevent_network(self):
        registration = diagnostic.remote.read(self.registration)
        registration['planned_generation_attempts'] = 2
        self.registration.write_text(json.dumps(registration), encoding='utf-8')
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertFalse((self.folder/'run').exists())
        self.record_registration()
        body_path = self.prepared/'authoritative_body.json'
        body = diagnostic.remote.read(body_path); body['options']['temperature'] = 1
        body_path.write_text(json.dumps(body), encoding='utf-8')
        with self.assertRaises(ValueError): self.run_fixture()
        self.assertFalse((self.folder/'run').exists()); self.assertEqual(self.server.show_count, 0)

    def test_existing_run_directory_is_not_reused(self):
        (self.folder/'run').mkdir()
        with self.assertRaises(FileExistsError): self.run_fixture()
        self.assertEqual(self.server.show_count, 0)


if __name__ == '__main__':
    unittest.main()
