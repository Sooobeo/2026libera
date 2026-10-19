"""Independent AI methods/document review of a preserved manuscript revision."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = 'research/v493_manuscript_round2_input_20261019.json'
TARGET = 'research/v493_manuscript_round2_review_20261019.json'


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return {'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}


paper = read(SNAPSHOT)
blocks = paper['blocks']
text = '\n'.join(b.get('text', '') for b in blocks)
tables = {b['caption']: b for b in blocks if b['type'] == 'table'}
calc = read('research/v492_computational_references_20261019.json')
protocol = read('research/v492_evaluation_protocol_20261019_r2.json')
runtime = read('research/v492_runtime_candidate_20261019.json')
refs = {r['reference_id']: r for r in calc['references']}
checks = []


def check(label, passed, evidence):
    checks.append({'check': label, 'pass': bool(passed), 'evidence': evidence})


t1 = tables['표 1 공통 투자 대상']['rows']
check('Eleven sector codes and ETF identities', [r[0] for r in t1] == calc['sector_codes'] and
      [r[2] for r in t1] == ['XLE','XLB','XLI','XLY','XLP','XLV','XLF','XLK','XLC','XLU','XLRE'], 'Frozen market manifest and computational reference sector order')
t5 = tables['표 5 이미 계산한 공통 참고 배분']['rows']
for index, code in enumerate(calc['sector_codes']):
    check('Equal-weight displayed percent ' + code, t5[index][1] == format(100*refs['equal_weight']['weights'][code], '.2f'), 'Exact 1/11; display rounding only')
    check('Minimum-variance displayed percent ' + code, t5[index][2] == format(100*refs['long_only_minimum_variance']['weights'][code], '.2f'), 'Frozen all-face/SLSQP cross-checked solution')
for name in ['equal_weight', 'long_only_minimum_variance', 'existing_market_benchmark']:
    number = format(100*refs[name]['annualized_in_sample_volatility'], '.2f')
    check('Displayed volatility ' + name, number + '%' in text, 'sqrt(252*w^T*Sigma*w), same frozen daily covariance')
check('Window and date bounds', calc['observations'] == 60 and calc['dates'] == ['2026-04-21','2026-07-16'] and '60개 일별 수익률' in text, 'Frozen computational input, no new outcome window')
check('Five cells and ten maximum calls', protocol['expected_cases_per_split'] == 5 and runtime['pilot_max_generation_requests'] == 10 and '55개 산업행' in text, 'Two sources times E/L plus one shared C; no pseudo-replication')
check('Current model and engineering ceiling', runtime['model'] in text and '4500초' in text and 'num_ctx 65536' in text and 'num_thread 8' in text, 'Frozen runtime; engineering settings distinguished from paper constants')
check('C treated as an AI strategy control', '전략 비교의 대조군은 C이다' in text and '독립적인 대조군 네 개가 생기는 것은 아니다' in text, 'Frozen E/L/C matched-stage design')
check('No invented institutional numerical gold', '산업별 숫자 목표' in text and '최적 포트폴리오를 복원하지 않는다' in text, 'Original outlooks do not publish a complete eleven-sector numeric target')
check('No realized return or loss-probability claim', '수익률 하락 확률' in text and '투자성과에 대한 결론을 도출하지 않는다' in text, 'Frozen historical risk diagnostic only')
check('No causal population or pure anchoring claim', '순수한 기억 효과나 심리적 앵커링' in text and '통계적 유의성 검정이나 모집단 효과 추정은 계획하지 않는다' in text, 'One market/model and one first final per cell')
check('Honest ongoing-pilot status', '예비실험을 실행 중' in text and '실증 결론은 아직 없다' in text, '18:00 KST manuscript cutoff; prior 08:58 UTC launch acceptance confirms pilot still in progress without reading response content')
check('AI review disclosure and no independent-human claim', '사람에 의한 타당화' in text and '독립적인 세 측정' in text, 'Frozen delegated AI coding protocol')
check('Corrected D0 continuation versus final-vector eligibility', '필수 설명 구조' in text and '출력 토큰 상한 때문에 종료된 D0도 숫자가 읽히더라도 F0로 진행하지 않는다' in text, 'sector_v491_contract.py:234-264 and sector_v492_runtime.py:337-355,533-545')
check('Corrected source-comparison row identity in section 4.2', '11개 산업별 두 기관 비교행' in text, 'Two source documents times eleven sectors, then eleven within-sector cross-source comparisons')
check('Removed internal E2A bibliographic instruction', 'use arXiv version unless' not in text, 'Reference retains arXiv v1 rather than an unverified proceedings claim')
check('Numerical self-checks all pass', all(c['pass'] for c in checks), 'No failed numeric or core-design check in this preserved revision')

findings = [
    {'id':'R2-01','severity':'required_clarification','status':'corrected_in_preserved_revision',
     'location':'4.5 / block 45','issue':'Initial wording narrowed the D0 continuation gate to unavailable complete weights, omitting explanation-schema and normal-stop requirements.',
     'verification':'The preserved revision now separates continuation from post-hoc vector analysis and explicitly states schema/termination gates. Frozen experiment code was not changed.'},
    {'id':'R2-02','severity':'required_source_disclosure','status':'open_in_preserved_revision',
     'location':'4.3, data references, and table 1/benchmark description',
     'issue':'The manuscript calls the ETF adjusted-price supplier only the current provider; Yahoo Finance and State Street provenance are absent from the data-reference list. The exact source/locator of the common S&P500 weights and the ETF-proxy replication limit should also be explicit.',
     'evidence':'data/sector_market/manifest.json: provenance.data and source URLs; benchmark.json: source_record and benchmark_proxy_limit.',
     'suggestion':'Name Yahoo Finance public chart adjusted-close data, collected 2026-10-17, with all eleven ticker requests retained in the manifest. Name State Street official product pages for ETF identity. Cite Fidelity Q3 p.2 for the 2026-06-30 S&P500 sector weights. Explain that ETF caps, fees and tracking error mean the resulting sleeve basket does not exactly replicate the index. These are data citations, not new paper-derived assumptions.'},
    {'id':'R2-03','severity':'required_interpretation_limit','status':'open_in_preserved_revision',
     'location':'7 final limitations paragraph / 6.3 reporting rule',
     'issue':'Null pairs are retained, but the text does not explicitly state that having no eligible comparison leaves the primary allocation question unanswered; the final claim that failed outcomes remain meaningful needs this boundary.',
     'evidence':'Frozen protocol interpretation.no_valid_pairs and no_valid_control.',
     'suggestion':'Add: 유효한 최종배분 비교쌍이 확보되지 않으면 기관 근거에 따른 배분 차이라는 주된 질문은 미답으로 남으며, 그 경우 실행 가능성과 측정 절차의 한계만 보고한다. C가 부적격이면 C 비교는 미관측으로 남기되 유효한 E/L 비교는 그 분모와 함께 별도로 보고한다.'},
    {'id':'R2-04','severity':'terminology','status':'partly_corrected_in_preserved_revision',
     'location':'4.2 block 29 corrected; 5.4 block 59 still open',
     'issue':'Section 4.2 now correctly says eleven within-sector two-source comparison rows, but section 5.4 still says 산업 간 비교행.',
     'suggestion':'Use 산업별 기관 간 비교행 or 산업별 관찰행 in section 5.4 so it does not suggest a cross-industry comparison matrix.'},
    {'id':'R2-05','severity':'copy_edit','status':'open_in_preserved_revision',
     'location':'Table 5 note','issue':'소수 둘째 자리에서 반올림 is ambiguous/technically inconsistent with two displayed decimal places.',
     'suggestion':'Use 소수 셋째 자리에서 반올림하여 둘째 자리까지 표시하였다. All 22 displayed percentages were numerically checked and are correct.'},
    {'id':'R2-06','severity':'copy_edit','status':'corrected_in_preserved_revision',
     'location':'E2A reference','issue':'An internal instruction about when to use arXiv versus proceedings had entered the bibliography.',
     'verification':'The preserved revision retains arXiv v1, 13 September 2026 and removes that instruction.'},
]

source_notes = [
    {'claim':'60-observation lookback and 252-day annualization','status':'directly_supported',
     'source':'research/evidence/v48_reference_20261018/portbench_2605_27887v6.html',
     'locators':['Appendix B market context, local line 2007','Appendix B covariance, local line 2089','Appendix C.1 default L=60, local line 2133'],
     'limit':'This supports a borrowed risk convention, not optimality for this sample or the entire five-case design.'},
    {'claim':'GMV, equal weighting, half-L1 distance and temperature/output settings','status':'consistent_with_retained_primary_source_reviews',
     'sources':['research/v492_computational_reference_review_20261019.json','research/v493_paper_source_review_20261019.json'],
     'limit':'The manuscript appropriately states that thinking mode, quantization, model size and hardware differ, and does not transfer composite scores.'},
    {'claim':'Other scholarly claims','status':'scope_checked_against_primary_verified_source_review',
     'source':'research/v493_paper_source_review_20261019.json',
     'limit':'This round did not freshly browse every bibliography entry; it independently checked how the verified claims are used in the manuscript. FSB remains a policy report, not a peer-reviewed experiment.'},
]
inputs = [SNAPSHOT, 'research/v492_evaluation_protocol_20261019_r2.json', 'research/v492_computational_references_20261019.json',
 'research/v492_computational_reference_review_20261019.json','research/v492_source_review_20261019.json','research/v492_runtime_candidate_20261019.json',
 'research/sector_v492_runtime.py','research/sector_v492_contract.py','research/sector_v491_contract.py',
 'data/sector_market/manifest.json','data/sector_market/benchmark.json','research/v481_conference_alignment_20261018.json',
 'research/v493_paper_source_review_20261019.json','research/evidence/v48_reference_20261018/portbench_2605_27887v6.html',
 'research/v492_postpilot_launch_acceptance_20261019.json']
report = {'status':'document_clarifications_requested_core_design_and_numbers_pass','round':2,
 'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'reviewer':'/root/v491_review_pack',
 'review_kind':'independent AI technical/methods reading; not independent human validation',
 'manuscript_scope':'A preserved intermediate revision; root was applying fixes during review. Open findings refer to this immutable copy, not an unexamined later file.',
 'preserved_manuscript_ref':ref(SNAPSHOT),'current_source_at_recording_ref':ref('paper/v493_manuscript_20261019.json'),
 'input_refs':[ref(p) for p in inputs], 'checks':checks, 'passed_checks':sum(c['pass'] for c in checks),
 'failed_checks':sum(not c['pass'] for c in checks),'findings':findings,'source_notes':source_notes,
 'alignment':{'topic':'PASS: public institutional evidence -> stated interpretation -> numerical allocation is a bounded economic/management workflow question.',
 'conference':'PASS within the user-provided overview: concrete organizational problem, traceable evidence and response tied to observed findings. The overview is not an independently authenticated official grading rubric; submission-format compliance is not certified.',
 'control':'PASS: matched-stage common-only AI C is the strategy control; 1/N and GMV are evaluator-only diagnostic references.',
 'scope':'PASS: no market-wide homogenization, private-mandate recovery, pure anchoring, profitability or human-validation claim.',
 'status':'PASS: ongoing pilot and absent completed comparison results are disclosed; implementation tests are not empirical financial outcomes.'},
 'requested_changes_affect_experiment':False,'requested_changes_are_manuscript_clarification_only':True,
 'actual_model_generation_calls':0,'actual_pilot_response_content_read':False,'frozen_experiment_files_modified':False,
 'manuscript_source_modified_by_reviewer':False,'visual_layout_review_performed':False}
assert all(c['pass'] for c in checks), 'A numerical/core-design check failed; inspect before claiming pass'
with (ROOT / TARGET).open('x', encoding='utf8', newline='\n') as out:
    json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False); out.write('\n')
print(json.dumps({'report':ref(TARGET),'status':report['status'],'checks_passed':report['passed_checks'],'open_findings':[f['id'] for f in findings if f['status'] in ['open_in_preserved_revision','partly_corrected_in_preserved_revision']]},ensure_ascii=False))
