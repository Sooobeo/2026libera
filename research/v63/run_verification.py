"""Record engineering verification, explicitly separate from experimental runs."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/v63_20261027/audit'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    previous=OUT/'engineering_verification.json'
    if previous.is_file():
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        history=OUT/'verification_history'/stamp
        history.mkdir(parents=True,exist_ok=False)
        for path in [previous,*OUT.glob('test_*.log'),*OUT.glob('test_*.xml')]:
            shutil.copy2(path,history/path.name)
    python=ROOT/'tmp/v63_numerics_venv/Scripts/python.exe'
    if not python.is_file(): python=Path(sys.executable)
    suites=['research.v63.test_numerics','research.v63.test_runtime_retrieval','research.v63.test_statistics','research.v63.test_delivery','research.v63.test_ollama_transport','research.v63.test_campaign','research.v63.test_evaluate']
    records=[]
    for suite in suites:
        filename=suite.split('.')[-1]+'.log'
        junit=OUT/(suite.split('.')[-1]+'.xml')
        command=[str(python),'-m','pytest',suite.replace('.','/')+'.py','-q','--junitxml',str(junit)]
        start=time.perf_counter()
        run=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        log=run.stdout+run.stderr
        (OUT/filename).write_text(log,encoding='utf-8')
        count=sum(int(node.get('tests','0')) for node in ET.parse(junit).getroot().iter('testsuite')) if junit.is_file() else 0
        records.append({'suite':suite,'command':command,'exit_code':run.returncode,
                        'tests':count,'elapsed_seconds':time.perf_counter()-start,
                        'log':(OUT/filename).relative_to(ROOT).as_posix(),
                        'log_sha256':hashlib.sha256((OUT/filename).read_bytes()).hexdigest()})
    result={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'engineering_only':True,
            'scope':'offline automated tests only; separate live connectivity probe is not counted here',
            'real_model_generation_calls':0,'real_fund_experiment_completed':False,
            'status':'passed' if all(r['exit_code']==0 and r['tests']>0 for r in records) else 'failed',
            'tests':sum(r['tests'] for r in records),'suites':records,
            'source_code_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted((ROOT/'research/v63').glob('*.py'))}}
    (OUT/'engineering_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'tests':result['tests'],'real_model_calls':0}))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
