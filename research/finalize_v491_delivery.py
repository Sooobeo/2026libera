"""Bind completed design reviews; does not freeze or execute the experiment."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from build_v491_context_plan import ROOT, PLAN, PAPER, METHOD, CONFIG, OUT, CONTEXT, read, ref, save
from research_progress_log import read_verified


def embedded_refs(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            yield value
        for item in value.values(): yield from embedded_refs(item)
    elif isinstance(value,list):
        for item in value: yield from embedded_refs(item)


def main():
    checks=[]
    for i in (1,2,3):
        path=f'research/v491_validation_round{i}_20261019'+('_r2' if i in (1,2) else '')+'.json'
        value=read(path)
        if value['status']!='PASS':raise ValueError('Review did not pass: '+path)
        for item in embedded_refs(value):
            p=ROOT/item['path']
            if not p.is_file() or ref(p)['sha256']!=item['sha256']:
                raise ValueError('Stale review reference: '+item['path'])
        checks.append({'review':ref(path),'status':'PASS'})
    for value in (read(CONFIG),read(OUT/'prepared/preparation_manifest.json'),read('research/artifacts/v491_visual_20261019/r2/visual_review.json')):
        for item in embedded_refs(value):
            if ref(item['path'])['sha256']!=item['sha256']:
                raise ValueError('Stale input/capture reference: '+item['path'])
    events=read_verified(ROOT/'research/v491_process_20261019.jsonl')
    output=ROOT/'research/v491_handoff_20261019.json'
    for doc in (PLAN,PAPER,METHOD):
        soup=BeautifulSoup(doc.read_text('utf-8'),'html.parser')
        for a in soup.select('a[href]'):
            u=urlparse(a['href'])
            if u.scheme or u.netloc:continue
            target=(doc.parent/unquote(u.path)).resolve() if u.path else doc
            if target==output and not target.exists():continue
            if not target.is_file():raise ValueError('Broken local link: '+a['href'])
            if u.fragment and BeautifulSoup(target.read_text('utf-8'),'html.parser').find(id=unquote(u.fragment)) is None:
                raise ValueError('Broken fragment: '+a['href'])
    files=set()
    for base in (CONTEXT,OUT,ROOT/'research/artifacts/v491_visual_20261019',ROOT/'research/artifacts/v491_review_history_20261019'):
        files.update(p for p in base.rglob('*') if p.is_file())
    files.update(p for p in (ROOT/'research').glob('*v491*') if p.is_file() and p!=output)
    files.update((PLAN,PAPER,METHOD,CONFIG,ROOT/'.gitattributes',ROOT/'.gitignore'))
    status=subprocess.run(['git','status','--porcelain','-uall'],cwd=ROOT,capture_output=True,text=True,check=True)
    if any('tmp/v491_visual' in x for x in status.stdout.splitlines()):raise ValueError('Disposable browser files not ignored')
    handoff={'protocol_version':'4.9.1','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'common_context_design_inputs_paper_and_offline_contract_complete',
        'experiment_frozen':False,'model_calls':0,'pilot_calls':0,'main_calls':0,
        'independent_human_review_completed':False,
        'entrypoints':{'plan':ref(PLAN),'full_term_paper_draft':ref(PAPER),'methods_replacement':ref(METHOD),
                      'configuration':ref(CONFIG),'prepared_messages':ref(OUT/'prepared/preparation_manifest.json')},
        'ordered_reviews':checks,
        'process_chain':{'events':len(events),'last_event_sha256':events[-1]['event_sha256'],'valid':True},
        'exact_delivery_files':[ref(p) for p in sorted(files)],
        'changes':['Explicit new-money US equity sleeve, 12-month judgment horizon, qualitative equity-loss acceptance',
                   'Seven dated official macro facts added identically from D0; release vintage and units preserved',
                   'Prepared eight D0 inputs; source exposure and later exact-history F0 calculation contract wired offline',
                   'Context use evaluation and full pre-experiment term paper synchronized',
                   'Disposable HTML browser profiles ignored; source evidence and previews retained'],
        'reproduce_preparation':['python -B -X utf8 research/build_v491_context_plan.py',
                                'python -B -X utf8 research/prepare_sector_v491.py'],
        'reproduction_note':'Rebuilding reviewed artifacts or modifying code requires new hash-bound review. Commands prepare data only and do not run a model.',
        'remaining_before_main':['Validate live v4.9.1 transport and full retained-history token/memory/backend operation',
                                 'Run and account for the separate four-case pilot without outcome-based selection',
                                 'Complete two separate human source/meaning reviews and reconcile disagreements',
                                 'Freeze exact input/model/evaluation/order/resource ceilings, then execute main'],
        'not_claimed':['An executed experiment','A completed result-bearing submission','Guaranteed valid model portfolios or statistical significance',
                       'An institutional private mandate or whole-client suitability test','12-month realized performance or harmful market-wide homogenization'],
        'visual_scope':'Four screenshots inspected; not a final printed-paper pagination audit',
        'git_scope':'No commit or push of this new design performed in this task; prior cleanup push is separate.'}
    save(output,handoff)
    print(json.dumps({'status':handoff['status'],'ordered_reviews':3,'files':len(files),
                      'handoff':ref(output),'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
