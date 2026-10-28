"""Verify the active handoff offline; --historical checks the old snapshot.

No model loading, service requests, or experiment dispatches occur here.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

BUNDLE=Path(__file__).resolve().parent
ROOT=BUNDLE.parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def checked_file(path, expected, boundary, errors):
    path=path.resolve()
    if not path.is_relative_to(boundary):
        errors.append({'path':str(path),'reason':'outside intended directory'})
    elif not path.is_file():
        errors.append({'path':str(path),'reason':'missing'})
    elif (hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']
          or path.stat().st_size!=expected['bytes']):
        errors.append({'path':str(path),'reason':'bytes differ'})


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
    def handle_starttag(self, tag, attrs):
        if tag=='a':
            self.links.extend(value for name,value in attrs if name=='href' and value)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--historical',action='store_true',help='Check the old full snapshot, including unavailable files.')
    args=parser.parse_args()
    errors=[]
    if args.historical:
        manifest=read(BUNDLE/'자료목록.json')
        records=manifest['files']+manifest['generated_files']
        for row in records:
            checked_file(BUNDLE/row['copy'],row,BUNDLE,errors)
        result={'scope':'historical_snapshot','status':'passed' if not errors else 'incomplete_or_changed',
                'checked_files':len(records),'errors':errors,'model_calls':0}
        destination=BUNDLE/'검증결과_과거스냅샷.json'
    else:
        manifest=read(BUNDLE/'현재자료목록_20261028.json')
        for row in manifest['generated_files']:
            checked_file(BUNDLE/row['copy'],row,BUNDLE,errors)
        for row in manifest['workspace_files']:
            checked_file(ROOT/row['path'],row,ROOT,errors)
        link_count=0
        for name in manifest['active_html']:
            page=BUNDLE/name
            links=Links()
            links.feed(page.read_text(encoding='utf-8'))
            for href in links.links:
                parsed=urlsplit(href)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                path=(page.parent/unquote(parsed.path)).resolve()
                link_count+=1
                if not path.is_relative_to(ROOT) or not path.exists():
                    errors.append({'page':name,'href':href,'reason':'missing or outside workspace link'})
        state=read(BUNDLE/'현재실험상태_20261028.json')
        scope=read(ROOT/state['design']['path'])
        config=read(ROOT/state['config']['path'])
        design=scope['design']
        if (design['arms']!=['R0','R1','R2','R3'] or design['precision_levels']!=[.5,2.]
                or len(design['main_scenario_ids'])!=10 or design['replicates']!=1
                or design['enabled_phases']!=['B-main'] or scope['planned_output_slots']!=480
                or scope['planned_trajectories']!=160 or scope['separate_preliminary_generation_requests']!=0
                or set(config['phase_budgets'])!={'B-main'}
                or config['main_direct_design']['arms']!=design['arms']
                or config.get('allow_infrastructure_retries') is not False
                or config.get('skip_duplicate_render_identity') is not True):
            errors.append({'reason':'active design/configuration mismatch'})
        if (BUNDLE/'현재실험설정_20261028.json').read_bytes()!=(ROOT/state['design']['path']).read_bytes():
            errors.append({'reason':'bundled design differs from authoritative design'})
        result={'scope':'active_main_only_handoff','status':'passed' if not errors else 'failed',
                'checked_files':len(manifest['generated_files'])+len(manifest['workspace_files']),
                'checked_local_links':link_count,'errors':errors,'model_calls':0,
                'historical_snapshot':'Not checked; optional --historical reports its known missing copies separately.',
                'experiment_started_by_verifier':False}
        destination=BUNDLE/'검증결과_현재.json'
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=True))
    return int(bool(errors))


if __name__=='__main__':
    raise SystemExit(main())
