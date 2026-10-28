"""Temporary Windows power requests bound to a live selected v6.3 run.

This auxiliary helper never changes power plans, experiment files, or processes.
Use --probe to acquire and immediately release the same documented APIs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from research.observe_v63_candidate_003 import (
    ROOT, RECORD, atomic_text, process_alive, read, windows_process_info,
)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002
POWER_REQUEST_EXECUTION_REQUIRED = 3
HANDOFF_STATUS = 'feasibility_complete_requires_measured_resource_review'
DOCS = [
    'https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate',
    'https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powercreaterequest',
    'https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest',
    'https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powerclearrequest',
    'https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-reason_context',
]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2)+'\n')


class DetailedReason(ctypes.Structure):
    _fields_ = [('module', ctypes.c_void_p), ('reason_id', ctypes.c_uint32),
                ('count', ctypes.c_uint32), ('strings', ctypes.POINTER(ctypes.c_wchar_p))]


class ReasonUnion(ctypes.Union):
    _fields_ = [('detailed', DetailedReason), ('simple', ctypes.c_wchar_p)]


class ReasonContext(ctypes.Structure):
    _fields_ = [('version', ctypes.c_uint32), ('flags', ctypes.c_uint32),
                ('reason', ReasonUnion)]


class PowerRequests:
    """Acquire and clear thread requirements on the same main thread."""

    def __init__(self, reason):
        if os.name != 'nt':
            raise RuntimeError('This helper requires Windows.')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        self.kernel.SetThreadExecutionState.restype = ctypes.c_uint32
        self.kernel.PowerCreateRequest.argtypes = [ctypes.POINTER(ReasonContext)]
        self.kernel.PowerCreateRequest.restype = ctypes.c_void_p
        for name in ('PowerSetRequest', 'PowerClearRequest'):
            function = getattr(self.kernel, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_int]
            function.restype = ctypes.c_int
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.CloseHandle.restype = ctypes.c_int
        self.context = ReasonContext(0, 1, ReasonUnion(simple=reason))
        self.handle = None
        self.thread_active = False
        self.execution_active = False
        self.events = []

    def acquire(self):
        try:
            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            previous = self.kernel.SetThreadExecutionState(flags)
            if not previous:
                raise ctypes.WinError(ctypes.get_last_error())
            self.thread_active = True
            self.events.append({'api':'SetThreadExecutionState', 'flags':flags,
                                'return_value':previous, 'success':True})
            self.handle = self.kernel.PowerCreateRequest(ctypes.byref(self.context))
            if not self.handle or self.handle == ctypes.c_void_p(-1).value:
                self.handle = None
                raise ctypes.WinError(ctypes.get_last_error())
            self.events.append({'api':'PowerCreateRequest', 'success':True})
            if not self.kernel.PowerSetRequest(self.handle, POWER_REQUEST_EXECUTION_REQUIRED):
                raise ctypes.WinError(ctypes.get_last_error())
            self.execution_active = True
            self.events.append({'api':'PowerSetRequest', 'request_type':'PowerRequestExecutionRequired',
                                'success':True})
        except BaseException:
            self.release()
            raise

    def release(self):
        if self.execution_active:
            success = bool(self.kernel.PowerClearRequest(self.handle, POWER_REQUEST_EXECUTION_REQUIRED))
            self.events.append({'api':'PowerClearRequest', 'success':success})
            self.execution_active = False
        if self.handle is not None:
            success = bool(self.kernel.CloseHandle(self.handle))
            self.events.append({'api':'CloseHandle', 'success':success})
            self.handle = None
        if self.thread_active:
            result = self.kernel.SetThreadExecutionState(ES_CONTINUOUS)
            self.events.append({'api':'SetThreadExecutionState', 'flags':ES_CONTINUOUS,
                                'return_value':result, 'success':bool(result)})
            self.thread_active = False


@contextmanager
def kernel_lock(path):
    """One kernel-owned byte-range lock per run, automatically released on exit."""
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def command_tokens(command):
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(pointer)


def process_metadata(pid):
    # Only validated numeric PID is interpolated. No user-provided shell text.
    if type(pid) is not int or pid <= 0:
        return None
    command = ('[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); '
               f'Get-CimInstance Win32_Process -Filter "ProcessId={pid}" | '
               'Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, encoding='utf-8', timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def command_matches(metadata, config_path, role):
    modules = {
        'supervisor':{'research.run_v63_candidate_003_development'},
        'guardian':{'research.v63.longrun_guardian'},
        'campaign':{'research.v63.campaign'},
    }
    if not metadata or Path(metadata.get('ExecutablePath') or '').name.lower() not in ('python.exe','pythonw.exe'):
        return False
    tokens = command_tokens(metadata.get('CommandLine') or '')
    try:
        module = tokens[tokens.index('-m')+1]
        if module not in modules[role]:
            return False
        candidate = tokens[tokens.index('--config')+1] if '--config' in tokens else tokens[tokens.index('-m')+2]
        return (ROOT/candidate).resolve() == config_path
    except (ValueError, IndexError, OSError):
        return False


class RunObserver:
    def __init__(self, config_path):
        self.config_path = (ROOT/config_path).resolve()
        if ROOT not in self.config_path.parents or not self.config_path.parent.name.startswith('candidate_'):
            raise ValueError('Expected candidate configuration inside this workspace.')
        errors = []
        config = read(self.config_path, errors, required=True)
        selection_path = self.config_path.parent/'selection_receipt.json'
        selection = read(selection_path, errors, required=True)
        if config is None or selection is None:
            raise ValueError(str(errors))
        self.run_id = selection['new_run_id']
        if len(self.run_id) != 64 or any(char not in '0123456789abcdef' for char in self.run_id):
            raise ValueError('Invalid selected run ID.')
        self.config_sha = digest(self.config_path)
        self.selection_path = selection_path
        self.selection_sha = digest(selection_path)
        self.output_root = (ROOT/config['output_root']).resolve()
        if ROOT not in self.output_root.parents:
            raise ValueError('Experiment output root must be inside workspace.')
        self.states = {}
        self.identities = {}

    def identity(self, pid, expected, role):
        result = {'pid':pid, 'role':role, 'expected_record_time':expected, 'verified_alive':False}
        alive = process_alive(pid, expected)
        if alive is not True:
            result['verified_alive'] = alive
            return result
        alive, created = windows_process_info(pid)
        if alive is not True or created is None:
            result['verified_alive'] = None if alive else False
            return result
        created_text = created.isoformat()
        key = (pid, role, created_text)
        result['creation_time_utc'] = created_text
        if key not in self.identities:
            try:
                metadata = process_metadata(pid)
                matched = command_matches(metadata, self.config_path, role)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                return {**result, 'verified_alive':None, 'error':str(exc)}
            if not matched:
                return {**result, 'reason':'process_command_or_executable_mismatch'}
            self.identities[key] = metadata
        # Reject a process that exited or was reused during the metadata query.
        alive_after, created_after = windows_process_info(pid)
        return {**result, 'verified_alive':alive_after is True and created_after == created,
                'executable':self.identities[key]['ExecutablePath'],
                'command_line':self.identities[key]['CommandLine']}

    def observe(self):
        if digest(self.config_path) != self.config_sha or digest(self.selection_path) != self.selection_sha:
            return {'decision':'terminal', 'reason':'selected_config_or_run_identity_changed'}
        errors = []
        specs = (
            ('supervisor', self.output_root/'development_supervisor'/self.run_id/'state.json'),
            ('guardian', self.output_root/'guardian'/self.run_id/'checkpoint.json'),
        )
        fresh = {}
        for role, path in specs:
            value = read(path, errors)
            if isinstance(value, dict):
                if value.get('run_id') != self.run_id:
                    errors.append({'path':str(path), 'error':'run_identity_mismatch'})
                    continue
                self.states[role] = value
                fresh[role] = True
        role = 'guardian' if 'guardian' in self.states else 'supervisor'
        state = self.states.get(role, {})
        status = state.get('status')
        observation = {'observed_at_utc':now(), 'controller':role, 'status':status,
                       'state_fresh':fresh.get(role,False), 'read_errors':errors, 'processes':[]}
        if fresh.get(role) and (str(status).startswith('stopped') or status in ('completed','incomplete')):
            return {**observation, 'decision':'terminal', 'reason':'controller_recorded_stop_or_completion'}
        if role == 'guardian':
            targets = [(state.get('pid'), state.get('updated_at_utc'), 'guardian'),
                       (state.get('child_pid'), state.get('updated_at_utc'), 'campaign')]
        else:
            targets = [(state.get('supervisor_pid'), state.get('started_at_utc'), 'supervisor'),
                       (state.get('campaign_pid'), state.get('updated_at_utc'), 'campaign')]
        for pid, expected, target_role in targets:
            if type(pid) is int and pid > 0:
                observation['processes'].append(self.identity(pid, expected, target_role))
        active = status != HANDOFF_STATUS and any(item['verified_alive'] is True for item in observation['processes'])
        return {**observation, 'decision':'active' if active else 'gap',
                'reason':'live_same_candidate_process_verified' if active else 'handoff_or_process_identity_unavailable'}


def keep_decision(observation, monotonic_now, last_active, grace_seconds):
    if observation['decision'] == 'terminal':
        return False, last_active, observation['reason']
    if observation['decision'] == 'active':
        return True, monotonic_now, 'active_experiment'
    if last_active is not None and monotonic_now-last_active < grace_seconds:
        return True, last_active, 'bounded_handoff_grace'
    return False, last_active, 'no_verified_active_experiment_after_grace'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--handoff-grace', type=float, default=120)
    args = parser.parse_args()
    if not 1 <= args.interval <= 30 or not 0 <= args.handoff_grace <= 300:
        parser.error('interval must be 1..30 seconds; handoff-grace must be 0..300 seconds')
    output_dir = (ROOT/args.output_dir).resolve()
    if RECORD not in output_dir.parents:
        parser.error('output-dir must be below research/device_migration_20261027')
    output_dir.mkdir(parents=True, exist_ok=True)
    observer = RunObserver(args.config)
    base = {'schema':'libera_temporary_keepawake_v1', 'started_at_utc':now(), 'pid':os.getpid(),
            'candidate':observer.config_path.parent.name, 'run_id':observer.run_id,
            'config':str(observer.config_path.relative_to(ROOT)), 'config_sha256':observer.config_sha,
            'helper_sha256':digest(__file__), 'docs':DOCS, 'model_calls':0,
            'power_plan_changes':False, 'experiment_or_process_mutation':False,
            'handoff_grace_seconds':args.handoff_grace,
            'limitations':'OS power policy and explicit user sleep still apply; execution request protects this helper, not an exemption for other processes. Display/system requirements prevent automatic idle entry while active.'}
    status_path = output_dir/('probe.json' if args.probe else 'status.json')
    power = PowerRequests('LIBERA 후보 '+observer.config_path.parent.name+' 실행 중 자동 절전 방지')
    last_active = None
    acquired = False
    final_reason = 'helper_exiting'
    observation = {}
    try:
        with kernel_lock(RECORD/'keepawake_locks'/(observer.run_id+'.lock')):
            while True:
                observation = observer.observe()
                keep, last_active, reason = keep_decision(observation, time.monotonic(), last_active, args.handoff_grace)
                if not keep:
                    final_reason = reason
                    break
                if not acquired:
                    power.acquire()
                    acquired = True
                write_json(status_path, {**base, 'updated_at_utc':now(), 'status':'active',
                                        'reason':reason, 'observation':observation, 'api_events':power.events})
                if args.probe:
                    final_reason = 'probe_successfully_acquired_then_released'
                    break
                time.sleep(args.interval)
    except BaseException as exc:
        final_reason = type(exc).__name__+': '+str(exc)
        raise
    finally:
        power.release()
        write_json(status_path, {**base, 'updated_at_utc':now(), 'status':'released',
                                'ever_acquired':acquired, 'reason':final_reason,
                                'observation':observation, 'api_events':power.events})
        print(json.dumps({'status':'released', 'ever_acquired':acquired, 'reason':final_reason}), flush=True)
    return 0 if acquired else 2


if __name__ == '__main__':
    raise SystemExit(main())
