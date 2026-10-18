"""Versioned, offline label clarification; preserve v1 HTML/receipt bytes."""
import json
from datetime import datetime, timezone

import render_v48_source_comparison as base


def main():
    old_receipt = base.read(base.RECEIPT)
    old_html = base.OUT.read_text(encoding="utf-8")
    old_references = [base.ref(base.OUT), base.ref(base.RECEIPT), base.ref(base.__file__)]
    assert old_references[0] == old_receipt["html"]
    assert old_references[2] == old_receipt["renderer"]
    for item in old_receipt["inputs"]:
        assert base.ref(base.ROOT / item["path"]) == item
    assert base.ref(base.EXCERPTS) == old_receipt["excerpts"]
    comparison = base.read(base.SOURCE)
    packets = {}
    for group in comparison["splits"].values():
        for item in group["inputs"]:
            packet = base.read(base.ROOT / item["path"])
            packets[packet["source_id"]] = packet
    rendered = base.render(comparison, packets, base.read(base.EXCERPTS)["sources"])
    assert rendered + "\n" == old_html
    before, after = "<dt>문서 수집 기준일</dt>", "<dt>자료 포함 기준일(회고적)</dt>"
    assert rendered.count(before) == 4
    rendered = rendered.replace(before, after)
    inventory = base.Inventory(); inventory.feed(rendered)
    checks = {
        "four_date_labels_clarified": rendered.count(after) == 4 and before not in rendered,
        "same_22_rows_44_sources": len(inventory.rows) == 22 and len(inventory.sources) == 44,
        "same_44_local_original_row_images": len(inventory.images) == 44 and all((base.OUT.parent / p).is_file() for p in inventory.images),
        "all_human_rows_unreviewed": all(r["data-review-state"] == "unreviewed" for r in inventory.rows),
        "no_script_or_auto_verdict": inventory.scripts == 0 and "PASS" not in rendered,
        "escaped_text_still_safe": base.text('<script>"&') == '&lt;script&gt;&quot;&amp;',
        "only_declared_label_changed": rendered.replace(after, before) + "\n" == old_html,
    }
    assert all(checks.values())
    output = base.OUT.with_name("v48_source_comparison_20261018_v2.html")
    receipt_path = base.RECEIPT.with_name("v48_source_comparison_render_receipt_20261018_v2.json")
    if output.exists() or receipt_path.exists(): raise FileExistsError("Version 2 outputs already exist")
    with output.open("x", encoding="utf-8") as f: f.write(rendered + "\n")
    checks["v1_html_receipt_and_renderer_preserved"] = old_references == [base.ref(base.OUT), base.ref(base.RECEIPT), base.ref(base.__file__)]
    assert checks["v1_html_receipt_and_renderer_preserved"]
    receipt = {"status": "RENDERED_UNREVIEWED", "version": 2, "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "renderer": base.ref(__file__), "html": base.ref(output), "prior_version_references": old_references,
               "change": "Date label changed from document collection cutoff to retrospective material-inclusion cutoff. No new collection-date claim.",
               "checks": checks, "check_count": len(checks), "human_review_completed": False,
               "automatic_substantive_verdict": None, "model_calls": 0, "network_calls": 0,
               "frozen_inputs_modified": False, "latest_html": str(output.relative_to(base.ROOT)).replace("\\", "/"),
               "prior_evidence": "Retains the source extraction, source-row images, self-tests and AI visual spot checks recorded by the preserved v1 receipt."}
    with receipt_path.open("x", encoding="utf-8") as f: json.dump(receipt, f, ensure_ascii=False, indent=2); f.write("\n")
    print(json.dumps({"html": receipt["html"], "receipt": base.ref(receipt_path), "checks": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
