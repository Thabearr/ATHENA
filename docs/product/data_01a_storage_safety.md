# DATA-01A storage safety (D3 only)

The app owns only `WritableRoots.data_root/athena-app.sqlite3` and exactly the
nine control-core tables. No operational/history database is migrated or adopted.
Installed mode inventories only this app locator. An exact verified development
checkout also inventories `database/athena.db` (legacy operational) and
`database/athena_history.db` (historical warehouse), without writing either.
There are currently no source-controlled generated research database locators.
Unknown locations remain unknown; there is no recursive home-directory scan.

Every repository operation opens a verified connection on its executing thread,
enables foreign keys, checks the schema and migration identity, then closes the
connection in `finally`. Reads use read-only connections; writes own explicit
transactions. Closing waits for active operations and rejects further use.

Preview persistence uses one `BEGIN IMMEDIATE` transaction for the local
presentation profile, release verification, exact capability snapshot and preview.
A failure between the inserts rolls back the whole bundle. The preview source
must equal the reverified runtime release, not merely a database provenance row.

Before opening/creating the migration target, a bounded ownership inventory is
published under `migration-evidence/inventories/<sha256>.json`. For an existing
SQLite database, SQLite's backup API produces a consistent, content-addressed
snapshot under `migration-evidence/backups/<sha256>.sqlite3`; live WAL files are
never naively copied. The canonical pre-state manifest is published as
`migration-evidence/<sha256>.json`. The migration ledger binds its exact bytes.
Temporary files are fsynced and atomically published without overwriting existing
evidence. Links/junctions are rejected. Failed migrations retain recovery material.
An absent database records absence and has no fabricated SQLite backup.

## Owner-directed rollback

Stop the app completely before recovery. Verify the manifest digest recorded by
the migration ledger and, for an existing pre-state, the snapshot's byte digest
and byte count. Preserve the current database and evidence for diagnosis. Restore
the verified SQLite snapshot to the app locator with no live application or stale
WAL/SHM files. For an absent pre-state, restoring absence means removing only the
new app database and its sidecars after preserving them. This is not an automatic
rollback command or a D5 backup product; no restore/deletion is performed here.

Artifact locators are canonical relative POSIX paths, never user filesystem paths.
Preferences allow only `theme`, `display_timezone`, and `page_size`; they never
grant provider, delivery, wager, worker, or run authority. Durable run admission
remains unavailable and D4/D5 tables are absent.
