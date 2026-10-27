"""User-requested pause: suspend only the owned caller at a durable HTTP boundary."""
import ctypes,json,time,hashlib,os
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
RUN_ID='de1b479b54d5b4429211059df1496be588c3c5af81ec21f4d4c355e3004f76ec'
RUN=ROOT/'data/v63_20261027/local_campaign_results/runs'/RUN_ID
TASK=RUN/'B-development/development-001__F03__R2__1'
ATTEMPT=TASK/'http/attempt_000001'
OUT=ROOT/'data/v63_20261027/continuation/pause_20261027'
PID=20340
kernel=ctypes.windll.kernel32;nt=ctypes.windll.ntdll
kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_ulong)]
nt.NtSuspendProcess.argtypes=[ctypes.c_void_p];nt.NtSuspendProcess.restype=ctypes.c_long
kernel.CloseHandle.argtypes=[ctypes.c_void_p]
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(value):
    path=OUT/'pause_boundary.json';temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf8') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
def open_owned(pid,expected_suffix):
    handle=kernel.OpenProcess(0x0800|0x1000,False,pid)
    if not handle:raise OSError('Cannot open owned process '+str(pid))
    name=ctypes.create_unicode_buffer(32768);length=ctypes.c_ulong(len(name))
    if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(length)) or not name.value.lower().endswith(expected_suffix.lower()):
        kernel.CloseHandle(handle);raise ValueError('Unexpected process executable.')
    return handle,name.value
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'pause_boundary.json').exists():raise ValueError('Existing pause boundary record.')
    handle,path=open_owned(PID,r'\Python312\python.exe')
    before=sorted(str(p.relative_to(RUN)) for p in RUN.rglob('generation.dispatch_started.json'))
    record={'status':'waiting_for_current_receipt_only','requested_at_utc':now(),'campaign_pid':PID,'campaign_image':path,
            'current_attempt':str(ATTEMPT),'dispatches_before':before,'new_model_requests_authorized':0}
    save(record);deadline=time.monotonic()+600
    try:
        while time.monotonic()<deadline:
            if (ATTEMPT/'attempt_receipt.json').exists():
                status=nt.NtSuspendProcess(handle)
                if status!=0:raise OSError('NtSuspendProcess failed '+str(status))
                record.update(status='campaign_suspended_at_durable_receipt',suspended_at_utc=now(),ntstatus=status)
                # The atomic attempt receipt follows all raw responses and both identity checks.
                files=[p for p in ATTEMPT.rglob('*') if p.is_file()]
                record['attempt_files_sha256']={p.relative_to(ATTEMPT).as_posix():sha(p) for p in files}
                raw=json.loads((ATTEMPT/'generation.response.bin').read_bytes())
                record['response_metadata']={k:raw.get(k) for k in ('done','done_reason','prompt_eval_count','eval_count','total_duration')}
                after=sorted(str(p.relative_to(RUN)) for p in RUN.rglob('generation.dispatch_started.json'))
                record['dispatches_after']=after;record['new_dispatches_since_pause_request']=[p for p in after if p not in before]
                record['safe_boundary']=not record['new_dispatches_since_pause_request'] and raw.get('done') is True
                save(record);print(json.dumps(record),flush=True);return
            time.sleep(.001)
        status=nt.NtSuspendProcess(handle)
        record.update(status='campaign_suspended_inflight_boundary_timeout',ntstatus=status,safe_boundary=False,recorded_at_utc=now())
        save(record);print(json.dumps(record),flush=True)
    finally:kernel.CloseHandle(handle)

if __name__=='__main__':main()
