#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latex-resilient-compile: prepare (analysis) / compile / finalize.

Degrade-not-die: every path writes contract-shaped result.json.
TeX index discipline: word tuples are irrelevant here; we handle TeX source lines.
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import traceback

WORK = "/app/work"
OUT = "/app/output"
TEX_ENVS_ALLOWING_AMP = re.compile(
    r"\\begin\{(tabular\*?|longtable|align\*?|aligned|cases|array|split|equarray)\}")
CMD = {"pdflatex": "pdflatex", "xelatex": "xelatex", "latexmk": "latexmk",
       "tectonic": "tectonic"}


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


def tex_files(case, input_dir):
    cands = []
    listed = _pick(case, ["materials", "files", "tex", "sources", "inputs"])
    if isinstance(listed, list):
        for x in listed:
            cands.append(x.get("path") if isinstance(x, dict) else x)
    elif isinstance(listed, str):
        cands.append(listed)
    seen = set()
    for c in cands:
        if isinstance(c, str) and c:
            p = c if os.path.isabs(c) else os.path.join(input_dir, c)
            if os.path.exists(p) and p not in seen:
                seen.add(p)
    if os.path.isdir(input_dir):
        for fn in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, fn)
            if fn.lower().endswith((".tex", ".cls", ".sty", ".bib")) and p not in seen:
                seen.add(p)
    return sorted(seen)


def copy_sources(files, src_dir):
    os.makedirs(src_dir, exist_ok=True)
    copied, errors = [], []
    for p in files:
        dst = os.path.join(src_dir, os.path.basename(p))
        try:
            with io.open(p, "r", encoding="utf-8", errors="strict") as f:
                text = f.read()
            with io.open(dst, "w", encoding="utf-8") as f:
                f.write(text)
            copied.append({"name": os.path.basename(p), "path": p, "lines": text.count("\n") + 1,
                           "error": None})
        except Exception as e:
            try:
                shutil.copy(p, dst)
                copied.append({"name": os.path.basename(p), "path": p, "lines": None,
                               "error": "utf8_decode_failed_copied_raw"})
            except Exception as e2:
                errors.append({"path": p, "error": str(e2)})
    return copied, errors


def line_of_pos(text, pos):
    return text.count("\n", 0, pos) + 1


def analyze(src_dir):
    """Deterministic analysis; never needs TeX. Returns analysis dict."""
    files = sorted(glob.glob(os.path.join(src_dir, "*.tex"))) + \
        sorted(glob.glob(os.path.join(src_dir, "*.cls"))) + \
        sorted(glob.glob(os.path.join(src_dir, "*.sty")))
    analysis = {"files": [], "main_file": None, "template_fields": {}, "unescaped_ampersands": [],
                "env_imbalance": [], "packages_used": [], "packages_missing": [],
                "input_map": {}, "backend": {}}
    packages = set()
    env_stack = []
    for p in files:
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            analysis["files"].append({"name": os.path.basename(p), "error": str(e)})
            continue
        name = os.path.basename(p)
        entry = {"name": name, "lines": text.count("\n") + 1, "error": None}
        if "\\documentclass" in text and analysis["main_file"] is None:
            analysis["main_file"] = name
        # template fields
        for fld, pat in (("title", r"\\title\{([^}]*)\}"), ("author", r"\\author\{([^}]*)\}"),
                         ("date", r"\\date\{([^}]*)\}")):
            m = re.search(pat, text)
            if m:
                analysis["template_fields"][fld] = {"present": True, "empty": not m.group(1).strip()}
        if re.search(r"\\begin\{abstract\}", text):
            analysis["template_fields"]["abstract"] = {"present": True}
        # packages
        for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]*)\}", text):
            for pkg in m.group(1).split(","):
                packages.add(pkg.strip())
        # unescaped & counting: exclude verbatim and math alignment environments
        in_verb = False
        cur_env = None
        for ln_no, line in enumerate(text.split("\n"), start=1):
            if "\\begin{verbatim}" in line:
                in_verb = True
            if "\\end{verbatim}" in line:
                in_verb = False
                continue
            if in_verb:
                continue
            mb = re.search(r"\\begin\{(tabular\*?|longtable|align\*?|aligned|cases|array|split)\}", line)
            if mb:
                cur_env = mb.group(1)
            me = re.search(r"\\end\{(tabular\*?|longtable|align\*?|aligned|cases|array|split)\}", line)
            # strip \& escapes and comments
            probe = re.sub(r"\\&", "", line)
            probe = probe.split("%")[0]
            n_amp = probe.count("&")
            in_allowed = cur_env is not None
            if n_amp and not in_allowed and "\\&" not in line:
                # suspicious & outside any alignment env
                analysis["unescaped_ampersands"].append(
                    {"file": name, "line": ln_no, "count": n_amp,
                     "context": line.strip()[:80]})
            if me:
                cur_env = None
            # env balance
            for m2 in re.finditer(r"\\(begin|end)\{(\w+\*?)\}", line):
                if m2.group(1) == "begin":
                    env_stack.append((name, m2.group(2), ln_no))
                else:
                    if env_stack and env_stack[-1][1] == m2.group(2):
                        env_stack.pop()
                    else:
                        analysis["env_imbalance"].append(
                            {"file": name, "line": ln_no,
                             "issue": "\\end{%s} without matching begin" % m2.group(2)})
        for (fn, env, ln) in env_stack:
            if fn == name:
                analysis["env_imbalance"].append(
                    {"file": fn, "line": ln, "issue": "\\begin{%s} unclosed" % env})
        env_stack = []
        # input map
        for m in re.finditer(r"\\(?:input|include)\{([^}]*)\}", text):
            analysis["input_map"].setdefault(name, []).append(m.group(1))
        analysis["files"].append(entry)
    # missing packages by command usage
    all_text = ""
    for p in files:
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                all_text += f.read()
        except Exception:
            pass
    need = {"toprule": "booktabs", "midrule": "booktabs", "bottomrule": "booktabs",
            "includegraphics": "graphicx", "SI": "siunitx", "numprint": "siunitx",
            "pgfplots": None, "tikzpicture": "tikz", "algorithm": "algorithm",
            "algorithmic": "algorithmic", "hyperref": None, "lstlisting": "listings",
            "gls": "glossaries", "mathpar": None, "bm": "bm"}
    for cmd_name, pkg in need.items():
        if pkg is None:
            pkg = cmd_name if cmd_name in ("pgfplots", "hyperref") else None
        if pkg is None:
            continue
        if re.search(r"\\%s\b" % re.escape(cmd_name), all_text) and pkg not in packages:
            analysis["packages_missing"].append({"command": cmd_name, "package": pkg})
    for name, pkg in (("pgfplots", "pgfplots"), ("hyperref", "hyperref")):
        if name in all_text and pkg not in packages:
            analysis["packages_missing"].append({"command": name, "package": pkg})
    analysis["packages_used"] = sorted(packages)
    for tool in ("latexmk", "pdflatex", "xelatex", "tectonic"):
        analysis["backend"][tool] = shutil.which(tool) is not None
    return analysis


def triage_log(log_text):
    """Compile log -> triaged diagnosis with file/line/class/fix."""
    diag = []
    file_cursor = "main.tex"
    for line in log_text.split("\n"):
        fm = re.search(r'(?:\./)?([\w\-./]+\.tex)[:(]', line)
        if fm:
            file_cursor = os.path.basename(fm.group(1))
        lm = re.search(r"^l\.(\d+)", line)
        if "Undefined control sequence" in line:
            diag.append({"file": file_cursor, "line": (int(lm.group(1)) if lm else None),
                         "error_class": "package_or_command",
                         "message": line.strip()[:120],
                         "suggested_fix": "add missing \\usepackage or fix the command name"})
        elif "Missing $ inserted" in line:
            diag.append({"file": file_cursor, "line": (int(lm.group(1)) if lm else None),
                         "error_class": "math_mode",
                         "message": line.strip()[:120],
                         "suggested_fix": "close math mode; escape _ ^ outside math"})
        elif "Misplaced alignment tab character &" in line:
            diag.append({"file": file_cursor, "line": (int(lm.group(1)) if lm else None),
                         "error_class": "escape",
                         "message": line.strip()[:120],
                         "suggested_fix": "replace bare & with \\& outside tabular/align"})
        elif "File .* not found" in line or re.search(r"! LaTeX Error: File `([^']+)' not found", line):
            m = re.search(r"File `([^']+)' not found", line)
            diag.append({"file": file_cursor, "line": None, "error_class": "file_not_found",
                         "message": (m.group(1) if m else line.strip())[:120],
                         "suggested_fix": "fix path/case or remove the dependency"})
        elif "! LaTeX Error:" in line or "! Package .* Error:" in line:
            diag.append({"file": file_cursor, "line": (int(lm.group(1)) if lm else None),
                         "error_class": "latex_error",
                         "message": line.strip()[:120],
                         "suggested_fix": "read the message; fix the named construct"})
    # dedupe
    seen, out = set(), []
    for d in diag:
        k = (d["file"], d["line"], d["error_class"], d["message"][:60])
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out[:40]


def compile_pdf(src_dir, out_dir):
    """Multi-backend compile. Returns dict(status, pdf, pages, log, passes)."""
    passes = []
    main = None
    for p in sorted(glob.glob(os.path.join(src_dir, "*.tex"))):
        with io.open(p, "r", encoding="utf-8", errors="replace") as f:
            if "\\documentclass" in f.read():
                main = p
                break
    if main is None:
        return {"status": "no_main", "pdf": None, "pages": None, "log": "", "passes": passes}
    base = os.path.splitext(os.path.basename(main))[0]
    attempts = [["latexmk", "-pdf", "-interaction=nonstopmode", "-f", base],
                ["pdflatex", "-interaction=nonstopmode", base],
                ["xelatex", "-interaction=nonstopmode", base],
                ["tectonic", base]]
    for cmd in attempts:
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, cwd=src_dir, capture_output=True, text=True, timeout=180)
            passes.append({"cmd": " ".join(cmd), "exit": r.returncode})
            pdf = os.path.join(src_dir, base + ".pdf")
            if r.returncode == 0 and os.path.exists(pdf):
                pages = None
                try:
                    import fitz
                    doc = fitz.open(pdf)
                    pages = doc.page_count
                    doc.close()
                except Exception:
                    m = re.search(r"Output written on .*?\((\d+) page", r.stdout or "")
                    pages = int(m.group(1)) if m else None
                dst = os.path.join(out_dir, base + ".pdf")
                shutil.copy(pdf, dst)
                return {"status": "success", "pdf": os.path.basename(dst), "pages": pages,
                        "log": (r.stdout or "")[-8000:], "passes": passes}
            log = ""
            logf = os.path.join(src_dir, base + ".log")
            if os.path.exists(logf):
                with io.open(logf, "r", encoding="utf-8", errors="replace") as f:
                    log = f.read()
            # retry pdflatex twice for refs if it made progress
            if cmd[0] == "pdflatex" and len([p2 for p2 in passes if p2["cmd"].startswith("pdflatex")]) < 3 \
                    and os.path.exists(pdf):
                continue
            if r.returncode != 0:
                return {"status": "failed", "pdf": None, "pages": None, "log": log[-8000:] or (r.stdout or "")[-8000:],
                        "passes": passes}
        except subprocess.TimeoutExpired:
            passes.append({"cmd": " ".join(cmd), "exit": "timeout"})
        except Exception as e:
            passes.append({"cmd": " ".join(cmd), "exit": "error: %s" % e})
    return {"status": "no_backend_or_failed", "pdf": None, "pages": None,
            "log": "", "passes": passes}


def read_json(p):
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def write_result(out_dir, case, payload):
    keys = contract_keys(case)
    result = {"case_id": _pick(case, ["case_id", "id", "caseId"]), **payload}
    for k in keys:
        if k not in result:
            result[k] = None
    with io.open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def stage_prepare(args):
    os.makedirs(WORK, exist_ok=True)
    case, err = load_case(args.input)
    files = tex_files(case, args.input)
    if not files:
        write_result(args.output, case, {
            "status": "cannot_determine", "status_reasons": ["missing_tex_sources"],
            "analysis": None, "compile": None, "diagnosis": [], "compile_log": [],
            "handoff": "no .tex/.cls/.sty in case", "case_error": err,
            "changes_log": [{"change": "prepare", "detail": "no sources found"}]})
        print(json.dumps({"stage": "prepare", "status": "cannot_determine"}))
        return
    copied, errors = copy_sources(files, os.path.join(WORK, "src"))
    analysis = analyze(os.path.join(WORK, "src"))
    analysis["copy_errors"] = errors
    with io.open(os.path.join(WORK, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=1)
    print(json.dumps({"stage": "prepare", "files": len(copied), "errors": len(errors),
                      "main_file": analysis["main_file"],
                      "unescaped_amp": len(analysis["unescaped_ampersands"]),
                      "env_imbalance": len(analysis["env_imbalance"]),
                      "packages_missing": len(analysis["packages_missing"]),
                      "backend": analysis["backend"]}))


def stage_compile(args):
    os.makedirs(OUT, exist_ok=True)
    case, _ = load_case(args.input)
    analysis = read_json(os.path.join(WORK, "analysis.json"))
    if not analysis:
        print(json.dumps({"stage": "compile", "error": "analysis_missing; run prepare first"}))
        return
    if not any(analysis["backend"].values()):
        result = write_result(args.output, case, {
            "status": "partial", "status_reasons": ["no_tex_backend"],
            "analysis": analysis, "compile": None, "diagnosis": [],
            "compile_log": [], "pdf_file": None, "pdf_pages": None,
            "handoff": "install texlive or run on a host with TeX",
            "changes_log": [{"change": "compile", "detail": "no TeX binary available"}]})
        print(json.dumps({"stage": "compile", "status": "partial", "reason": "no_tex_backend"}))
        return
    comp = compile_pdf(os.path.join(WORK, "src"), args.output)
    diagnosis = triage_log(comp.get("log") or "") if comp["status"] != "success" else []
    status = "success" if comp["status"] == "success" else "partial"
    result = write_result(args.output, case, {
        "status": status,
        "status_reasons": ([] if status == "success" else ["compile_failed" if comp["status"] == "failed" else comp["status"]]),
        "analysis": analysis,
        "compile": {"status": comp["status"], "passes": comp["passes"],
                    "pdf": comp["pdf"], "pages": comp["pages"]},
        "compile_log": comp["passes"],
        "diagnosis": diagnosis,
        "pdf_file": comp["pdf"], "pdf_pages": comp["pages"],
        "unescaped_ampersands": analysis["unescaped_ampersands"],
        "handoff": (None if status == "success" else
                    "fix diagnosis[] items; each names file+line+class+fix"),
        "changes_log": [{"change": "compile", "detail": "multi-backend attempt",
                         "passes": len(comp["passes"]), "status": comp["status"]}]})
    print(json.dumps({"stage": "compile", "status": status, "pdf": comp["pdf"],
                      "pages": comp["pages"], "diagnosis": len(diagnosis)}))


def main():
    global WORK, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["prepare", "compile"], required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--output", default=OUT)
    ap.add_argument("--work", default=WORK)
    args = ap.parse_args()
    WORK, OUT = args.work, args.output
    try:
        (stage_prepare if args.stage == "prepare" else stage_compile)(args)
    except Exception:
        os.makedirs(args.output, exist_ok=True)
        err = traceback.format_exc(limit=4)
        try:
            case, _ = load_case(args.input)
        except Exception:
            case = {}
        write_result(args.output, case, {
            "status": "partial", "status_reasons": ["engine_exception"],
            "error": err[-1200:], "analysis": None, "compile": None,
            "diagnosis": [], "compile_log": [], "pdf_file": None, "pdf_pages": None,
            "handoff": "inspect error; stages restartable"})
        print(json.dumps({"stage": args.stage, "status": "partial", "engine_exception": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
