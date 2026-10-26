"""Check content parity and structural formatting against the JSON source."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from html.parser import HTMLParser
import json, hashlib, sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'paper/v500_manuscript_20261026.json'
DOCX=ROOT/'paper/LIBERA_소논문_실험결과와해결방향_v5.0_20261026.docx'
HTML=ROOT/'paper/LIBERA_텀페이퍼_v5.0_20261026.html'
QA=ROOT/'research/paper_update_20261026/qa'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def tx(e):
    return ''.join((n.text or '') if n.tag==f'{{{NS["w"]}}}t' else ('\n' if n.tag==f'{{{NS["w"]}}}br' else '\t') for n in e.xpath('.//w:t|.//w:br|.//w:tab',namespaces=NS))
def norm(s):return ' '.join(s.split())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

class HTMLTexts(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=False
    def handle_starttag(self,t,a):
        if t in ('script','style'):self.skip=True
    def handle_endtag(self,t):
        if t in ('script','style'):self.skip=False
    def handle_data(self,d):
        if not self.skip:self.parts.append(d)

def main():
    source=json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    expected=[source['title'],source.get('subtitle',''),source.get('date','')+'  |  '+source.get('version','')]
    for b in source['blocks']:
        if b['type'] in ('heading','paragraph','bullet','list_item'):expected.append(b['text'])
        elif b['type']=='table':
            expected.append(b['caption']);expected+=list(map(str,b['headers']))
            for row in b['rows']:expected+=list(map(str,row))
            expected.append(b.get('note',''))
        elif b['type']=='reference':expected.append(b['text']+' '+('원문' if b.get('url') else '')+''.join('  '+x['label'] for x in b.get('links',[])))
        else:raise ValueError('Unknown type')
    with ZipFile(DOCX) as z:
        tree=etree.fromstring(z.read('word/document.xml'));styles=etree.fromstring(z.read('word/styles.xml'))
        actual=[tx(p) for p in tree.xpath('./w:body//w:p',namespaces=NS)]
        relationships=etree.fromstring(z.read('word/_rels/document.xml.rels'))
    mismatches=[]
    for i in range(max(len(expected),len(actual))):
        a=actual[i] if i<len(actual) else None;e=expected[i] if i<len(expected) else None
        if a is None or e is None or norm(a)!=norm(e):mismatches.append({'position':i,'expected':e,'actual':a})
    parser=HTMLTexts();parser.feed(HTML.read_text(encoding='utf-8'))
    allhtml=norm(' '.join(parser.parts));htmlmissing=[]
    for i,b in enumerate(source['blocks']):
        texts=[b['text']] if 'text' in b else [b['caption'],*b['headers'],*(v for r in b['rows'] for v in r),b.get('note','')]
        for t in texts:
            if norm(str(t)) not in allhtml:htmlmissing.append({'block':i,'text':t})
    tables=tree.xpath('./w:body/w:tbl',namespaces=NS)
    table_findings=[]
    for i,t in enumerate(tables):
        table_findings.append({'table':i+1,'header_repeats':bool(t.xpath('./w:tr[1]/w:trPr/w:tblHeader',namespaces=NS)),'light_gray_borders':len(t.xpath('./w:tblPr/w:tblBorders/*[@w:color="D9D9D9"]',namespaces=NS))==6,'fixed_row_heights':len(t.xpath('.//w:trHeight[@w:hRule="exact"]',namespaces=NS))})
    title_style=styles.xpath('./w:style[@w:styleId="Title"]',namespaces=NS)[0]
    title_paras=tree.xpath('./w:body/w:p[w:pPr/w:pStyle[@w:val="Title"]]',namespaces=NS)
    result={'status':'pass' if not mismatches and not htmlmissing and len(title_paras)==1 and all(t['header_repeats'] and t['light_gray_borders'] and not t['fixed_row_heights'] for t in table_findings) else 'fail','source_sha256':digest(SOURCE),'docx_sha256':digest(DOCX),'html_sha256':digest(HTML),'expected_text_nodes':len(expected),'actual_text_nodes':len(actual),'docx_content_mismatches':mismatches,'html_missing_source_text':htmlmissing,'title_paragraph_count':len(title_paras),'title_border_count':len(title_style.xpath('.//w:pBdr',namespaces=NS)),'tables':table_findings,'external_hyperlinks':len(relationships.xpath('//*[local-name()="Relationship" and @TargetMode="External"]')),'runtime_python':sys.executable,'visual_review_required':True}
    (QA/'structural_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if result['status']!='pass':raise SystemExit(1)
if __name__=='__main__':main()
