#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper-structured-notes: deterministic extraction + finalize for source-grounded notes.

Stages
  extract  : /input/case.json -> /app/work/segments.json + case_meta.json
  finalize : merge agent notes -> /app/output/result.json

Design rules (competition-proven):
  - stdlib only for the engine; optional PDF backends probed at runtime
  - top-level try/except: ALWAYS write a contract-shaped result.json
  - missing -> null / not_reported; never reject the whole chain
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

# ---------------------------------------------------------------- case parsing

CASE_FIELD_ALIASES = {
    "case_id": ["case_id", "id", "caseId"],
    "task": ["task", "task_description", "question", "instruction", "prompt"],
    "materials": ["materials", "files", "inputs", "sources", "documents", "paper", "pdf"],
}


def _pick(d, names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d and d[n] not in (None, "", [], {}):
            return d[n]
    return default


def load_case(input_dir):
    """Tolerant case.json reader. Returns (case_dict, meta_dict)."""
    path = os.path.join(input_dir, "case.json")
    raw = None
    err = None
    if os.path.exists(path):
        try:
            with io.open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:  # malformed json
            err = "malformed_case_json: %s" % e
    else:
        # look for any *.json that looks like a case
        for fn in sorted(os.listdir(input_dir)):
            if fn.endswith(".json"):
                try:
                    with io.open(os.path.join(input_dir, fn), "r", encoding="utf-8") as f:
                        cand = json.load(f)
                    if isinstance(cand, dict) and ("case" in fn or _pick(cand, CASE_FIELD_ALIASES["case_id"])):
                        raw, path = cand, os.path.join(input_dir, fn)
                        break
                except Exception:
                    continue
    case = raw if isinstance(raw, dict) else {}
    if err is None and raw is None:
        err = "missing_case_json"
    meta = {
        "case_path": path if raw is not None else None,
        "case_id": _pick(case, CASE_FIELD_ALIASES["case_id"]),
        "task": _pick(case, CASE_FIELD_ALIASES["task"]),
        "parse_error": err,
    }
    return case, meta


def contract_keys(case):
    """Every key the output_contract declares, whatever shape it takes."""
    oc = case.get("output_contract") or case.get("outputContract") or case.get("contract")
    keys = []
    if isinstance(oc, dict):
        for k, v in oc.items():
            if isinstance(v, (list,)) and v and isinstance(v[0], str):
                keys.extend(v)  # {"answer_fields": ["a","b"]} style
            elif k not in ("type", "format", "$schema", "version"):
                keys.append(k)
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                keys.append(item)
            elif isinstance(item, dict) and item.get("name"):
                keys.append(item["name"])
    return sorted(set(keys))


def material_paths(case, input_dir):
    """Resolve material files: strings (paths) or dicts with path/content fields."""
    mats = _pick(case, CASE_FIELD_ALIASES["materials"], default=[])
    out = []
    if isinstance(mats, str):
        mats = [mats]
    if isinstance(mats, dict):
        mats = [mats.get(k) for k in ("path", "file", "url", "content") if mats.get(k)]
    for m in mats or []:
        if isinstance(m, str):
            p = m if os.path.isabs(m) else os.path.join(input_dir, m)
            if os.path.exists(p):
                out.append(p)
            elif os.path.exists(m):
                out.append(os.path.abspath(m))
        elif isinstance(m, dict):
            p = m.get("path") or m.get("file")
            if p:
                p = p if os.path.isabs(p) else os.path.join(input_dir, p)
                if os.path.exists(p):
                    out.append(p)
    return out

# ---------------------------------------------------------------- pdf/text extraction

PDF_BACKENDS = []


def _try_backends():
    global PDF_BACKENDS
    try:
        import fitz  # PyMuPDF
        PDF_BACKENDS.append("pymupdf")
    except Exception:
        pass
    try:
        from pdfminer.high_level import extract_text as pm_text
        PDF_BACKENDS.append("pdfminer")
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        PDF_BACKENDS.append("pypdf")
    except Exception:
        try:
            from PyPDF2 import PdfReader
            PDF_BACKENDS.append("pypdf2")
        except Exception:
            pass
    import shutil
    if shutil.which("pdftotext"):
        PDF_BACKENDS.append("pdftotext")


def _norm_ws(s):
    return re.sub(r"[ \t]+", " ", s.replace("\r\n", "\n").replace("\r", "\n"))


def extract_pdf_pages(path):
    """Returns (pages:[{text,char_count}], backend, anomaly). Never raises."""
    _try_backends()
    anomaly = None
    for backend in PDF_BACKENDS:
        try:
            if backend == "pymupdf":
                import fitz
                doc = fitz.open(path)
                pages = [_norm_ws(p.get_text("text")) for p in doc]
                doc.close()
                return pages, "pymupdf", anomaly
            if backend == "pdfminer":
                from pdfminer.high_level import extract_pages
                from pdfminer.layout import LTTextContainer
                pages = []
                for page_layout in extract_pages(path):
                    buf = []
                    for el in page_layout:
                        if isinstance(el, LTTextContainer):
                            buf.append(el.get_text())
                    pages.append(_norm_ws("\n".join(buf)))
                return pages, "pdfminer", anomaly
            if backend in ("pypdf", "pypdf2"):
                if backend == "pypdf":
                    from pypdf import PdfReader
                else:
                    from PyPDF2 import PdfReader
                r = PdfReader(path)
                pages = [_norm_ws((p.extract_text() or "")) for p in r.pages]
                return pages, backend, anomaly
            if backend == "pdftotext":
                import subprocess, tempfile
                pages = []
                with tempfile.TemporaryDirectory() as td:
                    # page-split mode for per-page text
                    n = None
                    try:
                        info = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=60)
                        m = re.search(r"Pages:\s+(\d+)", info.stdout or "")
                        n = int(m.group(1)) if m else None
                    except Exception:
                        n = None
                    if not n:
                        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=120)
                        return [_norm_ws(out.stdout)], "pdftotext", "single_blob"
                    for i in range(1, n + 1):
                        out = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", path, "-"], capture_output=True, text=True, timeout=120)
                        pages.append(_norm_ws(out.stdout))
                return pages, "pdftotext", anomaly
        except Exception:
            continue
    return [], None, "no_backend_or_unreadable_pdf"


def extract_any(path):
    """Any material -> (pages, backend, anomaly)."""
    if not os.path.exists(path):
        return [], None, "missing_file"
    low = path.lower()
    if low.endswith(".pdf"):
        return extract_pdf_pages(path)
    if low.endswith((".txt", ".md", ".text")):
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return [_norm_ws(f.read())], "plaintext", None
    if low.endswith((".json",)):
        try:
            with io.open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            # find the big text blob(s)
            blobs = []

            def walk(o):
                if isinstance(o, str) and len(o) > 200:
                    blobs.append(_norm_ws(o))
                elif isinstance(o, dict):
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(data)
            return blobs or [json.dumps(data, ensure_ascii=False)], "json_text", None
        except Exception:
            with io.open(path, "r", encoding="utf-8", errors="replace") as f:
                return [_norm_ws(f.read())], "json_raw", "json_parse_failed"
    if low.endswith((".xml", ".nxml", ".html", ".htm")):
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        text = re.sub(r"<[^>]+>", "\n", raw)
        text = _norm_ws(text)
        return [text], "xml_strip", None
    with io.open(path, "r", encoding="utf-8", errors="replace") as f:
        return [_norm_ws(f.read())], "raw", None

# ---------------------------------------------------------------- segmentation

HEADER_RE = re.compile(
    r"^\s*(?:"
    r"(?:abstract|summary|introduction|background|related\s+work|methods?|materials?\s+and\s+methods?|"
    r"experimental(?:\s+(?:section|setup|procedures))?|results?(?:\s+and\s+discussion)?|discussion|"
    r"conclusions?|acknowledg(?:e?ments?|ments?)|references?|supplementary(?:\s+material)?|data\s+availability"
    r"|[ivx]+\.|[0-9]+(?:\.[0-9]+)*\.?|[0-9]+\s+[A-Z])"
    r"[^\n]{0,80})$",
    re.IGNORECASE,
)
CN_HEADER_RE = re.compile(r"^\s*(摘\s*要|引\s*言|前\s*言|相关工作|方\s*法|材料与方法|实验(?:与?方法|部分|设置)?|结\s*果|结果与讨论|讨\s*论|结\s*论|结论与展望|致\s*谢|参考文献|附录)\s*$")
CAPTION_RE = re.compile(r"^(?:图|表|Figure|Fig\.?|Table)\s*\.?\s*\d+", re.IGNORECASE)


def detect_header(line, next_line=""):
    s = line.strip()
    if not (2 < len(s) <= 90):
        return None
    if CAPTION_RE.match(s):
        return None
    # numbered heading like "2.1 Thermal analysis" — short, ends w/o period, Next not continuation
    if re.match(r"^\d+(?:\.\d+)*\.?\s+\S", s) and not s.endswith("."):
        return s
    if HEADER_RE.match(s) and not s.endswith(".") and (next_line is None or next_line.strip() == "" or next_line[:1].isupper() or True):
        m = re.match(r"^[ivx]+\.", s)
        if m or len(s.split()) <= 12:
            return s
    if CN_HEADER_RE.match(s):
        return s
    return None


def segment_pages(pages):
    """pages -> paragraphs list with anchors + sections list."""
    paras = []
    sections = []
    cur_section = "preamble"
    for pno, text in enumerate(pages, start=1):
        start = 0
        if not text or not text.strip():
            paras.append({"page": pno, "section": cur_section, "para_index": len(paras),
                          "text": "", "char_span": [0, 0]})
            continue
        # split on blank lines; join lines inside a paragraph
        blocks = re.split(r"\n\s*\n", text)
        pos = 0
        for b in blocks:
            btxt = "\n".join(ln.strip() for ln in b.split("\n") if ln.strip())
            # locate block start (search from pos for first non-space char of b)
            first_char = b.lstrip()[:1]
            idx = text.find(first_char, pos) if first_char else pos
            if idx < 0:
                idx = pos
            h = detect_header(btxt.split("\n")[0] if btxt else "")
            if h:
                cur_section = h
                sections.append({"section": h, "page": pno, "para_index": len(paras)})
            # each visual paragraph within block = one note-able paragraph
            sub = re.split(r"\n(?=[A-Z\u4e00-\u9fff0-9•\-–])", btxt)
            for s in sub:
                s = s.strip()
                if not s:
                    continue
                sidx = text.find(s[:24], idx) if s else -1
                if sidx < 0:
                    sidx = idx
                paras.append({"page": pno, "section": cur_section, "para_index": len(paras),
                              "text": s, "char_span": [sidx, sidx + len(s)]})
                idx = sidx + len(s)
            pos = idx
    # trim empties
    paras = [p for p in paras if p["text"]]
    return paras, sections

# ---------------------------------------------------------------- stages

def stage_extract(args):
    os.makedirs(WORK, exist_ok=True)
    case, meta = load_case(args.input)
    mats = material_paths(case, args.input)
    if not mats:
        # last resort: any pdf/text file in input dir
        for fn in sorted(os.listdir(args.input)):
            if fn.lower().endswith((".pdf", ".txt", ".md", ".xml", ".nxml")) and fn != "task.md":
                mats.append(os.path.join(args.input, fn))
    if not mats:
        mats = [os.path.join(args.input, "task.md")] if os.path.exists(os.path.join(args.input, "task.md")) else []
    all_paras, all_sections, page_map, backends, anomalies = [], [], {}, [], []
    for mp in mats:
        pages, backend, anomaly = extract_any(mp)
        backends.append({"file": os.path.basename(mp), "backend": backend, "pages": len(pages)})
        if anomaly:
            anomalies.append({"file": os.path.basename(mp), "anomaly": anomaly})
        base = len(page_map)
        for i, t in enumerate(pages):
            page_map[base + i + 1] = {"file": os.path.basename(mp), "chars": len(t)}
        # keep raw page texts for audit re-slicing
        for i, t in enumerate(pages):
            fn = os.path.join(WORK, "page_%03d.txt" % (base + i + 1))
            with io.open(fn, "w", encoding="utf-8") as f:
                f.write(t)
        paras, sections = segment_pages(pages)
        for p in paras:
            p["page"] = base + p["page"]
        for s in sections:
            s["page"] = base + s["page"]
        all_paras.extend(paras)
        all_sections.extend(sections)
        if all(p["text"] == "" for p in paras) and pages:
            anomalies.append({"file": os.path.basename(mp), "anomaly": "no_text_layer"})
    segments = {
        "case_id": meta["case_id"],
        "paragraphs": all_paras,
        "sections": all_sections,
        "pages": page_map,
        "extraction": {"backends": backends, "anomalies": anomalies},
        "note": "char_span is [start,end) into the page text stored verbatim in work/page_%03d.txt; audit.py re-slices it.",
    }
    with io.open(os.path.join(WORK, "segments.json"), "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=1)
    meta["contract_keys"] = contract_keys(case)
    meta["materials"] = [os.path.basename(m) for m in mats]
    with io.open(os.path.join(WORK, "case_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "extract", "pages": len(page_map), "paragraphs": len(all_paras),
                      "sections": len(all_sections), "backends": backends, "anomalies": anomalies}, ensure_ascii=False))


def _load_notes(path):
    if not os.path.exists(path):
        return None
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_status(segments, notes, problems):
    if segments is None:
        return "cannot_determine", ["segments_missing"]
    if not segments.get("paragraphs"):
        return "cannot_determine", ["no_extractable_text"]
    if notes is None:
        return "partial", ["notes_missing: run semantic pass first"]
    if not notes.get("cards"):
        return "partial", ["no_cards"]
    if problems:
        return "partial", problems
    return "success", []


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, meta = load_case(args.input)
    seg_path = os.path.join(WORK, "segments.json")
    segments = _load_notes(seg_path)
    notes = _load_notes(args.notes) if args.notes else None
    keys = contract_keys(case)
    problems = []
    # --- validate notes against segments
    valid_notes = {}
    if notes and segments:
        by_id = {p["para_index"]: p for p in segments.get("paragraphs", [])}
        for n in notes.get("notes", []) or []:
            pid = n.get("para_index")
            quote = n.get("quote", "")
            page = n.get("page")
            if pid not in by_id:
                problems.append("note %s: para_index %s not in segments" % (n.get("note_id"), pid))
                continue
            para = by_id[pid]
            if quote and quote not in para["text"]:
                problems.append("note %s: quote not verbatim in paragraph %s" % (n.get("note_id"), pid))
                n["quote_mismatch"] = True
            if page is not None and para["page"] != page:
                problems.append("note %s: page %s != segment page %s" % (n.get("note_id"), page, para["page"]))
                n["page_corrected"] = para["page"]
            n["page"] = para["page"]
            n["char_span"] = para["char_span"]
            n["section"] = para["section"]
            valid_notes[n.get("note_id")] = n
    cards = []
    if notes:
        for c in notes.get("cards", []) or []:
            card = {"section": c.get("section"), "page": c.get("page")}
            for field in ("research_question", "data", "method_conditions", "main_findings",
                          "limitations", "assumptions"):
                v = c.get(field)
                if isinstance(v, dict):
                    nids = [i for i in (v.get("note_ids") or []) if i in valid_notes]
                    bad = len(nids) != len(v.get("note_ids") or [])
                    if bad:
                        problems.append("card %s field %s: dangling note_ids %s" % (c.get("section"), field, v.get("note_ids")))
                    card[field] = {"text": v.get("text", "not_reported"), "note_ids": nids}
                elif isinstance(v, str):
                    card[field] = {"text": v, "note_ids": []}
                else:
                    card[field] = {"text": "not_reported", "note_ids": []}
            cards.append(card)
    status, reasons = _compute_status(segments, notes, problems)
    result = {
        "case_id": meta["case_id"],
        "status": status,
        "status_reasons": reasons,
        "cards": cards,
        "notes": [valid_notes[k] for k in sorted(valid_notes, key=lambda x: (x is None, x))] if valid_notes else [],
        "evidence": {
            "pages": (segments or {}).get("pages", {}),
            "sections": (segments or {}).get("sections", []),
            "anchor_unit": "page text file (work/page_%03d.txt), char_span=[start,end)",
        },
        "extraction": (segments or {}).get("extraction", {"backends": [], "anomalies": [{"anomaly": "segments_missing"}]}),
        "uncertainty": [n for n in (notes or {}).get("uncertainty", [])] if notes else [],
        "not_reported_count": sum(1 for c in cards for f in c.values()
                                  if isinstance(f, dict) and f.get("text") == "not_reported"),
        "changes": [
            {"change": "extraction", "detail": "run.py stage extract", "result": "segments.json"},
            {"change": "cards", "detail": "agent semantic pass", "result": "notes.json"},
            {"change": "validation", "detail": "anchor + contract checks", "problems": problems[:20]},
        ],
        "handoff": ("OCR required: no text layer detected" if any(a.get("anomaly") in ("no_text_layer",)
                   for a in ((segments or {}).get("extraction", {}).get("anomalies", []))) else None),
    }
    # fill every output_contract key (null when unknown) — never drop keys
    base = {"cards": result["cards"], "notes": result["notes"], "status": result["status"]}
    for k in keys:
        if k not in result:
            result[k] = base.get(k, None)
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status, "cards": len(cards),
                      "notes": len(valid_notes), "problems": problems[:10],
                      "contract_keys_filled": keys}, ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extract", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--notes", default=os.path.join(WORK, "notes.json"))
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    try:
        if args.stage == "extract":
            stage_extract(args)
        else:
            stage_finalize(args)
    except Exception:
        # last-resort: still write a contract-shaped result.json
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            _, meta = load_case(args.input)
        except Exception:
            meta = {}
        result = {
            "case_id": meta.get("case_id"),
            "status": "partial",
            "status_reasons": ["engine_exception"],
            "cards": [], "notes": [],
            "error": err[-1500:],
            "handoff": "inspect error field; stages are restartable",
        }
        try:
            case, _ = load_case(args.input)
            for k in contract_keys(case):
                result.setdefault(k, None)
        except Exception:
            pass
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)  # contract satisfied; do not crash the chain


if __name__ == "__main__":
    main()
