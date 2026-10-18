"""Narrow offline author observations of C1; never replace or pool primary C0."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"
CASE = "fidelity_q2_2026__R1"
C0 = RUN / CASE / "C0/record.json"
C1 = RUN / CASE / "C1/record.json"
PREP = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
PACKET = PREP / "packets/fidelity_q2_2026.json"
REGISTRY = PREP / "public_numeric_registry.json"
OUT = Path(__file__).with_name("v48_guarded_fidelity_R1_C1_author_observations_20261019.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path, locator=None, **extra):
    result = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path), **extra}
    if locator is not None:
        result["locator"] = locator
    return result


def pointer(value, locator):
    for part in locator[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def main():
    if OUT.exists():
        raise FileExistsError("Preserve the note; write a new version")
    provider = C1.parent / "http_0001_generation/response.json"
    files = [C0, C1, PACKET, REGISTRY, provider, PREP / "manifest.json", Path(__file__)]
    pinned = {path: sha(path) for path in files}
    assert pinned[C0] == "0c650b3a2eb08406bf884007a49e033731f30dad9f7373a70083aa0708ec2f36"
    assert pinned[C1] == "b976ab482d90a0006230be60a911eae8e0f5e4dc0989a9ebf5cea5029b68e2ba"
    before, after, packet, registry = map(read, (C0, C1, PACKET, REGISTRY))
    assert after["response_complete"] is True and after["transport_status"] == "completed"
    assert after["schema_validation"]["valid"] is True
    assert after["raw_response_text"] == read(provider)["message"]["content"]
    assert json.loads(after["raw_response_text"]) == after["parsed_response"]
    old, new = before["parsed_response"], after["parsed_response"]
    assert len(old["weights"]) == len(new["weights"]) == 11
    old_values = {row["sector_code"]: Decimal(str(row["weight"])) for row in old["weights"]}
    new_values = {row["sector_code"]: Decimal(str(row["weight"])) for row in new["weights"]}
    deltas = {code: new_values[code] - old_values[code] for code in old_values}
    assert {code for code, value in deltas.items() if value != 0} == {"45"}
    assert old_values["45"] == Decimal("0.42") and new_values["45"] == Decimal("0.38")
    assert sum(old_values.values()) == Decimal("1.035") and sum(new_values.values()) == Decimal("0.995")
    assert after["feedback"]["allocation"]["valid"] is False
    facts = {row["fact_id"]: (i, row) for i, row in enumerate(registry["rows"])}
    baseline_index, baseline = facts["M:baseline_weights:45"]
    baseline_delta = new_values["45"] - Decimal(str(baseline["value"]))
    visible_sum_index = next(i for i, row in enumerate(after["visible_calculator_facts_before_generation"])
                             if row["fact_id"] == "C:C0:sum")

    def passage(index):
        return ref(PACKET, f"/evidence_passages/{index}", passage_literal=packet["evidence_passages"][index])

    observations = []

    def observe(identifier, locator, claim, evidence, refs, assessment, limits):
        literal = pointer(after, locator)
        assert isinstance(literal, str) and literal
        observations.append({"id": identifier, "case_id": CASE, "endpoint": "C1",
                             "claim_or_action": claim, "model_quote": literal,
                             "response_locator": locator, "response_artifact": ref(C1),
                             "evidence_summary": evidence, "evidence_refs": refs,
                             "author_assessment": assessment, "limits": limits,
                             "independent_human_judgment": None, "automatic_semantic_score": None})

    observe("guarded_C1_actual_IT_change_but_sum_claim_disagrees", "/parsed_response/risk_discussion",
            "IT를 실제로 낮췄지만 합계를 1.000으로 고쳤다는 설명은 제출 수치와 다르다.",
            "C0의 11개 원비중 중 IT만0.420에서0.380으로 바뀌고 나머지10개 값은 같다. Decimal 합계는1.035→0.995이며 signed residual은 -0.005다. C1전에 보인 C:C0:sum은1.035다. 응답은 IT감소와 RE유지를 정확히 서술하는 한편 합계1.000·완전투자라고 적는다.",
            [ref(C0, "/parsed_response/weights"), ref(C1, "/parsed_response/weights"),
             ref(C1, "/feedback/allocation"), ref(C1, "/feedback/raw_weight_deltas"),
             ref(C1, f"/visible_calculator_facts_before_generation/{visible_sum_index}")],
            "이번 보조안에는 실제 좌표 변화가 있지만 합계 수정의 완료 주장은 지지되지 않는다. 수정 행동과 산술 조건 충족을 구분해 보존한다.",
            "C1을 C0의 대체값이나 추가 독립 사례로 쓰지 않는다. 0.995를 정규화하지 않으며, C2의 결과나 이후 복구 성공을 추정하지 않는다.")
    observe("guarded_C1_IT_stated_overweight_vs_current_coordinate", "/parsed_response/weights/7/rationale",
            "IT의 출처 이유와 확대 표현은 남았지만 실제 비중은 0.380으로 바뀌었다.",
            "제공 문장은 IT의 펀더멘털과 하락 후 가치평가를 근거로 Overweight를 제시한다. C1은 그 이유와 significant overweight 표현을 유지하면서 실제0.380을 제출한다. 등록된 정확한 공통 기준은0.38038038038038036이며 차이는 -0.00038038038038036이다. 응답에 표시한 기준0.380과는 같은 숫자다.",
            [passage(8), ref(REGISTRY, f"/rows/{baseline_index}", fact_literal=baseline),
             ref(C0, "/parsed_response/weights/7"), ref(C1, "/parsed_response/weights/7/weight")],
            "제공된 전망 이유가 문장에 남아 있다는 점과 변경 후 실제 좌표가 자기 확대 서술을 어떻게 뒷받침하는지는 별도로 읽어야 한다. 여기서는 정확한 수치 차이와 문구만 기록한다.",
            "작은 기준 차이를 기관 전략의 역전·보존 성공·실패로 판정하지 않는다. 반올림된 기준을 사용한 이유나 내부 의도를 추정하지 않고, 의미 있는 차이의 임의 문턱도 추가하지 않는다.")
    observe("guarded_C1_RE_adjustment_wording_without_coordinate_change", "/parsed_response/weights/10/rationale",
            "부동산 이유에는 adjusted 문장이 추가됐지만 원비중은 0.075 그대로다.",
            "C0와 C1의 RE 값은 모두0.075이고 delta는0이다. 제공된 valuation dispersion 이유와 확대 표현은 유지된다. RE rationale에는 'adjusted from the previous proposal (0.075)'가 추가됐지만 risk_discussion은 RE를0.075로 유지했다고 서술한다.",
            [passage(11), ref(C0, "/parsed_response/weights/10"), ref(C1, "/parsed_response/weights/10/weight"),
             ref(C1, "/feedback/raw_weight_deltas/60"), ref(C1, "/parsed_response/risk_discussion")],
            "같은 응답의 수정 표현과 유지 설명을 실제 좌표 변화와 대조해 읽을 필요가 있다. 출처 이유를 재사용했다는 사실만으로 RE 비중이 수정됐다고 기록하지 않는다.",
            "서술의 불일치 관측이며 비공개 기관 목적이나 선택의 최적성은 판단하지 않는다. 이 행의 미변경을 전체 보조 수정이 전혀 없었다는 주장으로 확대하지 않는다.")
    for observation in observations:
        assert pointer(after, observation["response_locator"]) == observation["model_quote"]
        for evidence in observation["evidence_refs"]:
            path = ROOT / evidence["path"]
            assert sha(path) == evidence["sha256"]
            pointer(read(path), evidence["locator"])
    assert all(sha(path) == expected for path, expected in pinned.items())
    result = {
        "artifact_kind": "interim_guarded_repeat_C1_auxiliary_author_observations",
        "reviewer_role": "assistant_self_review", "reviewer_id": "v48_offline_evaluator",
        "independent_human_review_completed": False, "case_id": CASE, "endpoint": "C1",
        "scope": "Narrow reading of changed weight/rationale rows and correction description in this completed C1; not a new 11-sector semantic review, final auxiliary-terminal conclusion or replacement of primary C0.",
        "provenance": {"created_at_utc": datetime.now(timezone.utc).isoformat(), "manifest": ref(PREP / "manifest.json"),
                       "evaluation": None, "run_summary": None, "run_root": RUN.relative_to(ROOT).as_posix(),
                       "pending_provenance_reason": "The fixed-four repeat and C2 are unfinished at this note; final bundle and auxiliary-terminal binding are deferred.",
                       "files": [ref(path) for path in files]},
        "paper_observations": [], "auxiliary_observations": observations,
        "descriptive_arithmetic": {"C0_raw_sum_decimal": str(sum(old_values.values())), "C1_raw_sum_decimal": str(sum(new_values.values())),
                                   "C1_signed_residual_decimal": str(sum(new_values.values()) - Decimal("1")),
                                   "raw_weight_deltas_decimal": {key: str(value) for key, value in deltas.items()},
                                   "changed_weight_codes": ["45"], "changed_rationale_codes": ["45", "60"],
                                   "IT_minus_exact_common_baseline_decimal": str(baseline_delta),
                                   "C1_valid_raw_allocation_as_recorded": False, "C1_valid_portfolio_risk_as_recorded": after["feedback"]["valid_portfolio_risk"],
                                   "normalized_or_repaired": False, "behavioral_threshold_added": False},
        "unchanged_top_level_fields": [key for key in old if old[key] == new[key]],
        "model_calls_by_this_review": 0, "online_artifacts_changed": False, "automatic_semantic_score": None,
        "limits": ["Source passages are supplied researcher paraphrases; this note is not an independent human PDF review.",
                   "No public document specifies a unique target vector; raw-coordinate differences are descriptive, not private institutional strategy labels.",
                   "No observed future C2 result, four-case comparison or successful portfolio performance is inferred."],
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": sha(OUT),
                      "auxiliary_observations": len(observations), "C1_raw_sum": "0.995", "model_calls": 0}))


if __name__ == "__main__":
    main()
