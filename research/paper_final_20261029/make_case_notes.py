"""Save an explicitly illustrative matched case and concise audit notes."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
audit = json.loads((OUT / "numeric_audit.json").read_text(encoding="utf-8"))
with (OUT / "trajectory_audit.csv").open(encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
chosen = sorted([r for r in rows if r["scenario"] == "main-009" and r["fund"] == "F01"], key=lambda x:x["arm"])
matched, source_traces = [], []
for row in chosen:
    path = ROOT / row["trace_path"]
    raw_bytes = path.read_bytes()
    trace = json.loads(raw_bytes)
    source_traces.append({"path": row["trace_path"], "sha256": hashlib.sha256(raw_bytes).hexdigest()})
    if row["arm"] == "R0":
        h = np.asarray(trace["effective_weights"])
    for stage in trace["stages"]:
        if stage["stage"] not in (2, 3):
            continue
        weights = np.asarray(stage["raw_output"]["weights"])
        norm = stage["normalization"]
        outcome = "raw_valid" if norm["postprocessed_valid"] and norm["raw_valid"] else ("normalized_rescue" if norm["postprocessed_valid"] else "fallback")
        relative = "h" if np.max(np.abs(weights-h)) <= 1e-12 else ("-h" if np.max(np.abs(weights+h)) <= 1e-12 else "other")
        matched.append({"scenario": "main-009", "r": 2., "fund": "F01", "arm": row["arm"], "stage": stage["stage"],
                        "raw_sum": float(weights.sum()), "raw_minimum": float(weights.min()), "outcome": outcome,
                        "raw_relation_to_h_1e12": relative, "failure_reason": norm["failure_reason"],
                        "effective_change_from_h_tv": float(np.abs(np.asarray(norm["effective_weights"])-h).sum()/2),
                        "raw_weights": weights.tolist(), "effective_weights": norm["effective_weights"],
                        "final_full_regret": float(row["full_regret"]) if stage["stage"] == 3 else None})
example = {"schema": "libera_illustrative_matched_case_v1", "run_id": audit["run_id"],
           "selection_role": "Illustrative diagnostic of h/negative-h/normalized-reallocation mechanisms; not a representative-sample estimator or new hypothesis test.",
           "equality_tolerance": "max absolute component difference <=1e-12", "h": h.tolist(), "rows": matched,
           "source_traces": source_traces,
           "interpretation_ko": "R3의 점검 단계는 음수 비중을 h로 되돌려 원출력 유효성을 회복했지만, 이미 실패 처리에서 h를 적용했으므로 실제 배분은 바뀌지 않았다. R1은 비례 보정 뒤 유효한 재배분이 됐으나 기준해 대비 기대수익 기회손실은 h 유지보다 컸다."}
(OUT / "matched_case_main009_F01.json").write_text(json.dumps(example, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
with (OUT / "matched_case_main009_F01.csv").open("w", encoding="utf-8-sig", newline="") as f:
    fields = [k for k in matched[0] if k not in ("raw_weights", "effective_weights")]
    writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(matched)

notes = [
    "완료 본실험 수치 검증 메모 — 원본 실험자료는 변경하지 않음",
    "",
    "검증: analysis 입력해시166개, trace해시160개, 단계2/3 정규화 영수증320개, 시나리오×조건 지표40개를 대조했다. 지표의 최대 차이는 numeric_audit.json checks에 기록했다.",
    "",
    "우선 서술할 결과",
    "1. 원출력 유효19/160(11.875%), 외부 비례 보정으로 유효47/160(29.375%), 실패하여 h 유지94/160(58.75%). 원출력 유효19개는 모두 h와 성분별1e-12 이내로 같았다. 따라서 유효성 자체와 새로운 재배분을 구분한다. 최종 적용 비중113/160(70.625%)가 h였고, 실제 재배분47/160(29.375%)는 전부 외부 보정의 도움을 받았다.",
    "2. R0/R1/R2/R3의 최종 유효 비율은50/42.5/10/62.5%. R3가 가장 높지만 R0보다 평균G는 더 음수였고 평균기회손실R은 더 컸다. 정보의 늦은 제공이 검증 가능한 원출력을 늘린 것과 기준해에 맞는 경제적 차별화를 회복한 것은 같은 결과가 아니다.",
    "3. 실패94개의 원인은 음수비중79개와 비례 보정 후 위험상한 초과15개다. 음수79개 중55개는 -h와 성분별1e-12 이내로 같았다. 이는 부호를 뒤집으면 안 된다는 보정 정책에 따라 실패로 남겼다. h와 -h의 일치 판정은 비트 단위의 정확한 일치가 아니다.",
    "4. 배분안 작성 단계에서 보정 후 유효한71개가 점검·수정 뒤66개가 됐다. 유효→무효8개, 무효→유효3개이며 세 회복 사례는 전부R3/F01(main003,009,010)이 h를 다시 출력한 경우다. 회복이 실제 적용 포트폴리오 변화로 이어지지는 않았다.",
    "5. 단계2와3의 원비중 배열이 그대로인 작업은132/160(82.5%). 실제 적용 비중이 성분별 오차를 넘어서 바뀐 작업은TV>1e-12 기준11/160(6.875%):R0=3,R1=3,R2=1,R3=4. 실제 계산 도구 호출은0회다. 단계2/3의calculator_check.performed도320개 모두false였다. valid만true인필드1개(main004/F03/R2)가 있으므로 자기보고를 실제 검산 수행으로 세면 안 된다.",
    "6. 평균G의 수치 기준해 구간은R0/R3에서 음수,R1/R2에서 양수다. 하지만 개별시나리오G는 조건별로 각각5/5/5/4개만 양수이며 방향이 섞여 있다. 구간은 최적해 근방의 수치 불확실성이지 표본 신뢰구간이 아니다.",
    "7. R2의G는.0285046이며, 실패가 포함된 펀드쌍의기여.0206662와 보정된유효쌍의기여.00783846로 나뉜다. R1의G=.0191721은 보정유효쌍+.0625933, 실패포함쌍-.0434212의 합이다. 겉으로 보이는 거리 변화는 유효한 정보 반영과 실패 시 기존 비중 유지가 섞인 정책 결과다.",
    "",
    "R0의 정보 기준 구분",
    "추가전망이 없는R0는 이용가능정보 기준R=.00708260339314(월간.708260339314%p), 전체정보 기준R=.00901604362737(월간.901604362737%p)이다. 차이.193344023423%p는 평가 정보기준을 바꾼 차이이며, 목적함수μ와 최적배분v가 함께 달라지므로 독립적인 인과적 정보부족효과라고 쓰지 않는다. G_available=-.3219465244, G_full=-.0334104776이다.",
    "",
    "기존비중만 유지하는 비교 계산",
    "모든펀드가h를유지할경우 D=.358139275126, 평균전체정보R=.00878394921208(월간.878394921208%p). 네모델조건의표본평균R은이값보다모두높다. 이는같은기준해에대한진단용산술비교이며 새로수행한모델대조군이아니다.",
    "",
    "표본·범위·단위 각주",
    *["- " + text for text in audit["method_notes"]],
    "- 동일 run의 480개 응답기록과 원출력실패도 전부 포함했다. 483회 원장 비용에는 응답 미확정 전송3회가 포함되어, 응답분석의분모480과구분한다.",
    "- R의단위는월간예상수익률의소수단위다.100을곱하면%p,10000을곱하면bp다.실제운용수익률이아니다.",
    "- 예시main009/F01은기전을설명하려고선택한사례이고평균효과의근거는전체160개다. 예시R1재배분은제약상유효하나h보다기회손실이크다.",
    "",
    "정밀도별 결과(각행:5개독립시나리오,20개작업흐름)",
    "r | 조건 | 원유효/보정유효/실패 | D | G | E | A | R(월간%p)",
]
for row in audit["stratum_arm_summary"]:
    notes.append(f"{row['r']} | {row['arm']} | {row['raw_valid']}/{row['rescued']}/{row['fallback']} | {row['D_full']:.6f} | {row['G_full']:.6f} | {row['E_full']:.6f} | {row['A_full']:.6f} | {row['R_full_monthly_percentage_points']:.6f}")
(OUT / "numeric_audit_notes.txt").write_text("\n".join(notes)+"\n", encoding="utf-8")
print(json.dumps({"matched_case_rows":len(matched), "notes":str(OUT / "numeric_audit_notes.txt")}))
