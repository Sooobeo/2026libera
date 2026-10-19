"""Review final reader documents against the fixed v492 protocol and records.

Text/DOM/link/formula audit only. No visual-render inspection is claimed here.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plan/LIBERA_대조군포함_실험계획_v4.9.2_20261019.html'
PAPER = ROOT / 'paper/LIBERA_텀페이퍼_초안_v4.9.2_20261019.html'
OUT = ROOT / 'research/v492_reader_documents_review_20261019.json'


def ref(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    if OUT.exists():
        raise SystemExit('Do not overwrite the completed document review; use a new version.')
    docs = {p.name: BeautifulSoup(p.read_text(encoding='utf8'), 'html.parser') for p in [PLAN, PAPER]}
    record = json.loads((ROOT / 'research/v492_computational_references_20261019.json').read_text(encoding='utf8'))
    checks = []
    local_links = []

    def check(name, ok, evidence):
        checks.append({'check': name, 'pass': bool(ok), 'evidence': evidence})

    for path in [PLAN, PAPER]:
        soup = docs[path.name]
        text = soup.get_text(' ', strip=True)
        prefix = path.parent.name + ':'
        check(prefix + 'no stale current-human-gate or four-total-final claim',
              '독립 사람 검토 전' not in text and 'VERSION 4.9.1' not in text and '최종안 4개' not in text and '산업 행 44개' not in text,
              'Historical v4.9.1 citations are retained; four source-conditioned cases remain correctly distinguished from the five total cases.')
        check(prefix + 'five-case and denominator statements', all(x in text for x in ['사례는 5개', '최대 10번', '최종안 5개', '산업 행 55개', '44행', 'C는 11행']),
              '5 cases × 11 rows = 55; four source-conditioned finals give 44 and one C gives 11.')
        check(prefix + 'C has no source penalty and no duplicated sample', '기관 견해 충실성은 해당 없음' in text and '대조군 표본이 두 개가 되지 않는다' in text,
              'One common C is reused only descriptively; invented source attribution remains an error.')
        check(prefix + 'all condition labels removed with masking limitation', 'E/L/C 표지와 실행순서를 제거' in text and '완전한 맹검은 아니다' in text,
              'The new protocol masks labels while admitting that actual contents can reveal conditions.')
        check(prefix + 'source interpretation is AI-assisted and not independent human validation', '사람 두 명의 검토는 필수 조건에서 제외' in text and '독립 사람 검증이나 평가자 간 신뢰도 확보로 표현하지 않는다' in text,
              'User-delegated AI review is not recast as a human-signature requirement.')
        check(prefix + 'model and engineering settings are explicit', all(x in text for x in ['Qwen3.5-4B', 'Q4_K_M', 'Ollama 0.35.1', '8,192', '65,536', '4,500', '70.5분', '75분']),
              '4500 sec = 75 min; roughly 70.46 min extrapolation is rounded to 70.5 for display, not represented as expected completion.')
        check(prefix + 'short throughput scenario caveat', '6토큰 출력' in text and '완료를 보장하지 않는다' in text and '하드웨어 운영 설정' in text,
              'The operational ceiling is not described as a paper-estimated behavioral setting.')
        check(prefix + 'no source gold or future-performance guarantee', '기관별 정답 비중과의 일치율은 계산하지 않는다' in text and '미래 수익이나 기관 전략의 최적해가 아니다' in text,
              '1/N and sample GMV do not optimize the full research objective or recover an institution portfolio.')
        check(prefix + 'raw outcomes, null comparisons and finite inference retained', '재생성·정규화·대체하지 않는다' in text and '비교는 미관측' in text and '독립 표본으로 늘리거나 유의성 검정을 하지 않는다' in text,
              'Arithmetic invalidity and infrastructure failures remain visible; similarity alone is not interpretation loss.')
        check(prefix + 'prepared status does not claim completed experimental results', '예비실험 실행과 본실험은 아직 결과가 없는 준비 단계' in text,
              'At this review no v492 pilot output has been reported or examined.')

        tables = [t for t in soup.select('table') if '최소분산 참고안' in t.get_text()]
        check(prefix + 'one complete numerical reference table', len(tables) == 1 and len(tables[0].select('tbody tr')) == 11,
              'The table is a display of the saved evaluator references.')
        numeric_ok = len(tables) == 1
        if numeric_ok:
            rows = tables[0].select('tbody tr')
            for i, row in enumerate(rows):
                cells = [x.get_text(strip=True) for x in row.select('td')]
                code = record['sector_codes'][i]
                wanted = [f"{record['references'][j]['weights'][code] * 100:.2f}%" for j in range(2)]
                numeric_ok = numeric_ok and cells[1:] == wanted
        check(prefix + 'all 22 reference numbers have correct two-decimal display', numeric_ok and '소수 둘째 자리까지 반올림' in text,
              'Compared each 1/N and GMV display value with the immutable full-precision JSON in the same sector order.')
        ids = [x['id'] for x in soup.select('[id]')]
        check(prefix + 'unique HTML identifiers', len(ids) == len(set(ids)), 'No repeated section/reference anchor ID found.')
        errors = []
        for a in soup.select('a[href]'):
            href = a['href']
            target = urlsplit(href)
            if target.scheme:
                continue
            destination = (path.parent / unquote(target.path)).resolve() if target.path else path
            exists = destination.is_file()
            valid_fragment = True
            if exists and target.fragment and destination.suffix.lower() == '.html':
                target_soup = soup if destination == path else BeautifulSoup(destination.read_text(encoding='utf8'), 'html.parser')
                valid_fragment = target_soup.find(id=unquote(target.fragment)) is not None
            local_links.append({'document': path.relative_to(ROOT).as_posix(), 'href': href, 'exists': exists, 'fragment_valid': valid_fragment})
            if not exists or not valid_fragment:
                errors.append(href)
        check(prefix + 'local paths and HTML fragments resolve', not errors, 'External citation URLs were not all re-fetched in this editorial review.')

    paper = docs[PAPER.name]
    header = paper.header.get_text(' ', strip=True)
    check('paper header and navigation name current version', 'VERSION 4.9.2' in header and all('v491' not in a['href'] and 'v4.9.1' not in a['href'] for a in paper.select('header a[href]')),
          'Current plan, r2 evaluation and v492 process ledger are linked; historical references are left as history.')
    common = paper.select_one('#common-context-method').get_text(' ', strip=True)
    check('common-context paragraph distinguishes E/L and C', 'E/L 사이에서는' in common and 'C와의 비교에서는 기관 자료를 제공하는지 자체가 달라진다' in common,
          'C absence is part of the design, not merely another first-exposure time.')
    check('literature timing statement scoped to E/L', 'E/L의 최종 단계에는 같은 기관 자료를 양쪽에 제공' in paper.select_one('#literature').get_text(' ', strip=True),
          'C never receives that institution packet.')
    check('topic and claim boundaries preserved', all(x in paper.get_text() for x in ['비명시적·분산적 알고리즘화', '관측 대상은 보이는 근거와 원비중', '시장 전체의 인과효과가 아니다', '기관의 사적 목표·실제 보유·고유 최적배분을 관측하지 않는다']),
          'The broader business/economics motivation remains connected to observable source-to-choice traces without overstating identification.')
    result = {
        'protocol_version': '4.9.2', 'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'review_kind': 'AI technical, editorial and methods-consistency review; no independent humans',
        'input_refs': [ref(PLAN), ref(PAPER), ref(ROOT / 'research/build_v492_reader_documents.py'), ref(ROOT / 'research/v492_evaluation_protocol_20261019_r2.json'), ref(ROOT / 'research/v492_source_review_20261019.json'), ref(ROOT / 'research/v492_computational_references_20261019.json'), ref(ROOT / 'research/v492_resource_decision_20261019.json')],
        'initial_findings_resolved': [
            {'finding': 'Stale VERSION 4.9.1 and independent-human-review-pending header', 'resolution': 'Now VERSION 4.9.2 and actual preparation status without a human prerequisite.'},
            {'finding': 'Three current navigation links targeted prior v491 artifacts', 'resolution': 'Now current v492 plan, r2 evaluation and process ledger.'},
            {'finding': 'Common-context ending described only first-exposure timing', 'resolution': 'E/L timing and C permanent source absence are explicitly separated.'},
            {'finding': 'Optional E/L-only masking wording conflicted with new protocol', 'resolution': 'All E/L/C labels and execution order are removed, with imperfect-masking caveat.'},
            {'finding': 'Literature paragraph said both final stages receive source without naming E/L scope', 'resolution': 'Explicit E/L qualifier now prevents implying that C receives it.'},
        ],
        'checks': checks, 'local_links': local_links, 'open_material_findings': [],
        'visual_render_inspected': False,
        'scope_limits': ['Text, DOM structure, local links and numeric displays checked; no browser screenshot/layout acceptance in this receipt.', 'Historical literature verification scope is inherited and disclosed; this task did not reread every background source.', 'No pilot/main results are present, and this receipt does not establish execution feasibility.', 'Reader documents may later update execution status; such versions require their own updated hash/review record.'],
        'model_calls_by_this_review': 0,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'status': result['status'], 'checks': len(checks), 'sha256': ref(OUT)['sha256'], 'failed': [x['check'] for x in checks if not x['pass']]}, indent=2))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
