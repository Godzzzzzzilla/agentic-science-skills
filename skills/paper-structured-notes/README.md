# paper-structured-notes

Source-grounded structured reading notes for scientific papers — the skill behind
**阅读10｜文献总结与结构化笔记** (product-arena-06).

## What it does

Turns one scientific paper into **re-checkable reading notes**: per-section cards with six
fields (research question / data / method conditions / main findings / limitations /
assumptions), where every field is either backed by a verbatim quote with a machine-checkable
character-span anchor, or explicitly `not_reported`.

The audit re-verifies the whole deliverable against the source with one command:

```
python3 scripts/audit.py --input /input --output /app/output
```

## Install / requirements

- Python 3.8+ (stdlib only for the engine).
- Optional PDF backends, probed at runtime in this order: PyMuPDF (`pip install pymupdf`),
  pdfminer.six, pypdf, `pdftotext` (poppler) on PATH. Any one of them suffices; plain
  text / JSON / XML inputs need nothing extra.

## Usage

```
# 1. deterministic extraction (pages, sections, paragraphs, anchors)
python3 scripts/run.py --stage extract --input /input --output /app/output

# 2. agent semantic pass: fill /app/work/notes.json  (see SKILL.md §3)

# 3. validate + merge into the contract-true result.json
python3 scripts/run.py --stage finalize --input /input --output /app/output \
  --notes /app/work/notes.json

# 4. one-command audit (exit 0 = every quote re-verified against the source)
python3 scripts/audit.py --input /input --output /app/output
```

Self-test (no external files needed): `python3 scripts/selftest.py`

## Input / output

- **Input** `/input/case.json` (+ materials it declares: PDF, txt, md, JSON, JATS XML;
  field aliases `materials/files/inputs/sources/documents/paper/pdf` tolerated) and the
  platform's `task.md`.
- **Output** `/app/output/result.json` — every `output_contract` key (null if unknown),
  plus `case_id`, `cards`, `notes` (with anchors), `evidence`, `status` (computed),
  `uncertainty`, `extraction`, `changes`. Schema: [references/output-contract.md](references/output-contract.md).

## Key methods

- Multi-backend PDF text extraction with per-page fallback, recording which backend ran.
- Blank-line paragraph segmentation (`"\n\n"`), never single newlines — keeps anchor
  offsets stable.
- Bilingual (EN/CN) section-header detection, page-by-page.
- Anchor = page + `char_span` into the verbatim page text (kept in `work/page_NNN.txt`
  for re-slicing), so verification is pure string matching.
- Failure routes for: no text layer, missing material, malformed case, garbled pages —
  each yields a defined partial result, never a crash.

## Applicable scope / limits

- One paper (or a small set) per case; designed for born-digital PDFs. Scanned PDFs
  without a text layer are honestly reported `cannot_determine` with an OCR handoff note.
- Figures/equations are treated as structural elements (caption text extracted); the
  skill does not interpret their scientific content.
- Semantic cards reflect only what quoted evidence supports; gaps stay `not_reported`.

## Maintenance

- `manifest.yaml` lists every file with a one-line role and sha256 (recompute after edits).
- Behavior changes go in `changes` inside result.json; version in SKILL.md frontmatter.
- `selftest.py` must stay green; it exercises extract → finalize → audit on a synthetic case.

## License

MIT.
