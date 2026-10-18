"""Download the authorized local target and record metadata; never runs inference."""
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
TARGET='qwen3.6:35b'
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=ROOT/'data/sector_runtime'/('install_'+stamp)
    folder.mkdir(parents=True,exist_ok=False)
    host=os.environ.get('OLLAMA_HOST','http://localhost:11434')
    if '://' not in host:host='http://'+host
    host=host.rstrip('/')
    def save(name,data):
        (folder/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def call(endpoint,body=None):
        req=urllib.request.Request(host+endpoint,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    save('before.json',{'version':call('/api/version'),'models':call('/api/tags'),'inference_calls':0})
    start=time.monotonic();last=0;prior_status=None;terminal=None
    req=urllib.request.Request(host+'/api/pull',data=json.dumps({'model':TARGET,'stream':True}).encode(),headers={'Content-Type':'application/json'})
    print('Pulling '+TARGET+'; records: '+str(folder.relative_to(ROOT)),flush=True)
    try:
        with urllib.request.urlopen(req,timeout=120) as response,(folder/'pull_events.jsonl').open('w',encoding='utf-8') as log:
            for line in response:
                event=json.loads(line);log.write(json.dumps(event)+'\n');log.flush()
                if event.get('error'):raise RuntimeError(event['error'])
                terminal=event;now=time.monotonic();status=event.get('status')
                if now-last>=30 or status!=prior_status:
                    total=event.get('total',0);done=event.get('completed',0)
                    print(json.dumps({'elapsed_seconds':round(now-start),'status':status,'completed_GB':round(done/1e9,2),'total_GB':round(total/1e9,2),'percent':round(done/total*100,1) if total else None}),flush=True)
                    last=now;prior_status=status
        if not terminal or terminal.get('status')!='success':raise RuntimeError('Pull ended without success event')
        tags=call('/api/tags');selected=next(m for m in tags['models'] if m['name']==TARGET)
        show=call('/api/show',{'model':TARGET})
        save('model_show.json',show)
        save('result.json',{'status':'installed','model':selected,'engine':call('/api/version'),'elapsed_seconds':time.monotonic()-start,'template_sha256':hashlib.sha256(show.get('template','').encode()).hexdigest(),'inference_calls':0})
        print(json.dumps({'status':'installed','digest':selected['digest'],'bytes':selected['size'],'folder':str(folder.relative_to(ROOT))}),flush=True)
    except Exception as exc:
        save('failure.json',{'type':type(exc).__name__,'message':str(exc),'elapsed_seconds':time.monotonic()-start,'inference_calls':0})
        raise
if __name__=='__main__':main()
