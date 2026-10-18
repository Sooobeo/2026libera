"""Build separate v4.4 plan/paper/config from preserved v4.3 and saved evidence."""
from __future__ import annotations
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'plan': 'plan/LIBERA_실험계획_{version}20261018.html',
         'paper': 'paper/LIBERA_텀페이퍼_초안_{version}20261018.html',
         'config': 'plan/LIBERA_실험설정_{version}20261018.json'}
CONDITIONS = ROOT / 'research/v44_conditions_reference_20261018.json'
REGISTRATION = ROOT / 'data/sector_protocol/v44_single_case_registration_20261018.json'
RENDERER = ROOT / 'research/v44_renderer_policy_20261018.json'
ADDENDUM = ROOT / 'data/sector_protocol/v44_single_case_registration_renderer_addendum_20261018.json'
CASE = 'fidelity_q2_2026__R1'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def esc(value):
    return html.escape(str(value))


def state_label(value):
    return {'not_run': '미실행', 'not_started': '미실행', 'hard_deadline': '시간 제한 종료',
            'failed': '실패', 'cancelled': '중단', 'completed_four_stages': '4단계 기록 완료',
            'worker_exited': '실행 프로세스 종료', 'completed': '수신 완료',
            'started_without_terminal_response': '생성 시작·완료 응답 없음'}.get(value, value)


def fragment(markup):
    return list(BeautifulSoup(markup, 'html.parser').contents)


def replace(node, markup):
    for item in fragment(markup):
        node.insert_before(item)
    node.decompose()


def append(node, markup):
    for item in fragment(markup):
        node.append(item)


def observe(run_dir):
    if run_dir is None:
        return {'status': 'not_run', 'completed_cases': 0, 'completed_calls': 0,
                'http_streams_completed': 0, 'attempted_calls': 0, 'stages': [], 'main_model_calls': 0, 'path': None}
    run_dir = run_dir.resolve()
    summary = read(run_dir / 'summary.json')
    if summary.get('case_id') != CASE or summary.get('main_model_calls') != 0:
        raise ValueError('Only the registered single pilot is accepted')
    stages = []
    for n in range(1, 5):
        transport = run_dir / f'stage{n}_transport'
        response = transport / 'http_0001_generation/response.json'
        result = transport / 'http_0001_generation/result.json'
        supervisor = transport / 'supervisor_result.json'
        render = transport / 'render_only/validation.json'
        stages.append({'stage': n, 'workflow_record': (run_dir / CASE / f'stage{n}_record.json').is_file(),
            'generation_request': (transport / 'http_0001_generation/request.json').is_file(),
            'supervisor_status': read(supervisor).get('status') if supervisor.is_file() else 'not_started',
            'transport_status': read(result).get('status') if result.is_file() else ('started_without_terminal_response' if (transport / 'http_0001_generation/request.json').is_file() else 'not_started'),
            'render_validation': read(render) if render.is_file() else None,
            'response_present': response.is_file(),
            'done_reason': read(response).get('done_reason') if response.is_file() else None,
            'metrics': read(result).get('metrics') if result.is_file() else None})
    complete = all(r['workflow_record'] for r in stages) and (run_dir / CASE / 'final.json').is_file()
    if complete != (summary['status'] == 'completed_four_stages'):
        raise ValueError('Summary and complete four-stage evidence disagree')
    return {'status': summary['status'], 'completed_cases': int(complete),
            'completed_calls': sum(r['workflow_record'] for r in stages),
            'http_streams_completed': summary['http_streams_completed'],
            'attempted_calls': sum(r['generation_request'] for r in stages),
            'stages': stages, 'main_model_calls': 0, 'path': rel(run_dir),
            'summary_sha256': sha(run_dir / 'summary.json'), 'wall_seconds': summary.get('wall_seconds'),
            'error': summary.get('error'), 'render_validations_observed': [r['stage'] for r in stages if r['render_validation'] is not None]}


def status_text(pilot):
    return (f"v4.4 단일 예비 사례: 완료 {pilot['completed_cases']}건, 단계 기록 {pilot['completed_calls']}/4, "
            f"수신 완료 응답 {pilot['http_streams_completed']}회 / 생성 요청 {pilot['attempted_calls']}회, {state_label(pilot['status'])}. 본과제 0건·미동결. 독립 사람 검토 대기.")


def methods(conditions):
    def displayed_reason(row):
        if row['field'] == 'engine_and_backend':
            return '서비스 버전·모델 digest·템플릿을 호출마다 자동 비교한다. 바이너리·GPU 배치는 별도 설치 기록과 서버 로그의 관측 근거이며 실행기의 별도 차단 조건이 아니다. 아래 정정 설명 참조.'
        return row['reason']
    rows = ''.join('<tr><td>' + esc(row['field']) + '</td><td><code>' +
                   esc(json.dumps(row['value'], ensure_ascii=False)) + '</code></td><td>' +
                   esc(displayed_reason(row)) + '<br><small>' + esc(row['level']) + '</small></td></tr>'
                   for row in conditions['conditions'])
    return f'''<h3 id="model-v44">4.6. v4.4의 실행 조건과 근거 수준</h3>
<p>노트북의 Ollama 0.35.1에서 기본 Qwen3.5-4B의 Q4_K_M 변형을 사용한다. Intel Arc 140V의 Vulkan 배치를 관측했으며 설치 digest와 템플릿을 호출마다 확인한다. FinVector 추가학습 모델이나 MLX 실험을 그대로 재현한 것이 아니다. 기관 문서·11개 산업·R1/R4 연구질문은 유지한다.</p>
<p><a href="https://arxiv.org/pdf/2610.08882">FinVector §4.1</a>의 기본 모델·greedy·thinking 비활성화·seed 3407을 근거로 삼는다. 출력 8192는 <a href="https://arxiv.org/html/2605.27887v6#S3.SS1">PortBench §3.1</a>의 값을 다른 모델과 과제에 옮긴 것이다. FinVector의 출력 700을 따른다는 주장은 하지 않는다.</p>
<div class="table-wrap"><table><thead><tr><th>조건</th><th>적용값</th><th>선정 근거와 수준</th></tr></thead><tbody>{rows}</tbody></table></div>
<p><strong>근거표의 구현 범위 정정:</strong> 위 표에 인용한 고정 근거표의 “바이너리·실제 배치까지 실행기에서 고정”이라는 문구는 실행기의 검사 범위를 넓게 표현했다. 호출마다 자동 비교하는 것은 서비스 버전·모델 digest·템플릿이다. 바이너리와 GPU 배치는 별도 설치 기록·서버 로그의 관측 근거이며, 실행기의 별도 차단 조건이 아니다. 원본 근거표와 실제 요청은 변경하지 않고 이 구분을 명시한다.</p>
<p>v4.3의 상속 presence penalty 1.5는 v4.4에서 0으로 명시하고 반복·빈도 벌점도 중립화한다. 이는 저자 공개 최소 예제와 MLX-LM 0.31.3의 무가공 argmax 경로를 옮기는 구현 선택이며, 논문이 보고한 penalty 수치가 아니다. Qwen 제작사의 일반 non-thinking 권장 조건과도 다르다. 논문 미보고 조건을 논문 직접값으로 간주하지 않는다. 전체 근거·원문 코드 해시·적용 한계는 <a href="../research/v44_conditions_reference_20261018.html">실행 전 고정 근거표</a>에 남겼다.</p>
<p>시장 입력에서 정확히 중복된 공분산과 기준 비중 배열만 제거하고 복원 일치를 검사한다. 고유 수치·근거 문장·원문 등급은 변경하지 않는다. 이후 모델 응답과 계산 피드백은 그대로 이어 보낸다. 이 표현 변경도 모델 행동에 영향을 줄 수 있어 v4.4로 구분하며, 양 비교 절차에 같은 표현을 적용해야 한다.</p>
<p>문맥 검사는 UTF-8 길이에 임의 상수를 더하는 방식에 의존하지 않는다. HTTP로 전송하는 원래 메시지와 응답 문자열은 보존한다. 고정된 Ollama의 render-only 응답에서는 공식 Qwen35 템플릿의 바깥 공백 제거를 반영하되, RFC 8259가 정한 JSON 바깥의 네 공백 문자만 허용하고 JSON 값과 모든 내부 문자가 유지되는지 검사한다. 모든 메시지가 순서대로 존재해야 하며, 실제 생성에도 truncate=false와 shift=false를 보낸다. 생성 전 고정한 <a href="../research/v44_renderer_policy_20261018.json">렌더 정책</a>과 <a href="../data/sector_protocol/v44_single_case_registration_renderer_addendum_20261018.json">등록 부록</a>에 근거·해시를 남겼다. 문맥 초과·누락·출력 상한·시간 제한은 실패 기록으로 보존한다. 이는 보이는 입력의 보존 검사이며, 독립적인 토큰 수 측정이나 의미적 기억의 보장은 아니다.</p>
<p>본과제 조건은 아직 동결하지 않았다. 현재는 사전 지정한 Fidelity Q2/R1 한 사례의 실행 가능성을 점검한다. 이 사례의 결과를 보고 모델을 유리하게 고르거나 R1/R4 효과를 주장하지 않는다.</p>'''


def runtime_section(pilot, reviews, findings):
    rows = ''
    for row in pilot['stages']:
        m = row['metrics'] or {}
        def number(key):
            value = m.get(key)
            return ('완료 요약 없음' if row['generation_request'] else '미실행') if value is None else f'{value:.3f}' if isinstance(value, float) else esc(value)
        rows += '<tr>' + ''.join(f'<td>{x}</td>' for x in
            (row['stage'], esc(state_label(row['supervisor_status'])), esc(state_label(row['transport_status'])), esc(row['done_reason'] or ('완료 응답 없음' if row['generation_request'] else '미실행')), number('wall_seconds'),
             number('ttft_content_seconds'), number('prompt_eval_count'), number('eval_count'),
             '기록 있음' if row['workflow_record'] else '미완료')) + '</tr>'
    review_links = ''.join(f'<li><a href="../{esc(rel(p))}">{esc(p.name)}</a></li>' for p in reviews)
    evidence = f'<a href="../{esc(pilot["path"])}/summary.json">단일 사례 실행 원본</a>' if pilot['path'] else '실제 실행 전'
    findings_markup = ''
    if findings:
        findings_markup = '<h3>관측과 검토에서 확인한 사항</h3>' + ''.join(
            '<p>' + esc(item['statement']) + ' ' + ' '.join(
                f'<a href="../{esc(source)}">검토 근거</a>' for source in item['evidence']) + '</p>'
            for item in findings['findings'])
    review_heading = '세 차례 자체 검증' if len(reviews) == 3 else f'자체 검증 기록 {len(reviews)}건 / 예정 3건'
    return f'''<section id="runtime-v44"><h2>v4.4 단일 예비 실행과 {review_heading}</h2>
<p>{esc(status_text(pilot))} {evidence}.</p>
<div class="table-wrap"><table><thead><tr><th>단계</th><th>감독 상태</th><th>응답 상태</th><th>종료 이유</th><th>요청 초</th><th>첫 내용 초</th><th>입력 토큰</th><th>출력 토큰</th><th>단계 기록</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>이 사례와 검증 범위는 생성 전에 <a href="../data/sector_protocol/v44_single_case_registration_20261018.json">별도 기록</a>으로 고정했다. 계획한 1차는 실행·입력·이력, 2차는 독립 산술·등급·인용 범위, 3차는 원문에 따른 주장·배분 근거·연구주제 연결의 대조다. 아래 연결한 실제 검토 기록은 {len(reviews)}건이다. 검토 기록의 존재와 모든 출력 내용이 정확하다는 판정은 구분한다. 오류·유보·미제시는 각 검토 원본에 남긴다.</p>
<ul>{review_links}</ul><p>이 세 차례는 자동·분담 자체 검증이다. 독립 사람이 수행한 원문·의미 검토로 세지 않는다. 한 R1 사례만으로 근거 제공 시점의 효과나 전체 예비 묶음의 적합성을 확정할 수 없다.</p>
{findings_markup}
<p>이전 원격 실행·속도 진단은 <a href="../research/remote_sector_execution_20261018.html">원격 기록</a>과 <a href="../research/local_sector_latency_20261018.html">노트북 속도 기록</a>에 보존한다. v4.3과 v4.4의 생성 조건을 섞어 같은 실험의 결과로 합산하지 않는다.</p></section>'''


def build_html(path, kind, conditions, pilot, reviews, findings):
    soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
    design = soup.find(id='design')
    old_method = soup.find(id='model-v43')
    if design is None or old_method is None:
        raise ValueError('Expected preserved v4.3 methods section')
    for node in list(old_method.next_siblings):
        node.extract()
    old_method.decompose()
    append(design, methods(conditions))
    replace(soup.find(id='runtime-v43'), runtime_section(pilot, reviews, findings))
    for ident in ('remote-runtime-historical-scope', 'local-engineering-20261018'):
        node = soup.find(id=ident)
        if node: node.decompose()
    for node in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if 'LOCAL_ENGINEERING_' in str(node): node.extract()
    for node in soup.select('.status'):
        node.clear(); node.append(status_text(pilot))
    for node in soup.select('.callout'):
        if 'v4.3' in node.get_text():
            node.clear(); node.append(status_text(pilot))
    for node in soup.select('.eyebrow'):
        node.string = node.get_text().replace('4.3', '4.4')
    if soup.title:
        soup.title.string = soup.title.get_text().replace('v4.3', 'v4.4')
    for node in soup.find_all('strong'):
        if node.get_text().startswith('v4.3 ·'):
            node.string = 'v4.4 · 단일 예비 사례와 본과제 결과를 구분한다.'
    conclusion = soup.find(id='conclusion')
    if conclusion:
        for text in list(conclusion.find_all(string=True)):
            if '실험 전 사례 설계' in str(text):
                text.replace_with(str(text).replace('실험 전 사례 설계', '공개자료 기반 사례 설계'))
        paragraphs = conclusion.find_all('p', recursive=False)
        for p in paragraphs:
            text = p.get_text()
            if '설치: 설치 기록 있음.' in text:
                p.string = status_text(pilot) + ' 예비 점검은 실행과 해석 가능성을 확인하며 본과제 효과의 증거가 아니다. 상경·경영학적 기여는 조직의 판단 근거가 최종 결정에 전달되는 업무 절차와 검토 책임을 분석하는 데 있다.'
    abstract = soup.select_one('.abstract')
    if abstract:
        for p in abstract.find_all('p'):
            for text in list(p.find_all(string=True)):
                if '실험 전 사례 설계' in str(text):
                    text.replace_with(str(text).replace('실험 전 사례 설계', '공개자료 기반 사례 설계'))
    old_appendix = soup.find(id='appendix')
    replace(old_appendix, '''<section id="appendix"><h2>부록. 재현 자료와 남은 실행 순서</h2>
<p><a href="../data/sector_documents/corpus_card.json">공개 문서 코퍼스</a>, <a href="../data/sector_market/market_input.json">공통 시장 입력</a>, <a href="../data/sector_protocol/evaluation_spec.json">기계적 평가 명세</a>, <a href="../research/local_sector_single_case.py">v4.4 단일 사례 실행기</a>와 저장된 manifest를 사용한다. 실행기는 이 한 사례만 지원하며 본과제를 실행하지 않는다. 원본·조건·실행 ID를 보존하고 반복 실행을 새 독립 표본으로 취급하지 않는다.</p>
<p>다음 순서는 단일 사례 검토 → 필요한 수정의 별도 버전 기록 → 나머지 예비 사례와 R1/R4 전체 검증 → 독립 사람의 원문 검토 → 본과제 입력·조건·평가기준 동결 → 별도 본실험 → 결과 해석이다. 현 실행을 본과제 동결이나 전체 예비 묶음의 승인으로 대신하지 않는다.</p>
<p>기존 시장자료·산식·평가 규칙의 근거는 보존한 <a href="../research/design_revision_20261017/parameter_basis_v42.json">v4.2 근거표</a>를 함께 참조한다. 현재 개정은 생성 조건과 이 한 사례의 실행·검증에 관한 것이며, 기존 수치 근거를 새로 추정하지 않는다.</p>
<p>텀페이퍼 제출은 2026년 11월 1일, 발표는 11월 6일이며 APA 인용을 따른다. 확인되지 않은 분량·제출 형식·자체 결과 필수 여부는 임의로 정하지 않는다. 저자·소속은 제출 전에 기입한다.</p></section>''')
    candidates = soup.find(id='candidates')
    if candidates:
        candidate_state = ('한 사례의 기록만으로 본과제 적합성을 확정하지 않는다.' if pilot['completed_cases'] else '현재 단일 사례는 완주하지 못했다. 기본 과제 수행을 확보하기 전까지 현 조건의 본과제 채택을 보류하고, 원인 진단과 별도 버전의 예비 재검증을 우선한다.')
        replace(candidates, '<section id="candidates"><h2>현재 선택과 남은 검증</h2><p>이번 예비 실행의 모델은 노트북의 Qwen3.5-4B Q4_K_M이다. ' + candidate_state + ' 전체 예비 묶음·본과제 동결·독립 사람 검토는 남아 있다. 정확 비중 정답이나 기관별 위험회피 수치는 추가로 만들지 않는다.</p></section>')
    for anchor in soup.find_all('a', href=True):
        anchor['href'] = anchor['href'].replace('#runtime-v43', '#runtime-v44')
        if anchor.get_text() == 'v4.3 실행 상태':
            anchor.string = 'v4.4 단일 예비 실행'
        for name in NAMES.values():
            anchor['href'] = anchor['href'].replace(Path(name.format(version='')).name,
                                                  Path(name.format(version='v4.4_')).name)
        if anchor.get_text() == 'v4.3 설정과 상태 출처':
            anchor.string = 'v4.4 설정과 상태 출처'
        if anchor.get_text() == 'v4.3 모델·조건 근거':
            anchor.string = '이전 모델·조건 검토(v4.3)'
    footer = soup.find('footer')
    if footer:
        footer.string = 'LIBERA · 2026-10-18 · ' + status_text(pilot) + ' 이전 감사는 당시 파일에만 적용.'
    return str(soup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--review', type=Path, action='append', default=[])
    parser.add_argument('--findings', type=Path)
    args = parser.parse_args()
    conditions = read(CONDITIONS); registration = read(REGISTRATION)
    for item in [*registration['reference_files'], *read(ADDENDUM)['references']]:
        if sha(ROOT / item['path']) != item['sha256']:
            raise ValueError('Registered reference changed: ' + item['path'])
    pilot = observe(args.run_dir)
    for path in args.review:
        if not path.is_file(): raise FileNotFoundError(path)
    findings = read(args.findings) if args.findings else None
    if findings:
        for item in findings['findings']:
            for source in item['evidence']:
                if not (ROOT / source).is_file(): raise FileNotFoundError(source)
    inputs = {key: ROOT / name.format(version='') for key, name in NAMES.items()}
    before = {key: sha(path) for key, path in inputs.items()}
    config = copy.deepcopy(read(inputs['config']))
    config.update(protocol_version='4.4', previous_protocol=rel(inputs['config']),
        status='one_prespecified_local_pilot; main_not_run_not_frozen',
        execution_conditions={'reference': rel(CONDITIONS), 'sha256': sha(CONDITIONS),
                              'request': conditions['recommended_request'],
                              'execution': conditions['recommended_execution'],
                              'documentation_correction': 'Per-call automatic pinning covers engine version, model digest and template. Binary hash and GPU placement are separate installation/log observations, not additional per-call gates. The immutable original conditions evidence is retained.',
                              'all_numbers_reported_by_papers': False},
        current_single_case=pilot,
        review_records=[{'path': rel(p), 'sha256': sha(p)} for p in args.review])
    if args.findings:
        config['findings_reference'] = {'path': rel(args.findings), 'sha256': sha(args.findings)}
    config.pop('local_engineering_addendum', None)
    config['main']['blocking_design_decisions'] = []
    config['main']['pending'] = ['Address the observed one-case failure if present; then complete and review the full pilot under explicitly versioned conditions',
        'Independent substantive human source review', 'Prepare and validate v4.4 main-run path',
        'Freeze inputs, model and rubric before main responses', 'Main execution and offline evaluation']
    config['main']['paths']['runner'] = None
    config['main']['paths']['single_case_runner'] = '../research/local_sector_single_case.py'
    config['main']['runtime_policy'] = 'Single-case v4.4 observations only. Remaining pilot cases, separate main-run path, human review and main freeze are pending.'
    config['model'].update(protocol_version='4.4', runtime_ready=False,
        runtime_manifest_path='data/sector_protocol/v44_single_case_20261018/manifest.json',
        settings_observation_scope='Versioned request conditions; actual observations are in the linked single-case transport records.',
        explicit_request_options=conditions['recommended_request']['options'],
        context_check_policy='Require render-only visible-history validation with explicit truncate=false/shift=false; no UTF-8 token heuristic. Actual checks are recorded stage by stage.',
        context_check_observed_stages=pilot.get('render_validations_observed', []),
        renderer_policy={'path': rel(RENDERER), 'sha256': sha(RENDERER), 'http_history': 'verbatim', 'rendered_history': 'Only declared JSON boundary whitespace removal; internal characters and parsed values unchanged.'},
        one_case_workflow_completed=bool(pilot['completed_cases']),
        decoding_revision_applied='Neutral penalties and seed explicitly specified; not claimed as unreported benchmark values.',
        future_candidate_scope='Superseded by the pinned v4.4 conditions evidence for this single pilot.')
    config['model'].pop('future_decoding_candidates_not_applied', None)
    config['model']['review'] = '../research/v44_conditions_reference_20261018.html'
    config['results'] = dict(ai_runs=pilot['completed_cases'], ai_completed_calls=pilot['http_streams_completed'],
        pilot_completed_cases=pilot['completed_cases'], pilot_completed_calls=pilot['http_streams_completed'],
        pilot_completed_workflow_stages=pilot['completed_calls'],
        pilot_attempted_calls_observed=pilot['attempted_calls'], main_completed_cases=0, main_completed_calls=0,
        count_scope='This v4.4 one-case pilot only; earlier v4.3 and engineering probes remain separate.',
        human_runs=None, main_execution_ready=False, main_effect_estimate=None)
    config['observed_execution'] = {'pilot': pilot, 'main': {'status': 'not_run', 'completed_cases': 0,
        'completed_calls': 0, 'frozen': False}, 'human_review': {'status': 'pending'},
        'historical_v43_record': rel(inputs['config'])}
    config['revision_provenance'] = {'builder': rel(Path(__file__)), 'source_version': '4.3',
        'source_files': {k: {'path': rel(inputs[k]), 'sha256': v} for k, v in before.items()},
        'conditions': {'path': rel(CONDITIONS), 'sha256': sha(CONDITIONS)},
        'registration': {'path': rel(REGISTRATION), 'sha256': sha(REGISTRATION)},
        'renderer_addendum': {'path': rel(ADDENDUM), 'sha256': sha(ADDENDUM)},
        'model_calls_by_builder': 0}
    outputs = {key: ROOT / name.format(version='v4.4_') for key, name in NAMES.items()}
    documents = {key: build_html(inputs[key], key, conditions, pilot, args.review, findings) for key in ('plan', 'paper')}
    if before != {key: sha(path) for key, path in inputs.items()}:
        raise RuntimeError('Source documents changed during build')
    for key, document in documents.items(): outputs[key].write_text(document, encoding='utf-8')
    outputs['config'].write_text(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'outputs': {k: rel(v) for k, v in outputs.items()},
        'source_v43_preserved': True, 'pilot': pilot['status'], 'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__': main()
