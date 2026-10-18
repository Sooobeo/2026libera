"""Offline evaluator. Never imported by the online model runner."""
import argparse
import json
from pathlib import Path
from sector_engine import score_response, paired_workflow_distances, parse_response
from run_sector_workflow import ROOT, OUT, MARKET, read, write, verify_freeze

def evaluate(run_dir):
    run_dir=Path(run_dir); metadata=read(run_dir/'runtime.json'); split=metadata['split']
    if split=='main':verify_freeze(read(run_dir/'main_freeze.json'))
    golds=[json.loads(x) for x in (ROOT/'data/sector_documents/evaluator_only/reference_annotations.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    sources=[x for x in read(OUT/'cases.json') if x['split']==split]
    gold_by_id={g['source_id']:g for g in golds}; records=[]; responses={}
    for case in sources:
        folder=run_dir/case['case_id']; value=None
        status='not_started'
        if folder.exists():
            status='attempted_without_valid_final'
            if (folder/'final.json').exists():
                parsed=parse_response((folder/'final.json').read_text(encoding='utf-8'))
                if parsed['ok']:value=parsed['value'];status='completed'
        scored=score_response(value,gold_by_id[case['source_id']],read(MARKET))
        records.append({'case_id':case['case_id'],'arm':case['arm'],'status':status,'score':scored})
        responses.setdefault(case['source_id'],{})[case['arm']]=value
    paired=paired_workflow_distances(responses,tuple(responses))
    arms={arm:{'correct':sum(x['score']['primary_rating']['correct'] for x in records if x['arm']==arm),
               'expected':sum(x['score']['primary_rating']['expected'] for x in records if x['arm']==arm)} for arm in ('R1','R4')}
    result={'split':split,'records':records,'predeclared_roster_by_arm':arms,'distances':paired,
            'all_planned_runs_attempted':all(x['status']!='not_started' for x in records),
            'all_planned_runs_completed':all(x['status']=='completed' for x in records),
            'missing_rule':'All prespecified cases retained; not-started distinguished from attempted failures. Do not treat unexecuted jobs as observed AI errors.',
            'semantic_review':'pending; citation IDs do not validate the meaning of allocation reasons',
            'inference':'Descriptive case study; sectors and repeated arms are not independent institutional samples.'}
    write(run_dir/'offline_scores.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_dir',type=Path)
    a=p.parse_args();result=evaluate(a.run_dir)
    print(json.dumps({'split':result['split'],'by_arm':result['predeclared_roster_by_arm']},ensure_ascii=False))
