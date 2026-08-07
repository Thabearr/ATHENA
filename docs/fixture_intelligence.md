# Fixture Intelligence Evidence Contract

## 1. Purpose
This PR introduces the `FixtureIntelligenceSnapshot` and related evidence contract models. It establishes a strictly typed, immutable foundation for gathering, representing, and storing intelligence (such as weather, form, injuries) about a fixture prior to kickoff.

## 2. Architecture Diagram

```text
FotMob fixture catalog
        |
        v
Fixture Intelligence Evidence
        |
        +--> form
        +--> injuries/suspensions
        +--> lineup
        +--> schedule/rest/fatigue
        +--> performance/xG
        +--> weather
        +--> venue/referee/context
        +--> official corroboration
        +--> discovery-only search leads
        |
        v
future feature mapping
        |
        v
market-specific probability models
```

## 3. Intelligence Categories
- `FIXTURE_CONTEXT`: General context about the match.
- `FORM`: Recent team results and goal trends.
- `AVAILABILITY`: Injuries, suspensions, or missing key players.
- `LINEUP`: Expected or confirmed starting XIs.
- `SCHEDULE_LOAD`: Fixture congestion, rest days, travel fatigue.
- `PERFORMANCE`: Underlying metrics like xG.
- `WEATHER`: Meteorological conditions.
- `VENUE`: Pitch conditions, referee assignments, stadium context.
- `MATCH_CONTEXT`: Derbies, motivation, must-win situations.
- `OFFICIAL_NEWS`: Corroborated statements from clubs/managers.

## 4. Source Roles
- `PRIMARY_FOOTBALL_CONTEXT`: Backbone data (e.g., FotMob).
- `OFFICIAL_CORROBORATION`: First-party team or league data.
- `WEATHER_CONTEXT`: Dedicated meteorological sources.
- `VERIFIED_EXTERNAL`: Trusted third-party analysis.
- `DISCOVERY_ONLY`: Unverified leads (e.g., search queries) that cannot directly support a fact.

## 5. Fact Status Semantics
- `SUPPORTED`: Validated and trusted evidence.
- `STALE`: Evidence that is considered outdated.
- `CONFLICTED`: Contradictory supported evidence exists for the same field.
- `UNVERIFIED`: Data lacking corroboration or trust.

## 6. Primary Football-Context Backbone
FotMob serves as the primary football-context backbone. It provides the base layer of intelligence. Note that this is not yet wired in this PR.

## 7. Official Sources
Official corroboration is required to elevate certain claims (like injuries or lineups) from rumors to supported facts.

## 8. Weather Context
Weather intelligence is modeled as a dedicated `WEATHER_CONTEXT` source role, mapping to the `WEATHER` category.

## 9. Search as Discovery Only
Search results and exploratory web scraping act as `DISCOVERY_ONLY` leads. They yield `UNVERIFIED` facts and cannot become `SUPPORTED` directly without corroboration.

## 10. Pricing and Bookmakers
SportyBet (or other bookmakers) serves as a pricing/bookmaker source only. Odds do not dictate ground-truth intelligence.

## 11. Relation to Model Status
The intelligence gathered here will eventually map to features as defined in `domain/model_status.py` in a future step.

## 12. Relation to Prediction Engine
This contract will act as a contextual overlay for `intelligence/prediction_engine.py`.

## 13. Safety Flags
The snapshot includes explicit safety flags (e.g., `network_acquisition_authorized`, `bet_authorized`). All must be `False` to ensure this contract merely represents inert data, not executable actions.

## 14. THIS PR DOES NOT:
- make predictions
- decide which source wins conflicts
- enable any market
- qualify SportyBet
- activate legacy FotMob network workers

## 15. Core Epistemic Rules:
- Unknown remains unknown
- Conflicted remains conflicted
- Discovery remains unverified
- No data may influence ATHENA merely because it was fetched successfully
