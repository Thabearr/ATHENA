# SportyBet ↔ FotMob partial-calendar reconciliation candidate

## Purpose

PR #158 can qualify a specific preserved SportyBet event display clock as `GMT` while deliberately leaving its year unknown. This boundary uses that exact result against already-reviewed FotMob fixture catalog inputs without smuggling a year into the SportyBet evidence.

A unique match is still only a **candidate**. It does not prove the SportyBet year and does not authorize production fixture reconciliation.

No SportyBet or FotMob network request is introduced by this boundary.

## Exact input chain

The SportyBet side is not trusted by an object type or hash alone. The supplied PR #158 artifact is deterministically rebuilt from:

`exact PR #153 event manifest + exact PR #154 native inventory + exact preserved event HTML`

plus

`exact PR #157 Terms qualification + exact preserved Terms HTML`

through the PR #158 builder. The supplied and rebuilt PR #158 canonical bytes must be identical.

The FotMob side accepts only `FotMobReviewedFixtureCatalogInput` values that have already crossed the existing explicit FotMob fixture-review gate. Duplicate source fixture identifiers fail closed.

## Frozen matching rule

For each reviewed FotMob fixture, ATHENA compares the following values with exact case-sensitive equality:

- SportyBet home display name = FotMob home team;
- SportyBet away display name = FotMob away team;
- SportyBet competition display = FotMob competition;
- SportyBet GMT day = FotMob UTC day;
- SportyBet GMT month = FotMob UTC month;
- SportyBet displayed weekday = deterministic FotMob UTC weekday;
- SportyBet GMT hour = FotMob UTC hour;
- SportyBet GMT minute = FotMob UTC minute.

The FotMob kickoff itself must have exactly zero seconds and zero microseconds. A non-minute-aligned FotMob timestamp does not match. This is deliberate: `20:00` on the SportyBet page is not evidence that ATHENA may round or tolerate a FotMob `20:00:30` timestamp.

There is:

- no fuzzy team matching;
- no alias table;
- no case folding;
- no home/away reversal;
- no fuzzy competition matching;
- no kickoff tolerance;
- no year inference.

The year component of the FotMob timestamp is intentionally omitted from the equality key because PR #158 has not proven a SportyBet year.

## Dispositions

The deterministic result is one of:

- `UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN` — exactly one reviewed FotMob row matches every frozen partial-calendar and text field;
- `NO_EXACT_PARTIAL_CALENDAR_MATCH` — zero rows match;
- `AMBIGUOUS_EXACT_PARTIAL_CALENDAR_MATCH` — two or more reviewed rows match and ATHENA refuses to choose one.

A unique candidate may record the matched FotMob fixture's full trusted kickoff and therefore its FotMob year. That **does not promote that year into the SportyBet evidence**. The output continues to carry:

- `sportybet_kickoff_year = null`;
- `sportybet_kickoff_utc = null`;
- `sportybet_year_proven = false`.

This distinction prevents a unique search result from becoming circular proof of the missing SportyBet year.

## Why ambiguity matters

The same teams and competition can in principle meet on the same day/month and displayed time in different years, or duplicate reviewed fixture rows may otherwise satisfy the partial identity. Since the SportyBet year is still unknown, ATHENA must not silently pick a year from the FotMob population.

If multiple rows satisfy the exact frozen key, the result is explicitly ambiguous and no matched fixture is emitted.

## What remains blocked

This boundary does **not** authorize:

- SportyBet network acquisition;
- SportyBet year inference or year resolution;
- production SportyBet ↔ FotMob fixture reconciliation;
- bookmaker equivalence;
- canonical market mapping;
- fresh-price claims;
- model integration or value calculation;
- selection;
- ACCA/slip construction;
- booking-code generation;
- SportyBet execution;
- `BET`.

Every corresponding safety field remains exact `false`.

## Next evidence boundary

A unique partial-calendar candidate is useful evidence, but the missing year must still be resolved by a separately reviewed, non-circular source or provider-native identity mechanism before `fixture_reconciliation_authorized` can ever change. If the real evidence remains ambiguous, ATHENA stays fail-closed rather than using calendar proximity or current-year assumptions.
