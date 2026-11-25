#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for two-paper-kg-builder: corpus load, provenance verification,
cross-paper merge rationale enforcement, >=3 queries. python3 scripts/selftest.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

MANIFEST = {
    "papers": [
        {"source_id": "primary", "doi": "10.1000/primary.001", "role": "primary",
         "file": "primary-material.json", "license": "CC-BY"},
        {"source_id": "secondary", "doi": "10.1000/secondary.002", "role": "secondary",
         "file": "secondary-material.json", "license": "CC-BY"},
    ]
}

PRIMARY = {"paragraphs": [
    {"id": "s1.1", "text": "We propose EdgeNet, a graph neural network for molecular property prediction."},
    {"id": "s2.1", "text": "EdgeNet achieves 0.42 kcal/mol MAE on the QM9 subset."},
    {"id": "s2.2", "text": "The model was trained at 25 °C with batch size 64."},
]}

SECONDARY = {"paragraphs": [
    {"id": "p1", "text": "EdgeNet was evaluated on free-solvation datasets with different hardware."},
    {"id": "p2", "text": "GNN baselines include ChemProp and D-MPNN."},
    {"id": "p3", "text": "Our EdgeNet run used batch size 128 on A100 GPUs."},
]}

CASE = {
    "case_id": "selftest-kg-001",
    "task": "Build a KG across the two papers with provenance and >=3 queries.",
    "output_contract": {
        "nodes": "graph nodes", "edges": "graph edges",
        "queries": "executed queries with results", "status": "success|partial",
    },
}

GRAPH = {
    "nodes": [
        {"node_id": "n1", "label": "EdgeNet", "type": "method", "source_id": "primary",
         "para_id": "s1.1", "quote": "We propose EdgeNet, a graph neural network",
         "aliases": ["EdgeNet"],
         "merge_rationale": {"with": "n4", "evidence": [
             {"source_id": "primary", "para_id": "s1.1", "quote": "We propose EdgeNet"},
             {"source_id": "secondary", "para_id": "p1", "quote": "EdgeNet was evaluated"}]}},
        {"node_id": "n2", "label": "QM9 subset", "type": "dataset", "source_id": "primary",
         "para_id": "s2.1", "quote": "0.42 kcal/mol MAE on the QM9 subset"},
        {"node_id": "n3", "label": "batch size 64", "type": "condition", "source_id": "primary",
         "para_id": "s2.2", "quote": "trained at 25 °C with batch size 64"},
        {"node_id": "n4", "label": "EdgeNet (secondary eval)", "type": "method",
         "source_id": "secondary", "para_id": "p1", "quote": "EdgeNet was evaluated on free-solvation datasets"},
        {"node_id": "n5", "label": "batch size 128", "type": "condition", "source_id": "secondary",
         "para_id": "p3", "quote": "used batch size 128 on A100 GPUs"},
        {"node_id": "n6", "label": "ChemProp", "type": "method", "source_id": "secondary",
         "para_id": "p2", "quote": "GNN baselines include ChemProp"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "type": "measures",
         "source_id": "primary", "para_id": "s2.1", "quote": "achieves 0.42 kcal/mol MAE"},
        {"edge_id": "e2", "from": "n6", "to": "n1", "type": "compares",
         "source_id": "secondary", "para_id": "p2", "quote": "GNN baselines include ChemProp"},
    ],
    "kept_separate": [
        {"entities": ["n3", "n5"],
         "reason": "batch size 64 (primary run) and 128 (secondary run) are different physical runs; merging would fabricate a shared condition"}
    ],
    "uncertainty": [],
}

QUERIES = {"queries": [
    {"q_id": "q1", "type": "by_label", "label": "EdgeNet", "note": "find all EdgeNet mentions"},
    {"q_id": "q2", "type": "edges_of", "node_id": "n1", "note": "edges of EdgeNet"},
    {"q_id": "q3", "type": "by_type", "node_type": "condition", "note": "run conditions"},
    {"q_id": "q4", "type": "cross_paper", "label": "edgenet", "note": "cross-paper alignment"},
]}


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1800:], r.stderr[-1800:])
        sys.exit(1)
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-kg-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        with io.open(os.path.join(inp, "corpus-manifest.json"), "w", encoding="utf-8") as f:
            json.dump(MANIFEST, f, ensure_ascii=False)
        with io.open(os.path.join(inp, "primary-material.json"), "w", encoding="utf-8") as f:
            json.dump(PRIMARY, f, ensure_ascii=False)
        with io.open(os.path.join(inp, "secondary-material.json"), "w", encoding="utf-8") as f:
            json.dump(SECONDARY, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "load", "--input", inp, "--output", out,
                             "--work", work]))
        by_sid = {p["sid"]: p["paras"] for p in r1["papers"]}
        assert by_sid["primary"] == 3 and by_sid["secondary"] == 3, r1
        with io.open(os.path.join(work, "graph.json"), "w", encoding="utf-8") as f:
            json.dump(GRAPH, f, ensure_ascii=False, indent=1)
        with io.open(os.path.join(work, "queries.json"), "w", encoding="utf-8") as f:
            json.dump(QUERIES, f, ensure_ascii=False, indent=1)
        run([runpy, "--stage", "queries", "--input", inp, "--output", out, "--work", work])
        r3 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out,
                             "--work", work]))
        assert r3["status"] == "success", r3
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        for k in CASE["output_contract"]:
            assert k in res, k
        assert res["case_id"] == CASE["case_id"]
        assert res["queries"]["queries_executed"] >= 3
        # q4 cross_paper must find EdgeNet on both sides
        q4 = [q for q in res["queries"]["results"] if q["q_id"] == "q4"][0]
        assert len(q4["results"]) >= 2, "cross-paper query should hit both papers"
        r4 = json.loads(run([audit, "--input", inp, "--output", out, "--work", work]))
        assert r4["audit"] == "PASS", r4
        # broken: quote drift
        bad = json.loads(json.dumps(GRAPH))
        bad["nodes"][0]["quote"] = "We propose GraphNet"
        work2, out2 = os.path.join(tmp, "work2"), os.path.join(tmp, "output2")
        os.makedirs(work2), os.makedirs(out2)
        shutil.copy(os.path.join(work, "corpus.json"), os.path.join(work2, "corpus.json"))
        with io.open(os.path.join(work2, "graph.json"), "w", encoding="utf-8") as f:
            json.dump(bad, f, ensure_ascii=False, indent=1)
        run([runpy, "--stage", "queries", "--input", inp, "--output", out2, "--work", work2])
        r5 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out2,
                             "--work", work2]))
        assert r5["status"] == "partial", r5
        print(json.dumps({"selftest": "PASS", "nodes": r3["nodes"], "edges": r3["edges"],
                          "queries": r3["queries"], "good_status": r3["status"],
                          "bad_status": r5["status"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
