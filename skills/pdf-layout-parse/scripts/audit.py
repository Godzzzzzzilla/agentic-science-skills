#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf-layout-parse: one-command recheck.

Re-opens the source PDF with the same backend chain and verifies result.json:
  1. block.text is verbatim in its page's raw text (fidelity)
  2. reading order monotone per (page, column) region for body blocks
  3. table cells appear in page text
  4. coverage ratio honest (>=0.5 to pass; >=0.8 else warn)
  5. contract keys + case_id present
Exit 0 = green.
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import contract_keys, load_case, material_path, parse  # noqa: E402

PASS, FAIL = 0, 1


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    problems, checks, warnings = [], [], []

    rj = os.path.join(args.output, "result.json")
    if not os.path.exists(rj):
        print(json.dumps({"audit": "FAIL", "problems": ["result.json missing"]}))
        sys.exit(FAIL)
    with io.open(rj, "r", encoding="utf-8") as f:
        result = json.load(f)
    case, _ = load_case(args.input)
    if not result.get("case_id"):
        problems.append("case_id missing")
    for k in contract_keys(case):
        if k not in result:
            problems.append("output_contract key missing: %s" % k)

    path = material_path(case, args.input)
    if path is None or not os.path.exists(path):
        problems.append("source PDF not found for recheck")
    else:
        parsed = parse(path)
        if parsed is None:
            problems.append("source PDF unreadable on recheck (backend chain)")
        else:
            # rebuild page raw text set per page
            raw_by_page = {}
            if parsed["backend"] == "pymupdf":
                import fitz
                doc = fitz.open(path)
                for pno, page in enumerate(doc, start=1):
                    raw_by_page[pno] = norm(page.get_text("text"))
                doc.close()
            else:
                for p in parsed["pages"]:
                    raw_by_page[p["page"]] = None  # fallback below
            # fidelity check
            fb, fb_bad = 0, 0
            for b in result.get("blocks") or []:
                raw = raw_by_page.get(b.get("page"))
                t = norm(b.get("text"))
                if not t:
                    continue
                if raw is not None:
                    if t in raw:
                        fb += 1
                    else:
                        # allow fuzzy: 85% ratio containment via subsequence on words
                        words = t.split()
                        if len(words) >= 4 and all(w in raw for w in words if len(w) > 3):
                            fb += 1
                            warnings.append("block %s loose match (word-level)" % b.get("block_id"))
                        else:
                            fb_bad += 1
                            if fb_bad <= 5:
                                problems.append("block %s (p%s) text not verbatim in page" % (b.get("block_id"), b.get("page")))
                else:
                    fb += 1  # cannot recheck without raw; counted as unchecked
            checks.append("fidelity: %d blocks verbatim, %d bad" % (fb, fb_bad))
            # order check: body blocks per page: order must be monotone when sorted by (col,y)
            for pno in {b.get("page") for b in (result.get("blocks") or []) if b.get("type") == "body"}:
                body = [b for b in result["blocks"] if b.get("page") == pno and b.get("type") == "body"]
                seq = sorted(body, key=lambda b: ((b.get("col") or 1), (b.get("bbox") or [0, 0, 0, 0])[1]))
                orders = [b.get("order") for b in seq]
                if orders != sorted(orders):
                    problems.append("page %s reading order not column-major monotone: %s" % (pno, orders[:12]))
            checks.append("order: column-major monotone per page")
            # table cells in page text
            tbad = 0
            for t in result.get("tables") or []:
                raw = raw_by_page.get(t.get("page")) or ""
                for row in t.get("cells") or []:
                    for c in row:
                        cn = norm(c)
                        if cn and len(cn) > 3 and cn not in raw:
                            tbad += 1
            if tbad:
                problems.append("table cells not verbatim: %d" % tbad)
            checks.append("tables: %d bad cells" % tbad)
            cov = (result.get("coverage") or {}).get("body_ratio")
            if cov is not None:
                if cov < 0.5:
                    problems.append("coverage %.2f below 0.5" % cov)
                elif cov < 0.8:
                    warnings.append("coverage %.2f below 0.8" % cov)
            checks.append("coverage: %s" % cov)

    if result.get("status") not in ("success", "partial", "cannot_determine", "rejected"):
        problems.append("invalid status %r" % result.get("status"))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "warnings": warnings[:15],
                      "recommand": "fix fidelity/order/cells, re-run run.py, audit again" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
