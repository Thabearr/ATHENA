# Historical expected-goals successor real-corpus receipt

This PR records the exact one-shot, retrospective chronological execution of the frozen PR73 successor fitter. It is canonical evidence, not a model change or approval.

**THIS PR RECORDS EVIDENCE. IT DOES NOT APPROVE THE MODEL.**

## Frozen ancestry

PR72 froze the successor protocol before fitting, and PR73 merged the deterministic fitter before the real-corpus execution. This receipt embeds the complete revalidated PR73 candidate, anchored to the preserved football-data.co.uk source corpus and the PR69, PR70, PR71, and PR72 boundaries. It records the expected candidate SHA-256 `1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660` and its 19,956 canonical bytes.

The evaluation is `RETROSPECTIVE_CHRONOLOGICAL_EVALUATION_NOT_UNTOUCHED_HOLDOUT`: training uses 2020-21 through 2023-24 and evaluation uses 2024-25 and 2025-26. It is not prospective or an untouched holdout.

## Result recorded

Across 6,903 chronological evaluation fixtures, the successor has lower mean joint Poisson NLL than all four frozen comparators. It is lower than the PR68 form component, PR68 Elo fallback component, frozen constant baseline, and strict pre-match rolling identity-league baseline overall, in both evaluation seasons, and in each of the eleven exact identity leagues. The receipt intentionally records these factual comparisons without a statistical-significance claim.

## Calibration and coefficient caveats

The receipt preserves every frozen calibration bin. The high-rate bins show overprediction, including home 2.5–3.0 and 3.0+ as well as away 2.5–3.0 and 3.0+. It does not claim calibration is materially superior to legacy Elo: PR71's legacy-Elo calibration used a broader full-corpus population, whereas this candidate uses the frozen chronological evaluation subset. A same-fixture calibration comparison remains future work.

The cross-form coefficients are directionally coherent: stronger away form suppresses home scoring and stronger home form suppresses away scoring. Fatigue warrants separate stability or ablation work. PR69 defines positive fatigue as the home side having fewer rest days; the learned home response is positive and away response negative, opposite a simple causal fatigue-disadvantage story and the legacy heuristic effect. This receipt does not flip, remove, or refit fatigue. `fatigue_pr31_semantic_equivalence` remains `UNPROVEN`.

## PR71 newline provenance

The PR71 worktree JSON representation observed CRLF conversion, so its working-tree bytes did not carry the frozen canonical receipt SHA. Reconstruction therefore used the immutable committed Git blob (`d33097e128534588609d15c41ba25620254a6ac8`) whose bytes match the canonical PR71 SHA. The converted working-tree bytes were not normalized and were not used as evidence.

## Safety boundary

No source freshness regime was reconstructed. Elo initialization remains the `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`, not an observed value. All successor safety flags remain false. This receipt authorizes no successor approval, expected-goals production use, score matrix, probability inference or adjustment, production calibration, pricing, market activation, selection, or betting.
