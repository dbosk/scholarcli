# Network, caches and rate limits

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Network: proxy and User-Agent

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
- **Identifiers in URL paths** (#304): never paste a DOI or id into a
  URL; a `#` cut it at the fragment, a `?` started a query. Query
  strings go to `requests`/the client as a mapping. One encoder,
  `network.quote_identifier` (network.nw `sec:identifier-in-path`):
  encodes `# ? %`, space, C0/DEL, non-ASCII, `< > " { } | \ ^`, the
  backtick and `[ ]`; keeps `/ : @ ! $ & ' ( ) * + , ; =` literal. Rule:
  an identifier that worked before goes out exactly as before (DOI
  Handbook 4.7 would encode an inner slash, Crossref says not to;
  scholar always sent it literal). Used by
  `providers.s2_paper_url(paper_id, relation=None)` (DOI lookup,
  citations/references, `pdf.resolve_doi_s2`) and
  `pdf.doi_resolver_url(doi)`. `pdf.extract_doi` decodes a pasted
  doi.org URL once (`...CO;2-%23` was sent as `%2523`); a raw DOI is
  never decoded. The PDF cache key `get_cached_doi_pdf_path` stays
  unencoded (never requested). Already encoded, left as they were:
  Crossref and Unpaywall (`quote(doi, safe='')`, the `%2F` form is
  answered), OpenAlex (pyalex `quote_plus`s the whole
  `https://doi.org/...`; a space becomes `+`, unchecked whether
  OpenAlex reads it as a space), Europe PMC, IEEE, WoS, Scopus (query
  parameters), arXiv (library). Tests: conftest's `request_targets`
  (loopback stand-in for named hosts, rewrites in `HTTPAdapter.send`,
  keeps raw request targets; `paths()`/`queries()` decode),
  `awkward_doi` (`10.5555/a#b?c%d e<f>g`), and request lines pinned to
  what the code before #304 sent (`TestDoiInRequestPaths`).

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
