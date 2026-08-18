# SportyBet -> FotMob exact fixture reconciliation candidate

## Purpose

PR #154 makes exact SportyBet provider-native event/market/outcome/odds evidence machine-readable from reviewed user-controlled HTML. The remaining blocker before those odds can be attached to ATHENA's trusted football fixture is event identity.

The reviewed SportyBet Lite HTML contract still does not prove machine-readable competition, participant or kickoff fields. The visible page can show those values, but ATHENA has not yet proven a provider-native structural association for them. This boundary therefore does **not** invent one.

Instead it freezes a deliberately conservative reconciliation-candidate contract:

`verified PR #154 SportyBet event/odds inventory -> explicit user-attested visible event header -> exact comparison against reviewed FotMob catalog inputs -> reconciliation candidate`

The result is research evidence only. `fixture_reconciliation_authorized` remains false.

## Why user-attested metadata is separate

The SportyBet event ID and odds remain bound to exact reviewed HTML bytes through the PR #154 inventory SHA-256. The competition name, home participant, away participant and displayed kickoff are captured separately with authority:

`USER_ATTESTED_FROM_REVIEWED_SPORTYBET_PAGE`

The user also supplies the corresponding UTC kickoff explicitly. ATHENA does not silently assume a timezone from the Nigeria site, convert the displayed time behind the user's back, or claim that the displayed time is a provider quote timestamp.

This separation is important: the SportyBet event/market/odds evidence is provider-native; the event header association is still user-attested until a machine-readable SportyBet representation is proven.

## Exact matching rule

The frozen matching basis is:

`EXACT_HOME_AWAY_COMPETITION_KICKOFF_NO_FUZZY_NO_REVERSAL`

A reviewed FotMob catalog input is an exact candidate only when all four fields are exactly equal:

1. SportyBet displayed home participant == FotMob reviewed home team;
2. SportyBet displayed away participant == FotMob reviewed away team;
3. SportyBet displayed competition == FotMob reviewed competition;
4. user-attested SportyBet kickoff UTC == FotMob reviewed kickoff UTC.

There is no fuzzy matching, token similarity, case folding, nickname inference, alias guessing or home/away reversal.

Examples:

- `Newcastle` does **not** silently equal `Newcastle United`;
- `Liverpool vs Newcastle` does not match `Newcastle vs Liverpool`;
- a one-minute kickoff difference does not match;
- an otherwise identical fixture in a different competition does not match.

If exactly one reviewed FotMob row matches, the disposition is:

`EXACT_MATCH_CANDIDATE_USER_ATTESTED`

If none match:

`NO_EXACT_MATCH`

If more than one reviewed FotMob fixture is exactly identical on the frozen comparison fields:

`AMBIGUOUS_EXACT_MATCH`

ATHENA never chooses one arbitrarily.

## Lineage

The user-attested SportyBet identity records:

- exact PR #154 source evidence ID;
- exact PR #154 native inventory SHA-256;
- exact preserved SportyBet raw HTML SHA-256;
- exact SportyBet event-detail source URL;
- exact provider event ID and sport ID;
- displayed competition/home/away/kickoff strings;
- explicit user-attested UTC kickoff;
- original user-attested SportyBet observation time;
- explicit identity authority.

The reconciliation candidate additionally records:

- SHA-256 of the complete SportyBet identity record;
- SHA-256 of the complete reviewed FotMob fixture population used for comparison;
- exact match count;
- exact matched FotMob source fixture identity and its capture/candidate/evidence hashes when there is one unique match;
- the frozen matching basis;
- all downstream authority flags as false.

The FotMob population hash is deterministic and independent of caller ordering.

## Product safety

This boundary does not change `BettingService` and does not authorize:

- production SportyBet fixture reconciliation;
- bookmaker equivalence;
- canonical ATHENA market mapping;
- provider quote freshness;
- pricing/value;
- model integration;
- selection;
- ACCA/slip construction;
- SportyBet booking-code generation;
- SportyBet execution;
- `BET`.

An exact candidate therefore means only:

> the user-attested visible SportyBet event header exactly agrees with one already-reviewed FotMob fixture on the frozen fields.

It does **not** mean ATHENA has proven a provider-machine-readable SportyBet fixture identity.

## Why this still advances the odds path

The SportyBet odds remain attached to the provider event through the PR #154 inventory. Once an exact reconciliation candidate exists, the downstream architecture has a deterministic event-level join key available for review without changing or re-parsing the odds.

That preserves the intended chain:

`SportyBet event + exact native odds -> reviewed fixture identity -> canonical market equivalence -> fresh-price proof -> model/value -> selection -> ACCA/slip -> booking code`

No downstream gate is skipped.

## Next boundary

The next bookmaker trust task is to replace the user-attested SportyBet event header with a reviewed machine-readable provider event-metadata source, or to freeze explicit reviewed cross-provider aliases where exact provider/FotMob names differ.

Only after that stronger identity evidence is reviewed should `fixture_reconciliation_authorized` be considered for promotion. The booking-code mechanism remains a separate later boundary after exact selection/slip construction is proven.
