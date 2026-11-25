# latex-resilient-compile

Resilient LaTeX analysis, fixing and compilation — the skill behind
**写作13｜LaTeX 写作与编译** (product-arena-07).

## Design principle

A compile failure is a **diagnosis**, not a verdict. Every path ships a contract-true
result.json: compiled PDFs with page counts, or triaged errors (file, line, class,
suggested fix), or an honest `no_tex_backend` partial with the full source analysis.
No gate ever zeroes the run.

## What it does

1. **prepare** (no TeX needed) — main-file detection, template fields (title/author/
   date/abstract presence+emptiness), unescaped-`&` counting with real line numbers
   (verbatim + legal alignment contexts excluded), environment balance, package
   usage vs missing packages, backend availability.
2. **compile** — latexmk → pdflatex (≤3 passes) → xelatex → tectonic; success copies
   the PDF (+page count); failure triages the log into diagnosis entries.
3. **fix loop** (agent) — fix classes in order (escape → math → package →
   environment → file → encoding), recompile after each class; identical errors
   twice = unresolved, move on.

## Usage

```
python3 scripts/run.py --stage prepare --input /input --output /app/output
# fix work/src/*.tex per analysis.json
python3 scripts/run.py --stage compile --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (broken source → diagnosis + partial, no
crash; good source → success when a TeX backend exists).

## Install / requirements
Python 3.8+, stdlib. TeX binaries (pdflatex/latexmk/xelatex/tectonic) probed at
runtime — absence is an honest partial, never a crash. PyMuPDF optional (page count).

## Limits
- Diagnoses cover the common error classes; exotic errors still surface as
  `latex_error` with the log message.
- Does not invent missing files; `file_not_found` entries say what to fix.

## License
MIT.
