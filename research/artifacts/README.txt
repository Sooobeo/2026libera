연구 실행 자료 보관 (2026-10-19)

Git 변경 목록을 줄이기 위해 실행 결과 원본을 ZIP으로 묶었습니다.
원본 파일은 삭제하지 않았습니다. ZIP 내부 경로와 각 파일의 SHA-256은
manifest.json에 기록되어 있으며, 기존 논문·검증 기록의 경로로 복원됩니다.
코드, 논문, 실험 설정은 계속 개별 파일로 관리합니다.
.gitattributes에는 이번 전달 파일의 줄바꿈 자동 변환을 막는 규칙을
기록했습니다. 다른 운영체제로 복제해도 검증에 사용한 원래 바이트를 유지합니다.
이전에 이미 추적하던 과거 자료는 유지하되, 계속 바뀌는 서버 로그 두 개는
현재 시점의 내용을 압축 보관하고 개별 Git 추적을 해제합니다.

저장소 루트에서 압축본 검증:
python -B research/restore_research_artifacts.py research/artifacts/runtime-evidence-20261019.manifest.json

새로 복제한 저장소에서 원래 위치로 복원:
python -B research/restore_research_artifacts.py research/artifacts/runtime-evidence-20261019.manifest.json --restore

복원은 없는 파일만 생성합니다. 기존 파일이 다르면 덮어쓰지 않고 중단합니다.
서버 로그가 이후 변경됐다면 --destination으로 별도 폴더에 복원해 비교하세요.

Git에서 제외하는 펼쳐진 산출물 위치:
data/local_sector_runtime/
research/evidence/
research/evaluator_only/
이 경로 안의 Python 코드는 제외하지 않습니다.

주의: 이후 새로 생성하는 실행 자료는 이번 압축본에 자동으로 추가되지 않습니다.
새 결과를 공유할 때는 새로운 압축본과 파일별 해시 목록을 함께 보관해야 합니다.
압축본은 과거 실행의 증거 보존용이며, 실패한 파일도 그대로 포함합니다.
