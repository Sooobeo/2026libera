"""Record old and new evidence without relabeling derived captures as raw originals."""
import json,hashlib,re,datetime,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'data/v63_20261027';OUT=BASE/'continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
profiles=read(OUT/'profiles_v2.json')['profiles'];active=set(x for p in profiles for x in p['source_evidence_ids']);entries=[]
def record(path,kind,url=None,**extras):
 entries.append({'source_id':path.stem,'local_path':str(path.relative_to(ROOT)),'evidence_kind':kind,'sha256':sha(path),'bytes':path.stat().st_size,'source_url':url,'active_profile_reference':path.stem in active,**extras})
for p in sorted(OUT.rglob('*.html')):
 receipts=[p.with_name(p.stem+'_receipt.json'),p.with_suffix('.receipt.json')];rec=next((read(x) for x in receipts if x.exists()),{})
 status=rec.get('http_status',rec.get('status'));status=200 if status in ['downloaded','success'] else status
 url=rec.get('source_url',rec.get('url',rec.get('requested_url')))
 kind='official_HTTP_response_bytes' if status==200 else 'failed_or_unverified_HTTP_response_bytes'
 record(p,kind,url,http_status=status,original_response_bytes=True,original_successful_document=status==200,receipt_path=next((str(x.relative_to(ROOT)) for x in receipts if x.exists()),None),acquired_at=rec.get('retrieved_utc',rec.get('retrieved_at_utc',rec.get('acquired_at'))),recorded_hash_matches=not rec.get('sha256') or rec['sha256']==sha(p))
for p in sorted(OUT.rglob('*.pdf')):
 rec=next((read(x) for x in [p.with_name(p.stem+'_receipt.json'),p.with_suffix('.receipt.json')] if x.exists()),{})
 record(p,'official_PDF_response_bytes',rec.get('source_url',rec.get('url')),original_response_bytes=True,http_status=rec.get('status',rec.get('http_status')))
for p in sorted(OUT.glob('*.json')):
 if 'receipt' in p.name or p.name in ['source_manifest_v2.json']:continue
 try:d=read(p)
 except Exception:continue
 if isinstance(d,dict) and d.get('source_url') and d.get('original_html_bytes') is False:
  record(p,'browser_visible_capture_not_original_HTTP_bytes',d['source_url'],original_response_bytes=False,capture_method=d.get('capture_method'),filing_date=d.get('filing_date'),report_as_of=d.get('report_as_of'),series=d.get('series'),field_usage_note='Only complete dom_snapshot is used; rendered_html in development capture is truncated and excluded.' if p.name=='FCNTX_dev_20250930_browser.json' else None)
for p in sorted(OUT.glob('*.txt')):
 if '.part' in p.name or not any(s in p.name for s in ['web','_evidence','_excerpt']):continue
 text=p.read_text(encoding='utf8');urls=list(dict.fromkeys(re.findall(r'https://[^\s<>\)\]"\x00-\x1f]+',text)))
 record(p,'normalized_web_text_not_original_HTTP_bytes',urls[0] if urls else None,original_response_bytes=False,source_urls=urls[:10],web_error_detected=bool(re.search(r'(Failed to fetch|HTTP 403|HTTP 400|Internal Error)',text[:1500])))
sic=read(OUT/'issuer_sic_manifest.json')['receipts']
for r in sic:
 p=ROOT/r['path'];record(p,'official_SEC_issuer_submissions_JSON',r['url'],original_response_bytes=True,http_status=r['status'],cik=r['cik'],official_name=r.get('official_name'),sic=r.get('sic'),acquired_at=r.get('retrieved_utc'),mapping_vintage='current official SEC fallback / retrospective classification',recorded_hash_matches=sha(p)==r['sha256'])
old=read(BASE/'source_manifest.json');old_bykind=collections.Counter(s.get('content_validation','unknown') for s in old['sources']);kinds=collections.Counter(e['evidence_kind'] for e in entries)
successful=[e for e in entries if e.get('http_status')==200 and e.get('original_response_bytes')]
result={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'version':'v2 continuation; original manifest and source bytes are retained separately','original_manifest':{'path':str((BASE/'source_manifest.json').relative_to(ROOT)),'sha256':sha(BASE/'source_manifest.json'),'source_receipts':len(old['sources']),'classification_counts':dict(old_bykind),'original_eligibility_labels_are_historical':True},'continuation_summary':{'source_entries':len(entries),'kinds':dict(kinds),'successful_original_HTTP_records':len(successful),'successful_original_HTTP_unique_hashes':len({e['sha256'] for e in successful}),'issuer_submissions_records':len(sic),'issuer_submissions_unique_CIKs':len({r['cik'] for r in sic}),'nonissuer_successful_original_HTTP_records':sum(e['evidence_kind']!='official_SEC_issuer_submissions_JSON' for e in successful),'browser_captures':kinds['browser_visible_capture_not_original_HTTP_bytes'],'active_parsed_positions':len(read(OUT/'holdings_mapped_v2.json')['rows']),'scientific_ready_profiles':sum(p['scientific_ready'] for p in profiles)},'sources':entries,'active_fund_period_contracts':[{'fund_id':p['fund_id'],'period':p['period'],'holdings_as_of':p['holdings_as_of'],'publication_cutoff':p['publication_cutoff'],'publication_date':p['publication_date'],'source_evidence_ids':p['source_evidence_ids'],'parser_path':p['source_parser_path'],'mandate_source_version':p['mandatory_source_version']} for p in profiles],'dispositions':{'original_TRBCX_manager_summaries':'Retained but superseded for active holdings/NAV by complete SEC NPORT public rendered schedules. The old sources are not deleted or merged.','SEC_bulk_403':'Retained in bulk_probe.json and failed response bodies. No circumvention was used. Individual SEC filings and public rendered displays were accessible through ordinary requests/browser.','VPMCX_development':'Original active source is complete browser DOM; later HTTP request outcomes are separate receipts.','FCNTX_C_mandate_change':'May 15 2026 same-fund Class K SAI raises illiquid limit 10% to 15%; fee differences are excluded.','source_constraints':'No source-defined industry limit is silently translated into a numeric FF12 cap. A/b empty reflect representability, not absence of mandate rules.'},'human_review_mode':'user_assumed_completed','actual_independent_signatures':None}
(OUT/'source_manifest_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(result['continuation_summary'])
