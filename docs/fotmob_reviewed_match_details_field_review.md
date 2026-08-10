# Reviewed FotMob match-details field semantics review

## Purpose

PR #54 adds an explicit **human decision** boundary after PR #53 structural assessment. It does not decide FotMob semantics automatically.

The reviewed chain is:

```text
PR #52 exact historical evidence
→ PR #53 strict structural inventory
→ PR #54 explicit reviewer decisions about selected structural paths
→ later UNVERIFIED value extraction only
```

No field is approved merely because its key name looks familiar.

## Exact ancestry

The review builder receives the complete PR #52/PR #53 chain: verified evidence object, exact PR #52 receipt bytes, exact manifest/raw bytes, exact PR #53 assessment object and exact canonical PR #53 assessment bytes.

It reruns PR #53 from the underlying bytes and requires the supplied assessment object and bytes to match that exact rebuild. A hand-constructed or mutated structural assessment cannot become the basis for semantic review.

## Reviewer decision

Every `MatchDetailsFieldReviewDecision` identifies one exact observed structural path and one observed JSON kind. Disposition is either:

- `APPROVED`: reviewer explicitly accepts one path → Fixture Intelligence category/field semantic mapping as eligible for later **UNVERIFIED** extraction;
- `REJECTED`: reviewer explicitly declines/defer semantics for that structural path and carries no category/field mapping.

An approved decision is narrow:

- non-root path only;
- exact path must exist in PR #53 assessment;
- exactly one JSON kind must have been observed there;
- approved kind must be one of STRING, INTEGER, NUMBER or BOOLEAN;
- ARRAY, OBJECT and NULL cannot be approved in this boundary;
- array wildcard `/*` paths cannot be approved;
- approved pointer length is capped at 384;
- output field must obey the existing Fixture Intelligence field-name contract;
- category/field semantic targets must be unique within a review bundle.

Array semantics and cardinality require a dedicated later contract rather than silently flattening repeated records.

## Review timing

`reviewed_at` must use exact `datetime.timezone.utc`, must not predate evidence observation, and must remain strictly before fixture kickoff. `reviewer_reference` is mandatory, trimmed and bounded.

## What APPROVED does not mean

`APPROVED` means only that a human reviewer approved that **mapping definition** for this exact structural assessment. It does not mean:

- the raw value is correct;
- the source is qualified for that semantic capability;
- the value is fresh enough for a model;
- the value is corroborated;
- any Fixture Intelligence fact is SUPPORTED.

PR #54 performs no value extraction at all.

## Safety

The review bundle keeps all downstream authorization false, including automatic semantic review, source qualification, value extraction, Fixture Intelligence facts/snapshots, model features, probabilities, pricing, selection and betting.

PR #55 may consume an exact PR #54 review to extract only deterministic **UNVERIFIED** fact candidates from non-wildcard approved scalar paths.
