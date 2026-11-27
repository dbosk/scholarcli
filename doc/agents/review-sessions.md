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
the summary: since #349 `decision_reasons_sentence`, see "One trace"
below). An older Scholar loads such files
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
included, is complete (`verdicts_without_a_fitting_category`, shared
with `sessions screen`): a keep names exactly one fitting category ("no
category" otherwise); a discard names one, or no category and an
exclusion criterion (a `reason_tags` tag; "no category and no
exclusion criterion" otherwise: note tags only). Since #349 (author,
2026-11-27) a bearing record excluded under a rule is a discard with
its criterion and no category, by every source; before, every row
needed a category. Then the fit rule for every way (below, "One
procedure for a human").
Per source: agent as `--reasons-file` (agent_reason/by/time/batch);
human: `record_human_decision(via="decide", by=..., reason=row)`, the
reason optional (`human_verdicts_layout()`: empty or `-` is none), a
confidence dropped with one note; llm: `llm_model` =
`--by`, `llm_reason` = `truncate_reason(row)`, `llm_decided_at` = run
time, prompt version and truncation left None (the report's sentence
now says "for k of them the prompt was not recorded" for decisions with
a model and no version; `sessions show` shows no model for any
classifier decision, as before); since #349 each source stores the
row's batch (`agent_batch`, `human_batch` via `record_human_decision(
batch=)`, `llm_batch`) and the old "batch ids given here are not
stored" note is gone. With `--sheet`, `whole_sheet` makes a missing sheet row a
gap: "A verdicts file answers its whole sheet ..." instead of "Missing
rows are fine", counted in `unanswered` (shared with `screen`, which
sets `whole_sheet = False`) and refused by `--strict`; rows given twice
with the same verdict (`twice`, per paper) are listed and refused by
`--strict` with or without a sheet (reasons files unchanged). Summary
"Marked 6 kept, 4 discarded by agent N in session 'x'" (dry run "Would
mark ...; nothing written.").
**Confirming by a file row (#349, cli.nw `TestConfirmingByAFileRow`).**
A human's row on an unreviewed agent/llm decision goes through
`mark_as_reviewed` like a human `--keep/--discard`: same status →
source `agent_reviewed`/`llm_reviewed`, the machine's trace (reason,
by, time, `llm_confidence`, batch) kept, `is_example` False, human
record written (row reason as `human_reason` if given, row batch as
`human_batch`); other status → `is_example` True. Tags follow
`tags_after_decision`: the row's tags are appended, the old category
dropped only when the row names one (so a same-category row moves the
category behind the old themes: `[supports-claim, loops]` + row
`supports-claim,recursion` → `[loops, supports-claim, recursion]`).
Since #349 part B a row (or `--keep/--discard`) that changes the
category is a change (`is_example` True; it was a confirmation from
#347 until then), see below. Stated in the `--verdicts-file` help and
docstring.

**One trace (#349, review.nw `sec:decision-trace`).**
`review.decision_trace(d)` → `DecisionTrace(source, decider, machine,
confirmed, parts)` of `TracePart(kind, name, reason, at, confidence,
batch)` (kinds agent/llm/human; stored field names unchanged). Decider
by source alone (not status): `REVIEWED_BY_A_HUMAN` → human part,
unreviewed known → the machine part (`MACHINE_OF_SOURCE`), unknown
source → None; `machine` = the source's machine also when reviewed;
`llm_confidence` only on that machine's part (a human part never has a
confidence); `confirmed` = reviewed source, decided, `is_example`
False; `parts` = every kind with any field set plus decider/machine
(an earlier classifier call under an agent's `--keep-trace` is a part,
not the machine). `.reason` = decider's words, else (confirmed) the
machine's; `.batches` = distinct part batches. Used by
`verdict_screener`, `stored_batch_check`, `sessions reset --batch`
and the reason count. **Decided without a reason** (author's rule):
reason = `reason_tags(tags)` (not `AUDIT_CATEGORIES`, not a key of
`AUDIT_STRINGS["en"]["notes"]`) or words. `decision_reason_counts` →
per source (order of `decision_source_counts`, decided only)
`ReasonCount(decided, in_words, tags_only, neither)`. `sessions show`
line "Reasons of the decisions: human (13): 0 in words, 11 tags only, 2
without a reason; ..." (before the quote "Reasons:" line) and JSON
`decision_reasons` {source: {decided, in_words, tags_only,
without_reason}}; both left out (`shows_decision_reasons`) when no
decision has words and none lacks a reason (all tags only). Report:
`decision_reasons_sentence` ("Of the N decisions, a give a reason in
words, b give only tags (themes or motivations) and c were decided
without a reason (by source, in that order: human 0, 1 and 0 of 1;
..."); with no words anywhere it returns the old
`agent_reasons_sentence` (or ""), so such reports are unchanged.

**One procedure for a human (#349 part B, review.nw
`sec:decision-rules`, tui.nw `sec:tui-human-decision`).** The three
ways a human decides (verdicts-file row, one-record `decide`, TUI key)
call the same functions of review.nw: `decision_tags(tags,
status_changed, new_tags, removed_tags)` (= `tags_after_decision` +
the new tags each once; decide computes it before recording and stores
it, so checks see the stored tags); `unfitting_category(status, tags)`
(the last category, `audit_category`, not in `STATUS_CATEGORIES`;
None for pending or no category) and `category_misfit(decisions,
status, tags)` (None when not `uses_categories(decisions)` before the
decision); `category_misfit_message(category, status)` (one line: what
fits, then `BEARING_EXCLUSION_ADVICE`); `changes_the_verdict(decision,
status, tags)` (status or deciding category differs). **Category
rule:** checked on the record AFTER the decision, every source, no
category never a misfit. `decide`: chunk `<<refuse a decision whose
category would not fit>>`, after the file's completeness check and
after the ids are looked up (needs the session), every selected record
(file rows and `--keep/--discard`), exit 2, "No changes saved. A stored
category stays unless --untag removes it." (a same-status decision
without a category keeps a stored misfit and is refused). The llm
pre-load check of a named `--tag`/row category stays. Before, a human's
or agent's one-record decide could store a bearing category on a
discard (pinned by `TestRelayedVerdictFitsItsDecision`, now refused).
Stored pairs are not rewritten; the audit table renders them as before.
**Changed category (D3):** `mark_as_reviewed(user_agrees=not
changes_the_verdict(...))` in decide and TUI; a decision without a
category keeps the stored one (confirmation if same status); removing
it (`--untag`, the TUI's quick keep, which clears all tags) is a
change; other tags or the human's own reason with status and category
as stored stay a confirmation (the author was asked about the category
only). A change: `is_example` True, so `decision_trace(...).confirmed`
False, the machine's reason no longer stands for it (counts as tags
only without the human's words in `decision_reasons`), the report's
confirmed/changed counts follow. **TUI:** the eight handlers (K, T, d,
C on list and detail screen) call `PaperReviewApp.decide_as_human(d,
status, tags)` (None = refused: notification, timeout
`RULE_NOTICE_TIMEOUT` 15 s, nothing stored, detail screen stays; else
whether a machine verdict changed) or `confirm_as_human(d,
reason=None)` (refused on a stored misfit pair: it would become the
human's; otherwise exactly as before, pinned field by field). Key `r`
(both screens) → `ask_reason` → `ReasonModal`: the machine's reason
(trace machine part), the human's present one, `earlier_reasons`
(humans' `human_reason`, most used first, `REASON_CHOICES` = 5; Tab
then Enter picks), an input (Enter; empty or Escape leaves the reason).
Pending → "Decide first ..."; human/reviewed → new
`record_human_decision(via="tui", by=reviewer, reason=, batch=kept)`;
unreviewed machine → `confirm_as_human(reason=)`; hidden blind paper →
refused like C. Opens by itself after a human changes a machine's
status or category (Escape dismisses). Detail screen (outside blind
review): "─── Decision ───", "Decided by: <source_label>[, confirmed|,
changed]", "Reason (<kind> [name]): <decision_trace(d).reason>"
(`decision_lines`); the blind review section reads its reason by
`decision_trace` too. **Still different for a human:** the TUI keeps
the stored source of an already reviewed decision when a human decides
it again (decide sets `human`); the TUI's tag dialogs replace the tags
whole, so a TUI keep can hold two categories (decide drops the old
one, #195); a confidence is the machine's only; `sessions screen`'s
human verdicts are not held to the completeness rule (machines only).
Audit table: a discard with a criterion and no category is labelled by
its criterion (`audit_exclusion_criterion`), sorted with the other
rows (`AUDIT_ORDER_OTHER`) and counted per criterion in the caption.
