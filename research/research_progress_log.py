"""Append-only, hash-chained research work ledger; never edits prior records.

Entries report when they were recorded. Earlier events may be described in the
detail field, but timestamps are never backdated. This is local provenance, not
an external timestamp authority or a substitute for raw execution artifacts.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'research/progress_20261018.jsonl'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def read_verified(path=LEDGER):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        payload = {k: v for k, v in row.items() if k != 'event_sha256'}
        if row['event_sha256'] != digest(payload):
            raise ValueError('Event hash mismatch')
        if row['sequence'] != len(rows) + 1:
            raise ValueError('Event sequence mismatch')
        if row['previous_event_sha256'] != (rows[-1]['event_sha256'] if rows else None):
            raise ValueError('Event chain mismatch')
        rows.append(row)
    return rows


def append(phase, status, detail, paths=(), path=LEDGER):
    rows = read_verified(path)
    refs = []
    for p in paths:
        p = Path(p).resolve()
        refs.append({'path': p.relative_to(ROOT).as_posix(),
                     'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    event = {'sequence': len(rows) + 1,
             'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
             'phase': phase, 'status': status, 'detail': detail,
             'reference_files': refs,
             'previous_event_sha256': rows[-1]['event_sha256'] if rows else None}
    event['event_sha256'] = digest(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as out:
        out.write(canonical(event) + '\n')
        out.flush()
    if read_verified(path)[-1] != event:
        raise ValueError('Append verification failed')
    return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase')
    parser.add_argument('--status')
    parser.add_argument('--detail')
    parser.add_argument('--ref', action='append', default=[])
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        rows = read_verified()
        print(json.dumps({'events': len(rows), 'chain_valid': True,
                          'last_event_sha256': rows[-1]['event_sha256'] if rows else None}))
    else:
        if not all((args.phase, args.status, args.detail)):
            parser.error('--phase, --status, --detail are required')
        print(json.dumps(append(args.phase, args.status, args.detail, args.ref), ensure_ascii=False))


if __name__ == '__main__':
    main()
