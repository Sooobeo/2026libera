"""Reporting must survive partial files and count recovered tasks once."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research.v63 import record_continuation_snapshot as report
from research.v63.build_continuation_report import verify_completion_commit


class AccountingTest(unittest.TestCase):
    def test_completion_requires_immutable_verified_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            state={'all_experiments_completed':True,'selected_run_id':'synthetic-run'}
            with self.assertRaises(ValueError):verify_completion_commit(state,root)
            def ref(path):return {'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            html=root/'report.html';html.write_text('synthetic test fixture')
            results=root/'results.json';results.write_text('{"synthetic_verification":true}')
            commit=root/'commit.json';commit.write_text(json.dumps({'status':'validated_complete_run','run_id':'synthetic-run','terminal_trajectories':3272,'planned_logical_stages':9816,'artifacts':{'report':ref(html),'results':ref(results)}}))
            state['finalization_commit']=ref(commit)
            self.assertEqual(verify_completion_commit(state,root)['run_id'],'synthetic-run')
            html.write_text('changed after validation')
            with self.assertRaises(ValueError):verify_completion_commit(state,root)

    def test_partial_trace_and_recovered_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'campaign_results';run=out/'runs'/'run1'
            task=run/'B-main'/'task1';(task/'trajectory').mkdir(parents=True)
            (task/'input_identity.json').write_text('{}')
            (task/'trajectory/trace.json').write_text('{"status":')
            with patch.object(report,'ROOT',root):
                partial=report.run_observation(out,run,{})
                self.assertEqual(partial['saved_terminal_traces'],0)
                self.assertEqual(len(partial['selected_trace_issues']),1)
                selected=task/'recovery_001/trajectory/trace.json';selected.parent.mkdir(parents=True)
                selected.write_text(json.dumps({'status':'completed'}))
                (task/'trace_pointer.json').write_text(json.dumps({'relative_path':'recovery_001/trajectory/trace.json','sha256':hashlib.sha256(selected.read_bytes()).hexdigest()}))
                # The original malformed trace remains as crash evidence.
                recovered=report.run_observation(out,run,{})
                self.assertEqual(recovered['saved_terminal_traces'],1)
                self.assertEqual(recovered['trace_status_counts']['completed'],1)
                self.assertEqual(recovered['selected_trace_issues'],[])

    def test_requests_count_original_attempts_and_uncertain_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'campaign_results';run=out/'runs'/'run1'
            task=run/'B-main'/'task1'
            for i,count in ((1,1),(2,0),(3,None)):
                attempt=task/'http'/f'attempt_{i:06d}';attempt.mkdir(parents=True)
                (attempt/'runner_request.bin').write_bytes(b'original')
                if count is not None:(attempt/'attempt_receipt.json').write_text(json.dumps({'generation_requests':count}))
            # Recovery replay copies reside outside runs and are never requests.
            copied=out/'phases/run1/B-main/recovery_inputs/attempt_000001';copied.mkdir(parents=True)
            (copied/'attempt_receipt.json').write_text('{"generation_requests":1}')
            with patch.object(report,'ROOT',root):value=report.run_observation(out,run,{})
            self.assertEqual(value['generation_requests_started'],2)
            self.assertEqual(value['main_generation_requests'],2)
            self.assertEqual(value['request_accounting']['confirmed_attempt_records'],1)
            self.assertEqual(value['request_accounting']['uncertain_dispatch_requests'],1)


if __name__=='__main__':unittest.main()
