## 6. 결과에 따른 해결방안

본실험에서는 펀드별 보유상태와 위험조건을 이미 제공하고, 추가 전망을 처음 연결하는 단계를 달리하였다. 계획·배분안 작성 단계부터 근거를 제공한 조건에서는 평균 과잉수렴이 나타났고, 점검 단계 제공은 높은 유효율과 큰 배분 차이를 보였지만 기대수익 손실을 개선하지 못했다. 따라서 기관별 자료를 제공하는 것만으로 필요한 전략 차이와 판단 품질이 함께 확보되지는 않았다. 이에 본고는 공통 GenAI의 중간 판단을 후속 업무에서 어떻게 활용하고 재검토할 것인지에 초점을 맞추어 Workflow RAG의 보완 방향을 제안한다.

첫째, 기존 배분안을 수정하는 절차와 별도로, 그 초안을 보지 않고 기관별 근거를 분석하는 경로를 둔다. 기존 실험은 이전 계획과 응답을 모두 유지한 채 다음 단계로 진행하였다. 보완 방안에서는 동일한 펀드별 전망·보유상태·위험조건을 제공하되, 기존 AI의 계획과 배분안, 대화 이력은 보여주지 않은 상태에서 별도의 배분안을 작성하게 한다. 운용 검토에서는 두 안의 비중이 달라진 산업과 판단 근거를 대조하고, 해당 펀드의 정보와 조건에 더 부합하는 안을 선택하거나 수정한다. 이때 기관별 원자료의 사실값과 AI가 작성한 해석을 구분하여 제시한다. 이는 앞선 AI의 관점에 의존할 가능성에 대응하는 설계이며, 본실험에서 초기 판단의 고착이 원인으로 확인되었다는 뜻은 아니다.[^1]

둘째, 실제 운용에서는 자료의 변화나 의견 충돌이 발견될 때 관련 근거를 다시 검색하고, 필요한 경우 앞선 판단 단계로 돌아가도록 Workflow RAG를 확장한다. 예를 들어 전망의 기준시점이 달라졌거나 기관별 전망과 공통 시장 해석이 상충하면, 재검토할 산업과 쟁점을 지정하여 자료를 검색한다. 새 근거는 최종 배분의 설명을 보충하는 데만 사용하지 않고, 해당 산업의 전망 평가와 투자대안 선택을 다시 수행하는 입력으로 연결한다. 의견이 다르다는 이유만으로 기관별 전망을 따르게 하지는 않으며, 보유상태와 위험조건을 함께 고려하여 채택 또는 보류 이유를 제시하도록 한다. 다만 본실험에서는 추가 전망 열두 항목이 모두 검색되었으므로, 이 방안은 검색 누락을 해결했다는 결론이 아니라 자료 갱신과 충돌에 대응하기 위한 실무 확장안이다. 자료 접근범위와 기준시점, 검색 횟수의 상한을 정하여 불필요한 반복을 제한한다.[^2]

셋째, 공통 AI의 정보 선택에 대한 의존을 줄이기 위해 기관의 사전 판단을 별도로 유지한다. 담당 운용자는 AI가 작성한 요약이나 추천안을 보기 전에, 펀드의 운용원칙에 비추어 중요한 투자논거와 검토할 대안을 먼저 정리한다. 이후 RAG를 활용한 AI 분석과 대조하여, AI가 제시한 대안뿐 아니라 기관이 먼저 정한 대안도 함께 검토한다. 이는 최종 승인만 사람에게 맡기는 방식에 더하여, 무엇을 중요한 정보와 투자대안으로 볼 것인지 정하는 단계에도 기관의 관점을 남기는 방안이다. 기관의 기존 판단이 항상 옳다고 가정하지 않으며, AI 분석과 기관의 사전 판단 모두를 자료와 운용조건에 비추어 수정할 수 있도록 한다.[^3]

넷째, 근거를 처음 제공할 단계는 필요한 차이와 판단 품질을 함께 기준으로 선택한다. 점검 단계의 높은 유효율만으로 후기 배치를 최적의 해결책으로 채택하지 않고, 계획·작성·점검 단계의 각 배치에 같은 보완 절차를 적용하여 비교한다. 후속 통제 과제에서는 과잉수렴 격차 G와 거리 오차 A, 방향 불일치 E, 기대수익 손실 R을 함께 평가한다. 실제 운용의 시범 적용에서는 펀드의 투자목표·위험한도와의 부합 여부 및 수정 이유를 검토한다. 배분의 차이가 커졌다는 사실만으로 성과를 인정하지 않으며, 독립 분석과 추가 검색에 드는 시간과 비용도 채택 기준에 포함한다.[^4]

효과를 평가할 때에는 새로운 정보에 따른 재배분, 근거에 따른 기존 비중 유지, 제약에 따른 보류, 제안 실패 후 기존 비중 적용을 구분한다. 본실험에서는 기존 보유 유지가 관측된 펀드 간 차이에 관여했으므로, 이를 기관별 정보가 반영된 성과로 곧바로 해석해서는 안 된다. 한 펀드의 추가 전망만 바꾸는 후속 비교를 통해 설명에서 제시한 근거와 실제 선택의 반응도 대조한다.[^5] 수치 계산과 제약 검사는 이러한 판단을 뒷받침하는 기본 절차로 유지한다. 이상의 방안은 근거의 제공 시점뿐 아니라 공통 AI의 중간 판단을 이어받는 방식과 재검토 경로를 보완하려는 제안이다. 한 소형 양자화 모델과 열 개의 합성 상황으로 얻은 현재 결과는 공유 모델 자체의 인과효과나 제안한 보완책의 효과를 입증하지 않으며, 그 효과는 새로운 상황과 실제 운용자료에서 후속 검증해야 한다.

[^1]: Laban, P., Hayashi, H., Zhou, Y., & Neville, J. (2025). [LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120v1). arXiv:2505.06120v1. 초기 응답과 누적 대화가 후속 판단에 영향을 줄 수 있다는 문헌적 배경이며, 본고의 독립 배분안 비교 절차가 금융 과제에서 효과적임을 입증한 연구는 아니다.

[^2]: Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511). arXiv:2310.11511. 필요에 따른 검색과 생성 결과의 검토를 연결하는 관점을 참고하였다. 본고의 업무 단계 복귀 절차는 별도로 제안하는 운용 설계다.

[^3]: CFA Institute. (2022). [Ethics and Artificial Intelligence in Investment Management A Framework for Professionals](https://www.cfainstitute.org/-/media/documents/article/industry-research/Ethics-and-Artificial-Intelligence-in-Investment-Management_Online.pdf). AI 활용 과정의 감독과 책임에 관한 원칙을 참고하였다. AI 분석 전 기관의 투자논거를 작성하는 구체적 절차는 본고의 제안이다.

[^4]: Bommasani, R., Creel, K. A., Kumar, A., Jurafsky, D., & Liang, P. (2022). [Picking on the Same Person: Does Algorithmic Monoculture lead to Outcome Homogenization?](https://proceedings.neurips.cc/paper_files/paper/2022/hash/17a234c91f746d9625a75cf8a8731ee2-Abstract-Conference.html). Advances in Neural Information Processing Systems, 35, 3663–3678; Doshi, A. R., & Hauser, O. P. (2024). [Generative AI enhances individual creativity but reduces the collective diversity of novel content](https://discovery.ucl.ac.uk/id/eprint/10195027/). Science Advances, 10(28), eadn5290. 개별 품질과 집단 수준의 차이를 함께 평가하는 관점을 참고하였다.

[^5]: Matton, K., Ness, R. O., Guttag, J., & Kıcıman, E. (2025). [Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations](https://proceedings.iclr.cc/paper_files/paper/2025/file/b5ec50eb177908f21f78ed0d76ed525c-Paper-Conference.pdf). International Conference on Learning Representations. 설명에서 중요하다고 한 근거와 입력 변경에 실제로 반응하는 근거의 대응을 검토하는 관점을 참고하였다.
