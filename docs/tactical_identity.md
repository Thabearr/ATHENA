# Tactical Identity Engine

Expansion Phase 3 adds a research-only historical Tactical Identity layer. Its
purpose is to express evidence-backed team behaviour without encoding club
reputation. A Getafe-class signal therefore means that strictly prior evidence
supports a low-event environment or defensive suppression; it never means that
a team name is mapped to an Under-style stereotype.

## Source and leakage boundary

The primary source is the canonical Phase 2 historical as-of corpus. The exact
canonical historical warehouse is additionally opened read-only for source-bound
prior team-match observations, prior coach evidence, and strictly prior
competition baselines.

Construction fails closed unless the as-of corpus metadata warehouse SHA-256
matches the SHA-256 calculated from the actual warehouse bytes. Historical
feature-registry and generation-contract identities are revalidated. Corpus
payload bytes are replayed canonically and target identity is checked against
the exact source-bound warehouse row.

Canonical Tactical Identity snapshots are source-builder-only. There is no
public constructor token or caller-authoritative assembler that can combine a
real source SHA with fabricated target payloads or competition baselines.
Caller-provided SHA strings, fake private attributes, or a recomputed output hash
do not establish ancestry.

`DATE_STRICT_PRIOR_FIXTURES_V1` remains authoritative. For target date D, only
completed fixtures with `match_date < D` may influence the target. Target FT,
HT, xG, shots, events, target coach evidence, same-date fixtures, and later
fixtures cannot enter that target's identity.

Team identity remains:

`COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1`

The same display name in another competition is not automatically the same
historical identity. The schedule fields inherited from Phase 2 therefore remain
`COMPETITION_SCOPED_WORKLOAD_CONTEXT_V1`; they are not complete all-competition
club congestion.

## Frozen Tactical Identity contract

Tactical Identity registry version 1 is independently pinned to:

`f3bc2dadefe51126093c44abdacb0a252498684fbed23c4a5662d8d8e8d01d0e`

Tactical generation contract version 1 is independently pinned to:

`5658030a4583acc2c6f35ebc1ea0f950e01f1f22d4c6e82ed722e77f26769f9b`

The generation contract binds the actual output semantics, including:

- Tactical Identity registry version and SHA;
- Phase 2 feature-registry version and SHA;
- Phase 2 generation-contract version and SHA;
- historical completion and advanced-period safety policies;
- DATE_STRICT and competition-scoped identity policies;
- the 60-day recency half-life;
- freshness-sensitive shrinkage policy and K=5;
- minimum team component evidence of 3;
- minimum competition baseline population of 20;
- descriptor thresholds -0.5 and +0.5;
- independent LAST_20 history policy by scope;
- manager-regime and regime-profile policies;
- opponent-adjustment policy;
- workload-context, score-state, and matchup-interaction policies.

Changing these values or policy IDs without a reviewed version/pin change fails
same-version validation.

## Dimensions

Every canonical team profile resolves evidence as `AVAILABLE`, `MISSING`, or
`BLOCKED` across:

- EVENT_ENVIRONMENT;
- ATTACKING_PRODUCTION;
- DEFENSIVE_SUPPRESSION;
- SHOT_PROFILE;
- FIRST_HALF_ENVIRONMENT;
- CONTROL_TEMPO;
- SCORING_RELIABILITY;
- VENUE_EXPRESSION;
- OPPONENT_INTERACTION;
- REGIME_CONTEXT;
- EVIDENCE_UNCERTAINTY.

Continuous component estimates remain visible. Goals, xG, shots, shots on
target, possession, HT evidence, clean-sheet/failed-to-score rates, BTTS, and
total-goal rates are not silently substituted for each other. Missing xG stays
missing. Possession is only a proxy and does not prove pressing, field tilt,
low-block behaviour, or another tactical mechanism.

## Recency and shrinkage

`EXPONENTIAL_DATE_DECAY_60_DAY_HALF_LIFE_V1` gives a valid observation of age
`a` integer days:

`w(a) = 2 ** (-a / 60)`

The profile retains both:

`Kish ESS = (sum(w) ** 2) / sum(w ** 2)`

and the freshness-sensitive evidence mass:

`decayed evidence mass = sum(w)`

Kish ESS describes weight concentration; it is not used as an age-invariant
substitute for freshness. Shrinkage uses
`DECAY_WEIGHT_MASS_EMPIRICAL_SHRINKAGE_K5_V1`:

`reliability = evidence_mass / (evidence_mass + 5)`

`shrunk = reliability * team_raw + (1 - reliability) * competition_prior`

This means an equally sized history moved hundreds of days into the past gets
less shrinkage reliability. A competition prior never creates team evidence
when the team has no qualifying observations.

## Strictly prior competition baselines and descriptors

`DATE_STRICT_COMPETITION_BASELINE_V1` uses only completed observations strictly
before the target date. Same-date and future observations are excluded.

A component receives a competition-relative z value only when a sufficient
strictly prior competition population exists. A tactical dimension combines
only qualifying component z values using the versioned registry orientations
and arithmetic-mean rule.

For the dimensions with descriptive bands,
`PRIOR_COMPETITION_Z_BANDS_HALF_SIGMA_V1` uses:

- `score <= -0.5`: LOW;
- `score >= +0.5`: HIGH;
- otherwise: MID.

These are descriptive historical research bands, not probabilities, prices, or
betting decisions.

## Independent overall and venue histories

History policy is:

`INDEPENDENT_COMPLETE_BOUNDARY_LAST_20_BY_SCOPE_V1`

OVERALL uses the last 20 qualifying overall fixtures with complete-date-boundary
semantics. HOME_ONLY independently filters all qualifying history to home
fixtures and then applies its own last-20 complete-date window. AWAY_ONLY does
the same for away fixtures.

The venue profile is therefore not merely the home/away subset found inside the
overall last 20. Venue deltas are emitted only where both underlying continuous
profiles exist; missing evidence does not become a zero delta.

## Feature-local conflicts

Conflict coverage is component-local. For example, an xG-for component counts
conflicts on the exact side-specific xG warehouse field used by that component;
a referee, possession, coach, or unrelated opponent-field conflict does not
inflate xG conflict coverage.

## Opponent adjustment

`PRIOR_MATCH_OPPONENT_PREMATCH_RESIDUAL_V1` is implemented through a safe
pre-prior-match join.

For each contributing prior match P, the engine uses P's source-issued observed
team projection and the opponent's Phase 2 as-of snapshot for P. The opponent
expectation therefore comes from evidence that existed before P. Supported
residual families include goals, xG, shots, and shots on target where both sides
of the residual are safely available.

The engine never uses the opponent's state after P or the target-date opponent
state to normalize P. Missing pre-P opponent state stays missing; blocked state
stays blocked. Raw averages are never relabelled opponent-adjusted. The profile
retains valid/missing/blocked sample counts, contributing match keys, source
opponent snapshot identities, and recency-weighted residuals.

## Manager regime

Manager policy is:

`LAST_OBSERVED_PRIOR_EXACT_MANAGER_DATE_BUCKET_V1`

Only exact prior coach observations are used. Same-date observations are treated
as a date bucket; distinct manager identities within one prior date bucket fail
closed as `AMBIGUOUS_SAME_DATE_PRIOR_MANAGER`. Match-key ordering is never used
to invent intra-day chronology.

Unknown coach gaps do not prove uninterrupted regime continuity. The profile
retains the last observed prior manager, last observed date, observed manager
change status, exact regime match keys, unknown-gap/continuity metadata, and:

`current_manager_confirmed = false`

The target's stored post-hoc coach never establishes the target's current
manager.

When a safe last-observed prior regime exists, the engine emits both the general
recency-weighted Tactical Identity profile and a separate
`LAST_OBSERVED_PRIOR_MANAGER_REGIME` profile plus available deltas against the
general profile.

## Score state

Score-state behaviour remains:

`FUTURE_EVIDENCE_REQUIRED_V1`

No leading/level/trailing duration is invented from FT/HT scores. A later
reviewed contract may use complete regulation-only preferred-event chronology.

## Matchup interaction

`DESCRIPTIVE_STATISTICAL_DIFFERENCES_ONLY_V1` exposes only supported numerical
interactions such as event-environment difference and attack-versus-suppression
differences. It does not manufacture mechanism labels such as press-vs-build-up
or low-block-vs-possession.

## Canonical output and bulk construction

Canonical snapshots retain target identity, exact as-of corpus SHA, exact
warehouse SHA, Phase 2 registry/generation identities, Tactical Identity
registry/generation identities, policy IDs, home/away profiles, matchup
interaction, coverage, and all-false authority flags. Serialization is
self-contained and does not consult a future mutated registry.

`scripts/build_tactical_identity_corpus.py` writes a separate generated SQLite
corpus. The implementation processes chronological source/corpus records with
bounded per-team rolling histories and independent overall/home/away date
buckets rather than materializing the full corpus target universe in one Python
set. Source databases remain read-only and generated databases stay outside
Git.

## Scope and authority

Fixture State v2 tactical slots are not activated by this PR and
`fixture_model_features` v1 is unchanged. Tactical Identity grants no network or
provider acquisition, model training/promotion, probability inference or
adjustment, calibration, bookmaker pricing, market activation, routing,
selection, accumulator, production approval, or BET authority.
