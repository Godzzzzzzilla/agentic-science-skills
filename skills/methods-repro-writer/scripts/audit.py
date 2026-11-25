#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""methods-repro-writer: one-command recheck (tolerant; demote-only)."""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import contract_keys, load_case, verify_tolerant  # noqa: E402

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

    params = result.get("params") or []
    no_source = [p.get("name") for p in params if not p.get("source")]
    if no_source:
        problems.append("params without source: %s" % no_source[:8])
    checks.append("params: %d (not_reported %d)" %
                  (len(params), sum(1 for p in params if p.get("source") == "not_reported")))
    steps = result.get("steps") or []
    nums = [s.get("n") for s in steps if isinstance(s.get("n"), int)]
    if nums and nums != list(range(1, len(nums) + 1)):
        problems.append("step numbering gaps: %s" % nums[:12])
    checks.append("steps: %d" % len(steps))
    # null values must be not_reported
    for p in params:
        if p.get("value") is None and p.get("source") not in (None, "not_reported"):
            problems.append("param %s: null value but source claims data" % p.get("name"))
    # conflicts preserved, not silently resolved
    checks.append("conflicts listed: %d" % len(result.get("conflicts") or []))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "add source fields / fix step numbers" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
