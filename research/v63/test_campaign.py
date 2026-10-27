"""Orchestrator unit/integration tests; source profiles here are synthetic fixtures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from research.v63.build_run import profile_errors,load_profiles,select_phase_schedule,b_input,make_numeric_callbacks,baseline_for,original_rule_units,actual_document_input
from research.v63.campaign import normalized_input_hash,verify_amendment,validate_phase_freeze
from research.v63.retrieval import TokenCounter
from research.v63.runtime import gate_errors,REQUIRED_GATES


def profile(fid='F01'):
    return {'fund_id':fid,'period':'development','scientific_ready':True,'complete_holdings':True,'nav_reconciled':True,
        'publication_verified':True,'starting_constraints_verified':True,'coverage':.95,'h':[.05]*10+[.2,.3],
        'source_evidence_ids':['SYNTHETIC-SOURCE'],'objective':'SYNTHETIC UNIT TEST ONLY',
        'mandatory_constraints':[{'evidence_id':'SYNTHETIC-SOURCE','text':'long only'}],'A':[],'b':[]}

def calibration():return {'m0':np.linspace(.001,.012,12),'Sigma':np.eye(12)*.01,'V0':np.eye(12)*.001,'Omega0':np.eye(12)*.001}
def scenario():return {'scenario_id':'development-001','r':1.,'signal_date':'2025-09-30','y':np.linspace(.001,.012,12),
                      'private_signals':{f'F{i:02d}':np.linspace(.01,.12,12) for i in range(1,5)}}
COUNTER=TokenCounter('EXPLICIT SYNTHETIC TEST COUNTER; no production use',lambda x:len(x.split()),True)


class CampaignTests(unittest.TestCase):
    def test_source_gate_is_not_overridden_by_human_assumption(self):
        p=profile();self.assertEqual(profile_errors(p),[])
        p['publication_verified']=False;p['human_review_mode']='user_assumed_completed'
        self.assertIn('publication_verified',profile_errors(p))
        for coverage in [float('nan'),float('inf'),True,.89,1.1]:
            p=profile();p['coverage']=coverage;self.assertTrue(profile_errors(p))

    def test_duplicate_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'profiles.json';path.write_text(json.dumps({'profiles':[profile(),profile()]}))
            with self.assertRaisesRegex(ValueError,'Duplicate'):load_profiles(path,'development',funds=['F01'])

    def test_stage_plan_counts_are_nested_development_subsets(self):
        smoke=select_phase_schedule('technical-smoke','F03');paired=select_phase_schedule('paired-feasibility','F03')
        full=select_phase_schedule('development-pilot','F03')
        self.assertEqual([len(x)*3 for x in (smoke,paired,full)],[15,60,720])
        self.assertTrue(all(row in paired for row in smoke));self.assertTrue(all(row in full for row in paired))
        self.assertEqual(len(select_phase_schedule('B-main','F03'))*3,7200)

    def test_own_numeric_registry_does_not_expose_other_funds(self):
        case=b_input(profile(),calibration(),scenario(),COUNTER)
        self.assertTrue(all('/F01/' in eid for eid in case['evidence_registry']))
        self.assertNotIn('private_signals',case['baseline'])
        self.assertNotIn('theta',case['baseline'])
        tools,_=make_numeric_callbacks(case)
        some=list(case['evidence_registry'])[:2]
        self.assertIn('error',tools('posterior',{'exposed_evidence_ids':some},frozenset()))
        result=tools('posterior',{'exposed_evidence_ids':some},frozenset(some))
        self.assertEqual(set(result),{'mean','covariance','evidence_ids'})
        self.assertEqual(result['evidence_ids'],sorted(some))

    def test_long_mandate_collection_preserves_whole_individual_rules(self):
        p=profile();p['mandatory_constraints']=[{'text':('rule'+str(i)+' ')*100} for i in range(10)]
        case=b_input(p,calibration(),scenario(),COUNTER)
        full=case['retrieval']['full']['text']
        self.assertTrue(all(('rule'+str(i)+' ')*100 in full for i in range(10)))
        self.assertTrue(all(c['tokens']<=400 for c in case['retrieval']['all_chunk_scores']))

    def test_calculator_numeric_strings_do_not_crash_or_normalize(self):
        case=b_input(profile(),calibration(),scenario(),COUNTER);tools,check=make_numeric_callbacks(case)
        raw=[str(v) for v in profile()['h']]
        result=tools('check_portfolio',{'raw_weights':raw},frozenset())
        self.assertAlmostEqual(result['sum'],1.)
        invalid=[.2]*12;self.assertFalse(check(invalid)['valid'])
        self.assertEqual(check(invalid)['raw_weights'],invalid)

    def test_a_c_baseline_has_no_synthetic_observations(self):
        for module in ('A','C'):
            base=baseline_for(profile(),calibration(),None,module)
            self.assertFalse(set(base)&{'y','m0','V0','Omega0'})

    def test_explicit_constraint_coefficients_are_visible(self):
        p=profile();p['A']=[[1]+[0]*11];p['b']=[.5]
        base=baseline_for(p,calibration(),scenario(),'B')
        translated=base['mandatory_constraints'][-1]
        self.assertEqual(translated['rows'][0]['coefficients'],p['A'][0])
        self.assertEqual(translated['rows'][0]['upper_bound'],.5)

    def test_negative_input_hash_ignores_only_virtual_labels(self):
        hashes=[]
        for label in ('N01','N02','N03','N04'):
            s=scenario();s['scenario_id']='negative_control-001';s['private_signals']={label:np.linspace(.01,.12,12)}
            case=b_input(profile(label),calibration(),s,COUNTER,fund_id=label)
            hashes.append(normalized_input_hash(case,'R1',{'seed':1001}))
        self.assertEqual(len(set(hashes)),1)
        case['baseline']['h']=[1/12]*12
        self.assertNotEqual(normalized_input_hash(case,'R1',{'seed':1001}),hashes[0])

    def test_user_amendment_is_hash_bound_without_fake_humans(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'amendment.json'
            path.write_text(json.dumps({'human_review_mode':'user_assumed_completed','human_review_gate_satisfied_by_user_assumption':True,
                                       'actual_independent_human_reviews_evidenced':False}))
            ref={'path':'amendment.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertFalse(verify_amendment(root,ref)['actual_independent_human_reviews_evidenced'])
            freeze={'workspace_root':str(root),'human_review_mode':'user_assumed_completed','execution_amendment':ref,
                    'execution_phase':'technical-smoke','gates':{k:True for k in REQUIRED_GATES}}
            freeze['gates']['complete_sources']=False;freeze['gates']['pilot_measurements']=False
            errors=gate_errors(freeze)
            self.assertNotIn('two_independent_human_audits_missing',errors)
            self.assertIn('complete_sources',errors);self.assertNotIn('pilot_measurements',errors)
            ref['sha256']='bad';self.assertIn('human_assumption_amendment_hash_missing',gate_errors(freeze))

    def test_main_requires_explicit_post_development_model_freeze(self):
        validate_phase_freeze({'main_model_frozen':False},'technical-smoke')
        with self.assertRaisesRegex(ValueError,'resource review'):
            validate_phase_freeze({'main_model_frozen':False},'B-main')
        validate_phase_freeze({'main_model_frozen':True},'B-main')

    def test_projection_preserves_semantics_and_full_source_slices(self):
        p=profile();rule={'evidence_id':'RULE','source_document_id':'SOURCE','source_url':'https://example.test/source','source_line':2,
            'source_excerpt':'Full original clause one. Full original clause two.','text':'Complete audited rule with every exception.',
            'denominator':'NAV','handling':'class3','numerically_enforced_in_FF12':False}
        p['mandatory_constraints']=[rule];base=baseline_for(p,calibration(),scenario(),'B')
        projected=base['mandatory_constraints'][0]
        self.assertEqual(projected['text'],rule['text']);self.assertNotIn('source_excerpt',projected)
        cut=26;parts=[{'text':rule['source_excerpt'][:cut],'original_start':0,'original_end':cut,'shared_context':''},
                    {'text':rule['source_excerpt'][cut:],'original_start':cut,'original_end':len(rule['source_excerpt']),'shared_context':'NAV'}]
        mapping={'F01|development|RULE':{'source_excerpt_sha256':hashlib.sha256(rule['source_excerpt'].encode()).hexdigest(),'source_document_id':'SOURCE','units':parts}}
        case=b_input(p,calibration(),scenario(),COUNTER,mandate_units=mapping)
        self.assertTrue(all(part['text'] in case['retrieval']['full']['text'] for part in parts))
        self.assertIn(rule['text'],case['retrieval']['full']['text'])
        parts[1]['original_start']+=1
        with self.assertRaisesRegex(ValueError,'contiguous'):original_rule_units(p,rule,mapping)

    def test_explicit_gold_and_source_cutoff_do_not_change_visible_original_units(self):
        base={'fund_id':'F01','period':'C','role':'outlook','source_eligibility_verified':True,'text_is_original_eligible_section':True,
              'header':'Original source.','source_url':'https://example.test/source','units':[{'text':'forecast fact','evidence_ids':['G']},{'text':'footnote retained','evidence_ids':['N']}],
              'retrieval_gold_evidence_ids':['G']}
        docs=[{**deepcopy(base),'document_id':'eligible','publication_date':'2026-04-01'},
              {**deepcopy(base),'document_id':'old','publication_date':'2026-03-31'},
              {**deepcopy(base),'document_id':'future','publication_date':'2026-07-01'}]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'documents.json';path.write_text(json.dumps(docs))
            result=actual_document_input(profile(),calibration(),'C',path,COUNTER)['retrieval']
            self.assertEqual(result['eligible_ids'],['eligible']);self.assertEqual(result['diagnostics_evaluator_only']['gold_unit_count'],1)
            self.assertIn('footnote retained',result['full']['text'])
            docs[0]['retrieval_gold_evidence_ids']=['UNKNOWN'];path.write_text(json.dumps(docs))
            with self.assertRaisesRegex(ValueError,'gold IDs'):actual_document_input(profile(),calibration(),'C',path,COUNTER)

if __name__=='__main__':unittest.main()
