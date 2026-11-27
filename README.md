# Scholar

A command-line tool for literature searches across many bibliographic
databases, and for the record of a systematic review built on them:
which searches were run, what each returned, who decided what about
each paper and why, and how the decisions can be checked.

Scholar searches, keeps every search and decision in a named review
session, and writes the session out as a report, an audit table, a
CSV or BibTeX with provenance. Every command takes `--help`; the
interactive tutorials (`scholar tutorial list`) walk through the work
in order, and `doc/scholar.pdf` documents the method and the code
(a literate program: the documentation and the implementation are one
text).

## Install

```bash
pipx install scholarcli
```

Or with `pip install scholarcli`, or `uv pip install scholarcli`.
Scholar needs Python 3.12 or later.

## A first search

```bash
scholar search "literate programming" -p openalex -l 20
scholar tutorial run first-search
```

The first line searches OpenAlex and prints the first 20 results. The
second starts the first lesson: each step opens a shell, you type the
command the step asks for, and Scholar checks the transcript before the
lesson moves on. Every lesson runs in its own workspace, so practice
sessions never appear among your own.

| Lesson | What it covers |
|---|---|
| `first-search` | search, providers, output formats, saving a session |
| `reviewing-in-the-tui` | recording decisions in the review screen |
| `enrich-verify-export` | abstracts and open access, retractions, exports |
| `tiered-search` | a search screened in tiers, a sample of the rest |
| `llm-synthesis` | setting up `llm`, LLM classification, an overview |
| `scholar-with-an-agent` | what an agent does with Scholar, and how to check it |

```bash
scholar tutorial list                       # the lessons and your progress
scholar tutorial run --restart first-search # start a lesson over
scholar tutorial review first-search        # read back what you typed
```

## Searching

```bash
scholar search "federated learning" -p openalex -p s2 -l 200
scholar search "literate programming" -p openalex --in title-abstract -l 50
scholar syntax
scholar providers check
```

A search fetches every result unless `-l N` limits each provider to N;
`scholar syntax` lists what an unlimited search costs per provider, and
an unlimited search says on stderr when a provider reports 10,000
records or more for it. `--in title-abstract` matches the query in titles and
abstracts only, where the provider can (OpenAlex and its preprint
servers, Scopus, Web of Science); Semantic Scholar, DBLP, IEEE, arXiv
and HAL ignore it with a warning, and the OpenAlex semantic search
refuses it, as it refuses every filter.
`scholar providers check` probes each configured provider once and
exits 1 when one of them fails, so it can stand before a long search.

| Provider | Name | Needs |
|---|---|---|
| Semantic Scholar | `s2` | `S2_API_KEY` optional |
| OpenAlex | `openalex` | `OPENALEX_API_KEY` optional (a key raises the daily budget OpenAlex grants), `SCHOLAR_EMAIL` optional |
| OpenAlex semantic search | `openalex-semantic` | as OpenAlex; opt-in, at most 50 ranked results |
| DBLP | `dblp` | nothing |
| arXiv | `arxiv` | nothing |
| HAL | `hal` | nothing |
| Web of Science | `wos` | `WOS_EXPANDED_API_KEY` or `WOS_STARTER_API_KEY` |
| IEEE Xplore | `ieee` | `IEEE_API_KEY` |
| Scopus | `scopus` | `SCOPUS_API_KEY`; `SCOPUS_INST_TOKEN` and `SCOPUS_VIEW` optional |
| SSRN, bioRxiv, medRxiv, ChemRxiv, Research Square, Preprints.org, IACR ePrint | `ssrn`, `biorxiv`, `medrxiv`, `chemrxiv`, `researchsquare`, `preprintsorg`, `iacr` | as OpenAlex (searched through OpenAlex, pinned to the server) |

Without `-p`, a search asks every available provider except the
semantic search and the preprint servers, whose papers a default search
already reaches through OpenAlex; `-p preprints` names arXiv, HAL and
all the preprint servers at once. `SCHOLAR_EMAIL` is the contact address for
the services that ask for one (OpenAlex, Crossref, Unpaywall, which
requires it). Scopus serves abstracts and full author lists only in its
COMPLETE view, which it grants to the subscribing institution's network
or with `SCOPUS_INST_TOKEN`; Scholar asks for it and falls back by
itself, and `scholar providers check` says which view you get.
`scholar --proxy socks5h://127.0.0.1:1081 search ...` (or
`SCHOLAR_PROXY`) routes the requests through a proxy, for example an
SSH tunnel to that network. Searches are cached without expiry
(`scholar cache info`, `scholar cache clear`), and the quotas of the
providers that have one (IEEE's requests a day, Scopus's weekly quota,
OpenAlex's daily budget) are tracked across runs
(`scholar providers limits`).

## Sessions

```bash
scholar search "literate programming" -p openalex -l 100 -n my-review
scholar sessions show my-review
scholar sessions decide my-review --source human --keep --doi 10.5555/example.1
scholar sessions decide my-review --source human --discard --tag off-topic --doi 10.5555/example.2
scholar sessions resume my-review
```

`-n` saves a search in a named session; another search with the same
name adds to it, and a paper found again keeps its decision.
`sessions show` lists each search with its outcome ("100 of 6,405
(capped at 100)"), the order its answer came in and the command that
repeats it, then the papers by status with their ids. `sessions decide`
records decisions without the interactive screen; `--source` says who
decided (`human`, `agent` or `llm`), and a discard needs a tag.
`sessions resume` opens the review screen (lesson
`reviewing-in-the-tui`).

## Screening in tiers

```bash
scholar sessions export my-review -f screen-sheet --pending --top 50 -o tier1
scholar sessions export my-review -f screen-sheet --pending --top 50 --rest-sample 60 --seed 7 -o rest
scholar sessions tier-sample my-review --report
```

A large search can be screened in tiers: `--top 50` lists the pending
papers at place 50 or better in an answer ordered by relevance
(`--min-providers N` and `--provider P` are other conditions), as a
tab-separated sheet, and writes the counts of what was and was not
selected to `tier1-tier.json`. `--rest-sample 60 --seed 7` draws a
seeded random sample of the pending papers the tier leaves out and
records the draw in the session. Once the sample is screened,
`sessions tier-sample --report` gives the share of the sampled records
that bear on the question, with a 95% interval, and a sentence for a
method section; before that, it gives no rate. Lesson `tiered-search`.

## The classifier and second screens

```bash
scholar llm context my-review "Does literate programming improve program documentation?"
scholar llm classify my-review --top 50 --count 20
scholar llm classify my-review --second-screen --over machine
scholar sessions screen my-review --as human --by "a colleague" --verdicts-file verdicts.tsv
scholar sessions agreement my-review
scholar sessions conflicts my-review --unresolved
scholar llm sample my-review --discarded -n 30 --seed 7
scholar llm sample my-review --report
```

`llm classify` asks a language model (through the
[`llm`](https://llm.datasette.io/) package and its default model) to
decide pending papers, with the human decisions as examples. Each
decision stores the model, the time, a prompt version, the model's
reason and its confidence, and is marked unreviewed until a human
confirms or changes it. `--second-screen` has the model screen decided
papers again and stores each answer as a screening beside the decision;
`sessions screen` stores a second screener's verdicts the same way.
`sessions agreement` gives the agreement between two screeners (with
Cohen's kappa and the prevalence and bias indices), and
`sessions conflicts` lists the papers they disagree on. `llm sample`
draws a seeded random sample of the model's unreviewed decisions for a
human to check, and `--report` gives how many of them the human changed,
with a 95% interval.

The model packages for OpenAI, Anthropic, Gemini, Mistral, Azure,
GitHub Copilot and GPT4All are installed with Scholar. To set keys and
the default model with the `llm` command of Scholar's own environment,
install with `pipx install --include-deps scholarcli`, then:

```bash
llm keys set anthropic
llm models                  # the models the installed packages offer
llm models default MODEL    # MODEL: one of those
```

Lesson `llm-synthesis`; `scholar llm synthesize` writes an overview of
the kept papers.

## Provenance

```bash
scholar search "literate programming" -p openalex -l 20 -n my-review -f bibtex+prov > refs.bib
scholar prov import refs.bib
scholar prov export refs.bib --in-place
scholar prov check refs.bib --quotes --metadata
scholar prov found-via doi:10.5555/example.1
```

`-f bibtex+prov` writes each BibTeX entry under a comment block that
records the search that found it (`FOUND-VIA`, a command that repeats
it) and has fields for the claim the entry backs, why it was picked, a
quote and how it was verified. `prov import` keeps those blocks in
`scholar notes`, and `prov export` writes them back above the entries.
`prov check` reports blocks with a field missing or left as a
placeholder, blocks no entry follows or whose header names another
key, quotes not found in the cached full text or abstract
(`--quotes`), and entries whose title, authors or year differ from
Crossref (`--metadata`); it changes nothing.
`prov found-via` prints, for each saved session that returned a paper,
the `scholar search` command that repeats the search. Lesson `scholar-with-an-agent`.

## Full texts

```bash
scholar pdf quote https://arxiv.org/pdf/2301.00001.pdf --claim "Literate programs are easier to maintain."
scholar pdf import paper.pdf --doi 10.5555/example.1 --from "the publisher's site, by hand"
```

`pdf quote` downloads a PDF (or uses the cached copy) and lists the
passages that best match a claim, ranked by words and then by the
language model. Where a publisher answers scripts with a bot check,
Scholar stops; `pdf import` puts a PDF you fetched yourself in the cache
under its DOI or URL, where `pdf quote` and `llm classify --full-text`
find it.

## What protects a session

Every save of a session merges with what another process saved
meanwhile, under a lock, and keeps the previous file as
`<name>.json.bak`. Commands that change many decisions at once
(`enrich`, `sessions reset`, `sessions relabel`, `sessions screen`, the
rest sample, ...) first keep a copy, `<name>.json.pre-<command>-<time>.bak`,
the newest three per command. When a save cannot take the lock, the
session is kept beside it as `<name>.json.unsaved-<time>-...`, and

```bash
scholar sessions recover my-review.json.unsaved-20261123T101500Z-ab12cd
```

merges it back (`--discard` deletes it instead).

## Exports

```bash
scholar sessions export my-review -f all
scholar sessions export my-review -f table --lang en --label my-review -o audit
scholar sessions export my-review -f table --cited-from refs.bib -o audit
scholar sessions export my-review -f csv --spreadsheet-safe -o decisions
```

`-f all` writes a CSV with one row per decision and a LaTeX report with
its BibTeX file. `-f table` writes an audit table, a LaTeX fragment
with one row per work and the reason it was kept or excluded; with
`--cited-from` a row counts as cited when the text's `.bib` cites the
work. `--spreadsheet-safe` puts a `'` in front of every CSV cell that
begins with `=`, `+`, `-`, `@`, a tab, a carriage return or a line feed,
the full-width forms of `= + - @`, or `'` itself (the list of OWASP's
page on CSV injection); numbers in the numeric columns are left as
they are, and the default CSV holds the stored text, for scripts. Lesson `enrich-verify-export`.

## Documentation

`doc/scholar.pdf` is built from the literate sources in `src/scholar`
(`make -C doc`): the tutorials' design, the method ("Searching and
screening"), and every module with its tests.

## License

MIT License, see [LICENSE](LICENSE).
