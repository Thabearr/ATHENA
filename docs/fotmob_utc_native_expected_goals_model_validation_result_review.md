# FotMob UTC-native expected-goals validation result review

## Boundary

This review freezes the evidence produced by the successful source-bound validation run `32049714066`. It is a research-result review only. It does not refit or calibrate the model, build ScoreMatrix, calculate market probabilities, inspect bookmaker prices, select bets, or grant production/BET authority.

The successful execution is bound to `main` `b8ddc00f7529c5533c9da2daad613d997498cbf2`, owner command comment `5318114406`, durable attempt marker `5318115383`, and result comment `5318117332`.

The preserved result artifact is `9294215497`, `5,441,951` bytes, SHA-256 `e9eac385a66df04bf28e7d69062e55db516829e94405e4a8def0e4d6a346d6c5`. Its canonical result receipt is `55,507` bytes with SHA-256 `1fffee7474ab37ee613e6a7943b57fd9231f6d6bdf53ffa6b13ee2b62ceca06a`; its `6,948` prediction rows hash to `2f4939a8f2d41674660144f5315d2420ce2f006ce2b885e52c6655abd0e52420`.

## Reviewed signal

The frozen validation state is `MIXED_OR_WEAK_FOTMOB_UTC_NATIVE_SUCCESSOR_SIGNAL_REVIEW_REQUIRED`.

Nine of the ten pre-registered strong-signal checks passed. The native same-family refit beat the Elo-only nested GLM on mean joint Poisson NLL in both chronological evaluations and in the pooled `6,948` fixtures:

- Evaluation A: `-0.0019040180402716267` native-minus-Elo;
- Evaluation B terminal: `-0.002354865405624018`;
- pooled A+B: `-0.0021296363893399395`.

The nine-quarter delete-one-quarter robustness estimate is also directionally stable. Its full native-minus-Elo estimate is `-0.002129636389340353`; the frozen 95% interval is `[-0.003174014813778359, -0.0010852579649023473]`, so the upper bound remains strictly below zero.

The sole failed strong-signal gate is pooled home-goal WACE. Native refit home WACE is `0.05778673203465596`, while Elo-only home WACE is `0.05490445024426852`; native-minus-Elo is therefore `+0.0028822817903874365`, but the protocol requires native to be strictly lower.

The historical fixed-coefficient transfer and no-fatigue ablation remain diagnostics only under the pre-registered protocol. They are not approval gates and must not be retrospectively promoted into gates after seeing the result. The historical transfer happens to be lower than native pooled NLL by about `0.0000629233`; that observation does not authorize promoting the historical coefficients instead.

## Successor decision

The evidence supports retaining a real research signal from form/Elo/fatigue beyond Elo alone, but it does **not** support successor approval.

Therefore:

- `FOTMOB_NATIVE_SAME_FAMILY_REFIT` remains unapproved for production;
- the historical fixed-coefficient transfer is not promoted as a substitute;
- home calibration requires a pre-registered follow-up;
- league/competition robustness remains blocked because the frozen projection does not carry competition identity;
- runtime portability caveats remain uncleared;
- every ScoreMatrix, probability, pricing, selection, production, and BET authority remains false.

## Holdout consumption rule

Evaluation A and Evaluation B labels have now been inspected and are consumed by this result review. A later calibration or coefficient change may use them as development evidence only if explicitly pre-registered as such, but the same rows may not then be presented as a fresh confirmation set.

Any follow-up that tunes home calibration after this review must pre-register the transformation before inspecting its confirmation result and must obtain a fresh chronological holdout starting no earlier than `2026-08-15T00:00:00Z`, the exact exclusive end of the consumed terminal evaluation window. The follow-up dataset should also carry exact competition identity so league/competition robustness can finally be evaluated rather than inferred or fuzzily reconstructed.

## Next boundary

`PRE_REGISTER_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_HOME_CALIBRATION_AND_COMPETITION_IDENTITY_FOLLOWUP`

That next boundary is still research-only and cannot grant automatic production authority.
