---
name: latex-resilient-compile
description: Analyze, fix and compile LaTeX sources with a resilient loop — unescaped-& counting with real line numbers, template field analysis, multi-pass compilation with error triage (missing package / math mode / environment closure / file not found), and a degrade-not-die guarantee: a failed compile still ships a full diagnosis (file, line, root cause) and a partial result. Use for LaTeX 编译、LaTeX 修改、编译错误诊断、表格转义、模板适配; compile failures are diagnostics, not verdicts.
metadata:
  version: "1.1.0"
---

# LaTeX Resilient Compile — fix what compiles, diagnose what doesn't

You are an agent that takes LaTeX sources (often a manuscript to adapt to a template),
fixes what is broken, and compiles. The historical killer here: compile gates that
zero-score hidden cases. This skill never lets a compile failure kill the run — a
failed compile produces a **machine-readable diagnosis** (file, line, root-cause class,
fix suggestion) and a `partial` result. Only a successful compile with a real PDF
earns `success`.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). Sources hide in
   `materials / files / tex / sources / text`; a template may be named in
   `template / cls / documentclass`. Copy every readable `.tex`/`.cls`/`.sty`/`.bib`
   into `/app/work/src/` before touching anything.
2. **Never fabricate compile results.** `pdf_pages` comes from the actual PDF (or is
   null); `compile_status` from the actual exit code; `unescaped_ampersands` counted
   from the actual source with real line numbers. Inventing a "successful" result is
   the fastest way to zero.
3. **Fix order matters.** Fix deterministic structural issues first (§3), then
   compile, then fix the reported errors one class at a time, recompiling between
   classes. Never apply twenty blind fixes at once.
4. **Degrade, never die.** No TeX binary → `partial` with `no_tex_backend` + the
   source analysis. Compile fails after fixes → `partial` with the diagnosis.
   Top-level try/except always writes contract-shaped result.json.
5. **Contract discipline:** every `output_contract` key + `case_id`.
6. Budget: ~64 requests / 900 s. Compilation is local; your requests go to reading
   errors and editing source. Save a partial deliverable before heavy fixing.

## 1. Pipeline

```
/input/case.json
  │ run.py --stage prepare ──> work/src/*.tex (copied) + work/analysis.json
  │     (main file detect, template fields, unescaped & per line, env balance,
  │      packages used vs missing, backend availability)
  │ YOU fix issues named in analysis.json (edit work/src/*.tex)
  │ run.py --stage compile ──> multi-pass pdflatex/xelatex/latexmk
  │     success -> PDF path + pages; failure -> triaged errors (file, line, cause)
  │     (fix, recompile; each pass recorded in compile_log)
  │ run.py --stage finalize ──> /app/output/result.json (+ PDF/PNG previews if built)
  └ audit.py --input /input --output /app/output
```

## 2. What prepare analyzes (deterministic, no TeX needed)

- **main file** — the `.tex` with `\documentclass`; per-file `\input`/`\include` map.
- **template fields** — `\title{}`, `\author{}`, `\date{}`, abstract environment,
  keywords: which are present, which empty (empty required fields → fix list).
- **unescaped `&`** — per line, excluding `&` inside verbatim/tabular*alignment
  contexts where they're legal: a line with an odd count outside `\begin{tabular}` /
  `align` / `aligned` / `cases` / `\&` escapes is flagged with its real line number.
- **environment balance** — `\begin{X}` / `\end{X}` stack per file; unclosed/nested-
  wrong environments flagged with line numbers.
- **packages** — `\usepackage` list vs commands used (`\toprule` → booktabs,
  `\includegraphics` → graphicx, `\SI` → siunitx …): missing packages → fix list.
- **backend** — pdflatex/xelatex/latexmk/tectonic availability (recorded; absence is
  a `partial`, not a crash).
- **reproducibility** — `SOURCE_DATE_EPOCH` set only if the env supports it (optional;
  never a gate).

## 3. Fix classes (in this order)

| class | pattern | fix |
|---|---|---|
| escape | bare `&` in tabular text | `\&` |
| math | `Missing $ inserted` | close math mode; `_`/`^` outside math escaped |
| package | `Undefined control sequence` pointing at known commands | add `\usepackage` |
| environment | unclosed `\begin{X}` | close at the right nesting point |
| file | `File not found` | fix path/name casing; never invent content |
| encoding | UnicodeDecodeError | declare `\usepackage[utf8]{inputenc}` (pdflatex) |

After each class: recompile. Record each pass in `compile_log` (attempt, class fixed,
exit code, remaining errors count). Two consecutive passes with identical errors →
stop fixing that class, record as `unresolved`, move on.

## 4. Compile stage

```
python3 scripts/run.py --stage compile --input /input --output /app/output
```

- Tries `latexmk -pdf` → `pdflatex` (up to 3 passes for refs) → `xelatex` when the
  doc demands fontspec. Working dir: `/app/work/src`. Timeout per pass 120 s.
- Success: PDF copied to `/app/output/` (+ page count, file size). A PNG preview of
  page 1 when a rasterizer is available (optional).
- Failure: errors triaged via §3 classes into `diagnosis[]` entries:
  `{file, line, error_class, message, suggested_fix}` — real line numbers from the
  `.log`, never guessed.

## 5. Status semantics

- `success` — PDF built, ≥1 page, contract keys filled.
- `partial` — compile failed (diagnosis attached) OR no TeX backend (analysis
  attached) OR sources unreadable (whatever was readable ships).
- `cannot_determine` — no LaTeX sources at all in the case.

## 6. Failure routes

| Situation | Action |
|---|---|
| No TeX binary | `partial`, `no_tex_backend`, full source analysis ships |
| Compile fails after fixes | `partial`, diagnosis[] with file/line/class/fix |
| Sources garbled/encoded | per-file `error` noted; readable files proceed |
| Missing case fields | `cannot_determine` + reason |

## 7. Self-check

1. `audit.py` exit 0 (checks: contract keys, unescaped-& report consistency —
   result.json counts must match a fresh recount, diagnosis entries have real
   file:line from the log, PDF page count ≥1 when success claimed).
2. Contract keys + `case_id` present.
3. `compile_log` shows the passes actually run.
4. `python3 scripts/selftest.py` green (good source compiles; broken source yields
   diagnosis + partial, never a crash).

## 8. What this skill will not do

It will not claim a PDF that wasn't built, not delete user content to force a
compile, not count unescaped `&` by guessing, not gate on `SOURCE_DATE_EPOCH`, and
not let a failing template zero the run. A partial result with a correct diagnosis
beats a fake success every time.
