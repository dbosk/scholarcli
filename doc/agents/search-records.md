# Papers, search results and search records

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Data Models

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

## Search Limit (#301)

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
  `-l5`, `--limit=5` and the limit first; tiered-search writes
  `(?:.|\\\n)*` for `.*`, so a continued line passes too), so a learner
  who drops it fails the step. `test_tutorial_searches_carry_a_limit` (any line running
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

## Order of answers (#303)

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

## Title-and-Abstract Search (`--in`)

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

## Search Provenance (`prov found-via`)

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

**Places (#302, review.nw `sec:review-found-by`, scholar.nw
`sec:answer-places`).** A link may be a `SearchLink`: a tuple subclass
equal to and hashing as its 3-tuple key, with `.rank` = the paper's
1-based place in that part's answer (`link_rank(link)`, None for a
plain tuple; not part of the identity). Saved as `"rank"` in the link
object only when set; `stored_rank` reads a whole number >= 1, else
None; old files load None (a pre-#302 Scholar reads only
query/provider/filters and drops `rank` on save: read from its
`_load_found_by_link`, not run). Source: `SearchResult.places`
(empty = list order) and `place_of(i)` (None for a merged result);
`deduplicate()` recomputes places (`answer_places`: first occurrence,
matched by id, title-author hash of a DOI paper with
`plausibly_same_work` for a DOI-less copy, version DOIs; a part known
only by `sources` -> None); `merge` sets `found_at` (places per
`found_in` entry, `places_in_parts`). `paper_search_links` returns
`SearchLink`s (recomputes places when `found_in`/`found_at` do not
fit). Every link site uses `record_link(link)` /
`record_search(q, p, k, rank)` (a held link keeps the smaller rank,
`smaller_rank`, so a place can predate the record now kept: the tier
asks whether the search ever ranked the paper high): the six append branches, folds (`reconcile_copies`,
`apply_tombstones`), the concurrent merge union. Repoints use
`united_links` (dedup, smaller rank): legacy replacement in
`create_review_session` and in the merge, `supersede_merged_records`;
a link moved to another record is a plain key, so no rank (a covering
record's link keeps a rank only if the paper already had one). Copies
(`list(prev.found_by)`) carry ranks. Snowball adds no links.
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
