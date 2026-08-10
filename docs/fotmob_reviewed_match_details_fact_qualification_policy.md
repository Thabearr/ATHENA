# Reviewed FotMob match-details fact qualification policy

## Purpose

PR #58 adds a policy-only review boundary after merged PR #57.

The reviewed path is now:

```text
PR #52 exact persisted match-details evidence
→ PR #53 strict structural assessment
→ PR #54 explicit human scalar semantics
→ PR #55 exact scalar extraction candidates, still UNVERIFIED
→ PR #57 PR #30 fact representation, still UNVERIFIED
→ PR #58 explicit eligibility/freshness/corroboration policy only
```

PR #58 deliberately does **not** make a FotMob field `SUPPORTED`, does not qualify FotMob globally, does not mutate `SOURCE_CAPABILITY_REGISTRY`, and does not create a Fixture Intelligence snapshot.

## Why this boundary exists

PR #54 establishes that an exact structural path has a reviewer-approved football meaning. PR #55 extracts the exact scalar. PR #57 makes that scalar representable as a PR #30 fact while preserving `UNVERIFIED`.

Those steps still do not answer three separate trust questions:

1. Is this exact semantic field eligible to proceed toward a later trust/status decision?
2. How old may ATHENA's **capture** be at a future classification time?
3. Must another independent source corroborate the field before any later support decision?

PR #58 records those policy requirements explicitly rather than hiding them in later code.

## Exact input chain

`build_reviewed_match_details_fact_qualification_policy(...)` requires the complete exact PR #52→#57 chain:

- PR #52 verified persisted evidence and exact receipt bytes;
- exact historical `manifest.json` and `response.json` bytes;
- PR #53 structural assessment and exact canonical bytes;
- PR #54 field-semantics review and exact canonical bytes;
- PR #57 UNVERIFIED fact bundle and exact canonical bytes.

PR #58 invokes the PR #57 full-chain revalidator. The supplied PR #57 object and bytes therefore must still agree with the exact raw response and review chain before any policy can be created.

## One decision for every exact fact

Every exact PR #57 candidate must receive exactly one `MatchDetailsFactQualificationDecision`.

A decision is anchored by:

- `IntelligenceCategory`;
- exact Fixture Intelligence field name;
- exact reviewed JSON pointer;
- exact reviewed JSON scalar kind.

The policy rejects omitted candidates, extra candidates, duplicate targets, kind changes and reordered/non-canonical nested state.

The two dispositions are:

### `ELIGIBLE`

`ELIGIBLE` means only that the reviewer permits this **exact reviewed semantic target** to proceed to a future trust/status boundary, subject to all additional gates.

It requires:

- a positive bounded `max_capture_age_seconds`;
- an explicit boolean `requires_independent_corroboration`;
- reviewer notes may be recorded.

`MAX_CAPTURE_AGE_SECONDS` is a sanity/serialization ceiling, not a recommendation that any football field is valid for that long.

### `REJECTED`

`REJECTED` means the exact target may not proceed through this policy.

A rejected decision carries no freshness allowance and cannot request corroboration.

## Capture age is not provider freshness

`max_capture_age_seconds` concerns only the elapsed time from ATHENA's exact `observed_at` capture timestamp to a future classification time.

FotMob match-details has **not** been shown to expose trustworthy provider-side freshness metadata for these reviewed fields. Therefore PR #58 must not reinterpret acquisition time as proof of when FotMob originally produced or updated the football information.

Any future status classifier must keep those concepts separate.

## Source qualification remains unsatisfied

Even an `ELIGIBLE` decision does not mean the source is qualified.

The PR #58 safety contract keeps all of the following exact `false`:

- global source qualification authorization;
- source qualification satisfied;
- `SUPPORTED` status authorization;
- status classification authorization;
- Fixture Intelligence snapshot authorization;
- model feature authorization;
- probability, pricing, selection and betting authorization.

PR #58 also does not add `fotmob_match_details_reviewed` to the existing source capability registry. The registry continues to describe only capabilities that have separately passed their reviewed adapter boundaries.

## Prospective review timing

The policy review timestamp must:

- use exact `datetime.timezone.utc`;
- not predate the exact evidence observation;
- remain strictly before fixture kickoff.

This keeps the policy attached to the same prospective evidence lifecycle rather than allowing a post-match policy to retroactively imply pre-match trust.

## Embedded PR #57 identity

`ReviewedMatchDetailsFactQualificationPolicy` embeds the exact PR #57 bundle and its canonical size/SHA-256.

Fixture identity is therefore not caller-selected. The policy derives:

- fixture identifier;
- FotMob source match ID;
- kickoff;
- observation time;
- raw response SHA-256

from the exact embedded PR #57 handoff.

Every embedded PR #57 fact remains `UNVERIFIED`.

## Full-chain revalidation

`revalidate_reviewed_match_details_fact_qualification_policy(...)` requires:

- the same complete PR #52→#57 inputs;
- the exact PR #58 policy object;
- the exact canonical PR #58 bytes.

It rebuilds PR #57 from the raw evidence chain and then rebuilds PR #58 from the policy decisions. Supplied policy bytes must equal the canonical full-chain rebuild exactly.

This prevents a locally self-consistent forged PR #57 candidate/fact pair from entering policy review merely because its local hashes were recomputed: the original `response.json` bytes remain authoritative for the PR #57 replay.

The policy artifact itself is still a reviewer decision artifact. Exact canonical bytes must be preserved by any later boundary; PR #58 does not pretend that deterministic serialization is a cryptographic reviewer signature.

## Explicit non-authorizations

PR #58 does not authorize:

- network acquisition;
- global FotMob source qualification;
- automatic field qualification;
- changing any PR #57 fact from `UNVERIFIED`;
- constructing a Fixture Intelligence snapshot;
- making a PR #31 model feature `AVAILABLE`;
- probabilities;
- pricing;
- selections;
- bets.

## Next safe boundary

A later PR can consume an exact PR #58 policy together with independently reviewed source-qualification/corroboration evidence and classify exact PR #57 facts as `SUPPORTED`, `STALE`, `CONFLICTED`, or still `UNVERIFIED`.

That future classifier must fail closed when source qualification is absent, capture age exceeds policy, required corroboration is missing, or competing evidence conflicts. PR #58 intentionally does not perform that classification itself.
