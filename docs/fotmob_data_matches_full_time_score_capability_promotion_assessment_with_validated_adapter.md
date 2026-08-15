# Reviewed FotMob full-time-score capability assessment with validated adapter

## Purpose

PR #97 re-executes the frozen PR #93 scoped capability-promotion decision after the missing reusable score adapter has been built and independently validated.

This is still an assessment-only boundary. It does **not** change `domain/source_capabilities.py`, mutate the parent reviewed catalog, register the derived source key, prove historical coverage, or authorize source history, modelling, probability inference, pricing, selection, production, or betting.

## Exact base

```text
main 1831c9d6d631cf249c40e4352959be1905b1c01e
tree ba682efd2e90660dd9e40371ad5b135c1212a2b3
```

The base is the verified PR #96 merge.

## Frozen ancestry

PR #97 binds the current repository blobs and canonical identities for:

```text
PR93 capability-promotion protocol blob 27df60b90aa29273aeef4b8e9a51992c5c57cf9b
PR93 canonical SHA256              8606367857915046eb27b9f2bf751514e52e266966b23caf598d1fedbf6b4009
PR94 prior assessment blob         e81be529acc5471e875d4c619e9f77e885217716
PR94 canonical SHA256              adfe1a6e0103a65c30ed19026940bfb5474c63dc44328b7c632ea8dbe15d2eb5
PR95 reusable adapter blob         868563206e09010fce74b4ba7954028930baad54
PR96 validation blob               d6ad05c778669b976c4a475080da845cc8bf47cb
PR96 receipt SHA256                09dd9fdff1eddb7b421e968c8de93262b09ce526adeb3d3b95050ddf1f2d4562
source-capability registry blob    ffd9730d6675a7dbcc9e8622d6e9844b772b6f96
```

PR #94 remains a valid historical fail-closed receipt: at that assessed tree the reusable adapter was not yet implemented, so registration was blocked. PR #97 does not rewrite that history. It proves that the exact missing boundary has since been satisfied by PR #95 and validated by PR #96.

## Exact validated-adapter evidence

PR #96 froze:

```text
terminal candidate union          29
qualified ordinary-FT scores      28
excluded penalty fixtures          1
excluded penalty fixture     5844873
adapter result SHA256        7e3fcb2c8a4fa8f883ec7dcac2fd15ea8d2f1aa359c5c5f42ab7eaf604bdce27
qualified projection SHA256  ffdb20556808a1a6459d959b050e3aa5780f3c017d6971adf0c17a3c91ce03ab
```

The penalty fixture remains outside the ordinary-FT score capability.

## Assessment result

PR #97 reaches:

```text
QUALIFIED_SCOPED_ORDINARY_FT_FULL_TIME_SCORE_CAPABILITY_REGISTRATION
```

All assessment gates pass:

1. exact PR #93 protocol ancestry;
2. unchanged identity-only parent capability;
3. derived source key absent before registration;
4. exact reusable PR #95 adapter present;
5. exact PR #96 adapter validation qualified;
6. capability scope and penalty exclusion unchanged;
7. derived registration qualification passes.

The source-capability registry update is explicitly `NOT_PERFORMED`. Registry mutation remains the next separate reviewed boundary.

## What would be registered later

The parent remains:

```text
source                     fotmob_data_matches_reviewed_catalog
full_time_score            NOT_CAPTURED
reliable_fixture_identity  CONFIRMED
historical_coverage        UNKNOWN
```

The proposed separate derived key remains:

```text
fotmob_data_matches_reviewed_ordinary_ft_finished_score
```

If the later registration boundary succeeds, its exact scoped capability contract is still the PR #93 contract:

```text
full_time_score            CONFIRMED
half_time_score            NOT_CAPTURED
event_timestamps           NOT_CAPTURED
reliable_fixture_identity  CONFIRMED
historical_coverage        UNKNOWN
freshness_metadata         NOT_CAPTURED
```

`CONFIRMED` means only source-reported finished score for fixtures that pass the exact reviewed ordinary-FT gate. It does not establish regulation-time score, extra-time treatment, penalty-score semantics, bookmaker settlement, global `status.reason` semantics, historical completeness, or freshness.

## Canonical PR97 receipt

```text
sha256 edec152475a4c964084cdee1ba7c6a7385457297b63acf4a81e683dc74e99e03
size   5369 bytes
```

The canonicalizer accepts only the exact qualified assessment. Mutation of registration qualification, proposed capabilities, penalty exclusion, gate outcomes, registry-update state, or any safety flag fails closed.

## Safety boundary

All downstream and broadening authority remains false. In particular:

- no network acquisition;
- no source-capability registry mutation in this PR;
- no parent-source mutation;
- no global FotMob full-time-score capability;
- no historical-coverage qualification;
- no regulation/extra-time/penalty/settlement semantics;
- no source-history approval;
- no model/probability/calibration/pricing/market activation;
- no selection, production approval, or BET authority.

## Next boundary

```text
REGISTER_REVIEWED_FOTMOB_DATA_MATCHES_ORDINARY_FT_FINISHED_SCORE_CAPABILITY
```

That boundary may add only the separately derived adapter-scoped source key under the exact PR #93 capability contract. The parent reviewed catalog must remain unchanged and the penalty fixture/semantic exclusions must remain enforced.
