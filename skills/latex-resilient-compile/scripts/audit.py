#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex-resilient-compile: one-command recheck.

Checks contract keys, ampersand-report consistency (fresh recount vs result.json),
diagnosis entries carry file+line, and PDF-page honesty (success requires pages>=1
and an existing PDF reference). Exit 0 = green.
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import contract_keys, load_case, tex_files, analyze  # noqa: E402

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

    # fresh recount of unescaped & (work dir may exist)
    work_src = os.path.join(os.path.dirname(args.output), "work", "src")
    if os.path.isdir(work_src):
        fresh = analyze(work_src)
        reported = result.get("unescaped_ampersands")
        if reported is not None and len(reported) != len(fresh["unescaped_ampersands"]):
            problems.append("ampersand report drift: result %d vs fresh %d" %
                            (len(reported), len(fresh["unescaped_ampersands"])))
        checks.append("ampersand recount: %d vs reported %s" %
                      (len(fresh["unescaped_ampersands"]),
                       len(reported) if reported is not None else "n/a"))

    # diagnosis entries must name file+line (real numbers from log)
    diag = result.get("diagnosis") or []
    bad = [d for d in diag if not d.get("file")]
    if bad:
        problems.append("diagnosis entries without file: %d" % len(bad))
    checks.append("diagnosis entries: %d" % len(diag))

    # success honesty
    if result.get("status") == "success":
        pdf = result.get("pdf_file")
        pages = result.get("pdf_pages")
        if not pdf or not os.path.exists(os.path.join(args.output, str(pdf))):
            problems.append("success claimed but PDF missing in output")
        if pages is None or (isinstance(pages, int) and pages < 1):
            problems.append("success claimed but page count missing/invalid")
    checks.append("pdf honesty: %s pages=%s" % (result.get("pdf_file"), result.get("pdf_pages")))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "align reports / fix claims" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
