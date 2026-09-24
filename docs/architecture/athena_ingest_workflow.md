# ATHENA canonical ingest workflow (P4.4B)

P4.4B introduces `.github/workflows/athena-ingest.yml` as a manual-only source
ingest surface. Its v1 provider is FotMob. The only dispatch input is a comma-separated
list of 1–7 strictly increasing Gregorian `YYYYMMDD` dates. UTC and NGA are fixed in
the request contract. The service makes one reviewed `/api/data/matches` request per
date using `fetch_fotmob_data_matches`, without acquisition retry, and stops after
the first failure.

The workflow has `contents: read`, the `athena-ingest-fotmob` concurrency group,
and a 20-minute job timeout. It requires the exact main commit before resolving the
request. It has no schedule; scheduled acquisition is deferred to P4.4C owner review.
Neither CI nor this PR acquires provider data.

The uploaded `athena-ingest-${{ github.run_id }}` artifact is retained for 30 days.
It contains one resolved request, exact raw `response.json` and reviewed capture
`manifest.json` bytes under `sources/fotmob/<date>/<capture-id>/`, an ingest receipt,
an immutable `canonical-store-update.json` source delta, and a replay manifest.
The delta is not a second production database. A partial failure preserves completed
source captures but marks the batch `CANONICAL_SOURCE_UPDATE_NOT_COMMITTED`. Every
final or partial runtime receipt binds the exact 40-character checked-out commit and
the last truthful processing stage. Invalid dispatch input produces a failure receipt
containing only the SHA-256 of the exact input bytes, not the raw input itself.

The service has a 900-second monotonic execution budget inside the 20-minute job
timeout. The remaining five minutes are configured separation for artifact
finalization, not a guarantee of upload duration. A budget timeout stops any later
date acquisition, preserves completed source captures, and emits a `TIMEOUT` receipt
with the canonical update marked not committed.

`python -m scripts.replay_athena_ingest_artifact --artifact-root <directory>` verifies
the artifact with zero network requests. It rechecks every raw and manifest digest,
reconstructs each source record, and requires the reproduced canonical update hash
to equal the original. The offline integration test builds a two-date artifact from
deterministic fake acquisition, removes acquisition capability, and replays that one
artifact. This satisfies the ingest replay gate without a live provider request.
Replay reports the original commit SHA from the receipt but does not consult Git or
require that commit to be the current checkout.

The ingest lane does not parse fixtures or grant model, pricing, routing, portfolio,
share-code, login, wallet, stake, or wager authority. Existing ingest-like and
provider diagnostic workflows stay live; this ADD transition proves no retirement
equivalence. P4.4 remains incomplete, and P4.4C will separately review schedule
activation and capability migration.
