"""Render only the new status HTML; preserve the prior 69-file delivery."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import unquote

from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/artifacts/v491_runtimeprep_20261019'
SOURCE=ROOT/'plan/LIBERA_실행준비현황_v4.9.1_20261019.html'


def ref(path):
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def check_prior():
    prior=json.loads((ROOT/'research/v491_handoff_20261019.json').read_text(encoding='utf-8'))
    assert len(prior['exact_delivery_files'])==69
    assert all(ref(ROOT/r['path'])['sha256']==r['sha256'] for r in prior['exact_delivery_files'])


def cleanup(profile):
    # Profile is a script-created path under the verified ignored preview root.
    assert profile.resolve().is_relative_to((ROOT/'tmp/v491_visual').resolve())
    literal=str(profile).replace("'","''")
    script="$reviewProfile='"+literal+"'; $owned=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -and $_.CommandLine.Contains($reviewProfile) }); $before=@($owned | Select-Object -ExpandProperty ProcessId); $owned | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; $polls=0; do { Start-Sleep -Milliseconds 250; $left=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'chrome.exe' -and $_.CommandLine -and $_.CommandLine.Contains($reviewProfile) } | Select-Object -ExpandProperty ProcessId); $polls+=1 } while ($left.Count -gt 0 -and $polls -lt 20); @{ targeted_pids=$before; remaining_pids=$left; cleanup_polls=$polls } | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('Owned profile cleanup failed: '+result.stderr)
    evidence=json.loads(result.stdout)
    if evidence['remaining_pids']:
        raise RuntimeError('Owned headless processes remain; do not start another browser')
    return evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-profile-root',type=Path)
    args=parser.parse_args()
    check_prior()
    original=ref(SOURCE)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    preview_root=args.resume_profile_root.resolve() if args.resume_profile_root else ROOT/'tmp/v491_visual'/('runtimeprep_status_'+stamp)
    assert preview_root.is_relative_to((ROOT/'tmp/v491_visual').resolve())
    if args.resume_profile_root:
        assert preview_root.is_dir()
    else:
        preview_root.mkdir(parents=True,exist_ok=False)
    captures=[]
    for name,size in [('status_desktop','1360,3000'),('status_narrow','600,5000')]:
        profile=preview_root/(name+'_profile')
        target=OUT/(name+'.png')
        if target.exists():
            if not args.resume_profile_root or target.stat().st_mtime<SOURCE.stat().st_mtime:
                raise RuntimeError('Do not overwrite an earlier status capture or reuse one older than source')
            cleaned=cleanup(profile)
            captures.append({'image':ref(target),'viewport':size,'source':original,'owned_profile':profile.relative_to(ROOT).as_posix(),'cleanup':cleaned,'reused_after_initial_cleanup_check':True})
            continue
        command=['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--hide-scrollbars','--force-device-scale-factor=1','--virtual-time-budget=1000','--window-size='+size,'--user-data-dir='+str(profile),'--screenshot='+str(target),SOURCE.as_uri()]
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        stable=0;last_size=None;deadline=time.monotonic()+40
        try:
            while time.monotonic()<deadline:
                if target.exists():
                    now_size=target.stat().st_size
                    stable=stable+1 if now_size==last_size and now_size>0 else 0
                    last_size=now_size
                    if stable>=3:break
                time.sleep(.25)
            if stable<3:raise RuntimeError('Capture not completed: '+name)
        finally:
            cleaned=cleanup(profile)
        captures.append({'image':ref(target),'viewport':size,'source':original,'owned_profile':profile.relative_to(ROOT).as_posix(),'cleanup':cleaned,'initial_browser_pid':process.pid})
    soup=BeautifulSoup(SOURCE.read_text(encoding='utf-8'),'html.parser')
    links=[]
    for anchor in soup.find_all('a',href=True):
        href=anchor['href']
        if '://' in href:continue
        target=(SOURCE.parent/unquote(href.split('#')[0])).resolve()
        valid=target.is_relative_to(ROOT) and target.is_file()
        links.append({'href':href,'exists_inside_workspace':valid})
        if not valid:raise RuntimeError('Broken local link: '+href)
    assert ref(SOURCE)==original
    check_prior()
    receipt={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'source':original,'captures':captures,'local_link_checks':links,'prior_69_files_unchanged':True,'model_calls':0,'headless_instances_in_parallel':1,'visual_review_completed':False,'scope':'Actual new status page at desktop and 600px; no prior design or paper edits.','initial_incident':'Initial desktop screenshot completed. Immediate post-Stop-Process inventory briefly showed a terminating owned Chrome process, so the first helper stopped. Subsequent exact-profile inventory found zero. Cleanup now waits with bounded short polls; original desktop image was retained without overwrite and source mtime predates capture.' if args.resume_profile_root else None}
    (OUT/'status_capture_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'captures':len(captures),'local_links':len(links),'prior_files_unchanged':True}))


if __name__=='__main__':main()
