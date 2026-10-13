# PR #460 historical Pass-A source projection

DRAFT / DO NOT MERGE. Base `7c787130e2662e34813a61422b865046fae52ebd`; reviewed starting head `f98900bc815d7a97f73f2f865cc5242115ba886a`.

The in-memory forensic comparison changed only `sources`, `static_discovery_edges`, and their canonical digest. Exactly the qualification adapter, settlement adapter, and tick source differ. Only qualification lexical edges moved or were added; imports, workflow guards, permissions and callers remain equal. The companion JSON records every original and starting current identity and edge difference.

Pass-A reads exact checked-in predecessor bytes for these three paths after latest A2 authentication of their current tracked HEAD versions. Each predecessor must match both the original Pass-A Git blob SHA1 and LF-normalized SHA256. Missing, cross-wired, symlinked, untracked or tampered files fail closed. The historical view is never imported by current runtime. A2 builds source/AST data without calling Pass-A; the dependency is acyclic. No historical ancestor fetch is necessary.

Checkpoint-E historical tree projections retain the exact same three predecessor identities plus the base-main test identity; additive fixtures and forward evidence are explicitly enumerated. Original tree/receipt digests are unchanged. Latest A2 authenticates all current source and tests independently.

The retained archive asset 636458042 has SHA256 `1c1cd0769ce58300e9f9d71dcedf34edfbe164fed41aea0c14d8707e4c977963`. Exact manifests are retained separately from the wrapper-only projection. The second original manifest proves observed_at `2026-10-13T08:55:14.551847Z`, correcting the forward V6 timestamp. No historical response bytes or other capture fields changed. V6 still admits only date 20261014, wrapper 9469 and exact A/B/C/E label pairs. No provider or model authority is added.

A2 V156 follows V155; V157 follows V156 after correcting the synthetic Git commit arguments to satisfy the existing offline test guard; V158 follows V157 after constructing the untracked-file test without a disallowed Git removal command; never rewrite a predecessor. Current-source authentication, frozen inventory equality, tamper cases and exact retained manifest provenance are exercised by `tests/native/test_fresh_holdout_pass_a_source_projection.py`. Existing wrapper positives and negatives remain required.

Old Tests run 38394682795 failed seven shards; old PORT-02C 38395093675 succeeded but was a workflow_dispatch by Thabearr. API metadata did not prove authorization; the owner explicitly confirmed in this session that it was authorized CI-only work. A final exact-head natural Tests and PORT-02C run, complete workflow inventory, and resolution of governance questions remain required. Never waive an unresolved failed check as unrelated.

Restricted actions in this correction: zero. RUN-02A/E4/E5 remain unstarted. Source-review counter remains 4/5 while unmerged; an authorized merge reaches 5/5 and requires immediate controlling-source reread. PR remains draft and unmerged.

Natural Tests 38406552315 cleared the original Pass-A comparison but shard 2 exposed the nested immutable base scan in `audit_checkpoint_e_workflows.py`. Its three original rows independently match the same frozen predecessor pins. The historical `read`, Git inventory and worktree scan now delegate to the same authenticated, exact three-path owner, with explicit root equality. V159 follows V158 for this correction and downstream tamper tests. No frozen base scan, receipt or source identity is rewritten. The old-head native success does not qualify the new V159 head; fresh natural qualification is required.
