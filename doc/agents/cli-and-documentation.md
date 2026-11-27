# Lazy subcommands, tutorials and the methods part

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Snowball and Tuxedo Subcommands (lazy)

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

## Interactive Tutorials (`scholar tutorial`)

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
- **Lessons** (in order): first-search, reviewing-in-the-tui,
  enrich-verify-export, `tiered-search` (#310: one wording and its
  `--top 3` tier, a second wording, `sessions show`, a predicted then
  exported tier of two answers (with and without `--top`),
  `--rest-sample 2 --seed 7`, `sessions tier-sample --report` before and
  after the sample is decided), llm-synthesis, scholar-with-an-agent.
  OpenAlex, arXiv and HAL record `order: relevance`; Semantic Scholar
  (key optional) records relevance, `citations` (limited bulk) or
  `unknown` (unlimited) by `s2_order`, but its anonymous pool may refuse
  a learner, and DBLP serves an anti-bot page, so tiered-search poses the
  other-order contrast (S2 `citations`, IEEE `unknown`) as a question.
  A search a step refuses still ran and saved a record: the search steps
  say to `sessions retire-search tiers --record ID`. Pytorial's
  plain-string patterns collapse white space (Rich's wrapping is
  harmless); regex patterns do not, so multi-word regex anchors use
  `\s+`. Command patterns: names end with `(?=\s|$)`, long options take
  `[\s=]+`, lookaheads use `(?:.|\\\n)*` (continued lines);
  `TestTieredSearchPatterns` (cli.nw) feeds accepted and refused
  spellings. Tried live once (2026-11-23, two keyless OpenAlex requests).
- **Help pointers** (#310): `search`, `sessions export` and `llm
  classify` end their description with the lesson (`scholar tutorial
  run tiered-search`) and "Searching and screening" in doc/scholar.pdf
  (`TestHelpPointsToTheMethod`).
- **README** (#310): one section per kind of work.
  `TestReadmeCommands` (cli.nw, after the tutorial tests) parses every
  `scholar` command of its code blocks with the command line's own
  parser, every command of a line (split at `|`, `&&`, `||`, `;`, `&`
  by `shlex` with punctuation characters; redirections dropped; `uv
  run`, `env`, `VAR=...` prefixes taken off) (`make_context` down the
  groups, as Click's `Group.invoke`;
  Typer carries its own copy of Click, `typer._click`, so the test
  catches `typer.TyperException` with exit code 2, not
  `click.UsageError`), in a temp dir where the `.tsv`/`.bib` files a
  line names exist; nothing runs. A README command line must parse.

## The methods part of the documentation (#310, #311)

`doc/scholar.pdf` has a part after the Tutorials, "The methods behind
the defaults" (`doc/methods/methods.tex`, plain LaTeX, no code):
`procedure.tex` (the procedure, each step with its command and a
`\cref` to its grounds), `measured.tex` (our own measurements of
2026-11-23, anonymised; the scripts read private sessions and are not
published), `search.tex` (the literature search of 2026-11-23, sessions
`screenlit-q1..q4`, one agent screener), one backing chapter per claim
(`stopping.tex`, `abbreviated.tex`, `databases.tex`,
`llm-screening.tex`, known items in `reporting.tex`). Wording rules
(#252): nothing from memory; our measurements are "these cases"; a tier
is not a stopping rule; negatives as "none among N screened of M; a
sample of n held none (interval)". `doc/methods/tables/` is generated
from copies of the sessions (query lists and matrices with
`hits_label`, audit tables by `generate_audit_table --bearing-only`
with `--cited-from doc/bibliography.bib`); regenerate, do not hand-edit.
A query matrix is a whole `tabular` in its file: an `\input` inside a
tabular followed by `\bottomrule` fails ("Misplaced \noalign").
- `doc/bibliography.bib`: the review's 51 entries with provenance
  blocks (check with backing-claims' `check_provenance.py --quotes`);
  `\printbibliography` is in `scholar.tex`'s backmatter. The preamble
  loads `longtable` and `array` for the audit tables.
- #311: latexmk `-use-make` asks make for a missing `.bbl`, and tex.mk's
  `.aux` rule (bibtexu) came first; `doc/Makefile` has an explicit
  `ltxobj/scholar.bbl: ltxobj/scholar.bcf` rule running biber. The
  pdfTeX warning `name{noweb.}` came from noweb.sty itself: page ranges
  in "used in" lists (`342--46`) reach `\@nwhyperpagenum` with an empty
  label; the preamble leaves such a range unlinked.
- `TestMethodsPartSources` (cli.nw, after the woven-document guard)
  runs the unsettable-character check over `doc/methods/**/*.tex` and
  the non-comment lines of `doc/bibliography.bib` (comments hold the
  verbatim quotes, which biber never passes on).
- In `\texttt` (Bera Mono, T1) `--` sets as one dash: write `-{}-`.
