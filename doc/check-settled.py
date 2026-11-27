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


FOLIO = re.compile(r"^([0-9]+|[ivxlcdm]+)$")
ROMAN = re.compile(r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
ROMAN_DIGITS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500,
                "m": 1000}
FOLIO_LINES = 10     # the folio is looked for among a page's first/last lines
FOLIO_RUN = 10       # pages on either side whose folios a folio must fit
EDGE = 3             # last lines of a page that identify the break after it
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
LIST_HEAD, NUMBERS_ONLY = KINDS[0][0], KINDS[2][1]
CHUNK_TAG = re.compile(r"^\d+[a-z]?$")
WIDTH = 76           # longer lines are cut when shown
TEXT_TIMEOUT = 120   # seconds one pdftotext read may take (book: 14 s)
PLACE_HEAD = "check: where the layouts first part"


def masked(line):
    """Return `line` with its numbers and leader dots made alike."""
    return FILLER.sub(" ", NUMBER.sub("0", line)).strip()


def folio_value(text):
    """Return what a printed page number counts in, and its value."""
    if text.isdigit():
        return "arabic", int(text)
    if not ROMAN.match(text):
        return None
    digits = [ROMAN_DIGITS[letter] for letter in text]
    return "roman", sum(-digit if digit < after else digit
                        for digit, after in zip(digits, digits[1:] + [0]))


def page_lines(page):
    return [line.strip() for line in page.splitlines() if line.strip()]


def folio_candidates(number, lines):
    """Return the lone numbers among the first and last lines of page
    `number` (from 1), as (index, (kind, offset from the PDF's page))."""
    ends = list(range(min(FOLIO_LINES, len(lines))))
    ends += range(max(len(lines) - FOLIO_LINES, len(ends)), len(lines))
    found = []
    for index in ends:
        if FOLIO.match(lines[index]) and (value := folio_value(lines[index])):
            kind, counted = value
            found.append((index, (kind, number - counted)))
    return found


def folio_indices(candidates):
    """Return per page the index of its folio line, or None.

    The folio is the candidate whose offset the most pages within
    FOLIO_RUN pages share, and at least one page besides its own.
    """
    offsets = [{key for _, key in own} for own in candidates]
    chosen = []
    for page, own in enumerate(candidates):
        near = offsets[max(page - FOLIO_RUN, 0):page + FOLIO_RUN + 1]
        best, support = None, 1
        for index, key in own:
            count = sum(key in other for other in near)
            if count > support:
                best, support = index, count
        chosen.append(best)
    return chosen


class Layout:
    """What one run's PDF shows, kept small.

    Per page: its folio, the masked lines at its foot (enough to tell
    whether the break after it moved) and all its lines, compressed,
    for the one page that is shown in the end.
    """

    def __init__(self, text):
        pages = text.split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        self.folios, self.feet, self._packed = [], [], []
        indices = folio_indices([folio_candidates(number, page_lines(page))
                                 for number, page in enumerate(pages, 1)])
        for page, index in zip(pages, indices):
            lines = page_lines(page)
            self.folios.append(None if index is None else lines.pop(index))
            self.feet.append(tuple(map(masked, lines[-EDGE:])))
            self._packed.append(zlib.compress("\n".join(lines).encode()))

    def __len__(self):
        return len(self._packed)

    def lines(self, page):
        if page >= len(self):
            return []
        return zlib.decompress(self._packed[page]).decode().split("\n")

    def break_after(self, page):
        """What tells the break after `page`: the foot of that page."""
        return self.feet[page] if page < len(self) else None


def read_layout(pdf, timeout=TEXT_TIMEOUT):
    """Return the Layout of `pdf`, or why it cannot be read."""
    if shutil.which("pdftotext") is None:
        return "pdftotext (poppler-utils) is not installed"
    try:
        result = subprocess.run(
            ["pdftotext", "-q", "-enc", "UTF-8", str(pdf), "-"],
            stdin=subprocess.DEVNULL, capture_output=True, check=False,
            timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"pdftotext did not finish reading {pdf} within {timeout} s"
    except OSError as error:
        return f"pdftotext could not run ({error})"
    if result.returncode != 0:
        return (f"pdftotext could not read {pdf} (exit status "
                f"{result.returncode})")
    if not result.stdout.strip():
        return f"pdftotext found no text in {pdf}"
    return Layout(result.stdout.decode("utf-8", errors="replace"))


def guarded(find, *args):
    """Return `find(*args)`, or why it failed, as a string.

    Finding the place only adds to the warning; whatever goes wrong
    there must not change the verdict, so nothing may escape.
    """
    try:
        return find(*args)
    except Exception as error:  # the verdict is not this code's to change
        return f"{type(error).__name__}: {error}"


def not_found(reason):
    return [f"{PLACE_HEAD} could not be found: {reason}"]


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
    than numbers, as (index in `first`, side, index in its page, line),
    side 0 for `first` and 1 for `other`; a line that only went over
    the page break at the foot is left out."""
    ours, theirs = list(map(masked, first)), list(map(masked, other))
    found = []
    matcher = difflib.SequenceMatcher(None, ours, theirs, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        at_foot = i2 == len(ours) and j2 == len(theirs)
        if tag == "equal" or (at_foot and tag in ("insert", "delete")):
            continue
        found += [(i, 0, i, first[i]) for i in range(i1, i2)]
        found += [(i1, 1, j, other[j]) for j in range(j1, j2)]
    return found


def lists_on(lines):
    """Return noweb's lists on a page as {key: (first line, lines)}.

    A list is a line that begins one, with the lines of nothing but
    numbers that continue it; numbers at the top of a page continue a
    list from the page before.  The key is what the list is of (its
    first words, which name the identifier or chunk) and how many lists
    of that stand before it on the page, so that the same list is found
    in every state however its lines wrap.
    """
    found, seen, index = {}, {}, 0
    while index < len(lines):
        line, end = lines[index], index + 1
        if LIST_HEAD.search(line):
            what = re.sub(r"chunks\b", "chunk", masked(line).split(" 0")[0])
        elif index == 0 and NUMBERS_ONLY.search(masked(line)):
            what = "(continued from the page before)"
        else:
            index = end
            continue
        while (end < len(lines) and not LIST_HEAD.search(lines[end])
               and NUMBERS_ONLY.search(masked(lines[end]))):
            end += 1
        found[(what, seen.get(what, 0))] = (line, range(index, end))
        seen[what] = seen.get(what, 0) + 1
        index = end
    return found


def nearest_chunk(layout, page, before):
    """Return the name and the tag ("209a") of the chunk last defined
    before line `before` of `page`, looking back up to LOOK_BACK pages."""
    for back in range(page, max(page - LOOK_BACK, 0) - 1, -1):
        lines = layout.lines(back)
        if back == page:
            lines = lines[:before + 1]
        for index in range(len(lines) - 1, -1, -1):
            if m := CHUNK_LINE.search(lines[index]):
                tag = lines[index - 1] if index else ""
                return (CHUNK_PAGES.sub("", m.group(1)).strip(),
                        tag if CHUNK_TAG.match(tag) else None)
    return None, None


def alnum(text):
    return re.sub(r"\\(code|edoc)\{\}|[^0-9a-z]", "", text.lower())


def read_sources(sources):
    for source in sources:
        if source.suffix != ".tex":
            continue
        try:
            yield source, source.read_text(encoding="utf-8",
                                           errors="replace")
        except OSError:
            continue


def chunk_source(name, tag, labels, sources):
    """Return the source (the .nw if there is one) of a chunk.

    Many files define a chunk of the same name (<<functions>>), so the
    chunk is first looked up by its tag: the .aux gives the noweb label
    that reads that tag, and the woven source that sets that label is
    the one.  Without a tag or a label, the first source that defines a
    chunk of that name is taken.
    """
    keys = {key for key, value in labels.items() if value == ("", tag)}
    marks = [f"\\sublabel{{{key}}}" for key in keys]
    found = by_name = None
    for source, text in read_sources(sources):
        if any(mark in text for mark in marks):
            found = source
            break
        if by_name is None and any(alnum(defined) == alnum(name)
                                   for defined in MODDEF.findall(text)):
            by_name = source
            if not marks:
                break
    found = found or by_name
    if found is None:
        return None
    nw = found.with_suffix(".nw")
    return nw if nw.exists() else found


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


def nearest_section(toc, folio, above):
    """Return the heading of the .toc last begun before the place.

    The place is on page `folio` (an arabic page number), below the
    lines `above`; a heading on that page counts only if it stands
    among those lines.
    """
    if folio is None or not folio.isdigit() or not toc.exists():
        return None
    text_above = "".join(map(alnum, above))
    found = None
    for line in toc.read_text(encoding="latin-1").splitlines():
        groups = brace_groups(line)
        if (not line.startswith("\\contentsline") or len(groups) < 3
                or not groups[2].isdigit() or int(groups[2]) > int(folio)):
            continue
        number = NUMBERLINE.search(groups[1])
        title = re.sub(r"\\[a-zA-Z@]+\s*|[{}]", "",
                       NUMBERLINE.sub("", groups[1])).strip()
        if int(groups[2]) == int(folio) and alnum(title) not in text_above:
            continue
        found = f"{number.group(1)} {title}" if number else title
    return found


def cut(line):
    return line if len(line) <= WIDTH else line[:WIDTH - 3] + "..."


def counted(count):
    return "none" if count == 0 else f"{count} line" + "s" * (count > 1)


def place(layouts, labels, sources, toc):
    """Say where the layouts of a cycle's states first part."""
    reasons = [layout for layout in layouts if isinstance(layout, str)]
    if reasons:
        return not_found(reasons[0])
    page = first_parting(layouts)
    if page is None:
        return [f"{PLACE_HEAD}: no page break differs between the states; "
                "their pages differ at most in numbers"]
    folio = layouts[0].folios[page]
    if folio is None:
        at = f"page {page + 1} of the PDF"
    elif folio == str(page + 1):
        at = f"page {folio}"
    else:
        at = f"page {folio} (page {page + 1} of the PDF)"
    lines = [f"{PLACE_HEAD}: {at}, the first page whose break is not the "
             "same in all the states (numbered in the order of the runs)"]
    variants = {}
    for number, layout in enumerate(layouts, 1):
        key = (tuple(map(masked, layout.lines(page))),
               layout.break_after(page))
        variants.setdefault(key, []).append(number)
    variants = list(variants.values())
    pages = [layouts[numbers[0] - 1].lines(page) for numbers in variants]
    changes, cause = [], len(pages[0])
    for other in range(1, len(variants)):
        for index, side, own, line in changed_lines(pages[0], pages[other]):
            cause = min(cause, index)
            changes.append((0 if side == 0 else other, own, line))
    lists = [lists_on(text) for text in pages]
    grown = [key for key in dict.fromkeys(k for found in lists for k in found)
             if len({len(found[key][1]) if key in found else 0
                     for found in lists}) > 1]
    in_grown = {(variant, index) for variant, found in enumerate(lists)
                for key in grown if key in found
                for index in found[key][1]}
    nearest = []
    chunk, tag = nearest_chunk(layouts[variants[0][0] - 1], page, cause)
    if chunk:
        source = chunk_source(chunk, tag, labels[variants[0][0] - 1],
                              sources)
        nearest.append(f"chunk <<{chunk}>>"
                       + (f" ({source})" if source else ""))
    if section := nearest_section(toc, folio, pages[0][:cause]):
        nearest.append(f"section {section}")
    if nearest:
        lines.append(f"  nearest before it: {', '.join(nearest)}")
    for numbers, text in zip(variants, pages):
        verb = "ends" if len(numbers) == 1 else "end"
        lines.append(f"  {named_states(numbers)} {verb} that page with:")
        lines += [f"    | {cut(line)}" for line in text[-EDGE:]]
    if grown:
        lines.append("  noweb's lists on that page whose length differs:")
    for key in grown:
        first = next(found[key][0] for found in lists if key in found)
        lengths = ", ".join(
            f"{counted(len(found[key][1]) if key in found else 0)} in "
            f"{named_states(numbers)}"
            for numbers, found in zip(variants, lists))
        lines.append(f'    "{cut(first)}": {lengths}')
    changes = [(variant, line) for variant, own, line in changes
               if (variant, own) not in in_grown]
    if changes:
        lines.append("  other lines of that page whose text differs in "
                     "more than numbers:")
    shown, per_state = set(), {}
    for variant, line in changes:
        states = named_states(variants[variant])
        if (states, line) in shown:
            continue
        shown.add((states, line))
        per_state[states] = per_state.get(states, 0) + 1
        if per_state[states] <= SHOWN_LINES:
            lines.append(f"    {states}: {cut(line)}{kind(line)}")
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


def settle(job, outdir, engine, sources, text_timeout=TEXT_TIMEOUT):
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
        layouts.append(guarded(read_layout, pdf, text_timeout))
        if back := period(states):
            cycle = states[-back:]
            where = guarded(place, layouts[-back:],
                            [labels for _, labels in cycle], sources, toc)
            if isinstance(where, str):
                where = not_found(where)
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
    parser.add_argument("--text-timeout", type=int, default=TEXT_TIMEOUT)
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
        settle(job, outdir, args.engine, sources, args.text_timeout)
    else:
        (outdir / f"{job}.cycle").unlink(missing_ok=True)
    if not unsettled(text) and args.status != 0:
        fail(job, f"the build rule ended with status {args.status} "
             "(see its output above), and the log does not show why")
    if not pdf.exists():
        fail(job, f"{pdf} is missing")


if __name__ == "__main__":
    main(sys.argv[1:])
