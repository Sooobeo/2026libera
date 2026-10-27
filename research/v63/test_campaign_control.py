"""Persistence/lock/ledger tests; no real model requests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib,json,unittest
from research.v63.campaign_control import atomic_json,campaign_lock,phase_budget,budget_elapsed,task_request_cost,final_trace_path,merged_history,immutable_json,verify_frozen_artifacts

class ControlTests(unittest.TestCase):
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
