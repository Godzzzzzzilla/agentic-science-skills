#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for pdf-layout-parse: builds a synthetic 2-column PDF (PyMuPDF),
runs the parser, checks structure + coverage, runs the audit.

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

try:
    import fitz  # noqa: F401
    HAVE_FITZ = True
except Exception:
    HAVE_FITZ = False

BODY_COL1 = [
    "We study the phase behavior of block",
    "copolymers under shear. The simulations",
    "use a coarse-grained model with 40,000",
    "beads and a shear rate of 0.01 tau^-1.",
    "The order parameter increases with",
]
# last line of col 1 ends mid-sentence -> continuation into col 2
BODY_COL2 = [
    "applied strain, consistent with",
    "prior work on lamellar systems [4].",
    "The viscosity drops by 30% above",
    "the order-disorder transition",
    "temperature of 412 K.",
]
HEADER = "J. Chem. Phys. 158, 034901 (2023)  Sheared block copolymers"
FOOTER = "This article is copyrighted as indicated in the article."
FOOTNOTE = "1 Electronic mail: author@university.edu"
TABLE_ROWS = ["T (K)   Viscosity (mPa s)   Order",
              "400     12.4                 0.11",
              "412     8.7                  0.34",
              "430     6.1                  0.02"]
FORMULA = "sigma = sigma_0 + alpha * gamma_dot^2 + O(gamma^3)"

CASE = {
    "case_id": "selftest-pdf-001",
    "task": "Parse the PDF: structure with reading order, tables, footnotes, formulas.",
    "materials": ["paper.pdf"],
    "output_contract": {
        "pages": "page metadata", "blocks": "structured blocks",
        "full_text": "ordered text", "status": "success|partial",
    },
}


def build_pdf(path):
    import fitz
    doc = fitz.open()
    # page 1: header, col1 body (mid-sentence ending), table, formula, col2 body, footnote, footer
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 36), HEADER, fontsize=8)
    y = 100
    for line in BODY_COL1:
        page.insert_text((72, y), line, fontsize=10)
        y += 14
    y += 10
    for row in TABLE_ROWS:
        page.insert_text((72, y), row, fontsize=10, fontname="cour")
        y += 14
    y += 8
    page.insert_text((72, y), FORMULA, fontsize=10, fontname="cour")
    y = 100
    for line in BODY_COL2:
        page.insert_text((320, y), line, fontsize=10)
        y += 14
    page.insert_text((72, 760), FOOTNOTE, fontsize=7)
    page.insert_text((72, 780), FOOTER, fontsize=7)
    # page 2: same header + footer (repeat => detectable), simple body
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 36), HEADER, fontsize=8)
    page2.insert_text((72, 100), "The conclusions summarize the shear-thinning behavior.",
                       fontsize=10)
    page2.insert_text((72, 780), FOOTER, fontsize=7)
    doc.save(path)
    doc.close()


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(1)
    return r.stdout


def main():
    if not HAVE_FITZ:
        print(json.dumps({"selftest": "SKIP", "reason": "PyMuPDF not installed"}))
        return
    tmp = tempfile.mkdtemp(prefix="selftest-pdf-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        pdf = os.path.join(inp, "paper.pdf")
        build_pdf(pdf)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--input", inp, "--output", out, "--work", work]))
        assert r1["pages"] == 2, r1
        assert r1["blocks"] >= 6, r1
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        types = [b["type"] for b in res["blocks"]]
        # header/footer separated
        assert "header" in types or "footer" in types, "header/footer not detected: %s" % types
        # cross-column continuation: col2 first line merged into col1 last paragraph
        merged = [b for b in res["blocks"] if b.get("merged_into") is not None]
        assert merged, "expected cross-column continuation merge, blocks: %s" % json.dumps(
            [{"t": b["text"][:40], "m": b.get("merged_into")} for b in res["blocks"]], ensure_ascii=False)
        # table captured
        assert res["tables"], "table not detected"
        cells = res["tables"][0]["cells"]
        assert len(cells) >= 2 and len(cells[0]) >= 2, cells
        assert any("12.4" in " ".join(r) for r in cells), "cell 12.4 missing"
        # fidelity: full text contains col1 start
        assert "phase behavior" in res["full_text"], res["full_text"][:200]
        # continuation appears after the col-1 text (reading order)
        ft = res["full_text"]
        assert ft.index("phase behavior") < ft.index("applied strain"), "column order wrong"
        for k in CASE["output_contract"]:
            assert k in res, "contract key %s missing" % k
        assert res["case_id"] == "selftest-pdf-001"
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        assert r3["audit"] == "PASS", r3
        print(json.dumps({"selftest": "PASS", "blocks": r1["blocks"],
                          "types": sorted(set(types)), "tables": len(res["tables"]),
                          "merged": len(merged), "audit": r3["audit"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
