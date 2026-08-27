# Live FotMob runtime evidence preservation

## Scope

This boundary preserves the exact raw FotMob responses consumed by the legacy
`FotmobBypassClient` runtime **before** their values are normalized into
`fixture_extended`.

It is deliberately not a second canonical FotMob source or Fixture Intelligence
issuer.

The legacy client uses browser/TLS impersonation and rotating browser headers.
ATHENA's already-reviewed transparent FotMob source contracts use different,
explicit request identities. Re-labeling a legacy bypass response as one of
those reviewed captures would falsify provenance.

Therefore this boundary records the legacy bytes honestly and stops at:

`BLOCKED_REVIEWED_TRANSPARENT_FOTMOB_SOURCE_REPLAY_REQUIRED`

## Call graph

```text
legacy FotmobBypassClient HTTP response
  → exact response bytes + actual observation time
  → one compatibility capture per actual HTTP response
  → fixture_extended compatibility values/pointers
  → integrity-only replay
  → STOP: no canonical FixtureIntelligenceFact authority
```

The canonical path remains the existing reviewed chain, conceptually:

```text
reviewed transparent /api/data/matches capture
  → reviewed fixture/schema/candidate/admission chain
  → reviewed transparent /api/data/matchDetails capture
  → persisted-evidence verification
  → reviewed structural/semantic/admission replay
  → reviewed Fixture Intelligence snapshot issuer
  → Fixture State v2 / model-feature handoff
```

The current reviewed implementations descended from the PR #38 data-matches
capture boundary and PR #50–#65 match-details/Fixture-Intelligence boundaries
remain the authority. This module does not replace them.

## One response, one capture

A `/api/data/matches` response belongs to the HTTP request, not to a single
fixture. The runtime therefore writes that response exactly once and every
fixture derived from it references the same immutable compatibility-evidence
receipt.

A `/api/data/matchDetails?matchId=<id>` response is captured once for that exact
request and may be referenced by the corresponding enriched runtime fixture.

This prevents the earlier #242 draft behavior that copied one large fixture-list
response once per match.

## Evidence root and replay safety

Compatibility evidence is written beneath the fixed ignored root:

`.cache/athena-runtime/fotmob-live-evidence`

Each capture contains:

- exact `response.json` bytes;
- canonical `manifest.json` bytes;
- exact source URL;
- actual observed-at timestamp;
- raw SHA-256 and size;
- browser-impersonation provenance;
- explicit false canonical/downstream authority flags.

Replay rejects:

- an alternate root;
- `..` traversal;
- symlinked root/path components;
- symlinked `response.json`;
- symlinked `manifest.json`;
- raw SHA mismatch;
- manifest SHA mismatch;
- non-canonical manifest bytes;
- receipt/manifest identity drift;
- any attempted authority upgrade.

The database stores only replay pointers, hashes and observation times for
legacy operational compatibility. Detached database values are never canonical
source authority.

## Runtime compatibility fields

`current_home_form`, `current_away_form`, and
`current_form_observed_at` remain operational compatibility values.

Each side's form is preserved only when the source payload contains that side;
a missing away/home side is not manufactured. `current_form_observed_at` comes
from the exact match-details response observation when raw compatibility
evidence was captured.

Those values may be compared later with a separately source-replayed reviewed
snapshot, but this legacy capture cannot itself mint a reviewed fact.

## Why canonical issuance is still blocked

ATHENA already has reviewed transparent FotMob source contracts. The current
legacy runtime request profile does not satisfy those request identities, and
the reviewed match-details chain additionally requires the exact reviewed
fixture/bootstrap/admission lineage before canonical semantics can be issued.

The correct response is therefore to fail closed rather than generate an
`UNVERIFIED` snapshot and then try to weaken Fixture State.

No Fixture State status is upgraded by this boundary.

## Safety

This module grants no source qualification, Fixture Intelligence, model-feature,
probability, calibration, pricing, selection, accumulator, SportyBet, staking or
bet authority.

It does not modify the direct ATHENA SportyBet semantic resolution → create →
reload → exact-verification architecture.

`wager_placed = false` remains unchanged.
