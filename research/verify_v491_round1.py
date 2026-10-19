"""Ordered first audit of actual context/prepared inputs; no model inference."""
from __future__ import annotations
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup

from v49_compaction_review_20261019 import untab
from sector_v491_contract import evidence_ids, strict_json
from build_v491_context_plan import ROOT, OUT, CONTEXT, CONFIG, PLAN, METHOD, PAPER, read, ref, save


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=['r1','r2'], default='r2')
    args=parser.parse_args()
    checks=[]
    def check(name, passed, detail=None):
        checks.append({'check':name, 'pass':bool(passed), 'detail':detail})
    refs={}
    def bind(path):
        item=ref(path); refs[item['path']]=item; return item
    def all_refs(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
                yield value
            for item in value.values(): yield from all_refs(item)
        elif isinstance(value,list):
            for item in value: yield from all_refs(item)

    config=read(CONFIG)
    candidate=read(OUT/'public_compact_candidate.json')
    prior=read('data/sector_protocol/v49_design_20261019/public_compact_candidate.json')
    context=read(CONTEXT/'common_context.json')
    macro=read(CONTEXT/'market_context.json')
    audit=read('research/v491_macro_source_audit_20261019.json')
    manifest=read(OUT/'prepared/preparation_manifest.json')
    evaluation=read('research/v491_evaluation_protocol_20261019.json')
    for path in [CONFIG, PLAN, METHOD, PAPER, OUT/'public_compact_candidate.json', OUT/'prompt_contract.json',
                 OUT/'response_schema.json', OUT/'prepared/preparation_manifest.json',
                 CONTEXT/'common_context.json', CONTEXT/'market_context.json',
                 'research/v491_macro_source_audit_20261019.json', 'research/v491_mandate_basis_20261019.json',
                 'research/v491_evaluation_protocol_20261019.json', 'research/v491_human_review_template_20261019.json',
                 'research/build_v491_context_plan.py', 'research/sector_v491_contract.py',
                 'research/prepare_sector_v491.py', 'research/test_sector_v491_contract.py',
                 'research/requirements-v491.txt', 'research/verify_v491_round1.py']:
        bind(path)
    check('macro_source_audit_matches_exact_packet',audit['packet_sha256']==ref(CONTEXT/'market_context.json')['sha256'])
    check('macro_source_checks_pass',audit['status']=='PASS' and all(x['pass'] for x in audit['checks']))
    check('macro_fact_factoring_is_lossless',untab(context['market_context']['fact_table'])==macro['facts'])
    check('shared_context_matches_aggregate',context==candidate['common_context'])
    check('context_fact_count',len(evidence_ids(context))==17)
    check('source_packets_preserved_exactly',candidate['public_source_packets']==prior['public_source_packets'])
    check('all_numeric_market_values_unchanged',
          {k:v for k,v in candidate['common_market'].items() if k!='baseline_derivation'}==
          {k:v for k,v in prior['common_market'].items() if k!='baseline_derivation'})
    check('numeric_registry_unchanged',candidate['public_numeric_fact_index']==prior['public_numeric_fact_index'])
    check('twelve_month_horizon_same_basis',context['operating_brief']['judgment_horizon_months']==
          read('research/v491_mandate_basis_20261019.json')['selected_task']['judgment_horizon_months']==12)
    check('benchmark_comparison_only',context['operating_brief']['benchmark_role']=='comparison_only_not_holdings_not_gold')
    check('no_unjustified_numeric_preferences',all(context['operating_brief'][k] is None for k in ('numeric_risk_limit','numeric_utility_coefficient','required_return')))
    for fact in macro['facts']:
        check('release_before_cutoff:'+fact['evidence_id'],fact['publication_date']<'2026-07-17')
        check('fact_unit_period_source:'+fact['evidence_id'],all(fact.get(k) for k in ('unit','observation_period','source_url','release_vintage','source_locator')))
    for item in all_refs({'config':config,'manifest':manifest,'audit':audit}):
        p=ROOT/item['path']
        check('hash:'+item['path'],p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'])
        if p.is_file(): bind(p)

    check('eight_prepared_cases',len(manifest['prepared_cases'])==8)
    check('no_prepared_final_or_model_output',manifest['counts']['prepared_F0']==0 and manifest['model_calls']==0)
    check('no_live_success_claim',not config['model']['runtime_validated'] and not config['current_state']['frozen'])
    check('context_evaluation_prespecified','context_use' in evaluation['dimensions'])
    late=[]
    common=[]
    for case in manifest['prepared_cases']:
        messages=read(case['path']); payload=strict_json(messages[1]['content'])
        sid=case['assigned_source_id']
        common.append({k:payload[k] for k in ('common_context','common_market','public_numeric_fact_index','response_schema')})
        check('correct_context:'+case['case_id'],payload['common_context']==context)
        check('no_controller_metadata:'+case['case_id'],not set(payload)&{'case_id','arm','source_id','split','public_source_packets','evaluator_only'})
        if case['arm']=='L':
            late.append(messages)
            check('late_source_absent:'+case['case_id'],'institution_document' not in payload and
                  re.search(r'\b(?:fidelity|ubs)\b',json.dumps(messages),flags=re.I) is None)
        else:
            check('early_assigned_packet_only:'+case['case_id'],payload['institution_document']==candidate['public_source_packets'][sid])
        bind(case['path'])
    check('all_common_inputs_identical',all(x==common[0] for x in common))
    check('identical_L_inputs_independent_case_ids',all(x==late[0] for x in late) and len({x['case_id'] for x in manifest['prepared_cases']})==8)

    future_links={'research/v491_validation_round1_20261019.json','research/v491_validation_round2_20261019.json',
                  'research/v491_validation_round3_20261019.json','research/v491_handoff_20261019.json',
                  'research/v491_validation_round1_20261019_r2.json','research/v491_validation_round2_20261019_r2.json'}
    pending=[]
    for path in (PLAN,METHOD,PAPER):
        raw=path.read_text('utf-8'); soup=BeautifulSoup(raw,'html.parser')
        check('unicode_clean:'+path.name,'\ufffd' not in raw and '???' not in raw)
        for a in soup.select('a[href]'):
            u=urlparse(a['href'])
            if u.scheme or u.netloc: continue
            target=(path.parent/unquote(u.path)).resolve() if u.path else path
            rel=target.relative_to(ROOT).as_posix()
            if rel in future_links and not target.exists():
                pending.append({'document':path.name,'target':rel});continue
            okay=target.is_file()
            if okay and u.fragment:
                okay=BeautifulSoup(target.read_text('utf-8'),'html.parser').find(id=unquote(u.fragment)) is not None
            check('local_link:'+path.name+':'+a['href'],okay)
        if path==PAPER:
            for section in ('intro','literature','framework','design','evaluation','readiness','implications','conclusion','references','appendix'):
                check('full_paper_section:'+section,soup.find(id=section) is not None)
            check('paper_Laban_reference',soup.find(id='ref-laban') is not None)
            check('paper_LiveMacro_reference',soup.find(id='ref-livemacro') is not None)
            check('paper_macro_table',len(soup.select('#design table tbody tr'))==7)
            check('paper_footer_current_rules',soup.footer is not None and 'v4.9.1' in soup.footer.get_text() and 'v4.8' not in soup.footer.get_text())

    suites=[]
    for pattern in ('test_sector_v491_contract.py','test_sector_engine.py'):
        cmd=[sys.executable,'-B','-X','utf8','-m','unittest','discover','-s','research','-p',pattern]
        done=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        suites.append({'command':cmd,'returncode':done.returncode,'stdout':done.stdout,'stderr':done.stderr})
        check('suite:'+pattern,done.returncode==0)
    receipt={'protocol_version':'4.9.1','round':1,'review_revision':args.revision,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
             'scope':'actual input data/hash integrity, ordered context isolation, schema and arithmetic contracts, document links; not inference or human review',
             'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','check_count':len(checks),'checks':checks,
             'unit_suites':suites,'reviewed_files':list(refs.values()),'pending_cross_stage_links':pending,
             'pending_link_policy':'Only reports written after this ordered stage. Final handoff must verify all such links exist.',
             'runtime_dependencies':{x:importlib.metadata.version(x) for x in ('numpy','jsonschema','beautifulsoup4')},
             'initial_audit_correction':{'path':'research/v491_validation_round1_initial_20261019.json',
                'reason':'The initial independent audit used substring ubs, which matched the ordinary word subsequent. Use institution-name word boundaries. Actual prepared inputs did not change; initial FAIL retained.'},
             'model_calls':0,'independent_human_review_completed':False}
    if args.revision=='r2':
        receipt['supersedes']=ref('research/v491_validation_round1_20261019.json')
        receipt['correction_history']=ref('research/artifacts/v491_review_history_20261019/snapshot_manifest.json')
    save('research/v491_validation_round1_20261019'+('_r2' if args.revision=='r2' else '')+'.json',receipt)
    print(json.dumps({'status':receipt['status'],'checks':len(checks),'failed':[x for x in checks if not x['pass']],
                      'suites':[{'returncode':x['returncode'],'result':x['stderr'][-170:]} for x in suites]},ensure_ascii=False))
    return 0 if receipt['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
