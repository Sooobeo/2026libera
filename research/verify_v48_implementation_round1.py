"""Capture offline integration tests and bind checks to an exact pilot manifest."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import copy
import tempfile
from unittest.mock import patch
import run_sector_v48 as runner


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--legacy-investigation')
    args=parser.parse_args();manifest_path=Path(args.manifest).resolve();out=Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest,runtime,contract,registry,market=runner.verify_manifest(manifest_path)
    checks=[]
    def check(name,passed,evidence): checks.append({'id':name,'passed':bool(passed),'evidence':evidence})
    modules=['test_sector_v48_contract','test_sector_v48_transport','test_evaluate_sector_v48','test_run_sector_v48',
             'test_sector_engine','test_compact_sector_prompt','test_evaluate_sector_v48_artifacts']
    cmd=[sys.executable,'-B','-X','utf8','-m','unittest','-v',*modules]
    result=subprocess.run(cmd,cwd=runner.ROOT/'research',capture_output=True)
    (out/'tests.stdout.txt').write_bytes(result.stdout);(out/'tests.stderr.txt').write_bytes(result.stderr)
    runner.save(out/'test_invocation.json',{'argv':cmd,'cwd':str(runner.ROOT/'research'),'returncode':result.returncode,
                                         'model_calls':0,'description':'Offline/fake HTTP unit and integration tests only'})
    check('offline_test_suite',result.returncode==0,runner.ref(out/'tests.stderr.txt'))
    if args.legacy_investigation:
        investigation=runner.read(args.legacy_investigation)
        check('legacy_failure_disposition_recorded',bool(investigation),runner.ref(args.legacy_investigation))
    check('exact_pilot_roster_and_budget',len(manifest['roster'])==4 and manifest['planned_core_calls']==16 and manifest['maximum_auxiliary_calls']==8,manifest['roster'])
    check('main_not_authorized',manifest['main_authorized'] is False,{'scope':manifest['scope']})
    for case in runner.ROSTER:
        packet=runner.read(manifest_path.parent/'packets'/f'{case["source_id"]}.json')
        for stage in range(1,5):
            payload=runner.stage_payload(stage,case['arm'],packet,market,registry)
            exposed='institution_document' in payload
            check(case['case_id']+f'_stage{stage}_source_onset',exposed==(stage==(1 if case['arm']=='R1' else 4)),
                  {'packet_supplied_this_stage':exposed,'source_retained_in_previous_messages':case['arm']=='R1' and stage>1})
            if case['arm']=='R4' and stage<4:
                check(case['case_id']+f'_stage{stage}_assigned_source_absent',packet['source_id'] not in runner.canonical(payload),
                      'Checks assigned identity; common baseline provenance remains the same across all cases.')
    # A forged current design reference must be rejected, even if the input and
    # executable software snapshots themselves have not changed.
    forged=copy.deepcopy(manifest);forged['design_references'][0]['sha256']='0'*64
    original_read=runner.read
    def read_with_forgery(path):
        return forged if Path(path).resolve()==manifest_path else original_read(path)
    rejected=False
    with patch.object(runner,'read',side_effect=read_with_forgery):
        try: runner.verify_manifest(manifest_path)
        except ValueError as exc: rejected='design reference changed' in str(exc)
    check('design_hash_tamper_rejected',rejected,'Negative check of manifest verification; no files modified.')
    # Verify the gate cannot be satisfied by an unbound PASS-only note.
    with tempfile.TemporaryDirectory() as tmp:
        notes=[]
        for n in (1,2,3):
            p=Path(tmp)/f'review{n}.json';runner.save(p,{'status':'PASS','round':n,'manifest_sha256':runner.sha(manifest_path),'reviewed_files':[]});notes.append(p)
        rejected=False
        try: runner.register(manifest_path,notes,Path(tmp)/'registration.json')
        except ValueError as exc: rejected='complete executable software inventory' in str(exc)
        check('empty_review_inventory_rejected',rejected,'No registration or model request produced.')
    check('paper_numeric_basis_retained',runner.sha(runner.ROOT/'research/v48_parameter_reference_addendum_20261018.json')=='37af0008222199720a65483512b32ed08292f21be18ea610d63d258dbcb5d474',
          '60-day/252/distance/8192/seed/thinking paper provenance unchanged; engineering controls explicitly separated.')
    check('topic_design_retained',runner.sha(runner.ROOT/'research/v48_topic_alignment_basis_20261018.json')=='6f8057c99a160a2b481b1394aa65569cd27eb9f42a0857169f1e1f1caec1ae28',
          'Published judgment -> evidence-linked rationale -> actual raw allocation; no private strategy or causal homogenization claim.')
    status='PASS' if all(x['passed'] for x in checks) else 'FAIL'
    report={'round':1,'status':status,'created_at_utc':runner.now(),'manifest_sha256':runner.sha(manifest_path),
            'reviewer':'root AI implementation/integration review, not independent human review',
            'reviewed_files':[runner.ref(runner.ROOT/'research'/x) for x in runner.SOFTWARE],
            'offline_reviewed_files':[runner.ref(runner.ROOT/'research'/x) for x in ['evaluate_sector_v48.py',* [m+'.py' for m in modules]]],
            'checks':checks,'topic_alignment':{'core':'Trace source judgments through reasons into raw C0 sector weights.',
                'arithmetic_scope':'Feasibility and calculation only; not strategic judgment success.',
                'semantic_review':'Literal passages and rationales retained; human judgments still pending.',
                'limits':'One model, two public pilot documents, bundled R1/R4 timing/use intervention; descriptive pilot.'},
            'model_calls':0,'main_frozen':False,'human_review_completed':False}
    report['test_scope']={'included':'New v4.8 executable/evaluation path plus shared arithmetic and lossless projection regressions.',
        'earlier_expanded_suite':'research/evidence/v48_implementation_20261018/round1.json',
        'legacy_workflow_exclusion':'local_sector_structured_case.py is not imported or executed by v4.8. Its historical cancellation failure remains FAIL; this report does not certify that retired workflow. Shared cancellation artifact handling in the new path is covered by explicit new tests.',
        'legacy_investigation':runner.ref(args.legacy_investigation) if args.legacy_investigation else None}
    runner.save(out/'round1.json',report)
    print(json.dumps({'status':status,'checks':len(checks),'passed':sum(x['passed'] for x in checks),'report':str(out/'round1.json')}))
    return 0 if status=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
