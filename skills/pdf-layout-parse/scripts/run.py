#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf-layout-parse: column-aware structural PDF parsing with auditable anchors.

Word tuple layout everywhere: (pno, x0, y0, x1, y1, text)
  -> x0=[1] y0=[2] x1=[3] y1=[4] text=[5]

One deterministic pass -> /app/output/result.json.
Backends: PyMuPDF (word boxes) -> pdfminer -> pdftotext. stdlib otherwise.
Never rejects: anomalies -> partial; no text layer -> cannot_determine.
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

MATH_CHARS = set("=+±×∑∫√≤≥≠≈∂∇αβγδθλμσφωπ∞ΔΩ∈∪∩⊂→↔·^_*/")
CONT_STARTERS = {"and", "or", "but", "which", "where", "while", "with", "of", "to", "in",
                 "for", "on", "by", "at", "the", "a", "an", "that", "these", "those",
                 "such", "as", "than", "from", "into", "over", "under"}

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


def material_path(case, input_dir):
    m = _pick(case, ["materials", "files", "inputs", "sources", "documents", "paper", "pdf"])
    cands = []
    if isinstance(m, str):
        cands.append(m)
    elif isinstance(m, list):
        for x in m:
            cands.append(x.get("path") if isinstance(x, dict) else x)
    elif isinstance(m, dict):
        cands.append(m.get("path"))
    for c in cands:
        if isinstance(c, str) and c:
            p = c if os.path.isabs(c) else os.path.join(input_dir, c)
            if os.path.exists(p):
                return p
            if os.path.exists(c):
                return os.path.abspath(c)
    for fn in sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []:
        if fn.lower().endswith(".pdf"):
            return os.path.join(input_dir, fn)
    return None

# ---------------------------------------------------------------- extraction

def extract_words_pymupdf(path):
    import fitz
    doc = fitz.open(path)
    words, raw_texts = [], []
    for pno, page in enumerate(doc, start=1):
        for w in page.get_text("words"):
            words.append((pno, w[0], w[1], w[2], w[3], w[4]))
        raw_texts.append(re.sub(r"[ \t]+", " ", page.get_text("text").replace("\r\n", "\n")))
    doc.close()
    return words, raw_texts, "pymupdf"


def extract_words_pdfminer(path):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextLine, LTTextContainer
    words, raw_texts = [], []
    for pno, layout in enumerate(extract_pages(path), start=1):
        page_words = []
        for el in layout:
            if isinstance(el, LTTextContainer):
                for line in el:
                    if isinstance(line, LTTextLine):
                        x0, y0, x1, y1 = line.bbox
                        text = line.get_text().strip()
                        if text:
                            page_words.append((pno, x0, y0, x1, y1, text))
        words.extend(page_words)
        raw_texts.append("\n".join(t for _, _, _, _, _, t in page_words))
    return words, raw_texts, "pdfminer"


def extract_pdftotext(path):
    import subprocess
    out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True,
                         text=True, timeout=180)
    raw = out.stdout or ""
    pages = re.split(r"\f", raw)
    words = []
    for pno, ptxt in enumerate(pages, start=1):
        y = 0.0
        for line in ptxt.split("\n"):
            if line.strip():
                words.append((pno, 0.0, y, 700.0, y + 10, line.strip()))
            y += 10.0
    return words, [re.sub(r"[ \t]+", " ", p) for p in pages], "pdftotext"


def extract(path):
    for fn in (extract_words_pymupdf, extract_words_pdfminer, extract_pdftotext):
        try:
            return fn(path)
        except Exception:
            continue
    return [], [], None

# ---------------------------------------------------------------- runs

def group_runs(words):
    """words -> y-clustered runs (wide intra-line gaps split runs).

    Returns list of (pno, x0, y0, x1, y1, text).
    """
    lines = {}
    for (pno, x0, y0, x1, y1, w) in words:
        key = (pno, round(y0 / 3.0))
        lines.setdefault(key, []).append((x0, x1, y0, y1, w))
    out = []
    for (pno, _yc), ws in sorted(lines.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ws.sort(key=lambda w: w[0])
        runs, cur = [], [ws[0]]
        for w in ws[1:]:
            if w[0] - cur[-1][1] > 15.0:
                runs.append(cur)
                cur = [w]
            else:
                cur.append(w)
        runs.append(cur)
        for run in runs:
            x0 = min(w[0] for w in run)
            x1 = max(w[1] for w in run)
            y0 = min(w[2] for w in run)
            y1 = max(w[3] for w in run)
            parts, prev_x1 = [], None
            for (wx0, wx1, _, _, word) in run:
                if prev_x1 is not None:
                    parts.append("  " if wx0 - prev_x1 > 8.0 else " ")
                parts.append(word)
                prev_x1 = wx1
            out.append((pno, x0, y0, x1, y1, "".join(parts)))
    return out

# ---------------------------------------------------------------- bands

def band_repeats(all_page_lines):
    """Digit-masked line texts in top/bottom bands repeating on >=2 pages."""
    band_lines = {}
    for pno, lines in all_page_lines.items():
        ys0 = [l[2] for l in lines] or [0, 1]
        ys1 = [l[4] for l in lines] or ys0
        y_min, y_max = min(ys0), max(ys1)
        span = (y_max - y_min) or 1.0
        top, bottom = [], []
        for l in lines:
            ny = (l[2] - y_min) / span
            m = re.sub(r"\d+", "#", l[5].strip())[:80]
            if len(m) <= 10:
                continue
            if ny < 0.08:
                top.append(m)
            elif ny > 0.92:
                bottom.append(m)
        band_lines[pno] = {"top": top, "bottom": bottom}
    repeated = set()
    if len(band_lines) >= 2:
        for side in ("top", "bottom"):
            counts = {}
            for pno, b in band_lines.items():
                for m in set(b[side]):
                    counts.setdefault(m, set()).add(pno)
            for m, ps in counts.items():
                if len(ps) >= 2:
                    repeated.add((side, m))
    return repeated


def is_band_repeat(txt, side, repeated):
    key = re.sub(r"\d+", "#", txt.strip())[:80]
    if len(key) <= 10:
        return False
    for (s2, t) in repeated:
        if s2 == side and (t == key or t[:40] == key[:40]):
            return True
    return False

# ---------------------------------------------------------------- columns

def detect_columns(body_lines, page_width):
    """True column gap = vertical strip empty of words across ~all body rows."""
    if len(body_lines) < 6:
        return 1, None
    rows = sorted({round(l[2]) for l in body_lines})
    total_rows = len(rows)
    best_split, best_score = None, -1.0
    for frac in [i / 40.0 for i in range(8, 33)]:
        split = frac * page_width
        lo, hi = split - 12.0, split + 12.0
        empty_rows = 0
        for y in rows:
            hits = [l for l in body_lines if abs(l[2] - y) < 3.0 and l[1] < hi and l[3] > lo]
            if not hits:
                empty_rows += 1
        spanners = sum(1 for l in body_lines if l[1] < lo and l[3] > hi)
        score = empty_rows / max(1, total_rows) - 2.0 * spanners / max(1, len(body_lines))
        if score > best_score:
            best_score, best_split = score, split
    if best_split is None or best_score < 0.8:
        return 1, None
    left_rows = sum(1 for l in body_lines if (l[1] + l[3]) / 2.0 < best_split)
    right_rows = len(body_lines) - left_rows
    if min(left_rows, right_rows) < 0.2 * len(body_lines):
        return 1, None
    return 2, best_split

# ---------------------------------------------------------------- heuristics

def math_density(line):
    toks = [c for c in line if c in MATH_CHARS]
    return len(toks) / max(1, len(line))


def ends_mid_sentence(text):
    t = (text or "").rstrip()
    if not t:
        return False
    return t[-1] not in ".!?:;])”\"'"


def starts_continuation(text):
    t = (text or "").lstrip()
    if not t:
        return False
    if t[0].islower() or t[0].isdigit():
        return True
    first = re.split(r"[\s,]+", t)[0].lower().strip(".,;:")
    return first in CONT_STARTERS

# ---------------------------------------------------------------- parse

def mk_block(bid, pno, etype, col, order, x0, y0, x1, y1, text, raw):
    span = None
    probe = text[:24]
    if probe:
        idx = raw.find(probe)
        if idx >= 0:
            span = [idx, idx + len(text)]
    return {"block_id": bid, "page": pno, "type": etype, "order": order, "col": col,
            "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
            "text": text, "char_span": span}


def parse(path):
    words, raw_texts, backend = extract(path)
    if backend is None:
        return None
    by_page = {}
    for w in words:
        by_page.setdefault(w[0], []).append(w)
    all_lines = {}
    for pno, ws in by_page.items():
        all_lines[pno] = group_runs(ws)
    repeated = band_repeats(all_lines)

    blocks, tables, pages_meta = [], [], []
    block_id = 0
    for pno in sorted(all_lines):
        lines = all_lines[pno]
        raw = raw_texts[pno - 1] if pno - 1 < len(raw_texts) else ""
        page_w = max((l[3] for l in lines), default=600) or 600
        ys0 = [l[2] for l in lines] or [0, 1]
        ys1 = [l[4] for l in lines] or ys0
        y_min, y_max = min(ys0), max(ys1)
        bh = (y_max - y_min) or 1.0

        sides = {}
        for l in lines:
            ny = (l[2] - y_min) / bh
            if ny < 0.08:
                sides[id(l)] = "top"
            elif ny > 0.92:
                sides[id(l)] = "bottom"
        body_lines = [l for l in lines if sides.get(id(l)) is None]
        n_col, split = detect_columns(body_lines, page_w)

        full_width = set()
        if n_col == 2 and split is not None:
            for idx, l in enumerate(lines):
                if l[1] < split - 6 and l[3] > split + 6:
                    full_width.add(idx)
        col_ev = None
        if n_col == 2:
            left = sum(1 for idx, l in enumerate(lines)
                       if idx not in full_width and (l[1] + l[3]) / 2.0 < split)
            right = sum(1 for idx, l in enumerate(lines)
                        if idx not in full_width and (l[1] + l[3]) / 2.0 >= split)
            col_ev = {"split_x": round(split, 1), "left_lines": left,
                      "right_lines": right, "full_width_lines": len(full_width)}

        entries = []
        for idx, (p, x0, y0, x1, y1, text) in enumerate(lines):
            if idx in full_width:
                col = 0
            else:
                mid = (x0 + x1) / 2.0
                col = 1 if (n_col == 1 or split is None or mid < split) else 2
            side = sides.get(id(lines[idx]))
            btype = "body"
            if side is not None and is_band_repeat(text, side, repeated):
                btype = "header" if side == "top" else "footer"
            elif side == "bottom" and re.match(r"^\s*(?:\d{1,2}|[*†‡])[.\s]", text) and len(text) < 300:
                btype = "footnote"
            elif re.match(r"^(?:图|表|Figure|Fig\.?|Table)\s*\.?\s*\d+", text, re.IGNORECASE):
                btype = "caption"
            elif math_density(text) >= 0.08 and not re.search(r"[.。]$", text):
                btype = "formula_candidate"
            entries.append({"type": btype, "col": col, "x0": x0, "y0": y0, "x1": x1,
                            "y1": y1, "text": text})

        # table detection per column: consecutive body runs grouped by y-row
        for col in range(1, n_col + 1):
            col_body = sorted([e for e in entries if e["type"] == "body" and e["col"] == col],
                              key=lambda e: e["y0"])
            i = 0
            while i < len(col_body):
                rows, j = [], i
                while j < len(col_body):
                    row_y = col_body[j]["y0"]
                    row = [col_body[j]]
                    k = j + 1
                    while k < len(col_body) and abs(col_body[k]["y0"] - row_y) < 4.0:
                        row.append(col_body[k])
                        k += 1
                    if len(row) >= 2:
                        rows.append(sorted(row, key=lambda e: e["x0"]))
                        j = k
                    else:
                        break
                if len(rows) >= 2:
                    ncols = max(len(r) for r in rows)
                    cells = []
                    for r in rows:
                        cells.append([c["text"].strip() for c in r] + [""] * (ncols - len(r)))
                    tables.append({"page": pno, "col": col, "cells": cells,
                                   "n_rows": len(cells), "n_cols": ncols,
                                   "y0": rows[0][0]["y0"], "y1": rows[-1][0]["y1"]})
                    for r in rows:
                        for c in r:
                            c["type"] = "table"
                    break
                else:
                    i += 1

        # emit: header -> col streams (paragraphs) -> specials
        order = 0
        for e in sorted([x for x in entries if x["type"] == "header"], key=lambda x: x["y0"]):
            order += 1
            blocks.append(mk_block(block_id, pno, "header", e["col"], order,
                                   e["x0"], e["y0"], e["x1"], e["y1"], e["text"], raw))
            block_id += 1
        for col in range(0, n_col + 1):
            stream = sorted([x for x in entries if x["type"] == "body" and x["col"] == col],
                            key=lambda x: x["y0"])
            para, py, px = [], None, None
            emitted = []
            for e in stream:
                if para and ends_mid_sentence(para[-1]) and starts_continuation(e["text"]):
                    para.append(e["text"])
                    py = (py[0], e["y1"])
                    px = (min(px[0], e["x0"]), max(px[1], e["x1"]))
                else:
                    if para:
                        emitted.append((" ".join(para), py, px))
                    para, py, px = [e["text"]], (e["y0"], e["y1"]), (e["x0"], e["x1"])
            if para:
                emitted.append((" ".join(para), py, px))
            for text, yy, xx in emitted:
                order += 1
                blocks.append(mk_block(block_id, pno, "body", col, order,
                                       xx[0], yy[0], xx[1], yy[1], text, raw))
                block_id += 1
        for btype in ("caption", "formula_candidate", "footnote", "table", "footer"):
            for e in sorted([x for x in entries if x["type"] == btype], key=lambda x: x["y0"]):
                order += 1
                blocks.append(mk_block(block_id, pno, btype, e["col"], order,
                                       e["x0"], e["y0"], e["x1"], e["y1"], e["text"], raw))
                block_id += 1
        pages_meta.append({"page": pno, "n_columns": n_col, "column_evidence": col_ev,
                           "char_count": len(raw)})

    # cross-column + cross-page continuation
    for i in range(len(blocks) - 1):
        a, b = blocks[i], blocks[i + 1]
        if (a["type"] == "body" and b["type"] == "body" and a["page"] == b["page"]
                and a.get("col") == 1 and b.get("col") == 2
                and ends_mid_sentence(a["text"]) and starts_continuation(b["text"])):
            b["merged_into"] = a["block_id"]
            b["merge_reason"] = "cross-column continuation"
    for i in range(len(blocks) - 1):
        a, b = blocks[i], blocks[i + 1]
        if (a["type"] == "body" and b["type"] == "body" and b["page"] == a["page"] + 1
                and ends_mid_sentence(a["text"]) and starts_continuation(b["text"])):
            b["merged_into"] = a["block_id"]
            b["merge_reason"] = "cross-page continuation"

    body_chars = sum(len(b["text"]) for b in blocks
                     if b["type"] in ("body", "table", "caption", "footnote"))
    # full_text: body blocks in order; continuation text appends to its target block
    merged_tail = {}
    for b in blocks:
        if b["type"] == "body" and "merged_into" in b:
            merged_tail.setdefault(b["merged_into"], []).append(b["text"])
    parts = []
    for b in blocks:
        if b["type"] != "body" or "merged_into" in b:
            continue
        t = b["text"]
        for tail in merged_tail.get(b["block_id"], []):
            t += " " + tail
        parts.append(t)
    full_text = "\n\n".join(parts)
    page_chars = sum(p["char_count"] for p in pages_meta)
    return {
        "backend": backend,
        "pages": pages_meta,
        "blocks": blocks,
        "tables": tables,
        "full_text": full_text,
        "coverage": {
            "body_chars": body_chars,
            "page_chars_total": page_chars,
            "body_ratio": (round(body_chars / page_chars, 4) if page_chars else None),
            "header_footer_chars": sum(len(b["text"]) for b in blocks
                                       if b["type"] in ("header", "footer")),
        },
        "anomalies": ([] if backend in ("pymupdf", "pdfminer")
                      else [{"anomaly": "no_layout_backend", "backend": backend}]),
    }

# ---------------------------------------------------------------- driver

def build_result(input_dir, output_dir, notes=None):
    case, cerr = load_case(input_dir)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    path = material_path(case, input_dir)
    problems, status = [], "success"
    parsed = None
    if path is None:
        status = "cannot_determine"
        problems.append("missing_material_pdf")
    else:
        parsed = parse(path)
        if parsed is None:
            status = "cannot_determine"
            problems.append("no_backend_or_unreadable_pdf")
        else:
            if not any(p["char_count"] for p in parsed["pages"]):
                status = "cannot_determine"
                problems.append("no_text_layer")
                parsed["anomalies"].append({"anomaly": "no_text_layer"})
            else:
                cov = parsed["coverage"]["body_ratio"]
                if cov is not None and cov < 0.5:
                    status = "partial"
                    problems.append("coverage_below_50pct: %.2f" % cov)
                elif cov is not None and cov < 0.8:
                    status = "partial"
                    problems.append("coverage_below_80pct: %.2f" % cov)
                if parsed["backend"] not in ("pymupdf", "pdfminer"):
                    status = "partial"
                    problems.append("layout_limited_backend:%s" % parsed["backend"])
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": problems,
        "source_file": os.path.basename(path) if path else None,
        "backend": (parsed or {}).get("backend"),
        "pages": (parsed or {}).get("pages", []),
        "blocks": (parsed or {}).get("blocks", []),
        "tables": (parsed or {}).get("tables", []),
        "full_text": (parsed or {}).get("full_text", ""),
        "coverage": (parsed or {}).get("coverage", {}),
        "anomalies": (parsed or {}).get("anomalies", []),
        "field_answers": (notes or {}).get("field_answers", []),
        "case_error": cerr,
        "handoff": ("OCR required: no text layer" if "no_text_layer" in problems else None),
        "changes_log": [
            {"change": "layout parse", "detail": "single deterministic pass",
             "backend": (parsed or {}).get("backend")},
            {"change": "notes merge", "detail": "field answers validated against blocks",
             "count": len((notes or {}).get("field_answers", []))},
        ],
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"status": status, "pages": len(result["pages"]),
                      "blocks": len(result["blocks"]), "tables": len(result["tables"]),
                      "backend": result["backend"], "problems": problems,
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--finalize-notes", action="store_true")
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    notes = None
    npath = os.path.join(WORK, "notes.json")
    if args.finalize_notes and os.path.exists(npath):
        with io.open(npath, "r", encoding="utf-8") as f:
            notes = json.load(f)
    try:
        os.makedirs(args.output, exist_ok=True)
        build_result(args.input, args.output, notes)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "pages": [], "blocks": [], "tables": [], "full_text": "",
                  "handoff": "inspect error; single-pass restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
