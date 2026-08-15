# FotMob `primaryId` competition-mapping qualification

## Purpose

This boundary executes the competition-family identity semantics pre-registered
by PR #107 against the **already preserved** PR #105 FotMob source-history
campaign evidence.

No new FotMob network acquisition occurs. The reviewed GitHub Actions artifact
is downloaded only as immutable evidence and is rejected unless its exact
SHA-256 and byte size match the frozen PR #105 receipt.

This boundary qualifies one fact only:

> For the initial eleven domestic-league research families, FotMob `primaryId`
> is qualified as the stable **FotMob source-scoped competition-family
> identity** across the preserved 2020-08-01 through 2026-08-14 campaign.

It does not make `primaryId` a global cross-provider identifier and it does not
authorize model training, calibration, pricing, selection, production, or
betting.

## Exact evidence ancestry

The qualification starts from merged main:

`72cfd3aea494b85188e625328f8f49d379dbdf23`

The PR #107 canonical protocol remains:

- SHA-256:
  `6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e`
- size: `7,370` bytes
- blob:
  `649fe1b28693ac283e0fb0f93f1554c12b77f19e`

The PR #105 completeness receipt remains:

- SHA-256:
  `a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363`
- size: `11,995` bytes

The preserved GitHub Actions campaign artifact is exactly:

- artifact ID: `9249856559`
- name:
  `fotmob-ordinary-ft-source-history-campaign-31887523012`
- size: `61,886,753` bytes
- SHA-256:
  `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`

The embedded research cache is exactly:

- size: `61,881,610` bytes
- SHA-256:
  `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`

The artifact contains all `4,410` response files across all `2,205` required UTC
request dates.

## Reproduction method

`scripts/qualify_fotmob_primary_id_competition_mapping.py` performs the reviewed
qualification.

The script:

1. verifies the exact campaign ZIP hash and size before reading it;
2. extracts and re-verifies the exact `athena-research-cache.tar.gz`;
3. reads every preserved `response.json` file;
4. selects only the eleven PR #107 initial `primaryId` candidates;
5. records every target top-level league observation with request date, capture
   ID, country code, wrapper `league.id`, display name, `parentLeagueId`,
   match count, and every observed match `leagueId`;
6. deterministically sorts and canonicalizes those observations;
7. checks the resulting wrapper/name counts against PR #105;
8. rejects wrapper ownership conflicts, parent/primary conflicts, match-wrapper
   identity conflicts, and country-lineage conflicts;
9. emits the canonical qualification receipt.

The complete mapping-evidence projection contains `15,088` target league-object
observations and has:

- SHA-256:
  `05a468ad53d3feea1b7072bafea1c0b91e6e1ceeccdf0f1edfe031359a369d3a`
- size: `3,361,516` bytes

The checked-in canonical qualification receipt has:

- SHA-256:
  `fdb55feef9585fe0aa2668ddb9ac9a6eb8e63ac8870c06cdb7917d1f996e7bc9`
- size: `13,681` bytes

## Result

All eleven initial families qualify.

| ATHENA code | `primaryId` | Country | wrapper IDs | name variants | Result |
|---|---:|---|---:|---:|---|
| B1 | 40 | BEL | 25 | 11 | QUALIFIED |
| D1 | 54 | GER | 1 | 2 | QUALIFIED |
| E0 | 47 | ENG | 1 | 1 | QUALIFIED |
| F1 | 53 | FRA | 1 | 1 | QUALIFIED |
| G1 | 135 | GRE | 20 | 4 | QUALIFIED |
| I1 | 55 | ITA | 1 | 2 | QUALIFIED |
| N1 | 57 | NED | 13 | 3 | QUALIFIED |
| P1 | 61 | POR | 1 | 2 | QUALIFIED |
| SC0 | 64 | SCO | 19 | 3 | QUALIFIED |
| SP1 | 87 | ESP | 1 | 1 | QUALIFIED |
| T1 | 71 | TUR | 1 | 1 | QUALIFIED |

Every candidate is observed only with its exact expected domestic country code.
Every match-level `leagueId` is accounted for by its containing observed wrapper
`league.id`. Any observed `parentLeagueId` for the initial candidates is exactly
the candidate `primaryId`.

The conflict counts are all zero:

- wrapper/`primaryId` conflicts: `0`
- parent/`primaryId` conflicts: `0`
- match/wrapper identity conflicts: `0`
- country conflicts: `0`
- competition-class conflicts: `0`
- primary-ID collisions: `0`

## Why wrapper and name drift now passes

PR #105 correctly blocked the mapping because PR #101 had never authorized
`primaryId` as the stable family field.

PR #107 froze the rule **before** this qualification was executed. Under that
rule, wrapper `league.id` and display-name changes are permitted only if the
preserved evidence proves stable `primaryId` lineage and no semantic conflict.

That is exactly what the full campaign shows.

Examples:

- Belgium (`B1`) spans 25 wrapper IDs and 11 display names, including normal
  league and playoff presentation variants, while retaining `primaryId=40` and
  `ccode=BEL`.
- Greece (`G1`) spans 20 wrapper IDs and four names while retaining
  `primaryId=135` and `ccode=GRE`.
- Netherlands (`N1`) spans 13 wrapper IDs and three exact name variants,
  including the source's non-breaking-space spelling
  `Eredivisie ECL Playoff`, while retaining `primaryId=57` and `ccode=NED`.
- Scotland (`SC0`) spans 19 wrapper IDs and three names while retaining
  `primaryId=64` and `ccode=SCO`.

The direct-root families remain simple: Bundesliga, Premier League, Ligue 1,
Serie A, Liga Portugal, LaLiga, and Super Lig each use their root `primaryId` as
the observed wrapper ID in this campaign.

## The eleven leagues are still not ATHENA's final universe

This qualification does **not** convert the initial proof set into a permanent
whitelist.

PR #107's generic competition classes remain intact for later reviewed
expansion to:

- additional domestic leagues;
- domestic cups;
- domestic league cups;
- UEFA Champions League;
- UEFA Europa League;
- UEFA Conference League;
- other continental club competitions;
- international tournaments;
- international qualifiers;
- international friendlies.

Those competition families are not rejected. They are simply not promoted by
this eleven-family qualification receipt.

## Remaining blockers

Mapping qualification is now proven, but historical source completeness is
still **not** proven.

The following blockers remain exactly fail-closed:

- `BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW`
- `BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`
- `BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN`
- `BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

The 25 awarded wins, three after-extra-time fixtures, three after-penalties
fixtures, unresolved non-result states, 250 rearranged/kickoff-changing fixture
IDs, and PR #69 initialization-equivalence boundary are not silently resolved by
competition mapping.

## Next reviewed boundary

`PRE_REGISTER_REVIEWED_FOTMOB_SOURCE_HISTORY_SPECIAL_RESULT_SEMANTICS_PROTOCOL`

That boundary must be frozen before special-result evidence is dispositioned.

## Safety

`mapping_qualification_proven` is the only promoted fact in this boundary.

No competition registry is mutated. No source capability registry is mutated.
Historical coverage remains false. The broader competition universe remains
unqualified. Every model, calibration, expected-goals, probability, pricing,
market activation, selection, production, and BET authorization flag remains
exact `false`.
