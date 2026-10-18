"""Synthesize the saved failed pilot and three offline reviews; no model access."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
RUN = 'data/local_sector_runtime/single_case_v44_20261018'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def main():
    summary_path = RUN + '/summary.json'
    summary = read(summary_path)
    if not (summary['status'] == 'hard_deadline' and summary['generation_requests_attempted'] == 1
            and summary['completed_workflow_stages'] == 0 and summary['main_model_calls'] == 0):
        raise ValueError('This synthesis is specific to the preserved failed attempt')
    reviews = [f'research/v44_single_case_round{n}_20261018.json' for n in (1, 2, 3)]
    for p in reviews:
        read(p)
    events_path = RUN + '/stage1_transport/http_0001_generation/events.jsonl'
    events = [json.loads(line) for line in (ROOT / events_path).read_text(encoding='utf-8').splitlines() if line.strip()]
    content = [x for x in events if x['event'].get('message', {}).get('content')]
    ttft = content[0]['elapsed_seconds']
    if any(x['event'].get('done') for x in events):
        raise ValueError('Unexpected terminal event')
    findings = [
        {'statement': '예비실험용 v4.4 조건을 생성 전에 고정했다. 기본 Qwen3.5-4B, greedy·thinking 비활성화·seed는 FinVector 선례를 참조한다. 출력 상한 8192는 PortBench에서 다른 과제에 옮긴 값이며, 벌점·엔진·문맥·GPU·시간 제한은 저자 코드, 공식 구현, 이전 실측 또는 운영상의 선택으로 근거 수준을 별도 공개한다. 모든 수치가 논문 직접값이라는 주장은 하지 않는다.',
         'evidence': ['research/v44_conditions_reference_20261018.html', 'data/sector_protocol/v44_single_case_registration_20261018.json']},
        {'statement': f'Fidelity Q2/R1 한 사례의 4단계 실행을 시도했지만 첫 단계가 사전 설정한 900초 제한으로 종료됐다. 정리까지 전체 {summary["wall_seconds"]:.2f}초가 걸렸고, 생성 요청은 1회·완료 응답과 완료 단계는 0회다. 2~4단계는 미실행이며 자동 재시도는 없다. 이 기록은 완주한 예비실험이나 본과제 결과가 아니다.',
         'evidence': [summary_path, RUN + '/stage1_transport/supervisor_result.json']},
        {'statement': f'저장된 스트림에서 첫 내용은 생성 HTTP 요청 시작 약 {ttft:.2f}초 뒤 관측됐지만 정상 종료 이벤트와 완성된 답변은 없다. 첫 내용이 빨리 나오는 것만으로 연구 과제를 수행할 수 있다고 판단하지 않는다. 스트림 이벤트 수를 토큰 수로 대체하지 않았다.',
         'evidence': [events_path, reviews[0], reviews[1]]},
        {'statement': '1차 자체 검증: 실행 전에 고정한 조건·모델 식별값과 실제 전송을 대조했고, 첫 단계 입력의 가역적 중복 제거와 렌더링 문장 보존을 확인했다. 시간 제한 종료와 미실행 후속 단계는 실패·미관측으로 구분했다. 네 단계 전체 이력 보존이나 독립적인 토큰 용량 측정에 성공했다는 주장은 하지 않는다. 종료 후 모델 해제와 빈 실행 목록도 기록했다.',
         'evidence': [reviews[0], RUN + '/stage1_transport/unload_and_residency.json']},
        {'statement': '2차 자체 검증: 원본 스트림과 저장 이벤트의 일치를 독립 확인했다. 완료된 기관 등급·비중 제안이 없으므로 등급 정확도, 비중 합계, 능동 비중과 위험은 평가·계산 불가다. 원본 시장 공분산을 모델이 제출한 포트폴리오로 바꾸어 계산하거나 미제출을 0점으로 채점하지 않았다.',
         'evidence': [reviews[1], 'research/v44_single_case_round2_20261018.html']},
        {'statement': '3차 자체 검증: 부분 출력에는 stage·task·common_market 등 입력의 재서술이 나타난다. 이를 기관 전망의 해석이나 근거 있는 배분 전략으로 세지 않는다. 완성된 주장·비중이 없어 전략의 타당성이나 원문 충실성의 성패를 점수화할 수 없다. 이 한 번의 실패로 모델 크기·입력 길이·JSON 설정 중 어느 요인이 원인인지 또는 R1/R4 중 어느 절차가 우월한지를 식별할 수 없다.',
         'evidence': [reviews[2], 'research/v44_single_case_round3_20261018.html']},
        {'statement': '본과제 호출은 0회이고 조건 동결과 독립 사람 검토도 완료되지 않았다. 다음 단계는 실패 원인을 구분할 진단과 필요한 조건 개정의 근거를 별도 버전으로 정리한 뒤, 전체 예비실험을 다시 검증하는 것이다. 이번 관측을 보고 유리한 결과만 선택하거나 현재 조건을 본과제 준비 완료로 승인하지 않는다.',
         'evidence': [summary_path, reviews[0], reviews[2]]},
    ]
    references = sorted({p for item in findings for p in item['evidence']} | {
        'research/v44_conditions_reference_20261018.json',
        'research/local_sector_single_case.py',
        'research/build_sector_revision_v44.py',
    })
    value = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'One failed prespecified pilot and three completed offline review processes, not three passes or a completed four-stage experiment.',
             'findings': findings, 'conditions_display_erratum': {
                 'original_field': 'engine_and_backend',
                 'original_conditions_kept_immutable': True,
                 'correction': 'Per-call checks pin engine version, model digest and template. Executable hash and GPU placement are separate installation/log observations, not per-call executable/Vulkan gates. No generation request or criterion was changed retrospectively.'},
             'first_content_http_seconds': ttft,
             'source_files': [{'path': p, 'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in references],
             'model_calls_by_synthesis': 0, 'main_frozen': False, 'independent_human_review_complete': False}
    output = ROOT / 'research/v44_single_case_findings_20261018.json'
    with output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'model_calls': 0}))


if __name__ == '__main__':
    main()
