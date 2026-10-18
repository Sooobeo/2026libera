"""Register a versioned repair attempt before generation; evaluator refs stay offline."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def reference(path):
    path = Path(path).resolve()
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--implementation-review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = read(args.manifest)
    if manifest.get('case_id') != 'fidelity_q2_2026__R1':
        raise ValueError('Only the previously selected case is registered')
    prior = ROOT / 'data/local_sector_runtime/single_case_v44_20261018/summary.json'
    assert read(prior)['status'] == 'hard_deadline'
    refs = [args.manifest, args.implementation_review, prior,
            ROOT / 'research/v45_revision_reference_20261018.json',
            ROOT / 'research/evaluator_only/v45_structured_prerun_review_20261018.json',
            ROOT / 'research/evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json',
            ROOT / 'data/sector_protocol/evaluation_spec.json',
            ROOT / 'data/sector_documents/source_manifest.json', Path(__file__)]
    value = {
        'protocol_version': '4.5', 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'case_id': 'fidelity_q2_2026__R1', 'planned_cases': 1, 'planned_stages': [1, 2, 3, 4],
        'purpose': 'Repair the output interface on the same failed pilot case under a new user-authorized revision. This is not an independent confirmatory sample or a main-study run.',
        'revision': [
            'Supply an explicit response JSON schema to the API format parameter.',
            'Ground the same schema in each stage task prompt, preserving original task, source and market values.',
            'Validate the declared response structure after preserving raw output; do not repair or resample.',
        ],
        'unchanged': ['model/digest/engine/template', 'decoding options and output/context budgets',
                      '900-second supervised per-stage execution deadline', 'source packet and market numeric values',
                      'four task stages and calculator', 'raw assistant and calculator history',
                      'original offline source annotations and numeric scoring definitions'],
        'joint_intervention_limit': 'Prompt schema visibility and API grammar constraints change together. One paired engineering attempt cannot isolate their individual effects or establish a general causal performance gain.',
        'schema_is_not_a_target_answer': 'No source-specific rating, target allocation, risk-aversion number, expected return or hidden evidence answer is supplied by the schema. Common taxonomy and response shape are controls, not demonstrated capabilities.',
        'execution_policy': {'automatic_retries': 0, 'raw_repair': False, 'main_calls': 0,
                             'retain_failed_attempts': True,
                             'future_revision': 'A further change must preserve this attempt, identify its evidence and be recorded before new generation. Do not repeat unchanged requests to select favorable output.'},
        'completion_dimensions': {
            'workflow': 'Four terminated, structurally valid raw responses and four stage records.',
            'numeric': 'Report final raw calculator validity separately; provisional errors are fed back before the next stage, not normalized by the runner.',
            'semantic': 'Source ratings, rationale and strategy are reviewed separately; schema validity never means semantic PASS.',
        },
        'three_postrun_reviews': [
            {'round': 1, 'scope': 'Pinned inputs, schema grounding, visible history, raw transport, termination, version identity and cleanup.'},
            {'round': 2, 'scope': 'Independent exact arithmetic, source-label denominator, code and citation-scope checks on saved raw proposals.'},
            {'round': 3, 'scope': 'Original-source entailment, each stage task, rationale, risk interpretation and relation to the research question.'},
        ],
        'denominator_clarification': {
            'preserve_prior_reports': True,
            'registered_extraction_metric': 'The original evaluation specification keeps 11 expected sector labels in the denominator, including nonresponses. Thus the v4.4 failed attempt contributes 0/11 to that mechanical metric.',
            'conditional_semantic_and_numeric_review': 'No completed allocation means numeric and semantic assessments are not applicable, not an invented zero-risk or zero-strategy-quality score.',
            'reporting': 'Report completion, fixed-denominator extraction and applicable semantic/numeric assessment separately. Do not exclude failures to inflate successful-answer performance or pool protocol revisions as one fixed experiment.',
        },
        'online_boundary': 'This registration and evaluator-only review material are offline. The runner receives public evidence, market values, structural schema and execution provenance only.',
        'reference_files': [reference(p) for p in refs],
        'independent_human_review_complete': False, 'main_frozen': False,
        'model_calls_by_registration': 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'registration': str(args.output), 'sha256': reference(args.output)['sha256'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
