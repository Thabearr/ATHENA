# PR194 scope and acceptance contract

This PR establishes one boundary only: exact PR193 real player-context semantics -> exact PR190 team-strength feature resolutions.

Acceptance requires all of the following:

- exact PR192 evidence is replayed through the PR193 builder;
- no caller-constructed PR193 wrapper is trusted;
- only `home_unavailable_player_count = 1` and `away_unavailable_player_count = 5` are AVAILABLE;
- aggregate lineup state remains UNVERIFIED because bench evidence is absent;
- bench count is never inferred as zero;
- numeric position codes are not mapped to position groups;
- market value is not used as player quality;
- no historical player/schedule evidence is invented;
- source freshness ends at PR193 `CLASSIFIED_AT`;
- no xG/probability adjustment exists;
- pricing, selection, production approval and BET authority remain false;
- hosted deterministic Tests and the dedicated exact real-evidence replay are green on the exact reviewed head.
