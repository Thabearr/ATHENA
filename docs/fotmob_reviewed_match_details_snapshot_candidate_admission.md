# Reviewed FotMob match-details snapshot candidate admission

## Purpose

PR #64 is a narrow human admission boundary over one exact PR #63 candidate
set. It performs no evidence collection, no football-truth decision, no
conflict resolution, and no snapshot construction.

```text
exact PR #52 -> PR #62 materializations -> PR #63 candidate set
    -> PR #64 human candidate-set admission
    -> later separately reviewed PR #30 snapshot construction
```

The dataset is
`athena-fotmob-reviewed-match-details-snapshot-candidate-admission-v1`, schema
version exact integer `1`, with scope
`EXACT_FIXTURE_CLASSIFICATION_MOMENT_CANDIDATE_SET_ONLY`.

## Exact scope and reviewer attestation

An admission binds exactly one fully replayed PR #63 candidate set, including:

- its canonical SHA-256 and byte size;
- exact source-scoped fixture identifier and source match ID;
- kickoff and exact PR #61/62 `classified_at` moment;
- every PR #63 member materialization SHA-256;
- every flattened materialized-fact SHA-256, retained as an ordered multiset
  so identical payloads from distinct observations are not lost.

For `ADMITTED`, the reviewer must supply exactly
`NO_KNOWN_OMITTED_REVIEWED_MATERIALIZATIONS`. Its meaning is only:

> The reviewer knows of no omitted fully reviewed/revalidated PR #62
> materializations for this exact fixture identifier/source match ID and exact
> classified-at time within this reviewed match-details workflow represented
> here.

This is a reviewer attestation. It is **not** machine proof of global
completeness, exhaustive provider coverage, exhaustive network capture, all
football evidence, or source-wide completeness. `REJECTED` requires exactly
`NOT_ATTESTED` and exposes no admitted identity.

## Time semantics

The reviewer supplies `reviewed_at`; software never infers current time. It
must satisfy `classified_at <= reviewed_at < kickoff` in exact UTC.

Admission does not reevaluate freshness. The PR #61/62 fact statuses remain
the evidence state **as of `classified_at`**, even when human review occurs
later. Thus `ADMITTED` does not claim that a supported fact is still fresh at
`reviewed_at`. A later snapshot boundary must use `as_of = classified_at`.

## Whole-set-only admission

An admitted artifact exposes exactly one detached identity for the whole exact
candidate set; a rejected artifact exposes zero. There is no API for selected
facts, accepted members, excluded members, preferred sources, or winner
observations.

An admitted set may contain differing `SUPPORTED` values, `STALE` evidence,
`UNVERIFIED` evidence, or incomplete model-field coverage. Those conditions
do not cause automatic rejection because admission is about the intended
evidence set, not conflict-free/model-ready evidence. PR #30 must later
preserve conflicts and PR #31 must later apply its existing blockers.

`ADMITTED` means only that the exact candidate set is eligible for the **next
separately reviewed snapshot-construction boundary**. It does not mean all
evidence is supported, conflicts are resolved, model features are available,
probabilities may run, prices may be used, or a bet may be emitted.

## Replay and safety

The legal constructor and full revalidator both require the complete PR #63
input needed by `revalidate_reviewed_match_details_snapshot_candidate_set`.
That replays every PR #52→PR #62 member chain before PR #63 and then PR #64
identities are rebuilt. Supplied candidate/admission objects and immutable
canonical bytes must equal the rebuild exactly.

Canonical bytes are sorted-key compact UTF-8 JSON, `ensure_ascii=False`,
`allow_nan=False`, and exactly one trailing newline. Canonicalization rebuilds
decision and admitted-identity objects; full replay rejects coordinated local
candidate/admission mutation.

All safety flags remain exact `false`, including network acquisition,
source-wide qualification, source identity resolution, snapshot creation,
conflict resolution, model features, probability, pricing, selection,
production approval, and betting. PR #64 imports no PR #30 snapshot or PR #31
model-feature code. FotMob remains unqualified source-wide.
