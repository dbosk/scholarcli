# Preprints, copies of one work and renamed papers

Agent notes for Scholar; the index is `AGENTS.md` in the repository root.

## Preprint Fallback (adopt a preprint when no PDF is found)

When enrichment ends with no `pdf_url` (providers + Unpaywall found
nothing), `preprint.find_preprint(paper, search=False)` tries to locate a
preprint version and **replace the entry with it** (preprint DOI, venue,
pdf_url) so citations point at the version actually read. The published
DOI is kept in `Paper.published_versions`
(`{"doi": ..., "relation": "preprint-of"}`, drives
`is_preprint_substitute`). Tiers, first adoptable (= yields a PDF) wins:

0. `Paper.preprint_versions` links recorded by dedup (see below).
1. OpenAlex `locations` of the published DOI
   (`OpenAlexProvider.get_preprint_locations`); arXiv locations become a
   full replacement via the derived arXiv DOI, other hosts only fill
   `pdf_url` (no DOI to swap to).
2. Crossref `has-preprint` relation (`crossref.fetch_preprint_dois`,
   parsed from the same cached `fetch_currency` response; cache key is
   versioned via `CURRENCY_CACHE_VERSION`).
3. Only with `--preprint-search` (on `scholar enrich` and
   `search --enrich`): one OpenAlex `type:preprint` title search
   (`search_preprints_by_title`) + one arXiv search; candidates accepted
   only on exact `legacy_hash_paper_id(title, authors)` match — title and
   authors are the only data shared between versions, and fuzzy matching
   is deliberately avoided.

Identity change on adoption is handled by `notes.migrate_paper_id`
(notes + decision stores), announced by `scholar enrich`
("Adopted preprint <doi> ..."), and reconciled at session append in
`review.py` (both directions: returning published version folds into the
adopted entry; a later-arriving adoption upgrades an existing published
entry, keeping its decision).

**Version-aware dedup**: `deduplicate_papers` runs a second pass
(`deduplicate_versions`) grouping by `legacy_hash_paper_id`; a group of
exactly one published paper (`utils.is_preprint_paper` classifies by DOI
prefix/venue) plus preprints collapses onto the published entry, filling
content gaps via `merge_version_of` (never version-specific fields like
`pdf_url`) and recording `Paper.preprint_versions`
(`{"doi", "pdf_url"}`) for tier 0. Ambiguous groups are left untouched.

**DOI-less copies and namesakes** (#170, `scholar.nw`
`sec:same-work-guard`/`sec:doi-less-copies`, `review.nw`
`sec:session-copies`): `plausibly_same_work` (moved from the sessions
check; DOIs differ and are not version-linked, or years > 1 apart →
not the same work) guards every title-based match. `deduplicate_papers`
merges two hash-id copies only when it admits them (a DOI merges
whatever the years), then `link_doi_less_copies` folds a DOI-less copy
into the one published DOI copy whose `legacy_hash_paper_id` equals its
id (`doi_copy_index`/`doi_copy_of`; preprints and ambiguous choices are
left alone, and so is a copy without a year or a first author,
`foldable_copy`). In sessions an append never folds (folding at
append time raced other processes: double folds, notes moved by
`get_note` on read, undo losing enrichment, stale saves resurrecting
copies). `scholar sessions reconcile S [--dry-run]`
(`reconcile_session`) takes the session file lock (reentrant, so the
inner `save_session` takes it again), loads fresh, folds every
`foldable_copies` pair with `reconcile_copies` (an `is_unscreened` copy
-- pending, untagged, human, no confidence or `LLM_AUDIT_FIELDS` -- into
the other, or two equal decisions: `decision_state` includes source and
audit fields, so a fold never relabels a source; not if both ids have
notes), saves, and only then moves notes: `move_stranded_notes` moves
every tombstoned id's note whose new id has none and whose old id the
session no longer holds (a copy kept apart keeps its note), so a re-run
repairs a failed note write or a note a stale process saved under the
old id.
`--dry-run` runs `reconcile_copies` in memory without saving, so it
lists exactly what a real run folds. Each fold leaves a tombstone in `ReviewSession.folded` (`{old_id: new_id}`,
the DOI-less id always the old one; saved as `"folded"` only when
non-empty, united with the file's on save). `merge_concurrent_changes`
calls `apply_tombstones` after the three-way decision merge and the
disk additions (a disk target the session loaded and renamed is not
re-added). **Folding happens only in `sessions reconcile`; a save never
folds a decision.** `apply_tombstones` only drops an in-memory copy
under a tombstoned id that this process left untouched: unscreened,
unchanged since loaded, without a note, and no longer in the file (its
links, provider and `merge_version_of` metadata go to the target).
Every other copy stays beside its target, never copying or dropping a
decision, and is listed as foldable or conflicting for the next
reconcile. Races tested with real subprocesses in both save orders.
In the merge the tombstones run after the decision merge and before
the record merge and `supersede_merged_records`, which repoints the
links a dropped copy gave its target like all others; providers of
folded copies are united with `united_providers` (comma-joined, as
per-provider `found_by` records them). `repoint_paper_ids`
repoints snowball `source_papers`, LLM sample `paper_id`s and tier
sample ids through `folded` and `renamed` (see Renames below);
`create_review_session` routes a result under a tombstoned id to its
target, unless `plausibly_same_work` rules it out (a namesake goes to
`same_id_copies`). The drop guard allows only for decided copies the file holds
under a tombstoned id that the session no longer holds.
**Renames** (#319, review.nw `sec:session-renames`):
`ReviewSession.renamed` (old id -> id the session now holds the paper
under; saved as `"renamed"` only when non-empty, old files `{}`,
united `{**on_disk.renamed, **session.renamed}` in
`merge_concurrent_changes`, carried by `create_review_session` like
`folded`). A separate map, not tombstones: the append routes a
result under a folded-away id only if `plausibly_same_work`, which
would make a published version years younger than its adopted
preprint a namesake. `record_rename(session, old, new)` (drops a
reverse entry, then `repoint_paper_ids`) is called by the append's
renamed branch (homonym number, surname first) and its adoption
branch (`replaced`), by `scholar enrich`'s adoption and by the TUI's
enrichment `finish()`. A DOI-less decision met by its DOI copy is no
rename (the append keeps both; reconcile folds). `current_paper_id
(session, id, held)` follows `folded` (wins) then `renamed`, cycle
guard; an id a decision still holds is its own (so a copy kept apart,
or a stale process's write-back, keeps its sample entry).
`repoint_paper_ids` runs at each rename, in `read_session_file` and at
the end of every merge, so old files' samples are repointed once a
rename record names the id; renames before #319 left no record and
stay "not found". A stale process still writes a renamed paper back
under its old id (no tombstone drop for renames; pre-existing, #327);
two processes renaming one paper two ways (adoption vs append) leave
both decisions, the map entry of the last saver, and the sample on
the adopted id in both orders (pinned by real-subprocess tests).
`settle_rename_cycles` (after the merge's union) drops the entry of a
pair `a -> b`, `b -> a` that leads away from the held id, so a rename
back leaves no cycle on disk.
Checked: the pipx build 1.29 loads a file with `renamed` and drops
it on save (decisions kept).
Nothing unreconciled is silent: `foldable_copies` (counted with the
reconcile hint), `conflicting_copies` (pairs with different statuses,
plus `same_id_copies`), `alike_copies` (same status, different
tags/source: not folded, merging tags is a judgement) and
`possible_copies` (DOI-less decisions sharing an `audit_work_key` with a
DOI decision but in none of those lists) are shown by `sessions show`
(lines; foldable and possible copies counted, ids in JSON) and counted
in the report. The pairs are DOI-less/DOI copy pairs plus two decided
decisions under one id whose `decision_state` differs (`same_id_pairs`,
any id, DOI too; #215: a store re-run can leave them, see below);
conflicting if statuses differ, else alike; same state or a pending
copy: not listed; `sessions reconcile` never folds them (no other id to
fold to). Such a pair lasts (#228): `_build_previous_decision_lookup`
holds the *first* decision of an id (the returned paper attaches to
it; in #208's pairs that is the copy a search reached), the other
copies are carried through unchanged after the conversion (before it
they would be in `decision_lookup` and catch the returned paper); the
baseline keys decisions by occurrence when taken (`decision_keys`:
paper id, then `id#2`, `id#3` in session order; one decision per id =
plain ids; `decision_ids` maps key → paper id; paper states stay by
id, the registry gives copies one `Paper`). Places move, so each
decision carries its key (`ReviewDecision.baseline_key`, not saved,
`compare=False`, kept by `replace`), set by `assign_baseline_keys` at
load, after a save and for a built baseline of a session that loaded
nothing; `base_key_of(d, base)` = that key while `decision_ids[key]`
is still d's paper id, else the paper id (decisions made since,
renamed ones, a fold's survivor, which so meets the DOI copy's
baseline as before). The merge pairs via `pair_with_file` per paper
id: first our keyed copies with a free file copy in their loaded state
(among several: same `found_by` set, then same provider, then order),
then the rest by order; links, notes, paper fields and
decision changes pass only within pairs. Unpaired file copies: the
baseline's entries of the id no copy of ours carries were loaded and
are gone here (renamed/folded/dropped), matched by state first, then
by order; the rest are added. `apply_tombstones(session, base,
paired)` judges each decision under a folded id, "no longer in the
file" = unpaired; `warn_if_decisions_dropped` uses `base_key_of`.
`sessions decide` selects every decision of a `--doi`/`--paper-id`;
if any selected copies are a `same_id_pairs` pair it refuses (exit 2,
each pair named by `copy_conflict_line`, unsaved) unless
`--all-copies`; agreeing copies or a pending copy are decided together
without it. Its summary counts papers ("1 paper(s) marked kept (2
decisions)").
The report also states "Unique works" from the audit rows.
**Remaining gap**: the
pairing uses the exact title + surname hash, the audit work key is
looser (punctuation, case, year), so on the real sessions 2995 DOI-less
records share a work key with a DOI record and only 403 pair; the rest
are only counted as possible copies, deliberately not folded.
**Known limitation**: a DOI-less id is a hash of title + surname, so two
works years apart share it, and decisions, notes and the registry
cannot separate them without changing the id scheme. A session keeps
the stored paper unmerged and notes the newcomer in
`ReviewDecision.same_id_copies` (`{"year", "venue", "provider"}`,
saved only when non-empty, unioned by the concurrent merge), which
`sessions show` lists as a conflicting copy naming both years.
