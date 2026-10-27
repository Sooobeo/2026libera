"""Audit portable source provenance without modifying the supplied snapshot."""
from __future__ import annotations
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/v63_20261027/audit'
BUNDLE = ROOT / '실험참고자료_20261027'

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BUNDLE/'자료목록.json').read_text(encoding='utf-8-sig'))
    rows=[]
    for row in manifest['files'] + manifest['generated_files']:
        rel = row['copy']
        packaged = BUNDLE / rel
        alternative = ROOT / rel[len('snapshot/'):] if rel.startswith('snapshot/') else packaged
        candidates=[('package',packaged)]
        if alternative != packaged:
            candidates.append(('repository',alternative))
        record={'copy':rel,'expected_sha256':row['sha256'],'expected_bytes':row['bytes'], 'candidates':[]}
        for location,path in candidates:
            info={'location':location,'path':path.relative_to(ROOT).as_posix(),'exists':path.is_file()}
            if path.is_file():
                raw=path.read_bytes()
                info.update(bytes=len(raw),sha256=digest(raw),exact_match=digest(raw)==row['sha256'] and len(raw)==row['bytes'])
                if not info['exact_match']:
                    normalized=raw.replace(b'\r\n',b'\n')
                    info['lf_normalized_match']=digest(normalized)==row['sha256'] and len(normalized)==row['bytes']
            record['candidates'].append(info)
        exact=any(x.get('exact_match') for x in record['candidates'])
        normalized=any(x.get('lf_normalized_match') for x in record['candidates'])
        record['status']='exact' if exact else 'line_endings_only' if normalized else 'changed' if any(x['exists'] for x in record['candidates']) else 'missing'
        rows.append(record)
    result={'schema':'v63_workspace_provenance_v1','user_facing_date':'2026-10-27',
            'reference_snapshot_present':(BUNDLE/'snapshot').exists(),
            'counts':dict(Counter(r['status'] for r in rows)),
            'interpretation':'Repository sources are used at their current recorded byte hashes. Line-ending equivalence is not byte identity. No old result counts toward v6.3.',
            'files':rows}
    (OUT/'workspace_provenance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from pypdf import PdfReader
    reader=PdfReader(BUNDLE/'original/greengreen (1).pdf')
    abstract='\n\n'.join(p.extract_text() for p in reader.pages)
    (OUT/'original_abstract_extracted.txt').write_text(abstract,encoding='utf-8')
    print(json.dumps({'counts':result['counts'],'abstract_pages':len(reader.pages)},ensure_ascii=False))

if __name__=='__main__':
    main()
