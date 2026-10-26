"""Collect a byte-verified, local reference snapshot without moving source files."""
from __future__ import annotations

import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "실험참고자료_20261027"
SNAPSHOT = BUNDLE / "snapshot"
EXPANDED = ("data/local_sector_runtime/", "research/evidence/", "research/evaluator_only/")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main():
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    ).decode("utf-8").split("\0")
    selected = []
    omitted = []
    for name in sorted(set(filter(None, listed))):
        if not name.startswith(("plan/", "paper/", "data/", "research/", "tmp/")):
            continue
        path = ROOT / name
        if not path.is_file():
            continue
        if name.startswith(EXPANDED) and path.suffix != ".py":
            omitted.append(name)
            continue
        selected.append((path, SNAPSHOT / name))
    for name in (".gitattributes", ".gitignore"):
        selected.append((ROOT / name, SNAPSHOT / name))

    design = json.loads((ROOT / "plan/LIBERA_실험설정_v6.3_20261027.json").read_text(encoding="utf-8"))
    external = [Path(s["path"]) for s in design["lineage"] if Path(s["path"]).is_absolute()]
    for source in external:
        if not source.is_file():
            raise FileNotFoundError(source)
        selected.append((source, BUNDLE / "original" / source.name))

    entries = []
    for source, target in selected:
        source_hash = sha(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha(target) != source_hash:
                raise RuntimeError(f"Existing copy differs; refusing to overwrite: {target}")
        else:
            shutil.copy2(source, target)
        if sha(target) != source_hash or sha(source) != source_hash:
            raise RuntimeError(f"Copy/source verification failed: {source}")
        entries.append({
            "source": str(source), "copy": target.relative_to(BUNDLE).as_posix(),
            "bytes": target.stat().st_size, "sha256": source_hash,
        })

    write(BUNDLE / ".gitignore", "# Local copies of versioned materials; originals remain authoritative.\n/snapshot/\n")
    write(BUNDLE / ".gitattributes", "# Preserve hash-pinned source and inventory bytes across platforms.\n* -text\noriginal/** -text\n")
    readme = """LIBERA 실험 참고자료 모음 — 2026-10-27

시작: 00_먼저읽기.html 을 브라우저로 열기

1. 최종 기준
   snapshot/plan/LIBERA_최종실험설계_쉬운설명_v6.3_20261027.html
   snapshot/plan/LIBERA_실험설정_v6.3_20261027.json
   original/greengreen (1).pdf : 제목과 원초록 원문

2. 설계 근거와 검토
   snapshot/plan/LIBERA_실험설계서0925.html
   snapshot/plan/문규리 제안서 상세_최종.html
   snapshot/research/redesign_20261027/ : 원설계 복원과 출처 목록
   snapshot/research/redesign_3round_20261027/ : 3회 검토·개선과 검증 기록
   snapshot/paper/ : 현재 v5.4 원고와 과거 원고·관련 문헌
   과거 버전은 설계 계보와 오류 확인용이며 최종 실행 기준은 v6.3이다.

3. 새 본실험에서 출발할 데이터
   snapshot/data/documentary/source_inventory.json : 실제 4펀드 식별자·공식 자료 후보
   snapshot/data/french/ : FF12 수익률, SIC 분류, 다운로드 원본·출처 해시
   4펀드 공식 원문·전체 보유·시점별 적격성·사람이 감사한 정답표는 아직 완성되지 않았다.

4. 이전 실험의 참고자료
   snapshot/data/institutional_recent/ : 72개 가상 위임의 보조 정량자료
   snapshot/data/sector_documents/, sector_market/, sector_protocol/ : GICS11 계열
   snapshot/tmp/pdfs/sector_documents/ : 기존 전망 문서의 PDF 캐시
   snapshot/research/last_final_20261026/results_explained_ko.html : 완료 실험 쉬운 설명
   snapshot/research/delivery_20261026/completion_index.json : 결과·원응답·보관본 색인
   snapshot/research/artifacts/ : 기존 실행 원본 ZIP 및 파일별 해시 목록
   snapshot/research/ : 준비·실행·평가·검증 코드와 기존 검토 기록
   나머지 data 하위 폴더는 과거 비교·준비자료다. FF12 실제 4펀드 본실험과 혼합하지 않는다.
   과거 평가기는 목적함수가 다르므로 v6.3 분산상한 기준평가기의 완성 구현으로 쓰지 않는다.
   기존 직접 제공 실험을 실제 검색 RAG의 검증 결과로 합산하지 않는다.

5. 실험 시작 전 남은 작업
   (1) 실제 4펀드 공식 원문·전체 보유 수집과 시간 기준 확인
   (2) SIC 매핑·분류율·제약 및 정답표의 사람 감사
   (3) B 신호 생성기·분산상한 기준평가기 구현과 독립 검산
   (4) BM25 색인·검색 로그·정보 경계 구현
   (5) 세 단계·다섯 조건 실행기 구현과 파일럿
   (6) 모델·문맥·예산·표본 동결 후 본실험 실행
   이 폴더를 모았다는 사실은 위 작업 또는 새 실험이 완료됐다는 뜻이 아니다.

6. 사용과 검증
   원본을 이동·수정하지 않고 바이트가 같은 복사본을 모았다.
   자료목록.json에 원래 위치·복사 위치·크기·SHA-256을 기록했다.
   python verify_bundle.py 로 이 폴더의 복사본과 생성 안내 파일을 검증한다.
   복사본은 수집 시점의 스냅샷이다. 작업은 기존 저장소에서 진행한다.
   코드·설계 JSON의 기존 상대경로·절대경로는 보존했다. 다른 컴퓨터에서는 경로 조정이 필요하다.
   snapshot은 중복 커밋을 막도록 이 폴더의 .gitignore에서 제외했다. 원초록·안내·목록은 유지한다.
   이미 ZIP으로 보관된 대량 실행자료는 중복으로 펼쳐 복사하지 않았다. 목록의 생략 항목을 참고한다.
   임시 브라우저 프로필·모델 가중치·캐시·Word 페이지 미리보기 등 Git에서 제외된 생성물은 수집하지 않았다.
"""
    write(BUNDLE / "README.txt", readme)
    links = [
        ("최종 실험 설계 — 쉬운 설명", "snapshot/plan/LIBERA_최종실험설계_쉬운설명_v6.3_20261027.html"),
        ("최종 실험 설정 JSON", "snapshot/plan/LIBERA_실험설정_v6.3_20261027.json"),
        ("제목·원초록 PDF", "original/greengreen (1).pdf"),
        ("0925 원설계", "snapshot/plan/LIBERA_실험설계서0925.html"),
        ("3회 검토·개선 기록", "snapshot/research/redesign_3round_20261027/review_history.html"),
        ("설계 검증 결과 — 38개 확인", "snapshot/research/redesign_3round_20261027/verification.json"),
        ("4펀드 공식 자료 후보", "snapshot/data/documentary/source_inventory.json"),
        ("FF12 데이터 출처·해시", "snapshot/data/french/manifest.json"),
        ("기존 실험 결과 쉬운 설명", "snapshot/research/last_final_20261026/results_explained_ko.html"),
        ("기존 실험 증거 색인", "snapshot/research/delivery_20261026/completion_index.json"),
        ("현재 v5.4 원고", "snapshot/paper/LIBERA_소논문_원초록반영_v5.4_20261026.docx"),
        ("전체 자료목록", "자료목록.json"),
    ]
    for _, name in links:
        if name != "자료목록.json" and not (BUNDLE / name).is_file():
            raise FileNotFoundError(name)
    items = "".join(f'<li><a href="{html.escape(path, quote=True)}">{html.escape(label)}</a></li>' for label, path in links)
    write(BUNDLE / "00_먼저읽기.html", '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LIBERA 실험 참고자료</title><style>body{max-width:960px;margin:40px auto;padding:0 24px;font:17px/1.8 "Malgun Gothic",sans-serif;color:#243044}h1{font-size:28px}li{margin:8px 0}pre{white-space:pre-wrap;font:15px/1.9 "Malgun Gothic",sans-serif;border-top:1px solid #ccd3df;padding-top:24px}a{color:#164ec4}</style><h1>LIBERA 실험 참고자료</h1><p>실행 기준은 v6.3입니다. 기존 실험은 참고·회귀 사례이며 새 본실험은 아직 실행하지 않았습니다.</p><ol>' + items + '</ol><pre>' + html.escape(readme) + '</pre></html>\n')
    verifier = '''"""Verify this reference package without requiring the original machine."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "자료목록.json").read_text(encoding="utf-8"))
errors = []
records = manifest["files"] + manifest["generated_files"]
for row in records:
    path = (root / row["copy"]).resolve()
    if not path.is_relative_to(root):
        errors.append({"path": row["copy"], "reason": "outside package"})
        continue
    if not path.is_file():
        errors.append({"path": row["copy"], "reason": "missing"})
        continue
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != row["sha256"] or path.stat().st_size != row["bytes"]:
        errors.append({"path": row["copy"], "reason": "bytes differ"})
result = {"status": "passed" if not errors else "failed", "source_copies": len(manifest["files"]), "generated_files": len(manifest["generated_files"]), "checked_files": len(records), "errors": errors}
(root / "검증결과.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(1 if errors else 0)
'''
    write(BUNDLE / "verify_bundle.py", verifier)
    generated = []
    for name in ("README.txt", "00_먼저읽기.html", "verify_bundle.py", ".gitignore", ".gitattributes"):
        path = BUNDLE / name
        generated.append({"copy": name, "bytes": path.stat().st_size, "sha256": sha(path)})
    manifest = {
        "schema": "libera_reference_snapshot_v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": str(ROOT), "authoritative_design": "6.3-design",
        "new_experiment_executed": False, "source_files_moved_or_modified": False,
        "file_count": len(entries), "total_bytes": sum(e["bytes"] for e in entries),
        "groups": dict(Counter(e["copy"].split("/")[1] if e["copy"].startswith("snapshot/") else "original" for e in entries)),
        "excluded_expanded_evidence": {"reason": "Archived evidence retained under snapshot/research/artifacts; copied Python source separately.", "paths": omitted},
        "selection": "All existing Git-visible files under plan, paper, data, research, tmp; archived expanded runtime evidence excluded except Python source. External original-abstract PDF added from design lineage.",
        "readiness_at_collection": design["current_readiness"],
        "implementation_pending": design["design_vs_execution"]["implementation_pending"],
        "files": entries, "generated_files": generated,
    }
    write(BUNDLE / "자료목록.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    subprocess.run([sys.executable, "-X", "utf8", "-B", str(BUNDLE / "verify_bundle.py")], check=True)
    print(json.dumps({"folder": str(BUNDLE), "source_copies": len(entries), "MB": round(manifest["total_bytes"] / 2**20, 2), "groups": manifest["groups"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
