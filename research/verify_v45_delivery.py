"""Read-only document/link/provenance QA; no model access."""
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlsplit, unquote
from datetime import datetime, timezone
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def main():
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    config = read(ROOT / 'plan/LIBERA_실험설정_v4.5_20261018.json')
    checks = []
    def check(name, passed, detail=None):
        checks.append({'check':name,'passed':bool(passed),'detail':detail})
    for kind in ('plan','paper'):
        name = 'LIBERA_실험계획_v4.5_20261018.html' if kind=='plan' else 'LIBERA_텀페이퍼_초안_v4.5_20261018.html'
        path = ROOT / kind / name
        s = BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser')
        ids = [n['id'] for n in s.select('[id]')]
        check(kind+'_unique_ids',len(ids)==len(set(ids)))
        broken=[]
        for a in s.select('a[href]'):
            href=a['href']; u=urlsplit(href)
            if u.scheme or u.netloc: continue
            target=(path.parent/unquote(u.path)).resolve() if u.path else path
            if not target.exists(): broken.append(href); continue
            if u.fragment and target.suffix.lower()=='.html':
                t=s if target==path else BeautifulSoup(target.read_text(encoding='utf-8'),'html.parser')
                if not t.find(id=unquote(u.fragment)): broken.append(href)
        check(kind+'_all_local_links',not broken,broken)
        text=s.get_text(' ',strip=True)
        status_nodes=s.select('.status') or s.select('.callout')
        check(kind+'_current_status',bool(status_nodes) and all('4단계 완료' in n.get_text() and '4/4' in n.get_text() for n in status_nodes))
        check(kind+'_no_encoding_replacement','\ufffd' not in text)
        check(kind+'_reports_numeric_failure','잘못' in text and '193/200' in text and ('0.965' in text or '96.5%' in text))
        check(kind+'_three_audits',all(f'v45_single_case_round{i}_20261018.html' in path.read_text(encoding='utf-8') for i in (1,2,3)))
    check('config_truthful_state',config['protocol_version']=='4.5' and config['results']['pilot_completed_workflow_stages']==4 and config['results']['final_allocation_valid'] is False and config['results']['main_completed_calls']==0)
    for k,row in config['revision_provenance']['source_files'].items():
        check('preserved_v44_'+k,sha(ROOT/row['path'])==row['sha256'])
    refs=[]
    refs+=read(ROOT/'data/sector_protocol/v45_single_case_registration_20261018.json')['reference_files']
    refs+=read(ROOT/'research/v45_single_case_findings_20261018.json')['source_files']
    refs+=read(ROOT/'research/v45_single_case_round1_20261018.json')['sources']
    refs+=read(ROOT/'research/v45_single_case_round2_20261018.json')['source_files']
    refs += [{'path':p,'sha256':v['sha256']} for p,v in read(ROOT/'research/v45_single_case_round3_20261018.json')['evidence_files'].items()]
    wrong=[]
    for row in refs:
        if sha(ROOT/row['path'])!=row['sha256']: wrong.append(row['path'])
    check('all_registered_and_reviewed_hashes',not wrong,{'reference_records':len(refs),'changed':wrong})
    for n in range(1,5):
        actual=read(ROOT/f'data/local_sector_runtime/single_case_v45_20261018/stage{n}_transport/authoritative_body.json')
        check(f'config_request_header_stage{n}',config['execution_conditions']['request_headers_by_stage'][str(n)]=={k:v for k,v in actual.items() if k!='messages'})
    report={'created_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Delivery document QA after the three experimental self-reviews','checks':checks,'all_passed':all(c['passed'] for c in checks),'model_calls':0,
        'qa_correction':{'prior_report':'research/v45_delivery_validation_20261018.json','reason':'The first delivery check assumed both documents used a .status class and the literal 96.5%. The plan uses .callout and both documents disclose 193/200 with 0.965. The verifier now accepts the actual layouts and equivalent exact numeric representation. No experimental criterion, model response or generated document was changed.'}}
    p=ROOT/'research/v45_delivery_validation_v2_20261018.json'
    with p.open('x',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'all_passed':report['all_passed'],'checks':len(checks),'failures':[x for x in checks if not x['passed']],'report':str(p)},ensure_ascii=False))
    if not report['all_passed']: raise SystemExit(1)


if __name__ == '__main__': main()
