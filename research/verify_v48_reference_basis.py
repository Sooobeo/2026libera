"""Read-only checks of v4.8 reference metadata, source hashes, and budget accounting."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MEMO = ROOT / "research/v48_reference_basis_20261018.json"
OUT = ROOT / "research/evidence/v48_reference_20261018/reference_self_validation.json"


def main():
    memo = json.loads(MEMO.read_text(encoding="utf-8"))
    checks = []
    def check(key, ok, detail=None):
        checks.append({"id": key, "status": "pass" if ok else "fail", "detail": detail})
    refs = memo["primary_sources"] + memo["historical_context_references"]
    for item in refs:
        data = (ROOT / item["path"]).read_bytes()
        check("sha256:" + item["path"], hashlib.sha256(data).hexdigest() == item["sha256"] and len(data) == item["size_bytes"])
    source_by_id = {x["source_id"]: x for x in memo["primary_sources"]}
    paper_by_id = {x["id"]: x for x in memo["papers"]}
    expected = {"uptake": (1, 10), "symbolic": (1, 6), "finfirst": (1, 11), "externalization": (2, 4), "e2a": (1, 3), "fundapod": (5, 3), "instrument": (2, 5)}
    check("exact_seven_primary_papers", set(paper_by_id) == set(expected))
    texts = {}
    for sid, (version, authors) in expected.items():
        p = paper_by_id[sid]
        abs_soup = BeautifulSoup((ROOT / source_by_id[sid + "_abs_latest"]["path"]).read_bytes(), "html.parser")
        dateline = " ".join(abs_soup.select_one(".dateline").stripped_strings)
        seen_version = int(re.search(r"this version, v(\d+)", dateline).group(1)) if "this version" in dateline else 1
        seen_authors = [m["content"] for m in abs_soup.find_all("meta", attrs={"name": "citation_author"})]
        check("latest_version:" + sid, seen_version == version == p["version"])
        check("author_metadata:" + sid, len(seen_authors) == authors and seen_authors == p["metadata"]["citation_authors_original"] == [a["original_citation_author"] for a in p["bibliography"]["authors"]])
        full_soup = BeautifulSoup((ROOT / source_by_id[sid + "_fulltext"]["path"]).read_bytes(), "html.parser")
        texts[sid] = full_soup.get_text(" ", strip=True)
        check("fulltext_version:" + sid, p["arxiv_id"] + "v" + str(version) in texts[sid])
        check("support_fields:" + sid, all(p.get(k) for k in ("locators", "direct_support_ko", "application_ko", "adaptations_and_limits_ko", "numbers_adopted_or_rejected", "support_class")))
    # These presence checks supplement, rather than replace, the contextual source reading.
    check("uptake_budget_and_memory_locators", all(s in texts["uptake"] for s in ("Table 12", "Up to 3 outer", "I.5", "raw chat history")))
    check("symbolic_feedback_locators", all(s in texts["symbolic"] for s in ("III-B", "preset maximum")))
    check("finfirst_rubric_locators", all(s in texts["finfirst"] for s in ("2.2.2", "2.2.3", "2.3")))
    check("externalization_registry_and_scope", all(s in texts["externalization"] for s in ("3.4", "4.1.2", "unrestricted free form text")))
    check("e2a_corrected_section", "4.3.3 Scaling Is Not Monotonic" in texts["e2a"] and "3.3 Evidence Anchor Construction" in texts["e2a"])
    check("fundapod_design_and_discussion", all(s in texts["fundapod"] for s in ("DP2", "DP3", "DP4", "7 Discussion")))
    check("instrument_failure_and_execution_locators", all(s in texts["instrument"] for s in ("V-A Matrix and randomization", "V-C End-to-end outcome", "VII-C Failure boundaries")))
    instrument = paper_by_id["instrument"]
    check("instrument_exact_apa_author_order", instrument["bibliography"]["apa_authors"] == "Xiao, H., Xu, C., Zhou, K., Qian, G., & Yi, L.")
    check("instrument_latest_date", "9 Oct 2026" in instrument["metadata"]["dateline_original"] and instrument["bibliography"]["version_date"] == "2026-10-09")
    d = memo["selected_design"]
    check("three_endpoint_candidates_not_three_retries", d["max_endpoint_candidates_including_C0"] == 3 and d["max_additional_generation_calls"] == 2)
    check("four_stage_and_aux_budget", any(x.get("value") == 6 and x["item"] == "max generation calls per case" for x in memo["numeric_provenance"]) and 4 + d["max_additional_generation_calls"] == 6)
    check("four_case_generation_budget", any(x.get("value") == 24 and x["item"] == "max generation calls per four-case pilot" for x in memo["numeric_provenance"]) and 4 * 6 == 24)
    check("schema_transport_not_eligible", {"provider/transport failure", "strict JSON parse failure", "response schema failure"}.issubset(d["ineligible_failure_types"]))
    check("no_equal_realized_calls_claim", d["same_policy_across_arms"] and not d["equal_actual_calls_claimed"])
    check("no_implementation_or_main_claim", memo["model_calls_by_researcher"] == 0 and memo["main_model_calls"] == 0 and not memo["new_runtime_implementation"] and not memo["main_ready"] and not memo["main_frozen"])
    raw = MEMO.read_bytes()
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "Internal reference-file quality checks; not model performance, independent human review or three separate design audits.", "reviewed_file": {"path": MEMO.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}, "checks": checks, "all_passed": all(c["status"] == "pass" for c in checks), "failed_checks": [c["id"] for c in checks if c["status"] != "pass"], "model_calls": 0}
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"all_passed": report["all_passed"], "checks": len(checks), "failed_checks": report["failed_checks"], "output": OUT.relative_to(ROOT).as_posix()}))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
