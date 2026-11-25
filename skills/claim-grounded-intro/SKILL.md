---
name: claim-grounded-intro
description: Write introduction & related-work sections where every citation is real, every paraphrase accurate, and every research gap derives from cited works' stated limitations — with a light verification layer (citation existence + verbatim quote backtracking), not heavy coverage metrics. Use for 引言写作、相关工作、研究空白推导、literature review drafting、贡献映射; gaps without ≥2 supporting citations are marked as author judgment, never stated as fact.
metadata:
  version: "1.1.0"
---

# Claim-Grounded Introduction — real citations, derived gaps

You are an agent writing the introduction / related-work of a paper from supplied source
material. What loses points here is not missing metrics — it is **unverifiable writing**:
citations to works that are not in the material, paraphrases that silently change a
claim, and "research gaps" that no cited work actually states. The engine verifies two
things mechanically (citation existence, verbatim quotes); you own the writing quality.

## 0. Non-negotiable rules

1. **Read the real input.** `/input/case.json` (+ `task.md`). Source material may be a
   list of works (with abstracts/passages) in `materials/references/works/papers/text`,
   or an existing draft to extend (`draft/manuscript/source_text`). Read the actual
   content, not labels.
2. **Cite only what exists.** Every work you cite must resolve to a supplied material
   entry (the engine checks). A claim about a work carries a **verbatim quote** (≤240
   chars) from that work's supplied text — the engine re-slices and string-matches.
3. **Gaps are derived, not asserted.** Each gap statement must name the works whose
   stated limitations/uncovered cases imply it (≥2 works preferred), each with a quote
   of the limitation text. If the gap is your inference beyond what works state, label
   it `"type": "author_judgment"` — honest, not hidden.
4. **Paraphrase fidelity.** When summarizing a work: keep its claim's direction and
   strength (a work that "may improve X" is not one that "improves X"). Comparative
   statements between works only when both are cited and the comparison is supported.
5. **Never crash; never reject.** Missing material → `cannot_determine` + reason.
   Verification failures demote to `partial`, listing the offending sentences.
6. **Contract discipline:** every `output_contract` key + `case_id` in result.json.

## 1. Pipeline

```
/input/case.json
  │ run.py --stage collect ──> work/works.json (supplied works: fields + verbatim passages)
  │ YOU write work/draft.json:
  │   {"intro_text": "...", "related_work_text": "...",
  │    "citations": [{"marker": "[1]", "work_key": "smith2020", "quote": "...", "sent_idx": 12}],
  │    "gaps": [{"statement": "...", "support": [{"work_key": "...", "quote": "..."}],
  │              "type": "derived|author_judgment"}],
  │    "contributions": [{"text": "...", "evidence": "…how it maps to the work…"}]}
  │ run.py --stage verify  ──> citation existence + quote re-slice + gap support
  │        (fix what it names; re-run until clean)
  │ run.py --stage finalize ──> /app/output/result.json
  └ audit.py --input /input --output /app/output
```

## 2. Writing rules (what actually earns the points)

**研究背景** — start from the concrete problem, not "in recent years X has attracted
wide attention". Name the technical constraint that makes the problem hard now, with
the citation that states it.

**相关工作组织** — group by problem/method route, not chronologically. For each group:
- one or two sentences on the route's shared idea;
- per work: what it does, on what conditions/data, and its **stated** limitation
  (with quote when the limitation is load-bearing for your gap);
- compare on the SAME dimension across works (data regime, evaluation metric, cost) —
  never a list of disconnected summaries.

**研究空白** — derive from the limitations you just quoted: "A states X fails under Y
[quote]; B's evaluation excludes Y [quote]; therefore the behavior under Y remains
untested." That is a derived gap. State the corresponding contribution right after it.

**贡献映射** — each contribution sentence maps to the actual method/experiment (if the
case supplies a method description, reference its parts; do not invent results).

## 3. Verification (deliberately light)

`run.py --stage verify` checks ONLY:

1. **citation existence** — every `work_key` you cite resolves to a supplied work.
2. **quote backtracking** — every `quote` is a verbatim substring of that work's
   supplied text (re-sliced and matched; paraphrased quotes fail).
3. **gap support** — every `type: derived` gap has ≥1 supporting work with quote
   (≥2 preferred, recorded); `author_judgment` gaps are exempt but counted.

No coverage scores, no precision metrics, no completeness gates — those are the
metrics that historically *lower* scores on this task. Failures demote status to
`partial` with the offending items listed; they never reject the run.

## 4. Failure routes

| Situation | Action |
|---|---|
| No source material | `cannot_determine`, reason `missing_material`, contract keys null |
| Unreadable/empty works | skip + list; write with the readable subset, `status: partial` |
| Quote mismatches | verify names them; fix quotes (shorter, verbatim) and re-verify |
| Draft exists (extend mode) | keep its claims; only add grounded citations |

## 5. Self-check

1. `audit.py` exit 0.
2. Contract keys + `case_id` present.
3. `verification.citation_missing == []` and `quote_mismatch == []`.
4. Every `derived` gap lists its supporting quotes; `author_judgment` count is small
   (≤2) and intentional.
5. `python3 scripts/selftest.py` green locally.

## 6. What this skill will not do

It will not cite a work the material lacks, not paraphrase beyond the quote's support,
not invent a gap no work implies, not pad with completeness scores, and not reject the
whole run when one quote fails. Substance with evidence beats checks without it.
