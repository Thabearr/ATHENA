# PR284 — Current Shadow 30-minute prospective lead policy

This change is intentionally limited to the current all-market research/shadow runner.

- Preserve the frozen PR243 current-source policy at 3600 seconds for existing callers.
- Add a distinct versioned Shadow policy with a fixed 1800-second prospective lead.
- Preserve the 900-second source-age bound unchanged.
- Preserve exact requested-date, reviewed competition, PR41 conflict, and downstream safety gates.
- Do not expose the 1800-second value as a CLI or caller-supplied override.
- Do not change Price-all quote freshness/lead rules, Router thresholds, provider semantics, portfolio rules, production authority, staking, wallet, or wager behavior.

Regression proof must show that a fixture at exactly 1800 seconds is admitted by the Shadow policy, a fixture at 1799 seconds is excluded, and the frozen PR243 3600-second policy remains unchanged.
