"""Render the user-requested pause/resume handoff. No inference or process launch."""
from pathlib import Path
from html import escape
import json

ROOT=Path(__file__).resolve().parents[2]
def main():
    data=ROOT/'data/v63_20261027'
    pause=json.loads((data/'continuation/user_pause_20261027.json').read_text(encoding='utf-8'))
    notes=(ROOT/'research/v63/RESUME_20261027.txt').read_text(encoding='utf-8')
    stats_path=data/'continuation/git_ignore_summary_20261027.json'
    stats=json.loads(stats_path.read_text(encoding='utf-8')) if stats_path.exists() else {}
    before=stats.get('before',{});after=stats.get('after',{})
    git_line=(f"새 커밋 후보 {before.get('files','—'):,}개 → {after.get('files','—'):,}개. "
              f"파일 내용 {before.get('bytes',0)/1048576:.2f} MiB → {after.get('bytes',0)/1048576:.2f} MiB.") if before and after else 'Git 제외 목록의 최종 집계 기록을 준비하고 있습니다.'
    html=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIBERA v6.3 · 중지와 재개</title><style>body{{margin:0;background:#f4f6f8;color:#1b2838;font:16px/1.7 "Malgun Gothic",sans-serif}}main{{max-width:1050px;margin:auto;padding:40px 26px 65px}}h1{{font-size:30px}}.box{{padding:20px 24px;background:white;border:1px solid #d8e1e8;border-radius:9px;margin:18px 0}}.status{{border-left:5px solid #ac7136}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 Consolas,"Malgun Gothic",monospace;background:#eaf0f4;padding:20px}}a{{color:#075d83}}li{{margin:7px 0}}code{{overflow-wrap:anywhere}}</style>
<main><h1>실험 일시 중지 · 재개 안내</h1><div class="box status"><strong>사용자 요청으로 중지했습니다. 전체 실험 완료 상태가 아닙니다.</strong><p>현재 후보의 원응답 7건을 보존했습니다. R0/R1은 수치 조건 실패로 종료했고, R2 첫 응답은 저장·복구 검증을 마쳤습니다. 다음 새 요청은 R2의 두 번째 단계입니다.</p><p>PC 캠페인·모니터·모델 서버는 종료했고, 150번 컨테이너의 새 점검 요청도 실행되지 않았음을 확인했습니다.</p></div>
<div class="box"><strong>Git 정리</strong><p>{escape(git_line)}</p><p>원문 다운로드·원응답·실행 캐시는 로컬에 그대로 있습니다. 소스·실행 입력·설정·주요 검증과 재개 기록을 커밋 후보로 남겼습니다. Git 인덱스 변경이나 커밋은 하지 않았습니다.</p></div>
<div class="box"><strong>재개를 요청한 다음 실행</strong><pre>.\\research\\resume_v63_candidate_002.ps1</pre><p>작업 폴더: <code>C:\\Users\\kuri\\2026libera</code></p><p>현재 단계 예산 만료는 <strong>2026-10-27 19:34:12 KST</strong>입니다. 그 이후에는 중지 사유와 이전·새 한도를 기록한 예산 변경이 필요합니다. 기존 시작 시각과 호출 수를 지우지 않습니다.</p></div>
<ul><li><a href="../research/v63/RESUME_20261027.txt">전체 재개 안내 TXT</a></li><li><a href="../research/resume_v63_candidate_002.ps1">재개 스크립트</a></li><li><a href="../data/v63_20261027/continuation/user_pause_20261027.json">중지 상태와 증거 목록</a></li><li><a href="../data/v63_20261027/continuation/git_ignore_summary_20261027.json">Git 정리 전후 집계</a></li><li><a href="02_계속실행기록_20261027.html">실험 실행 기록</a></li></ul>
<p>Git에서 제외된 자료는 새 clone에 포함되지 않습니다. 동일 실행을 재개하려면 현재 PC의 원기록·모델 캐시·가상환경을 함께 보존해야 합니다.</p>
<details><summary>전체 재개 안내 펼치기</summary><pre>{escape(notes)}</pre></details></main></html>'''
    target=ROOT/'실험참고자료_20261027/04_중지와재개_20261027.html'
    target.write_text(html,encoding='utf-8')
    print(target)

if __name__=='__main__':main()
