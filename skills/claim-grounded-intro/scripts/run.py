#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim-grounded-intro: collect works, verify citations/quotes/gaps, finalize.

Deliberately light verification (citation existence + verbatim quotes + gap support).
stdlib only; never rejects; missing -> null / partial.
"""
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


def collect_works(case, input_dir):
    """Extract supplied works: (work_key, fields, full_text)."""
    works = []
    raw = _pick(case, ["works", "references", "papers", "materials", "literature"])
    if isinstance(raw, list):
        for i, w in enumerate(raw):
            if isinstance(w, dict):
                title = w.get("title") or w.get("name") or ("work_%d" % (i + 1))
                text = w.get("text") or w.get("abstract") or w.get("passage") or w.get("content") or ""
                key = re.sub(r"[^a-z0-9]+", "", (str(w.get("key") or title)).lower())[:40] or ("work_%d" % (i + 1))
                works.append({"work_key": key, "title": title,
                              "authors": w.get("authors") or w.get("author") or "",
                              "year": str(w.get("year") or ""),
                              "text": text})
            elif isinstance(w, str) and len(w) > 40:
                works.append({"work_key": "work_%d" % (i + 1), "title": w[:60],
                              "authors": "", "year": "", "text": w})
    # fallback: whole-text files in input dir
    if not works and os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, fn)
            if fn.lower().endswith((".txt", ".md")) and fn != "task.md":
                with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                    works.append({"work_key": os.path.splitext(fn)[0][:40], "title": fn,
                                  "authors": "", "year": "", "text": f.read()})
    return works


def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def verify(draft, works):
    """Light checks: citation existence, quote backtracking, gap support."""
    by_key = {w["work_key"]: w for w in works}
    problems = {"citation_missing": [], "quote_mismatch": [], "gap_support": [],
                "counts": {}}
    # gather text per work (verbatim check pool)
    texts = {k: norm_text(w.get("text") or "") for k, w in by_key.items()}
    n_cites = n_quotes = 0
    for c in draft.get("citations") or []:
        k = c.get("work_key")
        if k not in by_key:
            problems["citation_missing"].append({"marker": c.get("marker"), "work_key": k})
            continue
        n_cites += 1
        q = norm_text(c.get("quote") or "")
        if q:
            n_quotes += 1
            if q not in texts.get(k, ""):
                problems["quote_mismatch"].append({"work_key": k, "quote": q[:80]})
    for g in draft.get("gaps") or []:
        sup = g.get("support") or []
        good = 0
        for s in sup:
            k = s.get("work_key")
            if k not in by_key:
                problems["citation_missing"].append({"marker": "gap_support", "work_key": k})
                continue
            q = norm_text(s.get("quote") or "")
            if q and q not in texts.get(k, ""):
                problems["quote_mismatch"].append({"work_key": k, "quote": q[:80]})
            else:
                good += 1
        if g.get("type") == "derived" and good == 0 and sup:
            problems["gap_support"].append({"statement": (g.get("statement") or "")[:80],
                                            "reason": "all supports failed quote check"})
        elif g.get("type") == "derived" and not sup:
            problems["gap_support"].append({"statement": (g.get("statement") or "")[:80],
                                            "reason": "derived gap without support"})
    problems["counts"] = {"citations": n_cites, "quotes": n_quotes,
                          "gaps": len(draft.get("gaps") or []),
                          "author_judgment_gaps": sum(1 for g in (draft.get("gaps") or [])
                                                      if g.get("type") == "author_judgment")}
    return problems


def stage_collect(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    works = collect_works(case, args.input)
    with io.open(os.path.join(WORK, "works.json"), "w", encoding="utf-8") as f:
        json.dump({"works": works, "case_error": err}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "collect", "works": len(works),
                      "chars": sum(len(w["text"]) for w in works)}))


def stage_verify(args):
    case, _ = load_case(args.input)
    works = (read_json(os.path.join(WORK, "works.json")) or {}).get("works") or []
    draft = read_json(args.draft or os.path.join(WORK, "draft.json"))
    if draft is None:
        print(json.dumps({"stage": "verify", "error": "draft_missing"}))
        return
    problems = verify(draft, works)
    print(json.dumps({"stage": "verify", "citation_missing": len(problems["citation_missing"]),
                      "quote_mismatch": len(problems["quote_mismatch"]),
                      "gap_support_issues": len(problems["gap_support"]),
                      "counts": problems["counts"]}))


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    works = (read_json(os.path.join(WORK, "works.json")) or {}).get("works") or []
    draft = read_json(args.draft or os.path.join(WORK, "draft.json"))
    problems, status = [], "success"
    if draft is None or not works:
        status = "cannot_determine" if not works else "partial"
        problems.append("draft_or_works_missing")
        verification = {}
    else:
        verification = verify(draft, works)
        if verification["citation_missing"]:
            status = "partial"
            problems.append("citation_missing:%d" % len(verification["citation_missing"]))
        if verification["quote_mismatch"]:
            status = "partial"
            problems.append("quote_mismatch:%d" % len(verification["quote_mismatch"]))
        if verification["gap_support"]:
            status = "partial"
            problems.append("gap_support:%d" % len(verification["gap_support"]))
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "intro_text": (draft or {}).get("intro_text"),
        "related_work_text": (draft or {}).get("related_work_text"),
        "citations": (draft or {}).get("citations") or [],
        "gaps": (draft or {}).get("gaps") or [],
        "contributions": (draft or {}).get("contributions") or [],
        "verification": verification,
        "works_used": [w["work_key"] for w in works],
        "uncertainty": (draft or {}).get("uncertainty", []),
        "changes_log": [
            {"change": "collect", "detail": "works from case material", "works": len(works)},
            {"change": "write", "detail": "agent drafting with grounded citations"},
            {"change": "verify", "detail": "citation existence + quote backtracking + gap support",
             "violations": len(problems)},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status, "citations": len(result["citations"]),
                      "gaps": len(result["gaps"]), "problems": problems,
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["collect", "verify", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.draft is None:
        args.draft = os.path.join(WORK, "draft.json")
    try:
        (stage_collect if args.stage == "collect" else
         stage_verify if args.stage == "verify" else stage_finalize)(args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "intro_text": None, "related_work_text": None,
                  "citations": [], "gaps": [], "contributions": [],
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
