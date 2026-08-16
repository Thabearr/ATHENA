# PR69 Primary Time-Basis Evidence Acquisition Runner

## Status

**Implemented only. No primary network acquisition is executed by this PR.**

Runner ID: `REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER_V1`

Repository implementation anchor: `e094c53d9c881dc9d7a35c24ac85f733b7abe36e` (PR #124 merged `main`).

The runner pins and revalidates the exact PR #124 acquisition protocol:

- protocol blob: `df1a25227b8fee5fbbb21dce7f5f8be5d2464954`
- canonical SHA-256: `28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3`
- canonical size: `9,039` bytes

## Boundary

This implementation exists only to execute the already-reviewed acquisition contract deterministically and preserve the resulting raw primary evidence. It does not interpret a captured statement, infer a timezone, backdate current documentation, resolve PR69 source-local semantics, compare FotMob time, authorize PR80 input, train a model, produce probabilities, price a market, select a bet, approve production, or authorize BET.

Importing the runner is network-inert. The CLI requires an explicit mode: `--status` performs no network access, while `--execute-reviewed-protocol` authorizes only the frozen campaign. Programmatic live execution requires the exact boolean `execute_live_network=True`.

The supported live-execution entry points bind the reviewed `fetch_primary_evidence` transport, the runner's real UTC wall clock, and `time.sleep` directly. They do not accept a caller-supplied fetcher, and they reject caller-supplied clock or sleeper substitutions. Synthetic transport and timing are confined to the private orchestration seam used by tests against temporary repositories, so synthetic bytes cannot enter the supported trusted acquisition path while masquerading as primary evidence.

## Frozen campaign

The plan is exactly eight successful capture slots in this order:

1. `/notes.txt` slot A
2. `/data.php` slot A
3. `/downloadm.php` slot A
4. `/matches.php` slot A
5. `/notes.txt` slot B
6. `/data.php` slot B
7. `/downloadm.php` slot B
8. `/matches.php` slot B

The runner does not expose a source-set override. The capture root remains exactly:

`.cache/athena-research/pr69-primary-time-basis-evidence`

Each target/slot owns one immutable directory containing exactly `response.bin` and `manifest.json`. Existing indexed evidence is reverified rather than overwritten. Before network access, the runner scans the entire frozen capture tree rather than only the next slot. A partial, future-slot, complete-but-unindexed, unexpected-file, unexpected-directory, post-completion orphan, or otherwise inconsistent capture blocks; it is never silently promoted or deleted. Raw evidence remains outside Git.

## Transparent HTTP transport

The transport is a direct verified HTTPS GET to `www.football-data.co.uk:443`. It sends only the PR #124 headers:

- `Accept: text/plain,text/html;q=0.9,*/*;q=0.1`
- `Accept-Encoding: identity`
- `User-Agent: ATHENA/1.0`

It does not follow redirects, use cookies, reproduce a browser client, use proxies, or attempt anti-bot evasion. TLS verification uses the platform/default verified SSL context. A non-200 status, redirect response, wrong content type, compressed response, invalid/oversized Content-Length, empty body, body over 2 MiB, timeout, TLS error, malformed response, or persistence failure fails closed.

The exact HTTP body bytes are hashed and durably written before any later semantic use. No decoding or line-ending/charset normalization occurs on the raw evidence path.

## Manifest and provenance

Every successful manifest binds:

- runner and PR #124 protocol identity;
- target ID and A/B slot;
- attempt number;
- requested and final URL;
- exact reviewed request headers;
- empty redirect chain;
- UTC request-start, response-completion, and observation timestamps;
- HTTP status and TLS-verification state;
- reviewed response-header subset;
- `response.bin` filename;
- exact raw SHA-256 and byte size.

The campaign index and failure journal are separate canonical JSONL files but form one global sequence and SHA-256 hash chain. On every resume, the two files are merged by sequence and fully revalidated for exact pass order, contiguous attempts, terminal blockers, timestamps, and hash ancestry. Every indexed success is then re-read from disk and rehashed against its manifest.

Known request failures are durably appended to `failure-journal.jsonl`; retries use the frozen 60-second and 300-second delays measured from the durable failed-attempt record, so a process restart cannot shorten the retry delay. Three failed attempts for one slot are terminal.

## Inflight request safety

Before any HTTP call, the runner durably writes a self-hashed `inflight-attempt.json` marker that binds the exact pending evidence sequence/hash, target, slot, attempt, and intent timestamp.

The marker is cleared only after the request outcome is durably committed to the append-only campaign evidence. On restart:

- if the matching success/failure outcome is already durably recorded, the stale marker may be safely cleared;
- if the marker still matches a pending campaign state, the runner returns `UNRESOLVED_INFLIGHT_ATTEMPT_REQUIRES_RECONCILIATION` and performs **no automatic retry**;
- if marker and journal disagree, execution blocks as an evidence-state conflict.

A complete raw response/manifest directory is not itself permission to invent a successful journal event. A complete-but-unindexed capture without a matching durable outcome blocks for explicit review. This prevents a crash after the network call from silently causing either a duplicate request or an inferred success.

## Timing

The runner preserves the frozen pass order, requires at least one second between request starts, and uses the successful slot-A observation timestamp as the pair anchor. Before slot B, it waits until at least 300 seconds have elapsed and records a durable `SLOT_BLOCKED` event if the 3,600-second upper bound has already expired. A response whose final observation falls outside the same 300–3,600 second window is not promoted to a successful capture.

Before any new request intent is created, current UTC time must be at or after every relevant durable campaign timestamp already recorded: request starts, durable record times, and successful observation times. Clock rollback therefore fails closed even between different target-A captures, not only during same-target A/B timing. The supported live API also rejects custom clocks and sleepers, preventing a caller from manufacturing the frozen timing windows.

After the inflight marker is durably persisted, the runner samples request-start time and revalidates the entire timing gate again immediately before transport. The request-start time may not precede the durable intent timestamp, prior durable campaign evidence must still be temporally valid, and the inter-request/retry/pair window must still permit the request. If the clock rolls backward or the pair window expires while the inflight marker is being persisted, the marker is cleared without issuing a request; an expired pair window is then durably blocked.

## Durability and no-overwrite behavior

The repository/campaign path is constrained beneath the exact capture root. Symlink path components are rejected. Journal, lock, inflight, raw-response and manifest files must be ordinary single-link files where they already exist; append/create operations use no-follow behavior where the platform provides it. New directory entries and evidence files are durably synchronized. Evidence files use exclusive creation. A runner lock prevents concurrent execution.

If persistence becomes indeterminate after a request may have started, the inflight marker deliberately remains. The runner does not manufacture a failure event, remove partial evidence, or issue a replacement request. Preventing an unaccounted duplicate request is more important than automatic recovery.

## Execution output

After a separately reviewed execution, `--status` can report completed slots, blocker/inflight state, the next exact slot/attempt, and an A/B pair table containing separation and raw-hash equality. That output remains acquisition evidence only. Semantic extraction, historical effective-scope qualification, conflict resolution, and PR69 time-basis resolution are later reviewed boundaries.

## Safety

The implementation keeps all downstream authority false:

- semantic extraction: false
- historical effective-scope qualification: false
- PR69 source-local time-basis resolution: false
- PR80 constructor input: false
- model training: false
- probability inference: false
- pricing: false
- selection: false
- production approval: false
- BET: false

## Next boundary

`EXECUTE_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_CAMPAIGN`

Execution must use the exact reviewed PR #125 head after hosted synthetic-merge CI passes. Captured bytes still cannot resolve PR69 by themselves; a later qualification boundary must inspect exact primary statements and byte/line locations, pair drift, conflicts, and historical effective scope.
