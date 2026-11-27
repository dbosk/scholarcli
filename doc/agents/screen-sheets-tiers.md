# Screen sheets, the screening tier and the sample of the rest

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Screen sheets, the screening tier and the sample of the rest

Part of the documents of a double screen (screenings-agreement.md,
"Double screen in the documents"); the three items are options of
`sessions export -f screen-sheet`.

- **Screen sheet** (cli.nw `sec:screen-sheet`): `scholar sessions
  export S -f screen-sheet [--sample ID] [--undecided-by NAME] [-o
  F[.tsv]]` writes a header line `id title year venue abstract` and
  one line per paper id (copies once), tab-separated UTF-8, nothing
  else; tabs and every `str.splitlines` break → space
  (`sheet_field`). Papers (`screen_sheet_decisions`) =
  `second_screen_candidates` (`over="all"`, or the sample: decided
  only, since a second screen needs a first verdict; reset-since-draw
  left out); `--undecided-by` drops papers where `has_verdict_by` (a
  counted screening of that name, any kind, or `verdict_screener`
  name). With `--sample`, the lines of `review.sample_giveaway` (moved
  from tui.nw with `sample_holding`, review.nw `sec:sample-giveaway`;
  the TUI imports both) go to stderr. The two options with another
  format, or empty, exit 2; unknown sample exit 2 (screen's chunk).
  `--batch-size N` (#292; screen sheet only, >= 1, else exit 2; no
  default, the help gives the protocol's ~100 as a recommendation
  only: defaulted rows frequent at several hundred, rare at <= 100, in
  one run still in batches of 100) writes `BASE-001.tsv`… of at most N rows, each starting
  `# batch: <digest>-NNN`, `# session: <file name>`, `# records: n`,
  then header and rows as the single sheet (`csv.writer`, tab,
  `QUOTE_NONE`, `quotechar=None`, `\n`: quote marks as stored, bytes
  as the old tab-join, checked on 3.12-3.14; the reasons/verdicts
  reader stays own code, `csv.reader` splits at a lone `\r`); plus `BASE-manifest.tsv`
  (`batch file records first_id last_id`, written with `csv`, tab,
  `\n`, no comment line). Digest =
  first `SHEET_DIGEST_CHARS` = 8 hex of SHA-256 of [session file name,
  size, ids] (`screen_sheet_batches`): stable for one selection and
  size. Without the option the output is unchanged. `--pending`
  (#292, cli.nw `sec:first-screen-sheet`, `pending_sheet_decisions`)
  lists the pending papers instead (first screen; one per paper id,
  same columns), exit 2 before loading with `--sample`/`--undecided-by`
  or another format; its batch ids differ from a decided sheet's
  because the id lists differ.
  Prints "N paper(s) on the screen sheet." and no machine-review
  table. `all` stays csv + latex.
- **Screening tier** (#302, review.nw `sec:screening-tier`, cli.nw
  `sec:sheet-tier`): `sessions export S -f screen-sheet [--pending]
  [--top K] [--min-providers N] [--provider P ... [--query-like T]]`
  keeps the sheet's papers meeting any given condition
  (`screening_tier(decisions, session, TierRule)`): `top` = place <= K
  on a link whose current record has `order == "relevance"`
  (`relevance_place`; a date-ordered first place never selects; a
  semantic answer holds <= 50, so K >= 50 takes it whole, on purpose);
  `min_providers` = distinct DATABASES of current, non-merged linked
  records (`returning_databases`; database = `provider_database(name)`
  = `review.PROVIDER_DATABASES.get(name, name)`, a static map so that
  `sessions show` and the CSV never import `scholar.providers` (a child
  interpreter test checks show text/JSON and CSV; a test keeps the map
  equal to `ratelimit.quota_group` of the registered providers):
  openalex, its source-pinned servers and openalex-semantic are one);
  `provider` = a link to a current
  non-merged record of P whose query holds T (casefold). Records via
  `LinkedRecords` (current only; key None resolved as `search_record`).
  `TierSelection` counts: `met` (overlapping), `only`, `several`,
  `not_selected`, `place_unknown` (no ranked link to a current record),
  `no_relevance_place` (ranks only outside relevance answers),
  `databases_unknown` (links only to merged records or old links that
  fit several records); selected = sum(only) + several. Rule JSON has
  `meaning` (`TIER_CONDITION_MEANINGS`). Pending papers are one per
  paper id (`review.pending_papers`, used by the sheet, the show line
  and classify). Printed by `tier_lines` and written to
  `BASE-tier.json` (session, selection, rule, counts) with or without
  `--batch-size` (batch ids follow the tier). Without the options the
  sheet is unchanged (tested), except that a stale `BASE-tier.json` of
  the same base is removed after the staged files are in place (a
  failed export removes nothing), and only when it is a JSON object
  with every key of `cli.TIER_FILE_KEYS` (`is_tier_file`); any other
  file is left with a warning. Exit 2 before loading: another format,
  K/N < 1, `--query-like` without `--provider` or empty; after loading:
  a `--provider` no current non-merged record has. `sessions show`:
  `tier_overview_line` (`TIER_SHOW_TOP` = 100, `TIER_SHOW_PROVIDERS` =
  3 databases, pending papers; "none placed in a relevance-ordered
  answer" when no pending paper has a relevance place, e.g. S2 bulk
  `unknown` order) only when some link has a rank; JSON `ranks`
  per decision (`link_places_data`, ranked links only, key absent
  otherwise). CSV: `best_rank`, `providers_count` (databases) after `provider`
  (both in `CSV_NUMERIC_COLUMNS`).
- **Sample of the rest** (#315, cli.nw `sec:rest-sample-sheet`,
  `sec:sessions-tier-sample`; review.nw `sec:tier-sample-record`;
  llm_review.nw `sec:tier-sample`): `sessions export S -f screen-sheet
  --pending <tier options> --rest-sample N --seed S [--batch-size B]
  [--dry-run]` lists instead of the tier a draw of N of the pending
  papers the tier leaves out (`outside_tier`; one per paper id, so no
  decided and no tier paper), drawn by `llm sample`'s draw:
  `llm_review.smallest_keys(sorted ids, random.Random(seed), N)` (the
  key step of `draw_llm_sample`, now shared; `test_golden_draw` and the
  tier test's golden draw for seed 315 pin it), listed in key order;
  rest <= N -> all of it, `census` True; an empty rest is a ValueError
  (export exit 1). `draw_tier_sample` records a `review.TierSample`
  (`sample_id` `<drawn_at>/rest/seed=S/<12 uuid4 hex>`, `drawn_at` UTC,
  `seed`, `size`, `rule` = `TierRule.data()`, `rest`, `rest_digest` =
  sha256 of the sorted ids joined by newlines [:16], `papers` drawn ids
  in order, `census`) in `ReviewSession.tier_samples`: saved only when
  non-empty, old files load [], concurrent merge adds the file's draws
  by `sample_id` (real-subprocess race with a decide, both orders),
  ids repointed by `repoint_paper_ids` (folds and renames, #319; the
  version-link lookup of `drawn_decisions` stays only as a fallback).
  An older Scholar drops the
  list on save (read from its loader/serialiser, which know only their
  keys). This export SAVES the session (help says so): inside the
  staging, after `keep_copy_before_run(session, "pre-rest-sample")`,
  before the files are moved (the other order could leave a screened
  sheet whose draw is never recordable); a failure after the save says
  the draw's id is recorded and points to `sessions tier-sample`.
  A refused save (#317, `SessionNotSaved`, also from the pre-run copy)
  is re-raised for `main()`'s one line: staging discarded (no sheet, no
  tier file), nothing claims a recorded draw; the kept
  `.json.unsaved-*` file holds `tier_samples` (via `session_file_data`),
  so `sessions recover` adds the draw, sheetless (`sessions tier-sample`
  lists its papers). Tested with a real lock holder started after the
  pre-run copy.
  `--dry-run` draws in memory, prints no id, writes nothing. `BASE-tier.json`
  adds `rest_sample` (the record minus `rule`). Exit 2 before loading:
  `--rest-sample` without `--pending`, without a tier option, without
  `--seed`, N < 1, another format; `--seed`/`--dry-run` alone.
  Counting (`tier_sample_counts`, review.nw, no llm_review import so
  `sessions show` stays light): drawn ids looked up through
  `drawn_decisions` (`current_paper_id`: fold tombstones and renames,
  #319; then, only for an id no decision holds, a version-link DOI
  exactly one paper names: an adoption by a build without rename
  records); any other paper renamed before renames were recorded, or
  gone, is `not_found`. Screened = the first decided decision
  under the id (anyone). `tier_sample_verdict(d, uses_categories)`
  (one function for counts, show, table, JSON, sentence): a discard
  with a version note (`AUDIT_VERSION_NOTES`) or a record criterion
  (`AUDIT_RECORD_CRITERIA`) is EXCLUDED (counted by reason, out of the
  denominator `judged`); any other discard does not bear; in a session
  using categories (any tag in `AUDIT_CATEGORIES`) a keep bears iff its
  category is of bearing order, a keep without one is UNDETERMINED
  (rate withheld); without categories every keep bears, whoever kept
  it. NOT the audit table's cited rule (`check_bucket`), which ignored
  unreviewed keeps (review of #318: 0 of 60 vs 5 of 60). Deciders =
  `decision_source_items` over the screened drawn decisions, zero rows
  dropped at the call (JSON too; the function is unchanged), named in
  every output ("by human: 5; agent, unreviewed: 55"), never a reason
  to withhold. `sessions show`: one `tier_sample_line` per draw
  (`tier_sample_counts_text`) after the tier line, JSON `tier_samples`
  (record + screened, deciders, bearing, judged, excluded,
  undetermined, unscreened, not_found), both only with draws.
  `sessions tier-sample S [--report] [-f table|json]` (read-only): per
  draw counts and rule flags (`tier_rule_flags`), unscreened ids;
  `--report` adds rate = bearing/judged,
  `modified_wilson_interval(bearing, judged)` and `tier_sample_sentence`
  ("Of the 300 records pending on <draw date> outside the first tier
  (<`tier_rule_words`: the stored rule's own `meaning` with values put
  in>), a random sample of 60 (seed 7) was screened (by human: 5;
  agent, unreviewed: 55)[; k drawn records were excluded without a
  judgement of the work (no-abstract: k), so the rate is over the other
  n]; 3 bore on the question (5.0%; 95% modified Wilson interval 1.4%
  to 13.7%[: a sample in which none bore does not show that none of the
  rest does])."; a census: "every one was screened (...), a census
  since ..., so the count is exact"). Unlike `llm sample --report`,
  rate and interval are WITHHELD (`withheld_reason`, number agreement
  via `llm_review.counted`; the sentence then ends ". No rate is
  given: <reason>.") while any drawn paper is unscreened, not found,
  undetermined, or its decided copies give different verdicts
  (`copies_apart`, ids named; whichever copy is first), or when every
  screened one was excluded. A discard with a bearing category
  (`audit_excluded`) counts as not bearing and is stated
  (`discarded_bearing`: "k drawn record(s) was/were discarded although
  categorised as bearing"). JSON adds `drawn`, `copies_apart`,
  `discarded_bearing`. `tier_rule_words` fills values in through
  `as_written` (a function replacement: `re.sub` would read `\d`, `\1`
  as escapes) and `one_line` (line breaks/tabs -> space), also in
  `tier_rule_flags`; one provider reads "of scopus", not "of one of";
  a complete census gets its rate, no interval. LaTeX report: after the
  search parameters, a sub-heading "Records outside the screening tier"
  and one sentence per draw (`build_tier_sample_latex`, nothing
  without draws). Audit caption unchanged. `llm classify S
  --tier-sample ID` classifies the draw's still-pending papers
  (`candidates=`); exit 2 with `--second-screen`, `--top`,
  `--min-providers` or an unknown id; exit 1 when none is pending.
