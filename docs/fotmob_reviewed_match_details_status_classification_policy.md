# Reviewed FotMob match-details status-classification policy

## Purpose

PR #60 is the policy boundary immediately after merged PR #58.

It answers one narrow question:

> For each exact PR #58 `QUALIFIED` observation, until what exact UTC instant may a later, separately reviewed evaluator consider that observation fresh enough to participate in status classification?

PR #60 does **not** perform the classification itself.

The trust chain is:

```text
PR #52 persisted evidence verification
→ PR #53 strict structural assessment
→ PR #54 explicit scalar semantics review
→ PR #55 exact scalar extraction, UNVERIFIED
→ PR #57 PR #30 facts, still UNVERIFIED
→ PR #58 exact-observation qualification
→ PR #60 explicit freshness/conflict policy
```

## Why policy and promotion are separate

Freshness is a football-information policy decision, not a serialization detail. Combining freshness-policy review and fact-status promotion in one PR would make it difficult to tell whether a later `SUPPORTED` or `STALE` result came from an evidence rule or from promotion logic.

PR #60 therefore records only the reviewed policy inputs. A later PR must independently consume and revalidate this artifact before changing any PR #30 status.

## Exact observation scope

The policy scope is frozen to:

```text
EXACT_OBSERVATION_ONLY
```

A rule applies only to the exact PR #58 observation whose canonical fact payload hash, source reference, fixture identity, raw evidence SHA and qualification artifact are anchored in the policy.

It is not a provider-wide FotMob freshness rule and it cannot be reused for another fixture, response, capture, value or future observation.

## QUALIFIED observations

Each exact PR #58 decision with:

```text
disposition = QUALIFIED
```

must have exactly one `MatchDetailsFreshnessPolicyRule`.

The rule contains:

- exact Fixture Intelligence category;
- exact field;
- exact source reference;
- exact `fresh_until` UTC timestamp;
- non-empty reviewer rationale.

`fresh_until` must satisfy:

```text
observed_at <= fresh_until < kickoff
```

No default freshness duration exists. The boundary does not clamp, infer or silently extend a deadline.

The policy records the corresponding decision as:

```text
ELIGIBLE_FOR_LATER_CLASSIFICATION
```

This means only that a later evaluator is allowed to inspect freshness and conflict conditions. It does **not** mean `SUPPORTED`.

## Frozen freshness comparison

The time comparison itself is part of PR #60's reviewed policy contract rather than something a later evaluator may invent.

The exact rule is:

```text
FRESHNESS_COMPARISON = POLICY_REVIEWED_AT_LE_CLASSIFIED_AT_LE_FRESH_UNTIL
```

with the independent prospective gate:

```text
policy_reviewed_at <= classified_at < kickoff
```

For an eligible observation the time-only helper therefore returns fresh exactly when:

```text
policy_reviewed_at <= classified_at <= fresh_until
```

Equality at `fresh_until` is intentionally fresh. One microsecond later is outside the reviewed freshness window. Classification before the PR #60 policy existed fails closed instead of retroactively evaluating the observation.

`is_within_reviewed_freshness_window(...)` is the reusable helper for those semantics. It requires exact `datetime.timezone.utc`, verifies observation/policy/deadline/classification chronology against kickoff, and returns only a boolean. It creates no Fixture Intelligence status.

This split prevents a later evaluator from silently switching between `<` and `<=`, or from backdating classification before policy review.

## REJECTED observations

A PR #58 `REJECTED` observation is mechanically recorded as:

```text
BLOCKED_BY_QUALIFICATION
```

It cannot receive a `fresh_until` rule.

Callers cannot override a PR #58 rejection by supplying an extra freshness rule. Freshness rules must cover every and only exact PR #58 `QUALIFIED` decision.

## Conflict policy

PR #60 freezes the conflict policy to:

```text
PRESERVE_DIFFERING_QUALIFIED_VALUES
```

This deliberately rules out policies such as latest-wins, preferred-alias, silent normalization or arbitrary source-order selection.

PR #60 itself does not compare multiple observations. A later evaluator/aggregator that consumes multiple exact PR #60 artifacts must preserve differing qualified values and fail closed into conflict semantics rather than choosing one silently.

## Prospective chronology

The policy review must preserve the upstream chronology:

```text
observed_at
<= PR #58 qualification reviewed_at
<= PR #60 policy_reviewed_at
< kickoff
```

All datetimes must already use exact `datetime.timezone.utc`.

A freshness deadline may already have expired by the time policy review occurs. PR #60 records the reviewed deadline exactly; it does not rewrite history to make the observation fresh. The later comparator will correctly return `False` for a policy-reviewed classification time that is already after `fresh_until`.

## Detached artifact

`ReviewedMatchDetailsStatusClassificationPolicy` records detached identities only:

- PR #58 qualification SHA-256 and byte size;
- exact source-scoped fixture identity and FotMob match ID;
- kickoff and observation timestamp;
- PR #58 review timestamp and PR #60 review timestamp;
- raw response SHA-256;
- deterministic logical `response.json` evidence path;
- source provider and `PRIMARY_FOOTBALL_CONTEXT` role;
- reviewer reference;
- exact conflict-policy constant;
- one recorded decision per exact PR #58 decision;
- all safety flags exact `false`.

For each recorded decision it carries the exact PR #58 `fact_sha256`, so policy identity remains bound to the exact canonical PR #30 UNVERIFIED fact payload reviewed in PR #58.

## Full-chain revalidation

Local dataclass invariants are not enough to prove that a policy still belongs to the original raw evidence.

The legal consumption boundary is:

```text
revalidate_reviewed_match_details_status_classification_policy(...)
```

It requires the complete exact PR #52→#58 inputs, the supplied PR #60 object and caller-presented canonical PR #60 bytes.

It first reruns PR #58's full-chain revalidator. It then reconstructs the PR #60 freshness-rule inputs from the supplied policy and rebuilds PR #60. Consumption succeeds only when:

```text
supplied PR #60 canonical bytes
== exact full-chain PR #60 rebuild bytes
== caller-presented PR #60 bytes
```

Changing fact hashes, source references, fixture identity, evidence path, conflict policy, qualification ancestry or safety state therefore fails closed.

## Status remains unchanged

PR #60 imports no `FixtureIntelligenceFact` constructor and no `IntelligenceFactStatus` enum.

It creates no replacement facts and performs no status mutation. All PR #57 inputs remain `UNVERIFIED` after this boundary.

A later evaluator may use an exact revalidated PR #60 policy to determine whether an eligible observation is fresh or stale at a specific classification timestamp. A separate aggregation step must handle differing qualified values without latest-wins behavior.

## Explicit non-authorizations

PR #60 authorizes none of the following:

- automatic status classification;
- `SUPPORTED`, `STALE` or `CONFLICTED` status creation;
- fact-status promotion;
- conflict resolution by choosing a winner;
- source-wide FotMob qualification;
- Fixture Intelligence snapshot creation;
- model feature availability;
- probability inference;
- pricing;
- selection;
- betting;
- network acquisition.

All safety flags are exact immutable `false`.

## Next boundary

The next safe boundary is a deterministic **status evaluator** that consumes exact PR #57 facts + exact revalidated PR #58 qualification + exact revalidated PR #60 policy at an explicit UTC classification timestamp.

That evaluator should reuse `is_within_reviewed_freshness_window(...)` and produce only evidence-status candidates such as fresh-qualified, stale-qualified or blocked. Multi-observation conflict aggregation should remain explicit and must never silently prefer the newest value.
