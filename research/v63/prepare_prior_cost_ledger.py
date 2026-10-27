"""Record closed pre-candidate-002 costs. This is evidence, never authorization."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def ref(path):return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    rows=[]
    first=DATA/'local_campaign_results/runs/a151e0eea80931eb9bb281fc303a503410c5fd58e52ca9cff010d3e8ed11f10d'
    for p in sorted(first.rglob('generation.receipt.json')):
        receipt=read(p)
        rows.append({'kind':'superseded_experimental_candidate','location':'current_pc','generation_requests':1,
            'recorded_http_seconds':receipt['elapsed_seconds'],'evidence':ref(p)})
    remote=DATA/'continuation/deployment/remote_cost_summary.json';cost=read(remote)
    rows.append({'kind':'aborted_experimental_candidate','location':'container_150','generation_requests':cost['generation_requests_started'],
        'recorded_http_seconds':cost['recorded_request_seconds'],'evidence':ref(remote),
        'raw_original_location':'Remote hash-identified evidence archive; local JSON is a normalized browser-console extraction.'})
    probes=[DATA/'runtime/local_windows/q8_timing_probe_002/threads_4',DATA/'runtime/local_windows/q8_timing_probe_002/threads_8',DATA/'runtime/local_windows/f16_timing_probe_003']
    for directory in probes:
        paths=list(directory.glob('http/attempt_*/generation.receipt.json'))
        if len(paths)!=1:raise ValueError('Expected exactly one closed timing call: '+str(directory))
        p=paths[0];receipt=read(p)
        rows.append({'kind':'engineering_only','location':'current_pc','generation_requests':1,
            'recorded_http_seconds':receipt['elapsed_seconds'],'evidence':ref(p)})
    p=DATA/'runtime/local_windows/connectivity_probe_001/summary.json';receipt=read(p)
    rows.append({'kind':'engineering_only','location':'current_pc','generation_requests':receipt['live_engineering_generation_requests'],
        'recorded_http_seconds':receipt['wall_seconds'],'evidence':ref(p)})
    p=DATA/'runtime/remote_connectivity_probe_response.json';receipt=read(p)
    rows.append({'kind':'engineering_only','location':'container_150','generation_requests':1,
        'recorded_http_seconds':None,'observed_server_seconds':receipt['total_duration']/1e9,'evidence':ref(p),
        'timing_note':'Provider server duration exists; complete client HTTP wall time was not captured. Do not invent it.'})
    result={'schema':'libera_closed_prior_cost_ledger_v1','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'authorization':False,'scope':'Only closed attempts preceding candidate_002; excludes its active run entirely. Engineering generations consume resources but fill no experimental slots.',
        'generation_requests':sum(r['generation_requests'] for r in rows),
        'experimental_generation_requests':sum(r['generation_requests'] for r in rows if r['kind']!='engineering_only'),
        'engineering_generation_requests':sum(r['generation_requests'] for r in rows if r['kind']=='engineering_only'),
        'recorded_http_seconds_lower_bound':sum(r['recorded_http_seconds'] or 0 for r in rows),
        'requests_without_client_http_timing':sum(r['generation_requests'] for r in rows if r['recorded_http_seconds'] is None),
        'rows':rows}
    target=DATA/'continuation/deployment/prior_candidate_002_cost_ledger.json'
    if target.exists():raise ValueError('Closed cost ledger already exists; preserve the original.')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))

if __name__=='__main__':main()
