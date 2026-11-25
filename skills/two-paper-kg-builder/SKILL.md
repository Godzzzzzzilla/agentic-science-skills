---
name: two-paper-kg-builder
description: Build a knowledge graph across two supplied papers — nodes/edges each carrying source_id + paragraph_id + verbatim short quote, cross-paper alias candidates merged only with recorded rationale, conflicts and different-objects preserved (never forcing merges), and at least three actually-executed queries with results and evidence. Use for 知识图谱构建、实体关系抽取、跨篇实体对齐、KG 查询、alias reconciliation; JATS paragraph ids are the locations (no PDF page numbers invented).
metadata:
  version: "1.1.0"
---

# Two-Paper KG Builder — aligned, explainable, queryable

You are an agent building a knowledge graph over **two** supplied papers (primary +
secondary). The material is text (corpus-manifest.json + primary/secondary material
files with JATS paragraph ids) — there are no PDF pages, and you must not invent
page numbers. The grader checks: 抽得准 (entities are real objects from the text),
连得对 (relations typed/directed/conditioned by evidence), 对得齐 (aliases aligned
with rationale; no wrong merges), 查得到回得去 (queries answered; every node/edge
traces back).

## 0. Non-negotiable rules

1. **Read the real inputs.** `/input/case.json` + the material files it names
   (`corpus-manifest`, `primary-material`, `secondary-material`, `material`).
   Each paper keeps its own `source_id`, DOI/title/authors (the root metadata belongs
   to the primary only — never apply it to the secondary).
2. **Every node/edge carries provenance**: `source_id` (paper), `para_id` (JATS id),
   and `quote` (verbatim short quote ≤200 chars from that paragraph). The engine
   re-slices; a quote that isn't verbatim fails.
3. **Cross-paper merges are conservative.** Same concept in both papers merges only
   with `merge_rationale` citing evidence from BOTH sides (e.g. same method name +
   same measured quantity). Different conditions/samples/numerical results in the two
   papers are **different nodes** — record them as `kept_separate` with the reason.
   Never force every alias to merge; unambiguous in-paper abbreviations merge freely
   with rationale.
4. **At least 3 executed queries.** Queries run against the built graph (engine
   executes them); each result carries node/edge references, and every reference must
   exist in the graph.
5. **Never crash; never reject.** Missing paper → build on what exists, `partial`.
   Verification failures demote with named items.
6. **Contract discipline:** every `output_contract` key + `case_id`.

## 1. Pipeline

```
/input/case.json
  │ run.py --stage load ──> work/corpus.json
  │    (papers: source_id, metadata; paragraphs: para_id -> text; manifest check)
  │ YOU extract -> work/graph.json:
  │   {"nodes": [{"node_id": "n1", "label": "...", "type": "method|material|task|metric|finding|person",
  │       "source_id": "primary", "para_id": "s2.3", "quote": "...",
  │       "aliases": ["..."], "merge_rationale": null |
  │         {"with": "n7", "evidence": [{"source_id": "...", "para_id": "...", "quote": "..."}]}}],
  │    "edges": [{"edge_id": "e1", "from": "n1", "to": "n2", "type": "uses|compares|outperforms|supports|contradicts|measures",
  │       "source_id": "primary", "para_id": "s3.1", "quote": "...",
  │       "condition": null | "under X"}],
  │    "kept_separate": [{"entities": ["n3", "n9"], "reason": "different physical samples across papers"}]}
  │ run.py --stage verify ──> provenance re-slice + merge rationale + graph integrity
  │ run.py --stage queries --queries work/queries.json ──> executes ≥3 queries
  │ run.py --stage finalize ──> /app/output/result.json
  └ audit.py --input /input --output /app/output
```

## 2. Extraction rules

1. **抽得准** — entities = objects the text actually names (materials, methods,
   tasks, metrics, findings, named researchers). No commonsense completion ("the
   paper surely used Adam" is fabrication).
2. **连得对** — an edge exists only where a sentence states the relation; direction
   follows the sentence; comparisons carry their condition ("on dataset A").
   Co-occurrence is not an edge.
3. **对得齐** — in-paper alias chains (full name → abbreviation) merge with
   rationale from the definitional sentence. Cross-paper: merge when both sides
   name the same specific object; keep separate when the texts describe different
   samples/conditions/instances even under the same generic name.
4. **查得到** — queries like "which methods measure metric M", "what does paper X
   say about concept C", "list edges contradicting across papers". The engine
   supports label/predicate/type filters; you write the query objects.

Query format (`work/queries.json`):
```json
{"queries": [
  {"q_id": "q1", "type": "by_label", "label": "…", "note": "…"},
  {"q_id": "q2", "type": "by_type", "node_type": "metric", "note": "…"},
  {"q_id": "q3", "type": "edges_of", "node_id": "n1", "note": "…"},
  {"q_id": "q4", "type": "cross_paper", "label": "…", "note": "…"}
]}
```

## 3. Verification (mechanical)

- **provenance** — every node/edge quote re-sliced from its (source_id, para_id).
- **integrity** — edge endpoints exist; node_ids unique; para_ids exist in that
  paper's paragraph set.
- **merges** — every cross-paper merge has evidence from both papers; kept_separate
  entries recorded.
- **queries** — ≥3 queries; each result's node/edge refs exist in the graph.

Failures demote status to `partial` with named items; the run always ships.

## 4. Failure routes

| Situation | Action |
|---|---|
| One paper missing/unreadable | build on the other, `partial` + reason |
| Manifest missing | note it; source_ids from file names; `partial` |
| No JATS ids | positional ids `p1..pN` per paper, recorded as assigned |
| Quote drift | verify names them; shorten to exact substrings |
| Malformed case | `partial` + `malformed_case_json:<err>` |

## 5. Self-check

1. `audit.py` exit 0.
2. Contract keys + `case_id` present.
3. All quotes re-slice; merges carry bilateral evidence; ≥3 queries executed with
   existing references.
4. `python3 scripts/selftest.py` green locally.

## 6. What this skill will not do

It will not borrow the primary's metadata for the secondary, not merge across
different physical samples, not invent PDF pages, not create edges from co-occurrence,
and not answer queries with references to nodes that do not exist.
