# SportyBet ↔ FotMob full-UTC reconciliation

## Purpose

PR #162 promoted one reviewed SportyBet event's previously missing year and complete UTC kickoff only after the exact SportyBet GMT partial calendar, the exact SportyBet→Sportradar event-ID bridge, and confirmed official Sportradar metadata all independently rederived and agreed.

This boundary uses that provider-resolved full UTC to revisit SportyBet ↔ FotMob fixture reconciliation without any calendar guess, fuzzy alias, participant reversal, kickoff rounding, or tolerance.

## Exact source chain

A reconciliation attempt must receive the complete preserved source chain required by PR #162 again:

1. exact PR #153 SportyBet user-controlled evidence manifest;
2. exact PR #154 native inventory;
3. exact preserved SportyBet event HTML;
4. exact PR #157 Terms qualification and exact Terms HTML;
5. exact PR #158 event-local GMT qualification;
6. exact PR #160 SportyBet/Sportradar event-ID bridge;
7. exact PR #161 official Sportradar metadata evidence;
8. exact preserved Sportradar JSON response;
9. exact PR #162 kickoff-identity promotion;
10. one deterministic population of already-reviewed `FotMobReviewedFixtureCatalogInput` rows.

PR #162 is revalidated at consumption time from every preserved upstream source and must be canonical-byte identical. Hash-shaped or manually constructed promotion objects are not trusted.

## Exact matching rule

A FotMob row matches only when all four values are exact and case-sensitive:

- home team = SportyBet machine-readable home display;
- away team = SportyBet machine-readable away display;
- competition = SportyBet machine-readable competition display;
- FotMob UTC kickoff = the exact provider-resolved SportyBet UTC instant from PR #162.

The UTC comparison is an exact instant comparison. Provider seconds and microseconds preserved by PR #162 remain significant. `20:00:37.123456Z` does not match `20:00:00Z`, `20:00:37Z`, or any nearby time.

No normalization, case folding, punctuation cleanup, fuzzy name matching, alias inference, home/away reversal, nearest-fixture choice, kickoff tolerance, or rounding is authorized.

## FotMob population integrity

Only exact `FotMobReviewedFixtureCatalogInput` objects are accepted. The full comparison population is sorted by numeric `source_fixture_identifier` and canonically hashed, so caller ordering cannot alter lineage.

Duplicate FotMob source fixture identifiers fail closed before matching.

## Dispositions and authority

There are exactly three dispositions:

- `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`: exactly one reviewed FotMob row matches all four exact fields. The exact matched FotMob lineage is preserved and `fixture_reconciliation_authorized` becomes `true` for this result only.
- `NO_EXACT_FULL_UTC_MATCH`: zero rows match. No fixture reconciliation authority is granted.
- `AMBIGUOUS_EXACT_FULL_UTC_MATCH`: multiple reviewed rows match exactly. ATHENA chooses none and grants no fixture reconciliation authority.

A unique exact result promotes only the SportyBet↔FotMob fixture-reconciliation capability. It does not promote bookmaker market equivalence or any pricing/selection capability.

## What remains blocked

Even after a unique exact fixture reconciliation, this boundary does not authorize:

- SportyBet automated network acquisition;
- fuzzy or inferred provider aliases;
- canonical SportyBet market mapping;
- SportyBet provider quote timestamp or snapshot identity;
- fresh-price authority;
- pricing or value;
- model integration;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- BET.

All non-fixture downstream safety flags remain exact `false`.

## Consumption-time verification

`revalidate_full_utc_reconciliation()` rebuilds PR #162 from the complete preserved source chain, rebuilds the reconciliation against the exact reviewed FotMob population, and requires canonical byte-for-byte equality with the supplied result.

A coordinated forged result with plausible hashes therefore cannot acquire fixture-reconciliation authority unless it is the deterministic derivative of the preserved sources and exact FotMob population.

## Next boundary

After a real event receives `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`, ATHENA may work on exact SportyBet canonical market/selection mapping for that reconciled fixture.

If real SportyBet and FotMob participant or competition labels differ, this boundary must continue to fail closed. Any provider alias handling must be introduced separately as an explicit reviewed alias contract; fuzzy matching must not be smuggled into reconciliation.
