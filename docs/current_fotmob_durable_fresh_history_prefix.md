# Current FotMob durable fresh-history prefix binding

## Purpose

PR #245 closes the history-completeness gap identified by PR #244 without
creating another feature model or another settlement authority.

The reviewed chain being composed is:

`PR151 cumulative success Actions artifact`
→ GitHub artifact SHA-256 metadata
→ canonical tick receipt
→ exact success archive SHA/size
→ PR151 hardened archive extraction
→ append-only capture/prediction/identity/settlement/control journals
→ exact checkpoint reconciliation
→ every reviewed settled prediction in the durable prefix
→ PR244 current-fixture UTC-native shadow replay.

## Two proofs are required

A valid cumulative success archive proves that its internal state is complete
through its own committed tick. That is necessary but not sufficient to call the
state the **complete current history prefix** for a current FotMob observation.

A second proof must show that the selected success archive is the latest PR151
committed success state whose real `committed_at_utc` is not later than the exact
current source `observed_at`.

PR #245 is therefore implemented in two layers:

1. cumulative success archive proof; and
2. latest-applicable success selection proof.

The first layer fixes both:

- `latest_applicable_success_selection_proven = false`; and
- `current_fresh_history_prefix_complete = false`.

Those values cannot be relabelled to true.

## Archive proof

`domain/current_fotmob_durable_fresh_history_prefix.py` accepts only an exact
PR151 `success-...tar.gz` Actions artifact ZIP plus GitHub's independent artifact
ZIP SHA-256 metadata.

It reuses PR168's reviewed artifact/receipt verifier and then requires:

- exact canonical workflow receipt schema;
- PR151 runner identity and safety state unchanged;
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

## Authority

The archive-proof layer grants no downstream authority. In particular it does
not authorize:

- complete-current-history status;
- production model use;
- ScoreMatrix;
- football market probability;
- Phase 6;
- pricing;
- selection;
- SportyBet execution; or
- BET/wager placement.

`wager_placed=false`.

## Remaining #245 boundary

`LATEST_APPLICABLE_PR151_SUCCESS_PREFIX_SELECTION_REQUIRED`

The final #245 layer must use a fixed reviewed GitHub workflow/release inventory
query, not a caller-supplied run list, and prove there is no newer committed PR151
success state with `committed_at_utc <= current_source_observed_at` before it may
flip complete-current-history evidence to true.

Production model/ScoreMatrix/Phase-6 authority remains separately time-gated by
the pre-registered fresh-holdout confirmation process even after this history
prefix boundary is closed.
