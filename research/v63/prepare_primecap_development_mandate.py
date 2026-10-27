"""Freeze reviewed SEC extracted sections; leave shared integration to data builder."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/v63_20261027/continuation_sources'
URL = 'https://www.sec.gov/Archives/edgar/data/752177/000168386325000459/f40563d0.htm'
FILES = ['VPMCX_full_2025_web.txt', 'VPMCX_2025_mandate_sai_web_excerpt.txt', 'VPMCX_2025_mandate_prospectus_web_excerpt.txt', 'VPMCX_2025_amendments_web_1.txt', 'VPMCX_2025_amendments_web_2_and_liquidity.txt']
rules = [
 ('FOREIGN25',348,'Foreign securities, including depositary receipts, are limited to 25% of assets. The source does not explicitly call this denominator NAV.','assets (source wording)','class3_country_security_level'),
 ('DERIVATIVES',351,'Limited derivative use may provide alternate issuer or industry exposure; derivatives must not be used for speculation or to leverage investment returns.','instrument purpose','class3_instrument_and_purpose'),
 ('ISSUER25',4331,'At each taxable quarter end, single-issuer holdings are limited to 25% of total assets, excluding U.S. government securities and other regulated investment companies.','total assets','class3_security_level'),
 ('ISSUER75',4332,'For 75% of total assets, purchases may not exceed 10% of one issuer voting securities or result in over 5% of fund total assets in that issuer; U.S. government, agency and instrumentality obligations are excepted.','fund total assets and issuer voting securities','class3_security_level'),
 ('INDUSTRY',4333,'Do not concentrate in issuers whose principal activities share an industry or group of industries. This source classification is not FF12; no numerical FF12 cap is inferred.','source-defined industry/group','class3_source_taxonomy_differs_from_FF12'),
 ('OBJECTIVE_CHANGE',4335,'The investment objective cannot be materially changed without a shareholder vote.','governance condition','class3_conditional'),
 ('BORROWING',4327,'Borrowing is allowed only as permitted by the governing statutes, rules and regulators.','transaction attributes','class3_statutory_instrument_rule'),
 ('BORROWING_COVER',4394,'Maintain continuous asset coverage of 300% of borrowings, measured as total assets including borrowings less liabilities other than borrowings; temporary/emergency borrowing not exceeding 5% of total assets at borrowing has the stated exception.','borrowings and total assets','class3_security_and_path_dependent'),
 ('COMMODITIES',4329,'Commodity investments are allowed only as permitted by the governing statutes, rules and regulators.','instrument attributes','class3_statutory_instrument_rule'),
 ('LOANS',4336,'Loans are allowed only as permitted by the governing statutes, rules and regulators.','instrument attributes','class3_statutory_instrument_rule'),
 ('REAL_ESTATE',4337,'Direct real estate is prohibited except property acquired through ownership of securities or instruments; real-estate-company and real-estate-backed instruments are allowed.','instrument attributes','class3_instrument_rule'),
 ('SENIOR',4338,'Senior securities may be issued only under the stated statutory and regulatory permissions.','instrument attributes','class3_statutory_instrument_rule'),
 ('UNDERWRITING',4343,'Do not underwrite another issuer securities, except being deemed an underwriter in purchases or sales of portfolio securities.','transaction attributes','class3_transaction_rule'),
 ('PURCHASE_TIME',4344,'Percentage restrictions are generally tested on purchase; subsequent market movements alone do not breach a met restriction. Statutory exceptions, including continuous borrowing requirements and explicit quarter-end tests, remain applicable.','purchase-time holdings with explicit exceptions','class3_path_dependent'),
 ('ILLIQUID15',4864,'Aggregate illiquid investments are limited to 15% of NAV. Illiquid means not reasonably saleable within seven calendar days under current conditions without significantly changing market value.','NAV','class3_security_liquidity'),
 ('LENDING',4880,'Securities lending is limited to one-third of total assets; permitted collateral must remain at least 100% of loaned securities value, be marked to market, and satisfy termination and income rights.','total assets and collateral value','class3_security_transaction'),
 ('TEMPORARY_DEPARTURE',374,'Temporary departures require the advisor to judge them in the fund best interest and consistent with its objective. More favorably priced or needed-liquidity derivatives/ETFs, advisor transitions and large cash flows may justify departures from normal limits; alternate derivative exposure may address issuer/industry limits.','conditional portfolio state','class3_conditional'),
 ('DEFENSIVE',377,'Temporary defensive departures may respond to adverse or unusual market, economic, political or other conditions through substantial cash equivalents or less volatile instruments; these positions may fail to achieve the investment objective.','conditional portfolio state','class3_conditional'),
 ('VANGUARD_OWNERSHIP',4346,'The fundamental policies do not prevent the fund from owning Vanguard securities, lending to Vanguard or contributing to its costs or other financial requirements as part owner.','ownership-specific exception','class3_conditional'),
 ('BORROWING_RESTORE',4395,'If asset coverage falls below 300%, the fund may be required to sell holdings within three days, excluding Sundays and holidays, to reduce debt and restore coverage despite disadvantageous investment timing.','borrowing coverage and elapsed days','class3_path_dependent'),
]
evidence = [{'path': str(OUT / n), 'sha256': hashlib.sha256((OUT / n).read_bytes()).hexdigest(), 'capture_method': 'official SEC page text returned by web retrieval; not original HTML bytes'} for n in FILES]
constraints = []
for rid, line, text, denominator, handling in rules:
    doc = FILES[2] if line < 1000 else FILES[4] if line >= 4800 else FILES[1]
    constraints.append(dict(evidence_id='VPMCX_'+rid, source_document_id=Path(doc).stem, source_url=URL, source_line=line, text=text, denominator=denominator, handling=handling, numerically_enforced_in_FF12=False))
supplements = [
 ('2025-02-03','0001683863-25-000554','f40485d0.htm','Expense ratios and expense examples only.'),
 ('2025-02-21','0001683863-25-000986','f40794d1.htm','Portfolio disclosure schedules and service providers; no portfolio allocation change.'),
 ('2025-02-27','0001683863-25-001366','f40901d1.htm','Trustee elections, audit/risk committee and biographies.'),
 ('2025-03-24','0001683863-25-002403','f41206d1.htm','Redemption activity risk and investor frequent-trading exemptions.'),
 ('2025-07-02','0001683863-25-005558','f42371d1.htm','Officer appointments and biographies.'),
 ('2025-08-28','0001683863-25-007112','f42753d1.htm','Board investment committee oversight description.'),
 ('2025-09-30','0001193125-25-224194','f43052d1.htm','Legal/secretary leadership and biographies.'),
 ('2025-11-24','0001193125-25-293310','f43417d1.htm','Advisory fee structure and expense ratios; explicitly leaves investment objective, strategies and policies unchanged.'),
]
profile = dict(fund_id='F02', period='development', verified=True, objective='Long-term capital appreciation.', mandatory_constraints=constraints, A=[], b=[], source_url=URL, source_evidence_ids=[Path(n).stem for n in FILES], publication_date='2025-01-31', document_date='2025-01-31', filing_accession='0001683863-25-000459', cutoff='2025-12-31', capture_method='official SEC extracted sections and supplement chain; direct original HTML acquisition returned 403 and is not evidence', evidence_sha256=evidence[1]['sha256'], evidence_files=evidence, human_review_mode='user_assumed_completed', actual_independent_signatures=None, version_chain_verified=True, supplement_review=[dict(publication_date=d, accession=a, source_url='https://www.sec.gov/Archives/edgar/data/752177/'+a.replace('-','')+'/'+f, allocation_effect=n) for d,a,f,n in supplements], numerical_scope_note='Security, country, liquidity, instrument, purchase-time and source-industry restrictions cannot be certified from twelve FF12 weights. A and b are empty; no invented 80% equity mandate, 50%-basket requirement or 25% per-FF12 cap is imposed. The SAI 50% diversification clause expressly excludes PRIMECAP. Common-equity sleeve and outside assets remain fixed.')
(OUT/'VPMCX_development_mandate.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'fund':'F02','period':'development','rules':len(constraints),'verified':True}))
