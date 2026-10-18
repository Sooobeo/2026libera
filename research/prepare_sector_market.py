"""Prepare public GICS-11 sector-ETF inputs for a retrospective document case.

This script downloads public issuer identity pages and Yahoo Finance chart
responses, then builds one common, pre-cutoff 60-return observation panel.
It never calls an AI model, modifies an experimental plan, or reads FF12.
The data are a current downloaded vendor vintage, not archived point-in-time
releases and not a realized-performance or causal historical backtest.

Usage:
    python research/prepare_sector_market.py --fetch-only
    python research/prepare_sector_market.py
    python research/prepare_sector_market.py --verify-only
Raw files are cached; --refresh explicitly fetches a new source vintage.
The common S&P 500 allocation is read from the independently prepared
data/sector_documents/shared_benchmarks.json and preserves reported rounding.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/sector_market"
RAW = OUT / "raw"
BENCHMARK_SOURCE = ROOT / "data/sector_documents/shared_benchmarks.json"
CUTOFF_EXCLUSIVE = "2026-07-17"
FETCH_START = "2026-03-01"
RETURN_COUNT = 60
ANNUAL_TRADING_DAYS = 252
ASSETS = [
    ("10", "Energy", "XLE", "energy"),
    ("15", "Materials", "XLB", "materials"),
    ("20", "Industrials", "XLI", "industrial"),
    ("25", "Consumer Discretionary", "XLY", "consumer-discretionary"),
    ("30", "Consumer Staples", "XLP", "consumer-staples"),
    ("35", "Health Care", "XLV", "health-care"),
    ("40", "Financials", "XLF", "financial"),
    ("45", "Information Technology", "XLK", "technology"),
    ("50", "Communication Services", "XLC", "communication-services"),
    ("55", "Utilities", "XLU", "utilities"),
    ("60", "Real Estate", "XLRE", "real-estate"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, content: object) -> None:
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def utc_stamp(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def issuer_url(ticker: str, slug: str) -> str:
    return f"https://www.ssga.com/us/en/individual/etfs/state-street-{slug}-select-sector-spdr-etf-{ticker.lower()}"


def chart_url(ticker: str) -> str:
    query = urllib.parse.urlencode({"period1": utc_stamp(FETCH_START), "period2": utc_stamp(CUTOFF_EXCLUSIVE),
                                   "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"


def retrieve(spec: tuple[str, str, str], refresh: bool) -> dict:
    name, url, kind = spec
    path = RAW / name
    meta_path = RAW / (name + ".metadata.json")
    if path.exists() and meta_path.exists() and not refresh:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        require(metadata["sha256"] == sha(path) and metadata["url"] == url, f"Cached source mismatch: {name}")
        return metadata
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=35) as response:
        raw = response.read()
        metadata = {"url": url, "resolved_url": response.url, "http_status": response.status,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "content_type": response.headers.get("Content-Type"),
                    "kind": kind, "path": str(path.relative_to(ROOT)).replace("\\", "/")}
    require(len(raw) > 100, f"Empty/short source: {name}")
    if kind == "yahoo_chart":
        content = json.loads(raw)
        require(content.get("chart", {}).get("error") is None, f"Chart API error: {name}")
        require(len(content["chart"]["result"]) == 1, f"Unexpected chart result: {name}")
    else:
        soup = BeautifulSoup(raw, "html.parser")
        require(soup.find("h1") is not None, f"Issuer page lacks product title: {name}")
    path.write_bytes(raw)
    metadata.update({"sha256": sha(path), "bytes": len(raw)})
    write_json(meta_path, metadata)
    return metadata


def fetch(refresh: bool = False) -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    specs = []
    for _, _, ticker, slug in ASSETS:
        specs += [(f"ssga_{ticker}.html", issuer_url(ticker, slug), "issuer_identity"),
                  (f"yahoo_{ticker}.json", chart_url(ticker), "yahoo_chart")]
    sources, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [(spec[0], pool.submit(retrieve, spec, refresh)) for spec in specs]
        for name, future in pending:
            try:
                sources.append(future.result())
            except Exception as error:
                errors.append({"file": name, "error_type": type(error).__name__, "message": str(error)})
    write_json(OUT / "download_status.json", {"complete": not errors, "successful_sources": sources, "errors": errors,
                                              "network_policy": "Public unauthenticated requests; no challenge bypass or credential use."})
    require(not errors, f"Source acquisition incomplete: {errors}")
    return sources


def parse_identity(asset: tuple[str, str, str, str]) -> dict:
    code, sector, ticker, slug = asset
    soup = BeautifulSoup((RAW / f"ssga_{ticker}.html").read_bytes(), "html.parser")
    title = soup.find("h1").get_text(" ", strip=True)
    require(title.startswith(ticker + " ") and "Select Sector" in title, f"Wrong issuer product for {ticker}")
    rows = [[c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])] for row in soup.find_all("tr")]
    benchmark = next(r[1] for r in rows if len(r) == 2 and r[0] == "Benchmark")
    inception = next(r[1] for r in rows if len(r) == 2 and r[0] == "Inception Date")
    listing = next(r for r in rows if len(r) == 6 and r[0] == "NYSE ARCA" and r[3] == ticker)
    listing_date = datetime.strptime(listing[1], "%b %d %Y").date().isoformat()
    inception_date = datetime.strptime(inception, "%b %d %Y").date().isoformat()
    require(listing[2] == "USD" and listing_date < FETCH_START, f"Insufficient listed history: {ticker}")
    return {"gics_code": code, "gics_sector": sector, "ticker": ticker, "issuer_title": title,
            "benchmark_index": benchmark, "inception_date": inception_date, "listing_date": listing_date,
            "exchange": listing[0], "currency": listing[2], "CUSIP": listing[4], "ISIN": listing[5],
            "issuer_url": issuer_url(ticker, slug), "issuer_raw_sha256": sha(RAW / f"ssga_{ticker}.html"),
            "identity_scope": "Issuer identity and listing-history verification from current public product page; current holdings, prices and fund characteristics are excluded from the experiment packet."}


def parse_chart(ticker: str) -> tuple[dict, dict, list[dict]]:
    data = json.loads((RAW / f"yahoo_{ticker}.json").read_text(encoding="utf-8"))["chart"]["result"][0]
    meta = data["meta"]
    require(meta["symbol"] == ticker and meta["currency"] == "USD" and meta["instrumentType"] == "ETF", f"Chart identity mismatch {ticker}")
    tz = ZoneInfo(meta["exchangeTimezoneName"])
    time = data["timestamp"]
    close = data["indicators"]["quote"][0]["close"]
    adjusted = data["indicators"]["adjclose"][0]["adjclose"]
    require(len(time) == len(close) == len(adjusted), f"Chart length mismatch {ticker}")
    rows = {}
    for timestamp, c, a in zip(time, close, adjusted):
        date = datetime.fromtimestamp(timestamp, tz).date().isoformat()
        require(date not in rows, f"Duplicate date {ticker} {date}")
        if date < CUTOFF_EXCLUSIVE and c is not None and a is not None:
            require(np.isfinite(c) and np.isfinite(a) and c > 0 and a > 0, f"Invalid price {ticker} {date}")
            rows[date] = {"close": float(c), "adjusted_close": float(a)}
    events = []
    for kind, records in data.get("events", {}).items():
        for event in records.values():
            day = datetime.fromtimestamp(event["date"], tz).date().isoformat()
            if day < CUTOFF_EXCLUSIVE:
                events.append({"kind": kind, "date": day, **{k: v for k, v in event.items() if k != "date"}})
    allowed_meta = {k: meta.get(k) for k in ("symbol", "currency", "instrumentType", "exchangeName", "fullExchangeName", "exchangeTimezoneName", "firstTradeDate")}
    return rows, allowed_meta, events


def load_benchmark() -> dict:
    require(BENCHMARK_SOURCE.exists(), "Independently verified shared_benchmarks.json is not ready")
    source = json.loads(BENCHMARK_SOURCE.read_text(encoding="utf-8"))
    # The document agent's source schema is validated explicitly below; this
    # adapter never extracts numeric weights from prose or invents a benchmark.
    benchmark = source
    values = benchmark["raw_percent_by_sector_code"]
    require(benchmark["as_of"] == "2026-06-30" and benchmark["publisher_document_date"] < CUTOFF_EXCLUSIVE, "Benchmark source date violates common cutoff")
    weights = [float(values[code]) for code, _, _, _ in ASSETS]
    require(len(values) == 11 and all(w > 0 for w in weights), "Invalid sector benchmark coverage")
    total = float(sum(weights))
    require(abs(total - 99.9) < 1e-10, "Unexpected reported-rounding total; review source rather than silently normalize")
    return {"benchmark_type": "reported_SP500_sector_market_composition", "source_record": benchmark,
            "source_file": "data/sector_documents/shared_benchmarks.json", "source_file_sha256": sha(BENCHMARK_SOURCE),
            "sector_codes": [a[0] for a in ASSETS], "reported_weights_percent": weights,
            "reported_sum_percent": total, "baseline_weights": [w / total for w in weights],
            "normalization": "Each reported percentage divided by the reported 99.9 total, solely to obtain an exact full-investment starting vector. These derived values are not additional source precision or institutional target weights.",
            "role": "Same market-composition reference for both institutions; not either institution's optimal allocation, a generic equal-weight assumption, or a model response.",
            "benchmark_proxy_limit": "Sector ETF portfolios have their own index caps, fees and tracking error. Weighting them by S&P 500 sector proportions is a sector-exposure proxy and does not exactly replicate the S&P 500."}


def provenance() -> dict:
    return {
        "sector_unit": {"url": "https://arxiv.org/html/2503.09647v5", "locator": "Methodology and Appendix 9.3", "adopted": "Reasoning across 11 GICS sectors", "not_adopted": "Paper-specific stock universe, agent models, long/short strategy or reported performance."},
        "ETF_proxy_precedent": {"url": "https://arxiv.org/html/2603.22305", "locator": "Section 3.3 and Appendix B", "adopted": "Sector ETF proxies for allocation reasoning", "limit": "The paper uses 14 Chinese sector instruments; selection of these 11 US SPDR funds is LIBERA's public implementation, not that paper's asset list."},
        "lookback": {"url": "https://arxiv.org/html/2605.27887v6", "locator": "Appendix B market context/B.2 covariance and C.1", "adopted": "60 trading-day return lookback and 252-day annualization convention for risk diagnostics", "implementation": "61 closes produce 60 daily returns; all 11 assets use exactly the same observed dates.", "limit": "Risk diagnostics only, no borrowed profile caps, objective coefficients, confidence levels or claimed future optimality."},
        "GICS_definition": {"url": "https://www.msci.com/indexes/index-resources/gics", "status": "official industry classification source; GICS is separate from FF12"},
        "data": {"price_provider": "Yahoo Finance public chart endpoint", "identity_provider": "State Street official product pages", "price_field": "indicators.adjclose[0].adjclose", "return_kind": "vendor_adjusted_close_return_proxy", "limit": "Yahoo's adjusted-close series is preserved without claiming issuer-certified NAV total return. Current vendor revisions/adjustments may differ from data published at the historical cutoff. Raw close and corporate-action events are retained separately."},
    }


def prepare(refresh: bool = False) -> dict:
    sources = fetch(refresh)
    identities = [parse_identity(a) for a in ASSETS]
    charts, chart_meta, events = {}, {}, {}
    for _, _, ticker, _ in ASSETS:
        charts[ticker], chart_meta[ticker], events[ticker] = parse_chart(ticker)
    date_sets = [set(charts[ticker]) for _, _, ticker, _ in ASSETS]
    common = sorted(set.intersection(*date_sets))
    require(len(common) >= RETURN_COUNT + 1, "Not enough complete common observations")
    dates = common[-(RETURN_COUNT + 1):]
    require(dates[-1] == "2026-07-16", "Expected final pre-cutoff close unavailable")
    require(all(sorted(day for day in date_set if dates[0] <= day <= dates[-1]) == dates for date_set in date_sets), "Missing/nonmatching instrument dates inside selected window; no forward fill permitted")
    adjusted = np.asarray([[charts[ticker][day]["adjusted_close"] for _, _, ticker, _ in ASSETS] for day in dates])
    close = np.asarray([[charts[ticker][day]["close"] for _, _, ticker, _ in ASSETS] for day in dates])
    returns = adjusted[1:] / adjusted[:-1] - 1
    price_returns = close[1:] / close[:-1] - 1
    require(returns.shape == (RETURN_COUNT, 11) and np.all(np.isfinite(returns)), "Invalid daily return panel")
    selected_events = {ticker: [e for e in rows if dates[0] < e["date"] <= dates[-1]] for ticker, rows in events.items()}
    require(not any(e["kind"] == "splits" for rows in selected_events.values() for e in rows), "A within-window split requires explicit split validation before use")
    mean = np.mean(returns, axis=0)
    covariance = np.cov(returns, rowvar=False, ddof=1)
    correlation = np.corrcoef(returns, rowvar=False)
    eig = np.linalg.eigvalsh(covariance)
    require(eig[0] > 0, "Selected daily covariance is not positive definite")
    benchmark = load_benchmark()
    baseline = np.asarray(benchmark["baseline_weights"])
    panel = {"schema_version": "1.0", "status": "public_downloaded_retrospective_input_not_AI_output",
             "sector_codes": [a[0] for a in ASSETS], "sector_names": [a[1] for a in ASSETS], "tickers": [a[2] for a in ASSETS],
             "cutoff_exclusive": CUTOFF_EXCLUSIVE, "price_dates": dates, "return_dates": dates[1:],
             "price_observations": len(dates), "return_observations": RETURN_COUNT, "currency": "USD",
             "vendor_adjusted_close": adjusted.tolist(), "vendor_close": close.tolist(),
             "daily_returns": returns.tolist(), "daily_price_returns_comparator": price_returns.tolist(),
             "return_kind": "vendor_adjusted_close_return_proxy", "selected_corporate_actions": selected_events,
             "missing_data_policy": "No fill or imputation; selected dates must be shared and complete for all assets.",
             "raw_metadata_exclusion": "Current quote/range/regularMarketTime values in raw Yahoo responses and current holdings/valuation fields on issuer pages are archive-only and never enter the market packet.",
             "chart_identity_metadata_only": chart_meta}
    packet = {"schema_version": "1.0", "role": "common_market_input_for_documentary_retrospective_case",
              "cutoff_exclusive": CUTOFF_EXCLUSIVE, "last_observation_date": dates[-1],
              "sector_codes": panel["sector_codes"], "sector_names": panel["sector_names"], "tickers": panel["tickers"],
              "lookback_return_dates": [dates[1], dates[-1]], "return_observations": RETURN_COUNT,
              "daily_mean_return": mean.tolist(), "sample_covariance_ddof_1": covariance.tolist(), "covariance": covariance.tolist(),
              "correlation": correlation.tolist(), "daily_volatility": np.sqrt(np.diag(covariance)).tolist(),
              "annualized_volatility_diagnostic": np.sqrt(np.diag(covariance) * ANNUAL_TRADING_DAYS).tolist(),
              "annualization_trading_days": ANNUAL_TRADING_DAYS,
              "lookback_compound_return": (adjusted[-1] / adjusted[0] - 1).tolist(),
              "baseline_id": "sp500_sector_reference_20260630",
              "baseline_weights": dict(zip(panel["sector_codes"], baseline.tolist())), "baseline_weights_array": baseline.tolist(),
              "benchmark_reported_weights_percent": benchmark["reported_weights_percent"],
              "benchmark_reported_sum_percent": benchmark["reported_sum_percent"],
              "baseline_derivation": benchmark["normalization"], "benchmark_label": "S&P 500 sector reference, 2026-06-30",
              "baseline_annualized_volatility_diagnostic": float(np.sqrt(baseline @ covariance @ baseline * ANNUAL_TRADING_DAYS)),
              "covariance_unit": "daily_decimal_return_squared",
              "units": "Daily decimal vendor-adjusted-close returns and daily decimal-squared sample covariance; no RF subtraction.",
              "interpretation": "Observed historical ETF return and covariance diagnostics, not true expected future returns, an optimal answer, or realized post-decision performance.",
              "asof_scope": "Dates of included observations precede 2026-07-17. Downloaded current vendor vintage does not establish historical availability of identical adjusted prices. Same packet is supplied to both institutions and all compared workflows.",
              "classification_scope": "11 GICS sectors represented by US Select Sector SPDR ETFs; not the FF12 industry portfolios or stock-picking universe."}
    write_json(OUT / "asset_registry.json", {"assets": identities, "provenance": provenance()})
    write_json(OUT / "aligned_panel.json", panel)
    write_json(OUT / "benchmark.json", benchmark)
    write_json(OUT / "market_packet.json", packet)
    # Public common packet intentionally contains no institution identity,
    # source-specific report title, report identifier, URL or stance rating.
    write_json(OUT / "market_input.json", packet)
    verification = verify()
    write_json(OUT / "verification.json", verification)
    summary = {"status": "prepared_verified_public_market_input_no_AI_results", "sector_count": 11,
               "cutoff_exclusive": CUTOFF_EXCLUSIVE, "price_dates": [dates[0], dates[-1]], "return_dates": [dates[1], dates[-1]],
               "price_observations": 61, "return_observations": 60, "all_assets_officially_identified": True,
               "return_kind": panel["return_kind"], "benchmark_type": benchmark["benchmark_type"],
               "source_percent_sum": benchmark["reported_sum_percent"], "baseline_sum": float(sum(baseline)),
               "covariance_minimum_eigenvalue": float(eig[0]), "verification": verification, "AI_calls": 0,
               "scope": "A common dated retrospective case input and risk diagnostic; not a historical causal/backtesting result.", "provenance": provenance()}
    write_json(OUT / "summary.json", summary)
    names = ["asset_registry.json", "aligned_panel.json", "benchmark.json", "market_packet.json", "market_input.json", "verification.json", "summary.json", "download_status.json"]
    manifest = {"schema_version": "1.0", "status": summary["status"], "generator": "research/prepare_sector_market.py",
                "generator_sha256": sha(Path(__file__)), "sources": sources,
                "benchmark_source_file": str(BENCHMARK_SOURCE.relative_to(ROOT)).replace("\\", "/"), "benchmark_source_sha256": sha(BENCHMARK_SOURCE),
                "outputs": {name: {"bytes": (OUT / name).stat().st_size, "sha256": sha(OUT / name)} for name in names},
                "runtime": {"python": platform.python_version(), "numpy": np.__version__},
                "reproduce_cached": "python research/prepare_sector_market.py", "refetch_new_vintage": "python research/prepare_sector_market.py --refresh",
                "AI_calls": 0, "FF12_inputs": 0, "provenance": provenance()}
    write_json(OUT / "manifest.json", manifest)
    return {"summary": summary, "manifest_sha256": sha(OUT / "manifest.json")}


def verify() -> dict:
    panel = json.loads((OUT / "aligned_panel.json").read_text(encoding="utf-8"))
    packet = json.loads((OUT / "market_packet.json").read_text(encoding="utf-8"))
    benchmark = json.loads((OUT / "benchmark.json").read_text(encoding="utf-8"))
    require(panel["sector_codes"] == packet["sector_codes"] == [a[0] for a in ASSETS], "GICS order mismatch")
    require(panel["tickers"] == packet["tickers"] == [a[2] for a in ASSETS], "Ticker order mismatch")
    raw_rows = {ticker: parse_chart(ticker)[0] for _, _, ticker, _ in ASSETS}
    reconstructed = np.asarray([[raw_rows[ticker][day]["adjusted_close"] for _, _, ticker, _ in ASSETS] for day in panel["price_dates"]])
    require(np.array_equal(reconstructed, np.asarray(panel["vendor_adjusted_close"])), "Raw-price reconstruction mismatch")
    returns = reconstructed[1:] / reconstructed[:-1] - 1
    require(np.array_equal(returns, np.asarray(panel["daily_returns"])), "Return reconstruction mismatch")
    require(returns.shape == (60, 11), "Return dimensions")
    mean = returns.sum(axis=0) / 60
    centered = returns - mean
    cov = centered.T @ centered / 59
    difference = float(np.max(np.abs(cov - np.asarray(packet["sample_covariance_ddof_1"]))))
    tolerance = np.finfo(float).eps * 60 * float(np.linalg.norm(cov, np.inf))
    require(difference <= tolerance and np.array_equal(mean, np.asarray(packet["daily_mean_return"])), "Moment reconstruction mismatch")
    require(np.linalg.eigvalsh(cov)[0] > 0, "Reconstructed covariance is not SPD")
    require(max(panel["price_dates"]) < CUTOFF_EXCLUSIVE and max(panel["return_dates"]) < CUTOFF_EXCLUSIVE, "Post-cutoff input")
    require(len(set(panel["price_dates"])) == 61 and panel["return_dates"] == panel["price_dates"][1:], "Date alignment")
    weights = np.asarray(benchmark["reported_weights_percent"])
    derived = weights / weights.sum()
    require(np.allclose(derived, packet["baseline_weights_array"], rtol=0, atol=2e-16), "Benchmark normalization mismatch")
    require(packet["baseline_weights"] == dict(zip(panel["sector_codes"], packet["baseline_weights_array"])), "Baseline code mapping mismatch")
    require(abs(float(derived.sum()) - 1) <= 4 * np.finfo(float).eps, "Benchmark budget mismatch")
    compound_residual = float(np.max(np.abs(np.prod(1 + returns, axis=0) - reconstructed[-1] / reconstructed[0])))
    require(compound_residual <= 60 * np.finfo(float).eps, "Return-chain identity failed")
    public_packet = (OUT / "market_input.json").read_text(encoding="utf-8")
    require(json.loads(public_packet) == packet, "Common public packet differs from verified packet")
    require(not any(term in public_packet.lower() for term in ("fidelity", "schwab", "q3_2026", "9906006", "source_record", "overweight", "underweight")), "Institution identity or source stance leaked through common market input")
    return {"all_passed": True, "raw_source_reconstruction": True, "assets": 11, "price_dates": 61, "return_dates": 60,
            "GICS_order_verified": True, "same_pre_cutoff_dates": True, "no_fill_or_imputation": True,
            "independent_covariance_maximum_residual": difference, "return_chain_maximum_residual": compound_residual,
            "benchmark_reported_values_preserved": True, "explicit_proportional_normalization_verified": True,
            "AI_calls": 0, "scope": "Numerical/source interface validation, not empirical strategy validation."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    arguments = parser.parse_args()
    if arguments.fetch_only:
        result = {"downloaded_sources": len(fetch(arguments.refresh)), "AI_calls": 0}
    elif arguments.verify_only:
        result = verify()
    else:
        result = prepare(arguments.refresh)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
