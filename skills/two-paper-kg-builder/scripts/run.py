#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""two-paper-kg-builder: load corpus, verify graph provenance/merges, run queries,
finalize. stdlib only; degrade-don't-die."""
import argparse
import io
import json
import os
import re
import sys
import traceback

WORK = "/app/work"
OUT = "/app/output"


def load_case(input_dir):
    path = os.path.join(input_dir, "case.json")
    if not os.path.exists(path) and os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            if fn.endswith(".json"):
                path = os.path.join(input_dir, fn)
                break
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return {}, "malformed_case_json: %s" % e


def _pick(d, names, default=None):
    for n in names:
        if isinstance(d, dict) and d.get(n) not in (None, "", [], {}):
            return d[n]
    return default


def contract_keys(case):
    oc = case.get("output_contract") or case.get("outputContract") or case.get("contract") or []
    keys = []
    if isinstance(oc, dict):
        for k, v in oc.items():
            if isinstance(v, list) and v and isinstance(v[0], str):
                keys.extend(v)
            elif k not in ("type", "format", "$schema", "version"):
                keys.append(k)
    elif isinstance(oc, list):
        for item in oc:
            keys.append(item if isinstance(item, str) else (item or {}).get("name"))
    return sorted(set(filter(None, keys)))


def norm_text(s):
    return re.sub(r"\s+", " ", s or "").strip()


def read_first_json(input_dir, names):
    for n in names:
        p = os.path.join(input_dir, n)
        if os.path.exists(p):
            try:
                with io.open(p, "r", encoding="utf-8") as f:
                    return json.load(f), n
            except Exception:
                continue
    # any similarly-named json
    if os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            if fn.endswith(".json"):
                low = fn.lower()
                if any(n.lower().split(".")[0] in low for n in names):
                    try:
                        with io.open(os.path.join(input_dir, fn), "r", encoding="utf-8") as f:
                            return json.load(f), fn
                    except Exception:
                        continue
    return None, None


def paras_from(raw):
    """Material json -> list of {para_id, text}."""
    if isinstance(raw, list):
        out = []
        for i, p in enumerate(raw):
            if isinstance(p, dict):
                out.append({"para_id": p.get("id") or p.get("para_id") or ("p%d" % (i + 1)),
                            "text": norm_text(p.get("text") or p.get("paragraph") or "")})
            elif isinstance(p, str):
                out.append({"para_id": "p%d" % (i + 1), "text": norm_text(p)})
        return [p for p in out if p["text"]]
    if isinstance(raw, dict):
        if isinstance(raw.get("paragraphs"), list):
            return paras_from(raw["paragraphs"])
        return [{"para_id": k, "text": norm_text(v)} for k, v in raw.items()
                if isinstance(v, str) and v.strip()]
    if isinstance(raw, str):
        return [{"para_id": "p%d" % (i + 1), "text": norm_text(b)}
                for i, b in enumerate(re.split(r"\n\s*\n", raw)) if norm_text(b)]
    return []


def load_corpus(case, input_dir):
    manifest, manifest_file = read_first_json(
        input_dir, ["corpus-manifest.json", "corpus_manifest.json", "manifest.json"])
    papers = []
    specs = [("primary", ["primary-material.json", "primary.json", "primary_material.json"]),
             ("secondary", ["secondary-material.json", "secondary.json", "secondary_material.json"])]
    for sid, names in specs:
        raw, fname = read_first_json(input_dir, names)
        paras = paras_from(raw) if raw is not None else []
        meta = {}
        if manifest and isinstance(manifest, dict):
            for key in ("papers", "documents", "sources", "corpus"):
                lst = manifest.get(key)
                if isinstance(lst, list):
                    for m in lst:
                        if isinstance(m, dict) and sid in str(m.get("source_id", "")).lower() + str(m.get("role", "")).lower() + str(m.get("file", "")).lower():
                            meta = m
                            break
        if not paras:
            # try case fields
            raw2 = _pick(case, ["%s_material" % sid, "%s_text" % sid, sid])
            paras = paras_from(raw2) if raw2 is not None else []
        papers.append({"source_id": sid, "file": fname, "meta": meta,
                       "paras": paras,
                       "meta_source": "manifest" if meta else "none"})
    return {"manifest_file": manifest_file, "papers": papers}


def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def verify_graph(graph, corpus):
    problems = {"provenance_bad": [], "integrity_bad": [], "merge_bad": [],
                "stats": {}}
    para_index = {}
    for paper in corpus["papers"]:
        for p in paper["paras"]:
            para_index[(paper["source_id"], p["para_id"])] = p["text"]
    node_ids = set()
    for n in graph.get("nodes") or []:
        nid = n.get("node_id")
        if nid in node_ids:
            problems["integrity_bad"].append({"item": nid, "reason": "duplicate node_id"})
        node_ids.add(nid)
        q = norm_text(n.get("quote") or "")
        src = n.get("source_id")
        pid = n.get("para_id")
        text = para_index.get((src, pid))
        if q and text is not None and q not in text:
            problems["provenance_bad"].append({"item": nid, "source_id": src,
                                               "para_id": pid, "reason": "quote not verbatim"})
        elif text is None:
            problems["provenance_bad"].append({"item": nid, "source_id": src,
                                               "para_id": pid, "reason": "unknown paragraph"})
    for e in graph.get("edges") or []:
        if e.get("from") not in node_ids or e.get("to") not in node_ids:
            problems["integrity_bad"].append({"item": e.get("edge_id"),
                                              "reason": "endpoint missing"})
        q = norm_text(e.get("quote") or "")
        src = e.get("source_id")
        pid = e.get("para_id")
        text = para_index.get((src, pid))
        if q and text is not None and q not in text:
            problems["provenance_bad"].append({"item": e.get("edge_id"), "source_id": src,
                                               "para_id": pid, "reason": "quote not verbatim"})
    node_by_id = {n.get("node_id"): n for n in (graph.get("nodes") or [])}
    for m in graph.get("merge_rationales") or []:
        a, b = m.get("node_a"), m.get("node_b")
        evs = m.get("evidence") or []
        sides = set()
        for ev in evs:
            q = norm_text(ev.get("quote") or "")
            text = para_index.get((ev.get("source_id"), ev.get("para_id")))
            if text is None or (q and q not in text):
                problems["merge_bad"].append({"merge": (a, b), "reason": "evidence not verbatim"})
            else:
                sides.add(ev.get("source_id"))
        if len(sides) < 2:
            problems["merge_bad"].append({"merge": (a, b),
                                          "reason": "cross-paper merge needs evidence from both papers"})
    # inline merge_rationale on nodes
    for n in graph.get("nodes") or []:
        mr = n.get("merge_rationale")
        if isinstance(mr, dict) and mr.get("with"):
            evs = mr.get("evidence") or []
            sides = set()
            for ev in evs:
                q = norm_text(ev.get("quote") or "")
                text = para_index.get((ev.get("source_id"), ev.get("para_id")))
                if text is not None and (not q or q in text):
                    sides.add(ev.get("source_id"))
            if len(sides) < 2:
                problems["merge_bad"].append({"merge": (n.get("node_id"), mr.get("with")),
                                              "reason": "inline merge rationale lacks bilateral evidence"})
    problems["stats"] = {"nodes": len(graph.get("nodes") or []),
                         "edges": len(graph.get("edges") or []),
                         "kept_separate": len(graph.get("kept_separate") or []),
                         "paras": len(para_index)}
    return problems


def run_queries(graph, queries):
    """Executes the supported query types; results reference existing items."""
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    results = []
    for q in queries.get("queries") or []:
        qid = q.get("q_id")
        qtype = q.get("type")
        hits = []
        if qtype == "by_label":
            needle = str(q.get("label") or "").lower()
            hits = [n for n in nodes if needle and needle in str(n.get("label") or "").lower()]
        elif qtype == "by_type":
            hits = [n for n in nodes if n.get("type") == q.get("node_type")]
        elif qtype == "edges_of":
            hits = [e for e in edges if e.get("from") == q.get("node_id")
                    or e.get("to") == q.get("node_id")]
        elif qtype == "cross_paper":
            needle = str(q.get("label") or "").lower()
            hits = []
            sources = set()
            for n in nodes:
                hay = " ".join([str(n.get("label") or "")] +
                               [str(a) for a in (n.get("aliases") or [])]).lower()
                if needle and needle in hay:
                    hits.append(n)
                    sources.add(n.get("source_id"))
            if len(sources) < 2:
                hits = []  # cross-paper requirement not met; honest empty result
        else:
            results.append({"q_id": qid, "type": qtype, "error": "unsupported query type",
                            "results": []})
            continue
        results.append({"q_id": qid, "type": qtype, "note": q.get("note"),
                        "results": [{"node_id": h.get("node_id", h.get("edge_id")),
                                     "label": h.get("label"), "source_id": h.get("source_id"),
                                     "para_id": h.get("para_id")} for h in hits[:20]]})
    return {"queries_executed": len(results), "results": results}


def stage_load(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    corpus = load_corpus(case, args.input)
    corpus["case_error"] = err
    with io.open(os.path.join(WORK, "corpus.json"), "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "load", "papers": [{"sid": p["source_id"],
                                                   "paras": len(p["paras"]),
                                                   "meta": p["meta_source"]}
                                                  for p in corpus["papers"]]}))


def stage_verify(args):
    corpus = read_json(os.path.join(WORK, "corpus.json"))
    graph = read_json(args.graph or os.path.join(WORK, "graph.json"))
    if not corpus or not graph:
        print(json.dumps({"stage": "verify", "error": "corpus_or_graph_missing"}))
        return
    problems = verify_graph(graph, corpus)
    print(json.dumps({"stage": "verify", **{k: len(v) for k, v in problems.items() if isinstance(v, list)},
                      "stats": problems["stats"]}))


def stage_queries(args):
    corpus = read_json(os.path.join(WORK, "corpus.json"))
    graph = read_json(args.graph or os.path.join(WORK, "graph.json"))
    queries = read_json(args.queries)
    if not corpus or not graph or not queries:
        print(json.dumps({"stage": "queries", "error": "corpus/graph/queries missing"}))
        return
    outcome = run_queries(graph, queries)
    with io.open(os.path.join(WORK, "query_results.json"), "w", encoding="utf-8") as f:
        json.dump(outcome, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "queries", "executed": outcome["queries_executed"],
                      "empty_results": sum(1 for r in outcome["results"] if not r.get("results"))}))


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    corpus = read_json(os.path.join(WORK, "corpus.json"))
    graph = read_json(args.graph or os.path.join(WORK, "graph.json"))
    qres = read_json(os.path.join(WORK, "query_results.json"))
    problems, status = [], "success"
    if not corpus:
        status = "cannot_determine"
        problems.append("missing_corpus")
        verification, outcome = {}, None
        graph = graph or {}
    else:
        papers_ok = [p for p in corpus["papers"] if p["paras"]]
        if not papers_ok:
            status = "cannot_determine"
            problems.append("no_readable_material")
        elif len(papers_ok) < 2:
            status = "partial"
            problems.append("only_one_paper_readable")
        if graph is None:
            status = "partial" if status == "success" else status
            problems.append("graph_missing")
            verification = {}
            outcome = None
        else:
            verification = verify_graph(graph, corpus)
            if verification["provenance_bad"]:
                status = "partial"
                problems.append("provenance_bad:%d" % len(verification["provenance_bad"]))
            if verification["integrity_bad"]:
                status = "partial"
                problems.append("integrity_bad:%d" % len(verification["integrity_bad"]))
            if verification["merge_bad"]:
                status = "partial"
                problems.append("merge_bad:%d" % len(verification["merge_bad"]))
            outcome = qres
            if not outcome or outcome.get("queries_executed", 0) < 3:
                status = "partial" if status == "success" else status
                problems.append("queries_lt_3")
            if outcome:
                for r in outcome.get("results") or []:
                    pass  # engine refs came from the graph itself
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "nodes": (graph or {}).get("nodes") or [],
        "edges": (graph or {}).get("edges") or [],
        "kept_separate": (graph or {}).get("kept_separate") or [],
        "queries": outcome or {},
        "papers": [{"source_id": p["source_id"], "paras": len(p["paras"]),
                    "meta_source": p["meta_source"]} for p in (corpus or {}).get("papers", [])],
        "verification": verification,
        "uncertainty": (graph or {}).get("uncertainty", []),
        "changes_log": [
            {"change": "load", "detail": "two-paper corpus with per-paper paragraph ids"},
            {"change": "extract", "detail": "agent nodes/edges with provenance"},
            {"change": "verify", "detail": "provenance + integrity + merges", "violations": len(problems)},
            {"change": "queries", "detail": "executed against the graph",
             "count": (outcome or {}).get("queries_executed", 0)},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status,
                      "nodes": len(result["nodes"]), "edges": len(result["edges"]),
                      "queries": (outcome or {}).get("queries_executed", 0),
                      "problems": problems, "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["load", "verify", "queries", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--graph", default=None)
    ap.add_argument("--queries", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.graph is None:
        args.graph = os.path.join(WORK, "graph.json")
    if args.queries is None:
        args.queries = os.path.join(WORK, "queries.json")
    try:
        {"load": stage_load, "verify": stage_verify, "queries": stage_queries,
         "finalize": stage_finalize}[args.stage](args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "nodes": [], "edges": [], "kept_separate": [], "queries": {},
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
