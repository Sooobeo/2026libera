"""Period-specific rule packets, preserving source denominators and semantic scope."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
path=OUT/'mandates_v2.json';obj=json.loads(path.read_text(encoding='utf8'))
amends=json.loads((OUT/'mandate_amendment_manifest.json').read_text(encoding='utf8'))
def document(name,start=0):
 text=(OUT/(name+'_text.txt')).read_text(encoding='utf8');lines=text.splitlines()
 receipt=json.loads((OUT/(name+'_receipt.json')).read_text(encoding='utf8'))
 return {'name':name,'lines':lines,'start':start,'url':receipt['source_url'],'sha256':hashlib.sha256((OUT/(name+'.html')).read_bytes()).hexdigest()}
def rule(ticker,rid,text,doc,needle,den='security/transaction attributes',kind='class3_not_identifiable_from_FF12',after=0):
 matches=[i for i,l in enumerate(doc['lines']) if i>=max(after,doc['start']) and needle in l]
 assert matches,(doc['name'],needle)
 n=matches[0]
 return {'evidence_id':ticker+'_'+rid,'source_document_id':doc['name'],'source_url':doc['url'],'source_line':n+1,'source_excerpt':doc['lines'][n], 'text':text,'denominator':den,'handling':kind,'numerically_enforced_in_FF12':False}
def add(ticker,fid,period,prosp,sai,date,docdate,acc,rules,objective,notes):
 cutoff={'development':'2025-12-31','A_B':'2026-03-31','C':'2026-06-30'}[period]
 review=[{'source_id':r['source_id'],'filing_date':r['filing_date'],'sha256':r['sha256']} for r in amends if r['ticker']==ticker and r['filing_date']<=cutoff]
 p={'fund_id':fid,'period':period,'verified':True,'objective':objective,'mandatory_constraints':rules,'A':[],'b':[], 'source_url':prosp['url'],'source_evidence_ids':list(dict.fromkeys([prosp['name'],sai['name']])),'publication_date':date,'document_date':docdate,'filing_accession':acc,'evidence_sha256':prosp['sha256'],'capture_method':'official SEC HTTP original HTML bytes, locally parsed with source-line references','amendments_reviewed':review,'human_review_mode':'user_assumed_completed','actual_independent_signatures':None,'numerical_scope_note':'Rules involving issuer, liquidity, index membership, source industry taxonomy or transaction attributes remain semantic constraints. FF12 weights cannot certify those rules. A and b are empty; no invented FF12 caps.','version_notes':notes}
 obj['profiles']=[v for v in obj['profiles'] if (v['fund_id'],v['period'])!=(fid,period)]+[p]
 (OUT/f'{ticker}_{period}_mandate_evidence.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
for period in ['development','A_B','C']:
 dev=period=='development';name='FCNTX_dev_full485_20250225' if dev else 'FCNTX_main_full485_20260225';pr=document(name,3956 if dev else 4407)
 sai=document(name,5431 if dev else 11097)
 if period=='C':sai=document('FCNTX_amendment_20260515_000050',39)
 r=lambda *a,**k:rule('FCNTX',*a,**k)
 ill=15 if period=='C' else 10
 rules=[
 r('COMMON','Normally invest primarily in common stocks; domestic and foreign issuers and growth or value styles are permitted.',pr,"normally invests the fund's assets primarily in common stocks"),
 r('ISSUER75','For 75% of total assets, issuer exposure cannot exceed 5% of fund total assets or 10% of issuer voting securities; government and investment-company exceptions apply.',sai,'The fund may not with respect to 75%', 'total assets / issuer voting securities'),
 r('INDUSTRY25','Purchases must not produce more than 25% of total assets in one source-defined industry; U.S. government exceptions and stated look-through rules apply. This is not an FF12 cap.',sai,'more than 25% of the fund', 'total assets','class3_source_taxonomy_differs_from_FF12'),
 r('BORROW','Borrow only temporarily or for emergencies, not investment leverage, up to 33 1/3% of total assets including borrowings less other liabilities; excess must be reduced within three days excluding Sundays and holidays.',sai,'The fund may not borrow money','total assets including borrowing less non-borrowing liabilities'),
 r('LENDING','Securities/other loans cannot exceed 33 1/3% of total assets, subject to debt, repurchase and loan-acquisition exceptions. Non-securities lending is restricted, including affiliated interfund loans capped at 15% of NAV.',sai,'The fund may not lend any security','total assets; NAV for interfund cash loans'),
 r('ILLIQUID',f'Purchases must not result in illiquid securities above {ill}% of NAV; later excess requires consideration of liquidity-protecting steps.',sai,'The fund does not currently intend to purchase any security','NAV'),
 r('SHORT_MARGIN','Short sales require equivalent owned or obtainable securities; margin purchases are restricted to settlement credit and permitted futures/options margin.',sai,'The fund does not currently intend to sell securities short'),
 r('INSTRUMENTS','Senior securities, underwriting, physical real estate and physical commodities are restricted, with the legal, securities-backed and derivatives exceptions in the SAI.',sai,'The fund may not issue senior securities'),
 r('POOLED','All-assets investment in one affiliated matching-policy open-end fund is fundamentally permitted, but currently not intended.',sai,'The fund may, notwithstanding any other'),
 r('TIME','Percentage and quality restrictions normally apply immediately after acquisition; later value or asset changes do not alone breach those limits.',sai,'The following policies and limitations supplement'),
 r('TAX','Comply with Subchapter M diversification requirements in addition to the fund fundamental issuer limits.',sai,'regulated investment company'),
 r('DEFENSIVE','Temporary defensive strategies may differ from normal investment strategies.',pr,'temporarily use a different investment strategy'),
 ]
 add('FCNTX','F01',period,pr,sai,'2025-02-25' if dev else '2026-02-24','2025-03-01' if dev else '2026-02-28','0000024238-25-000018' if dev else '0000024238-26-000028',rules,'Capital appreciation through securities the adviser believes the public has not fully recognized.', '2025 supplements concern portfolio management and compensation. A uses February 2026 retail Contrafund/Trend SAI. C uses May 15 revised same Contrafund Class K SAI for fund-wide restrictions: illiquid limit changed from 10% to 15%; class fees are not imported. Portfolio/fund identity is shared, unlike the distinct Contrafund K6 fund.')
for period in ['development','A_B','C']:
 dev=period=='development';name='TRBCX_dev_full485_20250225' if dev else 'TRBCX_main_full485_20260225';pr=document(name)
 sainame={'development':'TRBCX_amendment_20251002_014522','A_B':'TRBCX_amendment_20260325_006885','C':'TRBCX_amendment_20260501_009623'}[period];sai=document(sainame);sai['start']=sai['lines'].index('INVESTMENT RESTRICTIONS')
 r=lambda *a,**k:rule('TRBCX',*a,**k)
 rules=[
 r('BLUE80','Normally at least 80% of NAV plus investment borrowings in blue-chip growth securities: S&P 500 membership and an appropriate third-party growth index define eligibility; qualifying derivatives count. Changes require 60 days notice.',pr,'The fund normally invests at least 80%', 'NAV plus investment borrowing'),
 r('NONDIVERSIFIED','The fund is nondiversified; the general 75%/5%/10% diversified-fund issuer limits explicitly exclude Blue Chip Growth.',sai,'Percent Limit on Assets Invested in Any One Issuer (All Funds'),
 r('INDUSTRY25','Purchases must not produce over 25% of NAV in one source-defined industry. Government exclusions apply; recognized provider/adviser classifications do not establish an FF12 cap.',sai,'more than 25% of the value of the funds', 'NAV','class3_source_taxonomy_differs_from_FF12'),
 r('BORROW','Temporary/emergency non-leveraging borrowing and permitted borrowing transactions together cannot exceed 33 1/3% of total assets including borrowing less other liabilities, subject to law.',sai,'Borrow money, except that the funds may (i) borrow for non-leveraging','total assets including borrowing less non-borrowing liabilities'),
 r('BORROW_PURCHASE','Do not purchase additional securities while borrowings exceed 5% of total assets; collateral transfers are restricted to permitted transactions and 33 1/3% of total assets.',sai,'Purchase additional securities when money borrowed','total assets'),
 r('LENDING','Portfolio and interfund lending together cannot exceed 33 1/3% of total assets; debt and repurchase exceptions apply.',sai,'Make loans, although the funds may (i) lend','total assets'),
 r('ILLIQUID','Do not acquire illiquid investments if the resulting exposure exceeds 15% of NAV.',sai,'Acquire an illiquid investment','NAV'),
 r('WARRANTS','Warrants cannot exceed 10% of NAV after investment.',sai,'Invest in warrants if','NAV'),
 r('LOW_GRADE','Below-investment-grade instruments cannot exceed 10% of total assets; convertible securities are exempt from this limit.',sai,'Invest in below-investment' if dev else 'Invest in below investment-grade','total assets'),
 r('OILGAS','Direct mineral/oil/gas exploration and development interests cannot exceed 5% of total assets.',sai,'Purchase participations or other direct interests','total assets'),
 r('SHORT_MARGIN','Short sales are prohibited; securities margin purchases are restricted to settlement credit and permitted investment margin deposits.',sai,'Short Sales (All Funds'),
 r('INSTRUMENTS','Physical real estate, physical commodities, senior securities and underwriting retain the stated statutory, securities-backed and ordinary-portfolio exceptions; investing for management control is prohibited.',sai,'Commodities (All Funds Except'),
 r('FUNDS','Other investment companies may be purchased only through the enumerated Price-fund exceptions or consistently with the 1940 Act.',sai,'Purchase securities of open-end or closed-end investment companies'),
 r('TIME','Maximum-percentage limits apply to acquisition or borrowing breaches. Securities-lending collateral is excluded from restriction total-assets calculations except for the tax diversification test.',sai,'Any investment restriction that involves a maximum'),
 r('DEFENSIVE','Temporary defensive positions may invest without limit in cash or liquid instruments.',pr,'For temporary defensive purposes'),
 ]
 add('TRBCX','F04',period,pr,sai,'2025-02-25' if dev else '2026-02-25','2025-03-01' if dev else '2026-03-01','0001741773-25-000623' if dev else '0001999371-26-004097',rules,'Long-term capital growth; income is secondary.','Latest cutoff-eligible common SAI used with fund-specific prospectus. Blue Chip Growth is explicitly excluded from diversified-fund issuer caps. June 30 2026 supplement changes other named funds effective July 1, not Blue Chip Growth.')
path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');print('Linked FCNTX and TRBCX all three periods')
