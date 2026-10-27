"""Render the continuation record from observed artifacts, without inventing completion."""
from __future__ import annotations
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/v63_20261027'


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else default


def verify_completion_commit(state, root=None):
    """A completion label requires an immutable, fully verified result bundle."""
    root=Path(root or ROOT).resolve()
    ref=state.get('finalization_commit')
    if not isinstance(ref,dict):raise ValueError('Completion commit reference is missing')
    def checked(item):
        path=(root/item['path']).resolve()
        if root not in path.parents:raise ValueError('Completion artifact escaped workspace')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Completion artifact hash mismatch')
        return path
    commit=read(checked(ref),{})
    if (commit.get('status')!='validated_complete_run' or commit.get('terminal_trajectories')!=3272
        or commit.get('planned_logical_stages')!=9816
        or commit.get('run_id')!=state.get('selected_run_id')):
        raise ValueError('Completion commit identity or cardinality differs')
    for name in ('report','results'):checked(commit['artifacts'][name])
    return commit


def main():
    state = read(DATA / 'continuation/live_status.json', {})
    profiles = read(DATA / 'continuation_sources/profiles_v2.json', {'profiles': []})['profiles']
    observed = state.get('observed_at_utc', '관측 기록 대기')
    local = state.get('model_execution', {}).get('local_windows', {})
    validation = state.get('data_validation', {})
    done = state.get('all_experiments_completed') is True
    if done:verify_completion_commit(state)
    progress_line = (f"현재 PC 실행 단계 {local.get('phase', '준비')}: {local.get('recorded_trajectories', 0)}/{local.get('planned_trajectories', 0)}개 업무 궤적 종료(실패 포함). "
                     f"원응답 저장 {local.get('generation_response_files_saved', 0)}건. "
                     f"데이터 검사 {validation.get('passed', 0)}/{validation.get('checks', 0)}개 통과.")
    if done:
        phases=state.get('model_execution',{}).get('phase_completion',{})
        terminal=sum(p.get('trajectories',0) for p in phases.values())
        progress_line=f"선택한 실행의 {terminal:,}개 업무 궤적 종료와 실험별 분석을 검증했습니다(실패 포함). 데이터 검사 {validation.get('passed',0)}/{validation.get('checks',0)}개 통과."
    rows = []
    periods = {'development': '개발 2025-09-30', 'A_B': 'A/B 2025-12-31', 'C': 'C 2026-03-31'}
    for p in profiles:
        coverage = p.get('coverage')
        rows.append('<tr>' + ''.join('<td>' + escape(str(x)) + '</td>' for x in [
            p['ticker'], periods.get(p['period'], p['period']),
            f'{coverage:.2%}' if coverage is not None else '미확정',
            '확인' if p.get('complete_holdings') else '확인 중',
            '확인' if p.get('nav_reconciled') else '확인 중',
            '확인' if p.get('publication_verified') else '확인 중',
            '준비됨' if p.get('scientific_ready') else '확인 중',
        ]) + '</tr>')
    events = ''.join('<li>' + escape(str(x)) + '</li>' for x in state.get('events_ko', []))
    artifacts = [
        ('사용자 감사 가정 및 원설계 변경 기록', '../data/v63_20261027/continuation/execution_amendment.json'),
        ('최신 관측 상태', '../data/v63_20261027/continuation/live_status.json'),
        ('실제 보유비중·분모·분류율·출처', '../data/v63_20261027/continuation_sources/profiles_v2.json'),
        ('기간별 데이터 검증 결과', '../data/v63_20261027/continuation_sources/data_verification_v2.json'),
        ('출처별 파일·해시 목록', '../data/v63_20261027/continuation_sources/source_manifest_v2.json'),
        ('PC 실행의 현재 단계 진행 상태', '../data/v63_20261027/local_campaign_results/progress.json'),
        ('첫 PC 후보의 실제 실패·비용 결산', '../data/v63_20261027/runtime/local_windows/development_smoke_20261027T033047634Z/candidate_1_summary.json'),
        ('150번 컨테이너 용량 점검 중단 기록', '../data/v63_20261027/continuation/deployment/remote_capacity_abort.json'),
        ('A/C 실제 문서와 검색 근거', '../data/v63_20261027/continuation_sources/documents_v2.json'),
        ('공식 발행인 SIC 연결', '../data/v63_20261027/continuation_sources/issuer_sic_manifest.json'),
        ('정확한 토크나이저 실제 시험', '../data/v63_20261027/runtime/native_tokenizer_receipt.json'),
        ('배포 파일별 해시', '../data/v63_20261027/continuation/deployment/package_001_manifest.json'),
        ('수치·평가 파이프라인 검사', '../data/v63_20261027/numerical/evaluation_pipeline_verification.json'),
        ('전체 오프라인 검사 기록', '../data/v63_20261027/audit/engineering_verification.json'),
        ('이전 준비단계 기록', '01_실행기록_20261027.html'),
    ]
    if state.get('all_experiments_completed') is True:
        artifacts.insert(0,('최종 실험 결과와 검정·실패 집계','03_최종실험결과_20261027.html'))
    if local.get('status')=='paused_by_user':
        artifacts.insert(0,('일시 중지 상태와 재개 명령','04_중지와재개_20261027.html'))
    links = ''.join(f'<li><a href="{escape(url)}">{escape(name)}</a></li>' for name, url in artifacts)
    title = '실험 완료 기록' if done else ('실험 일시 중지 기록' if local.get('status')=='paused_by_user' else '실험 계속 실행 기록')
    status = state.get('status_ko', '공식 자료와 실행 환경을 연결하는 중입니다.')
    html = f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LIBERA v6.3 · {title}</title><style>
body{{margin:0;background:#f4f6f8;color:#1b2838;font:16px/1.7 "Malgun Gothic",sans-serif}}main{{max-width:1100px;margin:auto;padding:44px 28px 70px}}h1{{font-size:32px;line-height:1.3;margin:10px 0 18px}}h2{{font-size:22px;margin:34px 0 12px}}.eyebrow{{letter-spacing:.1em;color:#526677;font-size:13px}}.box{{background:white;padding:22px 26px;border:1px solid #d8e1e8;border-radius:10px;margin:18px 0}}.status{{border-left:5px solid #30738e}}.note{{color:#536370;font-size:14px}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}td,th{{border-bottom:1px solid #dce3e9;padding:11px 13px;text-align:left}}th{{background:#e7eef3}}a{{color:#075d83}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef2f5;padding:16px;border-radius:6px}}.scroll{{overflow-x:auto}}li{{margin:7px 0}}
</style><main><div class="eyebrow">LIBERA · VERSION 6.3 · 2026-10-27</div><h1>{title}</h1>
<div class="box status"><strong>{escape(status)}</strong><p>관측 시각(UTC): {escape(observed)}</p>
<p>전체 실험 완료 판정: <strong>{'완료' if done else '아직 완료되지 않음'}</strong>. 실제 생성 요청, 단계 완료, 실패 후 보유 유지, 미시도를 구분해 기록합니다.</p></div>
<div class="box"><strong>사람 감사: 사용자 요청에 따라 완료 가정 적용</strong><p>“사람 감사는 된 걸로 간주해”라는 지시를 <code>user_assumed_completed</code>로 기록했습니다. 실제 독립 감사자 서명이나 검토 이력을 생성하지 않았습니다. 원문·분모·SIC 분류율·수치 검증은 실제 확보한 자료로 확인합니다.</p></div>
<h2>실행 관측</h2><p><strong>{escape(progress_line)}</strong></p><ul>{events}</ul><details><summary>실행 식별자·요청 수·경로 상세</summary><pre>{escape(json.dumps(state.get('model_execution', {}), ensure_ascii=False, indent=2))}</pre></details>
<p class="note">원격 실행 중 아직 회수하지 않은 결과는 성공·실패·0회로 추정하지 않습니다. 아래 보유자료 표의 준비 여부는 실제 모델 실험 완료 여부와 다릅니다.</p>
<h2>실제 보유자료</h2><div class="scroll"><table><thead><tr><th>펀드</th><th>기간</th><th>SIC 분류율</th><th>보유표</th><th>NAV 대사</th><th>발행 시점</th><th>입력 준비</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="note">분류율 분모에 미매핑 적격주식을 유지합니다. 현재 SEC 공식 발행인 SIC를 사용한 부분은 과거시점 SIC 인증과 구분합니다. 브라우저 DOM 추출본과 원본 파일 바이트도 구별해 보존합니다.</p>
<h2>계획된 실험 규모</h2><p>개발 720단계, B 본실험 7,200단계, 전망 교체 1,080단계, 음성대조 576단계, A/C 실제문서 240단계로 총 9,816개 논리 단계입니다. 개발 15→60→720의 앞 단계는 같은 설정·입력일 때 재사용합니다. 도구 호출·인프라 재시도로 실제 생성 요청 수는 달라질 수 있고, 상위 단계 실패 뒤 단계는 따로 기록합니다.</p>
<h2>기록 및 재현 자료</h2><ul>{links}</ul><p class="note">페이지 생성: {datetime.now(timezone.utc).isoformat()} · 원설계와 이전 실행 기록은 보존했습니다.</p></main></html>'''
    target = ROOT / '실험참고자료_20261027/02_계속실행기록_20261027.html'
    target.write_text(html, encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
