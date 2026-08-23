# SportyBet semantic share-code gate

## Incident addressed

On 2026-08-23 ATHENA successfully created and reloaded a SportyBet booking code whose provider-native identities were internally consistent but represented a different 20-selection set than the human-readable ATHENA selections shown to the user. The direct-share transport behaved correctly; the missing boundary was semantic intent binding before provider-native IDs were submitted.

## New canonical booking-code path

For ATHENA-selected slips, use:

```text
scripts/sportybet_semantic_share_bridge.py
```

The semantic gate accepts fixture and provider-label intent only. It rejects caller-supplied `marketId`, `outcomeId`, and odds, resolves those IDs from the current SportyBet event payload, and only then delegates to `scripts/sportybet_direct_share_bridge.py` for create/load transport verification.

Required order:

```text
ATHENA intent
  -> exact SportyBet event identity
  -> exact home/away semantic identity
  -> safely pre-match/bookable state
  -> unique active market + exact specifier
  -> unique active outcome
  -> derive provider-native IDs
  -> SportyBet create
  -> SportyBet reload
  -> exact native identity round trip
```

A failure at any step stops before a booking code is accepted.

## Intent file shape

Each selection is represented as:

```json
{
  "eventId": "sr:match:123456",
  "homeTeamName": "Porto",
  "awayTeamName": "FC Arouca",
  "marketName": "1X2",
  "outcomeName": "Home",
  "specifier": null
}
```

Line markets carry the exact provider specifier, for example:

```json
{
  "eventId": "sr:match:123456",
  "homeTeamName": "Newcastle",
  "awayTeamName": "Liverpool",
  "marketName": "Over/Under",
  "outcomeName": "Over 1.5",
  "specifier": "total=1.5"
}
```

The caller cannot replace semantic fields with native IDs. This is deliberate: native IDs are outputs of semantic resolution, not user-intent inputs.

## Evidence produced

The gate preserves:

- each exact raw SportyBet event response;
- SHA-256 and byte size for each event response;
- semantic-resolution receipt;
- derived provider-native selections;
- existing direct create/load raw responses and round-trip receipt;
- final semantic booking-code receipt binding the semantic and transport phases.

## Safety

This boundary creates only an anonymous share/booking code. It does not log in, use cookies, access a wallet, submit a stake, or place a wager. It does not grant ATHENA model-selection, value, staking, execution, or `BET` authority.

The low-level direct bridge remains transport infrastructure and historical evidence machinery. It is not sufficient user-intent proof on its own.
