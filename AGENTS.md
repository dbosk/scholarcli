# Scholar CLI - Agent Reference

## Project Overview

Scholar is a CLI tool for searching academic papers across multiple providers (Semantic Scholar, OpenAlex, DBLP, Web of Science, IEEE Xplore, Scopus, arXiv, HAL, and — via OpenAlex source pinning — the preprint servers SSRN, bioRxiv, medRxiv, ChemRxiv, Research Square, Preprints.org, and IACR Cryptology ePrint), plus OpenAlex's semantic search (`openalex-semantic`) as a check on keyword searches.

## How these notes are organised

This file is the index: what every session needs. It is loaded into
every request of an agent session, so it stays short (it was 283 KB
before it was split on 2026-11-27). The details of each area are in
`doc/agents/*.md`, listed under "Topic files" below.

- **Before changing code in an area, read its topic file.** The topic
  files record what the code does, why, and what was measured or
  decided; much of it cannot be seen from the code.
- **A change that alters what a topic file says updates that file in
  the same pull request.** A new area gets a new file and a row in the
  table. Do not add detail here: add a line to this file only when
  every session needs it.
- A reference such as "see Search Limit" names a section or a
  paragraph that begins with that name in bold. The table says which
  file holds it, and `grep -rn "Search Limit" doc/agents/` finds it.

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

### Data models in brief

- **Paper** (`scholar.nw`): `title`, `authors`, `year`, `doi`,
  `abstract`, `venue`, `url`, `source`, and more. `Paper.id` is the DOI,
  else a hash of the title and the first author's surname.
- **SearchResult**: `query`, `provider`, `timestamp`, `papers`,
  `filters`, `limit`, and the outcome (`error`, `retries`). Never show a
  failed result as 0: format counts with `hits_label`.
- A session (`review.nw`) holds one `SearchRecord` per provider search,
  identified by `(query, provider, filters key)`, and the decisions
  (`ReviewDecision`), each linked to the records that returned its
  paper (`found_by`).

Everything else about them: `doc/agents/search-records.md`.

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

## Topic files

In `doc/agents/`.

| File | Read before changing | Sections |
|------|----------------------|----------|
| `search-records.md` | `scholar.nw`'s data models, how a search is recorded in a session, `--limit`, `--in`, the order and places of answers, `prov found-via` | Data Models; Search Limit (#301); Order of answers (#303); Title-and-Abstract Search (`--in`); Search Provenance (`prov found-via`) |
| `providers.md` | any provider in `providers.nw`: endpoints, errors and what a failed search records, health checks, DBLP, Scopus views, Semantic Scholar's two searches, the semantic check, the contact address | Semantic Scholar: relevance vs bulk search (#161); Preprint-Server Providers and Groups; Semantic Search Check (#136); Error Handling; Provider Health Checks; DBLP Query Sanitization; Scopus Empty Results; Scopus Views; Contact Email; Provider Text Cleaning |
| `network-cache-ratelimits.md` | `network.nw`, `cache.nw`, `ratelimit.nw`: the proxy route and User-Agent, identifiers in URLs, what a cache may store and how it is saved, quotas and pacing (Crossref's two pools in detail: `enrichment.md`) | Network: proxy and User-Agent; Caching; Rate Limits and Quotas |
| `enrichment.md` | `pdf.nw`, `enrich.nw`, `unpaywall.nw`, `crossref.nw`, `europepmc.nw`: the PDF cache and `pdf import`, `scholar enrich` and its tallies, abstract sources, doubtful abstracts, retraction checks | PDF Cache and `scholar pdf import` (#296); Open-Access Lookup (Unpaywall); Abstracts from Crossref and Europe PMC (#260); Abstracts stored as paragraphs (#290); Doubtful Abstracts (#287); Currency / Retraction Checks |
| `versions-copies-renames.md` | `preprint.nw`, deduplication, `sessions reconcile`, tombstones (`folded`) and rename records (`renamed`), DOI-less ids | Preprint Fallback (adopt a preprint when no PDF is found), with Version-aware dedup, DOI-less copies and namesakes, Renames |
| `review-sessions.md` | `search -n` appends, `sessions show`, `sessions decide` (sources, `--force`, tags, `--untag`, `--keep-trace`, agent reasons), who decided as shown in outputs | Headless Review Sessions (with Agent reasons, Unknown stored sources) |
| `decision-checks.md` | batch ids and `--sheet`, the quote check, the batch check and `sessions check-batches`, `--dry-run`/`--strict`, the line on records decided without an abstract | Checks on a batch of decisions: Batch ids; Quote check; Batch check; Records decided without an abstract |
| `session-corrections.md` | `sessions relabel`, `sessions reset`, the human review record, `sessions set-abstract`, `sessions retire-search` | Correcting a session's record: Correcting a source (relabel); `sessions reset`; Human review record; `sessions set-abstract`; `sessions retire-search` |
| `screenings-agreement.md` | `ReviewDecision.screenings`, `sessions screen`, TUI blind review, `agreement.nw` (`sessions agreement`, `sessions conflicts`), the double-screening text of the report, synthesis summary and audit caption | Screenings: a second screener's verdicts (#253, part A); Agreement and conflicts (#253, part B); Double screen in the documents (#253, part E) |
| `screen-sheets-tiers.md` | `sessions export -f screen-sheet` (`--batch-size`, `--pending`, `--top`, `--min-providers`, `--rest-sample`), `sessions tier-sample`, `llm classify --top/--tier-sample` | Screen sheet; Screening tier; Sample of the rest |
| `session-integrity.md` | how a session argument is resolved, `save_session` (merge, lock, refused saves, `sessions recover`), baselines, appends, notes locks, `sessions export`'s staged moves | Session Arguments; Session Integrity |
| `exports-latex.md` | `bibtex+prov` and `scholar prov`, `search -f csv`, `--spreadsheet-safe`, the LaTeX escapers, cite keys, `.bib` field values, the report, the audit table and `--cited-from` | Provenance Round-Trip; `search -f csv` rows (#300); Spreadsheet-safe CSV (`--spreadsheet-safe`, #285); LaTeX Output: Standalone, Fragment, Audit Table |
| `llm-screening.md` | `llm_review.nw`: the prompt and its pinned version, vocabulary and categories, the retry and run tally, the audit fields, `llm sample`, second screens, unknown models | Classifier Vocabulary; LLM Screening Record and Review Samples (Samples, Second screen, First tier) |
| `cli-and-documentation.md` | `cli.nw`'s lazy `snowball`/`tuxedo` loading, `scholar tutorial` and its lessons, the part "The methods behind the defaults" and `doc/bibliography.bib` | Snowball and Tuxedo Subcommands (lazy); Interactive Tutorials (`scholar tutorial`); The methods part of the documentation (#310, #311) |

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

Outside pytest nothing is isolated. When you run `scholar` (or import
it) from a checkout to try something, set `SCHOLAR_CACHE_DIR` and
`SCHOLAR_DATA_DIR` to scratch directories on that command, so that a
development build never reads or writes the real cache and sessions.

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
needs to know; (c) a TeX special character standing bare in the prose
of a documentation chunk or of `doc/scholar.tex`/`doc/introduction.tex`
(`documentation_problems`, a small tokeniser over whole chunks, since
quotes run over line ends; `doc/preamble.tex` is left out): `#`
outside a `\newcommand`-family body, `&` outside an alignment
environment, `_`/`^` outside math, inline math not closed in its
paragraph, `}` without `{` or `{` not closed in its chunk, `%` right
after a number (`50%`: the rest of the line is silently dropped), a
`[[` never closed, and `\verb` (or a `#`/`%` in `\url`, `\path`,
`\href`, `\mintinline`) inside another command's braced argument.
Legitimate places it knows: code chunks, `[[...]]` quotes (also over
line ends), `verbatim`/`minted`/`lstlisting` and kin, `\verb`,
`\mintinline`, `\url`, `\path`, `\href`'s URL, math (`$`, `\(`, `\[`,
equation/align...), name arguments (`\label`, refs, cites, file
names), escapes and comments. `\texttt` protects nothing. It cannot
see: `~` (always legal), a backslash before an unknown word, a `$`
pair around prose (`$5 and $6` prints "5and6"), a `%` comment that
was meant as text after a non-number, a misplaced but counted brace,
verbatim in a bracketed argument (`\item[...]`), undefined macros.
Weaving a file without error proves nothing: noweave runs no TeX
(#318/#319 written bare stopped the book after the changed files wove
cleanly). New environments or commands with verbatim or name
arguments go in the lists in cli.nw `sec:woven-document`. The full
build is `make -C doc check
LATEXFLAGS="-shell-escape -interaction=nonstopmode"` (between 7 and
26 minutes on the machines tried, longer under load; 2692 pages at
6b9d135). `check` is `doc/check.mk` (included by `doc/Makefile`; it
sets latexmk's `$max_repeat=10`) plus `doc/check-settled.py`: it fails
on a missing or stale log, a LaTeX error, undefined references,
missing PythonTeX output, or a non-zero build status, and passes a
**cycle** of the references (a state that comes back within its 8
extra runs: a two-state flip, or up to 8 states; remembered in
`ltxobj/scholar.cycle`) with the warning "the references alternate
between two states and cannot settle" or "... cycle through N states
...". The full description is in cli.nw `sec:woven-document`
("What the check accepts", "Cycles of the references");
`TestDocumentCheck` (latex marker, about a minute and a half) tests it
on small documents. The root
`doc/scholar.pdf` target (used by `publish-github`) runs `check`.
`doc/Makefile`'s rules for `../src/scholar/%.tex` name the `.nw`, so a
changed source is re-woven (before, a stale woven chapter was used).
`doc/preamble.tex` redefines noweb's `\@subpageref` to always print
the chunk letter (`1865a`): with noweb's default, a letter only when
the page holds 2+ chunks, the references' width depended on the page
breaks and the document flipped between two layouts on every pass.

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

