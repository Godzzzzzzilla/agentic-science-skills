#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest: runs the full pipeline on a bundled synthetic case (no PDF needed).

  python3 scripts/selftest.py [--keep]

Creates a temp dir with case.json + paper.txt, runs extract -> fake-notes -> finalize
-> audit, and asserts the audit exits 0. Exit 0 = pipeline healthy.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

PAPER = """Deep learning for rainfall nowcasting: a benchmark study

Abstract

We benchmark eleven deep learning models for rainfall nowcasting on a new
dataset of 20,000 radar sequences. U-Net variants achieve the best skill
scores at lead times under 90 minutes.

1. Introduction

Rainfall nowcasting remains a hard problem. Traditional optical-flow
methods degrade quickly at lead times beyond 60 minutes. Deep learning
approaches have shown promise but lack a fair comparison.

2. Data and methods

2.1 Dataset

The dataset contains 20,000 radar sequences collected between 2019 and
2021 over northern Europe. Each sequence has 12 frames at 5-minute
intervals. We split sequences 70/15/15 into train, validation and test.

2.2 Models

We compare eleven models including ConvLSTM, U-Net, and a transformer
variant. All models are trained for 50 epochs with early stopping.

3. Results

U-Net variants achieve the best skill scores at lead times under 90
minutes. Performance degrades for all models beyond 120 minutes.
The transformer variant is slower to train by a factor of 3.4.

4. Discussion

Our benchmark has limitations: only northern European weather is
covered, and we did not evaluate ensemble methods.

References

[1] Shi et al. 2015. Convolutional LSTM network. NeurIPS.
"""

CASE = {
    "case_id": "selftest-case-001",
    "task": "Produce structured reading notes for the paper: one card per section "
            "with six fields; every field supported by verbatim quotes.",
    "materials": ["paper.txt"],
    "output_contract": {
        "cards": "per-section note cards",
        "notes": "evidence notes with anchors",
        "status": "success | partial | cannot_determine",
    },
}


def fake_agent_notes(work):
    """Simulates the agent's semantic pass by taking real verbatim slices."""
    with io.open(os.path.join(work, "segments.json"), "r", encoding="utf-8") as f:
        segs = json.load(f)
    paras = segs["paragraphs"]

    def pick(substr):
        for p in paras:
            if substr in p["text"]:
                q = p["text"]
                i = q.find(substr)
                return {"note_id": None, "para_index": p["para_index"], "page": p["page"],
                        "quote": q[max(0, i): i + 200]}
        return None

    n1 = pick("rainfall nowcasting on a new")
    n2 = pick("20,000 radar sequences collected")
    n3 = pick("U-Net variants achieve the best")
    n4 = pick("only northern European weather")
    notes = []
    nid = 0
    for n in (n1, n2, n3, n4):
        if n:
            nid += 1
            n["note_id"] = nid
            notes.append(n)
    cards = [
        {
            "section": "Abstract", "page": 1,
            "research_question": {"text": "Fair benchmark of deep learning models for rainfall nowcasting.",
                                  "note_ids": [1]},
            "data": {"text": "New dataset of 20,000 radar sequences.", "note_ids": [1]},
            "method_conditions": {"text": "Eleven deep learning models compared.", "note_ids": [1]},
            "main_findings": {"text": "U-Net variants achieve the best skill scores at lead times under 90 minutes.",
                              "note_ids": [3]},
            "limitations": {"text": "not_reported", "note_ids": []},
            "assumptions": {"text": "not_reported", "note_ids": []},
        },
        {
            "section": "Data and methods", "page": 1,
            "research_question": {"text": "not_reported", "note_ids": []},
            "data": {"text": "20,000 radar sequences, 2019-2021, northern Europe; 12 frames at 5-minute intervals; 70/15/15 split.",
                     "note_ids": [2]},
            "method_conditions": {"text": "All models trained 50 epochs with early stopping.", "note_ids": [2]},
            "main_findings": {"text": "not_reported", "note_ids": []},
            "limitations": {"text": "not_reported", "note_ids": []},
            "assumptions": {"text": "not_reported", "note_ids": []},
        },
        {
            "section": "Discussion", "page": 1,
            "limitations": {"text": "Only northern European weather covered; ensemble methods not evaluated.",
                            "note_ids": [4]},
            "research_question": {"text": "not_reported", "note_ids": []},
            "data": {"text": "not_reported", "note_ids": []},
            "method_conditions": {"text": "not_reported", "note_ids": []},
            "main_findings": {"text": "not_reported", "note_ids": []},
            "assumptions": {"text": "not_reported", "note_ids": []},
        },
    ]
    with io.open(os.path.join(work, "notes.json"), "w", encoding="utf-8") as f:
        json.dump({"cards": cards, "notes": notes}, f, ensure_ascii=False, indent=1)


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("CMD FAILED:", " ".join(cmd))
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        sys.exit(1)
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-notes-")
    try:
        inp = os.path.join(tmp, "input")
        work = os.path.join(tmp, "work")
        out = os.path.join(tmp, "output")
        os.makedirs(inp), os.makedirs(work), os.makedirs(out)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        with io.open(os.path.join(inp, "paper.txt"), "w", encoding="utf-8") as f:
            f.write(PAPER)
        runpy = os.path.join(HERE, "run.py")
        audit = os.path.join(HERE, "audit.py")
        r1 = run([runpy, "--stage", "extract", "--input", inp, "--output", out, "--work", work])
        d1 = json.loads(r1)
        assert d1["paragraphs"] >= 8, "expected >=8 paragraphs, got %s" % d1["paragraphs"]
        assert d1["sections"] >= 4, "expected >=4 sections, got %s" % d1["sections"]
        fake_agent_notes(work)
        r2 = run([runpy, "--stage", "finalize", "--input", inp, "--output", out, "--work", work,
                  "--notes", os.path.join(work, "notes.json")])
        d2 = json.loads(r2)
        assert d2["status"] in ("success", "partial"), d2
        assert d2["cards"] == 3, d2
        # contract keys filled
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        for k in CASE["output_contract"]:
            assert k in res, "contract key %s missing" % k
        assert res["case_id"] == "selftest-case-001"
        # audit must pass
        r3 = run([audit, "--input", inp, "--output", out, "--work", work])
        d3 = json.loads(r3)
        assert d3["audit"] == "PASS", d3
        # robustness: missing case.json -> still result.json
        r4 = run([runpy, "--stage", "extract", "--input", os.path.join(tmp, "nothing"), "--output", out, "--work", work])
        assert os.path.exists(os.path.join(out, "result.json"))
        print(json.dumps({"selftest": "PASS", "paragraphs": d1["paragraphs"],
                          "sections": d1["sections"], "cards": d2["cards"],
                          "audit": d3["audit"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
