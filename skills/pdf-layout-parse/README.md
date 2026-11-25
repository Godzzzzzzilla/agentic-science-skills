# pdf-layout-parse

Column-aware structural PDF parsing with auditable anchors — the skill behind
**阅读01｜文献文档解析** (product-arena-08).

## What it does

One deterministic pass turns a scientific PDF into a re-checkable structure:

1. **提得全** — word-box extraction (PyMuPDF → pdfminer → pdftotext fallback);
   header/footer bands separated by cross-page repetition (digit-masked signatures);
   footnotes captured; captions bound; nothing body-level silently dropped, and the
   coverage ratio states exactly what was classified.
2. **排得对** — column detection by the row-empty criterion: a true column gap is a
   vertical strip empty of words on ~every body row (a table's inner gap only clears
   its own rows, so it loses). Reading order: col 1 top→bottom, then col 2; the claim
   ships with its evidence (`n_columns`, `split_x`, per-side counts).
3. **拆得清** — tables detected as same-column runs grouped into rows by y (≥2 rows ×
   ≥2 cells), emitted as a cell matrix; formula regions flagged by math-symbol density
   (structure only, no semantics).
4. **核得回** — every block carries page + bbox (PDF points) + char-span into the
   page's raw text; cross-column/cross-page continuations merge only on explicit
   evidence (left ends mid-sentence, right starts continuation) and carry
   `merge_reason`.

```
python3 scripts/run.py --input /input --output /app/output          # parse
python3 scripts/run.py --finalize-notes --input /input --output /app/output   # merge field answers
python3 scripts/audit.py --input /input --output /app/output        # one-command recheck
```

Self-test builds a synthetic 2-column PDF (cross-column continuation, 2×3 table,
repeated header/footer, footnote, formula line) and asserts the full pipeline:
`python3 scripts/selftest.py`

## Install / requirements

Python 3.8+. Backends probed at runtime, first available wins:
`pip install pymupdf` (best: word boxes) → `pdfminer.six` → `pdftotext` on PATH.
Pure text/JSON/XML inputs need nothing.

## Input / output

- **Input** `/input/case.json` (+ the PDF under `materials/files/inputs/sources/
  documents/paper/pdf`) and the platform's `task.md`.
- **Output** `/app/output/result.json` — contract keys + `case_id`, `pages` (column
  claims + evidence), `blocks` (typed, ordered, anchored), `tables` (cell matrices),
  `full_text` (reading order, continuations joined), `coverage` (honest ratios),
  `anomalies`, computed `status`.
  Schema: [references/output-contract.md](references/output-contract.md).

## Key methods

- Row-empty column criterion (vertical strip empty on ≥80% of body rows, both sides
  ≥20% of rows) — rejects table-column gaps that fool word-count heuristics.
- Run splitting at >15 pt intra-line gaps, so same-y col1+col2 text never merges.
- Digit-masked line signatures for header/footer repetition (≥2 pages).
- Evidence-gated merges: no terminal punctuation + continuation start, else blocks
  stay separate with `merged_into: null`.
- Failure routes: no text layer → `cannot_determine` + OCR handoff; layout-limited
  backend (pdftotext) → `partial` with the limitation recorded; garbled pages →
  `low_confidence_extraction` flag, coverage stays honest.

## Applicable scope / limits

- Born-digital PDFs, 1–2 columns typical (n-column generalizes via the same
  criterion). Scanned PDFs without a text layer are reported, not OCR'd.
- Figures are region flags, not interpreted; image-only tables get an honest
  `figure_like_region` note instead of invented cells.

## Maintenance

`manifest.yaml` lists files; `selftest.py` must stay green; behavior changes go into
`changes_log` and bump the SKILL.md version.

## License

MIT.
