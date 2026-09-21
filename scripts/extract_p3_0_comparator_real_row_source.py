"""ATHENA P3.0 Comparator Real-Row Source Extraction.

Extracts the verified complete real replay row from the immutable GitHub Actions
artifact 10603511090 and creates the source-controlled projection receipt:
artifacts/p3-0-comparator-real-row-source-v1.json

Validates:
- Artifact zip digest (sha256:abe4727ae0eaa8e6e0580b2fe4d2298711b13cca0bd00546e958f30613f87c4d)
- Manifest file SHA-256 (62a52a3b9fd05953bf54a63b122fc65ab1283fe7b0c2d0e63210355a14209bcc)
- Verified paired bundle canonical SHA-256 (d0cd8f13360a8134af258a8dd9892cc637296fa9500627b564d860232a989191)
- Exact fixture join receipt (EXACT_SAME_FIXTURE_PROVEN)
- Exact temporal / as-of proof (PROVEN)
- Exact quote identity SHA-256 (7f6fb592626f12779b4824371bdf53ab45073e2125fee60e58f27d727fa2be11)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import zipfile

from domain.p3_0_replay_corpus import canonical_json_bytes, canonical_sha256

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P3_0_COMPARATOR_REAL_ROW_SOURCE_V1"

EXPECTED_ARTIFACT_ID = "10603511090"
EXPECTED_ARTIFACT_DIGEST = (
    "sha256:abe4727ae0eaa8e6e0580b2fe4d2298711b13cca0bd00546e958f30613f87c4d"
)
EXPECTED_MANIFEST_SHA256 = (
    "62a52a3b9fd05953bf54a63b122fc65ab1283fe7b0c2d0e63210355a14209bcc"
)
EXPECTED_BUNDLE_CANONICAL_SHA256 = (
    "d0cd8f13360a8134af258a8dd9892cc637296fa9500627b564d860232a989191"
)
EXPECTED_FIXTURE_ID = "FOTMOB:5749683"
EXPECTED_PROVIDER_EVENT_ID = "sr:match:71945268"
EXPECTED_QUOTE_IDENTITY_SHA256 = (
    "7f6fb592626f12779b4824371bdf53ab45073e2125fee60e58f27d727fa2be11"
)
EXPECTED_CANDIDATE_ID = "p3-e1:10603511090:0"


class ExtractionError(Exception):
    """Raised when artifact extraction or validation fails."""


def extract_real_row_from_zip(zip_path: Path) -> dict[str, Any]:
    """Extract and cryptographically verify the single real row from the artifact zip."""
    if not zip_path.is_file():
        raise ExtractionError(f"Artifact zip not found: {zip_path}")

    zip_bytes = zip_path.read_bytes()
    actual_digest = f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}"
    if actual_digest != EXPECTED_ARTIFACT_DIGEST:
        raise ExtractionError(
            f"Artifact digest mismatch: expected {EXPECTED_ARTIFACT_DIGEST}, got {actual_digest}"
        )

    with zipfile.ZipFile(zip_path) as z:
        # 1. Verify manifest
        try:
            manifest_raw = z.read("capture/manifest.json")
        except KeyError:
            raise ExtractionError("capture/manifest.json not found in artifact zip")
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        if manifest_sha != EXPECTED_MANIFEST_SHA256:
            raise ExtractionError(
                f"Manifest SHA256 mismatch: expected {EXPECTED_MANIFEST_SHA256}, got {manifest_sha}"
            )
        manifest = json.loads(manifest_raw.decode("utf-8"))

        if manifest.get("bundle_canonical_sha256") != EXPECTED_BUNDLE_CANONICAL_SHA256:
            raise ExtractionError("Bundle canonical SHA mismatch in manifest")

        # Verify all files listed in manifest match their exact byte sha256
        manifest_files = {f["path"]: f["sha256"] for f in manifest.get("files", [])}
        for file_path, expected_file_sha in manifest_files.items():
            entry_name = f"capture/{file_path}"
            try:
                entry_bytes = z.read(entry_name)
            except KeyError:
                raise ExtractionError(f"File {entry_name} listed in manifest missing from zip")
            actual_file_sha = hashlib.sha256(entry_bytes).hexdigest()
            if actual_file_sha != expected_file_sha:
                raise ExtractionError(
                    f"File {entry_name} byte SHA256 mismatch: expected {expected_file_sha}, got {actual_file_sha}"
                )

        # 2. Verify bundle
        bundle_raw = z.read("capture/bundle.json")
        bundle = json.loads(bundle_raw.decode("utf-8"))
        from domain import p3_0_comparison_evidence as evidence
        checked_bundle = evidence.verify_capture_bundle(bundle)
        actual_bundle_sha = checked_bundle.get("canonical_sha256")
        if actual_bundle_sha != EXPECTED_BUNDLE_CANONICAL_SHA256:
            raise ExtractionError(
                f"Bundle canonical SHA mismatch: expected {EXPECTED_BUNDLE_CANONICAL_SHA256}, got {actual_bundle_sha}"
            )

        fixture_records = bundle.get("fixture_records", [])
        if len(fixture_records) != 1:
            raise ExtractionError(
                f"Expected exactly 1 fixture record in bundle, got {len(fixture_records)}"
            )
        record = fixture_records[0]

        # 3. Verify join receipt
        join_receipt = record.get("join_receipt", {})
        if join_receipt.get("join_state") != "EXACT_SAME_FIXTURE_PROVEN":
            raise ExtractionError(f"Join receipt not proven: {join_receipt.get('join_state')}")
        join_sha = canonical_sha256(join_receipt)

        # 4. Verify as-of proof
        as_of_proof = record.get("as_of_proof", {})
        if as_of_proof.get("result") != "PROVEN":
            raise ExtractionError(f"As-of proof not proven: {as_of_proof.get('result')}")
        as_of_sha = canonical_sha256(as_of_proof)

        # 5. Verify fixture state and orientation
        fixture_state = record.get("canonical_fixture_state", {})
        fixture_id = fixture_state.get("fixture_identity")
        provider_event_id = fixture_state.get("provider_event_id")
        home = fixture_state.get("home_team")
        away = fixture_state.get("away_team")
        competition = fixture_state.get("competition")
        kickoff_utc = fixture_state.get("kickoff_utc")
        source_observed_at = fixture_state.get("source_observed_at")

        if fixture_id != EXPECTED_FIXTURE_ID:
            raise ExtractionError(f"Fixture identity mismatch: {fixture_id}")
        if provider_event_id != EXPECTED_PROVIDER_EVENT_ID:
            raise ExtractionError(f"Provider event ID mismatch: {provider_event_id}")
        if home != "Fiorentina" or away != "Napoli" or competition != "Serie A":
            raise ExtractionError("Team identity or competition mismatch")

        # 6. Extract canonical router selection
        router_output = record.get("router_output", {})
        router_payload = router_output.get("payload", {})
        router_status = router_payload.get("status")
        selected_opp_id = router_payload.get("selected_opportunity_id")
        if router_status != "SELECTED" or not selected_opp_id:
            raise ExtractionError("Router output did not produce SELECTED decision")

        selected_opp = None
        for opp in router_payload.get("opportunities", []):
            if opp.get("opportunity_id") == selected_opp_id:
                selected_opp = opp
                break
        if not selected_opp:
            raise ExtractionError("Selected opportunity not found in router opportunities list")

        price_result = selected_opp.get("price_result", {})
        decimal_odds = price_result.get("decimal_odds")
        market = price_result.get("market_id")
        outcome = price_result.get("outcome_id")
        line = price_result.get("line")
        quote_identity_sha = price_result.get("quote_identity_sha256")

        if quote_identity_sha != EXPECTED_QUOTE_IDENTITY_SHA256:
            raise ExtractionError(
                f"Quote identity mismatch: expected {EXPECTED_QUOTE_IDENTITY_SHA256}, got {quote_identity_sha}"
            )
        if decimal_odds != 1.61 or market != "ASIAN_HANDICAP" or outcome != "AWAY" or line != 0.0:
            raise ExtractionError("Selected opportunity fields mismatch")

        # 7. Extract exact quote details from snapshot in zip
        fixture_dir = "fixtures/b92977dd70219469b3fe580de952e1f56d37616f14f8ecebb944949f5974d065"
        quote_snapshot_raw = z.read(f"capture/{fixture_dir}/quote-snapshot.json")
        quote_snapshot = json.loads(quote_snapshot_raw.decode("utf-8"))
        matched_quote = None
        for q in quote_snapshot.get("quotes", []):
            if q.get("quote_identity_sha256") == EXPECTED_QUOTE_IDENTITY_SHA256:
                matched_quote = q
                break
        if not matched_quote:
            raise ExtractionError("Matching quote not found in quote snapshot")

        # 8. Extract legacy side
        legacy_output = record.get("legacy_output", {})
        authorized_analysis = legacy_output.get("authorized_analysis", {})
        legacy_status = authorized_analysis.get(
            "legacy_decision_status_before_runtime_gate", "ANALYTICAL_CANDIDATE"
        )
        legacy_no_bet_reasons = authorized_analysis.get("no_bet_reasons", [])
        legacy_rec = authorized_analysis.get("recommended_analytical_verdict")

        # 9. Individual constituent file SHAs from manifest
        legacy_output_file_sha = manifest_files.get(f"{fixture_dir}/legacy-output.json")
        legacy_input_file_sha = manifest_files.get(f"{fixture_dir}/legacy-input.json")
        router_output_file_sha = manifest_files.get(f"{fixture_dir}/router-output.json")
        price_all_output_file_sha = manifest_files.get(f"{fixture_dir}/price-all-output.json")
        probability_bundle_file_sha = manifest_files.get(f"{fixture_dir}/probability-bundle.json")

        payload: dict[str, Any] = {
            "candidate_id": EXPECTED_CANDIDATE_ID,
            "canonical": {
                "decimal_odds": decimal_odds,
                "eligibility": selected_opp.get("eligibility"),
                "line": line,
                "market": market,
                "outcome": outcome,
                "prediction_confidence": selected_opp.get("prediction_confidence"),
                "prediction_confidence_method": selected_opp.get("prediction_confidence_method"),
                "price_all_output_file_sha256": price_all_output_file_sha,
                "probability_bundle_file_sha256": probability_bundle_file_sha,
                "probability_floor": price_result.get("implied_probability"),
                "recommendation": f"{market} {outcome} {line} @ {decimal_odds} ({home} vs {away})",
                "rejection_reasons": selected_opp.get("rejection_reasons", []),
                "robust_net_expected_value": selected_opp.get("robust_net_expected_value"),
                "router_output_file_sha256": router_output_file_sha,
                "router_status": router_status,
                "selected_opportunity_id": selected_opp_id,
            },
            "fixture": {
                "as_of_proof_sha256": as_of_sha,
                "away_team": away,
                "canonical_fixture_state_sha256": manifest_files.get(f"{fixture_dir}/canonical-fixture-state.json"),
                "competition": competition,
                "fixture_identity": fixture_id,
                "home_team": home,
                "join_receipt_sha256": join_sha,
                "kickoff_utc": kickoff_utc,
                "provider_event_id": provider_event_id,
                "source_observed_at": source_observed_at,
            },
            "hashes": {
                "artifact_digest": EXPECTED_ARTIFACT_DIGEST,
                "canonical_price_all_output_sha256": price_all_output_file_sha,
                "canonical_probability_bundle_sha256": probability_bundle_file_sha,
                "canonical_router_output_sha256": router_output_file_sha,
                "legacy_input_file_sha256": legacy_input_file_sha,
                "legacy_output_file_sha256": legacy_output_file_sha,
                "manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
                "paired_bundle_canonical_sha256": EXPECTED_BUNDLE_CANONICAL_SHA256,
                "quote_identity_sha256": EXPECTED_QUOTE_IDENTITY_SHA256,
            },
            "legacy": {
                "decision_status": legacy_status,
                "disposition": "ANALYTICAL_ONLY_NO_BET",
                "final_recommendation": legacy_rec,
                "has_price": False,
                "legacy_input_file_sha256": legacy_input_file_sha,
                "legacy_output_file_sha256": legacy_output_file_sha,
                "no_bet_reasons": list(legacy_no_bet_reasons),
                "probability": None,
                "supported_path": "AnalysisPipeline",
            },
            "policy_id": POLICY_ID,
            "provenance": {
                "artifact_digest": EXPECTED_ARTIFACT_DIGEST,
                "artifact_id": EXPECTED_ARTIFACT_ID,
                "capture_id": bundle.get("capture_id"),
                "fixture_record_path": fixture_dir,
                "manifest_file_sha256": EXPECTED_MANIFEST_SHA256,
                "paired_bundle_canonical_sha256": EXPECTED_BUNDLE_CANONICAL_SHA256,
                "source_file_in_artifact": "capture/bundle.json",
            },
            "quote": {
                "decimal_odds": matched_quote.get("decimal_odds"),
                "mapping_contract_identity": matched_quote.get("provider_semantic_status"),
                "observed_at": matched_quote.get("observed_at"),
                "provider_market_id": matched_quote.get("provider_market_id"),
                "provider_market_name": matched_quote.get("provider_market_name"),
                "provider_observation_sha256": matched_quote.get("provider_observation_sha256"),
                "provider_outcome_id": matched_quote.get("provider_outcome_id"),
                "provider_outcome_name": matched_quote.get("provider_outcome_name"),
                "provider_registry_sha256": matched_quote.get("provider_registry_sha256"),
                "provider_specifier": matched_quote.get("provider_specifier"),
                "quote_identity_sha256": EXPECTED_QUOTE_IDENTITY_SHA256,
                "reconciliation_sha256": matched_quote.get("fixture_reconciliation_sha256"),
                "source_inventory_sha256": matched_quote.get("source_inventory_sha256"),
                "source_manifest_sha256": matched_quote.get("source_manifest_sha256"),
                "source_observed_at": bundle.get("capture_started_at"),
                "source_raw_sha256": matched_quote.get("source_raw_sha256"),
            },
            "schema_version": SCHEMA_VERSION,
            "source_mechanism": "VERIFIED_ARTIFACT_PROJECTION",
        }
        payload["canonical_sha256"] = canonical_sha256(payload)
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract real row source from verified artifact zip.")
    parser.add_argument(
        "--artifact-zip",
        type=Path,
        required=True,
        help="Path to downloaded artifact 10603511090 zip file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/p3-0-comparator-real-row-source-v1.json"),
        help="Target output path for real row source artifact.",
    )
    args = parser.parse_args(argv)

    extracted = extract_real_row_from_zip(args.artifact_zip)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(extracted))
    print(f"Extracted real row source to: {args.output}")
    print(f"CANONICAL_SHA256: {extracted['canonical_sha256']}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
