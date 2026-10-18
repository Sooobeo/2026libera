"""Build the public-sector-view case corpus, without calling an LLM.

Run from any directory: python research/prepare_sector_documents.py --check-live
Offline reproduction uses the checksum-pinned PDFs already in tmp/pdfs/sector_documents.
Missing PDFs can be fetched with --download-missing; downloaded bytes must match the
audited hash. Full PDFs are not copied to the distributed corpus directory.

The short source paraphrases and visually read chart labels below are researcher
transcriptions, NOT independent human-adjudicated ground truth. The generated blank
worksheet supports a separate substantive review before interpreting formal results.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "research/design_revision_20261017/sector_document_candidates.json"
OUT = ROOT / "data/sector_documents"
VERSION = "sector_documents_v4.2.1"
CUTOFF = "2026-07-17"
SECTORS = {
    "10": "Energy", "15": "Materials", "20": "Industrials",
    "25": "Consumer Discretionary", "30": "Consumer Staples", "35": "Health Care",
    "40": "Financials", "45": "Information Technology", "50": "Communication Services",
    "55": "Utilities", "60": "Real Estate",
}
SPLITS = {
    "fidelity_q2_2026": "pilot", "ubs_june_2026": "pilot",
    "fidelity_q3_2026": "main", "ubs_july_2026": "main",
}
EXPECTED_HASHES = {
    "fidelity_q2_2026": "d11c4403f90e7bbd1d06a7fa83c91673d8c772be325042d4d1f01fab4e7076d6",
    "fidelity_q3_2026": "4179aa3e97f3146e664655ac1008cc87942341069ec4bccfbfe7d7436467dd04",
    "ubs_june_2026": "1f8ec8afee56898124a450acf3557a1a493e282a4139c4cffa2212471b12b5a2",
    "ubs_july_2026": "07369578859be743e2323ea611f8d9b47e9bb7bc1e7b0e081d4b8df5ad2b4b7b",
}
BENCHMARK_PERCENT = {
    "10": 3.0, "15": 1.8, "20": 8.8, "25": 9.3, "30": 4.6, "35": 8.9,
    "40": 11.8, "45": 38.0, "50": 9.7, "55": 2.2, "60": 1.8,
}
FIDELITY_REASONS = {
    "10": "Unfavorable risk-return indicators.",
    "15": "Higher capital spending may burden the sector.",
    "20": "Forward-looking valuation evidence is favorable.",
    "25": "Forward valuations imply favorable risk-return.",
    "30": "Weak fundamentals raise value-trap concerns.",
    "35": "Risk-return evidence is balanced.",
    "40": "Relative valuations offer downside support.",
    "45": "Fundamentals and post-decline valuations support the view.",
    "50": "Technology-related components fare better than defensive components.",
    "55": "Valuations are unfavorable.",
    "60": "Valuation dispersion offers favorable risk-return.",
}
UBS_REASONS = {
    "20": "Aerospace growth and transportation's cyclical potential.",
    "25": "AI adoption and fiscal support for consumer spending.",
    "35": "Resilience if economic growth disappoints.",
    "40": "Regulatory easing and capital-markets activity.",
    "55": "Defensive resilience and AI-related exposure.",
}
LIMITATIONS = [
    "These are published sector judgments, not client mandates, risk-aversion coefficients, actual holdings, or complete institutional investment objectives.",
    "The common 2026-07-17 cutoff is a retrospective document-snapshot availability cutoff. It does not establish simultaneous information, the latest views of all institutions, or a historical trading replay.",
    "Current retrieved bytes and publisher dates do not prove which exact bytes were publicly available at the historical cutoff; no archived historical snapshot has been authenticated.",
    "Pilot and main reuse the same two institutions and similar wording. UBS labels are unchanged; only two Fidelity sector labels change. This is not an independent held-out institution sample.",
    "Pilot is a mechanical rehearsal using the same common market snapshot as main. Freeze pilot-derived rules before main; do not tune against main references.",
    "Fidelity strategist research uses the top 3000 US stocks, while benchmark weights are S&P 500. The shared GICS sector action space is a constrained interpretation task, not exact replication of that strategist's investable universe.",
    "Qualitative ratings do not identify unique numeric portfolio weights. Fidelity Overweight is relative to a benchmark; UBS Attractive is not an automatic Overweight instruction.",
    "Source paraphrasing and chart transcription can simplify or misread the original. Independent substantive human source review remains pending.",
    "The corpus tests source interpretation and reasoned proposed allocation. It cannot establish superior future returns, full strategy replication, or welfare effects.",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in values), encoding="utf-8")


def fetch_url(url: str) -> tuple[bytes, dict]:
    # The publisher proxy can return its HTML shell for a browser-style UA.
    # Use urllib's ordinary default request and verify content bytes, not HTTP 200 alone.
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=40) as response:
        data = response.read()
        return data, {"status": response.status, "final_url": response.url,
                      "content_type": response.headers.get("Content-Type"), "bytes": len(data),
                      "sha256": sha(data), "checked_at_utc": datetime.now(timezone.utc).isoformat()}


def check_live(source: dict) -> tuple[str, dict]:
    result = {}
    for field in ("url", "landing_url", "metadata_url"):
        if field not in source:
            continue
        try:
            data, audit = fetch_url(source[field])
            audit["success"] = True
            if field == "url":
                audit["is_pdf"] = data.startswith(b"%PDF")
                audit["matches_pinned_pdf"] = sha(data) == EXPECTED_HASHES[source["id"]]
            result[field] = audit
        except Exception as exc:
            result[field] = {"success": False, "error": str(exc),
                             "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    return source["id"], result


def dates_for(source: dict) -> dict:
    sid = source["id"]
    publication = source.get("publication_date", source.get("landing_updated"))
    return {
        "publisher_document_date": publication,
        "publisher_date_kind": "PDF p2 publication statement" if sid.startswith("ubs") else "official landing page updated date",
        "publisher_html_datePublished": source.get("publisher_html_datePublished"),
        "sector_view_as_of_raw": {"fidelity_q2_2026": "3/31/2026", "fidelity_q3_2026": "6/31/26",
                                  "ubs_june_2026": "21 May 2026", "ubs_july_2026": "18 June 2026"}[sid],
        "sector_view_as_of_normalized": None if sid == "fidelity_q3_2026" else source.get("sector_view_as_of", source.get("source_as_of")),
        "sector_view_date_status": "invalid_calendar_date_printed_6/31/26_unresolved" if sid == "fidelity_q3_2026" else "valid_reported_date",
        "market_statistics_as_of": source.get("market_statistics_as_of"),
        "snapshot_cutoff": CUTOFF,
        "cutoff_interpretation": "retrospective document-snapshot availability cutoff; not contemporaneous information or historical replay",
    }


def make_packet(source: dict) -> tuple[dict, dict]:
    sid = source["id"]
    fidelity = sid.startswith("fidelity")
    page = 3 if fidelity else 21
    reasons = dict(FIDELITY_REASONS if fidelity else UBS_REASONS)
    if sid == "fidelity_q3_2026":
        reasons.update({"15": "Selected mining opportunities.", "60": "Possible higher interest rates create a headwind."})
    if sid == "ubs_july_2026":
        reasons["25"] = "AI adoption, fiscal support, wealth effects, and fading tariff pressure."
    vocabulary = ["Underweight", "Neutral", "Overweight"] if fidelity else ["Unattractive", "Neutral", "Attractive"]
    passages = []
    index = {}

    def add(eid: str, source_page: int, text: str, codes: list[str], claims: list[str]):
        passages.append({"evidence_id": eid, "source_id": sid, "source_page": source_page,
                         "text": text, "representation": "researcher paraphrase; original rating labels preserved"})
        index[eid] = {"source_id": sid, "sector_codes": codes, "claims": claims,
                      "source_page": source_page, "human_entailment_review": "pending"}

    if fidelity:
        add(f"{sid}:p2:scope", 2,
            "A strategist's US GICS-sector judgments use the largest 3,000 US stocks. They need not represent Fidelity firm-wide. Overweight and Underweight describe hypothetical tilts against broad-market sector weights; portfolio choices depend on investor goals and risk tolerance.",
            list(SECTORS), ["scope", "rating_semantics"])
    else:
        add(f"{sid}:p21:scope", 21,
            "This section presents UBS CIO's S&P 500 sector preferences. It combines cyclical and longer-term growth opportunities. Sector ratings here are distinct from the report's regional and asset-class views.",
            list(SECTORS), ["scope"])
        add(f"{sid}:p27:scale", 27,
            "Preferences express opportunity judgments over twelve months. Actual tactical allocations may differ because of portfolio construction, concentration, or borrowing constraints. Attractive is not an automatic overweight instruction. Neutral does not prescribe an exact benchmark weight.",
            list(SECTORS), ["rating_semantics"])
    ratings = {}
    for code, name in SECTORS.items():
        label = source["ratings"][name]
        eid = f"{sid}:p{page}:sector:{code}"
        sentence = f"{name} receives {label}."
        if code in reasons:
            sentence += " " + reasons[code]
        add(eid, page, sentence, [code], ["rating"] + (["reason"] if code in reasons else []))
        ratings[code] = {"rating": label, "evidence_ids": [eid],
                         "reason_evidence_ids": [eid] if code in reasons else [],
                         "reason_status": "source_reason_present" if code in reasons else "not_separately_stated_in_selected_sector_section"}
    dates = dates_for(source)
    packet = {
        "schema_version": VERSION, "packet_id": sid, "source_id": sid, "split": SPLITS[sid],
        "title": source["title"], "issuer": source["issuer"], "source_url": source["url"],
        "task_scope": "Interpret this published sector judgment and propose a justified allocation under the separate common market packet and execution rules.",
        "dates": dates,
        "sectors": [{"sector_code": code, "sector_name": name} for code, name in SECTORS.items()],
        "rating_vocabulary": vocabulary,
        "evidence_passages": passages,
        "numeric_target_weights_published_in_selected_section": False,
        "shared_benchmark_id": "sp500_sector_reference_20260630",
        "common_market_snapshot_cutoff": CUTOFF,
        "interpretation_notes": [
            "Keep the source's rating vocabulary; do not translate Attractive to Overweight.",
            "Some sectors have a displayed rating without a separately stated sector reason; do not invent one.",
            "Portfolio weights are your proposed decision, not hidden published institutional targets.",
        ],
    }
    reference = {
        "schema_version": VERSION, "source_id": sid, "split": SPLITS[sid],
        "access_role": "evaluator_only_do_not_append_to_model_prompt",
        "rating_vocabulary": vocabulary, "sector_ratings": ratings, "evidence_index": index,
        "source_date_reference": dates,
        "exact_numeric_allocation_reference": None,
        "reference_status": "machine_prepared_source_annotations_independent_human_review_pending",
        "review_status": {"human_source_validation": "pending", "human_reason_entailment": "pending",
                          "second_independent_human_adjudication": "pending"},
        "scoring_cautions": [
            "Correct evidence IDs alone do not establish that the cited passage entails the model's reasoning.",
            "Do not treat omission of a source reason as permission to invent one.",
            "Numeric allocations have no unique source-derived gold target.",
            "Fidelity directional fidelity requires a declared common benchmark; UBS ratings do not by themselves impose weight inequalities.",
        ],
    }
    if fidelity:
        reference["allocation_semantics"] = {
            "kind": "benchmark_relative_tilt",
            "baseline_id": "sp500_sector_reference_20260630",
            "label_directions": {"Overweight": 1, "Underweight": -1, "Neutral": 0},
            "status": "optional_directional_diagnostic_only_not_numeric_weight_gold",
            "scope_caution": "The benchmark is LIBERA's common S&P 500 reference. Source strategist universe is top 3000 US stocks; exact implementation is not prescribed.",
        }
    return packet, reference


def review_html(sources: list[dict]) -> str:
    cards = []
    for s in sources:
        sid = s["id"]
        page = 3 if sid.startswith("fidelity") else 21
        rows = "".join(
            f'<tr><th>{code} {html.escape(name)}</th><td><input name="{sid}.{code}.rating" aria-label="{sid} {name} rating"></td>'
            f'<td><textarea name="{sid}.{code}.reason" aria-label="{sid} {name} reason"></textarea></td>'
            f'<td><input name="{sid}.{code}.page" aria-label="{sid} {name} page"></td></tr>'
            for code, name in SECTORS.items())
        cards.append(f'''<section><h2>{html.escape(s['title'])}</h2>
<p><a href="{html.escape(s['url'], quote=True)}" target="_blank" rel="noreferrer">원문 PDF</a> · 등급표 {page}쪽 · 용어·범위 {'2' if sid.startswith('fidelity') else '27'}쪽</p>
<label>원문 발행일 / 위치 <input name="{sid}.publication_date"></label>
<label>원문 판단 기준일 (표기 그대로) / 이상 여부 <input name="{sid}.view_date_raw"></label>
<label>등급의 의미와 적용범위 <textarea name="{sid}.semantics"></textarea></label>
<label>실제 목표 비중이나 강제 제약이 있는가? 근거 페이지 <textarea name="{sid}.weight_targets"></textarea></label>
<table><thead><tr><th>산업</th><th>원문 등급 그대로</th><th>근거 요지 / 근거 미제시</th><th>페이지</th></tr></thead><tbody>{rows}</tbody></table>
<label>날짜·범위·전사 오류 및 이견 <textarea name="{sid}.issues"></textarea></label></section>''')
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>기관 산업 판단 자료 독립 검토지</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1150px;margin:32px auto;padding:0 20px;color:#162839;background:#f7f9fb}
h1{font-size:28px}h2{font-size:22px}section{background:white;border:1px solid #cbd5df;border-radius:10px;padding:24px;margin:24px 0}
label{display:block;margin:12px 0}input,textarea{box-sizing:border-box;width:100%;font:inherit;border:1px solid #98aabd;border-radius:4px;padding:7px;background:white}
textarea{min-height:64px}table{width:100%;border-collapse:collapse;margin:16px 0}th,td{border:1px solid #cbd5df;padding:8px;vertical-align:top}thead{background:#e9eff4}
th:first-child{width:24%}td:nth-child(2){width:20%}td:last-child{width:10%}button{font:inherit;background:#173e62;color:white;padding:10px 16px;border:0;border-radius:6px;margin:8px 10px 8px 0}
.notice{border-left:5px solid #b07820;padding:12px 18px;background:#fff7e7}@media print{button{display:none}section{break-before:page}body{background:white;margin:0}textarea{min-height:85px}}
</style><h1>기관 산업 판단 자료 독립 검토지</h1>
<p class="notice">현재 인간 검토는 미완료입니다. 이 양식은 평가자 참고 정답과 모델 응답·처리조건을 보여주지 않습니다. 기관명은 원문에 나타나므로 기관 정체성을 가린 검토는 아닙니다. 원문을 직접 확인하여 독립적으로 작성하고, 별도로 보관한 참고 주석과 이후 대조하십시오.</p>
<p>등급을 새 의미로 바꾸지 마십시오. 판단이 제시되었다고 해서 기관의 실제 보유비중·고객 위험허용도·유일한 정답 배분을 추론할 수 있는 것은 아닙니다.</p>
<form id="review"><label>검토자 식별자 <input name="reviewer_id" required></label><label>검토 일시 <input name="reviewed_at" type="datetime-local"></label>
''' + "\n".join(cards) + '''<label>최종 검토 상태 <select name="review_status"><option value="pending">검토 중 / 미완료</option><option value="independent_review_completed">독립 원문 검토 완료 (합의 확정과 별개)</option></select></label>
<button type="button" onclick="saveReview()">작성 내용 JSON 저장</button><button type="button" onclick="window.print()">인쇄 / PDF 저장</button></form>
<p>자동 전송이나 자동 저장은 없습니다. 저장 버튼으로 파일을 내려받으십시오. 이 양식을 열거나 생성한 것만으로 검토 완료가 기록되지 않습니다.</p>
<script>function saveReview(){const fields=Object.fromEntries(new FormData(document.getElementById('review')));const result={schema_version:'sector_documents_v4.2.1',worksheet_type:'independent_source_extraction_blind_to_reference_and_model_output',exported_at:new Date().toISOString(),fields};const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sector_source_review.json';a.click();URL.revokeObjectURL(a.href);}</script></html>'''


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-live", action="store_true", help="Check all publisher URLs; record HTTP status and PDF byte hashes.")
    ap.add_argument("--download-missing", action="store_true", help="Fetch missing checksum-pinned PDF cache entries.")
    args = ap.parse_args()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8-sig"))
    by_id = {s["id"]: s for s in inventory["sources"]}
    sources = [by_id[sid] for sid in SPLITS]
    cached = {}
    for s in sources:
        path = ROOT / s["local_evidence_pdf"]
        if not path.exists() and args.download_missing:
            data, _ = fetch_url(s["url"])
            if sha(data) != EXPECTED_HASHES[s["id"]]:
                raise ValueError(f"Unreviewed publisher version: {s['id']}; do not replace pinned evidence automatically")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if not path.exists():
            raise FileNotFoundError(f"{path}; use --download-missing or restore the pinned research cache")
        actual = sha(path.read_bytes())
        if actual != EXPECTED_HASHES[s["id"]] or s["sha256"] != actual:
            raise ValueError(f"Pinned evidence hash mismatch: {s['id']}")
        cached[s["id"]] = {"path": s["local_evidence_pdf"], "sha256": actual, "size_bytes": path.stat().st_size}
    previous = OUT / "source_manifest.json"
    live = {}
    if args.check_live:
        with ThreadPoolExecutor(max_workers=4) as pool:
            live = dict(pool.map(check_live, sources))
    elif previous.exists():
        live = {s["source_id"]: s.get("live_link_audit", {}) for s in json.loads(previous.read_text(encoding="utf-8"))["sources"]}
    packets, references = zip(*(make_packet(s) for s in sources))
    benchmark = {
        "benchmark_id": "sp500_sector_reference_20260630",
        "benchmark_name": "S&P 500 sector composition reported by Fidelity",
        "source_id": "fidelity_q3_2026", "source_url": by_id["fidelity_q3_2026"]["url"], "source_page": 2,
        "as_of": "2026-06-30", "publisher_document_date": "2026-07-16",
        "evidence_id": "fidelity_q3_2026:p2:benchmark",
        "raw_percent_by_sector_code": BENCHMARK_PERCENT, "raw_percent_sum": 99.9,
        "reported_precision_percentage_points": 0.1,
        "rounding_handling": "Raw values retained. Any sum-to-one normalization must be separately labeled as a calculation, not a published target.",
        "used_for_splits": ["pilot", "main"], "market_snapshot_cutoff": CUTOFF,
        "not_institution_target_weights": True,
        "scope_caution": "S&P 500 composition is a common reference, not the exact universe of Fidelity's top-3000-stock strategist research.",
    }
    manifest = {
        "schema_version": VERSION, "inventory_path": str(INVENTORY.relative_to(ROOT)).replace("\\", "/"),
        "inventory_sha256": sha(INVENTORY.read_bytes()), "builder_sha256": sha(Path(__file__).read_bytes()),
        "historical_availability_status": "publisher-dated retrospective snapshot; historical bytes not independently archived",
        "pdf_redistribution": "No PDFs are copied to data/sector_documents; checksum-pinned research cache is referenced only.",
        "sources": [{"source_id": s["id"], "split": SPLITS[s["id"]], "title": s["title"],
                     "url": s["url"], "landing_url": s.get("landing_url"), "metadata_url": s.get("metadata_url"),
                     "dates": dates_for(s), "cache": cached[s["id"]], "live_link_audit": live.get(s["id"], {}),
                     "source_pages": s["pages"], "human_review_status": "pending",
                     "known_source_issues": s.get("limitations", [])} for s in sources],
        "paper_scope": {"url": "https://arxiv.org/html/2503.09647v5", "version_date": "2025-04-10",
                        "supports": "GICS sector-allocation stage and separation from stock-level decisions; section 4.",
                        "does_not_support": "Our document dates, qualitative labels, exact numeric allocation targets, or arbitrary thresholds."},
    }
    all_codes = set(SECTORS)
    checks = {
        "four_packets_two_per_split": len(packets) == 4 and all(sum(p["split"] == split for p in packets) == 2 for split in ("pilot", "main")),
        "all_sources_hash_pinned": len(cached) == 4,
        "exactly_11_gold_sectors_each": all(set(r["sector_ratings"]) == all_codes for r in references),
        "all_ratings_in_source_vocabulary": all(v["rating"] in r["rating_vocabulary"] for r in references for v in r["sector_ratings"].values()),
        "all_gold_evidence_resolves_in_same_packet": all(set(r["evidence_index"]) == {e["evidence_id"] for e in p["evidence_passages"]} for p, r in zip(packets, references)),
        "all_source_labels_present_in_source_passage": all(v["rating"] in next(e["text"] for e in p["evidence_passages"] if e["evidence_id"] == v["evidence_ids"][0]) for p, r in zip(packets, references) for v in r["sector_ratings"].values()),
        "no_reference_answers_as_packet_fields": all(not (set(p) & {"sector_ratings", "evidence_index", "reference_status", "exact_numeric_allocation_reference"}) for p in packets),
        "publisher_document_dates_not_after_cutoff": all(p["dates"]["publisher_document_date"] <= CUTOFF for p in packets),
        "invalid_fidelity_date_preserved_not_normalized": next(p for p in packets if p["source_id"] == "fidelity_q3_2026")["dates"]["sector_view_as_of_raw"] == "6/31/26" and next(p for p in packets if p["source_id"] == "fidelity_q3_2026")["dates"]["sector_view_as_of_normalized"] is None,
        "benchmark_raw_sum_preserved": abs(sum(BENCHMARK_PERCENT.values()) - 99.9) < 1e-9,
        "no_unique_numeric_allocation_gold": all(r["exact_numeric_allocation_reference"] is None for r in references),
        "all_human_review_pending": all(r["review_status"]["human_source_validation"] == "pending" for r in references),
        "each_source_paraphrase_under_200_words": all(sum(len(e["text"].split()) for e in p["evidence_passages"]) <= 200 for p in packets),
    }
    if not all(checks.values()):
        raise AssertionError({key: val for key, val in checks.items() if not val})
    card = {
        "schema_version": VERSION, "construct": "published sector-judgment interpretation and justified proposed allocation",
        "unit": "document case; eleven GICS sectors within each case", "sectors": SECTORS,
        "splits": {split: [sid for sid, part in SPLITS.items() if part == split] for split in ("pilot", "main")},
        "common_market_snapshot_cutoff": CUTOFF, "common_benchmark_id": benchmark["benchmark_id"],
        "limitations": LIMITATIONS,
        "readiness": {"model_packets_prepared": True, "mechanical_checks_passed": True,
                      "independent_substantive_human_review": "pending", "experiment_run": False},
        "model_input_boundary": "Pass only the selected model packet plus the common market packet and execution rules. Do not include evaluator_only files or this corpus card's review metadata in model prompts.",
        "blind_review_definition": "Worksheet is blank and blind to reference answers and model outputs/treatments; source identities remain visible.",
        "reproduce": "python research/prepare_sector_documents.py; optionally --check-live or --download-missing",
    }
    write_jsonl(OUT / "model_packets.jsonl", packets)
    write_jsonl(OUT / "evaluator_only/reference_annotations.jsonl", references)
    for p in packets:
        write_json(OUT / "packets" / p["split"] / (p["source_id"] + ".json"), p)
    write_json(OUT / "shared_benchmarks.json", benchmark)
    write_json(OUT / "source_manifest.json", manifest)
    write_json(OUT / "corpus_card.json", card)
    (OUT / "blind_review_worksheet.html").write_text(review_html(sources), encoding="utf-8")
    verification = {
        "schema_version": VERSION, "mechanical_checks": checks, "all_mechanical_checks_passed": all(checks.values()),
        "source_paraphrase_word_counts": {p["source_id"]: sum(len(e["text"].split()) for e in p["evidence_passages"]) for p in packets},
        "verification_limits": "These checks establish packaging, ID integrity and pinned source versions. They do not constitute independent human validation of facts or entailment.",
        "live_url_checks_recorded": bool(live),
        "live_pdf_hashes_match": all(live.get(s["id"], {}).get("url", {}).get("matches_pinned_pdf", False) for s in sources) if live else None,
        "artifact_sha256": {str(path.relative_to(OUT)).replace("\\", "/"): sha(path.read_bytes()) for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "verification.json"},
    }
    write_json(OUT / "verification.json", verification)
    print(json.dumps({"output_dir": str(OUT), "packets": len(packets), "checks_passed": all(checks.values()),
                      "live_pdf_hashes_match": verification["live_pdf_hashes_match"],
                      "human_review": "pending", "word_counts": verification["source_paraphrase_word_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
