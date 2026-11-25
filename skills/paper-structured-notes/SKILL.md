---
name: paper-structured-notes
description: Build verifiable, section-grounded reading notes from a scientific paper: extract full text with page anchors, cut it into per-section note cards (research question / data / method conditions / main findings / limitations / assumptions), and bind every card to exact character-span anchors that an audit script can re-slice from the source. Use for 文献总结、结构化笔记、论文卡片、逐节笔记、六字段阅读卡片; fields the paper does not report are marked not_reported, never invented.
metadata:
  version: "1.1.0"
---

# Paper Structured Notes — source-grounded reading cards

You are an agent that must turn one scientific paper into **re-checkable structured notes**. The grader does not trust prose; it re-runs one audit command against the source material. Everything you produce therefore either (a) comes verbatim from the source with a machine-checkable anchor, or (b) is explicitly marked `not_reported` / `uncertain`. There is no third kind of content.

## 0. Non-negotiable rules

1. **Read the real input.** First read `/input/case.json` (and the `task.md` next to it if present). Resolve the material paths it declares — PDF, plain text, JATS XML, or JSON — and read those files. Never assume content from a label like "paper" or "intro".
2. **Never fabricate.** If the paper does not state a field, write `not_reported`. If a value is ambiguous, quote both readings and mark `uncertain`. Fabrication is the single fastest way to lose points.
3. **Never reject the whole run.** If material is missing, unreadable, or the case looks malformed, still write `/app/output/result.json` with `status` = `partial` or `cannot_determine` plus the reason and the exact file/step where it failed. A missing field is a `null`, not a crash.
4. **Honor the contract.** `result.json` must contain every field listed in `case.json`'s `output_contract` (same keys), plus `case_id`. Unknown extra fields are allowed; missing contract fields are not.
5. **Budget discipline.** You have ~64 model requests and ~900 s. Extraction, anchoring, and verification are done by `scripts/run.py` (deterministic, stdlib-only). Reserve your own reasoning for the semantic cards.
6. Work under `/app/work` (create it). Final artifacts go to `/app/output`.

## 1. Pipeline overview

```
/input/case.json ──> run.py --stage extract ──> /app/work/segments.json
                                              (pages, sections, paragraphs, char anchors)
        you read segments.json, write /app/work/notes.json  (semantic cards, note_ids)
                     ──> run.py --stage finalize ──> /app/output/result.json
                     ──> audit.py ──> PASS / FAIL report (exit code)
```

## 2. Stage extract — deterministic grounding

Run:

```
python3 scripts/run.py --input /input --output /app/output --stage extract
```

What it does (all stdlib; multi-backend fallback):

- Parses `/input/case.json`; tolerates alias fields (`text` / `draft` / `source_text` / `original` / `materials` / `files`), missing fields, and extra files.
- Extracts text per page: tries PyMuPDF → pdfminer → pypdf → `pdftotext` (subprocess) for PDFs; reads `.txt`/`.md`/`.json`/`.xml` directly. Records which backend ran and per-page char counts.
- Detects section headers page by page (numbered headings `1.`, `2.1`, `Introduction`, `Abstract`, …, and Chinese equivalents), then splits paragraphs on blank lines (`"\n\n"` — never single `\n`, otherwise anchor offsets shift).
- Emits `/app/work/segments.json`: for every paragraph — `page`, `section`, `para_index`, `text`, and `char_span` = `[start, end)` into that **page's extracted text** (the unit the audit re-slices), plus a page-level `page_chars` map.
- Emits `/app/work/case_meta.json` with `case_id`, resolved material paths, output_contract keys, extraction backend, and any anomalies (0-char pages, no text layer, encrypted PDF).

**If the PDF has no text layer**, `segments.json` still gets written with `anomaly: no_text_layer` and per-page empty text. Follow the failure route in §6.

Check the console summary: it prints `pages`, `paragraphs`, `sections`, `backend`, `anomalies`. If paragraphs = 0, go to §6 before anything else.

## 3. Your semantic pass — the note cards

Read `/app/work/segments.json` and fill **one card per paper section** (skip reference list and acknowledgements) into `/app/work/notes.json`:

```json
{
  "cards": [
    {
      "section": "Results",
      "page": 5,
      "research_question": {"text": "...", "note_ids": [12]},
      "data":           {"text": "...", "note_ids": [13]},
      "method_conditions": {"text": "n=3, 25 °C, pH 7.4 (as stated)", "note_ids": [14]},
      "main_findings":  {"text": "...", "note_ids": [15, 16]},
      "limitations":    {"text": "...", "note_ids": [17]},
      "assumptions":    {"text": "...", "note_ids": [18]}
    }
  ],
  "notes": [
    {"note_id": 12, "para_index": 12, "page": 5, "quote": "…≤240 chars verbatim slice…"}
  ]
}
```

Rules that decide your score:

- **Every field value must carry ≥1 `note_id`** whose `quote` is a *verbatim substring* of the `segments.json` paragraph it points to. The audit re-slices and string-matches it; paraphrases fail the audit.
- A field the section genuinely does not address → `"text": "not_reported", "note_ids": []`.
- `note_id` list must be minimal-sufficient: the paragraphs that actually support the claim, not everything nearby.
- `quote` length ≤ 240 chars, cut at word boundaries. Prefer the exact sentence over a fragment.
- Card summaries are your prose, but each factual token (numbers, units, conditions, species, instruments) must appear in the quoted evidence. Write numbers exactly as the source renders them (`25 °C`, not `298 K`, unless you also quote the conversion).
- If two paragraphs conflict, put both notes and set the field `text` to `"conflicting: <short>"` with both `note_ids`; do not silently pick one.

Full schema: [references/output-contract.md](references/output-contract.md). Worked example: [references/example.md](references/example.md).

## 4. Stage finalize — contract-true result.json

```
python3 scripts/run.py --input /input --output /app/output \
  --stage finalize --notes /app/work/notes.json
```

This merges cards + notes + case meta into `/app/output/result.json`:

- includes **every `output_contract` key** from the case (missing ones stay `null`, never dropped);
- adds `case_id`, `cards`, `notes` (with anchors), `evidence` (page/section/char spans), `status` (computed from artifacts, not hand-written), `uncertainty`, `extraction` (backend, anomalies), `changes`;
- validation problems (bad anchor, wrong span, quote mismatch) are **reported and demoted to `partial`**, never used to reject the output.

## 5. Audit — the one command the grader trusts

```
python3 scripts/audit.py --input /input --output /app/output
```

It re-slices every `note.quote` from the **source material** using the recorded page + char span, and string-matches; checks contract-key coverage, note_id references, `not_reported` discipline, and status consistency. Exit 0 = green; non-zero prints the offending note/field with the delta. **Run it, fix what it names, re-run until exit 0.** Do not submit a red audit.

## 6. Failure routes (keep the run alive)

| Situation | What to do |
|---|---|
| No text layer / scanned PDF | Write `result.json` with `status: "cannot_determine"`, `reason: "no_text_layer"`, list pages that failed, output contract keys as `null`. Mark where a human can take over (`handoff: "OCR required for pages 3-7"`). |
| `case.json` unreadable | Same, `reason: "malformed_case_json"` + the parse error string. |
| Material file missing | `status: "partial"`, `reason: "missing_material:<path>"`, still produce cards for the parts you did read. |
| Truncated / garbled text | Flag `anomaly: low_confidence_extraction` per page; mark affected cards' fields `uncertain`. |
| Empty output_contract | Emit the standard fields (cards/notes/evidence/status/...) plus `case_id`. |

## 7. Self-check before finishing

1. `audit.py` exit 0.
2. `python3 -c "import json;d=json.load(open('/app/output/result.json'));assert d['case_id'];print(sorted(d))"` — every contract key present.
3. Count `not_reported` fields — they are legitimate, but a card with *all six* `not_reported` means you mis-picked the section; drop that card instead.
4. `selftest.py` locally verifies the pipeline on a bundled synthetic case (2 pages, 2 sections); it must pass before you trust the runtime.

## 8. What this skill deliberately does NOT do

It does not invent missing data, does not summarize sections it did not actually read, does not merge conflicting claims, does not beautify quotes, and does not output prose walls without anchors. Its entire value is that **another party can re-verify every note with one command** — see [references/why-verifiable.md](references/why-verifiable.md).
