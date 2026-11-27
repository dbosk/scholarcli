# Review sessions without the TUI: appends and `sessions decide`

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Headless Review Sessions

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
(`--reason`/`--reasons-file` with `human` are accepted since #347 and
stored as `human_reason`, see "Human reason" in
session-corrections.md; `--by` alone is accepted for a human since
#257), `--by` alone for an agent, any bad file line (all named:
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

**Verdicts file (#347, cli.nw `sec:decide-verdicts-file`).** `decide
S --verdicts-file F [--source agent|human|llm] [--by N] [-c C]
[--sheet ...] [--batch ID] [--strict] [--strict-quotes] [--dry-run]
[--force] [--all-copies] [--keep-trace]`: lines as `sessions screen
--verdicts-file` reads them (`parse_verdicts_file`, `VERDICTS_LAYOUT`;
`ID<TAB>kept|discarded<TAB>TAGS<TAB>REASON[<TAB>CONFIDENCE]`, `# batch:`
lines). No second code path: the file is read into `reason_lines`
where a reasons file is read (a `VerdictLine` has every `ReasonLine`
field plus `status`, `tags`), selected by the same chunk (`trace_of`;
messages say "verdicts-file line N"; two lines clash when
`line_verdict` differs: every field but line, paper, batch), and the
recording loop takes status and tags per decision from its line
(`<<take the verdict for this decision>>`; `<<replace the tags of a
changed decision>>` reads `given_tags`). Usage errors (exit 2, before
loading): `--keep/--discard/--doi/--paper-id/--tag/--untag/--reason/
--reasons-file` beside it (all named), agent or llm without `--by`, a
bad line (discard without tag, two categories, bad verdict), an llm
line whose category does not fit (`verdicts_without_a_fitting_category`,
shared with `screen`), `--keep-trace` without `-c` and a line without
confidence. After loading: unknown id exit 1, clash exit 2; in a
session that `uses_categories`, every line of every source, a human's
included, needs exactly one fitting category (exit 2, lines named); the
one-verdict form (`--keep/--discard --tag`) and the TUI still let a
human record a contradicting pair until #349.
Per source: agent as `--reasons-file` (agent_reason/by/time/batch);
human: `record_human_decision(via="decide", by=..., reason=row)`, the
reason optional (`human_verdicts_layout()`: empty or `-` is none), a
confidence dropped with one note; llm: `llm_model` =
`--by`, `llm_reason` = `truncate_reason(row)`, `llm_decided_at` = run
time, prompt version and truncation left None (the report's sentence
now says "for k of them the prompt was not recorded" for decisions with
a model and no version; `sessions show` shows no model for any
classifier decision, as before); llm rows store no batch id (it is an
agent field). With `--sheet`, `whole_sheet` makes a missing sheet row a
gap: "A verdicts file answers its whole sheet ..." instead of "Missing
rows are fine", counted in `unanswered` (shared with `screen`, which
sets `whole_sheet = False`) and refused by `--strict`; rows given twice
with the same verdict (`twice`, per paper) are listed and refused by
`--strict` with or without a sheet (reasons files unchanged). Summary
"Marked 6 kept, 4 discarded by agent N in session 'x'" (dry run "Would
mark ...; nothing written.").
