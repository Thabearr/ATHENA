# E1 / RUN-01A durable admission

Review candidate only. **DO NOT MERGE.** E2/E3/E4 are not implemented.

The job service commits admission through the existing D1/D4 atomic port
before claiming an attempt, publishing request bytes, or launching a worker.
Exact replay (including after expiry or restart) returns the committed run
without staging or launching again. Conflicting key ownership and consumed
previews retain the existing typed conflict responses.

The only E1 operation is `OFFLINE_IDENTITY_PROBE`; it does not execute the
requested business operation. Current Shadow, provider, share-code, delivery,
and account/wager actions are not enabled. Installed desktop admission remains
fail-closed until a separately pinned installed worker integration is reviewed.

A committed run is never revoked by launch failure. One fenced repository
transaction appends `WORKER_LAUNCH_FAILED`, finishes the initial attempt, and
projects `INTERRUPTED` with one state-version increment and the same timestamp.
Diagnostic and interruption commit together or roll back together. Store failure
leaves RUNNING and the active attempt unchanged; no fallback recovery is called.
The payload contains only the static diagnostic ID, never exception text,
paths, argv or secrets.
The committed run identity is retained and launch is never retried.
A commit-to-launch crash gap remains nonterminal and observable, with no
automatic redispatch. Worker completion,
monitoring, retry, and authenticated installed producer provenance remain open.

Run snapshots, events and history are provider-free durable projections.
Cancellation remains deferred to E3: `cancel_intent` is `blocked_implementation`
and POST cancel returns HTTP 503 `CANCEL_STORE_UNAVAILABLE` without mutation.
The pre-existing D4 cancellation storage primitive is unchanged. Existing D5
fixture/export ports and all historical receipts remain unchanged.

Evidence: `artifacts/product/run_01a_durable_admission_v1.json`, append-only
A2 V116/V117/V118 plus append-only V119 from V118, and focused offline tests. Hosted exact-head Tests and
automatic PORT-02C results (if triggered) are separate required review gates.
Source review counter remains 0/5 until owner-authorized merge.
