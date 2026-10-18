"""Create the pre-experiment manuscript and align the protocol with LIBERA.

No model experiment is run. Original September documents remain untouched.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plan'
PAPER = ROOT / 'paper'
PAPER.mkdir(exist_ok=True)
ARCHIVE = PLAN / 'archive'
ARCHIVE.mkdir(exist_ok=True)
plan_path = PLAN / 'LIBERA_실험계획_20261017.html'
config_path = PLAN / 'LIBERA_실험설정_20261017.json'
for source, destination in [(plan_path, ARCHIVE / 'LIBERA_실험계획_v3.2.html'), (config_path, ARCHIVE / 'LIBERA_실험설정_v3.2.json')]:
    if not destination.exists():
        shutil.copy2(source, destination)
old = json.loads((ARCHIVE / 'LIBERA_실험설정_v3.2.json').read_text(encoding='utf-8'))
old_html = BeautifulSoup((ARCHIVE / 'LIBERA_실험계획_v3.2.html').read_text(encoding='utf-8'), 'html.parser')
css = old_html.find('style').get_text() + '''
.abstract{background:#f2f6f7;padding:24px 28px;margin:28px 0}.abstract h2{font-size:18px}.subtitle{font-size:20px;color:#425560}.status{border-left:3px solid #175b67;padding:12px 18px;background:#f4f7f8;font-size:14px}.paper-body p{text-align:justify}.references{list-style:none;padding:0}.references li{padding-left:24px;text-indent:-24px;margin:18px 0;font-size:14px}.references .refnote{text-indent:0}.small{font-size:14px}.decision{background:#faf8f2;border-left:3px solid #a1884e;padding:16px 20px}.equation{padding:14px 20px;background:#f5f7f9;font:15px/1.9 Consolas,"Malgun Gothic",monospace;overflow-wrap:anywhere}.paper-body h2{font-size:23px}.paper-body h3{font-size:18px}.paper-body td p{margin:0;text-align:left}@media print{.status,.abstract{background:transparent}.paper-body p{orphans:3;widows:3}.abstract{padding:10px 0}.references li{font-size:9pt}.equation{font-size:9pt}.subtitle{font-size:13pt}.decision{background:transparent}section{break-inside:auto}}
'''

refs = '''
<li id="ref-agarwal">Agarwal, S., &amp; Zhang, Y. (2026). <i>Does generative AI increase investment convergence?</i> [Preprint; October 3 revision]. SSRN. <a href="https://doi.org/10.2139/ssrn.7294279">https://doi.org/10.2139/ssrn.7294279</a><span class="refnote">저자 등록 페이지의 서지·초록·개정일 확인. 전문 미확인. 본문에서는 초록에 보고된 범위만 사용했다.</span></li>
<li id="ref-bommasani">Bommasani, R., Creel, K. A., Kumar, A., Jurafsky, D., &amp; Liang, P. (2022). Picking on the same person: Does algorithmic monoculture lead to outcome homogenization? <i>Advances in Neural Information Processing Systems, 35</i>. <a href="https://papers.neurips.cc/paper_files/paper/2022/hash/17a234c91f746d9625a75cf8a8731ee2-Abstract-Conference.html">게재본</a></li>
<li id="ref-chen">Chen, S., Sialm, C., &amp; Xu, D. X. (2026). <i>The growth and performance of artificial intelligence in asset management</i> (Working Paper No. 35273). National Bureau of Economic Research. <a href="https://doi.org/10.3386/w35273">https://doi.org/10.3386/w35273</a><span class="refnote">공식 서지·초록과 공저자 연구 목록 확인. 전문 미확인. 광범위한 AI와 헤지펀드 수익률 동조화를 다룬다.</span></li>
<li id="ref-dellacqua">Dell’Acqua, F., McFowland, E., III, Mollick, E., Lifshitz, H., Kellogg, K. C., Rajendran, S., Krayer, L., Candelon, F., &amp; Lakhani, K. R. (2026). Navigating the jagged technological frontier: Field experimental evidence of the effects of artificial intelligence on knowledge worker productivity and quality. <i>Organization Science</i>. Advance online publication. <a href="https://doi.org/10.1287/orsc.2025.21838">https://doi.org/10.1287/orsc.2025.21838</a><span class="refnote">2026년 게재 연구이며, 실험 자체가 2026년 최신 모델로 수행됐다는 뜻은 아니다.</span></li>
<li id="ref-doshi">Doshi, A. R., &amp; Hauser, O. P. (2024). Generative AI enhances individual creativity but reduces the collective diversity of novel content. <i>Science Advances, 10</i>(28), eadn5290. <a href="https://doi.org/10.1126/sciadv.adn5290">https://doi.org/10.1126/sciadv.adn5290</a></li>
<li id="ref-fsb24">Financial Stability Board. (2024). <i>The financial stability implications of artificial intelligence.</i> <a href="https://www.fsb.org/2024/11/the-financial-stability-implications-of-artificial-intelligence/">공식 보고서</a></li>
<li id="ref-fsb26">Financial Stability Board. (2026, October 15). <i>Sound practices for responsible adoption of artificial intelligence (AI): Final report.</i> <a href="https://www.fsb.org/2026/10/sound-practices-for-responsible-adoption-of-artificial-intelligence-ai-final-report/">공식 최종 보고서</a><span class="refnote">학술 논문이 아닌 정책·실무 보고서다. 비구속적 원칙을 제시하며 실험 조건이나 RAG 효과의 근거로 사용하지 않았다.</span></li>
<li id="ref-hansen">Hansen, A. L., &amp; Lee, S. J. (2025). <i>Financial stability implications of generative AI: Taming the animal spirits</i> (Finance and Economics Discussion Series 2025-090). Board of Governors of the Federal Reserve System. <a href="https://doi.org/10.17016/FEDS.2025.090">https://doi.org/10.17016/FEDS.2025.090</a><span class="refnote">2025년 9월 25일자 공식 원문 및 arXiv v1 확인. §4의 경제 모형과 §5의 실험 구조를 구분한다. 논문 자체도 herding과 공통모델 동질화를 구별한다.</span></li>
<li id="ref-hedden">Hedden, B., &amp; Raghavan, M. (2026). <i>Algorithmic monoculture and its critics</i> (Version 3) [Preprint]. arXiv. <a href="https://arxiv.org/abs/2604.06047v3">https://arxiv.org/abs/2604.06047v3</a></li>
<li id="ref-kleinberg">Kleinberg, J., &amp; Raghavan, M. (2021). Algorithmic monoculture and social welfare. <i>Proceedings of the National Academy of Sciences, 118</i>(22), e2018340118. <a href="https://doi.org/10.1073/pnas.2018340118">https://doi.org/10.1073/pnas.2018340118</a></li>
<li id="ref-lewis">Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-t., Rocktäschel, T., Riedel, S., &amp; Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. <i>Advances in Neural Information Processing Systems, 33</i>, 9459–9474. <a href="https://arxiv.org/abs/2005.11401">저자 원고</a></li>
<li id="ref-sheng">Sheng, J., Sun, Z., Yang, B., &amp; Zhang, A. L. (2026). Generative AI and asset management. <i>The Review of Financial Studies</i>, hhag050. Advance online publication. <a href="https://doi.org/10.1093/rfs/hhag050">https://doi.org/10.1093/rfs/hhag050</a><span class="refnote">최종 게재본 서지·초록 확인. 2025년 11월 저자 원고 전문도 별도 확인했지만, 구원고의 세부 내용을 최종본 확인으로 표시하지 않았다.</span></li>
'''

body = '''
<header>
<div class="eyebrow">LIBERA 2026 · TERM PAPER · PRE-EXPERIMENT DRAFT</div>
<h1>공통 생성형 AI 아래<br>필요한 투자판단 차이는 보존되는가?</h1>
<p class="subtitle">액티브 주식형 펀드의 정보처리 문제와 근거 제공 시점의 실험설계</p>
<p class="meta">문헌 검토와 연구설계 소논문 · 2026년 10월 17일 초안 · 저자 정보는 제출 전 기입</p>
<div class="status"><strong>초안의 범위.</strong> 이 글은 제안서의 논점을 논문 형태로 정리한 실험 전 원고다. 선행연구의 결과와 본 연구가 제안하는 검증을 구별한다. 자체 AI 실험 결과와 실제 기관의 행동 변화는 아직 관측하지 않았다. 제출 분량·파일 양식·자체 실험 결과의 필수 여부는 제공된 학술제 개요에 명시돼 있지 않다.</div>
<div class="toolbar"><button onclick="window.print()">인쇄 및 PDF 저장</button><a href="../plan/LIBERA_실험계획_20261017.html">수정 실험계획 v3.3</a><a href="#appendix">제출 준비와 남은 선택</a></div>
</header>
<div class="abstract" id="abstract"><h2>초록</h2>
<p>생성형 AI가 투자 업무의 정보 탐색과 분석을 지원할 때, 동일한 모델의 활용이 기관마다 달라야 할 판단까지 비슷하게 만들 수 있는가? 이 질문은 판단의 유사성 자체보다 기관별 정보가 경제적으로 적절하게 반영되는지에 초점을 맞춰야 한다. 본 연구는 액티브 주식형 펀드를 문제의 맥락으로 삼아 공통 알고리즘, 금융 분야의 AI 활용, 조직의 업무 설계에 관한 문헌을 검토한다. 문헌은 공통 AI의 효과가 일방적이지 않으며, 정보 구조와 과업에 따라 수렴과 품질 개선이 함께 나타날 수 있음을 시사한다. 이에 공개 펀드 문서의 근거 추출 검증과, 최적 행동을 계산할 수 있는 논문 기반 거래 과제의 정보 제공 시점 비교를 구분하여 제안한다. 핵심 평가는 단순한 답변 다양성이 아니라 필요한 행동 차이의 보존과 기대이익 손실이다. 본 연구의 현재 기여는 기관별 근거를 어느 단계에서 전달하고 재검토해야 하는지 검증할 틀을 제시하는 데 있다. 실제 펀드의 자산배분 동질화와 시장 안정성에 관한 효과는 후속 검증 과제로 남는다.</p>
<p class="small"><strong>주제어:</strong> 생성형 AI, 알고리즘 동질화, 정보 집약, 자산운용, 업무 설계, 검색 증강 생성</p></div>
<nav aria-label="논문 목차"><a href="#intro">1. 서론</a><a href="#literature">2. 선행연구와 연구 공백</a><a href="#framework">3. 개념과 연구질문</a><a href="#design">4. 연구방법과 실험설계</a><a href="#alternatives">5. 반론과 대안적 설명</a><a href="#implications">6. 조직의 대응 방향</a><a href="#limits">7. 한계와 후속 연구</a><a href="#conclusion">8. 결론</a><a href="#references">참고문헌</a><a href="#appendix">부록. 제출 준비와 남은 결정</a></nav>
<article class="paper-body">
<section id="intro"><h2>1. 서론</h2>
<p>서로 다른 투자기관이 같은 생성형 AI를 사용할 때, 기관의 판단은 어디에서 달라져야 하는가? 액티브 주식형 펀드는 같은 시장을 관찰하더라도 운용 목표, 투자 가능 범위, 보유 자산, 해석의 근거가 서로 다를 수 있다. 투자자가 여러 운용사를 선택하는 이유 역시 이들이 서로 다른 전문성과 판단을 제공할 수 있다는 기대와 관련된다. 따라서 기관이 공통 기술을 도입할 때 중요한 문제는 답변의 표현이 닮는지보다, 의사결정에 필요한 기관별 차이가 최종 권고에 남는지다.</p>
<p>이 문제는 AI가 최종 매매를 자동으로 결정하는 상황에만 국한되지 않는다. 사람의 승인을 전제로 하더라도, AI가 자료를 요약하고 검토 대상을 제안하며 초안을 만드는 단계에서 판단의 범위를 좁힐 수 있다. 초기 초안에 포함되지 않은 근거가 이후 검토에서 충분히 재고되지 않는다면, 기관 고유의 정보는 자료실에 존재하면서도 실제 결정에는 반영되지 않을 수 있다. 본 연구는 이러한 경로를 ‘비명시적·분산적 알고리즘화’라는 분석 관점으로 제시한다. 이는 이미 실증된 현상의 명칭이 아니라 여러 업무 단계에서 공통 AI의 영향이 누적될 가능성을 설명하기 위한 연구 개념이다.</p>
<p>공통 AI에 대한 우려를 곧바로 동질화의 증거로 바꿀 수는 없다. Financial Stability Board(FSB, <a href="#ref-fsb24">2024</a>)는 공통 공급자 의존과 상관된 행동을 잠재적 금융 취약성으로 논의하지만, 해당 보고서는 특정 모델이 실제 펀드의 판단을 획일화했다는 인과추정이 아니다. 오히려 더 정확한 공통 정보가 널리 사용되면 불필요한 오판이 줄어들어 기관들의 판단이 합리적으로 가까워질 수도 있다. 연구는 이 가능성을 반론으로 수용한 상태에서 출발해야 한다.</p>
<p>이에 본 연구의 중심 질문은 다음과 같다. <strong>같은 생성형 AI를 사용하는 조건에서, 서로 다른 의사결정 근거가 요구하는 판단 차이가 보존되는가? 동일한 근거를 업무의 어느 단계에서 제공하고 유지하는지가 그 보존과 판단 품질에 영향을 주는가?</strong> 경제학적으로는 분산된 정보가 선택에 반영되는 문제이며, 경영학적으로는 정보 전달과 검토 권한을 조직하는 문제다. 대응 방향 또한 AI 사용을 일괄적으로 줄이거나 답변을 강제로 다양하게 만드는 것이 아니라, 기관별 근거가 실제 선택을 바꿔야 할 때 바꿀 수 있는 업무 절차를 찾는 데 있다.</p>
<p>이 글은 먼저 상반된 선행연구를 검토하고, 필요한 판단 차이와 해로운 동질화를 정의한다. 이어 공개 문서 검증과 경제 모형에 기반한 최소 실험을 제안하고, 그 결과에 따라 달라질 조직의 대응 원칙을 논의한다. 현재 단계에서는 문헌과 설계의 타당성을 제시하며, 실험 전 가설을 확인된 사실로 서술하지 않는다.</p>
</section>
<section id="literature"><h2>2. 선행연구와 연구 공백</h2>
<h3>2.1. 공통 알고리즘의 효과는 무엇에 달려 있는가</h3>
<p>Kleinberg와 Raghavan(<a href="#ref-kleinberg">2021</a>)은 여러 선택자가 같은 알고리즘을 사용할 때 개별 정확도의 향상이 집단적 후생 개선으로 자동 연결되지 않을 수 있음을 이론적으로 보였다. Bommasani 등(<a href="#ref-bommasani">2022</a>)은 자료 공유와 모델 공유를 구분하고, 특히 공통 모델의 결과가 적용·적응 방식에 따라 달라질 수 있음을 보였다. 이 연구들은 공통 기술의 성능만으로 조직 전체의 결과를 판단할 수 없다는 출발점을 제공한다. 다만 해당 결과를 금융기관의 생성형 AI 사용에 그대로 옮길 수는 없다.</p>
<p>Hedden과 Raghavan(<a href="#ref-hedden">2026</a>)의 최근 비판적 검토 역시 알고리즘 동질화에 관한 일반적 우려를 구체적 정보 구조와 성과 기준에 따라 평가할 필요를 제기한다. 본 연구가 관심을 두는 것은 기술의 공유 자체보다 경제적으로 관련 있는 정보가 공통 도구를 통과하면서 어떻게 사용되는가다. 동일한 답이 옳을 수 있는 상황과 서로 다른 답이 필요한 상황을 함께 두어야 공통 AI의 작동 조건을 구별할 수 있다.</p>
<h3>2.2. 금융 분야의 결과는 한 방향으로 정리되지 않는다</h3>
<p>최신 금융 연구는 동질화에 관한 질문이 이미 실증적으로 다뤄지고 있음을 보여준다. Agarwal과 Zhang(<a href="#ref-agarwal">2026</a>)의 프리프린트 초록은 ChatGPT 등장 이후 생성형 AI 의존성과 펀드 포트폴리오 유사성의 관계가 강화되는 결과를 보고한다. 동시에 가격발견 개선과 실적발표 주변 유동성 저하를 함께 보고한다. 따라서 포트폴리오가 비슷해진다는 관측 하나만으로 그 경제적 효과를 일률적으로 평가할 수 없다. 본 초안은 이 연구의 초록과 서지만 확인했으며, 세부 식별 전략의 타당성을 재검증한 것으로 제시하지 않는다.</p>
<p>반대 방향의 결과도 중요하다. Chen 등(<a href="#ref-chen">2026</a>)은 AI를 사용하는 헤지펀드의 수익률 동조화가 더 낮다는 결과를 보고한다. 이는 광범위한 AI에 관한 관측연구이며, 생성형 AI와 실제 보유종목 유사성을 직접 측정한 결과는 아니다. Hansen과 Lee(<a href="#ref-hansen">2025</a>)의 통제된 거래 실험에서는 기본 조건의 AI가 인간보다 사적정보를 강하게 활용했다. 공통 AI가 기관별 정보를 언제나 무시한다고 가정하면 이러한 반대 증거를 설명할 수 없다.</p>
<p>조직의 보완 자원도 결과를 달리할 수 있다. Sheng 등(<a href="#ref-sheng">2026</a>)은 생성형 AI 활용의 성과가 AI 인력과 기업별 정보 분석 역량에 따라 달라질 수 있음을 보여준다. 다만 이는 실제 운용사를 다룬 관측 결과로, 기관별 근거 제공 시점을 무작위로 바꾼 실험은 아니다. 본 연구는 이 차이를 업무 단계에서 검증할 수 있는 비교로 좁히고자 한다.</p>
<h3>2.3. 품질과 다양성을 함께 평가하는 업무 설계 연구</h3>
<p>Doshi와 Hauser(<a href="#ref-doshi">2024</a>)의 창작 실험은 개별 산출물의 품질 개선과 집단적 다양성 감소가 함께 나타날 수 있음을 보였다. Dell’Acqua 등(<a href="#ref-dellacqua">2026</a>)의 지식 업무 실험은 AI의 효용이 과업에 따라 달라짐을 보여준다. 각각 창작과 컨설팅을 다루므로 금융 효과의 직접 증거는 아니지만, 다양성 지표와 품질 지표를 분리하고 업무 단계를 구체화해야 한다는 방법상의 근거를 제공한다.</p>
<p>검색 증강 생성(RAG)은 외부 자료를 검색해 생성 모델의 입력에 연결하는 접근이다(Lewis et al., <a href="#ref-lewis">2020</a>). 그러나 검색된 문서가 최종 판단에 사용된다는 사실은 별도로 확인해야 한다. 본 연구의 차별성은 ‘동질화를 처음 발견한다’는 주장에 있지 않다. 동일한 근거의 최초 제공 단계와 이후 재검토 기회를 바꿔, 필요한 정보 반응과 경제적 품질을 함께 비교하는 데 있다. 검색의 정확성과 제공된 근거의 활용 능력도 분리해 평가한다.</p>
</section>
<section id="framework"><h2>3. 개념과 연구질문</h2>
<p>본 연구에서 ‘필요한 판단 차이’란 기관의 이름이나 문체가 달라서 생기는 차이가 아니다. 동일한 공개 상황에서도 유효한 정보나 목적·제약의 차이 때문에 최선의 행동이 달라지는 경우를 뜻한다. 따라서 기존 보유 비중이 다르다는 사실만으로 서로 다른 최종 비중이 반드시 옳다고 가정하지 않는다. 거래 비용이나 제약, 전망이 목적식에 들어가지 않는다면, 같은 수익·위험 입력을 받은 기관들의 기준 배분은 같을 수 있다.</p>
<p>이 정의에 따라 단순한 수렴, 과잉수렴, 부정적 동질화를 구분한다. 단순한 수렴은 결과가 가까워진 상태다. 과잉수렴은 주어진 정보와 평가 기준에서 필요한 차이가 결과에 충분히 반영되지 않은 상태다. 부정적 동질화는 그 정보 반응의 부족이 기대이익 손실이나 유효한 제약 위반과 함께 나타나는 경우다. 본 연구의 핵심 평가는 마지막 경우를 식별하는 데 있으며, 답변 사이의 거리 감소만으로 피해를 선언하지 않는다.</p>
<p>연구질문은 세 가지다. 첫째, 서로 다른 유효한 정보가 다른 최적 행동을 요구하는 상황에서 같은 AI는 필요한 행동 차이를 보존하는가? 둘째, 같은 정보 묶음을 초기에 제공하고 유지하는 업무정책은 최종 검토 때 제공하는 정책보다 정보 반영과 판단 품질을 개선하는가? 셋째, 관측된 실패는 검색 단계의 누락과 근거 제공 이후의 활용 실패 중 어디에서 나타나는가? 이 질문들은 동일 모델을 사용하는 조건 내부의 정보 처리에 관한 것이며, 공통모델 채택 자체의 인과효과와는 구별된다.</p>
<p>검증할 방향 가설은 <strong>초기 근거 제공이 늦은 제공보다 불필요한 동일 행동과 기대이익 손실을 줄인다</strong>는 것이다. 다만 초기 정보가 이후 판단에서 잊히거나 늦은 정보가 더 두드러지게 활용될 수도 있다. 양방향 결과와 무효과를 모두 보고한다. 또 두 정보 조건의 최적 행동이 같은 사례에서는 판단 차이 증가를 개선으로 간주하지 않는다. 이 조건은 사적정보 추종률을 무조건 높이는 해법을 배제한다.</p>
</section>
<section id="design"><h2>4. 연구방법과 실험설계</h2>
<h3>4.1. 실제 맥락과 통제된 검증의 역할</h3>
<p>자료는 일반 연구자가 합법적으로 접근할 수 있는 공시, 운용사 공개 문서, 공개 산업 수익률, 논문에 명시된 모형으로 한정한다. 공개 펀드 문서에서 투자방침과 보유 현황이 어떤 형태로 제시되는지 확인하되, 비공개 내부 전망을 관측한 것으로 해석하지 않는다. 공개 문서에서 근거를 찾는 과제와 정답을 계산할 수 있는 거래 과제는 서로 다른 증거를 제공하므로 결과도 구분한다.</p>
<div class="table-wrap"><table><caption>표 1. 증거별 역할과 가능한 결론</caption><thead><tr><th>연구 구성</th><th>관측·비교 대상</th><th>입증할 수 있는 범위</th></tr></thead><tbody>
<tr><td>A. 공개 펀드 문서</td><td>운용 규칙·날짜·금액·출처의 추출과 근거 반영</td><td>문서 처리의 정확성과 실제 업무에 대한 관련성</td></tr>
<tr><td>B1. 논문 기반 거래 과제</td><td>고정된 시장 상황에서 정보와 제공 시점에 따른 행동</td><td>정보 반영의 최소 기제와 주어진 보수 기준의 손실</td></tr>
<tr><td>B2. 산업 배분 확장</td><td>기관별 유효한 전망·목적·제약을 가진 배분</td><td>적정 차이를 정의할 모형이 확보된 뒤 검증할 후속 과제</td></tr>
<tr><td>C. 새 문서의 실제 검색</td><td>개발에 사용하지 않은 자료에서 검색·생성의 전체 과정</td><td>문서 과제의 검색 실패와 활용 실패에 대한 추가 진단</td></tr>
</tbody></table></div>
<p>A에서는 공시의 보고 기준일과 공개일을 분리하고, 주어진 시점에 공개된 자료만 입력에 넣는다. 문서의 서술을 임의의 기대수익률로 바꾸지 않으며, 빠진 수치를 AI가 보충하도록 요구하지 않는다. 정답표에는 값뿐 아니라 근거 위치와 ‘확인 불가’ 상태를 포함한다. 특정 펀드의 자료가 잘 갖춰져 있다는 이유로 선택한 경우에는 접근성 표본이라고 명시하고 전체 운용업계의 대표성을 주장하지 않는다.</p>
<h3>4.2. 경제적 기준이 있는 최소 거래 과제</h3>
<p>B1의 권고 후보는 Hansen과 Lee(<a href="#ref-hansen">2025</a>, §4)의 거래 모형이다. 공개 거래이력·가격과 서로 다른 사적신호를 결합해 매수·매도·보류 중 선택한다. <strong>이는 단일 자산의 정보 처리 검증이며 실제 펀드의 산업별 배분 모형이 아니다.</strong> 논문에서 가져오는 경제 조건과 본 연구가 추가하는 업무 단계 처치를 구별한다.</p>
<div class="table-wrap"><table><caption>표 2. 논문에서 직접 가져올 조건과 새 설계</caption><thead><tr><th>구분</th><th>조건과 출처</th></tr></thead><tbody>
<tr><td>직접 차용</td><td>신호 정확도 0.7, 자산가치 {0, 50, 100}; 매수·매도·보류 보수는 v−p, p−v, 0. 원문 §4.1.</td></tr>
<tr><td>비교 환경</td><td>I: 사건확률 ρ=1, 정보보유 비율 μ=1을 최소 실험 후보로 둔다. II: ρ=0.15, μ=0.95는 합리적 수렴의 추가 비교층이다. 원문 §4.2.</td></tr>
<tr><td>기준 행동</td><td>원문 식 (2)–(7)의 가격·조건부 기대가치로 계산. 시장의 q와 사건 발생을 아는 거래자의 q*를 구별한다.</td></tr>
<tr><td>LIBERA 확장</td><td>같은 이력·가격에서 좋은 신호와 나쁜 신호를 별도 대화에 배정하고 최초 근거 제공 단계를 바꾼다. 원논문의 실험을 그대로 재현하는 것은 아니다.</td></tr>
</tbody></table></div>
<p>원문은 두 신호에 대한 조건부 행동을 함께 묻는다. 여기서는 한 대화가 한 신호만 받도록 바꿔 제공 시점이 실제 처치가 되게 한다. 각 조건의 AI 행동이 후속 가격을 바꾸지 않도록 공개 이력과 가격은 사전에 고정한다. 이력 생성·선정 방식과 사례 수는 본실험 전에 정하며, 원문의 반복 횟수를 새로운 설계의 검정력 근거로 그대로 사용하지 않는다. II를 추가할 경우 사건 발생을 안다는 정보는 모든 조건에 처음부터 동일하게 주고, 신호 카드의 제공 시점만 바꾼다. 카드에는 정답 행동이나 계산된 기대가치를 넣지 않는다.</p>
<h3>4.3. 실험이 진행되는 과정</h3>
<p>실험을 쉽게 설명하면, 같은 시장을 보는 두 분석 담당자에게 서로 다른 신뢰할 만한 추가자료를 주고 AI의 조언이 그 차이에 맞게 달라지는지 확인하는 일이다. 우선 연구자는 주어진 정보에서 어떤 선택이 유리한지 계산할 수 있는 시장 상황을 준비한다. 한쪽 자료가 매수를, 다른 쪽 자료가 매도를 정당화하는 상황도 준비하고, 자료가 달라도 같은 선택이 합리적인 상황도 함께 둔다. 이 둘을 구별해야 다르게 말하는 AI를 무조건 좋은 AI로 평가하지 않게 된다.</p>
<p>각 상황은 서로 연결되지 않은 대화에서 반복한다. 신호 종류와 제공 정책을 교차하여, 같은 신호 안에서는 초기·후기 제공의 차이를 비교하고 같은 정책 안에서는 두 신호에 대한 행동 차이를 비교한다. AI는 상황 해석, 선택지 평가, 권고안 작성, 최종 재검토의 순서로 응답한다. 초기에 근거를 받는 조건에서는 첫 단계부터 추가자료를 계속 볼 수 있다. 늦게 받는 조건에서는 같은 자료를 마지막 재검토 직전에 처음 본다. 같은 신호의 초기·후기 조건은 최종 응답 시점에 동일한 정보를 보유하고 모든 선택지를 다시 고를 수 있다. 업무 단계 수와 출력 기회, 공개 규칙은 같게 유지한다. 초기에 근거를 여러 번 활용하는 기회는 이 정책의 일부이므로, 두 조건의 차이를 순수한 심리적 고착 효과라고 부르지 않는다.</p>
<p>핵심 비교에서는 연구자가 확인한 동일한 근거 묶음을 직접 전달한다. 이 단계는 ‘찾아낸 근거를 언제 제공할 것인가’의 검증이며 검색 성능 검증은 아니다. 이후 실제 검색기를 붙인 문서 과제에서 누락된 근거와 잘못 검색한 근거를 따로 추적한다. 정답 근거를 제공했을 때의 성능과 실제 검색 결과를 제공했을 때의 성능을 대조하면, 같은 실패를 무조건 모델의 추론 문제로 해석하는 오류를 줄일 수 있다.</p>
<h3>4.4. 평가와 분석 원칙</h3>
<p>거래 과제의 주된 품질 지표는 해당 정보에서 얻을 수 있는 최대 기대이익과 실제 선택의 기대이익 차이다. a를 매도 −1, 보류 0, 매수 1로 쓰고 m을 해당 정보의 조건부 기대가치, p를 가격으로 쓰면 다음 식은 원문 보수에서 직접 도출된다.</p>
<div class="equation">기대이익 = a(m − p)<br>기대이익 손실 = |m − p| − a(m − p)</div>
<p>최적 행동이 서로 다른 정보 쌍에서 AI가 같은 행동을 선택한 비율과 손실을 함께 제시한다. 최적 행동이 같은 사례는 별도로 보고하고, 무차별인 경우에는 복수의 최적 행동을 인정한다. 행동이 다르더라도 둘 다 틀릴 수 있으므로 다양성과 품질을 합산한 임의의 종합점수는 만들지 않는다. 출력 형식 오류와 응답 실패도 제외하지 않고 따로 집계하며, 경제적 행동을 식별할 수 없는 출력에 임의 보수를 부여하지 않는다. 경제적 손실은 유효 응답에서 계산되므로 실패율이 다른 정책을 유효 응답의 평균 손실만으로 순위화하지 않는다. 유효한 정보 쌍의 비율도 함께 보고한다.</p>
<p>동일 시장 상황의 정보 쌍과 제공 정책을 짝지어 비교하고, 거래 경로가 공유되는 자료는 독립 표본으로 세지 않는다. 무관한 기관명 변경과 동일한 정보 복제는 대조 조건으로 사용한다. 반복 수, 분석 단위, 불확실성 표시 방법은 개발용 파일럿 후 본실험 이전에 고정한다. 파일럿은 실행 가능성과 필요한 정밀도를 파악하는 용도이며, 효과가 잘 나오는 설정을 고르는 근거로 사용하지 않는다.</p>
</section>
<section id="alternatives"><h2>5. 반론과 대안적 설명</h2>
<p>첫 번째 반론은 수렴이 정확성 향상의 결과일 수 있다는 것이다. 서로 다른 기관의 초기 의견 중 일부가 틀렸다면 같은 근거를 통해 판단이 가까워지는 것은 바람직할 수 있다. 본 연구는 이 반론을 받아들여 필요한 차이가 존재하는 사례에만 과잉수렴의 정의를 적용한다. 자료의 차이가 행동을 바꿔야 하는지부터 평가하고, 사적신호를 따르는 행동과 경제적으로 적절한 행동을 동일시하지 않는다.</p>
<p>두 번째 반론은 기관별 차이를 유지하면 단순히 편향이나 오류를 보존하는 것 아니냐는 것이다. 이에 대한 대응은 각 기관의 과거 비중을 정답으로 삼지 않는 것이다. 공시는 관측된 상태이고, 최적 행동은 명시된 정보·목적·제약에서 계산되는 기준이다. 과거 비중, AI의 제안 비중, 평가 모형의 기준 비중은 서로 다른 개념으로 유지한다. 본 연구가 보존하려는 대상은 기존 관행 자체가 아니라 판단에 관련된 정보다.</p>
<p>세 번째 반론은 초기 제공의 우위가 시점보다 노출 횟수, 토큰 수 또는 추가 검토 기회에서 나올 수 있다는 것이다. 본 설계가 직접 추정하는 것은 최초 제공과 이후 활용을 합친 업무정책의 효과다. 비용은 입력·출력량과 실행 시간으로 함께 보고한다. 고착이나 기억 소실 같은 구체적 심리 기제를 주장하려면 노출량과 맥락 길이를 맞춘 추가 처치가 필요하다. 중간 답변만 관찰하고 그러한 기제가 인과적으로 확인됐다고 해석하지 않는다.</p>
<p>네 번째 반론은 같은 모델만 비교해서 공통모델의 위험을 논할 수 있느냐는 것이다. 동일 모델 조건은 모델 자체의 차이를 통제하는 장점이 있지만, AI를 쓰지 않는 조직이나 여러 모델을 사용하는 조직과의 인과 비교는 아니다. 따라서 본실험의 결론은 ‘공통 모델을 사용하는 주어진 조건에서 어떤 정보 전달 정책이 나은가’로 한정한다. 공통모델 채택의 효과를 직접 검증하려면 비사용 또는 모델 다양성 비교를 별도로 설계해야 한다.</p>
</section>
<section id="implications"><h2>6. 조직의 대응 방향</h2>
<p>기관이 취할 대응은 실험 결과에 따라 달라져야 한다. 초기 제공이 필요한 행동 차이를 보존하면서 손실도 줄인다면, 운용 조직은 공통 시장자료와 함께 기관별 근거를 후보 검토 단계부터 연결하는 절차를 고려할 수 있다. 분석 담당자는 근거의 출처와 적용 대상을 확인하고, 시스템 담당자는 해당 근거가 후속 단계에서도 유지되도록 관리하며, 최종 승인자는 권고안과 근거의 연결을 검토하는 방식이다. 이는 연구가 검증할 조건부 제안이지 이미 효과가 입증된 운영 지침은 아니다.</p>
<p>늦은 재검토가 사전에 정한 비열등성 또는 동등성 기준을 충족하고 비용을 줄인다면 최종 검토 단계의 근거 확인이 더 적합할 수 있다. 초기 제공이 답변의 차이만 늘리고 경제적 손실을 줄이지 못한다면, 이를 동질화 완화의 성공이라고 평가하지 않는다. 차이를 확인하지 못한 경우에는 해당 표본·과제에서의 불확실성을 보고한다. 실무적으로 작은 효과라는 판단에는 충분한 정밀도와 별도로 정당화한 기준이 필요하며, 유의한 차이가 없다는 사실만으로 두 정책이 같다고 결론 내리지 않는다.</p>
<p>검색 오류가 주된 원인이라면 근거 전달 시점을 바꾸는 것만으로 문제를 해결할 수 없다. 조직별 문서 범위, 공개 시점, 자료의 적용 대상을 구분하는 정보 관리가 우선이다. 반대로 정확한 근거를 전달해도 판단이 바뀌지 않는다면, 권고안을 다시 열어 검토할 권한과 절차가 있는지 살펴볼 필요가 있다. 본 연구는 이러한 진단을 통해 정보 수집의 실패와 정보 활용의 실패에 서로 다른 대응을 연결한다.</p>
<p>FSB(<a href="#ref-fsb26">2026</a>)의 최종 보고서는 AI 생애주기의 책임 배분, 자료 관리, 성능 평가, 인간 감독을 강조한다. 본 연구의 업무 설계 관점은 이 논의와 맞닿아 있지만, 해당 정책 보고서가 특정 RAG 배치의 효과를 검증한 것은 아니다. 논문이 제안하는 관리 대상은 ‘AI를 사용했는가’에 그치지 않고, 어떤 근거가 언제 들어왔고 그것이 최종 선택을 어떻게 지지하는가까지 포함한다.</p>
</section>
<section id="limits"><h2>7. 한계와 후속 연구</h2>
<p>현재 원고에는 자체 AI 실험 결과가 없다. 공개 수익률 정리와 기준 배분 계산은 평가 도구의 사전 점검이며 AI의 행동에 관한 증거가 아니다. 최종 원고에서 실행한 연구의 결과를 제시하려면 본실험의 입력·모델·분석 규칙을 고정하고 실패 사례를 포함한 원자료를 보존해야 한다. 결과를 얻지 못한 상태라면 문헌 검토와 연구설계의 기여로 결론을 한정해야 한다.</p>
<p>최소 거래 과제는 정보 활용을 명확하게 평가할 수 있지만 실제 펀드가 수행하는 다자산 배분, 위험 관리, 위임계약을 모두 표현하지 못한다. 공개 문서 검증과 거래 과제에서 각각 좋은 성능을 얻더라도 그것만으로 실제 기관의 전략적 이질성이 보존됐다고 주장할 수 없다. 기관별 유효한 전망이나 제약이 최적 배분을 바꾸는 모형을 별도로 확보하고, 그 입력을 공개자료와 연결하는 배분 확장이 필요하다.</p>
<p>또한 문서가 공개되어 있다는 사실은 그 안에 기관의 사적정보가 모두 담겼다는 뜻이 아니다. 제한된 펀드와 특정 모델에서 관측한 효과는 다른 운용사·과업·모델로 일반화되지 않을 수 있다. 본 연구는 시장가격의 내생적 변화, 대규모 공통 거래, 유동성 위기를 직접 추정하지 않는다. 금융안정은 연구의 동기이며, 실제 시장의 후생과 위험에 대한 결론은 시장 상호작용을 포함하는 후속 연구가 필요하다.</p>
</section>
<section id="conclusion"><h2>8. 결론</h2>
<p>같은 AI를 사용하는 기관들의 판단이 비슷해졌다는 사실만으로 조직의 정보 처리 능력이 약해졌다고 결론 내릴 수 없다. 중요한 질문은 주어진 정보에서 달라야 할 판단이 실제로 달라지고, 같아야 할 판단은 적절하게 수렴하는가다. 문헌은 공통 기술의 집단적 위험 가능성과 함께 정보 활용·성과 개선의 가능성도 보여준다. 따라서 동질화의 문제는 사전에 확정할 결론이 아니라 경제적 기준으로 검증할 대상이다.</p>
<p>본 연구는 액티브 주식형 펀드의 정보처리 문제를 출발점으로 삼고, 공개 문서의 근거 확인과 논문 기반 정보 반응 실험을 구분하는 설계를 제시했다. 핵심 제안은 동일한 근거의 내용은 유지한 채 제공 시점과 후속 검토 기회를 비교하고, 필요한 행동 차이와 판단 품질을 함께 평가하는 것이다. 이 단계의 성과는 공통 AI의 영향이 발생할 수 있는 업무 경로와 그 경로를 검증할 기준을 구체화했다는 데 있다.</p>
<p>실무적 대응은 다양성을 강제하는 목표보다 근거가 선택에 반영되는 과정을 관리하는 데서 출발해야 한다. 서론에서 제기한 ‘같은 AI를 쓰는 기관의 판단은 어디에서 달라져야 하는가’에 대한 답은 기관의 이름이나 모델의 말투에 있지 않다. 경제적으로 관련 있는 정보가 다른 행동을 정당화하는 지점에 있으며, 본 연구의 실험은 그 지점이 업무 과정에서 보존되는지를 확인하기 위한 것이다.</p>
</section>
</article>
<section id="references"><h2>참고문헌</h2><p class="note">APA 저자–연도 체계로 정리한 작업 서지. 학술 논문·프리프린트·정책 보고서를 구별했다. 2026년 10월 17일까지 확인한 자료를 사용하며, 이론과 방법의 원전은 최신 연구와 함께 유지했다.</p><ul class="references">REFS_PLACEHOLDER</ul></section>
<section id="appendix"><h2>부록. 제출 준비와 남은 결정</h2>
<p class="note">이 부록은 작업 관리용이며 최종 제출 시 본문·참고문헌과 분리할 수 있다.</p>
<p><a href="https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804">LIBERA Notion ‘개요’</a>에는 최종 페이퍼 제출 11월 1일, 피칭 11월 6일, 발표 5~10분, APA 인용이 안내되어 있다. 이 페이지는 오리엔테이션의 정리 자료이며 심사 항목별 배점은 작성자의 추정이다. 추정 배점을 공식 평가표로 사용하지 않는다. 분량·파일 양식·자체 실험 필수 여부는 확인된 개요에 없다.</p>
<div class="table-wrap"><table><thead><tr><th>결정이 필요한 부분</th><th>권고와 이유</th><th>대안과 영향</th></tr></thead><tbody>
<tr><td>본실험의 범위</td><td>B1 정보 반영의 최소 기제＋A 공개 문서 검증. 경제적 정답의 근거가 있어 좁은 질문을 검증할 수 있다.</td><td>B2 실제 펀드의 산업 배분까지 포함. 원제안서의 적용 범위와 더 가깝지만 기관별 차이를 정당화할 모형·입력을 추가로 확보해야 한다.</td></tr>
<tr><td>정보 제공 시점</td><td>최초 단계와 최종 재검토의 비교를 우선. 차이가 명료하고 실행 부담을 줄일 수 있다.</td><td>중간 단계를 추가해 어느 지점부터 달라지는지 탐색. 네 업무 단계는 LIBERA의 설계이며 선행논문이 검증한 구분이 아니다.</td></tr>
<tr><td>모델·실행 자원</td><td>논문에 사용된 접근 가능한 고정 버전 후보를 확인한 뒤 선정. 같은 버전·설정을 조건 전체에 유지한다.</td><td>다른 계열 모델을 추가하면 일반화 검증이 가능하지만, 모델별 배치를 별도로 기록해야 한다.</td></tr>
<tr><td>산업·배분식</td><td>현재 본문 B1에는 산업별 비중이 없어 선택을 요구하지 않는다. FF12·P/Q 계산은 부록 진단으로 유지한다.</td><td>B2를 주실험에 포함할 때 FF12/FF49와 목적식을 결정. 기존 보유 비중 차이만으로 필요한 목표 비중 차이를 만들 수 없다.</td></tr>
</tbody></table></div>
<p>11월 1일까지의 작업 순서는 원고 논점·서지 확정 → 최소 실험 범위 선택 → 공개자료와 기준 답 검증 → 파일럿 → 분석 규칙 고정 → 본실험 → 결과에 맞춘 본문·결론 수정 → 인용·형식 점검이다. 이는 연구 일정 제안이며 선행논문의 실험 조건이 아니다. 실행을 하지 않은 항목을 완료했다고 기재하거나 결과를 예상치로 채우지 않는다.</p>
</section>
<footer>출발 문서: plan/문규리 제안서 상세_최종.html 및 9월 실험설계·수행보고서. 원본을 보존하고 새 소논문 초안으로 작성했다. 이 파일은 제출 또는 공개 게시되지 않았다.</footer>
'''.replace('REFS_PLACEHOLDER', refs)

def document(title, content):
    return '<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' + title + '</title><style>' + css + '</style></head><body><main id="top">' + content + '</main></body></html>\n'

(PAPER / 'LIBERA_텀페이퍼_초안_20261017.html').write_text(document('LIBERA 텀페이퍼 초안 — 공통 생성형 AI와 필요한 투자판단 차이', body), encoding='utf-8')

# Rebuild the current plan. The numeric prototypes and all former details are retained in the archive.
plan_body = '''
<header><div class="eyebrow">LIBERA · RESEARCH ALIGNMENT · VERSION 3.3</div><h1>기관별 정보와 판단의 차이를<br>검증하는 연구계획</h1><p class="meta">2026-10-17 · 학술제 개요와 원제안서 정합성 수정 · AI 본실험 전</p>
<p class="lead"><strong>고정할 연구질문:</strong> 같은 AI를 사용할 때 경제적으로 필요한 판단 차이는 보존되는가? 같은 근거를 어느 단계에서 제공해야 정보 반영과 판단 품질이 개선되는가?</p>
<p>최종 산출물은 실험 도구가 아니라 <strong>상경·경영학술제 텀페이퍼</strong>다. <a href="../paper/LIBERA_텀페이퍼_초안_20261017.html">소논문 본문 초안</a>을 작성했다. 원제안서의 문제의식을 유지하되, ‘동일 AI가 반드시 동질화를 일으킨다’는 결론을 선행 가정하지 않는다.</p>
<p class="note">최신 기준은 이 문서와 <a href="LIBERA_실험설정_20261017.json">v3.3 설정</a>이다. <a href="archive/LIBERA_실험계획_v3.2.html">v3.2 상세</a>와 <a href="archive/LIBERA_실험설정_v3.2.json">이전 설정</a>은 이력으로 보존한다. 이전 추천 조합은 현재 주실험이 아니다. 9월 원본 세 파일은 보존했다.</p>
<div class="toolbar"><button onclick="window.print()">인쇄 및 PDF 저장</button><a href="../paper/LIBERA_텀페이퍼_초안_20261017.html">텀페이퍼 읽기</a><a href="#choices">남은 선택</a></div></header>
<nav aria-label="목차"><a href="#fit">1. 학술제 적합성과 수정</a><a href="#plain">2. 실험을 쉽게 설명하면</a><a href="#evidence">3. 증거와 주장 범위</a><a href="#protocol">4. 검증 정책과 평가</a><a href="#choices">5. 선택할 항목과 이유</a><a href="#numbers">6. 수치와 식의 근거</a><a href="#prepared">7. 준비된 자료의 용도</a><a href="#delivery">8. 제출까지의 작업</a></nav>
<section id="fit"><h2>1. 학술제 적합성과 수정</h2>
<p><a href="https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804">Notion ‘개요’</a>의 대주제는 ‘AI가 재편하는 사회와 경제: 변화와 대응의 방향’이다. 텀페이퍼는 구체적 문제, 중요성의 근거, 작동 원리, 반론, 대응을 연결해야 한다. 원제안서의 정보경제학·조직 의사결정 문제는 이에 적합하다.</p>
<div class="table-wrap"><table><thead><tr><th>직전 계획의 문제</th><th>v3.3 수정</th><th>논문에서의 의미</th></tr></thead><tbody>
<tr><td>공통 공분산의 제공 시점이 중심으로 이동</td><td>기관별 근거가 요구하는 판단 차이로 중심 복원</td><td>계산 정확도보다 정보 집약과 업무 설계를 설명</td></tr>
<tr><td>FF12＋P 식이 주실험 추천</td><td>P/Q는 평가 도구의 계산 진단 부록</td><td>같은 입력·목적의 같은 정답으로 기관 이질성을 입증하는 오류 방지</td></tr>
<tr><td>이질성 회복을 유사도와 연결할 위험</td><td>필요한 차이와 경제적 손실을 함께 평가</td><td>합리적 수렴·다양하지만 틀린 판단을 분리</td></tr>
<tr><td>문헌에서 효과의 방향을 미리 정할 위험</td><td>사적정보 활용 개선·낮은 동조화 등 반대 결과 포함</td><td>반증 가능한 가설과 조건부 대응안</td></tr>
<tr><td>실험계획이 사실상 최종 산출물</td><td>서론–문헌–개념–방법–반론–대응–한계–결론의 소논문 작성</td><td>제안서의 내용을 제출 가능한 논증으로 발전</td></tr>
</tbody></table></div>
<p>개요상 제출일은 <strong>11월 1일</strong>, 피칭은 <strong>11월 6일, 5~10분</strong>이며 APA 인용을 사용한다. 분량·지정 파일 양식·자체 실험 필수 여부는 명시되지 않았다. 개요의 심사 배점은 추정치이므로 공식 가중치나 연구 성과의 종합점수로 사용하지 않는다.</p></section>
<section id="plain"><h2>2. 실험을 쉽게 설명하면</h2>
<p>출발점은 ‘여러 기관이 같은 AI를 써도 각 기관이 가진 중요한 자료를 제대로 활용할까’이다. 시장의 공통 상황은 같게 놓고, 판단을 바꿀 만한 추가자료만 다르게 준다. 이때 기관 이름이 달라서 답이 달라지는 것은 관심 대상이 아니다. 자료가 다르기 때문에 선택이 달라져야 하는 상황인지부터 연구자가 확인한다.</p>
<p>AI는 상황을 해석하고, 선택지를 비교하고, 권고안을 만든 뒤 다시 검토한다. 한 조건은 추가자료를 첫 단계부터 계속 읽을 수 있다. 다른 조건은 같은 자료를 마지막 재검토 직전에 받는다. 같은 자료의 초기·후기 조건은 마지막에 동일한 정보를 알고 모든 선택을 다시 고를 수 있다. 같은 신호 안에서 시점을 비교하고, 같은 시점 정책 안에서 서로 다른 신호에 대한 행동을 비교하는 구조다. 이렇게 해야 ‘자료가 없어서 틀린 것’과 ‘자료를 받았어도 이미 만든 판단을 충분히 바꾸지 못한 것’을 구분할 수 있다.</p>
<p>먼저 논문에 있는 단일 자산의 매수·매도·보류 과제를 후보로 둔다. 어떤 행동이 유리한지 계산할 수 있어 자료의 차이를 무시한 손실을 평가하기 좋다. 실제 펀드 문서에서는 운용 규칙과 출처를 정확히 찾고 활용하는지도 따로 확인한다. 두 검증은 실제 펀드의 최적 산업 비중을 알아냈다는 뜻은 아니다. 그 확장에는 기관별 전망·목적·제약을 정당화할 추가 모형이 필요하다.</p>
<p>좋은 결과는 AI 답변이 서로 달라지는 것만으로 판단하지 않는다. 달라야 하는 때에 적절하게 달라지고, 같은 선택이 유리한 때에는 불필요하게 갈라지지 않아야 한다. 경제적 품질이 함께 나아지는지를 확인한 뒤에만 근거 제공 정책의 개선을 논의한다.</p></section>
<section id="evidence"><h2>3. 증거와 주장 범위</h2><div class="table-wrap"><table><thead><tr><th>구성</th><th>권고 위치</th><th>직접 평가</th><th>넘어갈 수 없는 결론</th></tr></thead><tbody>
<tr><td>A 공개 펀드 문서</td><td>현실 맥락과 문서 검증</td><td>출처·날짜·금액·운용 규칙·확인 불가 처리</td><td>비공개 전망 또는 운용사의 최적 배분</td></tr>
<tr><td>B1 논문 기반 거래 과제</td><td>최소 기제 실험 권고 후보</td><td>정보 조건별 행동과 기대이익 손실</td><td>기관 전체의 전략 동질화 또는 금융안정 효과</td></tr>
<tr><td>B2 기관별 산업 배분</td><td>추가 모형 확보 후 확장</td><td>실제 차이를 정당화할 기준 배분</td><td>P/Q만으로 완성되었다는 주장</td></tr>
<tr><td>C 새 문서의 실제 검색</td><td>A 이후 외부 문서 전이</td><td>검색 누락과 근거 활용의 구분</td><td>B1 효과와 합친 실제 펀드 RAG 완화효과</td></tr>
</tbody></table></div>
<p>원제안서의 주제는 선택지로 돌리지 않고 유지한다. 선택할 것은 <strong>이번 제출에서 어느 범위까지 직접 검증할지</strong>다. B1은 원논점의 정보 반영 부분을 좁게 검증하는 후보이고, B2를 이미 대체·완성한 것으로 서술하지 않는다.</p></section>
<section id="protocol"><h2>4. 검증 정책과 평가</h2>
<p>주된 비교 후보는 R1(처음부터 제공·유지)과 R4(최종 재검토 직전 제공)다. 시장 해석 → 선택지 평가 → 권고안 → 재검토라는 네 단계는 원제안서를 구체화한 <strong>LIBERA의 새 설계</strong>다. 네 단계가 선행논문에서 최적이라고 입증된 것은 아니다. 중간 제공 R2/R3은 자원과 파일럿 결과를 보고 추가 여부를 고정한다.</p>
<p>같은 시나리오·신호·근거 묶음·모델·공개 규칙·출력 기회를 짝지어 비교한다. 제공 후 근거는 계속 유지한다. 최종 선택지는 모두 열어 놓으며 후기 조건에서 초반 후보로만 답하도록 제한하지 않는다. 초기 제공에 따른 더 많은 활용 기회는 정책 효과에 포함된다. 정책 간 행동이 후속 시장가격을 바꾸지 않도록 공개 이력은 고정한다.</p>
<p>정답 근거를 직접 주는 B1에서는 검색기를 평가하지 않는다. A/C의 실제 검색은 별도 조건으로 두고 개발 자료로만 설정을 정한다. 출처가 없는 문장을 수익 전망으로 바꾸거나 정답 평가 파일을 검색 코퍼스에 넣지 않는다. ‘전체 문서를 처음부터 제공’ 조건이 R1과 내용·분량까지 같다면 중복 비교군으로 계산하지 않는다.</p>
<p>주평가는 최적 행동이 다른 정보 쌍의 불필요한 동일 행동과 기대이익 손실이다. 최적 행동이 같은 쌍, 무관한 이름 변경, 같은 정보 복제도 함께 평가한다. 중간 출력은 진단 자료로 활용하되 인과 매개효과라고 부르지 않는다. 오류·미응답·형식 실패를 제외해 성공률을 부풀리지 않는다. 같은 경로의 여러 회기나 동일 입력 반복은 독립 시장 표본이 아니다. 차이를 확인하지 못했다는 사실은 동등성의 증거가 아니며, 효과의 불확실성을 함께 보고한다.</p>
<p>모델 버전·호스팅·프롬프트·도구·출력 규칙·분석 단위·표본 구성·비용 한도를 본실험 전에 고정해야 한다. 현재 본실험과 파일럿은 수행하지 않았으며, API 호출 수와 예산을 임의로 채우지 않았다.</p></section>
<section id="choices"><h2>5. 선택할 항목과 이유</h2><div class="table-wrap"><table><thead><tr><th>어느 부분의 선택인가</th><th>권고 후보</th><th>다른 후보와 의미</th></tr></thead><tbody>
<tr><td>실험이 뒷받침할 주장</td><td><strong>A＋B1:</strong> 공개 근거 처리와 정보 반영의 최소 기제. 현재 논문 근거로 정답을 설명하기 쉽다.</td><td><strong>B2 추가:</strong> 실제 산업 배분까지 직접 검증. 기관별 유효한 전망·제약의 모형을 먼저 확보해야 한다.</td></tr>
<tr><td>업무정책 비교의 폭</td><td><strong>R1 대 R4:</strong> 처음과 마지막의 차이를 우선 확인</td><td><strong>R1~R4:</strong> 중간 단계까지 비교해 시점을 세분화. 해석·실행량이 늘어난다.</td></tr>
<tr><td>B1의 고정 시장 상황</td><td><strong>환경 I의 이론적 기준 경로 전수:</strong> 원문 8회기의 매수·매도 경로에서 길이 0~7의 이력 255개를 계산할 수 있다. 개수는 규칙에서 도출되며 전수열거는 새 설계다.</td><td><strong>원문 실행 기록 재생:</strong> 전체 기록을 확보하면 가능하지만 현재 확보되지 않았다. 255개 역시 독립 시장 표본이나 논문의 표본 N이 아니다.</td></tr>
<tr><td>재현성과 실행 자원</td><td><strong>논문 평가 모델 중 접근 가능한 고정 버전:</strong> 기존 PortBench 기반 Qwen 후보는 접근·버전 확인 전 미확정</td><td><strong>다른 계열 추가:</strong> 일반화 검증. 같은모델 배치와 섞지 않고 별도 보고</td></tr>
<tr><td>A의 사례 자료</td><td><strong>FCNTX·VPMCX·DODGX·TRBCX 적격성 확인:</strong> 공개 문서 후보가 이미 정리돼 있음</td><td>자료가 완전하지 않으면 사전 대체 순서 OAKMX→PRBLX 검토. 논문에서 선정된 표본이 아닌 접근성 후보</td></tr>
<tr><td>B2 또는 계산 부록의 산업</td><td><strong>FF12:</strong> 직접 사용한 선행논문과 준비된 자료가 있음</td><td><strong>FF49:</strong> 세밀하지만 차원이 커짐. B1 수행을 위해 정할 필요는 없음</td></tr>
<tr><td>B2의 배분 평가식</td><td><strong>미확정:</strong> 필요한 기관별 차이를 설명하는 모형부터 검증</td><td>P(최대 샤프)·Q(이차효용)는 같은입력 계산 진단. 둘 중 하나를 고르는 것만으로 기관 차이가 생기지 않음</td></tr>
</tbody></table></div>
<p>분량·지정 양식은 확인되는 대로 원고를 맞춘다. 실험 실시 여부를 결정하기 전에도 문헌의 주장–근거 대응, 반론, 공개 문서 적격성, 기준 행동의 검산은 진행할 수 있다. 연구질문 자체를 새로 고르라고 되묻지 않는다.</p></section>
<section id="numbers"><h2>6. 수치와 식의 근거</h2>
<p>B1의 경제 조건과 평가식은 <a href="../paper/LIBERA_텀페이퍼_초안_20261017.html#design">소논문 §4 및 표 2</a>에 출처와 함께 정리했다. Hansen–Lee의 2025년 원문에서 직접 확인한 조건만 차용한다. 새로운 정보 제공 시점 처치, 표본 구성, 업무 단계는 원논문과 구분한다. 원문의 반복 횟수는 새 실험에 충분한 표본이라는 근거가 아니므로 그대로 본실험 N으로 넣지 않는다.</p>
<p>전수열거 후보는 정상적으로 정보를 반영하는 이론적 기준 경로에 한정된다. 실제 AI가 보류를 선택해 만드는 모든 시장경로를 포함하지 않는다. 응답 선택에는 보류를 유지한다. 이 후보를 선택하면 회기별 경로 확률로 가중하고 회기별 결과를 보고하며, 모든 길이의 이력을 단순 평균하지 않는다. 환경 II는 별도 경로 규칙 검증 후 추가한다. 사건 발생을 안다는 지식은 양 정책에 처음부터 같게 주어 신호 제공 효과와 섞지 않는다.</p>
<p>기존 P/Q의 수치·목적식·공개 수익률은 보조 진단으로 보존한다. PortBench v6 T5의 매수 전용 최대 샤프식과 Salcher(2026)의 공매도 허용 이차효용식은 서로 다른 문제다. 비중을 임의로 정하지 않는다. h는 공시에서 계산한 현재 비중, w는 AI의 제안, w*는 주어진 입력의 계산상 최적해다. h가 두 식에 들어가지 않으면 출발 비중 차이가 필요한 목표 차이를 만들지 않는다.</p>
<p>근거 표시는 ① 논문 직접 조건, ② 자료에서 계산한 값, ③ 저자 코드에만 있는 설정, ④ LIBERA의 새 설계로 나눈다. 오래된 이론 원전은 유지하고 최신 관련 연구를 함께 검토한다. 정책 보고서는 실무 맥락의 근거로 쓰되 실험 수치를 정하는 논문으로 대체하지 않는다.</p></section>
<section id="prepared"><h2>7. 준비된 자료의 용도</h2>
<div class="table-wrap"><table><thead><tr><th>완료된 산출물</th><th>현재 용도</th><th>아직 입증하지 않은 것</th></tr></thead><tbody>
<tr><td>French 공개자료와 해시·결측 검증</td><td>재현 가능한 수익률 입력과 산업 정의</td><td>실제 펀드의 고유 전망</td></tr>
<tr><td>P 기준 배분 132건 검산</td><td>최대 샤프 목적식 계산 진단</td><td>AI의 동질화·정보 반영 효과</td></tr>
<tr><td>Q 기준 배분 3,750개 검산</td><td>이차효용 및 공분산 처리 점검</td><td>독립 표본 3,750건 또는 실제 투자성과</td></tr>
<tr><td>공개 펀드 공시 후보 목록</td><td>A/C 자료 적격성 검토의 출발점</td><td>원자료 전수 확보·SIC 연결·h 계산 완료</td></tr>
<tr><td>실험 전 텀페이퍼 HTML</td><td>문헌·개념·방법·반론·대응의 본문 초안</td><td>결과 포함 최종 제출본</td></tr>
</tbody></table></div>
<p>P의 일부 기준해가 단일 산업에 집중되고 Q에 공매도·큰 총노출이 나타난 계산 특성도 이전 기록에 남겼다. 이는 식의 성질을 보여주는 사전 점검이며 실제 투자 권고가 아니다. 관련 상세는 <a href="archive/LIBERA_실험계획_v3.2.html#completed">v3.2 계산 기록</a>과 설정 JSON의 검증 항목을 참조한다.</p></section>
<section id="delivery"><h2>8. 제출까지의 작업</h2>
<p><strong>지금:</strong> 소논문 초안의 논점·서지를 정리했고, 원제안서에서 벗어났던 주실험 권고를 수정했다. 원고의 참고문헌은 최신 금융·조직 연구와 반대 증거를 포함한다. 전문을 확인하지 못한 연구는 초록 수준 근거임을 표시했다.</p>
<p><strong>실험 전:</strong> A＋B1 또는 B2 포함 여부, 제공 단계, 모델과 자원을 선택한다. 공개자료·기준 행동 검산, 프롬프트·형식 검증을 마친 뒤 파일럿으로 규모와 비용을 확인한다. 분석 규칙을 동결한 다음 본실험을 실행한다. 선택되지 않은 모듈은 코드가 존재해도 주실험으로 자동 실행하지 않는다.</p>
<p><strong>11월 1일 제출 전:</strong> 실제 결과를 얻은 범위에서만 결과 절을 작성하고, 초록·가설·논의·결론을 관측 결과에 맞춰 수정한다. 무효과와 반대 결과도 포함한다. APA 인용과 참고문헌 대응, 저자 정보, 지정 형식, 문장·표의 가독성을 점검한다. 11월 6일 피칭은 문제–근거–핵심 비교–결과–대응으로 압축한다. 이 순서는 제출 준비 계획이며 논문에서 차용한 실험 조건이 아니다.</p>
<p class="decision"><strong>현재 권고:</strong> 원제안서의 기관별 정보 보존 문제를 유지하면서 <strong>문헌·공개 문서 검증＋좁은 B1 실험</strong>으로 제출 가능한 근거를 만든다. 실제 펀드의 산업 배분 동질화까지 결론 내리려면 B2가 추가로 필요하다. 산업·비중·식의 선택을 먼저 끝내는 것으로 이 논증상의 공백이 해결되지는 않는다.</p></section>
<footer>주요 학술 근거와 서지: <a href="../paper/LIBERA_텀페이퍼_초안_20261017.html#references">소논문 참고문헌</a>. 공개 수익률·P/Q 출처와 상세 설정: <a href="archive/LIBERA_실험계획_v3.2.html#references">보존한 v3.2 참고자료</a>. 원본 제안서·설계서·보고서는 수정하지 않았다.</footer>
'''
plan_path.write_text(document('LIBERA 연구계획 v3.3 — 학술제 논점과 텀페이퍼 정합성', plan_body), encoding='utf-8')

config = old.copy()
config.update({
    'protocol_version': '3.3',
    'status': 'pre_experiment_term_paper_draft; original_economic_question_restored; no_LLM_experiment_run',
    'previous_protocol': 'archive/LIBERA_실험설정_v3.2.json',
    'active_main_experiment': None,
    'research_question': 'Under a fixed common GenAI model, are economically warranted differences in judgment preserved, and how does evidence-onset policy affect information use and decision quality?',
    'deliverable': 'paper/LIBERA_텀페이퍼_초안_20261017.html',
    'conference_requirements': {
        'source': 'https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804',
        'tab': '개요', 'checked_on': '2026-10-17',
        'source_status': 'user-provided orientation summary, not original official rubric',
        'theme': 'AI가 재편하는 사회와 경제: 변화와 대응의 방향',
        'paper_due': '2026-11-01', 'pitch_date': '2026-11-06', 'pitch_minutes': [5, 10],
        'citation_style': 'APA', 'length': None, 'file_format': None, 'own_experiment_required': None,
        'rubric_weights_are_official': False,
        'note': 'The overview explicitly labels evaluation weights as estimates. Missing requirements are not inferred.'
    },
    'recommendation': {
        'question_is_not_a_new_choice': True,
        'recommended_evidence_scope': ['A_public_document_validation', 'B1_paper_based_information_use_mechanism'],
        'conditional_extension': 'B2_institution_specific_portfolio_allocation_after_valid_heterogeneous_benchmark',
        'financial_numeric_modules': 'P_and_Q_appendix_diagnostics_only',
        'recommended_onset_comparison': ['R1', 'R4'],
        'status': 'recommendation_only_not_frozen'
    },
    'selection_required': [
        {'stage': 'claim_and_experiment_scope', 'candidates': ['A+B1 minimum mechanism', 'A+B1+B2 portfolio extension'], 'reason': 'B1 does not establish actual institutional portfolio heterogeneity; B2 requires an evidenced institution-specific objective/input model'},
        {'stage': 'workflow_onsets', 'candidates': ['R1 versus R4', 'R1 through R4'], 'reason': 'main early/late policy contrast versus additional timing resolution'},
        {'stage': 'model_and_resources', 'candidates': ['one accessible fixed paper-evaluated model', 'primary plus another model family'], 'reason': 'access, reproducibility, cost and generalization; not yet verified'},
        {'stage': 'document_sample', 'candidates': ['audit existing four-fund candidates', 'prespecified public-data replacements'], 'reason': 'accessibility sample, not paper-selected representative institutions'},
        {'stage': 'B2_only_industry_and_objective', 'candidates': ['FF12 with a justified heterogeneous objective', 'FF49 extension'], 'reason': 'not a prerequisite for B1; P/Q alone do not identify warranted institution differences'}
    ],
    'module_roles': {'A': 'public documentary accuracy and institutional context', 'B1': 'minimal information-response mechanism', 'B2': 'unresolved portfolio extension', 'C': 'held-out documentary retrieval transfer', 'P': 'appendix arithmetic diagnostic', 'Q': 'appendix arithmetic diagnostic'},
    'B1_candidate': {
        'source': 'https://www.federalreserve.gov/econres/feds/files/2025090pap.pdf',
        'source_version': '2025-09-25 official paper; arXiv 2510.01451v1',
        'direct_conditions_locator': 'sections 4.1-4.2, equations 2-7',
        'signal_accuracy': 0.7, 'fundamental_values': [0, 50, 100],
        'treatments': {'I': {'rho': 1, 'mu': 1}, 'II': {'rho': 0.15, 'mu': 0.95}},
        'actions': {'sell': -1, 'no_trade': 0, 'buy': 1},
        'payoffs': {'buy': 'v-p', 'sell': 'p-v', 'no_trade': '0'},
        'oracle': 'Paper equations 2-7; distinguish market-maker q from informed-trader q_star',
        'regret_derived_from_paper_payoffs': 'abs(m-p)-a*(m-p)',
        'ties': 'all maximizing actions accepted',
        'new_LIBERA_adaptations': ['one realized signal per independent workflow instead of simultaneous two-signal strategy-method query', 'fixed public history and price across onset policies', 'same signal evidence packet retained after first provision', 'R1 versus R4 onset policy'],
        'main_history_sample': None, 'sample_size': None, 'original_repeat_count_is_new_power_analysis': False,
        'primary_treatment_candidate': 'I', 'additional_rational_convergence_layer': 'II',
        'event_knowledge': 'if II is used, informed/event-occurrence knowledge is supplied from the outset in all onset conditions; delay only realized signal',
        'signal_card_excludes': ['optimal action', 'calculated posterior expected value'],
        'history_candidates': {
            'paper_record_replay': {'status': 'full original records not obtained'},
            'I_normative_path_enumeration': {'status': 'candidate, not implemented or selected', 'paper_rounds': 8, 'derived_ordered_prefix_count': 255, 'prefix_lengths': [0, 7], 'history_actions': ['buy', 'sell'], 'model_response_actions': ['buy', 'sell', 'no_trade'], 'history_probability': '0.5*0.7**B*0.3**S + 0.5*0.3**B*0.7**S', 'aggregation': 'report each round using theoretical history probabilities; any equal-round summary explicitly designated as LIBERA estimand', 'scope': 'normative reference paths only, not all possible AI-induced paths', 'independent_market_sample': False}
        },
        'direct_institution_or_monoculture_claim': False,
        'implementation_complete': False
    },
    'workflow_policy': {
        'steps': ['interpret situation', 'assess choices', 'draft recommendation', 'review and revise'],
        'onset': {'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4},
        'stage_count_provenance': 'new LIBERA design from original proposal, not paper-validated optimum',
        'retention': 'retain identical evidence after onset',
        'final_choice_set': 'all choices remain available',
        'final_information_equal': True,
        'main_packet': 'verified fixed evidence; not an actual retrieval evaluation',
        'estimand': 'onset-and-subsequent-use policy effect, not pure anchoring',
        'controls': ['same-information pair', 'irrelevant institution-ID relabel', 'cases with same optimal action'],
        'full_context_duplicate_rule': 'do not count full-context-early as a distinct arm if identical to R1',
        'failures': 'report invalid and missing outputs plus valid-pair coverage separately; no selective dropping or fabricated economic action; do not rank policies with differing failure rates by conditional valid-response mean regret alone'
    },
    'claims_excluded': ['causal effect of adopting a shared model', 'real fund private forecasts observed', 'actual fund allocation homogenization established by B1', 'systemic risk or welfare quantified', 'actual RAG benefit established by fixed-packet experiment', 'combined A and B1 success proves real fund RAG mitigation'],
    'gates_before_main': {
        'core_question_aligned_to_proposal': True,
        'conference_overview_read': True,
        'scope_selected': False,
        'B1_history_and_oracle_validated': False,
        'B2_heterogeneous_benchmark_if_in_scope': False,
        'fund_sources_complete_for_documentary_module': False,
        'model_access_verified': False,
        'pilot_complete': False,
        'analysis_and_resource_limits_frozen': False,
        'preregistration_frozen': False
    }
})
config['retired_v32_main_proposal'] = config.pop('B_timing_proposal')
config['retired_v32_main_proposal']['active'] = False
config['retired_v32_main_proposal']['reason'] = 'common covariance timing does not test institution-specific warranted heterogeneity'
config['analysis'] = dict(old['analysis'], inference_plan='Freeze after scope, history construction and pilot; pair policies within market states and cluster by underlying path; no active numerical N or confidence level', primary_quality='expected-payoff regret for B1', primary_heterogeneity='same action when optimal signal-contingent actions differ', no_arbitrary_combined_score=True)
config['fund_document_protocol'] = dict(old['fund_document_protocol'], B_profile_usage='A/C context only; never translate holdings into B1 private signal or B2 optimal forecast')
config['A_C_document_tasks'] = dict(old['A_C_document_tasks'], math_probes='deterministic units/dates/arithmetic checks; P/Q separate appendix diagnostics', onset_policies=['R1', 'R4'], onset_definition='before first response versus before final response; identical own-task packet retained after onset')
config['model_candidate_pending_access'] = dict(old['model_candidate_pending_access'], role='numeric appendix candidate; B1 primary model requires scope-specific choice and fixed accessible version')
config['completed'] = dict(old['completed'], conference_overview_read=True, pre_experiment_manuscript_drafted=True, B1_model_experiment_run=False, B2_heterogeneous_reference_ready=False)
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'paper': str(PAPER / 'LIBERA_텀페이퍼_초안_20261017.html'), 'plan': str(plan_path), 'protocol_version': config['protocol_version'], 'AI_responses': config['completed']['AI_responses']}, ensure_ascii=False))
