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


def _safe_failure(output_dir: Path, *, exact_commit_sha: str | None, capture_id: str,
                  started_at: str, exc: BaseException) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    failure_chain, failure_chain_truncated = _failure_chain(exc)
    value = {
        "schema_version": FAILURE_RECEIPT_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
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
    (output_dir / "p3-0-capture-failure.json").write_bytes(evidence.canonical_json_bytes(value))


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


def _collect_sources(*, repository_root: Path, lineage_main_sha: str,
                     request_dates: tuple[str, ...]) -> Any:
    original_issuer = shadow_runner._issue_current_fixture_sources
    shadow_runner._issue_current_fixture_sources = (
        lambda *, repository_root: shadow_daily._issue_exact_fixture_sources(
            repository_root=repository_root, request_dates=request_dates
        )
    )
    try:
        return shadow_runner._acquire_router_inputs(
            repository_root=repository_root,
            lineage_main_sha=lineage_main_sha,
        )
    finally:
        shadow_runner._issue_current_fixture_sources = original_issuer



__all__ = tuple(name for name in globals() if not name.startswith("__"))
