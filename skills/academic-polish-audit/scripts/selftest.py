#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for academic-polish-audit: synthetic draft, honest edit, fact-drift probe.

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

CASE = {
    "case_id": "selftest-polish-001",
    "task": "Polish the draft for grammar and register; do not alter facts.",
    "text": ("The result of the experiments are shown in Figure 2. "
             "The samples which was treated with 5 mM NaCl did not showed any peak at 25 °C. "
             "This suggest that the treatment may reduce the solubility, as reported by "
             "(Smith et al., 2020). Approximately 30% of the protein was denatured [3]. "
             "Due to the fact that the buffer was old, we repeated the assay."),
    "output_contract": {
        "polished_text": "the polished draft",
        "changes": "per-change table",
        "status": "success|partial",
    },
}

HONEST_POLISH = ("The results of the experiments are shown in Figure 2. "
                 "The samples treated with 5 mM NaCl did not show any peak at 25 °C. "
                 "This suggests that the treatment may reduce the solubility, as reported by "
                 "(Smith et al., 2020). Approximately 30% of the protein was denatured [3]. "
                 "Because the buffer was old, we repeated the assay.")

DRIFT_POLISH = ("The results of the experiments are shown in Figure 2. "
                "The samples treated with 5 mM NaCl showed any peak at 25 °C. "
                "This proves that the treatment reduces the solubility, as reported by "
                "(Smith et al., 2020). 30% of the protein was denatured [3]. "
                "Because the buffer was old, we repeated the assay.")


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1500:], r.stderr[-1500:])
        sys.exit(1)
    return r.stdout


def scenario(tmp, name, polished):
    inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output-" + name)]
    for d in (inp, work, out):
        os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE, f, ensure_ascii=False)
    with io.open(os.path.join(work, "original.txt"), "w", encoding="utf-8") as f:
        f.write(CASE["text"])
    with io.open(os.path.join(work, "polished.txt"), "w", encoding="utf-8") as f:
        f.write(polished)
    runpy = os.path.join(HERE, "run.py")
    audit = os.path.join(HERE, "audit.py")
    r1 = json.loads(run([runpy, "--mode", "audit", "--input", inp, "--output", out,
                         "--work", work]))
    assert r1["pairs"] >= 5, r1
    r2 = json.loads(run([runpy, "--mode", "finalize", "--input", inp, "--output", out,
                         "--work", work]))
    with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
        res = json.load(f)
    for k in CASE["output_contract"]:
        assert k in res, "missing contract key %s" % k
    assert res["case_id"] == CASE["case_id"]
    r3 = json.loads(run([audit, "--input", inp, "--output", out]))
    return r1, r2, res, r3


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-polish-")
    try:
        # 1. honest polish: violations may be 0..n, audit must PASS
        r1, r2, res, r3 = scenario(tmp, "honest", HONEST_POLISH)
        assert r3["audit"] == "PASS", r3
        assert res["change_summary"]["changed_pairs"] >= 4, res["change_summary"]
        # 2. drift polish: violations detected; engine must demote status to partial (honest)
        d1, d2, dres, d3 = scenario(tmp, "drift", DRIFT_POLISH)
        n_viol = len(dres["audit"]["violations"])
        assert n_viol >= 3, "expected >=3 fact violations in drift scenario, got %d" % n_viol
        assert dres["status"] == "partial", "drift must demote status, got %s" % dres["status"]
        # adjudicate: reject all flagged pairs -> status partial->success path via verdicts
        inp, work = os.path.join(tmp, "input"), os.path.join(tmp, "work")
        out = os.path.join(tmp, "output-drift")
        verdicts = [{"pair": v["orig_index"], "accept": False, "reason": "fact drift: revert"}
                    for v in dres["audit"]["violations"]]
        with io.open(os.path.join(work, "notes.json"), "w", encoding="utf-8") as f:
            json.dump({"verdicts": verdicts}, f)
        runpy = os.path.join(HERE, "run.py")
        audit = os.path.join(HERE, "audit.py")
        json.loads(run([runpy, "--mode", "finalize", "--input", inp, "--output", out,
                        "--work", work, "--notes", os.path.join(work, "notes.json")]))
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            fixed = json.load(f)
        # reverted text must contain the original negation again
        assert "did not show" in (fixed.get("polished_text") or ""), "verdict revert failed"
        r4 = json.loads(run([audit, "--input", inp, "--output", out]))
        # after revert, remaining violations should be resolved; PASS expected
        assert r4["audit"] == "PASS", r4
        print(json.dumps({"selftest": "PASS", "honest_pairs": r1["pairs"],
                          "drift_violations": n_viol,
                          "after_verdict_audit": r4["audit"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
