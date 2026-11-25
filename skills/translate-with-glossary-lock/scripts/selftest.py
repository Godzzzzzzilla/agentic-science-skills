#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for translate-with-glossary-lock: segments a synthetic paper,
fakes a faithful translation pass, verifies; then a drift pass must fail checks.

python3 scripts/selftest.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

PAPER = """Graph neural networks for molecular property prediction

Abstract

Graph neural networks (GNNs) predict molecular properties from structure alone.
We benchmark 7 GNN architectures on 2 datasets and report mean absolute error.

1. Introduction

Molecular property prediction is a central task in drug discovery [1].
Traditional fingerprints lose geometric information. GNNs may preserve it.
Prior work by (Smith et al., 2020) suggests fingerprints remain competitive.

2. Results

The best model reaches 0.42 kcal/mol MAE at 25 °C on dataset A.
Fingerprints do not reach this accuracy, as shown in Figure 2.
Approximately 30% of the improvement comes from edge features.
"""

CASE = {
    "case_id": "selftest-trans-001",
    "task": "Translate the paper to Chinese with a locked glossary.",
    "text": PAPER,
    "output_contract": {
        "translations": "paragraph translations with anchors",
        "glossary": "locked term pairs",
        "status": "success|partial",
    },
}


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1500:], r.stderr[-1500:])
        sys.exit(1)
    return r.stdout


def fake_translation(work, drift=False):
    with io.open(os.path.join(work, "segments.json"), "r", encoding="utf-8") as f:
        segs = json.load(f)
    paras = segs["paras"]
    glossary = {"Graph neural networks": "图神经网络", "fingerprints": "指纹"}
    out = []
    for p in paras:
        t = p["text"]
        if drift:
            # drop numbers, drop negation, upgrade hedge
            tr = t.replace("0.42", "0.4").replace("30%", "约三分之一")
            tr = tr.replace("do not reach", "reach").replace("suggests", "证明")
            tr = tr.replace("[1]", "").replace("(Smith et al., 2020)", "")
            tr = "翻译：" + tr  # pretend translation
        else:
            tr = "【译】" + t  # faithful (keeps all tokens verbatim)
            tr = tr.replace("Graph neural networks", "图神经网络")
            tr = tr.replace("fingerprints", "指纹").replace("Fingerprints", "指纹")
        out.append({"para_id": p["para_id"], "translation": tr,
                    "uncertain": False, "note": None})
    with io.open(os.path.join(work, "translation.json"), "w", encoding="utf-8") as f:
        json.dump({"glossary": glossary, "paragraphs": out}, f, ensure_ascii=False, indent=1)


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-trans-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "segment", "--input", inp, "--output", out,
                             "--work", work]))
        assert r1["paras"] >= 5, r1
        assert r1["term_candidates"] >= 1, r1
        # faithful pass
        fake_translation(work, drift=False)
        r2 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out,
                             "--work", work]))
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        assert res["case_id"] == CASE["case_id"]
        assert res["verification"]["coverage"]["missing"] == []
        for k in CASE["output_contract"]:
            assert k in res, "contract key missing %s" % k
        # glossary execution check: term occurrences must carry the locked rendering
        # ("Graph neural networks" -> "图神经网络" not present in fake faithful pass,
        #  so verify must flag it; engine demotes status)
        n_gv = len(res["verification"]["glossary_violations"])
        if n_gv:
            assert res["status"] == "partial", "glossary violations must demote status"
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        # drift pass: numbers/negation/citations dropped -> fact violations
        work2 = os.path.join(tmp, "work2")
        os.makedirs(work2)
        shutil.copy(os.path.join(work, "segments.json"), os.path.join(work2, "segments.json"))
        fake_translation(work2, drift=True)
        out2 = os.path.join(tmp, "output2")
        os.makedirs(out2)
        r4 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out2,
                             "--work", work2,
                             "--translation", os.path.join(work2, "translation.json")]))
        with io.open(os.path.join(out2, "result.json"), "r", encoding="utf-8") as f:
            dres = json.load(f)
        n_fv = len(dres["verification"]["fact_violations"])
        assert n_fv >= 3, "drift must produce >=3 fact violations, got %d" % n_fv
        assert dres["status"] == "partial", dres["status"]
        print(json.dumps({"selftest": "PASS", "paras": r1["paras"],
                          "faithful_status": res["status"], "gloss_violations": n_gv,
                          "drift_fact_violations": n_fv, "drift_status": dres["status"]},
                         ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
