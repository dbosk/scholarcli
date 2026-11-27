# The classifier and review samples

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Classifier Vocabulary

`llm classify` tells the model to use only the session's existing
themes and motivations; `parse_llm_response(allowed_tags=…)` maps tags
case-insensitively onto that vocabulary, drops the rest with a warning
(`LLMDecision.dropped_tags`), and `classify_papers_with_llm` asks once
more, with the vocabulary spelled out, about a paper that would be left
without tags (see "Retry and run tally" below). A session without tags
imposes nothing unless
`llm classify --tag` (the `vocabulary=` argument) seeds it; with
`--allow-new-tags` (`allow_new_tags=`) the prompt asks the model to
prefer the vocabulary and new tags are not dropped. The `llm`
module is looked up via `globals()` so tests can substitute a fake model.

**Retry and run tally (#306, llm_review.nw `sec:retry-one-paper`,
`sec:classifier-run-cost`; cli.nw `sec:llm-classify-run-cost`).** The
retry no longer re-sends the batch: ONE second request holds only the
papers whose first answer needs it (`_needs_retry(decision, allowed)`:
`problem` set, or all tags dropped), built by
`build_classification_prompt` for those papers (same fixed parts) +
`_retry_reminder` (at the end); papers shown in batch (session) order;
each answer replaces its paper's first answer in place (matched by
paper id); the others are untouched. No third pass: still unusable ->
withheld. The retry prompt is built before the `try`, which holds
only `RequestTally.ask` (a fault in scholar's code propagates). A retry
REQUEST that raises (any exception) or a retry with no JSON withholds
EVERY paper asked again (`_withheld_after_retry`: problem = the non-empty
parts of "<first problem or `NO_TAG_LEFT`>; retry request failed:
<reason>" / "...; retry unreadable: <parse error>"; a paper whose tags
were all dropped is withheld too, as main left it undecided when the
run ended); the usable answers are applied. Reason via
`retry_failure_reason`: `requests` exceptions through
`network.request_failure_reason`, any other by class name only (plugin
texts may hold a header with the key). A failing FIRST request still raises out of
`classify_papers_with_llm` (command ends with the exception, nothing
decided). Covers `llm classify`, `--second-screen` and `rq`
(`candidates=` too). A first version (one request
per unusable paper, papers placed after the instructions) was run
against anthropic/claude-sonnet-5-5 on 2026-11-23 (50 papers, one run
per shape): papers-last made the model drop the category on 50 of 50
(batch of 50) and on 9 and 10 of 10 (two of five batches of 10), and
per-paper retries then cost the batch + 50 requests (138,101 tokens
in). A second check (main's order, one-request retry; same 50 papers,
same model, 2026-11-23): batch of 50 one request, no retry, 34,898 in /
6,830 out; five batches of 10 no retry, 39,410 / 5,845 in all. So the
prompt order is main's (fixed parts, papers, instructions)
and `TestPromptVersionPinned` pins `classification_prompt_version` to
main's value `470bf32517e3861b` for its probe arguments: a prompt change
must update the pin on purpose. Stand-in models in tests must answer
per paper (by title: `TitleAnsweringModel` in llm_review.nw), not per
position, since a retried paper gets a new index in the retry.
**Tally**: `RequestTally.ask(model, prompt)` counts
each request when sent (a failed one too) and sums `response.usage()`
(llm 0.38 `Usage.input/.output`, `None` unless the plugin called
`set_usage`; no `usage`, a raising `usage()` or a non-count
(`token_count`) = not reported, never an error). `LLMBatchResult`
gained `requests`, `retried` (paper ids asked again),
`input_reported`/`output_reported` (requests with that count);
`prompt_tokens`/`completion_tokens` are now the run's sums (before,
they read `response.prompt_tokens`, an attribute llm 0.38's responses
do not have, so they were None). `run_cost_line(batch, withheld_as)` → "Requests:
1 batch + 1 retry of 9 papers; left pending: 1; tokens: 300 in, 30 out"
(per direction: " (reported for k of n requests)" when partial, "out
not reported" when none of that direction; "tokens: not reported by
the model" when none at all); `cli.print_run_cost` prints it last in `llm
classify` and `rq`, and in the second screen with "no screening
stored". Nothing is stored in the session; no price is computed.
Dry runs (`llm classify --dry-run`, also with `--second-screen`) print
the prompt through `cli.print_dry_run_prompt`: a Rich `Text`,
`soft_wrap=True`, no highlighter, so the output is the prompt's exact
characters (before, Rich markup ate `[abstract truncated]` and any
tag-like brackets in titles, and lines were wrapped). `llm synthesize
--dry-run` still prints through markup (not changed here).

**Unknown model (#284).** Every model lookup (`classify_papers_with_llm`,
`second_screen_with_llm`, `generate_literature_synthesis`,
`suggest_theme_groups`, rq's `generate_provider_queries`, pdf's
`rerank_passages_llm`) goes through `utils.resolve_llm_model(llm_module,
model_id)` (utils.nw `sec:resolve-llm-model`): the `llm` package's
`UnknownModelError` (a `KeyError`; caught by class, read from the module
passed in, `KeyError` for a stand-in without it) becomes `ValueError("Unknown
model: X; `llm models` lists the available models")`. `llm classify`
(both runs), `llm synthesize` (also its `-i --suggest-groups` grouping,
which before ended in a traceback, named model or default: only
`ImportError` was caught there and `_resolve_themes` runs before the
command's `try`), `rq` (before any search) and `pdf quote` with `-m`
print it as one unwrapped line and exit 1. `pdf quote` without `-m`
and an unknown *default* model (llm's `default_model.txt`) keeps the
old fallback: `rerank_passages_llm` logs the message as a WARNING and
returns None (lexical order, exit 0). Dry runs of the ordinary classify
and of the synthesis resolve no model (a dry run works offline; resolving
asks every plugin), so they do not notice a typo; `--dry-run`'s help
says so. The second screen's dry run does resolve it: it needs the
model's own id (what decisions store as `llm_model`, whatever alias
was typed) to choose the papers the model has not screened. Tests use the real
package with `get_model_aliases`/`get_async_model_aliases` patched to
`{}` (resolving a model asks every plugin; llm-gpt4all fetches its list
over the network) and a long model name, so a wrapped line would fail.
llm-ollama (a dependency since #367; its chat models call `set_usage`)
asks the server at `OLLAMA_HOST` (default `localhost:11434`) for its
models whenever a model is resolved, and registers none, silently, when
it cannot reach it. `isolate_cache` sets `OLLAMA_HOST=127.0.0.1:1` for
non-live tests, so a developer's local Ollama (loopback passes
`block_network`) never shows in a test; see cache.nw.

Tag kinds: note tags (`NOTE_TAGS`, the union of every language's
`AUDIT_STRINGS[lang]["notes"]`) are human-only, never offered (not even
on examples' tag lines) and dropped if returned (`excluded_tags=`, also
under `--allow-new-tags`). When the vocabulary holds any of
`AUDIT_CATEGORIES`, the prompt lists them in a separate "Category
(exactly one per paper)" section and the theme lists become optional
extras; `parse_llm_response(category_tags=…)` sets
`LLMDecision.category_problem` unless exactly one category remains
after mapping, that triggers the same single retry, and a paper still
invalid afterwards gets no decision (stays pending) and is listed in
`LLMBatchResult.withheld`, which `llm classify` prints at the end
("Left pending, no single category that fits the decision").
The category must also fit the decision (#224, `STATUS_CATEGORIES`):
a keep takes supports/qualifies/adjacent, a discard adjacent/off-topic;
otherwise `category_problem` is "category X does not fit a <status>
paper" (checked only once exactly one category is left), with the same
retry and withholding. The prompt's category section and the retry
reminder state the rule (`_category_status_rule`, fixed wording, so the
prompt version moves) and say to keep a paper that bears on the claim
and leave its exclusion to a human. Once the session holds any of
`AUDIT_CATEGORIES`, the classifier offers all four (and adds them to
the vocabulary answers are checked against; themes and motivations stay
the session's own), so every decision has a fitting category; the
prompt-version probe offers the four too. Only classifier verdicts are
checked: `llm classify` answers, and `sessions decide --source llm`
(exit 2 before loading, naming the fitting categories). A human's or
agent's "supports, excluded" (rendered on purpose by the audit table,
#89) is recorded as given; existing records are not rewritten.
Sessions without category tags are classified as before.
A record whose category does not fit its status (a human's "supports,
excluded", or a pre-#177 leftover) is no example, though (#255,
llm_review.nw
`sec:example-category`): `get_example_decisions` leaves out every
candidate (`example_candidates`: tagged, kept/discarded, confirmed, or
unreviewed with `--include-llm-examples`) whose `audit_category` (last
category tag) is not in `STATUS_CATEGORIES[status]`
(`category_contradicts_status`), before the sort and the cut to
`max_kept`/`max_discarded`, so the lists stay full. Left out rather
than shown without a category (the prompt demands exactly one). Not
vocabulary-dependent; no category tag, no check. The INFO log says
"Left out N examples whose category does not fit their decision";
`llm status` counts the confirmed ones with the same
`contradictory_examples(session)` (row "Confirmed, not examples
(category does not fit decision)" only when > 0, apart from "Training
examples", which counts `is_example`; JSON `examples_left_out`
always). An example shows `example_tags(tags)` (llm_review.nw
`sec:example-tags`): no note tags and only the deciding category, so a
pre-#195 record tagged `supports-claim, off-topic-false-hit` shows
`off-topic-false-hit`; records with one category or none print as
before. The prompt version does not move (it hashes a fixed probe,
not the session's examples). `sessions show` does not list such
records.

## LLM Screening Record and Review Samples

Each decision applied by `llm classify` records `llm_model`,
`llm_decided_at` (UTC ISO), `llm_prompt_version` (16 hex digits:
`classification_prompt_version`, a hash of the prompt built for a fixed
probe plus the run options and research context; not the session's
tags or examples), `llm_reason` (cut to `MAX_REASON_CHARS` = 500) and
`llm_abstract_truncated` (#168). They live on `ReviewDecision`, named
once in `review.LLM_AUDIT_FIELDS` (`llm_audit_of()`), which load, save,
the append copy, `decision_state` and the concurrent merge all use; old
files load them as `None` (unknown) and nothing fills them in later.
A human review leaves them untouched (they are the model's record).
The per-decision CSV has a column for each, in this order, after
`source_relabelled` and before `agent_reason` (#281; the later columns
moved five places, `paper_id` stays last): empty when unset,
`llm_abstract_truncated` as `true`/`false`, the reason as stored (the
`csv` module quotes commas, quote marks and line breaks).

- **No invented values.** `parse_llm_response` returns one entry per
  paper; an unusable answer (no answer, decision not kept/discarded, a
  discard without tags, confidence missing/non-numeric/outside [0, 1])
  gets `LLMDecision.answer_problem`, puts the paper in the one retry
  request (#306), and is then withheld with the category-rule ones (`LLMDecision.problem`);
  `llm classify` and `rq` list them (`print_withheld_papers`) under
  "Left pending, no usable answer".
- **Quotes in the reasons (#256).** `llm classify` (not `rq`) ends
  with one line, `Reasons quoting words not in the record (N): id:
  "quote"; ...` (first `LLM_QUOTE_MISSES_SHOWN` = 3), when an applied
  decision's stored `llm_reason` quotes >= 3 words not in its title,
  abstract or the `--full-text` passages of this run
  (`LLMBatchResult.passages`, paper id -> passage texts, not stored).
  Nothing is withheld or retried for it. Later checks (`sessions show`,
  report) see only title and abstract (see "Quote check" in decision-checks.md).
  Answers without a valid `paper_index` are skipped (never index 0).
- **Sample of a tier's rest (#315).** `llm classify S --tier-sample ID`
  classifies the pending papers of a `TierSample` (see "Screening tier"
  in screen-sheets-tiers.md); `sessions tier-sample S --report` gives
  the bearing rate with the same `modified_wilson_interval`, withheld
  while the draw is not fully screened.
- **First tier (#302, cli.nw `sec:llm-classify-tier`).** `llm classify
  S --top K --min-providers N` classifies only the pending papers of
  `screening_tier` (either condition), printing `tier_lines`; passed as
  `classify_papers_with_llm(..., candidates=)` (pending among them, in
  order; examples and vocabulary unchanged, unlike `papers=`). Exit 2
  with `--second-screen` or K/N < 1; an empty tier exits 1 with "None
  of the N pending papers is in the tier".
- **Second screen (#253 C).** `scholar llm classify S --second-screen
  (--over all|machine | --sample ID) [-n N] [--rescreen]` (exactly one
  selection, no default: exit 2 before loading; `second_screen_candidates`
  raises `ValueError` for neither or both)
  (`llm_review.second_screen_with_llm`, llm_review.nw
  `sec:second-screen`; cli.nw `sec:llm-classify-second-screen`)
  classifies *decided* papers (never pending) and stores each usable
  answer as a screening (`kind` llm, `name` = the model's reported
  `model_id`, status, tags, confidence, `reason` cut by
  `truncate_reason`, `at` = batch time, `prompt_version` (the ordinary
  one), `abstract_truncated`, `blind` True, `blind_basis` "prompt",
  `sample_id`, `via` "classify") via `record_screening` (snapshot
  first); never `apply_llm_decisions`, decisions untouched (tested on
  `decision_state`/`human_record_of` and the saved JSON); with
  enrichment on (as in an ordinary run) a missing abstract may be filled
  and saved, and every copy under the paper's id gets the filled
  `Paper`. Selection (`second_screen_candidates`): `all` every decided
  paper,
  `machine` = `is_unreviewed_machine`, `--sample` = a band's
  `sample_id` (that band) or a banded draw's group id (`sample_group`,
  all bands; each screening stores its band's id); sampled papers
  `reset_since_draw` are skipped and counted. Session order, `-n` per
  run (one batch request + at most one retry request, as classify);
  decisions with a
  counted screening of identity `("llm", model, True)`
  (`has_second_screen_by`) are skipped unless `--rescreen`; copies under
  one id are shown once and all screened. `classify_papers_with_llm(...,
  papers=)` classifies given decisions and takes examples and
  themes/motivations from `visible` (shallow session copy without every
  decision sharing a `same_work_keys` key with a screened paper: paper
  id, `version_link_dois`, `work:<audit_work_key>` when the title part
  is non-empty; no namesake guard, a hidden namesake costs an example;
  copies the keys miss are not hidden); whether categories are offered
  is read from the whole session. An unknown model becomes a
  `ValueError` (`resolve_llm_model`, see Classifier Vocabulary): one
  line, exit 1, a dry run too. Prose cites Vembye 2025 Table 5 steps
  1-5 (test with recall >= .75, specificity >= .8, which Scholar does
  not run) and 9, Page 2021 E&E Box 3 (partial checks); a `machine` or
  single-status sample selection makes agreement conditional on the
  first screen. Tested: the prompt is byte-identical when the screened
  papers' verdicts are flipped. Refused (exit 2, before loading, no
  model call): `--include-llm-examples` with it, `--sample/--over/
  --rescreen` without it, `--sample` with `--over`, bad `--over`;
  unknown sample exit 2 (screen's chunk). Nothing left → exit 1. A
  decision the same model made (unreviewed `llm`, `llm_model` = model)
  is screened, never refused, and announced ("Same model as the first
  screen for N paper(s)"; `SecondScreen.same_model`). Withheld answers
  store nothing (no snapshot) and are listed under "No screening
  stored, ..." (`print_withheld_papers(lead=)`); the quote line checks
  the screenings' reasons (`print_reason_quote_misses(reason_of=)`).
  Saved only when something was recorded, after
  `keep_copy_before_run(session, "pre-screen")`. Dry run prints the
  prompt, stores nothing (resolves the model, to skip what it
  screened). Prints "Left to screen: N".
- **Abstracts.** `MAX_ABSTRACT_CHARS` = 4000 for papers to classify
  (marked `[abstract truncated]` in the prompt), `EXAMPLE_ABSTRACT_CHARS`
  = 1000 for examples.
- **Examples** are only `human`/`llm_reviewed`/`agent_reviewed` decisions
  (`CONFIRMED_SOURCES`, compared by value); `--include-llm-examples`
  adds unreviewed `llm`/`agent` ones after them.
- **Samples (#173).** `scholar llm sample S [S...] --discarded|--kept
  [--min-confidence C] -n N --seed SEED` pools unreviewed `llm`/`agent`
  decisions, sorts them by (session, paper id), keys each with
  `random.Random(seed).random()` (the only call Python promises to keep
  stable across versions) and takes the N smallest; it stores a
  `review.LLMSample` (seed, criteria, UTC date, population size and
  digest, this session's papers with the machine's status) in every
  pooled session (`ReviewSession.llm_samples`, merged by `sample_id`,
  which ends in uuid4 digits so two draws in one second never collide).
  `test_golden_draw` pins the drawn papers for seed 42.
  The TUI filter `s` (`sampled_for_review`) queues the unreviewed ones
  (blind mode, `sessions resume --blind` or `b`, hides their verdicts until the reviewer's own is
  recorded as a screening, see Screenings);
  `sessions decide` reviews them. `--report [-f json]`
  (`sample_reports`): a sampled decision counts as reviewed when decided
  and no longer an unreviewed machine source, as changed when its
  status differs from the recorded one; the rate gets the 95% modified
  Wilson interval (`modified_wilson_interval`, Brown, Cai & DasGupta
  2001, eq. 4 with the Poisson bound of eq. 10, p. 112, for x <= x*,
  x* = 2 for n <= 50 else 3), because plain Wilson coverage dips near
  p = 0, where disagreement rates live. The sentence says the rate
  covers only the reviewed part while some is unreviewed.
  A sampled paper renamed after the draw (homonym number, surname
  first, preprint adopted at an append, by `enrich` or in the TUI) is
  found: its stored id is repointed through `ReviewSession.renamed`
  (#319, see **Renames** under Preprint Fallback); one renamed before
  renames were recorded counts as not found.
  A sampled paper with a reset record (`ReviewDecision.resets`, #248)
  whose `at` >= the sample's `drawn_at` (both UTC ISO with seconds;
  `llm_review.reset_since_draw` compares them as datetimes, as strings
  if either fails to parse) no longer holds the drawn decision: it is
  counted as `SampleReport.reset_since_draw` (JSON `reset_since_draw`,
  sentence "N sampled decisions were reset to pending after the draw
  and are not counted"), never as reviewed, changed or unreviewed, is
  part of the `counted` total for sessions not given, and is not queued
  by `sampled_for_review`. A reset before the draw counts as usual.
  `LLMSample.sessions` are labels (`session_label`: name or query);
  since #231 `session_files` (same order, `session_file_path(s).name`,
  saved only when present; old samples load with None) records each
  pooled session's file. `pooled_sample_sessions(sessions, load=)`
  (used by `--report` and the report's screening section) reads the
  other sessions from those files (`load_listed_session`; a file gone
  -> its papers not found), old samples by label via `load`, each file
  once. The population digest still hashes labels (unchanged).
- **Bounds, bands, census (#254).** `--max-confidence C` is exclusive
  (`confidence_in_bounds`: `[min, max)`, a missing confidence meets no
  bound); `--no-confidence` selects only decisions without one (exit 2
  with a bound). `--bands 0.5,0.7,0.9` (`check_band_cuts`: strictly
  increasing in (0, 1); exit 2 with any bound or `--no-confidence`)
  draws `-n` per band, bands `below 0.5`, `0.5 to below 0.7`, ...,
  `at least 0.9` (open outer ends, so disjoint and exhaustive) plus
  `without a confidence` when any lack one (`band_strata`). Each band
  has its own generator, `random.Random(int(sha256("seed/min!r/max!r/
  no_confidence")[:8]))` (`band_random`), so adding a decision to one
  band never changes another band's draw. A band with <= n members is
  taken whole (`criteria["census"]`); `--census` takes everything (no
  `-n`, which is refused, and no seed: `LLMSample.seed` None, id
  `.../census/...`). A plain draw stores exactly the old criteria
  (new keys only when used; `test_golden_draw` unchanged). Record: one
  `LLMSample` per band with `criteria["stratum"] = {group, band, bands,
  cuts}`, id `<group>/band=<i>`, its own population/digest/size, empty
  bands recorded too; chosen over one record with a band list because
  an older Scholar keeps `criteria` and paper dicts whole on save and
  reports each band correctly as its own sample (it only misses the
  upper bound in the sentence; a census it states as a random sample
  "(seed None)" with an interval). `--report`: `group_sample_reports`
  joins bands into a `StratifiedReport` (table: band, population,
  drawn, reviewed, changed, rate, interval; census band no interval,
  "census, all reviewed"/"k left"); JSON keeps old keys for plain
  samples (`census` added only for a census), stratified: `stratified`,
  `bands` (+`band`, `census`), `estimate` (null until complete).
  `stratified_estimate`: p = sum N_h x_h/n_h / N and changed among the
  not reviewed sum (N_h - n_h) x_h/n_h (Franco, Little, Louis, Slud
  2019, JSSAM 7(3), eq. 10; read in full, authors' final version), given
  only when every band of the group is present, has no decision not
  found (a lost session is no random loss), has no unreviewed decision
  and has a review left (resets are left out of n_h and named);
  otherwise `StratifiedReport.withheld_reason()` gives the sentence's
  reason (JSON `estimate_withheld`, null once given). **No interval for
  the whole**: Franco et al.'s Wilson-with-effective-size results
  exclude zero estimated variance (all bands agreeing) and their
  smallest expected proportion is 0.05 (n >= 30). Per-band intervals
  stay.
- **Report.** `build_review_provenance_latex` calls
  `llm_review.build_llm_screening_latex` (one local import + call): an
  "LLM screening" section with models, prompt versions, dates, the
  truncated (from each decision's flag, no character count) and
  unrecorded counts, and `sample_report_sentence` per sample (one for
  all bands of a stratified sample; old samples byte-identical, pinned
  by `TestScreeningSectionWithBands`; a census says "A census of all
  N ..." without seed or interval)
  (other pooled sessions are loaded read-only). Nothing when the
  session has no LLM decisions and no samples.
