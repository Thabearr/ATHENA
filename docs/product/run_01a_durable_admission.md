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

A committed run is never revoked by launch failure. Owned launch failures are
best-effort fenced to `INTERRUPTED`; a commit-to-launch crash gap remains
nonterminal and observable, with no automatic redispatch. Worker completion,
monitoring, retry, and authenticated installed producer provenance remain open.

Run snapshots, events, history and cooperative cancel intent are provider-free
durable projections. Cancel intent does not control a process. Existing D5
fixture/export ports and all historical receipts remain unchanged.

Evidence: `artifacts/product/run_01a_durable_admission_v1.json`, append-only
A2 V116 plus its append-only V117 integration-guard successor, and focused offline tests. Hosted exact-head Tests and
automatic PORT-02C results (if triggered) are separate required review gates.
Source review counter remains 0/5 until owner-authorized merge.
