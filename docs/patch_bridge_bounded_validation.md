# ATHENA Patch Bridge synthetic sharded validation

## Purpose

The Patch Bridge applies an explicitly reviewed, SHA-bound patch to an open same-repository draft pull request. Because the bridge itself pushes with GitHub's `GITHUB_TOKEN`, that push must not be assumed to trigger a normal pull-request workflow run.

The earlier bounded-only bridge exposed this exact platform behavior: the bot push produced a `Tests` run with conclusion `action_required` and zero jobs, and its post-push issue-comment receipt was rejected as `Resource not accessible by integration`.

The bridge therefore has to prove the full synthetic-merge test gate **before the bridge is allowed to push**. It must not depend on a second workflow being triggered by its own token.

## Frozen mutation guards

Before any test or write authority is reached, the bridge still requires:

- owner-only `/athena-apply` on an open draft pull request;
- same-repository head branch;
- exact current head SHA matching the supplied `base-sha`;
- exact SHA-256 of the UTF-8 patch bytes;
- bounded patch size;
- successful `git apply --check` with whitespace errors rejected;
- every changed path inside the existing allowlist, including newly created untracked or ignored paths rather than only already-tracked diffs;
- `.github/` workflow mutation through Patch Bridge forbidden;
- binary patches forbidden by inspecting the exact patch numstat, including newly created binary files;
- a clean validation commit and `git diff --check`;
- exact GitHub synthetic merge SHA available;
- exact synthetic merge parents equal to the captured base SHA followed by the captured head SHA.

The root `athena.patch` transport file is the only untracked path excluded from changed-path admission. The path scan deliberately does not use standard ignore rules, so a patch cannot hide a new forbidden file by first adding it to `.gitignore`.

All external actions remain pinned to immutable commit SHAs.

## Parallel full-suite gate

After structural validation, the exact patch is uploaded once as a one-day artifact. The bridge then validates the **exact pre-push synthetic pull-request merge** in parallel:

1. Eight isolated `synthetic_test_shard` jobs check out the exact `refs/pull/<PR>/merge` commit.
2. Every shard verifies that checkout equals the merge SHA captured before validation.
3. Every shard verifies the patch artifact SHA-256 and applies that exact patch to the synthetic merge.
4. Each test shard removes only the patch transport file, stages the exact patched synthetic tree, records that tree with `git write-tree`, creates a local unpushed validation commit, proves the commit tree is exactly the recorded tree, and requires a clean tracked worktree before pytest. The local commit changes no tested bytes; it only prevents repository tests that correctly require a clean tracked checkout from mistaking the Bridge's own uncommitted validation patch for product dirtiness.
5. Test files are deterministically sorted and distributed across the same eight slices used by ATHENA's normal hosted Tests workflow.
6. All eight shards run their complete assigned pytest file sets with `PYTHONPATH` rooted in the checkout.
7. An independent `synthetic_syntax` job applies the same patch to the same pinned merge, runs repository-wide `compileall`, and records the exact resulting Git tree SHA.

The local synthetic validation commits are never pushed and grant no write authority. The authoritative object compared at the write gate remains the exact patched synthetic **tree**, not a temporary validation commit identity or timestamp.

The old serial `python -m pytest tests -q` bottleneck is not restored.

## Write gate

The commit job cannot start unless structural validation, all eight synthetic test shards, and synthetic syntax all succeed.

Immediately before writing, it re-reads the pull request and requires both:

- head SHA unchanged from the captured head;
- base SHA unchanged from the captured base.

It then re-verifies the patch artifact digest, reapplies the exact patch to the exact validated head, commits, and pushes without force.

Finally, it computes the merge tree of the exact captured base with the newly pushed head using `git merge-tree --write-tree`. That tree must equal the exact patched synthetic tree recorded by `synthetic_syntax`. A mismatch fails the bridge instead of claiming that an untested merge was pushed.

## Stacked pull requests

A stacked draft may be patched while its feature base is under review. The bridge validates the synthetic merge against that exact current feature-base SHA. If the stacked PR is later retargeted or its base advances, that new base is a new merge boundary and must be revalidated before merge readiness.

## What a successful bridge run means

A successful Patch Bridge run means:

- exact requested patch bytes were applied;
- path/mutation safety passed for tracked, newly created, and ignored paths;
- the exact base/head synthetic merge plus that patch passed all eight hosted test shards from clean tracked worktrees whose local commit trees equal the patched synthetic tree;
- synthetic syntax passed;
- the pushed merge tree exactly matched the tested synthetic tree.

It still does not merge the pull request or grant any product/model/evidence/pricing/selection/BET authority by itself.
