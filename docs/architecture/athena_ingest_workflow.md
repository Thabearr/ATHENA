# ATHENA canonical ingest workflow (P4.4B / P4.4C)

P4.4B introduced `.github/workflows/athena-ingest.yml` as a manual-only source-ingest
surface. P4.4C adds the first daily canonical ingest schedule, `0 8 * * *` UTC. A
scheduled event resolves exactly one date: the current Gregorian date at request
resolution, derived from a timezone-aware UTC clock. It never catches up, backfills,
or expands to a rolling range. Manual `workflow_dispatch` remains unchanged: its sole
input is a comma-separated list of 1–7 strictly increasing Gregorian `YYYYMMDD` dates.
The v1 provider remains FotMob; UTC and NGA are fixed in the canonical request.
Each requested date gets one reviewed `/api/data/matches` request through
`fetch_fotmob_data_matches`, with no acquisition retry, and the service stops after
the first failure. A scheduled run therefore makes at most one provider request.

The workflow has `contents: read`, the `athena-ingest-fotmob` concurrency group,
`cancel-in-progress: false`, a 20-minute job timeout, and a 900-second service budget.
The non-terminal shell preflight checks exact HEAD and main ref, the resolver requires
`refs/heads/main`, and the executor independently verifies the checked-out commit
against the expected SHA before acquisition. While P4.4C is open and unmerged, scheduled
acquisition is not active on main; implementation and review validation perform zero
provider requests. If the owner merges P4.4C, GitHub schedule activation permits one
bounded FotMob request for the current UTC date per daily scheduled run. That does not
authorize backfill, SportyBet, share-code creation, login, cookies, wallet, staking,
betting, or wager activity, and does not alter model, routing, or portfolio authority.
P4.4C intentionally changes the provider-acquisition trigger surface: automatic
canonical FotMob acquisition becomes permitted only if merged. It adds no provider
family, and does not change manual acquisition authority or any non-ingest authority.

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
share-code, login, wallet, stake, or wager authority. P4.4C reviewed exactly the five
frozen P4.3A `ATHENA_INGEST_FUTURE` workflows. The historical warehouse builder,
ordinary-FT source-history campaign, and prospective player-context campaign remain
distinct research/warehouse capabilities; the older current-reviewed-source path is
retained pending an exact compatibility adapter; and canonical Drive transfer remains
an archive-transfer capability. All five remain non-equivalent and unretired. No
legacy workflow is deleted by P4.4C. P4.4 and Architecture Checkpoint E remain
incomplete; after a P4.4C merge, the mandatory 5/5 architecture/source reread is
required before another remediation mission.

## P4.4D current-reviewed source compatibility boundary

P4.4D adds an offline adapter for exactly one already-completed canonical FotMob
capture whose request is one date, `timezone=UTC`, and `ccode3=NGA`. It requires a
successful committed canonical-source update, one network-acquired source record,
exact raw/manifest verification, and a successful canonical offline replay. The
adapter consumes the verified source in place under
`sources/fotmob/<date>/<capture-id>/`; it makes zero provider requests and does not
copy or rewrite the source bytes.

That exact source is projected through the existing PR243 current-reviewed
fixture-identity policy, catalog handoff/admission, and fixture bootstrap. The
existing legacy capture root and caller behavior remain the default. Noncanonical
timezone/ccode3 requests are not compatible, and this adapter does not claim full
legacy request-contract or workflow equivalence. The legacy
`issue-current-fotmob-reviewed-source.yml` workflow remains unchanged and live;
P4.4D grants no retirement authority. A later caller migration requires its own
review. No fixture-intelligence, model, probability, pricing, routing, portfolio,
share-code, account, or wagering authority is added. P4.4 and Architecture
Checkpoint E remain incomplete.

P4.4C's Actions run history is a read-only snapshot captured at
`2026-09-24T01:53:50Z`. Each run is the latest observed at that capture cutoff, not a
live pointer; later issue-comment or other workflow runs do not invalidate that
historical snapshot. The source-controlled auditor pins the capture timestamp,
run identities, row metadata, and frozen P4.3A dependency evidence.

## P4.4C rollback plan

For an emergency operational stop after merge, disable **ATHENA Canonical Ingest** in
GitHub Actions. This disables both its scheduled and manual executions. Do not fall
back automatically to a legacy acquisition workflow, and do not backfill missed
dates. This operational stop does not rewrite source history.

A permanent source rollback targets the exact P4.4B manual-only workflow identity:
blob `7f5fecabd8ada0ccac1fb35a8d2749601cc293c7`, source SHA-256
`acdb74d306e7cd2220123186112ee5ae197b7719761e304e7e3cd08dea628cbe`. It must append
a new reviewed ordinary `REVISE` transition restoring those manual-only bytes. It
must preserve P4.4C transition 4, its immutable checkpoint snapshot and receipt, and
the migration-review artifact; it must never delete or rewrite transition 4 to imply
that schedule activation did not occur. If PR #394 merges, source review reaches 5/5;
the mandatory architecture/source reread is required before the next normal
remediation mission. If an emergency stop is needed before then, disable the workflow
operationally rather than bypassing that reread with an unreviewed code change.

## P4.4E activation-ready current-source issuer seam

P4.4E composes the existing `AthenaIngestRequest`, shared
`execute_ingest_request(...)` service, and P4.4D offline compatibility adapter for
exactly one FotMob date with fixed `timezone=UTC` and `ccode3=NGA`. The issuer
requires the actual checked-out commit to equal the expected 40-character main
commit, and it only projects a successful one-request canonical ingest. Provider
transport remains owned by the canonical ingest service; the P4.4D projection
makes zero additional requests and consumes the verified capture in place.

This is an internal service seam only. It is not referenced by a workflow or a
supported live caller, and it does not modify the canonical ingest request schema,
either protected workflow, or the legacy current-reviewed issuer. The legacy
workflow remains live and unchanged; non-UTC/NGA inputs are not supported by this
compatibility seam. P4.4E does not claim full legacy workflow equivalence or
retirement authority. Caller migration is a later reviewed step. P4.4 and
Architecture Checkpoint E remain incomplete.

## P4.4F current-reviewed caller migration

P4.4F changes only the exact UTC/NGA lane of the existing
`issue-current-fotmob-reviewed-source.yml` workflow. That one-date FotMob request
uses the shared canonical ingest service, then the P4.4D compatibility adapter and
P4.4E issuer seam. The workflow continues to expose its existing manual date,
timezone, and ccode3 inputs. Every non-UTC/NGA combination remains on the legacy
issuer path; neither the legacy issuer nor its workflow is deleted or disabled.

The canonical source stays under `artifacts/athena-ingest-workflow/`; it is not
copied or rewritten into the legacy capture directory. The execution summary path,
artifact name, and retention remain stable, and a canonical failure has no retry or
legacy fallback. This is an exact-subset caller migration only: full legacy
equivalence and retirement authority are not claimed.

The migrated lane changes live provider execution behavior if merged. The bounded
owner-authorized compositional operational proof is complete for 2026-09-26 on exact
main `42341585c37a5e346b3aaea5cb550f004fa3f6a4`: one FotMob request produced a
successful committed canonical ingest with one source. The proof process then hit a
Windows proof-environment-only missing-`tzdata` blocker after acquisition; no retry
or second provider request was made. With `tzdata==2026.4` isolated outside the
repository, the same immutable artifact replayed offline and the P4.4D/PR243
projection verified 26 reviewed fixtures with zero adapter/provider requests and
`wager_placed=false`. The exact proof is frozen in
`artifacts/architecture/p4_4f_operational_proof_v1.json` (file SHA-256
`4740158a4b5b51764dbed1cf438544ddb05859dc0a5a353da385d1679c04b873`).
No workflow was dispatched. P4.4 and Architecture Checkpoint E remain incomplete.

## P4.4G canonical-only current-source workflow boundary

P4.4G leaves the proven UTC/NGA provider path unchanged and narrows only the
legacy compatibility branch of `issue-current-fotmob-reviewed-source.yml`.
The existing manual date/timezone/ccode3 request surface remains visible for
compatibility, but a non-UTC/NGA request now fails closed before provider
transport with an explicit unsupported-scope receipt. No legacy issuer, retry,
or automatic fallback is invoked by that path.

A read-only Actions review captured every workflow run returned at the P4.4G
review cutoff `2026-09-24T22:28:53.032418Z`: 12 workflow-dispatch runs, 11
successes and one failure. The authenticated job logs record UTC/NGA for all 12
runs. The source-controlled history receipt records that no noncanonical use was
observed while also stating that historical absence is not future capability
authority.

The legacy `scripts/issue_current_fotmob_reviewed_source.py` entry point is not
deleted or modified. It remains evidence/rollback/local-compatibility code, but
no live GitHub workflow calls it after P4.4G. The hosted UTC/NGA lane continues
to call `scripts/issue_current_fotmob_reviewed_source_via_ingest.py`, whose
P4.4F operational proof remains the applicable live proof because its provider
semantics are unchanged.

Implementation and review perform zero workflow dispatches and zero provider
requests. Workflow count remains 38, no workflow retirement is authorized, and
all model/pricing/routing/portfolio/share-code/account/wager authority remains
unchanged. P4.4 and Architecture Checkpoint E remain incomplete.

While P4.4G remains unmerged, `SOURCE_REVIEW_COUNTER = 3/5`; it becomes `4/5`
only after an owner-authorized merge. The mandatory five-review source reread is
therefore not due yet.
