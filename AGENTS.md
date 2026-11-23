# Scholar CLI - Agent Reference

## Project Overview

Scholar is a CLI tool for searching academic papers across multiple providers (Semantic Scholar, OpenAlex, DBLP, Web of Science, IEEE Xplore, Scopus, arXiv, HAL, and — via OpenAlex source pinning — the preprint servers SSRN, bioRxiv, medRxiv, ChemRxiv, Research Square, Preprints.org, and IACR Cryptology ePrint), plus OpenAlex's semantic search (`openalex-semantic`) as a check on keyword searches.

## Architecture

### Protocol-Based Provider System

Providers implement the `SearchProvider` protocol (structural typing, not inheritance):

```python
class SearchProvider(Protocol):
    name: str
    def search(self, query: str, limit: int = 100) -> list[Paper]: ...
```

Providers self-register via `register_provider()` at module load time.

### Key Files

| File | Purpose |
|------|---------|
| `src/scholar/providers.py` | All provider implementations |
| `src/scholar/providers.nw` | Literate programming source for providers |
| `src/scholar/scholar.py` | Core data models (Paper, SearchResult) |
| `src/scholar/crossref.py` | Crossref currency/retraction checks |
| `src/scholar/crossref.nw` | Literate source for currency checks |
| `src/scholar/unpaywall.py` | Unpaywall open-access lookup (per DOI) |
| `src/scholar/unpaywall.nw` | Literate source for open-access lookup |
| `src/scholar/europepmc.py` | Europe PMC abstract lookup (per DOI) |
| `src/scholar/europepmc.nw` | Literate source for the Europe PMC lookup |
| `src/scholar/preprint.py` | Preprint fallback (adopt a preprint when no PDF found) |
| `src/scholar/preprint.nw` | Literate source for the preprint fallback |
| `src/scholar/ratelimit.py` | Persistent cross-session rate-limit/quota tracking |
| `src/scholar/ratelimit.nw` | Literate source for rate-limit tracking |
| `src/scholar/network.py` | Proxy route and User-Agent for every request |
| `src/scholar/network.nw` | Literate source for the network settings |
| `src/scholar/agreement.py` | Agreement and conflicts between screeners (#253) |
| `src/scholar/agreement.nw` | Literate source for agreement and conflicts |
| `src/scholar/cli.py` | CLI commands and output formatters |
| `src/scholar/cli.nw` | Literate programming source for CLI |
| `src/scholar/tutorials/*.nw` | Literate sources of the interactive tutorials (tangle to `*.md`, weave to chapters) |

### Data Models

**Paper** (`scholar.py:14-39`):
- `title`, `authors`, `year`, `doi`, `abstract`, `venue`, `url`, `source`
- `affiliations`: institution names (Scopus COMPLETE view, OpenAlex). Merges
  like `authors` (kept, else filled), **not** unioned like `keywords`: two
  providers' lists are two spellings of one fact. Names only, no countries.
- `venue` is always `str | None`: `__post_init__` joins a list/tuple
  (DBLP proceedings) with `"; "` via `normalize_venue`, which also
  repairs sessions stored with a list on load. Consumers need no guard.

**SearchResult** (`scholar.py:42-67`):
- `query`, `provider`, `timestamp`, `papers`, `filters`, `limit`
- `error` (`None` = provider answered; else the reason it failed) and
  `retries` (repeats before the answer was accepted). `merge` prefixes
  each error with its provider and sums retries. Never show a failed
  result as 0: format counts with `hits_label(hits, error, retries)`
  ("12", "failed (reason)", "25, incomplete (reason)").
- Session `SearchRecord`s store the same outcome (`hits`, `error`,
  `retries`; old records load as `hits=None`). A record's identity is
  `SearchRecord.key` = `(query, provider, filters_key(filters))` (#140):
  the same query with other filters (`--year`, `--in`, ...) is a record
  of its own, the limit is not part of the key. `filters_key`
  (`scholar.py`) is `SearchFilters(**stored).cache_key()` plus any
  unknown keys as sorted JSON; `""` for no filters. A failed re-run of
  the same key does not overwrite an earlier answered record. The audit
  caption counts each record as one query (two filter sets = two
  queries, on purpose). Legacy records (`SearchRecord.is_legacy`:
  `filters` and `limit` both `None`; written before #61, which stored
  both together, while every search since records a limit) have
  unknown filters: a re-run of their (query, provider) replaces them
  whatever its filters, their links move to the new key
  (`replaced_links` in `create_review_session`), and
  `merge_concurrent_changes` guards both directions: it does not re-add
  a legacy record from disk that this session replaced, and it drops
  this session's own legacy record when the file replaced it (the key is
  in `SessionBaseline.record_keys`, gone from the file, and the file has
  a record of that (query, provider)); links move to the successor.
  `OpenAlexSemanticProvider` sets `HONOURS_SEARCH_IN = False`. The report's provider table has a
  Filters column (`filter_flags`, `scholar.py`, shared with
  `_search_flags`) and appears also when two records share
  (query, provider), when the records have several queries, or when
  any record knows its outcome or dates (then with a Date column).
  The report's search parameters describe all records (#163, search
  part): `search_parameter_items` (Query/Queries, Providers from
  `searched_providers` incl. merged ones, Searched period from
  `search_period`), and the abstract's "The search covered ..." uses
  `searched_providers`, not `session.providers` (last append only).
  `searched_providers` lists only providers that answered at least one
  search; skipped / failed-outright ones go to "Not searched: ieee
  (skipped: …)" (`unsearched_providers`, `provider_failure`, which
  splits merged errors at their provider prefixes); a provider a merged
  record with papers names as failed is listed with "(failed or
  incomplete in a merged record)", as in the caption
  (`searched_providers_text`). Failed and skipped
  records have no `search_source_date` and stay out of the periods.
  Records from before outcomes were kept (`outcome_unknown`: `hits`
  None and no error; every search since records its hits) do not show
  that the provider answered (#188: DBLP served only its anti-bot page
  then). Such a provider counts as searched only if a decision's
  `provider` names it (`decision_provider_names`, each decision read
  through `decision_provider_evidence`, below);
  otherwise it is listed as "Outcome not recorded: dblp"
  (`unrecorded_providers`, in the items and the abstract), not as "Not
  searched", also when another of its searches failed. `record_rank`
  still ranks such a record as answered, but a re-run that failed
  outright (or was skipped) replaces it unless the session has
  evidence of an answer (`record_may_have_answered`, #190): a
  decision's `found_by` names its key (an old `(q, p, None)` link
  counts), or a decision's `provider` names its provider (as
  `decision_provider_names`, also for decisions with links: records
  without an outcome predate links, #128). Pre-#164 merged decisions
  name every merged provider, so without evidence they keep such
  records too; with sources only the providers the sources or
  single-provider links name (`decision_provider_evidence`, below). A failed record
  never counts as searched.
  Provider evidence (#191, review.nw `sec:provider-evidence`):
  pre-#164 merged searches wrote the merged string (`openalex, dblp`)
  on every paper, whichever returned it, and since #164 (and the #192
  repair) a multi-name string can also be honest, so
  `decision_provider_evidence(decision)`, when the paper has
  `sources`, keeps a name of `provider` only if a source or a
  single-provider `found_by` link (its provider splits into one name)
  names it; without sources nothing is ruled out, since links are
  younger than the merged strings and miss old runs (#190's argument)
  (case-insensitive; string, sources and links all split on
  `PROVIDER_SEPARATORS`, since the notes-module fallback stores a
  joined provider as a source). The string stands unchanged without
  sources, when the evidence names none of its providers
  (`s2` alone, `previous`), with one name (a merged search wrote two
  or more), and for names not in `PROVIDER_FULL_NAMES` (`snowball`).
  Two decisions sharing a paper id share one registry `Paper`, so the
  second is judged by the first's sources. Sources only
  confirm names, never add them (enrichment unions the enriching
  provider into `sources`; preprint adoption the candidate's); links
  add their provider at the end. Used by `decision_provider_names`
  (so also by #190's record replacement) and `collect_audit_rows` (so the caption's rows part); the stored
  `provider` is never rewritten, and displays (`sessions show`, TUI,
  CSV, JSON) show it as stored.
- One record per provider search (#164). `SearchResult.parts` /
  `found_in` (not compared): `merge` keeps the single-provider results
  it was made of and, per merged paper, the indices of the parts that
  returned it (`parts_returning`: same `Paper.id`, or the part's
  provider in `sources`; computed before enrichment, which keeps the
  order). `create_review_session` records one `SearchRecord` per part
  (`search_parts_of`, Mock-safe) and links each paper to its parts only
  (`paper_search_links`); the decision's `provider` names those
  providers. Pre-#164 merged records (provider `openalex, dblp`, query
  `q | q`) load unchanged: `SearchRecord.is_merged`,
  `search_outcome_label` ("merged record (providers …): outcome cannot
  be split"); the audit caption counts them as a query of each provider
  and marks each provider their error names (the merge prefixed each
  error with its provider; `merged_record_failures`) as "failed or
  incomplete for k of n queries, in a merged record"; providers named
  in a merged record without papers count as not searched for it.
  A merged record is superseded once per-provider records of the same
  query (positional `q1 | q2` ↔ providers) and filters exist for every
  provider it names (`merged_record_cover`; the covering record must
  have answered, not failed outright or been skipped, and have a limit
  at least the merged one's unless that is unknown);
  `supersede_merged_records`
  (end of `create_review_session` and of `merge_concurrent_changes`)
  drops it, drops its links where the paper links to a covering record,
  else links the paper to all covering records. Partly covered: kept.
- Totals and caps (#166). Providers set `last_total` (+
  `last_total_estimated`) from the field they already page on
  (OpenAlex `meta.count`, DBLP `@total`, WoS `total`/`RecordsFound`,
  IEEE `total_records`, HAL `numFound`, Scopus
  `opensearch:totalResults`, arXiv feed header; none with arXiv's
  client-side year filter; an absent field is `None`, not 0), reset
  next to `last_error`, and announce it there through
  `first_total_known` (#301, see Search Limit). `search_provider` reads them Mock-safely
  (`provider_total`) into `SearchResult.total`/`total_estimated`,
  stored on `SearchRecord`. `hits_label(..., total=, limit=,
  estimated=)` / `count_label`: "100 of 2,130 (capped at 100)" (capped
  when hits == limit and the total does not show nothing was left);
  plain counts read as before. CSV keeps `# Results: N` numeric and
  adds `# Total reported:` / `# Capped at limit:` / per-provider
  `# Search:` lines; JSON adds `total` and `searches`. Audit caption:
  "capped at the limit for k of n queries" (`search_was_capped`). A
  narrower re-run (same key, smaller limit, both answered) never
  replaces a wider record: the wider one is kept, nothing new is
  recorded, links already share the key (`search_width`: None/0 =
  all; legacy records never count as wider).
  `ReviewSession.add_search_record(record)` carries records over whole.
  All record rules are one sort key, `record_rank(r)` =
  `(answered, width, searched_at, hits, complete)` (legacy width,
  unknown dates and unknown hits rank lowest); `preferred_record(a, b)`
  keeps the higher, `a` on equal keys (a total preorder: no cycles, no
  order dependence). So a search's record is its latest answered run of
  the widest scope, with that run's own outcome (a newer partial run
  reads "incomplete"); the date beats hits because PRISMA asks when each
  source was last searched; older runs' links stay on the same key.
  `create_review_session` (new run first) and
  `merge_concurrent_changes` (own record first, for a shared key) both
  use it through `session_preferred_record(a, b, links,
  provider_names)`, which adds the one session-dependent rule (#190,
  above; from the previous session's decisions, resp. the merged
  decisions plus the file's provider names), so `record_rank` stays a
  key of one record.
- Search dates (#167). `SearchResult`/`SearchRecord` have `searched_at`
  (UTC ISO, the run; `utils.utc_now_iso`), `fetched_at` (when the
  service answered; for a cache hit the original fetch, `None` =
  unknown) and `from_cache`. Providers report them through
  `last_fetched_at`/`last_from_cache`, set by four helpers in
  `providers.py` (`start_answer`, `answer_from_cache`, `fetching_now`,
  `cache_answer`) at each `search()`'s reset, cache hit, fetch and
  store. The fetch time and total of a cached answer live in a side
  entry of the same cache dict, `cache[(FETCH_META_KEY, key)]`
  (`cache.fetch_meta` / `remember_fetch` / `is_fetch_meta_key`): one
  top-level entry per answer, assigned via `__setitem__`, so the
  `PersistentCache` marks it changed and the merge-on-save keeps other
  processes' facts; reading never marks the cache changed. Old entries
  keep loading and read as "fetch date unknown"; no CACHE_VERSION bump.
  `search_dates_label` ("searched 2026-11-18, cached answer fetched
  2026-10-02") in `sessions show`; `search_source_date` feeds the audit
  caption's "Searched A to B." (+ "Search date not recorded for k of n
  searches.", en wording since #275; sv "Sökdatum saknas för ..."); `bibtex+prov`'s `DATE` is the fetch date of the parts
  that returned the paper, "unknown (cached answer, fetch date not
  recorded)" when the cache does not know, the timestamp's date only
  for results without any dates. The session's `timestamp` is
  unchanged.
- Retired searches (#275, review.nw `sec:retired-searches`).
  `SearchRecord.retired` = `{"at", "by", "note"}` or None (saved only
  when set, old files load None; `retire_record`, `retired_label` /
  `retirement_label` "retired 2026-11-20 by X: note",
  `current_records` / `retired_records`; the note's white space is
  collapsed, blank -> None). Not in `key`, not in `record_rank`.
  `SearchRecord.record_id`: first 7 hex digits (`RECORD_ID_LENGTH`) of
  SHA-256 of the key joined by `\x1f`; same across re-runs of the
  key, unlike the list position (each run's records go first);
  `records_with_id_prefix` (case-insensitive prefix). A re-run of the key (`create_review_session`) whose
  record wins replaces it unmarked (WARNING line "... running it again
  makes it current"); a kept retired record (failed/narrower re-run)
  keeps the mark (WARNING "... which stays retired"). A retired record
  never covers a current merged record (`merged_record_cover`); a
  current one covers a retired merged record. Concurrent merge
  (`sec:retired-in-merge`): `SessionBaseline.retired` (key -> mark
  copy); when both
  records of a key are the same run (`same_run`: searched_at,
  fetched_at, limit, hits, error), `merged_retirement` three-way (one
  side changed -> that side; both or no base -> ours), applied to the
  kept record via `replace`; different runs: the kept record's own
  mark. Reports count current records only: `searched_providers`,
  `unsearched_providers`, `unrecorded_providers`,
  `searched_providers_text`, `searched_queries`, `search_period`; the
  report adds a "Retired" item and the abstract the caption sentence
  (`audit_retired_count`); when every record is retired
  (`all_searches_retired`) the parameters are one item "Searches: all
  N searches of the session have been retired; see the table of
  searches" and the abstract "The N papers (...) were found through
  searches that have since been retired, in <full names>"
  (`retired_databases_text`, semantic left out); the provider table keeps every record,
  query cell "q (retired ...)" (`search_retirements`, `query_cell`),
  and is shown whenever any record is retired. Checked: the pipx 1.29
  build loads such a file and drops the mark on save; the searches
  then count as current again in every report. Both sides retiring one
  run with different notes: ours (the last save) wins.

### Search Limit (#301)

`scholar search` and `scholar rq` fetch everything unless `--limit` is
given (cli.nw `sec:no-limit-default`): the option is `Optional[int] =
None`; None and 0 both go to providers as `UNLIMITED_PROVIDER_LIMIT`
(`effective_limit = UNLIMITED_PROVIDER_LIMIT if not limit else
limit`), `-l N` limits. `DEFAULT_SEARCH_LIMIT` (1000) is gone; help
text `SEARCH_LIMIT_HELP` points to `scholar syntax`, whose table
"Searches without --limit (the default)" states the costs from the
code's constants: S2 always bulk (relevance only with `-l N`;
`S2_BULK_SAFETY_CAP`), `openalex-semantic` keeps 50 (lowered before
the search), IEEE `LIMITS.daily` 200 requests of `MAX_LIMIT` 200,
OpenAlex pages of 200 against the metered budget.
- **Reproduced commands always carry the limit**: `_search_flags`
  prints `--limit N` whenever the record knows it (`--limit 0` for the
  sentinel), legacy records (limit None) none. Changed output for
  existing sessions: records of limit 1000 (the old default) now show
  `--limit 1000` in `sessions show`, `prov found-via`, `bibtex+prov`
  FOUND-VIA and `retire-search` record lines (before: no flag).
- **Notice**: providers call `first_total_known(name, total,
  estimated)` (providers.nw `sec:first-total`) where they read the
  first page's total: OpenAlex (+ source-pinned), DBLP, WoS Starter and
  Expanded, IEEE, HAL, Scopus, arXiv (client, `_try_index == 0`), S2
  bulk (request without `token`, with `cap=S2_BULK_SAFETY_CAP` when
  unlimited). Not S2's relevance search (total known only at the end;
  an unlimited search never uses it) and never a cache hit. Restarts
  (arXiv after an empty page/HTTP error, DBLP's zero-hit retry)
  announce again. The listener `(name, total, estimated, cap)` lives
  in a `ContextVar`, installed by `listening_for_totals(listener)`
  (None = nothing); `search`/`rq` install `cli.large_total_notices()`
  (a fresh closure per command, remembering noticed providers: at most
  one notice per provider) only when `--limit` was not given. For a
  total >= `LARGE_RESULT_NOTICE` (10,000) it prints one unwrapped
  (`soft_wrap=True`) stderr line, `large_total_notice`:
  "<provider>: [about ]<total> results for this query; fetching all of
  them (give --limit N to take fewer)", or above a cap "...; fetching
  the first 100,000 (Semantic Scholar's safety cap; give --limit N to
  take fewer)" (`PROVIDER_FULL_NAMES`). `-l 0` gets none. Nothing is
  refused or cut. `--limit` has `min=0` on both commands (a negative
  limit is a usage error, exit 2).
- `scholar syntax`'s table reads `S2_BULK_SAFETY_CAP`,
  `OPENALEX_SEMANTIC_MAX_RESULTS`, IEEE's `LIMITS.daily`/`MAX_LIMIT`
  and `OPENALEX_PAGE_SIZE` (200, also the OpenAlex paging size).
- Tutorials keep `-l 5` on every practice search, and every search
  step's required pattern has the lookahead
  `scholar\s+search(?=.*\s(?:-l\s*|--limit[\s=]+)[1-9])\s+...` (accepts
  `-l5`, `--limit=5` and the limit first), so a learner who drops it fails
  the step. `test_tutorial_searches_carry_a_limit` (any line running
  `scholar search`/`rq`, wherever on the line) and
  `test_tutorial_search_steps_require_the_limit` (each search pattern
  matches the step's command, and not without its limit) check them.
  pytorial matches regex patterns with `re.search` on the recorded
  transcript (no DOTALL, continuations not joined; bash's PS2 `> `
  after a line break), so commands are fed as typed
  (`tutorial_commands(text, typed=True)`) and
  `test_tutorial_patterns_match_commands_as_typed` checks every regex
  pattern of every lesson; a pattern spanning a continued command uses
  `(?:.|\\\n)*` instead of `.*` (scholar-with-an-agent's two searches).
  `TestShowPinnedOutput` pins a limit-1000 record's `--limit 1000`.

### Search Flow

1. CLI parses args → `cli.py:search()`
2. Creates `Search(query)` object
3. Calls `Search.execute(providers)` → `scholar.py:70-114`
4. For each provider: `provider.search(query)` makes HTTP request
5. Results collected as `SearchResult` objects
6. Formatted output (table/json/bibtex)

### Providers

| Provider | Name | API | Auth |
|----------|------|-----|------|
| Semantic Scholar | `s2` | REST API (`requests`): relevance search with `-l N`, else bulk search (operators, or no limit: the default) | `S2_API_KEY` (optional) |
| OpenAlex | `openalex` | `pyalex` client | `OPENALEX_API_KEY` (optional, 10x daily budget), `SCHOLAR_EMAIL` (optional) |
| DBLP | `dblp` | REST API | None required |
| Web of Science | `wos` | REST API | `WOS_API_KEY` (required) |
| IEEE Xplore | `ieee` | REST API | `IEEE_API_KEY` (required) |
| Scopus | `scopus` | REST API | `SCOPUS_API_KEY` (required); `SCOPUS_INST_TOKEN`, `SCOPUS_VIEW` (optional, see Scopus Views) |
| arXiv | `arxiv` | `arxiv` client | None required |
| HAL | `hal` | REST API (Solr) | None required |
| SSRN | `ssrn` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| bioRxiv | `biorxiv` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| medRxiv | `medrxiv` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| ChemRxiv | `chemrxiv` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| Research Square | `researchsquare` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| Preprints.org | `preprintsorg` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| IACR ePrint | `iacr` | OpenAlex (`pyalex`), source-pinned | `SCHOLAR_EMAIL` (optional) |
| OpenAlex semantic search | `openalex-semantic` | OpenAlex `search.semantic` (`pyalex>=0.21` `Works().similar`), opt-in, ranked top 50 | as `openalex` |

**Key arguments.** The keyed constructors (`SemanticScholarProvider`,
`OpenAlexProvider`, `IEEEXploreProvider`, `ScopusProvider`) treat
`api_key=None` (or `""`) as "not given" and fall back to the environment
variable: `ScopusProvider(api_key=None)` has a key when `SCOPUS_API_KEY`
is set. The registry builds providers without arguments, so the
environment is the normal key source. Tests wanting no key must
`monkeypatch.delenv` the variable (or clear `provider.api_key` after
construction). Exception: `WebOfScienceProvider` uses a sentinel, so an
explicit `None` disables that tier (the legacy `WOS_API_KEY` still
fills it).

### Semantic Scholar: relevance vs bulk search (#161)

`SemanticScholarProvider.search` picks the endpoint per search
(`s2_uses_bulk(query, limit)`, providers.nw `sec:s2-two-searches`, API
description https://api.semanticscholar.org/graph/v1/swagger.json):
a query with operators (`s2_has_operators`: UPPERCASE AND/OR/NOT,
quotes, parentheses, `|`, a word-initial `+`/`-`, `*`) or a search
without a limit (`None`, `<= 0`, or `UNLIMITED_PROVIDER_LIMIT`, now
defined in `scholar.scholar` and imported by the CLI) goes to
`/paper/search/bulk` (`_search_bulk`, pages by `token` until it is
empty/absent or the limit is reached; with a finite limit it sends
`sort=citationCount:desc` and `last_via` is `"bulk, most cited first"`
(capped bulk answers are otherwise arbitrary, paperId order); without
a limit it stops at `S2_BULK_SAFETY_CAP` = 100,000 papers and records
"stopped at the 100000-paper safety cap" as incomplete;
`s2_bulk_query` translates AND→`+`, OR→`|`, NOT/AND NOT→`-` outside
quoted phrases and quotes unquoted hyphenated words, since bulk reads
an inner `-` as negation, #161 comment: `re-execution` 18,149 vs 251;
`s2_mixes_and_or` → WARNING for ungrouped AND/OR, no documented
precedence).
Hyphen quoting takes the whole blank-delimited token (`don't-care` →
`"don't-care"`; leading `+ - | (` and trailing `| )` stay outside);
a hyphenated word with `*` (`pre-print*`) is refused like foreign
field syntax (`s2_hyphen_wildcard`; the docs define `*` for words
only). A refused search has `last_via` None and `_routed` reset, so
`applied_filters` reports no `--in` for it.
`scholar.applied_filters(provider, query, filters, limit)` passes the
limit to a provider method that names a `limit` parameter (S2's does,
and recomputes the endpoint from query and limit), so a search skipped
by the rate limiter records the same filters, hence key, as an
answered one. `s2_foreign_field_syntax` refuses Scopus/WoS/arXiv field
codes before any request: `last_error` "query uses <db> field syntax,
not supported by Semantic Scholar" (failed, not cached). Plain words
with a limit stay on `/paper/search` (`_search_uncached`), which never
asks past offset 1000 and sets `last_error = S2_RELEVANCE_CEILING`
("relevance search stops at 1000", shown as "1000, incomplete (...)")
when it stops there with more asked for and reported. Bulk results are
cached under the relevance key plus `"bulk"` (old relevance entries,
including the wrong zeros of Boolean queries, are never served for a
bulk search; plain-word entries keep serving). **The cache holds
built-in types only** (an older scholar unpickles the shared file): the
papers as a plain list; fetch time and total go through the shared
hooks (`start_answer`/`answer_from_cache`/`fetching_now`/
`cache_answer`) into the `(FETCH_META_KEY, key)` dict side entry; the
snippet backend also keeps `("__s2_ranked__", key) = (scores,
fetched_at)`. A test unpickles a written cache with
`scholar.providers` unimportable. `search` sets `last_total` and
`last_total_estimated = True` (the description calls both totals
"Approximate"), and `last_via` (`"bulk"`, `"bulk, most cited first"`
or None). `--in title-abstract` is honoured on bulk (it matches
title+abstract by default): `SemanticScholarProvider.applied_filters`
decides from the query and the limit `search_provider` passes (before
and after the search, so a skipped search gets it too); `_routed`
(query, bulk) noted by `search` is read only by a caller without a
limit; only the relevance search
warns, once per search. `via` flows `provider_via()` (in
`search_provider`) → `SearchResult.via` (kept through `merge` as
`"s2: bulk"` and `deduplicate`) → `result_via(part)` per part in
`create_review_session` → `SearchRecord.via` (saved/loaded as `"via"`,
old files → None; not part of the record key nor of `record_rank`, so
a newer or wider bulk re-run replaces a relevance record, as intended) → `sessions show` ("s2 (via bulk): q", JSON
`via` when set). Bulk stems terms and matches title+abstract only
(`scholar syntax` says so). Not verified live: what `-` does before a
parenthesis or phrase.

### Order of answers (#303)

A limited search keeps the head of a provider's list, so each answer
records its order (providers.nw `sec:answer-orders`, scholar.nw
`sec:search-result-order`): `ANSWER_ORDERS` = `relevance`, `date`,
`citations`, `unknown` (`None` = not recorded). Each provider class
declares `ANSWER_ORDER` (the order scholar *asks for*, or the
documented default when it asks none); `start_answer` copies it into
`last_order`, reset with `last_error`; S2 sets it per search
(`s2_order`: relevance search `relevance`, bulk with a limit
`citations`, bulk without `unknown`) and a refused S2 search records
None. Path as `via`: `provider_order` (Mock-safe, vocabulary only) in
`search_provider` → `SearchResult.order` (`deduplicate` keeps it;
`merge` gives `unknown` when either input has one, else None) →
`result_order(part)` in `create_review_session` → `SearchRecord.order`
(saved only when set, old files → None; not in the key nor in
`record_rank`, so a re-run in the new order replaces the old record of
the key as any newer run) → `sessions show` " — order: X" after the
outcome for every recorded order, relevance included (shown only for
non-relevance, an old record would look ranked), JSON `order` when
set.

| Provider | Order | Source (read 2026-11-23) |
|---|---|---|
| scopus | relevance: sends `sort=relevancy` on every page | Scopus Search API WADL (dev.elsevier.com/documentation/ScopusSearchAPI.wadl): `sort` options incl. `relevancy`; no default stated |
| wos (both tiers) | relevance: sends `sortField=RS+D` | Starter OpenAPI (developer.clarivate.com/apis/wos-starter/swagger): supported fields list "RS - Relevance", example RS+D "Relevance (Descending)"; Expanded (…/apis/wos/swagger): no field list, RS rests on its example ("Relevance": RS+D) and the separator text ("'+' or ' '"); no default stated |
| openalex, source-pinned, openalex-semantic | relevance (no `sort` sent) | help.openalex.org/api/searching/: "sorted by it (descending) by default" |
| s2 | per endpoint (above) | swagger.json (#161) |
| arxiv | relevance (`sortBy=relevance&sortOrder=descending`) | info.arxiv.org/help/api/user-manual.html |
| hal | relevance (`HAL_SORT` "score desc,docid asc") | api.archives-ouvertes.fr/docs/search: "Par défaut, les résultats sont triés par pertinence" |
| ieee | unknown (no sort sent) | developer.ieee.org Sorting_and_Paging_Parameters: `sort_field` only article_number/article_title/publication_title, no default stated |
| dblp | unknown (no sort sent) | dblp's search API FAQ served an anti-bot page: not read |

Before #303 Scopus and WoS sent no sort and answered newest first
(issue's measurement on twelve cached queries: Scopus all lists, WoS
89 %). Both now key their cache by the order (`SCOPUS_ORDER_KEY`,
`WOS_ORDER_KEY` = `"sortField=RS+D"`, plain strings, no
`CACHE_VERSION` bump): old entries are unused, not deleted. So every
earlier Scopus/WoS cache entry is a miss: re-running an old session's
searches spends live quota on those two, and the #139 fallback to old
standard-view Scopus entries (off campus, inconclusive probe) no
longer finds them, so such a search fails. Right all the same: an old
entry's order is not the one now recorded, and a limited old entry
holds other records (the newest) than a relevance search returns.
Probes, DOI lookups (WoS: the tier functions take `sort_field`, only
`_search_uncached` passes it) and WoS's extended methods send no sort.
`search_provider` records no order for a search that failed outright
(error, no papers) or was skipped; an incomplete answer with papers
keeps it. No provider records `date` today.

### Title-and-Abstract Search (`--in`)

`scholar search/rq --in title-abstract` sets `SearchFilters.search_in`
(#135; values in `SEARCH_IN_CHOICES`, a Typer `Enum` in the CLI so a bad
value is a usage error). It is a filter: in `as_dict`/`cache_key` only
when set (old cache keys unchanged), in the session record's key, and
rendered back by `filter_flags` as `--in title-abstract`. A search
records the filters its provider *applied*
(`scholar.applied_filters(provider, query, filters)`, used by
`Search.execute` and rq): a provider's own `applied_filters(query,
filters)` method if it has one (Scopus), else `search_in` is kept only
when `HONOURS_SEARCH_IN is True` (OpenAlex and subclasses, WoS).
Provider cache keys still use the requested filters (an ignoring
provider caches an `--in` search separately; harmless).
`SearchResult.merge` keeps `search_in` when the inputs differ only in
it, since a merged record stands for the whole command. Per provider
(docs cited in `providers.nw`, section "Searching title and abstract
only"; `scholar syntax` has a "Default Search Fields" table):
- OpenAlex + source-pinned servers: scoped parameter
  `search.title_and_abstract=` instead of `search=` (which also matches
  full text). The filter form `title_and_abstract.search` is deprecated
  in OpenAlex's docs. `_base_query(query, filters)` is the seam;
  subclasses must pass `filters` on. Boolean queries work (checked live
  2026-11-18 via `meta.x_query.oql`). OpenAlex lacks abstracts for many
  works (its docs: >60% of 2022 works have one, ~45% pre-2000), so this
  is not the same search as in WoS/Scopus.
- Scopus: query wrapped as `TITLE-ABS-KEY(...)` unless it already has a
  field code (`SCOPUS_FIELD_CODE`, case-insensitive over the explicit
  `SCOPUS_FIELD_CODES` list from Elsevier's search tips, plus
  `PUBYEAR`/`REFPUBYEAR` with an operator); then it warns and does not
  record `search_in`. WoS: nothing to do
  (`TS=` = title, abstract, author keywords, Keywords Plus).
- S2, DBLP, IEEE, arXiv, HAL: `warn_search_in_ignored()` logs
  "`<name>: --in title-abstract not supported, ignoring`" and searches
  as usual.

### Preprint-Server Providers and Groups

The seven source-pinned providers exist because their servers have no
usable public search API (SSRN/Research Square: none; bioRxiv/medRxiv:
DOI/date lookup only; ChemRxiv: Cloudflare-blocked; Preprints.org:
registration-gated; IACR: HTML-only search). Each is an
`OpenAlexSourceProvider` — a subclass of `OpenAlexProvider` pinned via
the `locations.source.id` filter (not `primary_location`, which would
hide preprints later published elsewhere). They set
`default_enabled = False`, so `get_default_providers()` skips them: an
unscoped search already gets their papers through `openalex`, and
running them by default would only duplicate requests. Select them
explicitly (`-p ssrn`) or through the group alias `-p preprints`, which
`expand_provider_names()` (in `providers.py`) expands to
arxiv, hal, ssrn, biorxiv, medrxiv, chemrxiv, researchsquare,
preprintsorg, iacr. Groups are aliases, not registered providers, so
they never appear in `providers list/check` and provenance stays
per-server. TechRxiv is a known gap: no API and not in OpenAlex.

### Semantic Search Check (#136)

A keyword search's record cannot show what it missed; a search by
meaning can check it. `OpenAlexSemanticProvider` (`openalex-semantic`,
providers.nw `sec:openalex-semantic`; limits from
https://help.openalex.org/api/semantic-search/: 50 results, 2000
characters, 1 request/s, one search parameter per request) is one
request `pyalex.Works().similar(q).get(per_page=min(limit, 50))`, no
paging (`limit` 0 → 50). `default_enabled = False`, `MAX_LIMIT = 50`,
`RANKED_LIST = True`, quota group `openalex`. It refuses (failed, not
cached, via the inherited `search()` catch-all) any filter
(`not filters.is_empty()`) and any question over 2000 characters
(OpenAlex would truncate, so the recorded question would not be the
one matched). It returns a `RankedPapers` (list subclass with
`scores` = `relevance_score` per rank and `fetched_at`, UTC ISO); that
is what the cache stores (`CACHE_VERSION = 3`), so a hit keeps the
original fetch time; `search()` sets `last_from_cache`. A limiter
refusal sets `last_error` (else it would read as 0 works).

- **Ranked, not a count.** `scholar.RANKED_PROVIDERS` (a test keeps it
  equal to registered providers with `RANKED_LIST`) and
  `is_ranked_provider()` (joined strings: ranked only if every part
  is); `hits_label(..., ranked=True)` → "top 50, ranked (not a count)"
  (failed/incomplete unchanged). Every call site passes `ranked=`;
  `sessions show` drops the "hits:" prefix for such records, and
  `sessions show -f json` adds `"ranked": true` to them (key absent
  otherwise).
- **CLI search** (`<<refuse what a semantic search cannot do>>`, right
  after provider names are resolved): with `openalex-semantic` it must
  be the only provider and the query ≤ 2000 (exit 2); the limit is
  lowered to 50 before the search, so the record (and
  `prov found-via`) says `--limit 50`. Filters are refused by
  `<<refuse filters for a semantic search>>` right after the
  `SearchFilters` is built (`not filters.is_empty()`), so a new filter
  needs no change there, only in `SearchFilters.is_empty`.
- **`rq`** refuses `-p openalex-semantic` (exit 2) before asking for the
  question: its LLM writes keyword queries, mixes providers in one
  session, records a keyword search's limit and applies filters.
- **Audit table**: ranked records/rows are left out of the
  "Databases:" sentence and of `audit_search_shortfalls`; code `OA-sem`;
  `audit_semantic_sentence` adds `AUDIT_STRINGS[lang]["semantic"]` (en,
  sv) after it: "the 50 works" when every semantic record asked for the
  same number, "up to 50 works" (largest) when they differ or some do
  not say, "the works" when none does.
- **`scholar sessions check S [S ...] -s Q [-s Q2] [-k DOI|title-part]
  [-l N≤50] [-f table|csv|json] [-o DIR] [-b openalex|s2-snippets]`**:
  `-b s2-snippets` uses `SemanticScholarSnippetSearch` (providers.nw
  `sec:s2-snippets`; unregistered, name `s2-snippets`, own cache,
  `QUOTA_GROUP = "s2"`): one `/graph/v1/snippet/search` request with
  `limit=1000`, `fields=snippet.snippetKind`, reduced by
  `s2_snippet_works` to works (each once, at its best snippet, score
  kept) in a `RankedPapers`; snippets carry no DOI or year, so one
  `POST /paper/batch` (`CorpusId:` ids, `fields=externalIds,year`,
  through `_request`/`_send`, which now take a `json_body`) fills them
  in; if it fails, nothing is cached and `last_note` ("... matched by
  title and first author only") appears as `note` in the check's
  text/JSON/evidence (`check_note`). The 2000-character question limit
  applies to `openalex` only. Per question one
  provider search (quota pre-check → failed with the limiter's reason),
  then `review.check_against_sessions(papers, sessions, known)` →
  `(CheckRow[], KnownRow[])`. `session_match_index` keys: `Paper.id`
  (not for a DOI-less untitled paper), version-link DOIs
  (`preprint_versions`/`published_versions`) and
  `audit_work_key` when its title is non-empty, plus the title alone
  for a session paper without authors; `matched_by` `doi`,
  `title+author` or `title` (a session paper without authors records
  `title` on every title key, #152). A title match is dropped
  (`_plausibly_same_work`) when both papers have different DOIs not
  joined by a version link, or both years are more than 1 apart.
  Buckets per decision: bearing = cited by the audit rule
  (`audit_reason` order `AUDIT_ORDER_CITED`: human keep with theme
  tags or no tags) or supports/qualifies; adjacent; other topic;
  excluded (discarded with a bearing or no category: status wins, #89);
  unclassified (no category, pending or LLM keep included). Across
  sessions the most relevant wins (`CHECK_BUCKETS` order: bearing >
  adjacent > unclassified > other topic > excluded); the per-session
  list shows every view. `check_tally(rows)` gives the per-question
  line "N works: x bearing, …". `--known`: exact DOI if it normalises
  to `10.`, else case-insensitive title part (empty → exit 2); a known
  study not returned is still looked up in the sessions. Exit 1 for a
  missing/unreadable session (before any request) or a failed
  question; usage errors exit 2. Strictly read-only (test: session file
  byte-identical). Each question records `check_date` and `source`
  (`fetched <t>` / `cached, fetched <t>` / `cached (date unknown)`,
  never the check date as fetch time). `-o DIR` writes `<n>.json`
  (question, provider, limit, check_date, source, error, the works as
  `Paper.to_dict()` plus `rank` and `relevance_score`) and `<n>.txt`
  (the table-format text).

### Error Handling

All providers still return an empty (or truncated) `list[Paper]` on errors,
and no exceptions propagate to the CLI — but a failure is no longer
silent. A provider resets `last_error = None` first thing in `search()`
(before the cache lookup) and sets it to a short reason on every failure
path, which is also every path that declines to cache; a retrying
provider sets `last_retries`. `Search.execute` (and `rq`) read them via
`provider_outcome()` (Mock-safe) onto `SearchResult.error`/`retries`, and
the search output (`# Results: failed (...)` in CSV, the table, JSON),
`sessions show` ("Queries by provider:") and the report's provider table
show "failed". The keyed REST providers (S2/WoS/IEEE) set the generic
`SEARCH_CUT_SHORT` in the `cacheable=False` branch; DBLP, Scopus,
OpenAlex (+ source-pinned), HAL and arXiv set specific reasons. A new
provider should do the same.

DOI lookups (#259, providers.nw `sec:lookup-outcome`): every
`get_paper_by_doi` (S2, OpenAlex + subclasses, IEEE, WoS, arXiv,
Scopus; DBLP and HAL have none) resets `last_lookup_error = None`
first thing (its own attribute, so a lookup never overwrites a
search's `last_error`) and sets a reason on every uncached failure
path; an answer (record, 404/empty result, cache hit, arXiv's instant
"not an arXiv DOI") leaves None. Reasons are worded once in
network.nw (`sec:request-failure-reason`): `http_status_reason` ("rate
limited (HTTP 429)", "HTTP 503") and `request_failure_reason`
(`RetryError` -> `RETRIES_SPENT`, connection/timeout -> "connection
failed (SSLError)", other `requests` exceptions -> class name only,
since their text quotes the URL with DOI, key or address; anything
else, e.g. the `OSError` "Could not find a suitable TLS CA certificate
bundle, ..." -> its text, redacted, one line, <= 120 chars);
`providers.lookup_failure_reason` adds the limiter's reason for
`RateLimited`. WoS: each tier keeps the caught exception's reason in
`_tier_failure` (reset at the tier's start); the lookup records it,
`SEARCH_CUT_SHORT` only as fallback (searches still record
`SEARCH_CUT_SHORT`). arXiv's `UnexpectedEmptyPageError` ->
`ARXIV_EMPTY_PAGE` (its text quotes the URL). A third outcome,
*declined*, goes to `last_lookup_declined` (reset first thing too;
`last_lookup_error` stays None): keyless IEEE/Scopus/WoS (reason names
the variable) and Scopus without COMPLETE, under `SCOPUS_VIEW=standard`
or after the 401 view refusal (`_lookup_declined_reason`). Declining is
not failing: off campus Scopus would otherwise make every paper
"failed" and every run say "run again". `UnpaywallClient` and
`CrossrefClient` keep `last_lookup_error` the same way (module
`last_lookup_error()`); their warning lines log the exception through
`network.redact_secrets`. Enrichment reads both attributes Mock-safely
(`enrich.lookup_error`/`lookup_declined`, only a non-empty str counts).

OpenAlex (#150, #151): a limiter refusal sets `last_error` to its
reason; a refusal or failed request after some pages keeps those pages
(`PagesCutShort` from the paging loop → `N, incomplete (reason)`,
uncached). A refused request that reaches scholar as an `HTTPError`
records `HTTP <code>: <message>` from the JSON body (`message`, else
`error`; `openalex_error_message`, shortened to
`OPENALEX_REASON_MAX_CHARS` = 120), or `HTTP <code>` without one, plus
`; no API key: set OPENALEX_API_KEY` when keyless and the refusal is a
503 with OpenAlex's message in the body or a budget-spent 429;
`providers check` gives the same detail. Two refusals pyalex raises
itself as a `QueryError` before any `HTTPError`: a 400 whose `error`
mentions "query parameters" (the exception holds the body's
`message`) and a 401 whose `error` mentions "API key" (`error` plus
pyalex's "Did you configure a valid API key?"). Those record the
exception text, shortened, without the `HTTP <code>:` prefix. The
constructor sets `pyalex.config.retry_http_codes =
[]`: pyalex's default (`max_retries=0` with 429/500/503 listed) retried
nothing but turned those statuses into a `RetryError` without a
response, so no search ever saw a real 429 or 503 body. The per-paper
lookups (`get_paper_by_doi`, `get_preprint_locations`,
`search_preprints_by_title`) hand an `HTTPError` to
`_note_http_error(e, during=...)`, so a 429 there starts a cooldown.

Keys in messages (#159): `network.redact_secrets(text)` hides the
values of `api_key`/`apikey`/`api-key`/`key` URL parameters and
`mailto`/`email` (personal data, #160, #259), in any case. `check_provider` applies it to every health message; the
OpenAlex and IEEE (`apikey` in the URL) error logs use it. The OpenAlex
`/works` probe sends the key as `Authorization: Bearer` (documented,
as pyalex does); `/rate-limit` keeps the `api_key` parameter (the only
form documented for it).

### Provider Health Checks

Because search errors degrade silently, `scholar providers check` probes each
provider with a one-result request and reports
`ok`/`key rejected`/`rate limited`/`http error`/`network error`/`not
configured`. Exit code is 1 iff a *configured* provider fails — usable as a
pre-flight gate before a big search. `--offline` skips the network probes.
Implemented as `check_provider()`/`classify_check_response()` plus a
per-provider optional `check()` method in `providers.py`.
`classify_check_response(..., expect_json=True)` turns a 2xx body that is
not JSON into `http error` "non-JSON response (HTTP 200, text/html)"
(`non_json_reason()`); every JSON probe uses it (DBLP, Scopus, S2,
OpenAlex and its preprint servers, HAL, IEEE, WoS), only arXiv's
Atom probe does not. Since Sep 2026
dblp.org and both mirrors (uni-trier, dagstuhl) serve an Anubis anti-bot
HTML page with HTTP 200 to API clients; no header or mirror helps (#94),
so `providers check` fails for dblp and DBLP searches record `failed`.

### DBLP Query Sanitization

DBLP has no boolean syntax (space = implicit AND; uppercase `AND`/`OR`/`NOT`
become literal search terms). `DBLPProvider` strips operators, parentheses,
and quotes before sending (warning shows the sent query) and warns when a
query of ≥4 terms yields zero hits. Queries are never auto-relaxed — results
stay traceable to the recorded query. Because DBLP throttling can answer
with a valid zero, a query of ≥2 terms that returns nothing is repeated
(identical query) after 2 s and 5 s (`DBLP_ZERO_HIT_RETRY_DELAYS`, via
the `ratelimit._sleep` test seam); hits on a retry are logged at INFO,
the count goes to `last_retries` → `SearchResult.retries`, and a zero
that survives is recorded (and cached) as 0, not as failed (#82).

DBLP author names carry homonym numbers (`Wei Wang 0001`); `_convert_hit`
drops a trailing space + exactly four digits
(`utils.strip_dblp_homonym_number`), else the number becomes the
surname in cite keys, `audit_work_key` and the legacy hash id (#120).
At session append `review.py` strips it from incoming papers too
(cached DBLP results still carry it) and reconciles entries stored with
it like Scopus's surname-first ones (`homonym_free_id()` +
`migrate_paper_id`, keeping decisions and notes).
Papers stored with the number and not re-run keep it (in their id,
authors and cite key, e.g. `00012014`); `audit_work_key` strips it
(#233), so their audit rows and possible copies meet the plain-name
copies; `cite_key_base` deliberately does not (keys already cited stay
put; changing it would need a `SYNTHESIS_CACHE_VERSION` bump).

### Scopus Empty Results

A Scopus search with no hits returns one placeholder entry,
`{"@_fa": "true", "error": "Result set was empty"}` with
`opensearch:totalResults` "0" (live shape). `scopus_result_entries()`
drops it (any entry with `error`, or `@_fa` "false"), so it is never
converted into an empty paper (#106).

### Scopus Views

Searching Scopus works from any network, but how much each result holds
depends on the *view*: the default (STANDARD) view has title, venue, DOI
and the first author only; `view=COMPLETE` adds abstract, author
keywords and the full structured author list, and Elsevier serves it
only to the subscribing institution's IP range or with
`SCOPUS_INST_TOKEN` (elsewhere: HTTP 401 `AUTHORIZATION_ERROR`; a bad
key is 401 `AUTHENTICATION_ERROR`, and `scopus_view_refused()` tells
them apart). COMPLETE caps pages at 25, which is `MAX_LIMIT` anyway.

`ScopusProvider._get_best_view()` asks for COMPLETE and, on refusal,
falls back to the default view for the rest of the process (one INFO
line, one wasted request). `SCOPUS_VIEW=auto|complete|standard`
overrides: `standard` never asks, `complete` never falls back.
`providers check` reports which view it got.

The never-expiring cache is keyed by view and order (#303):
default-view results are `(query, limit, filters, "sort=relevancy")`
(`SCOPUS_ORDER_KEY`), COMPLETE results add `"COMPLETE"` after it; the
old 3-tuple / `"COMPLETE"` 4-tuple entries (newest first) are never
served and stay unused until `cache clear --provider scopus`; so old
sessions' Scopus re-runs cost live requests, and off campus a search
that the old standard-view entry used to serve (#139) now fails. COMPLETE results are served to everyone (unless
`SCOPUS_VIEW=standard`); default-view results only when COMPLETE is not
available, which a new process learns from one `count=1` probe
(`_complete_confirmed()`); a failed probe still serves the cache.
When it is served because the probe was inconclusive (HTTP 429/5xx/403,
a bad key, `RateLimited`, a network error; a *refusal* is the normal
off-campus case and silent, and so is `SCOPUS_VIEW=standard`), the
provider logs one WARNING per process naming the reason and the remedy
`scholar cache clear --provider scopus` (#139). The route (proxy or
direct) is deliberately not part of the key: what changes the data is
the view the route entitles, and that is already keyed.

`ScopusProvider.get_paper_by_doi()` (a one-result `DOI("...")` search)
makes Scopus the *last* entry of `ENRICHMENT_PROVIDERS` (after the
abstract services `crossref`, `europepmc`, #260). It returns
`None` unless the COMPLETE view is served (the default view has no
abstract to add), and after one refusal it declines without a request,
so an off-campus enrichment run costs Scopus a single request.

Scopus writes names surname first (`Fares E.`), which made
`legacy_hash_paper_id` hash the initial. `scopus_authors()` uses
COMPLETE's `given-name`/`surname`, else `utils.given_name_first()`
(moves trailing initials to the front, nothing else). Sessions that
stored the old form are reconciled at append in `review.py`
(`given_name_first_id()` + `migrate_paper_id`), keeping decisions.

### Contact Email

`SCHOLAR_EMAIL` is the one contact address for every service that asks for
one: OpenAlex and Crossref (polite pools, optional) and Unpaywall
(mandatory). `scholar.utils.contact_email(*override_vars)` resolves it;
`OPENALEX_EMAIL` / `CROSSREF_MAILTO` still work as per-service overrides.
The test `conftest.py` unsets all three so unit tests never make live calls.
Read the address when a request is built, never at construction or
import (#241): the Crossref and Unpaywall clients are built at import
(`_client`), which pytest does while collecting, before the conftest
unsets anything, so a stored value was the developer's real address.
`CrossrefClient.mailto` and `UnpaywallClient.email` are properties
calling `contact_email` per request; subprocess tests
(`TestCrossrefAddressAtRequestTime`, `TestUnpaywallAddressAtRequestTime`)
import with a dummy set, unset it, and check the requests a loopback
server records. The OpenAlex providers still write the address into
`pyalex.config` at construction; the conftest resets it per test
(#160, `TestPyalexConfigIsolation`). Keys held by registered providers
are reset the same way (#174).

OpenAlex additionally reads `OPENALEX_API_KEY` (free key from
openalex.org/settings/api; ten times the metered daily budget). The
provider hands it to `pyalex.config.api_key` (sent as a bearer token);
the health probe sends it as the `api_key` query parameter; `conftest.py`
unsets it too.

### Network: proxy and User-Agent

`network.py` (`network.nw`, chapter `ch:network`) owns the route and the
identity of every outgoing request:

- **Route**: global CLI option `--proxy URL` (stored by
  `network.set_proxy`, called by the app callback on every invocation)
  wins over `SCHOLAR_PROXY`; with neither, requests' own
  `HTTP(S)_PROXY`/`ALL_PROXY`/`NO_PROXY` handling applies. The proxy is
  passed per request (`proxies=`), because requests lets the environment
  override a session's `proxies` attribute. The callback validates the
  URL (scheme http/https/socks4/socks4a/socks5/socks5h, a host, PySocks
  for SOCKS) and exits 2 on a bad one, since a broken proxy would
  otherwise make every provider silently return nothing. Recommend
  `socks5h://` (DNS at the proxy).
- **Identity**: `scholar/<version> (+https://github.com/dbosk/scholarcli)`,
  overridable by `SCHOLAR_USER_AGENT`. No email in it on purpose: the
  UA goes to every host (publishers included); OpenAlex/Crossref/
  Unpaywall get `SCHOLAR_EMAIL` via their own parameters. A
  caller's own User-Agent header is kept (arXiv's `arxiv.py/...`;
  DBLP's own `DBLP_USER_AGENT` is gone, #120). Never imitate a browser: bot checks
  (Cloudflare challenges, login pages) are a stopping point, not
  something to work around.
- **Applying**: `network.get(url, **kw)` wraps `requests.get` (so tests
  that patch `requests.get` still intercept); `network.new_session(retry)`
  returns a `ScholarSession` (S2, Crossref, Unpaywall, the arXiv client's
  `_session`); `network.configure_pyalex()` sets pyalex's User-Agent and
  wraps the private `pyalex.api._get_requests_session` (warns if a
  pyalex release removes it while a proxy is set). Every provider uses
  these, `DBLPProvider` included (search pages and probe call
  `network.get`, #120).
- **Reporting**: `scholar providers check` prints `Route: direct` or
  `Route: proxy <scheme://host:port> (<source>)` (credentials redacted)
  above the table; `--show-ip` adds the exit IP from api.ipify.org (only
  on request; skipped with `--offline`).
- Not done: per-provider proxy selection (e.g. only Scopus and PDF
  downloads through the tunnel).

### PDF Cache and `scholar pdf import` (#296)

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
- Test PDFs are written by hand (`make_pdf` in pdf.nw, `make_cli_pdf` in
  cli.nw: optional text line, optional `/Encrypt`); in a code chunk
  every `<<` of PDF syntax must be written `@<<`.

### Open-Access Lookup (Unpaywall)

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

### Abstracts from Crossref and Europe PMC (#260)

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

### Abstracts stored as paragraphs (#290)

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

### Doubtful Abstracts (#287)

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

### Currency / Retraction Checks

`crossref.py` checks whether a paper has been retracted, corrected, or
superseded, using Crossref's `updated-by` (Retraction-Watch-backed) and
`relation` metadata. Results are cached per DOI via the shared cache layer.

- `Paper.updated_by` / `Paper.newer_versions` hold the findings;
  `None` means "never checked", `[]` means "checked, clean".
- `Paper.is_retracted` / `is_corrected` / `is_superseded` are convenience
  predicates; `crossref.currency_status(paper)` reduces these to one word
  (`retracted`/`corrected`/`superseded`/`preprint`/`ok`/`unknown`).
  `preprint` means a deliberately adopted preprint (see below) whose only
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

### Preprint Fallback (adopt a preprint when no PDF is found)

When enrichment ends with no `pdf_url` (providers + Unpaywall found
nothing), `preprint.find_preprint(paper, search=False)` tries to locate a
preprint version and **replace the entry with it** (preprint DOI, venue,
pdf_url) so citations point at the version actually read. The published
DOI is kept in `Paper.published_versions`
(`{"doi": ..., "relation": "preprint-of"}`, drives
`is_preprint_substitute`). Tiers, first adoptable (= yields a PDF) wins:

0. `Paper.preprint_versions` links recorded by dedup (see below).
1. OpenAlex `locations` of the published DOI
   (`OpenAlexProvider.get_preprint_locations`); arXiv locations become a
   full replacement via the derived arXiv DOI, other hosts only fill
   `pdf_url` (no DOI to swap to).
2. Crossref `has-preprint` relation (`crossref.fetch_preprint_dois`,
   parsed from the same cached `fetch_currency` response; cache key is
   versioned via `CURRENCY_CACHE_VERSION`).
3. Only with `--preprint-search` (on `scholar enrich` and
   `search --enrich`): one OpenAlex `type:preprint` title search
   (`search_preprints_by_title`) + one arXiv search; candidates accepted
   only on exact `legacy_hash_paper_id(title, authors)` match — title and
   authors are the only data shared between versions, and fuzzy matching
   is deliberately avoided.

Identity change on adoption is handled by `notes.migrate_paper_id`
(notes + decision stores), announced by `scholar enrich`
("Adopted preprint <doi> ..."), and reconciled at session append in
`review.py` (both directions: returning published version folds into the
adopted entry; a later-arriving adoption upgrades an existing published
entry, keeping its decision).

**Version-aware dedup**: `deduplicate_papers` runs a second pass
(`deduplicate_versions`) grouping by `legacy_hash_paper_id`; a group of
exactly one published paper (`utils.is_preprint_paper` classifies by DOI
prefix/venue) plus preprints collapses onto the published entry, filling
content gaps via `merge_version_of` (never version-specific fields like
`pdf_url`) and recording `Paper.preprint_versions`
(`{"doi", "pdf_url"}`) for tier 0. Ambiguous groups are left untouched.

**DOI-less copies and namesakes** (#170, `scholar.nw`
`sec:same-work-guard`/`sec:doi-less-copies`, `review.nw`
`sec:session-copies`): `plausibly_same_work` (moved from the sessions
check; DOIs differ and are not version-linked, or years > 1 apart →
not the same work) guards every title-based match. `deduplicate_papers`
merges two hash-id copies only when it admits them (a DOI merges
whatever the years), then `link_doi_less_copies` folds a DOI-less copy
into the one published DOI copy whose `legacy_hash_paper_id` equals its
id (`doi_copy_index`/`doi_copy_of`; preprints and ambiguous choices are
left alone, and so is a copy without a year or a first author,
`foldable_copy`). In sessions an append never folds (folding at
append time raced other processes: double folds, notes moved by
`get_note` on read, undo losing enrichment, stale saves resurrecting
copies). `scholar sessions reconcile S [--dry-run]`
(`reconcile_session`) takes the session file lock (reentrant, so the
inner `save_session` takes it again), loads fresh, folds every
`foldable_copies` pair with `reconcile_copies` (an `is_unscreened` copy
-- pending, untagged, human, no confidence or `LLM_AUDIT_FIELDS` -- into
the other, or two equal decisions: `decision_state` includes source and
audit fields, so a fold never relabels a source; not if both ids have
notes), saves, and only then moves notes: `move_stranded_notes` moves
every tombstoned id's note whose new id has none and whose old id the
session no longer holds (a copy kept apart keeps its note), so a re-run
repairs a failed note write or a note a stale process saved under the
old id.
`--dry-run` runs `reconcile_copies` in memory without saving, so it
lists exactly what a real run folds. Each fold leaves a tombstone in `ReviewSession.folded` (`{old_id: new_id}`,
the DOI-less id always the old one; saved as `"folded"` only when
non-empty, united with the file's on save). `merge_concurrent_changes`
calls `apply_tombstones` after the three-way decision merge and the
disk additions (a disk target the session loaded and renamed is not
re-added). **Folding happens only in `sessions reconcile`; a save never
folds a decision.** `apply_tombstones` only drops an in-memory copy
under a tombstoned id that this process left untouched: unscreened,
unchanged since loaded, without a note, and no longer in the file (its
links, provider and `merge_version_of` metadata go to the target).
Every other copy stays beside its target, never copying or dropping a
decision, and is listed as foldable or conflicting for the next
reconcile. Races tested with real subprocesses in both save orders.
In the merge the tombstones run after the decision merge and before
the record merge and `supersede_merged_records`, which repoints the
links a dropped copy gave its target like all others; providers of
folded copies are united with `united_providers` (comma-joined, as
per-provider `found_by` records them). `repoint_folded_ids`
repoints snowball `source_papers` and LLM sample `paper_id`s;
`create_review_session` routes a result under a tombstoned id to its
target, unless `plausibly_same_work` rules it out (a namesake goes to
`same_id_copies`). The drop guard allows only for decided copies the file holds
under a tombstoned id that the session no longer holds.
Nothing unreconciled is silent: `foldable_copies` (counted with the
reconcile hint), `conflicting_copies` (pairs with different statuses,
plus `same_id_copies`), `alike_copies` (same status, different
tags/source: not folded, merging tags is a judgement) and
`possible_copies` (DOI-less decisions sharing an `audit_work_key` with a
DOI decision but in none of those lists) are shown by `sessions show`
(lines; foldable and possible copies counted, ids in JSON) and counted
in the report. The pairs are DOI-less/DOI copy pairs plus two decided
decisions under one id whose `decision_state` differs (`same_id_pairs`,
any id, DOI too; #215: a store re-run can leave them, see below);
conflicting if statuses differ, else alike; same state or a pending
copy: not listed; `sessions reconcile` never folds them (no other id to
fold to). Such a pair lasts (#228): `_build_previous_decision_lookup`
holds the *first* decision of an id (the returned paper attaches to
it; in #208's pairs that is the copy a search reached), the other
copies are carried through unchanged after the conversion (before it
they would be in `decision_lookup` and catch the returned paper); the
baseline keys decisions by occurrence when taken (`decision_keys`:
paper id, then `id#2`, `id#3` in session order; one decision per id =
plain ids; `decision_ids` maps key → paper id; paper states stay by
id, the registry gives copies one `Paper`). Places move, so each
decision carries its key (`ReviewDecision.baseline_key`, not saved,
`compare=False`, kept by `replace`), set by `assign_baseline_keys` at
load, after a save and for a built baseline of a session that loaded
nothing; `base_key_of(d, base)` = that key while `decision_ids[key]`
is still d's paper id, else the paper id (decisions made since,
renamed ones, a fold's survivor, which so meets the DOI copy's
baseline as before). The merge pairs via `pair_with_file` per paper
id: first our keyed copies with a free file copy in their loaded state
(among several: same `found_by` set, then same provider, then order),
then the rest by order; links, notes, paper fields and
decision changes pass only within pairs. Unpaired file copies: the
baseline's entries of the id no copy of ours carries were loaded and
are gone here (renamed/folded/dropped), matched by state first, then
by order; the rest are added. `apply_tombstones(session, base,
paired)` judges each decision under a folded id, "no longer in the
file" = unpaired; `warn_if_decisions_dropped` uses `base_key_of`.
`sessions decide` selects every decision of a `--doi`/`--paper-id`;
if any selected copies are a `same_id_pairs` pair it refuses (exit 2,
each pair named by `copy_conflict_line`, unsaved) unless
`--all-copies`; agreeing copies or a pending copy are decided together
without it. Its summary counts papers ("1 paper(s) marked kept (2
decisions)").
The report also states "Unique works" from the audit rows.
**Remaining gap**: the
pairing uses the exact title + surname hash, the audit work key is
looser (punctuation, case, year), so on the real sessions 2995 DOI-less
records share a work key with a DOI record and only 403 pair; the rest
are only counted as possible copies, deliberately not folded.
**Known limitation**: a DOI-less id is a hash of title + surname, so two
works years apart share it, and decisions, notes and the registry
cannot separate them without changing the id scheme. A session keeps
the stored paper unmerged and notes the newcomer in
`ReviewDecision.same_id_copies` (`{"year", "venue", "provider"}`,
saved only when non-empty, unioned by the concurrent merge), which
`sessions show` lists as a conflicting copy naming both years.

### Headless Review Sessions

`scholar search -n <name>` persists the search to the named review session
even without `--review`: it creates or appends (same
`create_review_session()` merge the TUI uses — search records accumulate,
prior decisions are preserved, new papers land pending). Every CLI
append is named: `--review` without `-n` names the session after its
query (`cli.nw`, `session_name = name if name else query`), so
`search q --review` appends to `q.json`, or, when that does not exist,
continues an unnamed session of query `q` in its hash file (#213, see
Session Integrity). A paper the
re-run returns again keeps its stored paper, gaps filled from the new
copy (`stored_paper_with` → `Paper.merge_with`, stored values win,
sources united; a DOI-less stored paper met by a DOI copy, found under
its legacy hash id, goes `merge_version_of(returned, stored)`: the DOI
copy keeps identity and venue/year/url, the stored one fills abstract,
keywords, sources), and the decision is kept whole
(`dataclasses.replace`, lists copied) with `united_providers(old, new)`
as provider; the duplicate, folded, renamed and adopted branches unite
the provider too (#192; before, the decision was rebuilt around the
returned copy, losing abstracts, sources and providers). Without a
session file, a decision from the old per-query decision store does
the same with the record's paper (`paper_from_decision_record`, shared
with the restore of papers not returned; it drops DBLP homonym numbers
only from a paper with a DOI, so a DOI-less record keeps the id it is
stored under and the append's renaming moves its note, #215; provider
`united_providers(record, search)`; decision fields via
`decision_from_record`), filling only when
`stored_paper_fills`: `plausibly_same_work` (left for a record under
the paper's own DOI, years apart) and ids `stored_paper_with` can
merge (equal, or a DOI-less record vs a DOI copy; a hash-keyed record
can rebuild with a DOI or a derived arXiv DOI, and then the returned
copy stands) (#194). A namesake never takes the record's decision
(#203, as `sec:session-copies` does for session files). The lookup is
`store_record_of` (own id, else for a DOI paper the legacy hash id):
a legacy-id record counts only when `plausibly_same_work` with its
rebuilt paper *without* a DOI (a hash-keyed record was decided
DOI-less; a derived arXiv DOI must not make a preprint's record
another work than its published version). One that does not is
skipped (the DOI paper is new and pending, with the links; the
restore brings the record back under its own id, no links); one that
does is taken over and not restored again (#211): the restore defers
the keys the returned papers seek (`store_keys_sought`, papers
normalised as in the conversion), the store branch notes the keys it
uses (`used_store_keys`), and after the loop every deferred key not
used is restored, so a record whose paper an earlier branch caught
(`existing`, `replaced`, ...) stands beside as its own copy for
`sessions reconcile`, never lost. A DOI-less paper whose own-id record is
not plausibly its work (`is_record_namesake`; no id comparison, since
a record can rebuild with a DOI) leaves the record's decision as the
restore makes it (`restored_decision`, added by that branch since the
restore skips returned ids) and is noted in its `same_id_copies`, no
search link. A DOI paper under its own DOI is never a namesake.
Record fields → decision: `decision_from_record` (restore too; an
unknown source string stays an `is_unknown` pseudo-member); a record
without a provider gets provider `previous`, like its paper's sources
(the restore gave `""` before).
Tests of this
path need `isolated_registry()` between runs, else `Paper.from_dict`
returns the held object and hides the loss. The save
confirmation goes to stderr so `-f json`/`-f bibtex` stdout stays pure.
`scholar sessions decide <name> --keep|--discard --doi ...|--paper-id ...
--tag ...` records decisions non-interactively; discarding requires a tag
(motivation), and if any selector matches nothing the batch aborts unsaved.
`sessions show` prints each paper's id (`doi:…`/`hash:…`, the value
`--paper-id` takes) under its title, and `show -f json` carries `doi` and
`paper_id`, so a decision never needs a CSV detour.
Each paper line is a `rich.text.Text` (`session_paper_line`; own
pieces styled, stored strings appended as plain text: no markup, no
emoji codes, no highlighter), printed `PAPER_LINES_PER_PRINT` (200)
papers per call (`print_paper_lines`, #273; 10,000 decisions: ~24 s
→ ~7 s piped). Piped text is pinned by
`TestShowPinnedOutput` (80 and 200 columns) and equals the old
per-line output except where that was wrong: stored brackets
(`open[alex]` printed `(open)`; tags `x[bold`, `a]b[c` formed Rich
tags), emoji codes (`a:b:c`) and trailing backslashes (doubled). On a
terminal numbers and URLs in titles and ids are no longer coloured.
Every other line of `print_session_details` is a `Text` too
(`print_show_line(con, *parts)`, parts as for `Text.assemble`, with
the highlighter applied as `Console.print` applies it to a string, so
terminal colours stay); no stored string goes through markup.
`--source human|agent|llm` says who decided (#162). It defaults to
`human` only when stdin is a terminal; otherwise (scripts, agents) a
missing `--source` exits 2 before loading the session. `agent` (an AI
agent's own verdict) and `llm` (a classifier's verdict relayed) store
unreviewed decisions (`ReviewSource.AGENT_UNREVIEWED`/`LLM_UNREVIEWED`,
values `agent`/`llm`) that the TUI queues for confirmation, with
`--confidence/-c 0..1` in `llm_confidence` like `llm classify`
(validated; ignored with a note for human decisions; a machine decision
without `-c` gets None, never an earlier run's number); a human `decide`
(or TUI confirm) on such a row marks it `agent_reviewed`/`llm_reviewed`
(`ReviewSource.reviewed`), with `is_example` set when the status
changed. Ask a source `is_unreviewed` / `is_machine` instead of
listing members. A machine `decide` also calls
`review.clear_machine_audit(decision)`, which sets every field named in
`review.MACHINE_AUDIT_FIELDS` to None (empty here; classifier audit
fields register there so a replaced decision does not keep the old
run's model/prompt/reason). `--keep-trace` (#245) skips that call for
`--source agent`, so an agent's correction of a (relabelled) classifier
call keeps `LLM_AUDIT_FIELDS` and the report's LLM screening section
(`first_made_by_llm`) still counts it with its model and prompt; all
other decide rules are unchanged. It needs `-c` (exit 2 before loading
otherwise: the confidence column is the current decider's, never a
kept classifier number); with `--source llm` it is refused (exit 2
before loading: a relayed verdict is a new run, and the kept trace
would be read as its); with `--source human` it is only noted (a
human never clears the trace). Nothing new is stored: `sessions show`
marks a decision whose `llm_model` is set but whose source is not
`llm`/`llm_reviewed` (`cli.earlier_classifier_trace`;
`CLASSIFIER_SOURCES` duplicates `llm_review.LLM_SOURCES` so `show`
does not import llm_review and its caches, a test keeps them equal)
with "(llm trace: earlier classifier call)" and JSON `"llm_trace":
"earlier classifier call"` (key absent otherwise). The
per-decision CSV shows the kept trace in its classifier columns (#281,
see LLM Screening Record).
**Agent reasons (#249).** `ReviewDecision` has an agent trace,
`agent_reason`, `agent_by`, `agent_decided_at` (UTC ISO), named once in
`review.AGENT_AUDIT_FIELDS` (`agent_audit_of`; load, `decision_state`,
concurrent merge and `is_unscreened` use it; the append keeps the
decision whole; saved only when set, `agent_audit_data`) and
registered in `MACHINE_AUDIT_FIELDS`, so every later machine `decide`
clears it; `--keep-trace` keeps only the LLM fields and clears the
agent's. A human decide and `sessions relabel` keep it; `sessions
reset` clears it and keeps it in `resets[-1]["trace"]`. `decide
--source agent --reason TEXT [--by NAME]` gives every selected record
that reason, `--by` (None if not given, never guessed) and one
`utc_now_iso()` per run. `--reasons-file F` (lines
`ID<TAB>REASON[<TAB>CONFIDENCE]`; ID = session paper id, else a DOI
bare or `doi:`, `cli.decisions_named_by`, no `https://doi.org/`
links, as for `--doi`; blank/`#` lines skipped; an empty third column
= none; no tabs in a reason, a 4th column is refused naming each extra
column; not quoted, not CSV: quote marks are stored as written; read
as `utf-8-sig`, so a BOM is dropped; lines end only at `\n` (a `\r`
before it is dropped), so U+2028, NEL, form feed stay in the reason
and error line numbers match an editor) is the selection (exit 2 with `--doi`/`--paper-id` or
`--reason`); its confidence overrides `-c` per line, and with
`--keep-trace` and no `-c` every line needs one. Usage errors (exit 2,
before loading): `--reason`/`--reasons-file`/`--by` with `--source
llm` (the classifier's reason is `llm classify`'s), `--reason`/
`--reasons-file` with `human` (out of scope; `--by` alone is accepted
for a human since #257, below), `--by` alone for an agent, any bad file line (all named:
`cli.parse_reasons_file`), empty or > `review.MAX_AGENT_REASON_CHARS`
(2000, stripped, never truncated) reason. After loading: an unknown id
exits 1 (like `--doi`), one paper given two different reasons or
confidences exits 2, both unsaved. `--source agent` without a reason
warns on stderr and records the decision. Shown in `sessions show`
(a `reason (by): …` line, cut at `SHOW_REASON_CHARS` = 160; JSON:
the three fields, `null` when unset), the per-decision CSV (three
columns after the classifier's, before the human record's;
`paper_id` stays last) and the report (one English sentence after
the summary, `agent_reasons_sentence`: agent and agent_reviewed
decisions with/without a reason). An older Scholar loads such files
and drops the fields on its next save (checked with the installed
pre-#249 pipx build).
**Batch ids (#292, cli.nw `sec:batch-ids-in-files`,
`sec:batch-against-sheet`, `sec:sheet-batches`; review.nw
`sec:stored-batches`).** `agent_batch` is the 4th field of
`AGENT_AUDIT_FIELDS` (so load, save-when-set, `decision_state`, merge,
`is_unscreened`, `clear_machine_audit`, the reset trace, `show -f
json`, and the CSV column right after `agent_decided_at` all handle it;
not in the text listing). A screening has key `batch` (in
`SCREENING_KEYS` after `sample_id`, `new_screening(batch=)`; a
snapshot takes `agent_batch` via `SNAPSHOT_FIELDS`/`verdict_screener`
for agent verdicts). `parse_tab_file` entries are 4-tuples `(line, id,
values, batch)`: a comment line `# batch: ID` (`BATCH_LINE`, `batch`
any case) gives the lines after it that id until the next one (several
batches concatenated; lines before the first: None); `ReasonLine`/
`VerdictLine.batch`. `read_batch_id`: white space collapsed, empty or >
`MAX_BATCH_ID_CHARS` = 100 → bad line (exit 2). Free text, never
checked against a manifest. `decide --batch ID` (needs `--reason`/
`--reasons-file`, exit 2) and `screen --batch ID` give the id to a
run without batch lines; with a file that has them exit 2
(`lines_with_batch`). The incoming batch check also runs per named
batch (`<<check each batch the file names>>`, `rows_by_batch`, "In batch
ID (n rows):" lines; skipped when one batch holds every row;
`without_repeated_reasons`: a shared reason (`BatchFinding.reason`)
is reported once, under the batch when its count equals the file's,
else in the file's line with ", k of them in batch B"); `--strict`
refuses on any. `--sheet FILE` (repeatable, both commands; decide needs
a reason option): `read_screen_sheets` (comment/blank lines and an `id`
header skipped, first column = id; no id, two batch lines, unreadable →
exit 2 before loading); `compare_with_sheets` matches the sheet's batch
rows (one sheet: all rows when it has no `# batch:` or the rows name
no batch; several sheets must each have a distinct batch id, else exit
2 before loading) by `decisions_named_by`; rows no sheet takes are
`SheetCheck.uncompared` ("N row(s) of batch X / with no batch id were
not compared with any sheet", refused under `--strict` as
`sheet_uncompared`);
stderr "NAME (batch B): returned R of N; M missing: …", "K id(s) not on
the sheet: …", "Missing rows are fine …"; ids not on the sheet set
`sheet_extras`, refused under `--strict` in `<<check the batch as a
whole>>`. `sessions reset --batch ID` (repeatable, `read_batch_id`;
alone or narrowing like `--source`) selects decisions by
`agent_batch`, never screenings; an id no decision carries is a stderr
note (a reset clears it). `stored_batch_check` → also
`StoredBatchCheck.batches` (`stored_batches`: rows with a batch id per
(what, kind, name, batch), `batch_findings` whole, confidence included,
one-reason runs NOT pooled; `stored_batch_findings`: a batch whose rows
all share one reason over >= `SHARED_REASON_MIN_RECORDS` works gets one
`one-reason` note "one reason for all N records of batch X: a rule given
with --reason, or the same reason on every line", no flat finding;
fewer works: nothing); `check-batches` lists them ("Stored
batches …: N, …; k with findings", `BATCH_CONFIDENCE_NOTE` on a flat
one: a `-c` for a whole run looks the same), JSON `batches`. The
installed pre-#292 pipx build (no screenings) drops `agent_batch` and
the screenings on save (checked); a build from main before #292 keeps
a screening's `batch` (dicts kept verbatim, `list(dec_data.get(
"screenings"))`, read) and drops only `agent_batch`.
**Quote check (#256, review.nw `sec:reason-quotes`, cli.nw
`sec:decide-quote-check`).** Pure functions: `quotes_in_reason`
(text between double marks `"…"`, `“…”`, `”…”`, `„…“`/`„…”`, `«…»`,
`»…«`; never single marks, apostrophes; a straight `"` right after a
letter or digit opens nothing: `5" disks`), `unmatched_quotes(reason,
paper, extra_texts=())` (quotes of >= `MIN_QUOTE_WORDS` = 3 words,
shorter = "not checked", never matched; compared with title, abstract
and the extras after `normalized_for_quotes`: `clean_metadata_text`,
then tag-like markup it leaves (`<jats:italic>`, `</jats:p>`:
`QUOTE_TAG`, a letter-initial name of letters, digits, `:`, `-`, only
`name="value"` attributes), NFKC, soft hyphens and quote marks of every
kind (single and apostrophes too) removed on both sides, dashes
unified, casefold, white space collapsed; `exam- ple` not repaired;
accents (`naive`/`naïve`) and LaTeX math not folded, so reported; an
ellipsis `…`, `...`, `. . .`, `[...]`, `(...)` splits into parts found
in order in one text; edge punctuation ignored; parts at word bounds;
nothing fuzzy),
`reason_quote_checks(decision)` (one `ReasonQuoteCheck` per
`agent_reason`/`llm_reason`, with `short` = quotes too short to
check), `quote_check_tally` (per kind: reasons, checked, unmatched
counted in reasons; `short_quotes` in quotes), `unmatched_quotes_of`.
Nothing stored; computed when shown. Limits: an abstract replaced
since (enrich) no longer matches; the classifier saw only
`MAX_ABSTRACT_CHARS`; `--full-text` passages are not stored (only the
run checks them); a found quote is the record's words, not a right
decision. `decide --reason/--reasons-file` checks each reason against
its own record after the ids resolve, before saving: stderr
`line N, ID: "quote"` (or `ID: "quote"` for `--reason`), first
`QUOTE_PROBLEMS_SHOWN` = 20, rest counted, saved anyway;
`--strict-quotes` refuses unsaved (exit 2), and without a reason
option exits 2 before loading. Bad file lines (exit 2 before loading):
a reason that is only a number or a paper id (starts with `doi:`,
`hash:` or `10.` and holds no white space; `reason_column_shift`), one
with no letter or digit (`-`, `...`), and a placeholder
(`is_placeholder_reason`: casefolded, letters/digits only, in
`REASON_PLACEHOLDERS` = placeholder, todo, tbd, xxx, reason, na), the
last two also for `--reason`. `sessions show`: a "Reasons: N recorded,
X with quotes checked, M with a quote not found in the record's title
or abstract" line when any machine reason exists, a mark `(quote not
in title or abstract)` on those papers, JSON `unmatched_quotes` per
decision (absent when empty) and top-level `reason_quotes` (per kind:
reasons, checked, unmatched, short_quotes; absent without machine
reasons, so such a session's JSON is as before). Report: `reason_quotes_sentence` after
`agent_reasons_sentence` (agent and classifier apart; none without
machine reasons). Audit table and CSV unchanged. Cost: one check per
decision per command (folding the abstract is most of it; ASCII and
single-space shortcuts in `normalized_for_quotes`, tested against the
plain definition; a review measured 30,000 decisions with two reasons
each at 3.0-4.4 s CPU under heavy load; the 10,000-decision test's 8 s
CPU limit guards against the ~10x slower `str.translate` folding, it
is no performance promise).
**Batch check (#291, review.nw `sec:batch-check`, `sec:stored-batches`,
`sec:batch-calibration`; cli.nw `sec:decide-batch-check`,
`sec:sessions-check-batches`).** `batch_findings(rows, one_reason=False,
confidence=True)` over `BatchRow(paper, title, reason, confidence,
status, tags)` (the confidence is the row's own column, never `-c`)
returns `BatchFinding`s (`kind`, `count`, `rows`, `papers`, `detail`,
`information`): one `shared-reason` per reason (white space collapsed +
casefold only, punctuation and templated ids kept: a known limit,
stated in the prose) given to >= `SHARED_REASON_MIN_RECORDS` =
10 records with different titles (titles folded to letters/digits, so
copies count once), whatever the batch size, most records first,
detail "shared by N records with different titles (M rows): \"…\""
(`shared_reason_findings`); then `flat-confidence` (every row with a
confidence has the same one, >= `FLAT_CONFIDENCE_MIN_ROWS` = 20; no
exception for high values, unlike the external ~100-row validator's
>= 0.9: a range is not flat, a default "off topic" at 0.95 would pass).
`one_reason=True` (one `--reason` for many records) gives only
`one-reason`, `information=True`, never refused. No share-of-batch
condition and no run check any more (2026-11-20 calibration on copies
of nine sessions of one project, in the prose as a table, anonymised
A–I: honest reasons shared by <= 7 records, defaulted >= 13; stored
runs merge many screeners' batches, 275 rows were 9 % of a 3,007-row
run; a run of 10 identical rows is a shared reason of 10, so the run
check only duplicated it). Runs in `sessions decide`
(`--reasons-file`/`--reason`, agent only) and `sessions screen`
(`--verdicts-file`/`--reason`) after the quote check, before saving
(`<<check the batch as a whole>>`, reads `trace_of`, `reason`,
`selected`, `by_id`, `by_doi`, `quote_misses`, `strict`, `saving`):
stderr lines with the first `BATCH_PAPERS_SHOWN` = 5 ids and "…and k
more", saved anyway. `--strict` (both commands; needs a reason/file,
exit 2 before loading) refuses unsaved, exit 2, on any non-information
finding OR any quote miss; `--strict-quotes` unchanged (refuses on
quotes before the batch check prints). The quote check's "Saved all
the same; --strict-quotes or --strict refuses" line prints only when
`saving and not strict`. **`sessions decide --dry-run`**: every check
and refusal with the real exit codes, records in memory only, prints
"Would mark N paper(s) kept|discarded by SRC in session 'x'; nothing
written." (`<<report or save the decisions>>`), never saves (decide
keeps no pre-run copy anyway). **`scholar sessions check-batches S
[-f table|json]`**: read-only, exit 0; `review.stored_batch_check` →
`StoredBatchCheck(shared, runs)`: runs group decisions with an
`agent_reason` by (`agent_by`, `agent_decided_at`) and screenings with
`origin` "screen" (snapshots left out) by (kind, name, `recorded_at`);
a run of two or more works (title keys) whose rows all share one
reason gets a `one-reason` note and counts as ONE pooled record (a row
keyed by the run, "run of N (agent NAME, TIME)"), so a rule applied to
50 records counts once while the same reason across runs adds up; a
one-row run is an ordinary row (a per-record `decide --paper-id X
--reason R` loop adds up); the text adds `ONE_REASON_RUN_NOTE` (a file
with one reason on every line is a shared reason at decide/screen time
and `--strict` refuses it); shared reasons are looked for
session-wide over the pooled rows, agent reasons and screening reasons
apart (`shared["agent decisions"]`, `shared["screenings"]`), since a
stored run is neither a screener's batch nor a superset of one; flat
confidence is not judged from runs, only per stored batch id (#292,
above). Text:
counts line, session-wide shared reasons, runs with one reason, stored
batches, then what a stored run is and that flat confidence is judged
per batch only. JSON:
`shared_reasons`, `runs`, `batches`, `flat_confidence`. The help states the
thresholds (a test ties them to the constants).
**Records decided without an abstract (#293, review.nw
`sec:abstract-lookup`, enrich.nw `sec:enrich-lookup-record`, cli.nw
`sec:decided-without-abstract`).** `ReviewDecision.abstract_lookup`
(dict or None): what `scholar enrich` found the last time it asked for
the paper's abstract, `{"at", "outcome", "asked", "failed"}` (last two
only when non-empty; outcome in `ABSTRACT_LOOKUP_OUTCOMES` = found,
none-found, failed, no-doi, none-asked, from
`enrich.abstract_lookup_outcome`, which `tally_lookups` now uses too).
Set only by `scholar enrich` per chunk, when `abstract` is in
`--fields`, for papers that lacked an abstract before the chunk and
have an outcome (`abstract_lookup_record`); one time per chunk; latest
attempt only. Saved only when set, loaded None from old files (non-dict
→ None), copied on append, concurrent merge keeps the later `at`
(`later_abstract_lookup`), a fold keeps the DOI copy's; NOT in
`decision_state` or `is_unscreened` (as `abstract_set`). `abstract_gap(
decisions)` → `AbstractGap(papers, without, none_found, failed,
not_asked, no_record, doubtful)`, one per paper id; a `found` record on
a paper without an abstract, an unknown outcome, or no record →
`no_record` ("no record of a lookup", never "never looked up").
`doubtful` counts papers with an abstract that `abstract_doubt`
(#287; never a hand-given text) doubts; the warning line, the
`sessions show`/report sentence (", and d on a doubtful one") and the
JSON (`doubtful_abstract`) include it, and the enrich hint is given
for doubtful ones too. Beside `abstract_fetched` (#287: which source
supplied the stored text, digest-checked, one entry per abstract
stored), `abstract_lookup` says when enrich last asked and what came of
it: enrich judges `not hand_given_abstract(d)` papers, a judged
doubtful abstract counts as lacking (`needs_enrichment(..., judge)`),
and `abstract_lookup_record(..., judge_abstract=)` gives `found` when
a source replaced it, else the sources' outcome. One stderr line
(`cli.print_abstract_gap`/`abstract_gap_line`) after `sessions decide
--source agent|llm`, `sessions screen --as agent|llm` (both also on a
dry run, "selected"), `llm classify` and `--second-screen`: "k of the n
records decided have no abstract (parts); run `scholar enrich S
--pending-only --fields abstract` first if that has not been tried."
(hint only with failed, no-record or doubtful parts; `--pending-only`
only where the records stay pending: dry run and `sessions screen`,
not after a real decide, classify or second screen; has/have and
record/records agree with the counts; S via `session_argument`,
shell-quoted). `sessions show`: `decided_without_abstract_sentence`
line (also the report's sentence, after the hand-abstract count), JSON
`abstract_lookup` per decision and top-level
`decided_without_abstract` (both only when present).
A machine
`decide` never replaces a decided
paper whose source is `human`, `llm_reviewed` or `agent_reviewed`:
the batch is refused unsaved (exit 2, each conflict named) unless
`--force`. When `decide` changes a record's status, only its old
category tags (`AUDIT_CATEGORIES`) are dropped before the new `--tag`s
are added (`review.tags_after_status_change`, #177); themes,
motivations and notes stay (dropping motivations lost themes on
keep→discard→keep). Same status: tags append as before, except that a
`--tag` in `AUDIT_CATEGORIES` also drops the old category tags (#195,
`review.tags_after_decision`: a record holds one category).
`--untag TAG` (repeatable) removes tags first, from every selected
record (machine sources too; the `--force` guard is unchanged); a tag
no selected record had is named once on stderr, not an error. A discard
still needs a `--tag` on the command line. More than one category among
the `--tag`s is refused (exit 2, before the session loads). `--untag` is
part of a decision (needs `--keep`/`--discard`): a machine untag without
`-c` clears `llm_confidence` and the audit fields (pass `-c` again), and
a human untag of an unreviewed agent/LLM decision marks it `*_reviewed`.
**Unknown stored sources** (e.g. `manual`, which no Scholar version
wrote, or a hand-edited `Agent`) load as `ReviewSource` pseudo-members
via `_missing_` (`is_unknown`; value kept verbatim on save), count as
unreviewed (never cited, not in `example_papers`, queued in the TUI;
a human review makes them `human`), are shown as "unknown source
'<value>'", and are warned about once per file and process
(`warn_about_unknown_sources`).
**Old installs:** a Scholar older than this change reads `agent`,
`agent_reviewed` (and any unknown source) as `human` and writes that
back on its next save. Reinstall every scholar installation (pipx,
other venvs) before anyone uses `--source agent`.
Who decided is shown everywhere decisions are counted (#163): the
LaTeX report (summary "Decided: <source>" rows, abstract sentence,
"(agent, unreviewed)" marks in the paper lists and overview table),
`llm synthesize` (both formats' summary), `sessions show` ("Decided
by:", marks after titles; JSON `source` per decision and
`decision_sources`), `llm status` (Agent rows) and the export's
confirmed/changed table (`machine_review_rows`, LLM and agent apart).
Labels come from `review.DECISION_SOURCE_LABELS` /
`decision_source_items` (decided papers only).
**Correcting a source** (#216): `scholar sessions relabel S --from SRC
[--from ...|a,b] --to agent|llm (--doi D ...|--paper-id ID ...|--all)
[--dry-run] [--note TEXT] [--by TEXT]` changes the source of decided
papers whose stored source is a `--from` value (pending papers never),
via `review.relabel_source`: status, tags, confidence,
`LLM_AUDIT_FIELDS`, `found_by`, provider stay; no `clear_machine_audit`.
`is_example` ("a human changed the machine's verdict") is cleared and
its old value stored in the record: left set, it counted as a training
example (`llm status`, `example_papers`, TUI filter), sorted first
under `--include-llm-examples`, and made a later unchanged human
confirmation read as "changed" (`machine_review_rows`, CSV).
`mark_as_reviewed` now sets `is_example = not user_agrees`, so no
stale flag survives a confirmation.
Targets are `review.RELABEL_TARGETS` (the `is_unreviewed` members):
`human`, `llm_reviewed`, `agent_reviewed` claim a human's confirmation
and exit 2 (a human confirms in the TUI or with `decide --source
human`). An LLM call an agent (not a human) confirmed becomes `agent`,
not `agent_reviewed` (that means agent proposed, human confirmed); its
LLM trace stays as provenance, and the report's LLM screening
sentence still counts it (`llm_review.first_made_by_llm`: an LLM
source, `llm_model` set, or a relabel record from an LLM source). Usage
errors exit 2 before loading (`--to` in `--from`, neither or both of
`--all` and selectors, an unknown `--from` no decision holds); an
unmatched selector exits 1 unsaved; a selected paper that is pending
or has another source is named and skipped. A selector takes every
decision of the paper. Prints `from -> to: N` counts; `--dry-run`
writes nothing (no copy). Otherwise `keep_copy_before_run(session,
"pre-relabel")`, one `_utcnow()` time for all records, `save_session`.
Each decision records `ReviewDecision.relabelled`
(`[{"from", "to", "at", "note", "by", "is_example"}]`; `by` only as
given, never guessed; `add_relabel` once each, kept sorted by `at`,
ties in insertion order): saved
only when non-empty, old files load `[]`, kept by the append copy,
united by `merge_concurrent_changes` (after `mine =
decision_state(...)` is taken, since the list is part of
`decision_state`: otherwise the union would read as a local change and
a stale process would keep its old source). Shown by `sessions show`
(`cli.relabel_mark` on the last record: "(relabelled from human)", or
"(relabelled from llm to agent, now llm)" when the source differs from
its `to`; JSON `relabelled` when set) and the CSV column
`source_relabelled` (`from->to time [by NAME]; ...`, before
`paper_id`).
A Scholar from before this loads such files but drops the list on its
next save (checked under 528d933).
**`scholar sessions reset S (--doi D|--paper-id ID|--source SRC|--all)
[--dry-run] [--note TEXT] [--by NAME] [--all-copies]`** (#248, cli.nw
`sec:sessions-reset`, review.nw `sec:reset-decision`) sets decided
papers back to pending so a flawed screen can be redone in place
(`llm classify` takes pending papers only) without re-running the
searches. `review.reset_decision(decision, at, note, by)`: status →
pending, tags → [], `llm_confidence` → None, `clear_machine_audit`,
`is_example` → False, source → `human` (the default of an undecided
paper; a pending `llm` would still get "(LLM, unreviewed)" from
`unreviewed_mark`); paper, provider, `found_by`, `same_id_copies`,
`relabelled`, records, rounds, samples, context untouched. Only
unreviewed sources (`agent`, `llm`, unknown stored values) can be
reset; `ValueError` otherwise. History in `ReviewDecision.resets`
(`[{"at", "status", "tags", "source", "llm_confidence", "is_example",
"trace", "note", "by"}]`; `trace` = the non-None fields of
`MACHINE_AUDIT_FIELDS` read at call time, so newly registered audit
fields are kept, omitted when empty; `add_reset` once each, sorted by
`at`), persisted exactly like `relabelled` (saved when non-empty, old
files `[]`, append copy, merge union after `mine`, in
`decision_state`); checked: bc8ec8c loads such a file (as pending) and
drops the list on save. A reset paper is not `is_unscreened`, so
reconcile never folds it away. CLI: `--source` is repeatable/comma
list, alone it selects every decision with that source, with
`--doi/--paper-id/--all` it narrows; one form required, `--all` with
explicit selectors refused (exit 2), unknown `--source` nobody holds
exit 2; unmatched `--doi/--paper-id` exit 1 unsaved; a `--source`
that matches nothing is not an error (a second run finds 0). Excluded
and pending papers selected by id are named and skipped. Any selected
`human`/`llm_reviewed`/`agent_reviewed` decision refuses the batch
(exit 2, unsaved, first `RESET_REFUSAL_NAMES` = 20 named, the rest
counted by source; no `--force`, leave them out with `--source`).
Copies decided apart (`same_id_pairs`) need `--all-copies`. Prints
`status by source: N`; `--dry-run` writes nothing (refusals still
apply); else `keep_copy_before_run(session, "pre-reset")`, one
`_utcnow()` time, `save_session`. Shown by `sessions show`
("(reset from discarded by llm)", `cli.reset_mark`; the relabel mark
is hidden on a still-pending reset paper and when the last relabel is
older than the last reset, `relabel_after_reset`; JSON `resets`) and
the CSV column `reset_from` (`status by source time [by NAME]; ...`,
after the agent-trace and human-record columns, before
`abstract_from`). Effects: audit table and
report show pending; a sampled decision reset at or after the draw
is gone from the sample (see Samples: `reset_since_draw`);
`first_made_by_llm` is False for any pending
paper; after a full reset the classifier vocabulary (tags of decided
papers) is empty, so pass `llm classify --tag`.
**Human review record (#257, review.nw `sec:human-review-record`).**
`human` is the dataclass default and needed no evidence, so scripts
writing through the API gave >1000 decisions a human source nobody
gave. `ReviewDecision` now has `human_decided_at` (UTC ISO),
`human_decided_via` (`tui` | `decide`, `HUMAN_DECISION_CHANNELS`) and
`human_by` (as given, never guessed), named once in
`review.HUMAN_AUDIT_FIELDS` (`human_record_of`; load, save only when
set via `human_record_data`, `decision_state`, concurrent merge,
`is_unscreened`; the append keeps the decision whole). NOT in
`MACHINE_AUDIT_FIELDS` (so not cleared by `clear_machine_audit`, not
in a reset's `trace`). Set only by `review.record_human_decision(d,
via, by=None, at=None)` (raises unless decided with a source in
`REVIEWED_BY_A_HUMAN` = human/llm_reviewed/agent_reviewed; `at`
defaults to `_utcnow`), called by the TUI's keep/themes/discard/confirm
in both screens (after `mark_as_reviewed`; `by=app.reviewer`, set by
`sessions resume --by` or the blind-mode name dialog, else None) and by `sessions decide`
with a human source (`--source human` or the terminal default; one
`utc_now_iso()` per run; `--by NAME` now accepted with human). The
API (`ReviewDecision(source=HUMAN)`, `mark_as_reviewed` alone) sets
nothing. A machine `decide` (with `--force` over a human/reviewed
decision) calls `clear_human_record`; `relabel_source` clears it and
keeps the set fields as `"human"` in its relabel record (key absent
without a record); a reset only takes unreviewed decisions, which have
none; a later human decision overwrites it (time included). Counted by
`human_record_counts(decisions)` (decided papers with
`human_decided_at` per `REVIEWED_BY_A_HUMAN` source) and
`decision_source_rows(decisions, always_note=False)` → `(label, count,
note)`, note "(k with a record of the review)" on those sources' rows
with a count, when `always_note` or any such decision lacks a record
(`source_row_text(count, note)`). `sessions show` "Decided by:" always
notes (`human: 1200 (0 with a record of the review)`), JSON adds the
three fields per decision (`null` when unset) and `review_records`
(counts by stored value); the report's "Decided:" rows, its abstract
sentence (`decision_sources_sentence`) and `llm synthesize`'s summary
note only when a record is missing, so a fully recorded session reads
as before; with the note they also give `REVIEW_RECORD_EXPLANATION`
once (`review_record_sentence`: after the report's summary, in its
abstract, after both synthesis summaries; no version or date in it).
The CSV adds `human_decided_at, human_decided_via,
human_by` after `agent_decided_at`. The audit table and its caption
are deliberately unchanged: they neither count nor mention the
records (tested byte-identical). Copies are compared by
`decision_verdict` (= `decision_state` without `HUMAN_AUDIT_FIELDS`;
LLM/agent fields stay in) in `_fold_direction`, `same_id_pairs` and
`_decided_pairs` (alike/conflicting), so two copies a human decided
alike at two moments still fold, are no alike pair and need no
`--all-copies`; a fold keeps the newer record (`newer_human_record`:
by `human_decided_at`, a record beats none; the fold also carries both copies' `abstract_set` records). `decision_state` (merge,
baseline, `pair_with_file`, `apply_tombstones`) keeps the record: those
compare one decision with itself across file versions. Wording: "without a record of the
review", never "not human" (old decisions have none). The default
source stays `human` (an undecided paper's). Checked 2026-11-20: the
pipx build of 4ba7a23 loads such a file and drops the fields on save.
**`scholar sessions set-abstract S (--paper-id ID | --doi D) --file F
--from TEXT [--by NAME] [--replace] [--dry-run]`**, or `--abstracts-file
F` (lines `ID<TAB>FROM<TAB>ABSTRACT`, split at the first two tabs, so
tabs inside the abstract become spaces; fewer than three columns
refused; the `--reasons-file` conventions: `utf-8-sig`, lines end at
`\n`, blank/`#` skipped, ID = paper id or DOI bare/`doi:`;
`cli.parse_abstracts_file`, every bad line named, exit 2 before
loading) (#258, cli.nw `sec:sessions-set-abstract`, review.nw
`sec:set-abstract`) stores an abstract found by hand. `--file -` reads
stdin (a BOM is dropped, as `utf-8-sig` drops it from a file); `--from`
is required. `review.set_abstract(decisions, text, origin, at, by,
replace)` cleans the text (`clean_abstract_text` = `clean_metadata_text`
+ white space collapsed; empty → exit 2; above `LONG_ABSTRACT_CHARS` =
10,000 only a stderr warning), sets `paper.abstract` on every decision
holding the paper (one registry `Paper`) and records on each decision
`ReviewDecision.abstract_set` = `[{"at", "from", "by", "chars", "text",
"previous"}]` (`text` = the stored text, kept so that a replaced hand
text survives somewhere; `previous` only when an abstract was replaced;
`by` None unless given). A paper with an abstract is refused (exit 2,
each named, unsaved) unless `--replace`; an unmatched selector exits 1
unsaved; two batch lines giving one paper different texts/origins exit
2. A possible or foldable copy (`cli.possible_twins` over
`possible_copies` / `foldable_copies`, both directions) gets a stderr
note naming it and `sessions reconcile`, plus a second note when the
paper has no DOI and the copy is a DOI record with an abstract (a fold
keeps that one); the abstract is still set. `--dry-run` writes
nothing; else `keep_copy_before_run(session, "pre-set-abstract")`, one
`_utcnow()` time, `save_session`. The record is on the decision, not
on `Paper` (no new paper-merge rule): saved only when non-empty, old
files `[]`, kept by the append copy (stored abstract wins via
`stored_paper_with`), united in `merge_concurrent_changes`, but **not**
in `decision_state` (it changes no decision: in the state, a
`set-abstract` save would put a stale pending decision back over a
decision another process saved meanwhile; tested). An older Scholar
(checked with the pipx build, which has no `abstract_set`, on a file
whose records hold `text`) keeps the abstract and drops the list on
its next save. Not part of `is_unscreened` either, so a pending copy
with a hand abstract still folds; the fold (`reconcile_copies` and
`apply_tombstones`) always carries a copy's records, texts included,
to the survivor (`abstract_records_after_fold`), with a WARNING when
the survivor kept its own abstract. The abstract itself follows the
#206 paper merge, plus two rules in `<<settle the abstract against the
file's hand records>>` (records apart, `mine_new`/`their_new`, taken
before the union): the file holds a hand record we lack whose `text`
is the file's abstract and we added none → the file's abstract wins
over ours (a stale enrichment never erases a hand text); we added a
hand record and the file's abstract (not None) differs from the loaded
one and ours → our text stays, and our newest record gets the file's
abstract as `previous` (what `--replace` would have kept). Both races
tested in real subprocesses, both save orders (`TestHandAbstractRaces`).
`enrich` never replaces a hand abstract (`needs_enrichment`,
`merge_with` keep stored values; tested), but a **preprint adoption**
takes the preprint's own abstract (`preprint._adopt`).
`hand_abstract_replaced(d)` (last record's `text` != the paper's
abstract; a record without `text` compared by `chars`) then makes
`sessions show` add ", since replaced" and the report not count it. The
DOI-less hash id does not move (title and author only; tested). Shown
by `sessions show` ("(abstract added by hand, from <from>)",
`cli.abstract_mark`; JSON `abstract_set` when set, the records whole,
`text` included: it is the record, and hand abstracts are few), the
report (`hand_abstracts_sentence`, one English sentence counting
papers, nothing when zero) and the CSV column `abstract_from` (`from
time [by NAME]; ...`, no text, `review.abstract_from_cell`, after
`reset_from`, before `paper_id`). The audit table is unchanged.
**`scholar sessions retire-search S (--query Q [-p P] [--filters-like
T] | --record ID ... | --all-failed-outright) [--undo] [--dry-run]
[--note T] [--by N]`** (#275, cli.nw `sec:sessions-retire-search`)
marks search records retired (record and links stay). `--record`
takes the ids `sessions show` prints ("  [3fa9c1e] s2: q", escaped
for Rich; JSON `id`), each a unique prefix of at least 4 characters
(`RECORD_ID_MIN_PREFIX`; shorter exit 2, ambiguous exit 2 naming the
records, unknown exit 1, all checked before exiting); `--query` is
exact and never matches a merged record (`q | q`), a match with
different filters keys exits 2 naming them unless `--filters-like`
(substring of the flags as `show` prints them, limit included) or
`--record`; same filters on several providers are retired together;
`--provider`/`--filters-like` need `--query` (exit 2); unmatched
`--query` exits 1 unsaved; a blank `--note` exits 2;
`--all-failed-outright` (`failed_outright`) matching nothing is not
an error. Already retired (or, with `--undo`, current) records are
named and left alone. `--undo` refuses `--note`/`--by` (exit 2).
Otherwise like reset: `open_session_argument`, `--dry-run` writes
nothing, `keep_copy_before_run(session, "pre-retire-search")`, one
`_utcnow()` per run. `sessions show` heading "Queries by provider: N
current, M retired" (only when any is retired), line suffix
"(retired <date>: note)", JSON `retired` when set.
Together these let scripted/agent-driven systematic reviews produce the same
session record and `sessions export` audit trail as TUI reviews.
#### Screenings: a second screener's verdicts (#253, part A)

`ReviewDecision.screenings` (review.nw `sec:screenings`, declared after
`abstract_set`) holds other screeners' verdicts beside the decision,
which stays the outcome; nothing reads the list to decide kept/cited.
Each record has every key of `review.SCREENING_KEYS` (`id` uuid4 hex,
`origin` screen|decision, `kind` llm|agent|human, `name`,
`confirmed_from`, `confirmed_name`, `status` kept|discarded, `tags`,
`confidence`, `reason` whole, `at`, `recorded_at`, `prompt_version`,
`abstract_truncated`, `blind`, `blind_basis` prompt|tui|declared,
`sample_id`, `batch` (#292), `via`), built by `new_screening` (validates) or
`decision_snapshot`. `record_screening(decision, record)` first adds a
snapshot of a *decided* paper's current verdict (`origin: "decision"`,
`via: "snapshot"`) unless a counted snapshot with the same
`_snapshot_key` (status, tags, kind, name, confirmed_*, at) exists;
pending papers get none. Snapshot screener (`verdict_screener`):
unreviewed llm/agent → kind llm/agent named by `llm_model`/`agent_by`
with its confidence, reason, time; `human`/`llm_reviewed`/
`agent_reviewed` → kind `human`, `name` = `human_by`, `at` =
`human_decided_at`, `confirmed_from` llm/agent/None, `confirmed_name`
model/`agent_by` (no machine confidence or reason); unknown source →
all None. `counted_screenings` = valid entries (`is_valid_screening`:
dict with `id` and kept/discarded status), not marked `set_aside_at`,
recorded strictly after the last reset's `at`; malformed entries are kept verbatim, skipped, one
WARNING per file (`warn_about_malformed_screenings`).
**Not in `decision_state` nor `decision_verdict`** (on purpose, unlike
`resets`): in the state a stale `screen` save would put an old decision
back over a human's (#258's finding); in the copy comparison a
screening would keep copies decided alike apart (#257's finding).
Instead: saved only when non-empty, loaded `[]`, copied by the append,
united by `unite_screenings` in `merge_concurrent_changes` and in the
fold (`<<fold [[absorbed]] into [[survivor]]>>`), which drops a second
snapshot of a verdict already held under another id. `add_screening`
dedups by `id`; two versions of one id become `merged_screening` (the
later `relabelled_at`'s, with the earliest `set_aside_at` of either).
`is_unscreened` requires no screenings. Not in `MACHINE_AUDIT_FIELDS`.
`relabel_source` (via `correct_relabelled_snapshots`) replaces the
screener fields of every counted snapshot of the old verdict with the
new `verdict_screener`, stamps `relabelled_at`, keeps the replaced
values under `before_relabel` (the first relabel's), and records the
old kind as `screenings_kind` in the relabel record (only when one was
corrected). `reset_decision` keeps the list and records
`"screenings": n` (the counted ones it saw) in the reset record when
n > 0. **Races** (`ConcurrentHistory.of(ours, theirs)` before the
union, `settle_concurrent_screenings` after the decision is merged, in
`merge_concurrent_changes`; the loop no longer `continue`s past it):
screenings one side added while the other side added a reset get
`set_aside_at` = that reset's `at`; snapshots one side added while the
other relabelled are corrected from `relabelled_verdict_keys` (undoes
the relabels: `from` source plus the record's `human`). The reset
record's count is not changed afterwards. Tested with real
subprocesses in both save orders (`TestScreeningRaces`). `screenings_summary`
gives `sessions show`'s line ("Screenings: N on P paper(s), S of them
snapshots of the decision; K set aside by a reset; M malformed,
skipped."); `show -f json` adds `screenings` per decision when
non-empty. Checked: the pre-change pipx build (1.29) loads such a file
and drops the list on save. Size in indented JSON: ~670 bytes per
screening, ~690 per snapshot, plus reasons.
**`scholar sessions screen S --as agent|human|llm --by NAME
(--verdicts-file F | (--doi D|--paper-id ID)... --keep|--discard
[--tag T]... [--reason TEXT]) [-c C] [--blind|--not-blind] [--sample
ID] [--all-copies] [--dry-run] [--strict-quotes] [--strict]`** (cli.nw
`sec:sessions-screen`): `--as` defaults to human at a terminal, else
exit 2; `--by` required for every kind (exit 2 before loading; the
model for llm); a screener whose `(kind, name)` is that of a selected
decided paper's `verdict_screener` is refused (exit 2, unsaved, papers
named: a change of mind is a `decide`; self-agreement is not computed
and a second record under one identity would hide the first); `-c`
refused with `--as human` (also file confidences). Verdicts file lines
`ID<TAB>kept|discarded<TAB>TAGS<TAB>REASON[<TAB>CONFIDENCE]` (TAGS
comma-separated, may be empty for a keep): parsed by `parse_tab_file`
with `VERDICTS_LAYOUT`; `parse_reasons_file` is the same function with
`REASONS_LAYOUT` (`TabFileLayout`/`TabFileColumn`: a column spec, same
line rules, `read_reason_column` applies #256's placeholder and
column-shift refusals). A discard needs a tag; at most one category.
Session uses categories (any decision tag in `AUDIT_CATEGORIES`) →
agent/llm verdicts need exactly one category fitting
`STATUS_CATEGORIES` (exit 2, lines named); human verdicts free.
Unknown ids exit 1, two different verdicts for one paper exit 2,
copies decided apart need `--all-copies`, `--sample` must be a
`sample_id` or a banded sample's `criteria["stratum"]["group"]` (exit 2
listing the held ids; membership of papers is not checked here). The
quote check is decide's chunk (`<<check the quotes of the agent's
reasons>>`, `--strict-quotes`); its "Saved all the same" line prints
only when `saving` (set before the chunk: decide True, screen
`not dry_run`). One `utc_now_iso()` per run =
`recorded_at` = `at`; `keep_copy_before_run(session, "pre-screen")`;
`--dry-run` writes nothing. `--blind`/`--not-blind` → `blind`
True/False, `blind_basis: "declared"`; neither → None. The decision is
never changed (tested on the saved JSON). **Screener identity**
(#253 C): `review.screener_identity(record)` = `(kind, name, via ==
"classify")`; comparisons (agreement, conflicts) pair by it, not by
`(kind, name)`: a classifier second screen keeps `name` = the model id
(so "same model" = both kind llm with equal names) but must not share
the identity of the snapshot of a decision the same model made, else
the latest-record rule hides the first verdict. Only `llm classify
--second-screen` writes `via: "classify"`; snapshots are `"snapshot"`,
`sessions screen` `"screen"`. Report surfaces and the screen sheet:
see "Double screen in the documents" below.
**TUI blind review (#253 part D, closes #254's last point; tui.nw
`sec:tui-blind-review`).** `scholar sessions resume S --blind [--by
NAME]` (`PaperReviewApp(..., blind=True)`) starts blind mode in
`on_mount` (`_start_blind_at_mount`) before the list is drawn:
`blind_unbroken` True; needs review mode and `session.llm_samples`
(else notice, off) and `app.reviewer` (`--by`, else
`ReviewerNameModal`; empty/Escape → off; empty `--by` exits 2 before
loading). Key `b` toggles during a run, only from the paper list
(`len(screen_stack) > 1` → refused); switching on mid-run (or off and
on) sets `blind_unbroken` False for the run: screenings then get
`blind: False, blind_basis: None` (still `via: "tui"`), status bar
"Blind (verdicts were shown earlier in this run): NAME" instead of
"Blind: NAME". On selects the `llm_sample` filter. `blind_state(d,
queue)`: None unless blind and `id(d)` in `blind_queue()` (= what
`sampled_for_review` lists: every sample, band, census; not reset since
draw); "own" if `made_by_reviewer` (`verdict_screener` kind human,
name = reviewer; unreachable via the queue today, which holds only
unreviewed machine decisions); "revealed" if `reviewer_screening` (a
counted `origin: screen` human screening of that name, also one from
`sessions screen`); else "hidden". Hidden: row shows `BLIND_MARK`
("B"), no status/machine mark/confidence; detail screen omits tags +
Themes/Motivations heading; `f` refused in blind mode
(`<<refuse the decision filters in blind mode>>`: every status/source/
example filter selects by decision; PR B's conflict filter `x` is in the
same dialog, so refused too, tested), `F` (year, venue, citations, OA,
pub type: `SearchFilters.matches` on the paper only) allowed; status
bar counts via `status_counts()` leave hidden papers out and add
"Hidden: N"; every tag dialog (normal and blind, both screens) takes
`tag_choices(keep)`: outside blind mode the session's
`all_themes/theme_counts` or `all_motivations/motivation_counts` as
before, in blind mode only non-hidden papers' tags of that status;
the blind dialog preselects nothing. `blind_verdict(d, status,
ask_tags, done)` runs first in K/T/d of both screens: hidden →
`record_blind_verdict` (`new_screening(kind="human", name=reviewer,
blind=blind_unbroken, blind_basis="tui" if blind_unbroken else None,
via="tui", sample_id=sample_holding(session, d))` via
`record_screening`, decision untouched, notification with
`revealed_verdict(d)`), the detail screen stays and shows a "Blind
review" block (both verdicts, the machine's reason); "own" → warning,
nothing recorded. `blind_refuses_confirm`: C on a hidden paper refused.
After the reveal K/T/d/C are the normal paths (`mark_as_reviewed` +
`record_human_decision(..., by=reviewer)`): the adjudication. Leaving
between keeps the screening; the decision stays unreviewed and listed,
revealed. The start notice (`BLIND_MODE_NOTICE`) adds, after a
newline, `sample_giveaway(session, queued)` (review.nw, also used by the screen sheet): one line per queued sample
that tells something, "Sample <sample_id> (N listed paper(s)) holds
<describe_sample_criteria of statuses+sources> only: their status is
known." for a single-status sample, plus (or alone, "... was drawn by
confidence ...") "It was drawn by confidence: the range of confidence
of each of its papers is known." for a banded (`stratum`) or bounded
draw; mixed samples get no line. The id is the one `llm sample` prints
("Sample <id>"); the list does not show which sample drew a row.
Saved by `sessions resume`'s `save_session`; PR A's merge sets aside a
screening made while another process reset the paper
(`TestBlindReview`, real subprocess, through `sessions resume
--blind`). Not hidden: the session file, other commands, what the
sample's criteria tell, and that queued papers are unreviewed machine
decisions (prose, `sessions resume` help, notice).

#### Agreement and conflicts (#253, part B)

`agreement.nw` (new module, chapter after llm_review; reads, never
writes). **Screener** = `review.screener_identity(record)` =
`(kind, name, via == "classify")` (defined in `sec:screenings`,
shared with PR C #277 so a model's second screen is apart from the
snapshot of its own decision; `screener_of` returns None for a kind
not in `SCREENING_KINDS`, counted by `unknown_origin_count`, never
paired); unnamed = `(kind, None, ...)`, one screener per kind,
labelled "unnamed agent"; second screen labelled "llm (m), second
screen". `--pair` form `kind[+second]:name` or bare `kind[+second]`
(`screener_spec`/`parse_screener_spec`, first colon splits;
`parse_screener_pair` splits `A,B` at the one comma followed by a kind
[+second] and `:` or the end, so names may hold commas; none or
several such commas, or one screener twice → ValueError, exit 2).
`pair_header` prints `Pair --pair <shlex-quoted A,B>`, copyable. `same_model(a, b)` (kind llm, one
name): header line "same model: m" plus both sides' prompt versions
("none recorded"), show line "(same model)". `screener_verdicts(decision)`: latest counted
record per screener by `at` else `recorded_at` (ties: later in list);
the live decision is never a verdict, its snapshot is.
`ScreenerProfile.label`: a screener all of whose records are snapshots
with `confirmed_from` is "the human-confirmed decision (by NAME;
proposed by llm MODEL)" (parts only when known/unique); partly →
"human (X) (k of n records the human-confirmed decision)"; profiles
also list prompt versions. **`AgreementTable`** (frozen; `cells[i][j]`
= A's label i, B's label j, positive first; everything computed from
cells): `n`, `agreeing`, `observed`, `positive_agreement` =
2x11/(2x11+x12+x21), `negative_agreement`, `prevalence_index` =
(x11-x22)/N, `bias_index` = (x12-x21)/N (signed), `chance_agreement`,
`kappa` None with `kappa_undefined_reason` when either screener used
one verdict ("one screener gave only one verdict" / "both ...", never
0), "no records screened by both", "not computed for more than two
categories". Sources in the prose: ShankarBangdiwala2014 (Po, kappa,
PI/BI, scenarios 1-3 as test vectors; Byrt and Cicchetti-Feinstein
cited through it), Tan2024 (Ppos/Pneg; lepidic/acinar vectors),
VachGerke2023, Wongpakaran2013 (zero marginal; Table 7 scales differ),
Vembye2025 p. 9, Reichenheim2004 (why no kappa interval). Not
computed: AC1, PABAK, B, kappa interval, multi-category kappa, verbal
labels. **Questions** (`QUESTIONS`, `verdict_value`): `status`,
`bearing` (category `<= AUDIT_ORDER_BEARING` of `audit_category(tags)`),
`category` (4x4, observed only); a verdict without category →
`without_category`. `screening_agreement(records, a, b, question)`
takes `screener_verdicts` maps (computed once); a record = a decision
(copies counted each). `screener_pairs` (fixed order by
`SCREENING_KINDS` then name). **Samples**: `sample_bands(sessions, id)`
(id or stratified group id; one `SampleBand` per stored band, papers
by id as `sample_reports`: `reset_since_draw` left out and counted,
missing papers and sessions not given → `not_found`); `band_agreement`
adds `modified_wilson_interval(agreeing, n)` unless
`interval_withheld`: census, or any counted sampled paper lacks a
verdict/category of either screener (reset/not found do not withhold).
No interval over all records. **Conflicts**: `conflicts(decision,
verdicts=None)` per screener pair: `status` if statuses differ, else
`category` if both categories present and different. `conflict_resolved`:
decided, source not `is_unreviewed`, `human_decided_at` not older
than the latest counted screening's `recorded_at`.
`conflict_outcome` → `a`/`b`/`neither` (status: decision status;
category: `audit_category(decision.tags)`). **Text**:
`agreement_block` (table, measures, then two sentences, always: "X of
N records were discarded by both, so observed agreement is at least
X/N (P %) whatever the screeners did with the rest; positive agreement
counts only records at least one screener kept." and "For the same
observed agreement, kappa is lower the more one verdict dominates. No
verbal label is given for kappa."; bearing worded "judged (not)
bearing"), `agreement_data`
(JSON, `interval` only for samples, category without kappa keys),
`pair_header`, `ScreeningOverview.of(decisions)` (None without any
decision with screenings; `lines()`, `data()`, `conflict_counts()`).
`conflict_counts(entries)`/`conflict_counts_line`: one definition for
show and `sessions conflicts` (a paper with any status conflict counts
as status, else "category only").
**CLI** (cli.nw `sec:sessions-agreement`, `sec:sessions-conflicts`):
`scholar sessions agreement S [S...] [--sample ID] [--pair A,B] [-f
table|json]` (sessions deduped by file; `--sample` reads
`pooled_sample_sessions`; one block per band; bad `--pair` or unknown
sample exit 2, missing session exit 1); `scholar sessions conflicts S
[--pair A,B] [--status-only|--category-only] [--unresolved] [-f
table|json]` (both kind flags exit 2; outcome counts per pair and kind
over resolved conflicts; one print). `sessions show` adds the
overview's lines after the "Screenings:" line (one per pair: records,
kept/discarded agreement, kappa with "(prevalence index …, bias index
…)" or undefined with its reason, status conflicts (resolved); then
"Screening conflicts: N status (R resolved by a human), C category
only"; unknown-origin count) in one print, and JSON
`double_screening` (`pairs`, `conflicts`, `unknown_origin`); neither
without screenings (`TestSessionsConflicts.test_show_unchanged_without_screenings`).
TUI filter `x` (`conflicts`): decisions with an unresolved conflict;
a TUI confirm resolves (tested with a pilot). A blind TUI screening
that differs from the machine's is a status conflict, unresolved until
the step-two confirm (`test_a_blind_verdict_is_a_conflict_until_confirmed`).

#### Double screen in the documents (#253, part E)

agreement.nw `sec:agreement-reports`; every number comes from
`ScreeningOverview` / `screening_agreement` (no second computation),
and every surface starts from `ScreeningOverview.of`, None without
screenings, so documents of sessions without screenings are byte for
byte as before (`TestDocumentsWithoutScreenings`: sha256 of report,
CSV, synthesis summary md+latex, audit table en+sv of
`_surface_session(False)`, pinned from b05c49e). Shared pieces:
`kappa_clause(table, minus="-")` (kappa always with PI/BI, else "kappa
undefined (reason)"; the report passes `MINUS` = U+2212),
`_records(n)` ("1 record", also in PR B's block, header, bound
sentence and show line), `ScreeningOverview.pair_summary(a, b)` →
(names, numbers) (the `show` line is `Double screening: names:
numbers`), `resolved_outcomes`, `sorted_outcomes`, `outcome_line`
(moved from `sessions conflicts`, which calls them; same text),
`blind_basis(record)` → `prompt`/`tui`/`declared` (blind True with that
ground), `unstated` (blind True, unknown ground), `not blind`,
`unknown` (None); `ScreenerProfile` counts `snapshots` and `bases`
(latest verdict per record). **Screened twice** =
`screened_twice(decision)`: counted verdicts of >= 2
`screener_identity`s (unknown-kind snapshots count as one); a pending
paper's lone screening (no snapshot) or a snapshot left alone by a
reset is not. `ScreeningOverview.screened_again`,
`screened_without_decision` (pending papers with a counted
screening), `second_screen_groups()` → {(kind, ground): (decisions,
screeners)} over records screened twice, `screen_sample` (the one
`sample_id` of every second-screen verdict, else None).
- **Report** (`double_screening_sentences(decisions)`, English, called
  by `llm_review.build_llm_screening_latex`, escaped by `latex_text`:
  `escape_latex` between `MINUS` signs, each `$-$`): after the LLM
  sentence and the samples, `\paragraph{Double screening}`; with no
  LLM step and no sample `<heading_command>{Double screening}` instead.
  Sentences: "k of the N decisions were/was screened a second time."
  (decisions, as the summary counts papers); "p pending paper(s)
  has/have a screening but no decision to compare it with."; with
  `screen_sample` "Every second-screen verdict was made for review
  sample S; scholar sessions agreement --sample S gives the agreement
  over that sample."; per screener (`screener_sentence`,
  `REPORT_BLINDNESS`): "label: n records, all <phrase>." or "(c1
  phrase1; c2 phrase2)" (snapshots: "copied from the decision when a
  screening was recorded"); per pair (`pair_sentences`)
  "Kept/discarded, A = …, B = …[ (same model)]: n records screened by
  both; both kept x11, A kept and B discarded x12, A discarded and B
  kept x21, both discarded x22; observed agreement, positive/negative
  agreement, Cohen's kappa (PI, BI)." plus PR B's bound sentence; PR B's
  kappa sentence once after all pairs; conflict counts ("… resolved by
  a human who decided after the latest screening; … had conflicts on
  the category only."; one record: ", and it was resolved by a human
  …" / ", and it is unresolved"; none: no resolution clause) and one
  `outcome_line` per pair and kind;
  unknown-origin count. No interval.
- **`llm synthesize`** summary (`summary_rows`): after the "Decided"
  rows, md `- Double screening (names): numbers`, LaTeX
  `\item[{Double screening: names}] numbers` (braced: names are user
  text); the LaTeX row writes negatives as `$-$` (`summary_rows(...,
  minus=MINUS)` + `latex_text`), the Markdown row keeps the hyphen.
- **Audit caption** (`audit_screening_sentence(decisions, strings,
  rows)`, in `build_audit_table_latex`'s `databases` join after
  `cited_rule`, i.e. after the reason/confidence sentence and the cited
  rule, before "Databases searched"). Counts unique hits by the rows'
  `work` (`audit_work_key`; a work is screened twice when any copy is;
  total = rows); without `rows` it counts records. en: "k of N hits
  were/was screened a second time (c by <a language model / an agent /
  a human / n agents>, <ground>; …)." (grounds: "blind by
  construction of the prompt", "blind in Scholar's review screens",
  "blind by the {agent's|model's|screener's; plural agents'|models'|
  screeners'} own declaration", "marked blind", "not blind",
  "blindness not recorded"; the report's declared phrase is "blind by
  the agent's own declaration, which Scholar cannot check"); per pair "Agreement on
  kept/discarded between <model m-1> and <agent a-2>[ (same model)]
  (a same-model second screen: "model m-1 (second screen, same
  model)", sv "(andra granskning, samma modell)"),
  over n records screened by both: P\,\% (Cohen's kappa K, prevalence
  index PI, bias index BI)." (or "undefined: reason"); "Status
  conflicts: s, of which r resolved by a human; category-only
  conflicts: c."; numbers via `audit_number`, negatives `$-$`; a
  screener all human-confirmed snapshots → "the human-confirmed
  decisions", partly → "human Hum (k of n records human-confirmed
  decisions)". sv: "k av N träffar granskades en andra gång (c
  granskade/granskad av en agent, blint enligt agentens egen uppgift;
  …)." (grounds: "blint genom promptens utformning", "blint i Scholars
  granskningsvyer", "blint enligt {owner} egen uppgift", "markerat som
  blint", "inte blint", "utan uppgift om blindning"); "(samma
  modell)"; "Statuskonflikter: s, varav r löst/lösta av en människa;
  …". Pending papers with a lone screening are left out of the caption.
  Strings in `AUDIT_STRINGS` (review.nw `sec:audit-double-screen`).
  Rows, order and reasons unchanged (tested with/without screenings).
  `TestDoubleScreeningCompiles` (marker `latex`) compiles report
  fragment + sv table in the pdfLaTeX T1 host with a name full of
  specials.
- **Screen sheet** (cli.nw `sec:screen-sheet`): `scholar sessions
  export S -f screen-sheet [--sample ID] [--undecided-by NAME] [-o
  F[.tsv]]` writes a header line `id title year venue abstract` and
  one line per paper id (copies once), tab-separated UTF-8, nothing
  else; tabs and every `str.splitlines` break → space
  (`sheet_field`). Papers (`screen_sheet_decisions`) =
  `second_screen_candidates` (`over="all"`, or the sample: decided
  only, since a second screen needs a first verdict; reset-since-draw
  left out); `--undecided-by` drops papers where `has_verdict_by` (a
  counted screening of that name, any kind, or `verdict_screener`
  name). With `--sample`, the lines of `review.sample_giveaway` (moved
  from tui.nw with `sample_holding`, review.nw `sec:sample-giveaway`;
  the TUI imports both) go to stderr. The two options with another
  format, or empty, exit 2; unknown sample exit 2 (screen's chunk).
  `--batch-size N` (#292; screen sheet only, >= 1, else exit 2; no
  default, the help gives the protocol's ~100 as a recommendation
  only: defaulted rows frequent at several hundred, rare at <= 100, in
  one run still in batches of 100) writes `BASE-001.tsv`… of at most N rows, each starting
  `# batch: <digest>-NNN`, `# session: <file name>`, `# records: n`,
  then header and rows as the single sheet (`csv.writer`, tab,
  `QUOTE_NONE`, `quotechar=None`, `\n`: quote marks as stored, bytes
  as the old tab-join, checked on 3.12-3.14; the reasons/verdicts
  reader stays own code, `csv.reader` splits at a lone `\r`); plus `BASE-manifest.tsv`
  (`batch file records first_id last_id`, written with `csv`, tab,
  `\n`, no comment line). Digest =
  first `SHEET_DIGEST_CHARS` = 8 hex of SHA-256 of [session file name,
  size, ids] (`screen_sheet_batches`): stable for one selection and
  size. Without the option the output is unchanged. `--pending`
  (#292, cli.nw `sec:first-screen-sheet`, `pending_sheet_decisions`)
  lists the pending papers instead (first screen; one per paper id,
  same columns), exit 2 before loading with `--sample`/`--undecided-by`
  or another format; its batch ids differ from a decided sheet's
  because the id lists differ.
  Prints "N paper(s) on the screen sheet." and no machine-review
  table. `all` stays csv + latex.

### Session Arguments

Every command that takes a saved session (`sessions show/export/decide/
relabel/reset/set-abstract/screen/resume/reconcile/check`, `llm classify/status/context/
synthesize/sample`, `enrich`, `verify`) opens it with
`cli.open_session_argument` → `review.load_session_argument` →
`resolve_session_argument` (#237, review.nw `sec:session-arguments`):
an argument ending in `.json` names that file in the sessions dir; a
`.json` path is accepted only into the sessions dir, any other
directory → `SessionArgumentError` "give a file name in <dir>" (taking
the base name had opened the live file of that name instead). Any
argument is also tried as `<arg>.json` and as its query's hash file.
More than one existing file → `AmbiguousSessionError` (a
`SessionArgumentError`; message names each file and what it holds,
`describe_session_file`). Both → exit 2, nothing read or written. One
file → read with `read_session_file` (the same file as the old
`load_session` lookup); none → None, also for a query too long to be a
file name. Tests of the commands stub `review.load_session_argument`.
`sessions reconcile` re-reads the resolved file under the lock. `llm
sample` and `sessions check` load a session named twice (`x x.json`)
once (by `session_file_path`). The `sessions list` table shows `name
(argument)` when they differ (`session_list_name`).
`session_argument(session)` /
`session_argument_for(label, path)` give what to type: the label, or
the file name when the label opens another file or fits two; used by
`list_sessions` (`argument` key), shell completion, `llm sample`'s drawn
list and `--report`'s "not yet reviewed" list (`SampleReport.unreviewed`
holds arguments). Never call `load_session` on a user-typed argument.

### Session Integrity

Commands that load a session and save it much later (`scholar enrich`,
`verify`, the TUI) used to overwrite whatever was saved in between. That
is how two classified sessions lost every decision and their research
context (#107). `review.save_session` now:

- **merges**: it re-reads the file and does a three-way merge against
  `session._baseline` (`SessionBaseline`, recorded by `read_session_file`
  and after each save). Decision fields and `research_context` this
  process did not change take the on-disk value. Papers, search records
  and snowball rounds that only the file has are added. Paper metadata
  of a paper both hold is merged three ways too (#206,
  `paper_merged_from(ours, theirs, base_state)`): the baseline keeps
  each paper's stored fields (`SessionBaseline.papers`: id →
  `paper_state(paper)`, the `Paper.to_dict()` fields frozen into
  immutable copies, lists → tuples, dicts → sorted item tuples, so
  in-place changes are seen; `None` ≠ `()`). A field ours still has
  as in the baseline takes the file's value if that differs and is
  not `None` (a retraction `verify` saved; a `None` on disk is a gap
  from an older writer or a hand edit); a field we changed keeps
  ours (also when both changed); then gaps are filled (#194,
  `paper_filled_from` = `ours.merge_with(theirs)`).
  `PAPER_FIELD_GROUPS` (`oa_status`+`oa_url`, one Unpaywall answer)
  are decided whole first: ours as loaded and the file's pair
  different with a non-None status → the file's pair (its `None`
  link too); else ours holds a status or changed → our pair whole,
  restored after the fill; else fill. `pdf_url` and the Crossref
  pair stay per field (Crossref never writes `None` there).
  Crossref notices (`CROSSREF_NOTICE_FIELDS`: `updated_by`,
  `newer_versions`) are united (#219, `united_crossref_notices`:
  ours first, each notice whole, keyed by normalised DOI + `type` /
  `relation`, DOI-less notices by equality; None+None → None,
  []+None → []) when the paper has no paper state or both copies
  changed them since the baseline (a retraction lost is worse than a
  withdrawn notice kept, which `verify` replaces); only one side
  changed → the three-way rule (ours as loaded → file's list; ours
  changed, file as loaded → ours).
  `ACCUMULATED_PAPER_FIELDS` are never judged three ways: sources,
  keywords, tags united and `citation_count` max (by `merge_with`),
  `preprint_versions`/`published_versions` united by
  `united_version_links` (ours first, links whole, matched by
  normalised DOI, DOI-less links by equality; also without a
  baseline). Paper states are recorded only from the file
  (`SessionBaseline.of(..., from_file=True)`: `read_session_file`
  and after each save); a baseline `create_review_session` builds
  (#209: other-file appends, new sessions, the ids a same-file append
  adds) has decision states only, since a built paper is no ancestor
  of the target's copy. No paper state (session never loaded or
  built, paper new here) → nothing taken, gaps filled, ours wins
  (Crossref notices united, above).
  `read_session_file` takes the baseline from the file's copy
  (`as_stored`), not from the registry's held object, else the
  file's older values would overwrite ours; the save's re-read passes
  `record_baseline=False` (it never needs one). Cost on an
  11,162-paper session copy: ~5 MB, load ~+10%. Nothing is taken or
  filled from a namesake (`plausibly_same_work`; DOI-less hash ids
  collide). The decision keeps its very `Paper` object when nothing
  changed. The file is read with
  `read_session_file(path, use_registry=False)`, else the registry
  would hand back our own objects and hide the file's copies; a paper
  new on disk is registered (`register`), and if this process
  already holds a copy of the same work, that copy wins, gaps filled
  from the file (a held namesake: the file's paper stays).
- **guards**: `warn_if_decisions_dropped` logs a WARNING (session,
  before/after decided counts, `.bak` path) when the save still leaves
  fewer decided papers than the file has, beyond this process's own
  resets to pending. It never refuses the save.
- **locks**: the re-read, merge and replace run under
  `utils.file_lock` (`filelock`: `flock` on POSIX, `LockFileEx` on
  Windows) on a hidden sidecar `.<name>.json.lock`, so two processes
  saving at once take turns. Held for milliseconds only, never from
  load to save; after `LOCK_TIMEOUT` (10 s) it warns and writes
  unlocked. Notes writers (`save_note`, `delete_note`, `get_note`,
  `import_notes`, `migrate_paper_id`) take the notes file's lock via
  `_holding_notes_lock`. Same machine only: no help across
  machines on a shared directory.
- **writes atomically**: `utils.atomic_write_text` (temp file in the
  same directory, fsync, `os.replace`), keeping the previous file as
  `<name>.json.bak` (one generation).
- **saves to the file it loaded** (#181): `read_session_file` sets
  `ReviewSession._loaded_from` (not persisted; `create_review_session`
  carries it over only when `appends_to_loaded_file`: both identities
  (name, else query hash) map to one file name; `search foo --review`
  must not write into named session foo's file) and
  `session_file_path` returns it, so lock, merge
  re-read, `.bak`, write and `keep_copy_before_run` use the loaded
  file, not the one the stored `name` maps to (`own_session_file_name`;
  new sessions still use that). A file whose stored name maps elsewhere
  (a hand copy) logs one WARNING per file and process
  (`warn_about_foreign_name`) and is flagged by `sessions list`
  (`name_mismatch` in the JSON, a stderr line); neither is renamed.
  A stored name is no key (named `foo` of query `bar` and the unnamed
  session of query `foo` both list as "foo"), so code that lists
  sessions reads each by its path, `load_listed_session(meta)` (#221:
  `list_all_themes`, `list_papers_for_theme`,
  `complete_session_paper_id`), never `load_session(meta["name"])`;
  pooled LLM sample sessions likewise by recorded file (#231).
  The loaded `_baseline` goes with `_loaded_from` (#207): an append
  that saves into another file takes `SessionBaseline.of(session)` at
  the end of `create_review_session` instead (no baseline would let
  the loaded file's decisions and context replace the target's; the
  loaded one reset the target's decisions of papers it lacked and
  dropped those under ids the append renamed). Same-file appends keep
  the loaded baseline (a renamed id must not come back from the file)
  and add the built state only for ids it lacks (#214: a paper new in
  this run, untouched, yields to another process's decision);
  `record_keys` and the context stay as loaded. A session that loaded
  nothing (brand new, or rebuilt from the decision store) takes the
  built state too (#214: two processes creating one session at once);
  only sessions constructed in code have no baseline. Whenever the
  session does not continue a loaded file, the built baseline's
  `record_keys` are empty: nothing was loaded from the target, so the
  legacy-record rule must not drop one of our legacy records.
- **an append loads only its own file** (#213):
  `create_review_session` loads `load_own_session(name, query)`, the
  file `own_session_file_name` gives (`<name>.json`, unnamed: the
  query's hash), never `load_session`'s other guess (an unnamed append
  for foo used to load named session foo's `foo.json`, whatever its
  query; `search bar -n foo` without `foo.json` the unnamed foo
  session's hash file). One exception, the `--review` default: a named
  append without its own file whose name is its query continues the
  hash file of that query if it holds an unnamed session of that query
  (that command always did); the session stays unnamed
  (`<<continue an unnamed session without a name>>`), so it saves back
  there with the loaded baseline and is found again next run. When the
  other file exists and is not continued, one line names it, what it
  stores (`_stored_identity`: name, or the unnamed session's query) and
  `pass -n '<its stem>'` to continue it: WARNING when the own file does
  not exist, INFO otherwise. A `<query>.json` too long for a file name
  reads as absent (the old lookup raised `OSError`).
  `appends_to_loaded_file` compares `previous._loaded_from.name` with
  `own_session_file_name(name, query)` (identities got hand copies
  wrong: `-n a` on `a.json` holding b took the built baseline and a
  renamed homonym id came back beside the new one). So every append
  that loaded a file continues it; the #207 built baseline serves only
  sessions that loaded nothing. `load_session` keeps its tolerant
  lookup for the user-facing commands (`sessions show/export/decide/
  ...`, `llm`, `enrich`, `verify`); `search -n`/`--review`, `rq` and the
  TUI all go through `create_review_session`. Real sessions
  (2026-11-19): no hash-named file, no unnamed session.

`scholar enrich` saves after every `ENRICH_SAVE_EVERY` (50) papers
(`cli.nw`, `sec:enrich-chunks`): enrich → Crossref check → assign →
`migrate_paper_id` for adoptions → `save_session`, per chunk. After such
a run `.bak` holds only the state before the last chunk, so before the
first chunk (only when there is something to enrich and the file
exists) `review.keep_copy_before_run` copies the saved file to
`<name>.json.pre-enrich-<UTC YYYYMMDDTHHMMSSZ>.bak` (atomic, under the
session lock). Each run adds a copy and the newest
`RUN_COPIES_KEPT` (3) are kept, so continuing an interrupted run does
not overwrite the original; `review._utcnow` is the test seam for the
time. The end-of-run and interrupt messages print the new path. The copy
covers the session file only: preprint adoption also rewrites the notes
and decision stores (`migrate_paper_id`), which a restore does not undo
(the report says so when a run adopted one). The name does not end in
`.json`, so the `*.json` globs of `list_sessions` and
`sessions_mentioning` skip it (tested). Ctrl-C (and
SIGTERM, turned into `KeyboardInterrupt` while the loop runs, so the
atexit cache save still happens) prints `Interrupted: saved K of N
papers; run again to continue` and exits 130.

`load_session(..., strict=True)` raises `SessionFileError` for a file
that exists but does not parse. `create_review_session` uses it, so
`search -n`/`--review`/`rq` stop with one line instead of rebuilding over
the file. Read-only callers still get `None` plus a warning.
Notes (`paper_notes.json`) and per-query decision files follow the same
rules (#114). A file that exists but does not parse raises
`notes.NotesFileError` instead of reading as empty, which used to make
the next save erase every other note. Writes are atomic with a `.bak`,
and write errors raise instead of being swallowed. `cli.main()` turns
the error into one line and exit 1. Two deliberate exceptions (#121):
the TUI catches it, shows it as a notification (and in red on the
detail screen), hides note markers and refuses note editing, but keeps
reviewing (a note whose save fails after editing is kept in
`unsaved-note-*.md`, data dir else temp dir, and the message names
it, #126); and `migrate_paper_id` logs a WARNING naming each unreadable
store file and both ids and skips it (raising would discard the
caller's enrichment run or search append), raising only on write
errors. `notes export` also writes atomically (no `.bak`).
`sessions export` stages all its files with `utils.staged_outputs` and
moves them into place only if every format succeeded (#83).
`sessions list` warns on stderr about sessions with records but no
decisions and no context (`needs_check` in the JSON). The paper registry
is process-global, so tests that load sessions should use unique DOIs or
`isolated_registry()`.

### Provenance Round-Trip

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

### Search Provenance (`prov found-via`)

Each `ReviewDecision` records the searches that returned its paper in
`found_by`: `(query, provider, filters key)` keys of the session's
`SearchRecord`s (merged `q | q` / `openalex, dblp` keys included), set in
`create_review_session` on every branch that resolves a result to a
decision, persisted as `found_by` in the session JSON
(`{"query", "provider", "filters"}`), and unioned from
disk by `merge_concurrent_changes` (#128). Old two-part links (no
`"filters"`) are resolved at load when exactly one record has that
query and provider; otherwise they stay `(q, p, None)` and are saved
back without `"filters"`. A resolved link supersedes the unresolved
links of its (q, p) (`without_superseded_links`, on record and on
load). `ReviewSession.search_record(q, p, key)`
matches the full key; with `key=None` it answers only a unique
(q, p). `prov found-via` prints one
command per resolved link via `search_record` and
`cli._search_command` (shared with `bibtex+prov`'s `_found_via`; undoes
the merge joins). JSON `link` is `recorded`, `inferred` (no links, but
the provider ran exactly one search in the session) or `missing` (no
command; printed under `Not reproducible:` with `candidate_queries`,
never with the `FOUND-VIA:` token; an ambiguous old link is `missing`
with the records of its query and provider as candidates). Old sessions get links when their
searches are re-run with `-n` (cache hits cost nothing). Never fall back
to `search_record_for(provider)`: with several queries on a provider it
returns the latest search, which is how #128 named wrong queries.
A retired search's command gets a shell comment on the same line
(`FOUND-VIA: scholar search ... # retired 2026-11-20: note`,
`_retired_comment`, whitespace collapsed), so it stays inside a
`prov import` block and is ignored when pasted to a shell; JSON adds
`retired` (absent for current searches). `bibtex+prov` only writes the
search just run, which is current, so it never carries the mark (#275).
`review.sessions_mentioning(fragment)` finds the sessions by a
case-insensitive byte search for the id in each file (every decision
stores `paper_id`; an arXiv DOI also matches its bare arXiv id) and
decodes only those; non-ASCII/`"`/`\` fragments decode every file.

### `search -f csv` rows (#300)

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

### Spreadsheet-safe CSV (`--spreadsheet-safe`, #285)

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

### LaTeX Output: Standalone, Fragment, Audit Table

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

### Provider Text Cleaning

`utils.clean_metadata_text` / `clean_paper_text` decode HTML entities,
strip inline tags (`<i>`, `<sup>`, …) and repair cp1252/Latin-1 mojibake
by a checked round trip. Applied at ingest in `Search.execute`,
`ReviewSession.add_papers_from_snowball` and at the end of
`enrich_paper` (except an abstract an abstract service supplied in
that call, `clean_paper_text_except`, #260); the LaTeX escapers apply it too, for sessions recorded
earlier. A DOI-less paper's hash id derives from the cleaned title, so a
record with markup ingested before this change gets a new id when it is
searched again.

### Classifier Vocabulary

`llm classify` tells the model to use only the session's existing
themes and motivations; `parse_llm_response(allowed_tags=…)` maps tags
case-insensitively onto that vocabulary, drops the rest with a warning
(`LLMDecision.dropped_tags`), and `classify_papers_with_llm` retries the
batch once with the vocabulary spelled out when a paper would be left
without tags. A session without tags imposes nothing unless
`llm classify --tag` (the `vocabulary=` argument) seeds it; with
`--allow-new-tags` (`allow_new_tags=`) the prompt asks the model to
prefer the vocabulary and new tags are not dropped. The `llm`
module is looked up via `globals()` so tests can substitute a fake model.

**Unknown model (#284).** Every model lookup (`classify_papers_with_llm`,
`second_screen_with_llm`, `generate_literature_synthesis`,
`suggest_theme_groups`, rq's `generate_provider_queries`, pdf's
`rerank_passages_llm`) goes through `utils.resolve_llm_model(llm_module,
model_id)` (utils.nw `sec:resolve-llm-model`): the `llm` package's
`UnknownModelError` (a `KeyError`; caught by class, read from the module
passed in, `KeyError` for a stand-in without it) becomes `ValueError("Unknown
model: X; `llm models` lists the available models")`. `llm classify`
(both runs), `llm synthesize` (also its `-i --suggest-groups` grouping,
which before ended in a traceback, named model or default: only
`ImportError` was caught there and `_resolve_themes` runs before the
command's `try`), `rq` (before any search) and `pdf quote` with `-m`
print it as one unwrapped line and exit 1. `pdf quote` without `-m`
and an unknown *default* model (llm's `default_model.txt`) keeps the
old fallback: `rerank_passages_llm` logs the message as a WARNING and
returns None (lexical order, exit 0). Dry runs of the ordinary classify
and of the synthesis resolve no model (a dry run works offline; resolving
asks every plugin), so they do not notice a typo; `--dry-run`'s help
says so. The second screen's dry run does resolve it: it needs the
model's own id (what decisions store as `llm_model`, whatever alias
was typed) to choose the papers the model has not screened. Tests use the real
package with `get_model_aliases`/`get_async_model_aliases` patched to
`{}` (resolving a model asks every plugin; llm-gpt4all fetches its list
over the network) and a long model name, so a wrapped line would fail.

Tag kinds: note tags (`NOTE_TAGS`, the union of every language's
`AUDIT_STRINGS[lang]["notes"]`) are human-only, never offered (not even
on examples' tag lines) and dropped if returned (`excluded_tags=`, also
under `--allow-new-tags`). When the vocabulary holds any of
`AUDIT_CATEGORIES`, the prompt lists them in a separate "Category
(exactly one per paper)" section and the theme lists become optional
extras; `parse_llm_response(category_tags=…)` sets
`LLMDecision.category_problem` unless exactly one category remains
after mapping, that triggers the same single retry, and a paper still
invalid afterwards gets no decision (stays pending) and is listed in
`LLMBatchResult.withheld`, which `llm classify` prints at the end
("Left pending, no single category that fits the decision").
The category must also fit the decision (#224, `STATUS_CATEGORIES`):
a keep takes supports/qualifies/adjacent, a discard adjacent/off-topic;
otherwise `category_problem` is "category X does not fit a <status>
paper" (checked only once exactly one category is left), with the same
retry and withholding. The prompt's category section and the retry
reminder state the rule (`_category_status_rule`, fixed wording, so the
prompt version moves) and say to keep a paper that bears on the claim
and leave its exclusion to a human. Once the session holds any of
`AUDIT_CATEGORIES`, the classifier offers all four (and adds them to
the vocabulary answers are checked against; themes and motivations stay
the session's own), so every decision has a fitting category; the
prompt-version probe offers the four too. Only classifier verdicts are
checked: `llm classify` answers, and `sessions decide --source llm`
(exit 2 before loading, naming the fitting categories). A human's or
agent's "supports, excluded" (rendered on purpose by the audit table,
#89) is recorded as given; existing records are not rewritten.
Sessions without category tags are classified as before.
A record whose category does not fit its status (a human's "supports,
excluded", or a pre-#177 leftover) is no example, though (#255,
llm_review.nw
`sec:example-category`): `get_example_decisions` leaves out every
candidate (`example_candidates`: tagged, kept/discarded, confirmed, or
unreviewed with `--include-llm-examples`) whose `audit_category` (last
category tag) is not in `STATUS_CATEGORIES[status]`
(`category_contradicts_status`), before the sort and the cut to
`max_kept`/`max_discarded`, so the lists stay full. Left out rather
than shown without a category (the prompt demands exactly one). Not
vocabulary-dependent; no category tag, no check. The INFO log says
"Left out N examples whose category does not fit their decision";
`llm status` counts the confirmed ones with the same
`contradictory_examples(session)` (row "Confirmed, not examples
(category does not fit decision)" only when > 0, apart from "Training
examples", which counts `is_example`; JSON `examples_left_out`
always). An example shows `example_tags(tags)` (llm_review.nw
`sec:example-tags`): no note tags and only the deciding category, so a
pre-#195 record tagged `supports-claim, off-topic-false-hit` shows
`off-topic-false-hit`; records with one category or none print as
before. The prompt version does not move (it hashes a fixed probe,
not the session's examples). `sessions show` does not list such
records.

### Snowball and Tuxedo Subcommands (lazy)

`scholar snowball` and `scholar tuxedo` come from the git submodules
(do not edit them) through their `register_commands(app)` hooks, but are
imported only when they run (#130): importing them (pandas, Textual,
openai) at startup made every command 2.3-2.8 s slower. `app` is created
with `cls=LazySubcommandGroup` (`cli.nw`, `<<lazy subcommand group>>`),
which lists a `LazySubcommandStub` per name in `LAZY_SUBCOMMANDS` (name →
help text, a copy guarded by a drift test) when `find_submodule()` finds
a spec (`scholar.<name>`, then `<name>`; nothing imported), so help and
first-word completion import nothing. `resolve_command` (dispatch and
completion descent) swaps the stub for `load_lazy_subcommand(name)`, the
command the hook registers on a scratch Typer app. A failing import is a
one-line usage error (exit 2); under completion it completes to nothing.
There is no `register_submodules()` any more; tests need no setup. Keep
heavy imports out of `cli.py`'s module level (`scholar.crossref` loads
its cache on import): `TestLazySubcommands` runs `main()` in a child
interpreter and fails if `--help` imports tuxedo, snowball, openai or
`scholar.crossref`.

### LLM Screening Record and Review Samples

Each decision applied by `llm classify` records `llm_model`,
`llm_decided_at` (UTC ISO), `llm_prompt_version` (16 hex digits:
`classification_prompt_version`, a hash of the prompt built for a fixed
probe plus the run options and research context; not the session's
tags or examples), `llm_reason` (cut to `MAX_REASON_CHARS` = 500) and
`llm_abstract_truncated` (#168). They live on `ReviewDecision`, named
once in `review.LLM_AUDIT_FIELDS` (`llm_audit_of()`), which load, save,
the append copy, `decision_state` and the concurrent merge all use; old
files load them as `None` (unknown) and nothing fills them in later.
A human review leaves them untouched (they are the model's record).
The per-decision CSV has a column for each, in this order, after
`source_relabelled` and before `agent_reason` (#281; the later columns
moved five places, `paper_id` stays last): empty when unset,
`llm_abstract_truncated` as `true`/`false`, the reason as stored (the
`csv` module quotes commas, quote marks and line breaks).

- **No invented values.** `parse_llm_response` returns one entry per
  paper; an unusable answer (no answer, decision not kept/discarded, a
  discard without tags, confidence missing/non-numeric/outside [0, 1])
  gets `LLMDecision.answer_problem`, triggers the single retry, and is
  then withheld with the category-rule ones (`LLMDecision.problem`);
  `llm classify` and `rq` list them (`print_withheld_papers`) under
  "Left pending, no usable answer".
- **Quotes in the reasons (#256).** `llm classify` (not `rq`) ends
  with one line, `Reasons quoting words not in the record (N): id:
  "quote"; ...` (first `LLM_QUOTE_MISSES_SHOWN` = 3), when an applied
  decision's stored `llm_reason` quotes >= 3 words not in its title,
  abstract or the `--full-text` passages of this run
  (`LLMBatchResult.passages`, paper id -> passage texts, not stored).
  Nothing is withheld or retried for it. Later checks (`sessions show`,
  report) see only title and abstract (see Headless Review Sessions).
  Answers without a valid `paper_index` are skipped (never index 0).
- **Second screen (#253 C).** `scholar llm classify S --second-screen
  (--over all|machine | --sample ID) [-n N] [--rescreen]` (exactly one
  selection, no default: exit 2 before loading; `second_screen_candidates`
  raises `ValueError` for neither or both)
  (`llm_review.second_screen_with_llm`, llm_review.nw
  `sec:second-screen`; cli.nw `sec:llm-classify-second-screen`)
  classifies *decided* papers (never pending) and stores each usable
  answer as a screening (`kind` llm, `name` = the model's reported
  `model_id`, status, tags, confidence, `reason` cut by
  `truncate_reason`, `at` = batch time, `prompt_version` (the ordinary
  one), `abstract_truncated`, `blind` True, `blind_basis` "prompt",
  `sample_id`, `via` "classify") via `record_screening` (snapshot
  first); never `apply_llm_decisions`, decisions untouched (tested on
  `decision_state`/`human_record_of` and the saved JSON); with
  enrichment on (as in an ordinary run) a missing abstract may be filled
  and saved, and every copy under the paper's id gets the filled
  `Paper`. Selection (`second_screen_candidates`): `all` every decided
  paper,
  `machine` = `is_unreviewed_machine`, `--sample` = a band's
  `sample_id` (that band) or a banded draw's group id (`sample_group`,
  all bands; each screening stores its band's id); sampled papers
  `reset_since_draw` are skipped and counted. Session order, `-n` per
  run (one request + the one retry, as classify); decisions with a
  counted screening of identity `("llm", model, True)`
  (`has_second_screen_by`) are skipped unless `--rescreen`; copies under
  one id are shown once and all screened. `classify_papers_with_llm(...,
  papers=)` classifies given decisions and takes examples and
  themes/motivations from `visible` (shallow session copy without every
  decision sharing a `same_work_keys` key with a screened paper: paper
  id, `version_link_dois`, `work:<audit_work_key>` when the title part
  is non-empty; no namesake guard, a hidden namesake costs an example;
  copies the keys miss are not hidden); whether categories are offered
  is read from the whole session. An unknown model becomes a
  `ValueError` (`resolve_llm_model`, see Classifier Vocabulary): one
  line, exit 1, a dry run too. Prose cites Vembye 2025 Table 5 steps
  1-5 (test with recall >= .75, specificity >= .8, which Scholar does
  not run) and 9, Page 2021 E&E Box 3 (partial checks); a `machine` or
  single-status sample selection makes agreement conditional on the
  first screen. Tested: the prompt is byte-identical when the screened
  papers' verdicts are flipped. Refused (exit 2, before loading, no
  model call): `--include-llm-examples` with it, `--sample/--over/
  --rescreen` without it, `--sample` with `--over`, bad `--over`;
  unknown sample exit 2 (screen's chunk). Nothing left → exit 1. A
  decision the same model made (unreviewed `llm`, `llm_model` = model)
  is screened, never refused, and announced ("Same model as the first
  screen for N paper(s)"; `SecondScreen.same_model`). Withheld answers
  store nothing (no snapshot) and are listed under "No screening
  stored, ..." (`print_withheld_papers(lead=)`); the quote line checks
  the screenings' reasons (`print_reason_quote_misses(reason_of=)`).
  Saved only when something was recorded, after
  `keep_copy_before_run(session, "pre-screen")`. Dry run prints the
  prompt, stores nothing (resolves the model, to skip what it
  screened). Prints "Left to screen: N".
- **Abstracts.** `MAX_ABSTRACT_CHARS` = 4000 for papers to classify
  (marked `[abstract truncated]` in the prompt), `EXAMPLE_ABSTRACT_CHARS`
  = 1000 for examples.
- **Examples** are only `human`/`llm_reviewed`/`agent_reviewed` decisions
  (`CONFIRMED_SOURCES`, compared by value); `--include-llm-examples`
  adds unreviewed `llm`/`agent` ones after them.
- **Samples (#173).** `scholar llm sample S [S...] --discarded|--kept
  [--min-confidence C] -n N --seed SEED` pools unreviewed `llm`/`agent`
  decisions, sorts them by (session, paper id), keys each with
  `random.Random(seed).random()` (the only call Python promises to keep
  stable across versions) and takes the N smallest; it stores a
  `review.LLMSample` (seed, criteria, UTC date, population size and
  digest, this session's papers with the machine's status) in every
  pooled session (`ReviewSession.llm_samples`, merged by `sample_id`,
  which ends in uuid4 digits so two draws in one second never collide).
  `test_golden_draw` pins the drawn papers for seed 42.
  The TUI filter `s` (`sampled_for_review`) queues the unreviewed ones
  (blind mode, `sessions resume --blind` or `b`, hides their verdicts until the reviewer's own is
  recorded as a screening, see Screenings);
  `sessions decide` reviews them. `--report [-f json]`
  (`sample_reports`): a sampled decision counts as reviewed when decided
  and no longer an unreviewed machine source, as changed when its
  status differs from the recorded one; the rate gets the 95% modified
  Wilson interval (`modified_wilson_interval`, Brown, Cai & DasGupta
  2001, eq. 4 with the Poisson bound of eq. 10, p. 112, for x <= x*,
  x* = 2 for n <= 50 else 3), because plain Wilson coverage dips near
  p = 0, where disagreement rates live. The sentence says the rate
  covers only the reviewed part while some is unreviewed.
  A sampled paper with a reset record (`ReviewDecision.resets`, #248)
  whose `at` >= the sample's `drawn_at` (both UTC ISO with seconds;
  `llm_review.reset_since_draw` compares them as datetimes, as strings
  if either fails to parse) no longer holds the drawn decision: it is
  counted as `SampleReport.reset_since_draw` (JSON `reset_since_draw`,
  sentence "N sampled decisions were reset to pending after the draw
  and are not counted"), never as reviewed, changed or unreviewed, is
  part of the `counted` total for sessions not given, and is not queued
  by `sampled_for_review`. A reset before the draw counts as usual.
  `LLMSample.sessions` are labels (`session_label`: name or query);
  since #231 `session_files` (same order, `session_file_path(s).name`,
  saved only when present; old samples load with None) records each
  pooled session's file. `pooled_sample_sessions(sessions, load=)`
  (used by `--report` and the report's screening section) reads the
  other sessions from those files (`load_listed_session`; a file gone
  -> its papers not found), old samples by label via `load`, each file
  once. The population digest still hashes labels (unchanged).
- **Bounds, bands, census (#254).** `--max-confidence C` is exclusive
  (`confidence_in_bounds`: `[min, max)`, a missing confidence meets no
  bound); `--no-confidence` selects only decisions without one (exit 2
  with a bound). `--bands 0.5,0.7,0.9` (`check_band_cuts`: strictly
  increasing in (0, 1); exit 2 with any bound or `--no-confidence`)
  draws `-n` per band, bands `below 0.5`, `0.5 to below 0.7`, ...,
  `at least 0.9` (open outer ends, so disjoint and exhaustive) plus
  `without a confidence` when any lack one (`band_strata`). Each band
  has its own generator, `random.Random(int(sha256("seed/min!r/max!r/
  no_confidence")[:8]))` (`band_random`), so adding a decision to one
  band never changes another band's draw. A band with <= n members is
  taken whole (`criteria["census"]`); `--census` takes everything (no
  `-n`, which is refused, and no seed: `LLMSample.seed` None, id
  `.../census/...`). A plain draw stores exactly the old criteria
  (new keys only when used; `test_golden_draw` unchanged). Record: one
  `LLMSample` per band with `criteria["stratum"] = {group, band, bands,
  cuts}`, id `<group>/band=<i>`, its own population/digest/size, empty
  bands recorded too; chosen over one record with a band list because
  an older Scholar keeps `criteria` and paper dicts whole on save and
  reports each band correctly as its own sample (it only misses the
  upper bound in the sentence; a census it states as a random sample
  "(seed None)" with an interval). `--report`: `group_sample_reports`
  joins bands into a `StratifiedReport` (table: band, population,
  drawn, reviewed, changed, rate, interval; census band no interval,
  "census, all reviewed"/"k left"); JSON keeps old keys for plain
  samples (`census` added only for a census), stratified: `stratified`,
  `bands` (+`band`, `census`), `estimate` (null until complete).
  `stratified_estimate`: p = sum N_h x_h/n_h / N and changed among the
  not reviewed sum (N_h - n_h) x_h/n_h (Franco, Little, Louis, Slud
  2019, JSSAM 7(3), eq. 10; read in full, authors' final version), given
  only when every band of the group is present, has no decision not
  found (a lost session is no random loss), has no unreviewed decision
  and has a review left (resets are left out of n_h and named);
  otherwise `StratifiedReport.withheld_reason()` gives the sentence's
  reason (JSON `estimate_withheld`, null once given). **No interval for
  the whole**: Franco et al.'s Wilson-with-effective-size results
  exclude zero estimated variance (all bands agreeing) and their
  smallest expected proportion is 0.05 (n >= 30). Per-band intervals
  stay.
- **Report.** `build_review_provenance_latex` calls
  `llm_review.build_llm_screening_latex` (one local import + call): an
  "LLM screening" section with models, prompt versions, dates, the
  truncated (from each decision's flag, no character count) and
  unrecorded counts, and `sample_report_sentence` per sample (one for
  all bands of a stratified sample; old samples byte-identical, pinned
  by `TestScreeningSectionWithBands`; a census says "A census of all
  N ..." without seed or interval)
  (other pooled sessions are loaded read-only). Nothing when the
  session has no LLM decisions and no samples.

### Interactive Tutorials (`scholar tutorial`)

`scholar tutorial list|run|review` is [pytorial](https://github.com/dbosk/pytorial)
mounted through `pytorial.cli.add_typer_subcommand` in `cli.nw`
(`<<tutorial command>>`, namespace `scholar`). It serves pytorial's own
`using-tutorials` lesson plus the files named in `TUTORIAL_FILES`, in that
order (the order is the lesson order; a directory would list
alphabetically). An untangled checkout mounts nothing instead of failing.

- **Sources.** `src/scholar/tutorials/<id>.nw` tangles to `<id>.md` (what
  pytorial runs; gitignored, shipped as package data via
  `[tool.setuptools.package-data]`) and weaves to `<id>.tex` (a chapter in
  the Tutorials part of `doc/scholar.pdf`). The `.md` is the learner's
  text; the woven chapter explains *how the lesson teaches* (what a step
  varies, what it holds invariant, why the order), and that reasoning is
  the chapter's own content, so it goes in body prose, not `\ltnote`.
- **Sandbox.** `tutorial_shell_runner` sets `SCHOLAR_DATA_DIR` to
  `<workspace>/scholar-data` (per run, so `--restart` is a clean slate
  and practice sessions never reach the real session list) and prepends
  the interpreter's bin dir to `PATH` (so `uv run scholar tutorial run`
  finds the same `scholar` and `llm`). The cache is shared on purpose.
  Rate-limit memory lives in the data dir, so lessons only use keyless
  providers (openalex, arxiv). Hook subprocesses (`check_command`,
  `post_command`) inherit the process environment, which the runner also
  updates; lessons validate with `required_patterns` only.
- **Anchors.** Steps validate on a regex for the command typed plus
  Scholar's own fixed output strings (`Saved session:`,
  `Queries by provider:`, `Exported:`, `Prompt (dry run):`, ...), never
  on ranking-dependent titles. Inside a code chunk a line must not start
  with `@` or `<<` (noweb markup): indent BibTeX examples by one space.
- **Adding a lesson.** Write `src/scholar/tutorials/<id>.nw` with root
  chunk `<<[[<id>.md]]>>=` and `id: <id>` in the front matter; add it to
  `src/scholar/tutorials/Makefile` (`MODULES` and `DOC` plus the two
  dependency lines), `TUTORIAL_FILES` in `cli.nw`, `SRC_TEX` in
  `doc/Makefile`, and an `\input` in `doc/scholar.tex`. The parametrised
  test in `cli.nw` then loads it with pytorial's parser.

## Testing

```bash
uv run pytest tests/
```

Key test files:
- `tests/test_providers.py` - Provider unit tests (mocked HTTP)
- `tests/test_scholar.py` - Data model tests
- `tests/test_cli.py` - CLI integration tests

A test that puts a stand-in module into `sys.modules` does it with
`monkeypatch.setitem(sys.modules, name, module)`, never by assignment:
an assigned fake stays for every later test in the process (#284: the
rq test left a fake `llm` without `UnknownModelError`, and later tests
passed or failed by order).

Unit tests are offline by construction (`tests/conftest.py`, tangled from
`cache.nw`): the autouse `isolate_cache` fixture unsets every provider
key/option variable (`S2_API_KEY`, `OPENALEX_API_KEY`, `IEEE_API_KEY`,
`WOS_*API_KEY`, `SCOPUS_API_KEY`, `SCOPUS_INST_TOKEN`, `SCOPUS_VIEW`),
the contact emails and the proxy/User-Agent variables, so a test that
needs a key sets it explicitly. It also resets `pyalex.config.email`
and (except for live tests) `pyalex.config.api_key`, which the OpenAlex
providers built at import (during collection) had set from the
developer's environment (#160; pyalex is imported inside the fixture).
For non-live tests it also sets the registered providers' key
attributes (`PROVIDER_KEY_ATTRIBUTES`: `api_key`, `inst_token`, WoS's
`_api_key`/`_starter_key`/`_expanded_key` and the derived
`_api_tier`/`_api_url`) to None, restored afterwards (#174);
`test_keys_read_at_import_are_cleared_in_tests` checks it in a
subprocess with dummy keys in the environment. The autouse `block_network` fixture
refuses DNS and connections to anything but loopback and **fails the
test** naming the hosts (providers swallow errors, so a refusal alone
would go unnoticed). Both exempt `@pytest.mark.integration` tests, which
run only with `--run-live` and keep the developer's keys. No `env -u`
prefix is needed to run the suite safely. The autouse
`fresh_paper_registry` fixture gives every test an empty `PaperRegistry`
(`Paper.from_dict` returns the registered object for a known id, so a
shared registry let one test's titles leak into the next), and
`fresh_rate_limiters` returns the limiter registry to its import-time
state after every test (test-created limiters dropped, the others'
limits, last request and warning flag reset). It restores rather than
empties: `providers limits` lists Crossref/Unpaywall only because
importing `scholar.crossref`/`scholar.unpaywall` registers their
limiters. `scholar.cli` imports Unpaywall lazily, so the fixture imports
`scholar.providers`, `crossref` and `unpaywall` itself (inside the
fixture, never at conftest level, #132) before taking its snapshot;
otherwise the first test to trigger the import lost the registration at
teardown (#131). No test needs to pop `ratelimit._LIMITERS`.

Per-test fixtures cannot protect state touched at import or at exit:
provider caches load when their module is imported (during collection)
and the `atexit` hook saves them after monkeypatch has restored the
environment, which used to overwrite the real `~/.cache/scholar`
(search and LLM caches) on every run (#132). `conftest.py` therefore
sets `SCHOLAR_CACHE_DIR`/`SCHOLAR_DATA_DIR` to a per-process temp dir
at import time; keep it free of module-level `scholar` imports.
`test_a_test_run_leaves_the_real_directories_alone` checks this in a
subprocess with a fake `XDG_CACHE_HOME`.

## Adding Features

### New Provider

1. Create class implementing `SearchProvider` protocol in `providers.py`
2. Call `register_provider(ProviderClass())` at module end
3. Add tests in `test_providers.py`

### New CLI Command

1. Add `@app.command()` decorated function in `cli.py`
2. Add tests in `test_cli.py`

A chunk tangled into a command function must not use one of that
function's parameters as a `for`, `with ... as` or `except ... as`
name: Python has no block scope, so it overwrites the option for the
rest of the command (#280: `sessions decide --keep-trace` printed a
field name as the session's name). `TestNoLoopRebindsAParameter` in
`cli.nw` parses `cli.py` and fails on any such binding; plain
assignments (`by = by.strip()`) are allowed.

## Literate Programming

This project uses noweb-style literate programming. The `.nw` files are the source of truth:
- Edit `.nw` files, then tangle to generate `.py` files
- Use the `literate-programming` skill when modifying `.nw` files

The woven document (`doc/scholar.pdf`, pdfLaTeX, T1) must keep building
(#279, cli.nw `sec:woven-document`). `TestWovenDocumentSources` (in
test_cli.py, no LaTeX, under a second per check) reads every
`src/scholar/**/*.nw` and fails, naming file and line, on (a) a
documentation-chunk quote that takes a LaTeX bracket: noweb closes a
quote at the *last* two of a run of `]`, so `\item[A [[x]]]` leaves the
label open (runaway argument) and `\item[[[x]]]` (or `\item [[[x]]]`)
loses the label;
write `\item[A [[x]] ]` / `\item[ [[x]] ]` (`[[[]]]`, quoting code that
ends in `]`, is fine); (b) a character pdfLaTeX cannot set: allowed are
printable ASCII and tab, U+00A0-U+024F outside `review.T1_UNSET_RANGES`,
the `\newunicodechar`s of `doc/preamble.tex`, and
`DOCUMENT_EXTRA_CHARACTERS` (eleven code points with the `.dfu` file
declaring each, checked by a `latex`-marked test). Write CJK, Cyrillic,
U+2028, U+FEFF and the like in code chunks as Python escapes
(`"\u5b66"`), as
most non-Latin tests already did; name them in the prose if the reader
needs to know. The full build is `make -C doc check
LATEXFLAGS="-shell-escape -interaction=nonstopmode"` (between 7 and
26 minutes on the machines tried, longer under load; 2471 pages):
`check` fails unless `ltxobj/scholar.log` and the PDF exist and the
log is newer than every source, and on `^! `, "There were
undefined", "Label(s) may have changed" or "Rerun to get" in the
log; the shared rule fails on none of these reliably; the root `doc/scholar.pdf` target (used by
`publish-github`) runs it.
`doc/Makefile`'s rules for `../src/scholar/%.tex` name the `.nw`, so a
changed source is re-woven (before, a stale woven chapter was used).
`doc/preamble.tex` redefines noweb's `\@subpageref` to always print
the chunk letter (`1865a`): with noweb's default, a letter only when
the page holds 2+ chunks, the references' width depended on the page
breaks and the document flipped between two layouts on every pass.

## Caching

Search results are cached to avoid redundant API calls:

- **Library**: `cachetools` with `@cachedmethod` decorator
- **Storage**: Pickle files per provider in `~/.cache/scholar/`
- **Expiration**: Never (manual clearing only)

CLI commands:
```bash
scholar cache info   # Show cache statistics
scholar cache clear  # Delete cached results (keeps LLM caches)
scholar cache clear --include-llm  # ... and the LLM synthesis caches
scholar cache path   # Print cache directory
```

`cache clear` keeps the `llm_*.pkl` caches (`cache.is_llm_cache`: the
synthesis prose of `scholar llm synthesize`, paid model output that
never goes stale) and says how many it kept; `cache info` lists them on
their own line. `clear_cache()` also empties the in-memory copy of each
deleted cache in `CACHE_REGISTRY`, else the exit hook would write it
back (any cache whose module the process has imported is in memory;
since #130 the CLI no longer imports `scholar.crossref` at startup,
only in the commands that use it).

`scholar cache clear --provider NAME` (repeatable) deletes only
`NAME.pkl` (`clear_cache(providers=[...])`), also emptying its in-memory
cache. Valid names are the registered providers plus `crossref` and
`unpaywall`; an unknown one exits 2 listing them. It cannot be combined
with `--include-llm` (exit 2 / `ValueError`).

Environment variable: `SCHOLAR_CACHE_DIR` to override cache location.

**Concurrent processes** (#175: two processes racing emptied the real
cache). `load_cache` returns a `PersistentCache` (a `dict` subclass with
a `changed` flag set by every mutating method). `save_cache` (and so the
`atexit` hook `save_all_caches`):

- skips a `PersistentCache` that was not changed (plain dicts are always
  saved), so read-only processes never write. The flag does not see
  changes *inside* a value: to add to a cached entry, reassign the key
  (`cache[k] = {**cache[k], "field": x}`), as the synthesis does for
  its report abstract;
- under `utils.file_lock` on `.<name>.pkl.lock`, re-reads the file and
  writes the union (in-memory wins on a shared key) with
  `utils.atomic_write_bytes` (temp file, fsync, `os.replace`), so a
  reader never sees a partial file and a save never drops another
  process's entries. Cache saves wait up to `CACHE_LOCK_TIMEOUT` (60 s,
  not the sessions' 10 s: a save re-reads and writes the whole file,
  0.6 s for 6 MB). Past it the save runs unlocked: still atomic, never
  truncated, but entries can be lost if another process replaces the
  file in between;
- never writes over a file it cannot read (`read_cache_file` catches
  any unpickling error; `load_cache` warns with the path and returns an
  empty cache): the file is kept and the entries go to a unique
  `<name>.pkl.unmerged-<UTC time>-<random>` beside it (mkstemp), with a
  warning. Nothing merges it back; `cache info` lists these files with
  a hint and `cache clear` deletes them by the caches' rules
  (`--provider`, LLM caches kept without `--include-llm`).

The files stay plain pickled dicts, readable by older versions.
`clear_cache` deletes each file under the same lock, but a process
running at the time keeps its loaded entries in memory and writes them
back at exit if it changes its cache (union cannot tell deleted from
lost entries); clear again once the other processes have ended.
Not covered: an older scholar without the lock writing in place, and
processes on different machines.

The keyed REST providers cache manually (search wrapper +
`_search_uncached` returning `(papers, cacheable)`) instead of via
`@cachedmethod`, so a rate-limited or errored empty result is never
frozen into the persistent cache.

## Rate Limits and Quotas

`ratelimit.py` tracks provider rate limits and quotas **persistently
across CLI invocations** — necessary because e.g. IEEE allows only 200
requests/day and each `scholar` run is a fresh process.
Searches fetch everything by default (#301, see Search Limit), so one
broad IEEE search (200 requests of 200 records) can spend the day, and
every OpenAlex page counts against its budget; the large-total notice
appears while such a search runs.

- Providers declare limits as class attributes read via `getattr`:
  `LIMITS = Limits(per_second=10.0, daily=200)` (IEEE), plus optional
  `QUOTA_GROUP` for providers sharing one API budget (the eight
  OpenAlex-backed providers share group `"openalex"`).
- Providers bracket each HTTP request with `limiter.acquire()`
  (paces, counts, raises `RateLimited` when the budget is spent) and
  `limiter.record_response(response)` (429 → cooldown honoring
  `Retry-After`; syncs `X-RateLimit-*` headers, which is how Scopus's
  weekly quota is tracked). IEEE additionally decodes Mashery
  `X-Mashery-Error-Code` 403s: `ERR_403_DEVELOPER_OVER_RATE` = daily
  quota spent (marks the day exhausted), `OVER_QPS` = transient.
- State: one JSON file per quota group in
  `$SCHOLAR_DATA_DIR/rate_limits/` (data dir, NOT the cache dir —
  `scholar cache clear` must not erase quota memory). Written
  atomically on every change; fail-open on corruption. Every
  read-modify-write (`acquire`, `record_limit_hit`, the header sync)
  runs in `RateLimiter._exclusive`: the limiter's `threading.RLock`
  plus `utils.file_lock` on the state file (`.<group>.json.lock`), so
  threads and processes take turns and no count is lost (#148). The
  locks are never held across a sleep: `acquire` loops (lock, load,
  refuse/pace check, stamp+save or unlock-sleep-reload) and waits again
  if someone else stamped while it slept. Stamps are wall-clock
  (`_now`), shared across processes. Daily quotas
  bucket on the UTC calendar day and self-correct via the provider's
  own rejection if the guess is wrong.
- `search_provider()` (`scholar.py`, behind `Search.execute` and
  `rq`) pre-checks `check_available()` and **skips** a blocked
  provider with one `logger.warning`; its `SearchResult` has no papers
  and `error="skipped: <reason>; resets <time>"`, so it is recorded
  as a failed search and never overwrites an answered record (#165).
  The search still exits 0 (as when every provider fails).
  `providers check` reports `quota exhausted`
  (yellow, exit 0) from persisted state without burning a probe.
- CLI: `scholar providers limits` shows usage/remaining/reset per
  quota group; `--reset <name|all>` clears state (use after a key
  rotation or when the real quota is known to have rolled over).
- Tests: `tests/conftest.py` isolates `SCHOLAR_DATA_DIR` per test,
  resets the in-memory limiters (`fresh_rate_limiters`) and
  no-ops the pacing sleep; `test_ratelimit.py` controls time via the
  module's `_now`/`_sleep` seams.
- OpenAlex meters requests in credits (a search is 10 credits, $0.001;
  the keyed budget is 10000/day, reset at midnight UTC). `LIMITS`
  therefore declares only the rate (`per_second=10.0`, shared by the
  source-pinned providers through the quota group) and the budget state
  comes from OpenAlex: the health probe's
  `X-RateLimit-Remaining`/`X-RateLimit-Reset` headers are synced via
  `record_response`, a keyed probe also reads `/rate-limit` for the
  detail column, and a search 429 that spends the budget becomes a
  quota block until `X-RateLimit-Reset` (`_note_http_error`), logged
  with the reset time and a key hint (`_warn_budget_spent`, shared with
  `openalex-semantic`).
  `openalex-semantic` (1 request/s) passes the group limiter and then
  a second limiter of its own, `get_limiter("oa-semantic",
  Limits(per_second=1.0))`: the group's 10/s cannot be lowered for one
  member (`get_limiter` honours limits only on creation). The short
  name keeps the `providers limits` table within 80 columns. A
  semantic 429 is routed by #138's rule (`_budget_spent`): a spent
  budget goes to the inherited `_record_429` (blocks the group); any
  other 429 cools down only `oa-semantic` (without
  `X-RateLimit-Remaining`). `check()` asks the group
  (`check_available`) before acquiring `oa-semantic`.
- OpenAlex prepaid credit (#138) is drawn after the daily allowance,
  and `X-RateLimit-Remaining(-USD)` count the allowance only (recorded
  2026-11-18); prepaid/one-time credit come as
  `X-RateLimit-Prepaid-Remaining-USD`/`X-RateLimit-Onetime-Remaining`.
  So: the detail column adds `+ $5.00 prepaid (expires …) + N one-time
  credits` when positive; a 429 is "spent" iff its body `reason` is
  `daily_budget` (documented: daily and prepaid spent), else iff
  `-Remaining-USD` ≤ 0 with no prepaid/one-time credit (headers read
  via `ratelimit._get_header`, either case);
  `OpenAlexProvider._record_response` drops `X-RateLimit-Remaining`
  before the limiter sync while such credit is reported, and for a 429
  whose `reason` is not `daily_budget`, so neither a spent day nor a
  per-second 429 blocks the quota group. Consequence: while prepaid
  credit is reported, `providers limits` gets no fresh remaining
  count (an earlier one until the reset, then none). A zero stored
  before the purchase stays until the reset
  (`providers limits --reset openalex`).
- Pacing is the limiter's job: S2 (`LIMITS` anonymous 1/3 per second,
  our own conservative choice: S2 documents only a shared 1000 RPS
  anonymous pool; `KEYED_LIMITS` 0.9, a margin under the documented
  1 RPS on all endpoints; `_acquire()` re-declares per request because a
  rejected key changes the rate), OpenAlex and arXiv (a
  `PacedArxivClient` subclass overrides the package's `_parse_feed`, with
  `delay_seconds=0`) and DBLP (`per_second=0.5`: its FAQ says 1-2 s
  between requests; DBLP never had pacing of its own, only its 429
  back-off) declare rates; no provider keeps its own timestamp.
  DBLP's 429 loop records only non-429 responses (a mid-loop 429 would
  start a cooldown that refuses the retry) and, on giving up, a
  cooldown of the last `Retry-After`; its back-off and zero-hit retry
  waits use `ratelimit._sleep`.
  `Limits.per_second` is a rate, not the old seconds-between-requests
  `RATE_LIMIT` (those names are gone). Health probes pass `acquire()` too
  and record their responses, so a probed 429 starts a cooldown.
  The Crossref and Unpaywall clients declare `LIMITS` too (Crossref
  5/s anonymous, 10/s with a mailto, #270; Unpaywall 10/s and its
  100000/day; Europe PMC 5/s) and go through `acquire()` /
  `record_response()`; `all_status()` lists every in-process limiter, so
  `providers limits` shows them alongside the providers.
  Every WoS request (searches, probe, and the extended methods: related,
  citing, references, citation report, `_get_uid_for_doi`) goes through
  `WebOfScienceProvider._get`; Scopus has no extended methods and all its
  requests already go through `ScopusProvider._get`. IEEE, HAL and WoS
  probes are counted too, and `pdf.resolve_doi_s2` uses the `s2` limiter.
- S2 has no urllib3 `Retry` (#148): `SemanticScholarProvider._send`
  (used by `_request`, so search, DOI lookup, citations/references and
  the 403 fallback) retries 429/500/502/503/504 and connection errors
  up to `MAX_RETRIES`, each attempt through `_acquire()`, backing off
  `RETRY_BACKOFF * 2**attempt` (at least `Retry-After`) via
  `ratelimit._sleep`. Like DBLP it records no mid-loop 429; when the
  retries run out (or `Retry-After` exceeds `MAX_RETRY_WAIT`) `_pause`
  calls `record_limit_hit`, so every path gets the cooldown;
  connection errors (incl. `SSLError`/`ProxyError`) that persist pause
  it for `CONNECTION_PAUSE` (60 s), so an unreachable S2 or a broken
  proxy fails fast instead of 14 s of back-off per call. Every retry
  adds to `last_retries`, which `search()` resets with `last_error`,
  so a page answered after a 500 shows "N after 1 retry". The
  offline tests in `TestS2OneRequestPerSecond` time arrivals at a
  loopback server (`s2_loopback` rewrites the host in
  `HTTPAdapter.send`), threads and two subprocesses included.
- Remaining (not done): urllib3 `Retry` back-off inside the
  Crossref/Unpaywall sessions is not counted by the limiter (only the
  request that reaches it is).

## Dependencies

- `requests` - HTTP client (PySocks, optional, for `socks5h://` proxies)
- `typer` - CLI framework
- `rich` - Terminal formatting
- `pyalex`, `arxiv` - Provider-specific clients (Semantic Scholar is
  called directly with `requests`)
- `cachetools` - Caching with decorators
- `pytorial` - Interactive tutorial runner behind `scholar tutorial`
- `llm` and its plugins (`llm-openai-plugin`, `llm-anthropic`, `llm-gemini`, `llm-mistral`, `llm-azure`, `llm-github-copilot`, `llm-gpt4all`, `llm-openai-via-codex`) - model access for `scholar rq` and `scholar llm`
- `platformdirs` - Platform-appropriate cache directory
- `filelock` - Cross-platform file lock around session/notes saves


## grepai - Semantic Code Search

**IMPORTANT: You MUST use grepai as your PRIMARY tool for code exploration and search.**

### When to Use grepai (REQUIRED)

Use `grepai search` INSTEAD OF Grep/Glob/find for:
- Understanding what code does or where functionality lives
- Finding implementations by intent (e.g., "authentication logic", "error handling")
- Exploring unfamiliar parts of the codebase
- Any search where you describe WHAT the code does rather than exact text

### When to Use Standard Tools

Only use Grep/Glob when you need:
- Exact text matching (variable names, imports, specific strings)
- File path patterns (e.g., `**/*.go`)

### Fallback

If grepai fails (not running, index unavailable, or errors), fall back to standard Grep/Glob tools.

### Usage

```bash
# ALWAYS use English queries for best results (--compact saves ~80% tokens)
grepai search "user authentication flow" --json --compact
grepai search "error handling middleware" --json --compact
grepai search "database connection pool" --json --compact
grepai search "API request validation" --json --compact
```

### Query Tips

- **Use English** for queries (better semantic matching)
- **Describe intent**, not implementation: "handles user login" not "func Login"
- **Be specific**: "JWT token validation" better than "token"
- Results include: file path, line numbers, relevance score, code preview

### Call Graph Tracing

Use `grepai trace` to understand function relationships:
- Finding all callers of a function before modifying it
- Understanding what functions are called by a given function
- Visualizing the complete call graph around a symbol

#### Trace Commands

**IMPORTANT: Always use `--json` flag for optimal AI agent integration.**

```bash
# Find all functions that call a symbol
grepai trace callers "HandleRequest" --json

# Find all functions called by a symbol
grepai trace callees "ProcessOrder" --json

# Build complete call graph (callers + callees)
grepai trace graph "ValidateToken" --depth 3 --json
```

### Workflow

1. Start with `grepai search` to find relevant code
2. Use `grepai trace` to understand function relationships
3. Use `Read` tool to examine files from results
4. Only use Grep for exact string searches if needed

