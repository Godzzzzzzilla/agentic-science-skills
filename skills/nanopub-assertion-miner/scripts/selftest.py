#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for nanopub-assertion-miner: JATS + JSON materials; grounded assertions
pass; quote drift + compound object produce problems. python3 scripts/selftest.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

JATS = """<article>
<front><article-title>Drug X reduces tumor growth</article-title></front>
<body>
<p id="p1">Drug X reduced tumor volume by 40% (p&lt;0.01) in male mice at 25 °C.</p>
<p id="p2">Survival improved from 12 to 19 weeks median. Drug X and Drug Y were compared.</p>
<p id="p3">Prior work (Lee et al., 2021) reported no effect in female mice.</p>
</body>
</article>"""

CASE = {
    "case_id": "selftest-nanopub-001",
    "task": "Decompose the conclusions into atomic assertions with bound evidence.",
    "material": {"text": JATS},
    "output_contract": {
        "assertions": {"subject": "s", "predicate": "p", "object": "o",
                        "evidence": {"para_id": "id", "quote": "verbatim"}},
        "provenance": "source metadata",
        "status": "success|partial",
    },
}

GOOD = {
    "assertions": [
        {"subject": "Drug X", "predicate": "reduces", "object": "tumor volume by 40%",
         "qualifier": "male mice, 25 °C, p<0.01",
         "evidence": {"para_id": "p1", "quote": "Drug X reduced tumor volume by 40%"},
         "inference": False, "conflicts": None},
        {"subject": "Drug X", "predicate": "improves", "object": "median survival from 12 to 19 weeks",
         "qualifier": None,
         "evidence": {"para_id": "p2", "quote": "Survival improved from 12 to 19 weeks median"},
         "inference": False, "conflicts": None},
        {"subject": "Lee et al. 2021", "predicate": "reports", "object": "no effect of Drug X in female mice",
         "qualifier": "female mice",
         "evidence": {"para_id": "p3", "quote": "reported no effect in female mice"},
         "inference": False, "conflicts": None},
    ],
    "provenance": {"title": "Drug X reduces tumor growth", "authors": None,
                   "year": None, "version": None},
    "uncertainty": [],
}

BAD = {
    "assertions": [
        {"subject": "Drug X", "predicate": "reduces", "object": "tumors and improves survival",
         "evidence": {"para_id": "p1", "quote": "Drug X reduced tumor volume by half"}},  # drifted quote
        {"subject": "Drug X", "predicate": "improves",
         "evidence": {"para_id": "p9", "quote": "Survival improved"}},  # unknown para
    ],
    "provenance": {},
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
    tmp = tempfile.mkdtemp(prefix="selftest-nanopub-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "collect", "--input", inp, "--output", out,
                             "--work", work]))
        assert r1["paras"] == 3, r1
        with io.open(os.path.join(work, "assertions.json"), "w", encoding="utf-8") as f:
            json.dump(GOOD, f, ensure_ascii=False, indent=1)
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
        # bad: drifted quote + unknown para id
        out2, work2 = os.path.join(tmp, "output2"), os.path.join(tmp, "work2")
        os.makedirs(out2), os.makedirs(work2)
        shutil.copy(os.path.join(work, "material.json"), os.path.join(work2, "material.json"))
        with io.open(os.path.join(work2, "assertions.json"), "w", encoding="utf-8") as f:
            json.dump(BAD, f, ensure_ascii=False, indent=1)
        r4 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out2,
                             "--work", work2,
                             "--assertions", os.path.join(work2, "assertions.json")]))
        assert r4["status"] == "partial", r4
        assert len(r4["problems"]) >= 1
        print(json.dumps({"selftest": "PASS", "paras": r1["paras"],
                          "good_assertions": r2["assertions"], "good_status": r2["status"],
                          "bad_status": r4["status"], "bad_problems": r4["problems"]},
                         ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
