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
          'diagnostic_launched':'진단 실행 시작', 'diagnostic_completed':'진단 종료',
          'review_completed':'검증 기록', 'phase_accepted':'세 검증 통과·다음 단계 허용',
          'revision_required':'수정 필요', 'candidate_prepared':'다음 수정안 준비',
          'delivery_verified':'문서·기록 전달 검증 완료',
          'design_verified':'v4.8 재설계의 세 차례 검증 완료'}


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
        phase_name='v4.8 논문·실험 재설계' if event['phase']=='redesign_v48' else PHASES.get(event['phase'],event['phase'])
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
'''+('''<div class="notice"><strong>현재 적용할 다음 설계: v4.8</strong><p>연구질문과 연결된 재설계를 세 차례 검증했다. 모델의 산술 성공과 측정 체계 검증을 분리하며 C0 원안이 주결과, C1/C2 수정은 보조 결과다. 아래 v4.7 실패는 그대로 보존한다. 새 실행기 통합·네 사례 예비실험·독립 사람 검토·본실험 전 동결은 아직 남아 있다. 본실험 0건.</p><p><a href="../plan/LIBERA_실험계획_v4.8_20261018.html">v4.8 실험계획</a> · <a href="v48_handoff_20261018.json">검증과 전달 기록</a></p></div><h2>이전 개발 단계의 결과 — v4.7 기준 보존</h2>''' if redesign_events else '<h2>단계별 현재 상태</h2>')+'''<table><tr><th>단계</th><th>상태</th></tr>'''+''.join(phases)+'''</table><p>세 차례 검증은 분담 자체 검토다. 독립 사람의 원문 내용 검토와 동일하다고 주장하지 않는다. 알려진 실패의 재검토 진단은 네 단계 전체 예비실험을 대체하지 않는다.</p>
<h2>시간순 기록</h2>'''+''.join(rows)+f'<p>검증된 장부 사건 {len(events)}개. <a href="progress_20261018.jsonl">원본 JSONL 장부</a></p></body></html>'
    OUTPUT.write_text(result,encoding='utf-8')
    print(str(OUTPUT))


if __name__=='__main__':
    render()
