# Reviewed Fixture Intelligence identity bootstrap

## Purpose

PR #47 adds the next narrow ATHENA trust boundary after the reviewed Fixture Catalog admission-artifact verifier in PR #46.

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
→ PR #46 exact canonical admission-artifact verification
→ PR #47 reviewed Fixture Intelligence identity bootstrap
→ later separately reviewed Fixture Intelligence fact boundaries
```

PR #47 does **not** promote any football fact into Fixture Intelligence. It creates a typed, deterministic, self-validating identity handoff so later fact acquisition and qualification can prove which already-reviewed fixture they are talking about.

## Why PR #46 must be the input

`domain/fixture_intelligence.py` intentionally defines a general deterministic snapshot contract. Its `build_snapshot(...)` primitive accepts a fixture identifier and kickoff because PR #30 defined how trusted facts are represented, not how a particular live fixture identity becomes eligible for that layer.

PR #45 admitted an exact reviewed catalog, but PR #46 added the separate current-use check that exact canonical admission bytes still match an exact, currently revalidatable `ADMITTED` admission and emitted a deterministic verification receipt.

PR #47 therefore does **not** accept a PR #45 admission object directly. A caller that has only `ReviewedFixtureCatalogAdmission` must first pass the PR #46 verifier. This prevents the Fixture Intelligence bootstrap from bypassing the canonical artifact-verification boundary.

A non-empty raw fixture identifier, an unverified PR #45 object, or a merely type-shaped object is not proof of bootstrap eligibility.

## Accepted input

`build_reviewed_fixture_intelligence_bootstrap(...)` accepts only an exact `VerifiedReviewedFixtureCatalogAdmissionArtifact` from PR #46.

Before construction succeeds, PR #47:

1. reconstructs the supplied PR #46 verified artifact through its own frozen dataclass constructor;
2. therefore re-runs PR #46's current PR #45 semantic/capability revalidation and exact admission/artifact-byte checks;
3. canonicalizes the supplied verification receipt and the reconstructed receipt and requires byte-for-byte equality;
4. requires a non-empty admitted fixture set;
5. computes and captures the exact PR #46 verification-receipt SHA-256;
6. carries forward the exact PR #45 admission SHA-256 and its candidate/review/handoff/catalog/manifest ancestry;
7. requires every fixture still to be prospective at the **PR #46 verification timestamp**, not merely at the older PR #45 admission-review time.

A stale capability profile, forcibly mutated verifier object, changed admission, changed artifact bytes, changed safety state, or verification at/after kickoff fails closed.

PR #46 itself deliberately permits a historical artifact to be verified after kickoff because its job is byte/semantic verification rather than prospective Fixture Intelligence admission. PR #47 adds the stricter prospective requirement at the point where identity is allowed to enter the Fixture Intelligence bootstrap.

## Output contract

Each bootstrapped identity contains only:

```json
{
  "fixture_identifier": "FOTMOB:<source match id>",
  "kickoff": "<UTC timestamp>",
  "admission_sha256": "<exact PR #45 canonical admission SHA-256>",
  "verification_receipt_sha256": "<exact PR #46 receipt SHA-256>"
}
```

The bootstrap as a whole captures only detached reviewed ancestry and timestamps:

- PR #46 verification dataset identity;
- exact PR #46 verification-receipt SHA-256;
- exact PR #46 verification timestamp;
- PR #45 admission SHA-256;
- PR #45 admission-review timestamp;
- PR #44 reviewed source-capability key and capability SHA-256;
- PR #40 candidate-bundle SHA-256;
- PR #41 review-bundle SHA-256;
- PR #42 handoff SHA-256;
- PR #29 strict catalog SHA-256;
- PR #29 manifest SHA-256;
- every and only verified admitted `FOTMOB:<match id>` identity + kickoff.

Duplicate identifiers, omissions, additions, changed kickoffs, changed receipt ancestry, changed catalog ancestry, or non-FotMob identifiers fail closed.

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

## Historical determinism

Bootstrap construction revalidates the exact PR #46 artifact against the current reviewed capability profile. If that capability is later revoked or changed, a **new** bootstrap from an old verifier object fails closed.

Once a bootstrap has been validly created, its canonical serialization deliberately reads only detached scalar ancestry, timestamps, immutable fixture identities, and its own safety mapping. It does not re-read the nested PR #46 verifier object during serialization.

Therefore later mutation of the live capability registry—or even a forcibly mutated nested verifier object—cannot alter the already-created bootstrap's canonical historical bytes. A new construction/revalidation from corrupted state still fails closed.

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

PR #47 imports neither the Fixture Intelligence fact/snapshot module nor the model-feature module. It performs no file writes, network requests, compiler invocation, source discovery, football-semantic interpretation, or runtime registration.

## Important interpretation

**Verified fixture identity is not Fixture Intelligence evidence.**

The bootstrap proves only that ATHENA may refer to one exact reviewed source-scoped fixture and kickoff when a later separately qualified intelligence source provides evidence about that fixture.

It does not establish form, injuries, lineups, availability, xG, performance, fatigue, weather, venue, news, freshness, score meaning, or any model feature.

The raw `fotmob_unofficial` capability remains separate and does not become trusted through this bootstrap.

## Next safe boundary

A later PR may discover and qualify one richer FotMob surface, such as a match-detail route, against preserved raw evidence. That work should independently define its raw capture, schema, provenance, freshness, and football-semantic contract before any fact can become `SUPPORTED` in PR #30 Fixture Intelligence.

That later workflow should resolve the target fixture through the PR #47 bootstrap and must not use bootstrap identity as evidence for the fact itself.
