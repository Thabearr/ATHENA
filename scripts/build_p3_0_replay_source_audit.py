"""Build the deterministic P3.0 retained-evidence source audit.

The builder reads only previously downloaded artifacts and source-controlled
fixtures.  It never acquires provider data or invokes application pipelines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from domain import p3_0_replay_corpus as replay


REPOSITORY_MAIN_SHA = "e4c028d08b19f2a3b46d85b490a4c6ea4fcd790a"
POST_BASELINE_FAILURES = (
    {
        "run_id": 35522650834,
        "job_id": 106109287808,
        "head_sha": REPOSITORY_MAIN_SHA,
        "exit_code": 2,
        "primary_artifact_id": 10609051331,
        "primary_artifact_digest": "sha256:8b0f84eee1cbbfac67b58a680a691af883ed9ddc2078fc6966a8a7c206c7a9b8",
        "diagnostics_artifact_id": 10608377277,
        "diagnostics_artifact_digest": "sha256:6a4085e0a4fb143da6f48920505f02fb350f328ebfb9682a92c7766c3b9243cc",
    },
    {
        "run_id": 35527434555,
        "job_id": 106121944857,
        "head_sha": REPOSITORY_MAIN_SHA,
        "exit_code": 2,
        "primary_artifact_id": 10609743958,
        "primary_artifact_digest": "sha256:f4881e3022a4a72806a465aacd20212b068f75825e5d8cf099bb693d5e921cef",
        "diagnostics_artifact_id": 10610492540,
        "diagnostics_artifact_digest": "sha256:22054efc57565a43ef5e6841d0373640bb5b208f00e547f2b0eb4dc7c791d3b3",
    },
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory_shape(root: Path) -> tuple[int, int, str]:
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
            }
        )
    return (
        len(records),
        sum(item["size"] for item in records),
        replay.canonical_sha256(records),
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise replay.ReplayCorpusError(f"{path} must contain a JSON object")
    return value


def _p3_baseline(
    path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = _load_json(path)
    inventory = [
        {
            "source_id": "p3-e1-baseline-audit",
            "source_class": "P3_0_E1_RETAINED_ARTIFACTS",
            "path": "artifacts/p3-0-comparator-corpus-audit.json",
            "canonical_sha256": baseline["canonical_sha256"],
            "artifact_count": baseline["corpus_summary"]["total_artifacts_audited"],
            "candidate_count": (
                baseline["corpus_summary"]["corpus_complete_members_count"]
                + baseline["corpus_summary"]["partial_not_comparator_authority_count"]
            ),
            "audit_state": "CONTENT_AND_DIGESTS_PREVIOUSLY_VERIFIED",
        }
    ]
    candidates: list[dict[str, Any]] = []
    for member in baseline["complete_corpus_members"]:
        for index, record in enumerate(member["fixture_records"]):
            candidates.append(
                {
                    "candidate_id": f"p3-e1:{member['artifact_id']}:{index}",
                    "source_id": "p3-e1-baseline-audit",
                    "source_artifact_or_file": (
                        f"github-actions-artifact:{member['artifact_id']}"
                    ),
                    "fixture_identity": record["fixture_identity"],
                    "provider_event_id": record["provider_event_id"],
                    "home_team": record["home_team"],
                    "away_team": record["away_team"],
                    "competition": record["competition"],
                    "kickoff_utc": record["kickoff_utc"],
                    "source_observed_at": "2026-09-20T09:34:50.939987Z",
                    "market_families": record["market_families"],
                    "duplicate": False,
                    "identity_proven": record["join_state"] == "EXACT_SAME_FIXTURE_PROVEN",
                    "temporal_lineage_proven": record["as_of_proof"] == "PROVEN",
                    "contract_current": True,
                    "canonical_lineage_proven": member["bundle_verifies"] is True,
                    "exact_quote_proven": member["bundle_verifies"] is True,
                    "legacy_lineage_proven": member["bundle_verifies"] is True,
                    "failed_requirement_detail": None,
                    "repairability_class": replay.COMPLETE,
                    "offline_repairability": "NOT_REQUIRED_REPLAY_COMPLETE",
                    "historical_contract_analysis": "HISTORICAL_CONTRACT_VERIFIABLE_AND_SEMANTICALLY_COMPATIBLE",
                    "identity_recovery_analysis": "EXACT_IDENTITY_PROVEN",
                    "legacy_lineage_analysis": "LEGACY_PRESERVED_COMPLETE",
                    "quote_lineage_analysis": "EXACT_QUOTE_COMPLETE",
                    "temporal_lineage_analysis": "TEMPORAL_ORDER_VALID",
                    "exact_fixture_identity_present": True,
                    "exact_home_away_orientation_present": True,
                    "competition_identity_present": True,
                    "kickoff_utc_present": True,
                    "source_identity_present": True,
                    "source_observed_at_present": True,
                    "capture_or_run_identity_present": True,
                    "exact_provider_event_id_present": True,
                    "exact_quote_identity_present": True,
                    "quote_decimal_odds_present": True,
                    "quote_market_identity_present": True,
                    "quote_outcome_identity_present": True,
                    "quote_line_present_if_required": True,
                    "quote_observed_at_present": True,
                    "quote_source_digest_present": True,
                    "quote_reconciliation_ancestry_present": True,
                    "canonical_probability_present": True,
                    "canonical_probability_contract_valid": True,
                    "price_all_output_present": True,
                    "price_all_contract_valid": True,
                    "router_output_present": True,
                    "router_contract_valid": True,
                    "canonical_owner_identity_present": True,
                    "supported_legacy_input_present": True,
                    "supported_legacy_output_present": True,
                    "supported_legacy_path_proven": True,
                    "exact_legacy_as_of_present": True,
                    "legacy_quote_binding_proven_if_required": True,
                    "prematch_temporal_order_valid": True,
                    "no_post_event_input": True,
                    "no_later_quote_reuse": True,
                    "historical_head_sha_present": True,
                    "historical_contract_identity_present": True,
                    "historical_contract_source_recoverable_from_git": True,
                    "current_contract_replay_possible": True,
                    "source_bytes_immutable_and_verified": True,
                    "hashes": {
                        "artifact_digest": member["artifact_digest"],
                        "canonical_lineage_sha256": member["bundle_canonical_sha256"],
                        "legacy_lineage_sha256": member["bundle_canonical_sha256"],
                        "manifest_file_sha256": member["manifest_file_sha256"],
                        "quote_identity_binding": (
                            "VERIFIED_INSIDE_BUNDLE:"
                            + member["bundle_canonical_sha256"]
                        ),
                    },
                }
            )
    for item in baseline["partial_and_unusable_artifacts"]:
        if item.get("fixture_count") != 1:
            continue
        fixture_identity = (item.get("fixture_identities") or [None])[0]
        candidates.append(
            {
                "candidate_id": f"p3-e1:{item['artifact_id']}:0",
                "source_id": "p3-e1-baseline-audit",
                "source_artifact_or_file": f"github-actions-artifact:{item['artifact_id']}",
                "fixture_identity": fixture_identity,
                "provider_event_id": None,
                "home_team": None,
                "away_team": None,
                "competition": (item.get("competitions") or [None])[0],
                "kickoff_utc": (item.get("fixture_kickoffs") or [None])[0],
                "source_observed_at": None,
                "market_families": item.get("market_families") or [],
                "duplicate": False,
                "identity_proven": bool(fixture_identity),
                "temporal_lineage_proven": False,
                "contract_current": True,
                "canonical_lineage_proven": False,
                "exact_quote_proven": False,
                "legacy_lineage_proven": False,
                "failed_requirement_detail": item["exclusion_reason"],
                "repairability_class": replay.TRUE_SOURCE_ABSENCE,
                "offline_repairability": "MISSING_CAPTURE_BYTES_CANNOT_BE_FABRICATED",
                "historical_contract_analysis": "OTHER_EXACT_BLOCKER",
                "identity_recovery_analysis": "IDENTITY_EVIDENCE_ABSENT",
                "legacy_lineage_analysis": "LEGACY_CONTEXT_ABSENT",
                "quote_lineage_analysis": "QUOTE_GAP",
                "temporal_lineage_analysis": "TEMPORAL_GAP",
                "exact_fixture_identity_present": bool(fixture_identity),
                "exact_home_away_orientation_present": False,
                "competition_identity_present": bool(item.get("competitions")),
                "kickoff_utc_present": bool(item.get("fixture_kickoffs")),
                "source_identity_present": True,
                "source_observed_at_present": False,
                "capture_or_run_identity_present": True,
                "exact_provider_event_id_present": False,
                "exact_quote_identity_present": False,
                "quote_decimal_odds_present": False,
                "quote_market_identity_present": False,
                "quote_outcome_identity_present": False,
                "quote_line_present_if_required": False,
                "quote_observed_at_present": False,
                "quote_source_digest_present": False,
                "quote_reconciliation_ancestry_present": False,
                "canonical_probability_present": False,
                "canonical_probability_contract_valid": False,
                "price_all_output_present": False,
                "price_all_contract_valid": False,
                "router_output_present": False,
                "router_contract_valid": False,
                "canonical_owner_identity_present": False,
                "supported_legacy_input_present": False,
                "supported_legacy_output_present": False,
                "supported_legacy_path_proven": False,
                "exact_legacy_as_of_present": False,
                "legacy_quote_binding_proven_if_required": False,
                "prematch_temporal_order_valid": False,
                "no_post_event_input": True,
                "no_later_quote_reuse": True,
                "historical_head_sha_present": True,
                "historical_contract_identity_present": False,
                "historical_contract_source_recoverable_from_git": True,
                "current_contract_replay_possible": False,
                "source_bytes_immutable_and_verified": True,
                "hashes": {"artifact_digest": item["artifact_digest"]},
            }
        )
    return inventory, candidates


def _current_shadow(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for run_dir in sorted(item for item in root.iterdir() if item.is_dir()):
        receipts = sorted(run_dir.rglob("current-shadow-all-market-run-receipt.json"))
        if not receipts:
            continue
        receipt_path = receipts[0]
        receipt = _load_json(receipt_path)
        source_id = f"current-shadow-run:{run_dir.name}"
        file_count, byte_count, shape_sha = _inventory_shape(run_dir)
        inventory.append(
            {
                "source_id": source_id,
                "source_class": "RETAINED_CURRENT_SHADOW_ALL_MARKET_ARTIFACT",
                "run_id": int(run_dir.name),
                "head_sha": receipt.get("exact_commit_sha"),
                "observed_at": receipt.get("observed_at"),
                "status": receipt.get("status"),
                "receipt_sha256": _sha256_file(receipt_path),
                "extracted_file_count": file_count,
                "extracted_byte_count": byte_count,
                "extracted_inventory_shape_sha256": shape_sha,
                "candidate_count": 0,
                "audit_state": "RETAINED_BYTES_AUDITED_OFFLINE",
            }
        )

        by_fixture: dict[str, Mapping[str, Any]] = {}
        for market in receipt.get("market_diagnostics") or []:
            for opportunity in market.get("opportunities") or []:
                fixture = opportunity.get("fixture_identity")
                if fixture:
                    by_fixture[fixture] = opportunity
        portfolio = receipt.get("portfolio") or {}
        for route in portfolio.get("route_audits") or []:
            fixture = route.get("fixture_identity")
            if fixture and fixture not in by_fixture:
                by_fixture[fixture] = route

        details: dict[str, Mapping[str, Any]] = {}
        for collection in (
            receipt.get("final_selected_legs") or [],
            portfolio.get("reserve_legs") or [],
            portfolio.get("selected_legs") or [],
        ):
            for leg in collection:
                fixture = leg.get("fixture_identity")
                if fixture:
                    details[fixture] = leg

        inventory[-1]["candidate_count"] = len(by_fixture)
        for fixture in sorted(by_fixture):
            opportunity = by_fixture[fixture]
            detail = details.get(fixture)
            identity_proven = bool(
                detail
                and detail.get("home_team")
                and detail.get("away_team")
                and detail.get("competition")
                and detail.get("kickoff_utc")
                and detail.get("provider_event_id")
            )
            quote_proven = bool(
                detail
                and isinstance(detail.get("quote_identity_sha256"), str)
                and len(detail["quote_identity_sha256"]) == 64
            )
            hashes = {
                "receipt_sha256": inventory[-1]["receipt_sha256"],
                "extracted_inventory_shape_sha256": shape_sha,
            }
            if detail:
                for field in (
                    "fixture_reconciliation_sha256",
                    "price_all_bundle_sha256",
                    "provider_observation_sha256",
                    "provider_registry_sha256",
                    "quote_identity_sha256",
                    "router_decision_sha256",
                    "source_inventory_sha256",
                    "source_manifest_sha256",
                    "source_raw_sha256",
                ):
                    value = detail.get(field)
                    if isinstance(value, str) and value:
                        hashes[field] = value

            temporal_proven = bool(
                identity_proven
                and str(receipt.get("observed_at")) < str(detail.get("kickoff_utc"))
            )

            candidates.append(
                {
                    "candidate_id": f"current-shadow:{run_dir.name}:{fixture}",
                    "source_id": source_id,
                    "source_artifact_or_file": receipt_path.relative_to(root).as_posix(),
                    "fixture_identity": fixture,
                    "provider_event_id": (
                        detail.get("provider_event_id")
                        if detail
                        else opportunity.get("provider_event_id")
                    ),
                    "home_team": None if not detail else detail.get("home_team"),
                    "away_team": None if not detail else detail.get("away_team"),
                    "competition": None if not detail else detail.get("competition"),
                    "kickoff_utc": None if not detail else detail.get("kickoff_utc"),
                    "source_observed_at": receipt.get("observed_at"),
                    "market_families": []
                    if not detail
                    else [detail.get("market_family")]
                    if detail.get("market_family")
                    else [],
                    "duplicate": False,
                    "identity_proven": identity_proven,
                    "temporal_lineage_proven": temporal_proven,
                    "contract_current": False,
                    "canonical_lineage_proven": False,
                    "exact_quote_proven": quote_proven,
                    "legacy_lineage_proven": False,
                    "failed_requirement_detail": (
                        "Retained Current Shadow receipt has no supported "
                        "AnalysisPipeline decision. Detailed selected rows bind quote, "
                        "Price-All, and Router hashes but do not preserve the full "
                        "canonical payloads required for replay admission; other routed "
                        "rows also lack complete fixture and quote projections."
                    ),
                    "repairability_class": replay.TRUE_SOURCE_ABSENCE,
                    "offline_repairability": (
                        "EVIDENCE_EXISTS_BUT_REPLAY_ADAPTER_AND_CONTRACT_MIGRATION_REQUIRED"
                        if identity_proven
                        else "PRESERVED_RECEIPT_PROJECTION_INSUFFICIENT_WITHOUT_FABRICATION"
                    ),
                    "historical_contract_analysis": "TRUE_SEMANTIC_CONTRACT_DRIFT",
                    "identity_recovery_analysis": (
                        "EXACT_IDENTITY_PROVEN"
                        if identity_proven
                        else "IDENTITY_REQUIRES_NEW_AUTHORITY"
                    ),
                    "legacy_lineage_analysis": "LEGACY_CONTEXT_ABSENT",
                    "quote_lineage_analysis": (
                        "EXACT_QUOTE_COMPLETE" if quote_proven else "QUOTE_GAP"
                    ),
                    "temporal_lineage_analysis": (
                        "TEMPORAL_ORDER_VALID" if temporal_proven else "TEMPORAL_GAP"
                    ),
                    "exact_fixture_identity_present": bool(fixture),
                    "exact_home_away_orientation_present": bool(detail and detail.get("home_team")),
                    "competition_identity_present": bool(detail and detail.get("competition")),
                    "kickoff_utc_present": bool(detail and detail.get("kickoff_utc")),
                    "source_identity_present": True,
                    "source_observed_at_present": bool(receipt.get("observed_at")),
                    "capture_or_run_identity_present": True,
                    "exact_provider_event_id_present": bool(
                        detail.get("provider_event_id") if detail else opportunity.get("provider_event_id")
                    ),
                    "exact_quote_identity_present": quote_proven,
                    "quote_decimal_odds_present": bool(detail and detail.get("decimal_odds")),
                    "quote_market_identity_present": bool(
                        detail and (detail.get("provider_market_id") or detail.get("market_id"))
                    ),
                    "quote_outcome_identity_present": bool(
                        detail and (detail.get("provider_outcome_id") or detail.get("outcome_id"))
                    ),
                    "quote_line_present_if_required": bool(detail and ("line" in detail)),
                    "quote_observed_at_present": quote_proven,
                    "quote_source_digest_present": bool(detail and detail.get("source_raw_sha256")),
                    "quote_reconciliation_ancestry_present": bool(
                        detail and detail.get("fixture_reconciliation_sha256")
                    ),
                    "canonical_probability_present": False,
                    "canonical_probability_contract_valid": False,
                    "price_all_output_present": False,
                    "price_all_contract_valid": False,
                    "router_output_present": False,
                    "router_contract_valid": False,
                    "canonical_owner_identity_present": False,
                    "supported_legacy_input_present": False,
                    "supported_legacy_output_present": False,
                    "supported_legacy_path_proven": False,
                    "exact_legacy_as_of_present": False,
                    "legacy_quote_binding_proven_if_required": False,
                    "prematch_temporal_order_valid": temporal_proven,
                    "no_post_event_input": True,
                    "no_later_quote_reuse": True,
                    "historical_head_sha_present": bool(receipt.get("exact_commit_sha")),
                    "historical_contract_identity_present": True,
                    "historical_contract_source_recoverable_from_git": True,
                    "current_contract_replay_possible": False,
                    "source_bytes_immutable_and_verified": True,
                    "hashes": hashes,
                }
            )
    return inventory, candidates


def build(
    *,
    repository_root: Path,
    current_shadow_root: Path,
) -> dict[str, Any]:
    inventory, candidates = _p3_baseline(
        repository_root / "artifacts" / "p3-0-comparator-corpus-audit.json"
    )
    shadow_inventory, shadow_candidates = _current_shadow(current_shadow_root)
    inventory.extend(shadow_inventory)
    candidates.extend(shadow_candidates)
    inventory.append(
        {
            "source_id": "p3-e1-post-baseline-failures",
            "source_class": "P3_0_E1_RETAINED_ARTIFACTS",
            "candidate_count": 0,
            "audit_state": "PUBLIC_RUN_METADATA_PROVES_CAPTURE_EXIT_CODE_2",
            "runs": list(POST_BASELINE_FAILURES),
        }
    )
    inventory.extend(
        [
            {
                "source_id": "source-controlled-p0-acceptance",
                "source_class": "SYNTHETIC_REPRODUCIBLE_P0_ACCEPTANCE_CASES",
                "path": "tests/fixtures/architecture/legacy_market_selection_cases_v1.json",
                "synthetic_case_count": 5,
                "candidate_count": 0,
                "audit_state": "EXCLUDED_FROM_REAL_CORPUS_BY_POLICY",
            },
            {
                "source_id": "source-controlled-current-shadow-shape",
                "source_class": "DETERMINISTIC_SHAPE_REPRODUCTION",
                "path": "tests/fixtures/p3_0/run_35441111017_source_viability_shape.json",
                "candidate_count": 0,
                "audit_state": "NO_RETAINED_REPLAY_ROW_BYTES",
            },
            {
                "source_id": "source-controlled-fotmob-post-finish-pair",
                "source_class": "POST_EVENT_RAW_SOURCE_CAPTURE",
                "path": "evidence/fotmob_data_matches/pr83_post_finish_pair",
                "capture_count": 2,
                "candidate_count": 0,
                "audit_state": "POST_EVENT_AND_NO_PROVIDER_QUOTE_OR_DECISION_LINEAGE",
            },
            {
                "source_id": "source-controlled-field-trial",
                "source_class": "UNVERIFIED_PLANNING_SUMMARY",
                "path": "evidence/prediction-field-trials/first-proper-20-leg-athena-field-trial-summary.json",
                "declared_leg_count": 20,
                "preserved_leg_count": 0,
                "candidate_count": 0,
                "audit_state": "NO_EXACT_PRESERVED_ROWS",
            },
        ]
    )
    return replay.build_source_audit(
        repository_main_sha=REPOSITORY_MAIN_SHA,
        source_inventory=inventory,
        candidates=candidates,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--current-shadow-root", type=Path, required=True
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/p3-0-replay-source-audit-v1.json"),
    )
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    audit = build(
        repository_root=repository_root,
        current_shadow_root=args.current_shadow_root.resolve(),
    )
    replay.write_source_audit(args.output, audit)
    print(audit["canonical_sha256"])
    print(audit["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
