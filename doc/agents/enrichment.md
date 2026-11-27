# Full texts, abstracts and enrichment

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## PDF Cache and `scholar pdf import` (#296)

`pdf.py` caches PDFs in `<cache dir>/pdfs/<sha256(url)[:16]>.pdf`
(`get_cached_pdf_path`); a DOI download resolves candidate URLs first
and caches under whichever delivered.
- **Readable or absent** (pdf.nw `sec:pdf-import-check`): a cached file
  is used only if PDFium (the engine `extract_pdf_pages` uses) opens it
  and finds a page (`usable_cached_pdf` → `pdf_file_problem(path)`);
  otherwise it is ignored with a WARNING and downloaded again (older
  versions left truncated files that were returned as hits forever).
  Downloads stream to a `temp_beside` file (`.<name>.<rand>.tmp`) and
  `os.replace` into place, so a broken response or Ctrl-C leaves
  nothing. The temp file is checked with `pdf_file_problem` first: a
  body that is no readable PDF (encrypted, HTML served as PDF) is not
  cached, the download fails with the reason, and the failure is
  remembered for the process (`UNREADABLE_DOWNLOADS`, keyed by cache
  path, memory only; other failures are not remembered). `get_pdf`
  peeks with `usable_cached_pdf(..., warn=False)` so "Ignoring the
  cached PDF" is logged once. `pdf clear` deletes `.*.tmp` files in
  `pdfs/` older than an hour (`STALE_TEMP_SECONDS`, by mtime, under the
  lock); `pdf info` counts them (`stale_temporary_files`). `find_quote_candidates` turns a `PdfiumError` into `[]`, or
  with `raise_errors=True` (what `pdf quote` passes) into a one-line
  `PDFUnreadableError` (a `PDFDownloadError`). **Change:** `pdf quote`
  now exits 1 with "Download failed: ..." when no PDF could be had; it
  used to print "No candidate passages found." and exit 0, but a failed
  download is not an empty result.
- **Import**: where a publisher answers with a bot check (scholar stops
  there, see Network), `scholar pdf import FILE (--url URL | --doi DOI)
  [--from TEXT] [--replace]` (FILE takes the positional slot of
  `open`/`quote`'s URL, their usage unchanged) → `import_pdf`
  (`sec:pdf-import`). The file is copied to a temp file in `pdfs/`,
  checked and hashed there (`file_sha256` = `hashlib.file_digest`;
  PDFium opens the path; nothing held in memory), then renamed in.
  Refusals exit 2: no file/key, both keys, not a PDF (HTML named,
  `looks_like_html`; an encrypted PDF, PDFium's `FPDF_ERR_PASSWORD`:
  "the PDF is encrypted; save an unencrypted copy"), bad DOI, other
  readable content cached without `--replace` (says "a downloaded" or
  "an imported" PDF and its sha256). An unreadable cached copy is
  replaced without `--replace`. A PDF with no text on any page is
  imported with a warning (`pdf_has_text`).
- **Key**: by URL, the download's key. By DOI, the key of
  `https://doi.org/<normalized_pdf_doi(doi)>` (`Paper._normalize_doi`
  plus trailing `.,;:'"` stripped; `get_cached_doi_pdf_path`, no index
  file); a `doi.org` `--url` counts as that DOI; the output says "Stored
  under DOI …". `download_doi_pdf` uses that file before resolving;
  `get_pdf(paper)` checks the DOI import first, then a cached `pdf_url`
  download, before any request (a non-string or blank `doi` counts as
  none), so `pdf quote <doi or doi.org URL>` and the full-text
  classification use it offline.
- **Record**: `<hash>.import.json` beside the copy (`import_record_path`):
  `sha256`, `size`, `imported_at` (UTC), `file_name` (base name only),
  `from`, `url`, `doi` as given, `stored_doi`. Written (atomically)
  before the PDF is renamed in. A PDF counts as imported only when its
  record's `sha256` is the file's (`import_record_of`); other records
  are orphans (`orphaned_import_records`): `pdf info` counts them,
  `clear` and an import of that key delete them.
- **Lock**: import and clear share one directory lock,
  `pdfs/.import.lock` (`pdf_cache_lock`); no per-PDF lock files.
  A download takes it only around its final rename: if the key then
  holds an import (record matches), the import stays and the download
  is discarded (one INFO line), so a hand-fetched file is never
  replaced by an automatic one (threads test, both orders).
- **Overwrite**: same content → no-op ("unchanged"), or adds the record
  to a same-content download ("recorded").
- **Clear/info**: `clear_pdf_cache` keeps imports unless
  `include_imported` (`pdf clear --include-imported`); `pdf clear` says
  how many it kept. `get_pdf_cache_info` adds `imported`,
  `imported_bytes`, `orphaned_records`; `pdf info` shows them and
  `--list-imported` lists `list_imported_pdfs()`. `scholar cache clear`
  deletes only top-level `*.pkl` files and never touches `pdfs/`
  (tested).
- **Fetch** (#345, pdf.nw `sec:pdf-fetch`/`sec:pdf-text`, cli.nw
  `sec:pdf-fetch-cli`): `scholar pdf fetch [SOURCE ...] [--text] [-f
  tsv|json]` → `fetch_pdf(source, text=, progress_callback=)` →
  `PDFFetch(source, path, error, text)`, never raises for the source:
  `source_problem` (not `extract_doi` and not an http(s) URL with a
  host → row error "neither a DOI nor an http or https URL", no
  request), else `get_pdf` (same DOI resolution, import first, route as
  open/quote); `PDFDownloadError` → `one_line` (lines joined by "; "),
  `OSError` → its strerror. No viewer. The `pdf` command's positional is
  now `arguments: Optional[list[str]]` (metavar URL); `<<take the URL
  from the positional arguments>>` sets `url = arguments[0]`, and any
  other action given a second one prints Click's "Error: Got unexpected
  extra argument (...)" on stderr and exits 2 (a `click.UsageError`
  raised in the command exited 1). No argument: stdin lines
  (`fetch_sources_from_stdin`: blank and `#` lines dropped; a terminal
  is not read); none at all → exit 2, as is a `-f` other than tsv/json
  (checked first). Rows in input order, `csv.writer` tab, `\n`, no
  header, flushed per source: source, path or `-`, `OK` | `ERROR:
  reason`, with `--text` the text path or `-` (`fetch_row`); `-f json`
  objects `source, path|null, status OK|ERROR, error|null[, text]`
  (`fetch_object`), printed at the end. Exit 1 if any row failed (a
  text not written counts, path kept). Progress on stderr.
- **Text** (`--text`): `write_pdf_text(pdf)` → `<hash>.txt`
  (`pdf_text_path`), PDFium via `extract_pdf_pages` (not `pdftotext`,
  which the old skill script ran: not a dependency), `\r\n`/`\r` → `\n`,
  each page + `PAGE_END` "\n\f" (pdftotext's page break). Kept when not
  older than the PDF (`text_is_current`, mtime_ns >=); else extracted
  outside the lock and written (`atomic_write_text`) under
  `pdf_cache_lock` only if `file_identity(pdf)` is unchanged, up to
  `TEXT_ATTEMPTS` 3, then `PDFTextError`. `clear_pdf_cache` deletes
  `orphaned_texts()` (no `.pdf` beside) after its deletions, which
  takes the deleted PDFs' texts too; an imported PDF kept keeps its
  text; `get_pdf_cache_info` adds
  `text_files`, `text_bytes`, `orphaned_texts` (`pdf info` rows "Text
  files", "Orphaned text files" when > 0); `import_pdf` deletes the
  text under the lock before renaming a new file in ("unchanged" and
  "recorded" keep it). A download that replaces an unusable cached file
  deletes the old text under the lock too.
- Test PDFs are written by hand (`make_pdf` in pdf.nw, `make_cli_pdf` in
  cli.nw: optional text line, optional `/Encrypt`); in a code chunk
  every `<<` of PDF syntax must be written `@<<`.

## Open-Access Lookup (Unpaywall)

`unpaywall.py` mirrors `crossref.py`: a cached per-DOI lookup, **not** a
search provider (Unpaywall's search endpoint is title-only and its OA data is
what OpenAlex already serves). `fetch_oa(doi)` returns
`{is_oa, oa_status, oa_url, pdf_url, host_type, version, license}` or
`None` (undetermined: no DOI, no email, 404, 429, error);
`annotate_paper(paper)` writes `Paper.oa_status`/`oa_url` and fills a
missing `pdf_url` (never overwrites one); `resolve_pdf_url(doi)` serves
`pdf.resolve_doi_unpaywall`. `enrich.enrich_paper` calls `annotate_paper`
whenever `pdf_url` is among the requested fields, so `scholar enrich`,
`search --enrich`, and the TUI all get it; `scholar enrich` prints an
`Open access: N of M checked papers (K with PDF link)` tally (or a
`set SCHOLAR_EMAIL` hint). `Paper.is_open_access` (checked status, else
`bool(pdf_url)`) backs the client-side `--open-access` filter.

`scholar enrich` flags (#137): `--pending-only` restricts everything
(metadata, Unpaywall, preprint adoption, Crossref check, tally) to
decisions whose stored status is pending; decided papers are saved
unchanged. `--fields abstract,pdf_url,keywords` (the default) is checked
against `enrich.ENRICHMENT_FIELD_NAMES` (unknown name: exit 2);
leaving out `pdf_url` also skips Unpaywall and the preprint fallback
(`--fields abstract` is the cheap run). The Crossref check always runs.

Lookup tally (#259, enrich.nw `sec:enrich-lookup-outcomes`, cli.nw
`sec:enrich-lookup-tally`): `enrich_paper(..., outcome=LookupOutcome())`
/ `enrich_papers(..., outcomes=[])` (optional; TUI and `search
--enrich` pass none, return types unchanged) record per paper the
providers asked, the failed ones with reasons, the declined ones
(`LookupOutcome.declined`, not in `asked`) and the Unpaywall failure.
`scholar enrich` collects them per chunk and, when `abstract`
is in `--fields`, ends (also on the exit-130 interrupt path, over the
saved papers) with `abstract_tally_lines`: "Still without an abstract:
N of M papers." then answered by every database asked (every provider
that was asked answered; declined ones do not count) / without a DOI /
"with a DOI that no database was asked about: each one declined or was
unavailable" / one info line per declined `provider not asked: reason
(N papers)`, no hint / failed lookups per `provider: reason (count)`
plus "Run again to retry the failed lookups." only when something
failed. After the `Open access:` line, `open_access_tally_lines` splits
unknown statuses into without a DOI / not in Unpaywall / failed (per
reason). Existing lines unchanged. Nothing is stored in the session
(the outcome is the run's). Stand-ins for `enrich_papers` must accept
`outcomes=` (or `**kwargs`).

**Batched OpenAlex DOI lookups.** `OpenAlexProvider.prefetch_dois(dois)`
(`sec:openalex-doi-batch`) fills the `("doi", CACHE_VERSION, doi)` cache
that `get_paper_by_doi` reads, 50 DOIs per request via
`pyalex.Works().filter_or(doi=[...]).get(per_page=100)` (OR with `|`,
documented max 100 values). It caches a DOI only when exactly one work
matches (never misses: the singleton lookup caches a real 404), keys by
each caller spelling grouped under `Paper._normalize_doi`, skips DOIs
with `,|+` or whitespace, and stops quietly at the first failure.
`enrich_papers` calls it before its loop when `openalex` is in the
provider order, for the DOIs (or derived arXiv DOIs) of papers that
`needs_enrichment`. S2 comes first in `ENRICHMENT_PROVIDERS` and is
paced at 1 request / 3 s without a key, so
`--enrich-providers openalex,s2,...` is the fast path.

## Abstracts from Crossref and Europe PMC (#260)

`ENRICHMENT_PROVIDERS` = s2, arxiv, openalex, ieee, wos, `crossref`,
`europepmc`, scopus: the two per-DOI abstract services (not registered
providers) come before Scopus, whose weekly metered quota they save;
Scopus stays last. `enrich.enrichment_source(name)` resolves a name to
`abstract_source(name)` (the module's shared client,
`<module>.enrichment_source()`) for the names in
`ABSTRACT_SOURCE_FIELDS`, else `get_provider`. Both clients have
`get_paper_by_doi` (a `Paper` with only DOI, abstract and
`sources=[name]`) and `last_lookup_error` (Europe PMC also
`last_lookup_declined`, for a DOI holding `"`), so the loop, the merge,
`Paper.sources` and the #259 tally treat them like any database. The
loop asks them only while the abstract is requested and still missing
(`<<skip an abstract service with nothing to fill>>`): a present
(hand-given, #258) abstract is never asked about; `--fields` without
`abstract` asks neither. `--enrich-providers` is validated
(`cli.parse_enrich_providers`, exit 2, before loading/searching; an
empty value is an error too; `search` checks it even without
`--enrich`; both help texts say so) against
`enrich.enrichment_source_names()` = registered providers with
`get_paper_by_doi` + the two services. Test files with enrichment
switch them off with `scholar.enrich.abstract_source` → None
(test_enrich autouse fixture, `TestEnrichLookupTally._invoke`).
- **Shared reading** `utils.markup_to_text` (utils.nw
  `sec:markup-to-text`): keeps the MathML version of a JATS
  `<alternatives>`, JATS/HTML block elements (p, sec, title, break, br,
  h1-h6, li, td, ...; any namespace prefix) → space, other tags (`<`
  directly followed by a letter) removed, entities decoded after, white
  space collapsed. Limit: plain text like `a<b and c>d` loses its
  middle. Both services return `None`, never `""`, for an abstract
  without text.
- **No double cleaning**: `enrich_paper` still cleans the whole paper
  at the end (held title/venue/abstract included, so `enrich` repairs
  old sessions' entities and mojibake), via
  `clean_paper_text_except(result, plain_abstract)`: the one exception
  is an abstract Crossref or Europe PMC supplied in that very call,
  already plain (`clean_metadata_text` is not idempotent: it decodes
  again, then strips `<i>`, so a JATS `&lt;i&gt;` would be lost).
- **Crossref** (`crossref.nw` `sec:crossref-abstract`): no request of
  its own. `_fetch_work` (shared by `fetch_currency` and
  `fetch_abstract`) caches both the currency result and the raw JATS
  abstract, a side entry `abstract_cache_key(doi)` = `("abstract",
  doi)` (str or None; a 404 caches None in both). Chosen over bumping
  `CURRENCY_CACHE_VERSION`, which would re-fetch every DOI's currency on
  the next enrich; an old currency entry without the side entry costs
  one request only when its abstract is asked for. `jats_to_text` =
  drop a leading `<title>Abstract</title>` (also as the first `<sec>`'s
  title) + `markup_to_text`. Docs (read 2026-11-20): the REST API page
  (abstracts exposed; "Some abstracts ... may be subject to copyright
  by publishers or authors"), the abstracts best-practice page (JATS),
  swagger `abstract: string`.
- **Crossref pools (#270)**: documented limits (access-and-authentication
  page, updated 2025-10-16): public 5/s, concurrency 1; polite (mailto)
  10/s, concurrency 3; announced in `x-rate-limit-limit` /
  `x-rate-limit-interval` (a recorded anonymous answer of 2026-11-20:
  5, 1s, concurrency 1). `CrossrefClient.LIMITS` 5/s,
  `POLITE_LIMITS` 10/s, chosen per request by `_acquire()` from
  `mailto` (as S2's keyed limits). The limiter does not read the
  `x-rate-limit-*` headers (its sync knows only
  `X-RateLimit-Remaining/Reset`).
- **429s reach the limiter**: Crossref's and Europe PMC's sessions no
  longer list 429 in urllib3's `Retry` `status_forcelist` (it retried
  out of the limiter's sight and ended in `RetryError`, so no cooldown):
  one 429 → `record_response` cooldown → later lookups refused without
  a request, tallied as failed (loopback tests). Unpaywall's session
  likewise (one 429 → cooldown → the next lookup refused without a
  request, a failed open-access lookup).
- **Europe PMC** (`europepmc.nw`, `EuropePMCClient`, cache
  `europepmc.pkl`, limiter `europepmc`): `GET
  https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"<doi>"
  &resultType=core&format=json&pageSize=5`; `abstract_for_doi` returns
  the raw `abstractText` of the first result whose `doi` matches
  (case-folded) and whose abstract leaves text, passing over the
  others; the cache holds it raw, read with `markup_to_text` on return;
  no result list → failure (not cached). The optional `email` parameter
  (registers the address for news) is never sent. Source: the API's
  OpenAPI document `.../rest/v3/api-docs` (records carry a three-letter
  source code: MED, PMC, PPR, ...; no coverage claim made); the
  europepmc.org pages were behind a bot challenge (2026-11-20, not
  read). Rate 5/s is scholar's choice (a forum reply says 10/s or
  500/min). PubMed E-utilities are not added.
- `cache clear --provider europepmc`, `providers limits` (imports
  europepmc), conftest `fresh_rate_limiters` imports it too (#131).

## Abstracts stored as paragraphs (#290)

WoS Expanded gives a multi-paragraph abstract as a list (XML `<p>`s);
the provider joins it since 311e42e (2026-03-03), but older sessions
and pickled WoS cache entries can hold the list. `utils.join_paragraphs`
(utils.nw `sec:abstract-paragraphs`): list/tuple → non-empty parts as
strings joined by `"\n\n"` (`PARAGRAPH_JOINER`, as the provider), empty
→ None, anything else unchanged. Applied by the WoS provider, by
`Paper.__post_init__` (sessions repaired on load, saved back as text,
like `normalize_venue`) and by `clean_paper_text` (unpickled cache
hits skip `__post_init__`). Title/venue/identifiers: not changed (title
feeds the DOI-less id); the calibration tool counts any non-text field.

## Doubtful Abstracts (#287)

A service's abstract field can hold a disclosure statement, a keywords
line, a table fragment, ... Flag, never drop.
- **Check** `scholar.abstract_check.doubtful_abstract(text) -> reason |
  None` (enrich.nw `sec:doubtful-abstracts`; its own module, tangled
  from enrich.nw, stdlib + `scholar.utils` only, so `sessions show` and
  the report do not import providers or the Crossref cache). Order:
  (1) `is_table_of_contents` (front-matter heading at the start, not
  followed by a lower-case word other than "by <Capitalised>", and "Chapter 1"/"Part I"/"1. X" within
  `FRONT_MATTER_CHARS` = 300) → "table of contents"; (2) `DOUBTFUL_OPENINGS`: per kind (the reason
  string) a few regexes matched only at the START of the text, after
  `TEXT_START` (white space, inline tags, footnote marks/quotes, a
  leading "Abstract"; `[` kept); (3) `first_sentence_statement`: the
  first sentence (≤ 300 chars) whose first "is/are (word) available"
  is within `AVAILABLE_WITHIN` = 120 chars, no `;` before it, and whose
  part before "available" names `SUPPLEMENTARY_MATERIAL`
  (supplementary/supplemental material(s)/information/data/file(s)/
  table(s)/figure(s)/appendix/appendices/text(s), or supporting
  information) → supplementary-material note, or names
  `AVAILABLE_THINGS` (data, dataset(s), code, material(s),
  transcript(s), script(s), software, questionnaire(s), protocol(s))
  with "available (up)on (word) request" → data-availability statement
  (the word "supplementary" alone, or a repository alone, is not a
  sign); (4) a statement from (2)/(3) is
  NOT doubtful when `abstract_follows`: later an `ABSTRACT_HEADING`
  (Abstract, Background, Objective(s), Purpose, Introduction, Aim(s),
  Methods; capitalised or caps, after space/punctuation, then `:`/`.`)
  with ≥ 100 chars after it (not for table/reference fragments,
  `NOT_RESCUED`; the TOC returns before); (5) `TOO_SHORT` = "fewer than
  100 characters" (`MIN_ABSTRACT_CHARS`, after collapsing white space;
  `weighed_length`: East Asian wide/fullwidth characters, W or F, count
  `WIDE_CHAR_WEIGHT` = 2, so short complete CJK abstracts pass).
  Kinds of (2): conflict-of-interest statement (incl. disclosure prose:
  Dr/Prof/Professor + 1-3 capitalised names, or "the author(s)", +
  has received honoraria/consulting|speaker|personal fees/grants/
  research support, serves as … editor, is an employee of, reports
  grants/fees), data-availability statement, funding statement ("This
  work was supported/funded by" unless the sentence goes on with "and"
  + one of `STUDY_VERBS` within 200 chars),
  acknowledgements (heading), opens with thanks ("We (would like to)
  thank", "The authors are grateful"), keywords line, author address or
  correspondence ("Correspondence to" needs `:` or a capitalised name;
  a bare "Corresponding author(s)" needs a delimiter),
  supplementary-material note, table fragment ("Table N" not followed
  by shows/lists/presents/summarises/reports/compares/gives/contains),
  reference-list fragment ("References"/"Bibliography" heading, or
  "[1] " with "[2]" within `REFERENCE_ENTRY_CHARS` = 200, so numbered
  paragraphs are not lists). A word that can be a topic ("Disclosure of
  HIV status", "Funding agencies", "Correspondence analysis",
  "Email-based", "Table tennis") is a heading only with `heading()`
  evidence: a delimiter (`: .` en/em dash, ` - `) not followed by a
  lower-case "a"/"an" ("Funding: a key determinant ..." is a topic),
  the end of the text, or a capitalised run-in word from a short
  case-sensitive list. A list
  or tuple is judged joined (`join_paragraphs`); other non-text values
  are not judged. All patterns and thresholds are scholar's own choice.
  `python -m scholar.abstract_check FILE.json ...` (reads the JSON
  only, never the data dir; dedups by paper id; skips hand-given
  abstracts; prints counts by reason, "Stored values that are not text:
  FIELD N" over `TEXT_FIELDS`, and each flagged text's first 80
  characters). Calibration (developer's sessions, scholar's own
  measurements, enrich.nw `sec:abstract-check-calibration`, shapes only,
  no real texts in the repo): first run 2026-11-20, 147,108 abstracts,
  667 flagged (0.45 %), 649 by the floor; its false positives (a
  disclosure or keywords line before a real abstract, numbered-paragraph
  articles) led to (4) and the "[2]" rule. Second run 2026-11-20:
  145,772 judged (36,981 papers without an abstract), 729 doubtful
  (0.50 %): 648 floor, 68 TOC, 6 thanks, 2 COI, 2 supplementary, 1
  keywords, 1 funding, 1 acknowledgements heading; 22 list abstracts.
  The review of PR #294 then narrowed (3), the heading delimiter, the
  table/front-matter/funding/correspondence openings and the floor (CJK)
  for real topics it found. Third run 2026-11-20: 145,772 judged, 724
  doubtful (0.50 %): 647 floor, 65 TOC, 6 thanks, 2 COI, 1
  supplementary, 1 keywords, 1 funding, 1 acknowledgements heading; 22
  list abstracts; against run 2 five dropped, none added (a complete
  Chinese abstract, a supplemental-content sentence before a real
  abstract, and three true TOCs opening "Foreword by <Name>"). After
  it, a front-matter word followed by "by" + a capitalised name is a
  heading again ("Foreword by the editors ... argues" stays prose). Not covered: free-form statements, an
  article's opening paragraph, non-English boilerplate. 10,000
  abstracts of ~1,000 characters take about 0.2 s (test allows 1 s).
- **enrich** (`sec:replace-doubtful-abstract`): `needs_enrichment(p,
  fields, judge_abstract=False)`, `enrich_paper(..., judge_abstract=
  False)`, `enrich_papers(..., judge_abstracts=[bool per paper])`.
  Judging is opt-in: only `scholar enrich` turns it on, per paper
  `not review.hand_given_abstract(d)` (a hand-given abstract, #258, is
  never judged or replaced); TUI and `search --enrich` unchanged. When
  judged, a doubtful abstract counts as missing (further sources incl.
  Crossref/Europe PMC are asked, OpenAlex prefetch includes it); the
  first non-doubtful abstract from a later source replaces it (merge
  into `replace(result, abstract=None)`); else the doubtful text stays
  (a later doubtful text never replaces it). A non-doubtful abstract is
  never replaced. `LookupOutcome` gained `abstract_from` (source whose
  abstract the call stored; dropped when a preprint adoption replaced
  the abstract), `doubtful`, `doubtful_text`, `doubtful_from` (None =
  held before the call), `abstract_adopted` (a preprint adoption
  replaced the abstract) and properties `doubtful_replaced`,
  `doubtful_ending` ("replaced" / "adopted" / "kept").
  `LookupTally.doubtful` counts `(reason, ending)`;
  `doubtful_tally_lines` prints after the abstract tally (also on the
  interrupt path): "Doubtful abstracts (...): N papers." then per
  reason "k replaced by a later source's abstract, j replaced by an
  adopted preprint's abstract, m kept, no better one found"
  (`DOUBTFUL_ENDINGS`), and `DOUBTFUL_KEPT_HINT` (sessions show,
  `sessions set-abstract --replace`) when any was kept. Known costs
  (prose and `enrich` help): a kept doubtful abstract is looked up
  again by every source on every run (WoS/Scopus DOI lookups are not
  cached), as a paper without an abstract is; no cache added. A DOI
  lookup returning another work can replace a doubtful abstract with
  that work's text; `replaced.text` keeps the old text and the source
  is named.
- **Origin** (review.nw `sec:fetched-abstract`):
  `ReviewDecision.abstract_fetched` = `[{"at", "from", "chars",
  "digest", "replaced"}]` (`replaced` = `{"text", "reason", "from"}`
  of the doubtful text it replaced), written by `scholar enrich` per
  chunk via `note_fetched_abstract(decision, source, at, replaced)`.
  On the decision like `abstract_set` (no paper-merge rule): saved only
  when non-empty, old files `[]`, append copy, united by
  `merge_concurrent_changes` and by both folds, not in
  `decision_state`. The stored abstract itself is not copied into the
  record (would double the file), only `chars` and `digest`; the
  replaced doubtful text, when there is one, is kept in full in
  `replaced.text`. `abstract_digest` (sha256[:16]) lets
  `fetched_abstract_source(d)` name the source only while the paper
  still holds that text; old data
  and changed abstracts show nothing. Search ingest records no source
  (the merged paper's abstract provider is unknown there).
- **Display**: `review.abstract_doubt(d)` (None for a hand-given
  abstract) is computed when shown, nothing stored. `sessions show`:
  "(doubtful abstract: REASON[, from SOURCE])" after the title
  (`cli.doubtful_mark`), a "Doubtful abstracts: N papers have ...;
  replace one with `scholar sessions set-abstract --replace`." line
  after the summary (both built as `Text` through `paper_line_notes` /
  `print_show_line`, stored strings plain, #286), JSON
  `abstract_doubtful` and `abstract_fetched_from` (each only when set;
  not `abstract_from`, the CSV's column for where a hand-given abstract
  was found); help text names `set-abstract --replace`.
  Report: `doubtful_abstracts_sentence` after the hand-abstract
  sentence (papers counted). Audit table and decisions unchanged (the
  review's `no-abstract` criterion is the reviewer's).

## Currency / Retraction Checks

`crossref.py` checks whether a paper has been retracted, corrected, or
superseded, using Crossref's `updated-by` (Retraction-Watch-backed) and
`relation` metadata. Results are cached per DOI via the shared cache layer.

- `Paper.updated_by` / `Paper.newer_versions` hold the findings;
  `None` means "never checked", `[]` means "checked, clean".
- `Paper.is_retracted` / `is_corrected` / `is_superseded` are convenience
  predicates; `crossref.currency_status(paper)` reduces these to one word
  (`retracted`/`corrected`/`superseded`/`preprint`/`ok`/`unknown`).
  `preprint` means a deliberately adopted preprint (see versions-copies-renames.md) whose only
  "newer version" is the recorded published DOI — info, not a warning.
- `scholar verify "<session>"` reports per-paper status (with `--json`);
  `scholar enrich "<session>"` warns on issues as a side effect. Both
  persist the findings back to the session.
- A failed check (any `fetch_currency` failure) leaves the paper
  unchanged, so `updated_by` stays None ("never checked"). Both commands
  count failures per reason (#259, crossref.nw
  `sec:crossref-check-failures`): `noting_failures(counter, callback)`
  wraps `annotate_papers`' progress callback (read right after each
  lookup; `annotate_papers`' signature is unchanged, so stand-ins keep
  working) and `check_failure_lines` prints "Crossref check failed for
  N papers (not checked in this run):" (true also for a paper whose
  earlier result is kept after a failed re-check) + `crossref: reason
  (n)` + `network.RUN_AGAIN_HINT`; enrich after its currency line,
  verify on stderr (JSON stays pure). The run never aborts.
