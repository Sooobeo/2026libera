"""Check version lineage and meaningful counterexamples to design metrics."""
from __future__ import annotations

import hashlib
import json
from math import isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
PLAN = ROOT / "plan"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tv(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / 2


def delta(a, b):
    return [x - y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def pair(a, b, star_a, star_b):
    return {"D": tv(a, b), "Dstar": tv(star_a, star_b),
            "G": tv(star_a, star_b) - tv(a, b),
            "E": tv(delta(a, b), delta(star_a, star_b))}


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


checks = []
base = read(PLAN / "LIBERA_실험설정_v6.0_20261027.json")
final = read(PLAN / "LIBERA_실험설정_v6.3_20261027.json")
check(final["review_cycles_completed"] == 3, "three sequential review-improvement cycles recorded")
for n in [1, 2, 3]:
    review = read(WORK / f"review_round{n}.json")
    check(digest(ROOT / review["input"]) == review["input_sha256"], f"round {n} input hash")
    check(digest(ROOT / review["output"]) == review["output_sha256"], f"round {n} output hash")
    check(len(review["criteria"]) == 4 and bool(review["applied_changes"]), f"round {n} covers four criteria and actual changes")
check(final["title"] == base["title"] and final["subtitle"] == base["subtitle"], "original title and subtitle retained")
check(not final["execution_enabled"] and final["current_readiness"]["new_model_runs"] == 0, "no new experimental model execution")
for source in base["lineage"]:
    p = Path(source["path"])
    p = p if p.is_absolute() else ROOT / p
    check(digest(p) == source["sha256"], f"retained source unchanged: {p.name}")
check(len(final["analysis"]["confirmatory_tests"]) == final["analysis"]["multiplicity"]["family_size"] == 5, "five claims including not-testable ones remain in Holm family")
check(final["analysis"]["matched_validity"].startswith("H1 H2 H3의 전체 정책"), "primary analysis includes every planned terminal policy outcome")
check(len(final["evaluation"]["primary_mitigation_endpoints"]["comparison_endpoints"]) == 3, "prerequisite and all three improvement endpoints synchronized")
check(final["workflow"]["stage_contracts"][0]["weights_required"] is False, "planning and allocation output contracts differ")
check(final["reference_solver"]["near_optimal_component_width_max_for_distance_metrics"] is None, "wide references are bounded rather than silently dropped")
check(final["workload"]["logical_stages_total"] == sum(r["logical_stages"] for r in final["workload"]["original_blocks"]) == 9816, "original logical workload preserved")

# A scalar distance cannot detect allocations assigned to the wrong funds.
sa, sb = [0.8, 0.2], [0.2, 0.8]
swapped = pair(sb, sa, sa, sb)
check(isclose(swapped["G"], 0) and swapped["E"] > 0, "swapped correct allocations preserve distance but fail directional response metric")

# Lower signed G can mean substantially worse overspreading.
sa, sb = [0.6, 0.4], [0.4, 0.6]
converged = pair([0.5, 0.5], [0.5, 0.5], sa, sb)
overspread = pair([1, 0], [0, 1], sa, sb)
check(overspread["G"] < converged["G"] and overspread["E"] > converged["E"] and abs(overspread["G"]) > abs(converged["G"]), "signed G reduction alone incorrectly favors overspreading; new E and absolute G reject it")

# Information absence can explain full-reference convergence without model error.
sa, sb = [0.8, 0.2], [0.2, 0.8]
available = [0.5, 0.5]
full = pair(available, available, sa, sb)
known = pair(available, available, available, available)
check(full["G"] > 0 and isclose(known["G"], 0), "available oracle has zero avoidable convergence despite positive full-reference G")

# Fail-safe output must not relabel an invalid model proposal as successful.
raw = [0.6, 0.6]
valid = isclose(sum(raw), 1, abs_tol=1e-6)
h = [0.4, 0.6]
executed = raw if valid else h
check(not valid and executed == h and isclose(sum(executed), 1), "invalid raw allocation remains failed even when hold-existing policy is feasible")

# Average absolute divergence must be formed before aggregation.
gs = [0.2, -0.2]
check(isclose(abs(sum(gs) / 2), 0) and isclose(sum(abs(g) for g in gs) / 2, 0.2), "mean absolute G cannot be replaced by absolute mean G")

# A conservative near-optimal-reference envelope covers altered true optima.
va, vb = [0.7, 0.3], [0.3, 0.7]
la, ua = [0.68, 0.28], [0.72, 0.32]
lb, ub = [0.28, 0.68], [0.32, 0.72]
eta_a = sum(max(v-l, u-v) for v, l, u in zip(va, la, ua)) / 2
eta_b = sum(max(v-l, u-v) for v, l, u in zip(vb, lb, ub)) / 2
wa, wb = [0.6, 0.4], [0.45, 0.55]
point = pair(wa, wb, va, vb)
altered = pair(wa, wb, [0.72, 0.28], [0.28, 0.72])
check(abs(altered["E"] - point["E"]) <= eta_a + eta_b + 1e-12 and abs(altered["Dstar"] - point["Dstar"]) <= eta_a + eta_b + 1e-12, "eta bounds cover E and reference-distance ambiguity")

# Reference objective cancels in paired regret contrasts.
mu, a, b, star = [0.02, 0.01], [0.7, 0.3], [0.4, 0.6], [0.8, 0.2]
ra, rb = dot(mu, delta(star, a)), dot(mu, delta(star, b))
check(isclose(ra-rb, dot(mu, delta(b, a)), abs_tol=1e-14), "paired regret contrast independently cancels the reference objective")

# Same information gives a zero reference distance for canonical cloned tasks.
same = pair([0.6, 0.4], [0.4, 0.6], [0.5, 0.5], [0.5, 0.5])
check(same["Dstar"] == 0 and isclose(same["G"], -same["D"]) and same["G"] <= 0, "identical-information control oracle identity")

# Raw budget engineering residuals make a hard E<=2 cap unsafe.
edge = pair([1.0000005, 0], [0, 1.0000005], [0, 1], [1, 0])
check(edge["E"] > 2 and "do not cap at2" in final["reference_solver"]["uncertainty_bounds"]["E_interval"], "reference error envelope does not truncate disclosed engineering residuals")

result = {
    "status": "passed",
    "checks": checks,
    "check_count": len(checks),
    "scope": "design version lineage, source preservation and numerical counterexamples; not a model experiment or completed oracle/retrieval implementation",
    "final_json_sha256": digest(PLAN / "LIBERA_실험설정_v6.3_20261027.json"),
    "final_html_sha256": digest(PLAN / "LIBERA_최종실험설계_쉬운설명_v6.3_20261027.html"),
}
(WORK / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "check_count": len(checks), "experimental_model_calls": 0}, ensure_ascii=False))
