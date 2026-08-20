# Reviewed FotMob match-details array records

## Boundary

This boundary is the dedicated repeated-record counterpart to PR54. PR54 is
unchanged: an ordinary scalar review still cannot approve `/*` paths. Here, a
wildcard is legal only as part of an exact-observation record-set decision that
fully replays the same PR52 persisted bytes and PR53 structural assessment.

The contract is `EXACT_OBSERVATION_ONLY`. It upgrades no global FotMob source
capability. Public descriptions and suggestive key names carry no authority.

## Exact reviewed contract

Every decision binds:

- the PR53 canonical SHA, PR52 receipt SHA, manifest SHA, raw SHA and size;
- fixture identifier, FotMob source match ID, kickoff and observation time;
- exact array-root and repeated-record pointer patterns;
- exact non-null scalar member patterns and observed JSON kinds;
- an exact provider team ID plus independent raw team-ID and home/away scalar
  pointers;
- record-set semantics (`TARGET_STARTING_XI`, `TARGET_BENCH`, or
  `TARGET_UNAVAILABLE`);
- `QUALIFIED` or `REJECTED`, explicit `fresh_until`, the inclusive comparator,
  reviewer identity, review time and classification time;
- optional exact lineup-state and source-position review mappings.

The record pattern is the exact `/*` child of its reviewed array root. The root
may itself contain reviewed wildcard coordinates; it must resolve to exactly
one array for the decision. Scalar member paths cannot introduce another
unreviewed array. Exact raw coordinates are retained as provenance, but record
identity is always the provider player ID. Source order and array index are
never identity or team side.

Provider team IDs and an independent reviewed Boolean establish HOME/AWAY.
First/second array position, parity and display order are forbidden. Qualified
nonempty records require `PLAYER_ID`; optional `TEAM_ID` and `IS_HOME_TEAM`
members must reconcile with the root-level binding. Duplicated player IDs, or
the same player in contradictory starter/bench/unavailable scopes, fail closed.

## Lineup, position, qualification and freshness

`CONFIRMED`, `EXPECTED`, and `NOT_AVAILABLE` arise only when an exact reviewed
source scalar matches an exact review mapping. Array presence and proximity to
kickoff never infer them; otherwise the state is
`UNVERIFIED_LINEUP_STATE`.

Exact source position text is preserved. A coarse `GK`, `DEF`, `MID`, or `FWD`
group exists only for an exact reviewed mapping whose source value occurs in
this raw observation. Unmapped values remain `UNKNOWN`; no name, shirt-number,
or fuzzy mapping exists.

Classification is prospective:

`observed_at <= reviewed_at <= classified_at < kickoff`.

`QUALIFIED` evidence is `SUPPORTED` when
`classified_at <= fresh_until`, otherwise `STALE`. `REJECTED` remains
`UNVERIFIED`. Contradictory provider identity fails closed; the typed status
vocabulary also preserves `CONFLICTED` for downstream reviewed evidence that
may explicitly carry that state. There is no default freshness duration.

## Completeness

An absent root proves nothing. A complete empty set exists only when the exact
raw root is present, PR53 proves `ARRAY`, replay reconstructs cardinality zero,
and the reviewer explicitly attests exact-observation completeness.

`ReviewedArrayCompletenessReceipt` binds FotMob/provider dataset, fixture,
source match, provider team, HOME/AWAY, `as_of`, raw and PR53 evidence hashes,
record patterns, exact identity-sorted provider player IDs and count. It is a
real reviewed receipt. PR190's `CompletenessReceiptCandidate` remains
candidate-only and cannot self-upgrade.

## Local evidence limitation

At this base, no preserved PR52/PR53 match-details raw capture containing player
arrays is available as a tracked or admissible local observation. This PR
therefore commits the deterministic boundary and synthetic adversarial proofs,
not a real-fixture array admission.

All array-artifact authority flags remain false.
