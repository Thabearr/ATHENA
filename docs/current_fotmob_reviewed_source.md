# Current reviewed FotMob source boundary

## Purpose

PR #243 removes the repeated manual fixture-identity preparation step from the
current transparent FotMob source path without weakening the older review
contracts.

It composes the existing reviewed chain:

```text
transparent /api/data/matches request (PR #38)
-> durable exact raw capture
-> strict schema assessment / UNREVIEWED candidates (PR #39/#40)
-> PR243 bounded fixture-identity decision policy
-> existing PR #41 decision/blocker validation
-> existing catalog handoff/compiler
-> reviewed catalog admission + artifact verification
-> reviewed Fixture Intelligence bootstrap + artifact verification (PR #47/#48)
```

The result is a verified **source-scoped current fixture bootstrap**. It is the
reviewed prerequisite for the existing transparent match-details probe/capture
chain.

This PR deliberately does not claim that a fixture identity bootstrap is already
a `FixtureIntelligenceSnapshot` containing football facts.

## Why a new policy boundary is required

The existing PR #41 contract is intentionally human-review-only and its safety
surface keeps `automatic_review_authorized=false`. PR #44 later confirmed that
`fotmob_data_matches_reviewed_catalog` can produce reliable source-scoped fixture
identity, but only under the existing review gates. Neither contract authorizes
silently approving every future FotMob fixture.

PR #243 therefore does **not** modify or reinterpret PR #41. It introduces one
new reviewed decision issuer:

```text
ATHENA_PR243_CURRENT_FOTMOB_FIXTURE_IDENTITY_POLICY_V1
```

with reviewer reference:

```text
athena-policy:pr243-current-fotmob-fixture-identity-v1
```

The issuer creates individual PR #41 `APPROVED` decisions only when every gate
below succeeds.

## Fixture-policy gates

A candidate is policy-reviewable only when:

1. its exact FotMob `(ccode, source competition name)` resolves through the
   existing `athena-competition-review-priority-v2` source-identity registry;
2. PR #41's own deterministic blocker derivation does not block the candidate;
3. the source observation is not later than the policy evaluation timestamp;
4. ATHENA acquired the exact source response no more than **900 seconds** before
   policy evaluation;
5. the fixture kickoff resolves to the exact requested source date in the exact
   source timezone; and
6. kickoff remains at least **3600 seconds** after policy evaluation.

The 900-second rule is explicitly **ATHENA acquisition recency**. It is not
provider-native freshness metadata and must never be relabelled as such.

The 900-second maximum source age and 3600-second minimum kickoff lead are frozen
reviewed production constants. The live Python entry point, CLI and hosted
workflow expose no override for either value. Replay/test helpers may exercise
other values only to prove fail-closed behavior; they are not a production
configuration surface.

The policy never emits a fabricated `REJECTED` decision. A candidate which does
not satisfy the policy simply remains unreviewed.

This means an unknown competition, ambiguous fixture/team/competition identity,
duplicate source identity, malformed catalog field, stale acquisition,
requested-date spillover, too-close fixture, or future-dated observation cannot
be promoted merely to increase accumulator fixture count.

International hierarchy entries which do not yet carry exact reviewed FotMob
source identities are not automatically admitted by this policy.

## Catalog admission

For the exact set produced by the PR243 policy, the current source issuer emits a
separate deterministic catalog-admission decision under:

```text
athena-policy:pr243-current-fotmob-catalog-admission-v1
```

That decision is not an approve-all wildcard. Its hashes bind the exact
candidate bundle, PR243 review bundle, handoff, compiled catalog, manifest, and
reviewed source-capability identity. All existing admission/artifact/bootstrap
constructors revalidate their normal ancestry.

The existing compiler still requires a clean tracked worktree and records the
actual current Git commit. No caller can supply fixture IDs, team names, a
preselected fixture list, or policy-bound overrides to this live path.

## Production entry point

The fixed entry point is:

```text
scripts/issue_current_fotmob_reviewed_source.py
```

A live call must explicitly authorize the one transparent network request:

```bash
git pull && python scripts/issue_current_fotmob_reviewed_source.py \
  --date YYYYMMDD \
  --timezone UTC \
  --ccode3 NGA \
  --execute-live-network
```

There is no `module:callable`, caller-native fixture authority, policy-bound
override, or legacy `FotmobBypassClient` input.

The hosted workflow is:

```text
.github/workflows/issue-current-fotmob-reviewed-source.yml
```

It accepts only the request date, request timezone and request country code. The
reviewed recency/lead policy cannot be weakened at dispatch time.

Whether execution succeeds or fails closed, the CLI writes its explicit result
receipt when `--output` is supplied. The workflow uploads that receipt together
with any exact PR #38 raw capture so a source failure is auditable rather than
hidden behind a missing artifact.

## Current authority after PR243

A successful result means:

```text
REVIEWED_CURRENT_FOTMOB_FIXTURE_BOOTSTRAP_VERIFIED
```

It proves a recent transparent ATHENA source acquisition and reviewed
source-scoped fixture identity ancestry under the frozen PR243 policy.

It does **not** authorize:

- provider `teamForm` array semantics;
- derived current form;
- Elo or fatigue;
- player-context/team-strength inference unless separately admitted by their
  existing reviewed boundaries;
- a complete `FixtureIntelligenceSnapshot` of model features;
- model inference;
- Phase 6 calibrated candidates;
- SportyBet price acquisition;
- market selection;
- accumulator construction;
- SportyBet execution;
- BET.

Every such downstream authority remains false, and `wager_placed=false`.

## SportyBet separation

PR #243 changes no SportyBet code-generation transport. The established ATHENA
path remains separate:

```text
ATHENA semantic intent
-> current SportyBet semantic resolution
-> ATHENA-derived provider-native identities
-> direct SportyBet create/share
-> direct SportyBet reload
-> exact native + human-readable semantic verification
```

No ParseBot, BookBet or other third-party booking-code service is introduced.
FotMob source qualification and SportyBet code-generation transport remain
separate authority boundaries.

## Next exact boundary

The next missing boundary is intentionally explicit:

```text
CURRENT_REVIEWED_FOTMOB_SEMANTIC_FACT_OR_MODEL_FEATURE_ISSUER_REQUIRED
```

The verified bootstrap can now feed ATHENA's already-reviewed transparent
`/api/data/matchDetails?matchId=<id>` probe/capture machinery without rebuilding
fixture identity by hand. The next PR must decide, using reviewed evidence,
whether the prospective model features should come from current match-details
semantics, the reviewed UTC-native historical-state constructor, or an exact
composition of those existing sources.

It must not copy the legacy bypass runtime's detached `home_form` / `away_form`
values into canonical authority.
