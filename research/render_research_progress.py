"""Render the verified append-only work ledger as a readable local HTML index."""
from datetime import datetime, timedelta, timezone
from html import escape
import os
from pathlib import Path
from urllib.parse import quote
from research_progress_log import ROOT, LEDGER, read_verified

OUTPUT = ROOT / 'research/progress_20261018.html'
PHASES = {'priority1':'① 계산 피드백 반영', 'priority2':'② 수치와 설명의 일치',
          'priority3':'③ 근거·대안·비중의 연결', 'pilot_integration':'④ 네 단계 예비실험 통합 검증'}
STATUS = {'design_selected':'수정 방법 선택', 'prepared':'입력·코드 준비',
          'failed':'실행 환경 오류·후속 단계 보류',
          'diagnostic_launched':'진단 실행 시작', 'diagnostic_completed':'진단 종료',
          'review_completed':'검증 기록', 'phase_accepted':'세 검증 통과·다음 단계 허용',
          'revision_required':'수정 필요', 'candidate_prepared':'다음 수정안 준비',
          'delivery_verified':'문서·기록 전달 검증 완료',
          'design_verified':'v4.8 재설계의 세 차례 검증 완료',
          'partial_trace_recorded':'중간 과정 관측 보존',
          'first_case_accounted':'첫 예비 사례의 완료·실패 기록',
          'three_reviews_passed':'세 차례 운영 검증 완료',
          'previous_run_reviews_completed':'원 실행의 세 검증 완료·실패 보존',
          'technical_validation_complete':'본실험 도구의 기술 검증 완료',
          'technical_validation_started':'본실험 도구의 통합 검증 진행',
          'preparation_helpers_verified':'입력 후보 감사·검토표 연결 도구 검증 완료',
          'primary_observation_captured':'예비실험 진행 중·첫 최종안 관측 보존',
          'interim_observation_recorded':'운영 중간 관측 보존·전체 운영 검증 대기',
          'candidate_accepted_pending_human':'후보 기술 검증 완료·사람 검토와 동결 대기'}
V48_PHASES={'v48_implementation':'v4.8 실행기·평가 연결', 'v48_pilot':'v4.8 네 사례 예비실험',
            'v48_operating_guard':'절전 중단 후 운영 보호·별도 반복',
            'v48_main_preparation':'본실험 경로의 오프라인 준비',
            'v48_delivery':'v4.8 결과·소논문 연결 검토', 'v48_human_review':'독립 사람 검토 준비'}
PHASE_ALIASES={'main_preparation':'v48_main_preparation', 'pilot':'v48_pilot',
               'operating_guard':'v48_operating_guard'}


def phase_key(event):
    return PHASE_ALIASES.get(event['phase'],event['phase'])


def v48_notice(events):
    latest={phase_key(event):event for event in events if phase_key(event) in V48_PHASES}
    implementation=latest.get('v48_implementation',{}).get('status')
    pilot=latest.get('v48_pilot',{}).get('status')
    texts=[]
    texts.append('실행기 통합은 세 차례 검증을 마쳤다.' if implementation=='phase_accepted' else '실행기 통합·검증이 남아 있다.')
    states={'diagnostic_launched':'고정된 네 사례 예비실험을 진행 중이다.',
            'failed':'별도 반복은 GPU 장치 오류로 중단되었다. 실패를 보존하며 본실험 후보 생성은 보류한다.',
            'first_case_accounted':'첫 사례의 완료·실패 기록을 보존했으며 나머지 사례는 진행 중이다.',
            'partial_trace_recorded':'예비실험의 중간 기록을 보존했으며 전체 실행은 완료 전이다.',
            'primary_observation_captured':'고정된 네 사례 예비실험이 진행 중이며 완료된 첫 최종안의 관측을 보존했다.',
            'diagnostic_completed':'예비실험 실행이 종료되었으며 후속 검증은 별도 기록으로 확인한다.',
            'phase_accepted':'예비실험 기록의 세 차례 검증을 마쳤다. 이는 모델의 판단이 옳다는 판정이 아니다.',
            'revision_required':'예비실험에서 다음 단계 진행을 막는 문제가 확인되었다. 실패 기록은 보존한다.'}
    texts.append(states.get(pilot,'전체 예비실험은 아직 실행 전이다.'))
    if latest.get('v48_main_preparation',{}).get('status')=='candidate_accepted_pending_human':
        texts.append('본실험 후보 경로의 오프라인 검증을 마쳤으며 실제 실행 승인·사람 검토·동결은 남아 있다.')
    elif latest.get('v48_main_preparation',{}).get('status') in ('technical_validation_complete','preparation_helpers_verified'):
        texts.append('본실험용 도구 검증은 마쳤으며 실제 입력 후보의 검증과 실행 승인은 별도 단계다.')
    texts.append('독립 사람의 원문·의미 검토와 본실험 전 동결은 별도 요건이다. 본실험은 실행하지 않았다.')
    links='<a href="../plan/LIBERA_실험계획_v4.8_20261018.html">고정한 v4.8 설계</a> · <a href="v48_handoff_20261018.json">당시 설계 전달 기록</a>'
    for name in ('LIBERA_텀페이퍼_초안_v4.8.1_20261019_r3.html','LIBERA_텀페이퍼_초안_v4.8.1_20261019_r2.html','LIBERA_텀페이퍼_초안_v4.8.1_20261019.html'):
        if (ROOT/'paper'/name).is_file():
            links+=' · <a href="../paper/'+name+'">예비실험 반영 소논문</a>'
            break
    rows=''.join('<tr><td>'+escape(label)+'</td><td>'+escape(STATUS.get(latest.get(key,{}).get('status'),'미완료·아직 통과 기록 없음'))+'</td></tr>' for key,label in V48_PHASES.items())
    return '<div class="notice"><strong>v4.8 현재 진행 상태</strong><p>'+escape(' '.join(texts))+'</p><p>첫 최종안 C0가 주결과이며, C1/C2는 보조 수정이다. 산술 성공과 기관 판단 보존은 분리하여 평가한다.</p><p>'+links+'</p></div><table><tr><th>현재 단계</th><th>기록된 상태</th></tr>'+rows+'</table><h2>이전 개발 단계의 결과 — v4.7 기준 보존</h2>'


def render():
    events = read_verified()
    redesign_events=[event for event in events if event['phase']=='redesign_v48']
    rows=[]
    for event in events:
        dt=datetime.fromisoformat(event['recorded_at_utc']).astimezone(timezone(timedelta(hours=9)))
        links=[]
        for ref in event['reference_files']:
            path=ROOT/ref['path']
            href=quote(os.path.relpath(path,OUTPUT.parent).replace('\\','/'),safe='/._-')
            links.append(f'<li><a href="{href}">{escape(ref["path"])}</a><br><small>SHA256 {escape(ref["sha256"])}</small></li>')
        phase_name='v4.8 논문·실험 재설계' if event['phase']=='redesign_v48' else ('v4.8 예비 과정 관측' if event['phase']=='v48_observation' else V48_PHASES.get(phase_key(event),PHASES.get(event['phase'],event['phase'])))
        rows.append(f'<article><h3>{event["sequence"]}. {escape(phase_name)} — {escape(STATUS.get(event["status"],event["status"]))}</h3>'
            f'<p class="time">기록 시각 {dt:%Y-%m-%d %H:%M:%S} KST</p><p>{escape(event["detail"])}</p>'
            f'<details><summary>근거 파일·해시</summary><ul>{"".join(links)}</ul><small>사건 해시 {event["event_sha256"]}</small></details></article>')
    phases=[]
    for key,label in PHASES.items():
        matching=[row for row in events if row['phase']==key]
        accepted=any(row['status']=='phase_accepted' for row in matching)
        state=('세 검증 통과' if accepted else
               '세 검증 완료·조건 미충족 — 후속 단계 보류' if matching and matching[-1]['status']=='revision_required' else
               '진행 중 — 다음 단계 통과 아님' if matching else '앞 단계 검증 후 진행')
        phases.append(f'<tr><td>{label}</td><td>{state}</td></tr>')
    result='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIBERA 실험 준비 과정 기록</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1060px;margin:36px auto;padding:0 22px;color:#1c2939;background:#f7f9fc}h1,h2,h3{line-height:1.4}article,.notice{background:white;border:1px solid #d7dee8;border-radius:10px;padding:20px;margin:18px 0}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #d7dee8;padding:12px;text-align:left}.time,small{color:#52627a}li,p,small{overflow-wrap:anywhere}a{color:#1756a9}summary{cursor:pointer}</style></head><body>
<h1>LIBERA 실험 준비 과정 기록</h1><p>사용자 지시: 우선순위대로 해결하고, 한 단계마다 세 차례 검증한 뒤 다음으로 진행한다. 본실험은 실행하지 않는다.</p>
<div class="notice"><strong>기록 방식</strong><p>기존 실패 원문과 새 시도의 입력·응답·계산 결과를 보존한다. 아래 장부는 이전 사건의 해시를 다음 사건에 연결한다. 수정 사항도 새 사건으로 남긴다. 로컬 파일의 기록이며 외부 기관이 보증한 사전등록은 아니다. 실행기 테스트 통과, 모델의 수치 통과, 내용 검증, 본실험 준비 완료는 서로 다른 상태다.</p></div>
'''+(v48_notice(events) if redesign_events else '<h2>단계별 현재 상태</h2>')+'''<table><tr><th>단계</th><th>상태</th></tr>'''+''.join(phases)+'''</table><p>세 차례 검증은 분담 자체 검토다. 독립 사람의 원문 내용 검토와 동일하다고 주장하지 않는다. 알려진 실패의 재검토 진단은 네 단계 전체 예비실험을 대체하지 않는다.</p>
<h2>시간순 기록</h2>'''+''.join(rows)+f'<p>검증된 장부 사건 {len(events)}개. <a href="progress_20261018.jsonl">원본 JSONL 장부</a></p></body></html>'
    OUTPUT.write_text(result,encoding='utf-8')
    print(str(OUTPUT))


if __name__=='__main__':
    render()
