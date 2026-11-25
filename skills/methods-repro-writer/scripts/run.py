#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""methods-repro-writer: collect facts (params with sources), tolerant verify, finalize.

NO strict cross-validation. Missing -> null + not_reported. stdlib only.
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


KEYVAL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.\-]*)\s*[:=]\s*([^#;\n]+)", re.MULTILINE)
SEED_RE = re.compile(r"(?:seed|random_state)\s*[:=]\s*(\d+)", re.IGNORECASE)
EPOCH_RE = re.compile(r"(?:epochs?|max_iter|num_steps)\s*[:=]\s*(\d+)", re.IGNORECASE)
LR_RE = re.compile(r"(?:learning_rate|lr)\s*[:=]\s*([\d.eE+-]+)", re.IGNORECASE)
BATCH_RE = re.compile(r"batch_size\s*[:=]\s*(\d+)", re.IGNORECASE)
VERSION_RE = re.compile(r"(python|torch|pytorch|tensorflow|numpy|cuda|scikit-learn)\s*[:=]?\s*v?([\d.]+[a-z]*)", re.IGNORECASE)


def flatten_kv(text):
    """key: value pairs from yaml/ini-style text."""
    out = []
    for m in KEYVAL_RE.finditer(text):
        k, v = m.group(1), m.group(2).strip().strip("'\"")
        if v:
            out.append((k, v))
    return out


def collect_materials(case, input_dir):
    """All readable material files with their text."""
    files = []
    listed = _pick(case, ["materials", "files", "configs", "logs", "documents", "inputs"])
    cands = []
    if isinstance(listed, list):
        for x in listed:
            cands.append(x.get("path") if isinstance(x, dict) else x)
    elif isinstance(listed, dict):
        for v in listed.values():
            if isinstance(v, str):
                cands.append(v)
            elif isinstance(v, list):
                cands.extend(v)
    elif isinstance(listed, str):
        cands.append(listed)
    seen = set()
    for c in cands:
        if isinstance(c, str) and c:
            p = c if os.path.isabs(c) else os.path.join(input_dir, c)
            if os.path.exists(p) and p not in seen:
                seen.add(p)
                cands_all = [p]
    if os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, fn)
            if p not in seen and fn.lower().endswith((".yaml", ".yml", ".json", ".log", ".txt", ".md", ".cfg", ".ini")) and fn != "task.md":
                seen.add(p)
                cands_all = cands_all if False else []
                cands_all.append(p)
    # dedupe cands_all
    result = []
    seen2 = set()
    for p in (cands_all if 'cands_all' in dir() else []):
        if p not in seen2:
            seen2.add(p)
            result.append(p)
    for p in sorted(seen):
        if p not in result:
            result.append(p)
    out = []
    for p in result:
        kind = "config" if p.endswith((".yaml", ".yml", ".json", ".cfg", ".ini")) else \
               ("log" if p.endswith(".log") else "text")
        try:
            if p.endswith(".json"):
                with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                text = json.dumps(data, ensure_ascii=False)
            else:
                with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            out.append({"path": p, "name": os.path.basename(p), "kind": kind, "text": text,
                        "error": None})
        except Exception as e:
            out.append({"path": p, "name": os.path.basename(p), "kind": kind, "text": "",
                        "error": str(e)})
    return out


def extract_params(files):
    """Parameters with values + sources. Never guesses; nulls for unknowns."""
    params = []
    seed = lr = batch = epochs = None
    versions = []
    conflicts = []
    for f in files:
        if f.get("error"):
            continue
        kvs = dict(flatten_kv(f["text"]))
        for k, v in kvs.items():
            params.append({"name": k, "value": v, "unit": None, "applies_to": None,
                           "source": "%s:%s" % (f["kind"], f["name"])})
        for rx, slot in ((SEED_RE, "seed"), (EPOCH_RE, "epochs"), (LR_RE, "learning_rate"),
                         (BATCH_RE, "batch_size")):
            m = rx.search(f["text"])
            if m:
                val = m.group(1)
                prev = slot == "seed" and seed or slot == "epochs" and epochs or \
                    slot == "learning_rate" and lr or slot == "batch_size" and batch
                if prev is not None and str(prev) != str(val):
                    conflicts.append({"param": slot, "values": [str(prev), str(val)],
                                      "sources": ["earlier", "%s:%s" % (f["kind"], f["name"])]})
                if slot == "seed":
                    seed = seed or val
                elif slot == "epochs":
                    epochs = epochs or val
                elif slot == "learning_rate":
                    lr = lr or val
                else:
                    batch = batch or val
        for m in VERSION_RE.finditer(f["text"]):
            versions.append({"lib": m.group(1), "version": m.group(2),
                             "source": "%s:%s" % (f["kind"], f["name"])})
    # canonical slots: value or None (never guessed)
    for name, val in (("random_seed", seed), ("epochs", epochs),
                      ("learning_rate", lr), ("batch_size", batch)):
        params.append({"name": name, "value": val, "unit": None,
                       "applies_to": "training",
                       "source": "not_reported" if val is None else "collected"})
    return params, versions, conflicts


def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def verify_tolerant(draft):
    """Only demotes; never rejects. Returns problems + stats."""
    problems, warnings = [], []
    steps = draft.get("steps") or []
    nums = [s.get("n") for s in steps if isinstance(s.get("n"), int)]
    if nums and nums != list(range(1, len(nums) + 1)):
        warnings.append("step numbering gaps: %s" % nums[:12])
    params = draft.get("params") or []
    no_source = [p.get("name") for p in params if not p.get("source")]
    if no_source:
        problems.append("params without source field: %s" % no_source[:8])
    n_nr = sum(1 for p in params if p.get("source") == "not_reported")
    setup = draft.get("setup") or {}
    for k, v in setup.items():
        if v is not None and not isinstance(v, (dict, str)):
            problems.append("setup.%s must be object/string, got %s" % (k, type(v).__name__))
    repro = draft.get("repro") or {}
    if repro.get("seed") is None:
        warnings.append("seed not_reported — should appear in limitations")
    return {"problems": problems, "warnings": warnings,
            "stats": {"params": len(params), "not_reported": n_nr, "steps": len(steps)}}


def stage_collect(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    files = collect_materials(case, args.input)
    params, versions, conflicts = extract_params(files)
    manuscript = _pick(case, ["text", "draft", "manuscript", "source_text", "content", "body"])
    if isinstance(manuscript, dict):
        manuscript = _pick(manuscript, ["text", "content", "body"])
    facts = {"files": [{k: f[k] for k in ("name", "kind", "error")} for f in files],
             "params": params, "versions": versions, "conflicts": conflicts,
             "manuscript_chars": len(manuscript) if isinstance(manuscript, str) else 0,
             "case_error": err}
    with io.open(os.path.join(WORK, "facts.json"), "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "collect", "files": len(files),
                      "file_errors": sum(1 for f in files if f.get("error")),
                      "params": len(params), "versions": len(versions),
                      "conflicts": len(conflicts)}))


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    facts = read_json(os.path.join(WORK, "facts.json"))
    draft = read_json(args.draft or os.path.join(WORK, "draft.json"))
    problems, status = [], "success"
    if facts is None or not (facts.get("files") or facts.get("manuscript_chars")):
        status = "cannot_determine"
        problems.append("missing_material")
    elif draft is None:
        status = "partial"
        problems.append("draft_missing")
    else:
        v = verify_tolerant(draft)
        problems.extend(v["problems"])  # only real field-type problems demote
        if v["problems"]:
            status = "partial"
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "methods_text": (draft or {}).get("methods_text"),
        "steps": (draft or {}).get("steps") or [],
        "params": (draft or {}).get("params") or (facts or {}).get("params") or [],
        "setup": (draft or {}).get("setup") or {},
        "repro": (draft or {}).get("repro") or {},
        "limitations": (draft or {}).get("limitations") or [],
        "conflicts": (facts or {}).get("conflicts") or [],
        "verification": (draft if False else verify_tolerant(draft)) if draft else None,
        "files_read": (facts or {}).get("files") or [],
        "uncertainty": (draft or {}).get("uncertainty", []),
        "changes_log": [
            {"change": "collect", "detail": "params with sources from configs/logs/text"},
            {"change": "write", "detail": "agent drafting steps + params + repro + limitations"},
            {"change": "verify", "detail": "tolerant schema check (demote-only)"},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status, "params": len(result["params"]),
                      "steps": len(result["steps"]), "problems": problems,
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["collect", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.draft is None:
        args.draft = os.path.join(WORK, "draft.json")
    try:
        (stage_collect if args.stage == "collect" else stage_finalize)(args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "methods_text": None, "steps": [], "params": [], "setup": {},
                  "repro": {}, "limitations": [],
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
