---
name: translate-with-glossary-lock
description: Translate scientific papers paragraph-by-paragraph with a locked bilingual glossary — segments the source with anchors, extracts terminology candidates, translates with carried context, then machine-verifies paragraph coverage (no missing/duplicated/shifted paragraphs), term consistency (one concept = one translation everywhere), and number/unit/citation preservation per aligned pair. Use for 文献翻译、论文翻译、术语表、双语对照、translation checking; every paragraph maps back to its source anchor; untranslated segments are listed, never silently skipped.
metadata:
  version: "1.1.0"
---

# Translate with Glossary Lock — coverage, consistency, evidence

You are an agent translating a scientific paper (typically EN→ZH). The grader checks
four things mechanically: **术语稳** (one term = one translation, everywhere), **段落全**
(no missing/duplicated/shifted paragraphs), **关系准** (numbers, units, negations,
citation markers preserved), **可核验** (every translated paragraph points back to its
source). The engine (`scripts/run.py`) does segmentation, glossary extraction, and all
four verifications; you do the actual translating.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). Source text hides in
   `text / draft / source_text / original / content / body / paper`; a target language
   may be named in `target_language / language / to`. Default: EN source → ZH target.
   If a glossary is supplied (`glossary / term_table / terminology`), use it verbatim as
   the seed and do not contradict it.
2. **Translate every segment.** No silent skips. A segment you cannot translate well
   still gets a best-effort translation plus `uncertain: true` and a reason.
3. **Never invent content.** Numbers, units, citation markers, negations, and hedges in
   the translation must match the source (the engine diffs them; additions/losses are
   violations). Do not "improve" the science.
4. **Never crash.** Top-level try/except writes a contract-shaped `result.json`
   (`status: partial` + reason). Missing source → `cannot_determine`.
5. **Contract discipline:** every `output_contract` key + `case_id` in result.json.
6. Budget: ~64 requests / 900 s. Translate in batches of ~6-10 paragraphs per request;
   carry the glossary and the previous paragraph as context.

## 1. Pipeline

```
/input/case.json
   │ run.py --stage segment ──> work/segments.json (para units + anchors)
   │                            work/glossary.json (term candidates, locked pairs)
   │ YOU translate: write work/translation.json (para pairs + glossary updates)
   │ run.py --stage verify  ──> coverage + glossary-execution + fact-token checks
   │        (fix what it names; re-run until clean)
   │ run.py --stage finalize ──> /app/output/result.json
   └ audit.py --input /input --output /app/output   (one-command recheck)
```

## 2. Stage segment

```
python3 scripts/run.py --stage segment --input /input --output /app/output
```

- Splits the source into paragraph units (blank-line + heading aware), each with
  `para_id` (1-based), `section`, `char_span` into the source, and `word_count`.
- Extracts **terminology candidates**: capitalized multi-word phrases, repeated
  noun phrases (≥3 occurrences), domain markers (units, methods, species-like Latin
  names). Each candidate gets occurrences and suggested contexts.
- Writes `work/glossary.json` with `locked: {}` (you fill) and `candidates: {...}`.

## 3. Your translation pass — quality rules

Write `work/translation.json`:

```json
{
  "glossary": {"deep learning": "深度学习", "U-Net": "U-Net", "van der Berg": "范德贝格"},
  "paragraphs": [
    {"para_id": 1, "translation": "…", "uncertain": false, "note": null},
    {"para_id": 2, "translation": "…", "uncertain": true,
     "note": "source sentence truncated in material; translated the visible part"}
  ]
}
```

Translation quality rules (these decide the style score — apply every paragraph):

1. **术语锁定** — look up every glossary term before writing; if you introduce a new
   term translation, add it to `glossary` in the same pass. One concept, one rendering:
   the SAME source term never gets two different translations (the engine checks
   paragraph-level term mapping; a second rendering is a violation).
2. **句法重组** — reorder to natural target-language syntax: EN passive often becomes
   ZH active ("the samples were analyzed" → "我们对样品进行了分析" or "分析样品时…");
   long relative clauses become前置定语或拆句; keep logical subject–verb proximity.
3. **限定词忠实** — may/might/suggest ≈ 可能/或许/表明 (not 证明); only ≈ 仅; no data
   negation flips (not → 未, never dropped).
4. **数字/单位/引用** — copy exactly: `5 mM`, `25 °C`, `[3]`, `(Smith et al., 2020)`,
   `Figure 2` → `图 2`(with the number unchanged). Units stay in original form.
5. **长句拆分** — split at clause boundaries when the ZH sentence would exceed ~60
   characters; keep the split INSIDE the paragraph (never merge paragraphs).
6. **标题/图注** — translate them too (they are segments like any other).

## 4. Stage verify + finalize

```
python3 scripts/run.py --stage verify --input /input --output /app/output
python3 scripts/run.py --stage finalize --input /input --output /app/output
```

verify checks (each failure names the para_id and the fix):

- **coverage** — every `para_id` 1..N translated exactly once; extra ids flagged.
- **glossary execution** — for each locked term: every occurrence paragraph uses its
  locked rendering; term mapping is a function (one source term → one target string).
- **fact tokens** — per paragraph: numbers (with units), citation markers, figure refs
  preserved; negation count not reduced to zero; hedge words not upgraded to strong
  claims (`prove/证明` where source has `suggest`).
- **anchors** — para_id → source char_span re-sliced from the material.

finalize writes `/app/output/result.json`: contract keys + `case_id`, `translations`
(para_id, translation, anchors, uncertain), `glossary` (final locked pairs),
`verification` (coverage/glossary/fact checks with violations), computed `status`
(`success` only when coverage 100% + zero violations; else `partial`).

## 5. Audit

```
python3 scripts/audit.py --input /input --output /app/output
```

Re-runs the same four checks independently against the source and result.json.
Exit 0 = green. Fix what it names, re-finalize, re-audit.

## 6. Failure routes

| Situation | Action |
|---|---|
| No source text | `cannot_determine`, reason `missing_source_text`, contract keys null |
| Garbled/truncated source | flag affected paragraphs `uncertain: true` + note; coverage still complete |
| Glossary conflict (same term, two renderings in draft) | verify names them; pick one and re-verify |
| Partially unreadable material | translate the readable span; `status: partial` with `unreadable_span` reason |
| Malformed case.json | `partial` + `malformed_case_json:<err>` |

## 7. Self-check

1. `audit.py` exit 0.
2. Contract keys + `case_id` present.
3. `verification.coverage.missing == []` and `extra == []`.
4. Zero `glossary_violations`; any remaining fact-token warnings adjudicated in notes.
5. `python3 scripts/selftest.py` green locally.

## 8. What this skill will not do

It will not skip hard paragraphs, not merge or split paragraph units, not invent a
translation for unreadable text (it marks `uncertain`), not let one term drift across
two renderings, and not upgrade hedges. A translation the grader cannot re-verify
paragraph-by-paragraph is a translation that did not happen.
