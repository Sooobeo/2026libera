"""Synthetic finalization/proof/rollback checks; never publish real results."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from research.v63 import finalize_experiment_report as f,longrun_guardian as g
from research.v63.test_longrun_guardian import approval_fixture,pilot_fixture,put


@pytest.fixture
def proofs_fixture(approval_fixture,monkeypatch):
    root,config_path,approval_path,approval,binding=approval_fixture
    config=g.read(config_path);run=binding['runtime_identity_sha256'];output=root/'outputs'
    original=pilot_fixture(root);directory=output/'guardian'/run;directory.mkdir(parents=True)
    pilot=put(directory/'pilot_precision_report.json',g.read(original))
    proof=g.read(original.with_suffix('.inputs.json'));proof['report']=g.file_ref(root,pilot)
    put(pilot.with_suffix('.inputs.json'),proof)
    measured=put(output/'phases'/run/'development-pilot/measurements.json',{'synthetic_test_fixture_only':True})
    monkeypatch.setattr(g,'check_phase_outputs',lambda *a,**kw:{'phase':a[3],'measurements':g.file_ref(root,measured),
        'mean_generation_requests':3,'mean_request_seconds':2})
    g.promote_main(root,config,approval,g.digest(approval_path),directory,pilot)
    monkeypatch.setattr(f,'ROOT',root);monkeypatch.setattr(f,'DATA',root/'data/v63_20261027')
    return root,config_path,approval_path,approval,output,run,directory


def test_main_completion_proof_check_is_read_only(proofs_fixture):
    root,config,path,a,output,run,directory=proofs_fixture
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=f.verify_main_completion_proofs(root,g.read(config),a,g.digest(path),output,run)
    assert set(result)=={'pilot_precision','pilot_inputs','main_freeze_transition','main_resource_review'}
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('name',['pilot_precision_report.json','pilot_precision_report.inputs.json',
    'main_freeze_transition.json','main_resource_review.json'])
def test_missing_completion_proof_never_changes_flags_or_publishes(proofs_fixture,monkeypatch,name):
    root,config,path,a,output,run,directory=proofs_fixture
    (directory/name).unlink();freeze=(root/'freeze.json').read_bytes()
    monkeypatch.setattr(g,'validate_approval',lambda *args,**kw:deepcopy(a))
    monkeypatch.setattr(f,'publish_validated_bundle',lambda *args:pytest.fail('Missing proof reached publication'))
    with pytest.raises((g.GuardianStop,OSError,ValueError)):
        f.finalize(output,run,config,path,g.digest(path))
    assert (root/'freeze.json').read_bytes()==freeze
    assert not (f.DATA/'final_results.json').exists()
    assert not (f.DATA/'continuation/live_status.json').exists()


@pytest.mark.parametrize('field,value',[('ready_for_precision_report',False),('synthetic_verification',True),
    ('main_N_fixed',59),('frozen_model_sha256','another-model'),('input_fingerprint','changed')])
def test_rehashed_bad_pilot_still_fails(proofs_fixture,field,value):
    root,config,path,a,output,run,directory=proofs_fixture
    pilot=directory/'pilot_precision_report.json';put(pilot,{**g.read(pilot),field:value})
    proof=directory/'pilot_precision_report.inputs.json';put(proof,{**g.read(proof),'report':g.file_ref(root,pilot)})
    with pytest.raises(g.GuardianStop):f.verify_main_completion_proofs(root,g.read(config),a,g.digest(path),output,run)


def test_main_resource_review_must_cover_every_phase_and_forbid_effect_selection(proofs_fixture):
    root,config,path,a,output,run,directory=proofs_fixture
    review=directory/'main_resource_review.json';transition=directory/'main_freeze_transition.json'
    original=g.read(review)
    for change in [{'phase_forecasts':{}},{'effect_or_pvalue_read_for_decision':True}]:
        put(review,{**original,**change});put(transition,{**g.read(transition),'resource_review':g.file_ref(root,review)})
        with pytest.raises(g.GuardianStop):f.verify_main_completion_proofs(root,g.read(config),a,g.digest(path),output,run)


@pytest.fixture
def publish_fixture(tmp_path,monkeypatch):
    root=tmp_path/'synthetic_publish_workspace';root.mkdir();data=root/'data/v63_20261027'
    monkeypatch.setattr(f,'ROOT',root);monkeypatch.setattr(f,'DATA',data)
    output=root/'outputs';run='synthetic-report-run'
    aliases=[root/'실험참고자료_20261027/03_최종실험결과_20261027.html',data/'final_results.json',data/'continuation/live_status.json',
        root/'실험참고자료_20261027/02_계속실행기록_20261027.html',data/'execution_status.json',data/'artifact_manifest.json']
    for path in aliases:path.parent.mkdir(parents=True,exist_ok=True)
    def render():
        # At first visible alias publication the immutable commit must exist.
        f.verify_completion_commit(g.read(data/'continuation/live_status.json'),root)
        aliases[3].parent.mkdir(parents=True,exist_ok=True);aliases[3].write_text('synthetic continuation',encoding='utf-8')
    def snapshot(*,status_override):
        f.verify_completion_commit(status_override,root)
        put(data/'execution_status.json',status_override);put(data/'artifact_manifest.json',{'synthetic_fixture_only':True})
    monkeypatch.setattr(f,'render_continuation',render);monkeypatch.setattr(f,'snapshot',snapshot)
    results={'status':'completed_real_experiments','run_id':run,'terminal_trajectories':3272,
        'planned_logical_stages':9816,'recorded_at_utc':'2026-10-27T00:00:00+00:00',
        'resource_approval':{'synthetic_fixture_only':True},'completion_proofs':{'synthetic_fixture_only':True}}
    summaries={'B-main':{'terminal_counts':{'completed':2400}}}
    return root,data,output,run,results,summaries,aliases


def test_valid_bundle_committed_before_any_complete_alias_and_tamper_detected(publish_fixture):
    root,data,output,run,results,summaries,aliases=publish_fixture
    result=f.publish_validated_bundle(output,run,results,'<html>synthetic fixture</html>',summaries)
    assert all(p.is_file() for p in aliases)
    commit=f.verify_completion_commit(g.read(data/'execution_status.json'),root)
    assert commit['run_id']==run and result['finalization_commit']['sha256']==g.digest(root/result['finalization_commit']['path'])
    report=root/commit['artifacts']['report']['path'];report.write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError):f.verify_completion_commit(g.read(data/'continuation/live_status.json'),root)


@pytest.mark.parametrize('prior_aliases',[False,True])
@pytest.mark.parametrize('failure',['stage_results','stage_commit','canonical_results','live','render','snapshot','final_verify'])
def test_publish_failure_restores_all_six_aliases_and_never_leaves_false_completion(publish_fixture,monkeypatch,prior_aliases,failure):
    root,data,output,run,results,summaries,aliases=publish_fixture
    if prior_aliases:
        for i,path in enumerate(aliases):put(path,{'previous_state':i,'all_experiments_completed':False})
    before={str(p):p.read_bytes() if p.exists() else None for p in aliases}
    original_write=f.write;raised=False
    def write(path,value):
        nonlocal raised
        path=Path(path)
        matches=((failure=='stage_results' and path.name=='results.json') or
                 (failure=='stage_commit' and path.name=='commit.json') or
                 (failure=='canonical_results' and path==data/'final_results.json') or
                 (failure=='live' and path==data/'continuation/live_status.json'))
        if matches and not raised:raised=True;raise OSError('Synthetic injected write failure')
        return original_write(path,value)
    monkeypatch.setattr(f,'write',write)
    original_render=f.render_continuation;original_snapshot=f.snapshot;original_verify=f.verify_completion_commit
    def render():
        original_render()
        if failure=='render':raise OSError('Synthetic continuation render failure after write')
    def snapshot(**kwargs):
        original_snapshot(**kwargs)
        if failure=='snapshot':raise OSError('Synthetic snapshot failure after writes')
    checks=0
    def verify(state,root):
        nonlocal checks
        checks+=1
        # Initial staging, render validation and snapshot validation pass;
        # fail only the post-publication execution_status verification.
        if failure=='final_verify' and checks==4:raise ValueError('Synthetic final verification failure')
        return original_verify(state,root)
    monkeypatch.setattr(f,'render_continuation',render);monkeypatch.setattr(f,'snapshot',snapshot)
    monkeypatch.setattr(f,'verify_completion_commit',verify)
    with pytest.raises((OSError,ValueError)):
        f.publish_validated_bundle(output,run,results,'<html>synthetic fixture</html>',summaries)
    if failure in {'stage_results','stage_commit','canonical_results','live'}:assert raised
    assert before=={str(p):p.read_bytes() if p.exists() else None for p in aliases}
    if failure not in {'stage_results','stage_commit'}:
        receipts=list((output/'finalization'/run).glob('*/publication_receipt.json'))
        assert len(receipts)==1
        receipt=g.read(receipts[0]);assert receipt['status']=='publication_failed_prior_aliases_restored'
        assert not receipt['rollback_errors']
        assert g.read(receipts[0].parent/'commit.json')['status']=='validated_complete_run'


@pytest.mark.parametrize('change',[{'run_id':'other'},{'status':'pilot_not_ready'},{'terminal_trajectories':3271}])
def test_incomplete_bundle_is_rejected_before_aliases(publish_fixture,change):
    root,data,output,run,results,summaries,aliases=publish_fixture
    with pytest.raises(g.GuardianStop):f.publish_validated_bundle(output,run,{**results,**change},'synthetic',summaries)
    assert not any(path.exists() for path in aliases)
