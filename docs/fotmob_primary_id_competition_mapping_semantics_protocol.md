# FotMob `primaryId` competition-mapping semantics protocol

## Purpose

This boundary pre-registers how ATHENA may interpret FotMob `primaryId` as a
**source-scoped competition-family identity** before any mapping is qualified
from the completed FotMob source-history campaign.

It is deliberately a protocol-only boundary. It performs no network request,
does not re-read or rewrite the large campaign artifact, does not mutate a
competition or source-capability registry, does not materialize source history,
and does not authorize model training, calibration, pricing, selection,
production, or betting.

## Why this boundary exists

PR #105 preserved a complete 4,410-slot campaign and exposed strong evidence
that the eleven frozen candidate root IDs appear as FotMob `primaryId` values
with the expected domestic country lineage. It also showed that season and
playoff `league.id` wrappers and some display names can vary.

PR #101 did not pre-authorize `primaryId` as the canonical cross-season mapping
field. ATHENA therefore correctly stopped at:

`BLOCKED_LEAGUE_MAPPING_UNPROVEN`

This PR freezes the semantic rules **before** a later qualification pass inspects
the preserved campaign evidence under those rules.

## The eleven leagues are not ATHENA's final universe

The eleven current mappings are the first controlled historical proof set:

| ATHENA code | FotMob `primaryId` | Country |
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

They are **not a permanent whitelist** and they are not the product boundary.

The generic competition identity contract explicitly leaves room for:

- additional domestic leagues;
- domestic cups;
- domestic league cups;
- continental club competitions;
- international tournaments;
- international qualifiers;
- international friendlies;
- other competition families that require separate review.

That means the architecture does not exclude the UEFA Champions League, Europa
League, Conference League, FA Cup and other domestic cups, or international
football. Those competitions are simply **not qualified by the initial
eleven-league evidence set**.

## Source identity semantics

The pre-registered rules are:

1. `primaryId` is a FotMob source-scoped competition-family identity candidate.
   It is not a global cross-provider ID.
2. `league.id` may represent a season, phase, playoff, or presentation wrapper.
   Wrapper changes are not automatically conflicts once a later qualification
   proves that all wrappers belong to one stable `primaryId` family.
3. Display names are metadata only. Name matching cannot establish identity.
4. Missing or malformed `primaryId` blocks qualification. ATHENA must not fall
   back to a convenient wrapper ID or name.
5. One `primaryId` cannot map to multiple incompatible ATHENA competition
   families.
6. Domestic mappings require the pre-registered country lineage.
7. Continental and international competitions must not inherit a domestic
   country rule. They require separately reviewed organizer/region and
   competition-class evidence.
8. Wrapper/name drift is acceptable only after the later evidence pass proves
   stable `primaryId` lineage and no collision or semantic conflict.
9. Any primary-ID collision, country conflict, or competition-class conflict
   fails closed.
10. Qualifying competition identity does not imply model/calibration/betting
    eligibility.

## Competition context remains separate

A stable competition family is only one layer of fixture meaning.

Later ATHENA layers must preserve competition-specific context such as stage,
phase, knockout round, first/second leg, aggregate state, neutral venue, and
tournament context. None of those fields may be inferred from `primaryId`
alone.

This matters particularly for Champions League knockouts, domestic cups, and
international tournaments where the same teams can behave very differently
from a normal domestic-league fixture.

## Unknown competitions are evidence, not garbage

A FotMob fixture from a competition outside the initial eleven is not silently
discarded and is not forced into the nearest known league code.

It may enter discovery as an unqualified competition candidate. If a later
downstream operation requires qualified competition identity, the operation
must fail closed until that competition family has been separately reviewed.

This is the expansion mechanism that allows ATHENA to grow beyond the first
eleven leagues without weakening identity discipline.

## Qualification boundary

The next reviewed boundary is:

`QUALIFY_REVIEWED_FOTMOB_PRIMARY_ID_COMPETITION_MAPPING_SEMANTICS_AGAINST_PRESERVED_CAMPAIGN_EVIDENCE`

That pass must use the already-preserved PR #105 campaign evidence. It may not
reacquire the internet corpus or alter these rules after seeing qualification
results.

For each initial candidate it must account for all observed wrapper
`league.id` values and display-name variants, match the exact expected country
lineage, detect collisions or contradictory family evidence, preserve every
conflict, and produce a deterministic canonical receipt.

Partial success must not promote historical coverage for any failed or
unqualified family.

## Boundaries deliberately not solved here

This protocol does not resolve the other blockers discovered by PR #105:

- awarded wins;
- after-extra-time results;
- after-penalties results;
- postponed/cancelled/abandoned result disposition;
- the 250 cross-date kickoff/rearrangement cases;
- PR #69 initialization-boundary equivalence.

Those remain separate reviewed boundaries.

## Exact protocol identity

- repository `main` at pre-registration:
  `6090bb46ef1a5662ddcec2761e3524647d83ba2e`
- PR #105 tracked receipt SHA-256:
  `a8c5a704e06853d6debfc029653132ca201b98c1fc8a32b3e3095db18f8e1363`
- PR #105 tracked receipt size: `11,995` bytes
- PR #101 protocol SHA-256:
  `cfd8542df66c9e8fbe748f0559d67c336d41e441f3b4de8d6601ac1087cad3a6`
- canonical PR #107 protocol SHA-256:
  `6d3e6083325853b481fe2a5ad928d67c5fe7cb46d25f5c33024146855c6e725e`
- canonical PR #107 protocol size: `7,370` bytes

## Safety

All authorization fields remain exact `false`.

This PR does not qualify `primaryId`, does not expand the approved competition
universe, does not prove historical coverage, does not approve a source-history
adapter, and does not authorize successor/model training, expected goals, score
matrices, probabilities, calibration, pricing, market activation, selection,
production, or BET.

The rule remains the same: a broader competition universe is achieved through
reviewed evidence, not by weakening the gates.
