# SportyBet official website time semantics

## Purpose

PR #156 can derive a machine event-header candidate from the exact preserved SportyBet event-detail HTML that also anchors the provider-native odds inventory. It deliberately leaves the displayed clock's timezone and year unproven.

This boundary addresses only the timezone-semantics half of that gap. It adds an **offline, user-controlled evidence qualifier** for SportyBet Nigeria's official Terms & Conditions page. ATHENA itself performs no SportyBet network request.

The reviewed source identity is exactly:

`https://www.sportybet.com/ng/help?nav=terms-and-conditions`

The qualifier succeeds only when the preserved visible provider text contains the exact global rule that website times relate to **GMT unless stated otherwise**. The exact statement text is frozen by SHA-256 in the protocol and code.

## Why this boundary exists

Search/discovery can tell us where an official statement appears, but ATHENA's evidence rules do not allow discovery output to silently become trusted provider evidence. The source must instead cross a reviewed preservation boundary.

The workflow is therefore:

`human opens official provider page -> human saves exact HTML -> ATHENA offline preservation -> exact visible-text qualification -> canonical qualification artifact`

No browser automation, credentials, cookies, proxying, anti-bot bypass, or SportyBet network acquisition is introduced.

## Exact semantics proved by a successful qualification

A successful qualification establishes only these global provider semantics:

- source role: `OFFICIAL_PROVIDER_TERMS`;
- global website time-zone label: `GMT`;
- civil offset represented by the rule: `0` seconds;
- qualifier status: `QUALIFIED_GLOBAL_WEBSITE_TIME_BASIS`;
- the provider rule contains an explicit exception: **unless stated otherwise**.

The evidence is bound to:

- exact source URL;
- exact user-attested observation timestamp;
- exact import timestamp;
- raw HTML SHA-256 and size;
- exact semantics-statement SHA-256;
- exact visible occurrence count;
- canonical qualification bytes.

Repeated identical rendered copies are allowed and counted. Missing, altered-case, weakened, conflicting, or non-GMT versions fail closed. Script/style/non-rendered text cannot satisfy the visible-text requirement because extraction reuses the reviewed PR #156 rendered-text boundary.

## What this still does **not** prove

The official global rule says GMT **unless stated otherwise**. Therefore this PR does not automatically apply GMT to every SportyBet event page.

Before a specific PR #156 event-header clock can be used as GMT, a later boundary must revalidate the exact event-detail HTML and prove that no event-local time-zone override changes the global rule for that displayed clock.

The event year also remains unproven. This PR does not invent a year from the user observation time, current calendar, weekday, competition, FotMob candidate, or any other heuristic.

Accordingly:

- `event_local_override_check_required = true`;
- `event_application_status = REQUIRES_EVENT_LOCAL_OVERRIDE_CHECK`;
- `event_year_proven = false`;
- `specific_event_time_basis_authorized = false` in the frozen protocol.

## User-controlled import command

After a human saves the exact official Terms & Conditions page as UTF-8 HTML, the offline command is:

```text
python -m scripts.import_sportybet_official_time_semantics \
  --html-file <saved-terms-page.html> \
  --source-url "https://www.sportybet.com/ng/help?nav=terms-and-conditions" \
  --observed-at <timezone-aware-ISO-8601> \
  --attestation "I_MANUALLY_OBSERVED_AND_EXPORTED_THIS_OFFICIAL_PROVIDER_PAGE"
```

The command writes only under:

`.cache/athena-research/sportybet-official-time-semantics/`

Evidence directories are content/observation bound, canonical, replay-verifiable, idempotent only for the exact same qualification and raw bytes, and no-overwrite on conflicting content.

## Safety state

This boundary does not change `BettingService` and does not authorize:

- ATHENA SportyBet network acquisition;
- provider quote timestamps or snapshots;
- event-specific timezone application;
- event year inference;
- production SportyBet ↔ FotMob reconciliation;
- bookmaker equivalence;
- canonical market mapping;
- fresh-price claims;
- pricing/value integration;
- model integration;
- selection;
- ACCA/slip construction;
- SportyBet booking-code generation;
- SportyBet execution;
- `BET`.

Every corresponding safety field remains exactly `false`.

## Product direction

The SportyBet product path remains:

`provider event + native odds -> reviewed fixture identity -> exact market equivalence -> fresh price -> calibrated model/value + fragility -> selection -> ACCA/slip -> SportyBet booking code`

This PR only strengthens the event-identity evidence needed near the beginning of that chain.

## Next boundary

After this qualifier is merged, the next narrow step should combine:

1. a genuine preserved official Terms page that successfully qualifies the global GMT rule; and
2. a genuine preserved PR #156 event-detail page;

then perform an exact event-local override check. If the event page does not state a different basis, ATHENA can qualify its machine-derived `DD/MM Weekday HH:MM` clock as GMT while still keeping the **year unknown**.

Only after that should we revisit exact SportyBet ↔ FotMob reconciliation using the provider's partial calendar identity without fuzzy names or time tolerance.
