# Historical training coverage and canonical market labels

PR #232 is ATHENA Expansion's post-match evidence audit boundary. The dated
roadmap called this deliverable #231, but the emergency infrastructure hotfix
consumed live #228; Tactical Identity is live #231 and Goal/Score Dynamics v2
therefore follows this work as #233.

## Why row count is not training richness

`database/athena_history.db` owns canonical football truth. Its existing
`PARTIAL`, `BASIC`, `STANDARD`, and `RICH` qualities remain unchanged:

- `BASIC`: regulation FT exists.
- `STANDARD`: FT plus HT or event evidence.
- `RICH`: FT, HT, referee, both coaches, and event evidence.
- `PARTIAL`: less than a complete regulation FT pair.

`RICH` does not imply xG, shots, lineups, complete goal chronology, 1UP/2UP
labels, Tactical Identity, or complete pre-match Fixture State. This layer adds
a separate capability vector and never redefines warehouse quality.

## Feature/label separation

Historical as-of features and Tactical Identity are pre-match namespaces. This
corpus uses target FT, HT, and qualified target events only for post-match
coverage and labels. It never writes target outcomes into either pre-match
corpus. A final lineup is named post-match lineup evidence, not pre-match lineup
availability; a stored target coach is not a confirmed pre-match manager.

## Source and identity

The warehouse is opened `mode=ro` and `query_only`, with exact file SHA-256,
schema/version pinning, repeated WAL/journal checks, and source-issued match
rows. Canonical rows cannot be directly constructed. The output records the
warehouse SHA, schema SQL SHA, registry and generation identities. Optional
Phase 2 and Phase 3 corpora are independently hashed, schema checked, and must
declare the same warehouse SHA before an exact `match_key` join is accepted.

Registry v1 is independently pinned to
`3eff35745371543bf6ff20c6c7e8550835382c04eba6583b8dbded932753e87b`.
The reviewed canonical-market fingerprint is
`b6a1de9415e27d9ed0e7394012435a60ca733187d41c951fd53d4a035ae84f11`.
Generation contract v1 is independently pinned to
`b60bbaaff1819d9eea09fae514d19c82af99878e7f9f799bb7efedbcc3149ee5`.
The fingerprint freezes market ID, family, settlement semantics, outcomes, and
line requirement. Same-version drift and unknown versions fail closed.

## Capability vector

Every target explicitly resolves `AVAILABLE`, `MISSING`, or `BLOCKED` for:

- regulation FT and HT;
- preferred events and complete regulation goal path;
- xG, shots, shots-on-target, possession, and card pairs/totals;
- home/away post-match lineup and coach evidence;
- referee evidence, advanced-stat source coverage, source provenance, and
  unresolved conflict state;
- optional historical-as-of and Tactical Identity target joins.

Absence remains missing. A relevant contested or malformed primitive is
blocked. Irrelevant conflicts remain local: a referee conflict cannot block a
score label.

On a mechanically identified extra-time/shootout match, aggregate xG, shots,
shots-on-target, possession, and card totals are blocked when present because
their source contracts do not universally prove regulation-only periods. The
normalized regulation FT/HT and schedule identity remain usable; no aggregate
is scaled, divided by 120, or otherwise repaired.

## Score and half labels

Safe regulation FT yields home/away goals, total goals, goal margin, 1X2,
BTTS, all Double Chance selection booleans, both Win-to-Nil labels, the three
current Result-or-Over-2.5 labels, and side-specific Draw No Bet settlement.
DNB is `WIN`, `PUSH`, or `LOSS`; a draw is never collapsed into a loss.

Safe FT+HT additionally yields both half scores, first/second-half result,
each side's first/second-half win, each Win Either Half label, and
`both_teams_won_a_half`. Negative FT-minus-HT arithmetic is blocked. Missing HT
stays missing.

## No historical line invention

The corpus stores `total_goals` and `goal_margin` as line-independent sufficient
statistics. They do not assert that any bookmaker offered a line. Pure kernels
accept an explicit quarter-goal line and return `WIN`, `HALF_WIN`, `PUSH`,
`HALF_LOSS`, or `LOSS`. No line or price is generated or copied into a target.

## Complete regulation goal path

Home/Away 1UP/2UP labels require
`COMPLETE_PREFERRED_REGULATION_GOAL_CHRONOLOGY_V1`:

1. safe canonical regulation FT;
2. `warehouse_events_preferred`, never raw cross-source aggregation;
3. reviewed regulation-period semantics;
4. supported scoring-team attribution, including reviewed own-goal inversion;
5. supported minute/stoppage/second chronology;
6. exact home and away reconciliation to FT;
7. ET and shootout exclusion;
8. no unresolved required score/event conflict.

V1 admits StatsBomb periods `1`/`2` and reviewed Fjelstul first/second-half
periods. StatsBomb `3`/`4`/`5` are excluded as ET/shootout. It does not use
generic `minute > 90`, event keys, source IDs, or lexical order as chronology.
Mixed-team goals at the same finest timestamp are blocked because their order
can change path settlement. Same-team ties are order-independent.

1UP Home/Away means the side ever reaches a one-goal lead. 2UP Home/Away means
the side reaches two goals ahead or wins at regulation FT. Draw remains ordinary
regulation draw and therefore needs only safe FT. These are overlapping early
payout events; they are not normalized and Home, Away, and Draw may all be true
for one completed path.

## Output and performance

The generated SQLite corpus contains:

- `corpus_meta`;
- `match_evidence_coverage` (canonical per-target payload/SHA);
- `evidence_capability_resolutions`;
- `market_label_resolutions`;
- `coverage_summary`.

The builder streams source-issued matches, uses bounded 500-match batches for
events and evidence relations, performs indexed set-based lookups, commits in
batches, derives summaries in SQL, writes an exclusive random temporary file,
and atomically replaces the requested output. It rejects source, operational
DB, optional-corpus, and SQLite companion collisions. Generated databases are
ignored by Git.

Summaries keep every target in the denominator and report whole-corpus, scope,
competition, season, data-quality, capability, market-family, and exact-label
status counts/rates. Unsupported targets are never silently discarded.

## Authority boundary

Reconstructible labels only mean that future research can evaluate that target.
They do not prove a model exists, a bookmaker offered a line, a market is
calibrated or active, or a bet is allowed. All acquisition, model, probability,
calibration, pricing, routing, selection, accumulator, production, and BET
authority flags are explicitly false. PR #232 performs no network acquisition.
