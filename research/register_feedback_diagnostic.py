"""Offline registration of one explicitly reviewed development diagnostic."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import local_sector_feedback_diagnostic as runner


def reference(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--implementation-review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest,*_=runner.verify_manifest(args.manifest)
    review=json.loads(args.implementation_review.read_text(encoding='utf-8-sig'))
    if review.get('all_passed') is not True:
        raise ValueError('Implementation preflight review has not passed')
    reviewed = review.get('reviewed_manifest', {})
    if (Path(reviewed.get('path', '')).resolve() != args.manifest.resolve()
            or reviewed.get('sha256') != reference(args.manifest)['sha256']):
        raise ValueError('Implementation review must pin this exact manifest')
    if not review.get('source_files'):
        raise ValueError('Implementation review must identify reviewed files')
    for row in review['source_files']:
        path = Path(row['path'])
        path = path if path.is_absolute() else runner.ROOT / path
        if reference(path)['sha256'] != row['sha256']:
            raise ValueError('Reviewed source changed: ' + str(path))
    refs=[args.manifest,args.implementation_review,
          runner.ROOT/'research/evaluator_only/v46_priority1_prerun_review_20261018.json',
          runner.ROOT/'research/evaluator_only/v46_replay_priority1_rubric_addendum_20261018.json',
          runner.ROOT/'research/v46_single_revision_basis_addendum_20261018.json',
          runner.ROOT/'data/sector_protocol/evaluation_spec.json',Path(__file__)]
    value={
        'protocol_version':runner.PROTOCOL,'diagnostic_id':runner.DIAGNOSTIC_ID,
        'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'manifest':reference(args.manifest),'planned_generation_attempts':1,
        'automatic_retries':0,'main_model_calls':0,'main_freeze':False,
        'purpose':'Priority1 development diagnostic on the preserved invalid v4.5 final candidate; not a four-stage workflow or independent confirmation.',
        'intervention':'Original public task plus complete old final response and exact calculator result, repeated in the active revision task. Model chooses raw correction; no target weights or external normalization.',
        'budget_basis':'One preselected corrective call is a local diagnostic scope, not an optimal iteration count claimed from a paper.',
        'retention':'All old and new raw, partial, invalid and completed outcomes are retained. This registration is not reused for repeated candidate selection.',
        'three_reviews':[
            {'round':1,'scope':'Provenance, exact inputs/options/rendering, raw output and recording.'},
            {'round':2,'scope':'Independent arithmetic, unchanged acceptance conditions, actual weight correction.'},
            {'round':3,'scope':'Truth of the prior-error, revision and final-validity explanations only.'}],
        'later_priorities':'No priority2 implementation or model call until all three priority1 reviews pass. Full-workflow suitability remains pending even after this diagnostic passes.',
        'limits':['The deliberately selected old failure is a development case.',
                  'Intermediate old assistant history is absent by design.',
                  'Market-number truth, source-rationale quality, R1/R4 effects and human source review remain unassessed in this gate.'],
        'reference_files':[reference(p) for p in refs],
        'online_boundary':'Registration and evaluator materials are not model prompt contents; only the frozen five messages are sent.',
        'human_semantic_pass':False,'model_calls_by_registration':0}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'registration':str(args.output),'sha256':reference(args.output)['sha256'],'model_calls':0}))


if __name__=='__main__':
    main()
