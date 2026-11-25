#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation-align-manager: align citations, dedup, renumber, finalize.

Stages
  align    : parse text + reference list -> work/citation_map.json
  finalize : apply verdicts -> updated text + list + /app/output/result.json

stdlib only; metadata verbatim; conservative merging; never reject.
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

PARTICLES = {"van", "von", "de", "der", "den", "del", "della", "di", "da", "la", "le",
             "du", "dos", "das", "ter", "ten", "bin", "ibn", "al", "el", "op", "'t"}
NUM_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;–\-]\s*\d+)*(?:\s*,?\s*(?:et al\.?|e\.g\.,)[^\]]*)?)\]")
AY_CITE_RE = re.compile(r"\(([A-Z][A-Za-z'’\-]+(?:\s+(?:et al\.?|and|&)\s+[A-Z][A-Za-z'’\-]+){0,2}),?\s*((?:19|20)\d{2}[a-z]?)\)")
REF_LABEL_RE = re.compile(r"^\s*(?:\[(\d+)\]|(\d+)[.\)]\s*|(\d+)\s+)\s*")


# ---------------------------------------------------------------- author utils

def split_surname(name):
    """'J. van der Berg' -> ('van der Berg', 'J.'); keeps particles in the surname."""
    name = name.strip().rstrip(",")
    parts = name.split()
    if not parts:
        return "", ""
    # find where the given-name part (initials or single capitalized word w/o particle) ends
    # heuristic: leading initials (X. or X.X.) or first non-particle token is given name
    i = 0
    if re.match(r"^[A-Z]\.?$", parts[0]) or re.match(r"^[A-Z]\.[A-Z]\.?\.?$", parts[0]):
        while i < len(parts) and re.match(r"^[A-Z]\.?[A-Z]?\.?\.?$", parts[i]) and parts[i].lower() not in PARTICLES:
            i += 1
        surname = " ".join(parts[i:]) or parts[-1]
        given = " ".join(parts[:i])
        return surname, given
    # no initials: last token(s) = surname, but trailing particles belong to surname
    j = len(parts) - 1
    while j - 1 > 0 and parts[j - 1].lower() in PARTICLES:
        j -= 1
    surname = " ".join(parts[j:])
    given = " ".join(parts[:j])
    return surname, given


def norm_key(s):
    s = re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return s


def authors_key(authors_str):
    """First author surname (particle-safe) as the merge key part."""
    if not authors_str:
        return ""
    first = re.split(r"[,;]|\s+and\s+", authors_str)[0]
    surname, _ = split_surname(first)
    return norm_key(surname)


# ---------------------------------------------------------------- reference parsing

def split_reference_block(text):
    """Cut the trailing reference list off a manuscript, if present."""
    m = list(re.finditer(r"(?im)^\s*(?:references|bibliography|文献|参考文献)\s*$", text))
    if m:
        cut = m[-1].end()
        return text[:cut].rstrip(), text[cut:].strip()
    # numbered entries at the tail
    tail = text[-4000:]
    labels = re.findall(r"(?m)^\s*(\d+)[.\)]\s", tail)
    if len(set(labels)) >= 4:
        # find where numbered entries begin
        m2 = re.search(r"(?m)^\s*1[.\)]\s", text)
        if m2 and m2.start() > len(text) * 0.5:
            return text[:m2.start()].rstrip(), text[m2.start():].strip()
    return text, None


def parse_references(block):
    """Reference list -> list of entries with verbatim + fields."""
    if not block:
        return []
    # split entries: [n] style or n. style at line starts
    entries = []
    matches = list(re.finditer(r"(?m)^\s*(?:\[(\d+)\]|(\d+)[.\)])\s*(.*)$", block))
    if len(matches) >= 3:
        for idx, m in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
            body = block[m.start():end]
            body = re.sub(r"(?m)^\s*(?:\[\d+\]|\d+[.\)])\s*", "", body).strip()
            label = m.group(1) or m.group(2)
            entries.append(parse_entry_body(body, int(label)))
    else:
        # blank-line separated entries
        for chunk in re.split(r"\n\s*\n", block):
            c = chunk.strip()
            if c and len(c) > 25:
                entries.append(parse_entry_body(c, None))
    return entries


def parse_entry_body(body, label):
    e = {"label": label, "verbatim": body, "authors": "", "year": "", "title": "",
         "venue": "", "volume": "", "pages": "", "doi": ""}
    doi = re.search(r"(?i)\b(10\.\d{4,9}/[^\s\"<>]+)", body)
    if doi:
        e["doi"] = doi.group(1).rstrip(".")
    y = re.search(r"\b((?:19|20)\d{2})[a-z]?\b", body)
    if y:
        e["year"] = y.group(1)
    # authors: text before the year (crude but deterministic)
    if y and y.start() > 3:
        head = body[:y.start()].strip().rstrip(",.")
    else:
        head = ""
    e["authors"] = head
    # title: segment after year up to next period or venue marker
    rest = body[y.end():] if y else body
    tm = re.search(r"[.\s]\s*([^\.\n]{15,}?)[.\s]\s*(?=[A-Z][a-z]+\s*[Jj]ournal|IEEE|ACM|Nature|Science|Proc\b|Adv\b|Appl\b|J\b| Comput| Phys| Chem| Biol)", rest)
    if tm:
        e["title"] = tm.group(1).strip()
    else:
        t2 = re.search(r"[.\s]\s*([^\.\n]{15,180})\.", rest)
        if t2:
            e["title"] = t2.group(1).strip()
    vm = re.search(r"(?i)\b(Nature\w*|Science\b|IEEE Trans[^\.,]*|ACM[^\.,]*|Proc\.\s*[A-Za-z]+\s*[A-Za-z]+|Journal of[^\.,]*|[A-Z][a-z]+\s+[A-Z][a-z]*\s*[Jj]ournal\b)", body)
    if vm:
        e["venue"] = vm.group(1).strip()
    pm = re.search(r"\b(\d+(?:[–-]\d+)?|\d+\s*[–-]\s*\d+)\s*$", body.strip())
    if pm:
        e["pages"] = pm.group(1)
    vm2 = re.search(r"\b(\d+)\s*[(:]\s*\d+", body)
    if vm2:
        e["volume"] = vm2.group(1)
    e["author_key"] = authors_key(head)
    e["title_key"] = norm_key(e["title"])
    return e


# ---------------------------------------------------------------- in-text citations

def find_inline_citations(text, entries):
    """All in-text citation markers with positions and resolution."""
    cites = []
    for m in NUM_CITE_RE.finditer(text):
        raw = m.group(1)
        nums = [int(n) for n in re.findall(r"\d+", raw)]
        for n in nums:
            cites.append({"pos": m.start(), "raw": m.group(0), "style": "numeric",
                          "number": n,
                          "resolved": any(e.get("label") == n for e in entries)})
    if entries and all(e.get("label") is None for e in entries) or not any(e.get("label") for e in entries):
        for m in AY_CITE_RE.finditer(text):
            surname, _ = split_surname(m.group(1))
            cites.append({"pos": m.start(), "raw": m.group(0), "style": "author-year",
                          "author_key": norm_key(surname), "year": m.group(2), "resolved": False})
        # resolve against entries
        for c in cites:
            if c["style"] == "author-year":
                for e in entries:
                    if e["author_key"] and c["author_key"] == e["author_key"] and e.get("year") == c["year"]:
                        c["resolved"] = True
                        c["entry_index"] = entries.index(e)
                        break
    for c in cites:
        if c["style"] == "numeric" and c.get("resolved"):
            for e in entries:
                if e.get("label") == c["number"]:
                    c["entry_index"] = entries.index(e)
                    break
    return cites


# ---------------------------------------------------------------- duplicates

def duplicate_groups(entries):
    groups, used = [], set()
    for i, a in enumerate(entries):
        if i in used:
            continue
        grp = [i]
        for j in range(i + 1, len(entries)):
            if j in used:
                continue
            b = entries[j]
            same_doi = a.get("doi") and a.get("doi") == b.get("doi")
            same_title = a.get("title_key") and a.get("title_key") == b.get("title_key")
            same_ay = a.get("author_key") and a.get("author_key") == b.get("author_key") and a.get("year") == b.get("year")
            if (same_doi and same_ay) or (same_title and same_ay):
                grp.append(j)
                used.add(j)
            elif (same_title or same_doi) and not same_ay:
                groups.append({"type": "merge_candidate", "indices": [i, j],
                               "reason": "title/doi match but author-year mismatch: needs adjudication"})
        if len(grp) > 1:
            groups.append({"type": "duplicate", "indices": grp,
                           "reason": "same work per DOI+author-year or title+author-year rule"})
        used.add(i)
    return [g for g in groups if g["type"] == "duplicate" or len(g["indices"]) > 1]


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
            v = d[n]
            return v
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


def get_texts(case):
    text = _pick(case, ["text", "draft", "manuscript", "source_text", "content", "body"])
    if isinstance(text, dict):
        text = _pick(text, ["text", "content", "body"])
    refs = _pick(case, ["references", "bibliography", "refs", "citation_list", "reference_list"])
    if isinstance(refs, list):
        refs = "\n\n".join(str(r) for r in refs)
    if isinstance(refs, dict):
        refs = _pick(refs, ["text", "entries", "list"]) or ""
    if isinstance(text, str) and isinstance(refs, str):
        refs = refs.strip() or None
    return (text if isinstance(text, str) else None), (refs if isinstance(refs, str) else None)


# ---------------------------------------------------------------- stages

def stage_align(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    text, refs_field = get_texts(case)
    problems = []
    if text is None:
        problems.append("missing_manuscript_text")
    body, ref_block = (text or ""), refs_field
    if ref_block is None and text:
        body, ref_block = split_reference_block(text)
        if ref_block is None:
            problems.append("missing_reference_list")
    entries = parse_references(ref_block) if ref_block else []
    cites = find_inline_citations(body, entries) if body else []
    # first-occurrence order
    order, seen = [], set()
    for c in cites:
        idx = c.get("entry_index")
        if idx is not None and idx not in seen:
            seen.add(idx)
            order.append(idx)
    dup = duplicate_groups(entries)
    unresolved = [c for c in cites if not c.get("resolved")]
    mapping = {"citation_map": {
        "entries": entries, "in_text": cites, "first_occurrence_order": order,
        "duplicates": dup, "unresolved": unresolved,
        "body_text": body, "problems": problems, "case_error": err,
    }}
    with io.open(os.path.join(WORK, "citation_map.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "align", "entries": len(entries), "citations": len(cites),
                      "unresolved": len(unresolved), "duplicate_groups": len(dup),
                      "problems": problems}, ensure_ascii=False))


def renumber_text(body, cites, renum):
    """Rewrite numeric citations per renum {old_entry_index: new_number}."""
    def repl(m):
        raw = m.group(1)
        nums = re.findall(r"\d+", raw)
        new = []
        for n in nums:
            old = int(n)
            tgt = None
            for c in cites:
                if c["style"] == "numeric" and c.get("number") == old and c.get("resolved"):
                    tgt = renum.get(c.get("entry_index"))
                    break
            if tgt is None:
                tgt = old
            if str(tgt) not in new:
                new.append(str(tgt))
        return "[" + ", ".join(new) + "]"
    return NUM_CITE_RE.sub(repl, body)


def stage_finalize(args):
    os.makedirs(OUT, exist_ok=True)
    case, err = load_case(args.input)
    keys = contract_keys(case)
    case_id = _pick(case, ["case_id", "id", "caseId"])
    mp = os.path.join(WORK, "citation_map.json")
    cmap = None
    if os.path.exists(mp):
        with io.open(mp, "r", encoding="utf-8") as f:
            cmap = json.load(f).get("citation_map")
    notes = None
    if args.notes and os.path.exists(args.notes):
        with io.open(args.notes, "r", encoding="utf-8") as f:
            notes = json.load(f)
    verdicts = {(v.get("group")): v for v in (notes or {}).get("merge_verdicts") or []}
    checks = []
    status = "success"
    if cmap is None:
        status = "cannot_determine" if (not os.path.exists(mp)) else "partial"
        result = {"case_id": case_id, "status": status,
                  "status_reasons": ["citation_map_missing"], "updated_text": None,
                  "updated_references": []}
        for k in keys:
            result.setdefault(k, None)
        with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": "finalize", "status": status}))
        return
    entries = cmap["entries"]
    cites = cmap["in_text"]
    body = cmap.get("body_text") or ""
    # apply merge verdicts
    drop = set()
    merge_log = []
    for gi, g in enumerate(cmap.get("duplicates") or []):
        v = verdicts.get(gi)
        if g["type"] == "duplicate" and (v is None or v.get("action") == "merge"):
            keep = (v or {}).get("keep") or ("entry_%d" % g["indices"][0])
            keep_idx = int(re.search(r"\d+", str(keep)).group()) if re.search(r"\d+", str(keep)) else g["indices"][0]
            for i in g["indices"]:
                if i != keep_idx:
                    drop.add(i)
            merge_log.append({"group": gi, "action": "merge", "kept": keep_idx,
                              "dropped": [i for i in g["indices"] if i != keep_idx],
                              "reason": (v or {}).get("reason") or g.get("reason", "rule-based")})
        elif v and v.get("action") == "keep_separate":
            merge_log.append({"group": gi, "action": "keep_separate",
                              "reason": v.get("reason", "adjudicated")})
        elif g["type"] == "merge_candidate":
            merge_log.append({"group": gi, "action": "kept_separate_conservative",
                              "reason": v.get("reason") if v else "no verdict; conservative default"})
    # entry renumbering: first-occurrence, skipping dropped
    order = [i for i in cmap.get("first_occurrence_order") or [] if i not in drop]
    renum = {old: new for new, old in enumerate(order, start=1)}
    # entries never cited: keep after cited ones, in original order
    uncited = [i for i in range(len(entries)) if i not in renum and i not in drop]
    for new, old in enumerate(uncited, start=len(order) + 1):
        renum[old] = new
    new_body = renumber_text(body, cites, renum) if body else None
    # build new reference list: verbatim bodies with new labels
    new_refs = []
    for old in sorted(renum, key=lambda o: renum[o]):
        e = entries[old]
        new_refs.append({"number": renum[old], "verbatim": e["verbatim"],
                         "fields": {k: e.get(k, "") for k in ("authors", "title", "venue", "year", "volume", "pages", "doi")}})
    unresolved = [{"raw": c["raw"], "pos": c["pos"]} for c in (cmap.get("unresolved") or [])]
    # metadata verbatim check: every field value must appear in some original verbatim body
    orig_bodies = "\n".join(e["verbatim"] for e in entries)
    meta_bad = []
    for r in new_refs:
        for k, v in r["fields"].items():
            if v and str(v) not in orig_bodies:
                meta_bad.append({"number": r["number"], "field": k})
    if meta_bad:
        status = "partial"
        checks.append("metadata_not_verbatim:%d" % len(meta_bad))
    if cmap.get("problems"):
        if "missing_manuscript_text" in cmap["problems"]:
            status = "cannot_determine"
        else:
            status = "partial"
        checks.extend(cmap["problems"])
    if unresolved and status == "success":
        status = "partial"
        checks.append("unresolved_citations:%d" % len(unresolved))
    # claim-citation checks from notes
    cc = (notes or {}).get("claim_citation_checks") or []
    result = {
        "case_id": case_id,
        "status": status,
        "status_reasons": checks,
        "updated_text": new_body,
        "updated_references": new_refs,
        "renumber_map": {str(k): v for k, v in renum.items()},
        "merge_log": merge_log,
        "unresolved_citations": unresolved,
        "claim_citation_checks": cc,
        "metadata_verbatim_check": {"violations": meta_bad},
        "uncited_entries_kept": [{"number": renum[i], "verbatim": entries[i]["verbatim"]} for i in uncited],
        "changes_log": [
            {"change": "align", "detail": "run.py stage align", "result": "citation_map.json"},
            {"change": "merge", "detail": "verdicts applied", "count": len(merge_log)},
            {"change": "renumber", "detail": "first-occurrence order", "entries": len(new_refs)},
        ],
        "case_error": err,
    }
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(OUT, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "finalize", "status": status, "refs": len(new_refs),
                      "merges": len(merge_log), "unresolved": len(unresolved),
                      "meta_violations": len(meta_bad), "contract_keys_filled": keys},
                     ensure_ascii=False))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["align", "finalize"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    ap.add_argument("--notes", default=None)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    if args.notes is None:
        args.notes = os.path.join(WORK, "notes.json")
    try:
        (stage_align if args.stage == "align" else stage_finalize)(args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), "status": "partial",
                  "status_reasons": ["engine_exception"], "error": err[-1200:],
                  "updated_text": None, "updated_references": [],
                  "handoff": "inspect error; stages restartable"}
        for k in contract_keys(case):
            result.setdefault(k, None)
        with io.open(os.path.join(args.output, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
