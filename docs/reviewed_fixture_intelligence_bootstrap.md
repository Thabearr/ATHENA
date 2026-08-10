# Reviewed Fixture Intelligence identity bootstrap

## Purpose

PR #46 adds the next narrow ATHENA trust boundary after the reviewed Fixture Catalog admission gate in PR #45.

The reviewed FotMob fixture path is now:

```text
verified PR #38 raw capture
→ PR #39 schema assessment
→ PR #40 UNREVIEWED fixture candidates
→ PR #41 explicit candidate review
→ PR #42 reviewed catalog handoff
→ PR #43 controlled PR #29 compiler workflow
→ PR #44 reviewed identity-only source capability
→ PR #45 explicit ADMITTED / REJECTED catalog admission
→ PR #46 reviewed Fixture Intelligence identity bootstrap
→ later separately reviewed Fixture Intelligence fact boundaries
```

PR #46 does **not** promote any football fact into Fixture Intelligence. It creates a typed, deterministic, self-validating identity handoff so later fact acquisition and qualification can prove which admitted fixture they are talking about.

## Why another boundary is required

`domain/fixture_intelligence.py` intentionally defines a general deterministic snapshot contract. Its `build_snapshot(...)` primitive accepts a fixture identifier and kickoff because PR #30 defined how trusted facts are represented, not how a particular live fixture identity becomes eligible for that layer.

A non-empty string passed to the generic PR #30 constructor is therefore **not** evidence that the fixture came through the reviewed FotMob catalog chain.

PR #46 closes that gap for the reviewed `/api/data/matches` path without changing the meaning of PR #30. A later FotMob intelligence workflow must start from this reviewed bootstrap rather than inventing or copying a fixture identifier directly.

## Accepted input

The bootstrap accepts one exact `ReviewedFixtureCatalogAdmission` from PR #45 and then revalidates it by reconstructing the frozen admission object through its own PR #45 constructor.

The input must still satisfy all PR #45 invariants, including:

- exact reviewed FotMob source capability;
- exact candidate/review/handoff/catalog/manifest ancestry;
- exact canonical PR #45 capability-profile hash;
- exact compiler provenance reconciliation;
- an explicit `ADMITTED` disposition;
- a non-empty admitted fixture set;
- prospective admission timing.

A merely type-shaped, mutated, rejected, stale, or capability-revoked admission fails closed.

## Output contract

The bootstrap records only source-scoped fixture identity and kickoff:

```json
{
  "fixture_identifier": "FOTMOB:<source match id>",
  "kickoff": "<UTC timestamp>",
  "admission_sha256": "<exact PR #45 canonical artifact SHA-256>"
}
```

For the catalog as a whole it also carries the exact:

- PR #45 admission SHA-256;
- PR #44 reviewed source-capability key and capability SHA-256;
- PR #40 candidate bundle SHA-256;
- PR #41 review bundle SHA-256;
- PR #42 handoff SHA-256;
- PR #29 strict catalog SHA-256;
- PR #29 manifest SHA-256;
- PR #45 admission review timestamp.

The fixture tuple must be every and only admitted fixture from PR #45 in deterministic catalog order. Duplicate identifiers, omissions, additions, changed kickoffs, changed ancestry, or non-FotMob identifiers fail closed.

## Exact identity resolution

`resolve_reviewed_fixture_intelligence_identity(...)` performs exact lookup only.

It has no:

- team-name matching;
- alias table;
- fuzzy matching;
- case normalization;
- numeric-ID coercion;
- competition inference;
- global team or competition identity resolution.

For example, `FOTMOB:1001` does not silently match `fotmob:1001`, `FOTMOB:01001`, a padded string, or a different source fixture.

## Historical determinism and capability revocation

Bootstrap construction revalidates the exact PR #45 admission against the current reviewed capability profile. If that capability is later revoked or changed, a **new** bootstrap from the old admission fails closed.

Once a bootstrap has been validly created, its canonical bytes use the capability and admission hashes captured at construction. Merely changing the live capability registry later does not mutate the historical bootstrap artifact.

Canonical bootstrap bytes are compact, sorted-key UTF-8 JSON with `allow_nan=False` and one final newline. The bootstrap SHA-256 is over those exact bytes.

## Safety boundary

Every downstream authorization flag remains exact immutable `False`:

- no network acquisition;
- no raw recapture;
- no automatic review;
- no global identity resolution;
- no Fixture Intelligence fact authorization;
- no Fixture Intelligence snapshot authorization;
- no model-feature authorization;
- no probability authorization;
- no pricing authorization;
- no selection authorization;
- no betting authorization.

PR #46 imports neither the Fixture Intelligence fact/snapshot module nor the model-feature module. It performs no file writes, network requests, compiler invocation, source discovery, football-semantic interpretation, or runtime registration.

## Important interpretation

**Fixture identity admission is not Fixture Intelligence evidence.**

The bootstrap proves only that ATHENA may refer to one exact reviewed source-scoped fixture and kickoff when a later separately qualified intelligence source provides evidence about that fixture.

It does not establish form, injuries, lineups, availability, xG, performance, fatigue, weather, venue, news, freshness, score meaning, or any model feature.

The raw `fotmob_unofficial` capability remains separate and does not become trusted through this bootstrap.

## Next safe boundary

A later PR may discover and qualify one richer FotMob surface, such as a match-detail route, against preserved raw evidence. That work should independently define its raw capture, schema, provenance, freshness and football-semantic contract before any fact can become `SUPPORTED` in PR #30 Fixture Intelligence.

That later workflow should resolve the target fixture through the PR #46 bootstrap and must not use bootstrap identity as evidence for the fact itself.
