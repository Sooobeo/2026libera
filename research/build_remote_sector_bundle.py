"""Package only runner code, public pilot inputs and market data for the server."""
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'tmp/sector_bridge_20261018'
paths = ['research/remote_sector_runtime.py', 'research/run_sector_workflow.py',
         'research/sector_engine.py', 'data/sector_market/market_input.json']
files = {name: (ROOT/name).read_bytes() for name in paths}
packet_path = ROOT / 'data/sector_documents/model_packets.jsonl'
lines = packet_path.read_text(encoding='utf-8-sig').splitlines()
pilot = [line for line in lines if json.loads(line)['split'] == 'pilot']
assert len(pilot) == 2
files['data/sector_documents/model_packets.jsonl'] = ('\n'.join(pilot)+'\n').encode('utf-8')
manifest = {'scope': 'pilot-only; evaluator/gold and main document packets excluded',
            'source_packets_sha256': hashlib.sha256(packet_path.read_bytes()).hexdigest(),
            'pilot_filter': "packet['split'] == 'pilot'; retain exact original JSONL lines",
            'files': {name: hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
files['bundle_manifest.json'] = (json.dumps(manifest, indent=2)+'\n').encode('utf-8')
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w') as archive:
    for name,raw in files.items():
        info = tarfile.TarInfo(name)
        info.size = len(raw)
        info.mode = 0o600
        info.mtime = 0
        archive.addfile(info, io.BytesIO(raw))
packed = gzip.compress(buffer.getvalue(), mtime=0)
DEST.mkdir(parents=True, exist_ok=True)
(DEST/'bundle.tar.gz').write_bytes(packed)
(DEST/'bundle_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'file': str(DEST/'bundle.tar.gz'), 'bytes': len(packed),
                  'sha256': hashlib.sha256(packed).hexdigest(), 'files': list(files)}, indent=2))
