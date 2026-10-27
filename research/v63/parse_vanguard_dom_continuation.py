import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
s=json.loads((OUT/'VPMCX_annual_20250930_browser_dom.json').read_text(encoding='utf8'))['dom_snapshot'];s=s[s.index('- generic: Schedule of Investments'):];s=s[:s.index('Total Common Stocks (Cost')]
rows=[]
for li,line in enumerate(s.splitlines()):
    m=re.match(r'^\s*- row "(.+?) ([\d,]+) ([\d,]+)":$',line)
    if not m:continue
    name,shares,value=m.groups()
    if not re.search('[A-Za-z]',name):continue
    rows.append({'ticker':'VPMCX','holdings_as_of':'2025-09-30','source_id':'VPMCX_annual_20250930_browser_dom','source_line':li,'source_text':line,'name_as_extracted':name,'shares':int(shares.replace(',','')),'value_usd':int(value.replace(',',''))*1000,'value_unit_in_source':'USD thousands','security_type_in_source':'Common Stocks','sic':None,'ff12':None,'eligible_equity':True,'human_review':'user_assumed_completed'})
summary={'source_id':'VPMCX_annual_20250930_browser_dom','ticker':'VPMCX','holdings_as_of':'2025-09-30','parsed_rows':len(rows),'parsed_value_usd':sum(r['value_usd'] for r in rows),'reported_common_stock_value_usd':75375073000,'source_nav_usd':76358567000,'source_investments_usd':76394525000,'source_other_assets_less_liabilities_usd':-35958000,'capture_method':'browser_visible_DOM_snapshot; not original HTML bytes'}
summary['common_stock_sum_matches']=summary['parsed_value_usd']==summary['reported_common_stock_value_usd'];summary['source_accounting_identity_matches']=summary['source_investments_usd']+summary['source_other_assets_less_liabilities_usd']==summary['source_nav_usd']
(OUT/'parsed/VPMCX_annual_20250930_browser_dom.json').write_text(json.dumps({'summary':summary,'rows':rows},indent=2),encoding='utf8');print(summary)
