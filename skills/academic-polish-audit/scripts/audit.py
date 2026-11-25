#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""academic-polish-audit: one-command recheck.

Re-runs the alignment + fact-token diff from the ORIGINAL case text and the polished
text stored in result.json, then verifies: contract coverage, case_id, ratio sanity
(null not 0), violation adjudication. Exit 0 = green.
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import (align_sentences, build_report, case_texts, contract_keys,  # noqa: E402
                 load_case, sent_split)

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
    checks.append("contract coverage")

    # recompute the report independently
    c_orig, c_pol = case_texts(case)
    orig = None
    w_orig = os.path.join(args.output, "work_original.txt")
    if os.path.exists(w_orig):
        with io.open(w_orig, "r", encoding="utf-8") as f:
            orig = f.read()
    orig = orig or (c_orig if isinstance(c_orig, str) else None)
    pol = result.get("polished_text")
    if orig is None:
        problems.append("original text unavailable for recheck")
    elif pol is None:
        if result.get("status") != "cannot_determine":
            problems.append("polished_text missing without cannot_determine status")
    else:
        recomputed = build_report(orig, pol)
        stored = result.get("change_summary") or {}
        if stored.get("pairs") not in (None, recomputed["pairs"]):
            problems.append("pair count drift: stored %s vs recomputed %s" %
                            (stored.get("pairs"), recomputed["pairs"]))
        nv = len(recomputed["fact_violations"])
        rejected = len([v for v in (result.get("audit") or {}).get("verdicts") or [] if v.get("accept") is False])
        if nv and not rejected and result.get("status") == "success":
            problems.append("status=success but %d unadjudicated fact violations" % nv)
        checks.append("recomputed: pairs=%d violations=%d rejected=%d" % (recomputed["pairs"], nv, rejected))

    for key in ("alignment_ratio", "fact_violation_ratio"):
        v = (result.get("change_summary") or {}).get(key)
        if v == 0 and (result.get("change_summary") or {}).get("pairs") == 0:
            problems.append("ratio %s is 0 with zero denominator (should be null)" % key)

    if result.get("status") not in ("success", "partial", "cannot_determine", "rejected"):
        problems.append("invalid status: %r" % result.get("status"))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems,
                      "recommand": "adjudicate violations via notes.json, re-finalize" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
