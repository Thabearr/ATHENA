# Reviewed Fixture Catalog admission

## Purpose

PR #45 adds the first explicit **Fixture Catalog admission/promotion boundary** for the reviewed FotMob `/api/data/matches` path.

PR #43 proved that explicit PR #41 review decisions could be rebuilt through the PR #42 handoff and compiled by the hardened PR #29 Fixture Catalog compiler. PR #44 then registered one narrowly scoped capability identity:

```text
fotmob_data_matches_reviewed_catalog
```

with only:

```text
reliable_fixture_identity = CONFIRMED
```

PR #45 does not broaden that claim. It decides whether one exact compiled reviewed catalog is admitted for later source-scoped fixture-identity use.

## Explicit disposition

The catalog-level decision is one of:

```text
ADMITTED
REJECTED
```

There is no default admission, threshold admission, approve-all mode, or inference from a successful compiler run.

An admission decision must anchor all of these exact SHA-256 values:

- PR #40 candidate bundle;
- PR #41 review bundle;
- PR #42 reviewed handoff;
- PR #29 strict catalog bytes;
- PR #29 manifest bytes.

It must also identify the exact source capability key `fotmob_data_matches_reviewed_catalog`, carry a timezone-aware UTC review timestamp, a non-empty trimmed reviewer reference, and notes.

## Revalidation before admission

The domain gate does not trust a `FixtureCatalogResult` merely because it has the right Python type. It independently rechecks:

1. the reviewed source-capability registration still exists and still has `reliable_fixture_identity = CONFIRMED`;
2. compiler records are non-empty, exact provenance records, and remain deterministically sorted;
3. compiler `as_of`, minimum lead time, clean-worktree flag, and generator commit satisfy the frozen contract;
4. every record remained reviewed before compiler `as_of` and satisfied its declared lead time;
5. normalized provenance JSONL bytes and SHA-256 are rebuilt exactly from the records;
6. the strict catalog object and canonical bytes are rebuilt exactly;
7. the manifest object and canonical bytes are rebuilt exactly;
8. every compiler provenance field still matches the exact PR #42 reviewed handoff input: source fixture ID, team names, competition, kickoff, source reference, review timestamp, evidence path, and evidence SHA-256;
9. the catalog-level decision hashes exactly match the revalidated handoff/catalog/manifest chain.

This deliberately repeats critical reconciliation at the promotion boundary rather than trusting an earlier successful run by assertion alone.

## ADMITTED semantics

`ADMITTED` exposes every and only compiled fixture identity and kickoff, in deterministic compiler order:

```json
{
  "fixture_identifier": "FOTMOB:<source match id>",
  "kickoff": "<UTC timestamp>"
}
```

The admission review timestamp must not predate compiler `as_of` or any upstream fixture review. The entire admitted catalog must still be prospective at admission time; if the earliest fixture has started, `ADMITTED` fails closed and a fresh reviewed catalog is required.

This is still only a **source-scoped fixture identity admission**. It does not establish global team identity, competition identity, lineup identity, source completeness, score meaning, event-timeline meaning, or source freshness.

## REJECTED semantics

`REJECTED` emits zero admitted fixture identities. A rejection may be recorded after kickoff because it cannot promote anything.

## Canonical admission artifact

The admission object serializes as compact, sorted, UTF-8 JSON with `allow_nan=False` and one final newline. The serialized form records:

- schema and dataset identity;
- source-capability key;
- candidate/review/handoff/catalog/manifest hashes;
- compiler normalized-input hash;
- generator commit;
- compiler `as_of` and minimum lead time;
- compiled and admitted fixture counts;
- exact catalog-level decision;
- admitted source-scoped fixture identities when disposition is `ADMITTED`;
- downstream safety flags.

The canonical admission SHA-256 therefore changes if any admitted fixture, upstream evidence identity, compiler artifact, or operator decision changes.

## Safety boundary

All downstream authorization flags remain exact `False` and immutable:

- no network acquisition;
- no raw recapture;
- no automatic review;
- no broader source qualification;
- no global identity resolution;
- no Fixture Intelligence fact authorization;
- no model-feature authorization;
- no probability authorization;
- no pricing authorization;
- no selection authorization;
- no betting authorization.

PR #45 performs no file output and registers no global runtime consumer. A later separately reviewed PR may define how a canonical `ADMITTED` artifact is persisted/verified and then used as the only legal fixture-identity bootstrap for Fixture Intelligence. That later work must not convert catalog admission into evidence support for any intelligence fact.