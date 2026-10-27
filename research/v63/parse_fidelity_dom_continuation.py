import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
for path in OUT.glob('FCNTX_*_browser.json'):
    d=json.loads(path.read_text(encoding='utf8'));s=d['dom_snapshot'];date=d['report_as_of'];sid=path.stem
    common=re.search(r'row "TOTAL COMMON STOCKS[^\n]* ([\d,]+)":',s)
    invest=re.search(r'row "TOTAL INVESTMENT IN SECURITIES[^\n]* ([\d,]+)":',s)
    nav=re.search(r'row "NET ASSETS[^\n]* ([\d,]+)":',s)
    other=re.search(r'row "NET OTHER ASSETS[^\n]* (\(?[\d,]+\)?)":',s)
    if not all([common,invest,nav,other]):print('missing totals',sid);continue
    def amount(m):return int(m.group(1).replace(',','').replace('(','-').replace(')',''))
    c=s[s.index('Common Stocks -'):common.start()];rows=[]
    for li,line in enumerate(c.splitlines()):
        m=re.match(r'^\s*- row "(.+?) ([\d,]+) ([\d,]+)":$',line)
        if not m:continue
        name,shares,value=m.groups()
        if not re.search('[A-Za-z]',name):continue
        rows.append({'ticker':'FCNTX','holdings_as_of':date,'source_id':sid,'source_line':li,'source_text':line,'name_as_extracted':name,'shares':int(shares.replace(',','')),'value_usd':int(value.replace(',','')),'value_unit_in_source':'USD','security_type_in_source':'Common Stocks','sic':None,'ff12':None,'eligible_equity':'warrant' not in name.lower() and int(value.replace(',',''))>0,'human_review':'user_assumed_completed'})
    summary={'source_id':sid,'ticker':'FCNTX','holdings_as_of':date,'parsed_rows':len(rows),'parsed_value_usd':sum(r['value_usd'] for r in rows),'reported_common_stock_value_usd':amount(common),'source_nav_usd':amount(nav),'source_investments_usd':amount(invest),'source_other_assets_less_liabilities_usd':amount(other),'capture_method':'browser_visible_DOM_snapshot; not original HTTP bytes','filing_date':d.get('filing_date'),'source_url':d['source_url']}
    summary['common_stock_sum_matches']=summary['parsed_value_usd']==summary['reported_common_stock_value_usd'];summary['source_accounting_identity_matches']=summary['source_investments_usd']+summary['source_other_assets_less_liabilities_usd']==summary['source_nav_usd']
    (OUT/'parsed'/path.name).write_text(json.dumps({'summary':summary,'rows':rows},indent=2),encoding='utf8');print(summary)
