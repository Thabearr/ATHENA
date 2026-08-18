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
9. exact PR #162 kickoff-identity promotion.

The FotMob side must also provide:

10. an exact `ReviewedFixtureCatalogAdmission` with `ADMITTED` disposition; and
11. the exact raw FotMob `/api/data/matches` capture bytes and PR #38 capture manifests from which that admitted catalog was derived.

PR #162 is revalidated at consumption time from every preserved upstream source and must be canonical-byte identical. Hash-shaped or manually constructed promotion objects are not trusted.

The FotMob admission is not trusted merely because it contains structurally valid reviewed rows. ATHENA rebuilds the candidate bundle from the supplied raw capture bytes/manifests, rebuilds the review bundle from those candidates plus the admission's exact human review decisions, rebuilds the catalog handoff, and requires canonical equality with the handoff embedded in the admitted catalog. The admission itself then revalidates its compiled catalog, decision hashes, prospective admission chronology, and the current reviewed-source capability profile.

This closes the authority gap that would otherwise allow a caller to manufacture a hash-shaped `FotMobReviewedFixtureCatalogInput` and obtain fixture reconciliation authority.

## Exact matching rule

An admitted FotMob row matches only when all four values are exact and case-sensitive:

- home team = SportyBet machine-readable home display;
- away team = SportyBet machine-readable away display;
- competition = SportyBet machine-readable competition display;
- FotMob UTC kickoff = the exact provider-resolved SportyBet UTC instant from PR #162.

The UTC comparison is an exact instant comparison. Provider seconds and microseconds preserved by PR #162 remain significant. `20:00:37.123456Z` does not match `20:00:00Z`, `20:00:37Z`, or any nearby time.

No normalization, case folding, punctuation cleanup, fuzzy name matching, alias inference, home/away reversal, nearest-fixture choice, kickoff tolerance, or rounding is authorized.

## FotMob population integrity

The comparison population comes only from the source-replayed `ADMITTED` reviewed catalog handoff. Standalone `FotMobReviewedFixtureCatalogInput` objects are not a public authority input to this boundary.

The full admitted comparison population is sorted by numeric `source_fixture_identifier` and canonically hashed, so ordering cannot alter lineage. Duplicate FotMob source fixture identifiers fail closed before matching.

The result preserves the exact hashes of the FotMob admission, candidate bundle, review bundle, handoff, compiled catalog, compiled manifest, and comparison population.

## Dispositions and authority

There are exactly three dispositions:

- `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`: exactly one source-replayed admitted FotMob row matches all four exact fields. The exact matched FotMob lineage is preserved and `fixture_reconciliation_authorized` becomes `true` for this result only.
- `NO_EXACT_FULL_UTC_MATCH`: zero admitted rows match. No fixture reconciliation authority is granted.
- `AMBIGUOUS_EXACT_FULL_UTC_MATCH`: multiple admitted rows match exactly. ATHENA chooses none and grants no fixture reconciliation authority.

A unique exact result promotes only the SportyBet↔FotMob fixture-reconciliation capability. It does not promote bookmaker market equivalence or any pricing/selection capability.

## What remains blocked

Even after a unique exact fixture reconciliation, this boundary does not authorize:

- SportyBet, Sportradar, or FotMob network acquisition;
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

`revalidate_full_utc_reconciliation()` replays both trust chains again: PR #162 from preserved SportyBet/Terms/Sportradar sources and the FotMob admission from raw captures through candidate extraction, exact human review decisions and handoff. It then rebuilds the reconciliation and requires canonical byte-for-byte equality with the supplied result.

A coordinated forged result with plausible hashes therefore cannot acquire fixture-reconciliation authority unless it is the deterministic derivative of both preserved source chains.

## Next boundary

After a real event receives `UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED`, ATHENA may work on exact SportyBet canonical market/selection mapping for that reconciled fixture.

If real SportyBet and FotMob participant or competition labels differ, this boundary must continue to fail closed. Any provider alias handling must be introduced separately as an explicit reviewed alias contract; fuzzy matching must not be smuggled into reconciliation.
