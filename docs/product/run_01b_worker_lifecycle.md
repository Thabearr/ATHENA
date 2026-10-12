# RUN-01B owned worker lifecycle

RUN-01B implements the E2 lifecycle on the existing PR #458 branch, after
normal synchronization with the PR #457 merge at `ba5e868d2fb1e44d8939489559958d2fda5815d3`.
The branch began at `8b1af2d3fb14eb9915b31f4cd7d5c59c06820387`; the synchronization
merge is `9b9d8ada06324bcd6ea0b2bce990e2e01fe89e3a`.

`AthenaJobService` preserves commit-before-launch and exact replay without a
second launch. `WorkerCoordinator` claims the one local worker slot through the
SQLite transaction, launches through the reviewed `WorkerLauncher`, persists an
exact platform process-group locator, and owns heartbeats, typed progress,
receipt verification, and finalization. A capacity loser remains durably
queued; RUN-01B does not drain it automatically.

The native locator helper accepts only a positive exact integer PID and emits
only `WINDOWS_PROCESS_GROUP` or `POSIX_PROCESS_GROUP` with that PID. The
cross-platform schema and invalid-PID cases are covered by
`tests/native/test_run_01b_worker_coordinator_native.py`.

Progress comes only from canonical `current-shadow-all-market-stage.json` and
`current-shadow-all-market-progress.json` files. Events preserve the exact
source-summary, source, model/history, Router, and Portfolio digest references.
Repeated evidence is deduplicated by its canonical evidence SHA. Stage and
count movement is monotonic. A value stays unavailable until typed evidence
proves it.

`TERMINAL` requires `RunReceipt.from_json_bytes` verification bound to the
admitted request, authority manifest, source commit, release, and attempt. The
receipt is published before its terminal database projection. An explicit
projection repair consumes only that retained receipt and does not rerun the
worker. A child exit without a verified receipt becomes `INTERRUPTED` with the
last proven stage and no retry.

Cancellation remains E3-deferred and non-mutating (`503
CANCEL_STORE_UNAVAILABLE`). Installed Current Shadow execution remains blocked
because installed producer provenance is not authenticated. E3 and E4 remain
unstarted.

The immutable E1 receipt remains
`de2222e7f1c472d7a336f8a4c9c7bec84c2e6ed533b8f568689a3857adaf4f71`; the
immutable D5 receipt remains
`c9be3cc4c74fea16c9f97c0db3fe7b54d9e12373fc5787d46677f36276f7441d`.
PR #457's four-epoch successor runtime policy remains
`9dc0cfb362cf7008d28bcf029755b7361481b683e41155528f9607047773ceba`, and its
legacy two-epoch policy remains
`3cf597440422433e7c7e2246d33de4ece22e55395218f8bc2eb8950a361dd68a`.
A2 V116–V135 remain immutable; RUN-01B appends V136 with canonical SHA-256
`daa5e71f17e9aedadabd4919022620f7625d8bef7e6133f98b487e1d372e2c78` from exact
V135 `be33b12c9149c6c8b645adadbe5770484ac25814269a2fb93c78b2666d37f91e`.

The canonical source/evidence receipt is
`artifacts/product/run_01b_worker_lifecycle_v1.json`; the non-writing audit is
`python -m scripts.audit_run_01b_worker_lifecycle`. Final exact-head Tests and
the naturally triggered Windows/Linux PORT-02C results are recorded in the
PR body after the last push. Source-review counter while PR #458 is unmerged:
`2/5`. **DO NOT MERGE.**
