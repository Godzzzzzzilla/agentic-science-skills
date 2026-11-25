---
name: academic-polish-audit
description: Polish academic prose with machine-checkable fact preservation — align original and polished sentences, verify every number, unit, citation marker, negation and qualifier survived, and emit a per-change table (original / polished / type / reason). Use for 学术润色、语言修改、论文语言检查、语法修正; when the case supplies an already-polished draft, audit it instead of rewriting it; never let polishing strengthen or weaken claims.
metadata:
  version: "1.1.0"
---

# Academic Polish & Audit — edit the language, prove you kept the facts

You are an agent polishing (or auditing) academic text. The deliverable is not just better
prose: it is better prose **plus a machine-checkable proof that nothing factual moved**.
The grader re-runs one audit command against your output; every number, unit, citation
marker, negation and hedge is compared sentence-by-sentence between original and polished
text. A beautiful rewrite that quietly upgrades "may" to "does" fails.

## 0. Non-negotiable rules

1. **Read the real input first.** `/input/case.json` (+ `task.md` if present). Resolve the
   draft text from alias fields (`text` / `draft` / `source_text` / `original` / `manuscript` /
   `content` / `body` / `paragraph`). If a polished version exists (`polished` / `revised` /
   `llm_draft` / `target_text`), you are in **audit mode** (§3); otherwise **edit mode** (§2).
2. **Fact tokens are load-bearing**: numbers with units, citation markers (`[1]`, `(Smith et al., 2020)`, superscripts), negation words, hedges/qualifiers, comparatives, species/gene names, figure/table pointers. Preserve them exactly, or change them only via the sanctioned conversion table (§4).
3. **Never fabricate** citations, data, or claims of improvement. If the draft is already correct, say so — zero changes is a valid, honest outcome.
4. **Never crash.** Top-level try/except writes a contract-shaped `result.json` with `status: partial` + reason. Missing text → `cannot_determine`.
5. **Contract discipline**: every `output_contract` key present in `result.json` (null if unknown) + `case_id`.
6. Budget: ~64 requests / 900 s. The alignment, token extraction, and audit are deterministic (`scripts/run.py`, stdlib + difflib). Spend your reasoning on register and grammar, not on counting tokens by hand.

## 1. Pipeline

```
/input/case.json
   ├─ has polished draft? ──> AUDIT mode
   │      run.py --mode audit --original <orig> --polished <pol>
   └─ only original? ──────> EDIT mode
          you produce a minimal-edit polished version (§2)
          run.py --mode audit --original <orig> --polished <yours>
                     │
                     ▼  sentence alignment + fact-token diff + change table
             fix what the audit flags, re-run until green
                     │
                     ▼
          run.py --mode finalize ... -> /app/output/result.json
          audit.py --input /input --output /app/output   (one-command recheck)
```

## 2. Edit mode — how to polish

Write the polished text to `/app/work/polished.txt` first, then audit it. Edit in this
priority order (fix hard errors before style):

1. **Grammar**: subject-verb agreement, tense/voice consistency, articles, prepositions,
   singular/plural, dangling modifiers, punctuation, long-sentence splits.
2. **Terminology consistency**: one concept = one term across the whole text; expand an
   abbreviation once at first use; keep capitalization/hyphenation consistent.
3. **Register**: tighten wordy constructions ("due to the fact that" → "because"),
   remove informal phrasing, keep the discipline's standard voice. Do not chase synonyms.
4. **What NOT to do**: no new claims, no new citations, no data changes, no reorder of
   logic, no tone upgrades (hedge removal), no "improving" numbers.

Each mechanical rule has an entry in [references/edit-rules.md](references/edit-rules.md)
with examples and the change-type label to use.

## 3. Audit mode — grade someone else's polish

When the case supplies both original and polished: do **not** rewrite further. Run
`run.py --mode audit`, inspect the report, and judge each flagged change:

- `loss: number` / `loss: citation` / `loss: negation` / `loss: hedge` → the polished text
  changed a fact token. **Reject that sentence pair** in your verdict (report it as a
  violation, restore the original sentence in the corrected output).
- `swap: hedge_stronger` (may→does, suggest→prove) → fact drift; reject.
- `swap: hedge_weaker` (does→may) → claim weakened; reject unless the case explicitly
  asks for conservative revision.
- pure grammar/wording changes → accept; record in the change table with a reason.

Your verdict goes to `/app/work/notes.json` (`{"verdicts": [{"pair": 12, "accept": true,
"reason": "..."}]}`), consumed by finalize.

## 4. Sanctioned conversions

Only these number changes are legal (record `type: unit_conversion`):

| from | to | factor |
|---|---|---|
| °C | K | +273.15 |
| % | 0–1 fraction | ÷100 |
| "approximately X" | "~X" / "ca. X" | same value |

Everything else (including rounding) is `loss: number`.

## 5. Run the tools

```
# align + extract tokens + build change table (both modes)
python3 scripts/run.py --mode audit --input /input --output /app/output \
    --original /app/work/original.txt --polished /app/work/polished.txt

# merge audit report + verdicts into result.json
python3 scripts/run.py --mode finalize --input /input --output /app/output \
    --notes /app/work/notes.json

# one-command recheck (the grader trusts this)
python3 scripts/audit.py --input /input --output /app/output
```

`run.py` never needs third-party packages. If case text fields are missing, write
`original.txt`/`polished.txt` yourself from the case before running (§0.1).

## 6. Failure routes

| Situation | Action |
|---|---|
| No draft text in case | `status: cannot_determine`, reason `missing_draft_text`, contract keys null |
| Unreadable case.json | `status: partial`, reason `malformed_case_json:<err>`, write partial result |
| Audit reports >30% pairs with fact loss | still finalize with `status: partial` + violations listed; never reject the whole run |
| Zero changes needed | finalize with `status: success`, empty change table — honest zero |
| Empty output_contract | emit standard fields + case_id |

## 7. Self-check

1. `audit.py` exit 0.
2. Every contract key present in result.json; `case_id` matches.
3. Change table entries each have original / polished / type / reason — no bare diffs.
4. `status` computed by the engine (never hand-written).
5. `python3 scripts/selftest.py` green locally before trusting runtime.

## 8. What this skill will not do

It will not invent evidence of improvement, not polish beyond the given text, not add
citations the draft lacks, not remove hedges to "sound more confident", and not output a
rewrite without its audit trail. Verifiability is the product; prose is the by-product.
