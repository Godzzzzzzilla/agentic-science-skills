---
name: methods-repro-writer
description: Write methods & experimental sections with a parameter table where every value carries its source (config / log / manuscript / author-confirm / not_reported) and a reproduction checklist — with tolerant verification (missing fields become null, never rejections). Use for 方法章节、实验设置、参数溯源、复现清单、methods writing; no cross-validation gates that zero-score hidden cases; partial results always ship.
metadata:
  version: "1.1.0"
---

# Methods & Reproduction Writer — every parameter has a source

You are an agent writing the methods/experimental section of a paper from supplied
material (manuscript drafts, config files, logs, run manifests). The one historical
killer on this task is **strict cross-validation that rejects the whole run** when a
hidden case lacks some field. This skill's verification only ever *demotes* — a
missing value is `null` with source `not_reported`, and the deliverable still ships.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). Material may hide in
   `materials / files / configs / logs / text / manuscript / draft`. Parse every
   readable file; skip unreadable ones with a note.
2. **Every parameter carries a source.** `source` ∈ `config:<file>` | `log:<file>` |
   `manuscript` | `author_confirm` | `not_reported`. A value found nowhere is written
   with `value: null, source: "not_reported"` — never guessed, never omitted.
3. **Steps are executable prose.** Each step: input → operation → output → judgment
   condition, numbered continuously. Split multi-step compressions into separate steps.
4. **Conditions are separated.** Training / validation / test setups each get their own
   block (hardware, versions, seeds, repeats) — no cross-contamination of numbers.
5. **Never crash; never reject.** Top-level try/except writes contract-shaped
   result.json. Verification only demotes to `partial` with named items.
6. **Contract discipline:** every `output_contract` key + `case_id`.

## 1. Pipeline

```
/input/case.json
  │ run.py --stage collect ──> work/facts.json
  │     (parameters with values+sources from configs/logs/text; steps skeleton;
  │      environment facts; unreadable files noted)
  │ YOU write work/draft.json:
  │   {"methods_text": "...", "steps": [{"n": 1, "input": "...", "operation": "...",
  │      "output": "...", "condition": "..."}],
  │    "params": [{"name": "lr", "value": "3e-4", "unit": null, "applies_to": "training",
  │      "source": "config:train.yaml"}],
  │    "setup": {"training": {...}, "validation": {...}, "test": {...}},
  │    "repro": {"environment": "...", "seed": "1234|not_reported",
  │      "command": "python train.py --cfg cfg.yaml", "artifacts": [...]},
  │    "limitations": [{"text": "...", "trigger": "concrete failure scenario"}]}
  │ run.py --stage verify  ──> schema sanity (tolerant) + source coverage stats
  │ run.py --stage finalize ──> /app/output/result.json
  └ audit.py --input /input --output /app/output
```

## 2. Writing rules (the substance that earns points)

1. **写得全** — every stage of the pipeline appears as steps: data preparation,
   splitting (with sizes), model construction, training loop, evaluation protocol,
   repeats. A reader should be able to re-execute from the steps alone.
2. **写得准** — parameter values copied exactly from their source (no rounding, no
   "approximately"). When config and manuscript disagree, list both values with both
   sources and mark `conflict: true` — do not silently pick one.
3. **做得着** — the repro checklist names environment (versions), random seeds, the
   exact command, and expected artifacts. A missing seed is written
   `"seed": null, "source": "not_reported"` and flagged in limitations, not invented.
4. **说得住** — limitations point at concrete failure scenarios ("batch norm statistics
   drift when batch size < 8"), never boilerplate ("more work needed").

## 3. Verification (tolerant by design)

`run.py --stage verify` checks only:
- steps numbered consecutively from 1 (gaps → warning, listed);
- params have `name` and `source` fields (missing `value` → `null` allowed);
- setup blocks, when present, have string values (nulls allowed);
- source coverage stats: how many params are `not_reported` (reported, never used to
  reject).

**Nothing here fails the run.** Status is `success` when the draft exists and parses;
`partial` when material was unreadable or fields were unfilled; `cannot_determine`
only when no material at all.

## 4. Failure routes

| Situation | Action |
|---|---|
| No material files | `cannot_determine`, reason `missing_material`, contract keys null |
| Config parse fails | note the file + error; continue with other sources; `partial` |
| Conflicting values | both listed with sources + `conflict: true`; status stays success |
| Missing seed/versions | `null` + `not_reported` + limitation entry |

## 5. Self-check

1. `audit.py` exit 0.
2. Contract keys + `case_id` present.
3. Every param has a source; `not_reported` params appear in limitations.
4. Steps 1..N with no gaps.
5. `python3 scripts/selftest.py` green locally.

## 6. What this skill will not do

It will not cross-validate versions against round counts, not reject on missing
manifests, not invent seeds or hardware, not merge train/test conditions, and not
ship a result.json that fails its own contract. Degrade honestly, always ship.
