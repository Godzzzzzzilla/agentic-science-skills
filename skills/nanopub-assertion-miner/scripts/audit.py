#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nanopub-assertion-miner: one-command recheck (schema + quote backtracking)."""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import (contract_keys, load_case, norm_text, collect_material,  # noqa: E402
                 verify)

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

    paras, src = collect_material(case, args.input)
    assertions = result.get("assertions") or []
    if paras and assertions:
        v = verify(assertions, paras)
        if v["schema_missing"]:
            problems.append("schema incomplete on %d assertions" % len(v["schema_missing"]))
        if v["quote_mismatch"]:
            problems.append("evidence quotes not verbatim: %d" % len(v["quote_mismatch"]))
        checks.append("assertions: %d, evidence_ok %d" %
                      (v["stats"]["assertions"], v["stats"]["evidence_ok"]))
        checks.append("atomicity hints: %d" % len(v["atomicity_hints"]))
    elif result.get("status") == "success":
        problems.append("success but no assertions to recheck")

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "fix schema/quotes, re-finalize" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
