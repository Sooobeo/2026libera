"""Read-only structural and provenance review of the new manuscript."""
from pathlib import Path
import hashlib,json,re,sys,zipfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
src=ROOT/'paper/v493_manuscript_20261019.json'
out=ROOT/'paper/LIBERA_소논문_연구설계와진행현황_20261019.docx'
m=json.loads(src.read_text(encoding='utf-8')); checks=[]
def ck(name,value):checks.append({'check':name,'pass':bool(value)})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
N={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with zipfile.ZipFile(out) as z:
    x=ET.fromstring(z.read('word/document.xml'))
    st=ET.fromstring(z.read('word/styles.xml'))
    rel=ET.fromstring(z.read('word/_rels/document.xml.rels'))
text=''.join(x.itertext())
paras=[''.join(p.itertext()) for p in x.findall('.//w:p',N)]
ck('Title text preserved',m['title'] in text)
ck('All prose and references preserved',all(b['text'] in text for b in m['blocks'] if b['type'] in ('paragraph','heading','reference')))
ck('All table cells preserved',all(str(c) in text for b in m['blocks'] if b['type']=='table' for row in [b['headers'],*b['rows']] for c in row))
tables=x.findall('.//w:tbl',N)
ck('Six scientific comparison tables',len(tables)==6)
ck('Table headers repeat',all(t.find('.//w:tblHeader',N) is not None for t in tables))
ck('Explicit light grey table borders',all(len(t.findall('./w:tblPr/w:tblBorders/*',N))==6 and all(b.get('{'+N['w']+'}color')=='D9D9D9' for b in t.findall('./w:tblPr/w:tblBorders/*',N)) for t in tables))
ck('No fixed table row heights',not x.findall('.//w:trHeight',N))
ck('No title or heading paragraph border',all(not el.findall('.//w:pBdr',N) for el in st.findall('w:style',N) if el.get('{'+N['w']+'}styleId') in ('Title','Subtitle','Heading1','Heading2')))
urls=[b['url'] for b in m['blocks'] if b.get('url')]+[l['url'] for b in m['blocks'] for l in b.get('links',[])]
targets=[r.attrib.get('Target') for r in rel]
ck('All scholarly and data URLs linked',all(u in targets for u in urls))
ck('No internal citation placeholders or editorial instructions',not any(v in text for v in ('turn0search','use arXiv version','TODO','TBD','[Author]')))
ck('No Unicode replacement glyph', '\ufffd' not in text)
ck('Study progress cutoff explicit','2026년 10월 19일 18시' in text and '본실험 미실행' in text)
ck('Incomplete study not presented as completed evidence','실증 결론은 아직 없다' in text)
ck('No comparison data implies unanswered question','조건 차이에 관한 연구질문은 미해결' in text)
ck('Reference calculations separate from company gold','기관별 정답이나 AI의 실험 결과가 아니다' in text)
ck('Strategic AI C present','전략 비교의 대조군은 C' in text)
ck('Public source rather than private institutional goal','실제 Fidelity와 UBS의 최적 포트폴리오를 복원하지 않는다' in text)
ck('Unvalidated semantic evaluation limitation','사람에 의한 타당화나 독립 평가자 신뢰도 검증을 거치지 않았다' in text)
calc=json.loads((ROOT/'research/v492_computational_references_20261019.json').read_text(encoding='utf-8'))
t5=next(b for b in m['blocks'] if b.get('caption','').startswith('표 5'))
gmv=next(r for r in calc['references'] if r['reference_id']=='long_only_minimum_variance')
ck('Reference weights match frozen calculation',all(row[1]==f'{100/11:.2f}' and row[2]==f'{gmv["weights"][code]*100:.2f}' for row,code in zip(t5['rows'],calc['sector_codes'])))
pins={
'paper/LIBERA_텀페이퍼_초안_v4.9.2_20261019.html':'680f33b8cc58712c876b588ccc6f2004a4525cf6eded2f6d7431561cb2343123',
'plan/LIBERA_대조군포함_실험계획_v4.9.2_20261019.html':'a3c21e64e9e30c87dc6b39d4311b57e0475e9fe85cc6bab9fd6794032ae08c83',
'research/v492_evaluation_protocol_20261019_r2.json':'807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1',
'research/v492_computational_references_20261019.json':'d65a7d302ed03f4fc430134b947f9f81f10b8b84fec1855511f258144a46bd11',
'research/v492_source_review_20261019.json':'3f6e4bd952b0bbf1d4e3487bb00a5e839a9f907038e43e895807425c21747718',
}
for p,h in pins.items():ck('Frozen file unchanged '+p,sha(ROOT/p)==h)
result={'round':3,'scope':'document structural/data/provenance review, separate from all-page visual review','source_sha256':sha(src),'docx_sha256':sha(out),'checks':checks,'passed':sum(c['pass'] for c in checks),'total':len(checks),'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','tables':len(tables),'hyperlinks':len(urls),'model_calls':0,'pilot_response_content_read':False}
(ROOT/'research/v493_manuscript_round3_structural_20261019.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False))
sys.exit(0 if result['status']=='PASS' else 1)
