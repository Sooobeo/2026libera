"""Register the reviewed, fixed two-call priority1 development diagnostic."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import local_sector_plan_execute_diagnostic as runner


def reference(path):
    path=Path(path).resolve()
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--implementation-review',type=Path,required=True)
    p.add_argument('--rubric',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    runner.verify_manifest(args.manifest)
    review=json.loads(args.implementation_review.read_text(encoding='utf-8-sig'))
    reviewed=review.get('reviewed_manifest',{})
    if (review.get('all_passed') is not True or Path(reviewed.get('path','')).resolve()!=args.manifest.resolve()
            or reviewed.get('sha256')!=reference(args.manifest)['sha256'] or not review.get('source_files')):
        raise ValueError('Require a passing implementation review of this exact manifest')
    for row in review['source_files']:
        path=Path(row['path']);path=path if path.is_absolute() else runner.ROOT/path
        if reference(path)['sha256']!=row['sha256']:raise ValueError('Reviewed source changed: '+str(path))
    refs=[args.manifest,args.implementation_review,args.rubric,
          runner.ROOT/'research/v47_planner_executor_reference_20261018.json',
          runner.ROOT/'research/v46_feedback_diagnostic_round1_20261018.json',
          runner.ROOT/'research/v46_priority1_round2_20261018.json',
          runner.ROOT/'research/v46_priority1_round3_20261018.json',
          runner.ROOT/'data/sector_protocol/evaluation_spec.json',Path(__file__)]
    value={'protocol_version':'4.7','diagnostic_id':runner.DIAGNOSTIC_ID,
           'registered_at_utc':datetime.now(timezone.utc).isoformat(),
           'manifest':reference(args.manifest),'planned_generation_attempts':2,
           'automatic_retries':0,'main_model_calls':0,'main_freeze':False,
           'purpose':'Finite development diagnosis: model-authored plan then model-authored final allocation on a known failed case.',
           'budget':'Planner once, then executor once if planning output satisfies its declared contract. No retry, A/C fallback, until-pass loop or favorable-output selection.',
           'planner':'Existing stage1 schema selector, exactly empty weights and future plan in narrative fields. Empty weights are a plan with no allocation, not a valid or invalid financial proposal.',
           'executor':'Reads the unmodified complete planning response and all new explicit history; constructs its own complete 11-weight response under the existing final schema.',
           'feedback':'Previous raw answer/calculation and exact v4.5-to-v4.6 weight deltas only. No target vector, suggested sector increase, normalization or host application of a plan.',
           'retention':'Preserve the v4.4/v4.5/v4.6 failures and every v4.7 outcome, including a planner contract failure preventing executor launch.',
           'three_reviews':[
               {'round':1,'scope':'Input/provenance/transport, raw planning and final outputs, complete history and two-call accounting.'},
               {'round':2,'scope':'Independent final raw arithmetic, actual changes, planning non-allocation distinction.'},
               {'round':3,'scope':'Truth of plan versus actual execution and prior-error/final-validity statements.'}],
           'limits':['Two-call scope and seven-key adaptation are not the paper optimal budget or exact PER reproduction.',
                     'Plan, prompt, feedback and compute change together; no isolated causal effect is identified.',
                     'The known development failure is not an untouched confirmation case.',
                     'Success does not certify the original four-stage R1/R4 workflow, market-number accuracy, institutional rationale, or general reliability.'],
           'later_steps':'Priority2/3 require the preceding gates; main execution remains prohibited under this request even after all gates pass.',
           'online_boundary':'Registration and offline review materials are not sent to the model.',
           'reference_files':[reference(x) for x in refs],
           'human_semantic_pass':False,'model_calls_by_registration':0}
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'registration':str(args.output),'sha256':reference(args.output)['sha256'],'model_calls':0}))


if __name__=='__main__':main()
