# Output contract for result.json

`result.json` is written to `/app/output/` (one per case). It must contain:

1. **Every key named by `case.json`'s `output_contract`** (identical key strings). Fill with the
   matching artifact when one exists, else `null`. Never drop or rename a contract key.
2. **`case_id`** — copied verbatim from the case.

## Standard body

```json
{
  "case_id": "…",
  "status": "success | partial | cannot_determine | rejected",
  "status_reasons": ["…"],
  "cards": [
    {
      "section": "Results",
      "page": 5,
      "research_question":  {"text": "…" | "not_reported", "note_ids": [12]},
      "data":                {"text": "…" | "not_reported", "note_ids": [13]},
      "method_conditions":   {"text": "…" | "not_reported", "note_ids": [14]},
      "main_findings":       {"text": "…" | "not_reported", "note_ids": [15, 16]},
      "limitations":         {"text": "…" | "not_reported", "note_ids": [17]},
      "assumptions":         {"text": "…" | "not_reported", "note_ids": [18]}
    }
  ],
  "notes": [
    {
      "note_id": 12,
      "para_index": 12,
      "page": 5,
      "section": "Results",
      "char_span": [1024, 1180],
      "quote": "…verbatim ≤240 chars…"
    }
  ],
  "evidence": {
    "pages": {"1": {"file": "paper.pdf", "chars": 3120}, …},
    "sections": [{"section": "1 Introduction", "page": 1, "para_index": 2}, …],
    "anchor_unit": "page text file (work/page_%03d.txt), char_span=[start,end)"
  },
  "extraction": {
    "backends": [{"file": "paper.pdf", "backend": "pymupdf|pdfminer|pypdf|pdftotext|plaintext|json_text|xml_strip", "pages": 9}],
    "anomalies": []
  },
  "uncertainty": ["human-readable items, e.g. 'page 7 garbled, marked uncertain'"],
  "not_reported_count": 6,
  "changes": [
    {"change": "extraction", "detail": "run.py stage extract", "result": "segments.json"},
    {"change": "cards", "detail": "agent semantic pass", "result": "notes.json"},
    {"change": "validation", "detail": "anchor + contract checks", "problems": []}
  ],
  "handoff": null
}
```

## Field semantics

- **`cards`** — one card per real content section (skip References/Acknowledgements). A card
  whose six fields are all `not_reported` is noise: drop the card instead.
- **`notes`** — the evidence pool. `quote` MUST be a verbatim substring of the paragraph
  `para_index` points at (audit.py re-slices the source and string-matches).
- **`char_span`** — `[start, end)` into the extracted page text (verbatim copy in
  `work/page_%03d.txt`), assigned by `run.py --stage finalize`; the agent never computes it.
- **`status`** — computed by the engine from artifacts, never hand-written:
  - `success` — cards exist, no validation problems;
  - `partial` — cards exist but some anchors/refs failed, or notes missing;
  - `cannot_determine` — no extractable text (e.g. no_text_layer) or malformed case.
- **`uncertainty`** — anything you could not pin down; conflicts go here too.
- **`handoff`** — where a human can continue (e.g. "OCR required for pages 3-7").

## Why anchors exist

The grader can re-verify any note with:

```
python3 scripts/audit.py --input /input --output /app/output
```

which re-reads the source material, re-slices the spans, and string-matches every quote.
An answer that cannot be re-checked is indistinguishable from an invented one.
