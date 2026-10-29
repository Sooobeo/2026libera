LIBERA 현재 실행 지침 — 2026-10-28 10:42 KST

새 세션 첫 파일: 실험참고자료_20261027/00_먼저읽기.html
전체 설계: 실험참고자료_20261027/06_현재실험설계와실행_20261028.html
현재 상태: research/device_migration_20261027/current_execution.json
실행 설정: data/v64_20261028/main_only_results/direct_main_config.json

확정 범위: B-main만 / r=0.5와2 각각5개 / 4펀드 / R0 R1 R2 R3 / 3단계 / 반복1회.
총 160개 작업 흐름, 480개 예정 단계 출력. FULL 및 별도 예비·보조실험은 제외.
비중은 원출력 보존 후 합계100% 비례 보정, 위험·제약 재검사. 부적격이면 기존 h 유지.
본실험은 이 갱신 작업에서 시작하지 않았다. 첫 실행 후 실제 progress/records가 정적 안내보다 우선한다.
이전 후보005의 개발 응답60개는 이번 본실험 표본이 아니다.

노트북 실행·재개 (이미 같은 config의 실행이 있으면 중복 시작 금지):
Set-Location 'C:\Users\Insun\2026libera'
.\research\start_v63_vulkan_ollama.ps1
.\tmp\v63_numerics_venv\Scripts\python.exe -m research.v63.campaign data/v64_20261028/main_only_results/direct_main_config.json --phase B-main

현재 소스 기준 실행 ID: b713cc4533c2f5b18e165f51592ca8f89223977fd1e15aee202adff8bbca6b54
진행: data/v64_20261028/main_only_results/phases/b713cc4533c2f5b18e165f51592ca8f89223977fd1e15aee202adff8bbca6b54/B-main/progress.json
오프라인 문서/설정 확인: .\tmp\v63_numerics_venv\Scripts\python.exe 실험참고자료_20261027/verify_bundle.py
이 확인은 AI 모델을 호출하지 않는다. 기존 전체 예비실험이나 guardian 승인 경로를 다시 실행하지 않는다.
서버·입력·문맥·정규화·제약 검사는 본실험의 필수 처리이며 별도 AI 채점 호출은 없다.
통신 오류/미확정 요청은 자동 재생성하지 않는다. 원기록을 지우지 말고 복구 차단 사유를 기록한다.
클라우드 환경은 아직 지정되지 않았으며 위 명령은 현재 Windows 노트북용이다.
전체 본실험 완료 후 지정 MD·원초록을 참고하여 탐색적 소논문 MD/HTML/DOCX를 작성한다.
과거 전체 설계와 이 기기 개발 안내는 history/before_main_only_20261028/에 보존했다.

수치 사전검사 수정 기록: research/reduction_20261028/numerics_fix_receipt.json
이전 실행은 38.233414초 후 생성 0회로 중단. 내부 목적함수 단위만 수정하고 검증 기준 유지.

추가 수치 사전검사 수정 기록: research/reduction_20261028/coordinate_numerics_fix_receipt.json
직전 실행은 38.534704초 후 생성 0회로 중단. 기존 검증 기준 유지.
