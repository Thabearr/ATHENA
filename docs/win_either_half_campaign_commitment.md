# Win Either Half Campaign Commitment Contract (Stage 5B4)

## Purpose and Relationship to Stage 5B2 & Stage 5B3

Stage 5B3 prospective capture campaigns emit an ignored, local schedule (`UNFROZEN_LOCAL_PLAN`). While Stage 5B3 campaign identity is fully deterministic, a locally generated schedule does not prove *when* it was created.

Stage 5B4 introduces a lightweight, tracked commitment declaration contract that binds a Stage 5B3 capture campaign schedule (`tasks`, `summary`, `manifest`, and upstream protocols) to a GitHub-hosted runner UTC timestamp prior to the campaign's earliest capture window (`commitment_deadline_at`).

```
Stage 5B2 (Prospective Replay Protocol)
   │
   ▼
Stage 5B3 (Prospective Capture Campaign Schedule) ──► UNFROZEN_LOCAL_PLAN (Ignored)
   │
   ▼
Stage 5B4 (Campaign Commitment Declaration) ───────► Tracked Git File + GitHub PR Check
```

## Untrusted Timestamps

Local system clocks, local file creation/modification times, Git author dates, and Git committer dates are user-controlled and are not accepted as authoritative proof of pre-registration.

Stage 5B4 separates declaration generation from timing qualification:
- **Local Generation**: Builds a deterministic JSON declaration freezing exact bundle hashes, campaign identity, and `commitment_deadline_at` without reading local wall clocks.
- **GitHub Qualification**: Evaluates the declaration on a pull request using GitHub-hosted runner UTC (`server_observed_at <= commitment_deadline_at`).

## Local Deterministic Declaration Generation

An operator generates a local declaration using:

```bash
python -m scripts.manage_win_either_half_campaign_commitment \
  --tasks .cache/athena-research/win-either-half/capture-campaign/capture-campaign-tasks-v1.jsonl \
  --summary .cache/athena-research/win-either-half/capture-campaign/capture-campaign-summary-v1.json \
  --manifest .cache/athena-research/win-either-half/capture-campaign/capture-campaign-manifest-v1.json \
  --create artifacts/research-commitments/win-either-half/WEH-CAP-<24-HEX>.json
```

Generation requires a clean tracked Git worktree and performs exact byte and parsed schema validation against committed Stage 5B2, Stage 5B3, and Stage 5B4 protocols.

## Exact Tracked Path and Filename Contract

Declarations must be created at:

`artifacts/research-commitments/win-either-half/<campaign_id>.json`

- Pattern: `^WEH-CAP-[0-9A-F]{24}\.json$`
- Exactly one campaign per file;
- Symlink path components are forbidden;
- Paths outside `artifacts/research-commitments/win-either-half/` are rejected.

## Exact Head-Tree Blob and Working-Tree Verification

Validation in `--validate-git-diff` mode verifies declarations using exact Git blob and tree objects:
- Exact tracked head-tree blob bytes are canonicalized and hashed.
- Working-tree bytes must equal head-tree blob bytes byte-for-byte.
- A local `--validate-git-diff` invocation is for offline verification only and is **not platform proof** of prospective timing.

## Atomic Persistence, File System Integrity, and Strict Cleanup

Stage 5B4 implements hardened fail-closed file system and Git parsing guarantees:
- **Strict Cross-Platform Fsync**: `_fsync_dir` and `_fsync_file` open directory/file handles and invoke `os.fsync` across all operating systems (including Windows and POSIX) without swallowing `OSError` or `IOError`.
- **Strict Tree Cleanup**: Directory tree removals use `_remove_tree_strict` with a single, fail-closed `shutil.rmtree` invocation.
- **Full 40-Hex Git Object SHA Enforcement**: `_parse_single_ls_tree_record` parses NUL-delimited `git ls-tree` records and validates object SHAs with `validate_git_sha` to prevent truncated or malformed hashes.
- **Unconditional Head Protocol Verification**: `validate_git_diff` unconditionally reads the head Stage 5B4 commitment protocol and asserts exact byte equality against the base-revision verifier protocol bytes before signing the attestation.

## GitHub Base-Verifier and Server-UTC Deadline Check

When a pull request introduces a new commitment declaration, the `.github/workflows/validate-win-either-half-campaign-commitment.yml` workflow runs:

1. **Exact Revision Checkouts**: Checks out the exact PR head SHA (`github.event.pull_request.head.sha`) and exact base SHA (`github.event.pull_request.base.sha`). The workflow explicitly verifies checked-out SHAs with `git rev-parse HEAD`.
2. **Base-Revision Verifier Execution**: Future declaration PRs execute verifier code from the base revision (`main`). The declaration PR's own code changes do not execute for deadline validation.
3. **Server-Observed UTC**: Obtains `date -u +%Y-%m-%dT%H:%M:%S.%6NZ` from the GitHub runner.
4. **Strict Comparison**: Requires `server_observed_at <= commitment_deadline_at`. Exact equality passes; even a single microsecond late fails closed.

## Local Check Mode and Generator Ancestry Verification

The `--check` verification mode:
- Rebuilds the expected declaration using the stored `generator_git_sha`.
- Verifies that `generator_git_sha` is a valid commit object in the repository (`git cat-file -e <sha>^{commit}`).
- Verifies that `generator_git_sha` is an ancestor of the current clean HEAD (`git merge-base --is-ancestor`).
- Rejects dirty tracked worktrees and requires exact stored byte equality.

## Separation of Tooling PRs and Declaration PRs

PR #27 is **tooling-only and contains no declaration**.

Future PRs must maintain strict separation of duties:
- A declaration PR must ONLY add new commitment files under `artifacts/research-commitments/win-either-half/`.
- A declaration PR that attempts to edit workflow, protocol, domain, or script code in the same pull request is rejected automatically.

## Immutability Contract

Commitment declarations are additions-only:
- `A` (Addition): Permitted for new valid files.
- `M` (Modification), `D` (Deletion), `R` (Rename), `C` (Copy), `T` (Typechange): Strictly forbidden.

Once merged to `main`, a commitment declaration can never be altered or removed.

## Attestation Artifacts and 90-Day Retention

Upon successful validation, the workflow emits a JSON attestation artifact:

`win-either-half-campaign-commitment-${{ github.run_id }}`

- Retained for 90 days as supplementary audit material.
- Artifact expiration does not erase the authoritative GitHub run ID and `success` conclusion.
- The authoritative platform record is the GitHub Actions workflow run ID and `success` conclusion.

## Truth Statement

"A declaration file alone does not prove prospective timing. Timing is qualified only when the declaration is added in a pull request and the GitHub-hosted `Validate Win Either Half Campaign Commitment` check succeeds no later than `commitment_deadline_at`. The check qualifies timing only. It does not validate future quote evidence, select an offset, enable a market, authorize production, or authorize a bet."

## Safety Boundary

- Both Win Either Half markets remain `DISABLED`.
- `selected_offset_seconds` remains `null`.
- `selection_authorized` remains `false`.
- `production_approval_authorized` remains `false`.
- `prospective_claim_authorized` remains `false`.
- No odds collection, pricing models, fair odds, EV, Kelly, or bet decisions are included.
