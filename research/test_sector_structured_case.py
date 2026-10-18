"""Fake local HTTP only: no model inference, gold access or semantic scoring."""
from contextlib import redirect_stdout
import copy
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

import local_sector_structured_case as single
import sector_response_schema as contract


class FakeServer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/api/version':
            return self.send_json({'version': single.ENGINE})
        if self.path == '/api/tags':
            return self.send_json({'models': [{'name': single.MODEL, 'digest': single.DIGEST}]})
        if self.path == '/api/ps':
            return self.send_json({'models': []})
        self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/show':
            self.server.show_count += 1
            template = self.server.template
            if self.server.bad_pin and self.server.show_count >= 3:
                template += 'changed'
            return self.send_json({'template': template})
        if self.path == '/api/generate':
            self.server.unloads.append(body)
            if self.server.bad_unload:
                return self.send_json({'error': 'fake unload failure'}, 503)
            return self.send_json({'done': True, 'model': single.MODEL, 'done_reason': 'unload'})
        if self.path != '/api/chat':
            return self.send_error(404)
        if body.get('_debug_render_only') is True:
            self.server.renders.append(body)
            if self.server.bad_render == 'overflow':
                return self.send_json({'error': 'input exceeds context length'}, 400)
            if self.server.bad_render == 'missing':
                return self.send_json({'model': single.MODEL})
            contents = [m['content'].strip(' \t\r\n') for m in body['messages']]
            if self.server.bad_render == 'drop':
                contents = contents[1:]
            rendered = {'model': single.MODEL,
                '_debug_info': {'rendered_template': '\n<role>\n'.join(contents), 'image_count': 0}}
            if self.server.bad_render == 'thinking':
                rendered['message'] = {'thinking': 'unexpected generation'}
            if self.server.bad_render == 'tool_calls':
                rendered['message'] = {'tool_calls': [{'function': {'name': 'unexpected'}}]}
            return self.send_json(rendered)
        self.server.generations.append(body)
        if self.server.cancel_path is not None:
            self.server.cancel_path.write_text('synthetic cancellation', encoding='utf-8')
        if self.server.generation_overflow:
            return self.send_json({'error': 'prompt exceeds context with shift disabled'}, 400)
        if self.server.stall:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.end_headers()
            self.wfile.write((json.dumps({'model': single.MODEL, 'message': {'content': '{'}, 'done': False}) + '\n').encode())
            self.wfile.flush()
            self.server.release.wait(8)
            return
        stage = json.loads(body['messages'][-1]['content'])['stage']
        value = dict(source_id=single.SOURCE, interpretations=[{'sector_code': code, 'rating': 'synthetic_rating',
            'evidence_ids': [], 'reason': 'Synthetic structure fixture, not a source judgment'}
            for code in self.server.market['sector_codes']],
            weights=[] if stage < 3 else [{'sector_code': code, 'weight': weight,
                'rationale': 'Synthetic interface fixture only', 'evidence_ids': []}
                for code, weight in self.server.market['baseline_weights'].items()],
            submitted_constraints=[], alternatives='Synthetic test', risk_discussion='Synthetic test', unresolved=[])
        if self.server.financial_error and stage in (3, 4):
            value['weights'][0]['sector_code'] = value['weights'][1]['sector_code']
            value['weights'][0]['weight'] = -0.25
        if self.server.echo:
            value = json.loads(body['messages'][-1]['content'])
        if self.server.missing_key:
            value.pop('risk_discussion', None)
        if self.server.extra_key:
            value['common_market'] = self.server.market
        if self.server.short_rows:
            value['interpretations'].pop()
        content = json.dumps(value, indent=2) + '\n'
        reason = 'stop'
        if self.server.invalid_json:
            content = '{'
        if self.server.length:
            content = '{'; reason = 'length'
        msg = {'role': 'assistant', 'content': content}
        if self.server.thinking:
            msg['thinking'] = 'unexpected synthetic thinking'
        return self.send_json({'model': self.server.response_model or single.MODEL,
            'done': True, 'done_reason': reason, 'message': msg,
            'prompt_eval_count': 100, 'eval_count': 50,
            'prompt_eval_duration': 1000000, 'eval_duration': 1000000,
            'load_duration': 1000, 'total_duration': 2001000})


class StructuredCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeServer)
        observation = single.remote.read(single.ROOT / 'data/local_sector_runtime/laptop_latency_4b_20261018/4b_threads2/model_observation.json')
        self.server.template = observation['show']['template']
        self.server.market = single.remote.read(single.workflow.MARKET)
        self.server.show_count = 0
        self.server.generations = []; self.server.renders = []; self.server.unloads = []
        self.server.bad_render = None; self.server.bad_pin = False; self.server.bad_unload = False
        self.server.response_model = None; self.server.stall = False
        self.server.generation_overflow = False
        self.server.cancel_path = None
        self.server.echo = False; self.server.missing_key = False; self.server.extra_key = False
        self.server.short_rows = False; self.server.financial_error = False
        self.server.invalid_json = False; self.server.thinking = False; self.server.length = False
        self.server.release = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.prepared = self.folder / 'prepared'
        with redirect_stdout(io.StringIO()):
            single.prepare(SimpleNamespace(output=self.prepared,
                conditions_evidence=single.ROOT / 'research/v44_conditions_reference_20261018.json',
                schema_evidence=single.ROOT / 'research/v45_revision_reference_20261018.json'))
        self.log = self.folder / 'fake_server.log'; self.log.write_bytes(b'fake service log\n')

    def tearDown(self):
        self.server.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.tmp.cleanup()

    def args(self):
        return SimpleNamespace(manifest=self.prepared / 'manifest.json', base_url=self.origin,
            server_log=self.log, output_root=self.folder, run_id='run')

    def run_fixture(self):
        with redirect_stdout(io.StringIO()):
            code = single.run(self.args())
        return code, single.remote.read(self.folder / 'run/summary.json')

    def test_four_stages_exact_history_render_and_counts_without_evaluator(self):
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if 'evaluator_only' in str(path) or path.name == 'model_packets.jsonl':
                raise AssertionError('Forbidden evaluator or all-split packet read')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            code, summary = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(summary['status'], 'completed_four_stages')
        self.assertEqual(summary['pilot_model_calls'], 4)
        self.assertEqual(summary['main_model_calls'], 0)
        self.assertEqual(summary['render_requests_attempted'], 4)
        self.assertEqual(summary['http_streams_completed'], 4)
        self.assertEqual(summary['completed_workflow_stages'], 4)
        self.assertEqual(summary['generation_stages_not_started'], [])
        self.assertFalse(summary['human_semantic_pass'])
        self.assertEqual(len(self.server.generations), 4)
        self.assertEqual(len(self.server.renders), 4)
        self.assertEqual(summary['structure_validated_stages'], [1, 2, 3, 4])
        self.assertTrue(summary['final_allocation_valid'])
        self.assertFalse(summary['semantic_validity_assessed'])
        for index, body in enumerate(self.server.generations):
            self.assertEqual(body['options'], single.OPTIONS)
            self.assertEqual(body['format'], contract.response_schema(index + 1))
            logical = single.remote.read(self.folder / f'run/stage{index+1}_transport/logical_messages.json')
            grounded = single.remote.read(self.folder / f'run/stage{index+1}_transport/grounded_messages.json')
            self.assertEqual(grounded, single.ground_messages(logical))
            task = json.loads(grounded[-1]['content'])
            self.assertEqual(task['response_schema'], body['format'])
            self.assertEqual(task['response_contract_instruction'], contract.CONTRACT_INSTRUCTION)
            self.assertIs(body['truncate'], False); self.assertIs(body['shift'], False)
            rendered_body = copy.deepcopy(self.server.renders[index])
            rendered_body.pop('_debug_render_only'); rendered_body['stream'] = True
            self.assertEqual(body, rendered_body)
            if index:
                previous = self.server.generations[index - 1]['messages']
                self.assertEqual(body['messages'][:len(previous)], previous)
                old_response = single.remote.read(self.folder / f'run/{single.CASE}/stage{index}_response.json')
                self.assertEqual(body['messages'][len(previous)]['content'], old_response['message']['content'])
                feedback = json.loads(body['messages'][len(previous) + 1]['content'])
                record = single.remote.read(self.folder / f'run/{single.CASE}/stage{index}_record.json')
                self.assertEqual(feedback, {'calculator_feedback': record['calculator_result']})

    def test_missing_or_dropped_render_prevents_all_generation(self):
        for mode in ('missing', 'drop', 'overflow', 'thinking', 'tool_calls'):
            with self.subTest(mode=mode):
                self.server.bad_render = mode
                args = self.args(); args.run_id = mode
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(single.run(args), 1)
                result = single.remote.read(self.folder / mode / 'summary.json')
                self.assertEqual(result['render_requests_attempted'], 1)
                self.assertEqual(result['pilot_model_calls'], 0)
                self.assertEqual(result['generation_stages_not_started'], [1, 2, 3, 4])
                if mode in ('thinking', 'tool_calls'):
                    self.assertEqual(result['unexpected_generation_evidence_in_render'], 1)
        self.assertEqual(self.server.generations, [])

    def test_template_change_after_render_prevents_generation(self):
        self.server.bad_pin = True
        _, summary = self.run_fixture()
        self.assertEqual(summary['render_requests_attempted'], 1)
        self.assertEqual(summary['pilot_model_calls'], 0)
        self.assertEqual(self.server.generations, [])

    def test_invalid_json_stops_no_retry_with_raw_retained(self):
        self.server.invalid_json = True
        _, summary = self.run_fixture()
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['generation_stages_not_started'], [2, 3, 4])
        self.assertTrue((self.folder / 'run/stage1_transport/http_0001_generation/response.json').is_file())
        self.assertEqual(summary['completed_workflow_stages'], 0)

    def test_generation_context_overflow_stops_all_followups(self):
        self.server.generation_overflow = True
        _, summary = self.run_fixture()
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['http_streams_completed'], 0)
        self.assertEqual(summary['generation_stages_not_started'], [2, 3, 4])
        raw = self.folder / 'run/stage1_transport/http_0001_generation/raw_stream.bin'
        self.assertIn(b'context', raw.read_bytes())

    def test_length_retains_response_and_stops(self):
        self.server.length = True
        _, summary = self.run_fixture()
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['completed_workflow_stages'], 0)
        self.assertEqual(single.remote.read(self.folder / f'run/{single.CASE}/stage1_response.json')['done_reason'], 'length')

    def test_unload_failure_prevents_followup(self):
        self.server.bad_unload = True
        _, summary = self.run_fixture()
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['generation_stages_not_started'], [2, 3, 4])
        self.assertIn('unload', summary['error'])

    def test_cancellation_is_distinct_and_prevents_followups(self):
        self.server.cancel_path = self.folder / 'run/CANCEL'
        _, summary = self.run_fixture()
        self.assertEqual(summary['status'], 'cancelled')
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['generation_stages_not_started'], [2, 3, 4])

    def test_wrong_model_response_is_never_forwarded(self):
        self.server.response_model = 'wrong-model'
        _, summary = self.run_fixture()
        self.assertEqual(summary['pilot_model_calls'], 1)
        self.assertEqual(summary['completed_workflow_stages'], 0)
        self.assertTrue((self.folder / 'run/stage1_transport/http_0001_generation/response.json').is_file())

    def test_hard_deadline_preserves_partial_stream(self):
        self.server.stall = True
        _, runtime, packet, market = single.verify_manifest(self.prepared / 'manifest.json')
        body = single.prepare_body([{'role': 'system', 'content': single.workflow.SYSTEM},
            single.workflow.stage_message(1, 'R1', packet, market)], runtime)
        target = self.folder / 'deadline'; target.mkdir(); spec = target / 'worker_spec.json'
        single.remote.save(spec, dict(origin=self.origin, body=body, deadline_seconds=2,
            cancel_path=str(target / 'CANCEL')))
        start = time.monotonic(); result = single.supervise(spec, 2, target / 'CANCEL')
        self.assertLess(time.monotonic() - start, 3.5)
        self.assertEqual(result['status'], 'hard_deadline')
        self.assertEqual(len(self.server.generations), 1)
        self.assertTrue((target / 'http_0001_generation/raw_stream.bin').read_bytes())

    def test_changed_prepared_runtime_and_reuse_are_rejected(self):
        args = SimpleNamespace(output=self.prepared,
            conditions_evidence=single.ROOT / 'research/v44_conditions_reference_20261018.json',
            schema_evidence=single.ROOT / 'research/v45_revision_reference_20261018.json')
        with self.assertRaises(FileExistsError):
            single.prepare(args)
        runtime_path = self.prepared / 'runtime.json'
        value = single.remote.read(runtime_path); value['options']['num_predict'] = 32
        runtime_path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(ValueError):
            single.verify_manifest(self.prepared / 'manifest.json')
        self.assertEqual(self.server.generations, [])

    def test_reference_boundary_policy_preserves_json_strings_and_http(self):
        content = ' \t\r\n{"text": "  keep internal spaces  "}\n\t'
        messages = [{'role': 'system', 'content': single.workflow.SYSTEM},
                    {'role': 'assistant', 'content': content}]
        response = {'model': single.MODEL, '_debug_info': {'rendered_template':
            single.workflow.SYSTEM + '\n' + content.strip(' \t\r\n')}}
        result = single.validate_render(response, messages)
        last = result['message_spans'][-1]
        self.assertEqual(last['removed_outer_prefix'], ' \t\r\n')
        self.assertEqual(last['removed_outer_suffix'], '\n\t')
        self.assertTrue(last['strict_json_payload_value_preservation'])
        self.assertFalse(last['http_content_modified'])
        self.assertEqual(messages[-1]['content'], content)
        changed = copy.deepcopy(response)
        changed['_debug_info']['rendered_template'] = single.workflow.SYSTEM + '\n{"text": "keep internal spaces"}'
        with self.assertRaises(ValueError):
            single.validate_render(changed, messages)
        messages[-1]['content'] = '\x1c{"text": "x"}'
        with self.assertRaises(ValueError):
            single.validate_render(response, messages)


    def test_echo_missing_extra_or_short_rows_stop_without_repair(self):
        for mode in ('echo', 'missing_key', 'extra_key', 'short_rows'):
            with self.subTest(mode=mode):
                setattr(self.server, mode, True)
                args = self.args(); args.run_id = mode
                with redirect_stdout(io.StringIO()): self.assertEqual(single.run(args), 1)
                result = single.remote.read(self.folder / mode / 'summary.json')
                self.assertEqual(result['pilot_model_calls'], 1)
                self.assertEqual(result['http_streams_completed'], 1)
                self.assertEqual(result['completed_workflow_stages'], 0)
                self.assertEqual(result['generation_stages_not_started'], [2, 3, 4])
                validation = single.remote.read(self.folder / mode / 'stage1_transport/response_contract_validation.json')
                self.assertFalse(validation['valid'])
                self.assertFalse(validation['response_repaired'])
                setattr(self.server, mode, False)

    def test_invalid_financial_values_are_retained_and_forwarded(self):
        self.server.financial_error = True
        code, summary = self.run_fixture()
        self.assertEqual(code, 0)
        self.assertEqual(summary['completed_workflow_stages'], 4)
        self.assertFalse(summary['final_allocation_valid'])
        self.assertFalse(summary['semantic_validity_assessed'])
        prior = single.remote.read(self.folder / f'run/{single.CASE}/stage3_record.json')
        self.assertFalse(prior['calculator_result']['allocation']['valid'])
        self.assertEqual(prior['raw_proposal']['weights'][0]['weight'], -0.25)
        stage4 = self.server.generations[3]['messages']
        feedback = json.loads(stage4[-2]['content'])['calculator_feedback']
        self.assertEqual(feedback, prior['calculator_result'])
        validation = single.remote.read(self.folder / 'run/stage3_transport/response_contract_validation.json')
        self.assertTrue(validation['valid'])
        self.assertFalse(validation['row_coverage_diagnostics']['weights']['all_public_codes_once'])

    def test_stage_shapes_and_no_answer_values_in_schema(self):
        for stage in range(1, 5):
            schema = contract.response_schema(stage)
            self.assertEqual(set(schema['required']), set(contract.REQUIRED_KEYS))
            self.assertIs(schema['additionalProperties'], False)
            self.assertEqual(schema['properties']['source_id'], {'type': ['string', 'null']})
            def inspect(node):
                if isinstance(node, dict):
                    self.assertNotIn('const', node); self.assertNotIn('default', node)
                    self.assertNotIn('prefixItems', node); self.assertNotIn('uniqueItems', node)
                    for key, value in node.items():
                        if key == 'enum':
                            self.assertIn(value, [list(single.workflow.read(single.workflow.MARKET)['sector_codes']),
                                                 ['sector_min_weight', 'sector_max_weight']])
                        inspect(value)
                elif isinstance(node, list):
                    for item in node: inspect(item)
            inspect(schema)
        schema = contract.response_schema(1)
        value = {'source_id': single.SOURCE,
            'interpretations': [{'sector_code': code, 'rating': 'arbitrary', 'evidence_ids': [], 'reason': 'fixture'}
                                for code in self.server.market['sector_codes']],
            'weights': [], 'alternatives': 'fixture', 'risk_discussion': 'fixture',
            'unresolved': [], 'submitted_constraints': []}
        self.assertTrue(contract.validate_response(json.dumps(value), 1, single.SOURCE)['valid'])
        self.assertFalse(contract.validate_response(json.dumps(value), 3, single.SOURCE)['valid'])
        value['source_id'] = 'wrong-public-identity'
        checked = contract.validate_response(json.dumps(value), 1, single.SOURCE)
        self.assertTrue(checked['valid'])
        self.assertFalse(checked['source_identity_matches_visible_metadata'])
        value['risk_discussion'] = 0
        self.assertFalse(contract.validate_response(json.dumps(value), 1, single.SOURCE)['valid'])
        self.assertFalse(contract.validate_response('{"source_id": null, "source_id": null}', 1, single.SOURCE)['valid'])

    def test_grounding_preserves_original_values_and_literal_history(self):
        _, runtime, packet, market = single.verify_manifest(self.prepared / 'manifest.json')
        original = [{'role':'system', 'content':single.workflow.SYSTEM},
                    single.workflow.stage_message(1, 'R1', packet, market)]
        for stage in range(1, 5):
            if stage > 1:
                original += [{'role':'assistant','content':' \n{"keep": "  internal spaces  "}\n'},
                             {'role':'user','content':'{"calculator_feedback": {"unrepaired": true}}'},
                             single.workflow.stage_message(stage, 'R1', packet, market)]
            saved = copy.deepcopy(original)
            grounded = single.ground_messages(original)
            body = single.prepare_body(original, runtime)
            for raw, revised in zip(original, grounded):
                if raw['role'] == 'user' and 'stage' in json.loads(raw['content']):
                    restored = json.loads(revised['content'])
                    restored.pop('response_schema'); restored.pop('response_contract_instruction')
                    self.assertEqual(restored, json.loads(raw['content']))
                else:
                    self.assertEqual(raw, revised)
            projected = json.loads(body['messages'][1]['content'])
            projected['common_market'] = single.base.restore_market(projected['common_market'])
            self.assertEqual(projected, json.loads(grounded[1]['content']))
            self.assertEqual(body['messages'][2:], grounded[2:])
            self.assertEqual(original, saved)


if __name__ == '__main__':
    unittest.main()
