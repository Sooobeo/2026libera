"""Read cost metadata only; write new audit artifacts without changing the run."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = '2e51a74582f096f6ca806c7012dac05169e778bfc8701dae0ba9cbbeae9cdfb2'
BASE = ROOT / 'data/v63_20261027/local_campaign_results'
CUTOFF = '2026-10-27T13:35:00+00:00'
KST = timezone(timedelta(hours=9))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ref(path):
    path = Path(path)
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def stats(values):
    values = sorted(values)
    def quantile(probability):
        location = (len(values) - 1) * probability
        lower = int(location)
        return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (location - lower)
    return dict(n=len(values), sum=sum(values), mean=statistics.mean(values), minimum=min(values),
                p10=quantile(.10), p25=quantile(.25), median=quantile(.50), p75=quantile(.75),
                p90=quantile(.90), p95=quantile(.95), maximum=max(values))


rows = []
all_stage_files = []
for path in (BASE / 'runs' / RUN / 'B-development').glob('*/http/attempt_*/generation.receipt.json'):
    receipt = read(path)
    response_path = path.with_name('generation.response.bin')
    payload = response_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == receipt['response_sha256']
    response = json.loads(payload)
    # Never extract message content, weights, explanations, validity metrics or effects.
    start = datetime.fromisoformat(receipt['started_at_utc'])
    end = start + timedelta(seconds=receipt['elapsed_seconds'])
    row = dict(case=path.parents[2].name, attempt=path.parent.name,
               started_at_utc=start.isoformat(), ended_at_utc=end.isoformat(),
               http_seconds=receipt['elapsed_seconds'], http_status=receipt['http_status'],
               receipt=ref(path), response=ref(response_path))
    for key in ['prompt_eval_count', 'prompt_eval_cached_count', 'eval_count']:
        row[key] = response.get(key)
    for key in ['total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration']:
        row[key.replace('_duration', '_seconds')] = response.get(key, 0) / 1e9
    row['decode_tokens_per_second'] = row['eval_count'] / row['eval_seconds']
    rows.append(row)
rows.sort(key=lambda row: row['started_at_utc'])
assert len(rows) == 60
case_counts = Counter(row['case'] for row in rows)
assert len(case_counts) == 20 and set(case_counts.values()) == {3}
for case in case_counts:
    names = sorted(p.name for p in (BASE / 'runs' / RUN / 'B-development' / case / 'trajectory').glob('stage*_round*_request.json'))
    assert names == ['stage1_round0_request.json', 'stage2_round0_request.json', 'stage3_round0_request.json']
    all_stage_files.extend(names)


def summarize(subset):
    groups = defaultdict(list)
    for row in subset:
        groups[row['case']].append(row)
    complete_groups = [group for group in groups.values() if len(group) == 3]
    begin = min(datetime.fromisoformat(row['started_at_utc']) for row in subset)
    end = max(datetime.fromisoformat(row['ended_at_utc']) for row in subset)
    result = dict(requests=len(subset), first_dispatch_utc=begin.isoformat(), last_http_end_utc=end.isoformat(),
                  first_dispatch_kst=begin.astimezone(KST).isoformat(), last_http_end_kst=end.astimezone(KST).isoformat(),
                  elapsed_dispatch_to_last_receipt_seconds=(end - begin).total_seconds(),
                  http_status_counts=dict(Counter(row['http_status'] for row in subset)),
                  complete_trajectories=len(complete_groups))
    for field in ['http_seconds', 'prompt_eval_count', 'prompt_eval_cached_count', 'eval_count',
                  'load_seconds', 'prompt_eval_seconds', 'eval_seconds', 'decode_tokens_per_second']:
        result[field] = stats([row[field] for row in subset])
    result['provider_aggregate_decode_tokens_per_second'] = sum(row['eval_count'] for row in subset) / sum(row['eval_seconds'] for row in subset)
    result['uncached_prompt_tokens'] = sum(row['prompt_eval_count'] - row['prompt_eval_cached_count'] for row in subset)
    result['complete_trajectory_http_seconds'] = stats([sum(row['http_seconds'] for row in group) for group in complete_groups])
    result['complete_trajectory_wall_seconds'] = stats([
        (max(datetime.fromisoformat(row['ended_at_utc']) for row in group) -
         min(datetime.fromisoformat(row['started_at_utc']) for row in group)).total_seconds()
        for group in complete_groups])
    return result


post = [row for row in rows if row['started_at_utc'] >= CUTOFF]
all_summary, post_summary = summarize(rows), summarize(post)
phases = BASE / 'phases' / RUN
paired_path, smoke_path = phases / 'paired-feasibility/measurements.json', phases / 'technical-smoke/measurements.json'
paired, smoke = read(paired_path), read(smoke_path)
assert paired['all_attempt_costs']['generation_requests'] == len(rows)
assert paired['all_attempt_costs']['prompt_tokens'] == sum(row['prompt_eval_count'] for row in rows)
assert paired['all_attempt_costs']['generated_tokens'] == sum(row['eval_count'] for row in rows)
smoke_budget = read(phases / 'technical-smoke/budget_state.json')
wall_start = datetime.fromisoformat(smoke_budget['first_started_at_utc'])
wall_end = datetime.fromisoformat(paired['recorded_at_utc'])
historical_path = ROOT / 'research/device_migration_20261027/followup_20261027/candidate005_historical_costs.json'
historical = read(historical_path)

memory_path = ROOT / 'data/v63_20261027/runtime/local_windows/candidate005_development_20261027T100125587Z/memory_observations.jsonl'
memory_summary_path = memory_path.with_name('memory_summary.json')
memory = [json.loads(line.lstrip('\ufeff')) for line in memory_path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def memory_stats(items):
    return dict(samples=len(items),
                available_physical_GiB=stats([r['memory']['FreePhysicalMemory'] / 1024**2 for r in items]),
                observed_process_combined_working_set_GiB=stats([r['combined_working_set_bytes'] / 1024**3 for r in items]))


capacity_path = ROOT / 'research/device_migration_20261027/input_capacity.json'
tokenizer_path = ROOT / 'data/v63_20261027/continuation/deployment/local_windows/candidate_005/tokenizer_config.json'
capacity, tokenizer = read(capacity_path), read(tokenizer_path)
tokenizer_matches = capacity['tokenizer_identity'] == 'native:' + tokenizer['gguf_sha256'] + ':' + tokenizer['model_sha256']
capacity_rows = [{key: row[key] for key in ['fund_id', 'period', 'case', 'baseline_tokens', 'packet_tokens', 'full_tokens'] if key in row}
                 for row in capacity['rows']]

mean_seconds = post_summary['complete_trajectory_wall_seconds']['mean']
p90_seconds = post_summary['complete_trajectory_wall_seconds']['p90']
forecasts = []
for category, counts, overhead_range, long_context_factor in [
    ('same_B_workload', [30, 60, 120], [1.0, 4.0], 1.0),
    ('actual_document_workload_unmeasured', [20, 40], [1.5, 6.0], 1.5)
]:
    for count in counts:
        center = count * mean_seconds / 3600
        high = count * p90_seconds * 1.20 * long_context_factor / 3600
        forecasts.append(dict(category=category, future_trajectories=count, nominal_generation_calls=count * 3,
                              same_shape_runtime_center_hours=center,
                              runtime_planning_range_hours=[center, high],
                              preparation_and_analysis_allowance_hours=overhead_range,
                              end_to_end_planning_range_hours=[center + overhead_range[0], high + overhead_range[1]],
                              additional_generation_tokens_at_observed_post_mean=count * 3 * post_summary['eval_count']['mean']))

report = dict(
    schema='libera_reduced_workload_measured_cost_review_v1', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    run_id=RUN, read_only_scope='Only timing, token, memory, runtime identity and input-capacity metadata; no portfolio content, effects or p-values extracted. No model calls, configuration, service or accounting changes.',
    all_60_http=all_summary,
    after_power_fix=dict(cutoff_utc=CUTOFF, criterion='HTTP dispatch started at or after cutoff; boundary-straddling request excluded only from future-rate estimator, never from cost ledger.',
                         summary=post_summary, request_count_before_cutoff=len(rows)-len(post),
                         first_half_mean_http_seconds=statistics.mean(r['http_seconds'] for r in post[:len(post)//2]),
                         second_half_mean_http_seconds=statistics.mean(r['http_seconds'] for r in post[len(post)//2:])),
    measured_request_shape=dict(trajectories=20, logical_stages=60, generation_requests=60, calls_per_trajectory=3,
                                additional_tool_round_requests=0, note='Every trajectory has stage1/2/3 round0 request files. This is the observed shape, not a guarantee for changed protocols or future tool calls.'),
    authoritative_costs_preserved=dict(
        paired_measurements_all_attempt_costs=paired['all_attempt_costs'],
        unique_005_generation_http_seconds=all_summary['http_seconds']['sum'],
        wrapper_minus_generation_http_seconds=paired['all_attempt_costs']['request_elapsed_seconds']-all_summary['http_seconds']['sum'],
        first_launch_to_paired_completion_seconds=(wall_end-wall_start).total_seconds(),
        first_launch_utc=wall_start.isoformat(), paired_completion_utc=wall_end.isoformat(),
        phase_wall_seconds={'technical-smoke':smoke['wall_seconds_this_phase'],'paired-feasibility':paired['wall_seconds_this_phase']},
        note='Paired measurements include the reused original 15 smoke requests: count 60, not 75. Raw HTTP duration, encompassing attempt duration and elapsed calendar time are distinct. All sleep/downtime stays charged.',
        historical_before_005={key:historical[key] for key in ['scope','generation_requests','experimental_generation_requests','engineering_generation_requests','uncertain_dispatch_reservations','recorded_http_seconds_lower_bound','unknown_duration_policy']},
        prior_ledger_note='Prior ledger values are preserved with their original definitions; do not treat unknown durations as zero or silently combine reservation counts into confirmed counts.'),
    memory=dict(all_observations=memory_stats(memory), after_cutoff=memory_stats([row for row in memory if row['recorded_at_utc'] >= CUTOFF]),
                observer_summary=read(memory_summary_path),
                interpretation='Sampled available RAM stayed above the 2 GiB stop threshold. iGPU uses shared system memory; do not add GPU memory to physical RAM. Sparse observations do not prove the absence of shorter peaks or guarantee larger-context capacity.'),
    actual_document_capacity=dict(existing_offline_audit_tokenizer_matches_005=tokenizer_matches,
                                  source_rows=capacity_rows,
                                  largest_A_full_document_tokens=14477, corresponding_F03_baseline_tokens=9070,
                                  simple_sum_before_rendered_history=23547,
                                  measured_005_max_rendered_prompt_tokens=18790,
                                  context_capacity_tokens=32768,
                                  warning='A/C phase inputs and rendered multi-stage histories have not been measured in this selected run. Document token sums omit wrappers, later responses and tools. Long FULL histories could approach the context limit; exact fit and runtime must be checked offline before launch.'),
    forecast_method=dict(
        units='Future additional trajectories; one trajectory is the complete three-stage workflow. Development responses are not implicitly reused as new main-sample observations.',
        center='Count × mean wall seconds of the 13 complete post-cutoff trajectories.',
        upper='Count × empirical post-cutoff trajectory P90 × 1.20 resource/retry margin; actual-document upper additionally ×1.50 for unmeasured context/output shape.',
        overhead='Planning allowances, not measured times: B preparation 0.5–2h plus analysis/report checks 0.5–2h; actual documents preparation 0.5–2h plus source/analysis checks 1–4h.',
        not_confidence_interval=True,
        caveats=['Only one development market scenario; 13 complete stabilized trajectories and 41 requests provide engineering rates, not population timing inference.',
                 'The lower endpoint is an empirical center, not a hard minimum; the upper endpoint is a planning margin, not a guarantee.',
                 'Observed extra tool rounds were zero. Future tool requests or retries increase calls beyond three per trajectory; worst permitted multi-round execution can exceed these ranges.',
                 'Output cap 4096 exceeds the observed maximum 2617 and post-cutoff mean 1579. Longer outputs, cold loads, GPU contention, power/thermal changes or restart downtime can materially increase runtime.',
                 'Preparation/analysis includes ordinary offline validation, not unforeseen protocol redesign, missing-source collection or independent human review.',
                 'No runtime reduction changes the statistical estimand or validates a smaller sample. Methodology and prior freeze must be amended separately before any new calls.']),
    reduced_future_forecasts=forecasts,
    original_plan_reference=dict(total_planned_trajectories=3272,
                                 stabilized_same_shape_runtime_hours=3272*mean_seconds/3600,
                                 stabilized_same_shape_runtime_days=3272*mean_seconds/86400,
                                 note='Illustrative no-additional-round runtime before preparation/analysis; not a new budget or authorization. Already completed development evidence remains separate.'),
    evidence=[ref(p) for p in [paired_path, smoke_path, phases/'technical-smoke/budget_state.json', historical_path,
                               memory_path, memory_summary_path, capacity_path, tokenizer_path, Path(__file__)]]
)
write('timing_resource_requests_005_20261028.json', rows)
report['request_table'] = ref(OUT/'timing_resource_requests_005_20261028.json')
write('timing_resource_review_005_20261028.json', report)
write('timing_resource_review_manifest_005_20261028.json', dict(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
     artifacts=[ref(OUT/'timing_resource_review_005_20261028.json'),ref(OUT/'timing_resource_requests_005_20261028.json'),ref(Path(__file__))],
     verified_responses=60, requests_and_token_totals_match_phase_measurements=True, model_calls=0,
     experiment_or_server_mutations=0, effect_or_pvalue_reads=0))
print(json.dumps(dict(report=str(OUT/'timing_resource_review_005_20261028.json'),
    post_cutoff_requests=len(post), post_cutoff_trajectories=post_summary['complete_trajectories'],
    mean_trajectory_seconds=mean_seconds, memory_min_GiB=report['memory']['all_observations']['available_physical_GiB']['minimum'],
    forecasts=forecasts, original_plan_runtime_days=report['original_plan_reference']['stabilized_same_shape_runtime_days']),ensure_ascii=False,indent=2))
