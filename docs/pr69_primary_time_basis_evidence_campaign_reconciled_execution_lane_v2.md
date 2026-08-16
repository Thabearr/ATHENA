# PR69 Primary Time-Basis Evidence Campaign Reconciled Execution Lane V2

## Status

**Control plane only. This boundary does not execute the live campaign.**

This boundary installs a second, independently one-shot hosted execution lane after the first reviewed campaign attempt failed closed and its evidence was preserved. It is a reconciliation successor to PR #128 and PR #129; it is not a replay of the old workflow.

## Why a new lane is required

The first one-shot execution from PR #128 produced run `31953949073` on main `0efe56f5003441b52e4ec3ba2723eb0d78a80422`. Its durable result was:

`EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY`

The preserved artifact is:

- artifact ID: `9266604353`
- artifact name: `pr69-primary-time-basis-evidence-campaign-31953949073`
- digest: `sha256:ce87f13cb72a917c0a01e4bbede87e4123d85861d5ee1cd98667bb802d380db7`
- retention expiry: 2026-09-15

The artifact shows four successful slot-A captures followed by a fail-closed slot-B `NOTES_TXT` attempt. The first A observation was `2026-08-16T15:07:50.067408Z`; B1 request start was `2026-08-16T16:07:34.269316Z`, leaving only about 15.8 seconds before the frozen 3,600-second ceiling. The B1 response then arrived too late and was classified `PAIR_OBSERVATION_TOO_LATE`, followed by `PAIR_WINDOW_EXPIRED_AFTER_RESPONSE`.

The same artifact also shows roughly 12m43s of network-free delay between each successful A observation and the next request start. Hosted CI separately measured the deep PR124 ancestry reconstruction in the tens-of-seconds range per invocation. PR #129 therefore changed only verification execution cost: it introduced a bounded deep-verification session while retaining direct identity checks and forcing fresh deep revalidation immediately before reviewed network I/O and again before durable request outcome publication.

PR #129 merged at:

`94577458d4b8af59a4e986edb2e4df9c426e21be`

No PR124 schedule, transport, retry, response, provenance, evidence, semantic, model, pricing, selection, production, or BET rule was relaxed.

## Exact reconciled inputs

The V2 lane is based on merged main `94577458d4b8af59a4e986edb2e4df9c426e21be` and pins:

- runner contract: `domain/pr69_primary_time_basis_evidence_acquisition_runner.py`
  - Git blob `04c30b177c2338848a448972cc0cfad0328e602c`
- live executor: `scripts/run_pr69_primary_time_basis_evidence_acquisition.py`
  - Git blob `b44a010d0957ad8d76474aae2f090d52ae5b0e6e`
- PR #124 protocol: `domain/pr69_primary_time_basis_evidence_acquisition_protocol.py`
  - Git blob `df1a25227b8fee5fbbb21dce7f5f8be5d2464954`
  - canonical SHA-256 `28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3`
  - canonical size `9,039` bytes
- dependency manifest: `requirements.txt`
  - Git blob `54d24a55dfa4c73ba3910d333257cfd2e68daf4b`

The lane also requires PR #129 to remain merged with the exact merge SHA above and requires the exact failed V1 result receipt and preserved artifact from PR #128 to remain available before a V2 attempt marker can be created.

## Frozen campaign remains unchanged

The campaign is still exactly:

1. `/notes.txt` slot A
2. `/data.php` slot A
3. `/downloadm.php` slot A
4. `/matches.php` slot A
5. `/notes.txt` slot B
6. `/data.php` slot B
7. `/downloadm.php` slot B
8. `/matches.php` slot B

The frozen same-target pair window remains 300–3,600 seconds. Request identity, direct HTTPS transport, no redirects, no cookies, no browser impersonation, no proxy evasion, one-second minimum request-start spacing, at most three attempts per slot, 60/300-second retry delays, no overwrite, and the 2 MiB response bound all remain unchanged.

## V2 one-shot authorization

The V2 workflow is `issue_comment` only and is bound to control PR #130. After PR #130 itself is merged and closed, only repository owner `Thabearr` may authorize execution by posting exactly:

```text
/athena-run-pr69-time-basis-evidence-v2
main-sha: <exact then-current lowercase 40-hex main SHA>
confirm: EXECUTE_RECONCILED_8_PRIMARY_TIME_BASIS_CAPTURES_V2
```

Before checkout or network access, the guard requires:

- PR #130 is merged and closed;
- PR #129 is merged at exact merge SHA `94577458d4b8af59a4e986edb2e4df9c426e21be`;
- the supplied SHA equals the current default-branch HEAD;
- PR #128 contains the exact failed V1 result receipt for run `31953949073`;
- that receipt names artifact ID `9266604353` and the exact preserved digest;
- the exact artifact still exists, is unexpired, and has the expected name;
- no prior V2 attempt marker exists on PR #130.

Only after those checks pass does the workflow write the durable V2 attempt marker. Any V2 marker forbids another V2 attempt and requires another reviewed reconciliation boundary.

## Exact checkout and live command

The lane checks out only the explicitly authorized current `main`, disables persisted Git credentials, verifies PR #129 is in its ancestry, and verifies all four exact Git blob pins.

A network-free empty-state preflight must still prove zero completed slots and no blocked/inflight state. The only live command remains:

```text
python scripts/run_pr69_primary_time_basis_evidence_acquisition.py --execute-reviewed-protocol
```

No alternate repository root, fetcher, clock, sleeper, target order, source identity, or maximum-successful-slot override is passed.

## Evidence preservation and final gate

The live command's exit code is captured rather than immediately aborting the job. Network-free post-status, packaging, non-semantic state assessment, and artifact upload are attempted after any controlled execution-stage failure.

The V2 artifact name is:

`pr69-primary-time-basis-evidence-campaign-v2-<run-id>`

with 30-day retention.

V2 succeeds only if campaign exit, post-status, packaging, assessment, and artifact upload all succeed; status proves exactly 8/8 successful slots; all four pair separations are within 300–3,600 seconds; no blocked/inflight state remains; all eight successful journal entries exist; and every semantic/downstream authority flag remains false.

The success state is:

`PRIMARY_EVIDENCE_CAMPAIGN_V2_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION`

Any other result is:

`EXECUTION_V2_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_FURTHER_RETRY`

and automatic replay remains forbidden.

## Safety boundary

A successful acquisition still does not infer the football-data.co.uk CSV timezone, establish historical effective scope, equate it with FotMob semantics, authorize PR80 constructor input, train or activate models, infer probabilities, price/select markets, approve production, or authorize BET.

## Sequence

1. review and merge PR #130;
2. verify the exact new `main` SHA and immutable V2 workflow inputs;
3. receive a separate explicit V2 live-execution authorization using that SHA;
4. execute the one-shot V2 campaign once;
5. preserve and inspect the V2 artifact;
6. only if the campaign is complete, create a separate semantic/effective-scope qualification boundary.
