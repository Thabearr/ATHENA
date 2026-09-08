# Current Shadow SportyBet team-label compatibility — run 126

This narrow compatibility review is grounded in the exact anonymous provider source diagnostic captured by workflow run `34243048761`, artifact `10062892966`, artifact SHA-256 `bbc5434425443b38a20d0807cc3e85a269a02a446ff229ea7025d28b4cd0dea4`.

Across 205 active provider tournaments, exactly one tournament response was rejected by the reviewed parser. The retained raw response SHA-256 is `d25423e8dfea8d8d49b15041338bb7d90e546a918471653afe5bfb5449ee0f54` for `sr:category:365` / `sr:tournament:27396`. Its sole rejected row is event `sr:match:74170884`: `homeTeamName` is exactly `"Comunicaciones FC "` with one trailing ASCII space and `awayTeamName` is `"CD Marquense"`.

The fix remains exact-tuple-only. It does not authorize generic trimming, leading whitespace, repeated trailing whitespace, tabs, fuzzy matching, fixture reversal, pricing, selection, login, wallet, staking, BET, or wagering. Raw provider bytes remain authoritative evidence.
