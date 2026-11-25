#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation-align-manager: one-command recheck.

Checks (from /app/output/result.json alone + case):
  1. numbering sequential from 1, no gaps
  2. every numeric citation in updated_text resolves to a list entry
  3. no duplicate pairs remain under the merge rules
  4. every output entry's metadata fields appear verbatim in the original list
  5. unresolved citations listed, not hidden
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
from run import (NUM_CITE_RE, authors_key, contract_keys, duplicate_groups,  # noqa: E402
                 norm_key, load_case, parse_references, split_reference_block, get_texts)

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

    refs = result.get("updated_references") or []
    text = result.get("updated_text")

    # 1. sequential numbering
    nums = [r.get("number") for r in refs]
    if nums and nums != list(range(1, len(refs) + 1)):
        problems.append("numbering not sequential: %s" % nums[:20])
    checks.append("numbering: %s" % ("sequential" if nums == list(range(1, len(refs) + 1)) else "BROKEN"))

    # 2. every numeric citation resolves OR is recorded as unresolved (never silently dropped)
    if text:
        cited = set()
        for m in NUM_CITE_RE.finditer(text):
            for n in re.findall(r"\d+", m.group(1)):
                cited.add(int(n))
        have = set(nums)
        recorded = set()
        for u in result.get("unresolved_citations") or []:
            for n in re.findall(r"\d+", str(u.get("raw", ""))):
                recorded.add(int(n))
        missing = cited - have - recorded
        if missing:
            problems.append("citations without entries and not recorded: %s" % sorted(missing)[:10])
        checks.append("resolution: %d/%d cited numbers resolve (%d recorded unresolved)" %
                      (len(cited & have), len(cited), len(recorded)))
    else:
        if result.get("status") not in ("cannot_determine", "partial"):
            problems.append("updated_text missing without partial/cannot_determine status")

    # 3. no duplicates remain (rebuild entries from verbatim + fields)
    entries = []
    for r in refs:
        e = {"verbatim": r.get("verbatim", ""), "authors": (r.get("fields") or {}).get("authors", ""),
             "title": (r.get("fields") or {}).get("title", ""), "year": (r.get("fields") or {}).get("year", ""),
             "doi": (r.get("fields") or {}).get("doi", "")}
        e["author_key"] = authors_key(e["authors"])
        e["title_key"] = norm_key(e["title"])
        entries.append(e)
    dup = duplicate_groups(entries)
    hard = [g for g in dup if g["type"] == "duplicate"]
    if hard:
        problems.append("duplicates remain: %s" % [g["indices"] for g in hard][:5])
    checks.append("duplicates remaining: %d (candidates %d)" % (len(hard), len(dup) - len(hard)))

    # 4. metadata verbatim vs original reference list
    text_case, refs_field = get_texts(case)
    orig_block = refs_field
    if orig_block is None and text_case:
        _, orig_block = split_reference_block(text_case)
    orig_entries = parse_references(orig_block) if orig_block else []
    orig_bodies = "\n".join(e["verbatim"] for e in orig_entries)
    meta_bad = 0
    for r in refs:
        for k, v in (r.get("fields") or {}).items():
            if v and str(v) not in orig_bodies:
                meta_bad += 1
                problems.append("entry %s field %s not verbatim in original list" % (r.get("number"), k))
    checks.append("metadata verbatim: %d violations" % meta_bad)

    # 5. unresolved listed
    unres = result.get("unresolved_citations") or []
    checks.append("unresolved citations: %d (listed)" % len(unres))

    if result.get("status") not in ("success", "partial", "cannot_determine", "rejected"):
        problems.append("invalid status %r" % result.get("status"))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:20],
                      "recommand": "fix numbering/dedup/metadata, re-finalize" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
