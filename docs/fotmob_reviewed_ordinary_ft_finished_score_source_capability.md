# Reviewed FotMob ordinary-FT finished-score source capability

## Purpose

This boundary performs the narrow registry mutation qualified by PR #97. It registers a **new derived adapter-scoped source key** for reviewed FotMob ordinary-FT source-reported finished scores.

It does not mutate the parent reviewed catalog capability, qualify historical coverage, broaden score semantics to penalties or other reason states, or authorize source history, modelling, probability inference, pricing, selection, production, or betting.

## Exact registration

Parent source key, unchanged:

```text
fotmob_data_matches_reviewed_catalog
full_time_score            NOT_CAPTURED
half_time_score            NOT_CAPTURED
event_timestamps           NOT_CAPTURED
reliable_fixture_identity  CONFIRMED
historical_coverage        UNKNOWN
freshness_metadata         NOT_CAPTURED
```

New derived source key:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
full_time_score            CONFIRMED
half_time_score            NOT_CAPTURED
event_timestamps           NOT_CAPTURED
reliable_fixture_identity  CONFIRMED
historical_coverage        UNKNOWN
freshness_metadata         NOT_CAPTURED
```

The derived capability uses the exact proposed evidence and notes frozen by the PR #93 capability-promotion protocol.

## Meaning of `CONFIRMED`

`full_time_score = CONFIRMED` means only **source-reported finished score for fixtures that pass the exact reviewed ordinary-FT gate through the reusable prospective adapter**.

It does not establish:

- regulation-time score semantics;
- extra-time score semantics;
- penalty-score semantics;
- bookmaker-settlement semantics;
- global FotMob `status.reason` semantics;
- historical completeness;
- freshness metadata;
- model readiness, pricing, selection, production approval, or betting authority.

Penalty fixture `5844873` remains outside this derived capability. The validated PR #96 evidence remains 29 terminal candidates, 28 qualified ordinary-FT score outputs, and one penalty fixture blocked.

## Historical receipt compatibility

PR #96 and PR #97 recorded the derived key as absent **at their exact execution/assessment trees**. This registration does not rewrite those historical facts. Their canonical receipts remain unchanged and revalidatable after this later reviewed registry mutation.

Likewise, older protocols that froze the pre-registration `domain/source_capabilities.py` blob continue to refer to that historical blob identity rather than asserting that the current registry file can never evolve.

## Safety consequence

The only new current capability claim is the separate derived ordinary-FT `full_time_score = CONFIRMED` entry. The parent remains identity-only and historical coverage remains `UNKNOWN`.

Therefore this registration does not yet clear the source-history completeness boundary required by the successor feature-construction chain. Any historical acquisition/completeness qualification remains a separate reviewed task.
