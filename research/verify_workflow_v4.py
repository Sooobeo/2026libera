"""Mechanical checks for offline preparation and scoring, using labelled fixtures.

Synthetic reference answers are created only in a temporary directory. They are
not AI observations and are never installed as research results.
"""
from pathlib import Path
import hashlib
import json
import tempfile
import numpy as np
from bs4 import BeautifulSoup
import prepare_workflow_v4 as wf

ROOT=Path(__file__).resolve().parents[1]

def main(round_number=1):
    cases=wf.read_jsonl(wf.CASE_PATH)
    by_id={c['case_id']:c for c in cases}
    runs=wf.read_jsonl(wf.OUT/'runs.jsonl')
    checks=[]
    # Recompute every current input directly from the public monthly table,
    # independently of the legacy Salcher-reference and new optimizer builders.
    raw=json.loads((ROOT/'data/french/monthly_returns.json').read_text(encoding='utf-8'))
    ff=raw['datasets']['FF12'];rf=raw['risk_free']
    industry={d:np.asarray(v,dtype=float) for d,v in zip(ff['dates'],ff['value_weighted_total_returns'])}
    riskfree={d:float(v[0] if isinstance(v,list) else v) for d,v in zip(rf['dates'],rf['values'])}
    max_mean_error=0.;max_cov_error=0.
    for case in cases:
        market=case['model_visible']['public_market_data']
        training=market['training_window']
        dates=[d for d in ff['dates'] if training['start']<=d<=training['end']]
        assert len(dates)==60
        excess=np.stack([industry[d]-riskfree[d] for d in dates])
        mu=excess.mean(axis=0);cov=np.cov(excess,rowvar=False,ddof=1)
        max_mean_error=max(max_mean_error,float(np.max(np.abs(mu-np.array(market['mean_excess_return'])))))
        max_cov_error=max(max_cov_error,float(np.max(np.abs(cov-np.array(market['sample_covariance_ddof_1'])))))
    assert max_mean_error<1e-15 and max_cov_error<1e-15
    checks.append({'check':'independent recomputation of every training mean/covariance from monthly FF12 table and matched RF','passed':True,'cases':1875,'max_mean_error':max_mean_error,'max_covariance_error':max_cov_error})
    with tempfile.TemporaryDirectory(prefix='libera_v4_evaluator_fixture_') as tmp:
        tmp=Path(tmp)
        rows=[]
        for run in runs:
            case=by_id[run['runner_only']['case_id']]
            gamma=case['model_visible']['institution_mandate']['gamma']
            obj={'weights':case['evaluator_only']['reference_weights'],'mandate_used_gamma':gamma,'mandate_evidence_id':'MANDATE','explanation':'SYNTHETIC ORACLE FIXTURE, NOT AN AI RESPONSE'}
            rows.append({'run_id':run['run_id'],'status':'completed','final_text':json.dumps(obj)})
        wf.write_jsonl(tmp/'fixture.jsonl',rows)
        wf.evaluate(tmp/'fixture.jsonl',tmp/'evaluation.json')
        result=json.loads((tmp/'evaluation.json').read_text(encoding='utf-8'))
        assert len(result['individual_records'])==5625
        assert all(x['valid'] and abs(x['utility_regret_direct'])<1e-14 for x in result['individual_records'])
        assert len(result['paired_individual_differences'])==1875
        assert len(result['paired_pair_differences'])==1875
        assert all(abs(x['R4_minus_R1_pair_response_error'])<1e-14 for x in result['paired_pair_differences'])
        for pair,shared in [('1-3',170),('1-5',83),('3-5',86)]:
            assert result['pair_paired_summaries'][pair+':shared']['four_output_complete_windows']==shared
            assert result['pair_paired_summaries'][pair+':all']['four_output_complete_windows']==625
        checks.append({'check':'all reference-answer fixtures have zero loss and zero paired errors, and certified strata agree','passed':True,'fixture_outputs':5625})
        # One invalid final answer must remove exactly the affected pair contrasts.
        broken=next(i for i,r in enumerate(runs) if r['runner_only']['arm']=='R4' and r['runner_only']['case_id']=='INST-W0001-G1')
        obj=json.loads(rows[broken]['final_text']);obj['weights'][0]=-0.1
        rows[broken]['final_text']=json.dumps(obj)
        wf.write_jsonl(tmp/'broken.jsonl',rows)
        wf.evaluate(tmp/'broken.jsonl',tmp/'broken_evaluation.json')
        invalid=json.loads((tmp/'broken_evaluation.json').read_text(encoding='utf-8'))
        assert invalid['individual_paired_complete_n']==1874
        assert len(invalid['paired_pair_differences'])==1873
        assert invalid['pair_paired_summaries']['1-3:all']['four_output_complete_windows']==624
        assert invalid['pair_paired_summaries']['1-5:all']['four_output_complete_windows']==624
        assert invalid['pair_paired_summaries']['3-5:all']['four_output_complete_windows']==625
        checks.append({'check':'one invalid R4/gamma1 removes exactly one individual and two four-output pair comparisons','passed':True})
        # Adversarial JSON must invalidate its own response, not stop the census.
        extreme=json.loads(rows[0]['final_text']);extreme['mandate_used_gamma']=10**400
        overflow_gamma={'run_id':rows[0]['run_id'],'status':'completed','final_text':json.dumps(extreme)}
        extreme_weights=json.loads(rows[1]['final_text']);extreme_weights['weights'][0]=10**400
        overflow_weights={'run_id':rows[1]['run_id'],'status':'completed','final_text':json.dumps(extreme_weights)}
        nested={'run_id':rows[2]['run_id'],'status':'completed','final_text':'['*2000+'0'+']'*2000}
        wf.write_jsonl(tmp/'adversarial.jsonl',[overflow_gamma,overflow_weights,nested])
        wf.evaluate(tmp/'adversarial.jsonl',tmp/'adversarial_evaluation.json')
        adversarial=json.loads((tmp/'adversarial_evaluation.json').read_text(encoding='utf-8'))
        assert sum(r['status']=='invalid_final' for r in adversarial['individual_records'])==3
        assert sum(r['status']=='missing' for r in adversarial['individual_records'])==5622
        checks.append({'check':'overflowing integer gamma/weights and deeply nested final JSON invalidate only their response','passed':True})
        # Empty observations must not become zero-scored observed performance.
        wf.write_jsonl(tmp/'empty.jsonl',[])
        wf.evaluate(tmp/'empty.jsonl',tmp/'empty_evaluation.json')
        empty=json.loads((tmp/'empty_evaluation.json').read_text(encoding='utf-8'))
        assert empty['supplied_records']==0 and empty['individual_paired_complete_n']==0
        assert all(g['utility_regret']['mean'] is None for g in empty['groups'].values())
        checks.append({'check':'missing responses remain missing; no invented zero performance','passed':True})
        for invalid_json in ['{"weights":[],"weights":[]}','{"weights":[NaN]}','[]','```json\n{}\n```']:
            try:
                wf.strict_object(invalid_json)
            except (ValueError,TypeError):
                pass
            else:
                raise AssertionError('Malformed final JSON accepted')
        checks.append({'check':'duplicate keys, nonfinite numbers, wrong schema and fenced text rejected','passed':True})
    cfg=json.loads(wf.CONFIG_PATH.read_text(encoding='utf-8'))
    manifest=json.loads((wf.OUT/'manifest.json').read_text(encoding='utf-8'))
    assert cfg['main']['institution_cases']==len(cases)
    assert cfg['analysis']['total_response_calls_planned']==sum(len(r['stage_user_contents']) for r in runs)==16875
    assert manifest['protocol_sha256']==wf.digest(wf.CONFIG_PATH.read_bytes())
    assert manifest['case_sha256']==wf.digest(wf.CASE_PATH.read_bytes())
    for filename,sha in manifest['sha256'].items():
        assert sha==wf.digest((wf.OUT/filename).read_bytes())
    checks.append({'check':'case counts, call counts and workflow input hashes agree with final protocol','passed':True})
    files=[ROOT/'plan/LIBERA_실험계획_20261017.html',ROOT/'paper/LIBERA_텀페이퍼_초안_20261017.html']
    unresolved=[]
    for path in files:
        soup=BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
        ids=[el['id'] for el in soup.select('[id]')]
        assert len(ids)==len(set(ids)),f'Duplicate HTML IDs in {path}'
        for a in soup.select('a[href]'):
            href=a['href']
            if href.startswith('#'):
                assert href[1:] in ids,f'Broken anchor {href}'
            elif not href.startswith(('https://','http://')):
                dest=(path.parent/href.split('#')[0]).resolve()
                if not dest.exists():
                    unresolved.append(str(dest.relative_to(ROOT)))
        assert not any(term in soup.get_text() for term in ['주실험 모형·입력 연결 구체화 중','저자 서지는 근거 대조표 확인 후 반영'])
    checks.append({'check':'HTML anchors unique and no stale model-pending or bibliography placeholders','passed':True})
    result={'round':round_number,'scope':'mechanical artifact and evaluator checks; does not replace substantive research review','synthetic_fixtures_not_AI_results':True,'AI_calls':0,'checks':checks,'pending_local_links':sorted(set(unresolved)),'sha256':{str(p.relative_to(ROOT)):wf.digest(p.read_bytes()) for p in files+[wf.CONFIG_PATH,ROOT/'research/prepare_workflow_v4.py',ROOT/'research/prepare_institutional_benchmark.py']}}
    dest=ROOT/f'research/audits/round{round_number}_mechanical.json'
    dest.parent.mkdir(exist_ok=True)
    wf.write_json(dest,result)
    print(json.dumps({'report':str(dest),'checks':len(checks),'all_checks_passed':all(c['passed'] for c in checks),'pending_links':result['pending_local_links']}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,default=1)
    args=p.parse_args();main(args.round)
