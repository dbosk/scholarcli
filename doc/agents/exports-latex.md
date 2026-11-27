# Exports: provenance blocks, CSV, LaTeX and BibTeX

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Provenance Round-Trip

The `bibtex+prov` export format wraps each entry in a provenance comment
block (`% === provenance: <key> ===` + `CLAIM`/`FOUND-VIA`/`PICKED`/`QUOTE`/
`VERIFIED`/`COUNTER`/`DATE`). `scholar prov` keeps those blocks in sync with `scholar
notes`:

- `scholar prov import refs.bib` parses each entry's block(s) into that
  paper's note, **merging by `CLAIM`** (idempotent — re-importing never
  duplicates) and preserving any personal note prose.
- `scholar prov export refs.bib` writes a paper's stored block(s) back above
  its entry; personal prose is never emitted. Prints to stdout (count on
  stderr) by default; `--in-place/-i` overwrites the file.

A note is parsed into ordered segments — `personal` (verbatim) or `prov`
(a parsed block) — by `_split_note_segments`. Entries are keyed by
reconstructing a `Paper` from the `.bib` fields and reusing `Paper.id`
(DOI, else title+author hash). Our `.bib` fields are escaped (#230),
so the id is recorded: `bibtex+prov` writes `% ID: <Paper.id>` in each
block (`ID` is in `PROV_FIELD_NAMES`), `prov export` writes the note's
current id into every block it emits, and `prov import` keys by it
(`_recorded_id`) and drops it from the stored note (`_without_ids`).
An entry's own DOI beats the recorded id (a paper that gained a DOI, a
block copied above another entry; a differing id is a WARNING naming
both); for a DOI-less entry the recorded id is tried like the other
candidates, by whether a note exists under it, and keys a new note
only when none does.
Without the line (old or hand-made files, plain `-f bibtex` for
export) `_paper_from_entry` tries existing notes: the id with the
`BIBTEX_SPECIALS` escapes undone, then a DOI-less note whose
`escape_bibtex` title equals the entry's and whose id that title and a
spelling of the first author's surname give (`_unescaped_spellings`
over `LATEX_UNICODE_PUNCTUATION`, `MAX_SPELLINGS`; `_noted_titles` is
built lazily, once per command), then the id of the text as written
(notes imported from hand-escaped files before #230); else the
unescaped paper. An import keeps an existing note's title.
`_unescape_bib` also drops the `\scholarnonlatin` wrapper (#234). When
an entry uses that macro, `search -f bibtex`/`bibtex+prov` print one
`@preamble{ "..." }` line with `review.nonlatin_definition()` before the
first entry (`review.nonlatin_bib_preamble`; biber copies it to
the .bbl; checked with pdflatex/xelatex/lualatex); no stderr hint.
All round-trip code lives in `cli.nw`'s
`<<formatter classes>>` and `<<prov command>>` chunks.

**`scholar prov check FILE.bib ... [--quotes] [--metadata]
[--allow-unbacked] [-f table|json]`** (#346, cli.nw `sec:prov-check`):
read-only on the `.bib`, notes and sessions (tested byte-identical);
no request except `--metadata`'s Crossref lookups. Reading
(`read_prov_bib` -> `ProvCheckEntry`): the line reader of `prov import`
(`_parse_bib_entries`: blocks, wrapped fields, stacked blocks, `ID`)
joined with bibtexparser (entry fields whole, LaTeX-decoded) on the
0-based start line (`ProvEntry.entry_start` == `Block.start_line`); DOI
and URL from the undecoded entry, read BEFORE `transform_entry`, which
mutates its argument (DOI via `read_bibtex_verbatim`, URL as written).
A `DuplicateBlockKeyBlock` (checked from `ignore_error_block`) and a
`ParsingFailedBlock` are errors; `@comment/@preamble/@string` skipped.
A block cut off by a blank line is missing (prov import skips it too).
Files are read as `utf-8-sig` (a BOM made the first entry blockless).
`stray_prov_blocks` (same line walk as `_parse_bib_entries`) reports
each block no entry directly follows (end of file, above `@string` or
`@comment`, cut off by a blank line) as an error with its line and
header key: `ProvStrayBlock`, text "  KEY (line L): provenance block
with no entry directly below it", summary ", N blocks without an
entry", JSON `unattached` list and `summary.unattached`. A header key
(`% === provenance: KEY ===`) other than the entry's key is an error
naming both (prov import ignores the header key; bibtex+prov and prov
export always write the entry's key, so no legitimate mismatch).
Blocks: per block `prov_block_problems` over `PROV_REQUIRED_FIELDS`
(CLAIM FOUND-VIA PICKED QUOTE VERIFIED COUNTER; ID and DATE not
required): missing, empty, placeholder (`is_prov_placeholder`: the value
BEGINS with the word `TODO`, capitals, so `TODO: find it` is one and
"keep the TODO list short" is not; or the whole value a `<...>`
template, bare or as the whole of one pair of double marks,
`"<verbatim passage>"` (`QUOTE_PATTERN.fullmatch`, #359; `--quotes`
skips it like `TODO`); a location, `(<loc>)`, judged alike). A QUOTE passage, or a
part of one between ellipses (`quote_parts`), with no letter and no
digit (`prov_passage_has_words`) is a block error "holds no words",
with or without `--quotes`, and is never looked up.
Fields are found by the first word of the name (`prov_field_values`:
`QUOTE (p.3)` -> location `p.3`). A name given twice in one block is
an error (`repeated_prov_fields` counts the comment lines; the line
reader's dict keeps only the last, so prov import loses the others).
No block: error; `--allow-unbacked` makes it a note (summary "N entries
without a block"). `--quotes` (`prov_quote_checks`): passages via
`quotes_in_reason` (double marks only; a QUOTE without one is not
checked); VERIFIED starting `abstract` -> the entry's `abstract` field
(none -> not checked), else full text from `pdf.cached_pdf_for(doi,
url)` (DOI import keys `doi_pdf_paths`, the link of a cached Unpaywall
answer `unpaywall.cached_pdf_link`, never a request, the `url` field's
download; first readable wins); text `pdf.pdf_running_text` (pages
joined, PDFium's U+FFFE line-end mark and `-` + line break kept as
`-`, lines joined). Match: `normalized_for_quotes` +
`fold_word_hyphens` (a hyphen between letters/digits removed on both
sides) + `quote_parts`/`quote_occurs` (ellipsis parts in order); every
passage checked, no 3-word minimum. A download resolved by Semantic
Scholar or the landing page is not found (their answers are not
cached). No cached PDF / unreadable / no text -> not checked (counted,
printed, not an error). Measured 2026-11-27 on arXiv 1706.03762v7 and
1810.04805v2: 6 of 6 quotes found, a misquote reported; keeping or
dropping the U+FFFE mark without the fold missed 2 resp. 3.
`--metadata` (`prov_metadata_checks`, `sec:prov-check-metadata`):
`crossref.fetch_bibliographic(doi)` (side entry `("bibliographic",
doi)` = `{title, subtitle, families, years}` written by
`_remember_work`, built-in types, no `CURRENCY_CACHE_VERSION` bump; an
older entry costs one request; `families` holds `family`, else an
organisation's `name`). Title (`metadata_title_result`, no threshold):
`metadata_fold` (casefold, accents/TeX/braces dropped, `[\W_]` runs ->
one space, any script kept) of the bib title must EQUAL Crossref's
title or title + subtitle; bib title = Crossref title + ":" + a
subtitle, Crossref holding none -> note "subtitle not in Crossref's
record" (counted in `summary.metadata.notes`, summary ", N notes";
the entry counts as agreeing); else differs. Authors: sorted folded
surnames (bibtexparser name parts of the author decoded a second time
with `keep_braced_groups=True`, so `{The Study Group}` is one name and
meets Crossref's `name`; `and others` dropped), compared only when
both sides have some; year (`year`, else `date`) in issued /
published-print / published-online (not `created`/`deposited`; no
`published` field read, unverified). Differ -> error; 404 ->
not checked "DOI ... is not known to Crossref" (no DataCite); failure
(`last_lookup_error` set: 429, 5xx, connection, cooldown) -> result
and finding level `lookup failed` (#356), "lookup failed: metadata:
Crossref: <reason>", counted apart (`summary.metadata["lookup
failed"]`, text ", N lookup failed" only when N > 0), not an error but
exit 1; no DOI -> not checked. Exit 1 on any error or failed lookup,
else 0; 2 for an unknown `-f` (before reading); 1 with one line for an
unreadable file (before any check; with `-f json` stdout still holds
`{"files": [... {"file", "error"}], "entries": [], "unattached": [],
"summary": null}`). Text: "FILE: N entries", per
finding "  key (line L[, block B]): [not checked: |note: ]message",
summary "E entries, B blocks, X errors[, U entries without a block][,
S blocks without an entry][; quotes: f found, m not found, u not
checked][; metadata: a agree, d differ, u not checked[, f lookup
failed][, n notes]]." JSON: `entries` (file, key, line, blocks,
findings, `quotes`/`metadata` when asked), `files` (file, error
null), `unattached` and `summary` (`prov_check_counts`). Left to the backing-claims skill: VERIFIED level
words, causal/quantitative claims verified at abstract level, COUNTER
wording and `see <key>`, missing DATE, QUOTE
without a location. Tests: `RequestTargets.answer(path, body,
status=200)` (conftest) serves a recorded body, or an injected status
(a 429 for the failed lookup); `make_pdf` /
`make_cli_pdf` take a list of lines.

## `search -f csv` rows (#300)

`search -f csv` is tab-separated, written by Python's `csv` module
(`csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")`, default
quote mark `"` and `QUOTE_MINIMAL`); read it with
`csv.reader(f, delimiter="\t")` (cli.nw `sec:search-csv-rows`). The `#`
lines and blank lines are printed as before; only the header and paper
rows go through the writer. A row whose fields hold no tab, line break
or quote mark is byte-identical to the old f-string output (tested);
**behaviour change**: a field holding a quote mark, a tab or a line
break is now quoted, its quote marks doubled (in the tests' invented
sample, 3 of 20 titles, the ones with a quote mark). Before, a tab or
line break split the cell or row. `clean_metadata_text` keeps tabs and
line breaks (and decodes `&#9;`/`&#10;` into them), so ingest cleaning
does not prevent them. Reading (cli.nw `sec:search-csv-comments`, in
the `--format` help): the output is blocks of `#` lines, a blank
line, the header, the paper rows, a blank line; parse it whole with
`csv.reader(f, delimiter="\t")`, rows up to the first empty row are
comments, then the header, then papers up to the next empty row. Never
drop lines starting with `#` before parsing (a quoted title can hold
`\n#...`, a title can begin with `#`). `csv_comment` turns tab,
CR and LF in every `#` line into spaces (a query `x<TAB>"y` or
`a<LF>"b` used to open a quoted field that swallowed every row);
quote marks stay, since a comment row is one field beginning with `#`
(tested with `"a b"`, several blocks, `# Results:`/`# Search:`
errors with line breaks).

## Spreadsheet-safe CSV (`--spreadsheet-safe`, #285)

`sessions export -f csv|all --spreadsheet-safe` and `search -f csv
--spreadsheet-safe` (review.nw `sec:spreadsheet-safe`) write each cell
that begins with a character of `SPREADSHEET_FORMULA_STARTS` (`=
+ - @`, tab, CR, LF, full-width U+FF1D U+FF0B U+FF0D U+FF20: OWASP's
CSV-injection list, read 2026-11-20 at
https://owasp.org/www-community/attacks/CSV_Injection, no more and no
fewer), or with `'` itself, with one `'` in front
(`spreadsheet_safe_cell`). The page's tab prefix was not taken: the
same page lists tab as a trigger. The page wraps and prefixes *every*
field; prefixing only trigger cells and leaving quoting to
`csv.writer`'s minimal rule is scholar's choice (exact undo, other
cells unchanged for scripts; quoting every field changed nothing in
LibreOffice, comma import). Numeric columns (`CSV_NUMERIC_COLUMNS` =
`year`, `llm_confidence`; `SpreadsheetSafeWriter` finds them by header
name, so a new column is text; search's year likewise) go through
`spreadsheet_safe_number`: left alone only for an int, a float or a
string `float()` reads that equals its `strip()` (`"\t5"` is text), else treated as text (a session can hold
`"year": "=1+2"`; `Paper.from_dict` keeps it). Undo: drop the first
character of every cell, in any column, that begins with `'` (exact: a
leading `'` is doubled, and a number left alone never begins with
`'`). `#` lines and headers are unchanged. In `search` the prefix is
put on the cell before `csv.writer` writes it, so a cell beginning with
a tab or line break stays one quoted cell (tested; LibreOffice read it
as one text cell, the old unquoted row as a formula). Off by default
and byte-identical without it (checked against e7dc5f5): scripts read
the raw file. To make it the default, set
`cli.SPREADSHEET_SAFE_DEFAULT = True` (the flag has
`--no-spreadsheet-safe`; `None` = not given). With another format it is
refused (exit 2; search: not csv/auto, before searching; export: not
csv/all, before loading). Limits, also in both helps: it protects only
a reader that uses the file's own separator (comma for the export, tab
for search; a semicolon import of the safe export gave the same
formulas as the raw one for a field holding `a;=1+2`); LibreOffice
shows the `'` as part of the text; Excel may drop the prefix on save
and reopen (the page). LibreOffice 26.2.6.3, tried 2026-11-20; Excel
not tried. Not covered: `sessions check -f csv`, the screen sheet.

## LaTeX Output: Standalone, Fragment, Audit Table

`review.py` owns the shared LaTeX pieces: the escapers (`escape_latex`,
`escape_bibtex`: one pass, Unicode punctuation mapped to TeX, single
Greek letters and math symbols in math mode, symbol-only characters
beyond Latin Extended-B (`☆`, emoji) dropped so pdflatex never sees
them), `LATEX_PACKAGES`,
`latex_document` (compilable skeleton, escaped title), `latex_fragment`
(body plus a `%` header telling the includer which packages,
`\addbibresource` line and biber run it needs; `\addbibresource` is
preamble-only, so a fragment can only instruct), `refsection`, the two
report body builders (`build_review_provenance_latex`,
`build_review_decisions_latex`) and the audit table
(`build_audit_table_latex` / `generate_audit_table`).

Text in other scripts (#220, `review.nw` `sec:non-latin-text`): every
run of letters/digits pdflatex cannot set in T1 (Cyrillic, CJK, Arabic,
Greek *words*: 3+ letters or an accented one; single Greek letters stay
math) is wrapped in `\scholarnonlatin{...}` by both escapers, never
dropped (`split_nonlatin`; a run bridges spaces, digits and punctuation
between such characters, stops at a Latin letter, brace or backslash;
specials inside are escaped). Also flagged: the 213 code points in
U+0080..U+024F that T1+utf8 inputenc does not set up (`T1_UNSET_RANGES`:
C1 controls, `ĸ`, `ħ`, `ſ`, most of Latin Extended-B; exactly what
`t1enc/ts1enc/omsenc/utf8enc.dfu` of TeX Live 2025 leave undeclared,
checked by compiling each code point and by
`test_t1_ranges_match_the_encoding_files`); a word holding a flagged
*Latin* letter (Unicode name `LATIN…`, e.g. Vietnamese) is wrapped
whole. The `.bib` keeps it the same way. A table row's first escaped
cell goes through `latex_row_cell` (`{}` before a leading `[` or `*`,
else unchanged), so `\\` before it cannot read `[conference paper]` as
a length (audit table, provider-specific queries table; the others
start with `\citetitle` or a number). Readable characters beyond the
cutoff are rendered, not wrapped: ligatures U+FB00–FB06 folded by NFKC
(`LATIN_LIGATURES`, only these), super/subscripts U+2070–209C to
`\textsuperscript{}`/`\textsubscript{}` (`LATEX_SCRIPT_CHARS`, built
from names + NFKC; script minus → `-`), `ℓ` → `\ensuremath{\ell}`,
`ʻ ʽ` → `` ` ``, `ʹ` → `'`; other spacing modifiers U+02B0–02FF do not
make a run text (`SPACING_MODIFIERS`), so alone they are dropped. Cc
controls are dropped inside runs too (they stop the T2A recipe).
`latex_document` loads `\usepackage[T1]{fontenc}`
(`STANDALONE_FONTENC`) before `LATEX_PACKAGES`: in OT1 `\textquotedbl`
(any quoted query) and `« » ð þ` … failed; the one line is the only
change to Latin-only standalone output. Fragments do not load it (the
host's choice, like inputenc).
`latex_document`/`latex_fragment` add `nonlatin_definition(marker)`
only when the output uses the macro (`uses_nonlatin` over title,
abstract, body, appendix and the `bib_text` callers pass), so Latin-only
output is byte-identical: three `\providecommand` lines, the text under
XeTeX/LuaTeX (`\ifdefined\XeTeXversion`/`\directlua`), else the marker
`[non-Latin text]` (`NONLATIN_MARKER`; audit table:
`AUDIT_STRINGS[lang]["nonlatin"]`, sv `[icke-latinsk text]`). Standalone:
in the preamble; fragment: in the body before first use, with a `%`
header saying how to define it first (pdflatex Cyrillic:
`\usepackage[T2A,T1]{fontenc}` +
`\newcommand{\scholarnonlatin}[1]{{\fontencoding{T2A}\selectfont #1}}`).
Separator (#262): where a wrapped run touches a letter or digit of the
source (CJK written against Latin: `\u5b66\u4e60Mac OS X...`), both
escapers write `\scholarnonlatinsep{}` between them (`NONLATIN_SEP`,
`_touches_text`; never next to a space or punctuation, so such output
is byte-identical). `nonlatin_definition(marker, separator=True)`
prepends `NONLATIN_SEP_DEFINITION` (empty under XeTeX/LuaTeX, else
`\ `; deliberately no test of whether `\scholarnonlatin` is defined:
an earlier fragment or a cited scholar `.bib`'s `@preamble` defines it
too, and the marker then ran into the Latin words), added by
`latex_document`/`latex_fragment`/`nonlatin_bib_preamble` only when
`uses_nonlatin_sep`; the fragment header then tells a host whose
`\scholarnonlatin` prints the text to add
`\newcommand{\scholarnonlatinsep}{}` (without it: a space where the
scripts touch). `uses_nonlatin` detects either macro; `cli._unescape_bib`
drops the separator before the wrapper; the `--cited-from` reader
(bibtexparser decoding) already drops it (pinned). pdflatex prints
"[non-Latin text] Mac OS X [non-Latin text]", also after an earlier
fragment and after a cited new or old-style `.bib`
(`TestNonLatinSeparatorCompiles`).
An audit row whose title keeps no letter outside such runs
(`only_nonlatin_letters`) also prints `(paper id)` (`doi:…`, else the
hash id; `audit_title_cell`, `AuditRow.nonlatin_title`), and
`build_audit_table_latex` warns once per table counting those rows.
`TestNonLatinCompiles` (marker `latex`, registered in `pyproject.toml`;
`-m "not latex"` skips; skipped without latexmk/biber/engine/pdftotext)
compiles the standalone report and both fragments in a pdflatex+T1 host
and the table under xelatex and lualatex (DejaVu Serif, `pdftotext`
shows the text; the lualatex run covers the `\directlua` line); the
fixture has a quoted query, a `[`-row, `ĸ`, `CO₂`, a ligature. About
30–60 s in all.

- `scholar sessions export -f latex [--standalone|--no-standalone]` →
  `generate_latex_report(session, path, standalone=True)`. Always writes
  the sibling `.bib` (`build_report_bibtex`). Every `.bib` writer (this
  one, the synthesis's `_build_bibtex_content`, `search -f bibtex`)
  starts the file with one `@preamble{ "..." }` line defining
  `\scholarnonlatin` (`nonlatin_bib_preamble`, joined by
  `bibtex_file_text`) when an entry uses it (#243), so a user's own
  document can cite it; plain files are unchanged. The report's
  document then has both definitions (`\providecommand`: first wins,
  same text). Standalone output is byte-identical to before; the
  fragment wraps its body in a `refsection` so the host's
  `\printbibliography` is not polluted by the report's `\fullcite`s.
- `scholar llm synthesize -f latex [--standalone|--no-standalone]`: the
  document ends with the decision record (`build_review_decisions_latex`)
  as `\appendix` inside a `refsection`, after `\printbibliography`, so the
  References list exactly what the prose cites (discarded and uncited
  kept papers stay out). Standalone embeds the bib via
  `\begin{filecontents*}[overwrite]{<stem>.bib}` (`overwrite`: LaTeX
  otherwise keeps a stale file of that name); `--no-standalone` requires
  `--output`, writes `<stem>.bib` next to the `.tex` from
  `SynthesisResult.bibtex`, and is rejected for markdown.
- **Key-stability rule.** The theme cache stores LLM prose containing
  literal `\textcite{key}`s, so `_synthesis_key_space` orders the key
  space as included kept papers (original order), then remaining kept,
  then discarded, deduplicated by paper id; suffixes are assigned in
  iteration order, so kept keys never change.
- **One key scheme** (#85, `review.py`): `cite_key_base` = surname
  (`author_surname`: before the comma in `Smith, John`, else the last
  word) lower-cased and reduced to letters/digits (biber-safe; `O'Brien`
  → `obrien`, `Smith-Jones` → `smithjones`, `Müller` kept) + year or
  `nd`; `unknown` without author. `assign_cite_keys` suffixes clashes in
  list order from `a` (`smith2024`, `smith2024a`, …, `z`, `aa`), so a
  key depends only on the papers before it. Both `report_cite_keys`
  (keyed by `id(decision)`: a loaded session can hold one paper twice,
  and the report lists both) and the synthesis's
  `_generate_all_citation_keys` (keyed by paper id after
  `_unique_by_paper_id`) use it; the builders keep the `cite_key`
  resolver because the two look keys up by different identities.
  Changing the scheme requires a `SYNTHESIS_CACHE_VERSION` bump (now
  `v5`: cached prose cites keys literally). `search -f bibtex` and
  `bibtex+prov` use it too (#122, `cli._keyed_papers`: keys assigned
  once over all results in output order); this changed their keys
  for comma-form names, apostrophes and clashes. Their title, author
  and journal go through `escape_bibtex` like the export's `.bib`
  (#230; before, raw `& % $ # _` and symbols stopped pdfLaTeX); the
  layout, field order and DOI (verbatim in biblatex) are unchanged.
  Every field of both writers (`format_bibtex_entry`, the search
  formatter's `_format_paper`) goes through `review.bibtex_field(name,
  value)` (#304, review.nw `sec:bibtex-field-values`). `doi`/`url`
  (`BIBTEX_VERBATIM_FIELDS`, `bibtex_verbatim_value`): as given except
  an unpaired brace (`unpaired_braces`, counted as biber counts), a
  backslash before a brace or at the end, and C0 controls, which are
  percent-encoded (`%7B %7D %5C %00`..`%1F`); `read_bibtex_verbatim`
  is the exact inverse and is applied to the DOI by both readers
  (`_cited_bib_papers` for `--cited-from`, `_paper_from_entry` for
  `prov import`) and to the `% ID:` line (`bibtex+prov` and `prov
  export` write it encoded, `_recorded_id` decodes; a line break in a
  DOI split the line and lost the entry). Exactly invertible: a `%`
  followed by zero or more `25` and then a writer code (`7B 7D 5C
  00`..`1F`, `BIBTEX_BEFORE_CODE`) is written `%25`; the reader decodes
  a code and such a `%25` (`BIBTEX_VERBATIM_ESCAPE`), nothing else, so
  `%20` stays and the DOIs `10.5555/a%7Db` (written `a%257Db`) and
  `10.5555/a}b` (written `a%7Db`) stay two papers (table
  `tab:bibtex-verbatim-escapes`; inversion tested on a generated set
  with every code after 0 to 3 `%25`). The `%25` rule is for the DOI
  and the ID line only (`exact=`): the `url` field keeps round 2's
  encoding, so a URL's own `%7B` stays and its link is unchanged
  (checked with `pdfinfo -url`). Old `.bib` files (DOI holding the text
  `%7D`): `prov import` keeps the DOI as written when the block's `ID`
  is that DOI's id (`<<keep the DOI as written when the recorded id
  names it>>`); `--cited-from` tries the decoded DOI, then the DOI as
  written for entries not matched by DOI (`_cited_bib_papers` returns
  `as_written_dois`), naming those on stderr. Other provenance fields carry no
  line break (placeholders, dates, fields parsed line by line), except
  FOUND-VIA's query (#323, left open: a shell command). Text fields (`bibtex_text_value`): tab
  and line breaks -> space, other C0 dropped (biber 2.21 core-dumps on
  a NUL); then `escape_bibtex` (review.nw `sec:latex-titles`): a value
  with a backslash is read as LaTeX by pylatexenc (declared dependency
  since #304; bibtexparser 2 depends on it) and written as its Unicode
  text only if every command is on the allow-list: accents
  (`LATEX_ACCENTS`, not `\d \b \t`), letters (`LATEX_LETTERS`), font
  commands and switches, escaped specials, `\textendash
  \textemdash \ ` (`LATEX_TEXT_ALLOWED`), and inside math only the
  decoder's one-character no-argument symbol macros plus the math
  alphabets (`_math_allowed`). Anything else (`\cite \url \href
  \footnote \ref \input`, environments, unknown) -> literal. Also
  required: strict parse, every backslash starts an allowed macro, at
  most `LATEX_DECODE_MAX_CHARS` 4000 characters (longest real title
  2042) and `LATEX_DECODE_MAX_DEPTH` 8, every decoded character
  settable (`_settable`: Latin in T1 or mapped by the escaper; math
  alphanumerics U+1D400-1D7FF NFKC-folded), non-empty, and no exception
  (any `Exception` -> literal; `\href` raised IndexError, deep nesting
  RecursionError). Only command nodes are decoded; a math span without
  a command (`$x^2$`) stays as written. `^` is now escaped
  (`\textasciicircum{}`; outside math it stopped pdfLaTeX, checked on
  main; `escape_latex` always escaped it). Fuzz in the suite: every
  macro the decoder knows x 10 shapes, seeded, 5 s cap. `\{`/`\}`
  decode to `LatexBrace` ->
  `\textbraceleft{}`/`\textbraceright{}`. Anything else: every backslash
  -> `\textbackslash{}` (`BIBTEX_SPECIALS`), a still-escaped `\{`/`\}`
  -> brace commands. Printed (main / every backslash escaped / now):
  `Caf\'e` Café / Caf\'e / Café; `The \textit{wolf}` The *wolf* / The
  \textitwolf / The wolf; `{\em x}` *x* / \em x / x; `$\alpha$-stable`
  stops / $\alpha$-stable / α-stable; `x\y`, `C:\dir\new` stop / literal
  / literal (table `tab:latex-titles`). The report's `escape_latex`
  still prints titles as stored; ingest-time cleaning is #329. Values
  without a backslash never reach the parser (byte-identical). Then an
  unpaired brace -> the same commands. No output
  value holds a backslash before a brace or at its end (bibtexparser
  then loses the entry, biber does not). Paired braces stay. 3 of 6,594
  papers of two copied real sessions write differently (2 titles with
  a backslash, 1 with a control character); keys never change.
  bibtexparser 2.1's writer was tried and not used: it encloses values
  unchecked and doubles braces on a second write. Biber counts `\{`
  as a brace, so there is no BibTeX escape for an unpaired one.
  `TestAwkwardBibCompiles` (latex marker) compiles such a report.
  `prov import/export`
  match entries by `Paper.id`, never by key, so old `.bib` files still
  round-trip.
- `scholar sessions export -f table --lang en|sv --label L --track T
  --theme TAG=NAME -o base` writes `base.tex`, always a fragment: one
  row per *work* (`audit_work_key`: title and first-author surname
  (`author_surname`; a blank author gives an empty surname; DBLP's
  homonym number is stripped first, #233) reduced to case-folded
  letters and digits, year ignored; joined
  provider strings like `openalex; dblp` are split, mapped to codes and
  deduplicated, keeping only the names `decision_provider_evidence`
  supports (#191, see Data Models); the best copy gives the row its reason,
  category, confidence, status and order (#204, one sort key
  `audit_copy_rank` = (tier, order, unreviewed): tier 0 = a keep or
  discard of the *work* by a confirmed source, i.e. not
  `is_unreviewed`, topical criterion discards included; a discard of
  the *record* (an `AUDIT_VERSION_NOTES` note, or a criterion in
  `AUDIT_RECORD_CRITERIA` = `no-abstract`, `insufficient-information`;
  the criterion skips named `--theme`s), pending
  copies and unreviewed/unknown sources are tier 1; on equal order a
  confirmed copy wins, not the machine's copy and its confidence; a human
  "qualifies, excluded" discard thus beats an unreviewed "supports"
  keep and stays out of `--bearing-only`), but the notes of every copy
  are united, #196: `collect_audit_rows` passes the other copies'
  `audit_note_tags` (what each copy's own row shows as notes: note
  tags, plus stray tags under `--theme`; pending copies included, after
  the pending label; none for criterion discards, whose other tags are
  earlier criteria) to `audit_reason(..., also_notes=)`, best copy's
  first, then in decision order, each once; themes are not united; a
  lent version note makes the row a version row for the caption). The
  per-decision CSV is unaffected. The *last* category tag
  is the decision (`decide -t` appends while the status stays the
  same; a status change replaces the old category, #177); confidence is
  shown for unreviewed and human-confirmed LLM or agent rows, not for
  changed ones, and
  such a row without one shows `AUDIT_STRINGS[lang]["no_confidence"]`
  (`n/a`, `saknas`) because the caption promises a confidence. Whose
  confidence (#262): `audit_reason_and_confidence` also returns the
  origin when the label shows one (`audit_confidence_origin`: agent
  sources → `agent`, LLM and unknown sources → `llm`; `audit_reason`
  drops it), kept as `AuditRow.confidence_by`; `audit_confidence_sentence`
  picks `confidence_llm`/`confidence_agent`/`confidence_both` or none
  from the *listed* rows (both caption forms, `{confidence}`). Numbers
  (#262): `audit_number(value, strings, decimals=None)` with
  `AUDIT_STRINGS[lang]["decimal_mark"]`/`["group_separator"]` (en `.`
  `,`; sv `,` `\,`), grouping from 1000, for every confidence and every
  caption count (categories, extras, k of n queries/searches, semantic
  n); years, DOIs, ids, dates never. Column head `provider` is
  "Database"/"Databas". The
  escapers decode HTML entities, strip inline markup, repair
  cp1252/Latin-1 mojibake and turn `"` into `\textquotedbl{}` (babel
  shorthand). Titles are printed whole unless `--truncate-titles`
  (word boundary near 180 characters, ellipsis). An empty table logs a
  warning. The CSV's last column is `paper_id` for `decide --paper-id`. Tags split three ways: category tags (`supports-claim` …),
  note tags (`AUDIT_STRINGS[lang]["notes"]`: `recorded-not-cited`,
  `duplicate-record-of-cited-source`, `extended-tech-report`, …) and
  theme tags (the rest; with `--theme` given, only the listed tags).
  *Cited* = kept by a decision that is not `is_unreviewed` (source
  `human`, `llm_reviewed` or `agent_reviewed`) with a theme tag or no
  tags; otherwise the last category tag (`audit_category`), with the
  confidence for unreviewed LLM or agent rows; notes are appended in
  parentheses, note-only rows are "other". An LLM's or an agent's keep
  is a candidate, not a citation. That is the rule *without*
  `--cited-from FILE.bib` (repeatable, `-f table` only, else exit 2;
  #218, review.nw `sec:audit-cited-from`/`sec:audit-cited-entries`).
  With it, *cited* = the text cites the work, whoever decided: the CLI
  reads the files with bibtexparser 2 (`_cited_bib_papers`, NOT `prov
  import`'s line reader, which misses wrapped fields and bare years:
  322 of 529 titles in intropy's `ltnotes.bib`; `LatexDecodingMiddleware`
  plus the `names` functions called directly, since the name
  middlewares skip a field spelled `Author`; the DOI from the
  undecoded parse, since decoding turns `--` into an en dash; year
  from `year`, else
  `date`; a second reading surname first when it names another surname,
  so `Lopez Gallucci, N.` matches either stored form), skips entries
  without title and DOI and counts unparsable blocks (stderr), and
  `match_cited_entries(entries, session)` reuses the sessions check's
  lookup (`matching_entries` over `session_match_index`: DOI incl.
  version-link DOIs, else `audit_work_key` under `plausibly_same_work`;
  failing both, a second chance, #272: `match_loose_title` on
  `loose_title` (a trailing edition phrase `, 2nd edition`/`(3rd rev.
  ed.)`/`second edition`: digit ordinals of any size, word ordinals
  first-tenth, not after the/a/an, not when it leaves no word; and,
  on a side without authors only, a leading chapter number before a
  title with no lower-case and some upper-case letter) on both titles;
  `matched_by` `CHECK_BY_LOOSE_TITLE`; the bib's `edition` field, the
  entries' optional third element, read by `edition_number`, else its
  title's phrase (`entry_edition`), must equal an edition the session
  title names, one side alone matches, candidates naming the entry's
  edition drop those naming none; still `plausibly_same_work`,
  author-less records by title, else same surname; candidates that
  differ in (named edition, surname) → no match,
  `CitedEntry.ambiguous`, else all their work keys. An entry naming an
  edition that the first lookup found only by title on records naming
  no or another edition takes the records naming that edition
  (`same_edition=True`) when there are any; a DOI match stands;
  `audit_work_key` and `sessions check` deliberately unchanged)
  → `CitedEntry.works` (work keys) → `collect_audit_rows(...,
  cited_works=)` → `audit_reason(..., cited=True/False)` per copy
  (None = old rule). Copies are still ranked on the screening's order
  (`audit_reason(cited=None)`), so the citation never changes which
  copy gives the row. Kept/pending + cited → order 0 (`\emph{cited}` +
  theme/category, machine confidence kept; pending: ", pending,
  unclassified"); discarded + cited → own reason + note "cited in the
  text"; a keep not cited (any source) → category order, else "kept,
  not cited in the text" (`audit_uncited_keep`, `AuditRow.uncited`;
  own caption count `extra_uncited`, ahead of duplicates). Caption
  gets `cited_rule` before the databases (en/sv), also when nothing
  matched. stderr: match counts (DOI / title / [title without
  edition or chapter number, only when > 0] / not in session), the
  loosened entries (key: bib -> session title) and the ambiguous ones
  (nothing extra when all match as before), then
  `cited_text_disagreements` lists the excluded (any matched row
  discarded) and the not-held entries (key: short title); not in the
  caption. Without the option the output is byte-identical (checked on
  real-session copies). Order: cited (0), `supports-claim` (1),
  `qualifies-claim` (2), `adjacent-subtopic` (3),
  `off-topic-false-hit` (4), pending (5), other (6). The status wins
  over the category (#89): a *discarded* row whose category is
  `supports-claim`/`qualifies-claim` (`audit_excluded`) is never in
  orders 0-2; it sorts as other (6) with reason "<category>, excluded"
  and the caption counts it apart (`extra_excluded`), so
  `--bearing-only` never lists a rejected hit. The other rows (6) are
  counted by kind (#169): rows with a version note
  (`AUDIT_VERSION_NOTES`) as "duplicates or other versions of cited
  sources", discards under an exclusion criterion
  (`audit_exclusion_criterion`: a discard with no category and no note
  tag, its last tag that is not a `--theme`, which the row shows too; e.g. `no-abstract`) per
  criterion as "excluded by the criterion <tag>" (`no-abstract`:
  "excluded for lack of an abstract", `AUDIT_STRINGS[lang]["criteria"]`),
  the rest as "other hits" (all localised). Criteria are the review's own labels, so
  there is no fixed list. The caption never
  names the session (it is a `%` comment in the fragment) and ends with
  a full-name-first "Databases searched:" ("Sökta databaser:", #262)
  sentence built from the providers
  the session searched (search records that answered at least once,
  zero hits included, plus the rows; rows only for old sessions). A
  database known only from records without an outcome and from no row
  is listed after it, "Also queried, with no recorded outcome: DBLP."
  (`AUDIT_STRINGS[lang]["unrecorded"]`, #188; the shortfall tuple's
  7th count); one
  whose `SearchRecord`s carry errors is marked
  "failed for k of n queries" / "incomplete for k of n queries"
  (localised), and one that failed every query outright is not
  named. Retired search records (#275, review.nw `sec:audit-retired`)
  are left out of the databases and dates sentences and the shortfall
  notes (`build_audit_table_latex` passes `current_records`);
  `audit_retired_sentence` then adds "{n} earlier searches that have
  since been retired are not counted here." / sv "{n} tidigare
  sökningar som sedan har strukits räknas inte här." (singular
  `retired_one`; `audit_number`), and a row code known only from
  retired records (`retired_only_codes`) is not named among the
  databases but in that sentence, code first (`audit_coded_names`):
  "; rows coded WoS (Web of Science) were found only through them"
  (sv "; rader märkta ... hittades bara genom dem"; singular "it" /
  "den"). Semantic (ranked) codes are never named there; the semantic
  sentence appears for a current semantic record or an OA-sem row and
  counts from all semantic records, retired too. Rows are untouched. Without
  retired records the caption is byte-identical. `--bearing-only` lists only orders 0-2 and states the other
  counts in the caption: without extras "the A adjacent and B false
  hits" (`unlisted_pair`), with extras each group with its noun and
  `audit_joined_list` putting "and"/"och" before the last ("the A
  adjacent hits, the B false hits, 2 unclassified and 1 ..."); the
  `extra_*` strings have no leading comma (the full caption adds ", ").
  `all` stays csv + latex.
- Double screen (#253 E): the report's screening section ends with a
  "Double screening" paragraph, the `llm synthesize` summary gets a row
  per screener pair, and the audit caption a few sentences (en/sv) before
  "Databases searched", all only when the session has screenings; see
  "Double screen in the documents".
- The TUI's `prompt_for_report` keeps the standalone default.
