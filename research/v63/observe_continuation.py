"""Read-only campaign observer; it never launches or retries model requests."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from research.v63.build_continuation_report import main as render_report,verify_completion_commit
from research.v63.campaign_control import task_request_cost

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/v63_20261027'


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def write(path, value):
    pending = path.with_suffix(path.suffix + '.writing')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending.replace(path)


def observe():
    path = DATA / 'continuation/live_status.json'
    state = read(path, {})
    if state.get('all_experiments_completed') is True:
        verify_completion_commit(state)
        return False
    pause=read(DATA/'continuation/user_pause_20261027.json',{})
    if pause.get('active') is True:
        state['status_ko']='사용자 요청으로 실험을 일시 중지했습니다. 원응답과 재개 지점을 보존했습니다.'
        state.setdefault('model_execution',{}).setdefault('local_windows',{})['status']='paused_by_user'
        write(path,state)
        render_report()
        return False
    now = datetime.now(timezone.utc).isoformat()
    root = DATA / 'local_campaign_results'
    progress = read(root / 'progress.json')
    if progress:
        active_run = root / 'runs' / progress['run_id']
        request_costs=task_request_cost(active_run)
        local = state.setdefault('model_execution', {}).setdefault('local_windows', {})
        if local.get('runtime_identity_sha256')!=progress['run_id']:
            local.clear()
        for obsolete in ('first_prompt_tokens','engineering_connectivity_calls_excluded'):
            local.pop(obsolete,None)
        local.update(phase=progress['phase'], current_task=progress.get('current_task'), status=progress['status'],
                     trajectory_level_progress_updated_at_utc=progress['updated_at_utc'],
                     runtime_identity_sha256=progress['run_id'],
                     generation_request_files_written=sum(1 for _ in active_run.rglob('generation.request.bin')),
                     generation_response_files_saved=sum(1 for _ in active_run.rglob('generation.response.bin')),
                     actual_request_accounting=request_costs,
                     output_directory=str(root.relative_to(ROOT)).replace('\\','/'),
                     recorded_trajectories=progress['recorded_trajectories'],
                     planned_trajectories=progress['planned_trajectories'],
                     terminal_counts=progress['terminal_counts'],
                     completed_receipt_costs=progress['actual_costs'],
                     count_scope='This run identity only, across its phases; active requests may not have final receipts.')
        state['selected_run_id']=progress['run_id']
        state['phase_progress']={p.parent.name:read(p,{}) for p in sorted((root/'phases'/progress['run_id']).glob('*/progress.json'))}
        guardian=root/'guardian'/progress['run_id']
        state['guardian_observation']={p.name:read(p,{}) for p in (guardian/'heartbeat.json',guardian/'checkpoint.json',guardian/'main_resource_review.json') if p.is_file()}
    readiness = read(DATA / 'continuation_sources/readiness_v2.json', {})
    state['data_readiness'] = readiness.get('summary', {})
    audit = read(DATA / 'continuation_sources/data_verification_v2.json', {})
    checks = audit.get('checks', [])
    state['data_validation'] = {'checks': len(checks), 'passed': sum(x.get('passed') is True for x in checks),
                                'failed': sum(x.get('passed') is not True for x in checks)}
    state['observed_at_utc'] = now
    abort = read(DATA / 'continuation/deployment/remote_capacity_abort.json')
    if abort:
        remote = state.setdefault('model_execution', {})
        remote.update(status=abort['status'],actual_generation_requests=abort['generation_requests_started'],
                      completed_trajectories=0,remote_abort_receipt='data/v63_20261027/continuation/deployment/remote_capacity_abort.json')
        remote['remote_observation'] = dict(generation_requests_started=abort['generation_requests_started'],
                    complete_model_responses_received=0,first_request_timeout_seconds=1800.1,
                    first_response_body_bytes=0,phase_status=abort['status'],
                    count_is_not_final=False,process_exit_observed=True,
                    interpretation='The second in-flight retry was interrupted; no completed experimental trajectory is claimed.')
    state['all_experiments_completed'] = False
    main_started=any(task_request_cost(p/'B-main')['generation_requests']>0 for p in (root/'runs').glob('*') if p.is_dir())
    phase=(progress or {}).get('phase','개발 준비')
    state['status_ko'] = f'기간별 데이터 12개 묶음을 준비했고, 현재 {phase} 단계의 실제 실행 기록을 수집하고 있습니다.'
    state['events_ko'] = [
        '사람 감사는 사용자 지시에 따라 완료 가정으로 기록했습니다.',
        '12개 기간별 보유비중, NAV 대사, 공식 SIC 연결 및 의무 운용규칙을 검증했습니다.',
        '150번 컨테이너와 현재 PC에서 동일 모델의 개발 후보를 실제 실행했습니다. 각 실행의 요청과 원응답을 따로 보존합니다.',
        '첫 PC 후보는 요청 5회 모두 2,048 출력토큰 한도에 도달했습니다. 뒤 10개 단계는 선행 실패로 미실행이며, 후보를 본실험에 사용하지 않습니다.',
        '150번 컨테이너는 첫 요청이 1,800초 뒤 응답 없이 시간 초과되어, 2번째 재시도 중 해당 후보만 중단했습니다. 기존 서버 서비스와 원기록은 보존했습니다.',
        ('본실험의 실제 생성 요청이 시작됐습니다. 각 실험의 종료 여부와 실패를 원기록으로 확인하며 전체 완료는 최종 검증 후에만 표시합니다.' if main_started else '본실험 7,200단계는 아직 시작하지 않았습니다. 출력 형식, 문맥 용량, 실제 비용을 확인한 뒤 설정을 동결합니다.'),
        '공식 문서에 없는 FF12별 산업 한도를 새로 만들지 않았으며, 현재 공식 SIC를 사용한 부분은 회고적 분류로 표시했습니다.',
    ]
    write(path, state)
    snapshot = {'observed_at_utc': now, 'local_progress': progress, 'data_readiness': state['data_readiness']}
    with (DATA / 'continuation/observer_history.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(snapshot, ensure_ascii=False) + '\n')
    render_report()
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    while True:
        active=observe()
        if not args.watch or not active:
            break
        time.sleep(60)
