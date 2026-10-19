"""Append an explicit v492 process event without changing prior version ledgers."""
import argparse
from pathlib import Path
from research_progress_log import append

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', required=True)
    parser.add_argument('--status', required=True)
    parser.add_argument('--detail', required=True)
    parser.add_argument('--ref', action='append', default=[])
    args = parser.parse_args()
    record = append(args.phase, args.status, args.detail, [ROOT / p for p in args.ref],
                    path=ROOT / 'research/v492_process_20261019.jsonl')
    print(record['event_sha256'])


if __name__ == '__main__':
    main()
