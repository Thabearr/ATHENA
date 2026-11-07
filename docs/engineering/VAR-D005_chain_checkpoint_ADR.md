# VAR-D005 — A2 inventory chain verification cost (ADR, PROPOSED)

Status: PROPOSED — design only. No code, no deletion, no change to V1..V347.
Decision owner: repository owner. This document only records options.
Opened by: VAR-01b (owner decision Q4, 2026-11-07).

## 1. Problem

Every A2 consumer authenticates the source-inventory chain by loading **all**
generations: strict discovery, exact canonical bytes, self-hash, V1 identity
and predecessor binding for every link. On main the chain is V1..V347:
347 files, 369 MB of canonical JSON. One full load costs about 1.8 s locally
(2.6 s of `json.loads` alone) and more on hosted runners.

Measured on main 016ae05b (VAR-01, local, Python 3.12, unprivileged, full history):

| Entry point | wall | full chain loads | generation reads |
|---|---|---|---|
| pytest session start (conftest) | ~52 s | 6 | 2,082 |
| one `completion_v9.audit()` | 655 s | 284 | 98,678 |

Chain loads are 79% of a V9 audit. Cost grows on two axes at once:

* **length**: every admitted change appends a ~1 MB generation, so every load
  gets longer;
* **fan-out**: every successor auditor re-authenticates its predecessors, and
  each of those loads the full chain again.

The product is roughly quadratic. Required hosted shards ran 5 h+ or were
cancelled at 6 h (run 40789392212), and the worst single nodes ran 4–5 h.

VAR-01b reduces the constant factor, not the growth:

* **F1** (call-scope hoisting in the B4 auditor): fewer loads per audit call.
* **Part D** (per-process shared chain): after the first authentication in a
  pytest process, later loads re-read and re-hash every generation (about
  0.6 s for 369 MB) but no longer decode. Re-reading and re-hashing still
  grows linearly with every generation and is still multiplied by fan-out.

Measured effect is recorded in the VAR-01b handoff.

## 2. Invariants every option must keep (v1.3)

1. Nothing is deleted, archived, collapsed or regenerated; V1..Vn stay byte-identical.
2. Every generation is still fully verified on every CI run of the exact head.
3. Required check names unchanged: `syntax`, `test shard 1 of 8` … `test shard 8 of 8`, `test`.
4. No persisted PASS cache, no cross-run or cross-process verdict, no artifact asserting upstream success.
5. A tampered old generation must fail the run.

## 3. Options

### Option 1 — one history-proof job per run; consumers verify the head link

A new job (for example `a2 history proof`) runs once per CI run on the exact
head. It fully verifies V1..Vn with today's loader and the V1 historical
rebuild. The eight `test shard N of 8` jobs declare `needs:` on it and run
only if its **job conclusion** is `success`. No artifact or verdict file is
consumed. In-test consumers then authenticate only:

* the latest generation's exact canonical bytes and self-hash; and
* its predecessor binding to V(n-1)'s exact bytes and canonical hash;

plus a cheap structural census (every file present, names contiguous, bytes
hashed) that fails closed if the directory differs.

Integrity analysis:

* A tampered old generation Vk (k < n-1) fails the history-proof job, so every
  shard is skipped and the aggregate `test` fails. Inside a shard, the census
  still sees changed bytes; whether a shard should also hard-fail on census
  drift is a sub-decision. Recommended: yes, by comparing the census to the
  exact byte hashes recorded in Vn's own chain of predecessor hashes.
* Risk: required-check semantics change. `test shard N` is now conditional on
  another job. The aggregate `test` job runs `if: always()` and requires
  `needs.test_shard.result` to equal `success`, so skipped shards fail it.
  The individual `test shard N of 8` contexts would report as skipped, and
  the owner must confirm the ruleset treats a skipped required context as
  not passing.
  The ruleset needs no edit, but the owner must accept the new job as part of
  the trust path.
* Shard cost: chain authentication becomes O(1) in chain length.

### Option 2 — epoch roots on top of option 1

Seal V1..Vk into an epoch root: an additive, signed document listing each
frozen generation's exact sha256. Option 1's job still fully verifies V1..Vn
every run *and* re-verifies the epoch root against them. In-test consumers
check Vn → V(n-1) → … only back to the epoch boundary.

Integrity analysis: same as option 1 for tamper detection (the full proof job
still verifies everything). It adds a new signed artifact class and key
management. It is only worth it if consumers genuinely need deeper-than-one-link
proofs.

### Option 3 — status quo plus VAR-01b Part D only

Keep every consumer's full-chain authentication. Rely on the per-process share
(no decode after the first load) and on F1.

Integrity analysis: unchanged from main. Every load still re-hashes all bytes;
mutation of the shared value fails the session.

Cost: re-hash cost still grows with every generation and with fan-out, so CI
time keeps rising. This defers the problem rather than solving it.

## 4. What a tampered old generation does

| Option | Tampered V100 bytes | Result |
|---|---|---|
| Main today | every load fails | run fails (but may hit the 6 h cancellation first) |
| 1 | history-proof job fails → shards skipped → `test` fails | run fails within minutes |
| 2 | history-proof job fails (chain + epoch root) | run fails within minutes |
| 3 | every hit's byte re-hash differs → real loader runs → fails | run fails |

## 5. Recommendation

Option 1, after VAR-01b merges and its hosted numbers are known. Option 2 only
if a concrete consumer needs multi-link proofs. Option 3 is acceptable only
as an interim state.

## 6. Rollback

Option 1 is additive: one new job, one new `needs:` edge, and a head-link
consumer helper. The helper must never read workflow context or environment
to decide how much to verify; that would be a forbidden workflow-context
bypass. The full proof is guaranteed only by the `needs:` edge. A local
pytest run therefore gets head-link verification only, unless the developer
also runs the history-proof command. This is the main integrity cost of
option 1 and needs explicit owner acceptance. Rollback removes the `needs:`
edge and the helper call sites (one tests.yml successor plus one A2
generation); every consumer falls back to today's full-chain loader, which
stays in the code throughout. Part D's kill switch
(`ATHENA_DISABLE_CHAIN_SHARE=1`) restores main's loader behaviour in tests
without a code change.
