"""Read-only delivery QA after three outcome audits; never approves main work."""
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlsplit,unquote
from datetime import datetime,timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]


def main():
    refs={};checks=[]
    def read(path,json_value=False):
        p=Path(path);p=p if p.is_absolute() else ROOT/p
        raw=p.read_bytes();refs[p.relative_to(ROOT).as_posix()]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw.decode('utf-8-sig')) if json_value else raw.decode('utf-8')
    def check(name,okay,detail=None):checks.append({'check':name,'status':'pass' if okay else 'fail','detail':detail})
    config=read('plan/LIBERA_실험설정_v4.7_20261018.json',True)
    bibliography=read(config['delivery_provenance']['added_bibliography']['path'],True)
    for kind,name in [('plan','LIBERA_실험계획_v4.7_20261018.html'),('paper','LIBERA_텀페이퍼_초안_v4.7_20261018.html')]:
        path=ROOT/kind/name;raw=read(path);doc=BeautifulSoup(raw,'html.parser');text=doc.get_text(' ',strip=True)
        ids=[n['id'] for n in doc.select('[id]')]
        check(kind+':unique_ids',len(ids)==len(set(ids)))
        broken=[]
        for a in doc.select('a[href]'):
            parsed=urlsplit(a['href'])
            if parsed.scheme or parsed.netloc:continue
            target=(path.parent/unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_file():broken.append(a['href']);continue
            if parsed.fragment and target.suffix.lower()=='.html':
                td=doc if target==path else BeautifulSoup(target.read_text(encoding='utf-8'),'html.parser')
                if not td.find(id=unquote(parsed.fragment)):broken.append(a['href'])
        check(kind+':local_links',not broken,broken)
        status=doc.select('.status') or doc.select('.callout')
        check(kind+':current_state',bool(status) and all('① 미해결' in n.get_text() and '본실험 0건·미동결' in n.get_text() for n in status))
        check(kind+':no_replacement_character','\ufffd' not in raw)
        section=doc.find(id='diagnostic-v47');st=section.get_text(' ',strip=True) if section else ''
        check(kind+':diagnosis_scoped',all(x in st for x in ('96.5%','네 단계 비교실험에 포함되지','독립 확인 표본','비중을 정규화')))
        table=section.find('table') if section else None
        rows=[[cell.get_text(' ',strip=True) for cell in r.find_all(['td','th'])] for r in table.find_all('tr')] if table else []
        check(kind+':exact_outcome_table',rows[1:]==[
            ['4.6','오류 피드백 후 수정 1회','1','1','96.500%','통과','불통과','불통과'],
            ['4.7','계획 1회 → 실행 1회','2','2','97.500%','통과','불통과','불통과']])
        check(kind+':reviews_linked',all(p in raw for d in config['development_diagnostics'].values() for p in [r['path'] for r in d['reviews']]))
        check(kind+':later_steps_unstarted','②·③ 구현 보류' in text and '후보 A' in text and '구현 미착수' in text)
        check(kind+':limits','독립 사람 검토를 대체하지 않는다' in text and '최적 횟수가 아니다' in text and '본실험은 이번 요청에서 실행하지 않는다' in text)
        for entry in bibliography['entries']:
            citation=doc.find(id='ref-v47-'+entry['id'])
            ct=citation.get_text(' ',strip=True) if citation else ''
            check(kind+':bibliography_'+entry['id'],bool(citation) and entry['apa_authors'] in ct
                  and entry['apa_title_sentence_case'] in ct and entry['implementation_limit_note_ko'] in ct
                  and bool(citation.find('a',href=entry['url'])))
        check(kind+':distinct_wang_authors','W. Wang 등(2026)' in text and 'X. Wang 등(2026)' in text)
    check('config:blocked_state',config['protocol_version']=='4.7' and config['priority_status']['priority1']=='unresolved_after_three_reviews'
          and config['priority_status']['priority2']=='literature_only_not_implemented' and config['priority_status']['priority3']=='literature_only_not_implemented')
    check('config:main_not_ready',config['results']['main_completed_calls']==0 and config['results']['main_execution_ready'] is False
          and config['model']['runtime_ready'] is False and config['observed_execution']['main']['frozen'] is False)
    check('config:original_workflow_preserved',config['execution_conditions']['protocol_version']=='4.5'
          and config['results']['pilot_completed_workflow_stages']==4 and config['results']['pilot_completed_calls']==4)
    refrows=list(config['delivery_provenance']['source_documents'].values())+[config['delivery_provenance']['builder']]
    refrows+=[config['delivery_provenance']['added_bibliography']]+bibliography['source_files']
    for entry in bibliography['entries']:
        original=next(r for r in entry['source_files'] if r['path'].endswith('_abs.html'))
        source=BeautifulSoup(read(original['path']),'html.parser')
        authors=[n['content'] for n in source.select('meta[name="citation_author"]')]
        title=source.select_one('meta[name="citation_title"]')['content']
        check('primary_metadata:'+entry['id'],authors==[a['original_citation_author'] for a in entry['authors']]
              and title==entry['title_registered'])
    check('bibliography_labels_preserved',all('?' not in e['body_author_year_label_ko']
          and '?' not in e['implementation_limit_note_ko'] for e in bibliography['entries']))
    refrows+=list(config['diagnostic_conditions'].values())
    for v,d in config['development_diagnostics'].items():
        folder='feedback_diagnostic_v46_20261018' if v=='4.6' else 'plan_execute_diagnostic_v47_20261018'
        actual=read('data/local_sector_runtime/'+folder+'/summary.json',True)
        check('config:raw_summary_'+v,d['summary']==actual)
        refrows+=d['reviews']
        for row in d['reviews']:
            audit=read(row['path'],True)
            refrows+=audit['source_files']
            check('review_completed:'+row['path'],audit['audit_completed'] is True and audit['not_observed_checks']==[])
    wrong=[]
    for row in refrows:
        p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=row['sha256']:wrong.append(str(p))
        refs[p.relative_to(ROOT).as_posix()]=digest
    check('all_source_hashes',not wrong,{'records':len(refrows),'changed':wrong})
    read(Path(__file__))
    failed=[c['check'] for c in checks if c['status']=='fail']
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'round':1,'phase':'delivery_record',
        'scope':'Truthful document counts, state, links and preserved provenance; not priority1 success or main approval.',
        'audit_completed':True,'all_passed':not failed,'checks':checks,'failed_checks':failed,
        'source_files':[{'path':p,'sha256':h} for p,h in refs.items()], 'model_calls':0,'main_ready':False,
        'qa_correction':{'prior_reports':['research/v47_delivery_round1_20261018.json','research/v47_delivery_round1_v2_20261018.json'],
            'reason':'The first report had a literal 97.5% versus equivalent 97.500% display mismatch, corrected by v2 without changing the exact table check. This final delivery adds six source-verified bibliography entries; the pre-bibliography documents are archived separately. No experimental output or outcome criterion changed.'}}
    out=ROOT/'research/v47_delivery_round1_v3_20261018.json'
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'all_passed':not failed,'checks':len(checks),'failed_checks':failed,'report':str(out)}))
    return int(bool(failed))


if __name__=='__main__':raise SystemExit(main())
