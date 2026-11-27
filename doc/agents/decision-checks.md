# Checks on a batch of decisions

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Checks on a batch of decisions

These paragraphs continue `sessions decide` (review-sessions.md) and
apply to `sessions screen` too.

**Batch ids (#292, cli.nw `sec:batch-ids-in-files`,
`sec:batch-against-sheet`, `sec:sheet-batches`; review.nw
`sec:stored-batches`).** Since #349 every source stores it:
`human_batch` (5th of `HUMAN_AUDIT_FIELDS`, set by
`record_human_decision(batch=)`, cleared by a later human record
without one) and `llm_batch` (6th of `LLM_AUDIT_FIELDS`, the only one
of them saved only when set: `llm_audit_data`,
`LLM_AUDIT_FIELDS_SAVED_WHEN_SET`; in `MACHINE_AUDIT_FIELDS`, kept by
`--keep-trace`, in a reset's trace; `llm classify` leaves it None); CSV
columns `llm_batch` after `llm_abstract_truncated`, `human_batch` after
`human_reason`; `show -f json` per decision `human_batch` and
`llm_batch` (`null` when unset). The 18eda86 build reads its own
registries by name, so it ignores both and drops them on save (read).
`agent_batch` is the 4th field of
`AGENT_AUDIT_FIELDS` (so load, save-when-set, `decision_state`, merge,
`is_unscreened`, `clear_machine_audit`, the reset trace, `show -f
json`, and the CSV column right after `agent_decided_at` all handle it;
not in the text listing). A screening has key `batch` (in
`SCREENING_KEYS` after `sample_id`, `new_screening(batch=)`; a
snapshot takes the decider's batch via `SNAPSHOT_FIELDS`/
`verdict_screener`: agent, llm or human batch). `parse_tab_file` entries are 4-tuples `(line, id,
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
the sheet: …", "Missing rows are fine …" (a `decide --verdicts-file`
answers its whole sheet: missing rows are gaps, refused under `--strict`,
#347, review-sessions.md); ids not on the sheet set
`sheet_extras`, refused under `--strict` in `<<check the batch as a
whole>>`. `sessions reset --batch ID` (repeatable, `read_batch_id`;
alone or narrowing like `--source`) selects decisions by
`decision_trace(d).batches` (any source's batch, #349), never
screenings; a human or reviewed decision among them still refuses the
run (help says so); an id no decision carries is a stderr note (a
reset clears it). `stored_batch_check` → also
`StoredBatchCheck.batches` (`stored_batches`: rows with a batch id per
(what, kind, name, batch), what = agent decisions, human decisions,
screenings, or `classifier decisions` (llm parts with `llm_batch`,
`_relayed_batch_rows`; relayed reasons are not in runs), `batch_findings` whole, confidence included,
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
`StoredBatchCheck(shared, runs)`: runs group the trace parts with a
reason (`_stored_run_rows` over `decision_trace(d).parts`: agent parts
by (`agent_by`, `agent_decided_at`), since #349 human parts by
(`human_by`, `human_decided_at`) as "human decisions", row confidence
= the part's, so None for a human and for an agent part on a
human-source decision) and screenings with
`origin` "screen" (snapshots left out) by (kind, name, `recorded_at`);
a run of two or more works (title keys) whose rows all share one
reason gets a `one-reason` note and counts as ONE pooled record (a row
keyed by the run, "run of N (agent NAME, TIME)"), so a rule applied to
50 records counts once while the same reason across runs adds up; a
one-row run is an ordinary row (a per-record `decide --paper-id X
--reason R` loop adds up); the text adds `ONE_REASON_RUN_NOTE` (a file
with one reason on every line is a shared reason at decide/screen time
and `--strict` refuses it); shared reasons are looked for
session-wide over the pooled rows, agent, human and screening reasons
apart (`shared["agent decisions"]`, `shared["human decisions"]`,
`shared["screenings"]`), since a
stored run is neither a screener's batch nor a superset of one; flat
confidence is not judged from runs, only per stored batch id (#292,
above; a human's batch has no confidence, so never flat). The
incoming checks of `decide`/`screen` already read a human's file
(`TestHumanReasonsAreChecked`; a human's file confidences are dropped
before the check). Text:
counts line ("N agent reasons, H human reasons and M screenings in K
stored run(s)."), session-wide shared reasons, runs with one reason, stored
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
