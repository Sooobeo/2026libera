import unittest
import numpy as np
from research.v63.statistics import (one_sided_positive,holm,pair_metrics,confirmatory_family,
    stratified_bootstrap,directional_mitigation,CLAIMS,ARMS)

class StatisticsTests(unittest.TestCase):
    def family_fixture(self):
        x=np.linspace(.1,.2,60)
        ids=[f'main-{i+1:03d}' for i in range(60)]
        strata=[(.5,1.,2.)[i%3] for i in range(60)]
        m={a:{'scenario_ids':list(ids),'scenario_strata':list(strata),
              'terminal_statuses':[['completed']*8 for _ in range(60)],'attempted_fund_replicates':[8]*60,
              **{key:x.copy() for key in ['G_full_lower','E_full_lower','E_full_upper','A_full_lower','A_full_upper','G_available_lower','R_available_lower']}}
           for a in ARMS}
        delta={a+'|'+b:np.zeros(60) for a,b in [('R1','R0'),('R1','R2'),('R1','R3'),('R2','R3')]}
        return m,delta,{'frozen_scenario_ids':ids,'frozen_strata':strata}

    def test_constant_does_not_manufacture_significance(self):
        self.assertEqual(one_sided_positive([1.]*60)['p'],1.)
        self.assertEqual(one_sided_positive([.1]*60)['p'],1.)
        self.assertEqual(one_sided_positive([np.nan,1])['p'],1.)

    def test_direction_and_holm_five_claims(self):
        self.assertLess(one_sided_positive(np.linspace(.1,.2,60))['p'],.001)
        result=holm(dict(zip(CLAIMS,[.001,.02,.03,.04,1.])))
        self.assertAlmostEqual(result['H1']['p_holm'],.005)
        self.assertAlmostEqual(result['H2']['p_holm'],.08)
        self.assertFalse(result['H2']['reject'])
        with self.assertRaises(ValueError): holm({'H1':.01})

    def test_swapped_reference_detected_despite_equal_distance(self):
        v=np.zeros((4,12));v[range(4),range(4)]=1
        exact=pair_metrics(v,v); swapped=pair_metrics(v[[1,0,3,2]],v)
        self.assertEqual(exact['G'],0.)
        self.assertEqual(swapped['G'],0.)
        self.assertGreater(swapped['E'],0.)

    def test_absolute_before_mean(self):
        rng=np.random.default_rng(1)
        v=rng.dirichlet(np.ones(12),4);w=rng.dirichlet(np.ones(12),4)
        m=pair_metrics(w,v)
        self.assertGreater(m['A'],abs(m['G']))

    def test_uncertainty_blocks_false_mitigation(self):
        base={'G_full_lower':np.linspace(.1,.2,60),'E_full_lower':np.linspace(.1,.2,60),'A_full_lower':np.linspace(.1,.2,60)}
        candidate={'E_full_upper':np.linspace(.4,.5,60),'A_full_upper':np.linspace(.4,.5,60)}
        self.assertGreater(directional_mitigation(candidate,base,np.linspace(-.2,-.1,60))['p'],.99)

    def test_full_family_and_unattempted_rejection(self):
        m,delta,frozen=self.family_fixture()
        result=confirmatory_family(m,delta,**frozen)
        self.assertEqual(len(result['claims']),5)
        self.assertTrue(result['claims']['H1']['reject'])
        self.assertFalse(result['claims']['H2']['reject'])
        m['R0']['attempted_fund_replicates'][0]=7
        with self.assertRaises(ValueError):confirmatory_family(m,delta,**frozen)

    def test_frozen_manifest_is_required_and_rejects_shared_wrong_ids(self):
        m,delta,frozen=self.family_fixture()
        with self.assertRaises(TypeError):confirmatory_family(m,delta)
        for data in m.values():data['scenario_ids'][0]='unregistered-scenario'
        with self.assertRaisesRegex(ValueError,'frozen input manifest'):
            confirmatory_family(m,delta,**frozen)

    def test_frozen_scenario_order_cannot_follow_observed_outputs(self):
        m,delta,frozen=self.family_fixture()
        for data in m.values():data['scenario_ids']=data['scenario_ids'][::-1]
        with self.assertRaisesRegex(ValueError,'frozen input manifest'):
            confirmatory_family(m,delta,**frozen)

    def test_precision_strata_must_match_frozen_and_be_balanced(self):
        m,delta,frozen=self.family_fixture()
        m['R2']['scenario_strata'][0]=1.
        with self.assertRaisesRegex(ValueError,'strata differ'):
            confirmatory_family(m,delta,**frozen)
        m,delta,frozen=self.family_fixture()
        frozen['frozen_strata'][0]=1.
        for data in m.values():data['scenario_strata']=list(frozen['frozen_strata'])
        with self.assertRaisesRegex(ValueError,'exactly 20'):
            confirmatory_family(m,delta,**frozen)

    def test_terminal_statuses_reject_unattempted_and_protocol_violation(self):
        for forbidden in ['not_attempted','protocol_violation','parent_failure','running','unknown']:
            m,delta,frozen=self.family_fixture()
            m['R3']['terminal_statuses'][7][5]=forbidden
            with self.assertRaisesRegex(ValueError,'eligible terminal'):
                confirmatory_family(m,delta,**frozen)

    def test_terminal_shape_and_model_operational_failures(self):
        m,delta,frozen=self.family_fixture()
        m['R1']['terminal_statuses'][0]=['completed']*7
        with self.assertRaisesRegex(ValueError,'eligible terminal'):
            confirmatory_family(m,delta,**frozen)
        m,delta,frozen=self.family_fixture()
        for data in m.values():
            data['terminal_statuses'][0][0]='model_output_failure'
            data['terminal_statuses'][0][1]='operational_failure'
        result=confirmatory_family(m,delta,**frozen)
        self.assertEqual(result['independent_units'],60)

    def test_bootstrap_is_paired_and_reproducible(self):
        x=np.arange(60)/60.;s=np.repeat([.5,1.,2.],20)
        a=stratified_bootstrap(np.stack([x,x],axis=1),s)
        b=stratified_bootstrap(np.stack([x,x],axis=1),s)
        self.assertEqual(a,b);self.assertEqual(a['lower'][0],a['lower'][1])

if __name__=='__main__':unittest.main()
