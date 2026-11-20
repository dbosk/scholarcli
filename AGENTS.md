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
| `src/scholar/preprint.py` | Preprint fallback (adopt a preprint when no PDF found) |
| `src/scholar/preprint.nw` | Literate source for the preprint fallback |
| `src/scholar/ratelimit.py` | Persistent cross-session rate-limit/quota tracking |
| `src/scholar/ratelimit.nw` | Literate source for rate-limit tracking |
| `src/scholar/network.py` | Proxy route and User-Agent for every request |
| `src/scholar/network.nw` | Literate source for the network settings |
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
  next to `last_error`. `search_provider` reads them Mock-safely
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
  caption's "Searched A to B." (+ "Search date unknown for k of n
  searches."); `bibtex+prov`'s `DATE` is the fetch date of the parts
  that returned the paper, "unknown (cached answer, fetch date not
  recorded)" when the cache does not know, the timestamp's date only
  for results without any dates. The session's `timestamp` is
  unchanged.

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
| Semantic Scholar | `s2` | REST API (`requests`): relevance search, or bulk search for operators / `-l 0` | `S2_API_KEY` (optional) |
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
  session, records the keyword default limit and applies filters.
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
`mailto` (personal data, #160), in any case. `check_provider` applies it to every health message; the
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

The never-expiring cache is keyed by view: default-view results keep the
historical 3-tuple key, COMPLETE results add `"COMPLETE"` as a fourth
part. COMPLETE results are served to everyone (unless
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
makes Scopus the *last* entry of `ENRICHMENT_PROVIDERS`. It returns
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
"earlier classifier call"` (key absent otherwise). The CSV
has no classifier-field columns, so it is unchanged.
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
llm` (the classifier's reason is `llm classify`'s) or `human` (out of
scope), `--by` alone, any bad file line (all named:
`cli.parse_reasons_file`), empty or > `review.MAX_AGENT_REASON_CHARS`
(2000, stripped, never truncated) reason. After loading: an unknown id
exits 1 (like `--doi`), one paper given two different reasons or
confidences exits 2, both unsaved. `--source agent` without a reason
warns on stderr and records the decision. Shown in `sessions show`
(a `reason (by): …` line, cut at `SHOW_REASON_CHARS` = 160; JSON:
the three fields, `null` when unset), the per-decision CSV (three
columns before `reset_from`; `paper_id` stays last) and the report (one English sentence after
the summary, `agent_reasons_sentence`: agent and agent_reviewed
decisions with/without a reason). An older Scholar loads such files
and drops the fields on its next save (checked with the installed
pre-#249 pipx build). A machine
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
after the agent-trace columns, before `paper_id`). Effects: audit table and
report show pending; a sampled decision reset at or after the draw
is gone from the sample (see Samples: `reset_since_draw`);
`first_made_by_llm` is False for any pending
paper; after a full reset the classifier vocabulary (tags of decided
papers) is empty, so pass `llm classify --tag`.
Together these let scripted/agent-driven systematic reviews produce the same
session record and `sessions export` audit trail as TUI reviews.

### Session Arguments

Every command that takes a saved session (`sessions show/export/decide/
relabel/reset/resume/reconcile/check`, `llm classify/status/context/
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
`review.sessions_mentioning(fragment)` finds the sessions by a
case-insensitive byte search for the id in each file (every decision
stores `paper_id`; an arXiv DOI also matches its bare arXiv id) and
decodes only those; non-ASCII/`"`/`\` fragments decode every file.

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
  (`n/a`, `saknas`) because the caption promises a confidence. The
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
  version-link DOIs, else `audit_work_key` under `plausibly_same_work`)
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
  matched. stderr: match counts (DOI / title / not in session), then
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
  a full-name-first "Databases:" sentence built from the providers
  the session searched (search records that answered at least once,
  zero hits included, plus the rows; rows only for old sessions). A
  database known only from records without an outcome and from no row
  is listed after it, "Also queried, with no recorded outcome: DBLP."
  (`AUDIT_STRINGS[lang]["unrecorded"]`, #188; the shortfall tuple's
  7th count); one
  whose `SearchRecord`s carry errors is marked
  "failed for k of n queries" / "incomplete for k of n queries"
  (localised), and one that failed every query outright is not
  named. `--bearing-only` lists only orders 0-2 and states the other
  counts in the caption. `all` stays csv + latex.
- The TUI's `prompt_for_report` keeps the standalone default.

### Provider Text Cleaning

`utils.clean_metadata_text` / `clean_paper_text` decode HTML entities,
strip inline tags (`<i>`, `<sup>`, …) and repair cp1252/Latin-1 mojibake
by a checked round trip. Applied at ingest in `Search.execute`,
`ReviewSession.add_papers_from_snowball` and at the end of
`enrich_paper`; the LaTeX escapers apply it too, for sessions recorded
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

- **No invented values.** `parse_llm_response` returns one entry per
  paper; an unusable answer (no answer, decision not kept/discarded, a
  discard without tags, confidence missing/non-numeric/outside [0, 1])
  gets `LLMDecision.answer_problem`, triggers the single retry, and is
  then withheld with the category-rule ones (`LLMDecision.problem`);
  `llm classify` and `rq` list them (`print_withheld_papers`) under
  "Left pending, no usable answer".
  Answers without a valid `paper_index` are skipped (never index 0).
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
  The TUI filter `s` (`sampled_for_review`) queues the unreviewed ones;
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

## Literate Programming

This project uses noweb-style literate programming. The `.nw` files are the source of truth:
- Edit `.nw` files, then tangle to generate `.py` files
- Use the `literate-programming` skill when modifying `.nw` files

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
  The Crossref and Unpaywall clients declare `LIMITS` too (10/s;
  Unpaywall also its 100000/day) and go through `acquire()` /
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

