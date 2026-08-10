# Reviewed FotMob match-details status evaluator

## Purpose

PR #61 is the deterministic evaluator immediately after merged PR #60.

It answers one narrow question:

> Given one exact fully revalidated PR #60 policy and one explicit UTC `classified_at`, what is the evidence-evaluation disposition of every exact reviewed field at that instant?

The only possible evaluator dispositions are:

```text
FRESH_QUALIFIED
STALE_QUALIFIED
BLOCKED_BY_QUALIFICATION
```

These are deliberately **not** PR #30 `IntelligenceFactStatus` values.

The trust chain is:

```text
PR #52 persisted evidence verification
→ PR #53 strict structural assessment
→ PR #54 explicit scalar semantics review
→ PR #55 exact scalar extraction, UNVERIFIED
→ PR #57 PR #30 facts, still UNVERIFIED
→ PR #58 exact-observation qualification
→ PR #60 explicit freshness/conflict policy
→ PR #61 deterministic evidence-status evaluation
```

## Why evaluation and promotion remain separate

PR #60 froze policy but created no status. PR #61 applies that policy deterministically but still creates no PR #30 status.

Keeping evaluation separate from promotion means a later review can answer a different question explicitly:

> Is a `FRESH_QUALIFIED` evaluator result sufficient to create a `SUPPORTED` fact in this exact domain context?

PR #61 intentionally does not answer that question.

## Exact inputs

`evaluate_reviewed_match_details_status_policy(...)` requires the complete exact PR #52→#60 chain:

- persisted-evidence verification object and canonical receipt bytes;
- exact raw manifest bytes;
- exact raw response bytes;
- strict structural assessment and canonical bytes;
- exact semantic review and canonical bytes;
- exact PR #57 UNVERIFIED fact bundle and canonical bytes;
- exact PR #58 qualification and canonical bytes;
- exact PR #60 policy and canonical bytes;
- explicit `classified_at` using exact `datetime.timezone.utc`.

PR #61 first reruns PR #60's full-chain revalidator. Evaluation never proceeds from a detached or merely shape-valid policy.

## Prospective classification time

Classification is permitted only when:

```text
policy_reviewed_at <= classified_at < kickoff
```

Classification before the reviewed policy existed fails closed. Classification at or after kickoff also fails closed.

For an eligible PR #60 decision, #61 reuses the frozen PR #60 comparison:

```text
FRESHNESS_COMPARISON = POLICY_REVIEWED_AT_LE_CLASSIFIED_AT_LE_FRESH_UNTIL
```

Therefore:

```text
classified_at <= fresh_until  -> FRESH_QUALIFIED
classified_at >  fresh_until  -> STALE_QUALIFIED
```

subject always to the prospective classification gate above.

Equality at `fresh_until` remains intentionally fresh; one microsecond later is stale-qualified.

## Rejected evidence remains blocked

A PR #60 decision that is:

```text
BLOCKED_BY_QUALIFICATION
```

must remain:

```text
BLOCKED_BY_QUALIFICATION
```

in PR #61.

It cannot receive a freshness deadline, cannot become fresh-qualified, and cannot become stale-qualified.

## Detached evaluation artifact

`ReviewedMatchDetailsStatusEvaluation` records:

- schema/dataset identity;
- `EXACT_POLICY_OBSERVATION_ONLY` scope;
- exact frozen freshness-comparison constant;
- exact conflict-policy constant from PR #60;
- SHA-256 and size of exact canonical PR #60 policy bytes;
- source-scoped fixture identity and FotMob match ID;
- kickoff, observation, qualification-review, policy-review and classification timestamps;
- raw-response SHA-256 and evidence path;
- exact source provider and source role;
- one deterministic decision per exact PR #60 decision;
- all safety flags exact `false`.

Every decision preserves the exact PR #58/PR #60 `fact_sha256`, category, field and source reference.

## Local self-validation

The artifact locally rejects:

- bad schema/dataset/scope constants;
- changed freshness or conflict policy constants;
- malformed SHA-256 values;
- fixture/source-ID mismatches;
- non-UTC or invalid chronology;
- unsorted, duplicated or malformed decisions;
- duplicate fact hashes;
- source references belonging to another fixture;
- blocked decisions made fresh/stale or given a deadline;
- eligible decisions missing a deadline;
- a fresh/stale result that disagrees with PR #60's frozen time comparison;
- any safety flag set to `true`.

Local validation proves internal consistency only. Full trust still requires replay against the exact upstream evidence chain.

## Full-chain revalidation

The legal consumption boundary is:

```text
revalidate_reviewed_match_details_status_evaluation(...)
```

It reruns PR #60's complete PR #52→#60 ancestry check, then rebuilds PR #61 using the supplied evaluation's exact `classified_at`.

Consumption succeeds only when:

```text
supplied PR #61 canonical bytes
== exact full-chain PR #61 rebuild bytes
== caller-presented PR #61 bytes
```

Coordinated mutation of policy/fact hashes, source identity, evidence lineage, deadlines, dispositions or safety state therefore fails closed against the original evidence chain.

## Conflict handling remains out of scope

PR #61 evaluates **one exact observation policy**. It does not combine multiple observations.

The inherited conflict policy remains:

```text
PRESERVE_DIFFERING_QUALIFIED_VALUES
```

A later aggregation boundary must preserve differing fresh-qualified values and produce explicit conflict semantics. It must not choose the newest value, preferred alias or arbitrary source order.

## Explicit non-authorizations

PR #61 authorizes none of the following:

- creation or mutation of PR #30 fact statuses;
- `SUPPORTED` fact creation;
- `STALE` fact creation;
- `CONFLICTED` fact creation;
- multi-observation conflict aggregation;
- conflict resolution by choosing a winner;
- source-wide FotMob qualification;
- Fixture Intelligence snapshot creation;
- model feature availability;
- probability inference;
- pricing;
- selection;
- betting;
- network acquisition.

The production module imports no `FixtureIntelligenceFact` constructor and no `IntelligenceFactStatus` enum.

## Next boundary

The next safe boundary is **multi-observation status aggregation**, not direct promotion.

That boundary should consume one or more exact fully revalidated PR #61 evaluations for the same fixture/category/field and preserve differing fresh-qualified scalar values as explicit conflict candidates. Only after that aggregation boundary is reviewed should a separate promotion PR consider creating PR #30 `SUPPORTED`, `STALE` or `CONFLICTED` facts.