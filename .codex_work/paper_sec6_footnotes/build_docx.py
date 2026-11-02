from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from lxml import etree

WORK = Path(__file__).parent
SOURCE = Path('C:/Users/Insun/Downloads/LIBERA_6절_통합축약_각주추가.md')
OUTPUT = Path('C:/Users/Insun/Downloads/소논문_6절_결과에따른해결방안_각주.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R}

md = SOURCE.read_text(encoding='utf-8-sig')
body_md = re.split(r'(?m)^\[\^13\]:', md, maxsplit=1)[0].strip()
# Two adjacent references to the same PAL paper become one Word footnote.
body_md = body_md.replace('[^15][^16]', '[^15]')
paragraphs = body_md.split('\n\n')
title = paragraphs.pop(0).removeprefix('## ')

# Each item is author/year, linked title, URL, publication details.
papers = {
    'lewis': ('Lewis, P., et al. (2020). ', 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks', 'https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html', '. Advances in Neural Information Processing Systems, 33, 9459–9474.'),
    'gao': ('Gao, L., et al. (2023). ', 'PAL: Program-aided Language Models', 'https://proceedings.mlr.press/v202/gao23f.html', '. ICML 2023, PMLR 202, 10764–10799.'),
    'gou': ('Gou, Z., et al. (2024). ', 'CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing', 'https://arxiv.org/abs/2305.11738v4', '. ICLR 2024. arXiv:2305.11738v4.'),
    'matton': ('Matton, K., Ness, R. O., Guttag, J., & Kıcıman, E. (2025). ', 'Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations', 'https://proceedings.iclr.cc/paper_files/paper/2025/file/b5ec50eb177908f21f78ed0d76ed525c-Paper-Conference.pdf', '. ICLR 2025.'),
    'doshi': ('Doshi, A. R., & Hauser, O. P. (2024). ', 'Generative AI enhances individual creativity but reduces the collective diversity of novel content', 'https://discovery.ucl.ac.uk/id/eprint/10195027/', '. Science Advances, 10(28), eadn5290. DOI: 10.1126/sciadv.adn5290.'),
    'bommasani': ('Bommasani, R., et al. (2022). ', 'Picking on the Same Person: Does Algorithmic Monoculture lead to Outcome Homogenization?', 'https://proceedings.neurips.cc/paper_files/paper/2022/hash/17a234c91f746d9625a75cf8a8731ee2-Abstract-Conference.html', '. Advances in Neural Information Processing Systems, 35, 3663–3678.'),
    'hornuf': ('Hornuf, L., Streich, D. J., & Töllich, N. (2025). ', 'Making GenAI Smarter: Evidence from a Portfolio Allocation Experiment', 'https://www.ifo.de/DocDL/cesifo1_wp11862.pdf', '. CESifo Working Paper No. 11862.'),
    'hansen': ('Hansen, A. L., & Lee, S. J. (2025). ', 'Financial Stability Implications of Generative AI: Taming the Animal Spirits', 'https://www.federalreserve.gov/econres/feds/financial-stability-implications-of-generative-ai-taming-the-animal-spirits.htm', '. FEDS 2025-090, Board of Governors of the Federal Reserve System. DOI: 10.17016/FEDS.2025.090.'),
    'anand': ('Anand, K., Kazinnik, S., Leonello, A., & Panetti, E. (2026). ', 'Ex Machina: financial stability in the age of artificial intelligence', 'https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp3225~52d8adae99.en.pdf', '. ECB Working Paper Series No. 3225. DOI: 10.2866/4103076.'),
}
note_keys = {'13': ['lewis'], '15': ['gao'], '17': ['gou'], '18': ['matton'], '20': ['doshi', 'bommasani', 'hornuf'], '19': ['matton'], '21': ['hansen', 'anand']}

doc = Document()
section = doc.sections[0]
section.page_width = Mm(210)
section.page_height = Mm(297)
section.top_margin = section.bottom_margin = Mm(22)
section.left_margin = section.right_margin = Mm(24)
section.header_distance = section.footer_distance = Mm(10)

def font(style, size, east='맑은 고딕', latin='Malgun Gothic'):
    style.font.name = latin
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    rp = style.element.get_or_add_rPr()
    rf = rp.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rp.insert(0, rf)
    for attr, value in [('ascii', latin), ('hAnsi', latin), ('eastAsia', east), ('cs', latin)]:
        rf.set(qn('w:' + attr), value)
    for attr in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        rf.attrib.pop(qn('w:' + attr), None)

normal = doc.styles['Normal']
font(normal, 10)
normal.paragraph_format.line_spacing = Pt(14.5)
normal.paragraph_format.space_after = Pt(7)
normal.paragraph_format.widow_control = True
normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
font(doc.styles['Title'], 13)
doc.styles['Title'].font.bold = True
doc.styles['Title'].paragraph_format.space_before = Pt(0)
doc.styles['Title'].paragraph_format.space_after = Pt(12)
doc.styles['Title'].paragraph_format.keep_with_next = True
doc.styles['Title'].paragraph_format.line_spacing = 1.2
doc.styles['Title'].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

for sty_name in ('Footnote Text', 'Footnote Reference'):
    if sty_name not in doc.styles:
        from docx.enum.style import WD_STYLE_TYPE
        doc.styles.add_style(sty_name, WD_STYLE_TYPE.PARAGRAPH if sty_name == 'Footnote Text' else WD_STYLE_TYPE.CHARACTER)
font(doc.styles['Footnote Text'], 8.5)
fp = doc.styles['Footnote Text'].paragraph_format
fp.line_spacing = Pt(11)
fp.space_before = Pt(0)
fp.space_after = Pt(3)
fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
fp.widow_control = True
font(doc.styles['Footnote Reference'], 8)
doc.styles['Footnote Reference'].font.superscript = True
# The bundled Word template contains blue borders in its Title styles.
for border in list(doc.styles.element.xpath('.//w:pBdr')):
    border.getparent().remove(border)
for style in (normal, doc.styles['Title'], doc.styles['Footnote Text']):
    pp = style.element.get_or_add_pPr()
    snap = OxmlElement('w:snapToGrid')
    snap.set(qn('w:val'), '0')
    pp.append(snap)
for grid in list(section._sectPr.findall(qn('w:docGrid'))):
    section._sectPr.remove(grid)
doc.add_paragraph(title, style='Title')

order = []
for text in paragraphs:
    p = doc.add_paragraph()
    for piece in re.split(r'(\[\^\d+\])', text):
        match = re.fullmatch(r'\[\^(\d+)\]', piece)
        if match:
            old_id = match.group(1)
            order.append(old_id)
            run = p.add_run()
            run.style = doc.styles['Footnote Reference']
            ref = OxmlElement('w:footnoteReference')
            ref.set(qn('w:id'), str(len(order)))
            run._r.append(ref)
        elif piece:
            p.add_run(piece)

# Ordinary Word footnotes at the bottom of the page, numbered continuously.
fnpr = OxmlElement('w:footnotePr')
for name, value in [('pos', 'pageBottom'), ('numFmt', 'decimal'), ('numStart', '1'), ('numRestart', 'continuous')]:
    item = OxmlElement('w:' + name)
    item.set(qn('w:val'), value)
    fnpr.append(item)
doc.settings.element.append(fnpr)
doc.core_properties.title = title
doc.core_properties.subject = '공통 GenAI와 기관투자자의 전략적 이질성 보존'
doc.core_properties.author = 'LIBERA'
doc.core_properties.last_modified_by = 'LIBERA'
stage = WORK / 'body.docx'
doc.save(stage)

def el(tag, **attrs):
    item = etree.Element('{' + W + '}' + tag)
    for key, value in attrs.items():
        item.set('{' + W + '}' + key, str(value))
    return item

def run(parent, text=None, style=None):
    r = etree.SubElement(parent, '{' + W + '}r')
    if style:
        rp = etree.SubElement(r, '{' + W + '}rPr')
        rp.append(el('rStyle', val=style))
    if text is not None:
        t = etree.SubElement(r, '{' + W + '}t')
        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        t.text = text
    return r

notes = etree.Element('{' + W + '}footnotes', nsmap={'w': W, 'r': R})
for note_id, kind in [(-1, 'separator'), (0, 'continuationSeparator')]:
    n = etree.SubElement(notes, '{' + W + '}footnote', {'{' + W + '}type': kind, '{' + W + '}id': str(note_id)})
    p = etree.SubElement(n, '{' + W + '}p')
    run(p).append(el(kind))

note_rels = etree.Element('{' + PR + '}Relationships', nsmap={None: PR})
hyperlink_count = 0
for index, old_id in enumerate(order, start=1):
    n = etree.SubElement(notes, '{' + W + '}footnote', {'{' + W + '}id': str(index)})
    for citation_index, key in enumerate(note_keys[old_id]):
        p = etree.SubElement(n, '{' + W + '}p')
        pp = etree.SubElement(p, '{' + W + '}pPr')
        pp.append(el('pStyle', val=doc.styles['Footnote Text'].style_id))
        pp.append(el('keepLines'))
        if citation_index < len(note_keys[old_id]) - 1:
            pp.append(el('keepNext'))
        if citation_index == 0:
            run(p, style=doc.styles['Footnote Reference'].style_id).append(el('footnoteRef'))
            run(p, ' ')
        prefix, linked_title, url, suffix = papers[key]
        if old_id == '19':
            prefix = 'Matton 등(2025), 앞의 논문. '
            linked_title = '원문 PDF'
            suffix = ''
        run(p, prefix)
        hyperlink_count += 1
        rel_id = 'rId' + str(hyperlink_count)
        etree.SubElement(note_rels, '{' + PR + '}Relationship', Id=rel_id, Type=R + '/hyperlink', Target=url, TargetMode='External')
        link = etree.SubElement(p, '{' + W + '}hyperlink', {'{' + R + '}id': rel_id})
        lr = run(link, linked_title)
        rp = etree.Element('{' + W + '}rPr')
        rp.append(el('color', val='1F4E79'))
        rp.append(el('u', val='single'))
        lr.insert(0, rp)
        run(p, suffix)

with ZipFile(stage) as z:
    package = {name: z.read(name) for name in z.namelist()}
relationships = etree.fromstring(package['word/_rels/document.xml.rels'])
etree.SubElement(relationships, '{' + PR + '}Relationship', Id='rIdFootnotes', Type=R + '/footnotes', Target='footnotes.xml')
content_types = etree.fromstring(package['[Content_Types].xml'])
etree.SubElement(content_types, '{' + CT + '}Override', PartName='/word/footnotes.xml', ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml')

def xml_bytes(root):
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)

package['word/_rels/document.xml.rels'] = xml_bytes(relationships)
package['[Content_Types].xml'] = xml_bytes(content_types)
package['word/footnotes.xml'] = xml_bytes(notes)
package['word/_rels/footnotes.xml.rels'] = xml_bytes(note_rels)
with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as z:
    for name, data in package.items():
        z.writestr(name, data)

body_xml = etree.fromstring(package['word/document.xml'])
actual_texts = [''.join(p.xpath('.//w:t/text()', namespaces=NS)) for p in body_xml.findall('.//w:body/w:p', NS)]
expected_texts = [title] + [re.sub(r'\[\^\d+\]', '', p) for p in paragraphs]
assert actual_texts == expected_texts
refs = body_xml.findall('.//w:footnoteReference', NS)
assert len(refs) == len(order) == 7
assert len(notes.findall('w:footnote', NS)) == 9
assert len(note_rels) == 10
audit = {'output': str(OUTPUT), 'body_paragraphs': len(paragraphs), 'word_footnotes': len(order), 'hyperlinks_in_footnotes': len(note_rels), 'source_to_word_note': {old: new for new, old in enumerate(order, 1)}, 'body_text_preserved': True}
(WORK / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(audit, ensure_ascii=False))
