# Reviewed FotMob ordinary-FT source-history campaign execution lane

This boundary installs the control plane needed to execute the already-reviewed PR #102 acquisition runner from GitHub Actions without weakening the frozen PR #101 campaign contract.

The pull request that adds this workflow **does not itself execute the campaign**. Live network execution becomes possible only after the control PR is merged to `main` and the repository owner posts the exact one-shot command on that merged control PR.

## Frozen execution target

The workflow is bound to the reviewed PR #102 implementation:

- domain runner blob: `533b339bcb2d6721dae55c699327b53eabbffb09`
- live runner blob: `6f067b8f069a760248a3b0b624c88d4f91aaa7ef`
- PR #101 protocol blob: `39541b351d2990f7ebb9572a8c9c674c85864284`
- reviewed capture script blob: `10b8858ab62f2708bd564d578a627c43718e5a12`
- reviewed capture contract blob: `ca2149395de868104666620173b55a880b10c729`
- request timezone: `UTC`
- `ccode3=NGA`
- required successful slots: `4410`
- historical interval: `2020-08-01` through `2026-08-14`

The execution workflow never substitutes a different transport, request identity, campaign schedule, retry policy, source, or result semantics.

## One-shot authorization

The workflow listens only to owner-authored issue comments and is bound to the merged control PR. The accepted command has exactly three non-empty lines:

```text
/athena-run-fotmob-history
main-sha: <exact current lowercase 40-hex main SHA>
confirm: EXECUTE_4410_LIVE_CAPTURES
```

Before checkout or network use, the workflow verifies that:

1. the command is on the exact control PR;
2. the control PR is already merged and closed;
3. the supplied SHA is the repository's current default-branch SHA;
4. no prior execution-attempt marker exists on the control PR.

Once those checks pass, the workflow writes a durable control-plane attempt marker comment **before** any campaign network request. Any later attempt marker blocks automatic replay. A failed, interrupted, cancelled, or partially completed run therefore requires explicit reviewed reconciliation rather than silently starting the campaign again from an empty hosted runner.

## Exact checkout and runtime pins

The job checks out the authorized `main` SHA with persisted Git credentials disabled. It then verifies the exact Git blob identities of the reviewed runner, protocol, capture script, and capture contract before installing dependencies or allowing live execution.

The workflow itself has only `contents: read` and `issues: write` permissions. Issue write permission exists only for durable start/result audit comments. The workflow cannot push commits, mutate branches, merge pull requests, alter source capabilities, or write campaign evidence into Git.

## Preflight

A network-free status check must report a fresh empty hosted-runner campaign:

- `completed_slots = 0`
- `total_slots = 4410`
- `complete = false`
- `blocked = false`
- no in-flight attempt marker
- `historical_coverage_proven = false`

Any other preflight state fails before live network execution.

## Live campaign

The only live command is:

```text
python scripts/run_fotmob_ordinary_ft_source_history_acquisition.py --execute-live-network
```

The workflow does not pass `--max-successful-slots`, alter sleeps, parallelize requests, or bypass the runner's retry and A/B observation gates. The job is serialized through a repository-wide campaign concurrency group and has a bounded 330-minute job timeout.

## Evidence preservation

Regardless of the runner's outcome, the workflow attempts to preserve:

- preflight status;
- execution metadata;
- complete runner log;
- post-run network-free status and stderr;
- the entire `.cache/athena-research` tree as a deterministic `tar.gz` snapshot;
- SHA-256 digests for the packaged files;
- an execution envelope recording run identity and exit codes.

The resulting GitHub Actions artifact is named:

`fotmob-ordinary-ft-source-history-campaign-<run-id>`

and is retained for 30 days. Raw captures and campaign journals remain research evidence only and are never committed to Git.

If the run fails or is not complete, the workflow records a result marker stating that execution is **not qualified** and that the artifact must be reviewed before any retry or reconciliation action.

## Success gate

A workflow run can finish successfully only when all of the following are true:

- live runner exit code is zero;
- network-free post-run status exits zero;
- exactly `4410` slots are complete;
- the campaign reports `complete = true` and `blocked = false`;
- no in-flight marker remains;
- no runner lock remains;
- the campaign index contains exactly `4410` successful slot entries.

Even then, the workflow does **not** promote `historical_coverage` or claim source-history completeness. The captured evidence must still pass the later reviewed completeness/mapping/chronology/result-disposition assessment before any source capability or downstream authority can change.

## Safety boundary

Installing this control plane does not itself perform network acquisition and does not establish historical coverage. Model, probability, pricing, selection, production, and BET authority remain false.

The intended sequence is:

1. merge this reviewed execution-lane PR;
2. verify branch cleanup and exact new `main`;
3. post the exact one-shot owner command using that `main` SHA;
4. preserve and inspect the resulting GitHub Actions evidence artifact;
5. only then create a reviewed campaign execution receipt/assessment.
