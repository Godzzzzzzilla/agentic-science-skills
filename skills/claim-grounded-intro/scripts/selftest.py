#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for claim-grounded-intro: grounded citations pass; fabricated citation
and paraphrased quote fail. python3 scripts/selftest.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

WORK_A = {"key": "smith2020", "title": "Fingerprint baselines for property prediction",
          "authors": "J. Smith, L. Wu", "year": 2020,
          "text": "We evaluate fingerprint baselines on six molecular datasets. "
                  "Fingerprints remain competitive with early graph models, though "
                  "they lose geometric information in conformer-sensitive tasks."}
WORK_B = {"key": "lee2022", "title": "Graph networks under distribution shift",
          "authors": "H. Lee, P. Ortiz", "year": 2022,
          "text": "We study graph neural networks under distribution shift and find "
                  "that performance degrades sharply when scaffold split is used, "
                  "and no baseline in our study covers conformer ensembles."}
WORK_C = {"key": "patel2021", "title": "Conformer-aware message passing",
          "authors": "R. Patel", "year": 2021,
          "text": "Our conformer-aware message passing improves MAE on rigid molecules "
                  "but fails to generalize to flexible macrocycles."}

CASE = {
    "case_id": "selftest-intro-001",
    "task": "Write an introduction and related-work section grounded in the supplied works.",
    "works": [WORK_A, WORK_B, WORK_C],
    "output_contract": {
        "intro_text": "introduction text",
        "related_work_text": "related work text",
        "citations": "citation records",
        "gaps": "gap statements with support",
        "status": "success|partial",
    },
}

GOOD_DRAFT = {
    "intro_text": ("Molecular property prediction must trade off structural summaries "
                   "against geometric fidelity. Fingerprint baselines remain competitive "
                   "with early graph models [1], yet they lose geometric information "
                   "exactly where conformer-sensitive tasks need it [1]."),
    "related_work_text": ("Fingerprint baselines [1] evaluate six datasets and stay "
                          "competitive. Graph networks under distribution shift [2] "
                          "degrade sharply on scaffold splits. Conformer-aware message "
                          "passing [3] improves MAE on rigid molecules but does not "
                          "generalize to flexible macrocycles."),
    "citations": [
        {"marker": "[1]", "work_key": "smith2020",
         "quote": "Fingerprints remain competitive with early graph models, though they lose geometric information"},
        {"marker": "[2]", "work_key": "lee2022",
         "quote": "performance degrades sharply when scaffold split is used"},
        {"marker": "[3]", "work_key": "patel2021",
         "quote": "fails to generalize to flexible macrocycles"},
    ],
    "gaps": [
        {"statement": "No supplied work evaluates conformer-aware methods under scaffold-shifted, flexible-molecule regimes together.",
         "type": "derived",
         "support": [{"work_key": "lee2022", "quote": "no baseline in our study covers conformer ensembles"},
                     {"work_key": "patel2021", "quote": "fails to generalize to flexible macrocycles"}]}
    ],
    "contributions": [
        {"text": "We combine conformer-aware message passing with scaffold-stratified evaluation.",
         "evidence": "addresses the combined gap derived from [2][3]"}
    ],
    "uncertainty": [],
}

BAD_DRAFT = {
    "intro_text": "Prior work [9] proves everything works.",
    "related_work_text": "All methods are perfect.",
    "citations": [
        {"marker": "[9]", "work_key": "nonexistent2023", "quote": "we prove the universal property"},
        {"marker": "[1]", "work_key": "smith2020", "quote": "fingerprints are useless and always wrong"},
    ],
    "gaps": [{"statement": "Nobody has ever studied anything.", "type": "derived", "support": []}],
    "contributions": [],
    "uncertainty": [],
}


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1500:], r.stderr[-1500:])
        sys.exit(1)
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-intro-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        run([runpy, "--stage", "collect", "--input", inp, "--output", out, "--work", work])
        # good draft
        with io.open(os.path.join(work, "draft.json"), "w", encoding="utf-8") as f:
            json.dump(GOOD_DRAFT, f, ensure_ascii=False, indent=1)
        r2 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out,
                             "--work", work]))
        assert r2["status"] == "success", r2
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        for k in CASE["output_contract"]:
            assert k in res, k
        assert res["case_id"] == CASE["case_id"]
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        assert r3["audit"] == "PASS", r3
        # bad draft: fabricated work + paraphrased quote + unsupported gap
        out2 = os.path.join(tmp, "output2")
        os.makedirs(out2)
        with io.open(os.path.join(work, "draft.json"), "w", encoding="utf-8") as f:
            json.dump(BAD_DRAFT, f, ensure_ascii=False, indent=1)
        r4 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out2,
                             "--work", work]))
        assert r4["status"] == "partial", r4
        assert r4["citations"] >= 2, "violations must be counted"
        print(json.dumps({"selftest": "PASS", "good_status": r2["status"],
                          "bad_violations": r4["citations"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
