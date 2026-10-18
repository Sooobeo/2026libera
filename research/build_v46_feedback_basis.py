"""Collect primary-source evidence for the feedback-only development revision.

No inference, portfolio editing, or changes to existing experiment artifacts.
The output is a reference memo, not execution authorization or protocol selection.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "research/evidence/v46_feedback_20261018"
OUT = ROOT / "research/v46_feedback_basis_20261018.json"
SOURCES = [
    ("openpm", "openpm_2608_09988v1.html", "https://arxiv.org/html/2608.09988v1"),
    ("openpm_metadata", "openpm_abs.html", "https://arxiv.org/abs/2608.09988"),
    ("uptake", "uptake_2607_15388v1.html", "https://arxiv.org/html/2607.15388v1"),
    ("uptake_metadata", "uptake_abs.html", "https://arxiv.org/abs/2607.15388"),
    ("code_repair", "code_repair_2604_10508v1.html", "https://arxiv.org/html/2604.10508v1"),
    ("code_repair_metadata", "code_repair_abs.html", "https://arxiv.org/abs/2604.10508"),
    ("critic", "critic_2305_11738v4.pdf", "https://arxiv.org/pdf/2305.11738v4"),
    ("critic_metadata", "critic_abs.html", "https://arxiv.org/abs/2305.11738"),
]


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def collect(entry: tuple[str, str, str]) -> dict:
    key, filename, url = entry
    path = EVIDENCE / filename
    req = urllib.request.Request(url, headers={"User-Agent": "LIBERA-research-evidence/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        blob = response.read()
        status, final_url = response.status, response.url
    if not blob or status != 200:
        raise RuntimeError(f"No complete primary source: {url}")
    if path.exists():
        if path.read_bytes() != blob:
            raise RuntimeError(f"Refusing to replace preserved evidence: {path}")
    else:
        path.write_bytes(blob)
    return {"source_id": key, "url": url, "resolved_url": final_url,
            "path": path.relative_to(ROOT).as_posix(), "sha256": digest(blob),
            "size_bytes": len(blob), "http_status": status}


def existing(path: str) -> dict:
    full = ROOT / path
    return {"path": path, "sha256": digest(full.read_bytes()), "size_bytes": full.stat().st_size}


def build(sources: list[dict]) -> dict:
    papers = [
        {
            "source_id": "openpm", "citation": "Cai et al. (2026), OpenPM, arXiv:2608.09988v1",
            "role": "latest_financial_precedent_for_separating_raw_adherence_and_system_feasibility",
            "locators": ["Section 3.3", "Section 4, final paragraph", "Section 5, Evaluation protocol", "Section 6.3"],
            "verified_findings": [
                "Typed constraints are enforced by a deterministic critic that directly projects, clips and scales proposed weights.",
                "Raw mandate adherence is reported separately from post-critic feasibility. The system, not the constructor model, guarantees the executed constraints.",
                "Audit artifacts distinguish PASS, FAIL and UNKNOWN contamination status; this is not a model-revision success rule."
            ],
            "not_supported": [
                "No model-feedback-rewrite iteration budget is established by these sections.",
                "Projection success cannot demonstrate that the model used feedback or chose feasible raw weights.",
                "Its position/name caps, cash buffer and trading assumptions are not imported into LIBERA."
            ],
            "libera_transfer": "Keep raw proposal, external check and acceptance status separate; reject its automatic projection for the current no-repair research question."
        },
        {
            "source_id": "uptake", "citation": "Yang et al. (2026), Precise but Uncoupled, arXiv:2607.15388v1",
            "role": "latest_direct_feedback_uptake_and_bounded_verifier_guided_revision_precedent",
            "locators": ["Sections 3.2-3.4", "Section 4.2, Within-PER coupling interventions; Figure 4", "Appendix I, Table 12", "Appendix I.1, Single-Agent Iterative and PER Reviewer", "Appendix I.3", "Section 6"],
            "verified_findings": [
                "Detection, immediate candidate change and successful repair are distinct observations; answer change alone does not prove understanding.",
                "Table 12 caps Single-Agent Iterative and PER at three outer attempts; PER has two inner rounds per attempt.",
                "Prior candidate and failure advice are exposed; the PER reviewer instruction forbids approval after a failure indicator.",
                "Mandatory verbal acknowledgment lowers FinalPassRate from 85.2% to 82.5%; embedding feedback reaches 86.3%, without uniformly improving all uptake diagnostics."
            ],
            "not_supported": [
                "The tested primary actor/evaluator is gpt-oss-120b on olympiad mathematics, not Qwen3.5-4B on financial allocation.",
                "Three attempts is an experimental configuration, not a proven optimum for this task.",
                "Acknowledgment is not evidence of repair, and direct presentation does not guarantee success.",
                "The paper states code/data release awaits institutional approval; executable implementation parity is not independently established here."
            ],
            "libera_transfer": "Observe raw-vector change and recalculated feasibility separately. A bounded external arithmetic acceptance gate is a LIBERA adaptation; never supply evaluator-only labels or target weights."
        },
        {
            "source_id": "code_repair", "citation": "Arimbur (2026), How Many Tries Does It Take?, arXiv:2604.10508v1",
            "role": "recent_minimal_error_feedback_and_model_rewrite_precedent",
            "locators": ["Section III-A", "Section V-H", "Section V-I", "Section VI-E", "Section VII"],
            "verified_findings": [
                "The next repair prompt contains the original specification, previous code and actual execution error; the model produces a new candidate and tests run again.",
                "The main protocol allows four repair rounds after an initial attempt, five attempts total; prompt ablations use two repair rounds, three attempts total.",
                "Greedy repair uses temperature zero. Model and task dependence, and the repair-versus-resampling decoding confound, are disclosed."
            ],
            "not_supported": [
                "The smallest evaluated model is Llama 3.1 8B; Qwen3 32B is not Qwen3.5-4B.",
                "Code-test success is not portfolio strategy quality. Published repair gains and budgets are not validated LIBERA outcomes.",
                "A repair prompt containing the previous candidate does not authorize dropping LIBERA's retained history."
            ],
            "libera_transfer": "Use the actual calculator error and unchanged task beside the prior raw proposal, ask the model to rewrite, then recompute; keep the original immutable."
        },
        {
            "source_id": "critic", "citation": "Gou et al. (ICLR 2024), CRITIC, arXiv:2305.11738v4",
            "role": "older_foundational_tool_critique_revision_algorithm_not_latest_financial_evidence",
            "locators": ["Algorithm 1, printed page 4 / PDF page index 3", "Section 3", "Section 4.2, printed page 7 / PDF page index 6"],
            "verified_findings": [
                "Algorithm 1 alternates external-tool critique and model correction under a finite iteration parameter n and a stopping condition.",
                "Its mathematical-program experiment permits four corrections and stops after two consecutive unchanged execution results; correction uses sampling p=0.5."
            ],
            "not_supported": [
                "Its stopping decision can use the critique rather than a sound arithmetic verifier.",
                "Its correction sampling and task budgets are not silently substituted for the frozen LIBERA greedy runtime.",
                "Returning the final candidate after the budget does not establish correctness or justify a success status."
            ],
            "libera_transfer": "Supports a finite verify-rewrite-verify pattern, with independent calculator acceptance and honest terminal failure added as explicit local design choices."
        }
    ]
    return {
        "schema_version": "libera_v46_feedback_basis_1.0",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "protocol_version_under_consideration": "4.6",
        "status": "primary_source_reference_memo_not_execution_registration",
        "priority_scope": "1_calculator_feedback_uptake_only",
        "model_calls_by_researcher": 0, "main_model_calls_authorized": 0,
        "prior_files_modified": False,
        "primary_sources": sources,
        "papers": papers,
        "observed_local_failure": {
            "source_files": [existing("research/v45_single_case_round2_20261018.json"), existing("research/v45_single_case_round3_20261018.json")],
            "facts": ["All four v4.5 raw proposals sum to 0.965 and remain invalid.", "Stage 4 claims the initial allocation already met the sum constraint despite three preceding calculator failures."],
            "not_generalized": "One reused development case, not evidence of population-level failure rates."
        },
        "recommended_first_candidate": {
            "name": "same_stage_budget_explicit_error_grounding_and_external_acceptance",
            "status": "recommendation_requires_pre_run_registration_of_exact_prompt_and_runner",
            "change_scope": "Make the current calculator failure and the instruction to revise the raw allocation explicit in the active task; derive acceptance status from a new calculator check, never from the model's self-approval.",
            "controls": "Retain four stages, model/decoding/time limits, source and market inputs, raw assistant history and feedback; add no extra generation attempts in this first candidate.",
            "budget_evidence": "Four stages is the existing LIBERA design, not the three outer attempts of Yang et al. or five code attempts of Arimbur. Preserving it limits a compute confound.",
            "steps": [
                "Keep the prior raw proposal and its actual calculator result unchanged and visible.",
                "Expose failing public task constraints, measured raw sum/residual and required existing condition in the current revision task; do not supply a corrected vector or a sector-specific suggested weight.",
                "The model may change its own candidate. Preserve the new raw response, calculate it afresh and compare the old/new vectors without normalization.",
                "Record changed versus unchanged, feasible versus infeasible and the truth of the model's feedback-use claim separately.",
                "At the predeclared final opportunity, retain an invalid candidate as invalid; do not turn workflow completion into allocation success or continue unregistered retries."
            ],
            "early_stage_rule": "An invalid provisional allocation is recorded and receives the next already-budgeted revision opportunity; it is never accepted as valid merely to advance the workflow.",
            "no_guarantee": "The v4.5 history already included calculator feedback. This narrower interface change is a testable hypothesis, not a literature-proven fix.",
            "next_priorities_excluded": ["Market-number/explanation consistency work", "Substantive allocation-rationale enrichment"]
        },
        "alternative_if_explicitly_selected_before_generation": {
            "name": "bounded_candidate_revision_loop",
            "max_candidate_attempts": 3, "max_revisions_after_initial": 2,
            "evidence": "Yang et al. Appendix I Table 12; Arimbur Section V-H has the same total in a prompt ablation.",
            "status": "unselected_transferred_candidate_not_a_paper_optimum",
            "warning": "Candidate attempts must be defined separately from the four research stages; adding this loop changes call budget and protocol topology and cannot be attributed only to prompt grounding."
        },
        "acceptance_and_terminal_rules": {
            "source_status": "Explicit LIBERA engineering/measurement adaptation; no paper reports this exact contract.",
            "numeric_acceptance": "Only the existing complete finite 11-sector, long-only, full-investment calculator rules and existing tolerances; no target portfolio or new behavioral threshold.",
            "numeric_tolerances": "Existing implementation tolerances are not paper-derived behavioral parameters. Exact Decimal/Fraction residuals remain separately reported.",
            "model_self_report_is_not_gate": True,
            "no_automatic_normalization_projection_clipping_cash_or_repair": True,
            "no_hidden_gold_or_source_specific_weight_targets": True,
            "on_budget_exhausted": "Preserve final raw invalid output, all failed checks and all attempts; status remains unresolved/invalid, with no successful-allocation claim.",
            "on_timeout_or_incomplete_output": "Preserve partial bytes and distinguish unobserved results from observed invalid complete proposals.",
            "priority2_and_priority3": "Do not begin until the three user-requested independent checks of priority 1 pass; three audits is a user instruction, not three model attempts or a paper-derived sample size.",
            "main_experiment": "Forbidden in the current authorization."
        },
        "falsifiable_outcomes": [
            "Did an invalid vector change after its actual failure feedback?",
            "Did a new raw vector pass the unchanged calculator without repair?",
            "Does the feedback-use claim agree with the actual prior and current results?",
            "Did the run stop within its registered call/time budget and keep every failure?"
        ],
        "claim_limits": [
            "Changing a candidate is not proof that feedback caused the change; this is a single development trajectory, not a randomized causal comparison.",
            "A feasible allocation does not establish rationale faithfulness, financial optimality, realized return or model generality.",
            "Mandatory acknowledgment alone has negative counterevidence; any status field is observational and must be checked against arithmetic.",
            "No cited paper directly validates this frozen quantized 4B model on this 11-sector institutional-document task."
        ]
    }


def render(d: dict) -> str:
    source = {s["source_id"]: s for s in d["primary_sources"]}
    rows = []
    for p in d["papers"]:
        link = source[p["source_id"]]["url"]
        claims = "<br>".join(html.escape(x) for x in p["verified_findings"])
        limitations = "<br>".join(html.escape(x) for x in p["not_supported"])
        rows.append(f'<tr><td><a href="{html.escape(link)}">{html.escape(p["citation"])}</a><p>{html.escape("; ".join(p["locators"]))}</p></td><td>{claims}</td><td>{limitations}</td></tr>')
    return '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>v4.6 계산 피드백 수정 근거</title>
<style>body{max-width:1100px;margin:36px auto;padding:0 20px;font:16px/1.65 system-ui;color:#182a3c}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ddd;vertical-align:top}td{width:33%}a{overflow-wrap:anywhere}</style><main>
<h1>계산 피드백 반영: 수정 전에 확인한 근거</h1>
<p><b>우선 권고는 기존 네 단계와 실행 예산을 유지하면서, 현재 과제에 실제 계산 오류와 수정 요구를 직접 붙이고 다음 원안의 재계산 결과로 유효성을 판정하는 것입니다.</b> 계산기가 비중을 대신 고치지 않습니다. 오류를 인정하는 문장을 쓰는 것만으로 성공 판정을 하지 않습니다.</p>
<p>v4.5는 네 단계 모두 비중 합계 96.5%를 그대로 유지했습니다. 기존 이력에도 피드백이 있었으므로, 전달 방식을 더 명확히 하는 이번 후보가 효과가 있을지는 새 개발 사례로 확인해야 합니다. 아직 새 실행이나 수정 성공은 보고하지 않습니다.</p>
<p>최신 직접 관련 연구는 오류 발견, 다음 답변의 변화, 실제 수정 성공을 나눠 평가합니다. 오히려 의무적인 오류 인정 문장만 추가한 조건은 성능이 떨어졌습니다. 따라서 다음 원안의 실제 수치와 재계산을 확인하는 절차가 필요합니다.</p>
<p>기존 네 단계를 넘는 별도 수정 루프를 선택한다면, 문헌에는 초안 포함 최대 세 번의 후보 제출이라는 선례가 있습니다. 이는 다른 모델·수학/코딩 과제에서 가져온 후보이며 최적값이 아닙니다. 추가 호출은 별도 사전등록 대상이고 네 연구 단계와 혼동하지 않습니다.</p>
<table><tr><th>원문·위치</th><th>확인한 내용</th><th>전용할 수 없는 주장</th></tr>''' + "".join(rows) + '''</table>
<p><b>실패 처리:</b> 정해진 기회 안에 합계 조건을 충족하지 못하면 마지막 원안을 무효로 남깁니다. 정규화·현금 간주·투영·정답 비중 주입·추가 무등록 재시도는 하지 않습니다. 완료되지 않은 응답과 완료됐지만 무효인 응답도 구분합니다.</p>
<p>이번 범위는 ① 계산 피드백 반영입니다. 사용자 요청에 따른 세 차례 검증을 통과하기 전에는 ② 숫자/설명 일치, ③ 근거 충실성 수정으로 넘어가지 않으며 본실험은 실행하지 않습니다. 세 차례 검증은 논문의 반복 횟수나 표본 수가 아닙니다.</p>
<p>이는 연구근거 메모이며 실행 등록서가 아닙니다. 정확한 프롬프트·상태 규칙·예산 선택은 실행 전에 별도로 고정해야 합니다. <a href="v46_feedback_basis_20261018.json">전체 출처·SHA·후보·한계 JSON</a></p></main></html>'''


def main() -> None:
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite a saved reference memo.')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        sources = list(executor.map(collect, SOURCES))
    d = build(sources)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    OUT.with_suffix('.html').write_text(render(d), encoding='utf-8')
    print(json.dumps({'path':str(OUT), 'sha256':digest(OUT.read_bytes()), 'primary_source_count':len(sources)}, indent=2))


if __name__ == '__main__':
    main()
