"""Prepare an exact, finite Treatment I answer table; do not call an AI model.

Hansen and Lee (2025), FEDS 2025-090, equations (1)--(7), sections
4.1--4.2 and 5.2.  The eight-period horizon comes from the paper.  Enumerating
all BUY/SELL prefixes, pairing the two signals at each prefix, and averaging
round-conditional losses equally are LIBERA benchmark construction choices.

Only the information-preserving, theoretical Treatment I path distribution is
enumerated.  Real AI sessions can choose NO_TRADE; their endogenous histories
are not represented by these prefixes.  NO_TRADE is nevertheless an admissible
response whose conditional regret can be evaluated at an enumerated state.

Examples (from the project root):
    python research/prepare_hansen_benchmark.py prepare
    python research/prepare_hansen_benchmark.py evaluate \
        --case-id T1-R01-ROOT-WHITE --action NO_TRADE

All benchmark arithmetic uses fractions.Fraction.  Serialized decimal values
are convenience approximations; the fraction strings are authoritative.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "hansen"
ROUNDS = 8
SIGNAL_ACCURACY = Fraction(7, 10)
PRIOR_HIGH = Fraction(1, 2)
HIGH_VALUE = Fraction(100)
LOW_VALUE = Fraction(0)
ACTIONS = {"BUY": 1, "SELL": -1, "NO_TRADE": 0}
SIGNALS = ("WHITE", "BLUE")


def rational(value: Fraction | int) -> dict[str, Any]:
    value = Fraction(value)
    return {"fraction": str(value), "decimal": float(value)}


def exact(value: dict[str, Any]) -> Fraction:
    """Read the authoritative representation, never its decimal approximation."""
    return Fraction(value["fraction"])


def require(condition: bool, description: str) -> None:
    if not condition:
        raise ArithmeticError(description)


def normalize_action(action: str) -> str:
    """Accept an action token only; invalid output is never changed to NO_TRADE."""
    canonical = action.strip().upper().replace("-", "_").replace(" ", "_")
    if canonical not in ACTIONS:
        raise ValueError(f"Invalid action {action!r}; expected BUY, SELL or NO_TRADE")
    return canonical


def history_state(history: tuple[str, ...]) -> tuple[Fraction, Fraction]:
    """Return P(v=100 | h), P(h) on the normative Treatment I paths."""
    buys = history.count("BUY")
    sells = history.count("SELL")
    good = SIGNAL_ACCURACY**buys * (1 - SIGNAL_ACCURACY)**sells
    bad = (1 - SIGNAL_ACCURACY)**buys * SIGNAL_ACCURACY**sells
    probability = PRIOR_HIGH * good + (1 - PRIOR_HIGH) * bad
    q = PRIOR_HIGH * good / probability
    return q, probability


def update_market_probability(q: Fraction, action: str) -> Fraction:
    """Equation (4) with rho=mu=1; NO_TRADE leaves q unchanged."""
    if action == "BUY":
        return SIGNAL_ACCURACY * q / (
            SIGNAL_ACCURACY * q + (1 - SIGNAL_ACCURACY) * (1 - q)
        )
    if action == "SELL":
        return (1 - SIGNAL_ACCURACY) * q / (
            (1 - SIGNAL_ACCURACY) * q + SIGNAL_ACCURACY * (1 - q)
        )
    if action == "NO_TRADE":
        return q
    raise ValueError(f"Invalid action {action!r}")


def signal_state(q: Fraction, signal: str) -> tuple[Fraction, Fraction]:
    """Return P(signal | h), P(v=100 | signal,h), equations (1),(6),(7)."""
    if signal == "WHITE":
        prob_high, prob_low = SIGNAL_ACCURACY, 1 - SIGNAL_ACCURACY
    elif signal == "BLUE":
        prob_high, prob_low = 1 - SIGNAL_ACCURACY, SIGNAL_ACCURACY
    else:
        raise ValueError(f"Invalid signal {signal!r}")
    probability = prob_high * q + prob_low * (1 - q)
    return probability, prob_high * q / probability


def evaluate_action(case: dict[str, Any], action: str) -> dict[str, Any]:
    """Score one valid action against the state-conditional monetary optimum.

    Regret is max_a E[payoff(a)|h,s] - E[payoff(action)|h,s].  It is not a
    realized investment return.  The private fundamental itself is not sampled.
    This function must receive a full answer-table case, not a prompt packet.
    """
    canonical = normalize_action(action)
    price = exact(case["model_visible"]["public_state"]["current_market_price"])
    expected_value = exact(case["evaluator_only"]["expected_fundamental_given_signal"])
    margin = expected_value - price
    expected_payoff = ACTIONS[canonical] * margin
    best_payoff = abs(margin)
    regret = best_payoff - expected_payoff
    require(regret >= 0, "Regret must be nonnegative")
    weights = case["evaluator_only"]["weights"]
    return {
        "case_id": case["case_id"],
        "action": canonical,
        "is_optimal": canonical in case["evaluator_only"]["optimal_actions"],
        "conditional_expected_payoff": rational(expected_payoff),
        "conditional_expected_regret": rational(regret),
        "round_joint_probability": weights["case_joint_probability_given_round"],
        "equal_round_evaluation_weight": weights["case_evaluation_weight"],
        "equal_round_weighted_regret_contribution": rational(
            regret * exact(weights["case_evaluation_weight"])
        ),
        "interpretation": "Conditional analytic score, not a realized or AI-observed result.",
    }


def source_metadata() -> dict[str, Any]:
    return {
        "title": "Financial Stability Implications of Generative AI: Taming the Animal Spirits",
        "authors": ["Anne Lundgaard Hansen", "Seung Jung Lee"],
        "series": "Finance and Economics Discussion Series 2025-090",
        "paper_date": "2025-09-25",
        "landing_url": "https://www.federalreserve.gov/econres/feds/financial-stability-implications-of-generative-ai-taming-the-animal-spirits.htm",
        "pdf_url": "https://www.federalreserve.gov/econres/feds/files/2025090pap.pdf",
        "arxiv_url": "https://arxiv.org/abs/2510.01451",
        "version_note": "The cited PDF is dated September 25, 2025; a landing-page update is not treated as a paper revision.",
        "locations": {
            "signal_accuracy": "Section 4.1, equation (1), printed page 9: correct WHITE/BLUE signal probability 0.7.",
            "price": "Section 4.1, equation (2): p_t = 100 q_t.",
            "market_update": "Section 4.1, equation (4): market-maker Bayesian update; use rho=mu=1 for Treatment I.",
            "optimal_action": "Section 4.2, equation (5): buy/sell according to private expected value relative to price.",
            "private_posterior": "Section 4.2, equations (6),(7), printed page 11: WHITE/BLUE conditional value, with q*=q in Treatment I.",
            "payoff": "Section 4.1, printed pages 9-10: one-unit, risk-neutral payoff v-p for BUY, p-v for SELL, zero for NO_TRADE. Table 5 (printed page 49) reports the corresponding conditional expected payoff. Regret is derived here, not copied as a reported paper statistic.",
            "treatment_I": "Section 4.2, printed page 12: rho=mu=1; an informed trader always buys on WHITE and sells on BLUE.",
            "eight_round_horizon": "Section 5.2, printed pages 15-16: four sessions of eight trading rounds per model; only the eight-round horizon is used here.",
        },
    }


def build_benchmark() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    histories: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    round_checks: list[dict[str, Any]] = []
    overall_optimal_payoff = Fraction(0)
    overall_history_weight = Fraction(0)
    overall_case_weight = Fraction(0)
    all_prices: list[Fraction] = []
    all_margins: list[Fraction] = []
    round_weight = Fraction(1, ROUNDS)
    for round_number in range(1, ROUNDS + 1):
        history_mass = Fraction(0)
        case_mass = Fraction(0)
        round_optimal_payoff = Fraction(0)
        count_history = 0
        count_case = 0
        for history in itertools.product(("BUY", "SELL"), repeat=round_number - 1):
            count_history += 1
            code = "".join("B" if x == "BUY" else "S" for x in history) or "ROOT"
            history_id = f"T1-R{round_number:02d}-{code}"
            q, probability_h = history_state(history)
            price = HIGH_VALUE * q
            public_state = {
                "trading_round": round_number,
                "history": list(history),
                "current_market_price": rational(price),
            }
            # Independent algebraic route: recursive equation (4) must agree.
            q_recursive = PRIOR_HIGH
            probability_recursive = Fraction(1)
            for past_action in history:
                signal = "WHITE" if past_action == "BUY" else "BLUE"
                probability_recursive *= signal_state(q_recursive, signal)[0]
                q_recursive = update_market_probability(q_recursive, past_action)
            require(q == q_recursive, f"Bayes/count identity failed at {history_id}")
            require(probability_h == probability_recursive, f"History chain-rule identity failed at {history_id}")
            require(update_market_probability(q, "NO_TRADE") == q, "NO_TRADE update identity")
            history_mass += probability_h
            overall_history_weight += probability_h * round_weight
            all_prices.append(price)
            histories.append({
                "history_id": history_id,
                "public_state": public_state,
                "evaluator_only": {
                    "market_high_value_probability": rational(q),
                    "informed_high_value_probability_before_signal": rational(q),
                    "history_probability_given_round": rational(probability_h),
                    "equal_round_pair_evaluation_weight": rational(probability_h * round_weight),
                    "signal_pair_case_ids": [f"{history_id}-{s}" for s in SIGNALS],
                },
            })
            signal_mass = Fraction(0)
            posterior_average = Fraction(0)
            for signal in SIGNALS:
                count_case += 1
                probability_s, q_signal = signal_state(q, signal)
                expected_value = HIGH_VALUE * q_signal
                margin = expected_value - price
                optimal_actions = [a for a, position in ACTIONS.items() if position * margin == abs(margin)]
                expected_action = "BUY" if signal == "WHITE" else "SELL"
                require(optimal_actions == [expected_action], f"Treatment I strict optimum at {history_id}/{signal}")
                joint = probability_h * probability_s
                evaluation_weight = joint * round_weight
                case = {
                    "schema_version": SCHEMA_VERSION,
                    "case_id": f"{history_id}-{signal}",
                    "history_id": history_id,
                    "treatment": "I",
                    "model_visible": {"public_state": public_state, "private_signal": signal},
                    "evaluator_only": {
                        "market_high_value_probability": rational(q),
                        "informed_high_value_probability_before_signal": rational(q),
                        "high_value_probability_given_signal": rational(q_signal),
                        "expected_fundamental_given_signal": rational(expected_value),
                        "optimal_actions": optimal_actions,
                        "optimal_conditional_expected_payoff": rational(abs(margin)),
                        "action_expected_payoffs": {
                            a: rational(position * margin) for a, position in ACTIONS.items()
                        },
                        "action_expected_regrets": {
                            a: rational(abs(margin) - position * margin) for a, position in ACTIONS.items()
                        },
                        "weights": {
                            "history_probability_given_round": rational(probability_h),
                            "signal_probability_given_history": rational(probability_s),
                            "case_joint_probability_given_round": rational(joint),
                            "equal_round_averaging_weight": rational(round_weight),
                            "case_evaluation_weight": rational(evaluation_weight),
                        },
                    },
                }
                for action in ACTIONS:
                    score = evaluate_action(case, action)
                    expected_regret = exact(case["evaluator_only"]["action_expected_regrets"][action])
                    require(exact(score["conditional_expected_regret"]) == expected_regret, "Evaluator regret identity")
                require(exact(case["evaluator_only"]["action_expected_regrets"][expected_action]) == 0, "Optimal regret zero")
                require(exact(case["evaluator_only"]["action_expected_regrets"]["NO_TRADE"]) == abs(margin), "NO_TRADE regret identity")
                opposite = "SELL" if expected_action == "BUY" else "BUY"
                require(exact(case["evaluator_only"]["action_expected_regrets"][opposite]) == 2 * abs(margin), "Opposite regret identity")
                cases.append(case)
                signal_mass += probability_s
                posterior_average += probability_s * q_signal
                case_mass += joint
                overall_case_weight += evaluation_weight
                round_optimal_payoff += joint * abs(margin)
                all_margins.append(abs(margin))
            require(signal_mass == 1, f"Conditional signal mass at {history_id}")
            require(posterior_average == q, f"Posterior tower identity at {history_id}")
        require(history_mass == 1, f"History mass in round {round_number}")
        require(case_mass == 1, f"Case mass in round {round_number}")
        require(count_history == 2 ** (round_number - 1), "History count per round")
        require(count_case == 2**round_number, "Case count per round")
        overall_optimal_payoff += round_weight * round_optimal_payoff
        round_checks.append({
            "trading_round": round_number,
            "history_count": count_history,
            "case_count": count_case,
            "history_probability_sum": rational(history_mass),
            "case_joint_probability_sum": rational(case_mass),
            "analytic_oracle_expected_payoff": rational(round_optimal_payoff),
            "analytic_always_no_trade_expected_regret": rational(round_optimal_payoff),
        })
    require(len(histories) == 2**ROUNDS - 1 == 255, "Total history count")
    require(len(cases) == 2 * (2**ROUNDS - 1) == 510, "Total signal case count")
    require(overall_history_weight == 1, "Equal-round history-pair weight sum")
    require(overall_case_weight == 1, "Equal-round case weight sum")
    require(len({x["case_id"] for x in cases}) == len(cases), "Case IDs unique")
    require(min(all_margins) > 0, "No indifferent cases on these finite Treatment I paths")
    checks = {
        "arithmetic": "exact fractions.Fraction; no numerical tolerances or sampled draws",
        "all_checks_passed": True,
        "rounds": round_checks,
        "equal_round_history_pair_weight_sum": rational(overall_history_weight),
        "equal_round_case_weight_sum": rational(overall_case_weight),
        "identities_verified": [
            "closed-form and sequential equation (4) Bayes updates coincide",
            "closed-form history probability equals the product of sequential normative action probabilities",
            "history probability sums to one separately in every round",
            "conditional WHITE and BLUE probabilities sum to one at every history",
            "case joint probabilities sum to one separately in every round",
            "conditional posterior mean equals pre-signal q (Bayes tower property)",
            "WHITE strictly prefers BUY and BLUE strictly prefers SELL in all cases",
            "optimal regret=0; NO_TRADE regret=absolute private-value-price gap; opposite regret=twice gap",
            "all action regrets are nonnegative; exported evaluator agrees with exact answer table",
        ],
        "price_minimum": rational(min(all_prices)),
        "price_maximum": rational(max(all_prices)),
        "positive_private_value_price_gap_minimum": rational(min(all_margins)),
        "positive_private_value_price_gap_maximum": rational(max(all_margins)),
        "analytic_equal_round_oracle_expected_payoff": rational(overall_optimal_payoff),
        "analytic_equal_round_always_no_trade_expected_regret": rational(overall_optimal_payoff),
        "analytic_equal_round_always_opposite_expected_regret": rational(2 * overall_optimal_payoff),
        "diagnostic_interpretation": "Analytic reference-policy scores only. No AI responses, observed experiment results, or statistical confidence claim.",
    }
    return histories, cases, checks


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def prepare(output: Path) -> dict[str, Any]:
    histories, cases, checks = build_benchmark()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "prepared_exact_answer_table_no_ai_experiment_run",
        "units": "One-unit asset prices, conditional expected payoffs and regret in the paper's fictional lire; not percentages or real investment returns.",
        "source": source_metadata(),
        "scope": {
            "treatment": "I",
            "paper_parameters": {"rho": rational(1), "mu": rational(1), "signal_accuracy": rational(SIGNAL_ACCURACY), "prior_high_value_probability": rational(PRIOR_HIGH), "fundamental_values": [rational(LOW_VALUE), rational(HIGH_VALUE)], "rounds": ROUNDS},
            "history_count": len(histories),
            "signal_case_count": len(cases),
            "history_lengths": list(range(ROUNDS)),
            "history_actions_enumerated": ["BUY", "SELL"],
            "response_actions_scored": list(ACTIONS),
            "signals": list(SIGNALS),
            "sampling": "Complete finite enumeration; no seed, simulated draws, or independently sampled markets.",
            "excluded": ["Treatment II and III", "endogenous AI trading histories including NO_TRADE prefixes", "new AI/API calls", "private institutional forecasts", "real investment returns"],
            "independence_warning": "The 255 histories and 510 conditional cases are overlapping finite benchmark states, not 255 or 510 independent observations. The paper's four sessions are not imported as a new sample-size or power claim.",
            "signal_pair_warning": "Every WHITE/BLUE pair has opposite strict optimal actions in Treatment I; no same-optimum signal pairs are supplied. This simple task may yield a ceiling effect.",
            "paper_vs_extension": "Treatment I primitives, Bayes updates, payoff/action rule and the eight-round horizon come from the paper. Exhaustive BUY/SELL prefix enumeration, separate-signal prompt cases, and equal-round aggregate reporting are LIBERA benchmark construction choices. The paper uses a strategy method that asks both counterfactual signals together.",
        },
        "formulas": {
            "history_probability": "P(h) = [0.7^B 0.3^S + 0.3^B 0.7^S]/2",
            "market_posterior": "q = 0.7^B 0.3^S/[0.7^B 0.3^S + 0.3^B 0.7^S]; q*=q in Treatment I",
            "price": "p = 100q",
            "signal_probability": "P(WHITE|h)=0.7q+0.3(1-q); P(BLUE|h)=0.3q+0.7(1-q)",
            "private_value": "m_WHITE=100(0.7q)/P(WHITE|h); m_BLUE=100(0.3q)/P(BLUE|h)",
            "action_payoff": "E[payoff(a)|h,s] = a(m_s-p), a in {+1 BUY,-1 SELL,0 NO_TRADE}",
            "regret": "R(a|h,s) = |m_s-p| - a(m_s-p)",
            "round_conditional_expected_regret": "sum_h P(h) sum_s P(s|h) R(a(h,s)|h,s)",
            "optional_equal_round_expected_regret": "(1/8) sum_t sum_h P(h|t) sum_s P(s|h) R(a_t(h,s)|h,s)",
            "paired_same_action_rate": "Within each history compare its WHITE and BLUE responses; weight histories by P(h|t) within each round. Optional equal-round aggregate uses P(h|t)/8. Pair collapse does not identify which action is correct; report regret as well.",
        },
        "prompt_exposure": {
            "allowed_model_input": ["model_visible.public_state", "model_visible.private_signal only at the assigned information-onset stage and later"],
            "runner_metadata_never_serialize_into_model_input": ["case_id", "history_id", "evaluator_only", "schema_version", "treatment"],
            "case_id_leak_warning": "case_id contains the signal token. It must not appear in early R4 prompts, tool arguments visible to the model, filenames visible to the model, or any other model-visible metadata. All case identifiers are runner-only.",
            "model_visible_schema": {"public_state": {"trading_round": "integer 1..8", "history": "BUY/SELL array of length round-1", "current_market_price": {"fraction": "exact rational string", "decimal": "approximation"}}, "private_signal": "WHITE or BLUE string; reveal at the workflow-specific stage only"},
            "keep_evaluator_only_hidden": True,
            "instruction": "R1/R4/FRESH packet construction is outside this file. Do not expose posterior q, private value m, optimum, regret, or probability weights to the model. Public rules/payoff/value/signal accuracy should be held constant by that packet builder.",
        },
        "checks": checks,
        "first_history_cases": cases[:2],
        "evaluator": {
            "python": "research.prepare_hansen_benchmark.evaluate_action(case, action)",
            "cli": "python research/prepare_hansen_benchmark.py evaluate --case-id T1-R01-ROOT-WHITE --action NO_TRADE",
            "valid_actions": list(ACTIONS),
            "invalid_response_policy": "Raise ValueError; never impute NO_TRADE, a numeric penalty, or an optimal answer. Workflow retry and invalid/missing coverage reporting belong to the runner.",
        },
    }
    write_jsonl(output / "histories.jsonl", histories)
    write_jsonl(output / "cases.jsonl", cases)
    write_json(output / "summary.json", summary)
    file_info = {}
    for name in ("histories.jsonl", "cases.jsonl", "summary.json"):
        path = output / name
        file_info[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": summary["status"],
        "generator": "research/prepare_hansen_benchmark.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source": source_metadata(),
        "outputs": file_info,
        "reproduce": "python research/prepare_hansen_benchmark.py prepare",
        "deterministic": True,
        "external_ai_or_network_calls": 0,
    }
    write_json(output / "manifest.json", manifest)
    return {
        "status": summary["status"],
        "output_directory": str(output),
        "histories": len(histories),
        "cases": len(cases),
        "all_exact_checks_passed": checks["all_checks_passed"],
        "analytic_equal_round_no_trade_regret": checks["analytic_equal_round_always_no_trade_expected_regret"],
        "not_independent_samples": True,
        "ai_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="Write exact benchmark data and validate all states")
    prep.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    evaluate = commands.add_parser("evaluate", help="Score one action token; no AI calls")
    evaluate.add_argument("--cases", type=Path, default=DEFAULT_OUTPUT / "cases.jsonl")
    evaluate.add_argument("--case-id", required=True)
    evaluate.add_argument("--action", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.output_dir)
    else:
        case = None
        for line in args.cases.read_text(encoding="utf-8").splitlines():
            candidate = json.loads(line)
            if candidate["case_id"] == args.case_id:
                case = candidate
                break
        if case is None:
            parser.error(f"Unknown case ID: {args.case_id}")
        try:
            result = evaluate_action(case, args.action)
        except ValueError as error:
            parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
