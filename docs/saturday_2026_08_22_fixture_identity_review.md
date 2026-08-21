# Saturday 2026-08-22 explicit fixture-identity review

## Purpose

This boundary takes the exact Saturday source evidence already frozen by PR #199 and the source-qualified competition-review policy merged by PR #200, then records explicit PR #41-style review decisions for the exact 50-fixture first-pass pool.

It is an **identity-only review**. Approval means the exact FotMob source match ID, home/away names, competition label and kickoff may proceed to the later reviewed Fixture Catalog handoff path. It does not say that a fixture is a good bet, that its current team news is fresh, that a model is reliable for it, or that any SportyBet price exists.

## Frozen ancestry

The review replays the exact current PR #199 source evidence:

- source PR head: `b879b2140d0bc3fb64fa8fec4c73c735240a3b41`;
- capture run: `32455713912`;
- artifact: `9437181220`;
- artifact digest: `sha256:360aac588f049fe6b0437c43e060b317edd12aaf4672db93ebe2fca42de00589`;
- raw SHA-256: `a22e449fd7c59bee011e71230e345c733e1322311f6a9481812a23b4dcae2dc8`;
- manifest SHA-256: `64fb631d4889dbf360af4fb988656aba579b67ca5340578df1056dc5324dc09e`;
- rebuilt PR #40 candidate-bundle SHA-256: `53b48ae1beabc10b638ad20f21e4807f78f0a3879ff8a21fd19a2da538a1ba3d`.

The explicit decision ledger is:

`evidence/saturday_2026_08_22_fixture_identity_review_decisions.json`

Its exact SHA-256 is:

`7555b821b126a9218f9c9ec94f812eba9ad4a20440bdcd43626dc5806d62b563`

Every decision names one exact capture-manifest SHA, source match ID and candidate SHA-256. There is no approve-all wildcard, fuzzy match, competition substring, or automatic review rule.

## Exact review scope

The Saturday source has 670 candidates. PR #200's source-qualified competition review produces exactly 50 first-pass fixtures. The explicit ledger approves exactly those 50 and leaves the other 620 unreviewed.

| Review rank | Competition | Explicit identity approvals |
|---:|---|---:|
| 1 | Premier League | 5 |
| 2 | La Liga | 3 |
| 3 | Serie A | 4 |
| 4 | Bundesliga | 0 |
| 5 | Ligue 1 | 5 |
| 6 | Primeira Liga | 3 |
| 7 | Süper Lig | 3 |
| 8 | Eredivisie | 4 |
| 9 | DFB-Pokal | 11 |
| 10 | Belgian Pro League | 3 |
| 11 | Scottish Premiership | 6 |
| 12 | Greek Super League | 3 |

The current capture contains no FA Cup, Copa del Rey, Coppa Italia or Coupe de France fixtures. Their shared major-cup review rank remains part of the reusable PR #200 policy but creates no phantom Saturday decisions.

## Replay contract

`scripts/verify_saturday_2026_08_22_fixture_identity_review.py` does not trust the serialized review bundle. It:

1. rechecks the exact PR #199 raw and manifest bytes;
2. rebuilds the PR #40 670-candidate bundle and requires byte equality with the frozen artifact;
3. loads the strict existing PR #41 decision-ledger format;
4. requires the ledger SHA and candidate-bundle SHA to match the frozen values;
5. rebuilds the current PR #200 Saturday competition-review universe;
6. requires the decision source-match IDs to equal exactly the 50 source-qualified priority identities;
7. requires every decision to be an explicit `APPROVED` identity decision with the frozen reviewer reference/timestamp and matching rank/competition note;
8. reruns `build_fotmob_fixture_candidate_review_bundle`, including duplicate/conflict/string blockers;
9. requires 50 approvals, 0 rejections, 620 unreviewed candidates and 0 review blockers;
10. writes a canonical review bundle and receipt for hosted inspection.

## Authority boundary

This PR records explicit fixture-identity review only. It does **not** perform or authorize:

- automatic candidate review;
- global source qualification;
- Fixture Catalog admission/promotion;
- refreshed lineup/injury/player context;
- model features or probabilities;
- calibration or model-league reliability claims;
- SportyBet event reconciliation;
- fresh bookmaker pricing;
- value calculation;
- selection or accumulator acceptance;
- BET or bookmaker execution.

The 50 therefore become a reviewed identity pool, not 50 betting candidates.

## Next boundary

After this review is merged, the next smallest safe step is to build and admit the exact reviewed Fixture Catalog identities from these 50 decisions while preserving the same source hashes and keeping Fixture Intelligence/model/pricing/selection/BET authority separate. Only after identity admission should the live Saturday path refresh fixture/player intelligence and begin football/model elimination toward the requested 20.
