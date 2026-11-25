# nanopub-assertion-miner

Atomic scientific assertions with bound verbatim evidence — the skill behind
**阅读14｜Nanopublication** (product-arena-09).

## What it does

1. **collect** — resolves material into paragraphs with ids (JATS `id=` attributes
   when present, positional `p1..pN` otherwise, recorded as such). JATS XML, JSON
   paragraph dicts/lists, and plain text all supported.
2. **decompose** (you) — atomic subject–predicate–object assertions with qualifiers
   separated, each bound to a verbatim ≤240-char quote in a named paragraph, with
   provenance (title/authors/year/version — null when the material lacks them) and
   honest `uncertainty` for unsupported conclusions.
3. **verify + finalize** — schema field-exactness (contract keys per assertion,
   nulls allowed / missing keys not), quote re-slicing from the actual paragraphs,
   atomicity hints for multi-clause objects (hints, not verdicts), light direction
   confirmation only.

## Usage

```
python3 scripts/run.py --stage collect --input /input --output /app/output
# write -> /app/work/assertions.json (schema in SKILL.md §1)
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (JATS parsing, grounded assertions pass;
drifted quote + unknown paragraph id produce partial).

## Install / requirements
Python 3.8+, stdlib only.

## Input / output
- Input: `case.json` — material in `material/text/document/paper` (JATS string, JSON
  paragraph dict/list) or .xml/.nxml/.txt/.md files.
- Output: `result.json` — contract keys + `case_id`, `assertions` (field-exact),
  `provenance`, `verification`, `uncertainty`, computed status.

## Limits
- Direction checks are confirmatory only; the engine flags, you judge.
- No inference of paragraph ids beyond positional assignment (declared).

## License
MIT.
