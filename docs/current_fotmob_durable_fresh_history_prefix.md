# Current FotMob durable fresh-history prefix binding

## Purpose

PR #245 closes the history-completeness gap identified by PR #244 without
creating another feature model, another settlement authority, or another source
of football truth.

The reviewed chain being composed is:

`reviewed PR151 GitHub Actions lineage`
→ current PR175 / ambiguity-recovery audit projection
→ immutable snapshot of every GitHub read consumed by that audit
→ exact audit replay from the snapshot
→ unique latest applicable committed PR151 success
→ GitHub Actions artifact SHA-256 metadata
→ canonical PR151 tick receipt
→ exact cumulative archive SHA/size
→ PR151 hardened archive extraction
→ append-only capture/prediction/identity/settlement/control journals
→ exact checkpoint reconciliation
→ every reviewed settled prediction in the durable prefix
→ PR244 current-fixture UTC-native shadow replay.

## Two proofs are required

A valid cumulative success archive proves that its internal state is complete
through its own committed tick. That is necessary but not sufficient to call the
state the **complete current history prefix** for a current FotMob observation.

A second proof must show that the selected success archive is the unique latest
PR151 committed success state whose real `committed_at_utc` is not later than the
exact current source `observed_at`.

PR #245 therefore has two layers:

1. cumulative success archive proof; and
2. latest-applicable success selection proof.

The first layer fixes both:

- `latest_applicable_success_selection_proven = false`; and
- `current_fresh_history_prefix_complete = false`.

Those values cannot be relabelled to true. Only the second layer may wrap that
lower proof with complete-current-history evidence.

## Archive proof

`domain/current_fotmob_durable_fresh_history_prefix.py` accepts only an exact
PR151 `success-...tar.gz` Actions artifact ZIP plus GitHub's independent artifact
ZIP SHA-256 metadata.

It reuses PR168's reviewed artifact/receipt verifier and then requires:

- exact canonical workflow receipt schema;
- PR151 runner identity, runner state, next-boundary and safety state unchanged;
- zero-exit committed success semantics;
- exact run ID / archive name / nominal slot / cron identity;
- archive SHA-256 and size equality;
- real commit time not later than the current FotMob capture observation;
- hardened PR151 archive extraction;
- canonical append-only journals;
- unique committed schedule slots;
- latest in-archive committed slot equal to the receipt slot;
- checkpoint schedule, phase, release and asset identity equality;
- checkpoint capture/prediction/terminal/control counts equal replayed journals;
- every reviewed settled prediction reconstructable through the existing PR151
  settlement parser; and
- no settlement observation later than the durable prefix commit.

The complete reviewed settlement tuple from that archive is then passed to PR244.
No caller-supplied form/Elo/fatigue values are introduced.

## Latest-applicable proof

`domain/current_fotmob_latest_durable_fresh_history.py` does not trust a detached
audit result or a caller-supplied run list.

Production acquisition is fixed to `Thabearr/ATHENA` and the reviewed PR151
scheduled workflow. The current compatibility surface is the unchanged PR174
read-only audit engine projected through PR175 and the later schedule-recovery
projection. The projection pins the current workflow, failure-lineage and
ambiguity-recovery helper identities before the audit runs.

Every GitHub read actually consumed by that audit is captured as an immutable
snapshot:

- current `main` ref JSON;
- paginated workflow-run JSON;
- per-run artifact metadata JSON;
- exact Actions artifact ZIP bytes;
- Release metadata JSON;
- exact Release asset bytes when consumed; and
- job metadata used by the reviewed no-acquisition proofs.

Read failures are also converted into deterministic recorded failure evidence so
a transient or missing GitHub response cannot silently disappear on replay.

Whenever the evidence bundle is reconstructed it re-runs the reviewed projected
audit entirely from those captured reads and requires byte-identical canonical
audit output. A canonical but fabricated audit result therefore cannot omit a
newer success and relabel a stale prefix as current.

The GitHub JSON snapshot is an auditable replay input, not a claim that GitHub
cryptographically signs every JSON response. Byte-level state authority remains
anchored independently by Actions artifact SHA-256 metadata, PR151 receipt/archive
commitments, and the reviewed long-lived Release checks.

## As-of selection rule

The current source observation is the exact FotMob capture manifest
`observed_at`. The selector:

- replays every audited success artifact and exact PR151 receipt;
- permits historical successes to have partial long-lived Release durability
  because they are not the selected state;
- rejects any completed-but-unverified PR151 run that existed by the source
  observation because it could hide a committed state;
- ignores a valid success whose real `committed_at_utc` is later than the source
  observation;
- selects the unique maximum `committed_at_utc <= source_observed_at`;
- fails on a tied latest commit time; and
- requires the selected latest success itself to have
  `RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED` durability.

The selected archive bytes and GitHub artifact digest metadata must then be the
same exact inputs consumed by the lower cumulative-prefix proof.

Only after all of those checks may #245 state:

- `latest_applicable_success_selection_proven = true`; and
- `current_fresh_history_prefix_complete = true`.

## Authority

Complete current history is evidence about the reviewed football-history state.
It does **not** grant downstream model or betting authority.

PR #245 keeps all of the following false:

- production model use;
- ScoreMatrix;
- football market probability;
- Phase 6;
- pricing;
- selection;
- SportyBet execution; and
- BET/wager placement.

`wager_placed=false`.

The next boundary remains:

`CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION`

Production model/ScoreMatrix/Phase-6 authority is separately time-gated by the
pre-registered fresh-holdout confirmation process. PR #245 does not bypass,
reinterpret, or shorten that holdout.
