# FotMob ordinary-FT source-history campaign completeness receipt

## Purpose

This boundary records the immutable execution receipt for the reviewed FotMob
ordinary-FT source-history acquisition campaign and executes the previously
frozen source-history completeness gates against the preserved campaign
evidence.

It is an evidence receipt and fail-closed assessment only. It does **not**
modify source capabilities, materialize a production history adapter, construct
successor features, approve a model, infer probabilities, activate pricing or
selection, or authorize betting.

## Exact execution ancestry

The reviewed campaign executed from repository `main`:

`12a32de1cca8ffb657f67fa4a8d3106aec6ce31b`

GitHub Actions execution:

- run: `31887523012`
- job: `95018889294`
- control PR: `#103`
- authorization comment: `5302462991`
- durable attempt marker: `5302463691`
- terminal result comment: `5303209973`
- runner exit code: `0`
- network-free post-status exit code: `0`
- package outcome: `success`
- artifact upload outcome: `success`
- campaign verification outcome: `success`

The preserved Actions artifact is:

- artifact ID: `9249856559`
- name: `fotmob-ordinary-ft-source-history-campaign-31887523012`
- size: `61,886,753` bytes
- SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`

The nested research-cache archive is `61,881,610` bytes with SHA-256
`cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`.

## Campaign integrity

Independent offline revalidation of the downloaded artifact establishes:

- all `2,205` frozen UTC request dates from `2020-08-01` through `2026-08-14`
  are present;
- all `4,410` required successful slots are present;
- there are exactly `4,410` raw response files and `4,410` manifests;
- the failure journal contains `0` entries;
- the campaign index sequence is contiguous and its SHA-256 chain revalidates;
- every raw and manifest hash matches the campaign index;
- every manifest retains the frozen `timezone=UTC`, `ccode3=NGA` request
  identity;
- same-date A/B separation ranges from `3761.138022` to `7454.335835`
  seconds, inside the frozen 300-second to 86,400-second window.

The campaign index itself is `3,316,829` bytes with SHA-256
`f0b74711d9df352c5f845838014f72df96eeed0efa3c2740db7b7efb5818be1a`.

The acquisition campaign therefore succeeded completely. This fact does not,
by itself, establish historical source completeness.

## Eleven-league mapping discovery remains unproven

The corpus provides strong mapping **discovery evidence**, but the mapping gate
does not pass in this boundary.

All eleven frozen candidate root IDs are observed as FotMob `primaryId` values
with the expected country-code lineage:

| Model league | Frozen candidate root | Country |
|---|---:|---|
| B1 | 40 | BEL |
| D1 | 54 | GER |
| E0 | 47 | ENG |
| F1 | 53 | FRA |
| G1 | 135 | GRE |
| I1 | 55 | ITA |
| N1 | 57 | NED |
| P1 | 61 | POR |
| SC0 | 64 | SCO |
| SP1 | 87 | ESP |
| T1 | 71 | TUR |

The receipt preserves aggregate wrapper/name evidence and binds the full
discovery projection by SHA-256
`cd4e83157310cd9652c302f48d3e611867a6ad4e0616ddfe0e858863468c1e32`
(5,911 canonical bytes).

That evidence also shows why qualification must remain separate: Belgium,
Greece, the Netherlands, and Scotland expose season/playoff wrapper
`league.id` values while retaining the candidate root as `primaryId`, and
several display names vary across the interval.

PR #101 pre-registered a candidate `fotmob_league_id` plus name/country
mapping. It did **not** pre-authorize `primaryId` as the canonical cross-season
competition identity. Promoting the newly observed `primaryId` relationship
inside this post-result assessment would change the mapping semantics after
seeing the evidence.

Therefore the correct gate state is:

`BLOCKED_LEAGUE_MAPPING_UNPROVEN`

The `primaryId` plus country-code grouping used below remains discovery-only
until a separate reviewed protocol qualifies those semantics.

## Discovery-only corpus result

Using the frozen candidate root `primaryId` plus expected country lineage only
as a discovery grouping, the corpus contains:

- `21,388` unique source fixture IDs;
- `21,640` fixture-date occurrences;
- `21,336` unique fixtures that pass the reviewed ordinary-FT finished-score
  gate;
- `31` unique finished fixtures outside that reviewed semantic scope;
- `21` additional source fixtures that never produce an admissible finished
  ordinary-FT result inside the captured interval.

The deterministic ordinary-FT discovery projection is not committed. Its
canonical receipt anchor is:

- rows: `21,336`
- size: `14,997,331` bytes
- SHA-256: `5cec30f37dd58f654c94f4fb9190a7098683cee0d1ab073e179e6177b37ec8c8`

Within every same-date A/B pair there are zero fixture-presence, identity,
score, or reason drifts. There are also zero duplicate fixture IDs within a
capture, zero request-date/kickoff-UTC-date mismatches, zero duplicate
qualified-row identity keys, and zero same-team/same-kickoff ambiguity among
the discovery rows.

These facts do not override the unproven competition-mapping gate.

## Additional observed completeness blockers

The discovery grouping exposes `31` unique finished fixtures outside the
current reviewed ordinary-FT semantics:

- `25` unique awarded-win fixtures (`26` source-date observations because
  fixture `3932603` appears terminal on two scheduled dates);
- `3` after-extra-time fixtures;
- `3` after-penalties fixtures.

The current reviewed adapter deliberately does not reinterpret any of these as
ordinary full-time history. The tracked receipt preserves every blocker fixture
ID and binds the full fixture-level projection by SHA-256
`d5f70aad76424a01249365da09d450b4fb7f27f3d03ab546e8b9783784f5a96b`.

A further `21` source fixtures remain outside an admissible result row:
`13` abandoned, `6` cancelled, and `2` postponed. Their fixture IDs are
preserved and the full state projection is bound by SHA-256
`153cca2a970bce982eecab45c2df5fbaf1df099d081c45f7c3195bb1580b8593`.
They are not silently interpreted as zero-fixture dates.

These observations preserve:

`BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW`

## Identity and chronology is an observed blocker

Cross-date evidence shows `250` source fixture IDs whose kickoff changes across
request dates. Static source fixture/team/competition identity remains stable
for those IDs, but PR #101 froze a stricter rule: the same fixture ID across
captures must have stable teams, competition, **and kickoff**, or a conflict
must be raised.

The evidence therefore reaches an actual blocked state rather than merely an
unknown state:

`BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`

Fixture `3932603` is especially important: the same awarded source fixture
appears as terminal on two scheduled dates. A later boundary must explicitly
disposition rearranged/rescheduled evidence before replay can consume it.

## Initialization remains unproven

The frozen PR #69 Elo replay initialization equivalence also remains unproven.
The campaign begins at `2020-08-01`, but ATHENA does not infer equivalence merely
because the capture window is early enough. A positive initialization claim
requires replay from a complete admissible and correctly mapped FotMob history
rowset.

The state remains:

`BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN`

## Gate result

The campaign-execution, daily-date coverage, and already-reviewed derived score
capability gates pass.

The eleven-league mapping gate remains unproven because `primaryId` cross-season
semantics were discovered by this corpus rather than pre-qualified. The
finished-result and non-ordinary-result gates are blocked by the 31 observed
special finished fixtures. Identity/chronology is blocked by the 250 observed
kickoff changes pending explicit rearrangement disposition. The Elo
initialization boundary remains unproven.

The primary status is therefore:

`BLOCKED_LEAGUE_MAPPING_UNPROVEN`

and overall:

`historical_coverage_proven = false`

The source capability registry is not mutated and no history adapter is
materialized in this boundary.

## Canonical receipt

The corrected tracked canonical receipt is sorted compact UTF-8 JSON plus a
final newline:

- dataset:
  `athena-fotmob-ordinary-ft-source-history-campaign-completeness-receipt-v1`
- SHA-256:
  `a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363`
- size:
  `11,995` bytes

The large raw campaign artifact remains outside Git. The receipt binds it by
GitHub artifact identity, digest, nested research-cache digest, campaign-index
digest, and deterministic discovery-row projection digest.

## Next reviewed boundary

The smallest next boundary is:

`PRE_REGISTER_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_PROTOCOL`

That protocol should freeze, **before qualification**, exactly whether and under
what evidence conditions FotMob `primaryId` may bridge season/playoff wrapper
league IDs to one model-league family. It must bind country lineage, allowed
wrapper/name drift, collision behavior, and fail-closed ambiguity handling.

Only after that mapping semantic is reviewed should ATHENA proceed to the
already-discovered special-result/rearrangement dispositions and the later
PR #69 initialization-equivalence proof.

## Safety

Every downstream authorization remains exact `false`, including source-history
adapter approval, source-history completeness, PR #80 constructor input,
successor live-input qualification, successor/model approval, expected-goals
production use, score matrices, probability inference or adjustment, production
calibration, pricing, market activation, selection, production approval, and
betting.

A successful 4,410-capture acquisition is evidence. It is not downstream
authority.
