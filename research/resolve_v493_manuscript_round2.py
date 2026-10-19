"""Close manuscript-only findings against exact final source bytes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'research/v493_manuscript_round2_review_20261019.json'
INITIAL = 'research/v493_manuscript_round2_initial_review_20261019.json'
FINAL_COPY = 'research/v493_manuscript_round2_final_input_20261019.json'
SOURCE = 'paper/v493_manuscript_20261019.json'


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return {'path':name,'sha256':hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}


prior_bytes = (ROOT / REPORT).read_bytes()
assert hashlib.sha256(prior_bytes).hexdigest() == 'f2d32f52702c861a72ba0edbcc18d364595c6eda87417f914cf8bb1062531793'
paper_bytes = (ROOT / SOURCE).read_bytes()
paper = json.loads(paper_bytes)
old = read('research/v493_manuscript_round2_input_20261019.json')
text = '\n'.join(b.get('text','') for b in paper['blocks'])
old_tables = {b['caption']:b for b in old['blocks'] if b['type']=='table'}
tables = {b['caption']:b for b in paper['blocks'] if b['type']=='table'}
references = {b.get('id'):b for b in paper['blocks'] if b['type']=='reference' and b.get('id')}
manifest = read('data/sector_market/manifest.json')
checks = []


def check(name, passed):
    checks.append({'check':name,'pass':bool(passed)})


check('Expected final manuscript size', len(paper['blocks'])==117)
for caption, value in old_tables.items():
    check('All numerical table rows retained: '+caption, tables[caption]['rows']==value['rows'])
old_model = next(b['text'] for b in old['blocks'] if b.get('text','').startswith('모델 식별:'))
check('Frozen model/options paragraph unchanged', old_model in text)
check('D0 schema and normal-stop gate stays explicit','필수 설명 구조' in text and '출력 토큰 상한 때문에 종료된 D0도 숫자가 읽히더라도 F0로 진행하지 않는다' in text)
check('Provider and retrieval date named','Yahoo Finance 공개 chart 자료의 조정종가를 2026년 10월 17일 수집' in text and 'State Street의 공식 상품 페이지' in text)
for id_, kind in [('state_street_identity','issuer_identity'),('yahoo_adjusted_close','yahoo_chart')]:
    expected = {r['url'] for r in manifest['sources'] if r['kind']==kind}
    actual = {r['url'] for r in references[id_]['links']}
    check('All eleven original data URLs match: '+id_, len(actual)==11 and actual==expected)
check('GICS sector terminology and official definition reference','GICS의 최상위 11개 섹터' in text and references['msci_gics']['url']==manifest['provenance']['GICS_definition']['url'])
check('Fidelity benchmark locator and common-C provenance limit explicit','3분기 보고서 2쪽' in text and 'C는 기관 전망 미제공 조건' in text)
check('ETF proxy and adjusted-close scope explicit','지수 자체를 정확히 복제한다고 보지 않는다' in text and '발행사가 인증한 순자산가치 총수익률과 동일하다고 주장하지 않는다' in text)
check('No valid comparison leaves question unanswered','조건 차이에 관한 연구질문은 미해결로 남고' in text)
check('Cross-source row terminology corrected throughout','산업 간 비교행' not in text and '산업별 기관 간 비교행' in text)
check('Two decimal place note corrected','소수 셋째 자리에서 반올림하여 둘째 자리까지' in tables['표 5 이미 계산한 공통 참고 배분']['note'])
check('Internal E2A editing instruction absent','use arXiv version unless' not in text)
check('Offline postprocessing trigger matches terminal-summary rule','유효한 종료 요약이 확인되면' in text and '유효한 종료 요약과 실행 정리가 확인되면' not in text)
check('Failures and unattempted finals retained in denominator','실패와 미시도 사례도 계획된 다섯 최종안의 분모에 남긴다' in text)
check('Natural-language numeric judgment remains future semantic work','자연어 수치 주장의 추출과 판정은 별도의 AI 보조 코딩 대상으로 남긴다' in text)
check('Model internal knowledge time limitation explicit','모델 내부 지식의 시점을 별도로 검증한 것은 아니므로' in text)
check('Pilot and substantive results remain incomplete','예비실험을 실행 중' in text and '실증 결론은 아직 없다' in text)
check('No manuscript change during final validation',(ROOT / SOURCE).read_bytes()==paper_bytes)
assert all(row['pass'] for row in checks), [row for row in checks if not row['pass']]

with (ROOT / INITIAL).open('xb') as out:
    out.write(prior_bytes)
with (ROOT / FINAL_COPY).open('xb') as out:
    out.write(paper_bytes)
report = json.loads(prior_bytes)
old_observation = report.pop('current_source_at_recording_ref')
report['historical_mutable_source_observation']={'source_path':old_observation['path'],'observed_sha256':old_observation['sha256']}
report['initial_review_status']=report['status']
report['status']='PASS_after_manuscript_clarifications'
report['initial_review_receipt_ref']=ref(INITIAL)
report['final_manuscript_ref']=ref(SOURCE)
report['final_manuscript_snapshot_ref']=ref(FINAL_COPY)
report['manuscript_scope']='Initial findings refer to the preserved intermediate revision; the resolution below independently rechecks the final 117-block manuscript. The initial report and both source revisions remain preserved.'
for finding in report['findings']:
    finding['final_resolution']='resolved_in_final_manuscript'
report['resolution']={
 'status':'PASS','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
 'final_source_sha256':ref(SOURCE)['sha256'],'checks':checks,'passed_checks':len(checks),'unresolved_findings':[],
 'additional_clarification':'The final text starts offline postprocessing on a valid terminal summary; it no longer implies that successful idle cleanup is a prerequisite for offline arithmetic/masking. Service implementation details are omitted from the academic body.',
 'review_boundary':'Text, formulas, tables, references and protocol alignment only. This does not certify DOCX rendering, completed pilot outcomes, semantic scorer validity or official submission-format compliance.',
 'model_generation_calls':0,'actual_pilot_response_content_read':False,'frozen_experiment_files_modified':False,
 'manuscript_source_modified_by_reviewer':False,'resolver_ref':ref('research/resolve_v493_manuscript_round2.py')}
temp = ROOT / (REPORT+'.resolving')
with temp.open('x',encoding='utf8',newline='\n') as out:
    json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False); out.write('\n')
temp.replace(ROOT / REPORT)
print(json.dumps({'report':ref(REPORT),'final_source':ref(SOURCE),'resolution_checks':len(checks),'status':report['status']},ensure_ascii=False))
