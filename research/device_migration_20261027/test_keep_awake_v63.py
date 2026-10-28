"""Isolated lifecycle and process-binding checks; no experiment/model actions."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from research import keep_awake_v63 as helper


class KeepAwakeTests(unittest.TestCase):
    def test_grace_is_bounded_and_terminal_releases_immediately(self):
        active = {'decision':'active'}
        gap = {'decision':'gap'}
        terminal = {'decision':'terminal', 'reason':'completed'}
        self.assertEqual(helper.keep_decision(active, 100, None, 120)[:2], (True,100))
        self.assertTrue(helper.keep_decision(gap, 219, 100, 120)[0])
        self.assertFalse(helper.keep_decision(gap, 220, 100, 120)[0])
        self.assertFalse(helper.keep_decision(terminal, 101, 100, 120)[0])
        self.assertFalse(helper.keep_decision(gap, 1, None, 120)[0])

    def test_kernel_lock_excludes_duplicate_then_releases(self):
        with tempfile.TemporaryDirectory(dir=helper.ROOT/'tmp') as directory:
            lock = Path(directory)/'run.lock'
            with helper.kernel_lock(lock):
                with self.assertRaises(OSError):
                    with helper.kernel_lock(lock):
                        self.fail('Second keeper acquired the same lock')
            with helper.kernel_lock(lock):
                pass

    def test_exact_config_and_role_match(self):
        config = helper.ROOT/'data/candidate_005/campaign_config.json'
        metadata = {'ExecutablePath':'C:/Python/python.exe',
                    'CommandLine':f'python.exe -m research.v63.campaign "{config}" --phase B-main'}
        self.assertTrue(helper.command_matches(metadata,config,'campaign'))
        self.assertFalse(helper.command_matches(metadata,config,'guardian'))
        self.assertFalse(helper.command_matches(metadata,config.parent/'other.json','campaign'))
        metadata['ExecutablePath'] = 'C:/Windows/notepad.exe'
        self.assertFalse(helper.command_matches(metadata,config,'campaign'))

    def observer(self):
        observer = helper.RunObserver.__new__(helper.RunObserver)
        observer.config_path = helper.ROOT/'data/candidate_005/campaign_config.json'
        observer.config_sha = 'hash'
        observer.selection_path = observer.config_path.parent/'selection_receipt.json'
        observer.selection_sha = 'hash'
        observer.output_root = helper.ROOT/'tmp/fake_experiment'
        observer.run_id = 'a'*64
        observer.states = {}
        observer.identities = {}
        return observer

    def test_guardian_handoff_uses_same_run_identity(self):
        observer = self.observer()
        supervisor = {'run_id':observer.run_id,'status':helper.HANDOFF_STATUS,'supervisor_pid':1}
        guardian = {'run_id':observer.run_id,'status':'running','pid':2,'updated_at_utc':'stamp'}
        with patch.object(helper,'digest',return_value='hash'), patch.object(helper,'read',side_effect=[supervisor,guardian]), patch.object(observer,'identity',return_value={'verified_alive':True}):
            observation = observer.observe()
        self.assertEqual(observation['controller'],'guardian')
        self.assertEqual(observation['decision'],'active')

    def test_wrong_run_guardian_cannot_keep_awake(self):
        observer = self.observer()
        with patch.object(helper,'digest',return_value='hash'), patch.object(helper,'read',side_effect=[None,{'run_id':'b'*64,'status':'running','pid':2}]):
            self.assertEqual(observer.observe()['decision'],'gap')

    def test_stale_state_can_use_verified_original_process(self):
        observer = self.observer()
        observer.states['supervisor'] = {'run_id':observer.run_id,'status':'running','supervisor_pid':1}
        with patch.object(helper,'digest',return_value='hash'), patch.object(helper,'read',return_value=None), patch.object(observer,'identity',return_value={'verified_alive':True}):
            observation = observer.observe()
        self.assertFalse(observation['state_fresh'])
        self.assertEqual(observation['decision'],'active')

    def test_recorded_stop_releases_even_when_process_still_exiting(self):
        observer = self.observer()
        state = {'run_id':observer.run_id,'status':'stopped_requires_review','supervisor_pid':1}
        with patch.object(helper,'digest',return_value='hash'), patch.object(helper,'read',side_effect=[state,None]), patch.object(observer,'identity') as identity:
            self.assertEqual(observer.observe()['decision'],'terminal')
            identity.assert_not_called()

    def test_pid_reused_during_metadata_query_is_rejected(self):
        observer = self.observer()
        created = datetime(2026,10,27,13,tzinfo=timezone.utc)
        later = datetime(2026,10,27,14,tzinfo=timezone.utc)
        with patch.object(helper,'process_alive',return_value=True), patch.object(helper,'windows_process_info',side_effect=[(True,created),(True,later)]), patch.object(helper,'process_metadata',return_value={'ExecutablePath':'python.exe','CommandLine':'proof'}), patch.object(helper,'command_matches',return_value=True):
            self.assertFalse(observer.identity(1,'stamp','supervisor')['verified_alive'])

    def test_changed_config_releases(self):
        observer = self.observer()
        with patch.object(helper,'digest',return_value='different'):
            self.assertEqual(observer.observe()['decision'],'terminal')

    def test_power_acquire_clear_and_close_once(self):
        kernel = MagicMock()
        kernel.SetThreadExecutionState.return_value = helper.ES_CONTINUOUS
        kernel.PowerCreateRequest.return_value = 123
        kernel.PowerSetRequest.return_value = 1
        kernel.PowerClearRequest.return_value = 1
        kernel.CloseHandle.return_value = 1
        with patch.object(helper.ctypes,'WinDLL',return_value=kernel):
            power = helper.PowerRequests('test')
            power.acquire()
            power.release()
            power.release()
        self.assertEqual(kernel.PowerSetRequest.call_count,1)
        self.assertEqual(kernel.PowerClearRequest.call_count,1)
        self.assertEqual(kernel.CloseHandle.call_count,1)
        self.assertEqual(kernel.SetThreadExecutionState.call_args_list[-1].args,(helper.ES_CONTINUOUS,))

    def test_partial_api_failure_cleans_up_thread_and_handle(self):
        kernel = MagicMock()
        kernel.SetThreadExecutionState.return_value = helper.ES_CONTINUOUS
        kernel.PowerCreateRequest.return_value = 123
        kernel.PowerSetRequest.return_value = 0
        kernel.CloseHandle.return_value = 1
        with patch.object(helper.ctypes,'WinDLL',return_value=kernel):
            power = helper.PowerRequests('test')
            with self.assertRaises(OSError):
                power.acquire()
        self.assertFalse(power.thread_active)
        self.assertIsNone(power.handle)
        kernel.CloseHandle.assert_called_once_with(123)
        kernel.PowerClearRequest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
