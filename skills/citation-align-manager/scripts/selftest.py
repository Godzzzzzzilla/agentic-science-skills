#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for citation-align-manager: renumber + dedup + unresolved + verbatim metadata."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

MANUSCRIPT = """Deep models for weather prediction

Neural precipitation nowcasting has improved rapidly [3]. Earlier optical-flow
methods degrade beyond 60 minutes [1]. U-Net architectures set the current
benchmark [2, 3]. A recent survey covers both families [3].

Some claims rest on preprints [4] and on work we could not locate [9].

References

[1] M. A. Rico, Optical flow methods for nowcasting, Journal of Weather Forecasting, 2018, 12(3): 211-229.
[2] J. van der Berg, U-Net for radar prediction, IEEE Transactions on Geoscience, 2021, 39(2): 88-102. doi:10.1109/tgs.2021.001
[3] L. Chen-Wang, S. Ito and T. Park, Deep learning for precipitation nowcasting, Nature Machine Intelligence, 2022, 4(7): 601-615. doi:10.1038/nmi.2022.050
[4] L. ChenWang, S. Ito and T. Park, Deep learning for precipitation nowcasting, Nature Machine Intelligence, 2022, 4(7): 601-615. doi:10.1038/nmi.2022.050
[5] K. Osei, Ensemble methods in forecasting, arXiv preprint, 2020, arXiv:2001.01234.
"""

CASE = {
    "case_id": "selftest-cite-001",
    "task": "Align citations with the reference list, merge duplicates, renumber by first occurrence.",
    "text": MANUSCRIPT,
    "output_contract": {
        "updated_text": "renumbered manuscript",
        "updated_references": "deduped renumbered list",
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


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-cite-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "align", "--input", inp, "--output", out, "--work", work]))
        assert r1["entries"] == 5, r1
        assert r1["citations"] >= 7, r1
        assert r1["unresolved"] >= 1, "citation [9] must be unresolved, got %s" % r1
        assert r1["duplicate_groups"] >= 1, "entries 3/4 are duplicates (same DOI + author-year), got %s" % r1
        r2 = json.loads(run([runpy, "--stage", "finalize", "--input", inp, "--output", out, "--work", work]))
        with io.open(os.path.join(out, "result.json"), "r", encoding="utf-8") as f:
            res = json.load(f)
        # [3] appears first -> becomes [1]; [1]->[2]; [2]->[3]; [5] uncited -> tail
        assert res["status"] == "partial", "unresolved [9] must demote status, got %s" % res["status"]
        assert "[1]" in res["updated_text"], "first-occurrence renumber failed"
        assert res["updated_text"].index("[1]") < res["updated_text"].index("[2]"), "order wrong"
        refs = res["updated_references"]
        assert len(refs) == 4, "5 entries - 1 duplicate = 4, got %d" % len(refs)
        assert any("van der Berg" in r["verbatim"] for r in refs), "particle surname lost"
        assert any("Chen-Wang" in r["verbatim"] or "ChenWang" in r["verbatim"] for r in refs)
        # metadata verbatim: no DOI appears that is absent from the original list
        assert res["metadata_verbatim_check"]["violations"] == []
        # unresolved recorded
        assert any(u["raw"].startswith("[9") for u in res["unresolved_citations"])
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        assert r3["audit"] == "PASS", r3
        print(json.dumps({"selftest": "PASS", "entries": r1["entries"],
                          "citations": r1["citations"], "unresolved": r1["unresolved"],
                          "dup_groups": r1["duplicate_groups"],
                          "final_refs": len(refs), "audit": r3["audit"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
