"""Build a Korean evidence index without treating engineering checks as research results."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
BUNDLE=ROOT/'실험참고자료_20261027'

def read(rel,default=None):
    p=DATA/rel
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else (default or {})

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def h(value):return html.escape(str(value))

def link(path,title):return f'<a href="../{h(path)}">{h(title)}</a>'

def preparation_schedule_summary(schedule,plan):
    """Fail closed if this preparation-only report is used after real attempts."""
    rows=schedule.get('schedule',[])
    if not rows or schedule.get('model_calls')!=0:
        raise ValueError('A complete zero-call preparation schedule is required.')
    total=sum(row.get('logical_stages',0) for row in rows)
    expected=sum(block['logical_stages'] for block in plan['workload']['original_blocks'])
    if total!=expected or schedule.get('logical_stages')!=total or schedule.get('trajectories')!=len(rows):
        raise ValueError('Schedule totals disagree with the v6.3 protocol.')
    by_block=Counter()
    keys=set()
    for row in rows:
        if row.get('logical_stages')!=3 or row.get('status')!='not_attempted' or row.get('effective_weights') is not None:
            raise ValueError('Preparation report cannot classify attempted trajectories or fallback weights as unattempted.')
        key=tuple(row.get(k) for k in ('block','scenario','fund_id','arm','replicate'))
        if key in keys:raise ValueError('Duplicate planned trajectory.')
        keys.add(key)
        by_block[row['block']]+=3
    names=('B-main','x-replacement','B-development','negative-control','actual-documents')
    expected_blocks={name:block['logical_stages'] for name,block in zip(names,plan['workload']['original_blocks'])}
    if dict(by_block)!=expected_blocks:raise ValueError('Experimental block counts disagree with the protocol.')
    return {'trajectories':len(rows),'logical_stages':total,'model_calls':0,
            'attempted_stages':0,'completed_stages':0,'not_attempted_stages':total,'by_block':dict(by_block)}

def numerical_summary(numerical):
    checks=numerical.get('checks',[])
    passed=sum(row.get('status')=='passed' for row in checks)
    failed=len(checks)-passed
    boundary=numerical.get('minimum_variance_boundary',{}).get('status','not_run')
    boundary_passed=boundary in {'passed','certified','verified'}
    if not checks:
        label='합성 수치 sweep 검증 기록 없음 / 실제 h 검증 대기'
    else:
        label=f'합성 수치 sweep {passed}/{len(checks)} 통과, 미해결 {failed}건'
        label+=' / 최소분산 경계 '+('통과' if boundary_passed else '미해결 또는 미검증')
        label+=' / 실제 h 검증 대기'
    return {'label':label,'sweep_passed':passed,'sweep_failed':failed,'sweep_total':len(checks),
            'minimum_variance_boundary_status':boundary,'all_synthetic_checks_resolved':bool(checks) and failed==0 and boundary_passed,
            'actual_holdings_validation_complete':bool(numerical.get('main_reference_audit_complete'))}

def main():
    planpath=next((ROOT/'plan').glob('*설정_v6.3_20261027.json'))
    plan=json.loads(planpath.read_text(encoding='utf-8-sig'))
    verification=read('audit/engineering_verification.json')
    sources=read('source_manifest.json').get('sources',[])
    readiness=read('readiness.json')
    source_summary=readiness.get('summary',{})
    source_verification=read('official_data_verification.json')
    provenance=read('audit/workspace_provenance.json')
    runtime=read('runtime/runtime_probe.json')
    schedule=read('runtime/planned_schedule.json')
    schedule_counts=preparation_schedule_summary(schedule,plan)
    numerical=read('numerical/verification.json')
    numerical_state=numerical_summary(numerical)
    runtime_verification=read('runtime/engineering_verification.json')
    remote_path='runtime/remote_runtime_inventory.json'
    if not (DATA/remote_path).is_file() and (DATA/'remote_runtime_inventory.json').is_file():
        remote_path='remote_runtime_inventory.json'
    remote_runtime=read(remote_path)
    remote_summary=remote_runtime.get('summary_ko','원격 Proxmox 실행 환경은 별도로 확인 중입니다.')
    if remote_runtime and 'summary_ko' not in remote_runtime:
        remote_summary='원격 실행 환경 점검 기록이 저장되었습니다. 모델·토크나이저의 최종 동결 여부는 상세 기록을 확인합니다.'
    runtime_test_label=(f"검색·실행기·HTTP 연결기 테스트 {runtime_verification.get('tests_run',0)}개 통과"
                        if runtime_verification.get('success') is True else '합성 상태기계·검색 테스트 확인 필요')
    adapter_test=next((row for row in verification.get('suites',[]) if row.get('suite')=='research.v63.test_ollama_transport'),{})
    adapter_label=('Ollama 0.35.1 adapter 후보·모의 HTTP 검증 통과 / 실제 서버·수치도구 통합 미검증'
                   if adapter_test.get('exit_code')==0 and adapter_test.get('tests',0)>0
                   else 'Ollama adapter 후보 구현 / 모의 HTTP·실 서버 통합 검증 기록 확인 필요')
    live_engineering_calls=remote_runtime.get('live_engineering_model_calls',0)
    if not isinstance(live_engineering_calls,int) or live_engineering_calls<0:
        raise ValueError('Invalid separately recorded live engineering call count.')
    gate_rows=[
        ('source_corpus','공식 전체 원문과 발행시점','미완료','readiness.json'),
        ('holdings_sic','전체 보유·SIC 90%·NAV·적용 제약','미완료','readiness.json'),
        ('human_audit','전 펀드 독립된 두 사람의 감사','미완료','human_audit/index.html'),
        ('numerics','B 생성기·사후분포·분산상한 기준해',numerical_state['label'],'numerical/verification.json'),
        ('retrieval','실제 BM25와 근거 노출 경계',runtime_test_label+' / 실제 모델 토크나이저 대기','runtime/engineering_verification.json'),
        ('runtime','3단계·5조건 실행기 후보',adapter_label,'runtime/engineering_verification.json'),
        ('pilot','개발 15 → 60 → 720단계 파일럿','미실행','runtime/planned_schedule.json'),
        ('freeze','모델·문맥·표본·예산·입력 동결','미완료','runtime/runtime_probe.json'),
        ('analysis','시나리오 단위 IUT·Holm·bootstrap','단위 테스트 기록 참조 / 원응답 지표 집계 연결 미완료','audit/engineering_verification.json'),
        ('semantic_evaluation','A/C 사실·귀속·제약·설명과 비중·오류전파 평가','의미 평가·사람 채점 및 단계별 오류전파 집계 미구현·미검증','runtime/engineering_verification.json')]
    blockers=[
        '4펀드×3시점의 적격 원문·전체 보유·SIC·NAV 대조가 완료되지 않았다.',
        'v6.3이 요구하는 전 펀드 두 명의 독립 사람 감사와 실제 사실 표본 감사가 없다.',
        'Ollama API adapter 후보는 구현했으나 실제 서버와 v6.3 모델별 renderer·정확한 문맥 계산·수치도구 통합을 완료하지 않았다.',
        '실제 입력의 파일럿, 문맥 길이, 지연, 호출 예산 및 본실험 입력 동결을 완료하지 않았다.',
        '원응답에서 통계 지표를 구성하는 연결과 A/C 의미 오류·사람 채점·오류전파 평가가 미완료다.'
    ]
    if not remote_runtime.get('models'):
        blockers.append('사용 가능한 모델과 정확한 토크나이저 자산을 확인해야 한다.')
    if not numerical_state['all_synthetic_checks_resolved']:
        blockers.append('합성 수치 sweep 또는 최소분산 경계 검증에 미해결 항목이 있다: '+numerical_state['label'])
    if verification.get('status')!='passed':blockers.append('공학 검증이 아직 모두 통과하지 않았다.')
    complete_rows=sum(bool(row.get('ready')) for row in readiness.get('rows',[]))
    # This delivery only records the preparation session; it must not infer attempts from plans.
    status={'schema':'libera_v63_execution_status_v1','user_facing_date':'2026-10-27',
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'protocol_version':plan['protocol_version'],'protocol_sha256':hashlib.sha256(planpath.read_bytes()).hexdigest(),
            'status':'incomplete_prerequisites','all_experiments_completed':False,
            'actual_experimental_model_requests':schedule_counts['model_calls'],'planned_trajectories':schedule_counts['trajectories'],
            'live_engineering_model_calls':live_engineering_calls,'live_engineering_excluded_from_experiments':True,
            'planned_logical_stages':schedule_counts['logical_stages'],
            'attempted_logical_stages':schedule_counts['attempted_stages'],'completed_logical_stages':schedule_counts['completed_stages'],
            'not_attempted_logical_stages':schedule_counts['not_attempted_stages'],'schedule_validation':schedule_counts,
            'numerical_verification':numerical_state,
            'official_source_verification':{'checks_passed':source_verification.get('checks_passed'),
                'checks_total':source_verification.get('checks_total'),'status':source_verification.get('status'),
                'parsed_holdings_rows':source_summary.get('parsed_holdings_rows'),
                'source_bytes_present_fund_periods':source_summary.get('source_bytes_present_fund_periods'),
                'historical_certification_or_human_review':False},
            'remote_runtime_inventory':{'available':bool(remote_runtime),'status':remote_runtime.get('status','checking_separately'),
                                        'evidence':remote_path if remote_runtime else None,'summary_ko':remote_summary},
            'engineering_verification':{'status':verification.get('status','not_run'),'tests':verification.get('tests',0)},
            'fund_period_profiles_ready':complete_rows,'fund_period_profiles_required':12,
            'blockers':blockers,'gates':[{'id':g[0],'description':g[1],'status':g[2],'evidence':g[3]} for g in gate_rows],
            'hypothesis_results':{name:{'status':'not_estimable_without_experimental_outputs','p':None,'p_holm':None}
                                  for name in ['H1','H2','H3_R1_R2','H3_R1_R3','H3_R2_R3']},
            'preservation':'Original papers, previous results, raw responses, v6.3 protocol and reference bundle retained. New work is separately recorded.',
            'scope_limit':'Synthetic h tests, mock model tests and generated scenario ledgers are engineering artifacts, not completed LLM experiments.'}
    save(DATA/'execution_status.json',status)
    # A journal of tangible operations and outputs, not invented experiment events.
    actions=[
        {'operation':'read_protocol','evidence':['실험참고자료_20261027/00_먼저읽기.html',planpath.relative_to(ROOT).as_posix()],'outcome':'v6.3 selected'},
        {'operation':'audit_reference_sources','evidence':['data/v63_20261027/audit/workspace_provenance.json'],'outcome':provenance.get('counts')},
        {'operation':'collect_official_sources','evidence':['data/v63_20261027/source_manifest.json','data/v63_20261027/readiness.json'],'outcome':{'requests_recorded':len(sources),'ready_profiles':complete_rows}},
        {'operation':'verify_engineering_implementation','evidence':['data/v63_20261027/audit/engineering_verification.json'],'outcome':status['engineering_verification']},
        {'operation':'probe_model_runtime','evidence':['data/v63_20261027/runtime/runtime_probe.json'],'outcome':'read-only probe; 0 generation requests'},
        {'operation':'record_remaining_work','evidence':['data/v63_20261027/runtime/planned_schedule.json','data/v63_20261027/execution_status.json'],'outcome':f"{schedule_counts['not_attempted_stages']} not_attempted stages; no fallback weights or p-values fabricated"}]
    if remote_runtime:
        actions.append({'operation':'inspect_remote_runtime','evidence':['data/v63_20261027/'+remote_path],
                        'outcome':{'status':remote_runtime.get('status'),'summary_ko':remote_summary,
                                   'live_engineering_model_calls':live_engineering_calls,'experimental_model_calls':0}})
    save(DATA/'execution_journal.json',{'recorded_at_utc':status['recorded_at_utc'],'actions':actions})
    counts=Counter(s.get('status','unknown') for s in sources)
    workload_rows=''.join(f'<tr><td>{h(b["block"])}</td><td class="num">{b["logical_stages"]:,}</td><td>미실행</td></tr>' for b in plan['workload']['original_blocks'])
    gate_html=''.join(f'<tr><td>{h(g[1])}</td><td>{h(g[2])}</td><td>{link("data/v63_20261027/"+g[3],"기록") if (DATA/g[3]).is_file() else "아래 자료·감사 기록 참조"}</td></tr>' for g in gate_rows)
    fundrows=''
    for row in readiness.get('rows',[]):
        issues=row.get('issues',[])
        if isinstance(issues,str):issues=[issues]
        fundrows+=f'<tr><td>{h(row.get("ticker"))}</td><td>{h(row.get("holdings_as_of"))}</td><td>{h(row.get("publication_cutoff"))}</td><td>{"완료" if row.get("ready") else "미완료"}</td><td>{h("; ".join(str(i) for i in issues))}</td></tr>'
    testrows=''.join(f'<tr><td>{h(r["suite"].split(".")[-1])}</td><td class="num">{r["tests"]}</td><td>{"통과" if r["exit_code"]==0 else "실패"}</td><td>{link(r["log"],"원본 로그")}</td></tr>' for r in verification.get('suites',[]))
    source_rows=''.join(f'<tr><td>{h(s.get("id"))}</td><td>{h(s.get("status"))}</td><td>{h(s.get("content_validation","원문 검증 기록 참조"))}</td><td><a href="{h(s.get("requested_url",""))}">공식 원본</a></td></tr>' for s in sources)
    doc=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LIBERA v6.3 실험 실행·검증 기록</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f0f3f6;color:#1e2d3e;font:16px/1.75 "Malgun Gothic",system-ui,sans-serif}}main{{max-width:1160px;margin:28px auto;background:white;padding:44px;border:1px solid #d9e1e8;border-radius:14px}}h1{{font-size:30px;line-height:1.4;margin:8px 0 18px}}h2{{margin-top:38px;font-size:22px}}h3{{font-size:18px}}a{{color:#1454a4;overflow-wrap:anywhere}}.eyebrow{{font-size:14px;font-weight:700;color:#315777}}.notice{{background:#fff3db;border-left:5px solid #a46513;padding:17px 22px}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}}.stat{{padding:18px;background:#eef4f9;border:1px solid #d7e3ee;border-radius:8px}}.stat strong{{display:block;font-size:26px}}.small{{color:#526275;font-size:14px}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{padding:11px 12px;border-bottom:1px solid #dbe2e9;text-align:left;vertical-align:top}}th{{background:#eef3f7}}.num{{text-align:right;white-space:nowrap}}li{{margin:9px 0}}code{{font-size:13px;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;background:#f4f7fa;padding:16px;font-size:13px}}details{{margin:18px 0;border:1px solid #dbe2e9;padding:14px}}summary{{font-weight:700;cursor:pointer}}footer{{border-top:1px solid #dbe2e9;margin-top:30px;padding-top:16px}}@media(max-width:760px){{main{{padding:22px 16px;margin:0;border:0;border-radius:0}}h1{{font-size:25px}}.stats{{grid-template-columns:1fr}}table{{min-width:640px}}}}@media print{{body{{background:white}}main{{border:0;margin:0;padding:10mm}}h2{{break-after:avoid}}tr,.notice,.stat{{break-inside:avoid}}}}
td:last-child a{{white-space:nowrap}}
.fund-table td:not(:last-child),.fund-table th:not(:last-child){{white-space:nowrap}}
</style></head><body><main><header><div class="eyebrow">LIBERA · v6.3 · 2026-10-27</div><h1>실험 실행·검증 기록</h1><p>공통 GenAI는 기관투자자의 전략적 이질성을 축소하는가?</p></header>
<div class="notice"><strong>본실험은 아직 실행하지 않았습니다.</strong><br>자료 수집과 오프라인 구현·검증을 진행했습니다. 공식 보유자료와 사람 감사, 실제 모델 실행 연결이 충족되지 않아 총 {schedule_counts['not_attempted_stages']:,}단계는 미실행으로 남겼습니다. 과거 실험이나 합성 테스트를 새 본실험 결과로 합산하지 않았습니다.</div>
<div class="stats"><div class="stat"><strong>{schedule_counts['attempted_stages']:,} / {schedule_counts['logical_stages']:,}</strong>실제 실험 단계 실행</div><div class="stat"><strong>{verification.get('tests',0)}개</strong>단위 테스트 {"통과" if verification.get('status')=='passed' else "기록 확인 필요"}</div><div class="stat"><strong>{complete_rows} / 12</strong>자료·감사를 마친 펀드×시점</div></div>
<h2>이번에 수행한 작업</h2><ul>
<li>‘먼저읽기’ HTML, v6.3 설정과 쉬운 설명, 2쪽 원초록을 읽고 새 실험의 범위와 사전 조건을 확인했습니다.</li>
<li>참고목록 2,244항목을 현 저장소와 대조했습니다. 바이트 일치 {provenance.get('counts',{}).get('exact',0):,}개, 줄바꿈만 다른 {provenance.get('counts',{}).get('line_endings_only',0):,}개, 그 외 차이 {provenance.get('counts',{}).get('changed',0):,}개입니다. v6.3 설정·쉬운 설명·원초록·FF12 월간 수익률은 원래 해시와 일치합니다. 빠진 snapshot 링크 대신 저장소 원본을 사용했습니다.</li>
<li>공식 자료의 원문·추출문·요청 URL·HTTP 결과·SHA-256을 저장했습니다. 성공 응답이라도 오류 페이지, 기간이 다른 가변 문서, 불완전 보유표는 적격 자료로 처리하지 않았습니다.</li>
<li>120개월 FF12 원본과 단위, 신호 생성·부분정보 사후분포·분산상한 최적화·근접최적집합의 오프라인 검산을 진행했습니다. 현재 수치 상태: <strong>{h(numerical_state['label'])}</strong>. 단위 테스트 통과와 수치 sweep·경계 사례 해결 여부는 구분합니다.</li>
<li>BM25 검색, 펀드·시점 필터, 동일 근거 유지, 실패 분류·재시도·원비중 보존, 60개 시나리오 단위 통계 커널을 구현하고 테스트했습니다.</li>
<li>{schedule_counts['trajectories']:,}개 궤적·{schedule_counts['logical_stages']:,}단계의 실행계획을 생성하고 설계의 블록별 단계 수와 대조했습니다. 계획된 v6.3 실험의 모델 요청 수는 {schedule_counts['model_calls']}입니다.</li></ul>
<p>{link('data/v63_20261027/execution_journal.json','실행 일지')} · {link('data/v63_20261027/execution_status.json','현재 상태 JSON')} · {link('data/v63_20261027/audit/workspace_provenance.json','원본 대조 기록')}</p>
<h2>실행을 위해 남은 조건</h2><div class="table"><table><thead><tr><th>항목</th><th>현재 상태</th><th>증거</th></tr></thead><tbody>{gate_html}</tbody></table></div>
<p>사람 감사는 v6.3의 <code>human_review.fund_eligibility_and_constraints = "two independent humans for all funds"</code> 및 <code>AI_review_not_human_substitute = true</code>를 따릅니다. AI 검토나 사용자 실행 지시를 사람 두 명의 실제 감사 기록으로 바꾸지 않았습니다.</p>
<p>{link(planpath.relative_to(ROOT).as_posix(),'최종 설계 JSON')} · {link('research/v63/README.md','재실행 방법과 구현 한계')}</p>
<h2>모델 실행 환경 확인</h2><p>현재 컴퓨터의 11434·11435·11436 포트에서 모델 서비스 응답을 얻지 못했고, 기존 기록이 가리키는 로컬 모델과 정확한 토크나이저 파일도 찾지 못했습니다. 이 확인을 원격 서버의 모델 부재로 해석하지 않습니다.</p>
<p>{h(remote_summary)} {link('data/v63_20261027/'+remote_path,'원격 환경 확인 기록') if remote_runtime else ''}</p>
<p>별도 실제 모델 연결검사는 <strong>{live_engineering_calls}회</strong>이며, v6.3 개발 파일럿과 본실험에는 포함하지 않았습니다. 연결검사 원응답과 메타데이터는 원격 서버에 보관했습니다. PC로 회수한 파일과 원본 해시 대조 결과는 원격 확인 기록에 표시했습니다.</p>
<p>현재 v6.3 실행기는 합성 응답으로 검증한 상태기계 후보입니다. {h(adapter_label)}. 모델별 대화 템플릿·정확한 전체 이력 토큰 계산·수치도구 연결과 실험 입력으로 수행하는 실모델 실행은 미검증입니다. A/C의 사실·귀속·제약 해석·설명과 비중의 일치·오류전파 평가도 구현과 사람 채점이 남아 있습니다.</p>
<h2>네 펀드 자료 준비 현황</h2><p>개발기 2025-09-30, 본기 2025-12-31, 보류기 2026-03-31을 구분합니다. 원문 확보 여부와 실험 사용 가능 여부는 다릅니다. SIC 누락 주식도 분류율 분모에 남기며, NAV 차이나 비공개 보유를 임의로 보정하지 않았습니다.</p>
<p>보유 항목 <strong>{source_summary.get('parsed_holdings_rows',0):,}행</strong>을 파싱했고, 전체 12개 펀드×시점 중 <strong>{source_summary.get('source_bytes_present_fund_periods',0)}개</strong>에 관련 원문 바이트를 확보했습니다. 실제 실험 준비 완료는 <strong>{complete_rows}개</strong>입니다. 자료의 바이트·추출 산술·준비 상태 검사 {source_verification.get('checks_passed',0)}/{source_verification.get('checks_total',0)}건 통과는 역사적 적격성 인증이나 사람 감사 완료를 뜻하지 않습니다. HTTP 2xx로 받은 오류 페이지도 별도로 제외했습니다.</p>
<div class="table"><table class="fund-table"><thead><tr><th>펀드</th><th>보유 기준일</th><th>공개 상한</th><th>실행 준비</th><th>미해결 사항</th></tr></thead><tbody>{fundrows}</tbody></table></div>
<p>{link('data/v63_20261027/readiness.json','12개 펀드·시점 상세')} · {link('data/v63_20261027/source_manifest.json','자료 수집 원장')}</p>
<details><summary>공식 자료 요청 기록 {len(sources)}건</summary><p>HTTP 다운로드 수와 역사적 적격 원문 수를 혼동하지 않습니다. 각 항목의 판정과 원문 해시는 자료 수집 원장을 확인합니다.</p><div class="table"><table><thead><tr><th>ID</th><th>전송 상태</th><th>내용 확인</th><th>출처</th></tr></thead><tbody>{source_rows}</tbody></table></div></details>
<h2>코드 검증 결과</h2><p>아래는 알고리즘과 실행 절차의 공학 검증입니다. 펀드의 실제 배분 결과, 모델 성능 또는 RAG 효과를 보여 주는 표가 아닙니다.</p>
<div class="table"><table><thead><tr><th>검증 범위</th><th>테스트 수</th><th>결과</th><th>증거</th></tr></thead><tbody>{testrows}</tbody></table></div>
<p>누락 근거·다른 펀드 정보의 유입, 부분정보 업데이트, 기준해 불확실성, 잘못된 합계의 자동 정규화, 모델 오류 재시도, 미시도 궤적의 h 대체 등을 점검했습니다. 통계에서는 펀드 쌍과 반복을 독립 시장표본으로 세지 않으며, 다섯 결합가설을 Holm 보정합니다. 분산이 0이거나 검정 불가능하면 p=1을 유지합니다.</p>
<p>{link('data/v63_20261027/audit/engineering_verification.json','통합 검증 기록')} · {link('data/v63_20261027/numerical/verification.json','수치 검산')} · {link('data/v63_20261027/runtime/engineering_verification.json','검색·실행기 검산')}</p>
<h2>실험별 실행 기록</h2><div class="table"><table><thead><tr><th>실험</th><th>예정 단계</th><th>현재 상태</th></tr></thead><tbody>{workload_rows}<tr><th>합계</th><th class="num">{schedule_counts['logical_stages']:,}</th><th>모두 미실행</th></tr></tbody></table></div>
<p>미시도 슬롯은 <code>not_attempted</code>, 비중은 <code>null</code>로 보존했습니다. h 유지는 실제 요청 후 모델·운영 실패에만 적용하는 정책이므로 미시도 실험에 채워 넣지 않았습니다. H1·H2·H3 결과와 p값은 산출하지 않았습니다.</p>
<p>{link('data/v63_20261027/runtime/planned_schedule.json','전체 실행 순서')} · {link('data/v63_20261027/runtime/runtime_probe.json','모델 환경 확인')}</p>
<h2>재개 순서</h2><ol><li>자료 준비표의 누락·불완전 보유·분모 차이·SIC를 해결하고 두 사람의 독립 감사를 기록합니다.</li><li>수치 sweep·최소분산 경계의 미해결 항목을 해결하고 실제 h로 기준해와 검색 입력을 검증합니다.</li><li>사용할 모델 서버·정확한 모델 버전·토크나이저를 고정하고 실제 API adapter·대화 템플릿·수치도구를 연결합니다.</li><li>원응답 지표 집계와 A/C 의미·오류전파 평가기를 완성하고 사람 채점 절차를 준비합니다.</li><li>개발자료로 15 → 60 → 720단계 파일럿을 진행해 문맥·시간·호출 예산을 측정합니다.</li><li>코드·모델·분석·입력 해시를 동결하고 본실험, 전망교체, 음성대조, 실제문서 A와 C를 실행합니다.</li><li>원응답과 실패를 포함한 전체 정책 결과를 집계하고 동결된 시나리오·정밀도 층·모든 펀드 반복의 적격 종료 상태를 확인한 뒤 사전 지정 가설을 검정합니다.</li></ol>
<footer class="small">기존 원고·설계·과거 원응답은 보존했습니다. 새 파일은 <code>research/v63/</code>와 <code>data/v63_20261027/</code>에 기록했습니다. 이 문서는 실행 완료 보고서가 아니라 수행한 준비·검증 및 미완료 사유의 기록입니다.</footer></main></body></html>'''
    report=BUNDLE/'01_실행기록_20261027.html'
    report.write_text(doc,encoding='utf-8')
    # Hash source and evidence outputs, excluding recursive manifest and regenerable previews.
    paths=[p for p in (ROOT/'research/v63').rglob('*') if p.is_file() and '__pycache__' not in p.parts]+[report]
    paths+= [p for p in DATA.rglob('*') if p.is_file() and p.name!='artifact_manifest.json' and not any('preview' in part for part in p.parts)]
    artifacts=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,
                'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(set(paths))]
    save(DATA/'artifact_manifest.json',{'schema':'v63_delivery_manifest_v1','recorded_at_utc':status['recorded_at_utc'],
        'experimental_model_calls':0,'live_engineering_model_calls':live_engineering_calls,'files':artifacts})
    print(json.dumps({'report':report.relative_to(ROOT).as_posix(),'status':status['status'],
                      'tests':verification.get('tests',0),'source_requests':len(sources),'files':len(artifacts)},ensure_ascii=False))

if __name__=='__main__':main()
