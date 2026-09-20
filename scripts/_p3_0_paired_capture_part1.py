#!/usr/bin/env python3
"""Explicit prospective paired capture for ATHENA P3.0-E1.

The command is default-off and only runs when invoked directly. It acquires the
reviewed Current Shadow source/Price-All/Router evidence up to the Router stage,
runs the supported legacy AnalysisPipeline against those exact reconciled
fixtures, and packages both sides into the immutable P3.0-E1 evidence contract.
It never calls Portfolio, share-code delivery, email, login, wallet, staking, or
wagering code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence

from domain import canonical_core
from domain import current_shadow_canonical_core_adapter as shadow_core_adapter
from domain import current_shadow_fixture_date_request as date_request
from domain import p3_0_comparison_evidence as evidence
from domain import provider_market_semantics
from domain.current_shadow_market_probability_adapter import (
    market_probability_bundle_from_current_shadow_fixture_scan,
)
from domain._current_shadow_quote_binding import build_current_shadow_exact_quotes
from domain import current_shadow_all_market_runner as shadow_runner
from scripts import execute_current_shadow_daily as shadow_daily

POLICY_ID = "ATHENA_P3_0_PROSPECTIVE_PAIRED_CAPTURE_V1"
FIXTURE_IDENTITY_POLICY = "P3_0_EXACT_FOTMOB_RECONCILED_FIXTURE_ID_V1"
MAX_FIXTURE_CAP = 50
FAILURE_RECEIPT_SCHEMA_VERSION = 2
FAILURE_CHAIN_MAX_DEPTH = 8
FAILURE_MESSAGE_MAX_CHARS = 800


class P30PairedCaptureError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise P30PairedCaptureError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _git_head(repository_root: Path) -> str:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True,
            stderr=subprocess.DEVNULL,
        ).strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise P30PairedCaptureError("exact repository commit SHA is unavailable") from exc
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise P30PairedCaptureError("repository commit SHA is invalid")
    return value


def _lineage_main_sha() -> str:
    value = os.environ.get(shadow_runner.EXPECTED_LINEAGE_MAIN_ENV, "").strip().lower()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise P30PairedCaptureError(
            f"{shadow_runner.EXPECTED_LINEAGE_MAIN_ENV} must contain exact lineage main SHA"
        )
    return value


def _fixture_cap(value: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("fixture cap must be an integer from 1 through 50") from exc
    if not 1 <= result <= MAX_FIXTURE_CAP:
        raise argparse.ArgumentTypeError("fixture cap must be an integer from 1 through 50")
    return result


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dates", required=True)
    parser.add_argument("--fixture-cap", required=True, type=_fixture_cap)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def _hash_if_file(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _failure_chain(exc: BaseException) -> tuple[list[dict[str, str]], bool]:
    """Project a bounded, cause-first exception chain for failure-only receipts."""
    records: list[dict[str, str]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    truncated = False
    while current is not None:
        if id(current) in seen:
            truncated = True
            break
        if len(records) >= FAILURE_CHAIN_MAX_DEPTH:
            truncated = True
            break
        seen.add(id(current))
        records.append({
            "exception_type": type(current).__name__,
            "message": str(current)[:FAILURE_MESSAGE_MAX_CHARS],
        })
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return records, truncated


def _destination_preexists(path: Path) -> bool:
    """Return True if path exists in ANY form (file, dir, symlink, etc.)."""
    try:
        if os.path.lexists(path):
            return True
        return path.exists() or path.is_symlink()
    except OSError:
        return True


def _claim_absent_failure_destination(output_dir: Path) -> bool:
    """Atomically claim an absent failure destination child inside an existing envelope.

    Returns True only if this process successfully created the exact child
    directory with parents=False and exist_ok=False. Returns False without
    mutation if parent envelope is missing/symlinked/not a directory, or if
    the child already exists in ANY form (directory, file, symlink), or if
    filesystem creation fails.
    """
    try:
        parent = output_dir.parent
        if parent.is_symlink() or not parent.is_dir():
            return False
        if _destination_preexists(output_dir):
            return False
        output_dir.mkdir(parents=False, exist_ok=False)
        return True
    except (FileExistsError, OSError):
        return False


def _publish_capture_artifact(
    bundle: Mapping[str, Any],
    output_dir: Path,
) -> Path:
    """Publish the verified capture bundle into an immutable artifact directory.

    Wraps only write_capture_artifact publication failures into
    CAPTURE_ARTIFACT_PUBLICATION_FAILED while preserving the underlying
    cause. Pre-validates the bundle so contract/validation errors are
    not mislabeled as publication failures.
    """
    evidence.verify_capture_bundle(bundle)
    try:
        return evidence.write_capture_artifact(bundle, output_dir)
    except Exception as exc:
        publication_err = P30PairedCaptureError(
            f"CAPTURE_ARTIFACT_PUBLICATION_FAILED: {type(exc).__name__}: {exc}"
        )
        publication_err.failure_code = evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED  # type: ignore[attr-defined]
        raise publication_err from exc


def _safe_failure(output_dir: Path, *, exact_commit_sha: str | None, capture_id: str,
                  started_at: str, exc: BaseException) -> None:
    if not _claim_absent_failure_destination(output_dir):
        return
    failure_chain, failure_chain_truncated = _failure_chain(exc)
    value = {
        "schema_version": FAILURE_RECEIPT_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "destination_policy_id": evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID,
        "capture_id": capture_id,
        "status": "CAPTURE_FAILED",
        "started_at": started_at,
        "failed_at": _iso(_now()),
        "exact_commit_sha": exact_commit_sha,
        "failure_type": type(exc).__name__,
        "failure_message": str(exc)[:FAILURE_MESSAGE_MAX_CHARS],
        "failure_chain": failure_chain,
        "failure_chain_truncated": failure_chain_truncated,
        "share_code_operation": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "stake": False,
        "wager_placed": False,
    }
    failure_code = getattr(exc, "failure_code", None)
    if failure_code is not None:
        value["failure_code"] = failure_code
    elif "CAPTURE_ARTIFACT_PUBLICATION_FAILED" in str(exc):
        value["failure_code"] = evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED

    diagnostic_prefix = "P3.0-E1 source acquisition produced zero Router inputs: "
    failure_message = value["failure_message"]
    if isinstance(failure_message, str) and failure_message.startswith(diagnostic_prefix):
        try:
            diagnostic = json.loads(failure_message[len(diagnostic_prefix):])
        except (json.JSONDecodeError, TypeError):
            diagnostic = None
        if isinstance(diagnostic, dict):
            for field in (
                "failure_code",
                "provider_event_count",
                "provider_prematch_bookable_count",
                "provider_inplay_count",
                "provider_future_lead_eligible_count",
                "provider_too_close_count",
                "provider_discovery_source_method",
                "provider_discovery_strategy_id",
                "provider_discovery_observed_at",
                "source_viability",
            ):
                if field in diagnostic:
                    value[field] = diagnostic[field]
    try:
        (output_dir / "p3-0-capture-failure.json").write_bytes(evidence.canonical_json_bytes(value))
    except OSError:
        return



def _authority_projection(bindings: Any) -> dict[str, Any]:
    contracts = canonical_core.validate_canonical_core_contract()
    records = []
    for record in bindings.records:
        records.append({
            "responsibility_id": record.responsibility_id,
            "component_id": record.component_id,
            "contract_sha256": record.contract_sha256,
            "artifact_git_blob_sha": record.artifact_git_blob_sha,
            "allowed_profiles": list(record.allowed_profiles),
            "main_authority": record.main_authority,
        })
    return evidence.normalize_canonical_authority({
        "canonical_core_policy_id": bindings.policy_id,
        "canonical_core_contract_sha256": contracts["canonical_core_contract_sha256"],
        "authority_manifest_sha256": bindings.authority_manifest_sha256,
        "registry_canonical_sha256": bindings.registry_canonical_sha256,
        "authority_profile": bindings.authority_profile,
        "resolved_components": records,
    })


def _fixture_state(source: Any) -> dict[str, Any]:
    return evidence.normalize_canonical_fixture_state({
        "fixture_identity": source.fixture_identity,
        "provider_event_id": source.provider_event_id,
        "home_team": source.home_team,
        "away_team": source.away_team,
        "competition": source.competition,
        "kickoff_utc": _iso(source.kickoff_utc),
        "source_observed_at": _iso(source.source_observed_at),
        "fixture_reconciliation_sha256": source.fixture_reconciliation_sha256,
        "source_raw_sha256": source.source_raw_sha256,
        "source_manifest_sha256": source.source_manifest_sha256,
        "source_inventory_sha256": source.source_inventory_sha256,
    })


def _fixture_identity(source: Any) -> dict[str, Any]:
    state = _fixture_state(source)
    return evidence.normalize_fixture_identity({
        "fixture_identity": state["fixture_identity"],
        "fixture_identity_policy": FIXTURE_IDENTITY_POLICY,
        "home_team": state["home_team"],
        "away_team": state["away_team"],
        "home_source_id": None,
        "away_source_id": None,
        "competition_identity": None,
        "competition_name": state["competition"],
        "kickoff": state["kickoff_utc"],
        "fixture_source": "FOTMOB",
        "fixture_source_event_id": state["fixture_identity"].removeprefix("FOTMOB:"),
        "fixture_source_observed_at": None,
        "fixture_source_artifact_sha256": None,
        "fixture_source_manifest_sha256": None,
    })


def _legacy_fixture_id(source: Any) -> int:
    """Project the exact reconciled FotMob ID into the legacy fixture shape.

    The supported legacy FotMob path uses the provider's numeric match ID as
    ``fixture_id``.  Preserve that input semantic rather than passing the
    canonical ``FOTMOB:<id>`` wrapper through legacy referee/evidence code.
    """
    fixture_identity = source.fixture_identity
    if type(fixture_identity) is not str or not fixture_identity.startswith("FOTMOB:"):
        raise P30PairedCaptureError("canonical source fixture identity is not FotMob-bound")
    raw = fixture_identity.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) <= 0 or str(int(raw)) != raw:
        raise P30PairedCaptureError("canonical FotMob fixture identity is not numeric/canonical")
    return int(raw)


def _legacy_bookmaker_quotes(source: Any) -> list[dict[str, Any]]:
    """Project the exact captured SportyBet quote snapshot into the legacy
    BookmakerQuote input shape; no second bookmaker acquisition is performed.
    """
    context = source.price_all_bundle._context
    snapshot_id = context.source_inventory_sha256
    result: list[dict[str, Any]] = []
    for quote in build_current_shadow_exact_quotes(context):
        raw = quote.to_dict()
        result.append({
            "market_id": raw["market_id"],
            "outcome_id": raw["outcome_id"],
            "line": raw["line"],
            "bookmaker_odds": raw["decimal_odds"],
            "source": "SportyBet:P3_0_E1_EXACT_CURRENT_SHADOW_CAPTURE",
            "quote_snapshot_id": snapshot_id,
            "observed_at": raw["observed_at"],
            "is_genuine": True,
            "is_current": raw["bookable"] is True,
        })
    return result


def _legacy_override_fixture(source: Any) -> dict[str, Any]:
    state = _fixture_state(source)
    return {
        "fixture_id": _legacy_fixture_id(source),
        "league": state["competition"],
        "home_team": state["home_team"],
        "away_team": state["away_team"],
        "match_date": state["kickoff_utc"],
        "status": "NS",
        "data_source": "P3_0_E1_CURRENT_SHADOW_RECONCILED",
        "bookmaker_odds": _legacy_bookmaker_quotes(source),
    }


def _probability_projection(source: Any) -> dict[str, Any]:
    context = source.price_all_bundle._context
    bundle = market_probability_bundle_from_current_shadow_fixture_scan(context.scan)
    payload = bundle.to_dict()
    return evidence.normalize_probability_bundle({
        "policy_id": payload["policy_id"],
        "canonical_sha256": bundle.canonical_sha256,
        "payload": payload,
    })


def _provider_projection(source: Any) -> dict[str, Any]:
    context = source.price_all_bundle._context
    provider_contract = provider_market_semantics.validate_provider_market_semantics_contract()
    registry_sha = provider_market_semantics.validate_provider_market_semantics_registry(
        context.provider_registry
    )
    if registry_sha != context.provider_registry_sha256:
        raise P30PairedCaptureError("provider semantic registry identity drifted")
    registry = context.provider_registry
    return evidence.normalize_provider_semantics({
        "canonical_contract_sha256": provider_contract[
            "canonical_provider_market_semantics_contract_sha256"
        ],
        "registry_sha256": registry_sha,
        "registry_policy_id": registry.policy_id,
        "registry_evaluation_time": _iso(registry.evaluation_time),
        "provider_event_id": context.provider_event_id,
        "source_raw_sha256": context.source_raw_sha256,
        "source_manifest_sha256": context.source_manifest_sha256,
        "source_inventory_sha256": context.source_inventory_sha256,
        "fixture_reconciliation_sha256": context.fixture_reconciliation_sha256,
    })


def _quote_projection(source: Any) -> dict[str, Any]:
    context = source.price_all_bundle._context
    quotes = build_current_shadow_exact_quotes(context)
    rows = []
    for quote in quotes:
        raw = quote.to_dict()
        rows.append({**raw, "quote_identity_sha256": quote.identity_sha256})
    rows.sort(key=lambda row: row["quote_identity_sha256"])
    core = {
        "fixture_identity": context.fixture_identity,
        "provider_event_id": context.provider_event_id,
        "evaluation_time": _iso(context.evaluation_time),
        "quotes": rows,
    }
    return evidence.normalize_quote_snapshot({
        **core,
        "canonical_sha256": evidence.canonical_sha256(core),
    })


def _price_projection(source: Any) -> dict[str, Any]:
    payload = source.price_all_bundle.to_dict()
    return evidence.normalize_price_all_output({
        "owner_responsibility_id": "price_all_and_de_vig",
        "owner_component_id": "domain.price_all",
        "payload_kind": evidence.PRICE_OUTPUT_KIND,
        "payload_sha256": source.price_all_bundle.canonical_sha256,
        "payload": payload,
    })


def _router_projection(source: Any) -> dict[str, Any]:
    payload = source.router_decision.to_dict()
    return evidence.normalize_router_output({
        "owner_responsibility_id": "market_router",
        "owner_component_id": "domain.market_router_canonical_adapter",
        "payload_kind": evidence.ROUTER_OUTPUT_KIND,
        "payload_sha256": source.router_decision.decision_sha256,
        "payload": payload,
    })


def _source_artifacts(source: Any) -> list[dict[str, Any]]:
    return [{
        "fixture_identity": source.fixture_identity,
        "provider_event_id": source.provider_event_id,
        "source_raw_sha256": source.source_raw_sha256,
        "source_manifest_sha256": source.source_manifest_sha256,
        "source_inventory_sha256": source.source_inventory_sha256,
        "fixture_reconciliation_sha256": source.fixture_reconciliation_sha256,
    }]


def _legacy_pipeline() -> Any:
    # Importing the supported application constructor is deferred until explicit
    # runtime invocation; importing this module does not initialize DB/provider code.
    from build_acca import AccaBuilder
    return AccaBuilder(days_ahead=1).pipeline


def _collect_sources(
    *,
    repository_root: Path,
    lineage_main_sha: str,
    request_dates: tuple[str, ...],
    execute_live_network: bool = True,
) -> Any:
    return shadow_runner._acquire_router_inputs(
        repository_root=repository_root,
        lineage_main_sha=lineage_main_sha,
        request_dates=request_dates,
        capture_mode="P3_E1_PRE_ROUTER_CAPTURE",
        execute_live_network=execute_live_network,
    )



def classify_published_capture_result(
    bundle: Mapping[str, Any],
    *,
    capture_stage_causes: Sequence[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    fixture_records = bundle.get("fixture_records") or []
    fixture_count = len(fixture_records)
    complete_fixture_count = sum(
        row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE"
        for row in fixture_records
    )
    incomplete_fixture_count = fixture_count - complete_fixture_count
    missing_reason_counts: dict[str, int] = {}
    for row in fixture_records:
        for reason in row["completeness_receipt"].get("missing_reasons") or []:
            missing_reason_counts[reason] = missing_reason_counts.get(reason, 0) + 1

    causes = set(capture_stage_causes or ())
    legacy_exec = bundle.get("legacy_execution_identity") or {}
    if legacy_exec.get("legacy_observer_incompleteness"):
        causes.add(evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE)
    elif any(
        "MISSING_LEGACY_OUTPUT" in (row.get("completeness_receipt", {}).get("missing_reasons") or [])
        for row in fixture_records
    ):
        causes.add(evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE)

    if fixture_count > 0 and complete_fixture_count == fixture_count:
        payload = {
            "status": "P3_0_E1_CAPTURE_WRITTEN",
            "capture_id": bundle["capture_id"],
            "fixture_count": fixture_count,
            "complete_fixture_count": complete_fixture_count,
            "incomplete_fixture_count": 0,
            "canonical_sha256": bundle["canonical_sha256"],
        }
        return 0, payload
    else:
        payload = {
            "status": "P3_0_E1_CAPTURE_PARTIAL",
            "failure_code": evidence.PAIRED_CAPTURE_PARTIAL,
            "capture_id": bundle["capture_id"],
            "fixture_count": fixture_count,
            "complete_fixture_count": complete_fixture_count,
            "incomplete_fixture_count": incomplete_fixture_count,
            "missing_reason_counts": missing_reason_counts,
            "canonical_sha256": bundle["canonical_sha256"],
        }
        if causes:
            payload["capture_stage_causes"] = sorted(causes)
        return 1, payload


def build_offline_proof_bundle(*, partial: bool = False) -> dict[str, Any]:
    from domain.markets import MarketId
    from domain.market_probabilities import (
        MarketProbabilityBundle,
        MarketProbabilityDistribution,
        ProbabilityAvailability,
    )

    start = "2026-09-30T12:00:00.000000Z"
    end = "2026-09-30T12:04:00.000000Z"
    kickoff = "2026-10-01T15:00:00.000000Z"
    quote_time = "2026-09-30T12:01:00.000000Z"
    canonical_time = "2026-09-30T12:02:00.000000Z"
    legacy_time = "2026-09-30T12:03:00.000000Z"
    fixture_id_str = "FOTMOB:fixture-100"

    identity = {
        "fixture_identity": fixture_id_str,
        "fixture_identity_policy": FIXTURE_IDENTITY_POLICY,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "home_source_id": None,
        "away_source_id": None,
        "competition_identity": None,
        "competition_name": "Test League",
        "kickoff": kickoff,
        "fixture_source": "FOTMOB",
        "fixture_source_event_id": "fixture-100",
        "fixture_source_observed_at": None,
        "fixture_source_artifact_sha256": None,
        "fixture_source_manifest_sha256": None,
    }
    timing = {
        "legacy_evidence_observed_at": legacy_time,
        "legacy_evaluation_time": legacy_time,
        "probability_evaluation_time": canonical_time,
        "provider_quote_observed_at": quote_time,
        "canonical_price_all_evaluation_time": canonical_time,
        "canonical_router_evaluation_time": canonical_time,
        "kickoff_time": kickoff,
    }
    fallback_shas = {
        "provider_market_semantics": ("737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830", "46eaf64b6704e1b7b47123a9a182346e0403cbe6"),
        "price_all_and_de_vig": ("30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425", "cf7214a6103d91a2974e3eb00c705f65c841d458"),
        "market_router": ("85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32", "3011b65fcd62e5ae91fcede967b8cba4f85cdda7"),
        "portfolio_optimizer": ("916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c", "d600d5d88baf5628df23441a9216c2fc68352e45"),
        "delivery_share_code_transport": ("ac73deca0834187480c656482a78f9048381fe2f07abacfe10b84d30c73502cb", "28c44656915607315e0227f54bcff7cc7af103c7"),
    }
    authority_records = []
    for resp in sorted(evidence.EXPECTED_COMPONENTS):
        contract, blob = fallback_shas[resp]
        authority_records.append({
            "responsibility_id": resp,
            "component_id": evidence.EXPECTED_COMPONENTS[resp],
            "contract_sha256": contract,
            "artifact_git_blob_sha": blob,
            "allowed_profiles": ["SHADOW"],
            "main_authority": False,
        })
    authority = {
        "canonical_core_policy_id": "ATHENA_SHARED_CANONICAL_CORE_V1",
        "canonical_core_contract_sha256": "af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a",
        "authority_manifest_sha256": "d" * 64,
        "registry_canonical_sha256": "e" * 64,
        "authority_profile": "SHADOW",
        "resolved_components": authority_records,
    }
    legacy_input = {
        "fixture_id": fixture_id_str,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "home_id": 1,
        "away_id": 2,
        "match_date": kickoff,
        "data_source": "P3_0_E1_CURRENT_SHADOW_RECONCILED",
        "is_knockout": False,
    }
    analysis = {
        "decision_status": "ANALYTICAL_CANDIDATE",
        "recommended_analytical_verdict": "HOME_WIN",
        "bookmaker_odds": None,
        "viable_markets": [{"verdict": "HOME_WIN", "prob": 0.6, "kelly_stake_pct": 5.0}],
        "accumulator_eligible_selection": None,
        "no_bet_reasons": [],
        "evidence_report": {
            "final_decision": "ANALYTICAL_CANDIDATE",
            "decision_reasons": ["test"],
            "possession": {"home": 55.0, "away": 45.0},
            "market_evaluations": [{"market_id": "MATCH_RESULT", "kelly_stake_pct": 5.0}],
        },
    }
    legacy_output = evidence.project_legacy_output(
        analysis,
        analysis,
        {
            "fixture_id": fixture_id_str,
            "fixture": "Alpha FC vs Beta FC",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "league": "Test League",
            "match_date": kickoff,
            "decision_status": "ANALYTICAL_CANDIDATE",
            "verdict": "HOME_WIN",
            "no_bet_reasons": ["legacy runtime authorization gate"],
            "evidence_report": analysis["evidence_report"],
            "source": "P3_0_E1_CURRENT_SHADOW_RECONCILED",
        },
    )
    fixture_state = {
        "fixture_identity": fixture_id_str,
        "provider_event_id": "100",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "competition": "Test League",
        "kickoff_utc": kickoff,
        "source_observed_at": quote_time,
        "fixture_reconciliation_sha256": "6" * 64,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
    }
    markets = tuple(
        MarketProbabilityDistribution(
            market_id=m,
            availability=ProbabilityAvailability.BLOCKED,
            topology=None,
            probability_method=None,
            probability_input_namespace=None,
            calibration_status=None,
            event_probabilities=(),
            settlement_distributions=(),
            blocker_reason="TEST_BLOCKED_WITHOUT_FABRICATION",
            source_projection_sha256=(f"{idx + 1:x}" * 64)[:64],
        )
        for idx, m in enumerate(MarketId)
    )
    prob_bundle = MarketProbabilityBundle(
        fixture_identity=fixture_id_str,
        score_grid=None,
        markets=markets,
        specialist_outputs=(),
        model_evidence={"artifact_sha256": "1" * 64},
    )
    probability = {
        "policy_id": prob_bundle.to_dict()["policy_id"],
        "canonical_sha256": prob_bundle.canonical_sha256,
        "payload": prob_bundle.to_dict(),
    }
    provider = {
        "canonical_contract_sha256": "737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830",
        "registry_sha256": "2" * 64,
        "registry_policy_id": "PRB_EXACT_CURRENT_SPORTYBET_SEMANTIC_POLICIES_V1",
        "registry_evaluation_time": canonical_time,
        "provider_event_id": "100",
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
    }
    def _compact_sha(v: Any) -> str:
        raw = json.dumps(v, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
    quote_row = {
        "fixture_identity": fixture_id_str,
        "provider_event_id": "100",
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
        "line": None,
        "provider_line": None,
        "provider_market_id": "1",
        "provider_market_name": "1X2",
        "provider_specifier": None,
        "provider_outcome_id": "1",
        "provider_outcome_name": "Home",
        "odds_raw": "1.50",
        "decimal_odds": 1.5,
        "observed_at": quote_time,
        "kickoff_utc": kickoff,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
        "provider_semantic_status": "SUPPORTED",
        "provider_registry_sha256": "2" * 64,
        "provider_observation_sha256": "8" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
        "current_mapping_rebind_sha256": None,
        "bridge_bundle_sha256": None,
        "bookable": True,
    }
    quote_row["quote_identity_sha256"] = _compact_sha(quote_row)
    quote_core = {
        "fixture_identity": fixture_id_str,
        "provider_event_id": "100",
        "evaluation_time": canonical_time,
        "quotes": [quote_row],
    }
    quote = {**quote_core, "canonical_sha256": evidence.canonical_sha256(quote_core)}
    price_result = {
        "fixture_identity": fixture_id_str,
        "market_id": "MATCH_RESULT",
        "outcome_id": "HOME",
        "line": None,
        "disposition": "PRICED",
        "model_probability": 0.6,
        "decimal_odds": 1.5,
        "quote_identity_sha256": quote_row["quote_identity_sha256"],
        "provider_event_id": "100",
        "prc_scan_sha256": "9" * 64,
        "prc_assessment_sha256": "a" * 64,
        "provider_registry_sha256": "2" * 64,
        "fixture_reconciliation_sha256": "6" * 64,
        "source_raw_sha256": "3" * 64,
        "source_manifest_sha256": "4" * 64,
        "source_inventory_sha256": "5" * 64,
    }
    price_payload = {
        "schema_version": 2,
        "dataset_name": "athena-current-shadow-all-market-price-all-router-v2",
        "fixture_identity": fixture_id_str,
        "evaluation_time": canonical_time,
        "results": [price_result],
        "authority": {"staking": False, "bet": False, "wager_placed": False},
        "wager_placed": False,
    }
    price = {
        "owner_responsibility_id": "price_all_and_de_vig",
        "owner_component_id": "domain.price_all",
        "payload_kind": evidence.PRICE_OUTPUT_KIND,
        "payload_sha256": _compact_sha(price_payload),
        "payload": price_payload,
    }
    opp_id = "b" * 64
    router_payload = {
        "schema_version": 2,
        "dataset_name": "athena-current-shadow-all-market-price-all-router-v2",
        "fixture_identity": fixture_id_str,
        "status": "SELECTED",
        "selected_opportunity_id": opp_id,
        "runner_up_opportunity_id": None,
        "strongest_rejected_opportunity_id": None,
        "opportunities": [{
            "opportunity_id": opp_id,
            "price_result": price_result,
            "eligibility": "ELIGIBLE",
            "rejection_reasons": [],
        }],
        "price_all_bundle_sha256": price["payload_sha256"],
        "router_policy_id": "TEST_ROUTER_POLICY",
        "authority": {"staking": False, "bet": False, "wager_placed": False},
        "value_first_selected_opportunity_id": opp_id,
        "value_first_runner_up_opportunity_id": None,
        "value_first_counterfactual_opportunity_id": None,
        "wager_placed": False,
    }
    router = {
        "owner_responsibility_id": "market_router",
        "owner_component_id": "domain.market_router_canonical_adapter",
        "payload_kind": evidence.ROUTER_OUTPUT_KIND,
        "payload_sha256": _compact_sha(router_payload),
        "payload": router_payload,
    }

    record_kwargs = dict(
        fixture_capture_id="FOTMOB-fixture-100",
        capture_id="capture-offline-proof",
        capture_started_at=start,
        capture_completed_at=end,
        legacy_identity=None if partial else identity,
        canonical_identity=identity,
        timing=timing,
        canonical_authority=authority,
        legacy_input=None if partial else legacy_input,
        legacy_output=None if partial else legacy_output,
        canonical_fixture_state=fixture_state,
        probability_bundle=probability,
        provider_semantics=provider,
        quote_snapshot=quote,
        price_all_output=price,
        router_output=router,
    )
    record = evidence.build_fixture_record(**record_kwargs)

    legacy_exec = {
        "policy_id": POLICY_ID,
        "supported_path": "AccaBuilder->AnalysisPipeline.run_pipeline_snapshot",
    }
    if partial:
        legacy_exec["legacy_observer_incompleteness"] = [{
            "failure_code": evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE,
            "fixture_identity": fixture_id_str,
            "provider_event_id": "100",
            "observation_count": 0,
            "exported_row_count": 0,
        }]

    bundle = evidence.build_capture_bundle(
        repository_commit_sha="c" * 40,
        capture_id="capture-offline-proof",
        capture_started_at=start,
        capture_completed_at=end,
        requested_dates=["20261001"],
        legacy_execution_identity=legacy_exec,
        canonical_execution_identity={"path": "Current Shadow Price-All -> Router"},
        authority_state={"main_authority": False, "authority_profile": "SHADOW", "wager_placed": False},
        source_artifacts=[{
            "fixture_identity": fixture_id_str,
            "provider_event_id": "100",
            "source_raw_sha256": "3" * 64,
            "source_manifest_sha256": "4" * 64,
            "source_inventory_sha256": "5" * 64,
            "fixture_reconciliation_sha256": "6" * 64,
        }],
        fixture_records=[record],
    )
    return bundle


__all__ = tuple(name for name in globals() if not name.startswith("__"))
