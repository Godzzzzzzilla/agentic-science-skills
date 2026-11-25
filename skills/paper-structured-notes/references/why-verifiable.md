# Why verifiable beats verbose

Two kinds of answers look identical to a reader but opposite to a grader:

1. A fluent summary that *claims* to come from the paper.
2. A summary whose every factual token can be re-derived from the paper by one command.

Kind 2 wins because the reviewer cannot distinguish kind 1 from fabrication — and the
scoring rubric explicitly rewards **结果可核验性** (verifiability) and punishes invented
content. This skill's entire design serves that asymmetry:

- **Anchors, not citations.** "Page 5" is a claim; `char_span [1024, 1180)` into a
  machine-extracted page text is a coordinate the audit can slice.
- **Verbatim quotes.** Paraphrase is a lossy channel; the note card's semantic text may
  compress, but its `note_ids` point at exact substrings that survive re-matching.
- **`not_reported` is a feature.** A field the paper does not address is *evidence about
  the paper*, not a gap to fill. Filling it is fabrication; marking it is precision.
- **Computed status.** `success/partial/cannot_determine` is derived from artifacts, so
  the result cannot claim more than it produced.
- **Degrade, never reject.** Missing material, no text layer, malformed case — each has
  a defined partial result with a handoff point. A crashed run produces no evidence at
  all, which is the only strictly worse outcome.

The same principle decides *what not to build*: no completeness metrics that reject
input, no cross-validation strong enough to 0-score a hidden case, no invented numbers
to fill a schema. Each of those raises local precision while destroying robustness on
unseen inputs — a trade this skill systematically refuses.
