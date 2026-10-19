"""Three ordered checks of blank human materials; never substitutes for humans."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "research/v491_human_review_pack_20261019"
OUT = ROOT / "research/artifacts/v491_runtimeprep_20261019"
SECTORS = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", required=True, type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(name, condition, evidence):
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    manifest = read(PREFIX + "_manifest.json")
    packs = [read(PREFIX + "_" + slot + ".json") for slot in ["R1", "R2"]]
    gate = read(PREFIX + "_gate_blank.json")
    if args.round > 1:
        prev = read(f"research/artifacts/v491_runtimeprep_20261019/human_pack_round{args.round - 1}.json")
        check("previous_round_passed", prev["status"] == "PASS", prev["status"])
        for item in prev["artifact_refs"]:
            check("previous_round_bytes_unchanged:" + item["path"], sha(item["path"]) == item["sha256"], item)
    if args.round == 1:
        for item in manifest["output_refs"] + manifest["prior_input_refs"] + [manifest["generator_ref"]]:
            check("exact_file_hash:" + item["path"], sha(item["path"]) == item["sha256"], item)
        old = read("research/v491_human_review_template_20261019.json")
        for pack in packs:
            slot = pack["reviewer_slot"]
            check(slot + ":source_count", len(pack["source_documents"]) == 4, len(pack["source_documents"]))
            for source in pack["source_documents"]:
                sid = source["source_id"]
                orig = read(f"data/sector_documents/packets/{source['split']}/{sid}.json")
                check(slot + ":packet_verbatim:" + sid, source["packet"] == orig, "All packet fields, date warnings and original-label paraphrases unchanged")
                check(slot + ":11_unique_prespecified_sectors:" + sid, [r["sector_code"] for r in source["sector_review_rows"]] == SECTORS, SECTORS)
                for row in source["sector_review_rows"]:
                    check(slot + ":passage_exact:" + sid + ":" + row["sector_code"], row["passages"] == [p for p in orig["evidence_passages"] if p["evidence_id"].endswith(":sector:" + row["sector_code"])], row["passages"][0]["evidence_id"])
            for split in ["pilot", "main"]:
                rows = copy.deepcopy(pack["source_comparison"][split]["rows"])
                for row in rows:
                    row.pop("answer_prefix")
                check(slot + ":comparison_verbatim:" + split, rows == old["source_comparison"][split]["rows"], "All 11 comparisons remain exactly blank original rows")
            context = read("data/sector_context/v491_20261019/common_context.json")
            candidate = read("data/sector_protocol/v491_design_20261019/public_compact_candidate.json")
            check(slot + ":context_exact", pack["common_context"] == context, "Common task and macro facts unchanged")
            check(slot + ":market_exact", all(pack[k] == candidate[k] for k in ["common_market", "public_numeric_fact_index"]), "Market values and numeric provenance unchanged")
            soup = BeautifulSoup((ROOT / (PREFIX + "_" + slot + ".html")).read_text(encoding="utf-8"), "html.parser")
            check(slot + ":html_row_counts", len(soup.select('.source-row')) == 44 and len(soup.select('.comparison-row')) == 22, [len(soup.select('.source-row')), len(soup.select('.comparison-row'))])
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('../'):
                    check(slot + ":local_link:" + href, (ROOT / "research" / href).resolve().exists(), href)
                elif href.startswith('#'):
                    check(slot + ":fragment:" + href, soup.find(id=href[1:]) is not None, href)
    if args.round == 2:
        r1, r2 = copy.deepcopy(packs)
        r1.pop('reviewer_slot'); r2.pop('reviewer_slot')
        check('identical_evidence_and_blank_form_between_reviewers', r1 == r2, "Only reviewer_slot differs; neither sees the other's answers")
        for pack in packs:
            slot = pack['reviewer_slot']
            keys = [f['key'] for f in pack['form_fields']]
            check(slot + ':unique_keys', len(keys) == len(set(keys)) == 228, len(keys))
            check(slot + ':all_answers_blank', all(v is None for v in pack['answers'].values()) and set(keys) == set(pack['answers']), '228 null fields')
            check(slot + ':no_completion_fabricated', pack['human_review_completed'] is False and pack['model_outputs_included'] is False, pack['status'])
            check(slot + ':pilot_scope_129_fields', len([k for k in keys if k.startswith(('meta.','common.','macro.','source.pilot.','comparison.pilot.'))]) == 129, 'main 99 fields remain optional until main gate')
            soup = BeautifulSoup((ROOT / (PREFIX + '_' + slot + '.html')).read_text(encoding='utf-8'), 'html.parser')
            controls = soup.select('[data-key]')
            check(slot + ':all_controls_blank', all((n.name == 'textarea' and not n.text) or (n.name == 'select' and n.find('option').get('value') == '' and not n.select('[selected]')) for n in controls), len(controls))
            check(slot + ':control_mapping', [n['data-key'] for n in controls] == keys, 'DOM control order matches form schema exactly')
            check(slot + ':no_remote_code_or_network_send', not soup.select('script[src], iframe, form[action]') and all(t not in soup.find_all('script')[-1].text for t in ['fetch(', 'XMLHttpRequest', 'sendBeacon', 'localStorage']), 'Local download/import only; source URLs open only on human click')
            runtime = soup.find_all('script')[-1].text
            metadata = soup.find('script', id='pack-data').text
            harness = '''const vm=require('vm'),assert=require('assert');
const data=META;
const controls=data.fields.map(f=>({dataset:{key:f.key},value:'',tagName:f.kind==='select'?'SELECT':'TEXTAREA',addEventListener(){}}));
const elements={'pack-data':{textContent:JSON.stringify(data)},progress:{textContent:''},export:{addEventListener(){}},import:{addEventListener(){}}};
const context={document:{getElementById:id=>elements[id],querySelectorAll:()=>controls},URL:{},Blob,Date,Map,JSON,Array,Object,Error,setTimeout};vm.createContext(context);
vm.runInContext(SCRIPT,context);
let out=vm.runInContext('exportPayload()',context);assert.strictEqual(out.human_review_completed,false);assert.strictEqual(Object.keys(out.answers).length,228);assert(Object.values(out.answers).every(v=>v===null));
controls.find(x=>x.dataset.key==='meta.reviewer_name').value='SYNTHETIC_TEST_ONLY';
controls.find(x=>x.dataset.key==='meta.independent_work').value='true';
controls.find(x=>x.dataset.key==='meta.review_scope').value='"pilot"';
out=vm.runInContext('exportPayload()',context);assert.strictEqual(out.answers['meta.independent_work'],true);assert.strictEqual(out.answers['meta.review_scope'],'pilot');
context.saved=JSON.parse(JSON.stringify(out));controls.forEach(x=>x.value='');vm.runInContext('applyAnswers(saved)',context);assert.strictEqual(controls.find(x=>x.dataset.key==='meta.reviewer_name').value,'SYNTHETIC_TEST_ONLY');
let failures=0;
for(const mutate of [x=>x.reviewer_slot='WRONG',x=>x.blank_form_ref.sha256='WRONG',x=>x.answers['meta.independent_work']='yes',x=>delete x.answers['meta.reviewer_name'],x=>x.answers.extra='bad']){context.bad=JSON.parse(JSON.stringify(out));mutate(context.bad);try{vm.runInContext('applyAnswers(bad)',context)}catch(e){failures++}}
assert.strictEqual(failures,5);console.log(JSON.stringify({blank_export:true,boolean_roundtrip:true,text_roundtrip:true,pilot_scope_roundtrip:true,negative_import_cases:failures,synthetic_only_no_saved_answers:true}));
'''.replace('META', metadata).replace('SCRIPT', json.dumps(runtime))
            js_path = OUT / ('human_pack_js_check_' + slot + '.js')
            js_path.write_text(harness, encoding='utf-8', newline='\n')
            proc = subprocess.run(['node', str(js_path)], capture_output=True, text=True, encoding='utf-8', check=False)
            check(slot + ':javascript_export_import_and_rejection', proc.returncode == 0, {'stdout':proc.stdout.strip(),'stderr':proc.stderr.strip()})
        check('receipt_still_unapproved', gate['status'] == 'pending_human_completion' and all(x['gate_approved_by_human'] is None for x in gate['splits'].values()), 'No synthetic test filled or saved a human submission')
    if args.round == 3:
        config = read('plan/LIBERA_실험설정_v4.9.1_20261019.json')
        protocol = read('research/v491_evaluation_protocol_20261019.json')
        pack = packs[0]
        check('rubric_matches_current_frozen_candidate', pack['evaluation_protocol'] == protocol, 'No score, threshold, gold weights or new semantic labels introduced')
        check('all11_pre_output_contrasts_per_split', all([r['sector_code'] for r in pack['source_comparison'][split]['rows']] == config['sectors'] for split in ['pilot','main']), 'Avoid choosing source differences after seeing output')
        check('source_roles_and_scope_match', {s:sorted(x['source_id'] for x in pack['source_documents'] if x['split'] == s) for s in ['pilot','main']} == {s:sorted(config['sources'][s]) for s in ['pilot','main']}, config['sources'])
        check('comparison_categories_preserved', all(row['comparison_allowed'] == gate['completed_receipt_contract']['comparison_decisions_allowed'] for obj in pack['source_comparison'].values() for row in obj['rows']), 'Supports difference, similarity, noncomparability, insufficient evidence, uncertainty')
        check('no_forced_success_requirement', gate['completed_receipt_contract']['approval_does_not_require'] == ['substantive_difference_supported in any row','unanimity','a numeric target allocation','successful model outputs'], 'Human gate does not select E wins, diversity, or successful model outputs')
        check('pre_output_pilot_and_main_gate_explicit', 'pilot as well as main' in pack['completion_policy']['pilot_gate'], pack['completion_policy']['pilot_gate'])
        check('human_not_AI_and_not_samples', 'Two distinct human readers' in pack['completion_policy']['reviewers'] and 'not extra statistical samples' in pack['completion_policy']['reviewers'], pack['completion_policy']['reviewers'])
        check('independent_originals_and_reconciliation', 'retains submitted originals and hashes' in pack['completion_policy']['independence'] and 'Do not force agreement' in pack['completion_policy']['uncertainty'], 'Preserve originals, disagreements, unresolved findings; do not coerce agreement')
        check('new_version_after_material_change', 'new version' in pack['completion_policy']['reconciliation'], pack['completion_policy']['reconciliation'])
        check('topic_evidence_to_decision_not_similarity', 'supported interpretations and allocation reasons' in pack['completion_policy']['topic_connection'] and 'harmful homogenization' in pack['completion_policy']['topic_connection'], pack['completion_policy']['topic_connection'])
        check('machine_limit_explicit', 'not certify' in gate['coordinator']['authenticity_note'], gate['coordinator']['authenticity_note'])
        check('pilot_can_proceed_without_main_answers', 'Main-only fields may remain null before pilot' in gate['completion_rules'][1], {'pilot_fields':129,'later_main_fields':99})
        check('current_readiness_not_overclaimed', manifest['human_review_completed'] is False and manifest['model_calls'] == 0 and gate['status'] == 'pending_human_completion', 'These are blank handoff materials; no human source judgment or research outcome has been invented')
    artifacts = manifest['output_refs'] + [{'path':PREFIX + '_manifest.json','sha256':sha(PREFIX + '_manifest.json')},manifest['generator_ref']]
    receipt = {'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','round':args.round,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'scope':{1:'Provenance, exact source/context preservation and HTML navigation',2:'Blank independence, split scope and executed JS export/import adversarial checks',3:'Research topic, inference limits, pre-output human gate and outcome-blindness'}[args.round],'check_count':len(checks),'checks':checks,'artifact_refs':artifacts,'human_review_completed':False,'main_or_pilot_model_calls':0,'limits':['These automated preparation checks do not complete independent human review.','No claims about browser visual layout, review quality, or human authenticity follow from these checks.']}
    target = OUT / f'human_pack_round{args.round}.json'
    target.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':receipt['status'],'checks':len(checks),'failed':[c['name'] for c in checks if not c['pass']],'receipt':str(target.relative_to(ROOT))}))
    raise SystemExit(0 if receipt['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
