#!/usr/bin/env python3
"""Check what a LaTeX build left; pass a cycle of references with a warning.

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

MORE_RUNS = 4
SHOWN = 20
UNSETTLED = ("Label(s) may have changed", "Rerun to get")
PYTHONTEX_MISSING = re.compile(
    r"Package PythonTeX Warning: (Missing|Non-existent) [a-z ]*content"
    r"|Run PythonTeX to create it")
FLIP_WARNING = ("the references alternate between two states and cannot "
                "settle")
CYCLE_WARNING = "the references cycle through {} states and cannot settle"
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
        return errors[0]
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
    """Return {label: (number, page shown)} from the .aux.

    A noweb chunk label has no number of its own (""); its page gets the
    letter noweb shows.
    """
    found, on_page = {}, {}
    if not aux.exists():
        return found
    for line in aux.read_text(encoding="latin-1").splitlines():
        if m := NEWSUBLABEL.match(line):
            key, page = m.groups()
            on_page[page] = on_page.get(page, 0) + 1
            found[key] = ("", page + chr(ord("a") + on_page[page] - 1))
        elif m := NEWLABEL.match(line):
            found[m.group(1)] = (m.group(2), m.group(3))
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


def alternatives(values):
    return ", ".join(values[:-1]) + " or " + values[-1]


def described(entries):
    """Say what a label reads in each state, in the order given."""
    present = [entry for entry in entries if entry is not None]
    numbers = {number for number, _ in present}
    pages = {page for _, page in present}
    if len(numbers) <= 1:
        return "page " + alternatives(
            [entry[1] if entry else "none" for entry in entries])
    if len(pages) == 1 and len(present) == len(entries):
        return (f"number {alternatives([number for number, _ in entries])}"
                f" on page {pages.pop()}")
    return alternatives(["none" if entry is None
                         else f"{entry[0]} on page {entry[1]}"
                         for entry in entries])


def differences(states, sources):
    """List the labels that do not read the same in all the states."""
    keys = sorted(k for k in set().union(*states)
                  if len({state.get(k) for state in states}) > 1)
    names = chunk_names(set(keys[:SHOWN]),
                        [s for s in sources if s.suffix == ".tex"])
    lines = []
    for key in keys[:SHOWN]:
        label = f"<<{names[key]}>> ({key})" if key in names else key
        lines.append(f"  {label}: "
                     f"{described([state.get(key) for state in states])}")
    if len(keys) > SHOWN:
        lines.append(f"  ... and {len(keys) - SHOWN} more labels")
    if not keys:
        lines.append("  no label differs; the other files that feed back do")
    return lines


def stood_still(states):
    """Whether some run left the files that feed back as it found them."""
    digests = [digest for digest, _ in states]
    return any(one == next_ for one, next_ in zip(digests, digests[1:]))


def period(states):
    """Return how many runs ago the last state was seen before, or None.

    A run that left the files as it found them while the log still asks
    for another run shows that something the snapshot does not hold
    feeds back.  The argument for a cycle needs the snapshot to hold
    everything a run depends on, so after such a run no repeat counts.
    """
    if len(states) < 3 or stood_still(states):
        return None
    last = states[-1][0]
    for back in range(2, len(states)):
        if states[-1 - back][0] == last:
            return back
    return None


def sources_digest(sources):
    digest = hashlib.sha256()
    for path in sources:
        digest.update(str(path).encode())
        digest.update(path.read_bytes() if path.exists() else b"\0missing")
    return digest.hexdigest()


def remembered(known, state, sources):
    """Return the warning of the recorded cycle that holds `state`, or None.

    The record counts only for the sources it was written for, and a
    record that cannot be read is no record.
    """
    try:
        record = json.loads(known.read_text())
        if (record["sources"] == sources_digest(sources)
                and state in record["states"]):
            return str(record["warning"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def cycle_warning(job, cycle, sources):
    """Word the warning for the states of one cycle, in run order."""
    if len(cycle) == 2:
        head = (f"{FLIP_WARNING}: {job} flips between two layouts on every "
                "run")
    else:
        head = (f"{CYCLE_WARNING.format(len(cycle))}: {job} comes back to "
                f"the same layout every {len(cycle)} runs")
    return "\n".join(
        [f"check: warning: {head}; these differ between them:"]
        + differences([labels for _, labels in cycle], sources)
        + ["check: passed with that warning (the PDF is the last run's)"])


def settle(job, outdir, engine, sources):
    """Run the engine up to MORE_RUNS times; pass a cycle."""
    log, aux, known = (outdir / f"{job}.{ext}"
                       for ext in ("log", "aux", "cycle"))
    files = feedback_files(job, outdir)
    states = [snapshot(files, aux)]
    if warning := remembered(known, states[0][0], sources):
        print(warning, file=sys.stderr)
        return
    known.unlink(missing_ok=True)
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
            known.unlink(missing_ok=True)
            return
        states.append(snapshot(files, aux))
        if back := period(states):
            cycle = states[-back:]
            warning = cycle_warning(job, cycle, sources)
            known.write_text(json.dumps(
                {"sources": sources_digest(sources),
                 "states": [digest for digest, _ in cycle],
                 "warning": warning}))
            print(warning, file=sys.stderr)
            return
    if stood_still(states):
        fail(job, f"it did not settle after {MORE_RUNS} more runs, and a "
             "run left the files that feed back as it found them while "
             "the log still asked for another run: something outside "
             "those files changes between runs, so no cycle can be shown")
    fail(job, f"it did not settle after {MORE_RUNS} more runs, and no "
         "earlier state came back, so it is not a cycle of at most "
         f"{MORE_RUNS} runs: the layout may be converging slowly or "
         "cycling with a longer period")


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
    else:
        (outdir / f"{job}.cycle").unlink(missing_ok=True)
    if not unsettled(text) and args.status != 0:
        fail(job, f"the build rule ended with status {args.status} "
             "(see its output above), and the log does not show why")
    if not pdf.exists():
        fail(job, f"{pdf} is missing")


if __name__ == "__main__":
    main(sys.argv[1:])
