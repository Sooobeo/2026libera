"""Pure schedule and mocked offline-builder checks; no solver or model calls."""
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from research.v64_reduced import design

ROOT = Path(__file__).resolve().parents[2]


class ScheduleTests(unittest.TestCase):
    def test_default_draft_preserves_all_types_but_all_424_are_fresh(self):
        specification = design.make_design()
        counts = design.phase_counts(specification)
        self.assertEqual(counts, {'development-pilot':60,'B-main':240,'x-replacement':36,
                                  'negative-control':48,'A':20,'C':20})
        metadata = design.derivation_metadata(specification)
        self.assertEqual(metadata['total_trajectories'],424)
        self.assertEqual(metadata['logical_stages'],1272)
        self.assertEqual(metadata['historical_responses_credited'],0)
        self.assertFalse(metadata['original_3272_trajectory_protocol_complete'])

    def test_parameterized_counts_and_scope(self):
        for n in design.SUPPORTED_MAIN_COUNTS:
            specification = design.make_design(main_scenarios=n)
            counts = design.phase_counts(specification)
            self.assertEqual(counts['B-main'],20*n)
            self.assertEqual(counts['x-replacement'],3*n)
            self.assertEqual(sum(counts.values()),148+23*n)
            strata = Counter(design.precision(sid) for sid in specification['main_scenario_ids'])
            self.assertLessEqual(max(strata.get(r,0) for r in (.5,1.,2.))-min(strata.get(r,0) for r in (.5,1.,2.)),1)
        main_only = design.make_design(main_scenarios=2,enabled_phases=('B-main',))
        self.assertEqual(design.phase_counts(main_only),{'development-pilot':0,'B-main':40,'x-replacement':0,'negative-control':0,'A':0,'C':0})
        with self.assertRaises(ValueError):
            design.make_design(enabled_phases=('x-replacement',))

    def test_target_cells_match_original_seed_3001_independently(self):
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(3001)))
        expected = {}
        for stratum,r in enumerate((.5,1.,2.)):
            funds = np.repeat(np.arange(4),5)
            rng.shuffle(funds)
            for i,fund in zip(range(stratum,60,3),funds):
                expected.setdefault((r,f'F{int(fund)+1:02d}'),f'main-{i+1:03d}')
        actual = {(row['precision'],row['replacement_target_fund']):row['scenario_id'] for row in design.original_target_cells()}
        self.assertEqual(actual,expected)
        self.assertEqual(design.choose_main_scenarios(12),['main-001','main-002','main-003','main-007','main-008','main-009','main-010','main-011','main-012','main-013','main-024','main-029'])
        self.assertEqual(design.choose_main_scenarios(6),['main-001','main-002','main-003','main-007','main-008','main-012'])

    def test_original_subset_order_and_unique_replicate_one(self):
        original = design.planned_schedule()
        selected = [row for phase in design.PHASES for row in design.select_phase_schedule(phase,'F03')]
        keys = [(r['block'],r['scenario'],r['fund_id'],r['arm'],r['replicate']) for r in selected]
        self.assertEqual(len(set(keys)),424)
        self.assertTrue(all(row['replicate']==1 and row['logical_stages']==3 for row in selected))
        self.assertEqual([row['execution_order'] for row in selected],sorted(row['execution_order'] for row in selected))
        self.assertTrue(all(original[row['execution_order']-1]==row for row in selected))
        selected[0]['fund_id']='corrupted-local-copy'
        self.assertNotEqual(design.select_phase_schedule('development-pilot','F03')[0]['fund_id'],'corrupted-local-copy')

    def test_pending_policy_cannot_credit_history_or_change_replicates(self):
        for field,value in [('historical_005_responses_credited_to_new_design',20),('replicates',2),('fresh_generation_required',False)]:
            specification = design.make_design()
            specification[field]=value
            with self.assertRaises(ValueError):
                design.validate_design(specification)
        for count in (True,0,4,60):
            with self.assertRaises(ValueError):
                design.choose_main_scenarios(count)


class OfflineBuilderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.addCleanup(self.directory.cleanup)
        self.manifest = Path(self.directory.name)/'design.json'
        self.manifest.write_text(json.dumps({'status':'DRAFT_PENDING_SCOPE_CONFIRMATION','design':design.make_design()}),encoding='utf-8')
        self.config = {'design_manifest_path':str(self.manifest.relative_to(ROOT)),
                       'profiles_path':'unused-profiles.json','documents_path':'unused-documents.json','smoke_fund_id':'F03'}
        self.profiles = {fund:{'fund_id':fund,'profile_marker':fund} for fund in design.FUNDS}
        self.calls = []
        self.generated_sizes = []

    def generated(self,calibration,block):
        count={'development':12,'main':60,'negative_control':8}[block]
        return ([{'scenario_id':f'{block}-{i:03d}','r':(.5,1.,2.)[(i-1)%3],
                  'private_signals':{fund:[i,int(fund[-1])] for fund in design.FUNDS}}
                 for i in range(1,count+1)],
                [{'scenario_id':f'{block}-{i:03d}','hidden_marker':i} for i in range(1,count+1)])

    def replacements(self,calibration,scenarios,hidden):
        self.generated_sizes.append((len(scenarios),len(hidden)))
        targets={r['scenario']:r['fund_id'] for r in design.planned_schedule() if r['block']=='x-replacement'}
        return [{'scenario_id':s['scenario_id'],'fund_id':targets[s['scenario_id']],
                 'replacement_x':['replacement',s['scenario_id']]} for s in scenarios]

    def b_input(self,profile,calibration,scenario,tokenizer,**kwargs):
        self.calls.append((deepcopy(profile),deepcopy(scenario)))
        return {'profile':deepcopy(profile),'scenario_id':scenario['scenario_id'],
                'signals':deepcopy(scenario['private_signals'])}

    def build(self,phase):
        original_selector = design.original.select_phase_schedule
        with ExitStack() as stack:
            stack.enter_context(patch.object(design.original,'load_profiles',return_value=deepcopy(self.profiles)))
            stack.enter_context(patch.object(design.numerics,'calibrate',return_value={'fixture':True}))
            generate=stack.enter_context(patch.object(design.numerics,'generate_scenarios',side_effect=self.generated))
            stack.enter_context(patch.object(design.numerics,'replacement_signals',side_effect=self.replacements))
            stack.enter_context(patch.object(design.original,'b_input',side_effect=self.b_input))
            stack.enter_context(patch.object(design.original,'actual_document_input',side_effect=lambda profile,cal,module,path,tokenizer:{'profile':profile,'module':module}))
            stack.enter_context(patch('urllib.request.urlopen',side_effect=AssertionError('No network in preparation')))
            result=design.build_phase(ROOT,self.config,phase,object())
        self.assertIs(design.original.select_phase_schedule,original_selector)
        return result,generate

    def test_main_returns_only_selected_scenarios_and_cases(self):
        package,_=self.build('B-main')
        self.assertEqual(len(package['scenarios_evaluator_only']),12)
        self.assertEqual(len(package['hidden_evaluator_only']),12)
        self.assertEqual(len(package['cases']),48)
        self.assertEqual(len(self.calls),48)
        self.assertEqual(len(package['entries']),240)
        self.assertEqual({s['scenario_id'] for s in package['scenarios_evaluator_only']},set(design.choose_main_scenarios(12)))

    def test_counterfactual_draws_from_full_original_60_before_filtering(self):
        package,_=self.build('x-replacement')
        self.assertEqual(self.generated_sizes,[(60,60)])
        self.assertEqual(len(package['scenarios_evaluator_only']),12)
        self.assertEqual(len(package['hidden_evaluator_only']),12)
        self.assertEqual(len(package['replacement_assignments']),12)
        self.assertEqual(len(package['cases']),12)
        targets={row['scenario_id']:row['fund_id'] for row in package['replacement_assignments']}
        for scenario in package['scenarios_evaluator_only']:
            target=targets[scenario['scenario_id']]
            self.assertEqual(scenario['private_signals'][target],['replacement',scenario['scenario_id']])
            self.assertEqual(sum(values[0]=='replacement' for values in scenario['private_signals'].values()),1)

    def test_negative_control_preserves_all_four_source_profiles_and_shared_signals(self):
        package,_=self.build('negative-control')
        self.assertEqual(len(package['entries']),48)
        self.assertEqual(len(package['cases']),16)
        for profile,scenario in self.calls:
            index=int(scenario['scenario_id'].rsplit('-',1)[1])-1
            expected=f'F{index%4+1:02d}'
            self.assertEqual(profile['profile_marker'],expected)
            self.assertEqual(profile['source_fund_id'],expected)
            self.assertEqual(set(scenario['private_signals']),{'N01','N02','N03','N04'})
            self.assertEqual(len({tuple(x) for x in scenario['private_signals'].values()}),1)

    def test_actual_documents_do_not_generate_unused_main_scenarios(self):
        for phase in ('A','C'):
            package,generate=self.build(phase)
            generate.assert_not_called()
            self.assertEqual(len(package['entries']),20)
            self.assertEqual(len(package['cases']),4)
            self.assertEqual(package['scenarios_evaluator_only'],[])
            self.assertEqual(package['hidden_evaluator_only'],[])

    def test_explicit_manifest_and_enabled_phase_required(self):
        with self.assertRaises(ValueError):
            design.build_phase(ROOT,{},'B-main',object())
        self.manifest.write_text(json.dumps({'design':design.make_design(main_scenarios=1,enabled_phases=('B-main',))}),encoding='utf-8')
        with self.assertRaises(ValueError):
            design.build_phase(ROOT,self.config,'A',object())


if __name__=='__main__':
    unittest.main()
