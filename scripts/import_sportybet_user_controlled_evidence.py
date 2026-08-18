"""Import a human-exported SportyBet Lite HTML page without network I/O."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

from domain.sportybet_user_controlled_evidence import (
    ATTESTATION,
    ALLOWED_OUTPUT_RELATIVE,
    SportyBetUserEvidenceError,
    manifest_sha256,
    read_user_html,
    store_user_controlled_evidence,
)
from domain.sportybet_lite_source_capture import parse_utc_timestamp, serialize_utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Persist user-controlled SportyBet Lite HTML evidence. "
            "This command performs no network acquisition."
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
    if attestation != ATTESTATION:
        raise SportyBetUserEvidenceError(
            "attestation must exactly confirm a manual user-controlled observation/export"
        )
    try:
        observed = parse_utc_timestamp(observed_at, "observed_at")
    except Exception as exc:
        if isinstance(exc, SportyBetUserEvidenceError):
            raise
        raise SportyBetUserEvidenceError(str(exc)) from exc
    imported = (
        dt.datetime.now(dt.timezone.utc)
        if imported_at_utc is None
        else imported_at_utc
    )
    raw = read_user_html(html_file)
    directory, manifest = store_user_controlled_evidence(
        raw,
        source_url=source_url,
        observed_at_user_attested=observed,
        imported_at_utc=imported,
        attestation=attestation,
        repository_root=repository_root,
        output_root=ALLOWED_OUTPUT_RELATIVE,
    )
    return {
        "status": "USER_CONTROLLED_EVIDENCE_PRESERVED",
        "provider": "SportyBet",
        "evidence_directory": directory.as_posix(),
        "manifest_sha256": manifest_sha256(manifest),
        "raw_sha256": manifest.raw_sha256,
        "raw_size": manifest.raw_size,
        "source_url": manifest.source_url,
        "source_request_target": manifest.request_target,
        "observed_at_user_attested": serialize_utc(manifest.observed_at_user_attested),
        "observation_authority": manifest.observation_authority,
        "provider_quote_at": None,
        "provider_snapshot_id": None,
        "athena_network_acquisition_performed": False,
        "network_acquisition_authorized": False,
        "fresh_price_authorized": False,
        "pricing_authorized": False,
        "selection_authorized": False,
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
    except SportyBetUserEvidenceError as exc:
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
