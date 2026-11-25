# translate-with-glossary-lock

Paragraph-aligned scientific translation with a machine-checked glossary lock — the
skill behind **阅读03｜文献翻译** (product-arena-01).

## What it does

Four mechanical guarantees around your translation:

1. **术语稳** — the glossary is a function: one source term, one rendering, executed
   everywhere (verified per occurrence, case-insensitive). New terms you introduce must
   be added to the same table.
2. **段落全** — 1:1 paragraph mapping (no missing, extra, duplicated, or shifted
   paragraphs; `para_id` order must be monotone).
3. **关系准** — per aligned pair: numbers/units, citation markers, figure refs
   preserved; negation not dropped; hedges not upgraded to strong claims.
4. **可核验** — every translation points back to `para_id` + source char span; the
   audit re-segments the source independently and re-checks all of the above.

Translation quality guidance (syntax reordering, passive→active, hedge fidelity,
long-sentence splitting) lives in SKILL.md §3 — the engine verifies the mechanical
layer, you own the linguistic layer.

## Usage

```
python3 scripts/run.py --stage segment --input /input --output /app/output
# translate -> /app/work/translation.json
#   {"glossary": {...}, "paragraphs": [{"para_id": 1, "translation": "...", "uncertain": false}]}
python3 scripts/run.py --stage verify --input /input --output /app/output
# fix what verify names, then:
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (faithful pass must verify clean; a drift
pass dropping numbers/negations/citations must produce ≥3 violations + partial status).

## Install / requirements

Python 3.8+, stdlib only (PDF sources probed via PyMuPDF when present).

## Input / output

- **Input** `/input/case.json` — source in `text/draft/source_text/original/content/
  body/paper` or a .txt/.md/.pdf file; optional seed glossary in
  `glossary/term_table/terminology` (dict or list of {source,target}).
- **Output** `/app/output/result.json` — contract keys + `case_id`, `translations`
  (with anchors + uncertainty), `glossary`, `verification`, computed `status`.
  Schema: [references/output-contract.md](references/output-contract.md).

## Applicable scope / limits

- EN→ZH by default; any language pair works for the mechanical checks (token lexicons
  are EN/ZH; other targets skip negation/hedge cross-checks and say so).
- One source document per case. Unreadable spans are translated best-effort with
  `uncertain: true` + note, never skipped or invented.

## Maintenance

`manifest.yaml` lists files; `selftest.py` must stay green.

## License

MIT.
