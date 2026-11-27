#!/usr/bin/env python3
"""Check what a LaTeX build left; pass a cycle of references with a warning
that says where the layouts of its states first part.

Usage: check-settled.py --status N --sources "F ..." JOB OUTDIR ENGINE ...

Called by `make check` (check.mk) after the build: N is the build rule's
exit status, ENGINE the engine command line for extra runs.  What it
accepts and why is described in the documentation, chapter on the
command-line interface, section "Keeping the woven document buildable"
(src/scholar/cli.nw, sec:woven-document).
"""
import argparse
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

MORE_RUNS = 8
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


FOLIO = re.compile(r"^(\d+|[ivxlcdm]+)$")
FOLIO_LINES = 3      # the folio is looked for among a page's first/last lines
EDGE = 3             # lines that identify a page break on either side of it
SHOWN_LINES = 8      # differing lines shown per state
LOOK_BACK = 20       # pages searched back for the nearest chunk
NUMBER = re.compile(r"\d+[a-z]?\b")
FILLER = re.compile(r"[\s.]+")
CHUNK_LINE = re.compile("\u27e8(.+?)\u27e9\\+?\u2261")
CHUNK_PAGES = re.compile(r"(\s+\d+[a-z]?(,\s*\d+[a-z]?)*)+$")
MODDEF = re.compile(r"\\moddef\{(.*?)~\{")
NUMBERLINE = re.compile(r"\\\w*numberline\s*\{([^{}]*)\}")
# What a changed line is, by its text and by its masked text.
KINDS = [
    (re.compile(r"\b(used|continued|defined) in chunks?\b|^Uses\b"
                r"|^Defines:"), None, "a list of noweb's cross-references"),
    (re.compile(r"(\. ){3,}|\.{4,}"), None,
     "a line of the table of contents"),
    (None, re.compile(r"^[0\W]*(and[0\W]*)?$"), "a line of numbers"),
]


def masked(line):
    """Return `line` with its numbers and leader dots made alike."""
    return FILLER.sub(" ", NUMBER.sub("0", line)).strip()


class Layout:
    """What one run's PDF shows, kept small.

    Per page: its folio, the masked lines at its head and at its foot
    (enough to tell whether a page break moved) and all its lines,
    compressed, for the one page that is shown in the end.
    """

    def __init__(self, text):
        pages = text.split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        self.folios, self.heads, self.feet, self._packed = [], [], [], []
        for page in pages:
            lines = [line.strip() for line in page.splitlines()
                     if line.strip()]
            folio = None
            ends = list(range(min(FOLIO_LINES, len(lines))))
            ends += range(max(len(lines) - FOLIO_LINES, len(ends)),
                          len(lines))
            for index in ends:
                if FOLIO.match(lines[index]):
                    folio = lines.pop(index)
                    break
            self.folios.append(folio)
            self.heads.append(tuple(map(masked, lines[:EDGE])))
            self.feet.append(tuple(map(masked, lines[-EDGE:])))
            self._packed.append(zlib.compress("\n".join(lines).encode()))

    def __len__(self):
        return len(self._packed)

    def lines(self, page):
        if page >= len(self):
            return []
        return zlib.decompress(self._packed[page]).decode().split("\n")

    def break_after(self, page):
        """What decides the break after `page`: its foot, the next head."""
        return (self.feet[page] if page < len(self) else None,
                self.heads[page + 1] if page + 1 < len(self) else None)


def read_layout(pdf):
    """Return the Layout of `pdf`, or why it cannot be read."""
    if shutil.which("pdftotext") is None:
        return "pdftotext (poppler-utils) is not installed"
    try:
        result = subprocess.run(
            ["pdftotext", "-q", "-enc", "UTF-8", str(pdf), "-"],
            stdin=subprocess.DEVNULL, capture_output=True, check=False)
    except OSError as error:
        return f"pdftotext could not run ({error})"
    if result.returncode != 0:
        return (f"pdftotext could not read {pdf} (exit status "
                f"{result.returncode})")
    return Layout(result.stdout.decode("utf-8", errors="replace"))


def first_parting(layouts):
    """Return the first page whose break differs among `layouts`, or None."""
    for page in range(max(len(layout) for layout in layouts)):
        if len({layout.break_after(page) for layout in layouts}) > 1:
            return page
    return None


def named_states(numbers):
    if len(numbers) == 1:
        return f"state {numbers[0]}"
    return (f"states {', '.join(map(str, numbers[:-1]))} and "
            f"{numbers[-1]}")


def kind(line):
    for in_text, in_masked, name in KINDS:
        if (in_text and in_text.search(line)
                or in_masked and in_masked.search(masked(line))):
            return f" ({name})"
    return ""


def changed_lines(first, other):
    """Return the lines of two versions of a page that differ in more
    than numbers, as (index in `first` or None, side, line); a line
    that only went over the page break at the foot is left out."""
    ours, theirs = list(map(masked, first)), list(map(masked, other))
    found = []
    matcher = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        at_foot = i2 == len(ours) and j2 == len(theirs)
        if tag == "equal" or (at_foot and tag in ("insert", "delete")):
            continue
        found += [(i, 0, first[i]) for i in range(i1, i2)]
        found += [(i1, 1, other[j]) for j in range(j1, j2)]
    return found


def nearest_chunk(layout, page, before):
    """Return the name of the chunk last defined before line `before`
    of `page`, looking back up to LOOK_BACK pages."""
    for back in range(page, max(page - LOOK_BACK, 0) - 1, -1):
        lines = layout.lines(back)
        if back == page:
            lines = lines[:before + 1]
        for line in reversed(lines):
            if m := CHUNK_LINE.search(line):
                return CHUNK_PAGES.sub("", m.group(1)).strip()
    return None


def alnum(text):
    return re.sub(r"\\(code|edoc)\{\}|[^0-9a-z]", "", text.lower())


def chunk_source(name, sources):
    """Return the source (the .nw if there is one) that defines `name`."""
    for source in sources:
        if source.suffix != ".tex":
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(alnum(found) == alnum(name) for found in MODDEF.findall(text)):
            nw = source.with_suffix(".nw")
            return nw if nw.exists() else source
    return None


def brace_groups(text):
    groups, depth, start = [], 0, 0
    for index, character in enumerate(text):
        if character == "{":
            depth += 1
            if depth == 1:
                start = index + 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0:
                groups.append(text[start:index])
    return groups


def nearest_section(toc, folio):
    """Return the heading of the .toc last begun on or before page
    `folio` (an arabic page number), or None."""
    if folio is None or not folio.isdigit() or not toc.exists():
        return None
    found = None
    for line in toc.read_text(encoding="latin-1").splitlines():
        if not line.startswith("\\contentsline"):
            continue
        groups = brace_groups(line)
        if len(groups) >= 3 and groups[2].isdigit() \
                and int(groups[2]) <= int(folio):
            title = NUMBERLINE.sub(r"\1 ", groups[1])
            found = re.sub(r"\\[a-zA-Z@]+\s*|[{}]", "", title).strip()
    return found


def place(layouts, sources, toc):
    """Say where the layouts of a cycle's states first part."""
    head = "check: where the layouts first part"
    reasons = [layout for layout in layouts if isinstance(layout, str)]
    if reasons:
        return [f"{head} could not be found: {reasons[0]}"]
    page = first_parting(layouts)
    if page is None:
        return [f"{head}: no page break differs between the states; their "
                "pages differ at most in numbers"]
    folio = layouts[0].folios[page]
    if folio is None:
        at = f"page {page + 1} of the PDF"
    elif folio == str(page + 1):
        at = f"page {folio}"
    else:
        at = f"page {folio} (page {page + 1} of the PDF)"
    lines = [f"{head}: {at}, the first page whose break is not the same "
             "in all the states (numbered in the order of the runs)"]
    variants = {}
    for number, layout in enumerate(layouts, 1):
        key = (tuple(map(masked, layout.lines(page))),
               layout.break_after(page))
        variants.setdefault(key, []).append(number)
    variants = list(variants.values())
    first = layouts[variants[0][0] - 1].lines(page)
    changes, cause = [], len(first)
    for numbers in variants[1:]:
        other = layouts[numbers[0] - 1].lines(page)
        for index, side, line in changed_lines(first, other):
            cause = min(cause, index)
            changes.append((variants[0] if side == 0 else numbers, line))
    nearest = []
    if chunk := nearest_chunk(layouts[variants[0][0] - 1], page, cause):
        source = chunk_source(chunk, sources)
        nearest.append(f"chunk <<{chunk}>>"
                       + (f" ({source})" if source else ""))
    if section := nearest_section(toc, folio):
        nearest.append(f"section {section}")
    if nearest:
        lines.append(f"  nearest before it: {', '.join(nearest)}")
    for numbers in variants:
        verb = "ends" if len(numbers) == 1 else "end"
        lines.append(f"  {named_states(numbers)} {verb} that page with:")
        lines += [f"    | {line}"
                  for line in layouts[numbers[0] - 1].lines(page)[-EDGE:]]
    if changes:
        lines.append("  lines of that page whose text differs in more "
                     "than numbers:")
    shown, per_state = set(), {}
    for numbers, line in changes:
        states = named_states(numbers)
        if (states, line) in shown:
            continue
        shown.add((states, line))
        per_state[states] = per_state.get(states, 0) + 1
        if per_state[states] <= SHOWN_LINES:
            lines.append(f"    {states}: {line}{kind(line)}")
    lines += [f"    {states}: ... and {count - SHOWN_LINES} more lines"
              for states, count in per_state.items()
              if count > SHOWN_LINES]
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
    record that cannot be read is no record; nor is one without the
    place where the layouts part, written before the check found it.
    """
    try:
        record = json.loads(known.read_text())
        if (record["sources"] == sources_digest(sources)
                and state in record["states"]
                and isinstance(record["where"], list)):
            return str(record["warning"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def cycle_warning(job, cycle, where, sources):
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
        + where
        + ["check: passed with that warning (the PDF is the last run's)"])


def settle(job, outdir, engine, sources):
    """Run the engine up to MORE_RUNS times; pass a cycle."""
    log, aux, known, pdf, toc = (
        outdir / f"{job}.{ext}" for ext in ("log", "aux", "cycle", "pdf",
                                            "toc"))
    files = feedback_files(job, outdir)
    states = [snapshot(files, aux)]
    layouts = [None]  # the layout of each state; the first is not needed
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
        layouts.append(read_layout(pdf))
        if back := period(states):
            cycle = states[-back:]
            where = place(layouts[-back:], sources, toc)
            warning = cycle_warning(job, cycle, where, sources)
            known.write_text(json.dumps(
                {"sources": sources_digest(sources),
                 "states": [digest for digest, _ in cycle],
                 "where": where,
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
