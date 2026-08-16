# PR69 Primary Time-Basis Evidence Campaign Execution Lane

## Status

**Control plane only. This PR does not execute the live campaign.**

This boundary installs the one-shot hosted execution lane for the already-reviewed PR #124 acquisition protocol and merged PR #125 runner. The execution lane may become usable only after this control PR is itself merged and closed, and only after a separate exact owner command names the then-current `main` SHA.

## Exact reviewed inputs

The lane pins the following immutable inputs from merged `main` `93ccc858c112ba73162db85efe96002d6b9308b5`:

- runner contract: `domain/pr69_primary_time_basis_evidence_acquisition_runner.py`
  - Git blob `6a990059cdc86297bb58a328afd4cb1fcd2c35d1`
- live executor: `scripts/run_pr69_primary_time_basis_evidence_acquisition.py`
  - Git blob `4b9bfd0a1acc25ad3568d5087b94fa3bd3e98e97`
- PR #124 protocol: `domain/pr69_primary_time_basis_evidence_acquisition_protocol.py`
  - Git blob `df1a25227b8fee5fbbb21dce7f5f8be5d2464954`
  - canonical SHA-256 `28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3`
  - canonical size `9,039` bytes
- dependency manifest: `requirements.txt`
  - Git blob `54d24a55dfa4c73ba3910d333257cfd2e68daf4b`

The live execution lane does not edit or relax any of those inputs.

## Frozen campaign

The campaign remains exactly the PR #124/PR #125 eight-success plan:

1. `/notes.txt` slot A
2. `/data.php` slot A
3. `/downloadm.php` slot A
4. `/matches.php` slot A
5. `/notes.txt` slot B
6. `/data.php` slot B
7. `/downloadm.php` slot B
8. `/matches.php` slot B

The request is the direct verified HTTPS `GET` to `www.football-data.co.uk:443` with only:

- `Accept: text/plain,text/html;q=0.9,*/*;q=0.1`
- `Accept-Encoding: identity`
- `User-Agent: ATHENA/1.0`

The runner keeps the frozen 300–3,600 second same-target A/B window, one-second minimum request-start spacing, at most three attempts per slot, 60/300-second durable retry delays, no redirects, no cookies, no browser impersonation, no proxy evasion, no source-set override, no alternate trusted repository root, and a 2 MiB response bound.

## One-shot authorization

The workflow is `issue_comment` only. It is bound to control PR #128 and accepts only a comment by repository owner `Thabearr` with exactly three non-empty lines:

```text
/athena-run-pr69-time-basis-evidence
main-sha: <exact current lowercase 40-hex main SHA>
confirm: EXECUTE_8_PRIMARY_TIME_BASIS_CAPTURES
```

Before checkout or any network request, the guard verifies:

- the command is on PR #128;
- PR #128 is already merged and closed;
- the command author is `Thabearr`;
- the command framing and confirmation token are exact;
- the supplied SHA is the repository's current default-branch HEAD;
- no prior execution-attempt marker exists.

After those gates pass, the workflow writes a durable attempt marker to the closed PR conversation **before** checkout or network use. Any marker from an earlier attempt forbids automatic replay and requires reviewed reconciliation.

The workflow permissions are intentionally narrow: `contents: read`, `issues: write`, and `pull-requests: write`. The pull-request write permission exists only because the audit marker/result must be persisted on a merged/closed pull-request conversation. There is no Git contents write permission, branch mutation, merge permission, source-capability mutation, or model/BET authority.

## Exact checkout and preflight

The workflow checks out the exact authorized `main` SHA with persisted Git credentials disabled and full ancestry available. It then verifies the four pinned Git blobs before dependency installation or live execution.

A network-free `--status` preflight must prove a fresh empty hosted campaign state:

- `completed_slots = 0`;
- `total_slots = 8`;
- `complete = false`;
- `blocked = false`;
- `inflight_attempt = null`;
- exact next slot ordinal `1`;
- status performs no network acquisition;
- semantic extraction, historical effective-scope qualification, PR69 time-basis resolution, PR80, model, probability, pricing, selection, production and BET flags are all false.

Any preflight mismatch stops before the live command.

## Live execution

The only authorized live command is:

```text
python scripts/run_pr69_primary_time_basis_evidence_acquisition.py --execute-reviewed-protocol
```

The control lane does not pass `--max-successful-slots`, `--repository-root`, a custom transport, a custom clock, a custom sleeper, or any alternate request identity. The merged PR #125 live wrapper itself binds the reviewed HTTPS transport, actual ATHENA checkout, real UTC wall clock and `time.sleep`.

The runner writes its append-only evidence below:

`.cache/athena-research/pr69-primary-time-basis-evidence`

Raw response bytes and manifests remain ignored research evidence rather than tracked Git content.

## Failure and replay safety

The workflow deliberately separates campaign execution from evidence preservation. The live command's exit code is recorded rather than allowing an immediate job abort. A network-free post-run status, evidence package, state assessment and artifact upload are attempted even when the live command fails.

The runner's own inflight marker protects indeterminate request outcomes. The control workflow adds a higher-level one-shot marker protecting the hosted execution attempt. Therefore a failed, interrupted, blocked, cancelled or partially completed run is **not** automatically replayed on a fresh hosted runner. The preserved artifact must first be reviewed and the attempt reconciled.

The fail-closed result state is:

`EXECUTION_NOT_QUALIFIED_REVIEW_ARTIFACT_BEFORE_ANY_RETRY`

## Preserved evidence artifact

Every attempted campaign packages available evidence into an Actions artifact named:

`pr69-primary-time-basis-evidence-campaign-<run-id>`

with 30-day retention. The package includes, when available:

- network-free preflight status;
- exact execution metadata and immutable blob pins;
- live runner log;
- network-free post-run status and stderr;
- a tar archive of the exact PR69 primary-evidence capture root;
- archive SHA-256 and byte size;
- non-semantic campaign-state assessment.

Artifact upload uses `if: always()` so failure evidence is retained whenever the workflow reaches the controlled execution stage.

## Execution success gate

The workflow may report the acquisition campaign as executed and preserved only when all of the following hold:

- live runner exit code is zero;
- post-run `--status` exits zero;
- `completed_slots = total_slots = 8`;
- `complete = true` and `blocked = false`;
- no block reason, next slot, inflight marker or runner lock remains;
- `campaign-index.jsonl` contains exactly eight `SLOT_SUCCEEDED` entries;
- the pair table contains exactly four target pairs;
- every A/B separation is within 300–3,600 seconds;
- both raw SHA-256 fields exist for every pair;
- status still reports every semantic/model/downstream authority flag false;
- evidence packaging succeeds;
- Actions artifact upload succeeds and returns an artifact ID.

Only then may the control-plane result state be:

`PRIMARY_EVIDENCE_CAMPAIGN_EXECUTED_AND_PRESERVED_PENDING_SEMANTIC_QUALIFICATION`

This state means only that the reviewed acquisition completed and its evidence was preserved. It does **not** say what any captured page means.

## Safety boundary

Neither this control PR nor a successful later campaign execution may:

- infer a PR69 source-local timezone;
- treat a current football-data.co.uk statement as historically effective without qualification;
- equate football-data.co.uk time semantics with FotMob `Europe/Oslo` display semantics;
- authorize PR80 constructor input;
- train or activate a model;
- infer probabilities;
- price or select a market;
- approve production;
- authorize BET.

All of those remain false until later reviewed boundaries establish the required evidence.

## Sequence

1. review and merge this control-lane PR;
2. verify the exact new `main` SHA;
3. receive a **separate explicit live execution authorization** using that SHA;
4. post the exact one-shot owner command;
5. preserve and inspect the resulting Actions artifact;
6. create a separate reviewed semantic/effective-scope qualification receipt before any PR69 time-basis conclusion.
