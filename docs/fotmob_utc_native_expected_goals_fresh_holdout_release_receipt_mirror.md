# FotMob UTC-native xG fresh-holdout release receipt mirror

## Boundary

The reviewed fresh-holdout collection workflow already preserves every completed tick in two places:

1. a GitHub Actions artifact with `retention-days: 90`; and
2. a long-lived GitHub Release archive under the weekly `athena-fresh-holdout-evidence-YYYY-Www` tag.

The Actions artifact contains both the cumulative state archive and `fresh-holdout-tick-receipt.json`. The canonical receipt records the archive SHA-256, byte size, run ID, nominal schedule slot, release tag/name, tick exit code and committed state.

Before this boundary, the long-lived Release retained only the `.tar.gz` archive and the collection workflow rechecked only its byte size. The canonical SHA-256 receipt remained inside the 90-day Actions artifact. That is too weak for a holdout whose hard close itself is 90 days after start and whose final settlement tail extends a further 24 hours: the oldest Actions artifact can reach retention at the moment the result-review lane needs to replay the oldest evidence.

This PR adds a **post-run provenance mirror**. It does not change the collection runner.

## Trigger

The new workflow runs only from GitHub's `workflow_run` completion event for:

`FotMob UTC-Native xG Fresh-Holdout Collection Runner`

The mirror script independently requires the source run to be:

- the exact reviewed workflow name/path;
- `event == schedule`;
- `status == completed`;
- `head_branch == main`.

There is no `schedule` trigger and no `workflow_dispatch` trigger in the mirror workflow. It cannot create or replay a FotMob observation slot.

## Exact artifact verification

For source run `R`, the completed collection run must expose exactly one unexpired evidence Actions artifact matching:

`(success|failure)-YYYYMMDDTHHMMSSZ-run-R.tar.gz`

The downloaded Actions artifact ZIP must contain exactly two safe root members:

- that cumulative `.tar.gz` archive; and
- `fresh-holdout-tick-receipt.json`.

Traversal, absolute paths, directories, symlinks, duplicate names and unexpected members fail closed.

The receipt must be canonical compact sorted-key UTF-8 JSON with exactly one trailing newline. Duplicate JSON keys fail closed.

The mirror rechecks:

- exact workflow run ID;
- exact durable archive name;
- weekly release-tag syntax;
- nominal schedule identity and `:07` / `:37` cadence;
- nominal timestamp encoded in the archive name;
- archive SHA-256;
- archive byte size;
- success => zero exit + committed tick;
- failure => non-zero exit + uncommitted tick.

## Long-lived Release verification

The mirror then opens the exact release tag named by the canonical receipt and requires exactly one uploaded release asset with the archive's exact name.

It **downloads the long-lived release archive bytes themselves**, rather than trusting release metadata alone, and requires:

- exact byte size equal to the canonical receipt;
- exact SHA-256 equal to the canonical receipt;
- byte-for-byte equality with the archive recovered from the authoritative Actions artifact.

Only after the release archive passes those checks may the receipt be mirrored.

## Canonical receipt sidecar

The long-lived sidecar name is unique per evidence archive:

`<archive-name>.receipt.json`

The exact canonical receipt bytes from the Actions artifact are uploaded without clobbering an existing asset.

If the receipt sidecar already exists, the operation is idempotent only when the downloaded release receipt is byte-for-byte identical to the authoritative Actions receipt. A same-name but different receipt is a hard failure.

After a new upload, the workflow reloads the release, downloads the receipt sidecar, and rechecks exact bytes and SHA-256.

The result is that every long-lived archive can retain its own canonical cryptographic commitment after the 90-day Actions artifact expires.

## Reviewed implementation pin

The post-run workflow pins:

- `actions/checkout` to immutable commit `11d5960a326750d5838078e36cf38b85af677262`;
- `actions/setup-python` to immutable commit `a26af69be951a213d495a4c3e4e4022e16d87065`;
- `scripts/mirror_fotmob_fresh_holdout_release_receipt.py` to Git blob `b311f3136c6b06dfbe40babd66a2fb9fdf18fedf`.

Changing the implementation file without a corresponding reviewed workflow-pin change causes the mirror job to fail closed.

## Safety

This boundary performs GitHub repository/release evidence transport only.

It performs no:

- FotMob/provider request;
- prospective capture;
- backfill or retry of a missed schedule slot;
- prediction construction;
- settlement construction;
- model fit or refit;
- calibration calculation;
- probability or ScoreMatrix inference;
- SportyBet access;
- pricing, market activation, selection, ACCA/slip, booking-code, execution or BET authorization.

The existing PR #150/151 collection cadence, request dates, source semantics, runner code and holdout start remain unchanged.

## Future source replay

The later fresh-holdout confirmation source-replay boundary should prefer these long-lived paired assets when an old Actions artifact is unavailable:

- exact cumulative archive bytes; and
- exact canonical `<archive>.receipt.json` bytes.

It must still reconstruct and revalidate the underlying PR #151 journals/source evidence and invoke the frozen PR #167 evaluator only after the selected close plus settlement tail. The existence of a durable receipt does not itself grant model or production authority.
