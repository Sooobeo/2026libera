"""Publish a new preparation record after both development diagnoses are audited.

No model calls, changes to raw runs, or approval of main execution occur here.
"""
from pathlib import Path
from html import escape
from decimal import Decimal
import copy
import hashlib
import json
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
V46='data/local_sector_runtime/feedback_diagnostic_v46_20261018'
V47='data/local_sector_runtime/plan_execute_diagnostic_v47_20261018'
REVIEWS={
    '4.6':['research/v46_feedback_diagnostic_round1_20261018.json',
           'research/v46_priority1_round2_20261018.json','research/v46_priority1_round3_20261018.json'],
    '4.7':['research/v47_plan_execute_round1_20261018.json',
           'research/v47_priority1_round2_20261018.json','research/v47_priority1_round3_20261018.json']}
NAMES={'plan':'plan/LIBERA_실험계획_v{version}_20261018.html',
       'paper':'paper/LIBERA_텀페이퍼_초안_v{version}_20261018.html',
       'config':'plan/LIBERA_실험설정_v{version}_20261018.json'}


def read(path):return json.loads((ROOT/path).read_text(encoding='utf-8-sig'))
def ref(path):return {'path':path,'sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest()}
def add(node,markup):
    for child in list(BeautifulSoup(markup,'html.parser').contents):node.append(child)
def replace(node,markup):
    for child in list(BeautifulSoup(markup,'html.parser').contents):node.insert_before(child)
    node.decompose()
def link(path,label):return f'<a href="../{escape(path,quote=True)}">{escape(label)}</a>'


def main():
    bibliography_path='research/v47_added_bibliography_v2_20261018.json'
    bibliography=read(bibliography_path)
    for row in bibliography['source_files']:
        if ref(row['path'])['sha256']!=row['sha256']:raise ValueError('Bibliography primary source changed')
    summaries={'4.6':read(V46+'/summary.json'),'4.7':read(V47+'/summary.json')}
    audits={v:[read(p) for p in paths] for v,paths in REVIEWS.items()}
    for v,rows in audits.items():
        if len(rows)!=3 or {r['round'] for r in rows}!={1,2,3}:
            raise ValueError('Three separately identified reviews required')
        for r in rows:
            if r.get('audit_completed') is not True:
                raise ValueError('Cannot present an unfinished audit as completed')
            for item in r['source_files']:
                path=Path(item['path']);path=path if path.is_absolute() else ROOT/path
                if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                    raise ValueError('Audited source changed: '+str(path))
            run=V46 if v=='4.6' else V47
            if r.get('phase')!='priority1' or r.get('run_dir')!=run:
                raise ValueError('Audit scope does not identify this diagnostic')
            required=['summary.json','revision_record.json']+(['plan_record.json'] if v=='4.7' else [])
            source_refs={str((Path(item['path']) if Path(item['path']).is_absolute() else ROOT/item['path']).resolve()):item['sha256']
                         for item in r['source_files']}
            for name in required:
                if source_refs.get(str((ROOT/run/name).resolve()))!=ref(run+'/'+name)['sha256']:
                    raise ValueError('Audits must share the exact settled diagnostic records')
    if any(s['main_model_calls']!=0 for s in summaries.values()):raise ValueError('Main run forbidden')
    if all(r['all_passed'] for r in audits['4.7']):
        raise ValueError('Successful diagnostic needs a subsequent-priority document; do not publish the blocked template')
    source={k:NAMES[k].format(version='4.5') for k in NAMES}
    before={k:ref(p) for k,p in source.items()}
    outputs={k:ROOT/NAMES[k].format(version='4.7') for k in NAMES}
    if any(p.exists() for p in outputs.values()):raise FileExistsError('Preserve versioned delivery')
    status='v4.7 개발 진단과 세 차례 검증 완료 · ① 미해결 · ②·③ 구현 보류 · 본실험 0건·미동결'
    rows=[]
    for v,s in summaries.items():
        verdicts=['통과' if r['all_passed'] else '불통과' for r in audits[v]]
        value='미제출' if s.get('raw_sum') is None else f"{Decimal(str(s['raw_sum']))*100:f}%"
        cells=[v,'오류 피드백 후 수정 1회' if v=='4.6' else '계획 1회 → 실행 1회',
               str(s['generation_requests_attempted']),str(s['http_streams_completed']),value,*verdicts]
        rows.append('<tr>'+''.join('<td>'+escape(c)+'</td>' for c in cells)+'</tr>')
    reviews=''.join('<p>v'+v+' '+ ' · '.join(link(p,f'{i}차 검증') for i,p in enumerate(paths,1))+'</p>' for v,paths in REVIEWS.items())
    record=read(V47+'/revision_record.json')
    prior=read(V46+'/revision_record.json')
    old={r['sector_code']:Decimal(str(r['weight'])) for r in prior['raw_proposal']['weights']}
    weights=record['raw_proposal']['weights']
    differences=[f"산업 {r['sector_code']}: {old[r['sector_code']]*100:f}% → {Decimal(str(r['weight']))*100:f}%" for r in weights
                 if Decimal(str(r['weight']))!=old[r['sector_code']]]
    diff_text='; '.join(differences) if differences else '11개 산업 비중이 모두 이전 답변과 동일했다.'
    diagnostic=f'''<section id="diagnostic-v47"><h2>추가 개발 진단: 오류를 알려 주면 실제 배분을 고치는가</h2>
<p>{status}. 이번 추가 호출은 원래 R1/R4 네 단계 비교실험에 포함되지 않는 개발 진단이다. 같은 Fidelity Q2/R1 실패 사례를 반복 사용했으므로 독립 확인 표본이나 본실험 결과로 합산하지 않는다.</p>
<p>v4.5에서 AI는 11개 산업에 돈을 나누어 넣는 답을 제출했지만 합계가 96.5%였다. v4.6에서는 이 답과 실제 계산 오류를 다시 보여 주고 수정하게 했다. AI는 100%로 고쳤다고 설명했으나 모든 비중을 그대로 제출했다. 이어 v4.7에서는 먼저 앞으로 어떻게 고칠지를 쓰게 하고, 그 계획을 읽은 다음 호출에서 최종 비중을 직접 제출하게 했다. 프로그램은 어느 산업에 얼마를 더 넣을지 정해 주지 않았으며, 비중을 정규화하거나 남는 금액을 현금으로 보충하지 않았다.</p>
<p>계획의 weights=[]는 배분 미제출이다. 이를 합계 0%인 포트폴리오나 산술 통과로 세지 않는다. 실제 포트폴리오 판정은 실행 호출의 11개 비중에만 적용한다. 계획과 실행이 분리됐다는 사실만으로 모델의 수정 능력이 개선됐다고 해석하지 않는다.</p>
<div class="table-wrap"><table><thead><tr><th>버전</th><th>범위</th><th>생성 요청</th><th>완료 응답</th><th>최종 합계</th><th>1차 기록 검증</th><th>2차 산술 검증</th><th>3차 수정 설명 검증</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>v4.7에서 관측한 실제 변경: {escape(diff_text)}</p>
<p>상세 판정은 아래 원문 감사에 남겼다. 1차의 통과는 입력·응답·계산 기록이 보존됐다는 뜻이며, 모델 답변의 정답 판정이 아니다. 2차는 실행기와 분리한 정확 산술, 3차는 계획·최종 변경·수정 주장의 일치를 검토했다. 세 검증은 분담 자체 검토이며 독립 사람 검토를 대체하지 않는다.</p>
{reviews}<p>{link(V46+'/summary.json','v4.6 실행 요약')} · {link(V47+'/summary.json','v4.7 실행 요약')} · {link(V47+'/plan_record.json','계획 원문 기록')} · {link(V47+'/revision_record.json','최종 원안과 계산')} · {link('research/progress_20261018.html','전체 진행 기록')}</p></section>'''
    method='''<h3 id="methods-v47">추가 진단의 논문 근거와 적용 범위</h3>
<p><a href="https://arxiv.org/html/2607.15388v1">Precise but Uncoupled §3.3·부록 I.1</a>의 계획자·실행자 구분을 참고했다. 여기서는 계획 1회와 실행 1회로 범위를 제한했으며, 원 논문의 전체 검토·반복 체계를 재현한 것은 아니다. 두 호출은 이 개발 진단의 범위이지 논문이 증명한 최적 횟수가 아니다. 과제·문맥 배치·호출 수가 함께 달라져 그 개별 효과를 식별할 수 없다.</p>
<p>이전 실제 계산 결과와 관측된 비중 변화량을 제공하는 방식은 <a href="https://arxiv.org/html/2606.27757v1">기호 검증 피드백 기반 계획 수정 §III-B</a>의 방법을 다른 과제로 옮긴 것이다. <a href="https://arxiv.org/html/2609.25192v1">FinFIRST §§2.2.2–2.3</a>는 입력·출처·계산·결론을 추적하는 평가의 근거다. 이 논문들이 현재 모델과 산업 배분 과제의 성공을 보장한다고 주장하지 않는다.</p>
<p>모델·공개 자료·시장 수치·샘플링·문맥·출력 상한·호출별 시간 제한은 v4.5에서 유지했다. 변경한 것은 별도 진단의 과제, 피드백 구성, 계획·실행 역할이다. 계획의 빈 비중 조건과 두 호출 예산은 명시한 구현 선택이다. 모든 수치를 논문에서 그대로 가져왔다고 표현하지 않는다. <a href="../research/v47_planner_executor_reference_20261018.html">선택한 방법의 근거와 한계</a> 및 <a href="../research/v46_feedback_basis_20261018.html">앞선 수정 진단 근거</a>를 별도로 보존한다.</p>'''
    remaining='''<section id="candidates"><h2>남은 우선순위와 선택해야 할 부분</h2>
<p><strong>① 계산 피드백에 따라 실제 배분을 고치는 문제는 미해결이다.</strong> 사전에 정한 진단 예산이 끝났으므로 같은 실패 사례를 통과할 때까지 재생성하지 않는다. 다른 방법·모델로 변경할 경우 근거, 변경 범위, 호출 예산과 평가 기준을 먼저 기록하고 별도 개발 진단으로 검증해야 한다. 원래 네 단계 전체 예비실험을 대체하지 않는다.</p>
<p>①에서 다음에 선택할 부분은 <strong>오류를 받은 뒤의 수정 절차</strong>다. 후보 A는 실제 계산 오류와 전후 변화량을 매번 확인하는 유한 반복으로, 현재 문제에 가장 가까운 반복 수정 선례가 있다. 후보 C는 설명·계산을 비중보다 먼저 출력하는 방식이지만 다른 모델의 수학 과제에서 가져온 근거여서 직접성이 더 약하다. 이번에 시행한 B는 계획과 실행을 나누는 진단이었으며 통과하지 못했다. <a href="../research/v47_priority1_revision_options_20261018.html">실행 전에 작성한 A·B·C 비교와 근거</a>를 보존한다. A나 C의 효과는 이 과제에서 아직 검증하지 않았고 자동으로 이어서 실행하지 않았다.</p>
<div class="table-wrap"><table><thead><tr><th>순서</th><th>실험의 어느 부분인가</th><th>현재 상태와 근거 후보</th></tr></thead><tbody>
<tr><td>② 수치와 설명</td><td>모델이 시장 수치·비중 차이·계산 결과를 설명하는 부분</td><td>구현 미착수. 숫자마다 대상·시점·단위·출처를 붙이고, 검증 가능한 수치 주장과 자유 설명을 나누는 방식이 후보이다. Reasoning Externalization v2와 FinFIRST를 검토했다. 자유 설명까지 자동 인증하는 방법으로 과장하지 않는다.</td></tr>
<tr><td>③ 기관 근거와 전략</td><td>기관 전망의 해석이 대안·최종 비중과 연결되는 부분</td><td>구현 미착수. 사실의 정확성과 전략의 일관성을 따로 평가하는 E2A-Bench 및 대안 해석을 기록하는 FundaPod가 후보이다. Overweight를 특정 정답 비중으로 바꾸거나 임의 위험회피 계수를 넣지 않는다.</td></tr>
<tr><td>④ 전체 예비실험</td><td>Fidelity·UBS × 자료 제공 시점 R1·R4 비교</td><td>앞 단계 통과 후 최종 조건에서 Fidelity Q2/R1을 포함한 예비 4사례 전체를 실행·검증한다. 기존 사례는 개발에 노출됐다는 사실을 유지하며 독립 확인 표본으로 바꾸지 않는다. 실행기·노출 시점·전체 이력을 검증하고 기존 개발 결과를 동일 조건의 반복으로 합산하지 않는다.</td></tr>
<tr><td>⑤ 본실험 직전</td><td>본실험 입력·평가·조건 고정</td><td>독립 사람의 출처 내용 검토, 실패 포함 분모, 코드·데이터·모델 해시, 분석 계획을 확정해야 한다. 본실험은 이번 요청에서 실행하지 않는다.</td></tr></tbody></table></div>
<p><a href="../research/priority23_paper_candidates_v2_20261018.html">②·③의 최신 논문별 후보·이유·적용 한계</a>. 이 후보 조사는 구현이나 효과 검증을 완료했다는 뜻이 아니다.</p></section>'''
    docs={}
    for kind in ('plan','paper'):
        soup=BeautifulSoup((ROOT/source[kind]).read_text(encoding='utf-8'),'html.parser')
        for node in soup.select('.status'):node.string=status
        for node in soup.select('.callout'):
            if 'v4.5' in node.get_text():node.string=status
        for node in soup.select('.eyebrow'):node.string=node.get_text().replace('4.5','4.7')
        if soup.title:soup.title.string=soup.title.get_text().replace('v4.5','v4.7')
        add(soup.find(id='design'),method)
        method_section=soup.find(id='methods-v47')
        method_labels={'2607.15388v1':'Yang 등(2026), ',
                       '2606.27757v1':'Zhang 등(2026), ',
                       '2609.25192v1':'W. Wang 등(2026), '}
        for node in method_section.next_siblings:
            if getattr(node,'name',None)=='h3':break
            if not hasattr(node,'find_all'):continue
            for a in node.find_all('a',href=True):
                for key,label in method_labels.items():
                    if key in a['href']:a.string=label+a.get_text()
        old=soup.find(id='runtime-v45')
        for heading in old.find_all('h3'):
            if heading.get_text()=='최종 원안의 산업 비중':heading.string='v4.5 최종 원안의 산업 비중'
        for item in list(BeautifulSoup(diagnostic,'html.parser').contents):old.insert_after(item)
        if soup.find(id='candidates'):replace(soup.find(id='candidates'),remaining)
        else:
            for item in list(BeautifulSoup(remaining,'html.parser').contents):soup.find(id='appendix').insert_before(item)
        candidate=soup.find(id='candidates')
        for node in list(candidate.find_all(string=True)):
            amended=str(node).replace('Reasoning Externalization v2','Kim 등(2026)의 Reasoning Externalization v2')
            amended=amended.replace('E2A-Bench','X. Wang 등(2026)의 E2A-Bench').replace('FundaPod','Zhu 등(2026)의 FundaPod')
            amended=amended.replace('FinFIRST를 검토했다','W. Wang 등(2026)의 FinFIRST를 검토했다')
            if amended!=str(node):node.replace_with(amended)
        references=soup.find(id='references').find('ul')
        for entry in bibliography['entries']:
            note=entry['implementation_limit_note_ko']
            title_note=entry.get('registered_vs_body_title_note')
            if title_note:note+=' '+str(title_note)
            markup=(f'<li id="ref-v47-{escape(entry["id"])}">{escape(entry["apa_authors"])} '
                f'({entry["year"]}). <i>{escape(entry["apa_title_sentence_case"])}</i> '
                f'(Version {entry["version"]}) [Preprint]. arXiv. '
                f'<a href="{escape(entry["url"],quote=True)}">{escape(entry["url"])}</a>'
                f'<span class="refnote">{escape(note)}</span></li>')
            add(references,markup)
        if kind=='paper':
            for item in sorted(references.find_all('li',recursive=False),key=lambda n:n.get_text(' ',strip=True).casefold()):
                references.append(item.extract())
        for node in soup.find_all('strong'):
            if node.get_text().startswith('v4.5 ·'):node.string='v4.7 · 개발 진단의 실패와 본실험의 미실행을 구분한다.'
        conclusion=soup.find(id='conclusion')
        if conclusion:add(conclusion,'<p>'+status+'. 현재 관측은 오류를 인식했다는 설명과 실제 수정 행동을 별도로 검증해야 함을 보여 준다. 기관 간 판단 수렴, 제공 시점의 효과, 투자 성과나 일반적인 모델 우열은 아직 결론낼 수 없다.</p>')
        add(soup.find(id='appendix'),'<p>'+link('research/progress_20261018.html','추가 과정 장부')+'와 v4.6·v4.7의 입력·코드·응답·계산·감사를 보존한다. 생성 전 로컬 등록은 외부 기관이 보증한 사전등록과 구분한다.</p>')
        for paragraph in soup.find(id='appendix').find_all('p'):
            if '나머지 예비 사례를 같은 버전으로' in paragraph.get_text():
                paragraph.string='이번에 반복 사용한 Fidelity Q2/R1은 개발에 노출된 사례이므로 독립 확인 표본이 아니다. 최종 조건에서 이 사례를 포함한 예비 4사례 전체를 다시 실행·검토한 뒤 본과제 입력·조건·평가를 동결해야 한다. 이전 버전의 결과는 개발 이력으로 보존하며 새 조건의 독립 반복으로 합산하지 않는다. 본실험은 이번 요청에서 실행하지 않는다.'
        for a in soup.find_all('a',href=True):
            for template in NAMES.values():a['href']=a['href'].replace(Path(template.format(version='4.5')).name,Path(template.format(version='4.7')).name)
            if a.get_text()=='v4.5 설정과 상태 출처':a.string='v4.7 설정과 상태 출처'
        if soup.footer:soup.footer.string='LIBERA · 2026-10-18 · '+status
        docs[kind]=str(soup)
    config=copy.deepcopy(read(source['config']))
    config.update(protocol_version='4.7',previous_protocol=source['config'],
        status='priority1_unresolved; later_implementation_not_started; main_not_run_not_frozen',
        development_diagnostics={v:{'summary':s,'reviews':[ref(p) for p in REVIEWS[v]]} for v,s in summaries.items()},
        priority_status={'priority1':'unresolved_after_three_reviews','priority2':'literature_only_not_implemented',
                         'priority3':'literature_only_not_implemented','pilot_integration':'pending','main':'prohibited_under_current_request'},
        diagnostic_conditions={'manifest':ref('data/sector_protocol/v47_plan_execute_diagnostic_20261018/manifest.json'),
                               'registration':ref('data/sector_protocol/v47_plan_execute_diagnostic_registration_20261018.json')},
        delivery_provenance={'builder':ref('research/build_sector_revision_v47.py'),'source_documents':before,
                             'added_bibliography':ref(bibliography_path),
                             'model_calls_by_builder':0,'diagnostics_not_four_stage_cases':True})
    config['main']['runtime_policy']='No main execution; original four-stage candidate remains v4.5, separate development diagnostics are v4.6/v4.7.'
    config['main']['pending']=['Resolve priority1 with a separately justified development decision',
        'Priority2 implementation and three reviews','Priority3 implementation and three reviews',
        'Validate all four pilot cases under the final protocol, including the previously exposed Fidelity Q2/R1 development case','Independent human source review',
        'Freeze inputs, evaluation and conditions; do not execute main under current request']
    config['model']['runtime_ready']=False
    config['results']['main_execution_ready']=False
    config['results']['count_scope']='Original v4.5 four-stage case only; v4.6/v4.7 separate development diagnostics in development_diagnostics, never independent replicate cases.'
    if before!={k:ref(p) for k,p in source.items()}:raise ValueError('Previous delivery changed')
    for kind,document in docs.items():outputs[kind].write_text(document,encoding='utf-8')
    outputs['config'].write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'outputs':{k:str(p) for k,p in outputs.items()},'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
