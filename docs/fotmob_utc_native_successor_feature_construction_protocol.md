# FotMob UTC-Native Successor Feature Construction Protocol

## Purpose

This PR pre-registers a **new source-native successor feature path** for ATHENA using the already-qualified FotMob historical corpus and canonical `status.utcTime` directly.

It is deliberately independent of the unresolved PR69/PR80 source-local equivalence lineage. It does **not** resolve PR69, does not claim PR80 parity, and does not reinterpret UTC as a source-local naive clock.

Protocol state:

`PRE_REGISTERED_NOT_EXECUTED_FOTMOB_UTC_NATIVE_FEATURE_CONSTRUCTION_UNQUALIFIED`

Next boundary:

`EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_SUCCESSOR_FEATURE_CONSTRUCTION_QUALIFICATION`

## Why this exists

PR119 already qualified and materialized an exact bounded FotMob historical corpus:

- 21,326 ordinary regulation-time finished fixtures;
- canonical kickoff UTC from `status.utcTime`;
- earliest admitted kickoff `2020-08-01T11:30:00Z`;
- latest admitted kickoff `2026-08-14T19:15:00Z`;
- exact eleven currently validated historical/model families;
- global FotMob historical coverage still `UNKNOWN`;
- no PR80/model/pricing/BET authority.

The old PR80 bridge converts canonical UTC through `Europe/Oslo` and then makes that value naive solely to study parity with the older PR69 source-local construction. That equivalence remains unresolved.

The successor product does not need to inherit that ambiguity. FotMob already exposes an unambiguous timezone-aware UTC coordinate. A new successor can train and operate on that coordinate directly, provided the new semantics are reviewed and validated as their own lineage.

## Exact evidence lineage

This protocol is anchored to current `main`:

`4a2ca10af4b14194253ba6fc84bca780e2b03d58`

It revalidates:

- PR119 qualification receipt SHA-256 `da8037cd9b4a4f91be942a4052e76134b66cc94221ed66e624c14008c9e562a0` / `6,810` bytes;
- PR119 receipt blob `870f661501e2a8bb9ca1bfee64a2f1a44319da70`;
- PR119 qualification module blob `f0d17dbcd70fc8b5432b50061525224642541c05`;
- preserved FotMob campaign artifact `9249856559`, SHA-256 `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`, size `61,886,753` bytes;
- PR119 materialization projection SHA-256 `e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2` / `10,545,099` bytes;
- PR80 constructor implementation blob `9135f056d036fd0207a3daead2599ac2520274be` as a mathematics reference only.

The PR119 materialized `source_local_kickoff` projection is **not** used as the new chronology coordinate. A later execution must go back through the preserved qualified raw lineage and re-derive aware UTC from exact `status.utcTime`.

## Frozen historical scope

The first UTC-native research corpus remains exactly the current eleven qualified historical/model families and the exact 21,326 PR119 rows through 14 August 2026.

That is not a permanent product whitelist. Cups, UEFA competitions, internationals and additional domestic leagues remain part of ATHENA's wider competition architecture; they require their own reviewed historical/prospective evidence coverage before joining this particular model-training corpus.

Rows after `2026-08-14` require a separately reviewed contiguous extension. No current protocol may silently treat later dates as historically complete.

## UTC chronology contract

The sole historical chronology coordinate is:

`status.utcTime` → timezone-aware UTC datetime.

Forbidden:

- conversion to `Europe/Oslo` or another local timezone;
- use of the FotMob display `time` field as chronology;
- dropping timezone information;
- storing naive UTC while calling it source-local time;
- claiming this representation is PR69/PR80-equivalent.

Strict prior means:

`history_kickoff_utc < target_kickoff_utc`

Fixtures with exactly the same UTC kickoff form one batch. Every fixture in the batch receives features from the state that existed before the batch; results from the batch are applied only after all batch features have been constructed. Fixture ID may provide deterministic output ordering, but cannot make a simultaneous result become prior evidence for another fixture.

## Feature mathematics

The new implementation may reuse the already-reviewed mathematical ideas, but the output is a new UTC-native feature lineage.

### Form

For each side:

- use up to the last five strictly prior ordinary-FT fixtures for the same source-scoped team;
- win = 3 points, draw = 1, loss = 0;
- `round(0.10 + ((points / (n * 3)) * 0.85), 3)`;
- no prior history → `MISSING`;
- no 0.50 or other default.

### Elo

The source-native research replay begins unseen teams at 1500. This is explicitly an **assumption**, not observed evidence.

- home expected-score adjustment: +50;
- standard divisor: 400;
- win/draw/loss scores: 1 / 0.5 / 0;
- K = 32 for fewer than 20 matches, 24 for fewer than 50, otherwise 16;
- update with `int(old + K * (score - expected))`;
- no seasonal reset;
- simultaneous fixtures update only after the whole kickoff batch is evaluated.

Because this is a new source-native model lineage, this initialization is not presented as PR69 numerical parity. The later model-validation boundary must judge the resulting feature/model performance on its own evidence.

### Fatigue

For each team, use the most recent strictly prior UTC kickoff.

- home rest = `(target_utc - home_last_prior_utc).days`;
- away rest = `(target_utc - away_last_prior_utc).days`;
- differential = home rest − away rest;
- fatigue = 0.30 when differential < −2, 0.10 when < 0, otherwise 0.0;
- if either required prior fixture is unavailable, fatigue is `MISSING`;
- no timezone conversion before subtraction.

### Historical live-data freshness

Historical `live_data_freshness` remains:

`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE`

It receives no numeric default and is excluded from the historical training feature set. Prospective freshness remains a separate live evidence/gating concern and must be qualified later.

## Qualification execution requirements

A later execution must:

1. revalidate the exact PR119 receipt, artifact and raw lineage;
2. admit exactly the reviewed ordinary-FT rows;
3. re-derive every kickoff from preserved raw `status.utcTime`;
4. verify fixture/team/result identity against PR119;
5. construct UTC-native form/Elo/fatigue with the frozen chronology rules;
6. report AVAILABLE/MISSING/BLOCKED counts for every feature;
7. report same-kickoff group accounting and any identity/lineage conflict;
8. emit a deterministic hash-sealed feature projection.

That execution stops at feature materialization. It cannot fit or tune expected goals, calculate market probabilities, inspect SportyBet, or make a betting decision.

## Safety / authority

All downstream authority remains false:

- successor approval;
- model training;
- expected-goals approval/production;
- score-matrix or probability inference/adjustment;
- production calibration;
- pricing / market activation / selection;
- production approval / BET;
- successor live-input qualification.

## Canonical protocol

SHA-256:

`948b34e5f5ca6d69895beed0b0cdb79368bc507015f45975f2b3192b619975db`

Canonical size:

`5,803` bytes.
