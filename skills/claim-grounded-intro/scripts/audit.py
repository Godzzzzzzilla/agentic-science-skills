#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim-grounded-intro: one-command recheck (citation existence, quotes, gaps)."""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import contract_keys, load_case, norm_text, read_json, verify, collect_works  # noqa: E402

PASS, FAIL = 0, 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    problems, checks = [], []

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
    if result.get("status") not in ("success", "partial", "cannot_determine", "rejected"):
        problems.append("invalid status %r" % result.get("status"))

    works = collect_works(case, args.input)
    # rebuild the draft view from result.json
    draft = {"citations": result.get("citations") or [],
             "gaps": result.get("gaps") or []}
    v = verify(draft, works)
    if v["citation_missing"]:
        problems.append("citations to missing works: %d" % len(v["citation_missing"]))
    if v["quote_mismatch"]:
        problems.append("quotes not verbatim in supplied works: %d" % len(v["quote_mismatch"]))
    checks.append("citations: %d checked, %d quote mismatches" %
                  (v["counts"]["citations"], len(v["quote_mismatch"])))
    aj = v["counts"]["author_judgment_gaps"]
    checks.append("gaps: %d (%d author_judgment)" % (v["counts"]["gaps"], aj))
    # derived gaps must have support recorded
    for g in result.get("gaps") or []:
        if g.get("type") == "derived" and not (g.get("support") or []):
            problems.append("derived gap without support: %s" % (g.get("statement") or "")[:60])
    if not (result.get("intro_text") or "").strip() and result.get("status") == "success":
        problems.append("success status but empty intro_text")

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "fix citations/quotes/gaps, re-finalize" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
