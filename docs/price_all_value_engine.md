# Price-all Value Engine

Phase 7 changes ATHENA's boundary from “choose a market, then inspect its price”
to “evaluate every upstream-authorized calibrated candidate against exact
SportyBet evidence.” It produces auditable value records for the Phase 8 Market
Router; it does not rank, route, select, export, or authorize a bet.

## Contract and source boundary

Contract version 1 is independently pinned at
`1fb0a6c891adccd76b4864a6197e55d22154176a4191f57ce92cde13501535aa`.
It binds the reviewed Phase 6 calibration contract, canonical market semantics,
reviewed SportyBet canonical-mapping semantics, the 900-second freshness rule,
de-vig classification, unit-stake settlement returns, and all authority flags.
Protocol records use deterministic JSON and SHA-256, never pickle or joblib.

The authoritative quote path is not a free-form odds dictionary, and the
reviewed canonical mapping cannot mint freshness by itself. Quote issuance
replays the exact `SportyBetUserControlledNativeInventory` evidence directory,
verifies its manifest and raw HTML, binds its canonical inventory SHA to the
reviewed mapping, and derives provider identity and decimal odds from the exact
native selection. Observation time comes from the verified manifest's
user-attested timestamp. This is explicitly
`USER_ATTESTED_NOT_PROVIDER_TIMESTAMP`; provider quote time and provider
snapshot identity remain unproven and `None`.

The canonical inventory SHA is the evidence-snapshot identity. The quote also
retains raw-evidence, manifest, inventory, mapping, and fixture-reconciliation
SHA ancestry. Evidence older than 900 seconds, future evidence, tampered bytes,
duplicate exact provider identities, or ambiguous ancestry fail closed.

## Calibrated candidates and dispositions

Candidate issuance requires an exact reviewed Phase 6
`ForwardCalibrationArtifact` and exact `CalibrationVectorRow`. The engine
validates the frozen calibration contract, artifact SHA, model identity,
calibration unit, canonical market/outcome/line, component vector, and
selection-specific semantics before projecting the calibrated distribution. A
caller boolean or syntactically valid artifact SHA has no authority. Phase 6
currently authorizes Total Goals only at non-negative half-goal lines; integer
and quarter-goal totals cannot become Phase 7 candidates merely because generic
settlement mathematics exists.

Every candidate receives one output,
including unpriced and blocked candidates. Output is ordered deterministically
by candidate ID. It contains no selected flag, ranking, recommendation, router
winner, accumulator approval, or BET authorization.

Win Either Half, 1UP, and 2UP remain blocked because Phase 6 does not grant the
required calibrated-probability authority. An exact quote may be retained by
the quote contract for audit, but it cannot manufacture probability authority.

## De-vig policy

Proportional de-vig is used only for a complete mutually-exclusive, exhaustive
partition from the same fixture, SportyBet event, source, exact evidence
snapshot, provider market ID, provider specifier/line, mapping ancestry,
inventory ancestry, reconciliation ancestry, canonical market, and line:

- regulation 1X2;
- BTTS Yes/No;
- Over/Under at one exact half-goal line;
- each Result-or-Over Yes/No market;
- each Win-to-Nil Yes/No market.

Double Chance and early-payout selections overlap and are never normalized as
a partition. DNB and Asian Handicap contain push or split-settlement states, so
ordinary proportional de-vig is not claimed. A genuine exact quote may still
receive settlement-aware EV while `fair_probability` remains absent.

## Settlement-aware value

For decimal odds `d`, unit-stake profits are: WIN `d-1`, HALF_WIN `(d-1)/2`,
PUSH `0`, HALF_LOSS `-0.5`, LOSS `-1`. EV is the calibrated probability-weighted
sum of those profits. DNB therefore requires WIN/PUSH/LOSS. Asian Handicap,
including quarter lines, requires WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS. Missing
states block pricing instead of being flattened to a scalar probability.

`expected_return_multiplier = 1 + net_expected_value`; EV percentage is net EV
times 100. These are candidate records, not decisions.

## Authority and real-current status

Only verified-price consumption and value-record computation are true. Football
probability generation, model promotion, market routing, final selection,
accumulator, production approval, and BET authority are false. Existing legacy
`domain/pricing.py` behavior remains available unchanged.

No current source-qualified SportyBet quote corpus is committed or available to
this implementation, so:

`REAL_CURRENT_SPORTYBET_PRICE_ALL_STATUS = NOT_RUN_VERIFIED_QUOTE_CORPUS_UNAVAILABLE`

Synthetic tests establish contract mathematics only; they make no claim about
current odds, coverage, or real-world EV.
