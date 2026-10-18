"""v4.7: one model-authored plan, then one model-authored allocation.

Prepare is offline. Only run contacts the service. Existing v4.4--v4.6 sources
and records are immutable. The old supervised worker is reused without mutation.
The planner's empty weights are a planning contract, never an invalid portfolio.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time

import local_sector_feedback_diagnostic as prior

transport, base, remote, bench, workflow = prior.transport, prior.base, prior.remote, prior.bench, prior.workflow
ROOT = prior.ROOT
PROTOCOL = '4.7'
DIAGNOSTIC_ID = 'fidelity_q2_2026__v46_plan_execute_revision'
V46_MANIFEST = ROOT / 'data/sector_protocol/v46_feedback_diagnostic_20261018/manifest.json'
V46_MANIFEST_SHA = '7be29c06056d0f909d66ee992d93ce3830b544b4d9cf331ede6c636edc1b35ec'
V46_RUN = ROOT / 'data/local_sector_runtime/feedback_diagnostic_v46_20261018'
SOURCE_PINS = {
    'summary.json': '045f3b55fde038975b2fdce144687a9b13dffd0ca816754a585a2d8852fb25e7',
    'revision_record.json': '5878882798e72b1284383b195ce11a78a26fbdce07f3346d1f6490ea19d04339',
    'revision_transport/http_0001_generation/response.json': 'e0d2cf4914aa2d0f142bda4dea9ab59fbb9ee3cf93aa71896c1a6220f2f0d595',
}
REFERENCE_SHA = '5e86ac4bf264aab67e9fbec7a58d0e81aaaad71b2e83008501a6f8443cf4ba48'
SOFTWARE = prior.SOFTWARE + ('local_sector_plan_execute_diagnostic.py',)
INPUTS = ('runtime.json', 'model_packet.json', 'market_input.json', 'prior_response.json',
          'prior_record.json', 'prior_delta_feedback.json', 'prior_feedback_message.json',
          'planner_logical_messages.json', 'planner_authoritative_body.json',
          'schema_planner.json', 'schema_executor.json')
PLANNER_TASK = (
    'This is the planning call of a separate two-call development diagnostic, not a four-stage run. '
    'The original public task, institution document and market data appear in the first user message. '
    'The preceding assistant message is the complete preserved v4.6 candidate. Its actual calculator '
    'result is repeated unchanged below. delta_feedback contains only measured changes between the '
    'preserved v4.5 and v4.6 submitted weights; it supplies no correct sector allocation. Intermediate '
    'assistant responses from the old four-stage case are not included. '
    'Write a concrete prospective plan for responding to the reported allocation errors. Choose your '
    'own intended changes and explain how the subsequent executor should check them against the '
    'existing nonnegative, complete-11-sector, sum-to-one conditions. Put the future plan in '
    'alternatives and risk_discussion. Do not execute the plan or produce a final 11-sector weight '
    'vector in this planning response. The weights field must be exactly []. Keep the existing seven '
    'top-level fields and the original source rating vocabulary. Do not state that a planned change '
    'has already happened. A plan is not evidence that any allocation is valid. Disclose unresolved '
    'issues in unresolved. Do not replace the calculator result or normalize a vector externally. '
    'Do not attribute an unsupported institutional mandate, target weight, risk preference or '
    'sector limit to the source. '
    'The scope is calculator-feedback reconciliation only; no separate market-number correction '
    'or source-rationale enrichment program is introduced. Those aspects remain unassessed.'
)
EXECUTOR_TASK = (
    'This is the execution call of the same separate two-call development diagnostic. The immediately '
    'preceding assistant message is your complete plan, not a validated allocation. Read that plan '
    'together with the original public task and the actual earlier calculator/delta feedback. '
    'Now determine and write the complete 11-sector weights yourself, using the plan where justified '
    'and checking the existing allocation conditions. No host has applied or completed your plan. '
    'Return all seven existing fields with actual weights, not merely a description of intended changes. '
    'Explain actual revisions in risk_discussion and disclose remaining issues in unresolved. '
    'Do not claim that the old invalid candidate was valid or that changes occurred unless your '
    'submitted numbers show them. Your claim of validity is not acceptance: the new raw vector will '
    'be calculated again without normalization, clipping or cash insertion. '
    'market_diagnostics.status concerns market-input checks; null risk or baseline results are not '
    'completed portfolio checks. The scope remains allocation/feedback reconciliation, not separate '
    'market-number verification, source-rationale enrichment or the main R1/R4 comparison.'
)


def reference_records(path):
    path = Path(path).resolve()
    if 'evaluator_only' in path.parts or remote.sha(path) != REFERENCE_SHA:
        raise ValueError('Require the immutable planner/executor reference package')
    value = remote.read(path)
    if value['protocol_version'] != PROTOCOL or value['change_scope'] != 'two_call_model_authored_plan_then_model_authored_full_response_with_actual_feedback':
        raise ValueError('Unexpected planner/executor reference scope')
    rows = [prior.sha_record(path)]
    for row in [value[k] for k in ('comparison_memo', 'inherited_conditions', 'renderer_policy', 'previous_schema_evidence')] + value['primary_sources']:
        p = (ROOT / row['path']).resolve()
        if 'evaluator_only' in p.parts or remote.sha(p) != row['sha256']:
            raise ValueError('Reference source changed: ' + str(p))
        rows.append(prior.sha_record(p))
    return rows


def original_inputs():
    if remote.sha(V46_MANIFEST) != V46_MANIFEST_SHA:
        raise ValueError('The previous one-call preparation changed')
    prior.verify_manifest(V46_MANIFEST)
    runtime, packet, market, public, _, v45_record, v45_sources = prior.original_inputs()
    sources = []
    for name, digest in SOURCE_PINS.items():
        path = V46_RUN / name
        if remote.sha(path) != digest: raise ValueError('Preserved v4.6 artifact changed: ' + name)
        sources.append(prior.sha_record(path))
    response = remote.read(V46_RUN / 'revision_transport/http_0001_generation/response.json')
    record = remote.read(V46_RUN / 'revision_record.json')
    parsed = prior.parse_response(response['message']['content'])
    if not parsed['ok'] or parsed['value'] != record['raw_proposal'] or response['done_reason'] != 'stop' or record['repair_applied'] is not False:
        raise ValueError('Previous revision is not the complete unrepaired raw candidate')
    calc = prior.calculate_portfolio(record['raw_proposal']['weights'], market=market,
        visible_evidence_ids=workflow.evidence_ids(packet),
        submitted_constraints=record['raw_proposal']['submitted_constraints'])
    if calc != record['calculator_result'] or calc['allocation']['valid'] is not False:
        raise ValueError('The selected v4.6 candidate must retain its actual failed calculation')
    delta = delta_feedback(v45_record, record)
    return runtime, packet, market, public, response, record, delta, sources, v45_sources


def delta_feedback(old_record, new_record):
    def weights(record):
        rows = record['raw_proposal']['weights']; codes = [r['sector_code'] for r in rows]
        if len(codes) != 11 or set(codes) != set(prior.market_codes()) or len(set(codes)) != 11:
            raise ValueError('Cannot silently resolve duplicate or missing comparison rows')
        return {r['sector_code']: r['weight'] for r in rows}
    old, new = weights(old_record), weights(new_record)
    return {'comparison': 'preserved_v45_final_to_preserved_v46_revision',
        'rows': [{'sector_code': c, 'old_weight': old[c], 'new_weight': new[c],
                  'delta': float(Decimal(str(new[c])) - Decimal(str(old[c])))} for c in prior.market_codes()],
        'old_raw_sum': old_record['calculator_result']['allocation']['raw_sum'],
        'new_raw_sum': new_record['calculator_result']['allocation']['raw_sum'],
        'old_raw_budget_residual': old_record['calculator_result']['allocation']['raw_budget_residual'],
        'new_raw_budget_residual': new_record['calculator_result']['allocation']['raw_budget_residual'],
        'scope': 'observed_numeric_difference_only_no_target_vector_or_semantic_judgment'}


def planner_messages(public, response, record, delta):
    feedback = record['calculator_result']
    task = {'stage': 1, 'diagnostic_id': DIAGNOSTIC_ID, 'role_in_diagnostic': 'planner',
        'stage_field_role': 'existing_schema_selector_not_a_workflow_stage', 'task': PLANNER_TASK,
        'calculator_feedback': copy.deepcopy(feedback), 'delta_feedback': copy.deepcopy(delta),
        'required_planner_weights': [], 'response_schema': transport.response_schema(1),
        'response_contract_instruction': transport.CONTRACT_INSTRUCTION}
    return copy.deepcopy(public) + [{'role': 'assistant', 'content': response['message']['content']},
        {'role': 'user', 'content': json.dumps({'calculator_feedback': feedback}, ensure_ascii=False, allow_nan=False)},
        {'role': 'user', 'content': json.dumps(task, ensure_ascii=False, allow_nan=False)}]


def executor_messages(messages, plan_response):
    task = {'stage': 4, 'diagnostic_id': DIAGNOSTIC_ID, 'role_in_diagnostic': 'executor',
        'stage_field_role': 'existing_schema_selector_not_a_workflow_stage', 'task': EXECUTOR_TASK,
        'response_schema': transport.response_schema(4),
        'response_contract_instruction': transport.CONTRACT_INSTRUCTION}
    return copy.deepcopy(messages) + [{'role': 'assistant', 'content': plan_response['message']['content']},
        {'role': 'user', 'content': json.dumps(task, ensure_ascii=False, allow_nan=False)}]


def request_body(messages, role):
    selector = {'planner': 1, 'executor': 4}[role]
    if json.loads(messages[-1]['content'])['stage'] != selector:
        raise ValueError('Unexpected diagnostic role/schema selector')
    body = base.prepare_body(messages, base.runtime_v44())
    body['format'] = transport.response_schema(selector)
    if body['messages'][2:] != messages[2:] or {k:v for k,v in body.items() if k != 'messages'} != transport.request_header(transport.runtime_v45(), selector):
        raise ValueError('Input strings or inherited numerical request settings changed')
    return body


def prepared_values(runtime, packet, market, public, response, record, delta):
    messages = planner_messages(public, response, record, delta)
    return {'runtime.json': runtime, 'model_packet.json': packet, 'market_input.json': market,
        'prior_response.json': response, 'prior_record.json': record, 'prior_delta_feedback.json': delta,
        'prior_feedback_message.json': messages[3], 'planner_logical_messages.json': messages,
        'planner_authoritative_body.json': request_body(messages, 'planner'),
        'schema_planner.json': transport.response_schema(1), 'schema_executor.json': transport.response_schema(4)}


def prepare(args):
    runtime, packet, market, public, response, record, delta, sources, v45_sources = original_inputs()
    refs = reference_records(args.revision_evidence)
    values = prepared_values(runtime, packet, market, public, response, record, delta)
    target = Path(args.output).resolve(); target.mkdir(parents=True, exist_ok=False)
    for name, value in values.items(): remote.save(target/name, value)
    manifest = dict(protocol_version=PROTOCOL, diagnostic_id=DIAGNOSTIC_ID, created_at_utc=remote.now(),
        planned_generation_attempts=2, planned_roles=['planner','executor'], automatic_retries=0,
        main_model_calls=0, main_freeze=False, human_semantic_pass=False,
        scope='two_call_development_plan_then_execute_on_preserved_v46_failure',
        selection='The prior failed development candidate is deliberately selected; not an independent sample.',
        call_count_basis='One planning call and one execution call are a local bounded adaptation, not a paper-derived optimum.',
        parent_preparation=prior.sha_record(V46_MANIFEST), original_sources=sources, v45_sources=v45_sources,
        revision_evidence=refs, inputs={n:remote.sha(target/n) for n in INPUTS},
        software={n:remote.sha(ROOT/'research'/n) for n in SOFTWARE},
        controls={'planner_message_count':5, 'executor_message_count':7,
          'planner_contract':'Existing stage1 API schema plus parent requirement weights==[]; its empty array is a planning artifact, not a zero-sum portfolio. A full final vector in narrative remains a separate semantic contract to review.',
          'executor_contract':'Existing stage4 API schema with 11 weights; the model alone writes the allocation. The host never executes or fills in the plan.',
          'history':'Original SYSTEM/public stage1, complete v46 final answer, original calculator values, and measured v45-to-v46 deltas. Old intermediate assistant history is absent; new planner content is appended verbatim.',
          'feedback_serialization':'The v46 calculator_result is newly serialized into a user message; it was not sent after that previous diagnostic.',
          'transport':'Unchanged v45 supervised worker, model/options/pins/rendering/monitoring. Stage1/stage4 select schemas only, not actual original workflow stages.',
          'deadline':'Each supervised child has the existing 900-second combined setup/metadata/render/generation bound. Cleanup and OS kill/scheduling overhead are outside.',
          'legacy_worker_counts':'Each reused worker labels its call pilot_model_calls; this parent counts only diagnostic_generation_calls, with four_stage_pilot_calls=main_model_calls=0.',
          'stopping':'No retry or replacement. Invalid planner weights preserve the raw plan and stop before executor; incomplete/capped/failed calls retain raw evidence.',
          'interpretation':'Plan prompting, an additional call and new context arrangement change together; success identifies none of their separate causal effects or original R1/R4 repair.',
          'assessment':'Numeric acceptance does not approve priority1, semantics, later priorities or main execution; three independent checks remain required.'})
    remote.save(target/'manifest.json', manifest)
    print(json.dumps({'manifest':str(target/'manifest.json'),'sha256':remote.sha(target/'manifest.json'),'model_calls':0}), flush=True)
    return 0


def verify_manifest(path):
    path = Path(path).resolve(); m = remote.read(path)
    if (m.get('protocol_version') != PROTOCOL or m.get('diagnostic_id') != DIAGNOSTIC_ID or
            m.get('planned_generation_attempts') != 2 or m.get('planned_roles') != ['planner','executor'] or
            m.get('automatic_retries') != 0 or m.get('main_model_calls') != 0 or
            m.get('main_freeze') is not False or m.get('human_semantic_pass') is not False):
        raise ValueError('Unexpected bounded diagnostic scope')
    if set(m['inputs']) != set(INPUTS) or set(m['software']) != set(SOFTWARE):
        raise ValueError('Incomplete artifact inventory')
    for name, digest in m['inputs'].items():
        if remote.sha(path.parent/name) != digest: raise ValueError('Prepared input changed: '+name)
    for name, digest in m['software'].items():
        if remote.sha(ROOT/'research'/name) != digest: raise ValueError('Prepared software changed: '+name)
    runtime, packet, market, public, response, record, delta, sources, v45_sources = original_inputs()
    if m['original_sources'] != sources or m['v45_sources'] != v45_sources or m['parent_preparation'] != prior.sha_record(V46_MANIFEST):
        raise ValueError('Preserved source provenance differs')
    if m['revision_evidence'] != reference_records(m['revision_evidence'][0]['path']):
        raise ValueError('Reference inventory differs')
    for name, value in prepared_values(runtime, packet, market, public, response, record, delta).items():
        if remote.read(path.parent/name) != value: raise ValueError('Prepared value differs: '+name)
    return m, runtime, packet, market, planner_messages(public, response, record, delta)


def verify_registration(path, manifest):
    r = remote.read(path)
    if (r.get('protocol_version') != PROTOCOL or r.get('diagnostic_id') != DIAGNOSTIC_ID or
            r.get('manifest') != prior.sha_record(manifest) or r.get('planned_generation_attempts') != 2 or
            r.get('automatic_retries') != 0 or r.get('main_model_calls') != 0 or r.get('main_freeze') is not False):
        raise ValueError('A separate registration must pin this two-call preparation')
    stamp = datetime.fromisoformat(r['registered_at_utc'].replace('Z','+00:00'))
    created = datetime.fromisoformat(remote.read(manifest)['created_at_utc'].replace('Z','+00:00'))
    if stamp.tzinfo is None or created.tzinfo is None or not created <= stamp <= datetime.now(timezone.utc):
        raise ValueError('Registration must follow preparation and precede execution')
    return r


def run(args):
    path = Path(args.manifest).resolve()
    manifest, runtime, packet, market, messages = verify_manifest(path)
    registration_path = Path(args.registration).resolve()
    registration = verify_registration(registration_path, path)
    origin = remote.validate_origin(args.base_url); server_log = Path(args.server_log).resolve()
    if not server_log.is_file(): raise ValueError('Existing owned service log required')
    target = remote.new_output(args.output_root,'plan_execute_diagnostic_v47',args.run_id)
    started = time.monotonic(); transports = []; active_role = 'preflight'
    summary = dict(status='not_started', protocol_version=PROTOCOL, diagnostic_id=DIAGNOSTIC_ID,
        planned_generation_attempts=2, automatic_retries=0, main_model_calls=0, four_stage_pilot_calls=0,
        main_freeze=False, human_semantic_pass=False, priority1_solved=False, numeric_acceptance=None,
        planner_completed=False, planner_contract_satisfied=None, executor_completed=False)
    frozen = {'manifest':prior.sha_record(path), 'registration':prior.sha_record(registration_path)}
    remote.save(target/'manifest_snapshot.json',manifest); remote.save(target/'registration_snapshot.json',registration)
    remote.save(target/'runtime.json',runtime)
    remote.save(target/'invocation.json',dict(started_at_utc=remote.now(),origin=origin,server_log=str(server_log),
        **frozen,controls=manifest['controls'],purpose=manifest['scope']))
    prior.append_event(target,'registered_diagnostic_started',**frozen)

    def call(role, logical, previous_body=None):
        if (target/'CANCEL').exists(): raise base.StageStopped('cancelled')
        verify_manifest(path); verify_registration(registration_path,path)
        if frozen != {'manifest':prior.sha_record(path),'registration':prior.sha_record(registration_path)}:
            raise ValueError('Registration or preparation changed')
        body = request_body(logical,role)
        if previous_body and body['messages'][:len(previous_body['messages'])] != previous_body['messages']:
            raise ValueError('Previously transmitted messages changed')
        folder = target/(role+'_transport'); folder.mkdir(); transports.append(folder)
        remote.save(folder/'logical_messages.json',logical); remote.save(folder/'authoritative_body.json',body)
        (folder/'authoritative_body.bin').write_bytes(json.dumps(body,ensure_ascii=False,allow_nan=False).encode())
        remote.save(folder/'response_schema.json',body['format'])
        before = server_log.read_bytes()
        remote.save(folder/'server_log_before.json',dict(path=str(server_log),bytes=len(before),sha256=hashlib.sha256(before).hexdigest()))
        spec = folder/'worker_spec.json'
        remote.save(spec,dict(origin=origin,body=body,deadline_seconds=runtime['deadline_seconds'],cancel_path=str(target/'CANCEL')))
        prior.append_event(target,'supervised_attempt_dispatched',role=role,body=prior.sha_record(folder/'authoritative_body.bin'))
        try:
            result = transport.supervise(spec,runtime['deadline_seconds'],target/'CANCEL')
        finally:
            clean = bench.unload_and_confirm(origin,base.MODEL); remote.save(folder/'unload_and_residency.json',clean)
            after = server_log.read_bytes(); (folder/'server_log_after_snapshot.bin').write_bytes(after)
            remote.save(folder/'server_log_delta.json',dict(original_prefix_retained=after.startswith(before),
                prior_bytes=len(before),after_bytes=len(after),sha256=hashlib.sha256(after).hexdigest()))
            prior.append_event(target,'cleanup_recorded',role=role,cleanup=prior.sha_record(folder/'unload_and_residency.json'))
        if clean['status'] != 'no_resident_models_observed': raise RuntimeError('Model unload/idle was not confirmed')
        if result['status'] != 'worker_exited': raise base.StageStopped(result['status'])
        status = result.get('worker',{}).get('status')
        if status != 'completed': raise base.StageStopped(status or 'worker_result_missing')
        response_path = folder/'http_0001_generation/response.json'; response = remote.read(response_path)
        parsed = prior.parse_response(response['message']['content'])
        if not parsed['ok']: raise ValueError('Invalid raw JSON; no host repair')
        return response, parsed['value'], body, response_path

    try:
        state = remote.api_json(origin,'/api/ps'); remote.save(target/'residency_before.json',state)
        if state.get('models') != []: raise ValueError('Existing model workload must be resolved by the operator')
        observed = bench.observe(origin,base.MODEL); remote.save(target/'initial_pin.json',observed); base.assert_pin(observed)
        active_role = 'planner'
        plan_response, plan, first_body, response_path = call('planner',messages)
        contract_ok = plan['weights'] == []
        remote.save(target/'plan_record.json',dict(raw_proposal=plan,planner_contract_satisfied=contract_ok,
            response_source=prior.sha_record(response_path),role='planner',repair_applied=False,
            arithmetic_status='not_applicable_to_plan_no_allocation_submitted' if contract_ok else 'not_evaluated_planner_contract_violated',
            financial_acceptance=None,calculator_called=False,
            narrative_no_final_vector_contract='pending_offline_semantic_review'))
        summary.update(planner_completed=True,planner_contract_satisfied=contract_ok)
        prior.append_event(target,'plan_recorded',record=prior.sha_record(target/'plan_record.json'),planner_contract_satisfied=contract_ok)
        if not contract_ok: raise base.StageStopped('planner_contract_failed')
        active_role = 'executor'
        full_messages = executor_messages(messages,plan_response)
        response, proposal, _, response_path = call('executor',full_messages,first_body)
        calc = prior.calculate_portfolio(proposal['weights'],market=market,
            visible_evidence_ids=workflow.evidence_ids(packet),submitted_constraints=proposal['submitted_constraints'])
        old = remote.read(path.parent/'prior_record.json')
        assessment = prior.numeric_assessment(calc,old['raw_proposal'],proposal)
        remote.save(target/'revision_record.json',dict(raw_proposal=proposal,
            calculator_arguments={'weights':proposal['weights'],'submitted_constraints':proposal['submitted_constraints']},
            calculator_result=calc,prior_calculator_result=old['calculator_result'],assessment=assessment,
            response_source=prior.sha_record(response_path),plan_source=prior.sha_record(target/'plan_record.json'),repair_applied=False))
        prior.append_event(target,'raw_revision_recalculated',record=prior.sha_record(target/'revision_record.json'))
        summary.update(status='completed_plan_execute_diagnostic',executor_completed=True,
            numeric_acceptance=assessment['numeric_acceptance'],weight_vector_changed=assessment['weight_vector_changed'],
            raw_sum=assessment['raw_sum'],raw_budget_residual=assessment['raw_budget_residual'])
    except BaseException as exc:
        summary.update(status='cancelled' if isinstance(exc,KeyboardInterrupt) else getattr(exc,'status','failed'),
            failed_role=active_role,error_type=type(exc).__name__,error=str(exc))
        remote.save(target/'failure.json',dict(type=type(exc).__name__,message=str(exc),role=active_role,
            handling='Preserve raw evidence and stop; no retry, replacement or host execution of the plan.'))
        prior.append_event(target,'diagnostic_stopped',status=summary['status'],role=active_role)
    finally:
        counts = {}
        for role in ('planner','executor'):
            folder = target/(role+'_transport'); result = folder/'http_0001_generation/result.json'; render = folder/'render_only/result.json'
            counts[role] = {'generation_requests_attempted':int((folder/'http_0001_generation/request.json').is_file()),
                'render_requests_attempted':int((folder/'render_only/request.json').is_file()),
                'http_streams_completed':int(result.is_file() and remote.read(result).get('status') == 'completed'),
                'unexpected_generation_evidence_in_render':bool(render.is_file() and remote.read(render).get('unexpected_generation_evidence'))}
        summary.update(finished_at_utc=remote.now(),wall_seconds=time.monotonic()-started,role_counts=counts,
            generation_requests_attempted=sum(c['generation_requests_attempted'] for c in counts.values()),
            diagnostic_generation_calls=sum(c['generation_requests_attempted'] for c in counts.values()),
            render_requests_attempted=sum(c['render_requests_attempted'] for c in counts.values()),
            http_streams_completed=sum(c['http_streams_completed'] for c in counts.values()),
            unexpected_generation_evidence_in_render=any(c['unexpected_generation_evidence_in_render'] for c in counts.values()),
            executor_not_started=counts['executor']['generation_requests_attempted']==0,
            semantic_validity_assessed=False,independent_reviews_completed=0,replaces_previous_failed_attempt=False,
            completion_scope='A registered budget of one planner call and one executor call; observed completion, plan contract, numeric acceptance and three independent reviews are separate.',
            reused_worker_count_scope=manifest['controls']['legacy_worker_counts'])
        remote.save(target/'summary.json',summary)
        prior.append_event(target,'diagnostic_finished',summary=prior.sha_record(target/'summary.json'))
    print(json.dumps({'output':str(target),**summary},ensure_ascii=False),flush=True)
    return 0 if summary['status']=='completed_plan_execute_diagnostic' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command',required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--revision-evidence',type=Path,required=True)
    runner = sub.add_parser('run'); runner.add_argument('--manifest',type=Path,required=True)
    runner.add_argument('--registration',type=Path,required=True); runner.add_argument('--base-url',default='http://127.0.0.1:11434')
    runner.add_argument('--server-log',type=Path,required=True)
    runner.add_argument('--output-root',type=Path,default=ROOT/'data/local_sector_runtime')
    runner.add_argument('--run-id',required=True); args = parser.parse_args(argv)
    return prepare(args) if args.command=='prepare' else run(args)


if __name__=='__main__':
    raise SystemExit(main())
