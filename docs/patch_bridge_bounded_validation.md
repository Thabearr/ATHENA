# ATHENA Patch Bridge bounded validation

## Purpose

The Patch Bridge exists to apply an explicitly reviewed, SHA-bound patch to an open draft pull request. It is a mutation transport and pre-push safety gate, not a replacement for ATHENA's normal hosted pull-request test workflow.

## Pre-push guarantees

Before the bridge may push a patch, it still requires:

- owner-only `/athena-apply` on an open same-repository draft pull request;
- the supplied `base-sha` to equal the exact current pull-request head;
- an exact SHA-256 match for the UTF-8 patch payload;
- successful `git apply --check` with whitespace errors rejected;
- changed paths to remain inside the existing allowlist;
- GitHub workflow mutation through Patch Bridge to remain forbidden;
- binary patches to remain forbidden;
- a clean validation commit and `git diff --check`;
- repository-wide Python `compileall` success;
- every pytest file changed by the patch to pass before push;
- exact revalidation that the pull-request head has not moved before the validated patch is committed;
- exact SHA-256 verification of the uploaded patch artifact before the write job applies it.

The validate job is bounded to 10 minutes and the commit job to 5 minutes.

## Full-suite authority

The bridge no longer executes `python -m pytest tests -q` serially. Pull requests targeting `main` already receive the repository's normal eight-shard Tests workflow plus syntax gate after the bridge pushes the new head. That hosted synthetic-merge CI is the authoritative full-suite merge gate.

For a deliberately stacked draft whose base is not `main`, the bridge provides only the bounded pre-push checks above. The stacked pull request must be retargeted to `main` and pass the normal full hosted suite before it can become merge-ready.

A successful Patch Bridge comment therefore means only that the requested patch passed the bounded pre-push contract and was committed/pushed. It does not claim that the pull request has passed its final full-suite merge gate.

## Reproducibility

All external actions used by the write-capable bridge are pinned to immutable commit SHAs rather than movable major-version tags.
