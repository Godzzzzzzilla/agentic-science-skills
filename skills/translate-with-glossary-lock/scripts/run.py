#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate-with-glossary-lock: segmentation, glossary, verification, finalize.

Word/paragraph indexing is 1-based (para_id). stdlib only.
Never rejects; missing -> null / partial.
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

UNIT_RE = re.compile(r"\d(?:\.\d+)?\s*(?:%|°C|K\b|kHz|MHz|GHz|Hz\b|kb|Mb|nm|µm|um|mm|cm|km|kg|mg|µg|mL|mol|mM|µM|ms|min|kcal|kJ|Pa|kPa|MPa|ppm|bp)", re.IGNORECASE)
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
CITE_RE = re.compile(r"\[[0-9]+(?:[,;\s\-–]+[0-9]+)*\]|\((?:[A-Z][A-Za-z'’\-]+(?:\s+et al\.?)?,?\s*(?:19|20)\d{2}[a-z]?)\)")
FIG_RE = re.compile(r"(?:Figure|Fig\.?|Table|图|表)\s*\.?\s*\d+", re.IGNORECASE)
NEG_SRC = {"no", "none", "not", "never", "neither", "nor", "cannot", "without", "lack"}
NEG_TGT = {"未", "不", "没有", "无", "并非", "不能", "缺乏"}
HEDGE_SRC = {"may", "might", "could", "suggest", "suggests", "possible", "possibly", "likely", "appear", "appears", "seem", "seems", "approximately", "about"}
STRONG_TGT = {"证明", "必定", "显然", "绝对"}


# ---------------------------------------------------------------- case utils

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


def source_text(case, input_dir):
    t = _pick(case, ["text", "draft", "source_text", "original", "content", "body", "paper", "manuscript"])
    if isinstance(t, dict):
        t = _pick(t, ["text", "content", "body"])
    if isinstance(t, str):
        return t, "case_field"
    # any text/pdf file in input
    for fn in sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []:
        p = os.path.join(input_dir, fn)
        if fn.lower().endswith((".txt", ".md")):
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read(), fn
        if fn.lower().endswith(".pdf"):
            try:
                import fitz
                doc = fitz.open(p)
                txt = "\n".join(re.sub(r"[ \t]+", " ", pg.get_text("text").replace("\r\n", "\n")) for pg in doc)
                doc.close()
                return txt, fn
            except Exception:
                pass
    return None, None

# ---------------------------------------------------------------- segmentation

def segment(text):
    """Paragraph units with anchors. Returns (paras, sections)."""
    paras = []
    cur_section = "preamble"
    blocks = re.split(r"\n\s*\n", text)
    pos = 0
    pid = 0
    for b in blocks:
        btxt = "\n".join(ln.strip() for ln in b.split("\n") if ln.strip()).strip()
        if not btxt:
            pos += len(b) + 2
            continue
        idx = text.find(btxt[:24], pos)
        if idx < 0:
            idx = pos
        first = btxt.split("\n")[0]
        if re.match(r"^(?:abstract|introduction|background|related\s+work|methods?|materials?\s+and\s+methods?|experimental|results?|discussion|conclusions?|references?|acknowledg)", first, re.IGNORECASE) or \
           re.match(r"^(摘要|引言|前言|相关工作|方法|材料与方法|实验|结果|讨论|结论|致谢|参考文献)$", first.strip()) or \
           re.match(r"^\d+(?:\.\d+)*\.?\s+\S", first) and not first.endswith("."):
            cur_section = first[:60]
        pid += 1
        paras.append({"para_id": pid, "section": cur_section, "text": btxt,
                      "char_span": [idx, idx + len(btxt)],
                      "word_count": len(btxt.split())})
        pos = idx + len(btxt)
    return paras

# ---------------------------------------------------------------- glossary

TERM_PATTERNS = [
    re.compile(r"\b(?:[A-Z][a-z]+(?:[\s-][A-Z][a-z]+){1,3})\b"),          # Capitalized phrases
    re.compile(r"\b(?:deep|neural|machine|reinforcement|transfer|convolutional|recurrent|attention|transformer|graph|federated|self-?supervised|contrastive|adversarial)\s+[a-z]{3,20}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z][a-z]+\s+[a-z]+\s+[a-z]+\b"),
]


def extract_terms(paras):
    """Term candidates with occurrence counts and example contexts."""
    full = "\n".join(p["text"] for p in paras)
    counts = {}
    for pat in TERM_PATTERNS:
        for m in pat.finditer(full):
            t = m.group(0).strip()
            if 4 < len(t) < 60 and not t.isupper():
                counts.setdefault(t, {"count": 0, "example": full[max(0, m.start() - 40):m.end() + 40]})
                counts[t]["count"] += 1
    cands = {t: v for t, v in sorted(counts.items(), key=lambda kv: -kv[1]["count"])
             if v["count"] >= 2}
    return cands

# ---------------------------------------------------------------- tokens

def src_tokens(text):
    words = set(re.findall(r"[a-zA-Z']+", (text or "").lower()))
    return {
        "numbers": set(NUM_RE.findall(text or "")),
        "units": set(u.strip() for u in UNIT_RE.findall(text or "")),
        "cites": set(c.strip() for c in CITE_RE.findall(text or "")),
        "figs": set(f.strip() for f in FIG_RE.findall(text or "")),
        "negs": words & NEG_SRC,
        "hedges": words & HEDGE_SRC,
    }


def tgt_tokens(text):
    return {
        "numbers": set(NUM_RE.findall(text or "")),
        "units": set(u.strip() for u in UNIT_RE.findall(text or "")),
        "cites": set(c.strip() for c in CITE_RE.findall(text or "")),
        "figs": set(f.strip() for f in FIG_RE.findall(text or "")),
        "negs": set(re.findall("|".join(NEG_TGT), text or "")),
        "strongs": set(re.findall("|".join(STRONG_TGT), text or "")),
    }

# ---------------------------------------------------------------- stages

def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def stage_segment(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    text, src_file = source_text(case, args.input)
    if text is None:
        with io.open(os.path.join(WORK, "segments.json"), "w", encoding="utf-8") as f:
            json.dump({"error": "missing_source_text", "case_error": err}, f, ensure_ascii=False)
        print(json.dumps({"stage": "segment", "error": "missing_source_text"}))
        return
    paras = segment(text)
    cands = extract_terms(paras)
    seed = _pick(case, ["glossary", "term_table", "terminology"]) or {}
    if isinstance(seed, list):
        seed = {g.get("source", g.get("en", "")): g.get("target", g.get("zh", "")) for g in seed if isinstance(g, dict)}
    gloss = {"locked": {k: v for k, v in seed.items() if isinstance(k, str) and isinstance(v, str)},
             "candidates": cands}
    with io.open(os.path.join(WORK, "segments.json"), "w", encoding="utf-8") as f:
        json.dump({"paras": paras, "source_file": src_file, "case_error": err}, f, ensure_ascii=False, indent=1)
    with io.open(os.path.join(WORK, "glossary.json"), "w", encoding="utf-8") as f:
        json.dump(gloss, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "segment", "paras": len(paras), "term_candidates": len(cands),
                      "seed_glossary": len(gloss["locked"])}))


def verify_translation(case, paras, translation):
    problems = {"coverage": {"missing": [], "extra": [], "duplicated": []},
                "glossary_violations": [], "fact_violations": [], "anchor_bad": []}
    gloss = {k: v for k, v in (translation.get("glossary") or {}).items() if k and v}
    by_id = {}
    for t in translation.get("paragraphs") or []:
        pid = t.get("para_id")
        if pid in by_id:
            problems["coverage"]["duplicated"].append(pid)
        by_id[pid] = t
    for p in paras:
        if p["para_id"] not in by_id:
            problems["coverage"]["missing"].append(p["para_id"])
    for pid in by_id:
        if pid not in {p["para_id"] for p in paras}:
            problems["coverage"]["extra"].append(pid)
    # glossary execution: one source term -> one rendering; occurrences use it
    full_tgt = "\n".join((t.get("translation") or "") for t in by_id.values())
    for term, rend in gloss.items():
        # rendering must appear wherever the term occurs in source paragraphs
        for p in paras:
            if re.search(r"\b" + re.escape(term) + r"\b", p["text"], re.IGNORECASE):
                tr = by_id.get(p["para_id"], {}).get("translation") or ""
                if tr and rend.lower() not in tr.lower():
                    problems["glossary_violations"].append(
                        {"term": term, "para_id": p["para_id"],
                         "expected": rend, "found": None})
    # fact tokens per aligned paragraph
    for p in paras:
        t = by_id.get(p["para_id"])
        if not t:
            continue
        st = src_tokens(p["text"])
        tt = tgt_tokens(t.get("translation") or "")
        miss_num = st["numbers"] - tt["numbers"]
        if miss_num and len(miss_num) <= 6:
            problems["fact_violations"].append({"para_id": p["para_id"], "type": "number",
                                                "missing": sorted(miss_num)[:6]})
        miss_cite = st["cites"] - tt["cites"]
        if miss_cite:
            problems["fact_violations"].append({"para_id": p["para_id"], "type": "citation",
                                                "missing": sorted(miss_cite)[:4]})
        miss_fig = st["figs"] - tt["figs"]
        if miss_fig:
            problems["fact_violations"].append({"para_id": p["para_id"], "type": "figure_ref",
                                                "missing": sorted(miss_fig)[:4]})
        if st["negs"] and not tt["negs"]:
            problems["fact_violations"].append({"para_id": p["para_id"], "type": "negation_dropped"})
        if tt["strongs"] and st["hedges"]:
            problems["fact_violations"].append({"para_id": p["para_id"], "type": "hedge_upgraded",
                                                "strong": sorted(tt["strongs"])[:3]})
    # anchors: para_id order matches segmentation order (no shifting)
    ordered_ids = [t.get("para_id") for t in (translation.get("paragraphs") or [])]
    if ordered_ids != sorted(ordered_ids):
        problems["anchor_bad"].append("para_ids out of order (shifted paragraphs)")
    return problems


def stage_verify(args):
    case, _ = load_case(args.input)
    segs = read_json(os.path.join(WORK, "segments.json"))
    tr = read_json(args.translation or os.path.join(WORK, "translation.json"))
    if not segs or segs.get("error") or not tr:
        print(json.dumps({"stage": "verify", "error": "segments_or_translation_missing"}))
        return
    problems = verify_translation(case, segs["paras"], tr)
    n_viol = len(problems["glossary_violations"]) + len(problems["fact_violations"])
    print(json.dumps({"stage": "verify", "missing": len(problems["coverage"]["missing"]),
                      "extra": len(problems["coverage"]["extra"]),
                      "duplicated": len(problems["coverage"]["duplicated"]),
                      "glossary_violations": len(problems["glossary_violations"]),
                      "fact_violations": len(problems["fact_violations"]),
                      "order_bad": len(problems["anchor_bad"])}))


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    segs = read_json(os.path.join(WORK, "segments.json"))
    tr = read_json(args.translation or os.path.join(WORK, "translation.json"))
    problems, status = [], "success"
    if not segs or segs.get("error") or not tr:
        status = "cannot_determine" if (not segs or segs.get("error", "").startswith("missing")) else "partial"
        problems.append("segments_or_translation_missing")
        verification = {}
        translations = []
        glossary = {}
    else:
        paras = segs["paras"]
        verification = verify_translation(case, paras, tr)
        by_id = {p["para_id"]: p for p in paras}
        translations = []
        for t in tr.get("paragraphs") or []:
            p = by_id.get(t.get("para_id"))
            translations.append({
                "para_id": t.get("para_id"),
                "translation": t.get("translation"),
                "source_section": p["section"] if p else None,
                "source_span": p["char_span"] if p else None,
                "uncertain": bool(t.get("uncertain")),
                "note": t.get("note"),
            })
        glossary = tr.get("glossary") or {}
        cov = verification["coverage"]
        n_g = len(verification["glossary_violations"])
        n_f = len(verification["fact_violations"])
        if cov["missing"] or cov["extra"] or cov["duplicated"]:
            status = "partial"
            problems.append("coverage_incomplete")
        if n_g:
            status = "partial"
            problems.append("glossary_violations:%d" % n_g)
        if n_f > 0 and n_f > max(2, 0.2 * len(paras)):
            status = "partial"
            problems.append("fact_violations:%d" % n_f)
        if verification["anchor_bad"]:
            status = "partial"
            problems.append("paragraph_order_shifted")
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "translations": translations,
        "glossary": glossary,
        "verification": verification,
        "source_file": (segs or {}).get("source_file"),
        "uncertainty": [t for t in translations if t.get("uncertain")],
        "changes_log": [
            {"change": "segment", "detail": "run.py stage segment", "paras": len((segs or {}).get("paras", []))},
            {"change": "translate", "detail": "agent pass with glossary lock"},
            {"change": "verify", "detail": "coverage+glossary+fact checks", "violations": len(problems)},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status, "paras": len(translations),
                      "glossary_terms": len(glossary), "problems": problems,
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["segment", "verify", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--translation", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    try:
        (stage_segment if args.stage == "segment" else
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
                  "translations": [], "glossary": {},
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
