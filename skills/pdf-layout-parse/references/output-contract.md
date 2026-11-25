# Output contract for result.json

Every `case.json` `output_contract` key (null if unknown) + `case_id`, plus:

```json
{
  "case_id": "…",
  "status": "success | partial | cannot_determine | rejected",
  "status_reasons": ["…"],
  "source_file": "paper.pdf",
  "backend": "pymupdf | pdfminer | pdftotext",
  "pages": [
    {"page": 1, "n_columns": 2,
     "column_evidence": {"split_x": 296.0, "left_lines": 18, "right_lines": 15,
                          "full_width_lines": 3},
     "char_count": 3120}
  ],
  "blocks": [
    {"block_id": 14, "page": 1, "type": "body", "order": 6, "col": 1,
     "bbox": [72.0, 100.2, 291.5, 158.9],
     "text": "…verbatim…",
     "char_span": [512, 1198],
     "merged_into": null,
     "merge_reason": null}
  ],
  "tables": [
    {"page": 1, "col": 1, "cells": [["T (K)", "Viscosity (mPa s)", "Order"],
                                     ["400", "12.4", "0.11"]],
     "n_rows": 2, "n_cols": 3, "y0": 170.7, "y1": 198.7}
  ],
  "full_text": "…body paragraphs in reading order, continuations joined…",
  "coverage": {"body_chars": 2870, "page_chars_total": 3120, "body_ratio": 0.92,
                "header_footer_chars": 140},
  "anomalies": [],
  "field_answers": [],
  "handoff": null,
  "changes_log": [...]
}
```

## Field semantics

- **`blocks[].type`** — `body | header | footer | footnote | caption | table |
  formula_candidate`. Headers/footers are separated from body; footnotes captured;
  captions bound to their figure/table; formulas flagged structurally only.
- **`bbox`** — PDF points `[x0, y0, x1, y1]`, directly re-checkable by re-opening the PDF.
- **`char_span`** — `[start, end)` into that page's raw extracted text; the audit
  re-slices and string-matches.
- **`n_columns` + `column_evidence`** — the reading-order claim plus its evidence
  (split position, per-side line counts). A wrong claim is auditable; a silent one is not.
- **`merged_into`** — cross-column/cross-page continuation: this block's text continues
  the target block. Merge requires: left ends mid-sentence (no terminal punctuation)
  AND right starts lowercase/continuation word. The merged text is appended to the
  target in `full_text` (never dropped).
- **`coverage.body_ratio`** — body+table+caption+footnote chars / total extracted chars.
  `< 0.8` → partial with reason; the ratio itself is honest, never padded.
- **`status`** — computed: `success` (clean parse, coverage ≥ 0.8), `partial`
  (anomalies/low coverage/limited backend), `cannot_determine` (no text layer, no
  backend, missing material).

## What the grader can re-verify

```
python3 scripts/audit.py --input /input --output /app/output
```

re-opens the source PDF with the same backend chain and checks: block text verbatim in
page (word-level loose match flagged as warning), reading order monotone per
(page, column), table cells verbatim, coverage honest, contract keys present.
