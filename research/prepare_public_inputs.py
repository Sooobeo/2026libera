"""Download and audit public French industry inputs; do not freeze experiment choices.

Run from any directory: python research/prepare_public_inputs.py
Only research/prepare_public_inputs.py and data/french/ are maintained here.
Raw downloads are immutable timestamped snapshots.  --offline reuses the latest
manifest and verifies every raw SHA256 without contacting the source website.
The 1964--2023 window prepares Salcher (2026) inputs, not a paper replication.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import zipfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "french"
LIBRARY = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"
MISSING_SENTINELS = {-99.99, -999.0}
EXPECTED_FF12 = [
    "NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq",
    "Telcm", "Utils", "Shops", "Hlth", "Money", "Other",
]
MONTH_ROW = re.compile(r"^\s*(\d{6})\s+(.+?)\s*$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(serialized, encoding="utf-8")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href" and value)


def source_link(html: str, page_url: str, filename: str) -> str:
    parser = Links()
    parser.feed(html)
    matches = {
        urljoin(page_url, href)
        for href in parser.hrefs
        if Path(urlparse(urljoin(page_url, href)).path).name.casefold() == filename.casefold()
    }
    if len(matches) != 1:
        raise ValueError(f"Expected one source link for {filename}, got {sorted(matches)}")
    url = matches.pop()
    if urlparse(url).hostname != "mba.tuck.dartmouth.edu":
        raise ValueError(f"Unexpected source host: {url}")
    return url


def fetch(url: str, raw_dir: Path, source_id: str, discovered_on: str | None) -> dict:
    request = Request(url, headers={"User-Agent": "LIBERA-public-research-input-preparation/1.0"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
        record = {
            "source_id": source_id,
            "requested_url": url,
            "resolved_url": response.geturl(),
            "downloaded_at_utc": utc_now(),
            "content_type": response.headers.get("Content-Type"),
            "last_modified_header": response.headers.get("Last-Modified"),
            "etag_header": response.headers.get("ETag"),
            "discovered_on": discovered_on,
            "sha256": sha256(payload),
            "bytes": len(payload),
        }
    filename = Path(urlparse(url).path).name
    path = raw_dir / filename
    if path.exists():
        raise FileExistsError(f"Never overwrite raw input: {path}")
    path.write_bytes(payload)
    record["path"] = path.relative_to(ROOT).as_posix()
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"ZIP CRC failure: {bad}")
            record["members"] = [
                {"name": item.filename, "bytes": item.file_size,
                 "sha256": sha256(archive.read(item))}
                for item in archive.infolist() if not item.is_dir()
            ]
    return record


def raw_bytes(record: dict) -> bytes:
    payload = (ROOT / record["path"]).read_bytes()
    if sha256(payload) != record["sha256"]:
        raise ValueError(f"Raw SHA256 changed: {record['path']}")
    return payload


def zip_text(record: dict) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes(record))) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) != 1 or not members[0].filename.lower().endswith(".txt"):
            raise ValueError(f"Unexpected ZIP members: {record['path']}")
        return archive.read(members[0]).decode("utf-8-sig")


def month_key(yyyymm: str) -> str:
    year, month = int(yyyymm[:4]), int(yyyymm[4:])
    if not (1900 <= year <= 2200 and 1 <= month <= 12):
        raise ValueError(f"Invalid month: {yyyymm}")
    return f"{year:04d}-{month:02d}"


def month_range(start: str, end: str) -> list[str]:
    year, month = map(int, start.split("-"))
    out = []
    while f"{year:04d}-{month:02d}" <= end:
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def parse_month_rows(lines: list[str], header_line: int, columns: list[str]) -> dict:
    dates, values = [], []
    index = header_line + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    start_line = index
    while index < len(lines):
        match = MONTH_ROW.fullmatch(lines[index])
        if not match:
            break
        fields = match.group(2).split()
        if len(fields) != len(columns):
            raise ValueError(f"Wrong field count on line {index + 1}")
        numeric = [float(field) for field in fields]
        if not all(np.isfinite(numeric)):
            raise ValueError(f"Nonfinite raw value on line {index + 1}")
        dates.append(month_key(match.group(1)))
        values.append([None if x in MISSING_SENTINELS else x / 100 for x in numeric])
        index += 1
    if not dates or dates != month_range(dates[0], dates[-1]):
        raise ValueError("Monthly rows must be unique, increasing and calendar-complete")
    return {
        "columns": columns,
        "dates": dates,
        "values": values,
        "first_data_line_1based": start_line + 1,
        "last_data_line_1based": index,
        "next_nondata_line": next((x.strip() for x in lines[index:] if x.strip()), None),
    }


def parse_industry_monthly(text: str, n: int, source_id: str) -> dict:
    lines = text.splitlines()
    if "Missing data are indicated by -99.99 or -999." not in text:
        raise ValueError("Industry missing-value convention changed; review parser")
    markers = [i for i, line in enumerate(lines)
               if line.strip() == "Average Value Weighted Returns -- Monthly"]
    if len(markers) != 1:
        raise ValueError(f"Expected exactly one value-weighted monthly block, got {markers}")
    marker = markers[0]
    header = marker + 1
    while not lines[header].strip():
        header += 1
    columns = lines[header].split()
    if len(columns) != n or len(set(columns)) != n:
        raise ValueError(f"Wrong FF{n} column header")
    if n == 12 and columns != EXPECTED_FF12:
        raise ValueError("FF12 official column order changed")
    parsed = parse_month_rows(lines, header, columns)
    if parsed["next_nondata_line"] != "Average Equal Weighted Returns -- Monthly":
        raise ValueError("Monthly value-weighted block did not terminate at equal-weighted block")
    parsed["value_weighted_total_returns"] = parsed.pop("values")
    parsed.update({
        "source_id": source_id,
        "source_header": lines[0],
        "source_units": "percent per month",
        "units": "decimal_monthly_return",
        "return_kind": "total return including dividends; value weighted",
        "selected_block": "Average Value Weighted Returns -- Monthly (first returns block only)",
        "missing_sentinels_in_percent_units": sorted(MISSING_SENTINELS),
        "missing_values_as": None,
    })
    return parsed


def parse_factors_monthly(text: str, source_id: str) -> dict:
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines) if line.split() == ["Mkt-RF", "SMB", "HML", "RF"]]
    # The annual section repeats the same labels; select the first (monthly)
    # table and independently require that its next section is annual.
    if not headers:
        raise ValueError("Unexpected factor header")
    parsed = parse_month_rows(lines, headers[0], ["Mkt-RF", "SMB", "HML", "RF"])
    if "Annual" not in str(parsed["next_nondata_line"]):
        raise ValueError("Factor monthly block did not terminate before annual block")
    parsed.update({"source_id": source_id, "units": "decimal_monthly_return",
                   "source_units": "percent per month", "source_header": lines[:3]})
    return parsed


def parse_ff12_daily(text: str, source_id: str) -> dict:
    lines = text.splitlines()
    markers = [i for i, line in enumerate(lines)
               if line.strip() == "Average Value Weighted Returns -- Daily"]
    if len(markers) != 1 or "Missing data are indicated by -99.99 or -999." not in text:
        raise ValueError("Unexpected FF12 daily table/sentinel convention")
    header = markers[0] + 1
    while not lines[header].strip():
        header += 1
    if lines[header].split() != EXPECTED_FF12:
        raise ValueError("Unexpected FF12 daily column order")
    dates, values = [], []
    index = header + 1
    start_line = index + 1
    while index < len(lines):
        match = re.fullmatch(r"\s*(\d{8})\s+(.+?)\s*", lines[index])
        if match is None:
            break
        date = datetime.strptime(match[1], "%Y%m%d").strftime("%Y-%m-%d")
        fields = match[2].split()
        if len(fields) != 12:
            raise ValueError(f"Wrong daily column count on line {index+1}")
        numeric = [float(field) for field in fields]
        if not all(np.isfinite(numeric)):
            raise ValueError("Nonfinite daily source return")
        dates.append(date)
        values.append([None if x in MISSING_SENTINELS else x / 100 for x in numeric])
        index += 1
    if not dates or dates != sorted(set(dates)):
        raise ValueError("Daily dates must be strictly increasing without duplicates")
    following = next((line.strip() for line in lines[index:] if line.strip()), None)
    if following != "Average Equal Weighted Returns -- Daily":
        raise ValueError("FF12 daily value-weighted table did not end before equal weighting")
    # Do not synthesize trading dates, forward-fill or drop source rows.
    required = [(date, row) for date, row in zip(dates, values, strict=True)
                if "2014-01-01" <= date <= "2025-12-31"]
    if not required or not np.isfinite(numeric_array([row for _, row in required])).all():
        raise ValueError("Missing FF12 daily observation in required 2014--2025 preparation window")
    if required[0][0] > "2014-01-03" or required[-1][0] < "2025-12-30":
        raise ValueError("Daily data do not span the requested 2014--2025 period")
    return {
        "schema_version": "1.0", "dates": dates, "columns": EXPECTED_FF12,
        "returns": values, "units": "decimal_daily_return", "source_units": "percent per day",
        "source_id": source_id, "source_manifest": "data/french/manifest.json",
        "source_header": lines[0], "selected_block": "Average Value Weighted Returns -- Daily",
        "return_kind": "value-weighted total return including dividends",
        "missing_sentinels_in_percent_units": sorted(MISSING_SENTINELS), "missing_values_as": None,
        "first_data_line_1based": start_line, "last_data_line_1based": index,
        "next_nondata_line": following,
        "required_window_audit": {"start": required[0][0], "end": required[-1][0],
                                  "n_observed_trading_dates": len(required), "missing_cells": 0},
        "calendar_rule": "Observed source dates only; no interpolated/forward-filled returns or assumed trading calendar",
        "vintage_caveat": "Current CIZ release; not the vintage used by PortBench or a tradable fund-return series",
    }


def parse_sic(text: str, n: int, source_id: str, detail_url: str) -> dict:
    groups, current = [], None
    for line in text.splitlines():
        heading = re.match(r"^\s*(\d{1,2})\s+([A-Za-z]+)\s+(.+?)\s*$", line)
        if heading:
            current = {"id": int(heading[1]), "label": heading[2],
                       "description": heading[3], "sic_intervals_inclusive": []}
            groups.append(current)
        interval = re.match(r"^\s*(\d{4})-(\d{4})(?:\s+(.*))?$", line)
        if interval:
            if current is None:
                raise ValueError("SIC interval before industry heading")
            low, high = int(interval[1]), int(interval[2])
            if not (100 <= low <= high <= 9999):
                raise ValueError(f"Invalid SIC interval: {line}")
            current["sic_intervals_inclusive"].append({
                "low": low, "high": high, "source_description": interval[3] or None,
            })
    if [g["id"] for g in groups] != list(range(1, n + 1)):
        raise ValueError("Unexpected SIC industry IDs")
    lookup = {}
    for group in groups:
        for interval in group["sic_intervals_inclusive"]:
            for sic in range(interval["low"], interval["high"] + 1):
                if sic in lookup:
                    raise ValueError(f"Overlapping official SIC interval {sic}")
                lookup[sic] = group["label"]
    if n == 12 and (groups[-1]["label"] != "Other" or groups[-1]["sic_intervals_inclusive"]):
        raise ValueError("FF12 residual-Other definition changed")
    if n == 49 and not groups[-1]["sic_intervals_inclusive"]:
        raise ValueError("FF49 Other must remain explicit, not catch-all")
    return {
        "schema_version": "1.0", "classification": f"FF{n}",
        "source_id": source_id, "official_detail_url": detail_url, "industries": groups,
        "classification_rule": (
            "Use the official inclusive intervals. A source-verified valid company SIC not in the first "
            "11 groups is FF12 Other. Do not assign missing/invalid/unverified SIC to Other."
            if n == 12 else
            "Use only the official inclusive intervals. Other has explicit intervals and is not a catch-all. "
            "A source-verified SIC outside all intervals remains unmapped."
        ),
        "missing_sic_rule": "None, empty, nonnumeric, 0, unavailable or unverified SIC stays unmapped; never impute an industry from a name or Other.",
        "normalization": "A three-digit SEC display such as 100 may be normalized to 0100 only with original source preserved; store four-character SIC.",
        "mapping_source_caveat": "Official returns use June Compustat SIC with CRSP fallback. SEC-SIC mapping of fund holdings is a proxy, not exact constituent replication.",
        "hierarchy_caveat": "FF12 and FF49 are not a strictly nested hierarchy; map original position-level SIC separately.",
        "explicit_interval_sic_code_count": len(lookup),
    }


def numeric_array(values: list) -> np.ndarray:
    return np.array([[np.nan if x is None else x for x in row] for row in values], dtype=float)


def selected_window(data: dict, rf: dict, start: str, end: str) -> tuple[list[str], np.ndarray, np.ndarray]:
    dates = month_range(start, end)
    by_date = dict(zip(data["dates"], data["value_weighted_total_returns"], strict=True))
    rf_by_date = dict(zip(rf["dates"], (row[0] for row in rf["values"]), strict=True))
    absent = [date for date in dates if date not in by_date or date not in rf_by_date]
    if absent:
        raise ValueError(f"Required calendar months absent: {absent}")
    returns = numeric_array([by_date[date] for date in dates])
    rf_values = np.array([rf_by_date[date] for date in dates], dtype=float)
    if not np.isfinite(returns).all() or not np.isfinite(rf_values).all():
        raise ValueError(f"Missing required FF{len(data['columns'])} window observation in {start}..{end}; no implicit row dropping")
    if (returns < -1).any():
        raise ValueError("A nonmissing total return is below -100%; check units/sentinels")
    return dates, returns, rf_values


def sample_moments(returns: np.ndarray) -> dict:
    covariance = np.cov(returns, rowvar=False, ddof=1)
    mean = returns.mean(axis=0)
    centered = returns - mean
    direct_cov = centered.T @ centered / (len(returns) - 1)
    if not np.allclose(covariance, direct_cov, rtol=1e-12, atol=1e-15):
        raise ValueError("Sample covariance cross-check failed")
    if not np.allclose(covariance, covariance.T, rtol=0, atol=1e-15):
        raise ValueError("Covariance is not symmetric")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues.min() < -1e-12:
        raise ValueError("Sample covariance is not numerically positive semidefinite")
    return {
        "n_months": len(returns), "mean": mean.tolist(), "covariance": covariance.tolist(),
        "covariance_ddof": 1, "covariance_estimator": "sample covariance (no shrinkage/final model choice)",
        "covariance_min_eigenvalue": float(eigenvalues.min()),
        "covariance_max_eigenvalue": float(eigenvalues.max()),
        "n_by_column": np.isfinite(returns).sum(axis=0).tolist(),
        "covariance_denominator": len(returns) - 1,
    }


def download_sources() -> dict:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw_dir = DEST / "raw" / timestamp
    raw_dir.mkdir(parents=True, exist_ok=False)
    records = {}
    records["library"] = fetch(LIBRARY, raw_dir, "library", None)
    library_html = raw_bytes(records["library"]).decode("utf-8")
    files = {
        "ff12_returns": "12_Industry_Portfolios_TXT.zip",
        "ff49_returns": "49_Industry_Portfolios_TXT.zip",
        "ff12_daily_returns": "12_Industry_Portfolios_daily_TXT.zip",
        "factors": "F-F_Research_Data_Factors_TXT.zip",
        "ff12_detail": "det_12_ind_port.html",
        "ff49_detail": "det_49_ind_port.html",
    }
    for source_id, filename in files.items():
        records[source_id] = fetch(source_link(library_html, LIBRARY, filename), raw_dir, source_id, "library")
    for n in (12, 49):
        detail_id = f"ff{n}_detail"
        detail_html = raw_bytes(records[detail_id]).decode("utf-8")
        definition_url = source_link(detail_html, records[detail_id]["resolved_url"], f"Siccodes{n}.zip")
        source_id = f"ff{n}_sic"
        records[source_id] = fetch(definition_url, raw_dir, source_id, detail_id)
    manifest = {
        "schema_version": "1.0", "created_at_utc": utc_now(),
        "purpose": "public input preparation only; no experimental settings frozen",
        "library_url": LIBRARY, "sources": records,
        "vintage_caveat": "Current downloaded French CIZ vintage, including revised historical returns. Not a contemporaneous historical data vintage or exact values used in the paper.",
        "script": "research/prepare_public_inputs.py", "python": sys.version,
        "numpy": np.__version__,
    }
    write_json(raw_dir / "snapshot_manifest.json", manifest)
    write_json(DEST / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Read and hash-verify latest raw manifest without downloading")
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((DEST / "manifest.json").read_text(encoding="utf-8")) if args.offline else download_sources()
    records = manifest["sources"]
    for record in records.values():
        raw_bytes(record)
    datasets = {f"FF{n}": parse_industry_monthly(zip_text(records[f"ff{n}_returns"]), n, f"ff{n}_returns") for n in (12, 49)}
    factors = parse_factors_monthly(zip_text(records["factors"]), "factors")
    rf_index = factors["columns"].index("RF")
    rf = {
        "source_id": "factors", "columns": ["RF"], "dates": factors["dates"],
        "values": [[row[rf_index]] for row in factors["values"]],
        "units": "decimal_monthly_return", "source_units": "percent per month",
        "definition": "French monthly RF column; subtract the same calendar month's RF from each industry return",
        "source_header": factors["source_header"],
    }
    monthly = {
        "schema_version": "1.0", "source_manifest": "data/french/manifest.json",
        "units": "decimal_monthly_return", "datasets": datasets, "risk_free": rf,
        "source_conversion": "raw percentage / 100, after replacing -99.99 and -999 sentinels with null",
        "not_frozen": "No universe selection, sample size, investor risk preference, covariance shrinkage or LLM experiment is frozen by these files.",
    }
    write_json(DEST / "monthly_returns.json", monthly)
    daily = parse_ff12_daily(zip_text(records["ff12_daily_returns"]), "ff12_daily_returns")
    write_json(DEST / "ff12_daily.json", daily)
    for n in (12, 49):
        definition = parse_sic(zip_text(records[f"ff{n}_sic"]), n, f"ff{n}_sic", records[f"ff{n}_detail"]["resolved_url"])
        if [group["label"] for group in definition["industries"]] != datasets[f"FF{n}"]["columns"]:
            raise ValueError(f"FF{n} definitions and returns use different column order")
        write_json(DEST / f"sic_definitions_ff{n}.json", definition)
    reports = {}
    for start, end, filename in (
        ("1964-01", "2023-12", "moments_1964_2023.json"),
        ("2015-01", "2025-12", "moments_2015_2025.json"),
    ):
        moments = {
            "schema_version": "1.0", "units": {"mean": "decimal per month", "covariance": "decimal squared per month"},
            "window": {"start": start, "end": end, "n_months": len(month_range(start, end))},
            "source_manifest": "data/french/manifest.json", "datasets": {},
            "purpose": "descriptive input statistics; no calibration parameter or experimental design frozen",
            "vintage_caveat": manifest["vintage_caveat"],
        }
        # The paper-linked historical calibration is FF12 only.  FF49 is a
        # separate modern-window candidate and has genuine early missing cells;
        # never change the calibration window or silently drop those rows.
        included = {"FF12": datasets["FF12"]} if start == "1964-01" else datasets
        for key, data in included.items():
            dates, total, risk_free = selected_window(data, rf, start, end)
            excess = total - risk_free[:, None]
            moments["datasets"][key] = {
                "columns": data["columns"], "total": sample_moments(total), "excess": sample_moments(excess),
                "risk_free_mean": float(risk_free.mean()),
                "excess_formula": "R_industry(t) - RF(t), both monthly decimal units",
                "missing_observations": 0,
            }
            if start == "1964-01" and key == "FF12":
                calibration = {
                    "schema_version": "1.0", "units": "decimal_monthly_return",
                    "window": moments["window"], "dates": dates, "columns": data["columns"],
                    "returns": excess.tolist(), "risk_free": risk_free.tolist(), "total_returns": total.tolist(),
                    "source_manifest": "data/french/manifest.json",
                    "reference": "Salcher (2026), Lost in Translation? Risk-Adjusting RMSE for Economic Forecast Performance, https://doi.org/10.1002/for.70134",
                    "purpose": "1964--2023 FF12 excess-return input preparation, not an exact paper or historical-vintage replication; no rolling model fit or risk preference frozen",
                    "vintage_caveat": manifest["vintage_caveat"],
                }
                write_json(DEST / "ff12_excess_calibration_1964_2023.json", calibration)
        write_json(DEST / filename, moments)
        reports[f"{start}..{end}"] = {key: {"n_months": entry["total"]["n_months"], "n_industries": len(entry["columns"]), "missing": entry["missing_observations"]} for key, entry in moments["datasets"].items()}
    report = {
        "schema_version": "1.0", "validated_at_utc": utc_now(),
        "all_raw_hashes_verified": True, "calendar_rows_unique_contiguous": True,
        "monthly_first_block_only": True, "source_percent_converted_to_decimal": True,
        "required_windows": reports,
        "full_source": {
            key: {"start": data["dates"][0], "end": data["dates"][-1], "n_months": len(data["dates"]),
                  "missing_by_column": dict(zip(data["columns"], np.isnan(numeric_array(data["value_weighted_total_returns"])).sum(axis=0).tolist(), strict=True)),
                  "source_header": data["source_header"], "first_data_line_1based": data["first_data_line_1based"], "last_data_line_1based": data["last_data_line_1based"], "following_block": data["next_nondata_line"]}
            for key, data in datasets.items()
        },
        "sample_covariance_crosschecked": True,
        "ff12_daily": {"start": daily["dates"][0], "end": daily["dates"][-1],
                       "n_observed_trading_dates": len(daily["dates"]),
                       "required_window_audit": daily["required_window_audit"],
                       "following_block": daily["next_nondata_line"]},
        "classification": "Official intervals audited for duplicate IDs, interval overlaps and exact return-column order; no name-based or missing-SIC imputation",
        "limitations": [manifest["vintage_caveat"], "SEC-SIC mapping is a proxy for Compustat/CRSP classification", "Statistics are sample moments, not chosen covariance-model parameters"],
    }
    write_json(DEST / "validation_report.json", report)
    print(json.dumps({"output_dir": DEST.relative_to(ROOT).as_posix(), "source_snapshot_utc": manifest["created_at_utc"], "raw_zip_files": sum(record["path"].lower().endswith(".zip") for record in records.values()), "required_windows": reports, "validation": "passed"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
