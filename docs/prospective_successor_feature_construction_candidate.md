# Prospective successor feature construction candidate

## Purpose

PR #80 is the first boundary after PR #79's fail-closed live-input semantic
qualification result.

PR #79 proved that ATHENA's reviewed FotMob -> Fixture Intelligence -> PR31
chain preserves finite source scalars and their evidence ancestry, but does not
prove that `home_elo`, `away_elo`, `home_form`, `away_form`, and `fatigue`
were mathematically constructed the same way as the historical inputs used to
fit the reviewed successor expected-goals candidate.

PR #80 does **not** loosen that conclusion. Instead, it provides a pure
deterministic constructor that can create those five raw successor inputs from
explicit source-scoped prior final-result evidence using the exact mathematics
frozen by PR #78.

The intended path is now:

```text
reviewed source history adapter + completeness proof       <-- later boundary
    -> exact PR80 prospective feature construction
    -> semantic qualification against frozen successor inputs
    -> later successor expected-goals shadow inference
    -> later calibration / score-matrix / probability work
    -> later exact pricing and decision gates
```

This PR stops at the pure construction boundary.

## Exact ancestry

The constructor binds the exact upstream reviewed artifacts:

- repository main after PR #79:
  `d118fa702856d267bb6dc49301ebaee2a50dd533`;
- PR #78 canonical semantic protocol SHA-256:
  `97a47d431ce57468598b17fcb24e9e0e9a41fa26c80ff1f4df9e2e611107ed7c`;
- PR #78 canonical protocol size: `4,904` bytes;
- PR #79 canonical semantic assessment SHA-256:
  `aea27d67b93bf777a01c4956757ba7b31c521e9eea71006d20ca5bd4acf791f4`;
- PR #79 canonical assessment size: `6,204` bytes.

The PR #80 construction specification itself is canonical sorted compact UTF-8
JSON with a final newline:

- SHA-256:
  `75fe157d1b767cf374e5c2a27cc3d96434aa12f2214fc37d7c91b1e7127eb4b7`;
- size: `2,330` bytes.

The builder revalidates the exact PR #78 and PR #79 canonical identities before
constructing a candidate.

## Input contract

The constructor accepts only explicit caller-supplied immutable evidence
objects. It performs no acquisition.

Each prior result row carries:

- one source namespace;
- exact source fixture identifier;
- naive source-local kickoff;
- exact UTC kickoff;
- source-scoped home and away team identifiers;
- explicit final home and away goals;
- UTC observation time for the final-result evidence;
- evidence SHA-256;
- evidence reference.

The target fixture carries the same source namespace and source-scoped identity
basis, local and UTC kickoff, a strictly pre-kickoff `as_of`, and target
evidence ancestry.

The source namespace must match across the target and every supplied history
row. Cross-source team or fixture identity is not inferred.

## Historical mathematics reproduced exactly

### Form

For each target team:

1. use only strictly prior eligible fixtures;
2. order most recent first;
3. take at most five;
4. score win = 3, draw = 1, loss = 0;
5. compute:

```text
round(0.10 + ((points / (n * 3)) * 0.85), 3)
```

No prior fixture means `MISSING_PRIOR_HISTORY`. There is no `0.50` or other
default.

### Fatigue

Use the most recent strictly prior fixture for each target team.

```text
difference =
    (target_local_kickoff - home_last_local_kickoff).days
    -
    (target_local_kickoff - away_last_local_kickoff).days
```

Then:

```text
0.30 if difference < -2
0.10 if difference < 0
0.00 otherwise
```

If either target team lacks prior history, fatigue is
`MISSING_PRIOR_HISTORY`. There is no default.

### Elo

Replay every eligible supplied result chronologically using the frozen PR #78 /
PR #69 semantics:

- overall rating starts at `1500`;
- `1500` is an explicit replay initial-state assumption, not observed evidence;
- home expected score applies `+50` home advantage;
- away expected score uses no home boost;
- logistic divisor is `400`;
- observed score is win `1.0`, draw `0.5`, loss `0.0`;
- K = `32` before 20 matches;
- K = `24` from 20 through 49;
- K = `16` from 50 onward;
- update is `int(old + K * (actual - expected))`;
- target Elo is the current overall rating before the target fixture.

An unseen target team may therefore have Elo `1500` with status
`CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION`. That is not presented as
observed source evidence.

## Temporal and observation-time safety

PR #80 is stricter than simply sorting rows.

For every supplied history row, source-local and UTC chronology relative to the
target must agree. For the eligible prior prefix, the complete local ordering
and UTC ordering must also agree exactly.

The constructor fails closed when:

- a duplicate source fixture identifier exists;
- the target fixture appears in result history;
- source namespaces differ;
- local and UTC chronology disagree;
- one source-scoped team appears in multiple supplied fixtures at the same
  source-local or UTC kickoff;
- a target team has another supplied fixture at the target kickoff;
- a supplied prior fixture's final result was not yet observed by the target
  `as_of`.

The last rule matters. A known prior fixture whose final result was unavailable
at the analysis time is not silently dropped from Elo/form/fatigue state.

Rows genuinely after the target are ignored by construction, but remain visible
in `supplied_history_count`.

## Determinism and lineage

The eligible prefix is sorted deterministically and canonicalized with its
source-local time basis and Elo initialization semantics. The candidate records
its exact prefix byte size and SHA-256.

Each feature records the fixture identifiers and evidence SHA-256 values used
for its derivation:

- form records the relevant recent-five rows;
- fatigue records the latest rows for the two target teams;
- Elo records the complete eligible replay prefix when the target team has
  participated in that history;
- an assumption-only `1500` Elo claims no result-evidence lineage.

Multiple fixtures may legitimately share the same capture/evidence SHA-256; the
parallel fixture/hash lineage therefore preserves duplicate evidence hashes
rather than pretending they are distinct captures.

Revalidation rebuilds the candidate from the original history and target and
requires exact canonical bytes. Mutated history, target, candidate, or
non-canonical bytes fail closed.

## What this PR proves

PR #80 proves that ATHENA can deterministically construct the five raw successor
inputs with the exact historical mathematics **if** it is supplied an adequate
source-scoped prior-result history.

The synthetic parity test builds the same small history through the PR #69
historical replay and the PR #80 prospective constructor and requires exact
equality for:

- `home_elo`;
- `away_elo`;
- `home_form`;
- `away_form`;
- `fatigue`.

This is a mathematical-construction proof, not a live-source qualification.

## What this PR deliberately does not prove

The central caveat remains:

```text
UNPROVEN_UNTIL_REVIEWED_SOURCE_ADAPTER_PROVES_HISTORY_COMPLETENESS_IDENTITY_AND_CHRONOLOGY
```

A caller could provide an incomplete history. PR #80 has no independent source
adapter and cannot know whether an omitted past fixture exists.

Therefore:

- `all_five_exact_semantic_equivalence` is always `false`;
- source-history adapter approval is `false`;
- source-history completeness proof is `false`;
- successor live-input qualification is `false`.

PR #80 does not use the opaque provider-supplied PR31 form/Elo/fatigue scalars
that PR #79 found insufficiently proven.

## Prohibited behavior

This boundary does not:

- make network requests;
- scrape or browse;
- call FotMob or SportyBet;
- read a database;
- write a database;
- create fixture intelligence;
- call PR31's provider-scalar handoff;
- execute the successor expected-goals model;
- call `ScoreMatrix`;
- calculate market probabilities;
- calibrate production probabilities;
- acquire bookmaker odds;
- calculate edge, EV, Kelly, or stake;
- activate a market;
- select a bet or accumulator;
- authorize `BET`.

The module imports only the reviewed PR #78/#79 semantic artifacts needed for
ancestry verification plus Python standard-library code.

## Safety contract

Every downstream authorization remains exact boolean `false`, including:

- source-history adapter approval;
- source-history completeness proof;
- successor live-input qualification;
- successor candidate approval;
- expected-goals transform approval;
- expected-goals production use;
- score matrix;
- probability inference and adjustment;
- production calibration;
- pricing;
- market activation;
- selection;
- production approval;
- betting.

Constructing all five numeric values is therefore **not** production approval.

## Next boundary

The next required boundary is:

```text
BUILD_REVIEWED_SOURCE_HISTORY_ADAPTER_AND_COMPLETENESS_PROOF
```

That work must determine which reviewed prospective source can supply the
required prior final-result history, preserve source-scoped fixture/team
identity, prove chronology and observation-time semantics, and establish a
defensible completeness rule before PR #80 output can be promoted to exact
successor input equivalence.

No source should be accepted merely because its numbers happen to match a
sample calculation.
