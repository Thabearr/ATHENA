# Historical expected-goals component validation

PR #70 is a retrospective, research-only statistical evidence boundary for the
legacy expected-goals transform frozen in PR #68. It consumes the exact PR #69
historical replay rebuilt from preserved football-data.co.uk source bytes and
asks a deliberately narrow question: do the FORM and ELO branches of the old
goal-rate heuristic contain useful predictive signal?

It does **not** reconstruct the historical `live_data_freshness` switch. That
evidence was not retained, so the two formula branches are evaluated as
counterfactual components rather than as claimed historical regimes.

## Exact ancestry

The builder requires the PR #69 source inputs, the PR #69 corpus object and its
canonical bytes. It calls the PR #69 full revalidator and then binds the exact
canonical PR #69 SHA-256/size, the raw source-corpus SHA-256, the PR #68
transform ID/specification SHA-256/size, and the frozen PR #70 validation
specification.

A naked fixture list, arbitrary feature mapping, changed coefficient, changed
benchmark, or detached validation artifact is not accepted.

## Frozen component formulas

`FORM_COMPONENT` is evaluated only on fixtures that PR #69 marks
`form_path_component_eligible`. It uses the exact replayed home form, away
form, and fatigue values.

`ELO_FALLBACK_COMPONENT` is evaluated only on fixtures that PR #69 marks
`elo_fallback_component_eligible`. It uses the exact replayed home/away Elo
values, the PR #68 Elo center/divisor and clamp, and the same fatigue value.

Both components then use the exact PR #68 home/away baselines, fatigue
coefficient, three-decimal rounding order and minimum-rate floor. The
production validation code reads the public frozen PR #68 specification; it
does not fit, tune, or optimize those constants.

The historical fixture result is used only as the later evaluation outcome. It
never changes that fixture's own replayed pre-match features or candidate rate.

## Scoring rule

The primary score is independent-Poisson joint negative log-likelihood. For
observed goals `y` and positive predicted rate `lambda`:

`NLL = lambda - y*log(lambda) + lgamma(y + 1)`

Home and away NLL are summed per fixture. The log-factorial term is retained so
stored scores are absolute Poisson NLL values. Lower is better.

For each component the artifact also records mean predicted and observed home
and away goals, bias, MAE, RMSE, and mean joint Poisson NLL.

## Benchmarks

Two immutable paired benchmarks are reported.

The fixed baseline uses the exact PR #68 constants: home `1.45`, away `1.25`.
Every component-eligible fixture is compared against this baseline on the same
sample.

The rolling league baseline is deliberately simple. For each exact PR #69
`identity_league`, it uses only source-local fixtures that are mechanically
proven to be earlier than the target to calculate historical mean home goals
and away goals. There is no smoothing or fallback. The baseline is unavailable
until at least one prior league fixture exists and both historical rates are
positive and finite.

Known-time fixtures sharing the same source-local kickoff are evaluated in a
batch before any outcome at that timestamp updates league state. Therefore
same-time fixtures cannot leak results into one another.

A missing source clock is handled conservatively without discarding its result
forever. If any fixture in a league/date has a missing clock, every rolling
baseline target in that same league/date is unavailable because exact within-day
ordering is unresolved. After that entire date is complete, all of the date's
outcomes enter league history together. A later source-local date can therefore
use those outcomes because the whole earlier date is mechanically prior. No
arbitrary clock is invented.

A component can legitimately have zero rolling-baseline pairs. That is stored
as an unavailable comparison: paired count `0` and null candidate, benchmark,
delta, and result fields. Lack of a rolling comparison does not invalidate the
otherwise valid component evidence.

Every populated paired comparison stores `candidate - benchmark` NLL. Negative
means the candidate is better; positive means it is worse; zero is an exact
tie. Aggregate rolling paired counts must reconcile exactly with both the
season and league breakdowns.

## Breakdown and calibration

Each component reports per-season and per-identity-league NLL comparisons so a
single competition or period cannot silently carry the aggregate result.

Home and away rates are calibrated in frozen bins:

- `[0.00, 0.50)`
- `[0.50, 1.00)`
- `[1.00, 1.50)`
- `[1.50, 2.00)`
- `[2.00, 2.50)`
- `[2.50, 3.00)`
- `[3.00, +infinity)`

The open upper bound is serialized as `null`, never JSON Infinity. Each bin
reports count, mean predicted goals, mean observed goals, and predicted minus
observed calibration error. Populated predicted means must remain inside their
own bin and observed means cannot be negative.

## Interpretation boundary

This artifact is labelled
`RETROSPECTIVE_PR69_COMPONENT_VALIDATION_RESEARCH_ONLY`. It is not presented as
an untouched out-of-sample or prospective validation because the development
history of the legacy heuristic is not proven sufficiently for those claims.

No threshold automatically approves a component. Poor results are evidence to
reject or replace the old heuristic, not a reason to tune the formula inside
this PR. Good results are evidence for further validation, not production
permission.

All safety flags remain exact `false`. PR #70 does not run a score matrix,
calculate 1X2/totals/BTTS probabilities, consume odds, calculate value, select a
bet, or authorize production use.
