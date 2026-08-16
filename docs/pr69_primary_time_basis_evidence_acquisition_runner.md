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

Importing the runner is network-inert. CLI execution without `--execute-reviewed-protocol` prints the frozen runner descriptor and performs zero network requests. Programmatic live execution requires the exact boolean `execute_live_network=True`.

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

Each target/slot owns one immutable directory containing `response.bin` and `manifest.json`. Existing complete evidence is verified rather than overwritten; incomplete or inconsistent evidence blocks. Raw evidence remains outside Git.

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

The campaign index is canonical JSONL and hash-seals every successful slot. On resume, indexed captures are re-read and rehashed against their manifests. A complete durable next-slot capture that exists before its index publication can be reconciled without making a duplicate network request. A partial capture never triggers automatic deletion or replacement.

Failed request attempts are canonical durable evidence in `failure-journal.jsonl`; retries use the frozen 60-second and 300-second delays. Up to three attempts are allowed per slot.

## Timing

The runner preserves the frozen pass order, requires at least one second between request starts, and uses the successful slot-A observation timestamp as the pair anchor. Before slot B, it waits until at least 300 seconds have elapsed and refuses to start after the 3,600-second upper bound. A response whose final observation falls outside the same 300–3,600 second window is not promoted to a successful capture.

## Durability and no-overwrite behavior

The repository/campaign path is constrained beneath the exact capture root and symlink/non-directory path components are rejected. New directory entries and evidence files are durably synchronized. Evidence files use exclusive creation. A runner lock prevents concurrent execution.

If a persistence operation becomes indeterminate, the runner fails rather than deleting evidence and retrying the network call. This is intentional: preventing an unaccounted duplicate request is more important than automatic recovery.

## Execution output

After a separately reviewed execution, the campaign status can report completed slots, failed-attempt count, and the A/B pair-separation table. That output is acquisition evidence only. Semantic extraction, historical effective-scope qualification, conflict resolution, and PR69 time-basis resolution remain later reviewed boundaries.

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

Execution must use this exact reviewed runner head after hosted synthetic-merge CI passes. The captured bytes still cannot resolve PR69 by themselves; a later qualification boundary must inspect the primary statements, their exact byte/line locations, pair drift, conflicts, and historical effective scope.