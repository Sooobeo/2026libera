"""Prespecify one pilot and three review scopes; no service or model access."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/sector_protocol/v44_single_case_registration_20261018.json'


def record(relative):
    path = ROOT / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    return {'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    value = {
        'protocol_version': '4.4',
        'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'One prespecified four-stage pilot case, followed by three distinct self-review rounds. No main run or main freeze.',
        'source_id': 'fidelity_q2_2026', 'arm': 'R1',
        'selection_basis': 'The same first pilot case used in the prior feasibility diagnosis; fixed before this full-response run, not chosen by an observed treatment effect.',
        'planned_cases': 1, 'planned_stages': [1, 2, 3, 4],
        'research_question_changed': False,
        'reference_files': [record(path) for path in (
            'research/v44_conditions_reference_20261018.json',
            'research/evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json',
            'data/sector_protocol/evaluation_spec.json',
            'data/sector_documents/source_manifest.json',
            'data/sector_market/market_input.json',
        )],
        'online_boundary': 'This registration is for offline audit. The online runner is given only its public packet, market, execution-condition evidence and code manifest. It must never read evaluator_only references.',
        'rounds': [
            {'round': 1, 'name': 'Execution, inputs and history',
             'basis': ['Pinned source bytes and settings', 'Official Ollama 0.35.1 request/rendering behavior', 'Four-stage workflow contract'],
             'checks': ['Exact selected public packet and market', 'Reversible duplicate-only projection',
                        'Model/engine/template/condition pins before each call',
                        'All visible messages preserved in the rendered prompt in order',
                        'Explicit no-truncation/no-shift flags and observed termination',
                        'Four captured stages or honest incomplete-case record',
                        'No automatic retry, response repair, hidden reference access or main call',
                        'Raw request/response, timing, memory, and unload evidence retained']},
            {'round': 2, 'name': 'Independent arithmetic and mechanical source checks',
             'basis': ['Existing evaluation_spec.json', 'Published sector labels and independently transcribed reference', 'Supplied common benchmark and covariance'],
             'checks': ['Sector identities and uniqueness', 'Exact submitted sum and signed residual',
                        'Nonnegative finite weights', 'Independent active-weight and quadratic-risk recomputation',
                        'Original source-label and evidence-ID scope checks',
                        'No invented exact-weight target or composite score'],
             'precision_policy': 'Report exact decimal/rational residuals when possible and preserve floating-point differences. Existing implementation tolerances are not paper-derived behavioral thresholds; no new outcome-dependent threshold.'},
            {'round': 3, 'name': 'Claim-to-source semantic review and study relevance',
             'basis': ['Pinned Fidelity Q2 original PDF with page locations', 'Selected public packet', 'Common market inputs and calculator results'],
             'checks': ['Each consequential claim linked to an actual source location or calculation',
                        'Supported, contradicted, not stated and uncertain kept separate',
                        'Public strategist view not recast as a legal mandate or hidden preference',
                        'Qualitative ratings not recast as unique numeric portfolio targets',
                        'Historical volatility not recast as loss probability or predicted performance',
                        'One R1 pilot not treated as R1/R4 effect, general strategy quality or main evidence']},
        ],
        'failure_policy': 'Keep failed, malformed, capped, timed-out and incomplete outputs. Do not silently retry, normalize weights, edit source text or tune settings against the observed allocation. A future revision must preserve this attempt and record new provenance.',
        'human_review': 'Three automated/assistant self-reviews do not constitute independent substantive human review.',
        'main_model_calls_authorized_here': 0, 'main_frozen': False,
        'generation_requests_by_this_script': 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'registration': str(OUTPUT), 'sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                      'model_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
