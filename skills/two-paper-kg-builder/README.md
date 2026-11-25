# two-paper-kg-builder

Cross-paper knowledge graph construction with provenance and executed queries — the
skill behind **阅读15｜文献知识图谱构建** (product-arena-10).

## What it does

1. **load** — corpus-manifest + primary/secondary material files resolved per paper,
   each with its own source_id, metadata (DOI/title/authors stay with their own paper),
   and paragraph set (JATS ids when present, positional otherwise — declared).
2. **extract** (you) — nodes/edges each carrying source_id + para_id + verbatim quote;
   in-paper alias merges with definitional rationale; cross-paper merges only with
   bilateral evidence; different runs/conditions/samples stay separate with explicit
   `kept_separate` reasons.
3. **verify** — provenance re-slicing (quote must be verbatim in that paper's named
   paragraph), graph integrity (unique ids, valid endpoints), merge rationale
   bilateral enforcement.
4. **queries** — engine executes by_label / by_type / edges_of / cross_paper against
   the built graph; ≥3 required; results reference existing items only.

## Usage

```
python3 scripts/run.py --stage load --input /input --output /app/output
# extract -> /app/work/graph.json + /app/work/queries.json (schemas in SKILL.md §1)
python3 scripts/run.py --stage queries --input /input --output /app/output
python3 scripts/run.py --stage finalize --input /input --output /app/output
python3 scripts/audit.py --input /input --output /app/output
```

Self-test: `python3 scripts/selftest.py` (two 3-paragraph papers; EdgeNet across
papers found by cross-paper query; batch-size conditions kept separate; quote drift
→ partial).

## Install / requirements
Python 3.8+, stdlib only.

## Input / output
- Input: corpus-manifest.json + primary-material.json + secondary-material.json
  (or case fields); paragraph lists with ids.
- Output: result.json — contract keys + case_id, nodes/edges/kept_separate with
  provenance, executed queries with results, verification, computed status.

## Limits
- Text-only materials (no PDF pages — ids are JATS/positional).
- Query engine supports the four listed types; others error honestly.

## License
MIT.
