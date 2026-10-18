"""Record the coordinating author's contract/topic review of the main path.

The substantive entries record an actual source-code/document reading. They are
not a programmatic proof of financial semantics or an independent human audit.
No study candidate, execution gate, authorization or model call is created.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_v48_main_gate as gate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/evidence/v48_main_integration_20261019'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    prior_paths = [OUT / 'round1/review.json', OUT / 'round2_v2.json']
    inventories = {
        'software_hashes': {name: sha(ROOT / 'research' / name) for name in gate.SOFTWARE},
        'evaluator_software_hashes': {name: sha(ROOT / 'research' / name) for name in gate.EVALUATOR_SOFTWARE},
    }
    for number, path in enumerate(prior_paths, 1):
        prior = read(path)
        if prior.get('round') != number or prior.get('status') != 'PASS':
            raise ValueError('The final preceding review is incomplete')
        if any(prior.get(key) != value for key, value in inventories.items()):
            raise ValueError('Preceding review does not bind current code')
    readings = [
        ('fixed_public_case_scope', 'run_sector_v48_main.py', 'ROSTER; run',
         'Four prescribed Fidelity Q3 / UBS July by R1 / R4 cases; this is not a sample of private mandates or institution populations.'),
        ('human_source_review_distinct_from_model_review', 'sector_v48_main_gate.py', '_human_review; verify_main_gate',
         'The pre-generation review concerns literal sources, researcher paraphrases and comparability. Uncertain or non-comparable source findings are allowed with reasons; favorable strategic outcomes are not required. Identity is a declaration, not authentication.'),
        ('mandatory_hashes', 'sector_v48_main_gate.py', '_inventory; verify_main_gate',
         'Required online code and candidate file hashes are validated as lowercase SHA-256 before the helper with an optional expected hash is called. Missing/null/empty hashes cannot silently mean skip comparison.'),
        ('source_onset_and_common_input', 'prepare_sector_v48_main_candidate.py', 'preview_payloads',
         'The assigned source first appears at R1 stage1 or R4 stage4. All non-treatment authored payloads remain equal. Common baseline provenance is not mistaken for an early assigned-document disclosure.'),
        ('full_actual_history', 'sector_v48_main_transport.py', 'validate_authored_history',
         'Every request is rebuilt from frozen authored previews, literal completed prior responses and feedback computed from those actual responses. Future answers are absent from preparation.'),
        ('request_and_renderer_evidence', 'sector_v48_main_transport.py', 'validate_spec; validate_render',
         'The selected runtime controls and source visibility are checked before HTTP. Render-only evidence checks ordered message content; it is not independent tokenization or proof of unused context capacity.'),
        ('first_final_primary', 'run_sector_v48_main.py', 'run_case',
         'C0 is the first stage4 response. No clipping, normalization, replacement by an auxiliary success, source-defined optimal vector or hidden strategic target is introduced.'),
        ('bounded_auxiliary_path', 'run_sector_v48_main.py', 'run_case auxiliary branch',
         'A complete schema-valid finite eleven-sector C0 with arithmetic budget/bound error can enter C1/C2. The first valid allocation, contract/transport failure or C2 cap stops that path. These remain within-case observations.'),
        ('durable_attempt_accounting', 'run_sector_v48_main.py', 'durable_counts; run_case finally; run finally',
         'Preserved generation request envelopes are counted even when response parsing, recording or worker completion fails. Actual main calls are distinct from evaluator calls and from planned maxima.'),
        ('instrument_failure_vs_model_outcome', 'run_sector_v48_main.py', 'run fixed case loop',
         'Instrument incidents stop the bundle; model contract or arithmetic failures remain outcomes and do not require favorable replacement runs.'),
        ('temporary_operating_change', 'sector_v48_main_awake.py', 'acquire; release',
         'Idle-sleep prevention is temporary and thread-scoped, restored after active work. It is an engineering operating condition, not a paper-derived experimental optimum or a guarantee against explicit sleep.'),
        ('offline_materials_fixed', 'prepare_sector_v48_main_candidate.py', 'evaluator_materials',
         'Six offline evaluation references retain hashes from the existing source verification and pilot-pinned design handoff. Their contents are not included among the 32 public input files.'),
        ('offline_material_verification', 'evaluate_sector_v48_main_artifacts.py', 'verify_evaluator_material_refs; build_report',
         'The annotation path as well as its bytes must match the candidate. All six materials are verified before scoring and rechecked after analysis; mismatch stops evaluation rather than changing raw outputs.'),
        ('fixed_denominators_and_missingness', 'evaluate_sector_v48.py', 'evaluate_case; evaluate_bundle',
         'All four C0 cases and 44 sector rows remain represented. Partial transport text cannot become a completed vector; unavailable distances remain null, not zero. Sector rows, stages and repairs are not independent replicates.'),
        ('distance_condition_and_direction', 'evaluate_sector_v48.py', 'evaluate_bundle',
         'Half-L1 is reported only for eligible complete valid raw pairs; the R4-minus-R1 between-source distance difference requires all four valid C0s. Larger distance is not defined as better strategy.'),
        ('literal_evidence_not_semantic_score', 'render_v48_main_review_packet.py', 'main report rendering',
         'Main captions may change, but raw quoted source/model content is not relabelled by global string replacement. Labels, resolved fact IDs and arithmetic remain diagnostics; human semantic findings stay unfilled.'),
        ('candidate_not_execution_authority', 'prepare_sector_v48_main_candidate.py', 'verify_technical_receipt; prepare',
         'Three technical reviews enable offline packaging only. Candidate flags remain main_authorized=false, main_frozen=false and human_review_completed=false. Later candidate-specific reviews and source review remain separate.'),
        ('research_question_preserved', 'v48_topic_alignment_basis_20261018.json', 'research_question_mapping; management_and_economics_connection',
         'The observation is public source judgment -> interpretation/reasons -> actual sector allocation. Calculation is a verifier, not a strategy ground-truth comparator. Responses concern organizational review responsibility without measuring real returns or social costs.'),
        ('limits_retained', 'v48_topic_alignment_basis_20261018.json', 'RQ2_workflow_comparison; forbidden_conclusions',
         'R1/R4 changes exposure onset, position, history and opportunities together. This case comparison does not isolate memory/anchoring or establish the causal effect of shared AI adoption.'),
        ('parameters_not_reinvented', 'v48_parameter_reference_addendum_20261018.json', 'entire pinned parameter classification',
         'Existing literature/adaptation/engineering distinctions remain intact. No new risk-aversion coefficient, source-to-weight conversion, composite success threshold or optimal numerical allocation is introduced.'),
    ]
    findings = [{'id': cid, 'status': 'PASS', 'review_method': 'coordinating_AI_source_reading',
                 'file': ref(ROOT / 'research' / filename), 'locator': locator, 'finding': finding}
                for cid, filename, locator, finding in readings]
    report = {
        'round': 3, 'status': 'PASS', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        **inventories, 'candidate_bound': False, 'model_calls': 0, 'main_model_calls': 0,
        'independent_human_review_completed': False,
        'reviewer': {'reviewer_id': '/root', 'name_or_model_identity': 'Codex coordinating AI reviewer',
                     'reviewer_role': 'assistant_self_review'},
        'scope': 'Contract, source lineage and paper-topic review of the main implementation; no production execution or semantic certification.',
        'authorship_disclosure': 'Root coordinated the implementation and wrote review/reporting code. Subagents authored implementation/tests. All three rounds are AI technical reviews, not independent human study review.',
        'checks': findings, 'previous_reviews': [ref(path) for path in prior_paths],
        'uncompleted': ['actual candidate-bound three-round review', 'independent human original-source review',
                        'main input/evaluator freeze and execution decision', 'main responses and their semantic review'],
        'auditor': ref(__file__),
    }
    path = OUT / 'round3.json'
    save(path, report)
    receipt = {
        'artifact_kind': 'v4.8_main_technical_three_review_receipt', 'status': 'PASS',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'candidate_bound': False,
        'model_calls': 0, 'main_model_calls': 0, 'independent_human_review_completed': False,
        **inventories, 'reviews': [ref(p) for p in [*prior_paths, path]],
        'inventory_counts': {'online_entries': 13, 'evaluation_entries': 9,
                             'unique_files': len(set(gate.SOFTWARE) | set(gate.EVALUATOR_SOFTWARE))},
        'scope': 'Non-authorizing implementation receipt; permits offline candidate preparation after separate actual-pilot reviews.',
    }
    save(OUT / 'three_review_receipt.json', receipt)
    print(json.dumps({'status': 'PASS', 'findings': len(findings), 'model_calls': 0,
                      'receipt': str(OUT / 'three_review_receipt.json')}))


if __name__ == '__main__':
    main()
