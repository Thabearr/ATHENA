# Saturday 2026-08-22 fixture-universe capture

## Purpose

This boundary starts the live evidence phase for ATHENA's Saturday 2026-08-22 20-fold target. It captures one exact transparent FotMob `/api/data/matches` response for `20260822`, replays the existing PR38→PR40 source path, and produces a deterministic neutral inventory of every source fixture returned for that UTC date.

It does **not** select a bet. The output is the candidate universe that later reviewed fixture-intelligence, model, SportyBet reconciliation, fresh-price, value, selection, correlation and accumulator gates must consume.

## Frozen request

The request is fixed to:

- request date: `20260822`;
- timezone: `UTC`;
- ccode3: `NGA`;
- target fold size: `20`.

The runner reuses the existing transparent FotMob capture implementation and therefore performs exactly one bounded GET to the reviewed `/api/data/matches` route. It does not use the legacy advanced scraper, cookies, a session, browser impersonation, X-Mas headers, proxies or bypass logic.

## Exact source chain

The hosted lane executes:

```text
transparent PR38 dataMatches capture
→ PR39 structural assessment
→ PR40 UNREVIEWED fixture-candidate bundle
→ exact Saturday UTC-date check
→ literal competition-name intersection with the reviewed priority registry
→ canonical Saturday fixture-universe artifact
```

The source candidate bundle stays `UNREVIEWED`. This boundary does not mass-approve the fixtures or convert the capture into a reviewed fixture catalog.

## Priority inventory

The report compares `source_competition_name` to ATHENA's existing league-priority registry using the registry's exact normalized whole-name resolver. No fuzzy or substring inference is introduced. A literal competition that cannot be resolved remains unprioritized and visible in the report.

The report records, per source fixture:

- `FOTMOB:<source_match_id>` identity candidate;
- source competition IDs/name/country code;
- source home/away team IDs and names;
- exact UTC kickoff;
- PR40 review status;
- bootstrap league name/rank/tier when exactly resolved.

It also records total source fixture count, priority-registry match count, unprioritized count, per-league counts, and whether the raw source universe even contains at least 20 fixtures. That last field is only a source-coverage fact; it is never an accumulator authorization.

## Hosted execution

The draft PR is owner-triggered through an exact `pull_request: edited` control block so the live evidence can be captured and reviewed before merge. The workflow is bound to the exact PR number, same-repository branch, frozen base SHA, exact current PR head SHA and repository owner actor. Checkout credentials are disabled and the job has read-only repository/PR permissions.

The artifact is named:

`saturday-2026-08-22-fixture-universe-evidence`

and contains:

```text
capture-receipt.json
saturday-fixture-universe.json
fixture/response.json
fixture/manifest.json
fixture/schema-assessment.json
fixture/fixture-candidates.json
```

## Authority

Every downstream authority flag remains false:

- candidate review;
- fixture catalog admission;
- fixture intelligence;
- model features and probability;
- SportyBet reconciliation and canonical market mapping;
- fresh bookmaker price and pricing;
- selection;
- accumulator authorization;
- BET.

This is deliberate. The immediate next step after a successful real capture is to review the actual Saturday candidate universe and promote only the fixtures needed by the priority/exhaustion path. Fresh player context and exact SportyBet evidence must then be collected close enough to kickoff to satisfy their own freshness rules.
