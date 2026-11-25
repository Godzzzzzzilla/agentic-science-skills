# Worked example (synthetic, marked as example)

Input `paper.txt` (excerpt):

```
1. Introduction

Rainfall nowcasting remains a hard problem. Traditional optical-flow
methods degrade quickly at lead times beyond 60 minutes.
```

`run.py --stage extract` emits `segments.json`:

```json
{
  "paragraphs": [
    {"page": 1, "section": "1. Introduction", "para_index": 2,
     "text": "Rainfall nowcasting remains a hard problem. Traditional optical-flow methods degrade quickly at lead times beyond 60 minutes.",
     "char_span": [184, 322]}
  ],
  "sections": [{"section": "1. Introduction", "page": 1, "para_index": 2}]
}
```

The agent's semantic pass writes `notes.json`:

```json
{
  "notes": [
    {"note_id": 1, "para_index": 2, "page": 1,
     "quote": "Traditional optical-flow methods degrade quickly at lead times beyond 60 minutes."}
  ],
  "cards": [
    {"section": "1. Introduction", "page": 1,
     "research_question": {"text": "Why optical-flow nowcasting degrades beyond 60-minute lead times.", "note_ids": [1]},
     "data": {"text": "not_reported", "note_ids": []},
     "method_conditions": {"text": "not_reported", "note_ids": []},
     "main_findings": {"text": "not_reported", "note_ids": []},
     "limitations": {"text": "not_reported", "note_ids": []},
     "assumptions": {"text": "not_reported", "note_ids": []}}
  ]
}
```

`run.py --stage finalize` validates + merges into `result.json` (contract keys filled,
anchors attached, status computed). `audit.py` then re-slices the quote from `paper.txt`
and confirms it is verbatim → `PASS`.

Note what makes this card trustworthy: the quote is byte-identical to the source, the
span is machine-assigned, and `not_reported` marks the fields this section truly does
not address. Nothing is summarized beyond what the quote supports.

This example is synthetic (selftest case), not a formal benchmark result.
