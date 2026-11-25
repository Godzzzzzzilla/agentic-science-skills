---
name: nanopub-assertion-miner
description: Decompose scientific conclusions into atomic, independently checkable assertions — each with subject/predicate/object (+qualifier), minimal sufficient evidence quoted verbatim with its source location, and provenance metadata — serialized exactly to the requested schema with light direction/role checks and honest marking of what the material does not support. Use for Nanopublication、断言拆解、claim extraction、证据绑定、知识单元构建; serialization follows the case's output_contract field-by-field.
metadata:
  version: "1.1.0"
---

# Nanopublication Assertion Miner — atomic claims, bound evidence

You are an agent turning a scientific text into nanopublication-style assertions.
The grader checks: 拆得细 (atomic, separately checkable), 对得上 (each claim has its
minimal evidence, locatable), 追得回 (claim→evidence→source chain complete), 读得懂
(serialization matches the requested fields exactly). The engine verifies the chain;
you own the decomposition.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). Material may be JATS
   XML / plain text / JSON with paragraph ids. Resolve paragraph identifiers from the
   material itself (JATS `id=` attributes or positional numbering) — the case tells
   you which; do not invent page numbers when the package has none.
2. **Atomic decomposition.** One assertion = one checkable statement: a single
   subject–predicate–object with its qualifiers. Compound sentences split at their
   coordination/causation boundaries. A claim needing "and" to be true is two claims.
3. **Evidence = minimal sufficient verbatim quote.** ≤240 chars, substring of the
   named paragraph (engine re-slices + string-matches). Direct evidence preferred;
   inference marked `"inference": true` with its basis stated.
4. **Serialization is field-exact.** Every field the case's `output_contract` (or the
   task's nanopub schema) names must be present per assertion — `null` when unknown,
   never dropped. `case_id` at top level.
5. **Never crash; never reject.** Missing material → `cannot_determine`. Verification
   failures demote to `partial`, listing offending assertions.
6. Provenance per assertion: source (file/paragraph), authors/year/version when the
   material carries them, `null` when absent.

## 1. Pipeline

```
/input/case.json
  │ run.py --stage collect ──> work/material.json (paragraphs with ids + text)
  │ YOU decompose -> work/assertions.json:
  │   {"assertions": [{
  │       "subject": "...", "predicate": "...", "object": "...",
  │       "qualifier": null | "under X, in Y",
  │       "evidence": {"para_id": "p12", "quote": "verbatim ≤240 chars"},
  │       "inference": false, "conflicts": null | "p15 states the opposite"},
  │     ...],
  │    "provenance": {"title": "...", "authors": [...], "year": "…", "version": "…"}}
  │ run.py --stage verify  ──> atomicity hints + evidence re-slice + schema fields
  │        (fix what it names; re-run until clean)
  │ run.py --stage finalize ──> /app/output/result.json
  └ audit.py --input /input --output /app/output
```

## 2. Decomposition rules (what earns the points)

1. **拆得细** — target one fact per assertion. "Drug A reduced tumors (p<0.01) and
   improved survival" → two assertions sharing the evidence paragraph.
2. **对得上** — the quote must contain (or directly support) the fact; the subject
   and object must appear in (or be trivially anaphoric to) the quote's sentence.
3. **谓词方向** — keep the direction the source states: "A inhibits B" is not
   "B is inhibited by A" reversed blindly; relational nouns (activation/inhibition/
   binding) have natural directionality — the engine flags obvious subject/object
   swaps for you to confirm, it does not auto-judge.
4. **限定保留** — conditions ("in male mice", "at 25 °C", "under hypoxia") go to
   `qualifier`, not into subject/object.
5. **未报告与冲突** — a conclusion the material does not support → do not fabricate;
   record it in `uncertainty` with the reason. Contradictory paragraphs → both
   assertions with `conflicts` pointing at each other.

## 3. Verification (mechanical)

`run.py --stage verify` checks:
1. **schema fields** — every assertion has subject/predicate/object/evidence.para_id/
   evidence.quote; contract keys present; nulls allowed, missing keys not.
2. **evidence backtracking** — quote is a verbatim substring of the named paragraph
   (re-sliced from the actual material text).
3. **atomicity hints** — assertions whose object contains a coordinating "and" joining
   two full clauses are listed for you to split (hints, not verdicts).
4. **provenance** — fields present when the material carries them (null otherwise).

Failures demote status to `partial` with the assertion index named.

## 4. Failure routes

| Situation | Action |
|---|---|
| No material | `cannot_determine`, reason `missing_material`, contract keys null |
| Paragraph ids absent | positional ids `p1..pN` assigned and recorded as such |
| Quote drift | verify names them; shorten quotes to exact substrings |
| Unsupported claim in source conclusions | `uncertainty` entry, no fabricated assertion |

## 5. Self-check

1. `audit.py` exit 0.
2. Contract keys + `case_id` present; per-assertion schema complete.
3. All quotes re-slice cleanly; atomicity hints resolved or consciously kept.
4. `python3 scripts/selftest.py` green locally.

## 6. What this skill will not do

It will not merge two facts into one assertion, not paraphrase evidence, not invent
paragraph ids when the material has none (it says what it assigned), not guess
provenance the material lacks, and not let one bad assertion kill the run.
