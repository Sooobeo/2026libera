"""Synthesize immutable v4.5 observations and three offline audits; no inference."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
RUN = 'data/local_sector_runtime/single_case_v45_20261018'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def main():
    summary_path = RUN + '/summary.json'
    summary = read(summary_path)
    reviews = [f'research/v45_single_case_round{n}_20261018.json' for n in (1,2,3)]
    r1,r2,r3 = [read(p) for p in reviews]
    if summary['main_model_calls'] != 0 or r3['audit_status'] != 'completed':
        raise ValueError('Unexpected main call or unfinished semantic audit')
    final = r2['registered_final_extraction_endpoint']
    if (final['correct'] != r3['source_label_primary_fixed_denominator']['correct']
            or final['expected'] != 11):
        raise ValueError('Independent final-label counts disagree')
    counts = {'workflow_stages':summary['completed_workflow_stages'],
        'attempted_generation_calls':summary['generation_requests_attempted'],
        'final_allocation_valid':summary['final_allocation_valid'],
        'original_label_endpoint':final, 'technical_round1_pass':r1['all_passed'],
        'round2_consistency_findings':len(r2['consistency_findings']),
        'semantic_review_conclusion':r3['semantic_review']['conclusion_ko']}
    sums = []
    for stage in r2['stages']:
        ar = stage.get('arithmetic') or {}
        sums.append(f"{stage['stage']}단계 " + ((ar.get('exact_sum') or {}).get('fraction') or '정확 합계 산출 불가(상세 감사 참조)'))
    findings = [
        {'statement':'v4.4의 입력 재출력·시간 제한 실패를 보존하고, 같은 예비 사례에 명시적 응답 스키마를 API와 단계별 프롬프트에 함께 제공했다. FinVector의 명시적 스키마 조건과 Ollama 공식 구현을 근거로 삼되, 두 변경의 효과를 따로 식별하거나 금융 판단 개선을 보장한 것으로 해석하지 않는다.',
         'evidence':['research/v45_revision_reference_20261018.html','data/sector_protocol/v45_single_case_registration_20261018.json']},
        {'statement':f"실제 생성 요청 {summary['generation_requests_attempted']}회 중 완료 응답 {summary['http_streams_completed']}회, 완료 단계 {summary['completed_workflow_stages']}/4를 기록했다. 정리까지 포함한 전체 시간은 {summary['wall_seconds']/60:.2f}분이다. 재시도 {summary['automatic_retries']}회이며 단계별 원문과 계산 결과를 보존했다. 이는 같은 한 사례의 실행 관측이고 독립된 네 사례가 아니다.",
         'evidence':[summary_path,reviews[0]]},
        {'statement':f"1차 실행 검증은 {r1['check_count']}개 항목을 확인했다. 실패 항목 {len(r1['failed_checks'])}개, 미관측 항목 {len(r1['not_observed_checks'])}개다. 입력 수치·공개 문서·단계별 응답 구조·이전 답변 및 계산 피드백·종료 상태를 대조했다. 형식과 이력 검증은 전략 타당성의 판정이 아니다.",
         'evidence':[reviews[0],'research/v45_single_case_round1_20261018.html']},
        {'statement':f"2차 독립 계산에서 제출 비중의 정확한 합계는 {', '.join(sums)}이다. 기존 계산기가 기록한 최종 비중 유효성은 {summary['final_allocation_valid']}이고 기록 간 불일치 발견은 {len(r2['consistency_findings'])}건이다. 원문 숫자를 정규화하거나 반올림해 오류를 지우지 않는다.",
         'evidence':[reviews[1],'research/v45_single_case_round2_20261018.html']},
        {'statement':f"최종 원래 등급 추출은 기존 고정 분모 기준 {final['correct']}/11이다. 이는 원문 평가 단어를 보존한 정도이며, 비중의 적합성이나 근거 설명의 진실성까지 뜻하지 않는다. 공개 전망에는 유일한 정답 비중이 없어 정확 비중 일치율을 임의로 만들지 않았다.",
         'evidence':[reviews[1],reviews[2],'data/sector_protocol/evaluation_spec.json']},
    ]
    for finding in r3['semantic_review']['reader_findings']:
        findings.append({'statement':'3차 원문·논리 검토: '+finding['title_ko']+' '+finding['detail_ko'],
                         'evidence':[reviews[2],'research/v45_single_case_round3_20261018.html']})
    findings.extend([
        {'statement':r3['semantic_review']['topic_connection_ko'],
         'evidence':[reviews[2]]},
        {'statement':'이전 v4.4 실패는 기존 등급 추출 지표에서 0/11로 포함하고, 완성 답변이 없어 수치·의미를 평가할 수 없었다는 조건부 판단과 구분한다. 실패를 분모에서 삭제하지 않으며 서로 다른 프로토콜 버전을 같은 고정 조건의 결과로 합산하지 않는다.',
         'evidence':[reviews[1],'data/sector_protocol/v45_single_case_registration_20261018.json']},
        {'statement':'본과제 호출은 0회이고 조건도 아직 동결하지 않았다. 이번에 다시 사용한 Fidelity Q2/R1은 개발용 예비 사례다. 나머지 예비 사례와 R4 절차, 독립 사람의 원문 검토, 본과제의 별도 동결·실행이 남아 있다. 세 차례 자체 검증을 사람의 독립 검토로 표시하지 않는다.',
         'evidence':[summary_path,reviews[2]]},
    ])
    paths = sorted({p for item in findings for p in item['evidence']} | {
        'research/summarize_v45_single_case.py','research/build_sector_revision_v45.py',
        'research/v45_revision_reference_20261018.json','research/local_sector_structured_case.py',
        'research/sector_response_schema.py'})
    value = {'protocol_version':'4.5','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'One versioned exploratory four-stage case and three completed self-review processes; completion, financial validity and semantic quality remain separate.',
        'observed_outcome':counts,'findings':findings,
        'source_files':[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths],
        'model_calls_by_synthesis':0,'main_frozen':False,'independent_human_review_complete':False}
    output = ROOT / 'research/v45_single_case_findings_20261018.json'
    with output.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
    print(json.dumps({'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                      'observed_outcome':counts},ensure_ascii=False))


if __name__ == '__main__': main()
