"""Fetch an isolated CPU subset from the official portable release and pinned model.

Uses supported HTTPS byte ranges to avoid downloading unused CUDA libraries.
ZIP CRCs and each extracted SHA are recorded; this is explicitly NOT a full ZIP
SHA verification. Windows Authenticode verification occurs before execution.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib,json,pathlib,struct,urllib.request,zlib,shutil

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/'tmp/v63_local_ollama'
RECORD=ROOT/'data/v63_20261027/runtime/local_windows'
ASSET='https://github.com/ollama/ollama/releases/download/v0.35.1/ollama-windows-amd64.zip'
SIZE=1471094402
EXPECTED_MODEL='8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7'
EXPECTED_GGUF='3d0b790534fe4b79525fc3692950408dca41171676ed7e21db57af5c65ef6ab6'
REGISTRY='https://registry.ollama.ai/v2/library/qwen3'

def now():return datetime.now(timezone.utc).isoformat()
def save(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
def sha_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(4*1024*1024),b''):h.update(data)
    return h.hexdigest()
def get_range(start,end):
    req=urllib.request.Request(ASSET,headers={'Range':f'bytes={start}-{end}','User-Agent':'LIBERA-research/1.0'})
    with urllib.request.urlopen(req,timeout=60) as response:
        if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{SIZE}':raise ValueError('Official server did not honor exact byte range.')
        data=response.read()
    if len(data)!=end-start+1:raise ValueError('Truncated range.')
    return data

def portable():
    OUT.mkdir(exist_ok=True);RECORD.mkdir(parents=True,exist_ok=True)
    tail=get_range(SIZE-65536,SIZE-1);eocd=tail.rfind(b'PK\x05\x06')
    fields=struct.unpack_from('<4s4H2LH',tail,eocd);central_size,central_offset=fields[5:7]
    central=tail[central_offset-(SIZE-65536):central_offset-(SIZE-65536)+central_size]
    rows=[];i=0
    while i<len(central):
        h=struct.unpack_from('<4s6H3L5H2L',central,i)
        if h[0]!=b'PK\x01\x02':raise ValueError('Invalid central directory.')
        n,e,c=h[10:13];name=central[i+46:i+46+n].decode('utf8')
        rows.append(dict(name=name,compressed=h[8],size=h[9],offset=h[-1],crc32=h[7],compression=h[4]));i+=46+n+e+c
    wanted=[r for r in rows if r['size'] and '/cuda_' not in r['name'] and '/vulkan/' not in r['name']]
    # All main CPU assets are contiguous after the CUDA bundles, plus one license.
    spans=[(0,769),(1433606771,SIZE-1)]
    payloads=[(start,get_range(start,end)) for start,end in spans]
    extracted=[]
    for row in wanted:
        offset=row['offset'];start,payload=next((a,b) for a,b in payloads if a<=offset<a+len(b));local=offset-start
        h=struct.unpack_from('<4s5H3L2H',payload,local)
        n,e=h[-2:];filename=payload[local+30:local+30+n].decode('utf8')
        if h[0]!=b'PK\x03\x04' or filename!=row['name']:raise ValueError('Entry header mismatch.')
        compressed=payload[local+30+n+e:local+30+n+e+row['compressed']]
        raw=zlib.decompress(compressed,-15) if row['compression']==8 else compressed
        if len(raw)!=row['size'] or zlib.crc32(raw)!=row['crc32']:raise ValueError('Entry CRC/size mismatch.')
        destination=(OUT/'portable'/filename).resolve()
        if (OUT/'portable').resolve() not in destination.parents:raise ValueError('Archive path escaped destination.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists() and destination.read_bytes()!=raw:raise ValueError('Existing CPU asset differs.')
        destination.write_bytes(raw)
        extracted.append({**row,'sha256':hashlib.sha256(raw).hexdigest(),'path':str(destination)})
    receipt={'recorded_at_utc':now(),'official_asset':ASSET,'official_archive_size':SIZE,
             'official_archive_sha256_from_release_api':'dc50b9ca7f9023c86525012632cd1615b093d0407987444a7f62ecab617e8e93',
             'full_archive_sha_verified':False,'verification':'HTTPS official supported exact ranges, ZIP CRC/size, per-file SHA; Authenticode must be verified separately.',
             'downloaded_bytes':65536+sum(len(p) for _,p in payloads),'extracted_bytes':sum(r['size'] for r in extracted),
             'files':extracted,'research_model_calls':0}
    save(RECORD/'portable_download.json',receipt)
    print(json.dumps({'status':'cpu_assets_extracted','files':len(extracted),'downloaded_bytes':receipt['downloaded_bytes']}),flush=True)

def model():
    with urllib.request.urlopen(REGISTRY+'/manifests/1.7b',timeout=30) as response:raw=response.read()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_MODEL:raise ValueError('Pinned model manifest bytes mismatch.')
    manifest=json.loads(raw);parts=[manifest['config'],*manifest['layers']]
    if not any(p['digest']=='sha256:'+EXPECTED_GGUF for p in parts):raise ValueError('Expected GGUF absent from pinned manifest.')
    free=shutil.disk_usage(OUT).free
    if free<sum(p['size'] for p in parts)+512*1024*1024:raise ValueError('Insufficient task-local model disk space.')
    record={'started_at_utc':now(),'official_registry':REGISTRY,'manifest_sha256':EXPECTED_MODEL,'status':'downloading','parts':[],'research_model_calls':0}
    save(RECORD/'model_download.json',record)
    blobs=OUT/'models/blobs';blobs.mkdir(parents=True,exist_ok=True)
    for part in parts:
        digest=part['digest'].removeprefix('sha256:');path=blobs/('sha256-'+digest)
        if path.is_file() and path.stat().st_size==part['size'] and sha_file(path)==digest:pass
        else:
            tmp=path.with_suffix('.part')
            with urllib.request.urlopen(REGISTRY+'/blobs/sha256:'+digest,timeout=90) as response,tmp.open('wb') as handle:
                shutil.copyfileobj(response,handle,length=4*1024*1024)
            if tmp.stat().st_size!=part['size'] or sha_file(tmp)!=digest:raise ValueError('Model blob digest/size mismatch.')
            tmp.replace(path)
        record['parts'].append({'digest':digest,'size':path.stat().st_size,'sha256_verified':True})
        save(RECORD/'model_download.json',record)
        print(json.dumps({'verified_model_blob_bytes':path.stat().st_size}),flush=True)
    target=OUT/'models/manifests/registry.ollama.ai/library/qwen3/1.7b';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    record.update(status='all_model_blobs_hash_verified',completed_at_utc=now());save(RECORD/'model_download.json',record)

if __name__=='__main__':
    import sys
    {'portable':portable,'model':model}[sys.argv[1]]()
