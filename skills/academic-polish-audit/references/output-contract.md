# Output contract for result.json

`result.json` (in `/app/output/`) contains every `case.json` `output_contract` key (null
when unknown) plus `case_id`, and at minimum:

```json
{
  "case_id": "…",
  "status": "success | partial | cannot_determine | rejected",
  "status_reasons": ["…"],
  "mode": "edit | audit",
  "polished_text": "…the final text (with rejected pairs reverted)…",
  "change_summary": {
    "pairs": 5,
    "changed_pairs": 4,
    "unchanged_pairs": 1,
    "alignment_ratio": 1.0,
    "fact_violation_ratio": 0.0,
    "rejected_pairs": 0
  },
  "changes": [
    {
      "orig_index": 1, "pol_index": 1, "similarity": 0.92,
      "original": "…", "polished": "…",
      "change_types": ["grammar"],
      "fact_risk": false
    }
  ],
  "audit": {
    "violations": [],
    "verdicts": [],
    "sanctioned_conversions": ["°C→K (+273.15)", "%→fraction (÷100)", "approximately→~/ca."]
  },
  "uncertainty": ["…"],
  "changes_log": [...]
}
```

## Field semantics

- **`polished_text`** — the deliverable. In audit mode with rejected verdicts, the flagged
  sentences are reverted to their originals before this field is written.
- **`changes`** — one row per aligned sentence pair, with `change_types` from
  references/edit-rules.md. `fact_risk: true` rows are exactly the ones the audit
  re-checks: numbers, units, citations, figure refs, negations, hedges, comparatives.
- **`change_summary.fact_violation_ratio`** — violations / pairs; `null` (not 0) when
  pairs = 0. Ratios never fake a denominator.
- **`mode`** — `edit` (you produced the polish) or `audit` (the case supplied a polished
  draft; you adjudicated it).
- **`status`** — computed: `success` when no unresolved violations; `partial` when
  violations exist unadjudicated or engine problems; `cannot_determine` when the draft
  text itself is missing.
- **`audit.verdicts`** — your adjudication of flagged pairs: `accept: true/false` +
  reason. Rejected pairs get reverted, so the final text never carries a flagged edit.

## What the grader can re-verify

```
python3 scripts/audit.py --input /input --output /app/output
```

re-aligns the original (from the case) against `polished_text` (from result.json),
re-extracts every fact token, and recomputes the violation set independently. A result
that claims `success` with recomputed violations fails this check.
