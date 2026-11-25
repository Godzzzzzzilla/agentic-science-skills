# Output contract for result.json

Every `case.json` `output_contract` key (null if unknown) + `case_id`, plus:

```json
{
  "case_id": "…",
  "status": "success | partial | cannot_determine | rejected",
  "status_reasons": ["…"],
  "source_file": "paper.txt",
  "translations": [
    {"para_id": 3, "translation": "…",
     "source_section": "1. Introduction", "source_span": [512, 1198],
     "uncertain": false, "note": null}
  ],
  "glossary": {"deep learning": "深度学习", "van der Berg": "范德贝格"},
  "verification": {
    "coverage": {"missing": [], "extra": [], "duplicated": []},
    "glossary_violations": [{"term": "…", "para_id": 3, "expected": "…"}],
    "fact_violations": [{"para_id": 3, "type": "number", "missing": ["0.42"]}],
    "anchor_bad": []
  },
  "uncertainty": [{"para_id": 7, "note": "source truncated; translated visible part"}],
  "changes_log": [...]
}
```

## Field semantics

- **`translations[].source_span`** — `[start, end)` char span of the source paragraph;
  the audit re-slices and matches para order (shifted paragraphs = `anchor_bad`).
- **`glossary`** — final locked pairs. Engine rule: one source term → one rendering;
  every source occurrence must use it (case-insensitive), violations listed per para.
- **`verification.fact_violations[].type`** — `number` (value lost or changed),
  `citation` (`[3]`/`(Smith et al., 2020)` dropped), `figure_ref`, `negation_dropped`
  (source negates, translation does not), `hedge_upgraded` (suggest→证明).
- **`status`** — `success` only with full coverage + zero glossary violations + fact
  violations within tolerance; else `partial`; missing source → `cannot_determine`.

## What the grader can re-verify

```
python3 scripts/audit.py --input /input --output /app/output
```

independently re-segments the source, re-checks coverage, glossary execution, fact
tokens (12-paragraph sample), and order. Paragraph 1:1 mapping means nothing was
silently skipped or merged.
