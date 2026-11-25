#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""academic-polish-audit: sentence alignment + fact-token diff + change table + finalize.

Modes
  audit    : --original A --polished B  -> aligns, diffs fact tokens, writes work report
  finalize : merges report + verdicts  -> /app/output/result.json (contract-true)

Design rules:
  - stdlib only (difflib, re, json)
  - every ratio with zero denominator -> null (never 0/1 masquerade)
  - status computed from artifacts; missing -> null / partial, never reject
"""
import argparse
import difflib
import io
import json
import os
import re
import sys
import traceback

WORK = "/app/work"
OUT = "/app/output"

# ---------------------------------------------------------------- fact tokens

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
UNIT_RE = re.compile(r"(?:\d)\s*(%|°C|K\b|kHz|MHz|GHz|Hz\b|kb|Mb|Gb|kbps|Mbps|kbit|Mbit|nm|µm|um|mm|cm|m\b|km|kg|g\b|mg|µg|mL|L\b|mol|mM|µM|M\b|s\b|ms|min|h\b|kcal|kJ|J\b|W\b|kW|V\b|mV|kV|A\b|mA|Pa|kPa|MPa|GPa|bar|atm|ppm|ppb|wt%|vol%|log\s?Kow|n\s?=\s?\d)", re.IGNORECASE)
CITE_RE = re.compile(r"\[[0-9]+(?:[,;\s\-–]+[0-9]+)*\]|\((?:[A-Z][A-Za-z'’\-]+(?:\s+(?:et al\.?|and|&)\s+[A-Z][A-Za-z'’\-]+)*,?\s*(?:19|20)\d{2}[a-z]?)\)")
NEG_WORDS = {"no", "none", "not", "never", "neither", "nor", "cannot", "without", "absence",
             "lacked", "lacking", "failed", "absent", "n't", "无", "未", "没有", "不"}
HEDGE_WORDS = {"may", "might", "could", "can", "would", "possible", "possibly", "probable",
              "probably", "suggest", "suggests", "suggested", "appear", "appears", "appeared",
              "seem", "seems", "seemed", "likely", "unlikely", "approximately", "approx",
              "about", "around", "roughly", "generally", "often", "sometimes", "可能", "大约",
              "似乎", "表明"}
STRONG_WORDS = {"prove", "proves", "proven", "demonstrate", "demonstrates", "always", "never fails",
                "certainly", "definitely", "证明", "一定"}
COMP_RE = re.compile(r"\b(?:more|less|fewer|higher|lower|greater|smaller|faster|slower|better|worse|stronger|weaker|larger|increase[d]?|decrease[d]?|reduc[d]?|elevat[d]?|较|更)\b", re.IGNORECASE)
FIGREF_RE = re.compile(r"(?:Figure|Fig\.?|Table|图|表)\s*\.?\s*\d+[a-z]?", re.IGNORECASE)

CONVERSIONS = {"c_to_k": 273.15, "pct_to_fraction": 100.0}


def sent_split(text):
    """Sentence splitter: abbreviation-aware enough for academic prose."""
    if not text:
        return []
    prot = text
    for ab in ("et al.", "e.g.", "i.e.", "cf.", "vs.", "Fig.", "Figs.", "Eq.", "Eqs.",
               "Ref.", "Refs.", "approx.", "ca.", "no.", "No.", "St.", "Prof.", "Dr.",
               "approx ."):
        prot = prot.replace(ab, ab.replace(".", "∯"))
    parts = re.split(r"(?<=[.!?。])\s+(?=[A-Z\u4e00-\u9fff(“\"\d])", prot)
    out = []
    for p in parts:
        p = p.replace("∯", ".")
        p = p.strip()
        if p:
            out.append(p)
    return out


def tokens_of(sentence):
    low = sentence.lower()
    words = set(re.findall(r"[a-zA-Z']+", low))
    return {
        "numbers": set(NUM_RE.findall(sentence)),
        "units": set(m.group(1).strip().lower() for m in UNIT_RE.finditer(sentence)),
        "citations": set(c.strip() for c in CITE_RE.findall(sentence)),
        "negations": words & NEG_WORDS,
        "hedges": words & HEDGE_WORDS,
        "strongs": words & STRONG_WORDS,
        "comparatives": set(m.group(0).lower() for m in COMP_RE.finditer(sentence)),
        "figrefs": set(f.strip().lower() for f in FIGREF_RE.findall(sentence)),
    }


def align_sentences(orig, pol):
    """Similarity-greedy alignment; returns list of (i, j, sim) with j=None for deletions."""
    pairs = []
    used = set()
    for i, o in enumerate(orig):
        best_j, best_sim = None, 0.0
        for j, p in enumerate(pol):
            if j in used:
                continue
            sim = difflib.SequenceMatcher(None, o, p).ratio()
            if sim > best_sim:
                best_sim, best_j = sim, j
        if best_j is not None and best_sim >= 0.35:
            used.add(best_j)
            pairs.append({"i": i, "j": best_j, "sim": round(best_sim, 3)})
        else:
            pairs.append({"i": i, "j": None, "sim": 0.0})
    # additions: polished sentences never matched
    matched = {p["j"] for p in pairs if p["j"] is not None}
    for j, p in enumerate(pol):
        if j not in matched:
            pairs.append({"i": None, "j": j, "sim": 0.0, "added": True})
    pairs.sort(key=lambda p: (p["i"] is None, p["i"] if p["i"] is not None else 0,
                              p["j"] if p["j"] is not None else 0))
    return pairs


def classify_change(o, p):
    """Classify one aligned pair into change types (grammar / wording / fact-risk)."""
    types = []
    if o is None:
        return ["addition"]
    if p is None:
        return ["deletion"]
    to, tp = tokens_of(o), tokens_of(p)
    for key, label in (("numbers", "loss: number"), ("citations", "loss: citation"),
                       ("figrefs", "loss: figure_reference")):
        if to[key] - tp[key]:
            types.append(label + " (%s)" % ",".join(sorted(to[key] - tp[key])[:4]))
    if to["negations"] - tp["negations"]:
        types.append("loss: negation (%s)" % ",".join(sorted(to["negations"])))
    if to["hedges"] - tp["hedges"]:
        gained_strong = bool(tp["strongs"] - to["strongs"])
        types.append("swap: hedge_stronger" if gained_strong else "loss: hedge (%s)" %
                     ",".join(sorted(to["hedges"] - tp["hedges"])[:3]))
    if tp["hedges"] - to["hedges"]:
        types.append("swap: hedge_weaker (%s)" % ",".join(sorted(tp["hedges"] - to["hedges"])[:3]))
    if to["units"] - tp["units"]:
        types.append("loss: unit (%s)" % ",".join(sorted(to["units"] - tp["units"])[:3]))
    if not types:
        if o.strip() == p.strip():
            types.append("unchanged")
        else:
            types.append("wording/grammar")
    return types


def build_report(orig_text, pol_text):
    orig, pol = sent_split(orig_text), sent_split(pol_text)
    pairs = align_sentences(orig, pol)
    table = []
    violations = []
    for p in pairs:
        o = orig[p["i"]] if p["i"] is not None else None
        q = pol[p["j"]] if p["j"] is not None else None
        types = classify_change(o, q)
        entry = {"orig_index": p["i"], "pol_index": p["j"], "similarity": p["sim"],
                 "original": o, "polished": q, "change_types": types,
                 "fact_risk": any(t.startswith(("loss", "swap")) for t in types)}
        table.append(entry)
        if entry["fact_risk"]:
            violations.append({"orig_index": p["i"], "types": types})
    changed = sum(1 for e in table if "unchanged" not in e["change_types"] and not e["change_types"] == ["unchanged"])
    return {
        "pairs": len(table),
        "changed_pairs": changed,
        "unchanged_pairs": len(table) - changed,
        "alignment_ratio": (round(len([p for p in pairs if p["j"] is not None]) / len(orig), 4) if orig else None),
        "fact_violations": violations,
        "fact_violation_ratio": (round(len(violations) / len(table), 4) if table else None),
        "change_table": table,
    }


# ---------------------------------------------------------------- case utils

def load_case(input_dir):
    path = os.path.join(input_dir, "case.json")
    if not os.path.exists(path):
        for fn in sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []:
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


def case_texts(case):
    orig = _pick(case, ["text", "draft", "source_text", "original", "manuscript", "content", "body", "paragraph", "source"])
    if isinstance(orig, dict):
        orig = _pick(orig, ["text", "content", "body"])
    pol = _pick(case, ["polished", "revised", "llm_draft", "target_text", "polished_text", "candidate", "edited"])
    if isinstance(pol, dict):
        pol = _pick(pol, ["text", "content", "body"])
    return orig, pol


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


# ---------------------------------------------------------------- modes

def mode_audit(args):
    os.makedirs(WORK, exist_ok=True)
    report = None
    meta = {"mode": "audit"}
    try:
        orig = io.open(args.original, "r", encoding="utf-8").read() if args.original and os.path.exists(args.original) else None
        pol = io.open(args.polished, "r", encoding="utf-8").read() if args.polished and os.path.exists(args.polished) else None
        case, err = load_case(args.input)
        c_orig, c_pol = case_texts(case)
        orig = orig or (c_orig if isinstance(c_orig, str) else None)
        pol = pol or (c_pol if isinstance(c_pol, str) else None)
        meta["case_id"] = _pick(case, ["case_id", "id", "caseId"])
        meta["case_error"] = err
        if orig is None:
            report = {"pairs": 0, "error": "missing_original_text"}
        elif pol is None:
            report = {"pairs": 0, "error": "missing_polished_text"}
        else:
            report = build_report(orig, pol)
    except Exception:
        report = {"pairs": 0, "error": traceback.format_exc(limit=3)[-800:]}
    with io.open(os.path.join(WORK, "audit_report.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "report": report}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"mode": "audit", "pairs": report.get("pairs"),
                      "changed": report.get("changed_pairs"),
                      "violations": len(report.get("fact_violations") or []),
                      "error": report.get("error")}, ensure_ascii=False))


def mode_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, err = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    rep = None
    rp = os.path.join(WORK, "audit_report.json")
    if os.path.exists(rp):
        with io.open(rp, "r", encoding="utf-8") as f:
            blob = json.load(f)
        rep = blob.get("report")
    verdicts = {}
    notes = None
    if args.notes and os.path.exists(args.notes):
        with io.open(args.notes, "r", encoding="utf-8") as f:
            notes = json.load(f)
        for v in notes.get("verdicts") or []:
            verdicts[v.get("pair")] = v
    problems = []
    if rep is None:
        problems.append("audit_report_missing")
    elif rep.get("error"):
        problems.append(rep["error"])
    pol_path = os.path.join(WORK, "polished.txt")
    polished_text = io.open(pol_path, "r", encoding="utf-8").read() if os.path.exists(pol_path) else None
    orig_path = os.path.join(WORK, "original.txt")
    original_text = io.open(orig_path, "r", encoding="utf-8").read() if os.path.exists(orig_path) else None
    if original_text is None or polished_text is None:
        c_orig, c_pol = case_texts(case)
        original_text = original_text or (c_orig if isinstance(c_orig, str) else None)
        polished_text = polished_text or (c_pol if isinstance(c_pol, str) else None)
    # apply verdicts: rejected pairs -> revert to original sentence
    if rep and polished_text is not None and original_text is not None and verdicts:
        orig_sents = sent_split(original_text)
        pol_sents = sent_split(polished_text)
        fixed = list(pol_sents)
        for e in (rep.get("change_table") or []):
            v = verdicts.get(e.get("orig_index"))
            if v and v.get("accept") is False and e.get("orig_index") is not None and e.get("pol_index") is not None:
                if e["pol_index"] < len(fixed) and e["orig_index"] < len(orig_sents):
                    fixed[e["pol_index"]] = orig_sents[e["orig_index"]]
        polished_text = " ".join(fixed)
    rejected = [v for v in verdicts.values() if v.get("accept") is False]
    if rep and rep.get("fact_violations") and not rejected:
        # unadjudicated violations keep partial status
        problems.append("unadjudicated_fact_violations:%d" % len(rep["fact_violations"]))
    status = "success"
    if rep is None or rep.get("error"):
        status = "cannot_determine" if (rep or {}).get("error", "").startswith("missing_") else "partial"
    elif problems:
        status = "partial"
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems or [],
        "mode": (rep or {}).get("mode") or ("audit" if verdicts else "edit"),
        "polished_text": polished_text,
        "change_summary": {
            "pairs": (rep or {}).get("pairs"),
            "changed_pairs": (rep or {}).get("changed_pairs"),
            "unchanged_pairs": (rep or {}).get("unchanged_pairs"),
            "alignment_ratio": (rep or {}).get("alignment_ratio"),
            "fact_violation_ratio": (rep or {}).get("fact_violation_ratio"),
            "rejected_pairs": len(rejected),
        },
        "changes": (rep or {}).get("change_table") or [],
        "audit": {
            "violations": (rep or {}).get("fact_violations") or [],
            "verdicts": list(verdicts.values()),
            "sanctioned_conversions": ["°C→K (+273.15)", "%→fraction (÷100)", "approximately→~/ca."],
        },
        "uncertainty": (notes or {}).get("uncertainty", []),
        "changes_log": [
            {"change": "alignment+audit", "detail": "run.py mode audit", "result": "audit_report.json"},
            {"change": "verdicts", "detail": "agent adjudication of flagged pairs", "count": len(verdicts)},
        ],
        "case_error": err,
    }
    for k in keys:
        if k not in result:
            result[k] = {"polished_text": polished_text, "changes": result["changes"],
                         "status": status}.get(k)
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"mode": "finalize", "status": status, "pairs": (rep or {}).get("pairs"),
                      "violations": len((rep or {}).get("fact_violations") or []),
                      "rejected": len(rejected), "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["audit", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--original", default=None)
    ap.add_argument("--polished", default=None)
    ap.add_argument("--notes", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.original is None:
        args.original = os.path.join(WORK, "original.txt")
    if args.polished is None:
        args.polished = os.path.join(WORK, "polished.txt")
    if args.notes is None:
        args.notes = os.path.join(WORK, "notes.json")
    try:
        (mode_audit if args.mode == "audit" else mode_finalize)(args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "polished_text": None, "changes": [],
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"mode": args.mode, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
