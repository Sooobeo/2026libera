"""Seal three design-review rounds and append the forward-only redesign decision."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from research_progress_log import ROOT, LEDGER, append, read_verified
from render_research_progress import render

HANDOFF='research/v48_handoff_20261018.json'
REPORTS=[
    'research/v48_design_round1_final_20261018.json',
    'research/v48_design_round2_sources_20261018.json',
    'research/v48_design_round2_methods_20261018.json',
    'research/v48_design_round3_20261018.json',
]


def read(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))
def ref(path): return {'path':path,'sha256':sha256((ROOT/path).read_bytes()).hexdigest()}


def main():
    events=read_verified()
    existing=[e for e in events if e['phase']=='redesign_v48' and e['status']=='design_verified']
    if existing:
        for item in existing[-1]['reference_files']:
            if ref(item['path'])!=item: raise ValueError('Previously delivered file changed: '+item['path'])
        print(json.dumps({'status':'already_recorded','sequence':existing[-1]['sequence']}))
        return
    reports=[read(p) for p in REPORTS]
    roster=reports[0]['inputs']
    for report in reports:
        if report['status']!='PASS': raise ValueError('Review did not pass')
        if report['inputs']!=roster: raise ValueError('Reviews do not cover identical artifacts')
        for item in report['inputs']:
            if ref(item['path'])!=item: raise ValueError('Reviewed file changed: '+item['path'])
    if {reports[0]['round'],reports[1]['round'],reports[2]['round'],reports[3]['round']}!={1,2,3}:
        raise ValueError('Expected three rounds, with two complementary second-round reports')
    config=read('plan/LIBERA_실험설정_v4.8_20261018.json')
    if config['current_execution']['v48_model_calls']!=0 or config['current_execution']['main_frozen']:
        raise ValueError('Wrong delivery scope')
    snapshot='research/evidence/v48_handoff_20261018/progress_before_redesign.jsonl'
    dest=ROOT/snapshot;dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and dest.read_bytes()!=LEDGER.read_bytes(): raise ValueError('Snapshot already exists with different history')
    dest.write_bytes(LEDGER.read_bytes())
    handoff={
        'version':'4.8','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'redesign_three_review_rounds_passed_runtime_preparation_pending',
        'delivered_artifacts':roster,
        'reviews':[{'round':r['round'],'report':ref(p),'status':r['status'],
                    'check_count':r.get('check_count'),'pass_count':r.get('pass_count')}
                   for p,r in zip(REPORTS,reports)],
        'review_scope':'Three self-review rounds: offline consistency; primary-source and evaluation methods; topic/logical alignment. Not independent human review, model performance acceptance, runtime certification or main freeze.',
        'forward_only_amendment':{
            'previous_model_success_gate':'v4.7 arithmetic-success prerequisite',
            'superseded_for_future_design':True,
            'new_gate':'Measurement/contract/provenance validity; model arithmetic and semantic errors are recorded outcomes.',
            'primary':'Each four-stage case first final C0; no replacement by repaired output.',
            'auxiliary':'At most C1/C2 arithmetic revisions for eligible complete vectors; common bounded policy, not equal realized calls.',
            'historical_failures_reclassified_as_pass':False,
            'insufficient_allocation_data':'No valid C0 pairs means no observed allocation-contrast result; readable explanations do not complete that missing research component.'},
        'current_execution':config['current_execution'],
        'next_steps':config['main']['pending'],
        'pre_delivery_ledger':{'snapshot':ref(snapshot),'events':len(events),
                               'last_event_sha256':events[-1]['event_sha256']},
        'recording_tools':[ref('research/record_v48_handoff.py'),ref('research/render_research_progress.py')],
        'initial_draft_audit':{'path':'research/v48_design_round1_20261018.json',
                                'scope':'Earlier 346-check draft before the parameter-addendum cross-link; final input version is the 350-check round1_final report.'},
        'main_execution_allowed_by_this_delivery':False,
    }
    (ROOT/HANDOFF).write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    event=append('redesign_v48','design_verified',
        '사용자의 재설계 지시에 따라 기관의 공개 판단→근거→실제 산업 배분을 중심으로 v4.8 계획·소논문·평가명세를 작성했다. 세 차례 자체 설계 검증을 완료했다. 앞으로의 준비 게이트는 측정·계약·기록의 정확성으로 구분하며 기존 v4.5–4.7 산술 실패를 소급 통과시키지 않는다. 4단계 C0가 주결과이고 최대 두 번의 사후 산술 수정은 보조 결과다. v4.8 모델 호출과 본실험은 0건이며 실행기 통합·전체 예비실험·독립 사람 검토·동결은 남아 있다. 이 사건은 완료 후 실제 기록 시각으로 남긴다.',
        [ROOT/HANDOFF]+[ROOT/p for p in REPORTS]+[ROOT/item['path'] for item in roster]+[ROOT/'research/render_research_progress.py'])
    render()
    verified=read_verified()
    checks={
        'three_rounds_present':{r['round'] for r in reports}=={1,2,3},
        'all_reviews_pass':all(r['status']=='PASS' for r in reports),
        'reviewed_hashes_unchanged':all(ref(x['path'])==x for x in roster),
        'new_event_references_match':all(ref(x['path'])==x for x in event['reference_files']),
        'ledger_append_preserved_prefix':LEDGER.read_bytes().startswith(dest.read_bytes()),
        'ledger_valid':verified[-1]==event,
        'historical_failure_preserved':handoff['forward_only_amendment']['historical_failures_reclassified_as_pass'] is False,
        'no_new_execution':config['current_execution']['v48_model_calls']==0,
        'no_main_freeze':config['current_execution']['main_frozen'] is False,
    }
    validation={'status':'PASS' if all(checks.values()) else 'FAIL',
                'created_at_utc':datetime.now(timezone.utc).isoformat(),
                'scope':'Handoff/ledger integrity only; not a fourth scientific review.',
                'handoff':ref(HANDOFF),'ledger_event':event['event_sha256'],
                'checks':checks,'event_sequence':event['sequence']}
    (ROOT/'research/v48_handoff_validation_20261018.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':validation['status'],'handoff':HANDOFF,'event_sequence':event['sequence'],'review_rounds':3,'model_calls':0},ensure_ascii=False))
    if not all(checks.values()): raise SystemExit(1)


if __name__=='__main__': main()
