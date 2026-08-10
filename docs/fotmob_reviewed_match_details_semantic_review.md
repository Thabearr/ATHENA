# Reviewed FotMob match-details semantic review

## Purpose

PR #54 adds the explicit human-review boundary after PR #53's semantics-free structural inventory.

```text
PR #52 exact persisted evidence verification
→ PR #53 strict structure only
→ PR #54 explicit human field-semantics decisions
→ later exact-value extraction candidates
```

This PR does **not** claim that a field is trustworthy merely because its key name looks familiar. It also does not create Fixture Intelligence facts.

## Exact ancestry gate

`build_reviewed_match_details_semantic_review(...)` requires:

- the exact PR #53 assessment object;
- the exact canonical bytes of that PR #53 assessment;
- the exact PR #52 verified evidence object and canonical receipt bytes;
- the exact persisted `manifest.json` bytes;
- the exact persisted `response.json` bytes.

The builder reruns PR #53 from the PR #52/raw-evidence chain, canonicalizes both the supplied and rebuilt PR #53 assessments, and requires:

```text
supplied assessment bytes
= rebuilt assessment bytes
= caller-presented PR #53 bytes
```

A mutated, detached, stale, or reserialized assessment therefore cannot silently cross this boundary.

## Human decisions

Every `ReviewedMatchDetailsFieldDecision` refers to one exact structural `json_pointer` that must actually exist in PR #53 and must repeat the exact observed JSON-kind tuple.

A decision is either:

- `APPROVED` — the reviewer explicitly supplies an ATHENA `IntelligenceCategory`, a strict lowercase logical field name, and `PRIMARY_FOOTBALL_CONTEXT`; or
- `REJECTED` — the decision carries no category, logical field, or source role.

Every decision requires a non-empty rationale. A path may be reviewed at most once in one review artifact. Decisions are sorted deterministically by structural path.

An `APPROVED` decision means only: **for this exact reviewed evidence, a human explicitly accepted this structural path as having the stated semantic label.** It does not prove completeness, freshness beyond the captured observation time, factual correctness, corroboration, or suitability for a model.

## Review provenance

The review records:

- exact PR #53 SHA-256;
- exact PR #52 evidence-receipt SHA-256;
- manifest and raw-evidence SHA-256;
- source-scoped fixture and match identity;
- kickoff and evidence observation time;
- exact UTC human review time;
- reviewer reference and notes;
- every explicit approved/rejected field decision.

`reviewed_at` must not predate the evidence observation. It may be after kickoff because PR #54 is an audit/review boundary, not a prospective-use grant.

## Deliberate non-authorizations

PR #54 performs no network acquisition and no filesystem write. It does not authorize:

- automatic semantic review;
- broad FotMob source qualification;
- value extraction;
- Fixture Intelligence fact or snapshot creation;
- model features;
- probabilities;
- pricing;
- selections;
- bets.

All downstream safety flags remain exact `false`.

## Next boundary

PR #55 may consume an exact PR #54 review and the same exact raw evidence to extract **only explicitly approved paths** into provenance-backed, still-unverified semantic candidates. It must rerun this full chain and must not silently promote those candidates to `SUPPORTED` Fixture Intelligence facts.
