# methods-repro-writer

Methods & experimental-section writing with sourced parameters and a reproduction
checklist — the skill behind **写作09｜方法与实验章节写作** (product-arena-05).

## Design principle

Verification is **demote-only**: every check either passes or demotes status to
`partial` with named items. A missing seed/version is `null` + `not_reported` +
a limitations entry — never a rejection, never an invented value. This skill exists
because strict cross-validation (version×round×split gates) historically zero-scored
hidden cases on this task.

## What it does

1. **collect** — parses configs/logs/text: key-value params each carrying
   `source: config:<file>` | `log:<file>` | `not_reported`; environment versions;
   **conflicts** (same param, different values across sources) preserved, never
   silently resolved; canonical slots (seed/epochs/lr/batch_size) value-or-null.
2. **write** — you produce numbered executable steps (input → operation → output →
   condition), separated train/validation/test setups, the repro checklist
   (environment, seed-or-null, command, artifacts), and concrete limitations.
3. **verify + finalize** — tolerant schema sanity; contract-true result.json.

## Usage

```
python3 scripts/run.py --stage collect --input /input --output /app/output
# write -> /app/work/draft.json (schema in SKILL.md §1)
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (yaml+log collection, batch_size conflict
detection, null-seed not_reported handling, audit PASS).

## Install / requirements
Python 3.8+, stdlib only.

## Input / output
- Input: `case.json` (`materials/files/configs/logs` + `text` draft fragments).
- Output: `result.json` — contract keys + `case_id`, `methods_text`, `steps`,
  `params` (sourced), `setup`, `repro`, `limitations`, `conflicts`, computed status.

## Limits
- Reads yaml/ini/json/log/txt/md material; binary artifacts are noted, not parsed.
- Does not run the experiment; repro checklist describes, not executes.

## License
MIT.
