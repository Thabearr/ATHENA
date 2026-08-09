# Offline FotMob data-matches schema assessment

## Purpose and boundary

PR #38 preserved the exact unsigned `/api/data/matches` response as raw bytes.
PR #39 assesses a verified PR #38 capture offline against one narrowly frozen
structural schema. It emits ancestry, counts, deterministic key-set metadata,
zero mismatch counts, and structural capability labels. It emits no fixture
record, match or team identifier, name, kickoff, score, or status reason.

Structural presence is not semantic trust. Schema conformity does not qualify
FotMob as a trusted source. `SOURCE_CAPABILITY_REGISTRY["fotmob_unofficial"]`
remains `UNKNOWN`, and this boundary creates no fixture candidate, catalog
record, intelligence fact, model feature, probability, price, selection, or
betting behavior.

The process is entirely offline:

```text
verified PR #38 capture
    -> independent bounded response.json read
    -> strict UTF-8 and strict JSON decoding
    -> exact reviewed structure, type, identity, and linkage checks
    -> metadata-only canonical assessment
    -> possible future separately reviewed PR #40
```

There is no URL, network flag, HTTP dependency, asset retrieval, fallback, or
file output. The CLI first invokes PR #38's capture-directory verifier with
network provenance required, then independently reads `response.json` at most
8 MiB plus one byte and rechecks its size and SHA-256.

## Source ancestry

The one reviewed source capture is:

```text
.cache/athena-research/fotmob-data-matches-captures/
    20260815/76d18629482ffda786e6b58e/
```

Its raw response is 314098 bytes with SHA-256
`6eabfb341d29f3b5db0833972a9aaf7dbd97df150ccecde09f6f67396bc73b27`.
Its canonical PR #38 manifest SHA-256 is
`3fe1d24a0738114c46114a815eca44c4221b53fe8da2476d5a487153ce72d145`.
The request identity is date `20260815`, timezone `UTC`, and country code
`NGA`.

Every assessment anchors the exact source capture dataset/schema, canonical
manifest SHA-256, raw SHA-256 and size, acquisition observation time, and
request identity. `source_observed_at` is ATHENA acquisition provenance; it is
not FotMob source freshness.

## Observed in the one reviewed capture

The response top level is an object with `leagues` followed by `date`. It has
150 league/group objects and 630 records at
`$["leagues"][i]["matches"][j]`. Those counts, the observed range of matches
per group, and the observed status distribution are observations only. They
are not V1 constants and are not required of another capture.

All 630 match IDs are non-null integers and globally unique. Every
`match.leagueId` equals its containing `league.id`. Every
`status.utcTime` is a parseable UTC ISO-8601 value ending in `Z`, every
`timeTS` is an integer epoch-millisecond value exactly matching it, and all
authoritative UTC dates are 2026-08-15. Display `time` values can spill into
August 16 and are not authoritative for request-date linkage.

All team `score` values are structurally integers, but the capture contains no
reviewed started/finished evidence that establishes their football meaning.
Full-time score capability is therefore `AMBIGUOUS`. No half-time score field
or source-provided freshness field occurs.

## V1 structural contract

Strict parsing requires valid UTF-8 JSON, rejects duplicate keys at every
level, rejects NaN and infinities, and requires an exact top-level object with
only:

| Field | Frozen domain |
| --- | --- |
| `date` | non-null exact string, equal to the manifest request date |
| `leagues` | non-null array |

No league count or match count is hardcoded. A conforming league may have an
empty `matches` array.

### League/group objects

Required keys are exactly:

```text
ccode
id
internalRank
matches
name
primaryId
simpleLeague
```

Optional keys are exactly:

```text
groupName
isGroup
localRank
parentLeagueId
parentLeagueName
```

The complete frozen domains are:

| Field | Presence | Frozen JSON type/null domain |
| --- | --- | --- |
| `ccode` | required | string, non-null |
| `id` | required | integer, non-null; Boolean rejected |
| `internalRank` | required | integer, non-null; Boolean rejected |
| `matches` | required | array, non-null |
| `name` | required | string, non-null |
| `primaryId` | required | integer, non-null; Boolean rejected |
| `simpleLeague` | required | Boolean, non-null |
| `groupName` | optional | string, non-null when present |
| `isGroup` | optional | Boolean, non-null when present |
| `localRank` | optional | integer, non-null when present; Boolean rejected |
| `parentLeagueId` | optional | integer, non-null when present; Boolean rejected |
| `parentLeagueName` | optional | string, non-null when present |

Names, country-code meaning, hierarchy, and ranking semantics are not inferred.
An unreviewed league key or type fails closed.

### Match and team objects

Every non-empty match object must have exactly these ten keys:

```text
away eliminatedTeamId home id leagueId status statusId time timeTS tournamentStage
```

`id`, `leagueId`, `statusId`, and `timeTS` are exact non-null integers with
Boolean rejected. `time` and `tournamentStage` are exact non-null strings.
`eliminatedTeamId` is frozen to JSON null only. `home`, `away`, and `status`
are objects. Match IDs must be globally unique within the payload, and
`leagueId` must equal the containing league object's exact integer `id`.
Tournament-stage and elimination semantics remain unreviewed.

Each `home` and `away` object has exactly:

| Field | Frozen domain |
| --- | --- |
| `id` | integer, non-null; Boolean rejected |
| `score` | integer, non-null; Boolean rejected |
| `name` | string, non-null |
| `longName` | string, non-null |

Repeated team IDs and names are permitted. Score values are not renamed or
interpreted as current, full-time, or result scores.

### Status, halves, and reason objects

The exact status union is:

```text
aggregatedStr cancelled finished halfs periodLength reason started utcTime
```

The exact status intersection and required key set is:

```text
cancelled finished halfs periodLength started utcTime
```

The frozen domains are:

| Field | Presence | Frozen JSON type/null domain |
| --- | --- | --- |
| `utcTime` | required | string, non-null; reviewed UTC timestamp contract |
| `halfs` | required | object, non-null |
| `periodLength` | required | integer, non-null; Boolean rejected |
| `started` | required | Boolean, non-null |
| `cancelled` | required | Boolean, non-null |
| `finished` | required | Boolean, non-null |
| `aggregatedStr` | optional | string, non-null when present |
| `reason` | optional | object, non-null when present |

`halfs` has the exact union and intersection `{firstHalfStarted}`; its value is
a non-null exact string. It is not interpreted. Any future half-time score key
is unreviewed and fails closed.

When present, `reason` has exactly `long`, `longKey`, `short`, and `shortKey`,
all non-null exact strings. These strings do not create a semantic status enum.
`aggregatedStr` does not create score semantics.

### Kickoff consistency

`status.utcTime` is the authoritative structural kickoff candidate. V1
requires a valid ISO-8601 UTC date-time ending in exact `Z`, with precision
compatible with integer epoch milliseconds. The assessor derives epoch
milliseconds using integer day/second/microsecond arithmetic and requires an
exact match with `timeTS`. The UTC calendar date must equal both payload
`date` and manifest request date. Invalid timestamps, mismatches, duplicate
match IDs, linkage conflicts, and all changed keys/types/nullability fail
closed without repair, deduplication, or conflict resolution.

Display `time` is validated only as a non-null string. It is not parsed and
its displayed calendar date is not required to equal the UTC request date.

## Assessment meaning and future work

For a conforming capture with match records, V1 reports structural fixture,
kickoff, team, competition-linkage, and status candidates as
`PRESENT_IN_CAPTURE`; score as `AMBIGUOUS`; and half-time score and source
freshness as `ABSENT_IN_CAPTURE`. These labels describe only the assessed
capture. They are not `VERIFIED`, `TRUSTED`, or `QUALIFIED` source capability.

The canonical assessment is compact sorted UTF-8 JSON with a final newline and
`allow_nan=False`. Key-set metadata is sorted deterministically. It contains no
fixture values. A later independently reviewed PR #40 may consider generating
explicitly `UNREVIEWED` fixture candidates, but PR #39 neither defines nor
generates them.
