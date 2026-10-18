"""Synthetic offline adversarial checks; no live model requests."""
from pathlib import Path
import copy
import json
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research"))
from audit_v48_pilot_round2 import SelfTests, build_audit, read, ref
from evaluate_sector_v48_artifacts import build_report

BASE = Path(__file__).resolve().parent
OUT = BASE / "followup_validation"
OUT.mkdir(exist_ok=False)
MANIFEST = ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"
GOLD = ROOT / "data/sector_documents/evaluator_only/reference_annotations.jsonl"
ORIGINAL = BASE / "synthetic_run"
BASE_EVALUATION = BASE / "synthetic_evaluation.json"
results = []


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def audit(name, run, evaluation, expected, fail_fragment=None):
    result = build_audit(MANIFEST, run, evaluation)
    destination = OUT / (name + "_audit.json")
    write(destination, result)
    failed = [c["id"] for c in result["checks"] if not c["passed"]]
    assert result["status"] == expected, (name, failed)
    if fail_fragment: assert any(fail_fragment in check for check in failed), (name, failed)
    results.append({"name": name, "expected_status": expected, "observed_status": result["status"],
                    "checks": len(result["checks"]), "failed_ids": failed, "report": ref(destination)})
    print(name, result["status"], len(result["checks"]), flush=True)
    return result


def copied_run(name):
    target = OUT / (name + "_run")
    shutil.copytree(ORIGINAL, target)
    # Rebind only copied artifact paths; original evidence is preserved.
    for summary_path in target.glob("*/case_summary.json"):
        summary = read(summary_path)
        for item in summary["endpoints"]:
            if item.get("record"):
                item["record"] = ref(summary_path.parent / item["endpoint"] / "record.json")
        for key in ("primary_record", "auxiliary_terminal_record"):
            if summary.get(key):
                endpoint = Path(summary[key]["path"]).parent.name
                summary[key] = ref(summary_path.parent / endpoint / "record.json")
        write(summary_path, summary)
    return target


test_result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SelfTests))
assert test_result.wasSuccessful()
audit("baseline", ORIGINAL, BASE_EVALUATION, "PASS")

# All four expected cases remain in the denominator even before any request.
empty = OUT / "all_not_reached_run"
empty.mkdir()
shutil.copy2(ORIGINAL / "manifest_snapshot.json", empty / "manifest_snapshot.json")
report, _ = build_report(MANIFEST, empty, GOLD)
write(OUT / "all_not_reached_evaluation.json", report)
audit("all_not_reached", empty, OUT / "all_not_reached_evaluation.json", "PASS")

# A complete response capture without its endpoint record preserves literal
# numbers and observed labels, but does not earn completion or C0 credit.
missing = copied_run("missing_record")
folder = missing / "fidelity_q2_2026__R4"
(folder / "C0/record.json").rename(folder / "C0/record.absent_fixture.json")
summary = read(folder / "case_summary.json")
summary["primary_record"] = None
summary["endpoints"] = [x for x in summary["endpoints"] if x["endpoint"] != "C0"]
summary["status"] = "interrupted_fixture"
write(folder / "case_summary.json", summary)
report, _ = build_report(MANIFEST, missing, GOLD)
write(OUT / "missing_record_evaluation.json", report)
result = audit("missing_record", missing, OUT / "missing_record_evaluation.json", "PASS")
case = next(c for c in result["case_numerics"] if c["case_id"] == "fidelity_q2_2026__R4")
assert case["raw_binary64_sum"] == 1 and not case["C0_completed"] and case["label_correct"] == 0

# Report-only mutations isolate auxiliary inventory and raw-value checks.
mutations = {
    "aux_duplicate": (lambda r: r["auxiliary_endpoint_cases"].append(copy.deepcopy(r["auxiliary_endpoint_cases"][0])), "auxiliary_exact_unique_inventory"),
    "aux_unexpected": (lambda r: r["auxiliary_endpoint_cases"][0].update(endpoint="C2"), "auxiliary_exact_unique_inventory"),
    "aux_raw_sum": (lambda r: r["auxiliary_endpoint_cases"][0]["allocation"].update(raw_sum=.5), "evaluation_C1:raw_sum"),
    "aux_metadata": (lambda r: r["auxiliary_endpoint_cases"][0].update(arm="R4"), "evaluation_C1:identity"),
}
for name, (mutate, fragment) in mutations.items():
    report = read(BASE_EVALUATION)
    mutate(report)
    path = OUT / (name + "_evaluation.json")
    write(path, report)
    audit(name, ORIGINAL, path, "FAIL", fragment)

# Feedback mutations do not alter allocation.raw_sum. Update the copied
# summary hash so a fact-specific check, not just a stale hash, must catch them.
fact_mutations = {
    "fact_value": (lambda f: f.update(value=1), "fact_value:"),
    "fact_metric": (lambda f: f.update(metric="unregistered_metric"), "fact_tuple:"),
    "fact_unit": (lambda f: f.update(unit="percent_weight"), "fact_tuple:"),
    "fact_period": (lambda f: f.update(period="wrong_period"), "fact_tuple:"),
    "fact_candidate": (lambda f: f.update(candidate_id="C1"), "fact_tuple:"),
    "fact_duplicate": (None, "fact_exact_unique_inventory"),
}
for name, (mutate, fragment) in fact_mutations.items():
    run = copied_run(name)
    folder = run / "fidelity_q2_2026__R1"
    record_path = folder / "C0/record.json"
    record = read(record_path)
    fact = next(f for f in record["feedback"]["facts"] if f["fact_id"] == "C:C0:sum")
    if mutate: mutate(fact)
    else: record["feedback"]["facts"].append(copy.deepcopy(fact))
    write(record_path, record)
    summary = read(folder / "case_summary.json")
    summary["primary_record"] = ref(record_path)
    for item in summary["endpoints"]:
        if item["endpoint"] == "C0": item["record"] = ref(record_path)
    write(folder / "case_summary.json", summary)
    audit(name, run, BASE_EVALUATION, "FAIL", fragment)

write(OUT / "validation_summary.json", {"status": "PASS", "auditor": ref(ROOT / "research/audit_v48_pilot_round2.py"),
      "validation_script": ref(__file__), "self_tests": test_result.testsRun, "cases": results,
      "synthetic_only": True, "model_calls": 0,
      "scope": "Engineering consistency regressions, not strategic or scientific confirmation."})
print("VALIDATION PASS", len(results), "cases", flush=True)
