# Historical expected-goals successor robustness real-corpus receipt

This PR records the exact first source-bound real-corpus execution of the frozen PR75 robustness protocol using the merged PR76 evaluator. It is an immutable research receipt only.

**THIS PR RECORDS EVIDENCE. IT DOES NOT APPROVE THE MODEL OR AUTHORIZE BETTING.**

## Execution ancestry

The execution was anchored to `main` commit `02de50766e54cc362aeab3ff819c267c0dbab2f4`, after PR76 had merged. The disposable execution transport was GitHub Actions run `31750880150`, job `94616111481`, on branch `research/pr76-real-robustness-20260813` at head `cbc0c50557d769dbb07ace8c7ad4dbcb7c88d52d`. That branch differed from `main` only by the temporary workflow used to invoke the already-merged evaluator.

The run reconstructed the exact 66-file football-data.co.uk corpus: 10,006,877 raw bytes and 21,226 fixtures. The source corpus SHA-256 remained `c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0`; the canonical PR69 replay SHA-256 remained `b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3`.

The exact frozen PR74 successor candidate identity was `1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660`. The frozen PR75 robustness protocol SHA-256 was `eaa2fd1f906f0a18c39f972d919a0393569c85dc8ad6038cbed10819fd2c0774`.

The resulting canonical robustness evaluation is 15,974 bytes with SHA-256 `3ff465edef9c4abd2f0d4dfcb4f776fea64103c0dc26941f44d2b09ba2e4066b`. Full source-bound revalidation succeeded before the result was accepted.

## Paired NLL robustness

On the exact 6,903 evaluation fixtures, successor minus legacy-Elo mean joint Poisson NLL is `-0.03694662075991243`.

The frozen 22-cluster season-by-identity-league jackknife reports standard error `0.004510654720214589` and nominal interval `[-0.045787504011533024, -0.028105737508291838]`. The interval upper bound remains below zero.

All eleven leave-one-league-out estimates remain negative, and both leave-one-evaluation-season-out estimates remain negative. This is a factual retrospective robustness result. It is not a prospective validation or a production approval criterion.

## Same-fixture calibration

The frozen same-fixture comparison materially improves the recorded calibration summaries relative to legacy Elo on the same 6,903 fixtures:

- home WACE: successor `0.05400574445723991`, Elo `0.17873040706939`;
- home WSCE: successor `0.006452547672985946`, Elo `0.06374291150237581`;
- away WACE: successor `0.04955633485504618`, Elo `0.10568318122555406`;
- away WSCE: successor `0.004728965840436059`, Elo `0.023870877820877004`.

The high-rate tail caveat remains. Sparse successor bins above 2.5 expected goals still overpredict, so this receipt does not claim calibration is solved.

## Fatigue ablation and stability

Removing fatigue slightly worsens evaluation NLL: full successor `2.9171103768278988`, no-fatigue `2.9172918076940935`, giving no-fatigue minus full `+0.0001814308661947095`. The frozen flag `no_fatigue_ablation_better_than_full` is therefore false.

Across all four leave-one-training-season refits, the home fatigue coefficient remains positive and the away fatigue coefficient remains negative. This establishes sign stability under the frozen refits, not causal meaning. `fatigue_pr31_semantic_equivalence` remains `UNPROVEN`.

## Runtime reproducibility observation

An Ubuntu diagnostic rebuilt the exact same coefficients, training NLLs, evaluation NLLs, and ancestry, but two unrounded pre-round convergence-gradient diagnostics differed at approximately machine-precision scale, which changed the canonical PR74 candidate SHA. No robustness result was accepted from that run.

A Windows Server 2025 / CPython 3.12.10 diagnostic reproduced the frozen PR74 candidate byte-for-byte with zero field differences. The accepted real robustness execution therefore used that runtime and retained the PR76 full ancestry gate without relaxation. Cross-runtime canonicalization should be hardened in a separate infrastructure boundary.

## Safety boundary

Historical freshness remains unreconstructed. Elo initialization remains `1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE`. PR31 fatigue semantic equivalence remains unproven.

Every recorded safety flag remains false: no successor approval, expected-goals production approval, score-matrix authorization, probability inference or adjustment, production calibration, pricing, market activation, selection, or betting authorization is created by this receipt.
