# SportyBet user-controlled evidence workflow

## Purpose

PR #152 established the reviewed public SportyBet Lite source shape but deliberately kept automated SportyBet acquisition blocked. This boundary provides a permitted alternative that does not make ATHENA act as a robot or scraper: a human user may manually observe a reviewed SportyBet Lite page in their ordinary browser, export/save the HTML, and then import those exact local bytes into ATHENA offline.

This boundary is evidence ingestion only. It does not authorize fixture reconciliation, canonical market mapping, fresh-price use, pricing, selection, slip construction, booking codes, SportyBet execution, or `BET`.

## Source method

The only admitted acquisition mode is:

`USER_CONTROLLED_BROWSER_EXPORT`

ATHENA itself performs **no network I/O** in this workflow. The import command accepts a local HTML file and the exact source URL that the user manually observed.

The user must supply the exact attestation:

`I_MANUALLY_OBSERVED_AND_EXPORTED_THIS_PAGE`

The attestation records provenance; it does not make the user-attested time a provider timestamp.

## Exact source identity

Only the source surface reviewed in PR #152 is admitted:

- `https://www.sportybet.com/ng/lite`
- `https://www.sportybet.com/ng/lite/preMatch/detail?eventId=...&marketGroupsName=Main&sportId=...`

The importer rejects alternate hosts, HTTP, explicit ports, user-info, fragments, unreviewed paths, duplicate query keys, missing event-detail keys, unreviewed market-group values, and noncanonical event-detail query identity.

Provider event and sport IDs retain their exact native `sr:match:<positive integer>` and `sr:sport:<positive integer>` forms.

## Observation-time semantics

`observed_at_user_attested` means only: **the user states that they observed/exported the page at this time**.

Its authority is frozen as:

`USER_ATTESTED_NOT_PROVIDER_TIMESTAMP`

Accordingly:

- `provider_quote_at = null`;
- `provider_snapshot_id = null`;
- `observed_at_user_attested` is never substituted for a provider quote time;
- this evidence is insufficient by itself for a future fresh-price authorization.

`imported_at_utc` is the later ATHENA import time. It must not precede the user-attested observation.

## Raw evidence durability

Evidence is published only under:

`.cache/athena-research/sportybet-user-controlled-evidence`

Each evidence directory contains exactly:

- `page.html` — the imported local bytes;
- `manifest.json` — canonical UTF-8/LF JSON provenance.

The manifest records source URL, exact reviewed request identity, user-attested observation time, import time, acquisition mode, raw byte length/hash, null provider quote/snapshot fields, and all downstream authority as false.

The evidence directory ID is deterministically bound to source URL + user-attested observation time + raw SHA-256. An exact replay of the same full manifest and raw bytes is idempotent; a later re-import with changed import metadata fails closed rather than overwriting earlier evidence. Differing evidence cannot overwrite an existing directory. Traversal and symlink escapes fail closed. Raw and manifest files are fsynced and the same reviewed directory-durability machinery used by the PR #152 SportyBet capture boundary is reused.

The manual-evidence root is deliberately distinct from PR #152's future authorized live-capture root so user-controlled evidence can never masquerade as ATHENA-acquired network evidence.

## Import command

Example:

```text
python -m scripts.import_sportybet_user_controlled_evidence \
  --html-file path/to/exported-page.html \
  --source-url 'https://www.sportybet.com/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1' \
  --observed-at '2026-08-18T12:00:00Z' \
  --attestation 'I_MANUALLY_OBSERVED_AND_EXPORTED_THIS_PAGE'
```

The command emits a deterministic receipt identifying the evidence directory, manifest SHA-256 and raw SHA-256 while explicitly reporting:

- `athena_network_acquisition_performed = false`;
- `network_acquisition_authorized = false`;
- `fresh_price_authorized = false`;
- `pricing_authorized = false`;
- `selection_authorized = false`;
- `sportybet_execution_authorized = false`;
- `bet_authorized = false`.

## What this unlocks

This creates a lawful/reviewable source lane for exact SportyBet HTML evidence without automated website access. A later boundary may verify a preserved user-controlled evidence directory, parse its provider-native SportyBet selections using the PR #152 inventory logic, and then begin exact SportyBet event-to-trusted-fixture reconciliation.

That later work must still preserve the distinction between:

1. user-attested observation time;
2. provider quote time, if a provider-native timestamp is ever proven;
3. ATHENA import time.

No price, no `BET`; and a user-attested timestamp alone is not a fresh provider price timestamp.
