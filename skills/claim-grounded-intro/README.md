# claim-grounded-intro

Introduction & related-work writing with grounded citations and derived gaps — the
skill behind **写作08｜引言与相关工作写作** (product-arena-04).

## What it does

- Collects the supplied works (fields + verbatim passages) into `work/works.json`.
- You write `intro_text` / `related_work_text` plus structured `citations`
  (marker → work_key → verbatim quote), `gaps` (derived from quoted limitations,
  with support; honest `author_judgment` when inference goes beyond the sources),
  and `contributions` (mapped to the actual work).
- Verification is deliberately light: citation existence, verbatim quote
  backtracking, gap support. No coverage scores, no precision metrics — the
  historically score-lowering additions are excluded by design.

## Usage

```
python3 scripts/run.py --stage collect --input /input --output /app/output
# write -> /app/work/draft.json (schema in SKILL.md §1)
python3 scripts/run.py --stage verify --input /input --output /app/output
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (grounded draft passes; fabricated work +
paraphrased quote + unsupported gap produce violations + partial).

## Install / requirements
Python 3.8+, stdlib only.

## Input / output
- Input: `case.json` with `works/references/papers/materials/literature` (list of
  dicts with title/authors/year/text or plain strings).
- Output: `result.json` — contract keys + `case_id`, texts, citations, gaps,
  contributions, verification, computed status.

## Limits
- Only supplied works are citable; quotes must be verbatim substrings.
- One paper's framing per case; no citation-style reformatting.

## License
MIT.
