# Fresh-holdout lineage audit permanent control issue

## Status

`OPEN_ISSUE_CONTROL_SURFACE_OBSERVABILITY_ONLY`

The read-only FotMob UTC-native xG fresh-holdout lineage audit was originally bound to merged PR #170. After PR #171 added explicit fail-closed workflow reporting, repeated owner commands posted through the connected GitHub client to the merged PR still produced no visible audit-result or fail-closed comment. That observation does **not** establish a GitHub Actions platform failure or a campaign-lineage outcome; it only establishes that the merged-PR command path is not a reliable observable control surface for this client.

GitHub issue #172, `ATHENA Fresh-Holdout Lineage Audit Control`, is therefore the permanent open owner-only control surface for the prospective campaign. The legacy merged PR #170 route remains accepted as a fail-closed fallback so the reviewed contract is not silently removed.

## Exact control issue identity

The workflow accepts the issue route only when all of the following remain true:

- issue number is exactly `172`;
- the event object is an ordinary issue, not a pull request;
- the issue is open;
- the issue was created by the repository owner;
- the title is exactly `ATHENA Fresh-Holdout Lineage Audit Control`;
- the comment author is the repository owner;
- the command is the exact reviewed three-line command;
- the supplied lowercase 40-character SHA is exact current `main`.

The guard re-fetches issue #172 from GitHub before granting `authorized=true`; event payload fields alone are not sufficient.

## Command

```text
/athena-audit-fresh-holdout-lineage
main-sha: <exact-current-main-sha>
confirm: READ_ONLY_ACTIONS_LINEAGE_AUDIT
```

No extra line, whitespace variant, uppercase SHA, different confirmation text, non-owner comment, closed issue, title drift, issue replacement, or moved `main` may authorize the audit.

## Result routing

A successful audit posts its compact observability result back to the exact approved surface that authorized it. An authorized control-workflow failure posts `AUDIT_CONTROL_WORKFLOW_FAILED_CLOSED` back to that same surface with the Actions run ID and no lineage authority.

Result comments do not contain the slash command or confirmation token and therefore cannot self-authorize another audit.

## Legacy PR #170 fallback

The prior PR #170 control surface remains accepted only when GitHub still proves it is the exact merged and closed PR. This is backward compatibility, not the preferred operating route. New operator commands should use open issue #172.

## Safety boundary

This change does not modify the PR #170 audit algorithm, PR #151 collection runner, PR #168 Release evidence contract, PR #169 source replay, xG model/calibration semantics, SportyBet evidence, or any football decision logic.

It grants no authority for:

- provider network acquisition;
- observation backfill or retrofill;
- workflow rerun or retry;
- Release repair or evidence mutation;
- model approval or production promotion;
- bookmaker equivalence;
- pricing or value claims;
- selection;
- slip/ACCA construction;
- booking-code generation;
- execution;
- `BET`.

The underlying Actions artifacts, canonical receipts, Release mirrors, and durable control journal remain the evidence. The issue comment is only an observability/control surface.

## Next boundary

`TRIGGER_OPEN_ISSUE_172_AND_REVIEW_EXPLICIT_FRESH_HOLDOUT_LINEAGE_AUDIT_RESULT`

After merge, post the exact command to open issue #172 against then-current `main`. A successful audit may report verified, partial, or no-completed-evidence state. A failed authorized workflow must remain failed and surface the exact audit Actions run ID without deriving campaign lineage.
