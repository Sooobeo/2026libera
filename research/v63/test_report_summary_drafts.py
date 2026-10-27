"""Pure report-draft checks with synthetic facts; no real report/model actions."""
import hashlib,json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]

def load_draft(name):
    path=ROOT/'data/v63_20261027/audit'/name;ns={}
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),ns)
    return ns


def main_fixture():
    diagnostics=[{'identity':['synthetic',f'F{j%4+1:02d}',arm,j//4],
        'raw_valid':True,'fallback':False} for arm in ('R0','R1','R2','R3','C-context') for j in range(480)]
    claims={'H2':{'p':.001,'p_holm':.005,'reject':True}}
    for a,b in [('R1','R2'),('R1','R3'),('R2','R3')]:
        claims['H3_'+a+'_'+b]={'p':.002,'p_holm':.01,'reject':True,
            'directions':{a+'_better':{'p':.001},b+'_better':{'p':1.}}}
    return {'trajectory_diagnostics':diagnostics,'inference':{'claims':claims}}


def test_recommendation_withheld_when_failures_increase_despite_joint_rejection():
    fn=load_draft('final_report_supplement_code_draft.txt')['recommendation_rows'];main=main_fixture()
    row=next(r for r in main['trajectory_diagnostics'] if r['identity'][2]=='R1');row.update(raw_valid=False,fallback=True)
    result=fn(main)
    assert '권고 보류' in result[0][-1] and '증가' in result[0][-1]
    assert result[0][1]=='R1 vs R0' and '0.21%' in result[0][3]


def test_h3_direction_comes_from_adjusted_iut_not_failure_rate_selection():
    fn=load_draft('final_report_supplement_code_draft.txt')['recommendation_rows'];main=main_fixture()
    claim=main['inference']['claims']['H3_R1_R3'];claim['directions']={'R1_better':{'p':1.},'R3_better':{'p':.001}}
    result=fn(main);row=next(r for r in result if r[0]=='H3_R1_R3')
    assert row[1]=='R3 vs R1' and '조건 충족' in row[-1]
    claim['p']=.001
    with pytest.raises(ValueError):fn(main)


def test_missing_raw_diagnostics_never_become_zero_failure():
    fn=load_draft('final_report_supplement_code_draft.txt')['recommendation_rows'];main=main_fixture()
    main['trajectory_diagnostics'].pop()
    with pytest.raises(ValueError):fn(main)


def source_fixture(tmp_path,cases):
    rows=[];facts=[]
    for fund,arm,stage_rows in cases:
        identity=['A',fund,arm,1];stages=[]
        for stage,citations in stage_rows:
            raw=[]
            for cited,comparison in citations:
                raw.append(cited)
                facts.append({'identity':identity,'stage':stage,'evidence_id':cited['evidence_id'],
                    'source_fact_scored':True,'literal_field_matches':{'value':False},
                    'correct_fund_attribution':True,'publication_within_cutoff':True,'correct_period':True,**comparison})
            stages.append({'stage':stage,'raw_output':{'evidence':raw}})
        trace={'fund_id':fund,'arm':arm,'engineering_only':False,'stages':stages,'synthetic_test_fixture_only':True}
        path=tmp_path/(fund+'_'+arm+'.json');path.write_text(json.dumps(trace),encoding='utf-8')
        rows.append({'identity':identity,'source':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'synthetic':False}})
    return {'status':'synthetic_test_fixture_only','rows':rows,'fact_checks':facts}


def cite(value=999,**extra):return {'evidence_id':'COMMON/example','value':value,'unit':'percent','date':'2026-03-18',**extra}


def test_exact_mismatch_shared_across_funds_and_persistent_across_stages(tmp_path):
    ns=load_draft('shared_source_mismatch_code_draft.txt')
    data=source_fixture(tmp_path,[('F01','R1',[(1,[(cite(),{})]),(2,[(cite(),{})])]),
        ('F02','R3',[(3,[(cite(),{})])])])
    result=ns['shared_source_mismatch_candidates'](data,tmp_path);pattern=result['patterns'][0]
    assert result['repeated_candidate_patterns']==1 and pattern['distinct_trajectories']==2
    assert pattern['distinct_locations']==3 and pattern['within_trajectory_stage_persistence'] and pattern['across_funds']
    assert result['semantic_error_count'] is None and result['economic_error_count'] is None
    assert '의미·경제적 오류 확정 수는 미산출' in ns['shared_source_mismatch_html'](result)
    json.dumps(result) # output is serializable; no sets leak into report artifacts


def test_review_flags_and_unscored_facts_do_not_become_confirmed_mismatches(tmp_path):
    fn=load_draft('shared_source_mismatch_code_draft.txt')['shared_source_mismatch_candidates']
    data=source_fixture(tmp_path,[('F01','R1',[(1,[(cite(),{'literal_field_matches':{'value':True},'requires_semantic_review':True})])]),
        ('F02','R3',[(3,[(cite(),{'source_fact_scored':False})])])])
    result=fn(data,tmp_path)
    assert result['mechanical_mismatch_candidate_records']==0 and result['repeated_candidate_patterns']==0
    assert result['review_only_records_not_counted_as_mismatches']==1 and result['source_unscored_records']==1


def test_same_id_different_wrong_values_are_not_one_shared_pattern(tmp_path):
    fn=load_draft('shared_source_mismatch_code_draft.txt')['shared_source_mismatch_candidates']
    result=fn(source_fixture(tmp_path,[('F01','R1',[(1,[(cite(100),{})])]),('F02','R3',[(3,[(cite(200),{})])])]),tmp_path)
    assert result['repeated_candidate_patterns']==0 and result['unrepeated_single_location_payload_groups']==2


def test_duplicate_stage_citation_does_not_create_propagation_or_guess_payload(tmp_path):
    fn=load_draft('shared_source_mismatch_code_draft.txt')['shared_source_mismatch_candidates']
    same=source_fixture(tmp_path,[('F01','R1',[(1,[(cite(),{}),(cite(),{})])])])
    result=fn(same,tmp_path)
    assert result['repeated_candidate_patterns']==0 and result['joined_candidate_records']==2
    different=source_fixture(tmp_path,[('F01','R1',[(1,[(cite(100),{}),(cite(200),{})])])])
    result=fn(different,tmp_path)
    assert result['repeated_candidate_patterns']==0 and len(result['unresolved_join_records'])==2


def test_original_trace_hash_drift_is_not_silently_rejoined(tmp_path):
    fn=load_draft('shared_source_mismatch_code_draft.txt')['shared_source_mismatch_candidates']
    data=source_fixture(tmp_path,[('F01','R1',[(1,[(cite(),{})])])]);Path(data['rows'][0]['source']['path']).write_text('{}')
    with pytest.raises(ValueError):fn(data,tmp_path)
