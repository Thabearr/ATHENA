# PR69 Formal Operational-Invariance Qualification Protocol

## Boundary

This PR pre-registers the second route already allowed by the frozen PR122 source-local time-basis protocol after PR132 established that the direct primary-source route remains unresolved.

It is **result-free and reference-only**. It does not execute an invariance assessment, infer a timezone or offset, normalize historical source bytes, inspect or compare FotMob candidate rows, authorize PR80 input, train a model, calculate probabilities, inspect prices, make selections, or authorize BET.

Protocol state:

`PRE_REGISTERED_NOT_EXECUTED_PR69_FORMAL_OPERATIONAL_INVARIANCE_UNQUALIFIED`

Next boundary:

`EXECUTE_REVIEWED_PR69_FORMAL_OPERATIONAL_INVARIANCE_QUALIFICATION`

## Why this boundary is reference-only

PR120's gate order is explicit:

1. resolve the PR69 source-local reference basis **or prove source-independent invariance**;
2. only then assess whether the FotMob `Europe/Oslo` naive representation is admissible;
3. only after that perform FotMob-vs-reference strict-prior, ordering, rest-day and fatigue equivalence checks.

Therefore this protocol may prove only that PR69's own pre-match operations are independent of the unresolved reference-clock transformation. It cannot inspect the 21,326 PR119 FotMob candidate rows or use their agreement/disagreement to obtain the reference result. Candidate semantic equivalence remains a later PR120/PR121-lineage boundary.

## Exact ancestry

The protocol is stacked on the exact approved PR132 head:

`f275a7404bbb74ade6ba29c4ec2d7f52d3e21abf`

It revalidates:

- PR132 semantic qualification receipt: `cbdf0bbf9e31d44e0d00125bd10d714272ac6046386cf52f1d9d27b3ab84bb8d` / `5,422` bytes
- PR132 checked-in receipt blob: `adc34350074a8cdcd447089e9d64727081a7c3b2`
- PR132 qualification implementation blob: `b9a4b109157fa704e65b0aba5c4816e178a3c168`
- PR122 source-local time-basis protocol: `d3bf061ade81bb1b60f38e98f5fa3c8c21ba5bf6652879f2cc19e151b53aee4a` / `6,983` bytes
- PR122 implementation blob: `712ce12157ade725a60b24c4557600fc7b06e504`
- PR120 FotMob/PR80 time-operation protocol: `a938ee4ea45c427c5396fe063af4efd2341a9c8e8ffccc1105aa7bdffdbb2918` / `5,242` bytes
- PR120 implementation blob: `e07616e99c0beaf2a95bcaec96d02616b21c378f`
- PR80 constructor implementation blob: `9135f056d036fd0207a3daead2599ac2520274be`

PR120 and PR80 are pinned here only to freeze the definitions of the time-sensitive operations that a later reference proof must preserve. Their FotMob candidate observations/results are not execution evidence for this boundary.

Frozen proof scope is exactly the PR69 reference corpus:

- 66 football-data.co.uk files
- 10,006,877 source bytes
- 21,226 fixtures
- seasons 2020-21 through 2025-26
- the existing eleven historical/model families only; this is **not** ATHENA's full competition universe
- FotMob candidate rows in scope: **false**
- FotMob candidate time basis assessed: **false**

## Why the proof has two stages

The phrase “formal invariance” must not become a way to assume the missing timezone indirectly.

A later execution must first prove an **admissible reference-transformation family**: the exact set or bounded schedule of clock transformations that primary/provenanced evidence permits over every relevant PR69 timestamp and effective period. Only after that family is established may ATHENA ask whether the PR69 replay operations are invariant under every transformation in it.

If no transformation family can be proven from admissible evidence, execution fails at the assumption gate with `BLOCKED_INVARIANCE_ASSUMPTIONS_UNPROVEN`. It may not invent a plausible ±1 hour, ±2 hour, DST, UK, country, league, venue, or IANA-zone envelope merely because such a rule seems reasonable.

### Examples of admissible representations

A future evidence bundle may establish, for example:

- one globally additive offset;
- a finite piecewise offset schedule whose transitions and effective periods are proven;
- a named-zone rule converted into its exact offset schedule for the frozen PR69 timestamps;
- another deterministic source-defined civil-time mapping.

These are **representation shapes, not assumptions supplied by this protocol**. Every member, bound, transition and effective period used in execution must itself be evidenced.

## Required operation-level proof

For **every PR69 row and every transformation in the proven admissible reference family**, a later execution must prove all of the frozen PR122 time-sensitive operations whose definitions are pinned by PR120/PR80:

1. strict-prior membership;
2. form ordering and exact fixture-identifier tiebreak behavior;
3. Elo ordering and exact fixture-identifier tiebreak behavior;
4. most-recent prior fixture selection per source-scoped team;
5. the integer `.days` component of each home and away datetime delta;
6. home-rest-days minus away-rest-days;
7. the resulting fatigue bucket.

This distinction matters because chronology can remain ordered while fatigue changes. A time-varying offset or daylight-saving transition can leave two fixtures in the same order yet move a datetime difference across an integer-day boundary. Therefore:

- zero ordering disagreements is not sufficient;
- equal observed form/Elo/fatigue outputs is not sufficient;
- aggregate agreement counts are not sufficient;
- a global additive offset may cancel exactly only **after** the evidence has proven that the allowed reference family really is globally additive.

For bounded/time-varying transformations, the machine-checkable proof must ensure that ordering intervals cannot cross equality except where the frozen fixture-ID tiebreak already resolves an exact tie, and that every allowed transformed datetime delta retains the same integer-day component, rest difference and fatigue bucket.

## Execution accounting

A later execution must report at minimum:

- PR69 reference rows considered;
- PR69 target-row boundaries considered;
- PASS / FAIL / NOT_REACHED for every operation gate;
- a concrete counterexample identity for every failed gate;
- the exact assumption/evidence bundle used to define the reference-transformation family.

It must explicitly prove that no FotMob candidate row was inspected to derive the reference invariance result.

Raw PR69 source date/time text remains immutable. The invariance execution cannot train/tune the successor model or use result quality to choose a convenient clock interpretation.

## Result vocabulary

The execution may use only statuses already admitted by PR122:

- `QUALIFIED_FORMAL_OPERATIONAL_INVARIANCE_WITHOUT_NAMED_TIMEZONE`
- `BLOCKED_INVARIANCE_ASSUMPTIONS_UNPROVEN`
- `BLOCKED_ANCESTRY_OR_SOURCE_CORPUS_MISMATCH`
- `BLOCKED_TIME_BASIS_SCOPE_OR_EFFECTIVE_PERIOD_AMBIGUOUS`

No post-result status vocabulary may be invented to rescue a failed proof.

## Parallel successor work

A separately reviewed FotMob-native UTC successor path may progress in parallel, but it cannot be counted as this invariance proof, cannot resolve PR69, and cannot retroactively authorize PR80 source-local parity.

If the PR69 invariance execution later qualifies, the existing PR120 semantic-equivalence lineage may resume from its reference gate and separately assess FotMob candidate-time admissibility and operation-level equivalence.

## Safety

Every authority remains false at pre-registration:

- PR69 source-local time basis resolution
- source-local semantic equivalence
- PR80 constructor input
- successor approval
- model training / expected-goals approval or production
- score matrix / probability inference or adjustment
- calibration for production
- pricing / market activation / selection
- production approval / BET

## Canonical protocol identity

SHA-256:

`d4cacdc85f8d2be5746853a89c00fe8d6521075234a9009469a6385f346be513`

Canonical size:

`5,841` bytes
