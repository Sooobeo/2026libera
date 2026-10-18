"""Clarify generated diagnostic headings; preserve frozen renderer and raw HTML."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019"
SOURCE = DIRECTORY / "review.html"
OUT = DIRECTORY / "review_with_label_scope.html"
RECEIPT = Path(__file__).with_name("review_label_scope_clarification.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def main():
    if OUT.exists() or RECEIPT.exists():
        raise FileExistsError("Preserve prior presentation artifacts")
    before_sha = sha(SOURCE)
    before = SOURCE.read_text(encoding="utf-8")
    after = before
    edits = [
        ('<p class="note">등급 문자열 진단: ', '<p class="note">출처 ID 포함 등급 일치 진단: ', 66),
        ('<p>정확한 등급 문자열 보조 진단: ', '<p>출처 ID 포함 등급 일치 보조 진단: ', 1),
        ('<p>프로그램은 실행·형식·산술·정확한 등급 문자열을 확인합니다.',
         '<p>프로그램은 실행·형식·산술·출처 ID를 포함한 등급 일치를 확인합니다.', 1),
    ]
    counts = []
    for original, replacement, expected_count in edits:
        count = after.count(original)
        assert count == expected_count, (original, count)
        after = after.replace(original, replacement)
        counts.append({"generated_prefix_before": original, "generated_prefix_after": replacement, "count": count})
    anchor = '<section id="accounting"><h2>전체 사례와 실패 분모</h2>'
    assert after.count(anchor) == 1
    note = '<p class="note">진단 범위 보충: 이 진단은 등급 문구뿐 아니라 source_id의 일치도 요구합니다. 완료된 Fidelity R1 C0에는 11개 등급 문구가 제공 문구와 같아도 source_id가 null이므로 공동 조건을 충족하지 않습니다. 0/44를 모든 등급 문구가 틀렸다는 뜻이나 전략 보존 실패 점수로 읽지 않습니다. 원문·원수치·평가 규칙은 변경하지 않았습니다.</p>'
    after = after.replace(anchor, anchor + note)
    old_dom, new_dom = BeautifulSoup(before, "html.parser"), BeautifulSoup(after, "html.parser")
    # Every raw text/citation block, observed metric and sector/case count stays.
    for selector in ("pre", ".metric", ".sector-title"):
        assert [x.get_text() for x in old_dom.select(selector)] == [x.get_text() for x in new_dom.select(selector)]
    assert len(new_dom.select("#primary article.sector")) == 44
    assert len(new_dom.select("#auxiliary article.sector")) == 22
    assert sha(SOURCE) == before_sha
    with OUT.open("x", encoding="utf-8") as handle:
        handle.write(after)
    result = {"artifact_kind": "presentation_only_joint_source_ID_and_label_scope_clarification",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS",
              "source_html": ref(SOURCE), "output_html": ref(OUT), "script": ref(Path(__file__)),
              "edits": counts, "additional_note": note,
              "verification": {"all_pre_blocks_literal_unchanged": True, "all_metric_blocks_unchanged": True,
                               "all_sector_titles_unchanged": True, "primary_sector_count": 44, "auxiliary_sector_count": 22,
                               "original_html_unchanged": True},
              "evaluation_rule_changed": False, "human_judgments_created": 0, "model_calls": 0,
              "frozen_renderer_modified": False, "scope": "Correct generated headings only; not a new evaluation or semantic review."}
    with RECEIPT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": ref(OUT), "receipt": ref(RECEIPT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
