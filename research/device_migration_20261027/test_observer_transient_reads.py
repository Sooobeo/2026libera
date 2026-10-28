"""Isolated Windows sharing-lock regressions; no live campaign or model work."""
import ctypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from research import observe_v63_candidate_003 as observer


@unittest.skipUnless(os.name == 'nt', 'Exercises real Windows file sharing locks.')
class ObserverSharingTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parents[2]
        self.temporary = tempfile.TemporaryDirectory(prefix='observer_share_test_', dir=self.workspace/'tmp')
        self.root = Path(self.temporary.name).resolve()
        self.assertEqual(self.root.parent, (self.workspace/'tmp').resolve())
        self.run_id = '4'*64
        self.config = self.root/'config/candidate_004/campaign_config.json'
        self.state_path = self.root/'data/current/development_supervisor'/self.run_id/'state.json'
        self.write(self.config, {'output_root':'data/current', 'runtime_freeze_path':'config/candidate_004/runtime_candidate.json'})
        self.write(self.config.parent/'selection_receipt.json', {
            'new_run_id':self.run_id, 'previous_experimental_generation_requests_recorded':14,
            'previous_engineering_generation_requests_recorded':5, 'previous_raw_files_expected':266,
            'previous_raw_files_available':0, 'previous_candidate_responses_reused':0,
            'historical_cost_scope':'Synthetic fixture only', 'new_python_version':'3.13.3',
            'human_review_mode':'user_assumed_completed',
        })
        self.write(self.config.parent/'runtime_candidate.json', {'main_model_frozen':False, 'model':'fixture'})
        self.state = {'run_id':self.run_id, 'status':'running', 'phase':'technical-smoke',
                      'supervisor_pid':os.getpid(), 'started_at_utc':datetime.now(timezone.utc).isoformat()}
        self.write(self.state_path, self.state)
        self.patches = [
            patch.object(observer, 'ROOT', self.root),
            patch.object(observer, 'RECORD', self.root/'research/observer'),
            patch.object(observer, 'JSON_OUTPUT', self.root/'research/observer/live.json'),
            patch.object(observer, 'HTML_OUTPUT', self.root/'reference/current.html'),
            patch.object(observer, 'READ_RETRY_DELAYS', (0.01, 0.02)),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        # Validate the exact recursive cleanup boundary before removing fixtures.
        self.assertEqual(Path(self.temporary.name).resolve().parent, (self.workspace/'tmp').resolve())
        self.temporary.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def exclusive(self, path):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                      ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return kernel, handle

    def test_real_exclusive_lock_retries_and_recovers(self):
        kernel, handle = self.exclusive(self.state_path)
        released = threading.Event()
        def release():
            kernel.CloseHandle(handle)
            released.set()
        timer = threading.Timer(0.12, release)
        timer.start()
        try:
            errors = []
            with patch.object(observer, 'READ_RETRY_DELAYS', (0.05, 0.1, 0.2)):
                value = observer.read(self.state_path, errors, required=True)
            self.assertEqual(value, self.state)
            self.assertEqual(errors, [])
        finally:
            timer.join(timeout=1)
            if not released.is_set():
                timer.cancel()
                kernel.CloseHandle(handle)

    def test_shared_reader_permits_rename_and_keeps_old_bytes(self):
        replacement = self.state_path.with_suffix('.replacement')
        self.write(replacement, {**self.state, 'phase':'paired-feasibility'})
        with observer.shared_reader(self.state_path) as stream:
            # FILE_SHARE_DELETE permits rename of the open target. Windows
            # MoveFileEx replacement may still need the writer's retry until
            # the old handle closes; do not claim it is unconditionally free.
            os.rename(self.state_path, self.state_path.with_suffix('.old'))
            os.replace(replacement, self.state_path)
            self.assertEqual(json.load(stream)['phase'], 'technical-smoke')
        self.assertEqual(observer.read(self.state_path, [])['phase'], 'paired-feasibility')

    def test_lock_with_last_known_live_pid_is_unknown_and_continues(self):
        previous = observer.snapshot(self.config)
        kernel, handle = self.exclusive(self.state_path)
        try:
            value = observer.snapshot(self.config, previous=previous)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(value['status'], 'supervisor_state_unavailable')
        self.assertFalse(value['supervisor_state_fresh'])
        self.assertEqual(value['supervisor_state_source'], 'last_known_snapshot')
        self.assertTrue(value['supervisor_alive'])
        self.assertTrue(value['watch_should_continue'])
        self.assertTrue(value['observation_errors'])
        self.assertEqual(value['observer_model_calls'], 0)

    def test_lock_without_history_stays_unknown_and_continues(self):
        kernel, handle = self.exclusive(self.state_path)
        try:
            value = observer.snapshot(self.config)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(value['status'], 'supervisor_state_unavailable')
        self.assertIsNone(value['supervisor_alive'])
        self.assertTrue(value['watch_should_continue'])
        self.assertNotEqual(value['status'], 'supervisor_not_started')

    def test_unlock_restores_fresh_running_observation(self):
        kernel, handle = self.exclusive(self.state_path)
        try:
            unknown = observer.snapshot(self.config)
        finally:
            kernel.CloseHandle(handle)
        value = observer.snapshot(self.config, previous=unknown)
        self.assertEqual(value['status'], 'running')
        self.assertTrue(value['supervisor_state_fresh'])
        self.assertEqual(value['supervisor_state_source'], 'current_read')
        self.assertTrue(value['watch_should_continue'])

    def test_unverified_process_query_keeps_watching(self):
        with patch.object(observer, 'process_alive', return_value=None):
            value = observer.snapshot(self.config)
        self.assertEqual(value['status'], 'supervisor_process_unverified')
        self.assertIsNone(value['supervisor_alive'])
        self.assertTrue(value['watch_should_continue'])

    def test_confirmed_dead_pid_stops_even_when_state_unreadable(self):
        previous = observer.snapshot(self.config)
        kernel, handle = self.exclusive(self.state_path)
        try:
            with patch.object(observer, 'process_alive', return_value=False):
                value = observer.snapshot(self.config, previous=previous)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(value['status'], 'supervisor_process_not_running')
        self.assertFalse(value['watch_should_continue'])

    def test_fresh_terminal_state_stops(self):
        self.write(self.state_path, {**self.state, 'status':'stopped_requires_review'})
        value = observer.snapshot(self.config)
        self.assertEqual(value['status'], 'stopped_requires_review')
        self.assertFalse(value['watch_should_continue'])

    def test_preboot_state_stops_before_access_denied_pid_query(self):
        now = datetime.now(timezone.utc)
        self.write(self.state_path, {**self.state, 'started_at_utc':(now-timedelta(hours=2)).isoformat()})
        with patch.object(observer, 'windows_boot_time', return_value=now-timedelta(hours=1)), \
                patch.object(observer, 'windows_process_info', return_value=(None, None)) as info:
            value = observer.snapshot(self.config)
        info.assert_not_called()
        self.assertEqual(value['status'], 'supervisor_process_not_running')
        self.assertFalse(value['supervisor_alive'])
        self.assertFalse(value['watch_should_continue'])

    def test_later_creation_time_detects_reused_pid(self):
        now = datetime.now(timezone.utc)
        expected = now-timedelta(minutes=2)
        with patch.object(observer, 'windows_boot_time', return_value=now-timedelta(days=1)), \
                patch.object(observer, 'windows_process_info', return_value=(True, expected+timedelta(seconds=60))):
            self.assertFalse(observer.process_alive(12345, expected.isoformat()))

    def test_matching_current_process_creation_is_alive(self):
        now = datetime.now(timezone.utc)
        expected = now-timedelta(seconds=10)
        with patch.object(observer, 'windows_boot_time', return_value=now-timedelta(days=1)), \
                patch.object(observer, 'windows_process_info', return_value=(True, expected-timedelta(seconds=2))):
            self.assertTrue(observer.process_alive(12345, expected.isoformat()))

    def test_real_get_process_times_for_this_interpreter(self):
        alive, created = observer.windows_process_info(os.getpid())
        self.assertTrue(alive)
        self.assertIsNotNone(created)
        self.assertLessEqual(created, datetime.now(timezone.utc))
        self.assertTrue(observer.process_alive(os.getpid(), created.isoformat()))

    def test_invalid_start_times_are_unknown(self):
        future = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        with patch.object(observer, 'windows_process_info') as info:
            for value in ('bad timestamp', '2026-10-27T00:00:00', future, 123):
                with self.subTest(value=value):
                    self.assertIsNone(observer.process_alive(12345, value))
        info.assert_not_called()

    def test_boot_margin_and_access_denied_remain_unknown(self):
        now = datetime.now(timezone.utc)
        boot = now-timedelta(hours=1)
        with patch.object(observer, 'windows_boot_time', return_value=boot), \
                patch.object(observer, 'windows_process_info', return_value=(None, None)):
            self.assertIsNone(observer.process_alive(12345, (boot-timedelta(seconds=15)).isoformat()))

    def test_snapshot_passes_recorded_start_to_process_check(self):
        with patch.object(observer, 'process_alive', return_value=True) as check:
            observer.snapshot(self.config)
        check.assert_called_once_with(os.getpid(), self.state['started_at_utc'])

    def test_atomic_output_retries_same_fsynced_bytes_until_real_unlock(self):
        target = self.root/'observer_output.json'
        target.write_text('old output', encoding='utf-8')
        kernel, handle = self.exclusive(target)
        released = threading.Event()
        def release():
            kernel.CloseHandle(handle)
            released.set()
        timer = threading.Timer(0.12, release)
        timer.start()
        original_replace = os.replace
        observations = []
        def replace(source, destination):
            path = Path(source)
            observations.append((str(path), path.stat().st_mtime_ns, path.read_bytes()))
            return original_replace(source, destination)
        try:
            with patch.object(observer.os, 'replace', side_effect=replace), \
                    patch.object(observer.os, 'fsync', wraps=os.fsync) as sync:
                observer.atomic_text(target, 'complete new output\n')
            self.assertEqual(sync.call_count, 1)
        finally:
            timer.join(timeout=1)
            if not released.is_set():
                timer.cancel()
                kernel.CloseHandle(handle)
        self.assertGreaterEqual(len(observations), 2)
        self.assertEqual(len(set(observations)), 1)
        self.assertEqual(target.read_text(encoding='utf-8'), 'complete new output\n')
        self.assertFalse(target.with_name('.'+target.name+'.'+str(os.getpid())+'.tmp').exists())

    def test_atomic_output_permanent_lock_stops_at_deadline(self):
        target = self.root/'observer_output.html'
        target.write_text('old output', encoding='utf-8')
        kernel, handle = self.exclusive(target)
        original_replace = os.replace
        observations = []
        def replace(source, destination):
            path = Path(source)
            observations.append((str(path), path.stat().st_mtime_ns, path.read_bytes()))
            return original_replace(source, destination)
        try:
            with patch.object(observer, 'OUTPUT_REPLACE_RETRY_SECONDS', 0.06), \
                    patch.object(observer.os, 'replace', side_effect=replace), \
                    patch.object(observer.os, 'fsync', wraps=os.fsync) as sync:
                with self.assertRaises(PermissionError) as error:
                    observer.atomic_text(target, 'complete retained temporary\n')
            self.assertIn(error.exception.winerror, {5, 32, 33})
            self.assertEqual(sync.call_count, 1)
        finally:
            kernel.CloseHandle(handle)
        self.assertGreaterEqual(len(observations), 2)
        self.assertEqual(len(set(observations)), 1)
        self.assertEqual(target.read_text(encoding='utf-8'), 'old output')
        temporary = target.with_name('.'+target.name+'.'+str(os.getpid())+'.tmp')
        self.assertEqual(temporary.read_text(encoding='utf-8'), 'complete retained temporary\n')

    def test_atomic_output_unrelated_error_propagates_without_retry(self):
        target = self.root/'observer_output.json'
        target.write_text('old output', encoding='utf-8')
        unrelated = ctypes.WinError(123)
        with patch.object(observer.os, 'replace', side_effect=unrelated) as replace, \
                patch.object(observer.time, 'sleep') as sleep:
            with self.assertRaises(OSError) as error:
                observer.atomic_text(target, 'new output')
        self.assertIs(error.exception, unrelated)
        self.assertEqual(replace.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(target.read_text(encoding='utf-8'), 'old output')

    def test_source_availability_observes_restored_hashes_not_historical_zero(self):
        source = self.root/'data/source.pdf'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b'exact original fixture')
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        self.write(self.root/'data/manifest.json', {'sources':[{'local_path':'data/source.pdf','sha256':expected,'active_profile_reference':True}]})
        self.write(self.root/'data/documents.json', {'documents':[{'document_id':'A-fixture','source_path':'data/source.pdf','source_bytes_sha256':expected}]})
        readiness = {'source_archive_availability':{'manifest':{'path':'data/manifest.json'},'A_C_raw_source_files_present':0,'missing_records':1}}
        value = observer.source_availability({'documents_path':'data/documents.json'}, readiness, [])
        self.assertEqual(value['A_C_raw_source_files_present'], 1)
        self.assertEqual(value['A_C_raw_source_files_hash_verified'], 1)
        self.assertEqual(value['historical_audit']['A_C_raw_source_files_present_at_that_time'], 0)
        source.write_bytes(b'different fixture')
        changed = observer.source_availability({'documents_path':'data/documents.json'}, readiness, [])
        self.assertEqual(changed['A_C_raw_source_files_present'], 1)
        self.assertEqual(changed['A_C_raw_source_files_hash_verified'], 0)

    def guardian(self, status='running', **extra):
        value = {'run_id':self.run_id, 'pid':os.getpid(), 'status':status, 'phase':'development-pilot',
                 'started_at_utc':(datetime.now(timezone.utc)-timedelta(days=10)).isoformat(),
                 'updated_at_utc':datetime.now(timezone.utc).isoformat(), **extra}
        path = self.root/'data/current/guardian'/self.run_id/'checkpoint.json'
        self.write(path, value)
        return path

    def test_guardian_transition_overrides_finished_development_supervisor(self):
        self.write(self.state_path, {**self.state,'status':'feasibility_complete_requires_measured_resource_review'})
        self.guardian()
        value = observer.snapshot(self.config)
        self.assertEqual(value['controller_kind'], 'guardian')
        self.assertEqual(value['controller_state']['phase'], 'development-pilot')
        self.assertEqual(value['status'], 'running')
        self.assertTrue(value['watch_should_continue'])
        self.assertEqual(value['process_identity_evidence']['reference_kind'], 'guardian_last_heartbeat_creation_upper_bound')

    def test_guardian_lock_preserves_unknown_watch_state(self):
        path = self.guardian()
        previous = observer.snapshot(self.config)
        kernel, handle = self.exclusive(path)
        try:
            value = observer.snapshot(self.config, previous=previous)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(value['controller_kind'], 'guardian')
        self.assertEqual(value['status'], 'supervisor_state_unavailable')
        self.assertFalse(value['controller_state_fresh'])
        self.assertTrue(value['watch_should_continue'])

    def test_guardian_terminal_state_stops_without_final_result_claim(self):
        self.guardian(status='completed')
        value = observer.snapshot(self.config)
        self.assertEqual(value['status'], 'guardian_completed')
        self.assertFalse(value['watch_should_continue'])
        self.assertIn('not a final experiment result', value['report_scope'])

    def test_other_run_guardian_is_ignored(self):
        self.guardian(run_id='9'*64)
        value = observer.snapshot(self.config)
        self.assertEqual(value['controller_kind'], 'development_supervisor')
        self.assertEqual(value['status'], 'running')
        self.assertTrue(value['watch_should_continue'])

    def test_verified_power_receipt_is_reported_as_recorded_not_live_query(self):
        path = observer.RECORD/'power_settings_fixture/receipt.json'
        self.write(path, {'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'verified_by_requery':True,
                         'settings':[{'setting':name,'after':{'AC':0,'DC':0}} for name in ('STANDBYIDLE','HIBERNATEIDLE','LIDACTION')]})
        value = observer.power_settings_receipt([])
        self.assertTrue(value['verified_no_idle_sleep_hibernate_or_lid_sleep_at_record_time'])
        self.assertIn('does not query or change OS', value['scope'])

    def test_display_power_receipt_requires_both_modes_zero(self):
        path = observer.RECORD/'power_settings_fixture/receipt.json'
        receipt = {'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'verified_by_requery':True,
                   'settings':[{'setting':'VIDEOIDLE','after':{'AC':0,'DC':0}}]}
        self.write(path, receipt)
        self.assertTrue(observer.power_settings_receipt([])['verified_no_display_idle_at_record_time'])
        receipt['settings'][0]['after']['DC'] = 180
        self.write(path, receipt)
        self.assertFalse(observer.power_settings_receipt([])['verified_no_display_idle_at_record_time'])

    def test_keepawake_claim_requires_current_run_alive_and_fresh(self):
        path = observer.RECORD/'keepawake_candidate005_fixture/status.json'
        receipt = {'run_id':self.run_id,'pid':os.getpid(),'status':'active',
                   'started_at_utc':datetime.now(timezone.utc).isoformat(),
                   'updated_at_utc':datetime.now(timezone.utc).isoformat()}
        self.write(path, receipt)
        self.assertTrue(observer.keepawake_receipt(self.run_id,[])['verified_active'])
        with patch.object(observer,'process_alive',return_value=False):
            self.assertFalse(observer.keepawake_receipt(self.run_id,[])['verified_active'])
        receipt['updated_at_utc']=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
        self.write(path, receipt)
        self.assertFalse(observer.keepawake_receipt(self.run_id,[])['verified_active'])
        self.assertIsNone(observer.keepawake_receipt('9'*64,[]))


if __name__ == '__main__':
    unittest.main()
