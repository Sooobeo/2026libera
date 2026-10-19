"""Download dated public releases and build the common v4.9.1 macro context.

Run with Python 3. Uses only stdlib, BeautifulSoup and pypdf. No model calls.
The released figures, not today's revised time-series database, are the source.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCES = OUT / "sources"
CUTOFF = "2026-07-17"
RELEASES = [
    {
        "source_id": "FED_FOMC_20260617",
        "publisher": "Board of Governors of the Federal Reserve System",
        "title": "Federal Reserve issues FOMC statement, June 17, 2026",
        "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
        "filename": "fed_fomc_20260617.html",
        "publication_date": "2026-06-17",
        "publication_time_local": "14:00:00",
        "publication_timezone": "America/New_York",
        "publication_date_text": "June 17, 2026",
        "locator": "Dated press release, first policy-decision paragraph",
        "vintage": "Dated policy announcement; not a later statistical time-series extraction",
    },
    {
        "source_id": "BLS_CPI_20260714",
        "publisher": "U.S. Bureau of Labor Statistics",
        "title": "Consumer Price Index, June 2026, released July 14, 2026",
        "url": "https://www.bls.gov/news.release/archives/cpi_07142026.htm",
        "filename": "bls_cpi_20260714.web_snapshot.txt",
        "capture_type": "web_tool_rendered_official_archive_excerpt",
        "publication_date": "2026-07-14",
        "publication_time_local": "08:30:00",
        "publication_timezone": "America/New_York",
        "publication_date_text": "July 14, 2026",
        "locator": "Archive release header and opening CPI-U paragraphs; Table A",
        "vintage": "June 2026 figures as printed in the July 14 release, not a current BLS API series",
    },
    {
        "source_id": "BLS_EMPSIT_20260702",
        "publisher": "U.S. Bureau of Labor Statistics",
        "title": "The Employment Situation, June 2026, released July 2, 2026",
        "url": "https://www.bls.gov/news.release/archives/empsit_07022026.htm",
        "filename": "bls_empsit_20260702.web_snapshot.txt",
        "capture_type": "web_tool_rendered_official_archive_excerpt",
        "publication_date": "2026-07-02",
        "publication_time_local": "08:30:00",
        "publication_timezone": "America/New_York",
        "publication_date_text": "July 2, 2026",
        "locator": "Archive release header and opening paragraph; Tables A-1 and B-1",
        "vintage": "June 2026 first-release estimates; subsequent payroll revisions are excluded",
    },
    {
        "source_id": "BEA_GDP_20260625",
        "publisher": "U.S. Bureau of Economic Analysis",
        "title": "GDP (Third Estimate), 1st Quarter 2026, June 25, 2026",
        "url": "https://www.bea.gov/sites/default/files/2026-06/gdp1q26-3rd.pdf",
        "filename": "bea_gdp_20260625.pdf",
        "publication_date": "2026-06-25",
        "publication_time_local": "08:30:00",
        "publication_timezone": "America/New_York",
        "publication_date_text": "June 25, 2026",
        "locator": "Release PDF page 1 and Real GDP and Related Measures table on page 3",
        "vintage": "2026 Q1 third estimate released June 25; later annual updates are excluded",
    },
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def download_release(source: dict) -> tuple[dict, str]:
    path = SOURCES / source["filename"]
    if not path.exists():
        if source.get("capture_type") == "web_tool_rendered_official_archive_excerpt":
            raise FileNotFoundError("Archived web-tool evidence must be restored from the repository; direct BLS downloads returned HTTP 403: " + str(path))
        request = urllib.request.Request(source["url"], headers={"User-Agent": "Mozilla/5.0 (academic public-data audit)"})
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}: {source['url']}")
            fetched_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
        path.write_bytes(raw)
        transport = {
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "requested_url": source["url"],
            "final_url": fetched_url,
            "http_status": 200,
            "content_type": content_type,
            "sha256": sha(raw),
        }
        path.with_suffix(path.suffix + ".retrieval.json").write_text(json.dumps(transport, indent=2) + "\n", encoding="utf-8")
    raw = path.read_bytes()
    transport = json.loads(path.with_suffix(path.suffix + ".retrieval.json").read_text(encoding="utf-8"))
    if "sha256" in transport:
        assert sha(raw) == transport["sha256"], f"Stored source evidence changed: {path}"
    if source.get("capture_type") == "web_tool_rendered_official_archive_excerpt":
        extracted = re.sub(r"L\d+(?:@P\d+(?:-\d+)?)?:", " ", raw.decode("utf-8"))
    elif path.suffix == ".pdf":
        extracted = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    else:
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        extracted = soup.get_text(" ", strip=True)
    text_path = path.with_suffix(".extracted.txt")
    text_path.write_text(norm(extracted) + "\n", encoding="utf-8")
    return source | {
        "evidence_path": path.relative_to(ROOT).as_posix(),
        "evidence_sha256": sha(raw),
        "capture_type": source.get("capture_type", "direct_official_original_download"),
        "extracted_path": text_path.relative_to(ROOT).as_posix(),
        "extracted_sha256": sha(text_path.read_bytes()),
        "retrieval": transport,
    }, norm(extracted)


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(download_release, RELEASES))
    source_records = {record["source_id"]: record for record, _ in fetched}
    source_text = {record["source_id"]: text for record, text in fetched}

    facts = [
        ("MACRO_FED_TARGET_20260617", "FED_FOMC_20260617", "Federal funds target range announced by FOMC", {"lower": 3.5, "upper": 3.75}, "percent per year", "2026-06-17 policy decision", "not applicable", "federal funds rate at 3-1/2 to 3-3/4 percent", "This is a policy target range, not an observed effective rate or an assumed future rate.", "interest_rate"),
        ("MACRO_CPI_HEADLINE_MOM_202606", "BLS_CPI_20260714", "CPI-U all items change from previous month", -0.4, "percent month over month", "2026-06", "seasonally adjusted", "decreased 0.4 percent", "Monthly price change; do not interpret as an annual inflation rate.", "inflation"),
        ("MACRO_CPI_HEADLINE_YOY_202606", "BLS_CPI_20260714", "CPI-U all items change over twelve months", 3.5, "percent year over year", "2025-06 to 2026-06", "not seasonally adjusted", "index increased 3.5 percent before seasonal adjustment", "Twelve-month price change ending June 2026.", "inflation"),
        ("MACRO_CPI_CORE_YOY_202606", "BLS_CPI_20260714", "CPI-U excluding food and energy change over twelve months", 2.6, "percent year over year", "2025-06 to 2026-06", "not seasonally adjusted", "rose 2.6 percent", "Core CPI excludes food and energy; it is not PCE inflation.", "inflation"),
        ("MACRO_UNEMPLOYMENT_202606", "BLS_EMPSIT_20260702", "Civilian unemployment rate", 4.2, "percent of civilian labor force", "2026-06", "seasonally adjusted", "unemployment rate (4.2 percent)", "Household-survey unemployment measure; not the payroll employment growth rate.", "labor_context"),
        ("MACRO_NONFARM_CHANGE_202606", "BLS_EMPSIT_20260702", "Change in total nonfarm payroll employment", 57000, "jobs from previous month", "2026-06", "seasonally adjusted", "payroll employment (+57,000)", "First-release establishment-survey estimate; subsequent revisions are excluded.", "labor_context"),
        ("MACRO_REAL_GDP_Q1_2026_THIRD", "BEA_GDP_20260625", "Real GDP change from previous quarter, annualized", 2.1, "percent quarter over quarter at annual rate", "2026-Q1", "seasonally adjusted annual rate", "annual rate of 2.1 percent", "Third estimate for January-March 2026; not Q2 growth, a year-over-year rate, or a forecast.", "activity_context"),
    ]
    packet_facts = []
    checks = []
    for record, extracted in fetched:
        checks.extend([
            {"check": f"{record['source_id']}:publication_date_in_original", "pass": record["publication_date_text"] in extracted},
            {"check": f"{record['source_id']}:published_before_cutoff", "pass": date.fromisoformat(record["publication_date"]) < date.fromisoformat(CUTOFF)},
            {"check": f"{record['source_id']}:official_publisher", "pass": urllib.parse.urlparse(record["url"]).hostname in {"www.federalreserve.gov", "www.bls.gov", "www.bea.gov"}},
        ])
    for eid, sid, label, value, unit, period, adjustment, excerpt, note, basis in facts:
        source = source_records[sid]
        checks.append({"check": f"{eid}:excerpt_in_archived_release", "pass": excerpt in source_text[sid]})
        packet_facts.append({
            "evidence_id": eid,
            "label": label,
            "value": value,
            "unit": unit,
            "observation_period": period,
            "seasonal_adjustment": adjustment,
            "publication_date": source["publication_date"],
            "publication_time_local": source["publication_time_local"],
            "publication_timezone": source["publication_timezone"],
            "source_id": sid,
            "source_url": source["url"],
            "source_excerpt": excerpt,
            "source_locator": source["locator"],
            "release_vintage": source["vintage"],
            "cutoff_status": "dated_official_release_precedes_exclusive_cutoff",
            "interpretation_note": note,
            "variable_selection_basis": basis,
        })
    checks.append({"check": "unique_fact_evidence_ids", "pass": len({f['evidence_id'] for f in packet_facts}) == len(packet_facts)})
    if not all(check["pass"] for check in checks):
        raise AssertionError(json.dumps([c for c in checks if not c["pass"]], indent=2))

    selection = {
        "framework_reference": {
            "paper": "PortBench: A Correlation-Aware, Full-Pipeline Benchmark for LLM-Driven Portfolio Management, v6",
            "url": "https://arxiv.org/html/2605.27887v6",
            "sections": ["2.1 Benchmark Construction", "Appendix B, Market context at decision time", "Appendix H.1 Market Snapshot Examples"],
            "supported_design": "Provide macroeconomic context together with trailing asset statistics, correlations and explicit portfolio/task state. Section 2.1 explicitly includes interest rates and inflation measures.",
            "not_claimed": "This seven-fact subset, exact official series and the extra labor/activity indicators are not a verbatim PortBench replication or a paper-validated optimal feature set.",
        },
        "sector_allocation_reference": {
            "paper": "Quek et al., Leveraging LLMs for Top-Down Sector Allocation in Automated Trading",
            "url": "https://arxiv.org/html/2503.09647v5",
            "latest_version_checked": "v5, April 10, 2025; arXiv abstract submission history checked October 19, 2026",
            "sections": ["3 Data Source", "4 Design Process"],
            "supported_design": "Sector-allocation input categories explicitly include interest rates, inflation, employment and growth; CPI and nonfarm payrolls are named. Official release dates govern availability.",
            "adaptation": "Use a compact dated-release table instead of the paper's multi-agent macro memory pipeline, stock news and PMI. Do not import its asset ranks, trading parameters or performance claims.",
        },
        "macro_measurement_reference": {
            "paper": "Zhao et al., Can LLMs Take the Pulse of the Economy? A Real-Time Evaluation of LLM Nowcasts on Macroeconomic Indicators",
            "url": "https://arxiv.org/html/2608.30110v1",
            "latest_version_checked": "v1, August 31, 2026; arXiv abstract submission history checked October 19, 2026",
            "sections": ["3.3 Macroeconomic Indicators", "Appendix D, Table 2: Variable definitions"],
            "supported_design": "The published variable table distinguishes real GDP quarterly annualized growth, CPI yearly growth, monthly nonfarm employment change and the unemployment-rate level, with explicit units and seasonal adjustment.",
            "adaptation": "These already-released indicators are background facts here, not nowcast targets. This reference supports variable definitions and temporal discipline, not optimal sector allocation or this seven-row subset's sufficiency.",
        },
        "interest_rate": "Paper-supported interest-rate category implemented using the dated official FOMC target-range announcement.",
        "inflation": "Paper-supported inflation category implemented using headline monthly/yearly CPI-U and core yearly CPI-U from one dated BLS release.",
        "labor_context": "Employment category and NFP are explicit in Quek et al. section 3. LiveMacroEval Table 2 defines both NFP monthly change and unemployment level. Transfer those categories to a compact common context using the original BLS release; do not import a regime label, weight or trading instruction.",
        "activity_context": "Economic growth is explicit in Quek et al. section 3 (using PMI there); GDP QoQ SAAR is defined in LiveMacroEval Table 2. The local adaptation uses dated BEA GDP as a publicly archived activity measure and retains its quarter and estimate vintage; it is not asserted equivalent to PMI.",
        "selection_lock": "Chosen before any v4.9.1 model output; same rows, values and ordering in every E/L and source condition. Do not add/remove facts after viewing an institutional contrast.",
        "omitted_from_minimal_context": "No researcher-written sector outlook, causal trading rule, forecast, sentiment score or numerical macro-to-weight coefficient. No live FRED/current-vintage series substitutes for dated release figures.",
    }
    packet = {
        "schema_version": "libera_common_market_context_v4.9.1",
        "packet_id": "us_macro_release_context_cutoff_20260717",
        "cutoff_exclusive": CUTOFF,
        "cutoff_timezone": "America/New_York",
        "decision_information_date": "2026-07-16",
        "role": "Common factual macro context supplied from the first draft to every condition, alongside the existing eleven-sector market packet and common task brief.",
        "facts": packet_facts,
        "information_policy": [
            "Use these dated release values as the common information set. Observation periods and publication dates are different fields.",
            "No fact in this packet implies a prescribed sector preference or allocation. A model may draw a conditional inference but must label it as its own inference and cite the relevant evidence IDs.",
            "The target-date context is July 2026; do not insert knowledge of later outcomes, later statistical revisions, or today's market state.",
            "A source outlook may have been written before these releases. Treat any resulting tension as dated evidence to explain, not as evidence that the outlook's author saw subsequent information.",
        ],
        "scope_limitations": [
            "Compact public-release context is not an exhaustive professional information terminal, complete client mandate, or a forecast target.",
            "These files were retrieved in October 2026 from official dated release archives. The original release date and retained release text support availability; there is no independently timestamped July download for this project.",
            "Fed HTML and BEA PDF originals are saved. BLS direct downloads returned HTTP 403, so the accessible official archive text is retained as exact web-tool snapshots; these snapshots are explicitly not original HTML files.",
            "The existing ETF adjusted-price input retains its current-vendor-vintage limitation. Adding release-vintage macro facts does not convert the full case into a verified point-in-time backtest.",
            "GDP is lagged quarterly information; employment first estimates and seasonally adjusted series can be revised. This packet preserves the selected release vintage.",
        ],
        "selection_provenance": selection,
    }
    packet_path = OUT / "market_context.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # A second pass reconstructs numbers from source text rather than comparing
    # hard-coded packet values to a second copy of the same constants.
    def number(source_id: str, expression: str) -> float:
        match = re.search(expression, source_text[source_id], flags=re.IGNORECASE)
        if match is None:
            raise AssertionError("Source-number extraction failed: " + expression)
        return float(match.group(1).replace(",", ""))

    rate_match = re.search(r"federal funds rate at (\d+)-(\d+)/(\d+) to (\d+)-(\d+)/(\d+) percent", source_text["FED_FOMC_20260617"])
    assert rate_match
    r = list(map(int, rate_match.groups()))
    independently_parsed = {
        "MACRO_FED_TARGET_20260617": {"lower": r[0] + r[1] / r[2], "upper": r[3] + r[4] / r[5]},
        "MACRO_CPI_HEADLINE_MOM_202606": -number("BLS_CPI_20260714", r"CPI-U\) decreased ([\d.]+) percent"),
        "MACRO_CPI_HEADLINE_YOY_202606": number("BLS_CPI_20260714", r"items index increased ([\d.]+) percent before seasonal adjustment"),
        "MACRO_CPI_CORE_YOY_202606": number("BLS_CPI_20260714", r"all items less food and energy index rose ([\d.]+) percent over the year"),
        "MACRO_UNEMPLOYMENT_202606": number("BLS_EMPSIT_20260702", r"unemployment rate \(([\d.]+) percent\)"),
        "MACRO_NONFARM_CHANGE_202606": number("BLS_EMPSIT_20260702", r"payroll employment \(\+([\d,]+)\)"),
        "MACRO_REAL_GDP_Q1_2026_THIRD": number("BEA_GDP_20260625", r"GDP\) increased at an annual rate of ([\d.]+) percent"),
    }
    numeric_checks = [{"check": f["evidence_id"] + ":independent_source_number_reconstruction", "pass": f["value"] == independently_parsed[f["evidence_id"]]} for f in packet_facts]
    scope_checks = [
        {"check": "all_rows_common_macro_not_institution_source", "pass": all(f["evidence_id"].startswith("MACRO_") for f in packet_facts)},
        {"check": "no_institution_names_in_common_packet", "pass": re.search(r"\b(?:fidelity|ubs)\b", json.dumps(packet), flags=re.IGNORECASE) is None},
        {"check": "all_fact_temporal_units_explicit", "pass": all(all(f[k] for k in ("unit", "observation_period", "publication_date", "seasonal_adjustment", "release_vintage")) for f in packet_facts)},
        {"check": "no_sector_weight_or_regime_fields", "pass": not any(k in f for f in packet_facts for k in ("weight", "sector_preference", "risk_on", "risk_off", "regime"))},
    ]
    assert all(c["pass"] for c in numeric_checks + scope_checks), [c for c in numeric_checks + scope_checks if not c["pass"]]
    audit = {
        "schema_version": "libera_v491_macro_source_audit_v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "scope": "Official release provenance, dates, units and exact source fragments. This is not model-output validation or independent human review.",
        "packet_path": packet_path.relative_to(ROOT).as_posix(),
        "packet_sha256": sha(packet_path.read_bytes()),
        "fact_count": len(packet_facts),
        "release_count": len(source_records),
        "checks": checks,
        "validation_rounds": [
            {"round": 1, "scope": "Official-source identity, release date before cutoff, source fragments and unique IDs", "status": "PASS", "checks": checks},
            {"round": 2, "scope": "Reconstruct each numeric value independently from preserved source text, including fraction conversion and negative monthly CPI sign", "status": "PASS", "checks": numeric_checks},
            {"round": 3, "scope": "Common-context isolation and explicit measurement boundaries; no institutional forecast, sector weights or assigned macro regime", "status": "PASS", "checks": scope_checks},
        ],
        "sources": list(source_records.values()),
        "method_reference_and_adaptations": selection,
        "measurement_caveats": packet["scope_limitations"],
        "reproduction_command": "python -B -X utf8 data/sector_context/v491_20261019/build_market_context.py",
        "no_model_inference_performed": True,
    }
    audit_path = ROOT / "research" / "v491_macro_source_audit_20261019.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "checks": len(checks), "facts": len(packet_facts), "packet_bytes": packet_path.stat().st_size, "packet_sha256": audit["packet_sha256"]}))


if __name__ == "__main__":
    main()
