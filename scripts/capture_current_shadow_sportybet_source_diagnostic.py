"""Bounded evidence-only capture for current SportyBet fanout parse failures.

This diagnostic never reconciles fixtures or grants model, pricing, selection,
transport, staking, BET, or wager authority. It preserves exact anonymous
provider responses before the reviewed fanout parser is asked to interpret
those bytes, so a parser failure cannot erase the live evidence needed for a
subsequent compatibility review.
"""
from __future__ import annotations

import argparse
from datetime import timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-sportybet-source-diagnostic-v1"
COMMAND = "/athena-shadow-source-diagnostic"
AUTHORITY = {
    "fixture_reconciliation": False,
    "canonical_market_mapping": False,
    "price_all": False,
    "market_router": False,
    "portfolio_optimization": False,
    "final_selection": False,
    "share_code_transport": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
}


class SportyBetSourceDiagnosticError(RuntimeError):
    """Raised when bounded source diagnostic evidence cannot be retained."""


def _canonical(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise SportyBetSourceDiagnosticError("diagnostic serialization failed") from exc


def _write_exclusive(path: Path, content: bytes) -> None:
    if type(content) is not bytes or not content:
        raise SportyBetSourceDiagnosticError(
            "diagnostic evidence must be non-empty bytes"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        fanout.base._sync_directory(path.parent)
    except FileExistsError as exc:
        raise SportyBetSourceDiagnosticError(
            f"refusing to overwrite diagnostic evidence {path.name}"
        ) from exc
    except OSError as exc:
        raise SportyBetSourceDiagnosticError(
            f"could not durably write diagnostic evidence {path.name}"
        ) from exc


def _observed_text(value: Any) -> str:
    try:
        text = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except Exception as exc:
        raise SportyBetSourceDiagnosticError(
            "provider observation time is invalid"
        ) from exc
    return text.replace("+00:00", "Z")


def _row_failure_excerpt(
    row: dict[str, Any],
    *,
    row_index: int,
    raw_sha256: str,
    observed_at: Any,
) -> dict[str, Any] | None:
    try:
        fanout.reviewed._event_from_mapping(
            row,
            inherited_competition=None,
            page_num=1,
            raw_sha256=raw_sha256,
            observed_at=observed_at,
        )
    except fanout.reviewed.SportyBetCurrentEventDiscoveryError as exc:
        return {
            "row_index": row_index,
            "eventId": row.get("eventId"),
            "homeTeamName": row.get("homeTeamName"),
            "awayTeamName": row.get("awayTeamName"),
            "bookingStatus": row.get("bookingStatus"),
            "status": row.get("status"),
            "matchStatus": row.get("matchStatus"),
            "setScore": row.get("setScore"),
            "playedSeconds": row.get("playedSeconds"),
            "estimateStartTime": row.get("estimateStartTime"),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "fixture_reconciliation_authorized": False,
        }
    return None


def _diagnose_tournament_rows(
    raw: bytes,
    *,
    raw_sha256: str,
    observed_at: Any,
) -> tuple[dict[str, Any], ...]:
    try:
        payload = fanout.live.strict_json_loads(raw)
    except fanout.live.SportyBetLiveEventQuoteEvidenceError:
        return ()
    if type(payload) is not dict or type(payload.get("data")) is not list:
        return ()
    failures: list[dict[str, Any]] = []
    for index, row in enumerate(payload["data"]):
        if type(row) is not dict:
            failures.append(
                {
                    "row_index": index,
                    "error_type": "NON_OBJECT_EVENT_ROW",
                    "error_message": "fanout event row must be object",
                    "fixture_reconciliation_authorized": False,
                }
            )
            continue
        failure = _row_failure_excerpt(
            row,
            row_index=index,
            raw_sha256=raw_sha256,
            observed_at=observed_at,
        )
        if failure is not None:
            failures.append(failure)
    return tuple(failures)


def capture_source_diagnostic(*, output_dir: Path) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise SportyBetSourceDiagnosticError(
            "diagnostic output directory already exists"
        )
    output.mkdir(parents=True, exist_ok=False)
    fanout.base._sync_directory(output.parent)

    catalog_raw, catalog_observed_at = fanout._network_get(
        fanout.catalog_request_target()
    )
    catalog_sha256 = hashlib.sha256(catalog_raw).hexdigest()
    _write_exclusive(output / "catalog.raw.json", catalog_raw)
    tournaments = fanout._parse_catalog(catalog_raw)

    observations: list[dict[str, Any]] = []
    for index, tournament in enumerate(tournaments):
        nonce = int(time.time() * 1000)
        target = fanout.tournament_request_target(
            category_id=tournament.category_id,
            tournament_id=tournament.tournament_id,
            request_nonce_ms=nonce,
        )
        try:
            raw, observed_at = fanout._network_get(target)
        except Exception as exc:
            observations.append(
                {
                    "category_id": tournament.category_id,
                    "tournament_id": tournament.tournament_id,
                    "request_target": target,
                    "acquisition_status": "SOURCE_ACQUISITION_FAILED",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "fixture_reconciliation_authorized": False,
                }
            )
            continue

        raw_sha256 = hashlib.sha256(raw).hexdigest()
        filename = f"tournament-{index:04d}-{raw_sha256[:16]}.raw.json"
        _write_exclusive(output / filename, raw)
        row_failures: tuple[dict[str, Any], ...] = ()
        try:
            observation, events = fanout._parse_tournament_response(
                raw,
                category_id=tournament.category_id,
                tournament_id=tournament.tournament_id,
                request_nonce_ms=nonce,
                observed_at=observed_at,
            )
            parse_status = "REVIEWED_PARSER_ACCEPTED"
            parser_error_type = None
            parser_error_message = None
            accepted_event_count = len(events)
            observation_sha256 = hashlib.sha256(
                _canonical(observation.to_dict())
            ).hexdigest()
        except fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError as exc:
            parse_status = "REVIEWED_PARSER_REJECTED"
            parser_error_type = type(exc).__name__
            parser_error_message = str(exc)
            accepted_event_count = 0
            observation_sha256 = None
            row_failures = _diagnose_tournament_rows(
                raw,
                raw_sha256=raw_sha256,
                observed_at=observed_at,
            )

        observations.append(
            {
                "category_id": tournament.category_id,
                "tournament_id": tournament.tournament_id,
                "request_target": target,
                "observed_at": _observed_text(observed_at),
                "raw_filename": filename,
                "raw_sha256": raw_sha256,
                "raw_size": len(raw),
                "parse_status": parse_status,
                "parser_error_type": parser_error_type,
                "parser_error_message": parser_error_message,
                "accepted_event_count": accepted_event_count,
                "observation_sha256": observation_sha256,
                "row_failures": list(row_failures),
                "fixture_reconciliation_authorized": False,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "command": COMMAND,
        "catalog_request_target": fanout.catalog_request_target(),
        "catalog_observed_at": _observed_text(catalog_observed_at),
        "catalog_raw_sha256": catalog_sha256,
        "catalog_raw_size": len(catalog_raw),
        "active_tournament_count": len(tournaments),
        "observations": observations,
        "authority": dict(AUTHORITY),
    }
    _write_exclusive(output / "manifest.json", _canonical(manifest))
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = capture_source_diagnostic(output_dir=args.output_dir)
    print(_canonical(manifest).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
