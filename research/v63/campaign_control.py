"""Durable campaign state and a process-held lock; no model or protocol choices."""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib,json,os,time
from pathlib import Path
import shutil

TERMINAL_STATUSES={'completed','model_output_failure','operational_failure'}
BLOCKED_STATUSES={'protocol_violation','recovery_interrupted'}

def immutable_json(path,value):
    path=Path(path)
    if path.exists():
        if json.loads(path.read_text(encoding='utf8'))!=value:raise ValueError('Immutable artifact changed: '+str(path))
    else:atomic_json(path,value)

def verify_frozen_artifacts(root,freeze_path):
    path=Path(freeze_path)
    if not path.exists():return
    frozen=json.loads(path.read_text(encoding='utf8'))
    for ref in frozen.get('artifacts',[]):
        artifact=Path(root)/ref['path']
        if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest()!=ref['sha256']:
            raise ValueError('Previously frozen artifact hash mismatch: '+ref['path'])

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.tmp')
    with temporary.open('w',encoding='utf8',newline='\n') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n');handle.flush();os.fsync(handle.fileno())
    # Windows readers can briefly deny replacement even after the new bytes
    # are flushed. Retry only those sharing/access errors, preserving this
    # same temporary file and the old destination until replacement succeeds.
    deadline=time.monotonic()+30.;delay=.05
    while True:
        try:
            os.replace(temporary,path)
            return
        except OSError as exc:
            if os.name!='nt' or getattr(exc,'winerror',None) not in (5,32,33):raise
            remaining=deadline-time.monotonic()
            if remaining<=0:raise
            time.sleep(min(delay,remaining));delay=min(.5,delay*2)

@contextmanager
def campaign_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b');handle.seek(0,2)
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError as exc:
        handle.close();raise RuntimeError('Another campaign writer holds this run lock.') from exc
    try:yield
    finally:
        handle.seek(0)
        if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        handle.close()

def phase_budget(path,limits):
    for key in ('max_generation_requests','max_wall_seconds'):
        value=limits.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or value<=0:raise ValueError('Invalid phase budget '+key)
    path=Path(path)
    if path.exists():
        state=json.loads(path.read_text(encoding='utf8'))
        if state['limits']!=limits:raise ValueError('Existing phase budget limits changed; an explicit budget amendment is required.')
    else:
        state={'first_started_at_utc':datetime.now(timezone.utc).isoformat(),'limits':limits,
               'wall_clock':'Elapsed UTC since first launch, including downtime; restart never resets the budget.'}
        atomic_json(path,state)
    return state

def budget_elapsed(state):
    elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(state['first_started_at_utc'])).total_seconds()
    if elapsed<0:raise ValueError('System clock moved before the persisted phase start.')
    return elapsed

def task_request_cost(task_dir):
    confirmed=0;uncertain=0
    for folder in Path(task_dir).rglob('attempt_*'):
        if not folder.is_dir():continue
        receipt=folder/'attempt_receipt.json'
        if receipt.is_file():
            try:
                row=json.loads(receipt.read_text(encoding='utf8'));count=row['generation_requests']
                if type(count) is not int or count not in (0,1):raise ValueError('Invalid attempt counter.')
                confirmed+=count;continue
            except (ValueError,KeyError):pass
        # A missing receipt cannot prove that the request was never sent.
        if (folder/'runner_request.bin').exists():uncertain+=1
    return {'generation_requests':confirmed+uncertain,'confirmed_attempt_records':confirmed,'uncertain_dispatch_requests':uncertain}

def final_trace_path(task_dir):
    task_dir=Path(task_dir);pointer=task_dir/'trace_pointer.json'
    if pointer.exists():
        row=json.loads(pointer.read_text(encoding='utf8'));path=(task_dir/row['relative_path']).resolve()
        if task_dir.resolve() not in path.parents:raise ValueError('Trace pointer escaped task directory.')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Trace pointer hash mismatch.')
        value=json.loads(path.read_text(encoding='utf8'))
        return path if value.get('status') in TERMINAL_STATUSES|BLOCKED_STATUSES else None
    path=task_dir/'trajectory/trace.json'
    if path.exists():
        try:
            value=json.loads(path.read_text(encoding='utf8'))
            return path if value.get('status') in TERMINAL_STATUSES|BLOCKED_STATUSES else None
        except (ValueError,OSError):return None  # retained as partial evidence for recovery
    return None

def merged_history(task_dir,destination):
    """Copy prior raw attempts to an immutable replay view OUTSIDE cost ledgers."""
    task_dir=Path(task_dir);destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    sources=[task_dir/'http',*[p/'http' for p in sorted(task_dir.glob('recovery_*')) if p.is_dir()]]
    manifest=[];index=0
    for source in sources:
        if not source.exists():continue
        for attempt in sorted(source.glob('attempt_*')):
            if not attempt.is_dir() or attempt.is_symlink():raise ValueError('Invalid prior HTTP attempt directory.')
            index+=1;target=destination/f'attempt_{index:06d}'
            for member in attempt.rglob('*'):
                if member.is_symlink():raise ValueError('History symlinks are not accepted.')
            shutil.copytree(attempt,target)
            hashes={p.relative_to(attempt).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in attempt.rglob('*') if p.is_file()}
            manifest.append({'source':str(attempt.resolve()),'copied_as':target.name,'file_hashes':hashes})
    atomic_json(destination/'copy_manifest.json',manifest)
    return destination
