"""Read-only checks of delivered paper against captured pilot and provenance.

This checks document accounting and links, not source entailment or human review.
No model requests, approval creation, historical edits or inferred portfolio fills.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def reference(path):
    path = resolve(path)
    return {"path": str(path), "sha256": digest(path)}


def verify(receipt_path, evaluation_path, run_root):
    receipt_path, evaluation_path, run_root = map(resolve, (receipt_path, evaluation_path, run_root))
    receipt, evaluation, summary = read(receipt_path), read(evaluation_path), read(run_root / "summary.json")
    bundle = evaluation["primary_C0_bundle"]
    checks = []

    def check(name, condition, detail=None):
        checks.append({"check": name, "pass": bool(condition), "detail": detail})

    check("terminal pilot", summary["status"] != "running", summary["status"])
    check("main not run or frozen", summary["main_model_calls"] == 0 and summary["main_frozen"] is False)
    check("delivery tool made no model calls", receipt["model_calls_by_builder"] == 0)
    check("independent human review still unfilled", all(x is False for x in (
        receipt["independent_human_review_completed"], evaluation["independent_human_review_completed"],
        summary["human_review_completed"])))
    check("four cases and forty-four expected sectors", bundle["planned_case_count"] == 4
          and bundle["expected_sector_count"] == 44 and len(evaluation["primary_C0_cases"]) == 4)
    check("observed call counts match report receipt", receipt["observed_core_requests"] == summary["core_generation_calls"]
          and receipt["observed_auxiliary_requests"] == summary["auxiliary_generation_calls"])
    check("no unregistered delivery outputs", len(receipt["outputs"]) == 2)
    for item in receipt["inputs"] + receipt["outputs"] + [receipt["builder"]]:
        path = resolve(item["path"])
        check("unchanged document dependency: " + path.name, path.is_file() and digest(path) == item["sha256"])
    check("evaluation is a bound builder input", reference(evaluation_path) in receipt["inputs"])
    manifest_ref = evaluation["provenance"]["prepared_manifest"]
    manifest_path = resolve(manifest_ref["path"])
    manifest = read(manifest_path)
    check("prepared manifest unchanged", digest(manifest_path) == manifest_ref["sha256"])
    for name, sha in manifest["software_hashes"].items():
        check("frozen pilot software: " + name, digest(ROOT / "research" / name) == sha)
    for name, sha in manifest["input_hashes"].items():
        check("frozen pilot input: " + name, digest(manifest_path.parent / name) == sha)

    documents = []
    for item in receipt["outputs"]:
        path = resolve(item["path"])
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        text = soup.get_text(" ", strip=True)
        documents.append((path, soup))
        check(path.name + ": Korean UTF-8 document", soup.html.get("lang") == "ko"
              and soup.find("meta", charset="utf-8") is not None)
        check(path.name + ": current version", "v4.8.1" in text)
        for stale in ("현재는 재설계와 오프라인 자료 준비 단계이고 새 절차의 실험 결과는 없다.",
                      "현재 실행기 통합은 미완료."):
            check(path.name + ": no obsolete current state", stale not in text, stale)
        table = next((t for t in soup.find_all("table") if t.caption and "첫 최종안 C0" in t.caption.get_text()), None)
        check(path.name + ": actual C0 table exists", table is not None)
        if table:
            rows = table.tbody.find_all("tr", recursive=False)
            check(path.name + ": all four cases displayed", len(rows) == 4)
            for row, case in zip(rows, evaluation["primary_C0_cases"]):
                cells = [x.get_text(" ", strip=True) for x in row.find_all("td", recursive=False)]
                observed = case["execution"]["raw_sum"]
                actual = None if cells[3] == "미관측" else Decimal(cells[3].removesuffix("%")) / 100
                check(path.name + ": raw sum displayed " + case["case_id"],
                      (actual is None and observed is None) or (actual is not None and observed is not None
                       and actual == Decimal(str(observed))))
                check(path.name + ": validity displayed " + case["case_id"],
                      (cells[4] == "예") is case["execution"]["valid_raw_allocation"])
                check(path.name + ": compound label score displayed " + case["case_id"],
                      cells[5] == str(case["source_fact_preservation"]["exact_label_correct_count"]) + "/11")
        for anchor in soup.find_all("a", href=True):
            url = urlsplit(anchor["href"])
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            check(path.name + ": local link " + anchor["href"], target.is_file())
            if url.fragment and target.is_file() and target.suffix.lower() == ".html":
                linked = soup if target == path else BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
                check(path.name + ": local fragment " + anchor["href"], linked.find(id=unquote(url.fragment)) is not None)
    paper_path, paper = next((p, s) for p, s in documents if s.find(id="intro"))
    for required in ("intro", "literature", "framework", "readiness", "implications", "conclusion", "references", "appendix"):
        check("paper section retained: " + required, paper.find(id=required) is not None)
    paper_text = paper.get_text(" ", strip=True)
    check("paper names core source-to-action chain", "근거와 선택의 연결" in paper_text and "실제 비중" in paper_text)
    check("paper distinguishes timing procedure from causal mechanism", "자료 노출 시점·위치·사용 기회" in paper_text)
    check("paper distinguishes source ID score from strategic outcome", "전략 보존 점수가 아니다" in paper_text)
    check("paper preserves unknown comparisons", "관측되지 않은 비교는 0이나 차이 없음으로 해석하지 않는다" in paper_text)
    check("paper retains earlier failed diagnostic provenance", "96.5%" in paper_text and "97.5%" in paper_text)
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "round": 1,
            "status": "PASS" if all(x["pass"] for x in checks) else "FAIL",
            "scope": "Delivered document accounting, provenance, local links and explicit claim boundaries; not semantic or human acceptance.",
            "provenance": {"receipt": reference(receipt_path), "evaluation": reference(evaluation_path),
                           "run_summary": reference(run_root / "summary.json"), "auditor": reference(__file__)},
            "checks": checks, "check_count": len(checks), "failed_check_count": sum(not x["pass"] for x in checks),
            "model_calls_by_this_audit": 0, "independent_human_review_completed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("receipt", "evaluation", "run-root", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    output = resolve(args.output)
    if output.exists():
        raise FileExistsError("Preserve prior review; select a new output")
    report = verify(args.receipt, args.evaluation, args.run_root)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["check_count"],
                      "failed": report["failed_check_count"], "output": str(output)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
