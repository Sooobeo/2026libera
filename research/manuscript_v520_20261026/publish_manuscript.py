"""Render a reviewed manuscript to portable Markdown and reader HTML."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re

ROOT = Path(__file__).resolve().parents[2]


def safe(text):
    return str(text).replace('|', '\\|').replace('\n', '<br>')


def render(source, md_path, html_path):
    m = json.loads(source.read_text(encoding='utf-8'))
    md = ['# ' + m['title'], '', m['subtitle'], '', m['date'] + '  |  v' + m['version'], '']
    esc = lambda t: html.escape(str(t))
    body = [f'<header><h1>{esc(m["title"])}</h1><p class="subtitle">{esc(m["subtitle"])}</p><p class="meta">{esc(m["date"])} · v{esc(m["version"])}</p></header>']
    toc = []
    for i, b in enumerate(m['blocks']):
        typ = b['type']
        if typ == 'heading':
            text = re.sub(r'^(\d+) (\d+) ', r'\1.\2 ', b['text'])
            level = b['level'] + 1
            md.extend(['#' * level + ' ' + text, ''])
            body.append(f'<h{level} id="sec-{i}">{esc(text)}</h{level}>')
            if b['level'] == 1:
                toc.append((text, f'sec-{i}'))
        elif typ == 'paragraph':
            md.extend([b['text'], ''])
            body.append('<p>' + esc(b['text']) + '</p>')
        elif typ == 'table':
            md.extend(['**' + b['caption'] + '**', '', '| ' + ' | '.join(safe(x) for x in b['headers']) + ' |', '| ' + ' | '.join('---' for _ in b['headers']) + ' |'])
            md.extend('| ' + ' | '.join(safe(x) for x in row) + ' |' for row in b['rows'])
            md.extend(['', '*주: ' + b.get('note', '') + '*', ''])
            header = ''.join('<th scope="col">' + esc(x) + '</th>' for x in b['headers'])
            rows = ''.join('<tr>' + ''.join('<td>' + esc(x) + '</td>' for x in row) + '</tr>' for row in b['rows'])
            body.append('<figure><figcaption>' + esc(b['caption']) + '</figcaption><div class="table-wrap"><table><thead><tr>' + header + '</tr></thead><tbody>' + rows + '</tbody></table></div><p class="note">' + esc(b.get('note', '')) + '</p></figure>')
        elif typ == 'reference':
            # The conference overview is not used by the newly written paper.
            if b.get('id') == 'conference_overview':
                continue
            links = ([{'label': '원문', 'url': b['url']}] if b.get('url') else []) + b.get('links', [])
            md.extend([b['text'] + ('  ' if links else '') + ' · '.join('[' + x['label'] + '](' + x['url'] + ')' for x in links), ''])
            body.append('<p class="reference">' + esc(b['text']) + ' ' + ' · '.join('<a href="' + esc(x['url']) + '">' + esc(x['label']) + '</a>' for x in links) + '</p>')
        else:
            raise ValueError(typ)
    nav = '<nav aria-label="목차"><details><summary>목차</summary><ol>' + ''.join(f'<li><a href="#{anchor}">{esc(title)}</a></li>' for title, anchor in toc) + '</ol></details></nav>'
    style = '''
    :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f1f2f3;color:#191919;font-family:"Malgun Gothic","Noto Sans KR",sans-serif;font-size:16px;line-height:1.9}
    main{max-width:1020px;margin:32px auto 64px;padding:54px 62px;background:#fff}header{margin-bottom:24px}h1,h2,h3{color:#000;line-height:1.5;word-break:keep-all}h1{font-size:30px;margin:0 0 12px}h2{font-size:24px;margin:44px 0 15px}h3{font-size:19px;margin:30px 0 12px}p{margin:0 0 17px;word-break:keep-all;overflow-wrap:anywhere}.subtitle{font-size:19px}.meta,.note{font-size:13px;color:#4b4b4b}.meta{margin-bottom:0}nav{margin:28px 0 38px}summary{cursor:pointer;font-weight:600}nav ol{list-style:none;padding-left:0}nav li{margin:4px 0}a{color:#1c4c6a;text-underline-offset:3px}figure{margin:26px 0}figcaption{font-weight:700;font-size:15px;margin-bottom:9px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.65}th,td{border:1px solid #d9d9d9;padding:9px 11px;vertical-align:middle;white-space:pre-line;overflow-wrap:anywhere}th{background:#e8edf1;color:#000}.note{line-height:1.7;margin:8px 0 0}.reference{font-size:14px;line-height:1.75;padding-left:20px;text-indent:-20px}
    @media(max-width:760px){main{margin:0;padding:28px 20px}h1{font-size:25px}h2{font-size:22px}table{min-width:650px}}
    @media print{body{background:#fff;font-size:10.5pt;line-height:1.65}main{max-width:none;margin:0;padding:0}nav{display:none}h1{font-size:19pt}h2{font-size:14pt;margin-top:22pt}h3{font-size:11.5pt}h2,h3,figcaption{break-after:avoid}p{orphans:2;widows:2}table{font-size:8.5pt;line-height:1.4}th,td{padding:5pt 6pt}tr{break-inside:avoid}thead{display:table-header-group}.reference{font-size:9pt}.note{font-size:8.5pt}.table-wrap{overflow:visible}@page{size:A4;margin:20mm 22mm}}
    '''
    page = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(m['title']) + '</title><style>' + style + '</style></head><body><main>' + body[0] + nav + ''.join(body[1:]) + '</main></body></html>'
    for path, text in [(md_path, '\n'.join(md)), (html_path, page)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'markdown': str(md_path), 'html': str(html_path), 'blocks': len(m['blocks']),
            'tables': sum(b['type'] == 'table' for b in m['blocks']),
            'prose_characters': sum(len(b['text']) for b in m['blocks'] if b['type'] == 'paragraph')}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=Path)
    ap.add_argument('--stem', required=True)
    ap.add_argument('--outdir', type=Path, default=ROOT / 'paper')
    args = ap.parse_args()
    result = render(args.source, args.outdir / (args.stem + '.md'), args.outdir / (args.stem + '.html'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
