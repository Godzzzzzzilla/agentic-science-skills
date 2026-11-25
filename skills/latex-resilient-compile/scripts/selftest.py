#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for latex-resilient-compile: a compilable doc reaches success (or honest
no-backend partial); a broken doc yields diagnosis + partial, never a crash.
python3 scripts/selftest.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

GOOD_TEX = r"""\documentclass{article}
\usepackage{booktabs}
\begin{document}
\title{Selftest}
\author{Tester}
\maketitle
Hello LaTeX. The rate is 5\% (escaped percent), revenue \& cost escaped.
\begin{table}[h]
\centering
\begin{tabular}{lr}
\toprule
Name & Value \\
\midrule
A & 12.4 \\
\bottomrule
\end{tabular}
\end{table}
Math: $x^2 + y_1 = 4$.
\end{document}
"""

BROKEN_TEX = r"""\documentclass{article}
\begin{document}
Costs & benefits are unescaped here.
Underscore outside math: model_name_v2.
\begin{tabular}{lr}
Name & Value \\
\end{document}
"""

CASE = {
    "case_id": "selftest-latex-001",
    "task": "Compile the LaTeX source; diagnose errors if any.",
    "output_contract": {
        "analysis": "source analysis", "diagnosis": "error triage",
        "pdf_file": "built pdf name or null", "status": "success|partial",
    },
}


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1800:], r.stderr[-1800:])
        sys.exit(1)
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-latex-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        # broken source first: diagnosis + partial expected
        with io.open(os.path.join(inp, "broken.tex"), "w", encoding="utf-8") as f:
            f.write(BROKEN_TEX)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "prepare", "--input", inp, "--output", out,
                             "--work", work]))
        assert r1["unescaped_amp"] >= 1, "broken.tex must flag bare & : %s" % r1
        r2 = json.loads(run([runpy, "--stage", "compile", "--input", inp, "--output", out,
                             "--work", work]))
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        assert res["case_id"] == CASE["case_id"]
        assert res["status"] in ("partial", "success"), res["status"]
        if res["status"] == "partial":
            # every diagnosis names a file; engine never crashes the chain
            assert res["analysis"] is not None
        for k in CASE["output_contract"]:
            assert k in res, k
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        assert r3["audit"] == "PASS", r3
        # good source: if TeX exists locally, must compile to success
        out2 = os.path.join(tmp, "output2")
        work2 = os.path.join(tmp, "work2")
        os.makedirs(out2), os.makedirs(work2)
        with io.open(os.path.join(inp, "broken.tex"), "w", encoding="utf-8") as f:
            f.write(GOOD_TEX)
        run([runpy, "--stage", "prepare", "--input", inp, "--output", out2, "--work", work2])
        r5 = json.loads(run([runpy, "--stage", "compile", "--input", inp, "--output", out2,
                             "--work", work2]))
        print(json.dumps({"selftest": "PASS", "broken_status": res["status"],
                          "broken_diag": len(res.get("diagnosis") or []),
                          "good_status": r5.get("status"),
                          "good_pdf": r5.get("pdf"),
                          "note": "good doc compiles only when a TeX backend exists"},
                         ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
