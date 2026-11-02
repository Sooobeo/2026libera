from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import re
import sys

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from lxml import etree

WORK = Path(__file__).parent
SOURCE = WORK / 'final.md'
OUTPUT = Path('C:/Users/Insun/Downloads/소논문_6절_해결방안_재작성_각주.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R}

markdown = SOURCE.read_text(encoding='utf-8-sig')
body_md = re.split(r'(?m)^\[\^\d+\]:', markdown, maxsplit=1)[0].strip()
definitions = dict(re.findall(r'(?m)^\[\^(\d+)\]:\s*(.+)$', markdown))
paragraphs = [p.strip() for p in body_md.split('\n\n') if p.strip()]
title = paragraphs.pop(0).removeprefix('## ')
references = re.findall(r'\[\^(\d+)\]', body_md)
assert set(references) == set(definitions)
assert len(references) == len(set(references))

doc = Document()
section = doc.sections[0]
section.page_width, section.page_height = Mm(210), Mm(297)
section.top_margin = section.bottom_margin = Mm(22)
section.left_margin = section.right_margin = Mm(24)
section.header_distance = section.footer_distance = Mm(10)

def font(style, size):
    style.font.name = 'Malgun Gothic'
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    rp = style.element.get_or_add_rPr()
    rf = rp.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rp.insert(0, rf)
    for attr in ('ascii', 'hAnsi', 'cs'):
        rf.set(qn('w:' + attr), 'Malgun Gothic')
    rf.set(qn('w:eastAsia'), '맑은 고딕')
    for attr in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        rf.attrib.pop(qn('w:' + attr), None)
    lang = rp.find(qn('w:lang'))
    if lang is None:
        lang = OxmlElement('w:lang')
        rp.append(lang)
    lang.set(qn('w:eastAsia'), 'ko-KR')

normal = doc.styles['Normal']
font(normal, 10)
normal.paragraph_format.line_spacing = Pt(14.5)
normal.paragraph_format.space_after = Pt(7)
normal.paragraph_format.widow_control = True
normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
title_style = doc.styles['Title']
font(title_style, 13)
title_style.font.bold = True
title_style.paragraph_format.space_before = Pt(0)
title_style.paragraph_format.space_after = Pt(12)
title_style.paragraph_format.keep_with_next = True
title_style.paragraph_format.line_spacing = Pt(17)
title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
for name, kind in [('Footnote Text', WD_STYLE_TYPE.PARAGRAPH), ('Footnote Reference', WD_STYLE_TYPE.CHARACTER)]:
    if name not in doc.styles:
        doc.styles.add_style(name, kind)
font(doc.styles['Footnote Text'], 8.5)
fp = doc.styles['Footnote Text'].paragraph_format
fp.line_spacing = Pt(11)
fp.space_after = Pt(3)
fp.alignment = WD_ALIGN_PARAGRAPH.LEFT
fp.widow_control = True
font(doc.styles['Footnote Reference'], 8)
doc.styles['Footnote Reference'].font.superscript = True
for border in list(doc.styles.element.xpath('.//w:pBdr')):
    border.getparent().remove(border)
for style in [normal, title_style, doc.styles['Footnote Text']]:
    snap = OxmlElement('w:snapToGrid')
    snap.set(qn('w:val'), '0')
    style.element.get_or_add_pPr().append(snap)
for grid in list(section._sectPr.findall(qn('w:docGrid'))):
    section._sectPr.remove(grid)

doc.add_paragraph(title, style='Title')
for text in paragraphs:
    p = doc.add_paragraph()
    for part in re.split(r'(\[\^\d+\])', text):
        match = re.fullmatch(r'\[\^(\d+)\]', part)
        if match:
            r = p.add_run()
            r.style = doc.styles['Footnote Reference']
            ref = OxmlElement('w:footnoteReference')
            ref.set(qn('w:id'), str(references.index(match.group(1)) + 1))
            r._r.append(ref)
        elif part:
            p.add_run(part)

fnpr = OxmlElement('w:footnotePr')
for name, value in [('pos', 'pageBottom'), ('numFmt', 'decimal'), ('numStart', '1'), ('numRestart', 'continuous')]:
    item = OxmlElement('w:' + name)
    item.set(qn('w:val'), value)
    fnpr.append(item)
doc.settings.element.append(fnpr)
doc.core_properties.title = title
doc.core_properties.subject = '공통 GenAI의 중간 판단과 기관별 전략 차이 보존을 위한 Workflow RAG 보완 방안'
doc.core_properties.author = 'LIBERA'
doc.core_properties.last_modified_by = 'LIBERA'
doc.core_properties.comments = ''
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
for index, source_id in enumerate(references, start=1):
    n = etree.SubElement(notes, '{' + W + '}footnote', {'{' + W + '}id': str(index)})
    p = etree.SubElement(n, '{' + W + '}p')
    pp = etree.SubElement(p, '{' + W + '}pPr')
    pp.append(el('pStyle', val=doc.styles['Footnote Text'].style_id))
    pp.append(el('keepLines'))
    run(p, style=doc.styles['Footnote Reference'].style_id).append(el('footnoteRef'))
    run(p, ' ')
    value = definitions[source_id]
    offset = 0
    for match in re.finditer(r'\[([^\]]+)\]\((https?://[^)]+)\)', value):
        if match.start() > offset:
            run(p, value[offset:match.start()])
        rel_id = 'rId' + str(len(note_rels) + 1)
        etree.SubElement(note_rels, '{' + PR + '}Relationship', Id=rel_id, Type=R + '/hyperlink', Target=match.group(2), TargetMode='External')
        link = etree.SubElement(p, '{' + W + '}hyperlink', {'{' + R + '}id': rel_id})
        lr = run(link, match.group(1))
        rp = etree.Element('{' + W + '}rPr')
        rp.append(el('color', val='1F4E79'))
        rp.append(el('u', val='single'))
        lr.insert(0, rp)
        offset = match.end()
    if offset < len(value):
        run(p, value[offset:])

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

body = etree.fromstring(package['word/document.xml'])
actual_texts = [''.join(p.xpath('.//w:t/text()', namespaces=NS)) for p in body.findall('.//w:body/w:p', NS)]
expected = [title] + [re.sub(r'\[\^\d+\]', '', p) for p in paragraphs]
assert actual_texts == expected
assert len(body.findall('.//w:footnoteReference', NS)) == len(references)
assert len(notes.findall('w:footnote', NS)) == len(references) + 2
assert not etree.fromstring(package['word/styles.xml']).xpath('//w:pBdr', namespaces=NS)
audit = {'output': str(OUTPUT), 'source_md_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'docx_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), 'body_paragraphs': len(paragraphs), 'body_characters': sum(map(len, expected)), 'word_footnotes': len(references), 'external_links': len(note_rels), 'body_text_preserved': True, 'no_title_borders': True}
(WORK / 'document_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(audit, ensure_ascii=False))
