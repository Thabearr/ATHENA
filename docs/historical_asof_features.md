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

The input is an explicit SQLite path opened with `mode=ro` and `PRAGMA query_only=ON`. Required warehouse tables/views and `warehouse_meta.schema_version = 1` are verified. A non-empty `-wal` or `-journal` companion is rejected, and file size, modification time, and a second SHA check detect changes during construction.

Every snapshot stores:

- the SHA-256 calculated from the exact warehouse file bytes;
- warehouse schema version;
- the repository historical schema SQL SHA-256;
- generation schema version;
- temporal-policy ID;
- independently pinned historical feature-registry version and SHA-256.

There is no caller-supplied warehouse SHA parameter. Canonical snapshot construction is internal to the verified file/streaming builders.

The warehouse's canonical columns are used as-is. `warehouse_field_provenance` source keys and `warehouse_conflicts` counts remain attached to derived feature resolutions. A retained conflict is visible but does not cause this layer to choose a weaker alternative value; provider precedence remains the warehouse's responsibility. Derived projection SHA-256 values are explicitly identities of canonical team-perspective projections, not provider payload hashes.

This implementation does not aggregate incidents. It therefore reads neither raw `warehouse_events` nor `warehouse_events_preferred`. If a later model-facing feature needs incidents, it must consume `warehouse_events_preferred`; raw cross-source incidents must never be double-counted.

## Historical feature registry

Registry version: `1`

Independently reviewed registry SHA-256:

```text
f8014761d168ade0fe95142c3e1358ba4b8d2e065880d37a2162887099269b51
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

No odds, bookmaker probability, market, price, tactical label, manager regime, lineup state, availability state, or live-data freshness field exists in this registry.

## Team projection, scopes, and missingness

A completed prior match is projected once from each team's perspective. The projection retains match/date/competition/season identity, opponent and home/away side, and only warehouse primitives actually present: regulation result, half-time result, xG, shots, shots on target, possession, corners, fouls, cards, provenance, and conflicts.

Missing pairs are never synthesized. For example, a missing away xG is not zero. A metric uses exactly its declared primitives: `xg_for_per_match` can use a present team xG, while `xg_total_per_match` requires both xG values.

Each target home team has distinct `OVERALL` and `HOME_ONLY` summaries. Each target away team has distinct `OVERALL` and `AWAY_ONLY` summaries. Schedule features use overall chronology. Performance summaries cover last 5, 10, and 20 complete-boundary-date windows plus same-season season-to-date history.

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

The builder streams matches in date order and handles each date as a batch. All target snapshots for date D are captured before D is added to rolling team state, which mechanically enforces DATE_STRICT and prevents same-day leakage. Rolling state retains complete date buckets through the last-20 boundary and bounded active season state. Output commits are batched. The process is linear in matches apart from indexed per-match provenance lookups and bounded feature aggregation; it does not rebuild history by scanning all prior matches for every target.

The output path must differ from both `athena_history.db` and operational `database/athena.db`. Existing output is refused unless `--replace` is explicit. No network code is called.

## Explicit deferrals and Fixture State v2

Historical Elo is not implemented here. This avoids falsely claiming parity between the current sequential Elo engine and the required future date-batched research replay. Opponent adjustment is also deferred; raw prior opponent identities and production evidence are retained instead of labeling raw averages as adjusted.

Target final lineups and target coaches are post-hoc warehouse facts, not proven pre-match observations, and cannot activate lineup, availability, or manager state. Historical live-data freshness cannot be reconstructed from source names, database timestamps, file age, retrieval dates, or match age and remains unavailable.

Fixture State v2 and `fixture_model_features` v1 are unchanged. Phase 2 supplies clean historical inputs for PR #231 to study low/high event environments, attack production, defensive suppression, xG and shot patterns, clean sheets, failed scoring, venue differences, first-half environments, and schedule effects. PR #231—not this layer—may define a separately reviewed Tactical Identity contract. No club name, including Getafe, maps to a style.

All acquisition, provider, probability, training/promotion, calibration, bookmaker, market, routing, selection, accumulator, production, and BET authority flags are explicit `false`.
