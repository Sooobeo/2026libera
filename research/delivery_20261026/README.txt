2026-10-26 다섯 조건 탐색적 분석 완료 자료

먼저 열 파일: ../last_final_20261026/results_explained_ko.html
결과와 11개 업종별 최종 배분을 한국어로 설명합니다. 파일 하나를 브라우저에서 열 수 있습니다. 근거 링크는 저장소의 상대 경로를 사용합니다.

현재 완료 상태와 보관 파일: completion_index.json
조건별 원문·전체 감사·별도 가림 검토 연결: ../last_final_20261026/five_condition_audit_index.json
기계가 읽을 통합 배분 결과: ../last_final_20261026/derived_allocation/completed_five_condition_dataset.json

범위: Fidelity·UBS 자료를 처음부터 제공한 두 조건, 초안 뒤 제공한 두 조건, 기관자료 없는 비교 조건. 각 조건의 초안과 최종안을 완료했습니다. 중단된 한 번을 포함한 실제 생성 요청은 11회이고, 완료한 논리적 단계는 10개입니다. 저장된 초안과 응답을 이어 사용했으며 이전 실패·중단 이력은 보존했습니다.

각 최종 배분의 합은 별도 계산으로 정확히 100.00%입니다. AI가 제출한 원래 합계와 설명·인용 오류는 보존했으므로, 계산 완료를 모델 답변 전체의 정확성으로 해석하면 안 됩니다.

이 다섯 조건은 결과 일부를 확인한 뒤 주된 탐색적 분석으로 채택한 사례입니다. 별도로 준비했던 Fidelity 3분기·UBS 7월 자료의 새 본실험은 실행하지 않았습니다. 순수한 시점의 인과효과나 투자성과 검증을 주장하지 않습니다.

옛 terminal, template, working draft의 중단·대기 표시는 해당 시점의 기록입니다. 현재 상태는 completion_index.json과 그 안의 최종 검토·보관 참조를 따릅니다. ZIP은 원본 바이트와 경로를 보관하고 manifest·verification이 무결성 검증을 기록합니다. .gitignore로 제외한 새 중복 로그도 검증된 보관본에 남아 있습니다.

원시 실행 파일이 없는 새 체크아웃에서는 research/restore_research_artifacts.py에 해당 manifest 경로를 넘겨 검증할 수 있습니다. --restore를 추가하면 누락된 파일만 복원하고 기존 파일은 덮어쓰지 않습니다. 현재 작업 폴더의 원본은 삭제하지 않았습니다.
