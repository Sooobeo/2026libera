"""Synthetic unit checks only: no actual process launch, HTTP or shutdown."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import watch_v492_postpilot as w


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / 'run'; self.run.mkdir()
        self.evidence = self.root / 'service'; self.evidence.mkdir()
        for p in list(w.SCRIPTS.values()) + ['research/watch_v492_postpilot.py']:
            f = self.root / p; f.parent.mkdir(parents=True, exist_ok=True); f.write_text('synthetic non-executable fixture')
        self.put('runtime.json', {'model': 'fixture', 'main_allowed': False})
        self.put('freeze.json', {'status': 'frozen_for_pilot_only', 'main_allowed': False, 'runtime_ref': w.ref(self.root, 'runtime.json')})
        self.put('gate.json', {'status': 'approved_for_pilot_before_generation', 'freeze_ref': w.ref(self.root, 'freeze.json')})
        self.put('service/service_receipt.json', {'status': 'ready', 'origin': 'http://127.0.0.1:11435'})
        self.put('run/pilot_declaration.json', {'purpose': 'pilot_only', 'case_order': w.CASES, 'max_generation_requests': 10,
            'automatic_retries': 0, 'main_model_calls': 0, 'main_frozen': False, 'review_gate': w.ref(self.root, 'gate.json'),
            'runtime': {'model': 'fixture', 'main_allowed': False}, 'runtime_sha256': w.ref(self.root, 'runtime.json')['sha256'], 'origin': 'http://127.0.0.1:11435'})
        self.config_ref = w.prepare_config(self.root, 'config.json', 'run', 'service', 'status.json')
        self.config = w.read(self.root / 'config.json')
        self.summary = {'status': 'pilot_attempt_sequence_finished', 'cases': [], 'generation_requests_attempted': 10,
            'main_model_calls': 0, 'automatic_retries': 0, 'post_final_calls': 0, 'AI_preoutput_review_completed': True,
            'review_mode': 'AI_delegated_by_user', 'independent_human_review_completed': False, 'frozen_for_pilot': True, 'main_frozen': False}
        for case in w.CASES:
            row = {'case_id': case, 'status': 'two_stages_completed_semantic_review_pending', 'stages': []}
            for stage in ['D0', 'F0']:
                s = {'stage': stage, 'status': 'completed', 'generation_requests_attempted': 1, 'continuation_eligible': True}
                row['stages'].append(s)
                self.put('run/' + case + '__' + stage + '/transport_result.json', s)
                self.put('run/' + case + '__' + stage + '/unload_and_residency.json', {'status': 'no_resident_models_observed'})
            self.summary['cases'].append(row)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, value):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding='utf8')

    def write_summary(self):
        self.put('run/pilot_summary.json', self.summary)

    def fake_runner(self, args, **kwargs):
        role = 'analysis' if '--output' in args else 'masked' if '--mapping-dir' in args else 'shutdown'
        self.calls.append(role)
        if role == 'analysis':
            self.put(self.config['analysis_output'], {'status': 'fixture_only_no_semantic_score'})
        elif role == 'masked':
            self.put(self.config['judge_dir'] + '/COMPLETE.json', {'status': 'complete', 'items': 5, 'scoring_performed': False})
            self.put(self.config['mapping_dir'] + '/private_mapping.json', {'fixture': True})
        else:
            self.put('service/service_shutdown_receipt.json', {'status': 'owned_pilot_service_stopped', 'no_resident_models_before_stop': True, 'owned_port_closed': True, 'existing_11434_listener_unchanged': True})
        return 0

    def run_once(self, runner=None):
        self.write_summary()
        return w.watch(self.root, 'config.json', self.config_ref['sha256'], runner=runner or self.fake_runner, max_polls=1)

    def test_dry_run_launches_nothing_and_writes_no_status(self):
        result = w.watch(self.root, 'config.json', self.config_ref['sha256'], dry_run=True, runner=self.fake_runner)
        self.assertEqual(result['status'], 'dry_run_validated_no_commands'); self.assertEqual(self.calls, [])
        self.assertFalse((self.root / 'status.json').exists())

    def test_config_hash_change_fails_before_commands(self):
        self.put('config.json', {**self.config, 'poll_seconds': 1})
        with self.assertRaises(ValueError): self.run_once()
        self.assertEqual(self.calls, [])

    def test_declaration_hash_change_fails_before_commands(self):
        self.put('run/pilot_declaration.json', {'purpose': 'main'})
        with self.assertRaises(ValueError): self.run_once()
        self.assertEqual(self.calls, [])

    def test_partial_summary_waits_without_commands(self):
        (self.run / 'pilot_summary.json').write_text('{')
        result = w.watch(self.root, 'config.json', self.config_ref['sha256'], runner=self.fake_runner, max_polls=1)
        self.assertEqual(result['state'], 'waiting_valid_completed_pilot_summary'); self.assertEqual(self.calls, [])

    def test_partial_write_then_valid_summary_processes_once(self):
        (self.run / 'pilot_summary.json').write_text('{')
        waits = []
        def sleeper(seconds): waits.append(seconds); self.write_summary()
        result = w.watch(self.root, 'config.json', self.config_ref['sha256'], runner=self.fake_runner, sleeper=sleeper, max_polls=2)
        self.assertEqual(waits, [30]); self.assertEqual(self.calls, ['analysis', 'masked', 'shutdown'])
        self.assertEqual(result['state'], 'completed_semantic_review_pending')

    def test_same_invalid_summary_three_polls_exits_without_commands(self):
        (self.run / 'pilot_summary.json').write_text('{')
        waits = []
        result = w.watch(self.root, 'config.json', self.config_ref['sha256'], runner=self.fake_runner, sleeper=waits.append)
        self.assertEqual(result['state'], 'stable_invalid_summary_attention_required')
        self.assertEqual(result['unchanged_invalid_summary_polls'], 3)
        self.assertEqual(waits, [30, 30]); self.assertEqual(self.calls, [])

    def test_observer_lifetime_limit_never_stops_active_work(self):
        times = iter([0, 0, 86400])
        waits = []
        result = w.watch(self.root, 'config.json', self.config_ref['sha256'], runner=self.fake_runner, sleeper=waits.append, clock=lambda: next(times))
        self.assertEqual(result['state'], 'observer_lifetime_exceeded_attention_required')
        self.assertEqual(self.calls, []); self.assertEqual(waits, [30])

    def test_wrong_count_and_wrong_order_never_trigger_processing(self):
        self.summary['generation_requests_attempted'] = 9; self.write_summary()
        with self.assertRaises(ValueError): w.valid_summary(self.root, self.config)
        self.summary['generation_requests_attempted'] = 10; self.summary['cases'].reverse(); self.write_summary()
        with self.assertRaises(ValueError): w.valid_summary(self.root, self.config)

    def test_ineligible_draft_cannot_have_final(self):
        self.summary['cases'][0]['stages'][0]['continuation_eligible'] = False; self.write_summary()
        with self.assertRaises(ValueError): w.valid_summary(self.root, self.config)

    def test_omitted_stage_directory_prevents_completed_identity(self):
        self.summary['cases'][0] = {'case_id': w.CASES[0], 'status': 'not_attempted_after_stop', 'stages': []}
        self.summary['generation_requests_attempted'] = 8; self.write_summary()
        with self.assertRaises(ValueError): w.valid_summary(self.root, self.config)

    def test_postprocessing_failure_still_runs_other_task_and_safe_shutdown(self):
        def runner(args, **kwargs):
            if '--output' in args: self.calls.append('analysis'); raise RuntimeError('synthetic processing failure')
            return self.fake_runner(args, **kwargs)
        result = self.run_once(runner)
        self.assertEqual(self.calls, ['analysis', 'masked', 'shutdown']); self.assertTrue(result['owned_service_stopped'])
        self.assertEqual(result['state'], 'completed_with_errors_attention_required')

    def test_script_changed_after_launch_not_executed_and_cleanup_still_attempted(self):
        self.write_summary(); summary, clean = w.valid_summary(self.root, self.config)
        (self.root / w.SCRIPTS['analysis']).write_text('changed after preflight')
        result = w.process_once(self.root, self.config, summary, clean, {}, runner=self.fake_runner)
        self.assertEqual(self.calls, ['masked', 'shutdown']); self.assertEqual(result['steps'][0]['status'], 'failed_no_retry')

    def test_unconfirmed_cleanup_prevents_shutdown(self):
        self.put('run/' + w.CASES[-1] + '__F0/unload_and_residency.json', {'status': 'idle_not_confirmed'})
        result = self.run_once()
        self.assertEqual(self.calls, ['analysis', 'masked']); self.assertFalse(result['owned_service_stopped'])
        self.assertEqual(result['steps'][-1]['status'], 'not_attempted_cleanup_not_confirmed')

    def test_no_resume_or_repeated_postprocessing(self):
        self.run_once()
        with self.assertRaises(ValueError): self.run_once()
        self.assertEqual(self.calls, ['analysis', 'masked', 'shutdown'])

    def test_stopped_before_first_generation_retains_five_missing_finals(self):
        self.summary['status'] = 'stopped'; self.summary['generation_requests_attempted'] = 0
        self.summary['cases'] = [{'case_id': c, 'status': 'not_attempted_after_stop', 'stages': []} for c in w.CASES]
        for p in self.run.iterdir():
            if p.is_dir():
                for f in p.iterdir(): f.unlink()
                p.rmdir()
        result = self.run_once()
        self.assertEqual(result['generation_requests_attempted'], 0); self.assertEqual(self.calls[-1], 'shutdown')


if __name__ == '__main__':
    unittest.main()
