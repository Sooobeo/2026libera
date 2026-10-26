"""Preserve prior runtime values; replace only owned-service evidence."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def request(route, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request('http://127.0.0.1:11435' + route, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def write_new(path, obj):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')

def main():
    prior_path = ROOT / 'research/remaining_20261026/runtime_candidate.json'
    receipt_path = HERE / 'service_ready/service_receipt.json'
    prior = read(prior_path)
    receipt = read(receipt_path)
    assert receipt['status'] == 'ready' and receipt['origin'] == 'http://127.0.0.1:11435'
    assert receipt['version'] == prior['engine_version'] == '0.35.1'
    assert receipt['listener_owner_verified'] and receipt['existing_11434_listener_unchanged']
    current = json.loads(json.dumps(prior))
    current['backend_evidence'][0] = {'path': str(receipt_path), 'sha256': digest(receipt_path), 'role': 'cpu_service'}
    restored = json.loads(json.dumps(current))
    restored['backend_evidence'][0] = prior['backend_evidence'][0]
    assert json.dumps(restored, sort_keys=True) == json.dumps(prior, sort_keys=True)
    version, tags = request('/api/version'), request('/api/tags')
    selected = [m for m in tags['models'] if m.get('name') == prior['model'] or m.get('model') == prior['model']]
    assert len(selected) == 1 and selected[0]['digest'] == prior['digest']
    shown = request('/api/show', {'model': prior['model']})
    template_hash = hashlib.sha256(shown['template'].encode()).hexdigest()
    assert version['version'] == prior['engine_version'] and template_hash == prior['template_sha256']
    residency = request('/api/ps')
    assert residency['models'] == []
    out = HERE.parent / 'runtime_candidate.json'
    write_new(out, current)
    observation = {
        'status': 'PASS_read_only_runtime_identity',
        'at_utc': datetime.now(timezone.utc).isoformat(),
        'prior_runtime_ref': {'path': str(prior_path), 'sha256': digest(prior_path)},
        'runtime_ref': {'path': str(out), 'sha256': digest(out)},
        'service_ref': {'path': str(receipt_path), 'sha256': digest(receipt_path)},
        'only_runtime_change': 'backend_evidence[0]',
        'version': version['version'], 'model': prior['model'], 'digest': selected[0]['digest'],
        'template_sha256': template_hash, 'resident_models': residency['models'],
        'generation_calls': 0, 'persistent_settings_changed': False,
    }
    write_new(HERE / 'readonly_prelaunch.json', observation)
    print(json.dumps(observation))

if __name__ == '__main__':
    main()
