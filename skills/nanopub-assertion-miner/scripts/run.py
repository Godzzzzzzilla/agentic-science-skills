#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nanopub-assertion-miner: collect material, verify assertions, finalize.

stdlib only; degrade-don't-die; serialization field-exact.
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


def collect_material(case, input_dir):
    """Material -> paragraphs with ids (JATS ids if present, else positional)."""
    raw = _pick(case, ["material", "text", "document", "paper", "content", "body", "passages"])
    if isinstance(raw, dict):
        # {"paragraphs": [{"id": "p1", "text": "..."}]} or {"p1": "text"}
        paras = raw.get("paragraphs") or raw.get("sections")
        if isinstance(paras, list):
            out = []
            for i, p in enumerate(paras):
                if isinstance(p, dict):
                    out.append({"para_id": p.get("id") or ("p%d" % (i + 1)),
                                "text": norm_text(p.get("text") or "")})
                elif isinstance(p, str):
                    out.append({"para_id": "p%d" % (i + 1), "text": norm_text(p)})
            if out:
                return out, "json_list"
        if isinstance(paras, dict) and paras:
            return [{"para_id": k, "text": norm_text(v)} for k, v in paras.items()
                    if isinstance(v, str) and v.strip()], "json_dict"
        if isinstance(raw.get("text"), str):
            raw = raw["text"]
        elif raw and all(isinstance(v, str) for v in raw.values()):
            return [{"para_id": k, "text": norm_text(v)} for k, v in raw.items()
                    if v.strip()], "json_dict"
    if isinstance(raw, str) and raw.strip():
        if raw.lstrip().startswith("<") and "<p" in raw:
            return jats_to_paras(raw), "jats_xml"
        return text_to_paras(raw), "raw_text"
    # files
    if os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, fn)
            if fn.lower().endswith((".xml", ".nxml", ".txt", ".md")) and fn != "task.md":
                with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if fn.endswith((".xml", ".nxml")):
                    return jats_to_paras(content), fn
                return text_to_paras(content), fn
    return None, None


def jats_to_paras(xml_text):
    """JATS paragraphs with their id attributes; positional fallback."""
    out = []
    for i, m in enumerate(re.finditer(r"<p[^>]*?(?:id=\"([^\"]+)\")?[^>]*>(.*?)</p>",
                                      xml_text, re.S)):
        pid = m.group(1) or ("p%d" % (i + 1))
        text = norm_text(re.sub(r"<[^>]+>", "", m.group(2)))
        if text:
            out.append({"para_id": pid, "text": text})
    return out


def text_to_paras(text):
    out = []
    for i, b in enumerate(re.split(r"\n\s*\n", text)):
        b = norm_text(b)
        if b:
            out.append({"para_id": "p%d" % (i + 1), "text": b})
    return out


def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


REQUIRED_ASSERTION_FIELDS = ["subject", "predicate", "object", "evidence"]


def verify(assertions, paras, contract_assertion_fields=None):
    problems = {"schema_missing": [], "quote_mismatch": [], "atomicity_hints": [],
                "stats": {}}
    by_id = {p["para_id"]: p for p in paras}
    n_ok = 0
    for i, a in enumerate(assertions):
        missing = [f for f in REQUIRED_ASSERTION_FIELDS
                   if f not in a or a.get(f) in (None, "", {}, [])]
        for f in contract_assertion_fields or []:
            if f not in a and f not in missing:
                missing.append(f)
        if missing:
            problems["schema_missing"].append({"index": i, "fields": missing})
            continue
        ev = a.get("evidence") or {}
        pid = ev.get("para_id")
        q = norm_text(ev.get("quote") or "")
        para = by_id.get(pid)
        if para is None:
            problems["quote_mismatch"].append({"index": i, "para_id": pid,
                                               "reason": "unknown paragraph id"})
        elif q and q not in para["text"]:
            problems["quote_mismatch"].append({"index": i, "para_id": pid,
                                               "reason": "quote not verbatim"})
        else:
            n_ok += 1
        obj = str(a.get("object") or "")
        if re.search(r"\band\s+\w+.*\band\b", obj) or obj.count(" and ") >= 2:
            problems["atomicity_hints"].append(
                {"index": i, "hint": "object joins multiple clauses; consider splitting"})
    problems["stats"] = {"assertions": len(assertions), "evidence_ok": n_ok}
    return problems


def stage_collect(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    paras, src = collect_material(case, args.input)
    if not paras:
        with io.open(os.path.join(WORK, "material.json"), "w", encoding="utf-8") as f:
            json.dump({"error": "missing_material", "case_error": err}, f, ensure_ascii=False)
        print(json.dumps({"stage": "collect", "error": "missing_material"}))
        return
    material = {"paras": paras, "source": src, "case_error": err,
                "note": "para ids from material attributes when present, positional otherwise"}
    with io.open(os.path.join(WORK, "material.json"), "w", encoding="utf-8") as f:
        json.dump(material, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "collect", "paras": len(paras), "source": src}))


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    material = read_json(os.path.join(WORK, "material.json"))
    assertions_doc = read_json(args.assertions or os.path.join(WORK, "assertions.json"))
    problems, status = [], "success"
    if not material or material.get("error"):
        status = "cannot_determine"
        problems.append("missing_material")
        verification = {}
        assertions = []
    elif not assertions_doc:
        status = "partial"
        problems.append("assertions_missing")
        verification = {}
        assertions = []
    else:
        assertions = assertions_doc.get("assertions") or []
        contract_assertion_fields = None
        oc = case.get("output_contract")
        if isinstance(oc, dict) and isinstance(oc.get("assertions"), dict):
            contract_assertion_fields = [k for k in oc["assertions"].keys()
                                         if k not in ("type", "description")]
        verification = verify(assertions, material["paras"], contract_assertion_fields)
        if verification["schema_missing"]:
            status = "partial"
            problems.append("schema_missing:%d" % len(verification["schema_missing"]))
        if verification["quote_mismatch"]:
            status = "partial"
            problems.append("quote_mismatch:%d" % len(verification["quote_mismatch"]))
        if not assertions:
            status = "partial"
            problems.append("no_assertions")
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "assertions": assertions,
        "provenance": (assertions_doc or {}).get("provenance") or {},
        "verification": verification,
        "uncertainty": (assertions_doc or {}).get("uncertainty", []),
        "source": (material or {}).get("source"),
        "changes_log": [
            {"change": "collect", "detail": "paragraphs with ids", "paras": len((material or {}).get("paras") or [])},
            {"change": "decompose", "detail": "agent atomic assertions with bound evidence"},
            {"change": "verify", "detail": "schema + quote backtracking + atomicity hints",
             "violations": len(problems)},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status,
                      "assertions": len(assertions), "problems": problems,
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["collect", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--assertions", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.assertions is None:
        args.assertions = os.path.join(WORK, "assertions.json")
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
                  "assertions": [], "provenance": {},
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
