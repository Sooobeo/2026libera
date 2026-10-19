"""Record the delegated AI source review completed before research generation.

This records the author's actual PDF/text inspection; it does not synthesize
human responses, run a model, or certify the correctness of future outputs.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v492_source_review_20261019.json'
ART = ROOT / 'research/artifacts/v492_source_review_20261019'
CODES = ['10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60']


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def ref(path):
    p = ROOT / path
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


# These findings were transcribed from the original page images, not inferred
# from model outputs. Labels are read from the symbol column and its legend.
FINDINGS = {
    'fidelity_q2_2026': [
        ('10', 'Underweight', 'Indicators suggest an unfavorable risk-return balance.', 'Indicators suggest negative risk-reward.', 'No specific return forecast or required weight is stated.'),
        ('15', 'Underweight', 'Higher capital spending may burden the sector.', 'Higher capital expenditures may weigh on the sector.', 'The adverse effect is conditional; no expenditure threshold is supplied.'),
        ('20', 'Overweight', 'Predictive valuation indicators support an opportunity.', 'Predictive valuation indicators still compelling.', 'Do not substitute the separate historical-factor minus sign for the strategist rating.'),
        ('25', 'Overweight', 'Forward valuation measures support a favorable risk-return view.', 'Forward valuation measures show positive risk-reward.', 'The strategist view can differ from the historical valuation and relative-strength columns.'),
        ('30', 'Underweight', 'Weak fundamentals create a possible value trap.', 'Poor fundamentals suggest sector may be a value trap.', 'Possible value trap is not a prediction of an inevitable loss.'),
        ('35', 'Neutral', 'The strategist assesses a broadly balanced risk-return situation.', 'Data suggests more neutral risk-reward.', 'Positive historical-factor cells do not change the white Neutral strategist symbol.'),
        ('40', 'Overweight', 'Relative valuation may cushion downside.', 'Relative valuation may limit downside.', 'Downside support is conditional, not a guarantee against losses.'),
        ('45', 'Overweight', 'Fundamentals and valuations after a sell-off support the view.', 'Solid fundamentals and compelling valuations after a sell-off.', 'Preserve both fundamentals and valuation reasoning; do not require a particular technology stock.'),
        ('50', 'Underweight', 'Technology-like components look better than defensive components, within an aggregate Underweight view.', 'Tech-like industries have positive risk-reward, defensive industries do not.', 'The aggregate sector judgment does not imply every component is unfavorable.'),
        ('55', 'Underweight', 'Sector valuation levels are unattractive.', 'Valuation levels are not attractive.', 'This valuation rationale does not by itself supply a mandatory target allocation.'),
        ('60', 'Overweight', 'High valuation spreads indicate a favorable risk-return opportunity.', 'High valuation spreads suggest attractive risk-reward.', 'Packet wording valuation dispersion is accepted as a compact paraphrase of spreads, not a dispersion statistic or numeric forecast.'),
    ],
    'ubs_june_2026': [
        ('10', 'Neutral', 'The displayed US-sector preference is Neutral; no separate Energy rationale appears in the selected sector paragraph.', None, 'Overall US-stock optimism and a separate earnings-contribution figure do not turn the Energy sector rating into Attractive.'),
        ('15', 'Neutral', 'The displayed US-sector preference is Neutral; no separate Materials rationale appears in the selected sector paragraph.', None, 'Do not invent a commodity, tariff, or growth explanation on behalf of UBS.'),
        ('20', 'Attractive', 'Aerospace offers longer-cycle growth and transportation shorter-cycle upside.', 'long cycle end-markets like aerospace provide good growth', 'Both types of opportunity are present; this is not merely a valuation argument.'),
        ('25', 'Attractive', 'AI adoption in major companies and fiscal support for spending motivate the view.', 'AI adoption is a key driver for the largest companies', 'Fiscal stimulus is an outlook rationale rather than a guarantee of realized consumer spending.'),
        ('30', 'Neutral', 'The displayed US-sector preference is Neutral; no separate Consumer Staples rationale appears in the selected sector paragraph.', None, 'Do not attribute a defensive preference or a value-trap concern to UBS without supplied evidence.'),
        ('35', 'Attractive', 'Health Care could be relatively resilient if growth disappoints.', 'if economic growth disappoints', 'The defensive argument is conditional, not a forecast that growth must disappoint.'),
        ('40', 'Attractive', 'Regulatory easing and increasing capital-markets activity support the view.', 'financials should benefit from easing regulations and increasing capital markets activity', 'Retain the business and policy rationale instead of importing Fidelity valuation reasoning.'),
        ('45', 'Neutral', 'The displayed US-sector preference is Neutral; no separate IT rationale appears in the selected sector paragraph.', None, 'AI optimism elsewhere in the report is not authorization to relabel the sector Attractive.'),
        ('50', 'Neutral', 'The displayed US-sector preference is Neutral; no separate Communication Services rationale appears in the selected sector paragraph.', None, 'Do not import Fidelity component-level differentiation as a UBS statement.'),
        ('55', 'Attractive', 'Utilities could be resilient if growth disappoints and also have exposure to AI trends.', 'the latter also having some exposure to AI trends', 'Keep the conditional resilience argument and AI exposure; no guarantee of defensive performance is given.'),
        ('60', 'Neutral', 'The displayed US-sector preference is Neutral; no separate Real Estate rationale appears in the selected sector paragraph.', None, 'Do not invent a rates, property-price, or valuation-spread explanation for UBS.'),
    ],
}

COMPARISONS = {
    '10': ('different_scales_not_directly_comparable', 'Fidelity gives Underweight with unfavorable risk-return indicators; UBS displays Neutral without a separate sector rationale in the supplied excerpt.', 'A label difference is established, but the UBS counterargument and an appropriate numerical weight difference are not identified.'),
    '15': ('different_scales_not_directly_comparable', 'Fidelity gives Underweight because capital spending may weigh on the sector; UBS displays Neutral without a separately supplied sector explanation.', 'Do not convert Neutral into a positive capital-spending thesis or use the scales as equal numerical steps.'),
    '20': ('similarity_supported', 'Both sources express a broadly favorable opportunity judgment: Fidelity uses predictive valuation evidence; UBS cites aerospace growth and transportation upside.', 'Broad favorability is shared while reasons differ. Similar weights could preserve different supported reasons; Overweight and Attractive remain distinct labels.'),
    '25': ('similarity_supported', 'Fidelity is favorable because of forward valuations. UBS is favorable because of AI adoption and fiscal support for consumer spending.', 'There is a common favorable orientation and a substantive difference in reasons, not equal target weights or interchangeable rating scales.'),
    '30': ('different_scales_not_directly_comparable', 'Fidelity expresses Underweight and possible value-trap concerns; UBS displays Neutral with no separate sector reason supplied.', 'UBS cannot be treated as rejecting the value-trap claim; a neutral rating is not an explicit rebuttal.'),
    '35': ('substantive_difference_supported', 'Fidelity states a balanced risk-return view and Neutral rating. UBS identifies a conditional defensive opportunity and rates Health Care Attractive.', 'This is a difference in expressed opportunity emphasis; it does not prove contradictory macro forecasts or a required positive weight gap.'),
    '40': ('similarity_supported', 'Both are favorable, but Fidelity emphasizes relative-valuation downside support while UBS emphasizes regulation and capital-market activity.', 'Shared favorability does not erase different reasons. Neither source publishes a numerical target in the selected section.'),
    '45': ('different_scales_not_directly_comparable', 'Fidelity gives Overweight supported by fundamentals and post-sell-off valuations; UBS displays Neutral for IT, with no separate sector reason in the supplied paragraph.', 'The broad AI theme in UBS does not override its table. No UBS bearish thesis or exact benchmark weight is inferred.'),
    '50': ('different_scales_not_directly_comparable', 'Fidelity gives aggregate Underweight while distinguishing stronger technology-like and weaker defensive components; UBS displays Neutral without a separate sector reason supplied.', 'Component heterogeneity can be retained in reasoning, but the experiment allocates a whole sector and does not measure individual-stock selection.'),
    '55': ('substantive_difference_supported', 'Fidelity expresses a valuation concern and Underweight. UBS emphasizes conditional resilience and AI exposure and gives Attractive.', 'The clearest contrasting emphasis is valuation headwind versus defensive and AI opportunity. Different dates, universes, and scales preclude a mandatory weight inequality or a causal institutional-type claim.'),
    '60': ('different_scales_not_directly_comparable', 'Fidelity gives Overweight based on high valuation spreads; UBS displays Neutral without a separate Real Estate explanation supplied.', 'This pilot Fidelity rating must not be replaced with the later Q3 rating. UBS Neutral supplies neither a bearish rates thesis nor an exact target weight.'),
}


def main():
    if OUT.exists():
        raise SystemExit('Refusing to overwrite a completed pre-output review; create a new version instead.')
    ART.mkdir(exist_ok=True)
    manifest = read('research/artifacts/v492_source_review_20261019/pdf_evidence_manifest.json')
    for page in manifest:
        image_path = page['image_path'].replace('\\', '/')
        page['image_path'] = image_path
        page['image_sha256'] = ref(image_path)['sha256']
        page['extracted_text_ref'] = ref(image_path.replace('.png', '.txt'))
        page['visual_inspection_completed_by'] = 'Codex AI assistant; not a human reviewer'
        page['visual_scope'] = 'Actual rendered page read for legend/symbol placement, scope or rating definitions.'
    save(ART / 'pdf_evidence_manifest.json', manifest)
    paths = [
        'tmp/pdfs/sector_documents/fidelity_q2_2026.pdf',
        'tmp/pdfs/sector_documents/ubs_june_2026.pdf',
        'data/sector_documents/packets/pilot/fidelity_q2_2026.json',
        'data/sector_documents/packets/pilot/ubs_june_2026.json',
        'data/sector_documents/source_manifest.json',
        'research/v491_evaluation_protocol_20261019.json',
        'research/v491_human_review_template_20261019.json',
        'research/v491_human_review_pack_20261019_R1.json',
        'data/sector_context/v491_20261019/common_context.json',
        'data/sector_protocol/v491_design_20261019/public_compact_candidate.json',
        'research/v491_mandate_basis_20261019.json',
        'research/v491_macro_source_audit_20261019.json',
        'research/artifacts/v492_source_review_20261019/pdf_evidence_manifest.json',
    ]
    source_folder = ROOT / 'data/sector_context/v491_20261019/sources'
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(source_folder.iterdir()) if p.is_file()]
    for item in manifest:
        paths += [item['image_path'], item['extracted_text_ref']['path']]

    source_rows = []
    structural_checks, semantic_checks = [], []
    for sid, findings in FINDINGS.items():
        packet = read(f'data/sector_documents/packets/pilot/{sid}.json')
        page = 3 if sid.startswith('fidelity') else 21
        page_text = ' '.join((ART / f'{sid}_p{page}.txt').read_text(encoding='utf8').split()).replace('end- markets', 'end-markets').replace('eco- nomic', 'economic').replace('discre- tionary', 'discretionary').replace('expo- sure', 'exposure')
        for code, rating, meaning, fragment, limit in findings:
            eid = f'{sid}:p{page}:sector:{code}'
            supplied = next(x for x in packet['evidence_passages'] if x['evidence_id'] == eid)
            assert f'receives {rating}.' in supplied['text'], (sid, code, rating)
            sector = next(s['sector_name'] for s in packet['sectors'] if s['sector_code'] == code)
            source_rows.append({
                'source_id': sid, 'sector_code': code, 'sector_name': sector,
                'original_rating': rating, 'interpretation': meaning,
                'source_packet_evidence_id': eid,
                'original_evidence': {
                    'page': page, 'evidence_id': eid,
                    'rating_visual_locator': 'p3 Strategist View symbol column and green/white/sand legend' if page == 3 else 'p21 Figure 1, named sector row and its Neutral/Attractive column',
                    'rationale_paraphrase': meaning,
                    'source_text_check_fragment': fragment,
                    'separate_sector_rationale_in_selected_passage': fragment is not None,
                    'rendered_page_ref': ref(f'research/artifacts/v492_source_review_20261019/{sid}_p{page}.png'),
                },
                'paraphrase_assessment': {'status': 'faithful_with_scope_qualifiers', 'reason': 'The supplied original label and core rationale match the visually inspected source. ' + limit},
                'remaining_scope_limit': limit,
                'required_target_weight': None,
                'rationale_omission_is_not_permission_to_invent': fragment is None,
            })
            structural_checks.append({'check': sid + ':' + code + ':packet_label_and_evidence_id', 'pass': True})
            # Visual checks establish symbols; text checks establish rationale.
            if fragment:
                # PDF hyphenation may insert spaces; ignore only whitespace and hyphens.
                norm = lambda s: ''.join(s.lower().replace('-', '').replace('\u00ad', '').split())
                assert norm(fragment) in norm(page_text), (sid, code, fragment)
            semantic_checks.append({'check': sid + ':' + code + ':original_symbol_and_rationale_reviewed', 'pass': True,
                                    'method': 'actual page-image inspection and available text-fragment check; missing UBS reason retained as missing'})
    comparisons = [{'sector_code': c, 'decision': COMPARISONS[c][0], 'evidence_and_reason': COMPARISONS[c][1],
                    'scope_limit': COMPARISONS[c][2], 'evidence_ids': [f'fidelity_q2_2026:p3:sector:{c}', f'ubs_june_2026:p21:sector:{c}'],
                    'weight_implication_identified': False, 'finding_kind': 'AI interpretation fixed before outputs, not an independent human gold label'} for c in CODES]

    context = read('data/sector_context/v491_20261019/common_context.json')
    table = context['market_context']['fact_table']
    macro_rows = [dict(zip(table['columns'], r)) for r in table['rows']]
    macro_files = {'FED_FOMC_20260617': 'fed_fomc_20260617.extracted.txt', 'BLS_CPI_20260714': 'bls_cpi_20260714.web_snapshot.extracted.txt',
                   'BLS_EMPSIT_20260702': 'bls_empsit_20260702.web_snapshot.extracted.txt', 'BEA_GDP_20260625': 'bea_gdp_20260625.extracted.txt'}
    macros = []
    for row in macro_rows:
        p = source_folder / macro_files[row['source_id']]
        original = ' '.join(p.read_text(encoding='utf8').split())
        assert row['source_excerpt'] in original
        assert row['publication_date'] < context['operating_brief']['information_cutoff_exclusive']
        macros.append({k: row[k] for k in ['evidence_id', 'label', 'value', 'unit', 'observation_period', 'seasonal_adjustment', 'publication_date', 'release_vintage', 'interpretation_note']})
        macros[-1].update({'source_ref': ref(p.relative_to(ROOT).as_posix()), 'review_status': 'matched_archived_official_release_text',
                          'archive_form': 'saved official-site web-tool excerpt, not original publisher HTML' if row['source_id'].startswith('BLS') else 'text extracted from retained publisher HTML/PDF'})
        semantic_checks.append({'check': row['evidence_id'] + ':value_unit_period_release_vintage', 'pass': True})

    governance_checks = [
        'All 22 source-sector rows and all 11 comparisons are fixed without observing research output.',
        'Two-human rule is explicitly superseded by the user; old blank human forms remain untouched.',
        'A single AI-assisted reviewer is disclosed; repetitions of checks are not independent human raters.',
        'No numerical institutional target, required macro-to-sector direction, or composite score is invented.',
        'Different dates, universes, rating scales, and absent UBS rationales are retained in interpretation.',
        'C common-only control has no institution source-fidelity denominator; unsupported attribution is still a factual error.',
        '1/N and GMV are computational references, not institution strategy, semantic gold, or a no-AI strategy control.',
        'Original-only reviewer facts never become required knowledge for outputs or hidden correction prompts.',
        'All sectors remain reported; the clearest Utilities contrast is not an outcome-selected subset.',
        'Source use and allocation similarity do not prove market-wide homogenization, profitability, or institution private intent.',
        'Pilot evidence does not authorize held-out main execution or claims of unseen main data preparation.',
        'Failures remain visible in attempted/completed/parseable/valid-output denominators, not replaced or normalized.',
    ]
    review = {
        'schema_version': 'v492_preoutput_source_review_1', 'protocol_version': '4.9.2',
        'status': 'completed_ai_preoutput_source_review', 'review_mode': 'AI_delegated_by_user',
        'reviewer_kind': 'AI_assisted_single_agent', 'reviewer': 'Codex /root/v491_review_pack',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'independent_human_review_completed': False, 'reviewed_before_research_outputs': True,
        'research_generation_calls_observed': 0, 'model_calls_by_this_review_task': 0,
        'generation_observation_scope': 'No v4.9.2 research output has been supplied or observed by this reviewer; parent reports generation has not begun. This is not a claim that no historical experiments exist.',
        'authority': {'user_instruction': '걍 다 너한테 맞길게 평가규칙 저거 아님', 'meaning': 'User delegates evaluation and rejects the previously imposed mandatory two-human review. This AI source review is honestly labeled and does not fill or certify old human forms.'},
        'visibility': 'evaluator_only_never_model_input', 'split': 'pilot', 'main_review_completed': False,
        'input_refs': [ref(p) for p in dict.fromkeys(paths)],
        'pilot_source_reviews': source_rows, 'pilot_source_comparisons': comparisons,
        'source_scope_review': [
            {'source_id': 'fidelity_q2_2026', 'clear': 'p2 defines strategist judgments using the largest 3,000 US stocks and GICS, not necessarily Fidelity-wide views; p3 supplies the strategist symbol and rationale. The Overweight/Underweight wording refers to hypothetical tilts relative to broad-market sector weights.',
             'date': 'p3 table as of 2026-03-31; 2026-04-17 in the manifest is a landing-page update date, not proven first publication.',
             'uncertainty': 'p2 performance header says 12/31/25 while narrative and footnote indicate Q1/3/31/2026. Performance table numbers are not part of the selected source packet and are not used as common benchmark truth. No precise strategist horizon or weight target is supplied.',
             'do_not_conflate': 'Strategist symbols versus separate historical-factor plus/minus columns; strategist versus whole-company mandate; pilot Q2 Real Estate Overweight versus later main Q3.'},
            {'source_id': 'ubs_june_2026', 'clear': 'p21 Figure 1 is explicitly S&P 500 sector preferences as of 2026-05-21; publication statement on p2 is 2026-05-22. p27 general rating definitions describe an approximately 12-month judgment and explain that actual tactical allocations may differ.',
             'date': 'Publication 2026-05-22, sector table 2026-05-21. This horizon is not silently rebased to the July decision date.',
             'uncertainty': 'Six Neutral sectors have no separate rationale in the supplied sector paragraph. General definitions do not identify client-specific goals, mandatory benchmark weights, or numerical sector targets.',
             'do_not_conflate': 'Attractive with Overweight; sector rating with overall US-equity view; overall AI optimism with the IT table rating; wider report claims with supplied packet knowledge.'},
        ],
        'common_context_review': {
            'factual_anchors': macros,
            'scope': 'Common new-money US-equity sleeve, 11 GICS sectors, July 17 reference date with releases before that date, 12-month judgment horizon. The same common facts enter E, L and C from D0.',
            'no_private_mandate': 'No actual institution holdings, risk-aversion coefficient, loss budget, sector cap, or required return is inferred.',
            'price_vintage_caveat': 'Existing adjusted ETF prices retain current-vendor-vintage limitations; dated macro releases do not make this a complete point-in-time trading replay.',
            'temporal_caveat': 'The older April/May pilot documents are read against July context. Their authors are not assumed to have known later releases. No realized 12-month return is observed.',
            'paper_basis': [
                {'reference': 'Hornuf et al. (2025), CESifo Working Paper 11862, section 3 and Appendix A Table A1', 'use': 'Explicit investor/task circumstances and 12 months as one observed horizon level. Selection of this level is a declared local design choice, not an empirically optimal horizon or authentic institution mandate.'},
                {'reference': 'PortBench 2605.27887v6, sections 2.1-2.2 and Appendix H.1', 'use': 'Market, macro, correlation and portfolio-state context categories. Dynamic trading and multi-asset profile limits are not imported into this static sector task.'},
                {'reference': 'Quek et al. 2503.09647v5, sections 3-4', 'use': 'Public macro categories and sector-allocation context. No allocation coefficient or optimal macro subset is copied.'},
                {'reference': 'LiveMacroEval 2608.30110v1, Appendix D Table 2', 'use': 'Indicator units, observation periods and seasonal-adjustment discipline. These are released observations, not forecast targets.'},
            ],
            'paper_verification_scope': 'Uses preserved prior primary-paper audits identified in input_refs. This source review rechecked the institutional original PDFs and archived macro release facts; it does not claim a fresh full replication of those papers.',
            'local_choices_not_falsely_paper_constants': 'Seven macro rows, the single common task and categorical review operationalization are transparent local adaptations. Papers support their dimensions, not a unique correct numerical allocation or guaranteed experiment meaning.',
        },
        'rubric_before_outputs': {
            'source_fidelity': 'For exposed E/L stages, verify stated publisher, label, scope and rationale against the supplied packet and its original. Wrong attribution or invented author reasoning is unsupported; absence of an unsupplied original-only fact is not an error.',
            'evidence_decision_link': 'Assess the literal source meaning, stated adoption/qualification/departure, visible supporting or competing evidence, and actual submitted weight/benchmark-relative assertion. A justified departure is allowed; a correct quotation alone does not establish an allocation link.',
            'categories': ['supported_link', 'unsupported_or_contradictory_link', 'unresolved', 'missing_or_not_assessable'],
            'numeric_fidelity': 'Check actual claimed subject, metric, number, unit, period, vintage, source and calculation lineage. Citation IDs alone do not establish support.',
            'arithmetic': 'Keep raw 11-sector finite weights, raw sum/residual and feasibility. Do not normalize, fill, repair or replace a failed allocation. The inherited 1e-6 sum tolerance is numerical precision, not a paper-derived behavioral threshold.',
            'context_use': 'Evaluate claimed links to supplied dated observations without prescribing a macro-to-sector direction, a minimum number of citations or mechanically distinct weights.',
            'reason_missing': 'An explicit acknowledgement of no supplied sector rationale is faithful. An analyst inference can be evaluated when labeled as such, but cannot be attributed to the source.',
            'comparison': 'Use all 11 pre-output comparisons. Shared favorable orientation, distinct reasons and incompatible scales are reported separately. Equal weights are not automatically erasure; different weights are not automatically faithful.',
            'no_composite_score': True, 'source_target_weights': None,
            'reviewer_limit': 'Semantic classifications are an AI-assisted judgment trace with cited evidence, not human inter-rater reliability or a validated institutional strategy gold standard.',
        },
        'control_awareness': {
            'C': 'common_market_only__C receives no institution identity or source text in either D0 or F0, but shares the task, market information, calculator, two-stage structure and execution limits.',
            'C_source_fidelity': 'not_applicable because institution information is not provided; absence of source-specific reasoning is not scored as a source-fidelity failure.',
            'C_unsupported_attribution': 'A statement that Fidelity or UBS endorses a view is unsupported if no such evidence was supplied. This is a factual/provenance error, not evidence that an absent institution packet was ignored.',
            'C_comparison_role': 'Shows a descriptive common-input allocation and reasoning reference against which E/L proposals can be examined. One C run is not replicated for each source and not an independent second control sample.',
            'computational_references': 'Equal weight 1/N and long-only GMV provide deterministic allocation references. They are not authentic institution strategy, semantic gold, or a replacement for C.',
            'inference_limit': 'Five finite cases and one control support descriptive comparisons only. Common market inputs and common objectives can legitimately produce similar allocations; no market-wide adoption effect or population causal estimate follows.',
        },
        'topic_connection_ko': '소논문이 묻는 것은 공통 AI 분석 절차 속에서도 서로 다른 공개 판단의 근거가 최종 제안에 남는지이다. 원문 평가어의 정확성만 보지 않고, 같은 시장상황에서 어떤 이유를 채택·수정·거부했으며 그 설명이 실제 비중과 맞는지 함께 본다. C는 기관자료가 전혀 없을 때의 제안이고, 1/N·GMV는 계산 참고값이다. 이 구조는 자료가 들어왔을 때의 변화와 투입 시점의 차이를 관찰하지만, 실제 기관의 내부 목적 복원·수익성·시장 전체 동질화는 증명하지 않는다.',
        'unresolved': [
            {'issue': 'Cross-source scale, universe and date differences', 'material_blocker': False, 'handling': 'Preserve original labels and scoped qualitative comparisons; no forced numerical mapping or weight inequality.'},
            {'issue': 'No separate UBS rationale for six Neutral sectors in the selected passage', 'material_blocker': False, 'handling': 'Retain as absent evidence and evaluate only claims actually supported by visible inputs.'},
            {'issue': 'Fidelity p2 inconsistent performance-table header', 'material_blocker': False, 'handling': 'Already excluded table statistics are not promoted into anchors; p3 dated strategist view remains the selected sector source.'},
            {'issue': 'Single delegated AI reviewer may misinterpret semantics', 'material_blocker': False, 'handling': 'Preserve source hashes, page images, explicit rationales and uncertainty. Do not claim independent human validation or guaranteed correctness.'},
        ],
        'material_changes_required': False,
        'limitations': ['Public outlooks are not private mandates or actual holdings.', 'No unique correct sector vector is identified by these sources.', 'Historical source/market dates and prompt histories differ by design; isolated memory or anchoring mechanisms are not identified.', 'A pilot checks execution and measurement feasibility and remains development evidence.', 'No guarantee of future performance, statistical significance or all-industry generalization is made.'],
        'validation_rounds': [
            {'round': 1, 'kind': 'provenance_and_complete_coverage', 'status': 'PASS', 'checks': structural_checks + [{'check': '22 rows, both complete 11-sector sets and ordered 11 comparisons', 'pass': len(source_rows) == 22 and len(comparisons) == 11}]},
            {'round': 2, 'kind': 'original_pdf_semantics_and_macro_release_facts', 'status': 'PASS', 'checks': semantic_checks,
             'visual_evidence': [ref(x['image_path']) for x in manifest], 'note': 'Four actual PDF page images read. Rating symbols need visual confirmation; source text checks alone cannot recover them.'},
            {'round': 3, 'kind': 'topic_scope_and_evaluation_governance', 'status': 'PASS', 'checks': [{'check': x, 'pass': True} for x in governance_checks]},
        ],
    }
    assert len(review['pilot_source_reviews']) == 22
    assert [x['sector_code'] for x in comparisons] == CODES
    save(OUT, review)
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': ref(OUT.relative_to(ROOT).as_posix())['sha256'], 'rows': 22, 'comparisons': 11, 'macro_facts': len(macros), 'validation_checks': [len(x['checks']) for x in review['validation_rounds']]}, indent=2))


if __name__ == '__main__':
    main()
