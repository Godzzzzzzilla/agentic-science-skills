---
name: citation-align-manager
description: Align in-text citations with the reference list, merge duplicate entries with recorded justification, renumber by first occurrence, and verify every step — author-name normalization handles particles (van der Berg, de la Cruz) and compound surnames; metadata is taken verbatim from the original list, missing DOI/volume stays empty, never completed. Use for 参考文献管理、引用对齐、文献去重、编号重排、citation checking、参考文献格式统一.
metadata:
  version: "1.1.0"
---

# Citation Align & Manager — align, merge, renumber, prove it

You are an agent managing citations for an academic manuscript. The mechanical core —
parsing in-text citations, aligning them with the reference list, normalizing author
names, detecting duplicates, renumbering — is deterministic and lives in `scripts/run.py`.
Your judgment is needed only for merge conflicts and claim-citation matching. The final
deliverable is a **updated manuscript + reference list + a merge/renumber/audit trail**
that another party can re-verify with one command.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). The manuscript text may hide
   in `text / draft / manuscript / source_text / content / body`; the reference list may be
   embedded at the end of the text or in a separate field (`references / bibliography /
   refs / citation_list`). Parse both from wherever they are.
2. **Metadata is verbatim or empty.** Authors, title, journal, year, volume, pages, DOI
   come character-for-character from the original reference list. A missing DOI stays
   missing. Never complete, normalize capitalization of titles, or "fix" anything.
3. **Duplicate merging is conservative.** Two entries are the same work only when
   (a) DOIs are equal AND (lead-author surname + year) match, or (b) normalized titles
   match AND (lead-author surname + year) match. Otherwise they stay separate entries
   and the pair is listed as `merge_candidate: unresolved` for you to adjudicate.
4. **Never invent a citation** that the text references but the list lacks: record it as
   `unresolved_citation` with its location. Never drop a citation silently.
5. **Never crash.** Top-level try/except writes a contract-shaped `result.json`
   (`status: partial` + reason). Missing manuscript → `cannot_determine`.
6. **Contract discipline:** every `output_contract` key in `result.json` (null if unknown) + `case_id`.

## 1. Pipeline

```
/input/case.json (text + reference list)
        │
        ▼  run.py --stage align
   work/citation_map.json   (in-text cites, ref entries, matches, duplicates, renumber plan)
        │
        ▼  you adjudicate merge candidates / claim-match conflicts -> work/notes.json
        │
        ▼  run.py --stage finalize
   /app/output/result.json  (updated_text, updated_references, merge_log, audit trail)
        │
        ▼  audit.py  (one-command recheck: numbering, dedup, verbatim metadata, unresolved)
```

## 2. Stage align

```
python3 scripts/run.py --stage align --input /input --output /app/output
```

Produces `work/citation_map.json`:

- **in-text citations** — numeric (`[1]`, `[1,2]`, `[3-5]`, superscript-like) and
  author-year (`(Smith et al., 2020)`, `Smith and Lee (2019)`) with sentence positions.
- **reference entries** — parsed into fields (authors / title / venue / year / volume /
  pages / DOI / type), each carrying `verbatim` = the untouched original entry string.
- **author normalization** — particles kept (`van der Berg` stays one surname; never
  truncated to `van`); compound surnames (`López-García`, `Chen-Wang`); initials order
  (full-first vs initials-first styles) normalized for matching only.
- **match table** — every in-text citation → reference entry (by number or by
  author-year key).
- **duplicate groups** — per §0.3, with `merge_reason`; candidates below that bar are
  `merge_candidate` awaiting your verdict.
- **renumber plan** — first-occurrence order over the whole text; mapping
  old_number → new_number (or author-year → new number).

## 3. Your adjudication

Write `work/notes.json`:

```json
{
  "merge_verdicts": [
    {"group": 1, "action": "merge", "keep": "entry_12", "reason": "same DOI 10.xxxx/yyy, lead author + year match"},
    {"group": 2, "action": "keep_separate", "reason": "preprint vs formal version differ in pagination; case asks conservative"}
  ],
  "claim_citation_checks": [
    {"sentence_index": 41, "citation": "[7]", "verdict": "supported|not_supported|unclear",
     "reason": "the claim about X matches entry 7's title/abstract scope"}
  ]
}
```

Rules: merging needs a stated reason; splitting a merge needs a stated reason; a
`not_supported` claim-citation pair is recorded, not silently re-cited to something else.

## 4. Stage finalize

```
python3 scripts/run.py --stage finalize --input /input --output /app/output \
    --notes /app/work/notes.json
```

Applies verdicts, rewrites the manuscript with new numbering, rewrites the reference
list (deduped, first-occurrence order, each entry's `verbatim` body preserved — only the
leading label changes), and writes `/app/output/result.json` with the contract keys +
`updated_text`, `updated_references`, `merge_log`, `renumber_map`, `unresolved_citations`,
`metadata_verbatim_check`, computed `status`.

## 5. Audit

```
python3 scripts/audit.py --input /input --output /app/output
```

Re-derives the citation set from the updated text and checks: (1) numbering is
sequential from 1 with no gaps; (2) every in-text citation resolves to a list entry;
(3) no duplicate pairs remain under the §0.3 rules; (4) every output entry's metadata
fields appear verbatim in the original list; (5) unresolved citations are listed, not
hidden. Exit 0 = green.

## 6. Failure routes

| Situation | Action |
|---|---|
| No manuscript text | `cannot_determine`, reason `missing_manuscript`, contract keys null |
| No reference list section found | `partial`, reason `missing_reference_list`; citations reported unresolved |
| Mixed/unknown citation styles | both parsers run; matches recorded with `style` tag; unmatched stay unresolved |
| Malformed case.json | `partial`, `malformed_case_json:<err>`, write partial result |
| Merge verdicts missing for candidates | candidates stay separate (conservative), listed in `merge_log` |

## 7. Self-check

1. `audit.py` exit 0.
2. Contract keys present; `case_id` matches.
3. `updated_references` count == distinct citations used in text (+ any explicitly kept-but-uncited entries, listed separately).
4. No metadata field in the output that is absent from the original list.
5. `python3 scripts/selftest.py` green locally.

## 8. What this skill will not do

It will not complete missing DOIs, not reformat entries into a different citation style
unless the case demands renumbering only, not merge on title similarity alone, not
re-cite unsupported claims to different references, and not output a renumbered text
without its renumber map. Alignment you cannot re-check is alignment you cannot trust.
