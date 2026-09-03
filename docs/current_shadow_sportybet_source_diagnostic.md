# Current Shadow SportyBet source diagnostic

This is an evidence-only diagnostic boundary for the current research Shadow lane.
It exists because exact-final-main run `33740669993` reached SportyBet catalog
fanout and returned the fail-closed source reason
`home_team_name must be an exact non-empty trimmed string`, while the existing
successful-capture path could not retain the failing tournament response before
parser rejection.

The diagnostic uses the same anonymous provider catalogue and tournament request
contracts as the reviewed current Shadow fanout boundary. It writes every acquired
raw response before invoking the reviewed parser, records exact SHA-256 ancestry,
and records bounded source fields for rows rejected by the reviewed event parser.
Those fields are evidence only and are never trimmed, normalized, aliased, reversed,
or promoted to fixture identity.

All diagnostic authority is false. In particular, it grants no fixture
reconciliation, canonical market mapping, Price-all, Router, Portfolio, share-code
transport, login, cookies, wallet, staking, BET, or wager authority.

Hosted invocation is intentionally separate from the normal Shadow command:

`/athena-shadow-source-diagnostic`

The command is accepted only from the repository owner on control issue `#276`.
The resulting artifact is named `current-shadow-sportybet-source-diagnostic`.
A later compatibility change may be reviewed only against exact evidence produced
by this boundary; this diagnostic itself does not change the reviewed parser.
