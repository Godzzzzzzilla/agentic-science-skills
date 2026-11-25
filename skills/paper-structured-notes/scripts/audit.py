#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper-structured-notes: one-command audit.

Re-creates every note quote from the SOURCE material using recorded anchors,
then checks contract-key coverage, note_id wiring, not_reported discipline,
and status consistency. Exit 0 = green; 1 = problems (printed, machine-readable).

Usage:
    python3 scripts/audit.py --input /input --output /app/output [--work /app/work]
"""
import argparse
import io
import json
import os
import re
import sys

PASS, FAIL = 0, 1


def load_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_materials(input_dir, case):
    mats = []
    if isinstance(case, dict):
        for key in ("materials", "files", "inputs", "sources", "documents", "paper", "pdf"):
            v = case.get(key)
            if isinstance(v, str):
                mats.append(v)
            elif isinstance(v, list):
                for m in v:
                    mats.append(m.get("path") if isinstance(m, dict) else m)
    seen, out = set(), []
    for m in mats:
        if not isinstance(m, str) or not m:
            continue
        p = m if os.path.isabs(m) else os.path.join(input_dir, m)
        if os.path.exists(p) and p not in seen:
            seen.add(p)
            out.append(p)
    for fn in sorted(os.listdir(input_dir)):
        p = os.path.join(input_dir, fn)
        if fn.lower().endswith((".pdf", ".txt", ".md", ".nxml", ".xml")) and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def source_text_of(path):
    """Best-effort plain-text of the source, used for quote re-matching."""
    low = path.lower()
    if low.endswith(".pdf"):
        # same backend chain as run.py, so anchors line up with extraction
        try:
            import fitz
            doc = fitz.open(path)
            t = "\n".join(re.sub(r"[ \t]+", " ", p.get_text("text").replace("\r\n", "\n")) for p in doc)
            doc.close()
            return t
        except Exception:
            pass
        try:
            import subprocess
            out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=120)
            return out.stdout
        except Exception:
            return None
    if low.endswith((".txt", ".md", ".text")):
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if low.endswith((".json",)):
        try:
            blobs = []
            data = load_json(path)

            def walk(o):
                if isinstance(o, str) and len(o) > 200:
                    blobs.append(o)
                elif isinstance(o, dict):
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(data)
            return "\n".join(blobs)
        except Exception:
            with io.open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
    if low.endswith((".xml", ".nxml", ".html", ".htm")):
        with io.open(path, "r", encoding="utf-8", errors="replace") as f:
            return re.sub(r"<[^>]+>", "\n", f.read())
    return None


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    problems, warnings, checks = [], [], []

    rj = os.path.join(args.output, "result.json")
    if not os.path.exists(rj):
        print(json.dumps({"audit": "FAIL", "problems": ["result.json missing"]}, ensure_ascii=False))
        sys.exit(FAIL)
    result = load_json(rj)

    # 1. case_id + contract coverage
    case_path = os.path.join(args.input, "case.json")
    case = load_json(case_path) if os.path.exists(case_path) else {}
    if not result.get("case_id"):
        problems.append("result.case_id missing/empty")
    oc = case.get("output_contract") or case.get("outputContract") or case.get("contract") or []
    contract_keys = []
    if isinstance(oc, dict):
        for k, v in oc.items():
            if isinstance(v, list) and v and isinstance(v[0], str):
                contract_keys.extend(v)
            elif k not in ("type", "format", "$schema", "version"):
                contract_keys.append(k)
    elif isinstance(oc, list):
        for item in oc:
            contract_keys.append(item if isinstance(item, str) else (item or {}).get("name"))
    for k in filter(None, contract_keys):
        if k not in result:
            problems.append("output_contract key missing: %s" % k)
    checks.append("contract_key_coverage: %d keys" % len(contract_keys))

    # 2. status sanity
    if result.get("status") not in ("success", "partial", "cannot_determine", "rejected"):
        problems.append("status invalid: %r" % result.get("status"))

    # 3. re-slice every note quote from SOURCE
    mats = find_materials(args.input, case)
    src_texts = [t for t in (source_text_of(m) for m in mats) if t]
    if not src_texts and case:
        warnings.append("source material not readable; quote recheck limited to segments")
    seg_path = os.path.join(args.work, "segments.json")
    segs = load_json(seg_path) if os.path.exists(seg_path) else None
    seg_by_pid = {p["para_index"]: p for p in (segs or {}).get("paragraphs", [])}
    page_files = {}
    wdir = args.work
    if os.path.isdir(wdir):
        for fn in os.listdir(wdir):
            m = re.match(r"page_(\d+)\.txt", fn)
            if m:
                page_files[int(m.group(1))] = os.path.join(wdir, fn)

    notes = result.get("notes") or []
    quoted = 0
    for n in notes:
        q = n.get("quote")
        if not q:
            continue
        pid = n.get("para_index")
        para = seg_by_pid.get(pid)
        nq = norm(q)
        ok_page = False
        if para and nq and nq in norm(para.get("text", "")):
            ok_page = True
        else:
            pf = page_files.get(n.get("page"))
            if pf and os.path.exists(pf):
                with io.open(pf, "r", encoding="utf-8") as f:
                    if nq in norm(f.read()):
                        ok_page = True
        ok_src = any(nq and nq in norm(t) for t in src_texts) if nq else False
        if ok_page or ok_src:
            quoted += 1
            if not ok_src and src_texts:
                warnings.append("note %s: quote matches segment but not source text (extraction drift)" % n.get("note_id"))
        else:
            problems.append("note %s: quote NOT found in source (fabrication or drift)" % n.get("note_id"))
    checks.append("quote_recheck: %d/%d notes verbatim in source" % (quoted, len(notes)))

    # 4. card -> note wiring
    dangling = 0
    note_ids = {n.get("note_id") for n in notes}
    for c in result.get("cards") or []:
        for field in ("research_question", "data", "method_conditions", "main_findings",
                      "limitations", "assumptions"):
            v = c.get(field) or {}
            if isinstance(v, dict):
                for i in v.get("note_ids") or []:
                    if i not in note_ids:
                        dangling += 1
                        problems.append("card '%s' field '%s': dangling note_id %r" % (c.get("section"), field, i))
    checks.append("card_note_wiring: %d dangling" % dangling)

    # 5. fabrication heuristic: numbers in card text must exist in quoted evidence
    numeric_issues = 0
    for c in result.get("cards") or []:
        for field in ("research_question", "data", "method_conditions", "main_findings"):
            v = c.get(field) or {}
            if not isinstance(v, dict) or v.get("text") in (None, "not_reported"):
                continue
            nums = set(re.findall(r"\d+(?:\.\d+)?", str(v.get("text"))))
            evidence = " ".join(str((seg_by_pid.get(i) or {}).get("text", "")) for i in (v.get("note_ids") or []))
            ev_nums = set(re.findall(r"\d+(?:\.\d+)?", evidence))
            missing = nums - ev_nums
            if missing and v.get("note_ids"):
                numeric_issues += 1
                warnings.append("card '%s' %s: numbers %s not in quoted evidence" % (c.get("section"), field, sorted(missing)[:5]))
    checks.append("numeric_support: %d fields with unsourced numbers" % numeric_issues)

    verdict = "PASS" if not problems else "FAIL"
    print(json.dumps({"audit": verdict, "checks": checks, "problems": problems,
                      "warnings": warnings[:20],
                      "recommand": "fix problems, re-run run.py --stage finalize, audit again" if problems else "ready"},
                     ensure_ascii=False, indent=1))
    sys.exit(PASS if not problems else FAIL)


if __name__ == "__main__":
    main()
