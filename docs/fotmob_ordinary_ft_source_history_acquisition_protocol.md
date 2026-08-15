# Reviewed FotMob ordinary-FT source-history acquisition protocol

PR #101 pre-registers the exact acquisition campaign that must exist before
ATHENA attempts to prove historical completeness for the registered derived
source:

`fotmob_data_matches_reviewed_ordinary_ft_finished_score`

This PR is a **protocol only**. It performs no network request, implements no
campaign runner, materializes no history rows, changes no source capability,
and authorizes nothing downstream.

## Why this boundary exists

PR #98 registered a narrow source-reported ordinary full-time score capability.
PR #99 then bound the source to the existing source-history completeness
contract. PR #100 executed that contract and correctly stopped at:

`BLOCKED_HISTORICAL_COVERAGE_UNPROVEN`

with the initialization boundary and all-eleven-league mapping still unproven.

The next safe step is therefore not to start downloading dates ad hoc. The
request identity, time window, repetition schedule, source mapping candidates,
raw lineage, failure behavior, special-result handling, and chronology checks
must be frozen first.

## Frozen request identity

Every campaign slot must use the already reviewed transparent data-matches
capture boundary:

- method: `GET`
- scheme/host: `https://www.fotmob.com`
- port: `443`
- path: `/api/data/matches`
- `date`: canonical `YYYYMMDD`
- `timezone=UTC`
- `ccode3=NGA`
- exact reviewed capture request headers
- no redirects
- no cookies
- no browser impersonation
- no proxy evasion

The protocol pins the current probe contract, raw-capture contract, and
capture script Git blobs. A later runner must call that reviewed capture path
rather than introducing a second network implementation.

## Frozen initial qualification interval

The initial campaign covers every UTC request date from:

- start: `2020-08-01`
- end: `2026-08-14`
- inclusive dates: `2,205`

The start is a frozen candidate lower bound for proving equivalence to the
PR #69 replay initialization boundary. **The protocol does not claim that
equivalence is already proven.** That proof belongs to the later reviewed
corpus assessment.

The end is the last complete UTC source date before this protocol's creation
day. Future rolling extension is not silently authorized by this protocol.

## Repeated-capture schedule

Every required date has two independent successful capture slots:

- slot `A`
- slot `B`
- all `A` dates run in ascending order, then all `B` dates in ascending order
- `B` must be observed at least `300` seconds after `A` for the same date
- the pair must remain within `86,400` seconds
- minimum inter-request spacing: `1.0` second
- maximum attempts per slot: `3`
- retry delays: `60`, then `300` seconds
- failed attempts never count as successful slots

Therefore initial qualification requires exactly:

`2,205 dates × 2 successful slots = 4,410 successful captures`

A date with only one valid slot remains incomplete.

## Eleven pre-registered mapping candidates

These mappings define the exact candidate universe the campaign must prove
from captured FotMob league ID/name/country evidence. They are deliberately
marked `PRE_REGISTERED_DISCOVERY_ONLY_REQUIRES_CAPTURE_PROOF`; placing them in
the protocol does not itself qualify them.

| Model league | FotMob league ID | Expected FotMob name | Expected country |
|---|---:|---|---|
| B1 | 40 | First Division A | Belgium |
| D1 | 54 | Bundesliga | Germany |
| E0 | 47 | Premier League | England |
| F1 | 53 | Ligue 1 | France |
| G1 | 135 | Super League 1 | Greece |
| I1 | 55 | Serie A | Italy |
| N1 | 57 | Eredivisie | Netherlands |
| P1 | 61 | Liga Portugal | Portugal |
| SC0 | 64 | Premiership | Scotland |
| SP1 | 87 | LaLiga | Spain |
| T1 | 71 | Super Lig | Türkiye |

The mapping is a scope bridge only. A football-data.co.uk league code is not a
FotMob fixture/team identity, and FotMob team IDs remain source-scoped.

## Raw evidence and campaign lineage

Every successful slot must preserve:

1. exact raw response bytes;
2. the reviewed canonical capture manifest;
3. request date and slot label;
4. capture identifier;
5. raw SHA-256 and byte size;
6. manifest SHA-256;
7. exact UTC observation time.

The later campaign runner must also produce a canonical append-only campaign
index and failure journal under untracked research evidence. Raw captures and
campaign evidence must not be committed to Git merely to make the review
easier.

No-overwrite semantics are mandatory. A later successful retry never deletes
or rewrites evidence that an earlier attempt failed.

## Failure semantics

The campaign fails closed when any required date lacks both valid successful
slots.

HTTP errors, timeouts, invalid content type, oversized or empty bodies,
manifest verification failures, and durability failures must be recorded.
Retries are bounded by the frozen policy; failure evidence survives a later
success.

Missing dates may not be silently skipped. They may not be filled from
`fotmob_historical`, football-data.co.uk, football-data.org, or any other
provider. The derived history must be proven from the reviewed FotMob
data-matches source itself.

## Ordinary-FT and special-result semantics

Only results admitted by the reusable reviewed ordinary-FT finished-score
adapter may enter the derived history.

Every in-scope finished fixture that the adapter rejects must remain visible
with its exact blocking disposition. Penalties, extra time, awarded results,
or another non-ordinary finish may not be coerced into an ordinary full-time
score.

Postponed, cancelled, abandoned, and rearranged fixtures also require explicit
source-state disposition. They may not disappear merely because they do not
produce an ordinary score row.

An unresolved in-scope finished fixture outside the ordinary-FT gate blocks
historical completeness unless a later separate review qualifies its
semantics.

## Identity and chronology

The later corpus must prove, rather than assume:

- stable FotMob fixture teams, competition, and kickoff across captures;
- no duplicate fixture ID;
- no same-team/same-kickoff ambiguity;
- consistency between request-date timezone and fixture kickoff UTC, or an
  explicit disposition;
- source-scoped team-ID continuity across seasons without fuzzy name merging;
- no target fixture included in its own prior history;
- deterministic replay order of kickoff UTC then source fixture ID after
  chronology qualification.

Capture-pair drift is evidence. It must be reconciled or blocked before that
date can support history.

## What remains unproven

After this protocol, all of the following remain unproven:

- PR #69 initialization-boundary equivalence;
- all eleven FotMob league mappings;
- complete daily historical coverage;
- result-evidence completeness;
- resolution of every non-ordinary finished state;
- identity and chronology consistency;
- source-history adapter approval;
- historical coverage promotion.

`historical_coverage` therefore remains `UNKNOWN`.

## Safety

Every safety flag is exact `false`, including network-acquisition authority,
campaign-runner approval, source-history acquisition execution,
source-history completeness, constructor input authorization, successor
approval, expected-goals production authority, probability execution, pricing,
market activation, selection, production approval, and BET authority.

The protocol does not weaken ATHENA's core rule that unknown evidence remains
unknown and no downstream layer inherits authority merely because an upstream
capture plan exists. This preserves the project's evidence-first decision
architecture. The project's canonical context likewise treats live GitHub as
the engineering source of truth and requires narrow, fail-closed PRs.

## Next boundary

`IMPLEMENT_REVIEWED_FOTMOB_ORDINARY_FT_SOURCE_HISTORY_ACQUISITION_RUNNER`

That PR may implement the deterministic campaign orchestrator and evidence
journal defined here. It should still remain separate from the later network
execution/qualification boundary.
