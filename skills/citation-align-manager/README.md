# citation-align-manager

Reference & citation management with a verifiable audit trail — the skill behind
**写作04｜参考文献与引用管理** (product-arena-03).

## What it does

1. **Align** — parses in-text citations (numeric `[1,2]`/`[3-5]` and author-year
   `(Smith et al., 2020)`) and the reference list (embedded or separate field), and
   matches every citation to an entry.
2. **Dedup** — finds duplicate entries under conservative rules (equal DOI + lead-author
   surname + year, or equal normalized title + lead-author + year). Particles and
   compound surnames survive normalization (`van der Berg` never becomes `van`).
   Ambiguous pairs become `merge_candidate` for agent adjudication, defaulting to
   keep-separate.
3. **Renumber** — first-occurrence order over the whole text; uncited entries keep their
   order at the tail; the renumber map ships with the result.
4. **Audit** — one command re-checks numbering, resolution, remaining duplicates,
   metadata verbatim-ness, and unresolved-citation transparency.

```
python3 scripts/run.py --stage align --input /input --output /app/output
# adjudicate merge candidates -> /app/work/notes.json {"merge_verdicts": [...], "claim_citation_checks": [...]}
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (5-entry list with a DOI duplicate, a
particle surname, an unresolved `[9]`, first-occurrence renumbering, verbatim check).

## Install / requirements

Python 3.8+, stdlib only.

## Input / output

- **Input** `/input/case.json` — manuscript in `text/draft/manuscript/source_text/content/
  body`; optional separate reference list in `references/bibliography/refs/citation_list/
  reference_list` (string or array).
- **Output** `/app/output/result.json` — contract keys + `case_id`, `updated_text`,
  `updated_references` (verbatim bodies + parsed fields), `renumber_map`, `merge_log`,
  `unresolved_citations`, `claim_citation_checks`, `metadata_verbatim_check`,
  `uncited_entries_kept`, computed `status`.
  Full schema: [references/output-contract.md](references/output-contract.md).

## Key methods

- Particle-aware author splitting (van/von/de/der/…; initials-first and surname-first
  styles).
- DOI + author-year identity, title + author-year fallback; candidates require a verdict.
- First-occurrence renumbering with map; unchanged verbatim entries (only labels move).
- Unresolved citations are kept in text, listed, and demote status — never dropped.
- Metadata fields are parsed views of the verbatim entry; anything absent in the
  original is absent in the output (no DOI completion, no style reformatting).

## Applicable scope / limits

- One manuscript per case; numeric and author-year citation styles; embedded or separate
  reference lists.
- The engine verifies structural consistency, not the scientific truth of citations;
  claim-citation scope checks are agent verdicts recorded with reasons.
- Reference entries are renumbered/reordered only — conversion between citation styles
  (APA↔GB/T 7714 etc.) is out of scope unless the case demands it.

## Maintenance

`manifest.yaml` lists files; `selftest.py` must stay green; changes go to `changes_log`
and bump the SKILL.md version.

## License

MIT.
