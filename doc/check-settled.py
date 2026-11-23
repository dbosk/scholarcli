#!/usr/bin/env python3
"""Check a LaTeX build's log, and tell a two-state flip from a failure.

Usage: check-settled.py JOB OUTDIR ENGINE [ARG ...]

Called by `make check` (check.mk) after latexmk has run.  The log of the
last run decides:

- an error (a line starting with "! ") or an undefined reference fails;
- a log without "Label(s) may have changed" or "Rerun to get" passes;
- otherwise the files that feed back into the next run did not become
  stable within latexmk's run limit.  We then run ENGINE (the engine
  command line latexmk uses) up to three more times, keeping a digest of
  those files after each run.  When the state after run k equals the
  state after run k-2 and differs from run k-1, the document alternates
  between two layouts and cannot settle: we print one named warning that
  lists the labels whose page or sub-page letter differs and pass.
  Anything else fails.

The files that feed back are the ones latexmk itself watches: the
sources of the engine's rule in JOB.fdb_latexmk that lie in OUTDIR (for
the scholar document: the .aux, .toc, .out, .run.xml, .unq, PythonTeX's
.pytxmcr/.pytxpyg and minted's cached highlights).  A flip found once is
remembered in JOB.flip (both states' digests), so running the check
again on the same build repeats the warning without new runs.

latexmk has no option for this: it offers $max_repeat (how many runs
before it gives up) and $failure_cmd (a command run after any failed
compilation, whatever the cause), but nothing that compares the states
of earlier runs.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MORE_RUNS = 3
SHOWN = 20
UNDEFINED = "There were undefined"
UNSETTLED = ("Label(s) may have changed", "Rerun to get")
FLIP_WARNING = ("the references alternate between two states and cannot "
                "settle")
NEWLABEL = re.compile(r"^\\newlabel\{(.+?)\}\{\{(.*?)\}\{(.*?)\}")
NEWSUBLABEL = re.compile(r"^\\newsublabel\{(.+?)\}\{\{.*?\}\{(.*?)\}\}")


def read_log(log):
    return log.read_text(encoding="latin-1") if log.exists() else ""


def log_failure(text):
    """Return why the log shows a failed build, or None."""
    errors = [line for line in text.splitlines() if line.startswith("! ")]
    if errors:
        return "LaTeX error: " + errors[0][2:]
    if UNDEFINED in text:
        return "undefined references or citations"
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


def differences(one, other, job, outdir):
    keys = sorted(k for k in one.keys() | other.keys()
                  if one.get(k) != other.get(k))
    fdb = outdir / f"{job}.fdb_latexmk"
    sources = []
    if fdb.exists():
        sources = [Path(line.split('"')[1]) for line in
                   fdb.read_text(encoding="utf-8",
                                 errors="replace").splitlines()
                   if line.startswith('  "') and '.tex"' in line]
    names = chunk_names(set(keys[:SHOWN]), sources)
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


def main(job, outdir, engine):
    outdir = Path(outdir)
    log, aux, flip = (outdir / f"{job}.{ext}" for ext in ("log", "aux", "flip"))
    text = read_log(log)
    if reason := log_failure(text):
        sys.exit(f"check: {job} failed: {reason}")
    if not unsettled(text):
        return
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
        subprocess.run(engine, stdout=subprocess.DEVNULL, check=False)
        text = read_log(log)
        if reason := log_failure(text):
            sys.exit(f"check: {job} failed: {reason}")
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
                + differences(states[run - 1][1], states[run][1], job, outdir)
                + ["check: passed with that warning (the PDF is the last "
                   "run's)"])
            flip.write_text(json.dumps({"states": [states[run - 1][0],
                                                   states[run][0]],
                                        "warning": warning}))
            print(warning, file=sys.stderr)
            return
    sys.exit(f"check: {job} did not settle after {MORE_RUNS} more runs, "
             "and it is not a two-state flip")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
