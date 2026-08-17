# FotMob UTC-native successor feature qualification execution V2

## Why V2 exists

The first reviewed execution boundary was merged in PR #138 and was invoked once on run `31987862156` against main `2bd05e98cd74f9db6fa59472c05d5253f69d0f68`.

That V1 run did **not** execute the qualification runner. It failed inside the first authorization guard when the workflow attempted to create its durable PR attempt-marker comment. GitHub returned `403 Resource not accessible by integration` because the workflow had `pull-requests: read` while writing a comment on a pull request conversation required write authority in this environment.

The following V1 steps were therefore skipped:

- checkout of the authorized main SHA;
- frozen runner/dependency verification;
- preserved PR119 artifact download;
- the 21,326-row UTC-native feature qualification runner;
- receipt and feature-projection production.

The failure evidence was preserved as GitHub Actions artifact `9274313978`, named `fotmob-utc-native-feature-qualification-31987862156`, with SHA-256 `1a46808c8ee4d21ab67ec03b1fd6c0a80e79fadf04933092e7a106522e31c337` and size `2,388` bytes.

A durable reconciliation receipt was then recorded on PR #138 as comment `5311071999` with state:

`V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY`

V1 is spent and must not be replayed.

## V2 boundary

PR #139 is the reviewed reconciliation boundary. It adds a separate V2 workflow rather than mutating or replaying the spent V1 workflow.

V2 remains research-only. A successful run may establish the exact PR119-derived UTC-native feature projection and canonical receipt, but it does not authorize model training, expected-goals production use, probability inference, pricing, market activation, selection, production approval, or `BET`.

## Permission correction

The V2 workflow explicitly grants both:

- `issues: write`;
- `pull-requests: write`.

Static contract tests fail if the V2 workflow regresses to `pull-requests: read`.

## Reconciliation prerequisite

Before a V2 attempt marker may be created, the workflow must find the exact V1 reconciliation receipt on PR #138 and prove that it still contains:

- V1 run ID `31987862156`;
- V1 failure-evidence artifact ID `9274313978`;
- state `V1_SPENT_GUARD_PERMISSION_FAILURE_NO_QUALIFICATION_EXECUTED_DO_NOT_REPLAY`.

If that receipt is absent or changed, V2 fails closed before execution.

## Frozen input

V2 must consume only preserved GitHub Actions artifact ID `9249856559`:

- artifact name: `fotmob-ordinary-ft-source-history-campaign-31887523012`;
- artifact size: `61,886,753` bytes;
- artifact SHA-256: `7c2fa200efed098bd5fca22fc139af816256c74967b98d8cb2c62fe3e793508f`;
- source workflow run: `31887523012`;
- source head SHA: `12a32de1cca8ffb657f67fa4a8d3106aec6ce31b`.

The artifact must still be live, metadata-exact, and its downloaded archive bytes must exactly match the frozen SHA-256 and size.

## Frozen implementation identities

Execution must pin and verify these Git blob identities on the explicitly authorized `main` SHA:

- qualification domain runner: `9c9e424791b65292f7bbe8849b3214c140834889`;
- qualification CLI: `68503c85569f31532a1a810249073c36242055e0`;
- PR #134 UTC-native protocol: `57cc133a7fb9daa76c5d5d8e9156903e583c6575`;
- PR #119 materialization executor: `2409676b4993a25024e2e8554e84e3525e7c5e6e`;
- `requirements.txt`: `54d24a55dfa4c73ba3910d333257cfd2e68daf4b`.

## V2 one-shot authorization

After PR #139 is separately reviewed and merged, V2 execution requires one exact owner comment on closed/merged PR #139:

```text
/athena-run-fotmob-utc-native-feature-qualification-v2
main-sha: <exact-current-main-40-hex>
confirm: EXECUTE_RECONCILED_21326_UTC_NATIVE_FEATURE_QUALIFICATION_V2
```

The workflow rejects malformed framing, a moved `main`, an unmerged control PR, a missing/changed V1 reconciliation receipt, altered frozen implementation identities, altered/expired source evidence, or a prior V2 attempt marker.

Once the V2 attempt marker exists, automatic replay is forbidden even if V2 later fails. Preserved evidence must be reviewed before any further execution boundary.

## Required V2 outputs

The run preserves, even on failure where possible:

- V2 execution metadata including V1 reconciliation ancestry;
- exact source artifact metadata and downloaded archive SHA-256/size;
- runner log and exit code;
- canonical qualification receipt when produced;
- canonical 21,326-row UTC-native NDJSON projection when produced;
- SHA-256 manifest for packaged V2 evidence;
- fail-closed result verification.

A successful V2 verification must prove at minimum:

- qualification status `QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION`;
- qualification state `EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED`;
- exactly `21,326` records and unique fixture identities;
- zero identity/lineage conflicts;
- historical live-data freshness remains blocked for all historical rows;
- preserved PR119 artifact identity remains exact;
- receipt projection SHA-256/size equal the actual emitted NDJSON;
- every downstream safety/authority flag remains `false`;
- next boundary remains `PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL`.

## V2 result states

Successful V2 evidence is recorded as:

`EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2`

Any incomplete or failed V2 execution after the attempt marker is recorded as:

`EXECUTION_NOT_QUALIFIED_V2_REVIEW_ARTIFACT_BEFORE_ANY_RETRY`

Neither state itself grants model, probability, pricing, selection, production, or BET authority.
