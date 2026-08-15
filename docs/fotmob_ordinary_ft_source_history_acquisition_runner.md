# Reviewed FotMob ordinary-FT source-history acquisition runner

PR #102 implements the deterministic, resumable runner required by the frozen
PR #101 acquisition protocol. It **does not execute the historical campaign**,
prove historical coverage, materialize result history, or authorize any model,
probability, pricing, selection, production, or betting path.

## Frozen upstream boundary

The implementation revalidates PR #101 exactly:

- protocol SHA-256:
  `cfd8542df66c9e8fbe748f0559d67c336d41e441f3b4de8d6601ac1087cad3a6`
- protocol size: `8511` bytes
- request timezone: `UTC`
- `ccode3=NGA`
- dates: `2020-08-01` through `2026-08-14` inclusive
- required dates: `2205`
- slots: all `A` dates ascending, then all `B` dates ascending
- successful slots required for a complete campaign: `4410`
- same-date A/B separation: `300..86400` seconds inclusive
- minimum inter-request separation: `1.0` second
- attempts per slot: at most `3`
- retry delays after attempts one and two: `60s`, then `300s`

The eleven model-league/FotMob mapping candidates remain discovery-only and are
not qualified by this runner.

## Implementation split

`domain/fotmob_ordinary_ft_source_history_acquisition_runner.py` is network-free.
It owns deterministic planning, journal schemas, canonical serialization,
hash-chain validation, resume state, retry timing, and the A/B pair-window gate.

`scripts/run_fotmob_ordinary_ft_source_history_acquisition.py` is the thin live
executor. It reuses the already-reviewed
`scripts/capture_fotmob_data_matches.py` transport and
`domain/fotmob_data_matches_capture.py` verifier at their PR #101-pinned Git
blob identities. No alternate HTTP client, proxy path, browser impersonation,
cookie path, or request identity is introduced.

## Append-only research evidence

Campaign control/evidence lives only under the ignored research root:

`.cache/athena-research/fotmob-ordinary-ft-source-history-campaign-v1/`

The durable artifacts are:

- `campaign-index.jsonl` — successful qualifying slot captures;
- `failure-journal.jsonl` — failed attempts and terminal slot blockers;
- `inflight-attempt.json` — a single durable pre-request intent marker;
- `runner.lock` — concurrent execution guard.

The index and failure journal share one global contiguous `sequence` and SHA-256
hash chain. Every entry binds the previous entry hash. On every append the runner
reloads and validates both files, appends with `O_APPEND`, fsyncs the file and
containing directory, then reloads the combined evidence again. Torn,
non-canonical, reordered, duplicated, hash-invalid, symlinked, or concurrently
changed evidence fails closed.

A successful index entry contains the exact PR #101 lineage fields: request
date, slot, capture identifier, raw SHA-256, raw size, manifest SHA-256, and UTC
observation time. Failed attempts are never erased by later success.

## Crash/restart attempt accounting

Before **every** network request the live executor writes and durably fsyncs
`inflight-attempt.json`. The canonical marker binds:

- runner identity;
- current append-only evidence sequence and previous entry SHA-256;
- request date;
- slot;
- attempt number;
- UTC attempt-start time;
- its own SHA-256.

The request is not allowed to start until that marker has been written,
directory-synced, reread, and revalidated.

After a normal success or failure, the corresponding append-only outcome entry
is committed first. Only after the outcome rereads successfully is the in-flight
marker removed and the directory synced.

This ordering closes the crash window that would otherwise allow an unaccounted
request or durable raw capture to be silently repeated after restart:

- if the process dies before an outcome is journaled, the in-flight marker
  remains and **automatic retry is forbidden**;
- if a durable capture exists but the append-only outcome is absent, the runner
  reports `UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION` and performs no
  new request;
- if the process dies after the append-only outcome is durable but before marker
  deletion, the next locked execution verifies that the marker exactly matches
  that one recorded outcome and safely removes the stale marker without
  repeating the completed attempt;
- marker/evidence disagreement fails closed as `INFLIGHT_ATTEMPT_STATE_CONFLICT`.

An unresolved in-flight attempt is intentionally **not guessed into success or
failure**. Its capture/network state must be explicitly reconciled in a later
reviewed evidence action before the campaign can continue.

The live executor also uses a fixed `runner.lock`. An existing lock blocks
concurrent execution. A lock left by an interrupted process must be manually
inspected before removal; the runner will not guess that a lock is stale.

## Resume and timing behavior

Resume state is derived only from revalidated append-only evidence plus the
validated in-flight marker. A slot that already succeeded is never requested
again. Failed attempts resume at the exact next attempt number and retain the
frozen retry delay across process restarts.

Before each request the runner enforces the maximum of:

1. the frozen `1.0s` inter-request spacing;
2. any outstanding `60s` or `300s` retry delay;
3. any wait required to reach the same-date `300s` A/B minimum.

If slot B has already exceeded the `86400s` upper bound before a request, the
runner appends an explicit terminal blocker and performs no network request. If
a durable capture is observed beyond the upper bound, that acquisition attempt
is retained as failure evidence with its capture/manifest lineage and the slot
is blocked. No out-of-window capture is promoted into the campaign index.

## Explicit live execution

Status inspection is network-free:

```text
python scripts/run_fotmob_ordinary_ft_source_history_acquisition.py --status
```

Live execution requires the explicit flag:

```text
python scripts/run_fotmob_ordinary_ft_source_history_acquisition.py --execute-live-network
```

A run may be intentionally chunked and resumed without weakening completeness:

```text
python scripts/run_fotmob_ordinary_ft_source_history_acquisition.py \
  --execute-live-network --max-successful-slots 100
```

A partial campaign remains partial. Nothing in the runner marks historical
coverage complete.

## Safety boundary

At this implementation boundary:

- campaign execution is **not** claimed;
- `historical_coverage` remains `UNKNOWN`;
- source-history completeness is not proven;
- no history rows are materialized;
- no penalty, regulation-time, extra-time, or settlement semantics are added;
- model/probability/pricing/selection/production/BET authority remains false.

The next reviewed boundary is:

`EXECUTE_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_CAMPAIGN`
