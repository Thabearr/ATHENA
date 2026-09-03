# Current FotMob reviewed extra-halfs schema V2

This change is a narrow current-source compatibility review prompted by exact live evidence from `current-shadow-all-market.yml` run `33690015364`, artifact `9869665644`.

The captured `/api/data/matches` response for request date `20260902` had raw SHA-256 `070c63fa4480e470ba94b2e6726ad4959c89f2bcffd6c3929304590ac8ef5973`. The preserved manifest file SHA-256 is `18dc76e89be17fbd24c048b17954c22c85dab07e5daeffe203f14c2040e0cb1d`.

Observed `status.halfs` additions:

- `firstExtraHalfStarted`: 4 occurrences, every observed value an exact string.
- `secondExtraHalfStarted`: 4 occurrences, every observed value an exact string.

These are the same two opaque keys already reviewed by the fresh-holdout structural compatibility path. The current fixture-candidate adapter V2 admits only these exact names and only exact string values. They are removed from a validation-only projection before replaying the frozen PR87/PR89 structural chain.

No extra-time football semantics are inferred. The strings do not become model features, probabilities, pricing inputs, selection authority, production authority, or betting authority. The exact original network raw SHA and manifest ancestry remain attached to emitted current fixture candidates.

Unknown `status.halfs` keys still fail closed. Null, numeric, boolean, list, and object values for either reviewed key still fail closed.

This change does not modify the frozen PR39, PR87, or PR89 implementations and does not belong to PR #287. It exists solely to restore exact current-source structural compatibility for the already observed additive fields.
