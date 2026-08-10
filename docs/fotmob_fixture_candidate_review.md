# FotMob fixture candidate review gate

## Purpose

This boundary sits between PR #40's provenance-backed `UNREVIEWED` FotMob
fixture candidates and PR #29's strict Fixture Catalog input contract.

It exists to prevent an `UNREVIEWED` candidate from becoming a catalog fixture
merely because its source JSON was well formed or because its fields look
plausible.

The chain is deliberately explicit:

```text
verified PR #38 capture
    -> PR #39 schema assessment
    -> PR #40 UNREVIEWED candidate bundle
    -> explicit review decision                 <-- this boundary
    -> PR #29-compatible provenance input
    -> separate Fixture Catalog compilation
```

PR #41 does **not** compile or publish a Fixture Catalog. It does not qualify
FotMob globally, resolve team or competition identity, fetch more data, create
Fixture Intelligence, run a model, price a market, select a bet, or authorize a
BET.

## Review is explicit, never automatic

`build_fotmob_fixture_candidate_review_bundle()` accepts an existing immutable
PR #40 `FotMobFixtureCandidateBundle` plus zero or more explicit
`FotMobFixtureCandidateReviewDecision` objects.

An empty decision set leaves every candidate unreviewed. There is no "approve
all", confidence threshold, default approval, inferred review timestamp, or
implicit promotion path.

Each decision is anchored to one exact candidate by all three of:

- source capture manifest SHA-256;
- exact source match ID;
- canonical candidate SHA-256.

Changing a candidate name, competition, kickoff, source ancestry, or any other
serialized candidate field changes the candidate SHA-256 and invalidates the
review decision.

The reviewer must also supply a timezone-aware `reviewed_at` value and a
non-empty `reviewer_reference`. `reviewed_at` cannot predate the preserved
source observation timestamp. The decision may be `APPROVED` or `REJECTED`.
Only an explicit `APPROVED` decision can produce a PR #29-compatible input.

## Conflict and compatibility blockers

Some candidates are derived as blocked before any reviewer decision is
considered. A blocked candidate cannot be approved by this contract.

The blocker set is deterministic and includes:

- repeated source match IDs;
- PR #40 fixture identity conflicts;
- PR #40 home-team identity conflicts;
- PR #40 away-team identity conflicts;
- PR #40 competition identity conflicts;
- exact source strings that cannot satisfy PR #29's strict non-empty,
  no-surrounding-whitespace catalog input contract;
- identical exact `home_name` and `away_name` values.

This means the known FotMob source-team conflict for ID `394121`
(`VfL Wolfsburg` versus `VfL Wolfsburg (W)`) remains surfaced and blocks every
candidate that relies on that conflicted source-team identity. PR #41 does not
infer that `(W)` means women, choose a preferred variant, remove the suffix, or
create a canonical ATHENA team identity.

Repeated source match IDs are also blocked even if their fixture tuple is
otherwise identical. Selecting one occurrence automatically would create an
unreviewed source-precedence decision and could collide with PR #29's
`FOTMOB:<source_fixture_identifier>` identity rule.

A reviewer may explicitly reject a blocked candidate, but cannot approve it
until a later separately reviewed identity-resolution boundary exists.

## Exact PR #29 projection

For an approved, unblocked candidate, the review bundle emits a
`FotMobReviewedFixtureCatalogInput`. Its `to_catalog_input_dict()` method has
exactly the PR #29 input keys.

| PR #29 input field | Source in PR #41 |
| --- | --- |
| `schema_version` | exact integer `1` |
| `source` | exact `FOTMOB` |
| `source_fixture_identifier` | decimal string of exact `source_match_id` |
| `home_team` | exact PR #40 `home_name` |
| `away_team` | exact PR #40 `away_name` |
| `competition` | exact PR #40 `source_competition_name` |
| `kickoff` | exact PR #40 reviewed UTC kickoff |
| `source_reference` | deterministic reference to the exact source capture manifest SHA-256 |
| `reviewed_at` | explicit reviewer timestamp |
| `evidence_file_path` | deterministic PR #38 `response.json` path beneath the capture root |
| `evidence_sha256` | exact PR #38 raw response SHA-256 carried through PR #40 |

No source string is trimmed, case-folded, transliterated, aliased, fuzzily
matched, or otherwise normalized. If an exact source string is incompatible
with PR #29's strict input contract, the candidate is blocked rather than
rewritten.

`home_long_name` and `away_long_name` remain preserved in the PR #40 candidate
but are not silently substituted for the PR #29 display-team fields. PR #41's
mapping explicitly uses `home_name` and `away_name`.

The deterministic evidence path is reconstructed from the PR #40 source
descriptor using PR #38's existing `capture_identifier()` contract. PR #29 will
still re-read the evidence file and verify its SHA-256 when a later operator
actually compiles a catalog.

## What approval means and does not mean

An `APPROVED` review decision means only that this exact candidate may be
projected into the already-reviewed PR #29 provenance-input schema.

It does **not** mean:

- FotMob is globally source-qualified;
- FotMob team IDs are canonical ATHENA identities;
- league IDs are canonical competition identities;
- score or status fields have trusted settlement semantics;
- freshness metadata exists;
- the candidate has been added to a catalog;
- the candidate is eligible for Fixture Intelligence, model inference, pricing,
  selection, or betting without the later boundaries succeeding.

`SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]` therefore remains unchanged
and `UNKNOWN` for the capabilities PR #37-#40 did not establish globally.

## Determinism and auditability

The review bundle records:

- upstream candidate bundle SHA-256;
- total candidate count;
- explicit decision count;
- approved/rejected/unreviewed counts;
- every derived blocked candidate and reason;
- every explicit review decision;
- every approved PR #29-compatible projection;
- an all-false safety map.

Decision input order does not affect canonical review-bundle bytes or SHA-256.
All candidate, block, decision, and approved-input keys are deterministic and
must be unique.

## Safety boundary

All authorization fields remain exact `false`, including automatic review,
source qualification, identity resolution, Fixture Catalog compilation,
Fixture Catalog promotion, Fixture Intelligence, model features, probability,
pricing, selection, and betting.

The production module performs no network acquisition and imports no HTTP,
browser, scraping, model, pricing, selection, or betting path. It deliberately
does not call `compile_fixture_catalog()`.

A later PR may add an operator-facing offline workflow that serializes reviewed
inputs and invokes the already hardened PR #29 compiler. That later step must
remain separately reviewable and must not weaken this per-candidate review gate.
