# Edit rules — with change-type labels

Each rule shows: pattern → fix → change-type label for the change table.
Labels feed the audit; `loss:*`/`swap:*` labels are fact-risk and get adjudicated.

## Grammar (type: `grammar`)

| pattern | fix | example |
|---|---|---|
| subject–verb disagreement | match number | "The result … are" → "The results … are" |
| tense inconsistency | pick the paragraph's dominant tense (methods: past; facts: present) | "did not showed" → "did not show" |
| wrong article | a/an/the per first sound / definiteness | "a hour" → "an hour" |
| which→that in restrictive clauses | remove comma + which | "samples, which was treated" → "samples that were treated" |
| dangling modifier | reattach subject | "Using X, the peak increased" → "Using X, we observed an increased peak" |
| run-on sentence | split at coordinating conjunction | two sentences |
| double negative in passive | "did not showed" → "did not show" | verb form after auxiliary |
| comma splice | semicolon or split | |

## Register (type: `register`)

| wordy | tight |
|---|---|
| due to the fact that | because |
| in order to | to |
| a majority of | most |
| it is possible that | X may |
| utilized | used |
| prior to | before |
| at this point in time | currently |

## Terminology consistency (type: `terminology`)

- One concept, one surface form. Build the term map while editing; apply globally.
- Abbreviation: expand at first use, abbreviate after ("quantitative PCR (qPCR)").
- Capitalization/hyphenation follow the draft's dominant convention, not the editor's taste.

## Fact-risk edits (types the audit flags — do NOT do these silently)

- `loss: number` — any numeric token in the original that vanishes in the aligned sentence.
- `loss: unit` — unit dropped or changed (5 mM → "5").
- `loss: citation` — `[3]` or `(Smith et al., 2020)` dropped.
- `loss: figure_reference` — "Figure 2" → "the figure".
- `loss: negation` — "did not show" → "showed". **The classic fatal edit.**
- `swap: hedge_stronger` — may→does / suggest→prove / possible→certain. Claim inflation.
- `swap: hedge_weaker` — does→may. Claim weakening (only under explicit instruction).

## Sanctioned conversions (type: `unit_conversion`)

- °C → K: +273.15
- % → 0–1 fraction: ÷100 (both forms kept in the change table)
- "approximately X" → "~X" / "ca. X": same value, register only

Rounding is NOT sanctioned: 30.1% → 30% is `loss: number`.

## Zero-change policy

A correct sentence stays byte-identical and appears in the table as `unchanged`.
A fully correct draft yields an empty change table with `status: success` — that is a
valid, honest outcome, not a failed job.
