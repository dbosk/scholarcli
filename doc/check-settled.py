#!/usr/bin/env python3
"""Check what a LaTeX build left; pass a two-state flip with a warning.

Usage: check-settled.py --status N --sources "F ..." JOB OUTDIR ENGINE ...

Called by `make check` (check.mk) after the build: N is the build rule's
exit status, ENGINE the engine command line for extra runs.  What it
accepts and why is described in the documentation, chapter on the
command-line interface, section "Keeping the woven document buildable"
(src/scholar/cli.nw, sec:woven-document).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MORE_RUNS = 3
SHOWN = 20
UNSETTLED = ("Label(s) may have changed", "Rerun to get")
PYTHONTEX_MISSING = re.compile(
    r"Package PythonTeX Warning: (Missing|Non-existent) [a-z ]*content"
    r"|Run PythonTeX to create it")
FLIP_WARNING = ("the references alternate between two states and cannot "
                "settle")
NEWLABEL = re.compile(r"^\\newlabel\{(.+?)\}\{\{(.*?)\}\{(.*?)\}")
NEWSUBLABEL = re.compile(r"^\\newsublabel\{(.+?)\}\{\{.*?\}\{(.*?)\}\}")


def fail(job, reason):
    sys.exit(f"check: {job} failed: {reason}")


def read_log(log):
    return log.read_text(encoding="latin-1") if log.exists() else ""


def log_failure(text):
    """Return why the log shows a failed build, or None."""
    errors = [line for line in text.splitlines() if line.startswith("! ")]
    if errors:
        return "LaTeX error: " + errors[0][2:]
    if "There were undefined" in text:
        return "undefined references or citations"
    if missing := PYTHONTEX_MISSING.search(text):
        return f"PythonTeX output is missing ({missing.group(0)})"
    return None


def unsettled(text):
    return any(marker in text for marker in UNSETTLED)


def feedback_files(job, outdir):
    """Return the files latexmk watches that the engine itself wrote."""
    fdb = outdir / f"{job}.fdb_latexmk"
    if not fdb.exists():
        return sorted(p for p in outdir.glob(f"{job}.*")
                      if p.suffix in (".aux", ".toc", ".out"))
    files, in_rule = [], False
    for line in fdb.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("["):
            in_rule = re.match(r'\["(pdf|xe|lua)?latex"\]', line) is not None
        elif line.startswith("  ("):
            in_rule = False  # "(generated)": outputs, not sources
        elif in_rule and line.startswith('  "'):
            path = Path(line.split('"')[1])
            if outdir.resolve() in path.resolve().parents:
                files.append(path)
    return sorted(set(files))


def snapshot(files, aux):
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path).encode())
        digest.update(path.read_bytes() if path.exists() else b"\0missing")
    return digest.hexdigest(), labels(aux)


def labels(aux):
    """Return {label: page shown} from the .aux, noweb's letters included."""
    found, on_page = {}, {}
    if not aux.exists():
        return found
    for line in aux.read_text(encoding="latin-1").splitlines():
        if m := NEWSUBLABEL.match(line):
            key, page = m.groups()
            on_page[page] = on_page.get(page, 0) + 1
            found[key] = page + chr(ord("a") + on_page[page] - 1)
        elif m := NEWLABEL.match(line):
            found[m.group(1)] = m.group(3)
    return found


def chunk_names(keys, sources):
    """Name noweb chunk labels by their chunk, from the woven sources."""
    names = {}
    pattern = re.compile(r"\\sublabel\{([^}]+)\}\\nwmargintag\{.*?\}\}\}"
                         r"\\moddef\{(.*?)~\{")
    for source in sources:
        if len(names) == len(keys):
            break
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for key, name in pattern.findall(text):
            if key in keys:
                names[key] = re.sub(r"\\(code|edoc)\{\}", "", name)
    return names


def differences(one, other, sources):
    keys = sorted(k for k in one.keys() | other.keys()
                  if one.get(k) != other.get(k))
    names = chunk_names(set(keys[:SHOWN]),
                        [s for s in sources if s.suffix == ".tex"])
    lines = []
    for key in keys[:SHOWN]:
        label = f"<<{names[key]}>> ({key})" if key in names else key
        lines.append(f"  {label}: page {one.get(key, 'none')} "
                     f"or {other.get(key, 'none')}")
    if len(keys) > SHOWN:
        lines.append(f"  ... and {len(keys) - SHOWN} more labels")
    if not keys:
        lines.append("  no label differs; the other files that feed back do")
    return lines


def settle(job, outdir, engine, sources):
    """Run the engine up to MORE_RUNS times; pass a two-state flip."""
    log, aux, flip = (outdir / f"{job}.{ext}" for ext in ("log", "aux", "flip"))
    files = feedback_files(job, outdir)
    states = [snapshot(files, aux)]
    if flip.exists():
        known = json.loads(flip.read_text())
        if states[0][0] in known["states"]:
            print(known["warning"], file=sys.stderr)
            return
    for run in range(1, MORE_RUNS + 1):
        print(f"check: the build did not settle; run {run} of {MORE_RUNS} "
              f"more: {' '.join(engine)}", file=sys.stderr)
        # No terminal: at an error the engine reads end of file and stops,
        # instead of waiting unseen at its prompt.  Its log is the evidence.
        subprocess.run(engine, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, check=False)
        text = read_log(log)
        if reason := log_failure(text):
            fail(job, reason)
        if not unsettled(text):
            print(f"check: settled after {run} more run(s)", file=sys.stderr)
            flip.unlink(missing_ok=True)
            return
        states.append(snapshot(files, aux))
        if run >= 2 and states[run][0] == states[run - 2][0] \
                and states[run][0] != states[run - 1][0]:
            warning = "\n".join(
                [f"check: warning: {FLIP_WARNING}: {job} flips between two "
                 "layouts on every run; these differ between them:"]
                + differences(states[run - 1][1], states[run][1], sources)
                + ["check: passed with that warning (the PDF is the last "
                   "run's)"])
            flip.write_text(json.dumps({"states": [states[run - 1][0],
                                                   states[run][0]],
                                        "warning": warning}))
            print(warning, file=sys.stderr)
            return
    fail(job, f"it did not settle after {MORE_RUNS} more runs, and it is "
         "not a two-state flip")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=int, required=True)
    parser.add_argument("--sources", default="")
    parser.add_argument("job")
    parser.add_argument("outdir", type=Path)
    parser.add_argument("engine", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    job, outdir = args.job, args.outdir
    sources = [Path(s) for s in args.sources.split()]
    log, pdf = outdir / f"{job}.log", outdir / f"{job}.pdf"
    if not log.exists():
        fail(job, f"{log} is missing; the build did not run")
    for source in sources:
        if source.exists() and log.stat().st_mtime < source.stat().st_mtime:
            fail(job, f"{log} is older than {source}; the build did not run")
    text = read_log(log)
    if reason := log_failure(text):
        fail(job, reason)
    if unsettled(text):
        settle(job, outdir, args.engine, sources)
    elif args.status != 0:
        fail(job, f"the build rule ended with status {args.status} "
             "(see its output above), and the log does not show why")
    if not pdf.exists():
        fail(job, f"{pdf} is missing")


if __name__ == "__main__":
    main(sys.argv[1:])
