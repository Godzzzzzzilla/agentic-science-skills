---
name: pdf-layout-parse
description: Parse scientific PDFs into verifiable structure — column-aware reading order (no cross-column concatenation), cross-column and cross-page paragraph continuation, header/footer separation, table region detection with cell-grid extraction, footnote capture, formula-region flagging — with every block anchored to page + bounding box + char span that an audit script re-verifies against the source. Use for PDF 解析、文献解析、双栏阅读顺序、表格提取、页眉页脚分离、footnote/公式定位; scanned PDFs without a text layer are reported honestly, not guessed.
metadata:
  version: "1.1.0"
---

# PDF Layout Parse — ordered, complete, re-checkable

You are an agent that turns a scientific PDF into a structured, machine-anchored
representation. The grader re-runs one audit command that re-opens the PDF and checks
your blocks: every text fragment must be verbatim in the page, the reading order must
follow the declared column layout, and nothing body-level may be silently dropped.
Structure is the deliverable; pretty prose is not.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). The PDF path may be under
   `materials/files/inputs/sources/documents/paper/pdf` — resolve and open the actual
   file; never trust a label.
2. **Verbatim or marked.** Text blocks are copied character-for-character from the
   extraction. Garbled/low-confidence regions are flagged, never "fixed" by guessing.
3. **Order is a claim.** For each page the engine records `n_columns` and the evidence
   (column gap). Reading order follows: header → column 1 (top→bottom) → column 2 → …
   → footer → footnotes. A wrong claim is auditable; a silent one is not.
4. **Merge with evidence, not hope.** A paragraph continued across columns/pages is
   merged only when the left fragment ends mid-sentence (no terminal punctuation, no
   closing bracket) and the right fragment starts lowercase or with a continuation word
   — the merge carries `merge_reason`. Otherwise blocks stay separate with
   `continued: false`.
5. **Never crash.** No text layer → `cannot_determine` + per-page failure list + OCR
   handoff. Malformed case → `partial` with reason. Top-level try/except always writes
   `result.json`.
6. **Contract discipline:** every `output_contract` key + `case_id` in result.json.

## 1. Pipeline

```
/input/case.json -> run.py --input /input --output /app/output
                      │  PyMuPDF (word boxes) → pdfminer → pdftotext fallback
                      ▼
            /app/output/result.json
            pages[] { n_columns, blocks[] {type, order, text, bbox, char_span} }
            full_text (reading order), tables[], coverage stats, anomalies
                      │
                      ▼
            audit.py --input /input --output /app/output   (one-command recheck)
```

The engine is one deterministic pass — no model requests needed for the structure
itself. Use your reasoning budget to review flagged regions (formula candidates,
merge decisions) and record verdicts in `work/notes.json` if the case asks for
specific fields; `run.py --finalize-notes` merges them.

## 2. What the engine does

- **Word-box extraction** (PyMuPDF preferred; pdfminer's LTTextContainer with bboxes
  next; `pdftotext` as last resort with `anomaly: no_layout_backend`).
- **Header/footer detection**: text in the top/bottom 8% band repeating (fuzzy) across
  ≥2 pages → `type: header|footer`, excluded from body text.
- **Column detection**: cluster block x-midpoints; a persistent vertical gap
  (≥ 6% of page width) crossing ≥ 60% of the text height ⇒ 2 columns (generalizes to
  n). Per-page `n_columns` + `column_evidence`.
- **Reading order**: column-major, y-major within column; captions bound to the nearest
  figure/table region above them.
- **Cross-column/cross-page continuation**: rule §0.4, recorded as
  `merged_into: <block_id>` with `merge_reason`.
- **Table regions**: grid of aligned short text lines (≥2 columns × ≥2 rows with
  consistent x-positions) → `type: table` with `cells [][]` extracted in row-major
  order, each cell string verbatim.
- **Footnotes**: bottom region blocks starting with a superscript-like marker
  (`1`, `*`, `†`) in smaller font → `type: footnote`.
- **Formula candidates**: lines with ≥3 math tokens (`= + - ± × ∑ ∫ α β …`) and no
  sentence-final punctuation → `type: formula_candidate` (structure only; no semantics).
- **Anchors everywhere**: every block carries `page`, `bbox` (x0,y0,x1,y1 in PDF
  points), and `char_span` into that page's raw text — the audit re-slices both.

## 3. Your review pass

Read `result.json`'s `review_queue` (merge candidates, formula candidates, garbled
pages). If the case/task asks for specific extracted fields (e.g. "give the abstract",
"list all section titles"), write them into `work/notes.json` as block references:

```json
{"field_answers": {"abstract": {"text": "…", "block_ids": [14]},
                   "section_titles": [{"text": "2 Methods", "block_ids": [21]}]}}
```

Then `python3 scripts/run.py --finalize-notes --input /input --output /app/output`
merges them into result.json (validated against the blocks they cite).

## 4. Output shape

`result.json` (contract keys + case_id +):

- `pages[]` — `{page, n_columns, column_evidence, char_count}`
- `blocks[]` — `{block_id, page, type (body|header|footer|table|footnote|caption|formula_candidate),
  order, text, bbox, char_span, merged_into?, merge_reason?}`
- `full_text` — body blocks in reading order, `\n\n` between logical paragraphs
- `tables[]` — `{block_id, page, cells, n_rows, n_cols}`
- `coverage` — `{body_chars, page_chars_total, body_ratio (null when 0 pages),
  header_footer_chars, unclassified_pages}`
- `anomalies[]` — no_layout_backend, garbled pages, no_text_layer …
- `status` — computed: `success` / `partial` (anomalies or coverage < 0.8 with text
  present) / `cannot_determine` (no text layer at all)

Schema details: [references/output-contract.md](references/output-contract.md).

## 5. Audit — the command the grader trusts

```
python3 scripts/audit.py --input /input --output /app/output
```

Re-opens the PDF with the same backend chain and checks, per block:
(1) `text` is a substring of the page's raw text (extraction fidelity);
(2) reading order matches the declared column layout (order indices monotone per
column region); (3) every table cell appears in its page's text; (4) coverage:
body+table+footnote+caption chars ≥ 80% of page chars (else warn, fail < 50%);
(5) contract keys present. Exit 0 = green. Run it; fix what it names (usually a merge
gone wrong); re-run.

## 6. Failure routes

| Situation | Action |
|---|---|
| No text layer (scanned) | `cannot_determine`, per-page failure list, `handoff: "OCR required for pages …"`; never invent text |
| Layout backend missing (only pdftotext) | structure from plain text; `anomaly: no_layout_backend`; order claim limited to linear — recorded, not hidden |
| Garbled/cid-glyph pages | page flagged `low_confidence_extraction`; its blocks stay but marked; coverage honest |
| Encrypted PDF | `partial`, `reason: encrypted_pdf`, empty blocks |
| case.json missing text fields | `cannot_determine` with `missing_material` |

## 7. Self-check

1. `audit.py` exit 0.
2. `full_text` paragraph count ≥ blocks/3 roughly (sanity: merges happening).
3. No `type: body` block inside the header/footer bands (they'd be misclassified).
4. `selftest.py` green (synthetic 2-column case with a cross-column continuation, a
   2×3 table, header/footer lines, a footnote, a formula line).

## 8. What this skill will not do

It will not OCR scanned pages, not interpret figure pixels or formula semantics, not
reconstruct tables that are actually images (they get `type: figure_like_region` with
an honest flag), and not reorder text by "what makes sense" — only by declared,
auditable layout rules. A parse someone cannot re-check is a parse that did not happen.
