# CORE-01D immutable offline inputs

- `accepted-athena-run-36860297707.zip`: exact downloaded GitHub artifact
  11163921301, `athena-run-36860297707`, 2,915,212 bytes. Independently computed
  SHA-256 matches GitHub metadata:
  `9d14b71413ed68e9e157d668a79851e3fbc3dd746c204c8ddfc0eaf245bcf355`.
  Public research source responses and finalized receipts are retained unchanged;
  no credentials, cookies, account state, SMTP configuration or workflow logs are
  included. Retention here removes dependence on the Actions artifact's expiry.
- `workflow-history-20261001.json`: read-only GitHub metadata capture of latest
  and last successful runs for all 39 exact-main workflows. This does not prove
  execution/request parity or authorize retirement. Unavailable metadata stays
  unknown, never fabricated as an empty history.
- `exact-main-source-inventory.json`: all 19,491 tracked base file Git identities,
  workflow tree identity and the explicit source scan set. Environment/cache and
  historical fixture contents are not caller-scan inputs; their committed Git
  identities remain protected. No historical source is rewritten.
- `pre-core01d-remediation-audit.py.txt`: exact tracked pre-C4 remediation audit
  source. The only allowed forward authenticates these two new C4 artifacts
  before subtracting them from the old artifact inventory. Its historical
  receipt/output and every old artifact remain unchanged.

The previous failed LG-A remains in `../lg_a_worker_launch_failure/`, permanently
failed/non-retryable. Its old true manifest is intentionally preserved while the
independent producer receipt validator rejects it forward.
