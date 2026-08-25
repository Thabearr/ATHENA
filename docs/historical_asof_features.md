# Historical as-of features

## Purpose and boundary

Expansion Phase 2 provides the canonical bridge from `database/athena_history.db` to leakage-safe, pre-match historical research features. The warehouse remains the football truth owner; this layer consumes its canonical fields and precedence decisions rather than re-merging providers. The generated feature corpus is a separate SQLite artifact and is ignored by Git through the repository's `*.db` rule.

This layer does not train a model, calculate Tactical Identity, infer or adjust probabilities, activate Fixture State v2 fields, acquire provider data, price markets, route selections, or grant BET authority. Tactical Identity is explicitly deferred to PR #231.

## Anti-leakage and time

Every target uses `DATE_STRICT_PRIOR_FIXTURES_V1`. A historical match is eligible only when:

```text
historical.match_date < target.match_date
```

The target's own score, half-time score, xG, shots, events, lineup, coach, and other post-hoc fields are never queried as feature inputs. Later matches are excluded. Same-date matches are excluded even when an unqualified raw `kickoff_time` appears earlier, because warehouse clock strings are not universally timezone-qualified or globally comparable.

Fixed-count windows use complete boundary dates. Dates are visited newest first and whole date buckets are added until at least 5, 10, or 20 matches are represented. The oldest selected date is never split using `match_key`; therefore the effective sample can exceed the requested count. `match_key` only gives deterministic serialization inside an already included date bucket.

## Exact source identity and source safety

The input is an explicit SQLite path opened with `mode=ro` and `PRAGMA query_only=ON`. Required warehouse tables/views and `warehouse_meta.schema_version = 1` are verified. Non-empty `-wal` or `-journal` companions are rejected before hashing, around/after opening, after schema validation, and at both sides of the final main-file hash/stat check. A companion appearing during construction therefore invalidates the output; logical state cannot silently depend on bytes outside `source_warehouse_sha256`.

Every snapshot stores:

- the SHA-256 calculated from the exact warehouse file bytes;
- warehouse schema version;
- the repository historical schema SQL SHA-256;
- generation schema version;
- temporal-policy ID;
- independently pinned historical feature-registry version and SHA-256.
- historical team-identity policy `COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1`.

There is no caller-supplied warehouse SHA or schema-SQL path parameter. Canonical snapshot construction is internal to the verified file/streaming builders. Warehouse schema version 1 is independently pinned to repository schema SQL SHA-256 `d5a3b545a639c43a2b35fb18529a429ba2572d2861ac52c638cce42a8141306f`; changed schema bytes or an unknown version fail closed.

## Historical team identity

The warehouse does not currently establish a globally unique cross-competition team ID. Its reviewed aliases are competition- and source-qualified. Phase 2 therefore uses the deliberately narrow policy:

```text
COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1
(scope, competition_key, exact canonical team text)
```

All three components must be present, exact, and whitespace-canonical. Missing competition identity produces no usable history. Identical display text in another competition or scope is a different identity. This temporarily prevents league/cup/UEFA joins even when a human believes the club is the same; losing coverage is safer than contaminating evidence. No case folding, normalization, fuzzy matching, Levenshtein matching, or guessed alias is used by this feature layer. Direct and bulk builders share the same identity function and snapshots/corpus metadata retain its policy ID.

The warehouse's canonical columns are used as-is. `warehouse_field_provenance` source keys and `warehouse_conflicts` counts remain attached to derived feature resolutions. A retained conflict is visible but does not cause this layer to choose a weaker alternative value; provider precedence remains the warehouse's responsibility. Derived projection SHA-256 values are explicitly identities of canonical team-perspective projections, not provider payload hashes.

This implementation does not aggregate incidents. It therefore reads neither raw `warehouse_events` nor `warehouse_events_preferred`. If a later model-facing feature needs incidents, it must consume `warehouse_events_preferred`; raw cross-source incidents must never be double-counted.

## Historical feature registry

Registry version: `1`

Independently reviewed registry SHA-256:

```text
2d1606e54463ee75f984973173af4ba4ba68fe0acc4d0be4e2525b08f5c863f8
```

The literal version-to-SHA pin is independent of the live registry calculation. Stable semantic drift under version 1, or an unknown version without a reviewed pin, fails closed. Each resolution freezes its algorithm ID, primitive dependencies, scope, window, sample metadata, and derived projection identity, so serialization of an existing snapshot does not consult a later live registry.

Registered features:

| Family | Feature IDs |
|---|---|
| Form/results | `points_per_match`, `win_rate`, `draw_rate`, `loss_rate`, `goals_for_per_match`, `goals_against_per_match`, `goal_difference_per_match` |
| Event environment | `total_goals_per_match`, `clean_sheet_rate`, `failed_to_score_rate`, `btts_rate`, `over_1_5_rate`, `over_2_5_rate` |
| Half-time | `first_half_goals_for_per_match`, `first_half_goals_against_per_match`, `first_half_total_goals_per_match` |
| Expected goals | `xg_for_per_match`, `xg_against_per_match`, `xg_total_per_match` |
| Shots | `shots_for_per_match`, `shots_against_per_match`, `shots_on_target_for_per_match`, `shots_on_target_against_per_match` |
| Possession | `possession_for_mean` |
| Discipline | `yellows_for_per_match`, `reds_for_per_match` |
| Schedule | `days_since_last_match`, `fixtures_last_7_days`, `fixtures_last_14_days`, `fixtures_last_28_days` |

Score-derived primitive dependencies are exact:

| Required primitives | Features |
|---|---|
| `goals_for` | `goals_for_per_match`, `failed_to_score_rate` |
| `goals_against` | `goals_against_per_match`, `clean_sheet_rate` |
| `goals_for + goals_against` | `points_per_match`, `win_rate`, `draw_rate`, `loss_rate`, `goal_difference_per_match`, `total_goals_per_match`, `btts_rate`, `over_1_5_rate`, `over_2_5_rate` |

Canonical warehouse admission still requires both regulation FT scores. The minimal dependency mapping prevents the registry itself from overstating each algorithm's mathematics; it does not authorize FT-incomplete warehouse rows to bypass the completed-prior-fixture gate.

No odds, bookmaker probability, market, price, tactical label, manager regime, lineup state, availability state, or live-data freshness field exists in this registry.

## Team projection, scopes, and missingness

A completed prior match is projected once from each team's perspective. The projection retains match/date/competition/season identity, opponent and home/away side, and only warehouse primitives actually present: regulation result, half-time result, xG, shots, shots on target, possession, corners, fouls, cards, provenance, and conflicts.

“Completed prior match” has one shared direct/bulk qualification rule: both canonical regulation FT scores must be exact non-negative integers. A dated scheduled, postponed, abandoned, or otherwise FT-incomplete row never enters performance, schedule, rest, congestion, season, or rolling state—even if xG, shots, events, or other aggregates happen to be present. A target row may itself be incomplete because its state is pre-match, but it is admitted into later history only after satisfying this completion rule.

Missing pairs are never synthesized. For example, a missing away xG is not zero. Registry dependencies are the minimal mathematical inputs: `goals_for_per_match` and `failed_to_score_rate` require only goals for; `goals_against_per_match` and `clean_sheet_rate` require only goals against. Result/outcome, goal-difference, total-goal, BTTS, and over-rate metrics require both. The same minimal rule applies to HT, xG, shots, possession, discipline, and schedule fields.

For a mechanically identified ET or shootout match, aggregate advanced fields without reviewed regulation-only semantics are unsafe. Any retained xG, shots, shots on target, possession, corners, fouls, yellows, or reds are `BLOCKED` from model-facing aggregation. Regulation FT/HT results and completed-match schedule chronology remain usable. No proportional scaling, 120-minute division, estimated subtraction, or provider-wide assumption is applied.

Each target home team has distinct `OVERALL` and `HOME_ONLY` summaries. Each target away team has distinct `OVERALL` and `AWAY_ONLY` summaries. Here `OVERALL` and all schedule fields mean overall only within `COMPETITION_SCOPED_EXACT_CANONICAL_TEAM_V1`. They are not all-competition club workload: league/cup/UEFA joining remains unauthorized, so PR #231 must not treat these schedule fields as complete real-world congestion. Performance summaries cover last 5, 10, and 20 complete-boundary-date windows plus same-season season-to-date history.

`season = NULL`, blank, or otherwise unusable is unknown—not an all-time season identifier. For such a target every `SEASON_TO_DATE` resolution is `MISSING`; last-5/10/20 and schedule features continue under their independent temporal rules.

Every resolution is explicitly:

- `AVAILABLE`: qualifying prior values exist and the finite derived value retains a deterministic contributing-projection identity;
- `MISSING`: no qualifying value exists, with `value = null` and no default;
- `BLOCKED`: an unsafe/invalid source condition is explicitly retained. Invalid non-finite or invalid count values currently fail the containing build closed before a misleading feature can be serialized.

For each metric the ledger retains requested window, effective match sample, valid-field sample, missing-field count, oldest/newest contributing dates, source keys, conflict count, algorithm ID, required primitives, and derived projection SHA. Metrics with different warehouse coverage therefore have different valid samples. No xG/stat absence becomes zero or a league average.

No prior match means rest and congestion are `MISSING`. Once prior chronology exists, a zero fixtures-in-window value is a legitimate derivation rather than a neutral default.

## Bulk corpus builder

Run offline:

```bash
python scripts/build_historical_asof_feature_corpus.py \
  --db database/athena_history.db \
  --output data/history_features/athena_history_asof_features.db
```

Development filters are `--competition`, `--start-date`, `--end-date`, and `--limit`. They select target rows only; all strictly prior warehouse matches remain eligible history, so filters cannot change feature semantics.

The builder streams matches in date order and handles each date as a batch. All target snapshots for date D are captured before completed rows from D are added to rolling team state, which mechanically enforces DATE_STRICT and prevents same-day leakage. Rolling state independently retains: complete date buckets through the last-20 boundary; every completed match in the previous 28 days for schedule counts; and the current usable exact season for season-to-date. The 28-day cache is pruned as every chronological bucket is added, including years before a filtered target range, so `--start-date` cannot cause unbounded schedule memory. A closed season reappearing after a later season fails closed rather than producing partial season state. Output commits are batched.

`days_since_last_match` uses every completed fixture in the complete most-recent prior-date bucket as its canonical evidence. Zero fixtures-in-N-day derivations use that same complete fallback bucket, never one match selected by `match_key` ordering.

Conflict attribution is match- and feature-local. Each feature maps its required primitives to the exact home/away warehouse columns for each contributing projection, then counts only conflicts on those columns in that match. A conflict on an opponent-side field cannot become relevant merely because the same column is used by another match in the sample.

Warehouse numeric validation rejects NaN, infinity, negative xG, and non-integer or negative count fields. The warehouse schema establishes xG as a non-negative quantity and count fields as exact counts. Possession remains finite-only because the repository does not yet prove one universal stored scale/domain; this layer does not invent a 0–1 or 0–100 bound.

The output path must differ from both `athena_history.db` and operational `database/athena.db`. Existing output is refused unless `--replace` is explicit. No network code is called.

## Explicit deferrals and Fixture State v2

Historical Elo is not implemented here. This avoids falsely claiming parity between the current sequential Elo engine and the required future date-batched research replay. Opponent adjustment is also deferred; raw prior opponent identities and production evidence are retained instead of labeling raw averages as adjusted.

Target final lineups and target coaches are post-hoc warehouse facts, not proven pre-match observations, and cannot activate lineup, availability, or manager state. Historical live-data freshness cannot be reconstructed from source names, database timestamps, file age, retrieval dates, or match age and remains unavailable.

Fixture State v2 and `fixture_model_features` v1 are unchanged. Phase 2 supplies clean historical inputs for PR #231 to study low/high event environments, attack production, defensive suppression, xG and shot patterns, clean sheets, failed scoring, venue differences, first-half environments, and schedule effects. PR #231—not this layer—may define a separately reviewed Tactical Identity contract. No club name, including Getafe, maps to a style.

All acquisition, provider, probability, training/promotion, calibration, bookmaker, market, routing, selection, accumulator, production, and BET authority flags are explicit `false`.
