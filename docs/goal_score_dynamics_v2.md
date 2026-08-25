# Goal/Score Dynamics v2

## Status

This live Expansion PR #233 defines an offline, research-only challenger and
rolling-origin evaluation boundary. It starts from main
`06c3df0b040e7314e6361cdd2d7732cf27a7e38c`. The infrastructure hotfix shifted
the dated roadmap: live #232 is Richness/Coverage + Market Labels, live #233 is
Goal/Score Dynamics v2, and forward-chaining calibration follows as #234.

The implementation is additive. It must not modify the frozen Historical As-Of
v1, Tactical Identity v1, #232 label, Fixture State v2, production score,
production probability, pricing, routing, selection, accumulator, WEH, 1UP, or
2UP boundaries.

## Architecture commitment

The canonical research question is the joint regulation-time distribution
`P(HomeGoals=h, AwayGoals=a)`. Historical As-Of and Tactical Identity provide
strictly pre-match inputs. The #232 corpus provides only the safe canonical
regulation-score target. Exact source files, row identities, registry identities,
and generation contracts are replayed before a compact training row can be
issued.

The feature/target firewall excludes target FT/HT/events/xG/shots, final lineup,
stored coach, referee, data quality, coverage richness, label availability,
bookmaker data, raw team identity, and manager identity from the model vector.
Unknown evidence remains MISSING or BLOCKED. Numeric filling is a fold-local
model transformation with separate status indicators, never recovered evidence.

Candidate families are independent Poisson GLMs, the same intensity model plus
the standard four-cell Dixon-Coles low-score correction, and deterministic
histogram-gradient-boosting Poisson intensity models. Every candidate produces
one normalized adaptive-tail score surface; market diagnostics are projections
of that shared surface rather than separately trained market probabilities.

Development uses expanding date-bucket rolling origins. The latest frozen 20%
of unique match dates form one terminal holdout and cannot influence model,
preprocessor, competition-prior, hyperparameter, or Dixon-Coles rho selection.
The primary score is mean exact-score negative log likelihood. Calibration
fitting is deferred to #234.

The current operational path is not claimed as a historical champion. Its Elo,
freshness, defaults, and fatigue inputs are not canonically replayable on this
corpus, so its status is `BLOCKED_NOT_CANONICALLY_REPLAYABLE` and no metric is
invented.

All production-facing authority remains false. A later experiment may identify
a `RESEARCH_CHALLENGER_WINNER`; that cannot replace the production model or
authorize calibration, pricing, routing, selection, accumulation, or BET.

The complete registry, mathematical, training-view, evaluation, safety, and
reproducibility details will be finalized with the implementation on this draft.
