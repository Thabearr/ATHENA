"""Current Shadow-only tolerant replay of exact SportyBet live-event quote evidence.

The reviewed direct-event capture remains authoritative and immutable.  This
adapter changes only row-level parsing inside Current Shadow: one malformed
provider market/outcome that ATHENA cannot interpret no longer invalidates the
entire otherwise-valid event inventory.  Invalid rows are omitted, never
normalized, repaired, guessed, or granted semantic authority.  Event identity,
kickoff, raw/manifest hashes, timestamps and all retained quote values remain
the exact reviewed direct-provider evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from domain import sportybet_live_event_quote_evidence as live


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_ROW_LOCAL_DIRECT_QUOTE_PARSE_V1"
POLICY_BASIS = (
    "EXACT_DIRECT_EVENT_RAW_MANIFEST_REPLAY_"
    "OMIT_ONLY_INDIVIDUAL_MALFORMED_PROVIDER_MARKET_OR_OUTCOME_ROWS_"
    "NO_NORMALIZATION_NO_REPAIR_NO_INFERENCE_NO_SYNTHETIC_PRICE"
)


def policy_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "policy_basis": POLICY_BASIS,
        "raw_event_mutation_performed": False,
        "provider_value_normalization_performed": False,
        "synthetic_quote_performed": False,
        "production_authority": False,
        "selection_authority": False,
        "sportybet_execution_authority": False,
        "bet_authority": False,
        "wager_placed": False,
    }


def build_shadow_live_event_quote_inventory(
    evidence_directory: Path, *, repository_root: Path
) -> live.SportyBetLiveEventQuoteInventory:
    """Replay one exact capture while containing malformed provider rows locally."""

    manifest = live.verify_live_event_quote_evidence(
        evidence_directory, repository_root=repository_root
    )
    raw = live._read_regular(
        Path(evidence_directory) / live.RAW_FILENAME,
        maximum=live.MAX_RESPONSE_BYTES,
        label="SportyBet live event raw response",
    )
    event = live._event_object(live.strict_json_loads(raw), manifest.event_id)

    selections: list[live.SportyBetLiveEventSelection] = []
    for market in event.get("markets"):
        if type(market) is not dict:
            continue
        try:
            market_native = market.get("id", market.get("marketId"))
            if market_native is None:
                continue
            market_id = live._native_id(market_native, "provider market ID")
            market_name = live._market_name(market)
            specifier = live._specifier(market.get("specifier"))
        except live.SportyBetLiveEventQuoteEvidenceError:
            # Preserve the raw row in evidence, but do not let one malformed
            # provider market destroy valid unrelated selections in this event.
            continue

        outcomes = market.get("outcomes")
        if type(outcomes) is not list:
            continue
        for outcome in outcomes:
            if type(outcome) is not dict:
                continue
            try:
                outcome_native = outcome.get("id", outcome.get("outcomeId"))
                if outcome_native is None:
                    continue
                bookable, bookability_basis = live._outcome_bookability(outcome)
                odds_raw, decimal_odds = live._odds(outcome.get("odds"))
                outcome_id = live._native_id(
                    outcome_native, "provider outcome ID"
                )
                outcome_name = live._outcome_name(outcome)
            except live.SportyBetLiveEventQuoteEvidenceError:
                # A malformed outcome is unavailable.  Nothing is trimmed,
                # defaulted or synthesized.
                continue
            selections.append(
                live.SportyBetLiveEventSelection(
                    event_id=manifest.event_id,
                    market_id=market_id,
                    market_name=market_name,
                    specifier=specifier,
                    outcome_id=outcome_id,
                    outcome_name=outcome_name,
                    bookable=bookable,
                    bookability_basis=bookability_basis,
                    odds_raw=odds_raw,
                    odds_decimal=decimal_odds,
                )
            )

    if not selections:
        raise live.SportyBetLiveEventQuoteEvidenceError(
            "current event contains no valid priced selections after row-local replay"
        )

    ordered = tuple(
        sorted(
            selections,
            key=lambda item: (
                item.market_id,
                "" if item.specifier is None else item.specifier,
                item.outcome_id,
            ),
        )
    )
    return live.SportyBetLiveEventQuoteInventory(
        dataset_name=live.INVENTORY_DATASET_NAME,
        event_id=manifest.event_id,
        home_team_name=live._exact_text(
            event.get("homeTeamName"), "provider home team"
        ),
        away_team_name=live._exact_text(
            event.get("awayTeamName"), "provider away team"
        ),
        kickoff_utc=live._kickoff(event),
        booking_status=(
            None
            if event.get("bookingStatus") is None
            else str(event.get("bookingStatus"))
        ),
        event_status=event.get("status"),
        match_status=(
            None if event.get("matchStatus") is None else str(event.get("matchStatus"))
        ),
        prematch_bookable_observed=live._event_is_prematch_bookable(event),
        observed_at=manifest.observed_at,
        observation_authority=live.OBSERVATION_AUTHORITY,
        provider_quote_at=None,
        provider_snapshot_id=None,
        source_manifest_sha256=live.manifest_sha256(manifest),
        source_raw_sha256=manifest.raw_sha256,
        selections=ordered,
    )


__all__ = [
    "POLICY_BASIS",
    "POLICY_ID",
    "SCHEMA_VERSION",
    "build_shadow_live_event_quote_inventory",
    "policy_summary",
]
