"""Summarize completed engineering evidence without making research claims."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/local_sector_runtime/v491_cpu_preflight_20261019'
OUT = ROOT / 'research/artifacts/v491_runtimeprep_20261019'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def ref(path):
    path = Path(path)
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def probe(folder):
    target = RAW / folder
    spec = read(target / 'spec.json')
    supervisor = read(target / 'supervisor_result.json')
    worker = supervisor.get('worker', {})
    result_path = target / 'http_0001_latency_probe/result.json'
    result = read(result_path) if result_path.exists() else {}
    samples, incomplete_lines = [], 0
    for line in (target / 'monitor.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            samples.append(json.loads(line))
        except ValueError:
            incomplete_lines += 1
    available = [r['memory']['available_physical_bytes'] for r in samples if isinstance(r.get('memory', {}).get('available_physical_bytes'), int)]
    workings = [r['memory']['working_set_sum_bytes'] for r in samples if isinstance(r.get('memory', {}).get('working_set_sum_bytes'), int)]
    return {'probe_id': folder, 'purpose': spec['purpose'],
        'threads': spec['body']['options']['num_thread'], 'context': spec['body']['options']['num_ctx'],
        'prompt_tokens_exact_preflight': spec.get('actual_prompt_tokens'),
        'output_limit': spec['body']['options']['num_predict'],
        'supervisor_status': supervisor['supervisor_status'], 'worker_status': worker.get('status'),
        'request_attempts': int((target / 'http_0001_latency_probe/request.json').is_file()),
        'metrics': result.get('metrics', {}), 'supervisor_elapsed_seconds': supervisor['elapsed_seconds'],
        'available_ram_min_bytes': min(available) if available else None,
        'named_process_working_set_max_bytes': max(workings) if workings else None,
        'memory_scope': 'System available RAM and observed named Ollama process working sets (may double-count shared pages); sampled values, not exclusive model allocation.',
        'incomplete_monitor_lines': incomplete_lines,
        'awake_release': read(target / 'awake_release.json')['status'],
        'cleanup': read(target / 'cleanup.json')['status'],
        'supervisor_evidence': ref(target / 'supervisor_result.json'),
        'not_a_pilot_or_full_task': True}


def main():
    rows = [probe(name) for name in ('synthetic_smoke', 'synthetic_large_input', 'synthetic_large_input_threads8')]
    tokens = read(ROOT / 'research/v491_token_review_20261019_r2.json')
    prior = read(ROOT / 'research/v491_handoff_20261019.json')
    unchanged = all(ref(ROOT / r['path'])['sha256'] == r['sha256'] for r in prior['exact_delivery_files'])
    if not unchanged:
        raise ValueError('Previous reviewed delivery changed')
    files = [ref(p) for p in sorted(RAW.rglob('*')) if p.is_file()]
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / 'cpu_engineering_evidence.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for item in files:
            bundle.write(ROOT / item['path'], item['path'])
    manifest = {'archive': archive.name, 'archive_sha256': ref(archive)['sha256'], 'files': files,
                'scope': 'Owned source-free CPU diagnostic service, including all failed/partial attempts; no actual research output.'}
    save(OUT / 'cpu_engineering_evidence.manifest.json', manifest)
    from restore_research_artifacts import restore
    verification = restore(OUT / 'cpu_engineering_evidence.manifest.json', ROOT)
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'runtime_prepared_and_engineering_measured_human_review_pending',
        'prior_delivery_69_files_unchanged': unchanged, 'engineering_probes': rows,
        'engineering_generation_requests': sum(row['request_attempts'] for row in rows),
        'pilot_generation_requests': 0, 'main_generation_requests': 0,
        'research_frozen': False, 'independent_human_review_completed': False,
        'D0_token_range': tokens['exact_D0_token_range'],
        'D0_schema_included_render_receipt': ref(ROOT / 'research/v491_token_review_20261019_r2.json'),
        'runtime_candidate': ref(ROOT / 'research/v491_runtime_candidate_20261019.json'),
        'archive': ref(archive), 'archive_manifest': ref(OUT / 'cpu_engineering_evidence.manifest.json'),
        'archive_verification': verification,
        'limits': ['Synthetic input/output differ from the investment task; no full D0/F0 feasibility or reliability guarantee.',
                   'Single fixed-order engineering probes with OS cache/background-work differences; not a controlled speed ranking.',
                   'Context65536, CPU threads and deadlines are engineering choices, not invented paper-derived behavioral conditions.',
                   'Actual F0 must be exactly tokenized after its own D0; all possible unknown histories are not bounded in advance.',
                   'The initial short-probe coordinator raised a duplicate receipt-write error after successful generation and cleanup. It was fixed without rerunning; incident retained.',
                   'Independent humans must review source meanings before formal pilot outputs under the existing evaluation protocol.'],
        'next_required': ['Two independent human pilot-source/common-context reviews and recorded reconciliation.',
                          'Four-case pilot, first D0/F0 attempts only, with actual capacity/memory/latency and failure denominators.',
                          'Main-source human review, exact protocol/runtime/evaluation/order freeze, then main experiment.']}
    save(ROOT / 'research/v491_runtimeprep_report_20261019.json', report)
    table = ''
    for row in rows:
        seconds = row['metrics'].get('wall_seconds', row['supervisor_elapsed_seconds'])
        observed = row['metrics'].get('prompt_eval_count', row['prompt_tokens_exact_preflight'])
        status = row['worker_status'] or row['supervisor_status']
        table += f"<tr><td>{html.escape(row['probe_id'])}</td><td>{row['threads']}</td><td>{observed}</td><td>{seconds:.1f}초</td><td>{html.escape(status)}</td></tr>"
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA v4.9.1 실행 준비</title>
<style>body{font:17px/1.75 system-ui,sans-serif;background:#f4f6f9;color:#172438;margin:0}main{max-width:1000px;margin:auto;padding:36px 24px 70px}h1{font-size:32px;line-height:1.3}h2{margin-top:42px}a{color:#1757a3}section,.notice{background:white;padding:22px;margin:20px 0;border-radius:10px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border-bottom:1px solid #ccd4df;text-align:left;overflow-wrap:anywhere}.scroll{overflow:auto}.notice{border-left:5px solid #c88213}code{overflow-wrap:anywhere}li{margin:10px 0}</style><main>
<p>2026-10-19 · 실행 준비 부록 · 기존 소논문/설계 v4.9.1 보존</p><h1>실행기와 검토 자료 준비 완료<br>실제 예비실험은 원문 검토 후 진행</h1>
<div class="notice">공학용 가상 입력 진단만 수행했습니다. 실제 기관 자료를 사용한 예비실험·본실험 생성은 각각 0회이며, 사람 검토와 본실험 동결은 아직 완료되지 않았습니다.</div>
<section><h2>이번에 해결한 부분</h2><p>동일한 공통 시장상황과 운용 과제를 유지하는 4개 사례의 실행기를 연결했습니다. 각 초안과 최종 답변은 1회씩만 시도하고, 실제 초안 원문·계산 피드백·해당 기관 자료를 그대로 이어 붙입니다. 합계가 틀리거나 인용이 부정확한 답변도 기록하며, 보기 좋은 답이 나올 때까지 다시 돌리지 않습니다.</p>
<p>설치된 모델의 실제 토크나이저로 8개 초안 입력을 검사했습니다. 길이는 12,228–13,225토큰이고, 출력 8,192토큰을 더해도 65,536토큰 설정 안에 들어갑니다. 최종 단계는 실제 초안이 생긴 뒤 다시 계산합니다. 한도를 넘으면 입력을 잘라내지 않고 실행 실패로 기록합니다.</p></section>
<section><h2>CPU 진단 결과</h2><div class="scroll"><table><thead><tr><th>가상 진단</th><th>CPU 스레드</th><th>입력 토큰</th><th>관측 시간</th><th>상태</th></tr></thead><tbody>''' + table + '''</tbody></table></div>
<p>실제 산업 판단을 생성한 결과가 아닙니다. 긴 가상 입력도 출력은 최대 32토큰만 허용했습니다. 실제 실험은 최대 8,192토큰을 허용하므로 위 시간을 본실험 소요 시간으로 사용할 수 없습니다. 고정된 순서의 1회 관측이며 캐시·다른 작업의 영향도 남습니다.</p>
<p>CPU 코어 수·문맥 크기·시간 제한은 하드웨어 실행 설정입니다. 논문에서 검증된 최적 수치라고 주장하지 않습니다. 기존 문헌 기반 과제·평가 규칙·출력 허용량은 유지했습니다.</p></section>
<section><h2>사람이 지금 해야 할 일</h2><ol><li>두 사람이 <a href="../research/v491_human_review_pack_20261019_R1.html">검토자 1 자료</a>와 <a href="../research/v491_human_review_pack_20261019_R2.html">검토자 2 자료</a>를 따로 엽니다. 우선 검토 범위를 <b>pilot</b>로 선택하면 됩니다.</li>
<li>각자 Fidelity Q2·UBS June 원문과 요약을 대조합니다. 각 자료의 11개 산업 의미와 공통 시장상황을 확인하고, 기관 간 차이를 미리 적습니다. 투자 비중이나 정답 포트폴리오를 정하는 작업은 아닙니다.</li>
<li>상대 답안을 보기 전에 각각 JSON을 저장합니다. 두 답안의 차이를 보존하면서 조정한 뒤 실행 관문에 연결합니다. 본실험 문서 부분은 이 단계에서는 비워 둘 수 있습니다.</li></ol>
<p>이 순서는 <a href="../research/v491_evaluation_protocol_20261019.json">기존 평가 규칙의 blind_review.before_generation</a>에 따른 것입니다. AI 출력에 맞추어 기관 간 차이를 사후에 고르는 것을 피하기 위한 연구 절차입니다. 프로그램 검증이나 AI 검토는 두 사람의 원문 의미 검토를 대신하지 않습니다.</p></section>
<section><h2>논문 주제와 연결</h2><p>여전히 “동일한 시장과 운용 과제 아래 기관별 공개 판단이 AI의 근거와 실제 산업 비중에 어떻게 반영되는가, 자료를 초안 전·후에 주면 무엇이 달라지는가”를 봅니다. CPU 진단은 이 질문에 대한 실험 결과가 아닙니다. 두 기관·한 모델의 문서 사례로 해석하며 시장 전체의 획일화나 수익성을 입증하지 않습니다.</p>
<p><a href="LIBERA_공통상황포함_실험계획_v4.9.1_20261019.html">기존 실험계획</a> · <a href="../paper/LIBERA_텀페이퍼_초안_v4.9.1_20261019.html">실험 전 텀페이퍼</a> · <a href="../research/v491_runtimeprep_report_20261019.json">기계 판독 보고서</a></p></section></main></html>'''
    (ROOT / 'plan/LIBERA_실행준비현황_v4.9.1_20261019.html').write_text(document, encoding='utf-8', newline='\n')
    print(json.dumps({'report': 'research/v491_runtimeprep_report_20261019.json', 'archive_files': len(files), 'engineering_calls': report['engineering_generation_requests']}))


if __name__ == '__main__':
    main()
