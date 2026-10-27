"""Read-only input/catalog inspection; no experiment outcomes or mutations."""
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib

ROOT=Path(__file__).resolve().parents[2]

def no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key: '+key)
        result[key]=value
    return result

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=no_duplicates)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    config_path=ROOT/'data/v63_20261027/continuation/deployment/local_windows/candidate_002/campaign_config.json'
    config=read(config_path);catalog_path=ROOT/config['source_catalog_path'];catalog=read(catalog_path)
    document_path=ROOT/config['documents_path'];documents=read(document_path)['documents']
    profile_path=ROOT/config['profiles_path'];profiles=read(profile_path)['profiles']
    plan_path=ROOT/'plan/LIBERA_실험설정_v6.3_20261027.json';plan=read(plan_path)
    documents_by_id={d['document_id']:d for d in documents};unit_owners={}
    for document in documents:
        for unit in document['units']:
            for eid in unit['evidence_ids']:
                if eid in unit_owners:raise ValueError('Evidence ID appears in multiple source units')
                unit_owners[eid]=document['document_id']
    assert set(unit_owners)==set(catalog)
    for eid,gold in catalog.items():
        doc=documents_by_id[unit_owners[eid]]
        assert gold['document_id']==doc['document_id'] and gold['source_bytes_sha256']==doc['source_bytes_sha256']
        assert gold['period']==doc['period'] and gold['source_url']==doc['source_url']
        assert eid.startswith(gold['period']+'-')
        if gold['period']=='C':assert '2026-03-31'<gold['publication_date']<='2026-06-30'
        else:assert gold['publication_date']<='2026-03-31'
    rules=[dict(fund_id=p['fund_id'],period=p['period'],**r) for p in profiles for r in p['mandatory_constraints']]
    mandatory_ids={r['evidence_id'] for r in rules};overlap=mandatory_ids&set(catalog);assert not overlap
    by_period={period:{(r['fund_id'],r['evidence_id']):r for r in rules if r['period']==period} for period in ('A_B','C')}
    common=by_period['A_B'].keys()&by_period['C'].keys();changes=[]
    for key in sorted(common):
        a=by_period['A_B'][key];c=by_period['C'][key]
        changed=[field for field in ('source_document_id','source_url','source_excerpt','source_line') if a.get(field)!=c.get(field)]
        if changed:changes.append({'fund_id':key[0],'evidence_id':key[1],'changed_fields':changed,
            'A_source_document_id':a.get('source_document_id'),'C_source_document_id':c.get('source_document_id'),
            'A_excerpt_sha256':hashlib.sha256(a.get('source_excerpt','').encode()).hexdigest(),
            'C_excerpt_sha256':hashlib.sha256(c.get('source_excerpt','').encode()).hexdigest()})
    result={'status':'read_only_catalog_date_and_source_version_audit_complete',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'experiment_outcomes_inspected':False,
        'core_candidate_or_catalog_modified':False,'generation_calls':0,
        'candidate_source_catalog_path':config['source_catalog_path'],'catalog_evidence_units':len(catalog),
        'catalog_period_counts':dict(Counter(g['period'] for g in catalog.values())),
        'catalog_publication_date_counts':dict(Counter(g['publication_date'] for g in catalog.values())),
        'catalog_documents':[{'document_id':d['document_id'],'period':d['period'],'role':d['role'],
            'publication_date':d['publication_date'],'units':len(d['units'])} for d in documents],
        'mandatory_rule_id_catalog_intersection':sorted(overlap),'all_catalog_ids_unique_and_one_source_version':True,
        'catalog_source_document_hashes_and_period_prefixes_verified':True,
        'A_C_shared_mandatory_ids':len(common),'A_C_shared_ids_with_changed_source_versions':len(changes),
        'changed_version_counts_by_fund':dict(Counter(r['fund_id'] for r in changes)),
        'changed_mandatory_source_versions':changes,
        'protocol_new_document_rule':plan['modules']['C']['new_document_rule'],
        'conclusions':[
            'Current source_catalog_v2 is restricted to the six original eligible additional documents (including explicitly labeled A historical commentary), not mandatory baselines.',
            'All C catalog facts are the new 2026-06-17 FOMC document. The current after-March31 condition cannot falsely flag an existing mandatory rule, because those IDs are absent from this catalog.',
            'A mandatory baseline citation is currently exposed but unscored for source facts: gold=None -> source_fact_scored=False; no publication_within_cutoff=False is assigned. This is a source-audit coverage limitation, not evidence that the rule is correct or wrong.',
            'A C citation to an A outlook ID is a different case: the old outlook is outside the C additional-document eligibility window, so its cutoff/period flag is appropriate.',
            'Current scored evidence IDs have A-/C- version-specific prefixes and map to exactly one original source SHA. Grouping by evidence ID plus literal payload does not combine different actual source versions in the current catalog.',
            'Baseline mandatory IDs are reused across A/C and some point to different source documents. If they are added to source scoring later, an eid-only catalog or recurrence key would be unsafe.',
            'Future extension requires role-aware publication checks (new outlook window versus effective mandatory-rule applicability), period/fund-aware mandatory lookup, and an explicit source_document_id/source_bytes_sha256 in each scored fact and recurrence group.',
            'No current evaluator/candidate change is needed to remove the suspected false violation. A future source-audit expansion is a declared new audit specification/global reanalysis, not an outcome-selected correction.'
        ],'source_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in [config_path,catalog_path,document_path,profile_path,plan_path,ROOT/'research/v63/evaluate.py',Path(__file__)]]}
    out=ROOT/'data/v63_20261027/audit/catalog_date_and_source_version_review.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    out.with_suffix('.txt').write_text('\n'.join(result['conclusions'])+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('catalog_evidence_units','catalog_period_counts','mandatory_rule_id_catalog_intersection',
        'A_C_shared_mandatory_ids','A_C_shared_ids_with_changed_source_versions','changed_version_counts_by_fund')}))

if __name__=='__main__':main()
