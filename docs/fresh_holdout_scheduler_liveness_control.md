# Fresh-holdout scheduler liveness control

This control exists only to repair GitHub Actions scheduler registration for the reviewed FotMob UTC-native xG fresh-holdout collection workflow.

It does **not** execute the collection job, call FotMob, choose or fabricate a nominal slot, reconstruct a missed observation, backfill/retrofill any holdout evidence, change count-only close semantics, confirm the model, or grant production/pricing/selection/BET authority.

The reviewed collection lattice remains exactly `:07` and `:37` UTC. The liveness watchdog runs independently at `:03` and `:33` UTC and considers the primary scheduler stale only when there is no non-completed scheduled run and the newest scheduled delivery is more than 90 minutes old. A disabled primary workflow is re-enabled. An active-but-stale workflow is disabled and immediately re-enabled solely to re-register its GitHub schedule.

The watchdog pins the reviewed primary collection workflow blob before any mutation. If that workflow changes, if GitHub metadata drifts, or if a collection run is already active, the control fails closed or performs no mutation.

Any control-plane repair is recorded on issue #172 with explicit `false` authority/backfill/acquisition markers. Resumption is left to future natural `:07`/`:37` schedule events and the existing fail-closed schedule-recovery logic. Missed slots remain missing; they are never replayed.
