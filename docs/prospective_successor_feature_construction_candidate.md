# Prospective successor feature construction candidate

## Purpose

PR #80 implements the next boundary identified by PR #79:

`BUILD_REVIEWED_EXACT_PROSPECTIVE_SUCCESSOR_FEATURE_CONSTRUCTION`.

PR #79 proved that the current reviewed FotMob -> Fixture Intelligence -> PR31
path preserves reviewed finite scalar observations but does not prove that
`home_elo`, `away_elo`, `home_form`, `away_form`, or `fatigue` were derived
using the exact mathematics used to train the validated historical successor.

PR #80 therefore stops trusting opaque provider feature scalars and implements
the five raw successor inputs directly from explicit source-scoped match-result
history supplied by a caller.

This is still a **candidate construction boundary**. No current live source is
authorized by this PR to populate a complete history corpus, and no output is
declared semantically qualified for the successor model.

## Frozen ancestry

PR #80 is based on merged `main`:

`d118fa702856d267bb6dc49301ebaee2a50dd533`

It mechanically revalidates the exact canonical PR #78 semantic protocol:

- SHA-256:
  `97a47d431ce57468598b17fcb24e9e0e9a41fa26c80ff1f4df9e2e611107ed7c`
- size: `4,904` bytes

and the exact canonical PR #79 fail-closed assessment:

- SHA-256:
  `aea27d67b93bf777a01c4956757ba7b31c521e9eea71006d20ca5bd4acf791f4`
- size: `6,204` bytes

The frozen PR #80 construction specification is:

- dataset:
  `athena-prospective-successor-feature-construction-candidate-v1`
- scope:
  `PURE_CALLER_SUPPLIED_SOURCE_SCOPED_HISTORY_TO_FROZEN_SUCCESSOR_RAW_FEATURES_ONLY`
- canonical SHA-256:
  `fd83222e0d0efe04cd312634ee113cc5757565a6c943770dd6d47b0df142af8f`
- canonical size: `2,118` bytes

Changing the specification without deliberately updating its canonical identity
fails closed.

## Input contract

The constructor accepts only explicit immutable in-memory evidence records. It
does not read the database, filesystem, network, providers, APIs, or legacy
analysis services.

Every prior result record carries:

- one exact source namespace;
- one exact source fixture identifier;
- source-local naive kickoff datetime;
- exact UTC kickoff datetime;
- exact source-scoped home and away team identifiers;
- final home and away goals;
- UTC evidence observation time;
- evidence SHA-256;
- evidence reference.

The target carries the same source namespace and source-scoped identities plus
source-local kickoff, UTC kickoff, a strictly pre-kickoff `as_of`, evidence
SHA-256, and evidence reference.

A result observation must occur after that result fixture's kickoff. This does
not by itself prove provider full-time semantics; the later reviewed source
adapter must establish that. PR #80 only defines the normalized construction
contract.

## Chronology

The training replay used source-local kickoff chronology. PR #80 preserves that
basis and additionally requires UTC chronology to agree.

A history row is usable only when:

1. its source-local kickoff is strictly before the target source-local kickoff;
2. its UTC kickoff is strictly before the target UTC kickoff;
3. its final-result evidence was observed no later than target `as_of`.

If source-local and UTC disagree on whether a fixture is prior to the target,
construction fails closed.

Eligible history is ordered by:

`source_local_kickoff ASC, fixture_identifier ASC`.

Sorting the same rows by UTC kickoff must produce the same fixture order.
Otherwise the history is temporally ambiguous and construction fails closed.

A source-scoped team cannot have two eligible fixtures at the same source-local
kickoff. Duplicate source fixture identifiers, a target fixture inside prior
history, cross-source history, or another supplied target-team fixture at the
target kickoff also fail closed.

## Form

PR #80 reproduces the PR #78 / PR #69 historical form construction exactly.

For each target team:

1. select strictly prior eligible fixtures containing that exact source-scoped
   team identity;
2. order most recent first;
3. take at most five;
4. score win = 3, draw = 1, loss = 0;
5. compute

   `round(0.10 + ((points / (n * 3)) * 0.85), 3)`.

If there is no prior fixture, form is `MISSING_PRIOR_HISTORY`.

There is **no 0.50 fallback** for missing history, database errors, provider
absence, or any other uncertainty.

The feature records the exact fixture identifiers and evidence SHA-256 values
used in its five-match window.

## Fatigue

PR #80 reproduces the frozen home-relative historical fatigue rule.

For each target team, use the most recent strictly prior eligible fixture. If
either team has no prior fixture, fatigue is `MISSING_PRIOR_HISTORY`.

Otherwise:

`difference = (target - home_last).days - (target - away_last).days`

and:

- `difference < -2` -> `0.30`
- `difference < 0` -> `0.10`
- otherwise -> `0.0`

The calculation uses the integer `.days` component of the source-local datetime
delta exactly as frozen by PR #78.

The feature records the exact two prior fixture identities and their evidence
hashes. No no-data value is silently converted to neutral fatigue.

## Elo

PR #80 reproduces the frozen historical overall Elo replay:

- initial rating = `1500`;
- home advantage = `+50`;
- logistic divisor = `400`;
- actual result = `1.0 / 0.5 / 0.0`;
- K = `32` before 20 matches;
- K = `24` from 20 through 49;
- K = `16` from 50 onward;
- update =
  `int(old_overall + K * (actual_score - expected_score))`;
- target feature = current overall rating before target fixture update.

Every eligible source fixture is replayed chronologically. The two target Elo
features therefore depend on the complete supplied history prefix, not only on
the target teams' direct fixtures. Their lineage is the canonical SHA-256 of the
entire eligible history prefix.

The initialization caveat remains exactly:

`1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`.

## Why the output is not yet live-qualified

Correct mathematics over an explicit supplied corpus is necessary but not
sufficient.

PR #80 does **not** prove that any existing provider or database can supply:

- a complete prior fixture corpus;
- final-result semantics;
- exact source-team identity continuity;
- complete source history from an appropriate Elo initialization boundary;
- source-local chronology equivalent to the historical training construction;
- conflict-free evidence across the complete prefix.

Therefore every artifact records:

`all_five_exact_semantic_equivalence = false`

even when all five numeric values can be constructed from a synthetic or
caller-supplied corpus.

The fixed caveat is:

`UNPROVEN_UNTIL_REVIEWED_SOURCE_ADAPTER_PROVES_HISTORY_COMPLETENESS_IDENTITY_AND_CHRONOLOGY`.

This prevents a caller from treating "we can calculate the formula" as "the live
feature is now approved for the successor".

## Determinism and evidence lineage

The constructor:

- rebuilds frozen dataclass inputs before use;
- canonicalizes eligible history independently of caller ordering;
- produces a canonical history-prefix SHA-256;
- records supplied and eligible history counts;
- records exact direct form/fatigue fixture lineage;
- records the history-prefix identity for Elo;
- uses compact sorted UTF-8 JSON with one final newline;
- rejects NaN/infinity through the canonical serializer;
- provides full candidate reconstruction/revalidation.

The tests also cross-check the five synthetic PR #80 values against PR #69's
historical replay on the exact same match sequence. This is intended to detect
drift in the form, Elo, or fatigue mathematics.

## Safety

PR #80 creates no expected goals, score matrix, probability, calibration,
price, market activation, selection, or bet.

All downstream authorization remains exact `false`, including:

- source-history adapter approval;
- source-history completeness proof;
- successor live-input qualification;
- successor candidate approval;
- expected-goals transform approval;
- expected-goals production use;
- score matrix;
- probability inference and adjustment;
- calibration for production;
- pricing;
- market activation;
- selection;
- production approval;
- betting.

## Next boundary

The next required boundary is frozen as:

`BUILD_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_PROOF`.

That boundary must identify a real reviewed source path capable of producing the
PR #80 normalized result-history contract and prove, rather than assume:

- result finality;
- team identity continuity;
- complete history coverage through target `as_of`;
- chronology;
- source-local/UTC linkage;
- the Elo initialization/corpus boundary.

Only after that source-specific proof may ATHENA reconsider whether the five
constructed values satisfy PR #78 exact semantic equivalence. Even then,
expected-goals execution and production authorization remain separately reviewed
boundaries.
