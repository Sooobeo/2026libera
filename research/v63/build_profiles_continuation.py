"""Build reproducible, source-backed FF12 sleeves without silently repairing missing data."""
import json,hashlib,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'data/v63_20261027';OUT=BASE/'continuation_sources'
def read(p):return json.loads(p.read_text(encoding='utf8'))
mapping={r['name']:r for r in read(OUT/'issuer_sic_mapping.json')}
industries=read(ROOT/'data/french/sic_definitions_ff12.json')['industries']
def ff(s):
    if not str(s).isdigit() or int(s) in [0,8880,9995] or int(s)>9999:return None
    for d in industries[:11]:
        if any(v['low']<=int(s)<=v['high'] for v in d['sic_intervals_inclusive']):return d['id']
    return 12
files=list((BASE/'parsed').glob('*.json'))+list((OUT/'parsed').glob('*.json'))
# A complete NPORT with disclosed identifiers supersedes the separate manager summary, while both raw sources remain preserved.
if any('TRBCX_main_20251231_nport_dom' in p.name for p in files):files=[p for p in files if p.name!='TRBCX_manager_q4_holdings_mutable.json']
if any('TRBCX_C_20260331_nport_dom' in p.name for p in files):files=[p for p in files if p.name!='TRBCX_manager_q1_holdings_mutable.json']
periods={'2025-09-30':('development','2025-12-31'),'2025-12-31':('A_B','2026-03-31'),'2026-03-31':('C','2026-06-30')}
ids={'FCNTX':'F01','VPMCX':'F02','DODGX':'F03','TRBCX':'F04'}
publications={
 'TRBCX_dev_20250930_nport_dom':('2025-11-25','0001099263-25-003630','SEC public NPORT renderer and filing index: exact series S000002069, full 74 named positions'),
 'TRBCX_main_20251231_nport_dom':('2026-02-26','0001099263-26-002537','SEC public NPORT renderer and filing index: exact series S000002069, full 74 named positions'),
 'TRBCX_C_20260331_nport_dom':('2026-05-28','0001099263-26-006586','SEC public NPORT renderer and filing index: exact series S000002069, full 74 named positions'),
 'FCNTX_dev_20250930_browser':('2025-11-25','0000035402-25-002136','SEC NPORT-EX quarterly full DOM and index snapshot verify fund, series, period and filing date'),
 'FCNTX_C_20260331_browser':('2026-05-26','0000035402-26-003312','SEC NPORT-EX quarterly full DOM and index snapshot verify fund, series, period and filing date'),
 'FCNTX_annual_20251231':('2026-02-20','0000024238-26-000023','2026-02-12 independent auditor report; SEC annual filing matching fund and period'),
 'VPMCX_annual_20250930_browser_dom':('2025-11-28','0001104659-25-116918','SEC original filing rendered in browser, fund heading and report period in same document'),
 'VPMCX_manager_holdings_dec2025':('2026-02-26','0000752177-26-000071','SEC NPORT-EX vg_primcap.htm matches common total and NAV; XML search number not used'),
 'VPMCX_manager_financial_statements_2025':('2026-06-01','0001104659-26-068850','Manager financial statements match SEC N-CSRS fund and reporting period'),
 'DODGX_QH3_20250930_browser':('2025-11-26','0001193125-25-299123','Official manager quarterly report + SEC same fund series S000011202 and period'),
 'DODGX_NCSR_20251231_browser':('2026-03-05','0000029440-26-000002','Manager annual financial statements + SEC N-CSR same fund and report period'),
 'DODGX_QH1_20260331_browser':('2026-06-01','0001193125-26-250426','SEC index verifies S000011202, NPORT-EX matches reported NAV $114748286307'),
}
mandates=read(OUT/'mandates_v2.json') if (OUT/'mandates_v2.json').exists() else {'profiles':[]}
mandates={(r['fund_id'],r['period']):r for r in mandates['profiles']}
ledger=[];profiles=[]
for path in files:
    d=read(path);s=d['summary'];source=s['source_id'];date=s['holdings_as_of'];period,cutoff=periods[date];ticker=s['ticker'];hvalues=[0.0]*12;eligible_total=0;allnamed=0
    for r0 in d['rows']:
        r=dict(r0);name=r['name_as_extracted'];m=mapping.get(name,{})
        eligible=r.get('eligible_equity',ticker!='TRBCX' or not (name.startswith('TRP Government') or name.startswith('Carvana 9 ') or 'Futures IM Collateral' in name))
        eligible=eligible and r['value_usd']>0
        code=ff(m.get('official_sic')) if eligible else None
        r.update({'fund_id':ids[ticker],'period':period,'eligible_equity':eligible,'issuer_cik':m.get('confirmed_cik'),'issuer_official_name':m.get('official_name'),'issuer_identity_method':m.get('identity_method'),'sic':m.get('official_sic'),'sic_source_url':m.get('sic_source_url'),'sic_evidence_sha256':m.get('sic_evidence_sha256'),'sic_mapping_vintage':'current official SEC issuer fallback; retrospective classification','ff12':code,'human_review_mode':'user_assumed_completed','actual_independent_signatures':None})
        if eligible:eligible_total+=r['value_usd']
        if code:hvalues[code-1]+=r['value_usd']
        allnamed+=r['value_usd'];ledger.append(r)
    concealed=s.get('concealed_miscellaneous_securities_usd',0)
    uncertainty=s.get('coverage_uncertainty_addition_usd',0)
    denominator=eligible_total+concealed+uncertainty # conservative potential eligible-equity mass is never removed from denominator
    mapped=sum(hvalues);nav=s['source_nav_usd'];h=[x/mapped for x in hvalues] if mapped else None;coverage=mapped/denominator if denominator else None
    complete=bool(s.get('common_stock_sum_matches') or s.get('complete_nport_position_schedule')) and not concealed
    reconciled=bool(s.get('source_accounting_identity_matches'))
    pub=publications.get(source);pubverified=bool(pub and pub[0]<=cutoff)
    mandate=mandates.get((ids[ticker],period),{});mandatoryok=bool(mandate.get('verified'))
    issues=[]
    if not complete:issues.append('Full security identity schedule is incomplete; concealed holdings remain unresolved.')
    if not reconciled:issues.append('Complete official NAV accounting reconciliation unavailable.')
    if not pubverified:issues.append('Official publication cutoff linkage unavailable.')
    if coverage is None or coverage<.9:issues.append('Mapped eligible-equity coverage below 90%.')
    if not mandatoryok:issues.append('Period-eligible mandatory-rule packet not yet linked.')
    holdings_ready=complete and reconciled and pubverified and coverage>=.9
    profile={'fund_id':ids[ticker],'ticker':ticker,'period':period,'holdings_as_of':date,'publication_cutoff':cutoff,'h':h,'q_NAV':mapped/nav,'coverage':coverage,'coverage_denominator_usd':denominator,'eligible_equity_value_usd':eligible_total,'mapped_equity_value_usd':mapped,'source_NAV_usd':nav,'complete_holdings':complete,'nav_reconciled':reconciled,'publication_verified':pubverified,'publication_date':pub[0] if pub else None,'publication_accession':pub[1] if pub else None,'publication_basis':pub[2] if pub else None,'source_evidence_ids':[source,'issuer_sic_manifest','official_FF12_SIC_intervals'],'objective':mandate.get('objective'),'mandatory_constraints':mandate.get('mandatory_constraints',[]),'A':mandate.get('A',[]),'b':mandate.get('b',[]),'mandatory_rules_verified':mandatoryok,'holdings_scientific_ready':holdings_ready,'scientific_ready':holdings_ready and mandatoryok,'ready':holdings_ready and mandatoryok,'issues':issues,'human_review_mode':'user_assumed_completed','actual_independent_signatures':None,'mapping_vintage':'current official SEC issuer fallback; retrospective classification','outside_scope_accounting':{'unmapped_eligible_equity_usd':eligible_total-mapped,'known_named_noneligible_usd':allnamed-eligible_total,'concealed_miscellaneous_usd':concealed,'investments_outside_parsed_schedule_usd':s['source_investments_usd']-allnamed,'other_assets_less_liabilities_usd':s.get('source_other_assets_less_liabilities_usd'),'NAV_less_mapped_sleeve_usd':nav-mapped,'note':'Original source rows and non-sleeve investment sections retained; this is a reconciliation summary, not a replacement cash holding.'},'source_parser_path':str(path.relative_to(ROOT))}
    profiles.append(profile)
    profile['coverage_kind']=s.get('coverage_kind','mapped eligible-equity value / all eligible-equity value')
    profile['source_caveats']=[s['miscellaneous_assessment']] if 'miscellaneous_assessment' in s else []
    profile['source_evidence_ids']+=mandate.get('source_evidence_ids',[])
    profile['objective_evidence_id']=mandate.get('source_evidence_ids',[None])[0]
    profile['mandatory_source_version']={k:mandate.get(k) for k in ['publication_date','document_date','supplement_effective_date','filing_accession','evidence_sha256']}
for ticker,fid in ids.items():
    for date,(period,cutoff) in periods.items():
        if any(p['fund_id']==fid and p['period']==period for p in profiles):continue
        profiles.append({'fund_id':fid,'ticker':ticker,'period':period,'holdings_as_of':date,'publication_cutoff':cutoff,'h':None,'q_NAV':None,'coverage':None,'complete_holdings':False,'nav_reconciled':False,'publication_verified':False,'source_evidence_ids':[],'objective':None,'mandatory_constraints':[],'A':[],'b':[],'holdings_scientific_ready':False,'scientific_ready':False,'ready':False,'issues':['Full official holdings schedule not yet obtained.'],'human_review_mode':'user_assumed_completed','actual_independent_signatures':None})
profiles.sort(key=lambda p:(p['fund_id'],list(periods).index(p['holdings_as_of'])))
for label,data in [('profiles_v2',{'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'profiles':profiles}),('holdings_mapped_v2',{'rows':ledger})]:
    (OUT/f'{label}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
summary={'fund_periods':len(profiles),'parsed_rows':len(ledger),'mapped_rows':sum(bool(r['ff12']) for r in ledger),'h_computed':sum(p['h'] is not None for p in profiles),'holdings_scientific_ready':sum(p['holdings_scientific_ready'] for p in profiles),'scientific_ready':sum(p['scientific_ready'] for p in profiles),'human_review_mode':'user_assumed_completed','actual_independent_signatures':None}
(OUT/'readiness_v2.json').write_text(json.dumps({'summary':summary,'rows':profiles},ensure_ascii=False,indent=2),encoding='utf8')
print(summary)
print([(p['ticker'],p['period'],round(p['coverage'] or 0,5),p['holdings_scientific_ready']) for p in profiles])
