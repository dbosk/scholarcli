# Providers

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Semantic Scholar: relevance vs bulk search (#161)

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

## Preprint-Server Providers and Groups

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

## Semantic Search Check (#136)

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

## Error Handling

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
`mailto`/`email` (personal data, #160, #259), in any case, and (#306)
the URL parameters `access_token`/`token`, the header/mapping forms
`api-key`/`api_key`/`apikey` (also with `x-` or `x-<vendor>-`, e.g.
`x-goog-api-key`)/`authorization` followed by `:` or `=` and a bare or
quoted value (scheme word Bearer/Basic/Token kept: `SECRET_HEADER`) and
any `Bearer <token>` (`BEARER_TOKEN`); in those two forms a value
counts only if it holds a digit or has >= `MIN_BARE_SECRET_CHARS` (16)
characters, so prose ("api_key: API key", "a bearer token") stays.
Idempotent: `[redacted]` is never redacted again. `check_provider` applies it to every health message; the
OpenAlex and IEEE (`apikey` in the URL) error logs use it. The OpenAlex
`/works` probe sends the key as `Authorization: Bearer` (documented,
as pyalex does); `/rate-limit` keeps the `api_key` parameter (the only
form documented for it).

## Provider Health Checks

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

## DBLP Query Sanitization

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

## Scopus Empty Results

A Scopus search with no hits returns one placeholder entry,
`{"@_fa": "true", "error": "Result set was empty"}` with
`opensearch:totalResults` "0" (live shape). `scopus_result_entries()`
drops it (any entry with `error`, or `@_fa` "false"), so it is never
converted into an empty paper (#106).

## Scopus Views

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

## Contact Email

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

## Provider Text Cleaning

`utils.clean_metadata_text` / `clean_paper_text` decode HTML entities,
strip inline tags (`<i>`, `<sup>`, …) and repair cp1252/Latin-1 mojibake
by a checked round trip. Applied at ingest in `Search.execute`,
`ReviewSession.add_papers_from_snowball` and at the end of
`enrich_paper` (except an abstract an abstract service supplied in
that call, `clean_paper_text_except`, #260); the LaTeX escapers apply it too, for sessions recorded
earlier. A DOI-less paper's hash id derives from the cleaned title, so a
record with markup ingested before this change gets a new id when it is
searched again.
