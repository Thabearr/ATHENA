# FotMob fresh-holdout request-date spillover review

## Preserved production evidence

Scheduled collector run `32612280129` resolved nominal slot `2026-08-23T01:37:00Z`, acquired live network evidence, then failed closed while qualifying the `20260823` capture. The failure archive is `failure-20260823T013700Z-run-32612280129.tar.gz` (Actions artifact `9485854548`, archive SHA-256 `359524b3477da9fc46a60dde41a0a2179631d735e1de4bfce7cea6fb1c6aa60c`).

The failing `20260823` capture was observed at `2026-08-23T02:13:12.040926Z`, raw SHA-256 `445bc09a013fabf3bd953e2980ee54bee6e1fb8ab50f4686ab2de67bea02c023`, manifest SHA-256 `7b763b0e55126529f1fd4879a2fe0170215ee3f467a28caad538ef77c8b561a8`.

Two rows in that exact response were grouped by the provider into the requested `20260823` payload while their explicit UTC kickoffs were on `20260822`:

- fixture `1000014538`: `status.utcTime=2026-08-22T23:07:00.000Z`, provider display `time=23.08.2026 01:07`;
- fixture `1000008693`: `status.utcTime=2026-08-22T23:30:00.000Z`, provider display `time=23.08.2026 01:30`.

For both rows, `timeTS` agrees with the explicit UTC kickoff. The failure therefore comes from frozen PR39's request-date-equals-kickoff-UTC-date rule, not from a timestamp disagreement.

## Reviewed compatibility boundary

The compatibility layer does not weaken PR39. The original network bytes remain immutable evidence. When this exact structural condition is present, the payload is partitioned by explicit UTC kickoff date and every partition is separately re-run through the reviewed PR89 -> PR87 -> PR39 chain using validation-only projected manifests.

Only an immediately previous UTC date is admitted as spillover, and only when the provider display `match.time` date equals the exact requested bucket date. Any older/future date, malformed display date, timestamp mismatch, unreviewed key, extra-half type drift, duplicate identity, or dependency drift still fails closed.

Only fixtures whose explicit UTC kickoff date equals the exact request date are returned to the fresh candidate population. Spillover fixtures are structurally validated but are not promoted to prospective fresh candidates. Returned fixtures remain bound to the original network capture raw and manifest SHA-256 values.

## Settlement boundary

The frozen ordinary-FT score adapter remains unchanged and continues reading original network bytes. Its PR89 structural hook is bridged through the same partition validation so request-bucket spillover cannot bypass structural review. No kickoff, score, reason, result, extra-time, model, pricing, selection, production, or BET semantics are changed.
