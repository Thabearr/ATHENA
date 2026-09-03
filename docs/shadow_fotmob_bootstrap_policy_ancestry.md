# Current Shadow FotMob bootstrap policy ancestry

Operational proof run `33775143494` on exact main `73eae73e2047930d2eb42b76e3ec4f91cf281fd3` exposed a fail-closed ancestry mismatch: the current Shadow source issuer creates fixture bootstraps under the reviewed Shadow V2 1800-second lead policy, while the UTC-native Shadow prediction replay still replays only the historical PR243 3600-second policy before comparing the review-bundle hash.

This repair is limited to replaying the exact reviewed fixture-review policy already proven by the supplied bootstrap ancestry. Historical PR243 bootstraps remain on PR243; exact Shadow V2 bootstraps may replay Shadow V2; unknown or mixed reviewer provenance fails closed. No production model, probability, pricing, selection, SportyBet execution, BET, stake, wallet, login, cookie, or wager authority changes.
