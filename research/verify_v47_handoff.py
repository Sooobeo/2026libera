"""Confirm delivery audits share final documents, without approving failed research."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
from research_progress_log import read_verified

ROOT=Path(__file__).resolve().parents[1]
REPORTS=['research/v47_delivery_round1_v3_20261018.json',
         'research/v47_delivery_round2_20261018.json','research/v47_delivery_round3_20261018.json']
DOCS=['plan/LIBERA_실험계획_v4.7_20261018.html','paper/LIBERA_텀페이퍼_초안_v4.7_20261018.html',
      'plan/LIBERA_실험설정_v4.7_20261018.json']


def ref(path):
    p=Path(path);p=p if p.is_absolute() else ROOT/p
    return {'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    rows=[json.loads((ROOT/p).read_text(encoding='utf-8-sig')) for p in REPORTS]
    if {r['round'] for r in rows}!={1,2,3}:raise ValueError('Three rounds required')
    counts=[]
    for report in rows:
        if report['audit_completed'] is not True or report['all_passed'] is not True or report['failed_checks']:
            raise ValueError('Document review is incomplete or failed')
        if not report['checks'] or any(c['status']!='pass' for c in report['checks']):raise ValueError('Empty or failed checks')
        refs={}
        for item in report['source_files']:
            actual=ref(item['path'])
            if actual['sha256']!=item['sha256']:raise ValueError('Reviewed file changed: '+item['path'])
            refs[actual['path']]=actual['sha256']
        if any(refs.get(p)!=ref(p)['sha256'] for p in DOCS):raise ValueError('Reviews do not share the final documents')
        counts.append(len(report['checks']))
    events=read_verified()
    if any(e['status']=='phase_accepted' for e in events):raise ValueError('Unexpected phase acceptance')
    for event in events:
        for item in event['reference_files']:
            if ref(item['path'])['sha256']!=item['sha256']:raise ValueError('Ledger reference changed')
    config=json.loads((ROOT/DOCS[2]).read_text(encoding='utf-8'))
    if config['results']['main_execution_ready'] or config['results']['main_completed_calls']!=0:
        raise ValueError('No main approval')
    tests='research/evidence/v47_posthoc_offline_tests_20261018/summary.json'
    snapshot='research/evidence/v47_handoff_20261018/progress_snapshot.jsonl'
    with (ROOT/snapshot).open('xb') as stream:stream.write((ROOT/'research/progress_20261018.jsonl').read_bytes())
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'delivery_reviews_completed':3,'delivery_reviews_all_passed':True,'check_counts_by_round':counts,
        'review_reports':[ref(p) for p in REPORTS],'documents':[ref(p) for p in DOCS],
        'process_ledger_snapshot':ref(snapshot),'process_events_verified':len(events),
        'posthoc_test_record':ref(tests),'bibliography':ref('research/v47_added_bibliography_v2_20261018.json'),
        'diagnostic_result':'Both v4.6 and v4.7 priority1 diagnoses failed their required numerical and semantic criteria.',
        'priority1_passed':False,'priority2_implementation_started':False,'priority3_implementation_started':False,
        'main_model_calls':0,'main_ready':False,'main_frozen':False,
        'scope':'Document handoff and historical process snapshot only; not a successful experimental outcome.',
        'next_work':['Choose and justify a new bounded priority1 method or model decision; no until-pass reroll.',
                     'After the prerequisite gate: implement and review priorities2 and3.',
                     'Validate all four pilot cases under final conditions, retaining prior development exposure.',
                     'Independent substantive human review and main-condition freeze. Main execution is outside this request.']}
    out=ROOT/'research/v47_handoff_20261018.json'
    with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'delivery_reviews_passed':True,'checks':counts,'priority1_passed':False,'main_ready':False,'output':str(out)}))


if __name__=='__main__':main()
