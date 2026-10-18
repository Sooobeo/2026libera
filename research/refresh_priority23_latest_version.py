"""Preserve the first screening memo and add the subsequently checked v2 source."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'research/priority23_paper_candidates_20261018.json'
OUT = ROOT / 'research/priority23_paper_candidates_v2_20261018.json'
URL = 'https://arxiv.org/html/2609.38869v2'
SOURCE = ROOT / 'research/evidence/priority23_candidates_20261018/externalization_fulltext_v2.html'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite completed screening memo.')
    data = json.loads(OLD.read_text(encoding='utf-8'))
    for source in data['primary_sources']:
        if sha(ROOT / source['path']) != source['sha256']:
            raise RuntimeError('Existing source hash mismatch: ' + source['path'])
    req = urllib.request.Request(URL, headers={'User-Agent': 'LIBERA-public-research/1.0'})
    with urllib.request.urlopen(req, timeout=45) as response:
        blob, final, status = response.read(), response.url, response.status
    if status != 200 or not blob:
        raise RuntimeError('Latest source not retrieved')
    text = BeautifulSoup(blob, 'html.parser').get_text(' ', strip=True)
    required = [
        '2609.38869v2', '06 Oct 2026', 'Structured Evidence Registry',
        'same underlying registry', 'system prompt and output schema were kept unchanged',
        'subject–predicate–value', 'rather than the overall semantic truthfulness',
        'Qwen3-32B-Instruct', 'WRDS', 'Narrative Synthesis',
    ]
    checked = {phrase: phrase in text for phrase in required}
    if not all(checked.values()):
        raise RuntimeError('Source locator check failed: ' + repr(checked))
    if SOURCE.exists() and SOURCE.read_bytes() != blob:
        raise RuntimeError('Refusing to replace source snapshot')
    SOURCE.write_bytes(blob) if not SOURCE.exists() else None
    old_source = next(s for s in data['primary_sources'] if s['source_id'] == 'externalization_fulltext')
    old_source['usage'] = 'superseded_v1_snapshot_retained_for_provenance_not_current_candidate_basis'
    data['primary_sources'].append({
        'source_id': 'externalization_fulltext_v2', 'path': SOURCE.relative_to(ROOT).as_posix(),
        'url': URL, 'resolved_url': final, 'http_status': status,
        'sha256': sha(SOURCE), 'size_bytes': len(blob), 'usage': 'current_candidate_basis',
    })
    data['schema_version'] = 'libera_priority23_paper_screening_1.1'
    data['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    data['supersedes_screening_memo'] = {'path': OLD.relative_to(ROOT).as_posix(), 'sha256': sha(OLD)}
    data['version_verification'] = {
        'externalization': 'Latest abs dateline reports v2 on 6 Oct 2026; v2 full text checked. v1 preserved.',
        'other_candidates': 'Downloaded abstract datelines show FinFIRST/Same-Number/E2A v1 and FundaPod v5.',
        'checks': checked,
        'limitation': 'This is targeted screening and latest version verification at retrieval time, not an exhaustive review.',
    }
    paper = next(p for p in data['candidates'] if p['id'] == 'externalization')
    paper['version'] = 2
    paper['source_ids'] = ['externalization_fulltext_v2', 'externalization_abs']
    paper['locators'].append('Section 4.5, Table 6: structured-claim metric and narrative-level aggregation differ')
    paper['limits'].append('v2는 구조화된 주장 유형별 집계와 서술문 판단이 달라질 수 있음을 보여준다. 자동 필드 검사를 자유 서술의 정확성 전체로 확대하지 않는다.')
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    markup = OLD.with_suffix('.html').read_text(encoding='utf-8')
    markup = markup.replace('2609.38869v1', '2609.38869v2')
    markup = markup.replace('priority23_paper_candidates_20261018.json', OUT.name)
    markup = markup.replace('<table>', '<p>최종 버전 확인: Reasoning Externalization은 2026년 10월 6일 v2를 사용합니다. 기존 v1 검토 파일은 보존했습니다. v2의 §4.5도 확인하여 구조화 필드의 집계와 서술문의 의미 평가를 구분했습니다.</p><table>', 1)
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': sha(OUT), 'source_count': len(data['primary_sources']), 'source_checks_passed': len(checked)}, indent=2))


if __name__ == '__main__':
    main()
