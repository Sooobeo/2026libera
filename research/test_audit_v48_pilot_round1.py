"""Pure artifact fixtures for the v4.8 pilot audit; no HTTP/model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import audit_v48_pilot_round1 as audit


class AuditArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def save(self, name, value):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    def test_only_partial_final_line_is_accepted(self):
        path = self.folder / 'events.jsonl'
        path.write_text('{"event":{"done":false}}\n{"event":', encoding='utf-8')
        values, partial = audit.complete_lines(path, event_wrapper=True)
        self.assertEqual(values, [{'done': False}]); self.assertTrue(partial)
        path.write_text('{broken}\n{"event":{"done":true}}\n', encoding='utf-8')
        with self.assertRaises(ValueError): audit.complete_lines(path, event_wrapper=True)
    def test_complete_raw_response_text_is_verbatim(self):
        raw = ' { "weights": [] }\n'
        self.save('response.json', {'message': {'content': raw}, 'done_reason': 'stop'})
        text, response = audit.captured_text(self.folder)
        self.assertEqual(text, raw); self.assertEqual(response['done_reason'], 'stop')
    def test_broken_response_falls_back_without_claiming_completion(self):
        (self.folder / 'response.json').write_text('{', encoding='utf-8')
        self.save('assembled_text.json', {'content': []})
        (self.folder / 'events.jsonl').write_text('{"event":{"message":{"content":"partial"}}}\n{"event":', encoding='utf-8')
        text, response = audit.captured_text(self.folder)
        self.assertEqual(text, 'partial'); self.assertIsNone(response)
    def render_fixture(self):
        body = {'model': audit.runner.transport.MODEL, 'stream': True, 'truncate': False, 'shift': False,
                'messages': [{'role': 'system', 'content': 'fixture system'},
                             {'role': 'user', 'content': ' \t{ "fixture": true }\n'}]}
        request = copy.deepcopy(body); request.update(stream=False, _debug_render_only=True)
        rendered = 'fixture system\n<role>\n{ "fixture": true }'
        response = {'model': body['model'], '_debug_info': {'rendered_template': rendered, 'image_count': 0}}
        validation = audit.runner.transport.validate_render(response, body['messages'], 'fixture system')
        self.save('request.json', {'path': '/api/chat', 'body': request})
        (self.folder / 'request_body.bin').write_bytes(json.dumps(request).encode())
        self.save('response.json', response); self.save('validation.json', validation)
        self.save('result.json', {'status': 'validated', 'unexpected_generation_evidence': False})
        (self.folder / 'rendered_prompt.txt').write_bytes(rendered.encode())
        return body
    def test_renderer_checks_preserve_json_values_and_recorded_spans(self):
        body = self.render_fixture(); checks = audit.Checks()
        audit.audit_render(checks, self.folder, body, 'fixture')
        self.assertTrue(all(x['passed'] for x in checks.rows), checks.rows)
    def test_changed_rendered_prompt_is_detected(self):
        body = self.render_fixture()
        (self.folder / 'rendered_prompt.txt').write_text('omitted history', encoding='utf-8')
        checks = audit.Checks(); audit.audit_render(checks, self.folder, body, 'fixture')
        failed = [x['id'] for x in checks.rows if not x['passed']]
        self.assertIn('fixture:render_saved_text', failed)
    def test_generation_in_render_only_response_is_detected(self):
        body = self.render_fixture()
        value = audit.read(self.folder / 'response.json'); value['eval_count'] = 1
        self.save('response.json', value)
        checks = audit.Checks(); audit.audit_render(checks, self.folder, body, 'fixture')
        self.assertIn('fixture:render_no_generation', [x['id'] for x in checks.rows if not x['passed']])


if __name__ == '__main__': unittest.main()
