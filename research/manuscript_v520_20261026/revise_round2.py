"""Apply the second documented review and write the final manuscript source."""
from pathlib import Path
import hashlib
import json
import re

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]


def main():
    src = WORK / 'revised_round1.json'
    m = json.loads(src.read_text(encoding='utf-8'))
    replacements = {
        'UBS Neutral과 이유 미제공은 기관 자료에 관한 사실이고, 가격 선반영은 추가 가설이며, 이를 이용한 감액은 운용판단이다.':
            '본 실험의 UBS 입력에서 정보기술의 등급은 Neutral이고 별도 산업별 이유는 제공되지 않았다. 가격 선반영은 모델의 추가 가설이며, 이를 이용한 감액은 별도의 운용판단이다.',
        '계산기는 금액 또는 정수 단위 이동을 적용하여 합계 100%와 의도한 방향을 유지한다.':
            '계산기는 증감 합계가 0이고 적용 후 모든 비중이 비음수이며 명시 제약을 충족하는 변경만 적용한다. 이때 금액 또는 정수 단위 이동으로 합계 100%와 선언한 증감 방향을 보존한다.',
        '이 구분은 처음부터 유효한 배분에서 늘릴 곳과 재원을 줄일 곳을 동시에 결정하는 설계의 필요성으로 이어진다.':
            '이 관찰을 바탕으로, 처음부터 유효한 배분에서 증액할 산업과 감액할 산업을 함께 정하는 방식을 검토할 수 있다.',
        '원고 v5.1은 2026년 10월 26일 완료된 실험 자료를 유지하면서 결과 해석과 대응 설계를 보강하였다. 최근 동향 확인은 같은 날짜까지 접근 가능한 원문·공식 기술 자료를 대상으로 했으며 체계적 문헌고찰을 수행한 것은 아니다. 기존 v5.0과 원응답·수치 집계는 보존하였다. 새 근거 개입이나 제안 절차의 효과 실험은 실행하지 않았다.':
            '본 원고 v5.2의 실험 자료와 대응 설계의 근거는 v5.1에 보관된 기록을 계승한다. 문헌 검토는 2026년 10월 26일까지 접근 가능한 원문·공식 기술 자료를 대상으로 한 목적형 탐색이며 체계적 문헌고찰은 아니다. 기존 원고와 원응답·수치 집계는 보존하였고, 이번 원고 작성 과정에서 새 생성 실험이나 근거 개입 및 대응 효과의 검증을 수행하지 않았다.'
    }
    for old, new in replacements.items():
        hits = 0
        for b in m['blocks']:
            if b['type'] == 'paragraph' and old in b['text']:
                b['text'] = b['text'].replace(old, new)
                hits += 1
        assert hits == 1, (old, hits)

    author_prefixes = {
        'kleinberg2021': 'Kleinberg, J., & Raghavan, M.',
        'bommasani2022': 'Bommasani, R., Creel, K. A., Kumar, A., Jurafsky, D., & Liang, P.',
        'doshi2024': 'Doshi, A. R., & Hauser, O. P.',
        'hornuf2025': 'Hornuf, L., Streich, D. J., & Töllich, N.',
        'quek2025': 'Quek, R. W. H., Vittori, E., Ong, K., Mao, R., Cambria, E., & Mengaldo, G.',
        'laban2025': 'Laban, P., Hayashi, H., Zhou, Y., & Neville, J.',
        'portbench2026': 'Zhao, Y., Chen, S., & Su, N.',
        'e2a2026': 'Wang, X., Xu, Y., & Wang, J.',
        'markowitz1952': 'Markowitz, H.',
        'pombal2026': 'Pombal, J., Rei, R., & Martins, A. F. T.',
        'shi2025': 'Shi, L., Ma, C., Liang, W., Diao, X., Ma, W., & Vosoughi, S.',
        'fsb2024': 'Financial Stability Board.',
    }
    for b in m['blocks']:
        if b['type'] == 'reference' and b.get('id') in author_prefixes:
            b['text'] = re.sub(r'^.*?\(', author_prefixes[b['id']] + ' (', b['text'], count=1)

    target = ROOT / 'paper/v520_manuscript_20261026.json'
    target.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    record = {
        'review_round': 2,
        'input_sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
        'review_file': 'review_round2.md',
        'output': str(target.relative_to(ROOT)),
        'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'review_items_addressed': ['R2-01', 'R2-02', 'R2-03', 'R2-04', 'R2-05'],
        'implementation_notes': {
            'R2-01': 'Data and source lineage clarified in the appendix; editorial review history is supplied in a separate review record.',
            'R2-02': 'UBS reason omission scoped to the supplied information-technology input.',
            'R2-03': 'Zero total movement, post-change nonnegativity, and explicit constraints required before application.',
            'R2-04': 'One possible design, not a necessity established by the observation.',
            'R2-05': 'English personal-author references normalized to surname and initials; existing years, titles and URLs retained.'
        },
        'data_tables_changed': False,
        'new_experiments': 0,
    }
    (WORK / 'revision_round2.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
