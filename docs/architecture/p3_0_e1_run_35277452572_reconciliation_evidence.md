# P3.0-E1 run 35277452572 reconciliation compatibility evidence

This receipt records bounded compatibility review only. Immutable source evidence
remains the retained `p3-0-comparison-evidence-source-diagnostics` artifact
`10520479660` from failed P3.0-E1 run `35277452572`, executed at
`d0ee4a341958ac80ecdfacb37e3e129b3051c28d`.

- Artifact ZIP SHA-256: `7e97785ce12d1158455fe49138376cfffa7057b294e84c8ff7316479d5949a8c`
- Retained FotMob 20260918 raw SHA-256: `0366592e6b227956d222d67de43031da82de9e4cc063f1529c01db85de722c9d`
- The compatibility projection is not source evidence and does not replace the
  artifact, its raw captures, or their manifest lineage.

## Admitted exact identity tuples

All rows retain exact UTC kickoff and home/away orientation. Team labels are
opaque strings; each wrapper/fixture is revalidated separately.

| SportyBet event | FotMob fixture | UTC kickoff | FotMob identity | SportyBet identity |
| --- | --- | --- | --- | --- |
| `sr:match:69343126` | `5204254` | `2026-09-18T11:00:00Z` | KAZ/225, `Premier League`; 2128 `Okzhetpes Kokshetau`, 1614087 `Zhenis` | 5359 `FC Okzhetpes`, 5363 `FC Zhenis` |
| `sr:match:69456602` | `5207231` | `2026-09-18T10:00:00Z` | CHN/9137, `China League`; 1282988 `Yanbian Longding`, 1623678 `Guangdong GZ-Power` | 793018 `Yanbian Longding`, 1110267 `Guandong GZ-Power FC` |
| `sr:match:69456604` | `5207232` | `2026-09-18T11:00:00Z` | CHN/9137, `China League`; 1617860 `Dalian K'un City`, 585867 `Ningbo Professional` | 1110197 `Dalian Kun City`, 252173 `Ningbo Professional FC` |

The explicit V2 alias rows are the five non-literal display pairs in those
tuples. `Yanbian Longding` is literal and has no alias row. The V3 stable-ID
recovery may bind the previously unbound China provider tournament only after
both exact oriented team identities are confirmed; no global `China League` /
`China League 1` normalization is introduced.

## Intentionally not admitted

The retained evidence does not prove a counterpart for:

`sr:match:111111114209600`, `sr:match:111111114209602`,
`sr:match:111111114408558`, `sr:match:111111114427068`,
`sr:match:111111114432617`, `sr:match:111111114459159`, and
`sr:match:68849770`.

Some have same-kickoff unrelated FotMob rows; that is not fixture identity.
No fuzzy matching, generic suffix stripping, punctuation normalization,
home/away reversal, or kickoff tolerance was added.

## Authority and next gate

This changes research-Shadow reconciliation compatibility only. Model,
probability, Price-All, Router ranking, Portfolio, selection, delivery,
authentication, cookies, wallet, staking, and wager authority remain unchanged.
The retained diagnostics artifact remains uploaded by the P3.0-E1 workflow and
can be inspected offline with `scripts/analyze_p3_0_e1_source_diagnostics.py`.

This continuity work does not satisfy P3.0 and does not start P3.1.
