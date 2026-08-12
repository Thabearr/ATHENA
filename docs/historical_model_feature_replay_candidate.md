# Historical model-feature replay candidate

PR #69 is an offline, research-only historical replay boundary. It turns
preserved football-data.co.uk CSV bytes into a deterministic corpus of
pre-kickoff feature candidates for later study of PR #68's legacy expected
goals transform candidate. It does not validate that transform, run a score
matrix, calculate probabilities, read SQLite, or authorize production use.

## Evidence and identity

The corpus accepts immutable source CSV bytes and records each source file's
season, league, SHA-256, byte size, and parsed row count. Its fixture and team
identity functions intentionally mirror the current football-data.co.uk
importer:

- fixture identity is a SHA-256 of the source, season, league, ISO date, raw
  time, and case-folded home/away names;
- team identity is a SHA-256 of the source, literal `team`, and a case-folded
  name.

These identities are **source-scoped**. They do not establish that a team is
the same as a FotMob, football-data.org, API-Football, SportyBet, or canonical
ATHENA team. No fuzzy aliases, SQLite team state, or `team_merger` behavior is
used.

CSV parsing follows the importer’s accepted encodings, required columns, date
formats, clock formats, score validation, and identity input semantics. A
malformed row, missing required column, duplicate source fixture identity, or
conflicting identity fails closed. The historical result is retained as a
future outcome only; it never contributes to that fixture's own replayed
features.

## Time boundary

football-data.co.uk cache timestamps are retained as naive source-local clock
times with `SOURCE_LOCAL_TIMEZONE_UNRESOLVED`. The corpus does not invent UTC
offsets. A source row with no clock time is marked `MISSING_SOURCE_TIME` and
is temporally blocked. A same-source-team, same-local-kickoff collision is
also blocked. Only strictly earlier source-local fixtures can become form,
fatigue, or Elo history.

Therefore this corpus is not a claim of globally normalized football
chronology. It is a bounded replay under mechanically safe source-local
ordering.

## Replayed features

`home_form` and `away_form` reproduce the current `TeamFormService` math for
strictly prior fixtures only: latest five results, W=3/D=1/L=0,
`0.10 + points/(n*3)*0.85`, rounded to three decimals. Unlike the legacy
service, no prior history is **not** substituted with `0.50`; it is
`MISSING_PRIOR_HISTORY` with no value.

`home_elo` and `away_elo` are labelled `DERIVED_HISTORICAL_ELO_REPLAY`, not
observed evidence. The replay freezes the current `EloEngine` procedure:
initial model state 1500, home expected-score boost +50, base-10 denominator
400, K=32 below 20 matches / 24 below 50 / 16 otherwise, 1/0.5/0 results, and
integer conversion after updates. Pre-Elo is captured before a fixture result
updates state for later fixtures. Initial 1500 is explicitly a replay-model
initial-state assumption, never a stored historical observation.

`fatigue` uses each team's strictly earlier source-local fixture date. It
reproduces the legacy modifier only when both dates exist: rest-day difference
below -2 is `0.30`, below 0 is `0.10`, otherwise `0.0`. No prior date is
`MISSING_PRIOR_HISTORY`, never a substituted `0.0`. Its equivalence to the
generic PR31 fatigue semantics remains explicitly `UNPROVEN`.

`live_data_freshness` is always
`NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE` and has no value. The corpus does
not derive freshness from source labels, cache age, filesystem metadata,
download time, season, or the current date.

## Counterfactual component eligibility

The corpus has two descriptive flags, neither of which assigns a historical
freshness regime:

- `form_path_component_eligible` requires available home form, away form, and
  fatigue;
- `elo_fallback_component_eligible` requires available home Elo, away Elo,
  and fatigue.

They state only that enough strict pre-kickoff source evidence exists to study
that branch counterfactually later. They never claim
`historical_regime=FORM` or `historical_regime=ELO_FALLBACK`. Exact
six-feature replay is always zero because retained historical freshness is
unavailable.

## PR #68 linkage and safety

The corpus anchors the exact PR #68 transform ID and canonical transform
specification SHA-256, but never calls PR #68's live reviewed-chain builder.
Historical research and the PR52→PR68 FotMob chain remain separate.

Every safety value is exact `false`, including historical replay approval,
transform approval, score-matrix/probability execution, pricing, selection,
and betting. A replay candidate is evidence for later research design, not
approval of the legacy heuristic.
