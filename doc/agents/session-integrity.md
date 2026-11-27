# Session arguments and session integrity

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Session Arguments

Every command that takes a saved session (`sessions show/export/decide/
relabel/reset/set-abstract/screen/resume/reconcile/check`, `llm classify/status/context/
synthesize/sample`, `enrich`, `verify`) opens it with
`cli.open_session_argument` → `review.load_session_argument` →
`resolve_session_argument` (#237, review.nw `sec:session-arguments`):
an argument ending in `.json` names that file in the sessions dir; a
`.json` path is accepted only into the sessions dir, any other
directory → `SessionArgumentError` "give a file name in <dir>" (taking
the base name had opened the live file of that name instead). Any
argument is also tried as `<arg>.json` and as its query's hash file.
More than one existing file → `AmbiguousSessionError` (a
`SessionArgumentError`; message names each file and what it holds,
`describe_session_file`). Both → exit 2, nothing read or written. One
file → read with `read_session_file` (the same file as the old
`load_session` lookup); none → None, also for a query too long to be a
file name. Tests of the commands stub `review.load_session_argument`.
`sessions reconcile` re-reads the resolved file under the lock. `llm
sample` and `sessions check` load a session named twice (`x x.json`)
once (by `session_file_path`). The `sessions list` table shows `name
(argument)` when they differ (`session_list_name`).
`session_argument(session)` /
`session_argument_for(label, path)` give what to type: the label, or
the file name when the label opens another file or fits two; used by
`list_sessions` (`argument` key), shell completion, `llm sample`'s drawn
list and `--report`'s "not yet reviewed" list (`SampleReport.unreviewed`
holds arguments). Never call `load_session` on a user-typed argument.

## Session Integrity

Commands that load a session and save it much later (`scholar enrich`,
`verify`, the TUI) used to overwrite whatever was saved in between. That
is how two classified sessions lost every decision and their research
context (#107). `review.save_session` now:

- **merges**: it re-reads the file and does a three-way merge against
  `session._baseline` (`SessionBaseline`, recorded by `read_session_file`
  and after each save). Decision fields and `research_context` this
  process did not change take the on-disk value. Papers, search records
  and snowball rounds that only the file has are added. Paper metadata
  of a paper both hold is merged three ways too (#206,
  `paper_merged_from(ours, theirs, base_state)`): the baseline keeps
  each paper's stored fields (`SessionBaseline.papers`: id →
  `paper_state(paper)`, the `Paper.to_dict()` fields frozen into
  immutable copies, lists → tuples, dicts → sorted item tuples, so
  in-place changes are seen; `None` ≠ `()`). A field ours still has
  as in the baseline takes the file's value if that differs and is
  not `None` (a retraction `verify` saved; a `None` on disk is a gap
  from an older writer or a hand edit); a field we changed keeps
  ours (also when both changed); then gaps are filled (#194,
  `paper_filled_from` = `ours.merge_with(theirs)`).
  `PAPER_FIELD_GROUPS` (`oa_status`+`oa_url`, one Unpaywall answer)
  are decided whole first: ours as loaded and the file's pair
  different with a non-None status → the file's pair (its `None`
  link too); else ours holds a status or changed → our pair whole,
  restored after the fill; else fill. `pdf_url` and the Crossref
  pair stay per field (Crossref never writes `None` there).
  Crossref notices (`CROSSREF_NOTICE_FIELDS`: `updated_by`,
  `newer_versions`) are united (#219, `united_crossref_notices`:
  ours first, each notice whole, keyed by normalised DOI + `type` /
  `relation`, DOI-less notices by equality; None+None → None,
  []+None → []) when the paper has no paper state or both copies
  changed them since the baseline (a retraction lost is worse than a
  withdrawn notice kept, which `verify` replaces); only one side
  changed → the three-way rule (ours as loaded → file's list; ours
  changed, file as loaded → ours).
  `ACCUMULATED_PAPER_FIELDS` are never judged three ways: sources,
  keywords, tags united and `citation_count` max (by `merge_with`),
  `preprint_versions`/`published_versions` united by
  `united_version_links` (ours first, links whole, matched by
  normalised DOI, DOI-less links by equality; also without a
  baseline). Paper states are recorded only from the file
  (`SessionBaseline.of(..., from_file=True)`: `read_session_file`
  and after each save); a baseline `create_review_session` builds
  (#209: other-file appends, new sessions, the ids a same-file append
  adds) has decision states only, since a built paper is no ancestor
  of the target's copy. No paper state (session never loaded or
  built, paper new here) → nothing taken, gaps filled, ours wins
  (Crossref notices united, above).
  `read_session_file` takes the baseline from the file's copy
  (`as_stored`), not from the registry's held object, else the
  file's older values would overwrite ours; the save's re-read passes
  `record_baseline=False` (it never needs one). Cost on an
  11,162-paper session copy: ~5 MB, load ~+10%. Nothing is taken or
  filled from a namesake (`plausibly_same_work`; DOI-less hash ids
  collide). The decision keeps its very `Paper` object when nothing
  changed. The file is read with
  `read_session_file(path, use_registry=False)`, else the registry
  would hand back our own objects and hide the file's copies; a paper
  new on disk is registered (`register`), and if this process
  already holds a copy of the same work, that copy wins, gaps filled
  from the file (a held namesake: the file's paper stays).
- **guards**: `warn_if_decisions_dropped` logs a WARNING (session,
  before/after decided counts, `.bak` path) when the save still leaves
  fewer decided papers than the file has, beyond this process's own
  resets to pending. It never refuses the save.
- **locks**: the re-read, merge and replace run under
  `utils.file_lock` (`filelock`: `flock` on POSIX, `LockFileEx` on
  Windows) on a hidden sidecar `.<name>.json.lock`, so two processes
  saving at once take turns. Held for the merge and write only, never
  from load to save. A session save NEVER writes unlocked (#316,
  review.nw `sec:session-lock`): `session_lock(path, hint)` =
  `file_lock(..., required=True, timeout=SESSION_LOCK_TIMEOUT (300 s),
  notice_after=SESSION_LOCK_NOTICE (= LOCK_TIMEOUT, 10 s),
  notice_every=SESSION_LOCK_REPEAT (60 s), notice_hint=...)`: WARNING
  lines naming the file, time waited and left, and that Ctrl-C stops
  the wait. `utils.LockNotTaken(path, reason, held=, lock_file=)`:
  `held` True = another holder (timeout), False = the lock file cannot
  be opened/created (`OSError`, "cannot open the lock file X: ...").
  `save_session` takes the lock apart from the merge (`ExitStack`); on
  `LockNotTaken` or `KeyboardInterrupt` during the wait,
  `refused_save` keeps the session as `<name>.json.unsaved-<UTC
  time>-<random>` (`keep_unsaved_session`, mkstemp) unless the
  directory is not writable (`os.access`; then no attempt, said in the
  line), and raises `SessionNotSaved(path, unsaved, reason, cause=
  held|lock-file|interrupted, keep_error=)`; `cli.main()` prints it as
  one unwrapped line, no traceback, exit 1 (130 when interrupted).
  Kept file = `session_file_data(session)` + `UNSAVED_KEY`
  `"scholar_unsaved"`: `{"target": "<name>.json", "baseline":
  baseline_data(...) | null, "baseline_keys": [...]}`. The baseline is
  plain JSON (NO pickle: a pickled baseline ran code on recover, review
  of #317): `SessionBaseline` fields by name, values through a tagged
  codec (`baseline_value_data`/`baseline_value`: one-key objects
  `tuple`, `list`, `frozenset`, `dict` as pairs, `enum` [name, value]
  from `BASELINE_ENUMS` = DecisionStatus, ReviewSource; leaves str,
  int, float, bool, null); `baseline_from_data` checks tags, field
  names and types, else `ValueError` -> `SessionFileError`.
  `scholar sessions recover FILE` (`recover_unsaved_session`) accepts
  only a `target` that is a plain non-hidden `<name>.json` the kept
  file's own name begins with, written in the sessions directory;
  restores baseline and keys, saves through `save_session` (same
  merge, under the lock) and deletes FILE; refused again: FILE stays,
  the new copy is removed. `--discard` deletes a kept file
  (`discard_unsaved_session`: name has `.json.unsaved-` and
  `read_kept_file` accepts it; else exit 2); every refused save leaves
  one full copy, never removed automatically. Crafted kept files
  (deep nesting -> `RecursionError`, non-string `baseline_keys`) are
  one-line refusals. The keep serialises first and creates the file
  only to write it (an interrupted keep leaves no file), and holds
  back SIGINT while keeping (`InterruptHeldBack`, main thread only;
  the command then exits 130); an interrupt that still stops it gives
  "... could not be kept ..., so its changes are lost". SIGTERM is no
  interrupt: `decide`/TUI end at once without a kept file (143), only
  `enrich` turns it into one. `reconcile_session` and
  `keep_copy_before_run` take `session_lock` too (hint
  `NOTHING_CHANGED_HINT`; refused: `lock_refusal`, `SessionNotSaved`
  with no kept file, "run the command again"). `scholar enrich` stops
  at a refused chunk save ("Stopped: saved K of N ...", exit 1 or 130;
  earlier chunks saved, the chunk in the kept file); the TUI's exit
  save raises through `run_review`/`sessions resume` to `main`; a
  refused `search -n` / `llm synthesize` prints nothing of its work
  (both save first; results in the kept file and the caches).
  `sessions list` warns about kept files (`unsaved_session_files`).
  Notes never write unlocked either (#319, notes.nw
  `sec:notes-lock`): `_holding_notes_lock` = `file_lock(required=True,
  timeout=NOTES_LOCK_TIMEOUT (30 s), notice_after=NOTES_LOCK_NOTICE
  (= LOCK_TIMEOUT, 10 s))`, one notice; refused -> `NotesNotLocked` (a
  `NotesFileError`; `held` as `LockNotTaken`; one line "Notes file X
  is locked by another scholar process (...)" / "cannot be locked
  (...; check its permissions), so no note or decision record was
  written."), nothing written. Locked writers: `save_note`,
  `delete_note`, `delete_all_notes` (`notes clear`), `import_notes`,
  `save_search_decisions`, `get_previous_decision`,
  `clear_all_decisions`, the move inside `get_note`
  (`_move_legacy_note`) and `migrate_paper_id` (`_move_records`).
  Readers take no lock (atomic replace); `get_note` reads unlocked and
  moves a legacy note only if the lock is free at once
  (`_if_notes_lock_free`, timeout 0, no notice, nothing logged), else
  returns it unmoved: the TUI's detail screen never waits. `main()` prints `NotesNotLocked` as its one line without
  the `.bak` repair advice (exit 1); the TUI's
  `notes_unavailable_message` likewise, the typed note kept in
  `unsaved-note-*.md` (`edit_note_in_editor` catches any
  `NotesFileError`). `migrate_paper_id` first looks without the lock
  (`_records_under`; an unreadable store counts as holding records) and
  returns True at once when the old id has nothing to move; otherwise
  it catches `NotesNotLocked`, moves nothing and returns False. Within
  a `moving_records()` batch (a `ContextVar`; nested uses join the
  outer; the append's conversion, the whole `enrich` run,
  `move_stranded_notes`) the first refusal is remembered, later moves
  are left without a wait, and ONE warning at the batch's end names
  every `old -> new` pair and `scholar sessions reconcile`; outside a
  batch the warning comes at once (TUI: plus a notification,
  `notes_left_message`, naming the reconcile command). Measured with
  the real 30 s timeout and a lock holder: an append with three
  noted homonym renames took one wait (was 90 s), none noted no wait.
  `move_stranded_notes` reads `renamed` as well as `folded`. Caches deliberately keep writing unlocked after
  `CACHE_LOCK_TIMEOUT` (60 s): atomic and merged, entries refetchable,
  and a refusal at exit would lose this process's entries for certain
  (cache.nw prose). Same machine only: no help across machines on a
  shared directory.
- **cost** (#316, review.nw `sec:save-cost`/`sec:pairing-cost`): a
  save is linear in the decisions. `pair_with_file` groups the
  baseline's keys by paper id once (`base_keys_by_id`; it used to scan
  every baseline key per paper id: 94 s at 30,000 decisions with five
  links each), and `save_session` runs under
  `paused_garbage_collection()` (gc off, then restored as it was).
  Measured after a load, invented session, 5 links per decision, under
  other jobs' load: 5,000 / 10,000 / 30,000 decisions 1.2 / 2.9 /
  8.1 s (before 4.1 / 15.5 / 172 s). The gc pause at 30,000: 12.3 s
  without it vs 7.7-8.4 s with it (ours); 13.3/18.8 vs 8.5/12.6 s
  (reviewer's), 2.6 vs 1.7-2.1 s at 5,000. Tests keep the old pairing
  as `reference_pair_with_file` (test_review.py; do not change it) and
  compare on the #228 scenarios and 400 seeded random cases.
- **writes atomically**: `utils.atomic_write_text` (temp file in the
  same directory, fsync, `os.replace`), keeping the previous file as
  `<name>.json.bak` (one generation).
- **saves to the file it loaded** (#181): `read_session_file` sets
  `ReviewSession._loaded_from` (not persisted; `create_review_session`
  carries it over only when `appends_to_loaded_file`: both identities
  (name, else query hash) map to one file name; `search foo --review`
  must not write into named session foo's file) and
  `session_file_path` returns it, so lock, merge
  re-read, `.bak`, write and `keep_copy_before_run` use the loaded
  file, not the one the stored `name` maps to (`own_session_file_name`;
  new sessions still use that). A file whose stored name maps elsewhere
  (a hand copy) logs one WARNING per file and process
  (`warn_about_foreign_name`) and is flagged by `sessions list`
  (`name_mismatch` in the JSON, a stderr line); neither is renamed.
  A stored name is no key (named `foo` of query `bar` and the unnamed
  session of query `foo` both list as "foo"), so code that lists
  sessions reads each by its path, `load_listed_session(meta)` (#221:
  `list_all_themes`, `list_papers_for_theme`,
  `complete_session_paper_id`), never `load_session(meta["name"])`;
  pooled LLM sample sessions likewise by recorded file (#231).
  The loaded `_baseline` goes with `_loaded_from` (#207): an append
  that saves into another file takes `SessionBaseline.of(session)` at
  the end of `create_review_session` instead (no baseline would let
  the loaded file's decisions and context replace the target's; the
  loaded one reset the target's decisions of papers it lacked and
  dropped those under ids the append renamed). Same-file appends keep
  the loaded baseline (a renamed id must not come back from the file)
  and add the built state only for ids it lacks (#214: a paper new in
  this run, untouched, yields to another process's decision);
  `record_keys` and the context stay as loaded. A session that loaded
  nothing (brand new, or rebuilt from the decision store) takes the
  built state too (#214: two processes creating one session at once);
  only sessions constructed in code have no baseline. Whenever the
  session does not continue a loaded file, the built baseline's
  `record_keys` are empty: nothing was loaded from the target, so the
  legacy-record rule must not drop one of our legacy records.
- **an append loads only its own file** (#213):
  `create_review_session` loads `load_own_session(name, query)`, the
  file `own_session_file_name` gives (`<name>.json`, unnamed: the
  query's hash), never `load_session`'s other guess (an unnamed append
  for foo used to load named session foo's `foo.json`, whatever its
  query; `search bar -n foo` without `foo.json` the unnamed foo
  session's hash file). One exception, the `--review` default: a named
  append without its own file whose name is its query continues the
  hash file of that query if it holds an unnamed session of that query
  (that command always did); the session stays unnamed
  (`<<continue an unnamed session without a name>>`), so it saves back
  there with the loaded baseline and is found again next run. When the
  other file exists and is not continued, one line names it, what it
  stores (`_stored_identity`: name, or the unnamed session's query) and
  `pass -n '<its stem>'` to continue it: WARNING when the own file does
  not exist, INFO otherwise. A `<query>.json` too long for a file name
  reads as absent (the old lookup raised `OSError`).
  `appends_to_loaded_file` compares `previous._loaded_from.name` with
  `own_session_file_name(name, query)` (identities got hand copies
  wrong: `-n a` on `a.json` holding b took the built baseline and a
  renamed homonym id came back beside the new one). So every append
  that loaded a file continues it; the #207 built baseline serves only
  sessions that loaded nothing. `load_session` keeps its tolerant
  lookup for the user-facing commands (`sessions show/export/decide/
  ...`, `llm`, `enrich`, `verify`); `search -n`/`--review`, `rq` and the
  TUI all go through `create_review_session`. Real sessions
  (2026-11-19): no hash-named file, no unnamed session.

`scholar enrich` saves after every `ENRICH_SAVE_EVERY` (50) papers
(`cli.nw`, `sec:enrich-chunks`): enrich → Crossref check → assign →
`migrate_paper_id` for adoptions → `save_session`, per chunk. After such
a run `.bak` holds only the state before the last chunk, so before the
first chunk (only when there is something to enrich and the file
exists) `review.keep_copy_before_run` copies the saved file to
`<name>.json.pre-enrich-<UTC YYYYMMDDTHHMMSSZ>.bak` (atomic, under the
session lock). Each run adds a copy and the newest
`RUN_COPIES_KEPT` (3) are kept, so continuing an interrupted run does
not overwrite the original; `review._utcnow` is the test seam for the
time. The end-of-run and interrupt messages print the new path. The copy
covers the session file only: preprint adoption also rewrites the notes
and decision stores (`migrate_paper_id`), which a restore does not undo
(the report says so when a run adopted one). The name does not end in
`.json`, so the `*.json` globs of `list_sessions` and
`sessions_mentioning` skip it (tested). Ctrl-C (and
SIGTERM, turned into `KeyboardInterrupt` while the loop runs, so the
atexit cache save still happens) prints `Interrupted: saved K of N
papers; run again to continue` and exits 130.

`load_session(..., strict=True)` raises `SessionFileError` for a file
that exists but does not parse. `create_review_session` uses it, so
`search -n`/`--review`/`rq` stop with one line instead of rebuilding over
the file. Read-only callers still get `None` plus a warning.
Notes (`paper_notes.json`) and per-query decision files follow the same
rules (#114). A file that exists but does not parse raises
`notes.NotesFileError` instead of reading as empty, which used to make
the next save erase every other note. Writes are atomic with a `.bak`,
and write errors raise instead of being swallowed. `cli.main()` turns
the error into one line and exit 1. Two deliberate exceptions (#121):
the TUI catches it, shows it as a notification (and in red on the
detail screen), hides note markers and refuses note editing, but keeps
reviewing (a note whose save fails after editing is kept in
`unsaved-note-*.md`, data dir else temp dir, and the message names
it, #126); and `migrate_paper_id` logs a WARNING naming each unreadable
store file and both ids and skips it (raising would discard the
caller's enrichment run or search append), raising only on write
errors; a refused notes lock is skipped the same way (#319, see
`sec:notes-lock` above). `notes export` also writes atomically (no `.bak`).
`sessions export` stages all its files with `utils.staged_outputs` and
moves them into place only if every format succeeded (#83). The moves
are a transaction (#320, utils.nw `sec:staged-outputs`,
`place_staged_files`): every target is checked first
(`output_target_problem`: a directory there, an unwritable directory,
the sticky-bit rule of rename(2)); then each existing target is moved
aside into `.scholar-replaced-*` before the new file goes in, and a
failure part-way undoes the moves (old file back, new file without a
predecessor removed). Removals (`staged_outputs(dir, remove=[names])`,
the screen sheet's stale `BASE-tier.json`) are moves aside in the same
transaction, made after every file is in place. The moves run under
`placing_lock(dir)`: `file_lock` (required, `PLACING_LOCK_TIMEOUT` 5 s)
on `<cache dir>/locks/.export-<16 hex of sha256(resolved dir)>.lock`
(`placing_lock_path`, via `cache.get_cache_dir`, so
`SCHOLAR_CACHE_DIR` applies; `locks/` made on demand; `cache
clear`/`cache info` look only at top-level `*.pkl`, tested). Nothing
of the lock lies in the output directory (exports go into paper
repositories). A lock another export holds fails the export with one
line ("another export is moving files into DIR"), moving nothing; a
cache directory that cannot hold the lock (`OSError`, or a lock file
that cannot be made) gives one WARNING ("Moving the files into DIR
without a lock ...") and the export goes on. Limit: processes with
different cache directories (agents with their own
`SCHOLAR_CACHE_DIR`) do not exclude each other; the identity check
then still keeps every export from removing or overwriting on undo a
file it did not place, so the worst case is files of two exports mixed
(as before #320), never a deleted file (tested with two cache dirs).
The undo removes
or overwrites a placed file only while it still is that file:
`file_identity` = lstat `(st_dev, st_ino, st_size, st_mtime_ns)` of the
staged file just before its rename (after `copymode`, which changes
ctime, not mtime; a rename keeps all four). Any write, a delete and
re-create (ext4 reuses inode numbers) and a mere touch (safe side)
count as another program's file: left in place, earlier version kept,
listed in `others` ("Replaced by another program meanwhile"). NOT
detected: a writer that restores size and mtime exactly; little to
compare on a file system without inode numbers and with coarse times.
SIGINT and SIGTERM are HELD BACK for the whole transaction
(`utils.InterruptHeldBack(HELD_SIGNALS)`, moved from review.nw, which
imports it and still holds only SIGINT for the session keep; main
thread only, elsewhere it does nothing): a signal is noted, the loop
checks the note between moves (never inside one), then undoes with the
signals still held, so a second or third signal changes nothing; the
outcome is raised once as `MovesInterrupted` (a `KeyboardInterrupt`
with `.failure`; `None` = the note came during the commit, every file
in place). Each move records its intent before the rename
(`pending_aside`, `placing`) and the undo settles a pending step from
the file system (`_settle_pending`: earlier version found in the
replaced-files directory = moved aside; target with the staged
identity = placed), so an exception between a rename and its record
(not only a signal) loses nothing. The replaced-files directory is
deleted after an undo only when nothing in it is unaccounted
(`strays`; else it stays and the error names the files, "Earlier
versions left, not put back"). Restore errors go into the one message
("Could not put back: ..."), not WARNING lines. The export prints one
line for Ctrl-C and SIGTERM alike ("Export stopped by an interrupt and
was rolled back: no files were written or changed.", or the lists when
a
restore failed) and exits 130. A replaced file's mode is kept
(`shutil.copymode` onto the staged file). Each export holds
`file_lock(staging / "staging")` (`.staging.lock` INSIDE the staging
directory) and, while its moves run, `file_lock(kept / "replaced")`
(`.replaced.lock` inside the `.scholar-replaced-*` directory); both go
with their directory and stay, unlocked, in a directory a killed
export (or a failed restore) leaves. Under the directory lock
`leftover_directories` reports each `.scholar-replaced-*` and
`.scholar-staging-*` whose own lock is free (`left_over`), so a live
export of another cache directory is never reported; one WARNING each
(`leftover_warning`; the replaced-files one says it holds the versions
from before the unfinished export and that the files in the directory
are the latest finished export's), deleting nothing. The export's own
staging directory is skipped BEFORE any lock is tried (#335:
`file_lock` is reentrant, so `left_over` took the export's own lock,
and a relative `-o` made `mkdtemp`'s absolute path differ from the
relative entries): `leftover_directories(dir, own=[...])` compares
`Path.resolve()` (`own_directory`), and `left_over` also answers held
for a lock this thread holds under that path (`is_locked`). The
replaced-files directory is made after the scan. Tested with relative,
`./`, `..` and symlinked spellings (`TestStagedOutputOwnDirectories`,
`TestExportRelativeOutput`). A failure raises
`OutputsNotPlaced` (`new`/`old`/`missing`/`not_written`/`others`, `kept`,
`rolled_back`, `changed`); `cli.export_failure_text` words the message
from it: "no files were written or changed" (with "and was rolled
back" when files had moved) only when `not changed`, else "Export
failed part-way and could not be rolled back" plus one line per kind
naming where an earlier version is kept (that directory is then left).
The rest-sample export says "None of the exported files was written or
changed" and "the screen sheet was not written" unless a restore
failed, then "... after the draw was recorded and could not be rolled
back" with the list. Limits (in the prose): several renames are not
one atomic step; between the move aside and the move in the name holds
no file; SIGKILL or a power loss undoes nothing: the moved files stay,
the earlier versions are in `.scholar-replaced-*` under their own names
(move them back, then delete both hidden directories), the unmoved new
files in `.scholar-staging-*`; the check is a forecast (`os.access`
caveats), the undo is the guard.
`sessions list` warns on stderr about sessions with records but no
decisions and no context (`needs_check` in the JSON). The paper registry
is process-global, so tests that load sessions should use unique DOIs or
`isolated_registry()`.
