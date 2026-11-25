#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""two-paper-kg-builder: one-command recheck (provenance, integrity, merges, queries)."""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import contract_keys, load_case, load_corpus, verify_graph, read_json  # noqa: E402

PASS, FAIL = 0, 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
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

    corpus = load_corpus(case, args.input)
    graph = {"nodes": result.get("nodes") or [], "edges": result.get("edges") or [],
             "kept_separate": result.get("kept_separate") or [],
             "merge_rationales": []}
    v = verify_graph(graph, corpus)
    if v["provenance_bad"]:
        problems.append("provenance failures: %d" % len(v["provenance_bad"]))
    if v["integrity_bad"]:
        problems.append("integrity failures: %d" % len(v["integrity_bad"]))
    checks.append("nodes %d, edges %d, kept_separate %d" %
                  (v["stats"]["nodes"], v["stats"]["edges"], v["stats"]["kept_separate"]))
    q = result.get("queries") or {}
    nq = q.get("queries_executed") or 0
    if nq < 3:
        problems.append("queries executed: %d (<3)" % nq)
    checks.append("queries executed: %d" % nq)
    # query results reference existing nodes
    node_ids = {n.get("node_id") for n in (result.get("nodes") or [])}
    edge_ids = {e.get("edge_id") for e in (result.get("edges") or [])}
    for r in (q.get("results") or []):
        for hit in r.get("results") or []:
            ref = hit.get("node_id")
            if ref and ref not in node_ids and ref not in edge_ids:
                problems.append("query %s references unknown item %s" % (r.get("q_id"), ref))
    # kept_separate must have reasons
    for ks in result.get("kept_separate") or []:
        if not ks.get("reason"):
            problems.append("kept_separate without reason: %s" % ks.get("entities"))

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems[:15],
                      "recommand": "fix provenance/integrity/queries" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
