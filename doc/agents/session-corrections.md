# Correcting a session's record

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Correcting a session's record

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
after the agent-trace and human-record columns, before
`abstract_from`). Effects: audit table and
report show pending; a sampled decision reset at or after the draw
is gone from the sample (see "Samples" in llm-screening.md: `reset_since_draw`);
`first_made_by_llm` is False for any pending
paper; after a full reset the classifier vocabulary (tags of decided
papers) is empty, so pass `llm classify --tag`.
**Human review record (#257, review.nw `sec:human-review-record`).**
`human` is the dataclass default and needed no evidence, so scripts
writing through the API gave >1000 decisions a human source nobody
gave. `ReviewDecision` now has `human_decided_at` (UTC ISO),
`human_decided_via` (`tui` | `decide`, `HUMAN_DECISION_CHANNELS`) and
`human_by` (as given, never guessed), named once in
`review.HUMAN_AUDIT_FIELDS` (`human_record_of`; load, save only when
set via `human_record_data`, `decision_state`, concurrent merge,
`is_unscreened`; the append keeps the decision whole). NOT in
`MACHINE_AUDIT_FIELDS` (so not cleared by `clear_machine_audit`, not
in a reset's `trace`). Set only by `review.record_human_decision(d,
via, by=None, at=None)` (raises unless decided with a source in
`REVIEWED_BY_A_HUMAN` = human/llm_reviewed/agent_reviewed; `at`
defaults to `_utcnow`), called by the TUI's keep/themes/discard/confirm
in both screens, all through `PaperReviewApp.decide_as_human` /
`confirm_as_human` since #349 part B (after `mark_as_reviewed`;
`by=app.reviewer`, set by
`sessions resume --by` or the blind-mode name dialog, else None) and by `sessions decide`
with a human source (`--source human` or the terminal default; one
`utc_now_iso()` per run; `--by NAME` now accepted with human). The
API (`ReviewDecision(source=HUMAN)`, `mark_as_reviewed` alone) sets
nothing. A machine `decide` (with `--force` over a human/reviewed
decision) calls `clear_human_record`; `relabel_source` clears it and
keeps the set fields as `"human"` in its relabel record (key absent
without a record); a reset only takes unreviewed decisions, which have
none; a later human decision overwrites it (time included). Counted by
`human_record_counts(decisions)` (decided papers with
`human_decided_at` per `REVIEWED_BY_A_HUMAN` source) and
`decision_source_rows(decisions, always_note=False)` → `(label, count,
note)`, note "(k with a record of the review)" on those sources' rows
with a count, when `always_note` or any such decision lacks a record
(`source_row_text(count, note)`). `sessions show` "Decided by:" always
notes (`human: 1200 (0 with a record of the review)`), JSON adds the
three fields per decision (`null` when unset) and `review_records`
(counts by stored value); the report's "Decided:" rows, its abstract
sentence (`decision_sources_sentence`) and `llm synthesize`'s summary
note only when a record is missing, so a fully recorded session reads
as before; with the note they also give `REVIEW_RECORD_EXPLANATION`
once (`review_record_sentence`: after the report's summary, in its
abstract, after both synthesis summaries; no version or date in it).
The CSV adds `human_decided_at, human_decided_via,
human_by` after `agent_decided_at`. The audit table and its caption
are deliberately unchanged: they neither count nor mention the
records (tested byte-identical). Copies are compared by
`decision_verdict` (= `decision_state` without `HUMAN_AUDIT_FIELDS`;
LLM/agent fields stay in) in `_fold_direction`, `same_id_pairs` and
`_decided_pairs` (alike/conflicting), so two copies a human decided
alike at two moments still fold, are no alike pair and need no
`--all-copies`; a fold keeps the newer record (`newer_human_record`:
by `human_decided_at`, a record beats none; the fold also carries both copies' `abstract_set` records). `decision_state` (merge,
baseline, `pair_with_file`, `apply_tombstones`) keeps the record: those
compare one decision with itself across file versions. Wording: "without a record of the
review", never "not human" (old decisions have none). The default
source stays `human` (an undecided paper's). Checked 2026-11-20: the
pipx build of 4ba7a23 loads such a file and drops the fields on save.
**Human reason (#347, review.nw `sec:human-reason`).** 4th field
`human_reason`, the last of `HUMAN_AUDIT_FIELDS`, so every rule above
applies (saved only when set; in `decision_state`, so a concurrent
change is merged; not in `decision_verdict`, so copies decided alike
with two reasons still fold and the fold keeps the newer record's
reason; cleared by `clear_human_record`; kept in a relabel record's
`"human"`; CSV column `human_reason` right after `human_by`; `show -f
json` per decision, `null` when unset). Set only by
`record_human_decision(..., reason=None)`, through
`checked_human_reason` (stripped, blank -> None, over
`MAX_AGENT_REASON_CHARS` -> ValueError before anything is written); a
later human record without a reason clears it. The TUI passes one
since #349 part B: key `r` and the prompt that opens after a human
changes a machine's decision (`ReasonModal`, see review-sessions.md
"One procedure for a human"); a decision itself still records none.
`sessions decide --source human` takes `--reason`, `--reasons-file`
and a verdicts file's REASON (optional there: empty or `-`); a
confidence in a human's file is read, then dropped with one note
counting the lines. A human's confirmation of an unreviewed machine
call keeps the machine's trace: without a reason `human_reason` stays
None, with one both are stored. `reason_quote_checks` reads it as kind
`human` (`REASON_FIELDS`), so the decide quote check, `--strict-quotes`,
`sessions show`'s "Reasons:" line and marks and the JSON
`reason_quotes` (now with a `human` key) count it; the report's
sentence reads only the machine kinds (unchanged). `sessions show`
prints "reason (human, NAME): ..." under the agent's line
(`human_reason_line`). Report and audit table unchanged. **Batch and
fold (#349).** 5th field `human_batch` (see decision-checks.md "Batch
ids"). A fold keeps the newer record whole; when it has no reason and
the other copy's record has one, `warn_about_a_dropped_reason` logs one
WARNING "<old id>: the reason the human gave on this copy was not kept;
it was folded with <id>, whose newer record of the review has no
reason. The reason was: <text>" (the tombstone is an id map, so the
text goes into the warning; `sessions reconcile` prints it, also on
`--dry-run`; tested with the real command). The build of
main 18eda86 loads only its three fields by name
(`dec_data.get(name)`), so it ignores the field and drops it on save
(read, not run).
**`scholar sessions set-abstract S (--paper-id ID | --doi D) --file F
--from TEXT [--by NAME] [--replace] [--dry-run]`**, or `--abstracts-file
F` (lines `ID<TAB>FROM<TAB>ABSTRACT`, split at the first two tabs, so
tabs inside the abstract become spaces; fewer than three columns
refused; the `--reasons-file` conventions: `utf-8-sig`, lines end at
`\n`, blank/`#` skipped, ID = paper id or DOI bare/`doi:`;
`cli.parse_abstracts_file`, every bad line named, exit 2 before
loading) (#258, cli.nw `sec:sessions-set-abstract`, review.nw
`sec:set-abstract`) stores an abstract found by hand. `--file -` reads
stdin (a BOM is dropped, as `utf-8-sig` drops it from a file); `--from`
is required. `review.set_abstract(decisions, text, origin, at, by,
replace)` cleans the text (`clean_abstract_text` = `clean_metadata_text`
+ white space collapsed; empty → exit 2; above `LONG_ABSTRACT_CHARS` =
10,000 only a stderr warning), sets `paper.abstract` on every decision
holding the paper (one registry `Paper`) and records on each decision
`ReviewDecision.abstract_set` = `[{"at", "from", "by", "chars", "text",
"previous"}]` (`text` = the stored text, kept so that a replaced hand
text survives somewhere; `previous` only when an abstract was replaced;
`by` None unless given). A paper with an abstract is refused (exit 2,
each named, unsaved) unless `--replace`; an unmatched selector exits 1
unsaved; two batch lines giving one paper different texts/origins exit
2. A possible or foldable copy (`cli.possible_twins` over
`possible_copies` / `foldable_copies`, both directions) gets a stderr
note naming it and `sessions reconcile`, plus a second note when the
paper has no DOI and the copy is a DOI record with an abstract (a fold
keeps that one); the abstract is still set. `--dry-run` writes
nothing; else `keep_copy_before_run(session, "pre-set-abstract")`, one
`_utcnow()` time, `save_session`. The record is on the decision, not
on `Paper` (no new paper-merge rule): saved only when non-empty, old
files `[]`, kept by the append copy (stored abstract wins via
`stored_paper_with`), united in `merge_concurrent_changes`, but **not**
in `decision_state` (it changes no decision: in the state, a
`set-abstract` save would put a stale pending decision back over a
decision another process saved meanwhile; tested). An older Scholar
(checked with the pipx build, which has no `abstract_set`, on a file
whose records hold `text`) keeps the abstract and drops the list on
its next save. Not part of `is_unscreened` either, so a pending copy
with a hand abstract still folds; the fold (`reconcile_copies` and
`apply_tombstones`) always carries a copy's records, texts included,
to the survivor (`abstract_records_after_fold`), with a WARNING when
the survivor kept its own abstract. The abstract itself follows the
#206 paper merge, plus two rules in `<<settle the abstract against the
file's hand records>>` (records apart, `mine_new`/`their_new`, taken
before the union): the file holds a hand record we lack whose `text`
is the file's abstract and we added none → the file's abstract wins
over ours (a stale enrichment never erases a hand text); we added a
hand record and the file's abstract (not None) differs from the loaded
one and ours → our text stays, and our newest record gets the file's
abstract as `previous` (what `--replace` would have kept). Both races
tested in real subprocesses, both save orders (`TestHandAbstractRaces`).
`enrich` never replaces a hand abstract (`needs_enrichment`,
`merge_with` keep stored values; tested), but a **preprint adoption**
takes the preprint's own abstract (`preprint._adopt`).
`hand_abstract_replaced(d)` (last record's `text` != the paper's
abstract; a record without `text` compared by `chars`) then makes
`sessions show` add ", since replaced" and the report not count it. The
DOI-less hash id does not move (title and author only; tested). Shown
by `sessions show` ("(abstract added by hand, from <from>)",
`cli.abstract_mark`; JSON `abstract_set` when set, the records whole,
`text` included: it is the record, and hand abstracts are few), the
report (`hand_abstracts_sentence`, one English sentence counting
papers, nothing when zero) and the CSV column `abstract_from` (`from
time [by NAME]; ...`, no text, `review.abstract_from_cell`, after
`reset_from`, before `paper_id`). The audit table is unchanged.
**`scholar sessions retire-search S (--query Q [-p P] [--filters-like
T] | --record ID ... | --all-failed-outright) [--undo] [--dry-run]
[--note T] [--by N]`** (#275, cli.nw `sec:sessions-retire-search`)
marks search records retired (record and links stay). `--record`
takes the ids `sessions show` prints ("  [3fa9c1e] s2: q", escaped
for Rich; JSON `id`), each a unique prefix of at least 4 characters
(`RECORD_ID_MIN_PREFIX`; shorter exit 2, ambiguous exit 2 naming the
records, unknown exit 1, all checked before exiting); `--query` is
exact and never matches a merged record (`q | q`), a match with
different filters keys exits 2 naming them unless `--filters-like`
(substring of the flags as `show` prints them, limit included) or
`--record`; same filters on several providers are retired together;
`--provider`/`--filters-like` need `--query` (exit 2); unmatched
`--query` exits 1 unsaved; a blank `--note` exits 2;
`--all-failed-outright` (`failed_outright`) matching nothing is not
an error. Already retired (or, with `--undo`, current) records are
named and left alone. `--undo` refuses `--note`/`--by` (exit 2).
Otherwise like reset: `open_session_argument`, `--dry-run` writes
nothing, `keep_copy_before_run(session, "pre-retire-search")`, one
`_utcnow()` per run. `sessions show` heading "Queries by provider: N
current, M retired" (only when any is retired), line suffix
"(retired <date>: note)", JSON `retired` when set.
Together these let scripted/agent-driven systematic reviews produce the same
session record and `sessions export` audit trail as TUI reviews.
