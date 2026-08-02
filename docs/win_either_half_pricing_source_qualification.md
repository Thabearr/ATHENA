# Win Either Half pricing-source qualification

Stage 5B1 defines a deterministic protocol for deciding whether supplied
evidence can support a pricing-source role. It performs no network request and
does not qualify a provider by reputation, popularity, or a weighted score.
Every mandatory gate must have an effective `PASS`; `UNKNOWN` and
`NOT_APPLICABLE` never satisfy mandatory gates.

Win Either Half is ATHENA's first end-to-end evidence, modelling, calibration,
and pricing pipeline. It is not ATHENA's only market. The canonical registry
continues to include Match Result, Asian Handicap, Total Goals,
result-or-over markets, Double Chance, BTTS, Draw No Bet, Win to Nil, 1UP, and
2UP. Stage 5B1 changes none of their statuses.

## Independent source roles

The protocol evaluates three roles independently:

- `HISTORICAL_RESEARCH_SOURCE` supplies archived or replayable bookmaker
  prices for research.
- `LIVE_PRICING_SOURCE` supplies genuine, current pre-decision prices.
- `EXECUTION_BOOKMAKER` identifies and constructs the exact final selection,
  detects price or availability changes, and may support a booking code.

One provider need not fill all three roles. Historical and live evidence can
come from different licensed providers, and an execution bookmaker can remain
unqualified for historical research. Live odds are required for pricing and
value decisions, not for basic probability-model training. This PR does not
calculate value.

Statuses are `QUALIFIED_FOR_HISTORICAL_RESEARCH`,
`QUALIFIED_FOR_LIVE_PRICING`, `QUALIFIED_AS_EXECUTION_BOOKMAKER`,
`QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY`, `PARTIALLY_QUALIFIED`,
`DISQUALIFIED`, and `UNKNOWN`. `UNKNOWN` never passes a mandatory gate.

## Exact market semantics

Only the canonical `HOME_WIN_EITHER_HALF` and `AWAY_WIN_EITHER_HALF` markets
are in scope. Each has the exact `YES` and `NO` outcomes and a null line.
Home `YES` means the home team wins at least one regulation half; Away `YES`
means the away team wins at least one regulation half. `NO` means the named
team does not win either regulation half.

First-half winner, second-half winner, win both halves, score in either half,
half-time/full-time, full-time result, Double Chance, Draw No Bet, bet-builder
approximations, and model-derived prices are not substitutions. Fuzzy market
matching cannot qualify a source.

Provider market names and labels may be localized and need not equal ATHENA's
English display names. Qualification instead requires non-empty provider
market/selection identifiers and descriptions, the exact canonical subject and
settlement semantics, exact YES/NO mapping, and a null line.

Evidence is market-specific. Exactly one quote mapping, snapshot sample,
historical record, and live-capability record is required independently for
each canonical market. A Home mapping or snapshot cannot prove Away support,
and selection identifiers cannot be borrowed across the two subjects. Shared
provider market identifiers fail unless reviewed evidence explicitly proves
that the identifier represents both canonical subjects.

## Mandatory evidence gates

Historical research requires exact semantics and YES/NO structure, raw decimal
odds, bookmaker provenance, provider quote/update timestamps, a common
bookmaker snapshot, exact fixture mapping, reproducible export, retained
settled history, all 36,318 frozen fixture-markets, and permission to retain
research evidence. Current-only or short-retention evidence cannot qualify for
history. It can qualify for prospective replay only when every prospective
gate passes.

Frozen historical coverage is reconciled both by market and evaluation role.
Home and Away each require 10,635 `CALIBRATION_FIT_OOF`, 3,476
`VALIDATION_SELECTION`, and 4,048 `FINAL_TEST` fixture-markets, totaling 18,159
per market. The combined totals remain 21,270 / 6,952 / 8,096 and 36,318.
Boolean full-coverage claims are not accepted.

Live pricing additionally requires current availability, deterministic latest
snapshot selection, reproducible provider mapping, and enforceable 900-second
freshness. Download timestamps are not quote timestamps. Best-price,
consensus, averaged, model-probability, or value-flag feeds cannot prove a
single bookmaker market.

Execution qualification is separate. It requires exact fixture, market, and
outcome selection; deterministic betslip construction; confirmation that the
execution price matches the validated quote; suspended, changed-odds, and
missing-market detection; explicit user confirmation; and a permitted
automation method. Booking-code support is recorded where provided, but this
PR generates no booking code and places no bet.
Booking-code capability is an optional gate: an execution bookmaker can
qualify while explicitly reporting it unavailable. No other mandatory gate may
use `NOT_APPLICABLE`.

## Snapshot and fixture rules

A snapshot contains one fixture, canonical market, bookmaker, snapshot ID,
common `observed_at`, `YES`, and `NO`. Different bookmakers, snapshots, or
update timestamps are never combined. When a native snapshot ID is unavailable,
the only permitted deterministic derivation uses provider, fixture, market,
bookmaker, and the exact common update timestamp.

Fixture mapping records provider event and competition identifiers, season
where available, kickoff, home and away participant identifiers and names,
neutral venue where available, and status. Results are `EXACT`, `CONFLICT`,
`AMBIGUOUS`, or `UNAVAILABLE`. Reversed participants fail. Kickoff differences
beyond 300 seconds fail. Fuzzy team names cannot independently qualify a
fixture; reviewed aliases are future work.

## Decision protocol

The tracked protocol prepares a decision contract with an ID, seconds before
kickoff, maximum quote age, snapshot-selection rule, UTC, postponed and
rescheduled handling, kickoff correction, abandoned/cancelled handling, frozen
timestamp, and revision. `seconds_before_kickoff`, `frozen_timestamp`, and
`frozen_revision` remain null because Stage 5B1 does not choose or freeze the
offset. A later decision must use operational availability evidence, never
match outcomes, model performance, pricing profitability, or FINAL_TEST.

FINAL_TEST season 2025-26 has already been consumed. Provider selection cannot
turn it into a pristine holdout; prospective validation remains mandatory.

## Candidate treatment

SportyBet is the priority execution candidate. Provisional evidence indicates
that it displays Home and Away Team to Win Either Half, explicit YES/NO decimal
prices, and SportyBet provenance. Stable provider IDs, quote timestamps,
snapshots, archives, permissions, automated betslip construction, and booking
codes remain unproven. The rules-only template therefore records every actual
SportyBet role status as `UNKNOWN`. A later local report may become partially
qualified only after verified structured evidence is supplied.

Sportmonks, The Odds API, and other licensed historical providers are protocol
candidates that begin `UNKNOWN`. No provider is qualified by this tooling PR.
No scraper, protected endpoint, login automation, account credential, browser
adapter, betslip, or booking-code mechanism is implemented. Any future
SportyBet Stage 7 adapter must use an official or permitted interface or a
local user-controlled browser workflow.

## Offline evidence lifecycle

Candidate evidence is JSON with schema version, provider identity, candidate
roles, checked time, all named evidence sections, gate evidence, limitations,
typed evidence claims, and evidence files. Evidence files must be regular files
below the allowed evidence root and are verified by relative path, byte size,
and SHA-256. Absolute paths, traversal, escaping symlinks, and identity mismatch
fail closed. A verified file identity proves only which bytes were reviewed; it
does not prove a capability.

Every typed claim has a unique ID, matching provider, verified file path,
document title, source reference, capability identifier, bounded paraphrased
statement, timezone-aware retrieval and review timestamps, and reviewer
conclusion. Gate declarations and structured sections reference claim IDs.
Capability allowlists prevent, for example, a market-semantics claim from
proving research permission or a booking-code claim from proving historical
retention. One physical file may support several separately typed claims, but
generic file text with no claims cannot pass a gate. Missing claims remain
`UNKNOWN`; contradictory or capability-mismatched claims produce `FAIL`.

Reviewer-declared gate status is never authoritative by itself. The exporter
derives each gate from its structured market, quote, timestamp, snapshot,
fixture, historical, live, licensing, export, or execution evidence. Reports
preserve declared, derived, and effective status separately. A derived pass
also requires valid typed claims for both the declaration and structured
evidence. Structured `FAIL` has first precedence, reviewer `FAIL` second, and
`UNKNOWN` remains unknown only when neither side fails. A `PASS` requires both
sides to pass. Mandatory `NOT_APPLICABLE` fails. Optional booking-code
`NOT_APPLICABLE` is accepted only when both reviewer and structured evidence
explicitly record that capability as unavailable; it cannot hide a conflict.
Missing documentation stays `UNKNOWN`; supplied contradictions become `FAIL`.

The supplied protocol must be semantically identical to the committed protocol.
Before qualification, its gate lists, statuses, market semantics, fixture
tolerance, snapshot rules, two-market evidence requirements, claim-capability
allowlists, 900-second maximum age, decision contract, per-market and combined
frozen denominators, holdout governance, and no-production flag are checked
against the applied domain rules. The report records the supplied protocol's
raw byte size and SHA-256 and uses its validated decision contract.

Example:

```powershell
python -m scripts.qualify_win_either_half_pricing_source `
  --input path/to/candidate-capabilities.json `
  --evidence-root path/to/reviewed-evidence `
  --output .cache/athena-research/win-either-half/pricing-source-qualification-v1.json
```

The local report is ignored. It contains independent role statuses,
prospective status, every gate, reasons, evidence identities, unsupported and
unknown capabilities, the complete market registry/status snapshot, consumed
holdout governance, and a no-production-approval statement. Generation requires
a clean tracked worktree and writes deterministic UTF-8/LF bytes atomically.

Stage 5B1 fetches no odds, uses no credentials, and adds no edge, expected
value, Kelly, profitability, stake, ACCA, betslip, booking-code, or `BET`
decision. Both Win Either Half markets remain `DISABLED`.
