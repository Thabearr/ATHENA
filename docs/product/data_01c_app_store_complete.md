# DATA-01C app storage boundary

DATA-01C adds six SQLite tables through `database/migrations/0003_app_projections_exports.sql`. The app store therefore contains 20 tables at schema version 3. The frozen 0001 and 0002 migrations, their ledger identities, the D3/D4 receipts, legacy football and warehouse databases, and historical A2 generations remain separate immutable evidence.

The fixture, opportunity, and portfolio tables are structurally ready and intentionally empty. A D4 `RunReceipt` authenticates the terminal run and retained receipt bytes, but its `selected_legs` are generic mappings without reviewed fixture, market, odds, confidence, Router, or Portfolio semantics. `services/app_projection_service.py` therefore returns typed `SOURCE_CONTRACT_UNAVAILABLE` with bounded receipt lineage and writes no projection rows. An empty table does not mean a successful zero-selection rebuild. The source dependency `E2/VERIFIED_DECISION_PROJECTION_SOURCE_CONTRACT` remains OPEN; no F1/E5 consumer may present those rows as verified.

`services/export_service.py` creates local, opaque-ID archives under server-owned paths. The default bundle includes canonical run request and independently authenticated receipt content only after the redaction scan accepts it, plus exact digest references and an inclusion/exclusion inventory. A generic receipt selection is exported, if included, as opaque raw receipt content. It is not normalized into market selections. Exports do not upload, email, copy to a clipboard, or activate `api/v1/exports.py`. `app_audit_events` accepts only bounded canonical redacted metadata through its append API; SHA-256 is checked on reads and SQL triggers reject update/delete.

`services/backup_service.py` takes the shared cross-process app-root lock, inserts a PREPARING index row, snapshots SQLite with the online backup API, and hashes every referenced immutable artifact and retained migration-recovery object while the same lock excludes supported app writers. The archive manifest records the precise migration ledger, release provenance, database digest and size, run IDs, raw and canonical artifact hashes, inclusion/exclusion classes, and member totals. The archive is immutable and verified before the live index becomes VERIFIED. Its SQLite snapshot intentionally contains the backup's PREPARING row: that snapshot predates archive verification and must never claim the archive was verified within itself. Archives live in a stable sibling backup vault so a restore generation switch preserves earlier backup files and index history on that machine.

Restore accepts a local archive path as read-only input. It requires a store-only ZIP with a bounded member count and total/member sizes, canonical normalized paths, no duplicate casefold/Unicode paths, no links or special files, and a canonical complete manifest. It hashes member streams while writing only to a fresh sibling staging root. It then authenticates schema version and migration/resource hashes, SQLite integrity and foreign keys, exact run and artifact membership, D3 migration recovery manifests, artifact bytes, and D4 run/receipt provenance. Installed terminal producer provenance is still an E2 dependency: such archives may be staged with an explicit diagnostic, but activation is refused until that producer identity can be independently authenticated.

Activation requires an existing app root and the same-volume sibling staging generation. A stable sibling OS lock, flushed journal, durable same-volume directory renames, preserved old-root generation, post-switch integrity checks, and automatic journal recovery prevent mixed-root activation. If activation fails, recovery restores the preserved prior root and retains any failed new generation for inspection. The switch protocol never merges unknown files and never deletes the old root. Both native Windows and Linux PORT-02C runs qualify the migration resource and simulated journal crash points.

The production run-admission endpoint remains HTTP 503 (`DURABLE_RUN_STORE_UNAVAILABLE`). No providers, workers, Router, Portfolio, share-code generation, login, wallet, staking, wagering, delivery, or manual GitHub workflow actions are invoked by DATA-01C. `E2/PACKAGING_AUTHENTICATED_INSTALLED_PRODUCER_PROVENANCE` remains OPEN. The source review counter remains 2/5 until a separately owner-authorized merge.

The immutable D3 receipt and its original D4 source snapshot are unchanged. D5 adds one separately sealed historical byte record for the D3-era `database/app_repository.py`, whose source hash is present in both D3 and A2 V68 but outside D4's retained snapshot scope. The additive record binds to the D3 receipt, the retained source-tree commit, and the exact V68 source hash so historical audits need no ancestor-object lookup.

## Native restore qualification successor

The owner-approved PORT-02C source-forward successor adds only the four offline
native lock/crash-marker cases and their filesystem-observed uploaded receipt.
The historical ADD and pre-D5 workflow successor remain immutable predecessor
evidence. No new workflow transition, trigger, permission or runtime authority
is introduced. Windows/NTFS and Ubuntu 24.04/ext4 proof is required from the
natural PORT-02C run on the final PR head; source presence is not execution proof.
The uploaded platform receipts and run/job metadata are authenticated separately
by audit_data_01c_restore_portability to avoid a commit/SHA evidence cycle.
Natural PORT-02C run `38002210555` passed the D5 lock and three recovery phases on
Windows/NTFS and Ubuntu 24.04/ext4 at candidate head `ab355b9a27f8ea8e7521014ba7c0770000f60641`.
That candidate is no longer the final head after historical source-test fixes, so
the exact-final-head Tests and PORT-02C gates remain required before review-ready
status is claimed.
Projection source/coverage remains unavailable, both named E2 dependencies remain
OPEN, and production admission remains unavailable. No merge is authorized.
