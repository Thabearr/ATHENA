# Unreviewed FotMob fixture candidates

## Purpose and boundary

PR #40 converts only verified, PR #39-conformant raw captures into deterministic,
provenance-backed fixture evidence objects. Every candidate is explicitly
`UNREVIEWED`. UNREVIEWED candidate generation is not Fixture Catalog promotion.
The production boundary neither imports Fixture Catalog nor creates a
`fixture_identifier`, catalog input, catalog record, promotion decision,
intelligence fact, model feature, probability, price, selection, or bet.

The source capability registry key `fotmob_unofficial` remains `UNKNOWN`.
Candidates preserve source observations; they do not qualify FotMob or establish
semantic trust.

```text
verified PR #38 capture(s)
    -> merged PR #39 schema assessment for every capture
    -> second inert strict JSON parse
    -> exact reviewed source-value mapping
    -> UNREVIEWED capture-specific candidates
    -> deterministic conflict observations and bundle SHA-256
```

The process is offline. The CLI exposes no URL, network execution flag, output
file, catalog, promotion, identity-resolution, gender, competition, or status
option. It writes no file and prints only a bounded canonical summary.

## Four-date evidence

PR #39 accepted four independently preserved captures without schema changes:

| Request date | Manifest SHA-256 | PR #39 assessment SHA-256 | Observed matches |
| --- | --- | --- | ---: |
| 20260815 | `3fe1d24a0738114c46114a815eca44c4221b53fe8da2476d5a487153ce72d145` | `a20f6fbf73414b88d8a4d41b12162d5e710aafb8a53d6f3bf937b5e3f5a1080b` | 630 |
| 20260816 | `dc4e22e012fb07b45fc3329833c096cd23957618495640ea978ed4d146144b57` | `a9e25141dca0b2fc061f9cb54442a6200fc06694f1bdae37b1a2734605608f3a` | 423 |
| 20260822 | `a0dd658ac4a0a20ad758ce9d60a92285292e2852ca5d3322751487ecf1b13a5d` | `e0096f9c574fa0e375c44efacb6f4bcf96461aea6c04200366411b81a5dfe6a8` | 698 |
| 20260829 | `a64715a5a4d37cbec04402496484ebb6bd499cdec4ca7134d6f74d19bbe93007` | `10c4dab151c1807df9859da94fab69abce192b2c38899775024d35afd9c1c7dd` | 750 |

The 2,501 records are observations from these four captures, not an endpoint
completeness claim. The later captures materially broadened observed
competition coverage, but PR #40 has no competition whitelist or product
selection filter.

## Exact source mapping

After a capture passes the merged PR #39 assessor, every value below is copied
from one exact `leagues[i].matches[j]` record:

| Candidate field | Exact source path |
| --- | --- |
| `source_match_id` | `match.id` |
| `source_league_id` | containing `league.id` |
| `source_competition_primary_id` | containing `league.primaryId` |
| `source_competition_name` | containing `league.name` |
| `source_competition_ccode` | containing `league.ccode` |
| `home_source_team_id` | `match.home.id` |
| `home_name` | `match.home.name` |
| `home_long_name` | `match.home.longName` |
| `away_source_team_id` | `match.away.id` |
| `away_name` | `match.away.name` |
| `away_long_name` | `match.away.longName` |
| `kickoff_utc` | reviewed `match.status.utcTime` |

The candidate also carries its exact canonical source manifest SHA-256, raw
SHA-256, request date, and acquisition observation timestamp. Each source
descriptor carries the PR #38 dataset/schema ancestry, raw size, request
timezone and country code, PR #39 assessment SHA-256, and computed candidate
count. Every conforming match produces exactly one candidate. Nothing is
silently filtered or deduplicated.

Source strings are preserved exactly: no trimming, case conversion,
transliteration, punctuation removal, aliasing, fuzzy matching, or competition
normalization occurs. Integers remain exact integers. Kickoff uses only PR #39's
reviewed UTC representation and is serialized canonically in UTC.

## Opaque source identity and conflicts

FotMob match, league, and team identifiers are source references. PR #40 does
not turn a source match ID into an approved `FOTMOB:<id>` catalog identifier.
In particular, **Same FotMob team ID does not establish same canonical ATHENA
team.** Candidate identity and equality do not depend solely on a team ID, and
there is no team registry, canonicalization, preferred-name selection, or
gender/category inference.

Across the four reviewed captures, source team ID `394121` had two exact
name/long-name pairs:

```text
VfL Wolfsburg / VfL Wolfsburg
VfL Wolfsburg (W) / VfL Wolfsburg (W)
```

The bundle reports both variants and their source-manifest ancestry. It does
not assert why the source ID was reused, remove `(W)`, infer gender, or choose a
preferred variant. The same rule applies to competition identity variants.

Repeated source match IDs remain as capture-specific candidates. The bundle
counts distinct repeated IDs and records a fixture identity conflict only when
the reviewed tuple `(league ID, home source team ID, away source team ID,
kickoff UTC)` differs. Identical repeats are duplicates, not conflicts; neither
case is silently reconciled.

## Deliberately excluded semantics

PR #40 does not map `home.score`, `away.score`, `statusId`, `started`,
`cancelled`, `finished`, `reason`, `aggregatedStr`, `halfs`,
`firstHalfStarted`, display `time`, `tournamentStage`, or
`eliminatedTeamId`. It emits no current/full-time/half-time score and no fixture
status. The source values remain available only in the preserved raw evidence
for future separately reviewed work.

## Determinism, verification, and CLI

The domain builder requires at least one `(raw bytes, PR #38 manifest)` pair,
rejects duplicate manifest inputs, validates raw size and SHA-256, and invokes
the merged PR #39 assessor before extraction. Schema drift fails closed. A
second strict UTF-8 JSON parse rejects duplicate keys, invalid constants, and
malformed JSON; it does not weaken the PR #39 schema.

Sources, candidates, conflicts, and variants use fixed deterministic ordering.
Reversing capture input order leaves canonical bundle bytes and SHA-256
unchanged. Canonical serialization is compact sorted UTF-8 JSON with
`allow_nan=False` and one final newline.

The CLI fixes its read boundary to
`.cache/athena-research/fotmob-data-matches-captures`, invokes PR #38's verifier
with network provenance required, then independently performs a regular-file,
non-symlink read bounded to 8 MiB plus one byte and rechecks raw size and hash:

```powershell
python -m scripts.build_fotmob_fixture_candidates `
  --capture-directory .cache/athena-research/fotmob-data-matches-captures/20260815/76d18629482ffda786e6b58e `
  --capture-directory .cache/athena-research/fotmob-data-matches-captures/20260816/54d0dd608289edd7cf40aedc
```

Standard output contains one canonical summary with only source request dates,
counts, and the complete deterministic bundle SHA-256. It contains no candidate
rows, source IDs, names, or kickoffs. The complete bundle is available through
the domain API for reproducible testing and future review, but is not persisted
by this boundary.

Cross-capture conflict reporting never grants identity resolution authority.
The artifact safety map remains all exact `false`. Any future Fixture Catalog
bridge, source qualification, team resolution, status/score interpretation, or
downstream use requires a separate reviewed change.
