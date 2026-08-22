# SportyBet Parse booking-code bridge

## Purpose

This boundary lets ATHENA use a repository secret named `PARSE_API_KEY` to call an independent Parse REST wrapper over public SportyBet Nigeria data. It is intentionally separate from the older direct SportyBet Lite source boundary.

The immediate Saturday workflow is two-stage:

1. discover today's SportyBet Nigeria events and exact provider-native markets for the 20 provisional target fixtures;
2. only after exact event/market/outcome identities are reviewed, submit those exact selections to the booking endpoint and require every requested outcome to be accepted before surfacing the returned share code.

## Security boundary

`PARSE_API_KEY` is read only from the environment. The bridge never writes it to a file, request URL, receipt, artifact, stdout, or git-tracked content. No SportyBet login, password, cookie, PIN, wallet, account ID, stake, or payment credential is accepted.

## External-service boundary

Parse is not an official SportyBet developer API. It is an independent managed wrapper. The bridge therefore records the intermediary explicitly and preserves the returned JSON as evidence. External success never silently upgrades ATHENA model or BET authority.

Discovery uses the Parse SportyBet API endpoint family that exposes `get_upcoming_events` and `get_event_odds`. Booking-code creation uses the separately documented SportyBet Nigeria `book_bet` endpoint, which accepts provider-native `eventId`, `marketId`, `outcomeId`, and optional `specifier` values and returns a share code/URL without placing a wager.

## Fixture matching

The tracked Saturday target file contains explicit reviewed name aliases. Matching is exact membership only. There is no fuzzy matching, substring matching, accent stripping, or guessed home/away swap. A missing or ambiguous fixture stays blocked.

## Booking gate

`book_exact_selections(...)` accepts only provider-native fields:

- `eventId`
- `marketId`
- `outcomeId`
- optional `specifier`

The bridge requires at most one selection per event, a non-empty returned `shareCode`, an HTTPS `shareURL`, zero `unavailableOutcomes`, and exactly as many accepted outcomes as requested selections. Otherwise it fails closed and does not claim a valid booking code.

## Current authority

The first PR run is probe-only. It inventories the exact live SportyBet event and market identities required for the 20-fold but does not call `book_bet` yet.

The resulting evidence does not by itself authorize model probabilities, value, staking, wager placement, or a `BET` classification. A generated booking code is only a shareable SportyBet betslip representation of exact selections; it is not evidence that a wager was placed.
