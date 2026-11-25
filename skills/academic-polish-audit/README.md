# academic-polish-audit

Academic language polishing with machine-checkable fact preservation — the skill behind
**写作02｜学术语言润色** (product-arena-02).

## What it does

Two modes, one guarantee:

- **edit mode** — you polish the draft (grammar, register, terminology); the engine then
  aligns original↔polished sentence-by-sentence and diffs every fact token.
- **audit mode** — the case supplies an already-polished draft; you do not rewrite it,
  you adjudicate each flagged change (accept grammar fixes, revert fact drift).

The audit is the product: numbers, units, citation markers, figure references, negation
words, hedges and comparatives are compared per aligned pair. A rewrite that upgrades
"may" to "proves" or drops "not" is caught mechanically, and rejected sentences are
automatically reverted to their originals.

## Install / requirements

Python 3.8+, stdlib only (`difflib`, `re`, `json`). No third-party packages.

## Usage

```
# 1. write the texts (or let the engine pick them from case.json)
#    /app/work/original.txt  /app/work/polished.txt

# 2. align + fact-token diff + change table
python3 scripts/run.py --mode audit --input /input --output /app/output \
    --original /app/work/original.txt --polished /app/work/polished.txt

# 3. (audit mode / flagged pairs) adjudicate via /app/work/notes.json
#    {"verdicts": [{"pair": 2, "accept": false, "reason": "negation dropped"}]}

# 4. finalize: merge, revert rejected pairs, write contract-true result.json
python3 scripts/run.py --mode finalize --input /input --output /app/output

# 5. one-command recheck
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (honest-polish and fact-drift scenarios,
verdict revert, contract coverage).

## Input / output

- **Input** `/input/case.json` with the draft in any of `text/draft/source_text/original/
  manuscript/content/body/paragraph`; an optional polished draft in
  `polished/revised/llm_draft/target_text/candidate/edited` switches to audit mode.
- **Output** `/app/output/result.json` — contract keys + `case_id`, `polished_text`,
  per-pair `changes` table, `audit` violations + verdicts, computed `status`.
  Schema: [references/output-contract.md](references/output-contract.md).

## Key methods

- Abbreviation-aware sentence splitter (et al., e.g., Fig., …).
- Similarity-greedy sentence alignment (difflib ratio ≥ 0.35), additions/deletions tracked.
- Fact-token extraction: numbers+units regex, citation markers (numeric and author-year),
  negation/hedge/comparative lexicons (EN+ZH), figure/table references.
- Change classification: `grammar / register / terminology / unit_conversion` vs
  `loss:* / swap:*` (fact-risk); risk rows are the audited ones.
- Sanctioned conversions only (°C→K, %→fraction, approximately→~); rounding is a loss.
- Zero-denominator ratios are `null`, never 0 or 1.
- Verdict-driven revert: rejected pairs are replaced by their original sentences.

## Applicable scope / limits

- One draft (or draft+polished pair) per case; English and Chinese academic prose.
- The engine checks fact-token preservation, not truth of the content; scientific
  validity of claims stays the author's responsibility.
- Stylistic taste beyond the rules in references/edit-rules.md is deliberately not
  automated — the agent applies the listed rules, nothing hidden.

## Maintenance

`manifest.yaml` lists files + sha256; `selftest.py` must stay green; behavior changes go
into `changes_log` in result.json and bump the version in SKILL.md frontmatter.

## License

MIT.
