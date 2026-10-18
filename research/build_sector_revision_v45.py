"""Build a separate v4.5 record from saved execution, three audits and findings."""
from pathlib import Path
import copy
import hashlib
import html
import json
from decimal import Decimal
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
RUN = 'data/local_sector_runtime/single_case_v45_20261018'
FINDINGS = 'research/v45_single_case_findings_20261018.json'
REGISTRATION = 'data/sector_protocol/v45_single_case_registration_20261018.json'
MANIFEST = 'data/sector_protocol/v45_single_case_20261018/manifest.json'
NAMES = {'plan': 'plan/LIBERA_실험계획_v{v}_20261018.html',
         'paper': 'paper/LIBERA_텀페이퍼_초안_v{v}_20261018.html',
         'config': 'plan/LIBERA_실험설정_v{v}_20261018.json'}


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def esc(value):
    return html.escape(str(value))


def append(node, markup):
    for item in list(BeautifulSoup(markup, 'html.parser').contents):
        node.append(item)


def replace(node, markup):
    if node is None:
        raise ValueError('Expected a known source section')
    for item in list(BeautifulSoup(markup, 'html.parser').contents):
        node.insert_before(item)
    node.decompose()


def status(summary):
    label = {'completed_four_stages':'4단계 완료','hard_deadline':'시간 제한 종료',
             'cancelled':'중단','failed':'실패'}.get(summary['status'],summary['status'])
    return (f"v4.5 단일 예비 사례: {label}, 단계 기록 {summary['completed_workflow_stages']}/4, "
            f"완료 응답 {summary['http_streams_completed']}회 / 생성 요청 {summary['generation_requests_attempted']}회. "
            "수치·의미 판정은 별도 보고. 본과제 0건·미동결, 독립 사람 검토 대기.")


def methods(runtime):
    opts = runtime['options']
    rows = [('모델', runtime['model'], '기본 Qwen3.5-4B의 Q4_K_M 구현. FinVector 추가 학습 모델이 아니다.'),
            ('출력 형식', 'API JSON Schema + 단계별 프롬프트에 같은 스키마 명시', 'FinVector §4.1의 명시적 스키마 제공과 Ollama 공식 기능을 조합. 문법 강제는 별도 구현 선택.'),
            ('샘플링', f"T={opts['temperature']}, seed={opts['seed']}, thinking=false", 'FinVector의 greedy·seed·thinking 조건을 Ollama에 적용. 동일 실행 엔진 재현은 아니다.'),
            ('생성 상한', opts['num_predict'], 'PortBench의 값을 다른 과제에 이식. FinVector의 700 토큰 조건과 구분.'),
            ('문맥·실행', f"num_ctx={opts['num_ctx']}, num_thread={opts['num_thread']}, num_batch={opts['num_batch']}, 단계 제한 {runtime['deadline_seconds']}초", '이전 실측과 실행 관리에 따른 구현 조건. 논문의 직접 실험 수치로 표시하지 않는다.'),
            ('반복 관련 벌점', f"repeat={opts['repeat_penalty']}, presence={opts['presence_penalty']}, frequency={opts['frequency_penalty']}", '기존 v4.4의 중립값 유지. 공개 저자 예제의 구현 해석이며 논문 미보고 값을 직접 인용하지 않는다.')]
    table = ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)
    return f'''<h3 id="model-v45">4.6. v4.5 출력 구조 수정과 실행 조건</h3>
<p>v4.4에서는 첫 단계가 입력 자료를 재출력하다가 900초 제한으로 끝났다. v4.5는 같은 Fidelity Q2/R1 사례에서 출력 구조를 명시하는 예비 수정이다. 모델·기관 문서·시장 수치·원래 네 단계 과제·계산기·샘플링 수치·출력 및 문맥 예산은 유지하고, API에 응답 스키마를 전달하는 것과 프롬프트에 그 스키마를 보여 주는 것을 함께 적용했다. 두 변경의 개별 효과를 식별한 비교실험은 아니다.</p>
<p><a href="https://arxiv.org/pdf/2610.08882">FinVector §4.1</a>은 과제별 JSON 스키마를 프롬프트에 명시하는 조건을 비교한다. 이 논문이 Ollama의 제약 디코딩을 사용했다고 주장하지 않는다. API 형식 제약은 <a href="https://docs.ollama.com/capabilities/structured-outputs">Ollama 공식 문서</a>와 사용 버전의 소스에서 확인한 구현이다. <a href="../research/v45_revision_reference_20261018.html">새 수정의 근거·적용 범위</a>와 <a href="../research/v44_conditions_reference_20261018.html">유지한 수치 조건의 근거</a>를 구분해 보존한다.</p>
<div class="table-wrap"><table><thead><tr><th>항목</th><th>적용</th><th>근거와 한계</th></tr></thead><tbody>{table}</tbody></table></div>
<p>스키마는 일곱 응답 필드, 자료형, 행 수와 공통 산업 코드만 제한한다. 기관의 정답 등급·정답 근거 ID·정답 비중은 넣지 않는다. 11행이 반드시 서로 다른 11개 산업이라는 뜻은 아니므로 중복·누락도 별도로 검사한다. 비중의 합계·부호 오류는 원안 그대로 계산기에 전달하고 다음 단계에서 모델이 검토하게 한다. 프로그램은 비중을 정규화하거나 실패 응답을 다시 뽑지 않는다.</p>
<p>과거 모델 응답과 계산 결과의 문자열은 보존한다. 각 단계 과제에 스키마 안내를 일관되게 추가하고, 기존의 중복 시장 필드 제거는 원래 수치로 복원되는지 확인한다. 실제 요청은 truncate=false·shift=false를 사용한다. 렌더 검사는 보이는 대화의 보존 검사이며 독립적인 토큰 용량 측정이나 의미 기억의 보장은 아니다. 엔진 버전·모델 digest·템플릿은 요청마다 확인하고, 실행 바이너리와 GPU 배치는 별도 관측 기록으로 구분한다.</p>'''


def execution(summary, findings):
    rows = []
    for stage in range(1, 5):
        folder = ROOT / RUN / f'stage{stage}_transport'
        attempted = (folder / 'http_0001_generation/request.json').is_file()
        p = folder / 'http_0001_generation/response.json'
        response = json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}
        timing = folder / 'http_0001_generation/result.json'
        result = json.loads(timing.read_text(encoding='utf-8')) if timing.is_file() else {}
        metric = result.get('metrics', {})
        supervisor_path = folder / 'supervisor_result.json'
        supervisor = json.loads(supervisor_path.read_text(encoding='utf-8')) if supervisor_path.is_file() else {}
        def num(key):
            value = metric.get(key)
            return ('완료 수치 없음' if attempted else '미실행') if value is None else f'{value:.2f}' if isinstance(value, float) else str(value)
        rows.append('<tr>' + ''.join('<td>'+esc(x)+'</td>' for x in
            [stage, supervisor.get('status','미실행'), result.get('status','미완료' if attempted else '미실행'),
             response.get('done_reason', '완료 응답 없음' if attempted else '미실행'), num('wall_seconds'),
             num('prompt_eval_count'), num('eval_count')]) + '</tr>')
    statements = ''.join('<p>'+esc(f['statement'])+' '+ ' '.join(
        f'<a href="../{esc(p)}">근거</a>' for p in f['evidence'])+'</p>' for f in findings['findings'])
    reviews = ''.join(f'<li><a href="../research/v45_single_case_round{n}_20261018.html">{n}차 검증 상세</a></li>' for n in (1, 2, 3))
    final_path = ROOT / RUN / 'fidelity_q2_2026__R1/final.json'
    allocation = ''
    if final_path.is_file():
        final = json.loads(final_path.read_text(encoding='utf-8'), parse_float=Decimal)
        market = json.loads((ROOT / 'data/sector_market/market_input.json').read_text(encoding='utf-8'), parse_float=Decimal)
        names = dict(zip(market['sector_codes'], ['에너지','소재','산업재','경기소비재','필수소비재','헬스케어','금융','정보기술','커뮤니케이션','유틸리티','부동산']))
        weight_rows = []
        for row in final['weights']:
            code = row['sector_code']
            ratings = [x['rating'] for x in final['interpretations'] if x['sector_code'] == code]
            weight, baseline = Decimal(str(row['weight'])), market['baseline_weights'][code]
            weight_rows.append('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in [code+' '+names[code],
                ' / '.join(ratings), f'{weight*100:.4f}%', f'{baseline*100:.4f}%',
                f'{(weight-baseline)*100:+.4f}%p'])+'</tr>')
        allocation = '<h3>최종 원안의 산업 비중</h3><p>아래는 모델이 제출한 값이다. 표시만 소수 네 자리로 반올림했으며 원본 비중을 수정하거나 정답 비중으로 해석하지 않는다. 등급도 모델이 추출한 것이므로 원문 일치 판정은 별도 검증을 따른다.</p><div class="table-wrap"><table><thead><tr><th>산업</th><th>모델 추출 등급</th><th>최종 비중</th><th>공통 기준 비중</th><th>차이</th></tr></thead><tbody>'+''.join(weight_rows)+'</tbody></table></div>'
    return f'''<section id="runtime-v45"><h2>v4.5 단일 예비 실행과 세 차례 자체 검증</h2>
<p>{esc(status(summary))} <a href="../{RUN}/summary.json">실행 원본</a> · <a href="../{REGISTRATION}">생성 전 등록</a>.</p>
<p>쉽게 말하면, 먼저 AI에게 공개 산업 전망과 같은 시장자료를 읽게 하고, 두 번째로 가능한 배분 대안과 위험을 비교하게 한다. 세 번째에는 11개 산업에 얼마씩 배분할지 초안을 만들게 하고, 계산기가 합계·제약·위험 수치를 확인한다. 마지막에는 앞선 판단과 계산 결과를 모두 보고 최종 비중과 근거를 다시 내게 한다. 이번 실행은 자료를 첫 단계부터 준 한 사례다.</p>
<div class="table-wrap"><table><thead><tr><th>단계</th><th>감독 상태</th><th>응답 상태</th><th>종료 이유</th><th>요청 시간(초)</th><th>입력 토큰</th><th>출력 토큰</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
{statements}
{allocation}
<ul>{reviews}</ul>
<p>1차는 입력·이력·실행 기록, 2차는 독립 산술·고정 분모·인용 범위, 3차는 원문 의미·판단 근거·연구주제와의 연결을 검토한다. 세 검토는 자동·분담 자체 검증이며 독립 사람의 내용 검토를 대신하지 않는다.</p>
<p><strong>이전 실패와 분모를 보존한다.</strong> <a href="../data/local_sector_runtime/single_case_v44_20261018/summary.json">v4.4 실패</a>는 완료 0/4로 남긴다. 기존 평가 명세의 실패 포함 고정 분모에 따르면 그 시도의 원문 등급 추출은 0/11이다. 이전 검토에서 수치·의미 판단을 적용 불가로 표시한 것은 완성된 답변이 없었다는 뜻이며, 이 추출 지표의 분모를 삭제한다는 뜻으로 사용하면 안 된다. v4.4와 v4.5를 같은 고정 조건의 독립 표본으로 합산하지 않는다.</p>
</section>'''


def build_html(source, summary, findings, runtime):
    soup = BeautifulSoup(source.read_text(encoding='utf-8'), 'html.parser')
    old = soup.find(id='model-v44')
    for node in list(old.next_siblings):
        node.extract()
    old.decompose()
    append(soup.find(id='design'), methods(runtime))
    replace(soup.find(id='runtime-v44'), execution(summary, findings))
    for n in soup.select('.status'):
        n.string = status(summary)
    for n in soup.select('.callout'):
        if 'v4.4' in n.get_text(): n.string = status(summary)
    for n in soup.select('.eyebrow'):
        n.string = n.get_text().replace('4.4', '4.5')
    if soup.title: soup.title.string = soup.title.get_text().replace('v4.4', 'v4.5')
    for n in soup.find_all('strong'):
        if n.get_text().startswith('v4.4 ·'):
            n.string = 'v4.5 · 단일 예비 실행과 본과제 결과를 구분한다.'
    conclusion = soup.find(id='conclusion')
    if conclusion:
        for p in conclusion.find_all('p', recursive=False):
            if 'v4.4 단일 예비 사례' in p.get_text():
                p.string = status(summary) + ' 예비 실행은 근거의 추출과 실제 배분을 분리해 검증할 필요를 보여 주며, 기관 간 수렴이나 근거 제공 시점의 효과를 아직 검증한 것은 아니다.'
    if soup.find(id='candidates'):
        replace(soup.find(id='candidates'), '<section id="candidates"><h2>현재 선택과 남은 검증</h2><p>이번 기록은 Qwen3.5-4B Q4_K_M을 사용한 Fidelity Q2/R1 한 사례다. 현재 관측으로 모델이나 조건의 전체 적합성을 확정하지 않는다. 나머지 예비 사례와 R4 실행기 검증, 독립 사람의 원문 검토, 본과제 조건 동결과 별도 실행이 남아 있다. 정성 문서에 유일한 정답 비중이나 위험회피 계수를 임의로 추가하지 않는다.</p></section>')
    replace(soup.find(id='appendix'), f'''<section id="appendix"><h2>부록. 재현 자료와 남은 실행</h2>
<p><a href="../research/local_sector_structured_case.py">v4.5 단일 사례 실행기</a>, <a href="../{MANIFEST}">입력·소프트웨어 고정 기록</a>, <a href="../data/sector_protocol/evaluation_spec.json">기존 기계적 평가 명세</a>, <a href="../research/v45_revision_reference_20261018.html">수정 근거</a>를 연결한다. 이전 v4.4 원본은 변경하지 않는다. 실제 응답은 실행 폴더에서 원문 그대로 보존한다.</p>
<p>이번에 선택한 사례는 실패를 진단하며 다시 사용한 예비 사례이므로 독립 확인 표본이 아니다. 나머지 예비 사례를 같은 버전으로 실행·검토한 다음 본과제의 입력·조건·평가를 동결하고 별도 본실험을 진행해야 한다. 이번 자체 검증은 그 절차를 승인하거나 대체하지 않는다.</p>
<p>텀페이퍼 제출은 2026년 11월 1일, 발표는 11월 6일이며 APA 인용을 따른다. 확인되지 않은 제출 분량·형식이나 실험 결과 필수 여부는 임의로 정하지 않는다. 저자·소속 정보는 제출 전에 기입한다.</p></section>''')
    for a in soup.find_all('a', href=True):
        a['href'] = a['href'].replace('#runtime-v44', '#runtime-v45')
        for template in NAMES.values():
            a['href'] = a['href'].replace(Path(template.format(v='4.4')).name, Path(template.format(v='4.5')).name)
        if a.get_text() == 'v4.4 단일 예비 실행': a.string = 'v4.5 단일 예비 실행'
        if a.get_text() == 'v4.4 설정과 상태 출처': a.string = 'v4.5 설정과 상태 출처'
    if soup.footer: soup.footer.string = 'LIBERA · 2026-10-18 · ' + status(summary)
    return str(soup)


def main():
    summary = read(RUN + '/summary.json')
    if summary['main_model_calls'] != 0: raise ValueError('Unexpected main run')
    findings = read(FINDINGS)
    reviews = [f'research/v45_single_case_round{n}_20261018.json' for n in (1, 2, 3)]
    for p in reviews: read(p)
    for item in findings['source_files']:
        if sha(item['path']) != item['sha256']: raise ValueError('Findings source changed')
    for item in read(REGISTRATION)['reference_files']:
        if sha(item['path']) != item['sha256']: raise ValueError('Registered source changed')
    runtime = read('data/sector_protocol/v45_single_case_20261018/runtime.json')
    paths = {k: t.format(v='4.4') for k, t in NAMES.items()}
    before = {k: sha(p) for k, p in paths.items()}
    config = copy.deepcopy(read(paths['config']))
    config.update(protocol_version='4.5', previous_protocol=paths['config'],
        status='versioned_single_case_pilot; main_not_run_not_frozen',
        current_single_case=summary,
        review_records=[{'path': p, 'sha256': sha(p)} for p in reviews],
        findings_reference={'path': FINDINGS, 'sha256': sha(FINDINGS)})
    config['main']['paths']['single_case_runner'] = '../research/local_sector_structured_case.py'
    config['main']['runtime_policy'] = 'v4.5 one-case observations only; remaining pilot and main pending.'
    config['main']['pending'] = ['Review and resolve the observed pilot limitations',
        'Validate R4 and complete the remaining pilot cases under explicit versioned conditions',
        'Independent substantive human source review', 'Freeze main inputs, model and rubric',
        'Separate main execution and offline evaluation']
    config['model'].update(protocol_version='4.5', runtime_ready=False,
        runtime_manifest_path=MANIFEST, review='../research/v45_revision_reference_20261018.html',
        response_contract='per-stage API JSON Schema and identical schema grounded in task prompt',
        one_case_workflow_completed=summary['completed_workflow_stages'] == 4,
        context_check_observed_stages=[n for n in range(1,5) if
            (ROOT / RUN / f'stage{n}_transport/render_only/validation.json').is_file()],
        future_candidate_scope='Pinned v4.5 single-case repair; no main freeze.')
    request = {key:runtime[key] for key in
        ('model','think','truncate','shift','stream','keep_alive','options')}
    config['execution_conditions'].pop('request',None)
    request_headers = {str(n):{**copy.deepcopy(request),
        'format':read(f'data/sector_protocol/v45_single_case_20261018/response_schema_stage{n}.json')}
        for n in range(1,5)}
    config['execution_conditions'].update(protocol_version='4.5', request_headers_by_stage=request_headers,
        runtime=runtime, per_stage_schema_files=[f'data/sector_protocol/v45_single_case_20261018/response_schema_stage{n}.json' for n in range(1,5)],
        schema_amendment={'path':'research/v45_revision_reference_20261018.json',
                          'sha256':sha('research/v45_revision_reference_20261018.json')})
    config['results'] = {'pilot_completed_cases':summary['completed_cases'],
        'pilot_completed_calls':summary['http_streams_completed'],
        'pilot_attempted_calls_observed':summary['generation_requests_attempted'],
        'pilot_completed_workflow_stages':summary['completed_workflow_stages'],
        'final_allocation_valid':summary['final_allocation_valid'],
        'main_completed_cases':0, 'main_completed_calls':0, 'main_execution_ready':False,
        'human_runs':None, 'main_effect_estimate':None,
        'count_scope':'v4.5 single case only; v4.4 failure retained separately'}
    config['evaluation']['denominator_clarification'] = read(REGISTRATION)['denominator_clarification']
    config['observed_execution'] = {'pilot':summary,
        'main':{'status':'not_run','completed_cases':0,'completed_calls':0,'frozen':False},
        'human_review':{'status':'pending'},'historical_v44_record':paths['config']}
    config['revision_provenance'] = {'builder':'research/build_sector_revision_v45.py',
        'source_version':'4.4', 'source_files':{k:{'path':paths[k],'sha256':v} for k,v in before.items()},
        'registration':{'path':REGISTRATION,'sha256':sha(REGISTRATION)},'model_calls_by_builder':0}
    outputs = {k:ROOT / t.format(v='4.5') for k,t in NAMES.items()}
    if any(p.exists() for p in outputs.values()): raise FileExistsError('Versioned output already exists')
    docs = {k:build_html(ROOT / paths[k],summary,findings,runtime) for k in ('plan','paper')}
    if before != {k:sha(p) for k,p in paths.items()}: raise ValueError('Source documents changed')
    for k,doc in docs.items(): outputs[k].write_text(doc,encoding='utf-8')
    outputs['config'].write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'outputs':{k:str(p) for k,p in outputs.items()},'model_calls':0},ensure_ascii=False))


if __name__ == '__main__': main()
