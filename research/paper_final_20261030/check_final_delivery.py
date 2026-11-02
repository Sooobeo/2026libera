"""Check the final paper exports, retain compact evidence, and update the index."""
from pathlib import Path
import hashlib
import json
import re
import sys

import fitz

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
QA = ROOT / 'tmp/paper_final_20261030_qa'
STEM = 'LIBERA_소논문_최종결과반영_20261030'
SOURCE = ROOT / 'paper' / (STEM + '.md')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


source = SOURCE.read_text(encoding='utf-8')
render = read(QA / (STEM + '.render_qa.json'))
word = read(QA / (STEM + '.word_export.json'))
numeric = read(QA / 'numeric_check.json')
browser = read(QA / 'browser_check.json')
assert render['status'] == browser['status'] == numeric['status'] == 'passed'
assert word['status'] == 'completed'
assert render['source_sha256'] == sha(SOURCE)
assert numeric['manuscript_sha256_current'] == sha(SOURCE)
assert render['counts']['tables'] == 15 and render['counts']['images'] == 2
assert not render['text_checks']['docx_mismatches']
assert not render['text_checks']['html_missing_blocks']
assert all(all(row.values()) for row in render['table_checks'])
assert browser['toc']['initiallyCollapsed']
assert not browser['desktop']['overflow'] and not browser['mobile']['overflow']

artifacts = []
for suffix, key in [('.md', 'source_sha256'), ('.docx', 'docx_sha256'), ('.html', 'html_sha256')]:
    p = SOURCE.with_suffix(suffix)
    assert sha(p) == render[key]
    artifacts.append({'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': sha(p)})
pdf_path = SOURCE.with_suffix('.pdf')
assert sha(pdf_path) == word['pdf_sha256'] == render['pdf_export']['sha256']
assert word['input_sha256_before'] == word['input_sha256_after'] == sha(SOURCE.with_suffix('.docx'))
assert word['existing_word_pids_before'] == word['existing_word_pids_still_running_after']
artifacts.append({'path': str(pdf_path.relative_to(ROOT)), 'bytes': pdf_path.stat().st_size, 'sha256': sha(pdf_path)})

assert re.findall(r'^## (\d+)\.', source, re.M) == list(map(str, range(1, 10)))
assert re.findall(r'^\*\*표 (\d+)\.', source, re.M) == list(map(str, range(1, 12)))
assert re.findall(r'^\*\*그림 (\d+)\.', source, re.M) == ['1', '2']
assert not re.search(r'^\*주:', source, re.M)
assert '단정할' not in source and '통계적으로 유의' not in source
references = source.split('## 참고문헌\n\n')[1].split('## 부록 A.')[0].strip().split('\n\n')
assert len(references) == 15
assert source.startswith('# 공통 GenAI는 기관투자자의 전략적 이질성을 축소하는가?')
assert '배치와 완화효과를 중심으로' in source

doc = fitz.open(pdf_path)
issues = []
previews = []
section_pages = []
for i, page in enumerate(doc):
    text = page.get_text()
    compact = re.sub(r'\s+', '', text)
    if len(text.strip()) < 20:
        issues.append({'page': i + 1, 'issue': 'near_empty'})
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                x0, y0, x1, y1 = span['bbox']
                if x0 < 0 or y0 < 0 or x1 > page.rect.width + 1 or y1 > page.rect.height + 1:
                    issues.append({'page': i + 1, 'issue': 'outside_page', 'text': span['text']})
    for key in ['1.문제제기', '5.실험결과', '7.해결방안:전략적이질성을보존하는WorkflowRAG', '9.결론']:
        if key in compact:
            section_pages.append({'page': i + 1, 'heading': key})
    if i == 0 or any(k in compact for k in [
        '5.1전략적이질성의축소와확대', '표9.실험결과와전략적이질성보존을위한해결방안',
        '7.3변경량과목표비중의수치관계를강제', '9.결론', '참고문헌']):
        image = QA / f'final_pdf_page_{i+1:02}.png'
        page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).save(image)
        previews.append(str(image.relative_to(ROOT)))
full_pdf = re.sub(r'\s+', '', ''.join(p.get_text() for p in doc))
for phrase in ['공통GenAI는기관투자자의전략적이질성을축소하는가?', '배치와완화효과를중심으로',
               '62.5%', '98.37', '70.6%', 'PAL', 'CRITIC', '3225', '기존보유대비기대수익증감']:
    if phrase not in full_pdf:
        issues.append({'issue': 'missing_pdf_text', 'phrase': phrase})
assert not issues, issues
assert '주제어' in doc[0].get_text(), 'Keep the final abstract and keywords on the first page.'

report = {
    'schema': 'libera_final_paper_delivery_v1', 'status': 'passed', 'date': '2026-10-30',
    'research_center': '원초록·제목: 공통 GenAI와 기관투자자의 전략적 이질성, Workflow RAG 배치와 완화효과',
    'artifacts': artifacts, 'pdf_pages': len(doc), 'main_sections': 9,
    'main_numbered_tables': 11, 'total_tables': 15, 'figures': 2, 'references': 15,
    'content_transfer': render['text_checks'], 'source_blocks_checked': render['counts']['source_text_blocks_checked'],
    'numeric_check': {k: numeric[k] for k in ['status', 'check_count', 'failure_count',
        'source_sha256', 'frozen_analysis_expected_sha256', 'original_data_mutated',
        'manuscript_sha256_current']},
    'detailed_numeric_receipt': {'path': str((QA / 'numeric_check.json').relative_to(ROOT)),
                                'sha256': sha(QA / 'numeric_check.json')},
    'browser': browser, 'pdf_layout_issues': issues, 'section_pages': section_pages,
    'previews': previews, 'abstract_and_keywords_on_first_page': True,
    'editorial_review': {
        'thesis_and_original_title_preserved': True,
        'failure_analysis_supports_the_heterogeneity_question': True,
        'performed_and_proposed_procedures_distinguished': True,
        'self_reported_changes_structured_for_code_checks': True,
        'expected_gain_and_optimal_regret_distinguished': True,
        'source_results_average_comparisons_explicit': True,
        'style_guidance_applied_without_reusing_outdated_experimental_facts': True,
    },
    'new_experiment_calls': 0, 'frozen_experimental_data_modified': False,
    'visual_review': 'completed' if '--visual-reviewed' in sys.argv else 'pending',
}
(HERE / 'final_delivery_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

readme = '''LIBERA 최종 전체 논문과 본실험 결과
2026년 10월 30일

최신 전체 논문 — 원초록의 문제 제기·완료 실험·결과·해결방안 통합
  LIBERA_소논문_최종결과반영_20261030.docx  — 수정용 Word
  LIBERA_소논문_최종결과반영_20261030.pdf   — 읽기·인쇄용
  LIBERA_소논문_최종결과반영_20261030.html  — 브라우저 읽기용, 그림 내장
  LIBERA_소논문_최종결과반영_20261030.md    — 본문 원본

논문 제목
  공통 GenAI는 기관투자자의 전략적 이질성을 축소하는가?
  액티브 주식형 펀드의 자산배분 프로세스 내 Workflow RAG 배치와 완화효과를 중심으로

구성
  문제 제기 → 선행연구 → 실험설계 → 실험과정·평가 → 결과 → 논의
  → 전략적 이질성을 보존하는 Workflow RAG 해결방안 → 후속 검증·기관 적용 → 결론
  본문 인용과 참고문헌 15편, 원문 링크, 재현 부록 포함

항목별 적용 기준
  문제와 제목: 원초록 반영 v5.4의 연구 질문 보존
  설계·해결방안: ../plan/LIBERA_최종실험설계_결과와해결방안_20261030.html
  수행 설계: ../plan/LIBERA_최종수행_실험설계서_20261030.html
  결과: B-main의 160개 종료 결과와 2026-10-29 검산 자료
  문체: LIBERA_소논문_구성과문장_레퍼런스분석_20261026.md

상세 결과 해석본
  LIBERA_본실험_결과해석_20261029.md / .docx / .html / .pdf

도표와 검수 근거
  assets_20261029/                        — 이번 원고에서도 사용한 검증 도표
  ../research/paper_final_20261029/        — 집계표·수치 검산·기존 문헌 확인
  ../research/solution_design_20261030/    — 해결방안 문헌 추가 확인
  ../research/paper_final_20261030/        — 집필 코드·최신 자료 적용 기록·최종 검수

2026-10-29 원고와 v5.4 이전 원고는 해당 날짜·버전의 기록이다.
기존 다섯 조건 결과를 이번 본실험 표본에 합산하지 않았다.
보완 절차의 완화효과는 제안된 후속 검증 대상으로 명시했다.
'''
(ROOT / 'paper/README.txt').write_text(readme, encoding='utf-8', newline='\n')
print(json.dumps({'status': report['status'], 'pages': len(doc), 'tables': 15,
                  'references': 15, 'previews': previews}, ensure_ascii=False))
