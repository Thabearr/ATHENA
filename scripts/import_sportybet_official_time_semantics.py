"""Preserve and qualify a human-exported official SportyBet time-semantics page."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

from domain.sportybet_official_time_semantics import (
    ALLOWED_OUTPUT_RELATIVE,
    ATTESTATION,
    EVENT_APPLICATION_STATUS,
    SEMANTIC_STATUS,
    SOURCE_URL,
    SportyBetOfficialTimeSemanticsError,
    parse_observed_at,
    qualification_sha256,
    read_official_time_semantics_html,
    store_official_time_semantics_evidence,
)
from domain.sportybet_lite_source_capture import serialize_utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Persist and qualify a user-controlled export of SportyBet Nigeria's "
            "official Terms & Conditions time-semantics evidence. This command "
            "performs no network acquisition."
        )
    )
    parser.add_argument("--html-file", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--attestation", required=True)
    parser.add_argument("--repository-root", default=".")
    return parser


def import_evidence(
    *,
    html_file: Path,
    source_url: str,
    observed_at: str,
    attestation: str,
    repository_root: Path,
    imported_at_utc: dt.datetime | None = None,
) -> dict[str, object]:
    if source_url != SOURCE_URL:
        raise SportyBetOfficialTimeSemanticsError(
            "source_url must be the exact reviewed official Terms & Conditions URL"
        )
    if attestation != ATTESTATION:
        raise SportyBetOfficialTimeSemanticsError(
            "attestation must exactly confirm manual observation/export of the official provider page"
        )
    observed = parse_observed_at(observed_at)
    imported = (
        dt.datetime.now(dt.timezone.utc)
        if imported_at_utc is None
        else imported_at_utc
    )
    raw = read_official_time_semantics_html(html_file)
    directory, qualification = store_official_time_semantics_evidence(
        raw,
        source_url=source_url,
        observed_at_user_attested=observed,
        imported_at_utc=imported,
        attestation=attestation,
        repository_root=repository_root,
        output_root=ALLOWED_OUTPUT_RELATIVE,
    )
    return {
        "status": "OFFICIAL_TIME_SEMANTICS_EVIDENCE_PRESERVED_AND_QUALIFIED",
        "provider": "SportyBet",
        "evidence_directory": directory.as_posix(),
        "qualification_sha256": qualification_sha256(qualification),
        "raw_sha256": qualification.raw_sha256,
        "raw_size": qualification.raw_size,
        "source_url": qualification.source_url,
        "observed_at_user_attested": serialize_utc(
            qualification.observed_at_user_attested
        ),
        "observation_authority": qualification.observation_authority,
        "semantic_status": SEMANTIC_STATUS,
        "time_zone_label": qualification.time_zone_label,
        "utc_offset_seconds": qualification.utc_offset_seconds,
        "unless_stated_otherwise": True,
        "event_local_override_check_required": True,
        "event_application_status": EVENT_APPLICATION_STATUS,
        "event_year_proven": False,
        "athena_network_acquisition_performed": False,
        "provider_quote_at": None,
        "provider_snapshot_id": None,
        "fixture_reconciliation_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "slip_construction_authorized": False,
        "booking_code_authorized": False,
        "sportybet_execution_authorized": False,
        "bet_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = import_evidence(
            html_file=Path(args.html_file),
            source_url=args.source_url,
            observed_at=args.observed_at,
            attestation=args.attestation,
            repository_root=Path(args.repository_root),
        )
    except SportyBetOfficialTimeSemanticsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
