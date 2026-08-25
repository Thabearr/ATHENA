# Prediction/post-match audit ledger

## Purpose and authority boundary

Phase 0 / PR #227 adds a deterministic research ledger for ATHENA prediction
field trials. It records what was preserved before kickoff, what was later
settled, and what can responsibly be attributed after the match. It does not
change a model, pricing rule, market-selection rule, value router, accumulator,
bookmaker integration, or production state. Every authority flag in the
artifact is exact `false`; the ledger cannot promote a selection to `BET`.

## Three independent namespaces

Each reconstructed leg contains three objects that are never merged:

1. `pre_match_decision` holds the fixture identity, prediction/model lineage,
   evidence references, complete preserved candidate set, chosen candidate,
   risk information, bookmaker mapping/quote evidence, and genuine pre-match
   counterfactuals. Its canonical SHA-256 is also the leg identity.
2. `post_match_settlement` holds regulation-score evidence and one settlement
   state: `WON`, `LOST`, `VOID`, `PARTIAL_WIN`, `PARTIAL_LOSS`, or `UNKNOWN`.
   It also carries an explicit verification state. Definitive outcomes require
   source references; a user-reported outcome remains visibly `UNVERIFIED`.
3. `post_match_attribution` holds decision quality and the controlled primary
   taxonomy: `MODEL_ERROR`, `CONTEXT_ERROR`, `MARKET_CHOICE_ERROR`,
   `PRICE_VALUE_ERROR`, `DATA_ERROR`, `IRREDUCIBLE_VARIANCE`, or `UNKNOWN`.

Adding or changing settlement or attribution does not change the pre-match
identity. A winning settlement does not prove a good decision; a losing
settlement does not prove model error. `IRREDUCIBLE_VARIANCE` requires verified
event evidence, so an unverified penalty report cannot create that attribution.

## Missingness and conflicts

Optional values use an explicit `AVAILABLE`, `MISSING`, or `UNKNOWN` envelope.
`MISSING` and `UNKNOWN` always serialize with `null`; the contract creates no
neutral Elo, form, probability, fair price, or bookmaker-odds default. Unknown
market/outcome/line combinations fail through `domain.markets`. Duplicate
source identities and conflicting output bytes fail closed instead of silently
overwriting evidence. `USER_REPORTED` evidence cannot be marked `VERIFIED`, and
a verified audit claim must reference verified source evidence.

A leg counts as reconstructed only when preserved evidence identifies both its
fixture and its selected canonical market/outcome candidate. A recorded shell
that lacks either is explicitly `UNRESOLVED`, does not reduce the unresolved
count, contributes nothing to the reconstructed settlement summary, and can
never make a trial `COMPLETE`.

## Counterfactual rule

Counterfactual candidate IDs may reference only other candidates inside the
same preserved pre-match candidate set. Each candidate retains its original
market, outcome, line, probability, rank/score, pricing evidence, reason not
selected, and pre-match evidence references when available. Post-match objects
reject counterfactual fields, so ATHENA cannot calculate a new probability
after settlement and represent it as yesterday's alternative.

## Import and replay

`scripts/import_prediction_field_trial.py` reads bounded local UTF-8 JSON only.
It rejects duplicate JSON keys, NaN/Infinity, malformed contracts, unsafe paths,
unknown markets, and any true authority flag. Output is canonical sorted compact
JSON with a final newline and a SHA-256 identity. An exact re-import is a no-op;
different bytes cannot overwrite an existing artifact. The importer performs no
network or provider/browser acquisition and changes no model or pricing state.
Import provenance separately records the frozen contract-origin commit and the
exact commit that executed the import. The execution commit is a required input,
so future imports are not mislabeled with the Phase 0 base SHA. File data is
flushed with `fsync`; directory synchronization is attempted where the platform
supports it and safely skipped where directory handles or directory `fsync` are
unsupported.

The first proper 20-leg trial is currently `SUMMARY_ONLY`: the operator's
planning declaration supports 20 total legs with an aggregate 17 won and 3
lost, but no exact preserved leg-level prediction/result source was recovered.
Therefore the committed artifact contains zero reconstructed legs and twenty
unresolved legs. It preserves no bookmaker prices or pre-match
counterfactuals. The Getafe vs Racing Over 1.5 example and reported Racing
penalty miss remain unverified diagnostic notes; they create neither a fixture
record nor tactical/failure attribution. This sample cannot establish an 85%
true hit rate or any model authority.

## Prospective writing rule

Future prediction runs should persist the pre-match object before kickoff,
including every candidate and exact source/quote snapshot identity, then freeze
its canonical SHA-256. Settlement should append only independently preserved
result evidence. Attribution should be a later explicit review referencing its
own evidence and verification state. Prospective capture removes the need to
reconstruct historical decisions from aggregate outcomes.
