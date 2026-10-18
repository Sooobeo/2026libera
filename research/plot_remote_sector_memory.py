"""Plot recovered monitor samples only; no inference, network or runtime edits.

The normal plot requires both completed artifact collections (monitor + summary),
including an unsuccessful pilot if that is what the saved summary reports.
--diagnostic-only explicitly permits a separate diagnostic-only image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
RECEIVED = ROOT/'data/remote_sector_20261018/data/sector_runtime'
GIB = 1024**3


def value_gib(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return math.nan
    return value/GIB if math.isfinite(value) and value >= 0 else math.nan


def load_samples(folder):
    folder = Path(folder)
    path, summary_path = folder/'monitor.jsonl', folder/'summary.json'
    if not path.is_file() or not summary_path.is_file():
        raise FileNotFoundError(f'Recovered monitor and final summary are required: {folder}')
    raw = path.read_bytes()
    rows = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    summary_raw = summary_path.read_bytes()
    summary = json.loads(summary_raw.decode('utf-8-sig'))
    seconds, rss, cgroup = [], [], []
    for index, row in enumerate(rows, 1):
        elapsed = row.get('elapsed_seconds')
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError(f'{path}:{index}: invalid elapsed_seconds')
        if seconds and elapsed < seconds[-1]:
            raise ValueError(f'{path}:{index}: elapsed_seconds decreased; samples were not reordered')
        memory = row.get('memory', {})
        seconds.append(elapsed)
        rss.append(value_gib(memory.get('rss_sum_bytes')))
        # Never substitute memory.peak, a cgroup limit, or /proc/MemTotal.
        cgroup.append(value_gib(memory.get('cgroup', {}).get('memory.current')))
    if not rows or not any(math.isfinite(x) for x in rss+cgroup):
        raise ValueError(f'No finite memory samples: {path}')
    intervals = [b-a for a,b in zip(seconds,seconds[1:])]
    finite = lambda values: [x for x in values if math.isfinite(x)]
    metadata = {
        'monitor_path':str(path.resolve()), 'monitor_sha256':hashlib.sha256(raw).hexdigest(),
        'summary_path':str(summary_path.resolve()),
        'summary_sha256':hashlib.sha256(summary_raw).hexdigest(),
        'recorded_status':summary.get('status'), 'sample_count':len(rows),
        'first_elapsed_seconds':seconds[0], 'last_elapsed_seconds':seconds[-1],
        'median_sample_interval_seconds':statistics.median(intervals) if intervals else None,
        'first_sample_utc':rows[0].get('memory',{}).get('observed_at_utc'),
        'last_sample_utc':rows[-1].get('memory',{}).get('observed_at_utc'),
        'finite_samples':{'rss_sum':len(finite(rss)), 'cgroup_memory_current':len(finite(cgroup))},
        'sampled_maximum_gib':{'rss_sum':max(finite(rss),default=None),
                               'cgroup_memory_current':max(finite(cgroup),default=None)},
    }
    return {'seconds':seconds, 'rss_gib':rss, 'cgroup_gib':cgroup, 'metadata':metadata}


def plot(diagnostic, pilot, output):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    try:
        font_path = font_manager.findfont('Malgun Gothic', fallback_to_default=False)
        korean = True
    except ValueError:
        font_path, korean = None, False
    if font_path:
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams.update({'axes.unicode_minus':False, 'font.size':10.5,
                         'axes.spines.top':False, 'axes.spines.right':False})
    records = [(diagnostic, '기술 진단' if korean else 'Technical diagnosis', 1)]
    if pilot is not None:records.append((pilot, '4단계 파일럿' if korean else 'Four-stage pilot', 60))
    fig, axes = plt.subplots(1,len(records),figsize=(14 if pilot else 9,7.3),sharey=True,squeeze=False)
    for ax,(record,label,scale) in zip(axes[0],records):
        x = [value/scale for value in record['seconds']]
        ax.plot(x,record['rss_gib'],color='#1874B4',linewidth=1.8,label='Named-process RSS sum')
        ax.plot(x,record['cgroup_gib'],color='#D76B27',linewidth=1.8,label='cgroup memory.current')
        if len(x)<=40:
            ax.scatter(x,record['rss_gib'],color='#1874B4',s=12,zorder=3)
            ax.scatter(x,record['cgroup_gib'],color='#D76B27',s=12,zorder=3)
        meta = record['metadata']
        ax.set_title(f"{label} | n={meta['sample_count']:,} | {meta['recorded_status']}",loc='left',fontsize=12,pad=13)
        ax.set_xlabel(('세션 경과 시간 (초)' if scale==1 else '세션 경과 시간 (분)') if korean else
                      ('Session elapsed time (seconds)' if scale==1 else 'Session elapsed time (minutes)'))
        ax.grid(axis='y',alpha=0.22)
        ax.legend(loc='best',fontsize=9.5,frameon=False)
    observed_max = max(value for record,_,_ in records
                       for value in record['rss_gib']+record['cgroup_gib'] if math.isfinite(value))
    axes[0][0].set_ylim(0,max(1,observed_max*1.12))
    axes[0][0].set_ylabel('관측 메모리 (GiB)' if korean else 'Observed memory (GiB)')
    title = '원격 런타임 메모리 관측' if korean else 'Remote runtime memory observations'
    if pilot is None:title += ' — 진단만' if korean else ' — diagnosis only'
    fig.suptitle(title,fontsize=18,x=0.07,ha='left',y=0.97)
    fig.text(0.07,0.915,'qwen3.5:4b-q4_K_M | v4.3 | 1 GiB = 1024^3 bytes',fontsize=11,color='#4A5568')
    if korean:
        caption = (
            '원자료: 각 세션 monitor.jsonl의 표본값을 선으로 연결. 평활화하지 않았으며 결측값은 빈 구간으로 남김. 시간축은 생성 시간이 아닌 세션 경과 시간.\n'
            'RSS 합계는 수집 대상 Ollama·runner 프로세스 범위이며 공유 페이지를 중복 집계할 수 있음. cgroup 값은 캐시와 다른 프로세스를 포함할 수 있음.\n'
            '두 계열은 범위가 달라 더하지 않음. memory.peak를 실행 최대치로 사용하지 않았으며, 표본 사이의 순간 최대치는 관측되지 않을 수 있음.\n'
            '호스트 전체 메모리 사용량·메모리 할당 한도·OOM 부재·본실험 실행 가능성을 이 그래프만으로 판단하지 않음.'
        )
    else:
        caption = (
            'Raw samples: each session monitor.jsonl. Lines connect recorded samples; missing values remain gaps. Elapsed time is session time, not generation time.\n'
            'RSS sums cover named Ollama/runner processes and may count shared pages more than once. cgroup values can include cache and other processes.\n'
            'The two series have different scopes and are never added. memory.peak is not used as a run maximum; between-sample peaks may be missed.\n'
            'This figure does not establish whole-host memory use, allocation limits, absence of OOM, or readiness for the main experiment.'
        )
    fig.text(0.07,0.045,caption,fontsize=8.6 if pilot else 7.5,color='#4A5568',linespacing=1.6,va='bottom')
    fig.subplots_adjust(left=0.07,right=0.98,top=0.82,bottom=0.27,wspace=0.18)
    metadata = {'scope':'Artifact diagnostic only; no inference or experiment performance scoring',
                'unit':'GiB (1024**3 bytes)', 'series_added':False, 'memory_peak_used':False,
                'diagnostic':diagnostic['metadata'], 'pilot':pilot['metadata'] if pilot else None,
                'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'matplotlib_version':matplotlib.__version__, 'font_path':font_path,
                'caption':caption}
    output = Path(output)
    if output.suffix.lower() != '.png':raise ValueError('Output must be a PNG file')
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=180,facecolor='white',metadata={'Description':json.dumps(metadata,ensure_ascii=False)})
    plt.close(fig)
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-dir',type=Path,default=RECEIVED/'diagnose_v43')
    parser.add_argument('--pilot-dir',type=Path,default=RECEIVED/'pilot_v43')
    parser.add_argument('--diagnostic-only',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args(argv)
    try:
        diagnostic = load_samples(args.diagnostic_dir)
        pilot = None if args.diagnostic_only else load_samples(args.pilot_dir)
    except FileNotFoundError as exc:
        print(json.dumps({'status':'awaiting_recovered_artifacts','output_created':False,'reason':str(exc)}))
        return 2
    suffix = '_diagnostic' if args.diagnostic_only else ''
    output = args.output or ROOT/f'research/evidence/remote_sector_memory{suffix}_20261018.png'
    metadata = plot(diagnostic,pilot,output)
    print(json.dumps({'status':'created','output':str(output),'sources':{
        'diagnostic':metadata['diagnostic'],'pilot':metadata['pilot']},'inference_calls':0},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
