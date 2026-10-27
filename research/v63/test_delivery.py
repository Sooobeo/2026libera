"""Delivery records must never turn attempted or unresolved work into completion."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from research.v63.build_delivery import numerical_summary, preparation_schedule_summary
from research.v63.runtime import planned_schedule


class DeliveryTests(unittest.TestCase):
    def fixture(self):
        root=Path(__file__).resolve().parents[2]
        path=next((root/'plan').glob('*설정_v6.3_20261027.json'))
        plan=json.loads(path.read_text(encoding='utf-8-sig'))
        rows=planned_schedule()
        return {'model_calls':0,'trajectories':len(rows),'logical_stages':9816,'schedule':rows},plan

    def test_plan_is_3272_unattempted_trajectories_and_9816_stages(self):
        schedule,plan=self.fixture()
        summary=preparation_schedule_summary(schedule,plan)
        self.assertEqual(summary['trajectories'],3272)
        self.assertEqual(summary['not_attempted_stages'],9816)
        self.assertEqual(summary['attempted_stages'],0)

    def test_missing_and_incomplete_schedule_fail_closed(self):
        schedule,plan=self.fixture()
        with self.assertRaises(ValueError):preparation_schedule_summary({},plan)
        schedule['schedule'].pop()
        with self.assertRaises(ValueError):preparation_schedule_summary(schedule,plan)

    def test_attempted_or_fallback_entries_cannot_report_zero(self):
        schedule,plan=self.fixture()
        for key,value in [('status','completed'),('status','operational_failure'),('effective_weights',[1/12]*12)]:
            changed=deepcopy(schedule)
            changed['schedule'][0][key]=value
            with self.assertRaises(ValueError):preparation_schedule_summary(changed,plan)
        schedule['model_calls']=1
        with self.assertRaises(ValueError):preparation_schedule_summary(schedule,plan)

    def test_duplicate_trajectory_rejected(self):
        schedule,plan=self.fixture()
        schedule['schedule'][1]=deepcopy(schedule['schedule'][0])
        with self.assertRaisesRegex(ValueError,'Duplicate'):preparation_schedule_summary(schedule,plan)

    def test_unresolved_sweep_never_completed(self):
        result=numerical_summary({'checks':[{'status':'passed'}]*40+[{'status':'failed'}]*8,
                                 'minimum_variance_boundary':{'status':'passed'}})
        self.assertEqual((result['sweep_passed'],result['sweep_failed']),(40,8))
        self.assertFalse(result['all_synthetic_checks_resolved'])
        self.assertIn('미해결 8건',result['label'])

    def test_boundary_failure_separate_from_passing_sweep(self):
        result=numerical_summary({'checks':[{'status':'passed'}]*48,
                                 'minimum_variance_boundary':{'status':'explicit_evaluator_failure_before_model_request'}})
        self.assertFalse(result['all_synthetic_checks_resolved'])
        self.assertIn('최소분산 경계 미해결',result['label'])
        self.assertFalse(numerical_summary({})['all_synthetic_checks_resolved'])


if __name__=='__main__':unittest.main()
