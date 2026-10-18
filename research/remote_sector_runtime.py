"""Stdlib Linux coordinator: explicit inventory, pull, diagnosis or pilot only.

No gold/reference annotations, offline scoring, main execution, server changes,
model substitutions or automatic retries. Run with --help for the interface.
A file named CANCEL in the exclusive output directory cooperatively cancels the
current request. Ctrl+C does the same. An unload request does not stop Ollama.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'qwen3.5:4b-q4_K_M'
EXPECTED_DIGEST = 'd8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04'
EXPECTED_ENGINE = '0.35.1'
DEFAULT_URL = 'http://127.0.0.1:11434'
PILOT_SOURCES = ('fidelity_q2_2026', 'ubs_june_2026')
PROCESS_NAMES = frozenset(('ollama', 'ollama_llama_server', 'llama-server'))
MEMORY_KEYS = ('MemTotal', 'MemAvailable', 'MemFree', 'SwapTotal', 'SwapFree',
               'Committed_AS', 'CommitLimit', 'Cached', 'Buffers')
PROCESS_KEYS = ('VmRSS', 'VmHWM', 'VmSize', 'RssAnon', 'RssFile', 'RssShmem')


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_origin(value):
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('base-url must be an HTTP(S) origin')
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise ValueError('base-url cannot contain credentials, paths, queries or fragments')
    _ = parts.port  # Validate the port without connecting.
    return value.rstrip('/')


def new_output(root, command, run_id=None):
    root = Path(root).resolve()
    run_id = run_id or (command + '_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', run_id):
        raise ValueError('run-id must be a simple alphanumeric filename')
    target = (root / run_id).resolve()
    if target.parent != root:
        raise ValueError('Output must be a direct child of output-root')
    root.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Existing outputs are never reused, overwritten or resumed.
    return target


def connect(origin, timeout):
    parts = urlsplit(validate_origin(origin))
    cls = http.client.HTTPSConnection if parts.scheme == 'https' else http.client.HTTPConnection
    return cls(parts.hostname, parts.port, timeout=timeout)


def api_json(origin, path, body=None, timeout=5):
    conn = connect(origin, timeout)
    try:
        conn.request('GET' if body is None else 'POST', path,
                     None if body is None else json.dumps(body).encode('utf-8'),
                     {'Content-Type': 'application/json'})
        response = conn.getresponse()
        raw = response.read()
        if not 200 <= response.status < 300:
            raise RuntimeError(f'HTTP {response.status}: {raw[:1000]!r}')
        value = json.loads(raw)
        if isinstance(value, dict) and value.get('error'):
            raise RuntimeError('Ollama error: ' + str(value['error']))
        return value
    finally:
        conn.close()


def optional_api(origin, path, body=None, timeout=2):
    try:
        return {'status': 'ok', 'value': api_json(origin, path, body, timeout)}
    except Exception as exc:
        return {'status': 'unavailable', 'error_type': type(exc).__name__, 'error': str(exc)}


def kv_bytes(text, keys):
    result = {}
    for line in text.splitlines():
        key, sep, value = line.partition(':')
        if sep and key in keys:
            pieces = value.split()
            if pieces:
                result[key + '_bytes'] = int(pieces[0]) * (1024 if len(pieces) > 1 and pieces[1] == 'kB' else 1)
    return result


def memory_snapshot(proc_root=Path('/proc'), cgroup_root=Path('/sys/fs/cgroup')):
    """Retain memory statistics only for named runtime processes; never cmdlines.

    /proc and cgroup report different scopes in containers. Neither process RSS
    sums nor host memory are substitutes for the container's allocation limit.
    """
    result = {'observed_at_utc': now(), 'source': 'linux_proc_and_cgroup', 'processes': []}
    try:
        result['proc_meminfo'] = kv_bytes((proc_root / 'meminfo').read_text(), MEMORY_KEYS)
    except (OSError, ValueError) as exc:
        result['proc_meminfo_error'] = str(exc)
    for location, names in ((cgroup_root, ('memory.current', 'memory.peak', 'memory.max',
                                         'memory.swap.current', 'memory.swap.max', 'memory.events')),
                            (cgroup_root / 'memory', ('memory.usage_in_bytes', 'memory.limit_in_bytes',
                                                     'memory.max_usage_in_bytes', 'memory.failcnt'))):
        for name in names:
            try:
                raw = (location / name).read_text().strip()
                result.setdefault('cgroup', {})[name] = int(raw) if raw.isdigit() else raw
            except OSError:
                pass
    try:
        entries = proc_root.iterdir()
        for path in entries:
            if not path.name.isdigit():
                continue
            try:
                comm = (path / 'comm').read_text().strip()
                try:
                    executable = Path(os.readlink(path / 'exe')).name.removesuffix(' (deleted)')
                except OSError:
                    executable = comm
                if executable not in PROCESS_NAMES:
                    continue
                status = (path / 'status').read_text()
                result['processes'].append({'pid': int(path.name), 'name': executable,
                                            **kv_bytes(status, PROCESS_KEYS)})
            except (OSError, ValueError):
                continue  # Processes can exit while the read-only sample is taken.
    except OSError as exc:
        result['process_inventory_error'] = str(exc)
    result['rss_sum_bytes'] = sum(x.get('VmRSS_bytes', 0) for x in result['processes'])
    result['interpretation'] = 'RSS can double-count shared pages; cgroup includes cache and other processes; no GPU-memory inference from RSS.'
    return result


def inventory(origin, destination):
    cpu = {}
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            key, sep, val = line.partition(':')
            if sep and key.strip() in ('model name', 'vendor_id'):
                cpu[key.strip()] = val.strip()
    except OSError:
        pass
    disk = shutil.disk_usage(destination)
    return {'observed_at_utc': now(), 'platform': platform.system(), 'machine': platform.machine(),
            'cpu': cpu, 'os_cpu_count': os.cpu_count(), 'memory': memory_snapshot(),
            'filesystem_bytes': {'total': disk.total, 'used': disk.used, 'free': disk.free},
            'filesystem_scope': 'Container-visible filesystem only; shared host thin-pool free space must be checked separately.',
            'ollama_version': optional_api(origin, '/api/version'),
            'ollama_tags': optional_api(origin, '/api/tags'),
            'ollama_residency': optional_api(origin, '/api/ps')}


class Cancelled(RuntimeError):
    pass


class RemoteCallError(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__(result.get('error', result['status']))


class ProtocolViolation(RuntimeError):
    pass


class Session:
    def __init__(self, target, origin, timeout_seconds=1800, monitor_seconds=2):
        self.target = Path(target)
        self.origin = validate_origin(origin)
        self.timeout_seconds = timeout_seconds
        self.monitor_seconds = monitor_seconds
        self.started = time.monotonic()
        self.cancel_event = threading.Event()
        self.monitor_stop = threading.Event()
        self.monitor_thread = None
        self.calls = []

    def cancelled(self):
        return self.cancel_event.is_set() or (self.target / 'CANCEL').exists()

    def check_cancel(self):
        if self.cancelled():
            raise Cancelled('Cancellation requested; no additional model requests will be made')

    def start_monitor(self):
        def monitor():
            with (self.target / 'monitor.jsonl').open('x', encoding='utf-8') as handle:
                while not self.monitor_stop.is_set():
                    start = time.monotonic()
                    sample = {'elapsed_seconds': start - self.started, 'memory': memory_snapshot(),
                              'ollama_ps': optional_api(self.origin, '/api/ps', timeout=1)}
                    handle.write(json.dumps(sample, allow_nan=False) + '\n')
                    handle.flush()
                    self.monitor_stop.wait(max(0, self.monitor_seconds - (time.monotonic() - start)))
        self.monitor_thread = threading.Thread(target=monitor, name='memory-monitor', daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self):
        self.monitor_stop.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=4)


def metrics(terminal, elapsed, first_any, first_content):
    result = {'wall_seconds': elapsed, 'ttft_any_generated_seconds': first_any,
              'ttft_content_seconds': first_content,
              'token_count_source': 'Ollama counters, not independent tokenization',
              'duration_unit_in_response': 'nanoseconds'}
    for name in ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration'):
        value = terminal.get(name)
        if isinstance(value, (int, float)):
            result[name + '_seconds'] = value / 1_000_000_000
    for name in ('prompt_eval_count', 'eval_count'):
        if name in terminal:
            result[name] = terminal[name]
    for prefix in ('prompt_eval', 'eval'):
        count, duration = terminal.get(prefix + '_count'), terminal.get(prefix + '_duration')
        result[prefix + '_tokens_per_second'] = count / (duration / 1e9) if isinstance(count, (int, float)) and isinstance(duration, (int, float)) and duration > 0 else None
    return result


def stream_call(session, path, body, kind):
    """One request, raw bytes flushed as received; deadline includes stream time.

    A watchdog shuts down this request's socket, never the server or other jobs.
    Partial bytes and parsed events survive timeout, HTTP error and cancellation.
    """
    session.check_cancel()
    folder = session.target / ('http_%04d_%s' % (len(session.calls) + 1, kind))
    folder.mkdir()
    save(folder / 'request.json', {'path': path, 'body': body, 'kind': kind})
    start = time.monotonic()
    call = {'kind': kind, 'folder': folder.name, 'started_at_utc': now(), 'status': 'attempted'}
    session.calls.append(call)
    conn = connect(session.origin, session.timeout_seconds)
    state = {'socket': None, 'reason': None}
    finished = threading.Event()
    terminal = {}
    content, thinking, tool_calls = [], [], []
    first_any = first_content = None
    buffer = b''
    generated = None

    def disconnect():
        sock = state['socket'] or conn.sock
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        conn.close()

    def watch():
        while not finished.wait(0.1):
            if session.cancelled():
                state['reason'] = 'cancelled'
            elif time.monotonic() - start >= session.timeout_seconds:
                state['reason'] = 'timeout'
            if state['reason']:
                disconnect()
                # Keep checking until the request exits: cancellation can race
                # the initial connection, before a socket has been assigned.

    watcher = threading.Thread(target=watch, name='request-deadline', daemon=True)
    watcher.start()
    try:
        with (folder / 'raw_stream.bin').open('xb') as raw_file, (folder / 'events.jsonl').open('x', encoding='utf-8') as events:
            conn.request('POST', path, json.dumps(body, ensure_ascii=False, allow_nan=False).encode(), {'Content-Type': 'application/json'})
            state['socket'] = conn.sock
            response = conn.getresponse()
            call['http_status'] = response.status
            done = False
            while not done:
                chunk = response.read1(65536)
                if not chunk:
                    if buffer.strip():
                        # A complete last JSON line need not have a trailing newline.
                        chunk = b'\n'
                    else:
                        break
                else:
                    raw_file.write(chunk)
                    raw_file.flush()
                buffer += chunk
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if not line.strip():
                        continue
                    event = json.loads(line.decode('utf-8'))
                    events.write(json.dumps({'elapsed_seconds': time.monotonic() - start, 'event': event}, ensure_ascii=False, allow_nan=False) + '\n')
                    events.flush()
                    if not isinstance(event, dict):
                        raise ValueError('Ollama stream event must be an object')
                    if event.get('error'):
                        raise RuntimeError('Ollama stream error: ' + str(event['error']))
                    message = event.get('message', {})
                    if message.get('content'):
                        content.append(message['content'])
                        if first_content is None:
                            first_content = time.monotonic() - start
                    if message.get('thinking'):
                        thinking.append(message['thinking'])
                    if message.get('content') or message.get('thinking'):
                        if first_any is None:
                            first_any = time.monotonic() - start
                    tool_calls.extend(message.get('tool_calls', []))
                    if (kind == 'pull' and event.get('status') == 'success') or (kind != 'pull' and event.get('done') is True):
                        terminal = event
                        done = True
                if done:
                    break
            if not 200 <= response.status < 300:
                raise RuntimeError('HTTP status ' + str(response.status))
            if state['reason']:
                raise Cancelled(state['reason'])
            if not done:
                raise RuntimeError('Stream ended without a terminal success/done event')
            generated = dict(terminal)
            if kind != 'pull':
                generated['message'] = {'role': 'assistant', 'content': ''.join(content)}
                if thinking:
                    generated['message']['thinking'] = ''.join(thinking)
                if tool_calls:
                    generated['message']['tool_calls'] = tool_calls
            call['status'] = 'completed'
    except KeyboardInterrupt:
        session.cancel_event.set()
        state['reason'] = 'cancelled'
        disconnect()
        call.update(status='cancelled', error='KeyboardInterrupt')
    except Exception as exc:
        timeout = isinstance(exc, (TimeoutError, socket.timeout)) or time.monotonic() - start >= session.timeout_seconds
        call.update(status=state['reason'] or ('timeout' if timeout else 'failed'),
                    error_type=type(exc).__name__, error=str(exc))
    finally:
        finished.set()
        disconnect()
        watcher.join(timeout=2)
        call['metrics'] = metrics(terminal, time.monotonic() - start, first_any, first_content)
        call['raw_bytes_path'] = str((folder / 'raw_stream.bin').relative_to(session.target))
        call['no_automatic_retry'] = True
        call['unexpected_thinking_with_disabled_request'] = body.get('think') is False and bool(thinking)
        if generated is not None:
            save(folder / 'response.json', generated)
        if content or thinking:
            save(folder / 'assembled_text.json', {'content': ''.join(content), 'thinking': ''.join(thinking), 'complete': call['status'] == 'completed'})
        save(folder / 'result.json', call)
    if call['status'] != 'completed':
        raise RemoteCallError(call)
    return generated


def observed_model(origin):
    version = api_json(origin, '/api/version')
    tags = api_json(origin, '/api/tags')
    matches = [m for m in tags.get('models', []) if m.get('name') == MODEL]
    if len(matches) != 1:
        raise RuntimeError('Exact target tag is not installed once; no substitute is permitted')
    selected = matches[0]
    if selected.get('digest', '').removeprefix('sha256:') != EXPECTED_DIGEST:
        raise RuntimeError('Installed target manifest does not equal the approved digest')
    if version.get('version') != EXPECTED_ENGINE:
        raise RuntimeError('Engine version differs from observed 0.35.1; record a runtime revision first')
    show = api_json(origin, '/api/show', {'model': MODEL})
    if not isinstance(show.get('template'), str):
        raise ValueError('Ollama show did not return a reproducible template string')
    quantization = show.get('details', {}).get('quantization_level', selected.get('details', {}).get('quantization_level'))
    if quantization != 'Q4_K_M':
        raise RuntimeError('Installed model is not the approved Q4_K_M variant')
    return {'version': version, 'selected_model': selected, 'show': show,
            'template_sha256': hashlib.sha256(show['template'].encode()).hexdigest()}


def pin_runtime(session):
    from run_sector_workflow import runtime_candidate_v43, validate_runtime
    observed = observed_model(session.origin)
    value = runtime_candidate_v43()
    value.update(base_url=session.origin, digest=EXPECTED_DIGEST, engine_version=EXPECTED_ENGINE,
                 template_sha256=observed['template_sha256'], timeout_seconds=session.timeout_seconds,
                 status='metadata_pinned; no claim of diagnosis or completed pilot', pinned_at_utc=now(),
                 intended_split='pilot', main_authorized_by_this_file=False,
                 timeout_basis='Engineering cancellation limit per request; not a paper condition')
    validate_runtime(value)
    save(session.target / 'model_metadata.json', observed)
    save(session.target / 'runtime_pinned.json', value)
    return value


def verify_runtime(session, runtime):
    from run_sector_workflow import validate_runtime
    validate_runtime(runtime)
    if runtime.get('protocol_version') != '4.3' or runtime.get('model') != MODEL:
        raise ValueError('Only the explicitly approved v4.3 model is supported')
    if runtime.get('context_tokens') != 65536 or runtime.get('timeout_seconds') != session.timeout_seconds:
        raise ValueError('Context or timeout differs from this coordinator invocation; record a new runtime revision')
    if validate_origin(runtime.get('base_url', DEFAULT_URL)) != session.origin:
        raise ValueError('Pinned base_url differs from the explicit coordinator endpoint')
    observed = observed_model(session.origin)
    expected = {'digest': EXPECTED_DIGEST, 'engine_version': EXPECTED_ENGINE,
                'template_sha256': observed['template_sha256']}
    if any(runtime.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Pinned model, engine or template changed; no model request made')
    return observed


def unload(session):
    # Empty generate is the documented unload request; no prompt or inference.
    return optional_api(session.origin, '/api/generate', {'model': MODEL, 'keep_alive': 0}, timeout=5)


def diagnose(session, runtime):
    verify_runtime(session, runtime)
    request = {'model': MODEL, 'stream': True, 'think': False, 'format': 'json', 'keep_alive': 0,
               'messages': [{'role': 'user', 'content': 'Return exactly this JSON object: {"ready":true}'}],
               'options': {'temperature': 0, 'num_predict': 256, 'num_ctx': 65536}}
    response = stream_call(session, '/api/chat', request, 'diagnose')
    content = response['message']['content']
    try:
        parsed = json.loads(content)
        valid = isinstance(parsed, dict) and set(parsed) == {'ready'} and parsed['ready'] is True
    except (ValueError, TypeError):
        valid = False
    unexpected_thinking = bool(response['message'].get('thinking'))
    result = {'status': 'completed' if valid and response.get('done_reason') != 'length' and not unexpected_thinking else 'diagnostic_response_failed',
              'synthetic_health_prompt_only': True, 'json_ready_response': valid,
              'unexpected_thinking_with_disabled_request': unexpected_thinking,
              'done_reason': response.get('done_reason'), 'diagnostic_calls': 1,
              'pilot_model_calls': 0, 'main_model_calls': 0,
              'settings_basis': '256 output tokens and 65536 context are engineering diagnostics, not paper conditions.',
              'interpretation': 'One short response does not establish complete four-stage feasibility or research quality.'}
    save(session.target / 'diagnosis.json', result)
    return result


def load_pilot_inputs(packet_path, market_path):
    # Only public model packets and market data are opened. No evaluator import.
    for path in (packet_path, market_path):
        if 'evaluator_only' in Path(path).resolve().parts:
            raise ValueError('Evaluator-only input is forbidden in the remote coordinator')
    corpus = [json.loads(line) for line in Path(packet_path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    chosen = [p for p in corpus if p.get('split') == 'pilot']
    ids = [p.get('source_id') for p in chosen]
    if len(ids) != 2 or set(ids) != set(PILOT_SOURCES):
        raise ValueError('Expected exactly the two named pilot sources, once each')
    if any('evidence_passages' not in p or 'sector_ratings' in p or 'evidence_index' in p for p in chosen):
        raise ValueError('Expected public evidence packets, not reference annotations or pre-labeled gold')
    return [next(p for p in chosen if p['source_id'] == source) for source in PILOT_SOURCES], read(market_path)


def pilot(session, runtime, packet_path, market_path):
    from run_sector_workflow import run_case, conservative_context_bound
    # The coordinator is stdlib-only, but the existing arithmetic engine needs
    # NumPy. Fail before any case attempt or generation if it is unavailable.
    import sector_engine
    verify_runtime(session, runtime)
    corpus, market = load_pilot_inputs(packet_path, market_path)
    destination = session.target / 'pilot'
    destination.mkdir()
    save(destination / 'runtime.json', {'settings': runtime, 'split': 'pilot', 'coordinator': 'remote_sector_runtime.py'})
    save(destination / 'dependencies.json', {'python_version': platform.python_version(),
                                           'numpy_version': sector_engine.np.__version__,
                                           'coordinator_standard_library_only': True,
                                           'pilot_engine_dependency': 'numpy'})
    save(destination / 'input_hashes.json', {'packets_sha256': sha(packet_path), 'market_sha256': sha(market_path),
                                          'coordinator_sha256': sha(Path(__file__)),
                                          'runner_sha256': sha(Path(__file__).with_name('run_sector_workflow.py')),
                                          'engine_sha256': sha(Path(__file__).with_name('sector_engine.py'))})
    cases = []
    for packet in corpus:
        for arm in ('R1', 'R4'):
            cases.append({'case_id': packet['source_id'] + '__' + arm, 'source_id': packet['source_id'],
                          'arm': arm, 'status': 'not_started'})
    save(destination / 'planned_cases.json', cases)
    for row in cases:
        if session.cancelled():
            break
        packet = next(p for p in corpus if p['source_id'] == row['source_id'])
        row['status'] = 'attempted'
        calls_before = len(session.calls)

        def adapter(messages):
            session.check_cancel()
            try:
                verify_runtime(session, runtime)  # Exact three pins before every inference call.
            except Exception as exc:
                raise ProtocolViolation('Pinned runtime could not be verified before request: ' + str(exc)) from exc
            upper = conservative_context_bound(messages)
            if upper + runtime['max_output_tokens'] > runtime['context_tokens']:
                raise RuntimeError('Conservative UTF-8 screening estimate plus output allowance exceeds context; not a tokenizer count; no truncation or retry')
            body = {'model': MODEL, 'messages': messages, 'stream': True, 'think': runtime['thinking'],
                    'format': 'json', 'keep_alive': 0,
                    'options': {'temperature': runtime['temperature'], 'num_predict': runtime['max_output_tokens'],
                                'num_ctx': runtime['context_tokens']}}
            raw = stream_call(session, '/api/chat', body, 'pilot')
            if raw['message'].get('thinking'):
                raise ProtocolViolation('Provider returned nonempty thinking despite think=false; full response remains in the HTTP call artifact; stop remaining pilot cases')
            return raw

        try:
            run_case(packet, row['arm'], market, adapter, destination / row['case_id'],
                     history_policy=runtime['history_policy'])
            row['status'] = 'completed'
        except KeyboardInterrupt:
            session.cancel_event.set()
            row.update(status='failed', error_type='KeyboardInterrupt', error='Cancelled between requests or while processing a response')
            save(destination / (row['case_id'] + '_coordinator_failure.json'), row)
        except Exception as exc:
            row.update(status='failed', error_type=type(exc).__name__, error=str(exc))
            save(destination / (row['case_id'] + '_coordinator_failure.json'), row)
            if isinstance(exc, RemoteCallError) and exc.result['status'] in ('timeout', 'cancelled'):
                session.cancel_event.set()  # Do not start another long case after a resource timeout.
            if isinstance(exc, ProtocolViolation):
                session.cancel_event.set()
        row['model_calls_attempted'] = len(session.calls) - calls_before
        row['http_call_folders'] = [c['folder'] for c in session.calls[calls_before:]]
    result = {'split': 'pilot', 'planned_runs': 4, 'attempted_runs': sum(r['status'] != 'not_started' for r in cases),
              'completed_runs': sum(r['status'] == 'completed' for r in cases), 'records': cases,
              'pilot_model_calls': sum(c['kind'] == 'pilot' for c in session.calls), 'main_model_calls': 0,
              'status': 'completed' if all(r['status'] == 'completed' for r in cases) else 'incomplete',
              'failure_policy': 'Raw and attempted cases retained; not-started cases are not observed model errors; no retry.',
              'evaluation_status': 'Not scored remotely; no gold uploaded or read; semantic human review remains separate.'}
    save(destination / 'summary.json', result)
    return result


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument('command', choices=('inventory', 'pull', 'diagnose', 'pilot'))
    value.add_argument('--base-url', default=DEFAULT_URL, help='Explicit override only; OLLAMA_HOST is ignored')
    value.add_argument('--output-root', type=Path, default=ROOT / 'data/sector_runtime')
    value.add_argument('--run-id')
    value.add_argument('--runtime', type=Path, help='Previously pinned runtime; required for pilot')
    value.add_argument('--pin-runtime', action='store_true', help='With inventory, pin an already installed exact model')
    value.add_argument('--timeout-seconds', type=float, default=1800, help='Engineering per-request deadline, not a paper parameter')
    value.add_argument('--packets', type=Path, default=ROOT / 'data/sector_documents/model_packets.jsonl')
    value.add_argument('--market', type=Path, default=ROOT / 'data/sector_market/market_input.json')
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    origin = validate_origin(args.base_url)
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0 or args.timeout_seconds > 86400:
        raise ValueError('timeout-seconds must be greater than zero and at most 86400')
    if args.command == 'pilot' and not args.runtime:
        raise ValueError('pilot requires an explicit --runtime from a completed metadata pin')
    target = new_output(args.output_root, args.command, args.run_id)
    session = Session(target, origin, args.timeout_seconds)
    save(target / 'invocation.json', {'command': args.command, 'base_url': origin, 'model': MODEL,
                                    'expected_digest': EXPECTED_DIGEST, 'expected_engine': EXPECTED_ENGINE,
                                    'timeout_seconds': args.timeout_seconds, 'monitor_interval_seconds': 2,
                                    'monitor_basis': 'Engineering diagnostic interval', 'started_at_utc': now(),
                                    'call_count_scope': 'Attempted HTTP generation requests; requests failing before a response do not prove model execution.',
                                    'main_automatic_execution': False})
    result = {'command': args.command, 'status': 'failed', 'output': str(target), 'main_model_calls': 0}
    try:
        save(target / 'inventory_before.json', inventory(origin, target))
        session.start_monitor()
        if args.command == 'inventory':
            if args.pin_runtime:
                pin_runtime(session)
            result.update(status='completed', metadata_pinned=args.pin_runtime, diagnostic_calls=0, pilot_model_calls=0)
        elif args.command == 'pull':
            stream_call(session, '/api/pull', {'model': MODEL, 'stream': True}, 'pull')
            pin_runtime(session)
            result.update(status='completed', metadata_pinned=True, diagnostic_calls=0, pilot_model_calls=0)
        else:
            runtime = copy.deepcopy(read(args.runtime)) if args.runtime else pin_runtime(session)
            if args.runtime:
                save(target / 'runtime_pinned.json', runtime)
            if args.command == 'diagnose':
                result.update(diagnose(session, runtime))
            else:
                result.update(pilot(session, runtime, args.packets, args.market))
    except KeyboardInterrupt:
        session.cancel_event.set()
        result.update(status='cancelled', error='KeyboardInterrupt')
    except Exception as exc:
        result.update(status='cancelled' if session.cancelled() else 'failed',
                      error_type=type(exc).__name__, error=str(exc))
    finally:
        if any(c['kind'] in ('diagnose', 'pilot') for c in session.calls):
            save(target / 'unload_result.json', unload(session))
        session.stop_monitor()
        save(target / 'inventory_after.json', inventory(origin, target))
        result.update(finished_at_utc=now(), script_wall_seconds=time.monotonic() - session.started,
                      diagnostic_calls=sum(c['kind'] == 'diagnose' for c in session.calls),
                      pilot_model_calls=sum(c['kind'] == 'pilot' for c in session.calls),
                      main_model_calls=0, calls=session.calls)
        save(target / 'summary.json', result)
    print(json.dumps({key: result[key] for key in ('command', 'status', 'output', 'script_wall_seconds',
                                                'diagnostic_calls', 'pilot_model_calls', 'main_model_calls')}, ensure_ascii=False), flush=True)
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
