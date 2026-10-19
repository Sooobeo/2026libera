"""Read-only inventory of the active MSI extraction; never copy or execute it."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json, os

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('C:/Users/Insun/AppData/Local/Temp/libera_v493_render_20261019/portable_manual')
mapping = json.loads((WORK/'file_mapping.json').read_text(encoding='utf-8'))
raw = WORK/'cab_files'
entries = {}
for entry in os.scandir(raw):
    if entry.is_file():
        entries[entry.name.casefold()] = entry.stat().st_size
groups = {}
completed = []
missing = []
for m in mapping:
    parts = m['relative_path'].split('/')
    group = '/'.join(parts[:3]) if parts[1:2] == ['share'] else '/'.join(parts[:2])
    bucket = groups.setdefault(group, {'total':0,'complete':0,'missing_examples':[], 'sequence_min':m['sequence'],'sequence_max':m['sequence']})
    bucket['total'] += 1
    bucket['sequence_min'] = min(bucket['sequence_min'],m['sequence'])
    bucket['sequence_max'] = max(bucket['sequence_max'],m['sequence'])
    actual = entries.get(m['file_key'].casefold())
    if actual == m['expected_size']:
        bucket['complete'] += 1
        completed.append(m)
    else:
        missing.append(m)
        if len(bucket['missing_examples']) < 4:
            bucket['missing_examples'].append({'path':m['relative_path'],'sequence':m['sequence'],'actual_size':actual,'expected_size':m['expected_size']})
critical_names = {'soffice.com','soffice.exe','soffice.bin','bootstrap.ini','fundamental.ini','uno.ini','unorc','services.rdb','types.rdb','offapi.rdb','oovbaapi.rdb','registrymodifications.xcu','sal3.dll','mergedlo.dll','swlo.dll','vcllo.dll','vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'}
critical = [dict(m,actual_size=entries.get(m['file_key'].casefold()),size_matches=entries.get(m['file_key'].casefold())==m['expected_size']) for m in mapping if m['relative_path'].split('/')[-1].lower() in critical_names]
report={'observed_at_utc':datetime.now(timezone.utc).isoformat(),'status':'read_only_partial_inventory_not_engine_validation','raw_entries':len(entries),'all_mapped_files':len(mapping),'size_complete_files':len(completed),'complete_sequence_min':min((m['sequence'] for m in completed),default=None),'complete_sequence_max':max((m['sequence'] for m in completed),default=None),'groups':groups,'critical_named_files':critical,'first_missing_by_sequence':sorted(missing,key=lambda m:m['sequence'])[:25],'engine_executed':False,'files_copied':0,'model_calls':0}
out=ROOT/'research/v493_partial_engine_inventory_20261019.json'
if out.exists():
    raise FileExistsError(out)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'report':str(out),'raw_entries':len(entries),'complete':len(completed),'groups':groups,'critical':critical},ensure_ascii=False,indent=2))
