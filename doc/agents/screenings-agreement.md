# Second screeners, agreement and how documents state them

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

### Screenings: a second screener's verdicts (#253, part A)

`ReviewDecision.screenings` (review.nw `sec:screenings`, declared after
`abstract_set`) holds other screeners' verdicts beside the decision,
which stays the outcome; nothing reads the list to decide kept/cited.
Each record has every key of `review.SCREENING_KEYS` (`id` uuid4 hex,
`origin` screen|decision, `kind` llm|agent|human, `name`,
`confirmed_from`, `confirmed_name`, `status` kept|discarded, `tags`,
`confidence`, `reason` whole, `at`, `recorded_at`, `prompt_version`,
`abstract_truncated`, `blind`, `blind_basis` prompt|tui|declared,
`sample_id`, `batch` (#292), `via`), built by `new_screening` (validates) or
`decision_snapshot`. `record_screening(decision, record)` first adds a
snapshot of a *decided* paper's current verdict (`origin: "decision"`,
`via: "snapshot"`) unless a counted snapshot with the same
`_snapshot_key` (status, tags, kind, name, confirmed_*, at) exists;
pending papers get none. Snapshot screener (`verdict_screener`):
unreviewed llm/agent → kind llm/agent named by `llm_model`/`agent_by`
with its confidence, reason, time; `human`/`llm_reviewed`/
`agent_reviewed` → kind `human`, `name` = `human_by`, `at` =
`human_decided_at`, `confirmed_from` llm/agent/None, `confirmed_name`
model/`agent_by` (no machine confidence or reason; since #349 the
human's own `human_reason` and `human_batch`, None when not given);
unknown source → all None. Read from `decision_trace` (#349), so an
llm snapshot also takes `llm_batch`. `counted_screenings` = valid entries (`is_valid_screening`:
dict with `id` and kept/discarded status), not marked `set_aside_at`,
recorded strictly after the last reset's `at`; malformed entries are kept verbatim, skipped, one
WARNING per file (`warn_about_malformed_screenings`).
**Not in `decision_state` nor `decision_verdict`** (on purpose, unlike
`resets`): in the state a stale `screen` save would put an old decision
back over a human's (#258's finding); in the copy comparison a
screening would keep copies decided alike apart (#257's finding).
Instead: saved only when non-empty, loaded `[]`, copied by the append,
united by `unite_screenings` in `merge_concurrent_changes` and in the
fold (`<<fold [[absorbed]] into [[survivor]]>>`), which drops a second
snapshot of a verdict already held under another id. `add_screening`
dedups by `id`; two versions of one id become `merged_screening` (the
later `relabelled_at`'s, with the earliest `set_aside_at` of either).
`is_unscreened` requires no screenings. Not in `MACHINE_AUDIT_FIELDS`.
`relabel_source` (via `correct_relabelled_snapshots`) replaces the
screener fields of every counted snapshot of the old verdict with the
new `verdict_screener`, stamps `relabelled_at`, keeps the replaced
values under `before_relabel` (the first relabel's), and records the
old kind as `screenings_kind` in the relabel record (only when one was
corrected). `reset_decision` keeps the list and records
`"screenings": n` (the counted ones it saw) in the reset record when
n > 0. **Races** (`ConcurrentHistory.of(ours, theirs)` before the
union, `settle_concurrent_screenings` after the decision is merged, in
`merge_concurrent_changes`; the loop no longer `continue`s past it):
screenings one side added while the other side added a reset get
`set_aside_at` = that reset's `at`; snapshots one side added while the
other relabelled are corrected from `relabelled_verdict_keys` (undoes
the relabels: `from` source plus the record's `human`). The reset
record's count is not changed afterwards. Tested with real
subprocesses in both save orders (`TestScreeningRaces`). `screenings_summary`
gives `sessions show`'s line ("Screenings: N on P paper(s), S of them
snapshots of the decision; K set aside by a reset; M malformed,
skipped."); `show -f json` adds `screenings` per decision when
non-empty. Checked: the pre-change pipx build (1.29) loads such a file
and drops the list on save. Size in indented JSON: ~670 bytes per
screening, ~690 per snapshot, plus reasons.
**`scholar sessions screen S --as agent|human|llm --by NAME
(--verdicts-file F | (--doi D|--paper-id ID)... --keep|--discard
[--tag T]... [--reason TEXT]) [-c C] [--blind|--not-blind] [--sample
ID] [--all-copies] [--dry-run] [--strict-quotes] [--strict]`** (cli.nw
`sec:sessions-screen`): `--as` defaults to human at a terminal, else
exit 2; `--by` required for every kind (exit 2 before loading; the
model for llm); a screener whose `(kind, name)` is that of a selected
decided paper's `verdict_screener` is refused (exit 2, unsaved, papers
named: a change of mind is a `decide`; self-agreement is not computed
and a second record under one identity would hide the first); `-c`
refused with `--as human` (also file confidences). Verdicts file lines
`ID<TAB>kept|discarded<TAB>TAGS<TAB>REASON[<TAB>CONFIDENCE]` (TAGS
comma-separated, may be empty for a keep): parsed by `parse_tab_file`
with `VERDICTS_LAYOUT`; `parse_reasons_file` is the same function with
`REASONS_LAYOUT` (`TabFileLayout`/`TabFileColumn`: a column spec, same
line rules, `read_reason_column` applies #256's placeholder and
column-shift refusals). A discard needs a tag; at most one category.
Session uses categories (any decision tag in `AUDIT_CATEGORIES`) →
agent/llm verdicts need exactly one category fitting
`STATUS_CATEGORIES` (exit 2, lines named); human verdicts free.
Unknown ids exit 1, two different verdicts for one paper exit 2,
copies decided apart need `--all-copies`, `--sample` must be a
`sample_id` or a banded sample's `criteria["stratum"]["group"]` (exit 2
listing the held ids; membership of papers is not checked here). The
quote check is decide's chunk (`<<check the quotes of the agent's
reasons>>`, `--strict-quotes`); its "Saved all the same" line prints
only when `saving` (set before the chunk: decide True, screen
`not dry_run`). One `utc_now_iso()` per run =
`recorded_at` = `at`; `keep_copy_before_run(session, "pre-screen")`;
`--dry-run` writes nothing. `--blind`/`--not-blind` → `blind`
True/False, `blind_basis: "declared"`; neither → None. The decision is
never changed (tested on the saved JSON). **Screener identity**
(#253 C): `review.screener_identity(record)` = `(kind, name, via ==
"classify")`; comparisons (agreement, conflicts) pair by it, not by
`(kind, name)`: a classifier second screen keeps `name` = the model id
(so "same model" = both kind llm with equal names) but must not share
the identity of the snapshot of a decision the same model made, else
the latest-record rule hides the first verdict. Only `llm classify
--second-screen` writes `via: "classify"`; snapshots are `"snapshot"`,
`sessions screen` `"screen"`. Report surfaces and the screen sheet:
see "Double screen in the documents" below.
**TUI blind review (#253 part D, closes #254's last point; tui.nw
`sec:tui-blind-review`).** `scholar sessions resume S --blind [--by
NAME]` (`PaperReviewApp(..., blind=True)`) starts blind mode in
`on_mount` (`_start_blind_at_mount`) before the list is drawn:
`blind_unbroken` True; needs review mode and `session.llm_samples`
(else notice, off) and `app.reviewer` (`--by`, else
`ReviewerNameModal`; empty/Escape → off; empty `--by` exits 2 before
loading). Key `b` toggles during a run, only from the paper list
(`len(screen_stack) > 1` → refused); switching on mid-run (or off and
on) sets `blind_unbroken` False for the run: screenings then get
`blind: False, blind_basis: None` (still `via: "tui"`), status bar
"Blind (verdicts were shown earlier in this run): NAME" instead of
"Blind: NAME". On selects the `llm_sample` filter. `blind_state(d,
queue)`: None unless blind and `id(d)` in `blind_queue()` (= what
`sampled_for_review` lists: every sample, band, census; not reset since
draw); "own" if `made_by_reviewer` (`verdict_screener` kind human,
name = reviewer; unreachable via the queue today, which holds only
unreviewed machine decisions); "revealed" if `reviewer_screening` (a
counted `origin: screen` human screening of that name, also one from
`sessions screen`); else "hidden". Hidden: row shows `BLIND_MARK`
("B"), no status/machine mark/confidence; detail screen omits tags +
Themes/Motivations heading; `f` refused in blind mode
(`<<refuse the decision filters in blind mode>>`: every status/source/
example filter selects by decision; PR B's conflict filter `x` is in the
same dialog, so refused too, tested), `F` (year, venue, citations, OA,
pub type: `SearchFilters.matches` on the paper only) allowed; status
bar counts via `status_counts()` leave hidden papers out and add
"Hidden: N"; every tag dialog (normal and blind, both screens) takes
`tag_choices(keep)`: outside blind mode the session's
`all_themes/theme_counts` or `all_motivations/motivation_counts` as
before, in blind mode only non-hidden papers' tags of that status;
the blind dialog preselects nothing. `blind_verdict(d, status,
ask_tags, done)` runs first in K/T/d of both screens: hidden →
`record_blind_verdict` (`new_screening(kind="human", name=reviewer,
blind=blind_unbroken, blind_basis="tui" if blind_unbroken else None,
via="tui", sample_id=sample_holding(session, d))` via
`record_screening`, decision untouched, notification with
`revealed_verdict(d)`), the detail screen stays and shows a "Blind
review" block (both verdicts, the machine's reason); "own" → warning,
nothing recorded. `blind_refuses_confirm`: C on a hidden paper refused, and so is the
reason key `r` (#349 part B: it would show the machine's reason). A
revealed paper's K/T/d/C go through `decide_as_human` /
`confirm_as_human` like any (category rule, changed category; the
reason prompt opens after a change); a blind verdict
(`record_blind_verdict`) is a screening, not a decision, and is not
held to the category rule.
After the reveal K/T/d/C are the normal paths (`mark_as_reviewed` +
`record_human_decision(..., by=reviewer)`): the adjudication. Leaving
between keeps the screening; the decision stays unreviewed and listed,
revealed. The start notice (`BLIND_MODE_NOTICE`) adds, after a
newline, `sample_giveaway(session, queued)` (review.nw, also used by the screen sheet): one line per queued sample
that tells something, "Sample <sample_id> (N listed paper(s)) holds
<describe_sample_criteria of statuses+sources> only: their status is
known." for a single-status sample, plus (or alone, "... was drawn by
confidence ...") "It was drawn by confidence: the range of confidence
of each of its papers is known." for a banded (`stratum`) or bounded
draw; mixed samples get no line. The id is the one `llm sample` prints
("Sample <id>"); the list does not show which sample drew a row.
Saved by `sessions resume`'s `save_session`; PR A's merge sets aside a
screening made while another process reset the paper
(`TestBlindReview`, real subprocess, through `sessions resume
--blind`). Not hidden: the session file, other commands, what the
sample's criteria tell, and that queued papers are unreviewed machine
decisions (prose, `sessions resume` help, notice).

### Agreement and conflicts (#253, part B)

`agreement.nw` (new module, chapter after llm_review; reads, never
writes). **Screener** = `review.screener_identity(record)` =
`(kind, name, via == "classify")` (defined in `sec:screenings`,
shared with PR C #277 so a model's second screen is apart from the
snapshot of its own decision; `screener_of` returns None for a kind
not in `SCREENING_KINDS`, counted by `unknown_origin_count`, never
paired); unnamed = `(kind, None, ...)`, one screener per kind,
labelled "unnamed agent"; second screen labelled "llm (m), second
screen". `--pair` form `kind[+second]:name` or bare `kind[+second]`
(`screener_spec`/`parse_screener_spec`, first colon splits;
`parse_screener_pair` splits `A,B` at the one comma followed by a kind
[+second] and `:` or the end, so names may hold commas; none or
several such commas, or one screener twice → ValueError, exit 2).
`pair_header` prints `Pair --pair <shlex-quoted A,B>`, copyable. `same_model(a, b)` (kind llm, one
name): header line "same model: m" plus both sides' prompt versions
("none recorded"), show line "(same model)". `screener_verdicts(decision)`: latest counted
record per screener by `at` else `recorded_at` (ties: later in list);
the live decision is never a verdict, its snapshot is.
`ScreenerProfile.label`: a screener all of whose records are snapshots
with `confirmed_from` is "the human-confirmed decision (by NAME;
proposed by llm MODEL)" (parts only when known/unique); partly →
"human (X) (k of n records the human-confirmed decision)"; profiles
also list prompt versions. **`AgreementTable`** (frozen; `cells[i][j]`
= A's label i, B's label j, positive first; everything computed from
cells): `n`, `agreeing`, `observed`, `positive_agreement` =
2x11/(2x11+x12+x21), `negative_agreement`, `prevalence_index` =
(x11-x22)/N, `bias_index` = (x12-x21)/N (signed), `chance_agreement`,
`kappa` None with `kappa_undefined_reason` when either screener used
one verdict ("one screener gave only one verdict" / "both ...", never
0), "no records screened by both", "not computed for more than two
categories". Sources in the prose: ShankarBangdiwala2014 (Po, kappa,
PI/BI, scenarios 1-3 as test vectors; Byrt and Cicchetti-Feinstein
cited through it), Tan2024 (Ppos/Pneg; lepidic/acinar vectors),
VachGerke2023, Wongpakaran2013 (zero marginal; Table 7 scales differ),
Vembye2025 p. 9, Reichenheim2004 (why no kappa interval). Not
computed: AC1, PABAK, B, kappa interval, multi-category kappa, verbal
labels. **Questions** (`QUESTIONS`, `verdict_value`): `status`,
`bearing` (category `<= AUDIT_ORDER_BEARING` of `audit_category(tags)`),
`category` (4x4, observed only); a verdict without category →
`without_category`. `screening_agreement(records, a, b, question)`
takes `screener_verdicts` maps (computed once); a record = a decision
(copies counted each). `screener_pairs` (fixed order by
`SCREENING_KINDS` then name). **Samples**: `sample_bands(sessions, id)`
(id or stratified group id; one `SampleBand` per stored band, papers
by id as `sample_reports`: `reset_since_draw` left out and counted,
missing papers and sessions not given → `not_found`); `band_agreement`
adds `modified_wilson_interval(agreeing, n)` unless
`interval_withheld`: census, or any counted sampled paper lacks a
verdict/category of either screener (reset/not found do not withhold).
No interval over all records. **Conflicts**: `conflicts(decision,
verdicts=None)` per screener pair: `status` if statuses differ, else
`category` if both categories present and different. `conflict_resolved`:
decided, source not `is_unreviewed`, `human_decided_at` not older
than the latest counted screening's `recorded_at`.
`conflict_outcome` → `a`/`b`/`neither` (status: decision status;
category: `audit_category(decision.tags)`). **Text**:
`agreement_block` (table, measures, then two sentences, always: "X of
N records were discarded by both, so observed agreement is at least
X/N (P %) whatever the screeners did with the rest; positive agreement
counts only records at least one screener kept." and "For the same
observed agreement, kappa is lower the more one verdict dominates. No
verbal label is given for kappa."; bearing worded "judged (not)
bearing"), `agreement_data`
(JSON, `interval` only for samples, category without kappa keys),
`pair_header`, `ScreeningOverview.of(decisions)` (None without any
decision with screenings; `lines()`, `data()`, `conflict_counts()`).
`conflict_counts(entries)`/`conflict_counts_line`: one definition for
show and `sessions conflicts` (a paper with any status conflict counts
as status, else "category only").
**CLI** (cli.nw `sec:sessions-agreement`, `sec:sessions-conflicts`):
`scholar sessions agreement S [S...] [--sample ID] [--pair A,B] [-f
table|json]` (sessions deduped by file; `--sample` reads
`pooled_sample_sessions`; one block per band; bad `--pair` or unknown
sample exit 2, missing session exit 1); `scholar sessions conflicts S
[--pair A,B] [--status-only|--category-only] [--unresolved] [-f
table|json]` (both kind flags exit 2; outcome counts per pair and kind
over resolved conflicts; one print). `sessions show` adds the
overview's lines after the "Screenings:" line (one per pair: records,
kept/discarded agreement, kappa with "(prevalence index …, bias index
…)" or undefined with its reason, status conflicts (resolved); then
"Screening conflicts: N status (R resolved by a human), C category
only"; unknown-origin count) in one print, and JSON
`double_screening` (`pairs`, `conflicts`, `unknown_origin`); neither
without screenings (`TestSessionsConflicts.test_show_unchanged_without_screenings`).
TUI filter `x` (`conflicts`): decisions with an unresolved conflict;
a TUI confirm resolves (tested with a pilot). A blind TUI screening
that differs from the machine's is a status conflict, unresolved until
the step-two confirm (`test_a_blind_verdict_is_a_conflict_until_confirmed`).

### Double screen in the documents (#253, part E)

agreement.nw `sec:agreement-reports`; every number comes from
`ScreeningOverview` / `screening_agreement` (no second computation),
and every surface starts from `ScreeningOverview.of`, None without
screenings, so documents of sessions without screenings are byte for
byte as before (`TestDocumentsWithoutScreenings`: sha256 of report,
CSV, synthesis summary md+latex, audit table en+sv of
`_surface_session(False)`, pinned from b05c49e). Shared pieces:
`kappa_clause(table, minus="-")` (kappa always with PI/BI, else "kappa
undefined (reason)"; the report passes `MINUS` = U+2212),
`_records(n)` ("1 record", also in PR B's block, header, bound
sentence and show line), `ScreeningOverview.pair_summary(a, b)` →
(names, numbers) (the `show` line is `Double screening: names:
numbers`), `resolved_outcomes`, `sorted_outcomes`, `outcome_line`
(moved from `sessions conflicts`, which calls them; same text),
`blind_basis(record)` → `prompt`/`tui`/`declared` (blind True with that
ground), `unstated` (blind True, unknown ground), `not blind`,
`unknown` (None); `ScreenerProfile` counts `snapshots` and `bases`
(latest verdict per record). **Screened twice** =
`screened_twice(decision)`: counted verdicts of >= 2
`screener_identity`s (unknown-kind snapshots count as one); a pending
paper's lone screening (no snapshot) or a snapshot left alone by a
reset is not. `ScreeningOverview.screened_again`,
`screened_without_decision` (pending papers with a counted
screening), `second_screen_groups()` → {(kind, ground): (decisions,
screeners)} over records screened twice, `screen_sample` (the one
`sample_id` of every second-screen verdict, else None).
- **Report** (`double_screening_sentences(decisions)`, English, called
  by `llm_review.build_llm_screening_latex`, escaped by `latex_text`:
  `escape_latex` between `MINUS` signs, each `$-$`): after the LLM
  sentence and the samples, `\paragraph{Double screening}`; with no
  LLM step and no sample `<heading_command>{Double screening}` instead.
  Sentences: "k of the N decisions were/was screened a second time."
  (decisions, as the summary counts papers); "p pending paper(s)
  has/have a screening but no decision to compare it with."; with
  `screen_sample` "Every second-screen verdict was made for review
  sample S; scholar sessions agreement --sample S gives the agreement
  over that sample."; per screener (`screener_sentence`,
  `REPORT_BLINDNESS`): "label: n records, all <phrase>." or "(c1
  phrase1; c2 phrase2)" (snapshots: "copied from the decision when a
  screening was recorded"); per pair (`pair_sentences`)
  "Kept/discarded, A = …, B = …[ (same model)]: n records screened by
  both; both kept x11, A kept and B discarded x12, A discarded and B
  kept x21, both discarded x22; observed agreement, positive/negative
  agreement, Cohen's kappa (PI, BI)." plus PR B's bound sentence; PR B's
  kappa sentence once after all pairs; conflict counts ("… resolved by
  a human who decided after the latest screening; … had conflicts on
  the category only."; one record: ", and it was resolved by a human
  …" / ", and it is unresolved"; none: no resolution clause) and one
  `outcome_line` per pair and kind;
  unknown-origin count. No interval.
- **`llm synthesize`** summary (`summary_rows`): after the "Decided"
  rows, md `- Double screening (names): numbers`, LaTeX
  `\item[{Double screening: names}] numbers` (braced: names are user
  text); the LaTeX row writes negatives as `$-$` (`summary_rows(...,
  minus=MINUS)` + `latex_text`), the Markdown row keeps the hyphen.
- **Audit caption** (`audit_screening_sentence(decisions, strings,
  rows)`, in `build_audit_table_latex`'s `databases` join after
  `cited_rule`, i.e. after the reason/confidence sentence and the cited
  rule, before "Databases searched"). Counts unique hits by the rows'
  `work` (`audit_work_key`; a work is screened twice when any copy is;
  total = rows); without `rows` it counts records. en: "k of N hits
  were/was screened a second time (c by <a language model / an agent /
  a human / n agents>, <ground>; …)." (grounds: "blind by
  construction of the prompt", "blind in Scholar's review screens",
  "blind by the {agent's|model's|screener's; plural agents'|models'|
  screeners'} own declaration", "marked blind", "not blind",
  "blindness not recorded"; the report's declared phrase is "blind by
  the agent's own declaration, which Scholar cannot check"); per pair "Agreement on
  kept/discarded between <model m-1> and <agent a-2>[ (same model)]
  (a same-model second screen: "model m-1 (second screen, same
  model)", sv "(andra granskning, samma modell)"),
  over n records screened by both: P\,\% (Cohen's kappa K, prevalence
  index PI, bias index BI)." (or "undefined: reason"); "Status
  conflicts: s, of which r resolved by a human; category-only
  conflicts: c."; numbers via `audit_number`, negatives `$-$`; a
  screener all human-confirmed snapshots → "the human-confirmed
  decisions", partly → "human Hum (k of n records human-confirmed
  decisions)". sv: "k av N träffar granskades en andra gång (c
  granskade/granskad av en agent, blint enligt agentens egen uppgift;
  …)." (grounds: "blint genom promptens utformning", "blint i Scholars
  granskningsvyer", "blint enligt {owner} egen uppgift", "markerat som
  blint", "inte blint", "utan uppgift om blindning"); "(samma
  modell)"; "Statuskonflikter: s, varav r löst/lösta av en människa;
  …". Pending papers with a lone screening are left out of the caption.
  Strings in `AUDIT_STRINGS` (review.nw `sec:audit-double-screen`).
  Rows, order and reasons unchanged (tested with/without screenings).
  `TestDoubleScreeningCompiles` (marker `latex`) compiles report
  fragment + sv table in the pdfLaTeX T1 host with a name full of
  specials.
