"""Pinned official Qwen3.5 2B Q4_K_M cache preparation; never contact model API."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,time,urllib.request,urllib.parse

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'tmp/v63_local_ollama/models'
OUT=ROOT/'data/v63_20261027/runtime/local_windows/qwen35_2b_q4_download'
REGISTRY='https://registry.ollama.ai/v2/library/qwen3.5'
TAG='2b-q4_K_M'
MANIFEST_SHA='1e2d21a4f03ab9e4a9c1976a4b7e88f21de61d65f2c5485d8fde8942be73f1e7'
EXPECTED={'application/vnd.ollama.image.model':('20cb277f0967ace47b0b5d5658e5e494a88937f7378b74b5a266496400938f4c',1274396992),
          'application/vnd.ollama.image.projector':('5ddf560e34046fd958b2576324f2a9b57d70f297afe6526958d60a23f3bfc20b',671372768)}
CHUNK=1024*1024
RATE=8*1024*1024

def now():return datetime.now(timezone.utc).isoformat()
def save(name,value):
    path=OUT/name;temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(CHUNK),b''):h.update(data)
    return h.hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();network_bytes=0
    receipt={'status':'preparing','started_at_utc':now(),'model':'qwen3.5:'+TAG,'manifest_sha256':MANIFEST_SHA,
        'official_registry':REGISTRY,'model_api_calls':0,'model_generation_requests':0,'model_engine_load_changes':0,
        'stream_buffer_bytes':CHUNK,'download_rate_limit_bytes_per_second':RATE,'parts':[],
        'concurrent_activity':'Candidate 002 qwen3:1.7b 15-stage development remains running; record this download interval when interpreting its latency.'}
    try:
        with urllib.request.urlopen(REGISTRY+'/manifests/'+TAG,timeout=60) as response:raw=response.read(65537)
        network_bytes+=len(raw)
        if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:raise ValueError('Official manifest differs from independently pinned bytes.')
        (OUT/'manifest.raw.json').write_bytes(raw);manifest=json.loads(raw)
        parts=[manifest['config'],*manifest['layers']]
        for media,(expected,size) in EXPECTED.items():
            matches=[p for p in parts if p['mediaType']==media]
            if len(matches)!=1 or matches[0]['digest']!='sha256:'+expected or matches[0]['size']!=size:raise ValueError('Pinned model/projector descriptor mismatch.')
        total=sum(p['size'] for p in parts);free=shutil.disk_usage(CACHE).free
        if total!=1945781358 or free<total+512*1024**2:raise ValueError('Unexpected download size or insufficient task-local disk space.')
        receipt.update(status='downloading',expected_blob_bytes=total,disk_free_before_bytes=free);save('receipt.json',receipt)
        for part in parts:
            checksum=part['digest'].removeprefix('sha256:');destination=CACHE/'blobs'/('sha256-'+checksum)
            if destination.exists():
                if destination.stat().st_size!=part['size'] or digest(destination)!=checksum:raise ValueError('Existing owned blob differs; refusing replacement.')
                receipt['parts'].append({**part,'status':'existing_blob_verified','new_network_bytes':0});save('receipt.json',receipt);continue
            partial=destination.with_suffix('.qwen35_download_partial')
            if partial.exists():raise ValueError('Existing partial download requires an explicit reviewed resume.')
            h=hashlib.sha256();count=0;part_start=time.monotonic();part_started=now()
            request=urllib.request.Request(REGISTRY+'/blobs/'+part['digest'],headers={'User-Agent':'LIBERA-research/1.0'})
            with urllib.request.urlopen(request,timeout=120) as response,partial.open('xb',buffering=CHUNK) as f:
                if response.status!=200:raise ValueError('Unexpected HTTP download status.')
                final_host=urllib.parse.urlsplit(response.url).hostname
                while True:
                    chunk=response.read(CHUNK)
                    if not chunk:break
                    f.write(chunk);h.update(chunk);count+=len(chunk);network_bytes+=len(chunk)
                    if count>part['size']:raise ValueError('Blob exceeded pinned size.')
                    delay=count/RATE-(time.monotonic()-part_start)
                    if delay>0:time.sleep(min(delay,1))
                    if count%(32*CHUNK)==0:
                        save('progress.json',{'updated_at_utc':now(),'current_blob':checksum,'current_bytes':count,
                            'current_expected_bytes':part['size'],'total_network_bytes':network_bytes,'elapsed_seconds':time.monotonic()-started,
                            'model_generation_requests':0})
                f.flush();os.fsync(f.fileno())
            if count!=part['size'] or h.hexdigest()!=checksum:raise ValueError('Downloaded blob size/SHA mismatch; partial preserved and not registered.')
            os.replace(partial,destination)
            row={**part,'status':'downloaded_stream_hash_verified','new_network_bytes':count,'started_at_utc':part_started,
                 'finished_at_utc':now(),'elapsed_seconds':time.monotonic()-part_start,'final_download_host':final_host}
            receipt['parts'].append(row);save('receipt.json',receipt);print(json.dumps({'verified':checksum,'bytes':count}),flush=True)
        target=CACHE/'manifests/registry.ollama.ai/library/qwen3.5'/TAG;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=raw:raise ValueError('Existing model tag differs; refusing replacement.')
        else:
            with target.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        receipt.update(status='downloaded_and_all_digests_verified_not_loaded',completed_at_utc=now(),
                       total_network_bytes=network_bytes,elapsed_seconds=time.monotonic()-started,
                       manifest_cache_path=target.relative_to(ROOT).as_posix(),disk_free_after_bytes=shutil.disk_usage(CACHE).free)
        save('receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('status','total_network_bytes','elapsed_seconds','model_generation_requests')}),flush=True)
    except BaseException as exc:
        receipt.update(status='failed_without_model_load',error_type=type(exc).__name__,error=str(exc),
                       total_network_bytes=network_bytes,elapsed_seconds=time.monotonic()-started,finished_at_utc=now())
        save('receipt.json',receipt);raise

if __name__=='__main__':main()
