# Canonical Fixture State v2

## Purpose and relationship to existing contracts

Expansion Phase 1 adds `athena-fixture-state-v2`, schema version `2`, as a
strict richer pre-match state boundary. It consumes one already-created
`FixtureIntelligenceSnapshot`; it does not acquire data or query a provider,
browser, historical database, or model.

`domain/fixture_model_features.py` remains the unchanged v1 six-numeric-feature
contract used by pinned research, holdouts, and current model consumers. V2 is
additive: it preserves compatible slots for those six fields while providing
typed representation slots needed by future historical as-of builders,
Tactical Identity, Goal/Score Dynamics, and specialist models. No v1 dataset,
enum, mapping, canonical identity, or replay semantic is renamed or replaced.

## Source hierarchy and field registry

The source-role planning order is: qualified FotMob football context; official
club, league, federation, or competition evidence where appropriate; a
specialist provider for specialist facts; deterministic ATHENA derivation from
qualified evidence; verified external evidence; and discovery-only leads.
This ordering is not a conflict-resolution rule. Conflicts remain `BLOCKED`
unless a separately reviewed precedence policy resolves them.

Every field definition embeds a typed source plan. `preferred source` is an
intended role, not a claim that the provider currently supplies the field.
`reviewed path` is true only where the repository contains a reviewed semantic
path; it does not imply prospective coverage. `FI` below means an exact
`FixtureIntelligenceSnapshot` category/field mapping. The matrix is a static,
deterministic rendering of the canonical registry.

| Field | Family | Value type | Preferred source class | Current reviewed upstream | Current state | Future work required |
| --- | --- | --- | --- | --- | --- | --- |
| `home_form` | legacy strength | finite number | `FOTMOB_PRIMARY` | FI `FORM/home_form` plus v1 binding; provider remains fact-qualified | `CURRENTLY_MAPPABLE` | prospective source qualification and as-of coverage |
| `away_form` | legacy strength | finite number | `FOTMOB_PRIMARY` | FI `FORM/away_form` plus v1 binding; provider remains fact-qualified | `CURRENTLY_MAPPABLE` | prospective source qualification and as-of coverage |
| `home_elo` | legacy strength | finite number | `ATHENA_DERIVED` | FI `PERFORMANCE/home_elo` plus v1 binding | `CURRENTLY_MAPPABLE` | preserve reviewed v1 semantics in as-of builders |
| `away_elo` | legacy strength | finite number | `ATHENA_DERIVED` | FI `PERFORMANCE/away_elo` plus v1 binding | `CURRENTLY_MAPPABLE` | preserve reviewed v1 semantics in as-of builders |
| `fatigue` | legacy strength | finite number | `ATHENA_DERIVED` | FI `SCHEDULE_LOAD/fatigue` plus v1 binding | `CURRENTLY_MAPPABLE` | preserve reviewed v1 semantics in as-of builders |
| `live_data_freshness` | legacy strength | finite number | `ATHENA_DERIVED` | FI `FIXTURE_CONTEXT/live_data_freshness` plus v1 binding | `CURRENTLY_MAPPABLE` | preserve reviewed v1 semantics in as-of builders |
| `home_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate historical as-of derivation |
| `away_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate historical as-of derivation |
| `home_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate historical as-of derivation |
| `away_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate historical as-of derivation |
| `home_opponent_adjusted_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate opponent-adjusted as-of derivation |
| `away_opponent_adjusted_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate opponent-adjusted as-of derivation |
| `home_opponent_adjusted_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate opponent-adjusted as-of derivation |
| `away_opponent_adjusted_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate opponent-adjusted as-of derivation |
| `home_venue_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate home/away-specific derivation |
| `home_venue_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate home/away-specific derivation |
| `away_venue_attack_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate home/away-specific derivation |
| `away_venue_defensive_strength` | team performance | finite number | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | validate home/away-specific derivation |
| `home_tactical_identity` | tactical/regime | categorical string | `ATHENA_DERIVED` | none | `FUTURE_DERIVED` | Phase 3 Tactical Identity Engine |
| `away_tactical_identity` | tactical/regime | categorical string | `ATHENA_DERIVED` | none | `FUTURE_DERIVED` | Phase 3 Tactical Identity Engine |
| `home_manager_regime_identity` | tactical/regime | categorical string | `ATHENA_DERIVED` | none | `FUTURE_DERIVED` | qualify manager evidence and regime segmentation |
| `away_manager_regime_identity` | tactical/regime | categorical string | `ATHENA_DERIVED` | none | `FUTURE_DERIVED` | qualify manager evidence and regime segmentation |
| `home_availability_state` | availability/lineup | structured record | `FOTMOB_PRIMARY` | exact reviewed FotMob player-context observations; FI mapping | `PARTIALLY_PROVEN` | prospective freshness, coverage, and corroboration policy |
| `away_availability_state` | availability/lineup | structured record | `FOTMOB_PRIMARY` | exact reviewed FotMob player-context observations; FI mapping | `PARTIALLY_PROVEN` | prospective freshness, coverage, and corroboration policy |
| `home_lineup_state` | availability/lineup | categorical string | `FOTMOB_PRIMARY` | exact reviewed predicted-lineup observation; FI mapping | `PARTIALLY_PROVEN` | prospective freshness and wider fixture coverage |
| `away_lineup_state` | availability/lineup | categorical string | `FOTMOB_PRIMARY` | exact reviewed predicted-lineup observation; FI mapping | `PARTIALLY_PROVEN` | prospective freshness and wider fixture coverage |
| `home_lineup_confirmed` | availability/lineup | boolean | `FOTMOB_PRIMARY` | reviewed player-context lineage does not prove confirmation | `PARTIALLY_PROVEN` | define predicted-versus-confirmed policy |
| `away_lineup_confirmed` | availability/lineup | boolean | `FOTMOB_PRIMARY` | reviewed player-context lineage does not prove confirmation | `PARTIALLY_PROVEN` | define predicted-versus-confirmed policy |
| `home_lineup_freshness` | availability/lineup | finite number | `FOTMOB_PRIMARY` | reviewed exact-observation timestamps; no general coverage | `PARTIALLY_PROVEN` | define prospective freshness computation |
| `away_lineup_freshness` | availability/lineup | finite number | `FOTMOB_PRIMARY` | reviewed exact-observation timestamps; no general coverage | `PARTIALLY_PROVEN` | define prospective freshness computation |
| `venue` | context | categorical string | `FOTMOB_PRIMARY` | none currently approved for this v2 field | `FUTURE_SOURCE_REQUIRED` | qualify prospective FotMob venue mapping |
| `home_travel_context` | context | structured record | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | derive from verified fixture and venue geography |
| `away_travel_context` | context | structured record | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | derive from verified fixture and venue geography |
| `weather` | context | structured record | `SPECIALIST_EXTERNAL` | none currently authorized | `FUTURE_SOURCE_REQUIRED` | qualify meteorological provider and freshness policy |
| `referee` | context | categorical string | `FOTMOB_PRIMARY` | none currently approved for this v2 field | `FUTURE_SOURCE_REQUIRED` | review FotMob or qualify official competition source |
| `competition_stage` | context | categorical string | `FOTMOB_PRIMARY` | none currently approved for this v2 field | `FUTURE_SOURCE_REQUIRED` | review FotMob or qualify official competition source |
| `motivation_match_context` | context | structured record | `ATHENA_DERIVED` | none; FI projection slot only | `FUTURE_DERIVED` | derive only from objective competition state and explicit evidence |

Official corroboration is marked as potentially required for lineup,
availability, manager-regime, referee, competition-stage, and motivation fields.
Fixture identity and kickoff remain SHA-bound snapshot-envelope facts rather
than model-value slots. Their preferred future football-context backbone is
qualified FotMob evidence. Official team news, if introduced as a later field,
must use `OFFICIAL_CORROBORATION`; xG, shots, starts, minutes, and ratings are
qualified inputs to later derivations, not silently added v2 values.

FotMob primacy does not authorize undocumented payload semantics, reuse of one
historical observation, treating a predicted lineup as confirmed, treating a
missing bench as empty, interpreting undocumented position IDs, using market
value as player quality, reusing stale availability, or translating unavailable
player counts directly into xG. General web search, news, forums, social posts,
and editorial analysis are `DISCOVERY_ONLY`; they cannot create `AVAILABLE`
state without separate preservation, corroboration, and evidence promotion.

### Sourcing and derivation backlog

These are the registered fields without a complete currently approved path.
The gap blocks only a future expert that explicitly declares the field required;
it does not make every Fixture State consumer unusable.

| Field | Desired source class | Why current evidence is insufficient | Bounded future task | Blocking scope |
| --- | --- | --- | --- | --- |
| `home_attack_strength` | `ATHENA_DERIVED` | no reviewed as-of aggregate | define and validate attack-strength builder | requiring experts only |
| `away_attack_strength` | `ATHENA_DERIVED` | no reviewed as-of aggregate | define and validate attack-strength builder | requiring experts only |
| `home_defensive_strength` | `ATHENA_DERIVED` | no reviewed as-of aggregate | define and validate defensive-strength builder | requiring experts only |
| `away_defensive_strength` | `ATHENA_DERIVED` | no reviewed as-of aggregate | define and validate defensive-strength builder | requiring experts only |
| `home_opponent_adjusted_attack_strength` | `ATHENA_DERIVED` | opponent adjustment is not defined | research leakage-safe opponent adjustment | requiring experts only |
| `away_opponent_adjusted_attack_strength` | `ATHENA_DERIVED` | opponent adjustment is not defined | research leakage-safe opponent adjustment | requiring experts only |
| `home_opponent_adjusted_defensive_strength` | `ATHENA_DERIVED` | opponent adjustment is not defined | research leakage-safe opponent adjustment | requiring experts only |
| `away_opponent_adjusted_defensive_strength` | `ATHENA_DERIVED` | opponent adjustment is not defined | research leakage-safe opponent adjustment | requiring experts only |
| `home_venue_attack_strength` | `ATHENA_DERIVED` | home/away split derivation is not reviewed | validate venue-specific strength builder | requiring experts only |
| `home_venue_defensive_strength` | `ATHENA_DERIVED` | home/away split derivation is not reviewed | validate venue-specific strength builder | requiring experts only |
| `away_venue_attack_strength` | `ATHENA_DERIVED` | home/away split derivation is not reviewed | validate venue-specific strength builder | requiring experts only |
| `away_venue_defensive_strength` | `ATHENA_DERIVED` | home/away split derivation is not reviewed | validate venue-specific strength builder | requiring experts only |
| `home_tactical_identity` | `ATHENA_DERIVED` | no Phase 3 engine exists | build time-stamped Tactical Identity Engine | requiring experts only |
| `away_tactical_identity` | `ATHENA_DERIVED` | no Phase 3 engine exists | build time-stamped Tactical Identity Engine | requiring experts only |
| `home_manager_regime_identity` | `ATHENA_DERIVED` | manager source and segmentation are unqualified | qualify evidence and regime boundaries | requiring experts only |
| `away_manager_regime_identity` | `ATHENA_DERIVED` | manager source and segmentation are unqualified | qualify evidence and regime boundaries | requiring experts only |
| `venue` | `FOTMOB_PRIMARY` | no approved prospective v2 mapping | qualify FotMob venue semantics and coverage | requiring experts only |
| `home_travel_context` | `ATHENA_DERIVED` | venue geography derivation is absent | qualify geography and derive travel burden | requiring experts only |
| `away_travel_context` | `ATHENA_DERIVED` | venue geography derivation is absent | qualify geography and derive travel burden | requiring experts only |
| `weather` | `SPECIALIST_EXTERNAL` | no weather provider is authorized | qualify provider, temporal scope, and schema | requiring experts only |
| `referee` | `FOTMOB_PRIMARY` | exact reviewed coverage is absent | review FotMob or official competition source | requiring experts only |
| `competition_stage` | `FOTMOB_PRIMARY` | exact reviewed semantics are absent | review FotMob or official competition source | requiring experts only |
| `motivation_match_context` | `ATHENA_DERIVED` | narrative claims are not objective state | define derivation from competition state | requiring experts only |

Lineup and availability are excluded from this no-path backlog because exact
reviewed FotMob player-context lineage exists, but they remain
`PARTIALLY_PROVEN`: prospective freshness, broader coverage, and any official
corroboration policy are still bounded follow-up work.

The registry contains no odds, bookmaker price, implied probability, expected
value, market, or selection field.

## Typed values and status semantics

V2 supports four checked value types:

- finite numeric scalar, normalized to `float` and rejecting NaN/Infinity;
- non-empty exact categorical string;
- exact boolean (never numeric `0`/`1`); and
- structured record with canonical unique keys and scalar string/number/boolean
  values only. Nested arbitrary dictionaries, duplicate keys, and unordered
  tuple records fail closed. Mutable mappings are detached into immutable sorted
  tuples before identity is calculated.

Every one of the 37 registered fields has exactly one resolution:

- `AVAILABLE` requires at least one matching `SUPPORTED` evidence identity, a
  valid non-conflicted value, and evidence observed no later than `as_of`.
- `MISSING` means there is no qualifying mapped evidence or the field is a
  future-derived slot. It has `null` value, no blocker, and no fabricated hash.
- `BLOCKED` means matching evidence exists but is conflicted, stale, unverified,
  invalid, or otherwise unsafe. It has `null` value and retains sorted evidence
  identities and explicit blockers.

No missing Elo becomes 1500, form becomes 0.5, fatigue becomes neutral, weather
becomes clear, lineup becomes full strength, venue becomes an assumed stadium,
or motivation becomes normal. Defaulting and shrinkage belong downstream.

## Temporal and provenance identity

Fixture State v2 is pre-match only: `as_of` must be strictly earlier than
kickoff, and every retained evidence observation must be at or before `as_of`.
The source fixture identity, kickoff, `as_of`, upstream fixture-intelligence
dataset name, upstream schema version, and canonical upstream snapshot SHA-256
are embedded in the state. The complete registry, resolutions, coverage,
provenance, and safety mapping have deterministic canonical JSON and SHA-256.
Changing the upstream snapshot changes the v2 source identity.

## Legacy-six compatibility and requirement evaluation

For equivalent intelligence evidence, v2 resolves `home_form`, `away_form`,
`home_elo`, `away_elo`, `fatigue`, and `live_data_freshness` with the same
status, normalized value, evidence SHA set, and blocker semantics as v1 for
available, missing, stale/unverified, conflicted, and invalid evidence. V1 stays
the production/research namespace; compatibility does not redirect consumers.

`evaluate_required_fields(snapshot, required_ids)` evaluates only the subset a
future expert explicitly declares. It returns exact available, missing, and
blocked IDs and is usable only when every declared requirement is `AVAILABLE`.
It does not assume that every model requires all 37 fields and cannot upgrade a
missing or blocked field.

Coverage is descriptive only: total, available, missing, and blocked counts and
their exact field IDs. It creates no BASIC/STANDARD/RICH population or training
eligibility tier.

## Tactical and authority boundary

Tactical and manager-regime fields are representation slots only. This phase
does not calculate Tactical Identity, manager regimes, or a low-event class;
team or club names cannot activate them. No Getafe, Racing, or other club
constant exists. Tactical Identity is strictly `ATHENA_DERIVED`. A later engine
may learn only from time-stamped, qualified football evidence such as goals and
xG for/against, shots, chance quality, event volume, qualified possession or
territorial measures, clean sheets, scoring/conceding frequency, first-half and
score-state behaviour, home/away splits, opponent strength, manager regime, and
lineup/availability context. Editorial descriptions cannot become tactical
state.

Every authority flag is explicit `false`: network/provider acquisition,
probability inference/adjustment, model promotion, calibration, bookmaker
pricing, market activation, selection, accumulator, production approval, and
BET. Phase 2 historical as-of work may consume this immutable contract, but it
must separately build evidence-complete historical states and training
populations. This phase performs no history transformation or training.
