# Output contract for result.json

Every `case.json` `output_contract` key (null if unknown) + `case_id`, plus:

```json
{
  "case_id": "…",
  "status": "success | partial | cannot_determine | rejected",
  "status_reasons": ["…"],
  "updated_text": "…manuscript with renumbered citations…",
  "updated_references": [
    {
      "number": 1,
      "verbatim": "L. Chen-Wang, S. Ito and T. Park, Deep learning for precipitation nowcasting, Nature Machine Intelligence, 2022, 4(7): 601-615. doi:10.1038/nmi.2022.050",
      "fields": {"authors": "…", "title": "…", "venue": "…", "year": "…", "volume": "…", "pages": "…", "doi": "…"}
    }
  ],
  "renumber_map": {"2": 3, "3": 1},
  "merge_log": [
    {"group": 0, "action": "merge", "kept": 2, "dropped": [3], "reason": "same DOI 10.1038/nmi.2022.050, lead author + year match"}
  ],
  "unresolved_citations": [{"raw": "[9]", "pos": 412}],
  "claim_citation_checks": [
    {"sentence_index": 41, "citation": "[7]", "verdict": "supported", "reason": "…"}
  ],
  "metadata_verbatim_check": {"violations": []},
  "uncited_entries_kept": [{"number": 5, "verbatim": "…"}],
  "changes_log": [...]
}
```

## Semantics

- **`updated_references[].verbatim`** — the entry text exactly as it appeared in the
  original list; only the leading label `[n]`/`n.` is rewritten. Fields are parsed views
  of that verbatim text, never "improved".
- **`renumber_map`** — old entry index → new number, first-occurrence order over the text;
  uncited entries keep their relative order at the tail.
- **`merge_log`** — every merge/keep decision with its reason. Rule-based merges
  (DOI+author-year, or title+author-year) may pass silently through the engine; candidate
  merges (title/DOI match but author-year mismatch) require your verdict in notes.json
  and default to keep-separate.
- **`unresolved_citations`** — markers in the text that reference nothing in the list.
  They stay in the updated text (never silently dropped) and demote status to `partial`.
- **`claim_citation_checks`** — your per-sentence verdicts on whether a cited claim
  matches the referenced work's scope (supported / not_supported / unclear + reason).
- **`status`** — `success` only with zero unresolved, zero metadata violations, zero
  remaining duplicates; otherwise `partial`; missing manuscript → `cannot_determine`.

## Merge rules (conservative)

same work ⇔ (equal DOI AND lead-author surname + year match) OR
            (normalized title equal AND lead-author surname + year match)

Lead-author surname keeps particles (`van der Berg`, `de la Cruz`) and hyphenated
compounds (`Chen-Wang`); it is never truncated to its particle. Title normalization
lowercases and strips non-alphanumerics for comparison only — the stored entry stays
verbatim. Preprint-vs-formal pairs with different pagination are candidates, not merges.
