# FotMob → PR80 source-local time semantic equivalence protocol

## Purpose

PR #120 pre-registers the next narrow ATHENA boundary after the PR #119 frozen historical materialization.

PR #119 proved scoped historical completeness through `2026-08-14` and materialized exactly `21,326` ordinary-FT rows, but deliberately left one important statement false:

`pr80_source_local_semantic_equivalence = UNPROVEN`

This PR does **not** try to answer that question. It freezes what a later execution must prove before those rows can become authorized PR #80 constructor history.

Protocol state:

`PRE_REGISTERED_NOT_EXECUTED_SOURCE_LOCAL_TIME_EQUIVALENCE_UNQUALIFIED`

No positive result is embedded in this PR.

## Exact ancestry

The protocol is anchored to `main`:

`37c5f031a71222b13cbea19eaab0fbd92ba74aa0`

It freezes:

- PR #119 receipt SHA-256 `da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0`, size `6,810`;
- PR #119 qualification blob `f0d17dbcd70fc8b5432b50061525224642541c05`;
- PR #80 constructor blob `9135f056d036fd0207a3daead2599ac2520274be`;
- PR #69 historical replay blob `b67a7e52954f47cc90c578ad193545c541984964`;
- PR #78 semantic protocol blob `cbd409fe42ffa8a3571f604e0817c06671db2a25`.

The canonical protocol is:

- SHA-256 `a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918`;
- size `5,242` bytes.

## Why this boundary exists

PR #69 intentionally records its football-data.co.uk time basis as:

`SOURCE_LOCAL_TIMEZONE_UNRESOLVED`

It parses the source `Date` and `Time` fields and combines them into a naive datetime. It does not prove which IANA timezone that wall clock belongs to.

PR #80 requires:

`SOURCE_LOCAL_NAIVE_DATETIME_REQUIRED_FOR_PR78_PARITY`

That naive value is not decorative. It participates in the exact historical successor semantics.

PR #119 currently represents FotMob history using canonical `status.utcTime`, converted to `Europe/Oslo`, then made naive. The frozen corpus has zero global source-local/UTC ordering disagreements and zero same-team same-kickoff conflicts. Those are useful facts, but they do not by themselves establish semantic equivalence to the unresolved PR #69 wall-clock basis.

## The fatigue reason matters

Form and Elo depend on chronological ordering. Fatigue is stricter.

The frozen fatigue calculation uses the Python-style integer `.days` component of naive datetime deltas, then computes:

`home_rest_days - away_rest_days`

and maps that difference into the frozen fatigue buckets.

A timezone or daylight-saving shift can leave the overall match order unchanged while still moving a datetime delta across an integer-day boundary. Therefore:

`ZERO_GLOBAL_ORDERING_DISAGREEMENT_DOES_NOT_PROVE_DATETIME_DELTA_DAYS_EQUIVALENCE`

This is why PR #120 will not promote the `Europe/Oslo` candidate solely because the global ordering happens to match UTC.

## What a positive future qualification must prove

A future execution must first resolve the PR #69 source-local basis to a deterministic reviewed rule **or** establish a formal source-independent invariance argument whose assumptions are themselves proven for the frozen scope.

It must then prove, rather than assume, that the FotMob `Europe/Oslo` naive representation is admissible under that reference and that every time-dependent PR #80 operation remains equivalent:

- strict-prior membership;
- form ordering and fixture-ID tie behavior;
- Elo ordering and fixture-ID tie behavior;
- most-recent prior fixture per source-scoped team;
- home and away integer rest-day components;
- home-minus-away rest-day difference;
- final fatigue bucket.

Any unresolved temporal ambiguity fails closed.

## Admissible evidence

Future execution may rely on exact frozen repository ancestry and raw source bytes, preserved/hash-bound primary football-data.co.uk documentation or source semantics, preserved/hash-bound primary FotMob documentation or response semantics, or a formal source-independent invariance proof with every required assumption proven for the frozen scope.

Documentation or inference must be preserved and auditable before it can support a positive result.

## Forbidden shortcuts

The protocol explicitly forbids:

- assuming `Europe/Oslo` equals the PR #69 source-local basis;
- inferring timezone merely from country, league or venue without reviewed evidence;
- treating zero global ordering disagreement as proof of fatigue-day equivalence;
- treating equal numeric feature outputs alone as semantic proof;
- using cross-source fixture/team identity inference to conceal time-basis uncertainty;
- changing PR #69, PR #78, PR #80 or PR #119 semantics after seeing execution results.

## Frozen scope only

The future qualification concerns exactly the `21,326` PR #119 rows, exactly the current eleven validated historical/model families, and exactly the frozen historical envelope through `2026-08-14`.

The eleven families are not ATHENA's complete competition universe.

This protocol does not authorize later dates, target-specific PR #80 construction, or global FotMob historical-coverage promotion.

## Fail-closed status vocabulary

The future execution must return one of the frozen statuses:

- `QUALIFIED_EXACT_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE`
- `BLOCKED_PR69_REFERENCE_TIME_BASIS_UNRESOLVED`
- `BLOCKED_FOTMOB_TIME_BASIS_EVIDENCE_INSUFFICIENT`
- `BLOCKED_TIME_DEPENDENT_OPERATION_MISMATCH`
- `BLOCKED_TEMPORAL_AMBIGUITY`
- `BLOCKED_ANCESTRY_OR_EVIDENCE_GAP`

The protocol does not pre-select which status execution will produce.

## Safety boundary

All downstream authority remains false. In particular this PR does not authorize PR #80 constructor input, successor live inputs, a successor candidate, model training, expected-goals production, a score matrix, probabilities, calibration, pricing, market activation, selection, production approval, or BET.

## Next boundary

After this preregistration is merged, the next exact boundary is:

`EXECUTE_REVIEWED_FOTMOB_PR80_SOURCE_LOCAL_TIME_SEMANTIC_EQUIVALENCE_QUALIFICATION`
