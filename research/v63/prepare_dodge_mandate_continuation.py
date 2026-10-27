import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/v63_20261027/continuation_sources'
path=OUT/'mandates_v2.json';obj=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'profiles':[]}
ev='DODGX_mandate_20250630_evidence';url='https://www.sec.gov/Archives/edgar/data/29440/000119312525151247/d12840d497.htm'
rules=[
 ('DODGX_EQ80','Normal circumstances require equity exposure of at least 80% of NAV; qualifying preferred/convertible securities, rights, warrants and equity derivatives may count.','NAV','class2_fixed_sleeve_invariant',1386),
 ('DODGX_FOREIGN20','Non-US issuers outside the S&P 500 are limited to 20% of total assets.','total assets','class3_not_identifiable_from_FF12',1387),
 ('DODGX_CURRENCY5','Securities denominated in non-USD currencies are limited to 5% of total assets.','total assets','class3_not_identifiable_from_FF12',1387),
 ('DODGX_INDUSTRY25','Issuer securities in a single source-defined industry cannot exceed 25% of total assets; government/GSE exceptions apply. Source uses third-party industry classifications and manager discretion, so this is not an FF12 25% cap.','total assets','class3_source_taxonomy_differs_from_FF12',3113),
 ('DODGX_ISSUER75','For 75% of total assets, issuer exposure is limited to 5% of fund total assets and 10% of issuer voting securities, subject to stated exceptions.','total assets and issuer voting securities','class3_security_level',3121),
 ('DODGX_ILLIQUID15','Illiquid securities purchases must not result in more than 15% of NAV in illiquid securities.','NAV','class3_security_level',3126),
 ('DODGX_TRANSACTION_SCOPE','Percentage restrictions apply when purchasing; later market changes do not automatically require a sale.','purchase-time holdings','class3_path_dependent',3135),
 ('DODGX_OTHER_RESTRICTIONS','Underwriting, physical real estate, physical commodities, borrowing/senior securities and lending restrictions retain the statutory and instrument exceptions listed in the SAI.','instrument and transaction attributes','class3_not_identifiable_from_FF12',3112),
 ('DODGX_DEFENSIVE','Temporary defensive allocations may consist entirely of cash and cash equivalents.','portfolio under temporary defensive circumstances','class3_conditional',1391),
]
constraints=[{'evidence_id':rid,'source_document_id':ev,'source_url':url,'source_line':ln,'text':txt,'denominator':den,'handling':handling,'numerically_enforced_in_FF12':False} for rid,txt,den,handling,ln in rules]
# Restrict completion to development now; later periods require their own effective-version chain.
profile={'fund_id':'F03','period':'development','verified':True,'objective':'Long-term growth of principal and income; reasonable current income is secondary.','mandatory_constraints':constraints,'A':[],'b':[],'source_url':url,'source_evidence_ids':[ev],'publication_date':'2025-06-27','document_date':'2025-05-01','supplement_effective_date':'2025-06-30','filing_accession':'0001193125-25-151247','capture_method':'official SEC text via normal web retrieval; original HTML bytes not captured','evidence_sha256':hashlib.sha256((OUT/(ev+'.txt')).read_bytes()).hexdigest(),'human_review_mode':'user_assumed_completed','actual_independent_signatures':None,'numerical_scope_note':'FF12 cannot certify security-level, country, currency, purchase-time or source-industry compliance. The common-equity sleeve mass and outside assets are held fixed, so the 80% rule is constant across feasible reallocations. No invented per-FF12 cap was imposed.'}
obj['profiles']=[p for p in obj['profiles'] if (p['fund_id'],p['period'])!=('F03','development')]+[profile];path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');print('DODGX development mandate linked')
