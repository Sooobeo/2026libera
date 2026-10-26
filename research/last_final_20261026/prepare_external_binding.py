"""Bind the saved control draft without rerunning or modifying it."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research'))
from last_final_20261026 import runtime_adapter as adapter

def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')

def main():
    directory = Path(__file__).resolve().parent
    binding = adapter.prepare_external()
    construction = directory / 'prepared_final_construction.json'
    save(construction, binding.pop('final_construction'))
    binding['external_draft_evidence_refs']['final_construction'] = adapter.artifact_ref(construction)
    adapter.validated_external_draft(binding)
    save(directory / 'external_draft_binding.json', binding)
    print(json.dumps({'status': 'external_saved_D0_bound', 'construction_ref': adapter.artifact_ref(construction),
                      'binding_ref': adapter.artifact_ref(directory / 'external_draft_binding.json'), 'model_calls': 0}))

if __name__ == '__main__':
    main()
