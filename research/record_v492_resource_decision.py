"""Record a pre-output engineering time ceiling using observed local rates."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / 'research/v492_resource_decision_20261019.json'
    if target.exists():
        raise ValueError('Existing engineering decision is immutable')
    source = ROOT / 'data/local_sector_runtime/v491_cpu_preflight_20261019/synthetic_large_input_threads8/http_0001_latency_probe/result.json'
    metrics = json.loads(source.read_text(encoding='utf-8'))['metrics']
    scenario = 57344 / metrics['prompt_eval_tokens_per_second'] + 8192 / metrics['eval_tokens_per_second'] + metrics['load_duration_seconds']
    record = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Engineering ceiling selected before any v492 research output; not a paper-derived behavioral parameter.',
        'prior_ceiling_seconds': 900, 'new_stage_ceiling_seconds': 4500,
        'model_or_research_output_allowance_changed': False,
        'observed_metrics_ref': {'path': source.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()},
        'observed_prompt_tokens': metrics['prompt_eval_count'], 'observed_output_tokens': metrics['eval_count'],
        'prompt_tokens_per_second': metrics['prompt_eval_tokens_per_second'],
        'output_tokens_per_second': metrics['eval_tokens_per_second'],
        'context': 65536, 'reserved_output_tokens': 8192, 'maximum_admissible_prompt_tokens': 57344,
        'scenario_formula': 'max_prompt / observed_prefill_rate + output_allowance / observed_decode_rate + observed_load_seconds',
        'scenario_seconds': scenario, 'rounding_choice': 'Round scenario upward to75minutes as an explicitly chosen operating ceiling.',
        'limitations': ['Decode rate came from only6tokens, so extrapolation is a rough resource scenario, not a forecast or completion guarantee.',
                       'F0 size is unknown until its actual D0 and deterministic feedback exist; exact token capacity is checked then.',
                       'First-attempt outputs, failures and unattempted cells remain in the planned denominator.',
                       'Stage unloading, no retries, raw-output preservation and the same settings in all five cells remain.'],
        'maximum_generations': 10, 'maximum_stage_ceiling_total_hours': 4500 * 10 / 3600,
        'ceiling_total_is_expected_runtime': False,
        'research_generation_requests_before_decision': 0,
        'stop_policy': 'User cancellation or transport/integrity/capacity failure as declared; no success-score-based retries or selection.',
    }
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'stage_ceiling': 4500, 'scenario_minutes': scenario / 60, 'model_calls': 0}))


if __name__ == '__main__':
    main()
