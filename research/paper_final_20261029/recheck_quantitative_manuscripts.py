"""Recheck final Markdown against the completed local numerical audit only."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RECEIPT = OUT / "quantitative_manuscript_review.json"
receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
audit = json.loads((OUT / "numeric_audit.json").read_text(encoding="utf-8"))


def read_csv(name):
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


arms = read_csv("arm_summary.csv")
strata = read_csv("stratum_arm_summary.csv")
traces = read_csv("trajectory_audit.csv")
case = read_csv("matched_case_main009_F01.csv")
checks = []
latest_documents = []


def require(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def row_exists(rows, expected, label):
    require(expected in rows, label)


for document in receipt["documents"]:
    path = ROOT / document["path"]
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines() if line.startswith("|")
    ]
    name = path.name
    doc_checks = []
    for arm in arms:
        row_exists(rows, [arm["arm"]] + [
            f"{int(arm[k]) / int(arm['trajectories']) * 100:.1f}%"
            for k in ("raw_valid", "rescued", "fallback", "policy_valid")
        ], name + ": validity " + arm["arm"])
    doc_checks.append("arm validity percentage table")
    for field, marker, scale in (
        ("D_full", " D (", 100), ("Dstar_full", " D* (", 100),
        ("G_full", " G (", 100), ("A_full", " A (", 100),
        ("E_full", " E (", 100), ("R_full", " R (", 10000),
    ):
        expected = [f"{float(arm[field]) * scale:.2f}" for arm in arms]
        require(any(marker in row[0] and row[1:] == expected for row in rows),
                name + ": metric " + field)
    doc_checks.append("D/Dstar/G/A/E/R table and unit conversions")
    for row in strata:
        row_exists(rows, [f"r={float(row['r']):g}", row["arm"],
            f"{int(row['policy_valid']) / int(row['trajectories']) * 100:.1f}%",
            f"{float(row['G_full']) * 100:.2f}",
            f"{float(row['R_full']) * 10000:.2f}"], name + ": precision " + row["r"] + row["arm"])
    doc_checks.append("precision-stratum table")
    baseline = float(arms[0]["hold_h_R_full"]) * 10000
    require(any(" h " in row[0] and row[1:] == [f"{baseline:.2f}", "0.00"] for row in rows),
            name + ": hold-h benchmark")
    for arm in arms:
        value = float(arm["R_full"]) * 10000
        row_exists(rows, [arm["arm"], f"{value:.2f}", f"{value-baseline:+.2f}"],
                   name + ": hold-h delta " + arm["arm"])
    doc_checks.append("hold-h comparator and deltas")
    for token in ("72.5%", "70.6%", "6.9%", "99.41", "113.52", "27시간 26분 43초"):
        require(token in text, name + ": core prose token " + token)
    doc_checks.append("core prose percentages, case regret, elapsed time")
    if "소논문" in name:
        for arm in arms:
            row_exists(rows, [arm["arm"]] + [arm[k] for k in (
                "raw_valid", "rescued", "fallback", "effective_equal_h_1e12")],
                name + ": appendix counts " + arm["arm"])
            actual_changes = sum(float(t["stage2_to3_effective_change_tv"]) > 1e-12
                                 for t in traces if t["arm"] == arm["arm"])
            row_exists(rows, [arm["arm"]] + [arm[k] for k in (
                "stage2_valid", "policy_valid", "valid_to_invalid", "invalid_to_valid")]
                + [str(actual_changes)], name + ": stage transitions " + arm["arm"])
            interval = f"{float(arm['G_numerical_lower'])*100:.2f}~{float(arm['G_numerical_upper'])*100:.2f}%p"
            require(interval.replace("-", "−") in text, name + ": G interval " + arm["arm"])
        row_exists(rows, ["합계", "19", "47", "94", "113"], name + ": aggregate counts")
        for token in ("132개", "79개", "15개", "55개", "70.83bp", "32.988", "57.37"):
            require(token in text, name + ": appendix/case token " + token)
        doc_checks.extend(["appendix actual counts and stage transitions", "all four numerical G intervals",
                           "R0 available-information benchmark and illustrative case"])
    latest_documents.append({"path": document["path"], "sha256": hashlib.sha256(raw).hexdigest()})
    for table_check in receipt["automated_table_checks"]:
        if table_check["document"] == document["path"]:
            table_check["checks"] = doc_checks
            table_check["status"] = "passed"

# Recheck arithmetic supporting rounded prose against local audit tables.
aggregate = audit["aggregate"]
require(aggregate["raw_valid"] == aggregate["raw_equal_h_1e12"] == 19, "all 19 raw valid equal h")
require(aggregate["rescued"] == 47 and sum(float(t["effective_change_from_h_tv"]) > 1e-12
        for t in traces) == 47, "47 rescues are all actual reallocations")
require(aggregate["effective_equal_h_1e12"] == 113 and f"{113/160*100:.1f}" == "70.6", "113/160 rounds to 70.6%")
require(sum(float(t["stage2_to3_effective_change_tv"]) > 1e-12 for t in traces) == 11
        and f"{11/160*100:.1f}" == "6.9", "11/160 stage changes round to 6.9%")
require(sum(int(a["stage2_to3_raw_exactly_unchanged"]) for a in arms) == 132, "132 unchanged raw vectors")
require(sum(int(a["negative_weight_failures"]) for a in arms) == 79, "79 negative-weight failures")
require(sum(int(a["normalized_constraint_failures"]) for a in arms) == 15, "15 normalized risk failures")
require(aggregate["raw_equal_negative_h_1e12"] == 55, "55 negative-h outputs within tolerance")
require(aggregate["actual_calculator_tool_calls"] == 0, "no actual calculator calls")
ratio = float(arms[2]["G_contribution_fallback"]) / float(arms[2]["G_full"]) * 100
require(f"{ratio:.1f}" == "72.5", "R2 fallback G share rounds to 72.5%")
for c in case:
    if c["stage"] == "3":
        require(f"{float(c['final_full_regret'])*10000:.2f}" == ("113.52" if c["arm"] == "R1" else "99.41"),
                "matched case regret " + c["arm"])
require(all(float(a["R_full"]) > float(a["hold_h_R_full"]) for a in arms), "all arm mean regrets exceed hold-h")
require(all(float(a["R_full"]) > float(arms[0]["R_full"]) for a in arms[1:]), "all RAG arm mean regrets exceed R0")
timing = receipt["manual_and_arithmetic_checks"]["timing"]
elapsed = (datetime.fromisoformat(timing["final_process_end"]) - datetime.fromisoformat(timing["first_same_run_process_start"])).total_seconds()
require(elapsed == 98803.352911 and int(elapsed) == 27*3600 + 26*60 + 43, "elapsed time 27h26m43s")

previous_documents = receipt["documents"]
receipt["documents"] = latest_documents
receipt["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
receipt["status"] = "passed_no_material_quantitative_errors"
receipt["latest_recheck"] = {
    "scope": "Latest two Markdown documents: existing numeric tables, core numeric claims and local audit arithmetic; no recollection or experiment rerun.",
    "previous_document_hashes": previous_documents,
    "assertions_passed": len(checks),
    "checks": checks,
    "audit_sha256": hashlib.sha256((OUT / "numeric_audit.json").read_bytes()).hexdigest(),
    "script": str(Path(__file__).relative_to(ROOT)),
    "original_experiment_mutated": False,
    "manuscripts_or_figures_modified": False,
}
receipt["resolved_wording_notes"] = receipt.get("optional_wording_notes", [])
receipt["optional_wording_notes"] = []
receipt["required_changes"] = []
RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": receipt["status"], "assertions_passed": len(checks),
                  "documents": latest_documents}, ensure_ascii=False, indent=2))
