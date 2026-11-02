## 6. 결과에 따른 해결방안

기관들이 최종 투자결정을 독립적으로 내리더라도, 검색·요약·전망 해석에서 공통 GenAI에 의존하면 중요하게 보는 정보와 검토할 투자대안이 유사해질 수 있다.[^1] 이에 대응하려면 기관별로 필요한 판단 차이를 유지하면서, 그 판단이 각 펀드의 투자목표와 운용조건에 부합하도록 업무를 설계해야 한다. 본고는 도입 전 내부 지침의 수립, 기관 자체의 판단과 대안 비교, 근거 변화에 따른 Workflow RAG의 재검토라는 세 가지 방안을 제안한다.

첫째, Workflow RAG 도입에 앞서 투자업무에서 GenAI를 사용하는 내부 지침을 마련한다. 직원들이 검색·요약·전망 분석에 AI를 개별적으로 활용하면, 기관이 별도의 투자 규칙을 채택하지 않아도 AI의 해석이 부서 간 보고와 후속 판단에 이어질 수 있다. 지침에는 업무별 AI 활용 범위와 검토 책임자를 명시하고, 원자료의 사실, AI의 해석, 운용자의 판단을 구분하여 전달하는 원칙을 포함한다. 예를 들어 투자검토서에는 AI를 사용한 단계, 확인한 원문자료, 해당 펀드에 적용할 이유를 함께 기재하도록 한다. AI가 작성한 산업 추천을 후속 업무에 활용할 때에도 펀드의 투자목표·현재 보유·위험한도에 비추어 채택한 이유를 제시한다. 이러한 지침은 별도 시스템 구축 없이 기존 검토서와 보고 양식에 반영할 수 있으며, AI 산출물이 기관의 판단근거로 받아들여지는 조건을 조직 차원에서 정하는 데 목적이 있다.[^2]

둘째, 기관 자체의 투자논거와 대안을 먼저 형성하고 이를 공통 AI의 분석과 대조한다. 담당 운용자는 AI의 요약과 추천안을 보기 전에 펀드의 운용조건을 바탕으로 핵심 투자논거, 반대근거와 검토할 대안을 정리한다. 이후 AI가 제시한 안과 비교하여 어떤 정보를 중요하게 보았는지, 어떤 산업의 배분 판단이 달라졌는지 검토한다.[^3] 필요한 경우에는 동일한 시장정보와 펀드별 자료를 사용하되 기존 AI의 계획·초안·대화 이력을 제외한 별도의 분석안도 작성한다.[^4] 이는 AI가 먼저 제시한 관점이 검토할 대안의 범위를 정하는 데 대응하고, 펀드별 조건에서 필요한 대안을 검토할 기회를 확보하기 위한 방안이다. 기관의 사전 판단과 AI의 분석안은 모두 자료와 운용조건에 따라 수정할 수 있도록 한다.

셋째, 기관별 근거가 바뀌면 그 근거에 의존한 투자판단까지 다시 검토하도록 Workflow RAG를 보완한다. 전망이 갱신되거나 기관별 자료와 공통 시장 해석이 상충하면, 관련 산업과 쟁점을 지정하여 필요한 자료를 다시 검색한다. 새 근거가 기존의 전망 평가나 위험판단을 바꿀 수 있는 경우에는 해당 단계로 돌아가 투자대안과 배분안을 재검토한다. 예를 들어 특정 산업의 전망을 뒷받침하던 근거가 수정되면, 그 전망을 이용한 산업 평가와 비중 조정의 이유도 함께 다시 검토한다. 기관별 전망의 채택 여부는 다른 시장정보와 펀드의 운용조건을 함께 고려하여 정하고, 검색 범위와 반복 횟수에 상한을 두어 불필요한 재검토를 제한한다. 이 방안의 핵심은 수정된 근거가 전망 평가와 배분 판단에 반영되도록 업무 단계를 다시 연결하는 데 있다.[^5]

세 방안의 운영기준은 필요한 전략 차이와 판단 품질을 함께 보존하는 데 둔다. 동일한 정보와 유사한 운용조건이 같은 선택을 지지한다면 유사한 배분이 적절할 수 있다. 반면 펀드별 정보와 제약상 필요한 배분 차이가 축소되는 과잉수렴과 함께 기대수익 손실이나 위험한도 위반이 나타난다면, 판단 품질 저하를 동반하는 부정적 동질화에 대응할 재검토가 필요하다. 따라서 배분 간 차이의 크기뿐 아니라 기관별 근거의 반영, 수익·위험 목표 및 제약과의 부합 여부를 함께 살피고, 추가 분석과 운용자 검토에 드는 시간·비용도 고려한다.[^6]

기관별 근거가 실제 판단에 작용했는지도 별도로 평가한다. 비중을 유지한 경우에는 근거에 따른 선택인지, 제약이나 제안 실패에 따른 결과인지 구분한다. 다른 조건을 유지한 채 핵심 근거를 바꾸어 선택의 반응을 대조함으로써, 설명에 근거를 언급한 것과 실제 판단에 활용한 것을 구분할 필요가 있다.[^7] 이러한 방안이 펀드별로 필요한 판단 차이를 보존하면서 부정적 동질화를 완화하는지, 어느 업무에 적용하는 것이 효과적인지는 후속 검증에서 확인해야 한다.

[^1]: Financial Stability Board. (2024). [The Financial Stability Implications of Artificial Intelligence](https://www.fsb.org/uploads/P14112024.pdf), §4.2.2. 공통 모델과 데이터 이용에 따른 상관 취약성의 가능성을 문제의 배경으로 참고하였다. 본고에서 기관 간 판단의 누적 경로를 직접 입증했다는 뜻은 아니다.

[^2]: ESMA. (2024, May 30). [On the use of Artificial Intelligence (AI) in the provision of retail investment services](https://www.esma.europa.eu/sites/default/files/2024-05/ESMA35-335435667-5924__Public_Statement_on_AI_and_investment_services.pdf). Public Statement, ESMA35-335435667-5924, §§4–5. EU 소매투자서비스 관련 성명에서 직원의 제3자 AI 활용까지 관리 대상으로 보는 관점을 참고하였다. 투자검토서의 구체적인 작성 항목과 과잉수렴에 대응하는 사용 원칙은 본고의 제안이다.

[^3]: CFA Institute. (2022). [Ethics and Artificial Intelligence in Investment Management A Framework for Professionals](https://www.cfainstitute.org/-/media/documents/article/industry-research/Ethics-and-Artificial-Intelligence-in-Investment-Management_Online.pdf). AI 활용 과정의 감독과 책임에 관한 원칙을 참고하였다. AI 분석 전에 기관의 투자논거를 작성하는 구체적인 절차는 본고의 제안이다.

[^4]: Laban, P., Hayashi, H., Zhou, Y., & Neville, J. (2025). [LLMs Get Lost In Multi-Turn Conversation](https://arxiv.org/abs/2505.06120v1). arXiv:2505.06120v1. 누적 대화와 앞선 응답이 후속 판단에 영향을 줄 수 있다는 문헌적 배경이다. 기존 초안을 제외한 분석안의 금융적 효과를 직접 입증한 연구는 아니다.

[^5]: Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2023). [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511). arXiv:2310.11511. 필요에 따른 검색과 생성 결과의 검토를 연결하는 관점을 참고하였다. 변경된 근거에 따라 투자판단의 이전 단계로 돌아가는 업무 설계는 본고의 제안이다.

[^6]: Bommasani, R., Creel, K. A., Kumar, A., Jurafsky, D., & Liang, P. (2022). [Picking on the Same Person: Does Algorithmic Monoculture lead to Outcome Homogenization?](https://proceedings.neurips.cc/paper_files/paper/2022/hash/17a234c91f746d9625a75cf8a8731ee2-Abstract-Conference.html). Advances in Neural Information Processing Systems, 35, 3663–3678; Doshi, A. R., & Hauser, O. P. (2024). [Generative AI enhances individual creativity but reduces the collective diversity of novel content](https://discovery.ucl.ac.uk/id/eprint/10195027/). Science Advances, 10(28), eadn5290. 개별 품질과 집단 수준의 차이를 함께 평가하는 관점을 참고하였다.

[^7]: Matton, K., Ness, R. O., Guttag, J., & Kıcıman, E. (2025). [Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations](https://proceedings.iclr.cc/paper_files/paper/2025/file/b5ec50eb177908f21f78ed0d76ed525c-Paper-Conference.pdf). International Conference on Learning Representations. 설명에서 중요하다고 한 근거와 입력 변경에 실제로 반응하는 근거의 대응을 검토하는 관점을 참고하였다.
