import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url)), root=path.resolve(here,'../../..');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const ref=async p=>({path:path.relative(root,p).replaceAll('\\','/'),sha256:sha(await fs.readFile(p))});
const rp=path.join(here,'common_market_only__C__F0_review.json');
const review=JSON.parse(await fs.readFile(rp,'utf8'));
const bp=path.resolve(root,review.bundle_ref.path), bundle=JSON.parse(await fs.readFile(bp,'utf8')), out=JSON.parse(bundle.raw_final_or_draft_text);
const strings=[];
function walk(v,p=''){
 if(typeof v==='string'){strings.push({p,t:v});return;}
 if(Array.isArray(v)){v.forEach((x,i)=>walk(x,p+'/'+i));return;}
 if(v&&typeof v==='object')for(const [k,x]of Object.entries(v)){
  if(['sector_code','source_id','source_label','source_stance','evidence_ids','source_evidence_ids','decision_evidence_ids'].includes(k))continue;
  walk(x,p+'/'+k);
 }
}
walk(out);
const actual=[];
for(const {p,t}of strings)for(const m of t.matchAll(/[-+]?\d+(?:\.\d+)?/g))actual.push({output_pointer:p,literal:m[0],start:m.index,end:m.index+m[0].length});
const ordered=x=>x.map(z=>JSON.stringify({output_pointer:z.output_pointer,literal:z.literal,start:z.start,end:z.end})).sort();
const expected=review.coverage.numeric_token_coverage;
if(JSON.stringify(ordered(actual))!==JSON.stringify(ordered(expected)))throw Error('Exhaustive narrative numeric token inventory differs');
const checks=actual.map(t=>{const stored=expected.find(e=>e.output_pointer===t.output_pointer&&e.start===t.start&&e.end===t.end);return {output_pointer:t.output_pointer,literal:t.literal,start:t.start,end:t.end,covered_by_claim:stored.claim_ids.length>0,identifier_exclusion:stored.excluded_identifier};});
if(checks.some(x=>!x.covered_by_claim&&!x.identifier_exclusion))throw Error('Uncovered quantitative token');
const receipt={version:'last_final_exhaustive_narrative_number_recheck_1',status:'PASS',completed_at_utc:new Date().toISOString(),review_ref:await ref(rp),bundle_ref:await ref(bp),validator_ref:await ref(fileURLToPath(import.meta.url)),scope:'Independently walks every current raw-output narrative string, excluding metadata/citation IDs, and checks exact numeric occurrence positions against the reviewed inventory. Not an automatic prose entailment grade.',actual_numeric_tokens:actual.length,reviewed_inventory_tokens:expected.length,uncovered_tokens:0,checks,model_calls:0,service_calls:0,raw_modified:false};
const target=path.join(here,'common_market_only__C__F0_coverage_validation.json');
await fs.writeFile(target,JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({status:'PASS',tokens:actual.length,receipt_ref:await ref(target)}));
