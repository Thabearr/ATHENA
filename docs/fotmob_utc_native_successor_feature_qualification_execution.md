# FotMob UTC-native successor feature qualification execution

## Boundary

This control PR authorizes no execution by itself. It exists to review the exact one-shot GitHub Actions wrapper that may later execute the already-merged PR #136 offline qualification runner against the exact preserved PR #119 FotMob campaign artifact.

The execution result is research evidence only. A successful run may establish the exact PR119-derived UTC-native feature projection and receipt, but it does not authorize model training, expected-goals production use, probability inference, pricing, market activation, selection, production approval, or `BET`.

## Frozen input

The workflow must consume only preserved GitHub Actions artifact ID `9249856559`:

- artifact name: `fotmob-ordinary-ft-source-history-campaign-31887523012`
- artifact size: `61,886,753` bytes
- artifact SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`
- source workflow run: `31887523012`
- source head SHA: `12a32de1cca8ffb657f67fa4a8d3106aec6ce31b`

The artifact must still be live and must match those metadata before execution.

## Frozen implementation identities

Execution must pin and verify these Git blob identities on the explicitly authorized `main` SHA:

- qualification domain runner: `9c9e424791b65292f7bbe8849b3214c140834889`
- qualification CLI: `68503c85569f31532a1a810249073c36242055e0`
- PR #134 UTC-native protocol: `57cc133a7fb9daa76c5d5d8e9156903e583c6575`
- PR #119 materialization executor: `2409676b4993a25024e2e8554e84e3525e7c5e6e`
- `requirements.txt`: `54d24a55dfa4c73ba3910d333257cfd2e68daf4b`

The merged runner itself revalidates the frozen PR #134 protocol SHA-256/size and re-executes the preserved PR #119 evidence path before constructing UTC-native features.

## One-shot authorization

After this control PR is reviewed and merged, execution requires one exact owner comment on this same closed/merged PR:

```text
/athena-run-fotmob-utc-native-feature-qualification
main-sha: <exact-current-main-40-hex>
confirm: EXECUTE_21326_UTC_NATIVE_FEATURE_QUALIFICATION
```

The workflow must reject malformed framing, a moved `main`, an unmerged control PR, a moved/frozen implementation identity, an altered/expired artifact, or any prior execution-attempt marker. Once an attempt marker exists, automatic replay is forbidden even if the run fails; preserved evidence must be reviewed before any new execution boundary.

## Required execution outputs

The run must preserve, even on failure where possible:

- execution metadata;
- artifact metadata and downloaded artifact SHA-256;
- runner log and exit code;
- canonical qualification receipt when produced;
- canonical 21,326-row UTC-native NDJSON projection when produced;
- SHA-256 manifest for packaged evidence;
- fail-closed verification result.

A successful verification must prove at minimum:

- qualification status `QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION`;
- qualification state `EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED`;
- exactly `21,326` output records and unique fixture identities;
- zero identity/lineage conflicts;
- historical live-data freshness remains blocked for all historical rows;
- upstream preserved artifact identity remains exact;
- receipt projection SHA-256/size equal the actual emitted NDJSON;
- every safety/authority flag remains `false`;
- next boundary is `PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL`.

## Result states

Successful execution evidence is recorded as:

`EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED`

Any failure or incomplete verification is recorded as:

`EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY`

No failure may silently downgrade into model or production authority.
