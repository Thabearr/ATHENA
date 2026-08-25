# Tactical Identity Engine

Expansion Phase 3 adds a research-only, historical Tactical Identity layer. It
addresses the Getafe-class diagnostic without encoding Getafe, or any club, as
a style. The question is what environment the qualifying pre-match evidence
describes—not what a team is reputed to be.

## Source and leakage boundary

The primary source is the canonical Phase 2 historical as-of corpus. The exact
canonical warehouse is additionally opened read-only for source-issued prior
team-match projections and prior coach observations. Construction fails unless
the corpus metadata warehouse SHA-256 equals the SHA-256 calculated from the
warehouse bytes. Corpus payload hashes are replayed and target identity is
checked against the exact source-issued warehouse row. Caller-provided SHAs
have no authority.

`DATE_STRICT_PRIOR_FIXTURES_V1` is retained. For target date D, only completed
fixtures with `match_date < D` enter team profiles or competition baselines.
Same-date targets are built before date-D observations enter bulk rolling
state. The target's FT/HT/xG/shots, target coach row, later matches, and future
baseline population therefore cannot influence its profile.

Team identity remains
`COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1`. Exact display-name equality does
not join league, cup, UEFA, club, or international identities. Consequently,
schedule values are explicitly
`COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1`; they are not complete real-world club
congestion and must not be described as such.

## Registry and dimensions

Registry v1 is independently pinned to:

`c71f11e9f97fcc71bd38eb7a9fa558ebc09e5dfbc648e5991862dc75b80fcb69`

Every canonical profile has explicit `AVAILABLE`, `MISSING`, or `BLOCKED`
resolution for these dimensions:

- event environment;
- attacking production;
- defensive suppression (opponent-output suppression, not a claimed low block);
- shot profile;
- first-half environment;
- control/tempo proxies;
- scoring reliability;
- venue expression;
- opponent interaction;
- regime context;
- evidence uncertainty.

Continuous source components remain visible. xG, goals, shots, HT evidence,
rates, and possession are not silently substituted for one another. Missing
xG stays missing. Possession is only a proxy and does not prove control,
pressing, PPDA, field tilt, or tactical mechanism.

## Recency and shrinkage

`EXPONENTIAL_DATE_DECAY_60_DAY_HALF_LIFE_V1` weights a valid observation of
integer date age `a` days as:

`w(a) = 2 ** (-a / 60)`

The 60-day half-life is a versioned research choice, not football truth. Each
component retains raw sample count, valid/missing/blocked counts, dates,
projection identities, conflicts, and effective weighted sample size:

`ESS = (sum(w) ** 2) / sum(w ** 2)`

`EFFECTIVE_SAMPLE_EMPIRICAL_SHRINKAGE_K5_V1` uses:

`reliability = ESS / (ESS + 5)`

`shrunk = reliability * team_raw + (1 - reliability) * prior`

The competition prior is available only with at least 20 strictly-prior valid
projection observations. A descriptor component requires at least three team
observations. No team observation remains `MISSING`; the competition prior
alone never creates team evidence. If the prior is unavailable, raw evidence
is retained but shrinkage and relative descriptors remain unavailable.

## Competition baselines and descriptors

`DATE_STRICT_COMPETITION_BASELINE_V1` maintains deterministic online moments by
scope and competition. Bulk construction is date-batched: every target on D is
emitted before D enters the baseline. Filters select target output only and do
not narrow prior history.

For supported dimensions, component values are transformed to competition
relative z values after shrinkage and combined by the registry's explicit
orientation and arithmetic-mean rule. There is no hidden magic score.
Descriptors use `PRIOR_COMPETITION_Z_BANDS_HALF_SIGMA_V1`:

- score `<= -0.5`: LOW;
- score `>= +0.5`: HIGH;
- otherwise: MID.

The profile retains the continuous score, normal-distribution percentile,
component estimates, prior population size, shrinkage weight, and coverage.
The labels are descriptive research bands, not probabilities or selections.

## Home/away and interaction

Each side retains `OVERALL` history and the target-relevant `HOME_ONLY` or
`AWAY_ONLY` history. Venue delta is available only when both continuous
profiles are available; missing splits do not become zero delta.

Matchup interaction contains only statistical dimension differences (event
environment, attack versus suppression). It does not emit folklore labels such
as press-vs-build-up or low-block-vs-possession.

Opponent adjustment is governed by
`PRIOR_MATCH_OPPONENT_PREMATCH_RESIDUAL_V1`. The only authorized future
mechanism is a source-compatible join from a prior observation P to the
opponent's pre-P as-of state. Raw averages are never relabeled
opponent-adjusted. Phase 3 leaves the value `MISSING` with sample zero when this
exact safe join is unavailable; no target-date or post-P opponent state is
used.

## Manager regime and score state

`LAST_OBSERVED_PRIOR_EXACT_MANAGER_V1` reads exact coach strings only from
completed prior matches. It retains the last observed prior manager, observation
date, consecutive prior-regime sample, and observed transitions. There is no
fuzzy coach matching. Critically, `LAST_OBSERVED_PRIOR_MANAGER` is not
`CURRENT_MANAGER`: `current_manager_confirmed` is always false without separate
pre-match evidence, and the target's stored post-hoc coach never establishes
the target manager.

Score-state behavior is `FUTURE_EVIDENCE_REQUIRED_V1`. No duration estimate is
invented from FT/HT, and raw event rows are not aggregated. A later bounded
contract may use complete regulation-only `warehouse_events_preferred`
chronology.

## Canonical identity and bulk construction

Generation contract v1 is independently pinned to:

`73482eb97e8ad0acaa6690a72921117541cc6c97948e35a4ff49b481b738d701`

It binds registry identity, Phase 2 source contracts, DATE_STRICT/team identity,
recency, competition baseline, shrinkage, manager regime, opponent adjustment,
descriptor policy, and schema version. Same-version drift and unknown versions
fail closed. Snapshots freeze every source/registry/generation identity and
serialize without consulting future live registry objects.

`scripts/build_tactical_identity_corpus.py` writes a separate generated SQLite
corpus. It uses chronological date batches, bounded complete-date LAST_20 team
histories, online competition moments, batched writes, read-only sources, and
collision-safe atomic output. Generated databases stay outside Git. No network
or provider acquisition occurs.

## Scope and authority

Fixture State v2 tactical slots are not activated here. Historical training,
model inference, probability adjustment, calibration, pricing, routing,
selection, accumulator changes, production approval, and BET authority are all
explicitly false. No odds, bookmaker probabilities, or team-name rules enter
the registry.
