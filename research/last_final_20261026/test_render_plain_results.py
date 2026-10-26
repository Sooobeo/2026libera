"""Synthetic adapter boundaries and exact displayed data; no actual output reads."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import re
import tempfile
import unittest
import render_plain_results as renderer


def fixture():
    c=renderer.core
    records=[]; vectors={}
    for case in c.CASES:
        for stage in ("D0","F0"):
            vector=dict(zip(c.CODES,[1000]*10+[0]))
            if case==c.CASES[-1] and stage=="F0":vector[c.CODES[0]]+=100;vector[c.CODES[1]]-=100
            vectors[(case,stage)]=vector
            records.append({"case_id":case,"stage":stage,"status":"finalized","version":"sector_allocation_finalizer_1",
                "policy":{"normalization":"positive_sum_proportional_scaling","rounding":"largest_remainder_to_10000_integer_units"},
                "raw_sum_exact_decimal":"1.02" if stage=="D0" else "0.95","final_total_units":10000,
                "rows":[{"sector_code":code,"final_units":n} for code,n in vector.items()]})
    groups={}
    for name,pairs in c.comparison_pairs().items():
        groups[name]=[]
        for left,right in pairs:
            l,r=vectors[tuple(left.rsplit(":",1))],vectors[tuple(right.rsplit(":",1))]
            delta={code:l[code]-r[code] for code in c.CODES}; tv=Fraction(sum(abs(n) for n in delta.values()),20000)
            groups[name].append({"left":left,"right":right,"status":"computed","final_unit_differences":delta,
                "total_variation_exact":{"numerator":str(tv.numerator),"denominator":str(tv.denominator)}})
    result={"version":"sector_last_final_finalizer_1","purpose":"primary_exploratory_last_final_dataset",
        "analysis_role":"primary_exploratory","case_order":list(c.CASES),"planned_final_allocations":5,
        "planned_final_sector_rows":55,"logical_stage_slots":10,"generation_calls":0,"service_calls":0,"main_model_calls":0,
        "primary_final_allocation_endpoint":"F0_derived_integer_allocation","raw_diagnostics_required":True,
        "last_final_generation_requests":1,"remaining_generation_requests":4,"completion_generation_requests":1,
        "prior_continuation_generation_requests":2,"original_generation_requests":3,"all_generation_requests_including_interrupted_attempt":11,
        "segment_planned_final_allocations":1,"segment_planned_stage_slots":1,"segment_case_order":[c.CASES[-1]],
        "segment_stage_order":[c.CASES[-1]+"__F0"],"stage_records":records,"derived_comparisons":groups,"finalized_finals":5}
    notes={"schema_version":"plain_results_notes_1","observations":[{"title":"<script>","text":"합성 & 검증"}],"caveats":[],"related_files":[]}
    return result,notes


class RendererTests(unittest.TestCase):
    def test_exact_units_totals_raw_and_tv_display(self):
        r,n=fixture();before=copy.deepcopy(r);html=renderer.render_html(r,n)
        cells=re.findall(r"data-case='([^']+)' data-units='([0-9]+)'",html)
        self.assertEqual(len(cells),55)
        for c in renderer.core.CASES:self.assertEqual(sum(int(v) for k,v in cells if k==c),10000)
        for text in ("102%","95%","100.00%","1.00%","11회 요청"):self.assertIn(text,html)
        self.assertEqual(r,before)

    def test_schema_and_cumulative_accounting_rejected(self):
        r,n=fixture()
        for key,value in (("version","sector_remaining_finalizer_1"),("all_generation_requests_including_interrupted_attempt",10),("last_final_generation_requests",True),("remaining_generation_requests",3),("segment_stage_order",["common_market_only__C__D0"])):
            with self.subTest(key=key),self.assertRaises(ValueError):renderer.render_html({**r,key:value},n)

    def test_no_normalization_or_forged_distance_by_renderer(self):
        r,n=fixture();r["stage_records"][-1]["rows"][0]["final_units"]+=1
        with self.assertRaises(ValueError):renderer.render_html(r,n)
        r,n=fixture();r["derived_comparisons"]["own_D0_F0"][-1]["total_variation_exact"]["numerator"]="5"
        with self.assertRaises(ValueError):renderer.render_html(r,n)

    def test_escaping_and_link_scheme_rejection(self):
        r,n=fixture();html=renderer.render_html(r,n)
        self.assertNotIn("<script>",html);self.assertIn("&lt;script&gt;",html);self.assertIn("합성 &amp; 검증",html)
        n["related_files"]=[{"label":"x","path":"javascript:alert(1)"}]
        with self.assertRaises(ValueError):renderer.render_html(r,n)

    def test_exclusive_cli_adapter_output_and_no_input_mutation(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-render-",dir=renderer.REPORT_ROOT) as folder:
            p=Path(folder);r,n=fixture();rp,np=p/"result.json",p/"notes.json"
            rp.write_text(json.dumps(r),encoding="utf-8");np.write_text(json.dumps(n),encoding="utf-8")
            before=(rp.read_bytes(),np.read_bytes());result=renderer.generate(rp,np,p/"out.html")
            self.assertEqual(result["source_result_version"],r["version"]);self.assertEqual(before,(rp.read_bytes(),np.read_bytes()))
            with self.assertRaises(FileExistsError):renderer.generate(rp,np,p/"out.html")
            with self.assertRaises(ValueError):renderer.generate(rp,np,renderer.ROOT/"research/remaining_20261026/never-written.html")


if __name__=="__main__":unittest.main(verbosity=2)
