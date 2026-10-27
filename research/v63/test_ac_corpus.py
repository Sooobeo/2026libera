"""Checks on the actual source corpus; no model experiments are simulated here."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/v63_20261027'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

class ActualCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=read(DATA/'continuation_sources/documents_v2.json')
        cls.docs=cls.corpus['documents']
        cls.catalog=read(DATA/'numerical/evaluator_only/source_catalog_v2.json')

    def test_dates_scope_and_source_hashes(self):
        self.assertEqual({d['fund_id'] for d in self.docs if d['period']=='A'}, {'COMMON','F01','F02','F03','F04'})
        self.assertEqual({d['fund_id'] for d in self.docs if d['period']=='C'}, {'COMMON'})
        for d in self.docs:
            self.assertEqual(hashlib.sha256((ROOT/d['source_path']).read_bytes()).hexdigest(),d['source_bytes_sha256'])
            self.assertLessEqual(d['publication_date'],'2026-03-31' if d['period']=='A' else '2026-06-30')
            if d['period']=='C':self.assertGreater(d['publication_date'],'2026-03-31')

    def test_every_visible_id_is_grounded_and_no_evaluator_facts_leak(self):
        ids=[]
        for d in self.docs:
            for u in d['units']:
                ids.extend(u['evidence_ids'])
                self.assertNotIn('facts',u)
                self.assertNotIn('value',u)
                for eid in u['evidence_ids']:
                    self.assertIn(eid,u['text'])
                    self.assertEqual(self.catalog[eid]['source_text'],u['original_normalized_text'])
                    self.assertEqual(self.catalog[eid]['document_id'],d['document_id'])
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),set(self.catalog))

    def test_all_projection_cells_and_numeric_definitions_preserved(self):
        for d in self.docs:
            if 'FOMC' not in d['document_id']:continue
            units=[u for u in d['units'] if 'Table 1 row' in u['source_locator'] and 'all four columns' in u['source_locator']]
            self.assertEqual(len(units),30) # 5 variables x current/prior x 3 statistics
            for u in units:
                for year in ('2026:','2027:','2028:','Longer run:'):self.assertIn(year,u['text'])
                self.assertIn('Percent',u['text'])
                self.assertTrue(any(s in u['text'] for s in ('median is the middle','central tendency excludes','range for a variable')))
                self.assertTrue(any(s in u['text'] for s in ('fourth quarter','end of the specified calendar year')))
            gold=[f for v in self.catalog.values() if v['document_id']==d['document_id'] for f in v.get('facts',[])]
            current=[f for f in gold if f['variable']=='Change in real GDP' and f['statistic']=='Median' and f['target_period']=='2026']
            self.assertEqual(current[0]['value'],2.4 if d['period']=='A' else 2.2)
            self.assertEqual(len(gold),114) # six blank core-PCE longer-run cells

    def test_fund_attribution_and_scope_are_explicit(self):
        f01=next(d for d in self.docs if d['fund_id']=='F01')
        self.assertTrue(all('K6' not in u['text'] for u in f01['units']))
        self.assertEqual(next(d for d in self.docs if d['fund_id']=='F03')['role'],'fund_investment_outlook')
        self.assertIn('No historically eligible own-fund new outlook bytes',self.corpus['C_scope_limitation'])

    def test_continued_pdf_sentences_and_gold_denominator(self):
        d=next(d for d in self.docs if d['fund_id']=='F03')
        text=' '.join(u['original_normalized_text'] for u in d['units'])
        for phrase in ('in our view, are being overlooked','Information Technology is now about 35%','the stock traded under 16 times earnings'):
            self.assertIn(phrase,text)
        for doc in self.docs:
            visible={e for u in doc['units'] for e in u['evidence_ids']}
            self.assertTrue(set(doc['retrieval_gold_evidence_ids'])<=visible)
            self.assertTrue(doc['retrieval_gold_evidence_ids'])
        self.assertLess(len(d['retrieval_gold_evidence_ids']),len(d['units']))

    def test_protocol_ticker_fund_and_actual_source_owner_agree(self):
        protocol=read(next((ROOT/'plan').glob('*v6.3*.json')))
        by_ticker={f['ticker']:f for f in protocol['data_contract']['funds']}
        expected_sources={'FCNTX':('FCNTX_A_shareholder_report.html','Fidelity'),
                          'VPMCX':('VPMCX_annual_20250930_browser_dom.json','Vanguard'),
                          'DODGX':('DODGX_2025_review_transcript.pdf','Dodge & Cox'),
                          'TRBCX':('TRBCX_annual_2025.pdf','T. Rowe Price')}
        for d in self.docs:
            if d['fund_id']=='COMMON':continue
            registered=by_ticker[d['ticker']]
            self.assertEqual(d['fund_id'],registered['fund_id'])
            self.assertEqual(d['source_owner'],registered['name'])
            self.assertIn(d['ticker'],d['document_id'])
            source_filename,owner=expected_sources[d['ticker']]
            self.assertEqual(Path(d['source_path']).name,source_filename)
            self.assertIn(owner,d['source_owner'])
            if d['ticker']=='DODGX':self.assertIn('Dodge & Cox Stock Fund',d['source_owner_evidence']['source_literal'])
            else:self.assertIn(d['ticker'],d['source_owner_evidence']['source_literal'])
            for u in d['units']:
                for eid in u['evidence_ids']:
                    self.assertEqual(self.catalog[eid]['fund_id'],registered['fund_id'])
                    self.assertEqual(self.catalog[eid]['ticker'],registered['ticker'])
                    self.assertEqual(self.catalog[eid]['source_owner'],registered['name'])
                    self.assertIn(d['ticker'],eid)

if __name__=='__main__':unittest.main()
