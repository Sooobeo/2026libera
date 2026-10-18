"""Freeze primary-source evidence for the v4.5 output-contract revision only."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'research/evidence/v45_structured_output_20261018'
OUT = ROOT / 'research/v45_revision_reference_20261018.json'
INHERITED = ROOT / 'research/v44_conditions_reference_20261018.json'
INHERITED_SHA = 'a403d4c37d1581f9af21af8ba7a6333614d890ff15277e83181c1204549a9c5b'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise FileExistsError('Evidence is immutable once published; use a new revision')
    if sha(INHERITED) != INHERITED_SHA:
        raise ValueError('The immutable inherited conditions changed')
    manifest = json.loads((DIR / 'manifest.json').read_text())
    for record in manifest['records']:
        if sha(ROOT / record['path']) != record['sha256']:
            raise ValueError('Archived primary source changed')
    if (DIR / 'ollama_LLAMA_CPP_VERSION_v0351.txt').read_text().strip() != 'b11232':
        raise ValueError('Unexpected declared upstream version')
    evidence = {
        'schema_version': 'libera_v45_revision_reference_1.0',
        'protocol_version': '4.5',
        'change_scope': 'response_schema_and_prompt_grounding',
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'primary_evidence_fixed_before_new_generation; intervention_not_yet_validated',
        'freeze_policy': 'Pin this complete file and listed source bytes before any v4.5 generation. Preserve v4.4 conditions, failed run and all prior reviews unchanged.',
        'inherited_conditions': {'path': INHERITED.relative_to(ROOT).as_posix(), 'sha256': INHERITED_SHA},
        'primary_sources': manifest['records'],
        'source_manifest': {'path': (DIR / 'manifest.json').relative_to(ROOT).as_posix(), 'sha256': sha(DIR / 'manifest.json')},
        'verified_claims': [
            {
                'id': 'financial_paper_explicit_contract',
                'evidence_level': 'direct_financial_paper_prompt_control',
                'sources': ['finvector_2610_08882.pdf'],
                'locations': ['Section 4.1, PDF pages 4-5', 'Section 6.1, PDF page 7', 'Section 10, PDF pages 11-12'],
                'finding': 'FinVector appends a task-specific JSON schema to the prompt while retaining matched examples, base revision and decoding. Its base-model JSON validity changes from 0% to 91.33%, but those scores belong to its 600-item MLX benchmark. The paper does not report Ollama grammar-constrained decoding. The prompt/schema registry and item-level outputs remain private.',
                'supports': 'Clarifying the expected output contract before interpreting a formatting failure as inability.',
                'does_not_support': 'Reproducing private benchmark prompts, importing its score as Q4_K_M performance, or proving that this LIBERA revision will complete.'
            },
            {
                'id': 'json_mode_is_not_task_schema',
                'evidence_level': 'version_pinned_official_implementation',
                'sources': ['ollama_llama_server_v0351.go'],
                'saved_source_lines': [54, 55, 56, 57, 58, 59, 60, 1678, 1683, 1684, 1686, 1687],
                'finding': 'format="json" selects a generic JSON-object grammar with arbitrary keys. An object-valued format is forwarded as json_schema. Thus valid JSON mode alone does not impose the existing LIBERA response fields or prevent an input-shaped object.',
                'not_a_guarantee': 'A schema cannot guarantee useful free-text reasons, correct source labels, complete streaming, or completion within a wall-clock limit.'
            },
            {
                'id': 'schema_visibility_and_grammar_are_distinct',
                'evidence_level': 'official_api_guidance_plus_upstream_implementation_guidance',
                'sources': ['ollama_structured_outputs.html', 'llamacpp_grammar_README_b11232.md'],
                'locations': ['Ollama: Generating structured JSON with a schema', 'llama.cpp saved README line 151'],
                'finding': 'Ollama recommends also placing the schema in the prompt. The upstream grammar guide says the schema constrains output but is not itself injected into the prompt. v4.5 therefore combines explicit prompt grounding with API schema enforcement; this pair does not identify their separate effects.'
            },
            {
                'id': 'declared_backend_revision',
                'evidence_level': 'version_pinned_source_build_declaration',
                'sources': ['ollama_LLAMA_CPP_VERSION_v0351.txt', 'ollama_llama_CMakeLists_v0351.txt', 'ollama_llama_README_v0351.md', 'ollama_compat_001_v0351.patch', 'ollama_compat_002_v0351.patch'],
                'saved_source_lines': {'ollama_llama_CMakeLists_v0351.txt': [115, 116, 184]},
                'finding': 'Ollama v0.35.1 declares llama.cpp b11232 and its CMake fetch uses that reference with compatibility patches. The archived patches do not modify the schema converter paths reviewed here.',
                'limit': 'This source chain is not an independently reproduced build or a binary attestation of every installed backend instruction.'
            },
            {
                'id': 'supported_schema_subset',
                'evidence_level': 'version_pinned_official_tests_and_implementation',
                'sources': ['ollama_structured_output_test_v0351.go', 'llamacpp_json_schema_to_grammar_b11232.cpp', 'llamacpp_schema_tests_b11232.cpp'],
                'saved_source_lines': {'ollama_structured_output_test_v0351.go': [15, 16, 17, 18, 19, 20, 21, 22],
                    'llamacpp_json_schema_to_grammar_b11232.cpp': [889, 891, 895, 898, 910, 924, 929, 930, 931, 952, 963, 964],
                    'llamacpp_schema_tests_b11232.cpp': [619, 621, 626, 637, 642, 685, 690, 691]},
                'finding': 'Official Ollama tests cover required properties, enum and additionalProperties=false. Pinned upstream code/tests cover homogeneous arrays with minItems/maxItems. Numeric bounds have an integer-specific branch; the number branch uses generic numeric syntax.',
                'required_caution': 'Finite numbers, bounds, sector uniqueness and the full-investment sum remain explicit offline checks; do not claim backend support for every JSON Schema keyword.'
            },
            {
                'id': 'tuple_documentation_implementation_discrepancy',
                'evidence_level': 'primary_source_discrepancy_recorded_not_resolved_by_assumption',
                'sources': ['llamacpp_grammar_README_b11232.md', 'llamacpp_json_schema_to_grammar_b11232.cpp', 'llamacpp_schema_tests_b11232.cpp'],
                'saved_source_lines': {'llamacpp_grammar_README_b11232.md': [207, 209, 210, 219],
                    'llamacpp_json_schema_to_grammar_b11232.cpp': [912, 913, 919, 922],
                    'llamacpp_schema_tests_b11232.cpp': [526, 527, 528, 530, 540, 541, 542, 544]},
                'finding': 'The pinned README warns about prefixItems, while the same revision includes tuple generation and successful tuple fixtures. This audit does not classify all prefixItems schemas as unsupported. The actual 11-sector ordered tuple was not executed or independently compiled.',
                'decision': 'Do not use prefixItems, tuple ordering, uniqueItems or contains in this revision. Preserve the existing array interface and separately check missing/duplicate codes.'
            }
        ],
        'recommended_revision': {
            'api_change': 'Replace only the generic format="json" value with a task-response JSON Schema object.',
            'prompt_change': 'Add response_schema and one fixed concise mechanical output-contract instruction to each stage task user JSON by the same deterministic transformation. When a prior stage task is resent, apply the identical transformation. Do not rewrite the original task, source or market values.',
            'explicit_invariants': ['Exact model tag, digest, quantization, engine and renderer policy',
                'All v4.4 temperature, seed, penalties, context, output-token and thread/batch settings',
                'Same 900-second engineering stage deadline and keep_alive=0',
                'Same predetermined Fidelity Q2/R1 case, market observations, covariance and baseline values',
                'Original SYSTEM and task strings, public institution-document values, previous assistant final strings and calculator-feedback strings',
                'No evaluator reference labels, hidden source answers, repairs, automatic retries or substituted cases'],
            'top_level_required_fields': ['source_id', 'interpretations', 'weights', 'alternatives', 'risk_discussion', 'unresolved', 'submitted_constraints'],
            'field_contract': {
                'source_id': 'String or null; no source-answer const or enum.',
                'interpretations': 'Array of objects with sector_code, rating, evidence_ids and reason. rating stays a free string; no sector-specific gold label is encoded.',
                'weights': 'Array of objects with sector_code, numeric weight, rationale and evidence_ids. No numeric target, benchmark-following value or signed tilt is encoded.',
                'sector_code': 'The same common 11-code GICS enumeration already disclosed in the task; this is the public output universe, not an answer key.',
                'evidence_ids': 'String array without a sector-specific correct-ID whitelist.',
                'text_fields': 'Free strings, with no invented maxLength or hidden preferred argument.',
                'submitted_constraints': 'Preserve the existing visible-input constraint interface; never insert a constraint or bound absent from the source.'
            },
            'array_count_policy': 'Where the existing stage contract requires a full allocation, minItems=maxItems=11 may constrain row count. Early-stage empty allocations remain allowed. Eleven rows do not establish eleven distinct codes; retain the existing missing/duplicate checks.',
            'prohibited_schema_answer_injection': ['Per-sector rating const/enum', 'Institution source_id answer const/enum',
                'Target weights, weight-ordering inequalities or forced benchmark allocation', 'Correct evidence ID per sector',
                'A required financial conclusion or fabricated institution constraint'],
            'schema_unsupported_or_unverified_features_not_used': ['prefixItems', 'ordered tuple schema', 'uniqueItems', 'contains',
                'number minimum/maximum as an assumed grammar guarantee'],
            'evaluation': 'Preserve the existing fixed 11-sector mechanical evaluation and its registered missing-response handling. Separately report completed versus incomplete responses, semantic evaluability, exact raw sums, validity and source evidence. No new composite strategy score or unique numeric gold.',
            'interpretation': 'This is a prospective repair of the output interface after an observed pilot failure. A successful rerun would establish feasibility for this revised case, not identify grammar versus schema-visibility effects, prove general capability, or erase the prior failure.'
        },
        'falsifiable_checks_before_claiming_success': [
            'Pin full schema JSON and the deterministic prompt transformation before generation.',
            'Compare immutable source/market and original string values with v4.4; disclose the two intentional schema-related changes.',
            'Save actual HTTP request/stream, renderer evidence, stop reason, token counters, time and cleanup status for each stage.',
            'Validate returned raw JSON against the declared structural contract without repair; also retain independent existing code/weight/evidence checks.',
            'Report partial output and failed attempts; schema validity alone is not four-stage completion or semantic correctness.',
            'Perform the three independent postrun checks requested by the user; keep main unfrozen until substantive remaining limitations are addressed.'
        ],
        'limits': [
            'The API schema is an engineering implementation supported by official code; it is not reported as an Ollama setting in FinVector.',
            'The 11 rows follow the LIBERA task universe, not a paper-derived optimal sample size or allocation rule.',
            'Grammar constraints change available next tokens and may change content or speed. Repeated schema visibility also adds input tokens; neither benefit nor four-stage capacity is guaranteed.',
            'Free text can still repeat irrelevant input or make unsupported claims. Number syntax does not enforce a sum of one or justify a strategy.',
            'A single development case, especially reused after failure, cannot estimate generalization, R1/R4 effects or comparative model superiority.'
        ],
        'model_calls_by_evidence_author': 0,
        'main_frozen': False,
    }
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    text = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>v4.5 출력 계약 수정 근거</title>
<style>body{font:16px/1.75 system-ui;max-width:900px;margin:42px auto;padding:0 22px;color:#19293c}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}code{overflow-wrap:anywhere}</style><main>
<h1>v4.5: 출력 구조를 명확히 하는 수정</h1>
<p>기존 실패 원본을 보존하고, 모델·디코딩·시장·기관 문서는 유지합니다. 바꾸는 것은 <b>API에 실제 JSON Schema를 전달하는 것</b>과 <b>각 단계에 같은 출력 스키마를 명시하는 것</b>입니다. 두 변경을 함께 적용하므로 각각의 효과를 따로 측정했다고 주장하지 않습니다.</p>
<table><tr><th>근거</th><th>확인한 범위</th></tr>
<tr><td><a href="https://arxiv.org/pdf/2610.08882">FinVector §4.1·§10</a></td><td>스키마를 프롬프트에 명시한 금융 과제 선례. Ollama 문법 강제를 사용했다는 보고는 없고 원 평가 프롬프트는 비공개입니다.</td></tr>
<tr><td><a href="https://docs.ollama.com/capabilities/structured-outputs">Ollama 공식 문서</a></td><td>format=json과 실제 스키마 객체 전달을 구분하며, 스키마를 프롬프트에도 제시하도록 권고합니다.</td></tr>
<tr><td><a href="https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llm/llama_server.go">v0.35.1 구현</a></td><td>기본 JSON 모드는 임의 키를 허용하지만, 스키마는 필요한 필드와 자료형을 제한합니다.</td></tr></table>
<p>산업 코드 11개와 기존 필드는 구조로 지정할 수 있습니다. 그러나 산업별 등급, 출처 정답, 비중, 올바른 근거 ID를 미리 넣지 않습니다. 특히 11개 행을 만들게 해도 산업 코드 중복·누락, 비중 합계, 이유의 타당성은 별도 검증해야 합니다.</p>
<p>고정된 llama.cpp b11232 문서와 구현 사이에 tuple 지원 설명 차이가 있어 이번에는 해당 기능을 사용하지 않습니다. 단순 배열·필드 구조만 사용하고, 수치 범위·합계·중복 검사는 유지합니다. 실행 성공과 전략 타당성은 별개이며, 새 조건에서의 완료 여부는 아직 검증되지 않았습니다.</p>
<p><a href="v45_revision_reference_20261018.json">전체 근거·원문 SHA·변경 범위와 한계</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(text, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': sha(OUT),
                      'sources': len(evidence['primary_sources']), 'model_calls': 0}))


if __name__ == '__main__':
    main()
