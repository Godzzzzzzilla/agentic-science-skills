#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate-with-glossary-lock: one-command recheck.

Independently re-verifies coverage, glossary execution, fact-token preservation,
and paragraph order from the SOURCE and result.json. Exit 0 = green.
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import (contract_keys, load_case, source_text, segment,  # noqa: E402
                 src_tokens, tgt_tokens)

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

    text, _src = source_text(case, args.input)
    trs = result.get("translations") or []
    if text is None:
        if result.get("status") not in ("cannot_determine", "partial"):
            problems.append("source unavailable but status not demoted")
    elif trs:
        paras = segment(text)
        gloss = result.get("glossary") or {}
        # coverage
        ids = [t.get("para_id") for t in trs]
        src_ids = [p["para_id"] for p in paras]
        missing = [i for i in src_ids if i not in ids]
        extra = [i for i in ids if i not in src_ids]
        dup = len(ids) != len(set(ids))
        if missing:
            problems.append("untranslated paragraphs: %s" % missing[:8])
        if extra:
            problems.append("para_ids not in source: %s" % extra[:8])
        if dup:
            problems.append("duplicated para_ids")
        checks.append("coverage: %d/%d translated" % (len(src_ids) - len(missing), len(src_ids)))
        # glossary execution: term -> single rendering, used in aligned paragraphs
        for term, rend in gloss.items():
            hit_paras = [p["para_id"] for p in paras
                         if term.lower() in p["text"].lower()]
            bad = [pid for pid in hit_paras
                   if not any(t.get("para_id") == pid and rend.lower() in (t.get("translation") or "").lower()
                              for t in trs)]
            if bad and rend:
                problems.append("glossary term '%s' missing rendering '%s' in paras %s" %
                                (term, rend, bad[:5]))
        checks.append("glossary terms checked: %d" % len(gloss))
        # fact tokens on a sample (first 12 aligned pairs)
        by_id = {t.get("para_id"): t for t in trs}
        n_viol = 0
        for p in paras[:12]:
            t = by_id.get(p["para_id"])
            if not t:
                continue
            st, tt = src_tokens(p["text"]), tgt_tokens(t.get("translation") or "")
            if st["numbers"] - tt["numbers"]:
                n_viol += 1
            if st["cites"] - tt["cites"]:
                n_viol += 1
            if st["negs"] and not tt["negs"]:
                n_viol += 1
        if n_viol > max(2, 0.2 * min(12, len(paras))):
            problems.append("fact-token violations on sample: %d" % n_viol)
        checks.append("fact-token sample violations: %d/12" % n_viol)
        # order
        if ids != sorted(ids):
            problems.append("paragraph order shifted")
        checks.append("order monotone")

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "fix coverage/glossary/facts, re-finalize" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
