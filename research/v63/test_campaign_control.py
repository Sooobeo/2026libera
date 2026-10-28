"""Persistence/lock/ledger tests; no real model requests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib,json,os,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
from research.v63 import campaign_control as control
from research.v63.campaign_control import atomic_json,campaign_lock,phase_budget,budget_elapsed,task_request_cost,final_trace_path,merged_history,immutable_json,verify_frozen_artifacts

class ControlTests(unittest.TestCase):
    def test_windows_transient_replace_errors_reuse_flushed_file(self):
        real_replace=os.replace
        for code in (5,32,33):
            with self.subTest(winerror=code), TemporaryDirectory() as d:
                path=Path(d)/'state.json';path.write_text('{"old":true}',encoding='utf8')
                clock=[0.];sleeps=[];snapshots=[]
                failure=OSError('temporary Windows reader lock');failure.winerror=code
                def sleep(seconds):sleeps.append(seconds);clock[0]+=seconds
                def replace(source,destination):
                    snapshots.append((source.read_bytes(),source.stat().st_mtime_ns))
                    if len(snapshots)<=4:raise failure
                    real_replace(source,destination)
                fake_os=SimpleNamespace(name='nt',replace=replace,fsync=os.fsync)
                fake_time=SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep)
                with patch.object(control,'os',fake_os), patch.object(control,'time',fake_time):
                    atomic_json(path,{'new':'새 상태'})
                self.assertEqual(json.loads(path.read_text(encoding='utf8')),{'new':'새 상태'})
                self.assertEqual(sleeps,[.05,.1,.2,.4])
                self.assertTrue(all(snapshot==snapshots[0] for snapshot in snapshots))
                self.assertFalse(path.with_name('.state.json.tmp').exists())

    def test_windows_permanent_lock_stops_after_thirty_seconds_without_data_loss(self):
        for code in (5,32,33):
            with self.subTest(winerror=code), TemporaryDirectory() as d:
                path=Path(d)/'state.json';original=b'{"old":true}\n';path.write_bytes(original)
                clock=[100.];sleeps=[];attempts=[]
                failure=OSError('permanent Windows lock');failure.winerror=code
                def sleep(seconds):sleeps.append(seconds);clock[0]+=seconds
                def replace(source,destination):
                    attempts.append((source.read_bytes(),source.stat().st_mtime_ns));raise failure
                fake_os=SimpleNamespace(name='nt',replace=replace,fsync=os.fsync)
                fake_time=SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep)
                with patch.object(control,'os',fake_os), patch.object(control,'time',fake_time):
                    with self.assertRaises(OSError) as raised:atomic_json(path,{'new':True})
                self.assertIs(raised.exception,failure)
                self.assertAlmostEqual(clock[0]-100.,30.)
                self.assertTrue(all(0<delay<=.5 for delay in sleeps))
                self.assertTrue(all(snapshot==attempts[0] for snapshot in attempts))
                self.assertEqual(path.read_bytes(),original)
                self.assertEqual(json.loads(path.with_name('.state.json.tmp').read_text()),{'new':True})

    def test_other_replace_errors_are_not_retried(self):
        for platform,code in (('nt',87),('nt',None),('posix',5)):
            with self.subTest(platform=platform,winerror=code), TemporaryDirectory() as d:
                path=Path(d)/'state.json';path.write_bytes(b'{"old":true}')
                failure=OSError('not a retryable Windows replacement error')
                if code is not None:failure.winerror=code
                attempts=[]
                def replace(source,destination):attempts.append(source);raise failure
                def sleep(seconds):self.fail('Unrelated replacement failure must propagate immediately.')
                fake_os=SimpleNamespace(name=platform,replace=replace,fsync=os.fsync)
                fake_time=SimpleNamespace(monotonic=lambda:0.,sleep=sleep)
                with patch.object(control,'os',fake_os), patch.object(control,'time',fake_time):
                    with self.assertRaises(OSError) as raised:atomic_json(path,{'new':True})
                self.assertIs(raised.exception,failure);self.assertEqual(len(attempts),1)
                self.assertEqual(path.read_bytes(),b'{"old":true}')

    @unittest.skipUnless(os.name=='nt','Requires real Windows file sharing semantics.')
    def test_real_windows_reader_without_delete_share_releases_pending_replace(self):
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
                                    wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        with TemporaryDirectory() as d:
            path=Path(d)/'state.json';original=b'{"old":true}\n';path.write_bytes(original)
            handle=kernel.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
            self.assertNotEqual(handle,wintypes.HANDLE(-1).value,ctypes.get_last_error())
            blocked=threading.Event();done=threading.Event();errors=[];codes=[]
            real_replace=os.replace
            def observed_replace(source,destination):
                try:real_replace(source,destination)
                except OSError as exc:
                    codes.append(getattr(exc,'winerror',None));blocked.set();raise
            def writer():
                try:atomic_json(path,{'new':'원자 교체'})
                except BaseException as exc:errors.append(exc)
                finally:done.set()
            thread=threading.Thread(target=writer,daemon=True)
            try:
                with patch.object(control,'os',SimpleNamespace(name='nt',replace=observed_replace,fsync=os.fsync)):
                    thread.start()
                    self.assertTrue(blocked.wait(5),'Actual locked replacement was not observed.')
                    self.assertFalse(done.is_set(),'Writer must wait while the read handle denies deletion.')
                    self.assertEqual(path.read_bytes(),original)
                    self.assertTrue(kernel.CloseHandle(handle));handle=None
                    self.assertTrue(done.wait(5),'Writer did not complete after the real read lock was released.')
                    thread.join(1)
                self.assertFalse(errors,errors)
                self.assertTrue(codes and all(code in (5,32,33) for code in codes))
                self.assertEqual(json.loads(path.read_text(encoding='utf8')),{'new':'원자 교체'})
                self.assertFalse(path.with_name('.state.json.tmp').exists())
            finally:
                if handle is not None:kernel.CloseHandle(handle)
                if thread.is_alive():thread.join(5)

    def test_parseable_partial_trace_is_preserved_for_recovery(self):
        with TemporaryDirectory() as d:
            task=Path(d);trace=task/'trajectory/trace.json'
            for status in ('not_attempted','running'):
                atomic_json(trace,{'status':status,'effective_weights':None})
                self.assertIsNone(final_trace_path(task));self.assertTrue(trace.is_file())
                atomic_json(task/'trace_pointer.json',{'relative_path':'trajectory/trace.json','sha256':hashlib.sha256(trace.read_bytes()).hexdigest()})
                self.assertIsNone(final_trace_path(task))
                (task/'trace_pointer.json').unlink()
            atomic_json(trace,{'status':'recovery_interrupted','effective_weights':None})
            self.assertEqual(final_trace_path(task),trace)

    def test_old_frozen_oracle_hash_checked_before_refreezing(self):
        with TemporaryDirectory() as d:
            root=Path(d);bank=root/'reference_bank.json';frozen=root/'frozen.json'
            immutable_json(bank,{'mu':[1]})
            atomic_json(frozen,{'artifacts':[{'path':bank.name,'sha256':hashlib.sha256(bank.read_bytes()).hexdigest()}]})
            verify_frozen_artifacts(root,frozen)
            atomic_json(bank,{'mu':[999]})
            with self.assertRaisesRegex(ValueError,'Previously frozen'):verify_frozen_artifacts(root,frozen)
            with self.assertRaisesRegex(ValueError,'Immutable'):immutable_json(bank,{'mu':[1]})

    def test_budget_start_and_limits_survive_reentry(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'budget.json';limits={'max_generation_requests':135,'max_wall_seconds':21600}
            first=phase_budget(path,limits);again=phase_budget(path,limits)
            self.assertEqual(first,again);self.assertGreaterEqual(budget_elapsed(again),0)
            with self.assertRaisesRegex(ValueError,'amendment'):phase_budget(path,{**limits,'max_generation_requests':270})

    def test_os_lock_rejects_second_writer_then_releases(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'lock'
            with campaign_lock(path):
                with self.assertRaisesRegex(RuntimeError,'writer'):
                    with campaign_lock(path):pass
            with campaign_lock(path):pass

    def test_unknown_send_is_counted_conservatively_and_copy_is_outside_ledger(self):
        with TemporaryDirectory() as d:
            root=Path(d);task=root/'run/task';a=task/'http/attempt_000001';a.mkdir(parents=True)
            (a/'runner_request.bin').write_bytes(b'{}')
            self.assertEqual(task_request_cost(task)['uncertain_dispatch_requests'],1)
            atomic_json(a/'attempt_receipt.json',{'generation_requests':1})
            view=merged_history(task,root/'phase/replay_view')
            self.assertTrue((view/'attempt_000001/runner_request.bin').exists())
            self.assertEqual(task_request_cost(task)['generation_requests'],1)

    def test_trace_pointer_is_hash_bound_and_cannot_escape(self):
        with TemporaryDirectory() as d:
            task=Path(d);trace=task/'recovery_001/trajectory/trace.json';atomic_json(trace,{'status':'operational_failure'})
            atomic_json(task/'trace_pointer.json',{'relative_path':trace.relative_to(task).as_posix(),'sha256':hashlib.sha256(trace.read_bytes()).hexdigest()})
            self.assertEqual(final_trace_path(task),trace.resolve())
            trace.write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash'):final_trace_path(task)

if __name__=='__main__':unittest.main()
