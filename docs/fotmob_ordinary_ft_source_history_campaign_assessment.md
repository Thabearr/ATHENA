# FotMob ordinary-FT source-history campaign assessment

## Purpose

This boundary records the first immutable post-execution assessment of the reviewed FotMob ordinary-FT source-history campaign. It consumes no network data and changes no runtime source capability. The full raw campaign remains external research evidence; this repository stores only a small canonical receipt anchored to the exact GitHub Actions artifact.

The assessment is deliberately fail-closed. The acquisition campaign succeeded, but acquisition success is not historical-completeness approval.

## Exact execution evidence

The reviewed campaign ran as GitHub Actions run `31887523012`, attempt `1`, against exact authorized repository `main`:

`12a32de1cca8ffb657f67fa4a8d3106aec6ce31b`

The workflow terminal state was:

`EXECUTION_COMPLETED_4410_SLOTS_EVIDENCE_ARTIFACT_PRESERVED`

Both the runner and post-run status exited `0`, and the workflow's campaign verification succeeded.

The preserved artifact is:

- artifact id: `9249856559`;
- artifact name: `fotmob-ordinary-ft-source-history-campaign-31887523012`;
- artifact size: `61,886,753` bytes;
- GitHub artifact SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- packaged research-cache tar SHA-256: `cbe665315258f7820e87265434d7a864c8e909cfb2e51950c56ed349860af5f6`.

The artifact is retained by GitHub through `2026-09-14T16:41:30Z`; the committed receipt remains the permanent small audit anchor, but full raw reproduction still requires preserved artifact bytes.

## Acquisition integrity result

The raw evidence independently rechecked as:

- every UTC request date from `2020-08-01` through `2026-08-14` present;
- `2,205` request dates;
- exactly `2,205` slot-A successes and `2,205` slot-B successes;
- exactly `4,410` successful slots;
- all successes occurred on attempt `1`;
- zero failed attempts;
- minimum same-date A/B observation separation `3,761.138022` seconds;
- maximum same-date A/B observation separation `7,454.335835` seconds;
- no unresolved inflight attempt;
- no stale runner lock.

Therefore campaign execution integrity and the frozen daily request schedule pass. The runner still correctly reports `historical_coverage_proven = false`.

## Pair stability discovery

`2,204` of `2,205` date pairs had byte-identical raw responses. The only raw difference was request date `2025-07-12`; it consisted of changing `liveTime` text in non-target competitions and did not change the terminal fixture set of the frozen target-league candidates.

This does not promote any unrelated live-state semantics. It only records why the single whole-response byte difference is not itself a target-history conflict.

## Eleven-league mapping discovery

The campaign proves that all eleven frozen candidate root ids are observable as FotMob `primaryId` values, but it also proves that an exact leaf `league.id` is not stable across all seasons/phases.

Examples include:

- B1 root `40`: season leaf ids include `868627`, `873802`, `880058`;
- G1 root `135`: season leaf ids include `869504`, `874482`, `880600`;
- N1 root `57`: season leaf ids include `868558`, `873789`, `879842`;
- SC0 root `64`: later season leaf ids include `873849`, `879858`, `886197`.

Names also drift while the root family remains visible, for example `First Division A` / `Belgian Pro League`, `Bundesliga` / `1. Bundesliga`, and `Liga Portugal` / `Primeira Liga`.

The acquisition protocol froze candidate competition ids/names/countries, but it did not pre-authorize treating `primaryId` as the canonical cross-season competition identity. The correct result is therefore:

`BLOCKED_LEAGUE_MAPPING_UNPROVEN`

The receipt's target-family counts are explicitly discovery-only groupings by the frozen candidate root `primaryId`; they are not an approved model-league mapping.

## Finished-result discovery

Under that discovery-only grouping, the artifact contains `21,367` unique terminal target-family fixture ids. The reviewed ordinary-FT gate admits `21,336` unique fixtures and exposes `31` unique fixtures requiring separate result semantics:

- `25` awarded wins (`AW / Awarded win`);
- `3` after-extra-time results (`AET / After extra time`);
- `3` after-penalties results (`Pen / After penalties`).

The ordinary-FT discovery counts by frozen model-league candidate are recorded in the canonical receipt. These counts do not authorize a history adapter because the mapping gate is still unresolved.

The observed special results force:

`BLOCKED_NON_ORDINARY_FT_RESULT_REQUIRES_SEPARATE_REVIEW`

They may not be silently dropped or coerced into ordinary full-time scores.

## Identity and chronology discovery

Fixture id `3932603` appears under the T1 candidate family on two different requested calendar dates with two different kickoff timestamps:

- request `2023-02-20`, kickoff `2023-02-20T17:00:00.000Z`;
- request `2023-03-05`, kickoff `2023-03-05T17:00:00.000Z`.

Both observations report an awarded 0-3 result. The same source fixture identity therefore carries rearranged chronology across the history. This is preserved as evidence and yields:

`BLOCKED_IDENTITY_OR_CHRONOLOGY_CONFLICT`

A later reviewed boundary must define how source fixture rescheduling/rearrangement is reconciled without double-counting or silently rewriting history.

## Initialization remains unproven

The frozen campaign start `2020-08-01` was only a candidate lower bound. The assessment does not prove that replaying the discovered FotMob competition families from that point is mathematically equivalent to PR #69's exact 1500 Elo replay initialization and source-fixture universe.

The result remains:

`BLOCKED_INITIALIZATION_BOUNDARY_UNPROVEN`

No ad-hoc reset point is introduced.

## Overall disposition

The assessment state is:

`EXECUTED_FAIL_CLOSED_HISTORICAL_COVERAGE_NOT_QUALIFIED`

with primary status:

`BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

The important positive result is that the acquisition itself is no longer the blocker: all 4,410 frozen captures exist with intact evidence lineage. The remaining blockers are semantic/reconciliation boundaries discovered from the real corpus.

## Safety

This receipt does not update `SOURCE_CAPABILITY_REGISTRY` and does not promote `historical_coverage`. It does not approve a source-history adapter or PR #80 constructor input and does not authorize successor models, expected goals, score matrices, probabilities, calibration, pricing, market activation, selection, production, or BET.

## Next reviewed boundaries

The receipt freezes the next required work as four separate concerns rather than weakening the completeness contract:

1. qualify FotMob `primaryId` / season-phase competition mapping semantics for all eleven model leagues;
2. qualify awarded, extra-time, and penalty result semantics or an explicit reviewed exclusion rule;
3. reconcile rearranged fixture identity/chronology, beginning with fixture `3932603`;
4. prove the resulting FotMob history initialization is equivalent to the frozen PR #69 replay-start semantics.

Historical completeness may be reconsidered only after those blockers are resolved from preserved evidence.
