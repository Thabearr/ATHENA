"""Real-provider proof for the PR258 research-shadow SportyBet transport seam.

This runner is deliberately transport-scoped. It discovers a current anonymous
SportyBet football event, captures one exact reviewed Total Goals half-line
partition, resolves one semantic intent from a fresh independent event GET, and
then performs the existing anonymous create -> reload share-code round trip.

It proves real provider transport/semantic/native/odds equality only. It does
not create model authority, Phase 6 authority, a production selection, a stake,
or a wager, and it does not claim to be a canonical PR258 model-selection proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import re
from typing import Any

from domain import current_shadow_sportybet_share_code as shadow_transport
from domain import sportybet_current_event_discovery_reconciliation as discovery
from domain import sportybet_live_event_quote_evidence as live
from scripts import sportybet_direct_share_bridge as direct_bridge
from scripts import sportybet_semantic_share_bridge as semantic_bridge


MINIMUM_PROOF_LEAD_SECONDS = 900
MAX_EVENT_DETAIL_ATTEMPTS = 16
MAX_CREATE_ATTEMPTS = 3
_TOTAL_HALF_LINE_RE = re.compile(r"^total=(?:0|[1-9][0-9]*)\.5$", re.ASCII)


class PR258LiveTransportProofError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safety_false(receipt: dict[str, Any], label: str) -> None:
    for field in (
        "sportybet_login_used",
        "sportybet_cookie_used",
        "sportybet_wallet_used",
        "stake_submitted",
        "wager_placed",
    ):
        if receipt.get(field) is not False:
            raise PR258LiveTransportProofError(
                f"{label} safety field {field} did not remain false"
            )


def _total_goals_partition(
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> tuple[live.SportyBetLiveEventSelection, live.SportyBetLiveEventSelection] | None:
    groups: dict[tuple[str, str], list[live.SportyBetLiveEventSelection]] = {}
    for selection in inventory.selections:
        if (
            selection.market_name != "Total Goals"
            or selection.specifier is None
            or _TOTAL_HALF_LINE_RE.fullmatch(selection.specifier) is None
            or not selection.bookable
        ):
            continue
        groups.setdefault((selection.market_id, selection.specifier), []).append(selection)

    for key in sorted(groups):
        rows = groups[key]
        over = [item for item in rows if item.outcome_name.casefold().startswith("over ")]
        under = [item for item in rows if item.outcome_name.casefold().startswith("under ")]
        if len(over) == 1 and len(under) == 1:
            return over[0], under[0]
    return None


def _capture_candidate(
    *,
    event: discovery.SportyBetDiscoveredEvent,
    repository_root: Path,
) -> tuple[live.SportyBetLiveEventQuoteInventory, live.SportyBetLiveEventSelection] | None:
    lead = (event.kickoff_utc - _now()).total_seconds()
    if (
        not event.prematch_bookable_observed
        or not math.isfinite(lead)
        or lead <= MINIMUM_PROOF_LEAD_SECONDS
    ):
        return None
    try:
        directory, _manifest = live.capture_live_event_quote_evidence(
            event_id=event.event_id,
            repository_root=repository_root,
            execute_live_network=True,
        )
        inventory = live.build_live_event_quote_inventory(
            directory,
            repository_root=repository_root,
        )
    except live.SportyBetLiveEventQuoteEvidenceError:
        return None

    partition = _total_goals_partition(inventory)
    if partition is None:
        return None
    # Deterministic single-leg transport proof. The market partition itself is
    # proven exact and two-sided; choosing Over here carries no model authority.
    selected = sorted(partition, key=lambda item: item.outcome_name)[0]
    return inventory, selected


def _semantic_intent(
    inventory: live.SportyBetLiveEventQuoteInventory,
    selection: live.SportyBetLiveEventSelection,
) -> dict[str, Any]:
    return {
        "eventId": inventory.event_id,
        "homeTeamName": inventory.home_team_name,
        "awayTeamName": inventory.away_team_name,
        "marketName": selection.market_name,
        "outcomeName": selection.outcome_name,
        "specifier": selection.specifier,
    }


def _verify_semantic_against_capture(
    *,
    inventory: live.SportyBetLiveEventQuoteInventory,
    captured: live.SportyBetLiveEventSelection,
    selections: tuple[dict[str, str], ...],
    receipt: dict[str, Any],
) -> None:
    _safety_false(receipt, "semantic resolution")
    if receipt.get("caller_supplied_market_outcome_ids_accepted") is not False:
        raise PR258LiveTransportProofError(
            "semantic resolution accepted caller provider-native IDs"
        )
    audits = receipt.get("resolved")
    if type(audits) is not list or len(audits) != 1 or len(selections) != 1:
        raise PR258LiveTransportProofError("semantic resolution count drifted")
    audit = audits[0]
    if type(audit) is not dict:
        raise PR258LiveTransportProofError("semantic audit is invalid")
    expected_selection = {
        "eventId": inventory.event_id,
        "marketId": captured.market_id,
        "outcomeId": captured.outcome_id,
        "specifier": captured.specifier,
    }
    if selections[0] != expected_selection:
        raise PR258LiveTransportProofError(
            "fresh semantic resolution changed provider-native identity"
        )
    exact = {
        "observed_home_team": inventory.home_team_name,
        "observed_away_team": inventory.away_team_name,
        "observed_market_name": captured.market_name,
        "observed_outcome_name": captured.outcome_name,
        "observed_specifier": captured.specifier,
        "marketId": captured.market_id,
        "outcomeId": captured.outcome_id,
    }
    if any(audit.get(key) != value for key, value in exact.items()):
        raise PR258LiveTransportProofError(
            "fresh semantic resolution changed exact provider semantics"
        )
    if Decimal(str(audit.get("odds"))) != Decimal(captured.odds_raw):
        raise PR258LiveTransportProofError(
            "fresh semantic resolution changed captured provider odds"
        )


def _verify_precreate_freshness(
    inventory: live.SportyBetLiveEventQuoteInventory,
) -> None:
    now = _now()
    age = (now - inventory.observed_at).total_seconds()
    lead = (inventory.kickoff_utc - now).total_seconds()
    if not math.isfinite(age) or age < 0 or age > live.MAX_OBSERVATION_AGE_SECONDS:
        raise PR258LiveTransportProofError(
            "captured provider quote became stale before create"
        )
    if not math.isfinite(lead) or lead <= live.MINIMUM_LEAD_SECONDS:
        raise PR258LiveTransportProofError(
            "fixture became live or too close to kickoff before create"
        )


def _verify_roundtrip(
    *,
    inventory: live.SportyBetLiveEventQuoteInventory,
    captured: live.SportyBetLiveEventSelection,
    receipt: dict[str, Any],
) -> None:
    _safety_false(receipt, "direct transport")
    if (
        receipt.get("selection_count") != 1
        or receipt.get("create_accepted_selection_count") != 1
        or receipt.get("load_accepted_selection_count") != 1
        or receipt.get("create_unavailable_outcomes") != 0
        or receipt.get("load_unavailable_outcomes") != 0
        or receipt.get("exact_roundtrip_selection_identity_verified") is not True
    ):
        raise PR258LiveTransportProofError(
            "direct create/reload count, availability, or identity proof failed"
        )
    create = receipt.get("create_accepted_outcomes")
    load_rows = receipt.get("load_accepted_outcomes")
    if type(create) is not list or len(create) != 1 or type(load_rows) is not list or len(load_rows) != 1:
        raise PR258LiveTransportProofError("provider accepted rows are incomplete")
    create_row = shadow_transport._accepted_row(create[0], "create")
    load_row = shadow_transport._accepted_row(load_rows[0], "load")
    if create_row != load_row:
        raise PR258LiveTransportProofError("provider create/reload rows changed")
    expected = {
        "eventId": inventory.event_id,
        "homeTeamName": inventory.home_team_name,
        "awayTeamName": inventory.away_team_name,
        "marketId": captured.market_id,
        "marketName": captured.market_name,
        "specifier": captured.specifier,
        "outcomeId": captured.outcome_id,
        "outcomeName": captured.outcome_name,
    }
    if any(load_row[key] != value for key, value in expected.items()):
        raise PR258LiveTransportProofError(
            "provider reload semantics/native identity differ from captured quote"
        )
    if load_row["odds"] != Decimal(captured.odds_raw):
        raise PR258LiveTransportProofError(
            "provider create/reload odds differ from captured quote"
        )
    if type(receipt.get("shareCode")) is not str or not receipt["shareCode"]:
        raise PR258LiveTransportProofError("verified provider response omitted shareCode")
    if type(receipt.get("shareURL")) is not str or not receipt["shareURL"].startswith("http"):
        raise PR258LiveTransportProofError("verified provider response omitted shareURL")


def run(*, repository_root: Path, output_dir: Path) -> dict[str, Any]:
    if shadow_transport.AUTHORITY["production_selection"] is not False:
        raise PR258LiveTransportProofError(
            "PR258 transport unexpectedly acquired production selection authority"
        )
    if shadow_transport.AUTHORITY["bet"] is not False:
        raise PR258LiveTransportProofError(
            "PR258 transport unexpectedly acquired BET authority"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    discovery_dir, manifest = discovery.capture_current_event_discovery(
        repository_root=repository_root,
        execute_live_network=True,
    )
    candidates = sorted(
        manifest.events,
        key=lambda item: (item.kickoff_utc, item.event_id),
    )

    errors: list[str] = []
    detail_attempts = 0
    create_attempts = 0
    for event in candidates:
        if detail_attempts >= MAX_EVENT_DETAIL_ATTEMPTS:
            break
        candidate = _capture_candidate(event=event, repository_root=repository_root)
        if candidate is None:
            continue
        detail_attempts += 1
        inventory, captured = candidate
        attempt_dir = output_dir / f"attempt-{detail_attempts:02d}-{inventory.event_id.replace(':', '_')}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        intent = semantic_bridge.validate_intents(
            [_semantic_intent(inventory, captured)]
        )
        try:
            selections, semantic_receipt = semantic_bridge.resolve_live_intents(
                intents=intent,
                output_dir=attempt_dir / "semantic-resolution",
                minimum_lead_seconds=live.MINIMUM_LEAD_SECONDS,
                delay_seconds=0.0,
            )
            _verify_semantic_against_capture(
                inventory=inventory,
                captured=captured,
                selections=selections,
                receipt=semantic_receipt,
            )
            _verify_precreate_freshness(inventory)
        except (
            semantic_bridge.SportyBetSemanticShareError,
            PR258LiveTransportProofError,
            ArithmeticError,
            ValueError,
        ) as exc:
            errors.append(f"{inventory.event_id}:semantic:{type(exc).__name__}:{exc}")
            continue

        if create_attempts >= MAX_CREATE_ATTEMPTS:
            break
        create_attempts += 1
        try:
            transport_receipt = direct_bridge.create_and_roundtrip(
                selections=selections,
                output_dir=attempt_dir / "transport-roundtrip",
            )
            _verify_roundtrip(
                inventory=inventory,
                captured=captured,
                receipt=transport_receipt,
            )
        except (direct_bridge.SportyBetDirectShareError, PR258LiveTransportProofError) as exc:
            errors.append(f"{inventory.event_id}:transport:{type(exc).__name__}:{exc}")
            continue

        proof = {
            "schema": "athena-pr258-real-sportybet-transport-proof-v1",
            "proof_scope": "REAL_PROVIDER_SEMANTIC_NATIVE_ODDS_CREATE_RELOAD_TRANSPORT_ONLY",
            "canonical_model_selection_proof": False,
            "production_authority_minted": False,
            "provider": "SportyBet Nigeria",
            "eventId": inventory.event_id,
            "homeTeamName": inventory.home_team_name,
            "awayTeamName": inventory.away_team_name,
            "kickoff_utc": inventory.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "captured_quote_observed_at": inventory.observed_at.isoformat().replace("+00:00", "Z"),
            "captured_inventory_sha256": inventory.canonical_sha256,
            "captured_source_manifest_sha256": inventory.source_manifest_sha256,
            "captured_source_raw_sha256": inventory.source_raw_sha256,
            "marketId": captured.market_id,
            "marketName": captured.market_name,
            "specifier": captured.specifier,
            "outcomeId": captured.outcome_id,
            "outcomeName": captured.outcome_name,
            "captured_decimal_odds": captured.odds_raw,
            "semantic_resolution_receipt": semantic_receipt,
            "transport_receipt": transport_receipt,
            "discovery_manifest_sha256": manifest.canonical_sha256,
            "discovery_evidence_directory": str(discovery_dir.relative_to(repository_root)),
            "shareCode": transport_receipt["shareCode"],
            "shareURL": transport_receipt["shareURL"],
            "combined_odds": transport_receipt["combined_odds"],
            "exact_semantic_native_odds_equality_verified": True,
            "exact_create_reload_verified": True,
            "authority": dict(shadow_transport.AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }
        (output_dir / "pr258-live-transport-proof.json").write_bytes(_canonical(proof))
        return proof

    detail = "; ".join(errors[-8:]) if errors else "no exact Total Goals half-line candidate found"
    raise PR258LiveTransportProofError(
        f"real provider proof could not complete within bounded attempts: {detail}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    repository_root = args.repository_root.resolve(strict=True)
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repository_root / output_dir
    proof = run(repository_root=repository_root, output_dir=output_dir)
    print(
        json.dumps(
            {
                "status": "PR258_REAL_PROVIDER_TRANSPORT_PROOF_VERIFIED",
                "eventId": proof["eventId"],
                "shareCode": proof["shareCode"],
                "selection_count": 1,
                "exact_semantic_native_odds_equality_verified": True,
                "exact_create_reload_verified": True,
                "production_authority_minted": False,
                "wager_placed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
