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

Fenced writes authenticate terminal evidence and current source for a matching
current lease before the finished-attempt fence. This preserves the specific
fail-closed diagnosis while a completed attempt still cannot mutate state;
stale and cross-run leases fail at the fence without that preflight.

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
A2 V116–V138 remain immutable; RUN-01B appends V139 from exact V138
`69243068a5d1106f896dde94f2f771961df4ac71630281eed199ac708c10fb88` with
`predecessor_rewritten=false`.

The canonical source/evidence receipt is
`artifacts/product/run_01b_worker_lifecycle_v1.json`; the non-writing audit is
`python -m scripts.audit_run_01b_worker_lifecycle`. Final exact-head Tests and
the naturally triggered Windows/Linux PORT-02C results are recorded in the
PR body after the last push. Source-review counter while PR #458 is unmerged:
`2/5`. **DO NOT MERGE.**

## Review correction after a7d420db

The legacy adapter first validates the original typed Current Shadow receipt.
RUN-01B requires the exact reviewed legacy authority vocabulary and compares
authority_profile, mode, provider_acquisition, share_code_generation, login,
cookies, wallet, staking, and wager against the admitted manifest. It retains
all legacy authority evidence and both manifest digests, then binds the final
canonical RunReceipt to the exact admitted authority. Request, source, run,
release, producer, and attempt remain bound; this path permits no delivery.

Command construction and staging failures use generic fenced interruption.
Only an exception from the actual launch call emits WORKER_LAUNCH_FAILED and
RUN_INTERRUPTED atomically. Neither path retries or launches on replay.

A verified terminal receipt supplies its exact Portfolio digest to a durable
WORKER_PROGRESS_PROVEN observation before terminal projection. The stage and
time come from an actual typed checkpoint, counts from validated receipt
evidence, and dedupe identity from the canonical final receipt. Portfolio
outcomes require a typed COMPLETE checkpoint; absent Portfolio stays None.

Terminal reads reauthenticate retained receipt bytes and project only the
exact selected_leg_count, shortfall, and receipt status. Execution and delivery
state stay unavailable because this correction adds no new projection
vocabulary. No raw share code or arbitrary evidence is exposed.

The correction appends V140 from immutable V139
5a633d61e8c3248db0cec33eecd4ee36809ff3fde87ecd9c1236dd7eb9a8a071.
V116–V139 remain unchanged. The focused synthetic regressions cover terminal
success, authority and Portfolio tamper, launch semantics, dedupe, monotonic
progress, authenticated snapshots, and read tamper. Local pytest is unavailable;
syntax and deterministic auditors run locally and fresh natural hosted Tests
and PORT-02C qualify the final pushed head. Exact final head and hosted gate
IDs are recorded in the PR body after the final push, preserving this source
evidence from a self-referential commit identity. SOURCE_REVIEW_COUNTER remains
2/5; restricted actions remain zero; E3/E4 remain unstarted. DO NOT MERGE.

The final regression correction preserves V140 byte-for-byte and appends V141
from V140 canonical SHA
29441c58c84171e2f5797b6104ed0cc629aed7367f05cd61ec0e6156a155f1db.
A test-only serialization correction uses RunReceipt.to_dict() to thaw retained
evidence. Seventeen focused synthetic cases passed by direct execution of the
existing test functions with a stdlib harness and transport guard. This was not
a pytest session, and no dependencies were installed. The cases covered both
terminal outcomes, nine authority/Portfolio mutations, progress regression,
snapshot tamper and cross-request rejection, staging versus launch failures,
and the existing E1 diagnostic-transaction failure regression. Current A2/E1/E2
auditors, syntax, and diff checks qualify source evidence locally; fresh natural
hosted Tests plus Windows/Linux PORT-02C remain the final qualification.
