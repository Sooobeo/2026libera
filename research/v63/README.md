# LIBERA v6.3 실행 기록 — 2026-10-27

기준: `plan/LIBERA_실험설정_v6.3_20261027.json`.
먼저 읽은 자료: `실험참고자료_20261027/00_먼저읽기.html`.

이 디렉터리는 새 v6.3의 데이터 수집, 수치·검색·실행기 후보와 검증 기록이다.
기존 GICS11 실험, 72개 가상 위임, 과거 원응답은 새 FF12 본실험으로 합산하지 않는다.
아직 실제 네 펀드의 자료와 독립된 두 사람의 감사, 모델 동결·파일럿을 갖추지 못했다.
계획표의 `not_attempted`는 관측 결과가 아니며 h 유지로 대체하지 않는다.
Mock 응답 테스트와 합성 보유비중에 대한 수치 검산은 LLM 실험이 아니다.
단위 테스트 통과와 수치 sweep·최소분산 경계 검증은 별도다. 수치 성공·실패 수와
미해결 상태는 `data/v63_20261027/numerical/verification.json`을 읽어 보고서에 반영한다.

## 현재 산출물

- `../../실험참고자료_20261027/01_실행기록_20261027.html`: 한국어 실행 정리.
- `../../data/v63_20261027/execution_status.json`: 완료·미완료 및 실제 요청 수.
- `../../data/v63_20261027/audit/engineering_verification.json`: 코드 검증 결과.
- `../../data/v63_20261027/source_manifest.json`: 요청 URL·응답·해시 및 실패 기록.
- `../../data/v63_20261027/audit/workspace_provenance.json`: 참고목록과 현 저장소 대조.
- `../../data/v63_20261027/runtime/planned_schedule.json`: 3,272 궤적, 9,816 단계의 미실행 계획.

## 재검증

PowerShell에서 저장소 루트를 작업 디렉터리로 사용한다.

```powershell
$env:PYTHONIOENCODING='utf-8'
python research/v63/audit_workspace.py
python research/v63/run_verification.py
python research/v63/build_delivery.py
```

수치 환경은 `tmp/v63_numerics_venv/`에 격리한다. 설치 버전과 재구축 명령은
`data/v63_20261027/numerical/`의 환경 기록을 확인한다. 검색기는
`rank-bm25==0.2.2`를 `tmp/v63_python_deps/`에 설치해 사용한다.
실행기 JSON 검증 의존성은 `requirements-runtime.txt`에 버전을 고정했다. 통합 검증은
pytest로 함수형 수치 테스트와 unittest 클래스 테스트를 모두 수집하고 JUnit XML로 건수를 확인한다.
이전 검증 로그는 `data/v63_20261027/audit/verification_history/`에 보존한다.
정확한 모델 토크나이저가 없는 상태에서 어절 수를 실제 문맥 길이로 사용하지 않는다.

## 실제 실행 전 남은 작업

1. 개발·본기·보류기의 네 펀드 공식 전체 보유표, NAV, SIC, 원문 발행일을 완성한다.
2. 누락 주식을 분모에 유지해 SIC 분류율 90% 이상을 확인하고 현금·고정자산·부채를 대조한다.
3. 전 펀드의 적격성·제약을 두 사람이 독립 감사한다. AI 검토는 이 기록을 대신하지 않는다.
4. 합성 수치 sweep·최소분산 경계의 미해결 항목을 해결한 뒤 실제 h와 명시 제약으로 수치 참조해 및 근접최적집합을 검증한다.
5. 실제 API adapter와 모델별 대화 템플릿·토크나이저·수치도구 연결을 구현하고 검증한다.
6. 원응답 지표 집계 연결과 A/C 사실·귀속·제약 해석·설명/비중 일치·오류전파 평가 및 사람 채점을 완성한다.
7. 고정한 모델과 실제 토크나이저로 개발 15→60→720단계 파일럿을 수행한다.
8. 모델·sampler·문맥·요청 제한·시간·비용과 전체 분석·실패 정책을 동결한다.
9. 실제 입력·검색 결과·해시·순서를 동결한 뒤 본실험·전망교체·음성대조·A/C를 실행한다.

`runtime.py`는 transport를 주입하는 실행기 후보이다. `ollama_transport.py`에 Ollama 0.35.1
adapter 후보를 구현했다. 모의 HTTP 서버로 응답·오류·버전변경·동일 바이트 재시도·원문 기록을
검증했으며 실제 원격 서버와 v6.3 과제의 통합은 아직 미검증이다. 요청마다 모델 digest·엔진·
양자화·템플릿을 확인하고 `stream=false`, `truncate=false`, `shift=false`를 유지한다.
이 adapter는 JSON envelope 방식의 도구 왕복을 지원하며 native tool_calls 사용을 주장하지 않는다.
모델별 renderer, 정확한 문맥 측정 및 수치도구 연결도 미통합·미검증이다. `freeze`의 참/거짓만 수동으로
바꾸어 실험을 시작하지 말고 연결된 증거·해시·서명과 실제 파일럿을 먼저 완성한다.
`numerics.py`의 생성 ledger에는 모든 펀드의 private signals가 있으므로 모델에 통째로
전달하지 않는다. 해당 펀드의 허용 근거만 `retrieval.py`를 거쳐 전달한다.

`statistics.py`는 60개 시나리오별 집계 입력을 받는 추론 커널이다. 실제 원응답에서
전체 metrics를 구성하는 최종 분석 연결, A/C 의미 오류의 사람 채점과 전파 기록도 필요하다.
`confirmatory_family`에는 첫 본실험 요청 전에 동결한 `frozen_scenario_ids`와 `frozen_strata`를
필수 keyword로 전달한다. 모든 군의 순서·정밀도 층이 동결본과 같아야 하며, .5/1/2 층은
각 20개다. `terminal_statuses`의 60×8 펀드·반복 칸은 `completed`,
`model_output_failure`, `operational_failure`만 허용한다. `protocol_violation`이나
`not_attempted`가 하나라도 있으면 확증 분석을 거부한다.
현재 검증 통과는 과잉수렴, RAG 완화, 도입시점 우위를 뒷받침하는 실험 결과가 아니다.

현재 컴퓨터의 모델 포트와 기존 로컬 모델·토크나이저 자산은 확인되지 않았다.
사용자가 지정한 원격 Proxmox 150 컨테이너에서 기존 Ollama·Qwen 모델을 확인했으므로
로컬 확인 결과를 모든 모델 서버의 부재로 해석하지 않는다. 별도 실제 연결검사 호출은
`live_engineering_model_calls`로 기록하고 실험 요청·개발 파일럿 호출과 합산하지 않는다.
보고서는 `data/v63_20261027/runtime/remote_runtime_inventory.json`의 상태와
`summary_ko`를 읽어 표시한다. 조사 기록만으로 모델 동결이나 파일럿 완료를 인정하지 않는다.

`build_delivery.py`는 준비 세션 보고서다. 계획의 궤적·블록별 단계 수를 집계·대조하고,
모든 슬롯이 `not_attempted`, 비중이 `null`, 모델 호출이 0인지 확인한다. 실제 요청이
시작되면 해당 생성기를 그대로 사용하지 말고 실제 실행 원장과 종료 상태를 집계하도록 확장한다.
