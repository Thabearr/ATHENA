# Win Either Half prospective capture campaign (Stage 5B3)

Stage 5B3 creates the immutable schedule needed to collect genuine prospective
Win Either Half pricing-availability evidence under the merged Stage 5B2
contract.

It is adapter-neutral and campaign-target-specific. It does not fetch a fixture,
open a bookmaker, collect a price, qualify a provider, select a decision offset,
calculate value, enable a market, or issue a bet. It only creates deterministic
observation tasks.

## Why this stage is next

Stage 5B1 defines what evidence a pricing source must prove. Stage 5B2 defines
how completed observation attempts and exact YES/NO quote snapshots are
validated. Stage 5B2 also states that at least 100 fixtures are required before
prospective availability evidence is interpreted.

A decision offset cannot be frozen before genuine prospective observations
exist. The next safe engineering step is therefore to predeclare the campaign
schedule before those observations are collected. This prevents later
backfilling, selective omission, or changing the six offsets after seeing the
data.

## Inputs

The planner accepts local files only:

1. a Stage 5B1 source-qualification report whose nested
   `qualification.prospective_replay_status` is either
   `QUALIFIED_FOR_HISTORICAL_RESEARCH` or
   `QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY`;
2. a Stage 5B2-compatible fixture catalog containing only schema version,
   fixture identifier, and timezone-aware kickoff;
3. the committed Stage 5B2 prospective replay protocol;
4. the committed Stage 5B3 capture-campaign protocol; and
5. an explicit UTC `anchor_at` timestamp supplied by the operator.

Protocol inputs are accepted only when their bytes exactly match the committed
repository protocols. No current wall-clock time is read.

## Campaign target freezing

One campaign freezes:
- `provider_identifier`;
- `source`;
- `bookmaker_identifier`; and
- `capture_method`.

These values are copied into every task and cannot be changed after observing
availability.

## Frozen schedule

Each fixture produces exactly twelve tasks:

- two canonical markets:
  - `HOME_WIN_EITHER_HALF`
  - `AWAY_WIN_EITHER_HALF`
- multiplied by six offsets before kickoff:
  - 86400 seconds - 24 hours
  - 21600 seconds - 6 hours
  - 10800 seconds - 3 hours
  - 3600 seconds - 1 hour
  - 1800 seconds - 30 minutes
  - 900 seconds - 15 minutes

For every task:

```text
scheduled_at = kickoff - offset_seconds_before_kickoff
capture_window_opens_at = scheduled_at - 300 seconds
capture_window_closes_at = scheduled_at + 300 seconds
```

The closing time remains strictly before kickoff. The campaign is rejected when
the frozen anchor is later than any fixture's first 24-hour capture-window
opening. This prevents a supposedly prospective campaign from beginning after
an expected check was already missed.

## Deterministic identity

The campaign identifier is derived from canonical JSON containing:

- provider identifier;
- eligible Stage 5B1 status;
- source qualification SHA-256;
- source, bookmaker identifier, and capture method;
- anchor timestamp;
- frozen offsets and attempt window;
- exact Stage 5B2 and Stage 5B3 protocol hashes; and
- the sorted fixture catalog.

Each task identifier is derived from the campaign identifier, fixture,
canonical market, offset, scheduled timestamp, source, bookmaker identifier, and
capture method. Reordering the fixture input cannot change the campaign
identifier, task identifiers, task order, summary, or manifest bytes.

## Commitment status

Stage 5B3 produces an `UNFROZEN_LOCAL_PLAN`. The operator-supplied anchor is
part of deterministic identity, but it is not trusted proof of when the file
was created. Therefore `prospective_claim_authorized` remains false. Before any
task may count as prospective evidence, a later reviewed commitment step must
track a small campaign commitment artifact before
`commitment_deadline_at`, which is the earliest capture-window opening.

## Outputs and repository policy

One transactional ignored bundle contains:

- `capture-campaign-tasks-v1.jsonl`
- `capture-campaign-summary-v1.json`
- `capture-campaign-manifest-v1.json`

Repository output policy:
- default ignored root inside repository: `.cache/athena-research/win-either-half/capture-campaign`;
- output outside the repository is allowed for temporary/test usage;
- other locations inside the repository are rejected;
- symlinked outputs and symlinked parent directory components are forbidden.

Successful generation requires staged-file, installed-file, and output-directory
fsync. Any durability failure fails closed; an incomplete rollback is reported
explicitly rather than being described as restored.

The task file is the immutable schedule. It contains no odds and no completed
attempt result. A permitted manual workflow or future reviewed provider adapter
may later use the task identifiers when creating Stage 5B2 attempt and quote
inputs. Stage 5B2 remains the authority that decides whether those completed
records are `AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`, or `INVALID`.

The summary records fixture and task counts, earliest and latest campaign
bounds, source status, commitment status, deadline, the 100-fixture
interpretation minimum, and whether the campaign is large enough for later
interpretation.

The manifest records all input and output hashes, the generator Git revision,
registry snapshots, target object, commitment object, deterministic identity
rules, and complete safety state.

## Generate a campaign

The first 24-hour capture window for every fixture must be at or after the
chosen anchor.

```bash
python -m scripts.manage_win_either_half_capture_campaign \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/future-fixtures.json \
  --source ODDS_PORTAL \
  --bookmaker-identifier PINNACLE \
  --capture-method MANUAL_REVIEW \
  --anchor-at 2026-08-10T00:00:00Z \
  --manifest-output \
    .cache/athena-research/win-either-half/capture-campaign/capture-campaign-manifest-v1.json
```

These flag values are examples only, not production endorsements. Existing output
is not replaced unless `--force` is supplied.

## Verify an existing campaign

```bash
python -m scripts.manage_win_either_half_capture_campaign \
  --source-qualification path/to/source-qualification.json \
  --fixtures path/to/future-fixtures.json \
  --source ODDS_PORTAL \
  --bookmaker-identifier PINNACLE \
  --capture-method MANUAL_REVIEW \
  --anchor-at 2026-08-10T00:00:00Z \
  --check \
    .cache/athena-research/win-either-half/capture-campaign/capture-campaign-manifest-v1.json
```

Verification is byte-for-byte and fails closed on source report, target, fixture,
protocol, Git-state, registry, task, summary, or manifest drift.

## Interpretation boundary

A campaign with fewer than 100 fixtures can be used only as a pilot. It is
recorded as `interpretation_eligible: false`. Crossing 100 fixtures makes the
schedule large enough for later interpretation; it does not qualify a provider,
select an offset, enable a market, or authorize production.

After genuine observations are completed, they are evaluated by Stage 5B2. A
later separately reviewed stage may assess offset readiness using only
operational availability, completeness, and freshness evidence. Match outcomes,
model performance, odds profitability, edge, expected value, Kelly, and stake
results remain forbidden from that decision.

## Safety boundary

Stage 5B3 performs no network request, scraping, browser automation, credential
use, bookmaker login, odds collection, betslip construction, booking-code
generation, model probability, fair-odds calculation, edge, expected value,
Kelly, staking, accumulator selection, or `BET` decision.

Both Win Either Half markets remain `DISABLED`. `selected_offset_seconds`
remains null, `selection_authorized` remains false, and no production approval
is granted.
