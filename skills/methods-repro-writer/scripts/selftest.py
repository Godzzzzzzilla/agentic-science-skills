#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for methods-repro-writer: config+log collection, tolerant missing-seed
handling, conflict preservation. python3 scripts/selftest.py"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CASE = {
    "case_id": "selftest-methods-001",
    "task": "Write the methods section with a sourced parameter table.",
    "materials": ["train.yaml", "run.log"],
    "text": "We train a graph model on the benchmark. (draft fragment)",
    "output_contract": {
        "methods_text": "methods prose", "steps": "numbered steps",
        "params": "parameter table with sources", "status": "success|partial",
    },
}

TRAIN_YAML = """learning_rate: 3e-4
batch_size: 64
epochs: 50
optimizer: adamw
hidden_dim: 256
"""

RUN_LOG = """2026-03-01 INFO python 3.10.12 torch 2.1.0 cuda 12.1
2026-03-01 INFO batch_size: 128  # overridden on resume
2026-03-02 INFO training complete, best val mae 0.31
"""

GOOD_DRAFT = {
    "methods_text": "We train with AdamW (lr 3e-4 from train.yaml). Batch size is 64 "
                    "per train.yaml; run.log records 128 on resume — both listed.",
    "steps": [
        {"n": 1, "input": "raw dataset", "operation": "normalize features",
         "output": "normalized tensors", "condition": "drop NaN rows"},
        {"n": 2, "input": "tensors", "operation": "train AdamW",
         "output": "model checkpoint", "condition": "early stop on val mae"},
    ],
    "params": [
        {"name": "learning_rate", "value": "3e-4", "unit": None,
         "applies_to": "training", "source": "config:train.yaml"},
        {"name": "batch_size", "value": "64", "unit": None, "applies_to": "training",
         "source": "config:train.yaml"},
        {"name": "batch_size_resume", "value": "128", "unit": None,
         "applies_to": "training", "source": "log:run.log"},
        {"name": "random_seed", "value": None, "unit": None, "applies_to": "training",
         "source": "not_reported"},
    ],
    "setup": {"training": "single GPU, mixed precision", "validation": "val split, mae",
              "test": "held-out test split"},
    "repro": {"environment": "python 3.10.12, torch 2.1.0, cuda 12.1",
              "seed": None, "command": "python train.py --cfg train.yaml",
              "artifacts": ["checkpoint.pt", "metrics.json"]},
    "limitations": [
        {"text": "Random seed not recorded in any source; exact re-sampling cannot be guaranteed.",
         "trigger": "seed-sensitive splits"}
    ],
    "uncertainty": ["seed missing"],
}


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAILED:", " ".join(cmd))
        print(r.stdout[-1500:], r.stderr[-1500:])
        sys.exit(1)
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-methods-")
    try:
        inp, work, out = [os.path.join(tmp, x) for x in ("input", "work", "output")]
        for d in (inp, work, out):
            os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(inp, "case.json"), "w", encoding="utf-8") as f:
            json.dump(CASE, f, ensure_ascii=False)
        with io.open(os.path.join(inp, "train.yaml"), "w", encoding="utf-8") as f:
            f.write(TRAIN_YAML)
        with io.open(os.path.join(inp, "run.log"), "w", encoding="utf-8") as f:
            f.write(RUN_LOG)
        runpy, audit = os.path.join(HERE, "run.py"), os.path.join(HERE, "audit.py")
        r1 = json.loads(run([runpy, "--stage", "collect", "--input", inp, "--output", out,
                             "--work", work]))
        assert r1["params"] >= 8, r1
        assert r1["versions"] >= 3, r1
        assert r1["conflicts"] >= 1, "batch_size 64 vs 128 conflict must be detected"
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
        assert res["conflicts"], "conflicts preserved in result"
        # null seed must carry not_reported source
        seed = [p for p in res["params"] if p["name"] == "random_seed"][0]
        assert seed["value"] is None and seed["source"] == "not_reported"
        r3 = json.loads(run([audit, "--input", inp, "--output", out]))
        assert r3["audit"] == "PASS", r3
        print(json.dumps({"selftest": "PASS", "params": r1["params"],
                          "conflicts": r1["conflicts"], "status": r2["status"],
                          "audit": r3["audit"]}, ensure_ascii=False))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
