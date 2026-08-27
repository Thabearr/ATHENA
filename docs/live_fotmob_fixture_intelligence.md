# Live FotMob runtime evidence → Fixture Intelligence

## Scope

This boundary preserves the exact raw FotMob responses consumed by the legacy
runtime before their values are normalized into `fixture_extended`.  It then
replays those immutable bytes to issue a standard
`FixtureIntelligenceSnapshot`.

It does not qualify the legacy browser-compatible transport, model a football
probability, price a market, route a selection, build an accumulator, or place
a wager.

## Call graph

```text
FotmobBypassClient exact response bytes
  → FotMobAdvancedScraper durable live-evidence capture
  → legacy normalized fixture_extended compatibility values
  → replayed response.json + canonical manifest.json
  → UNVERIFIED FixtureIntelligenceFact
  → FixtureIntelligenceSnapshot
```

Both a fixture-list response and its match-details response are required.  The
fixture-list evidence establishes the exact `FOTMOB:<id>` fixture and pre-match
kickoff; match-details evidence supplies `home_form` and `away_form` when those
fields are present.  The issuer rejects a non-unique fixture, a mismatched
match-details id, a hash/path/manifest mismatch, or post-kickoff evidence.

## Provenance and compatibility

Evidence is published beneath the fixed ignored root:

` .cache/athena-runtime/fotmob-live-evidence `

Each capture contains the exact `response.json` bytes and a canonical
`manifest.json` binding source URL, observation time, raw SHA-256, size,
fixture identity, and the recorded legacy transport characteristics.  The
database stores only a pointer, SHA-256, and observation time for operational
compatibility.  It is never canonical authority: deleting, replacing, or
altering the evidence makes replay fail closed.

`current_home_form`, `current_away_form`, and
`current_form_observed_at` retain their legacy shapes and remain traceable to
the same raw match-details bytes.  The corresponding facts are intentionally
`UNVERIFIED`; absent forms create no fact.  This keeps unknown data unknown and
ensures Fixture State v2 can consume the snapshot while correctly blocking
unverified fields.

## Safety

This module grants no model-feature, probability, pricing, selection, or bet
authority.  In particular it does not promote the legacy runtime’s browser
compatibility transport into a reviewed transparent source or a `SUPPORTED`
football fact.
