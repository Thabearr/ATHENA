"""Canonical provider-market-semantics facade (P2.0).

This is a promotion seam, not a second semantic table.  Every provider-native
market, outcome, specifier, settlement, freshness and source-evidence rule is
delegated to the reviewed current-provider implementation while P2 migration is
in progress.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_PROVIDER_MARKET_SEMANTICS_V1"
IMPLEMENTATION_ID = "domain.current_sportybet_semantic_registry"
IMPLEMENTATION_POLICY_ID = "PRB_EXACT_CURRENT_SPORTYBET_SEMANTIC_POLICIES_V1"
IMPLEMENTATION_SCHEMA_VERSION = 1
IMPLEMENTATION_DATASET_NAME = "athena-current-sportybet-semantic-readiness-registry-v1"
IMPLEMENTATION_CONTRACT_VERSION = 1
IMPLEMENTATION_GIT_BLOB_SHA = "646bf93549d0d859f00e1d42ba72aaa17a84a6e7"
DELEGATED_SOURCE_CONTRACT_IDENTITIES = MappingProxyType(
    {
        "event_detail": "b888cebab6447cd4072d823dab67b56f1f75f72eb72d67b692d47a4378b27555",
        "event_discovery": "64c7a2b71304f94a39de7e608be1f76a10e14a1a52a338f89d1c695ba0e5f1ee",
        "reviewed_canonical_mapping": "de022fd931313fa8d3c2c093ff0cb9b12f2c0f1ba0d9adc4b646c94dfd306e96",
        "early_payout_settlement": "921db06634ba4d210f100591c0c9acda5ae44db49452936e2229095530c01f76",
        "pr258_market18_reconciliation": "PR258_REVIEWED_MARKET18_TOTAL_GOALS_TO_OVER_UNDER_EXACT_NATIVE_ID_SPECIFIER_OUTCOME_LABEL_V1",
        "pr258_upcoming_discovery_source_blob": "fe132268d45ef61dac1316a2ee92f0f46cab1084",
    }
)
CANONICAL_MARKET_IDS = (
    "MATCH_RESULT", "ASIAN_HANDICAP", "TOTAL_GOALS", "DRAW_OR_OVER_2_5",
    "AWAY_OR_OVER_2_5", "HOME_OR_OVER_2_5", "HOME_WIN_EITHER_HALF",
    "AWAY_WIN_EITHER_HALF", "DOUBLE_CHANCE", "BTTS", "DRAW_NO_BET",
    "HOME_WIN_TO_NIL", "AWAY_WIN_TO_NIL", "MATCH_RESULT_1UP", "MATCH_RESULT_2UP",
)
PROVIDER_SEMANTIC_STATUS_VOCABULARY = (
    "SUPPORTED", "SUPPORTED_WITH_EXACT_LINE_POLICY", "CURRENT_PROVIDER_UNAVAILABLE/UNPROVEN",
)
SETTLEMENT_CLASS_VOCABULARY = (
    "REGULATION_1X2_PARTITION", "TOTALS_EXACT_LINE_SETTLEMENT",
    "RESULT_OR_TOTAL_UNION_COMPLEMENT", "WEH_COMPLEMENTARY_BINARY",
    "DOUBLE_CHANCE_OVERLAPPING_EVENTS", "BTTS_COMPLEMENTARY_BINARY", "DNB_WIN_PUSH_LOSS",
    "WIN_TO_NIL_COMPLEMENTARY_BINARY", "EARLY_PAYOUT_OVERLAPPING_EVENTS",
    "ASIAN_HANDICAP_FULL_SETTLEMENT",
)
EVIDENCE_FRESHNESS_VOCABULARY = (
    "CURRENT", "OBSERVED", "NO_EVIDENCE", "STALE", "FUTURE_DATED",
    "TOO_CLOSE_TO_KICKOFF", "NOT_PREMATCH_BOOKABLE", "CONFLICTING",
)
DELEGATED_AUTHORITY = MappingProxyType(
    {
        "production_model": False, "production_probability": False, "phase6": False,
        "production_price_all": False, "production_market_router": False,
        "production_portfolio": False, "production_selection": False,
        "sportybet_execution": False, "staking": False, "bet": False,
        "wager_placed": False,
    }
)


class ProviderMarketSemanticsError(ValueError):
    """Canonical provider-market-semantics evidence is unavailable or drifted."""


def canonical_json_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderMarketSemanticsError("canonical serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _contract_payload() -> dict[str, Any]:
    """Stable facts of the delegated semantic contract, not a copied table."""
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "implementation_id": IMPLEMENTATION_ID,
        "implementation_policy_id": IMPLEMENTATION_POLICY_ID,
        "implementation_schema_version": IMPLEMENTATION_SCHEMA_VERSION,
        "implementation_dataset_name": IMPLEMENTATION_DATASET_NAME,
        "implementation_contract_version": IMPLEMENTATION_CONTRACT_VERSION,
        "implementation_git_blob_sha": IMPLEMENTATION_GIT_BLOB_SHA,
        "source_contract_identities": dict(DELEGATED_SOURCE_CONTRACT_IDENTITIES),
        "canonical_market_ids": list(CANONICAL_MARKET_IDS),
        "provider_semantic_status_vocabulary": list(PROVIDER_SEMANTIC_STATUS_VOCABULARY),
        "settlement_class_vocabulary": list(SETTLEMENT_CLASS_VOCABULARY),
        "evidence_freshness_vocabulary": list(EVIDENCE_FRESHNESS_VOCABULARY),
        "delegated_authority": dict(DELEGATED_AUTHORITY),
        "fuzzy_provider_mapping": False,
        "price_all_authority": False,
        "market_router_authority": False,
        "portfolio_authority": False,
        "share_code_transport_authority": False,
        "provider_acquisition_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
    }


def calculate_provider_market_semantics_contract_sha256() -> str:
    return canonical_sha256(_contract_payload())


# Filled from the deterministic payload above.  It intentionally changes only
# when reviewed delegated semantic facts change.
EXPECTED_CONTRACT_SHA256 = "737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830"


def _implementation() -> Any:
    """Import only when semantics are actually consumed or validated.

    The delegated implementation verifies retained source bytes at import time.
    Keeping this import lazy avoids converting a pre-existing local capture/CRLF
    condition into authority while still making all real facade operations fail
    closed when that reviewed evidence cannot be verified.
    """
    try:
        from domain import current_sportybet_semantic_registry as delegate
    except Exception as exc:
        raise ProviderMarketSemanticsError(
            "reviewed delegated provider semantics are unavailable"
        ) from exc
    return delegate


def _implementation_git_blob_sha(delegate: Any) -> str:
    """Return the delegated source identity using Git's filtered blob rules."""
    path = getattr(delegate, "__file__", None)
    if type(path) is not str or not path.endswith(".py"):
        raise ProviderMarketSemanticsError("delegated provider semantics has no source artifact")
    source_path = Path(path).resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        relative_path = source_path.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise ProviderMarketSemanticsError(
            "delegated provider semantics source is outside repository"
        ) from exc
    try:
        completed = subprocess.run(
            [
                "git", "-C", str(repository_root), "hash-object", "--path",
                relative_path, "--filters", str(source_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProviderMarketSemanticsError(
            "delegated provider semantics Git blob verification failed"
        ) from exc
    digest = completed.stdout.strip()
    if completed.returncode != 0 or len(digest) != 40 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ProviderMarketSemanticsError(
            "delegated provider semantics Git blob verification failed"
        )
    return digest


def validate_provider_market_semantics_contract() -> Mapping[str, Any]:
    """Fail closed if the reviewed implementation or its semantic facts drift."""
    actual = calculate_provider_market_semantics_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise ProviderMarketSemanticsError("canonical provider semantics contract drifted")
    delegate = _implementation()
    if _implementation_git_blob_sha(delegate) != IMPLEMENTATION_GIT_BLOB_SHA:
        raise ProviderMarketSemanticsError("delegated provider semantics source artifact drifted")
    if delegate.POLICY_ID != IMPLEMENTATION_POLICY_ID:
        raise ProviderMarketSemanticsError("delegated provider semantics policy drifted")
    if delegate.SCHEMA_VERSION != IMPLEMENTATION_SCHEMA_VERSION:
        raise ProviderMarketSemanticsError("delegated provider semantics schema drifted")
    if delegate.DATASET_NAME != IMPLEMENTATION_DATASET_NAME or delegate.CONTRACT_VERSION != IMPLEMENTATION_CONTRACT_VERSION:
        raise ProviderMarketSemanticsError("delegated provider semantics identity drifted")
    if dict(delegate.SOURCE_CONTRACT_IDENTITIES) != dict(DELEGATED_SOURCE_CONTRACT_IDENTITIES):
        raise ProviderMarketSemanticsError("delegated provider source contracts drifted")
    if tuple(item.value for item in delegate.MarketId) != CANONICAL_MARKET_IDS:
        raise ProviderMarketSemanticsError("delegated canonical market vocabulary drifted")
    if tuple(item.value for item in delegate.ProviderSemanticStatus) != PROVIDER_SEMANTIC_STATUS_VOCABULARY:
        raise ProviderMarketSemanticsError("delegated status vocabulary drifted")
    if tuple(item.value for item in delegate.SettlementClass) != SETTLEMENT_CLASS_VOCABULARY:
        raise ProviderMarketSemanticsError("delegated settlement vocabulary drifted")
    if tuple(item.value for item in delegate.EvidenceFreshnessState) != EVIDENCE_FRESHNESS_VOCABULARY:
        raise ProviderMarketSemanticsError("delegated freshness vocabulary drifted")
    if dict(delegate._AUTHORITY) != dict(DELEGATED_AUTHORITY):
        raise ProviderMarketSemanticsError("delegated authority drifted")
    if "fuzzy" in delegate.POLICY_ID.lower():
        raise ProviderMarketSemanticsError("fuzzy provider mapping is forbidden")
    return MappingProxyType(
        {
            "canonical_provider_market_semantics_contract_sha256": actual,
            "implementation_id": IMPLEMENTATION_ID,
            "implementation_policy_id": IMPLEMENTATION_POLICY_ID,
            "implementation_schema_version": IMPLEMENTATION_SCHEMA_VERSION,
            "implementation_git_blob_sha": IMPLEMENTATION_GIT_BLOB_SHA,
            "source_contract_identities": MappingProxyType(
                dict(DELEGATED_SOURCE_CONTRACT_IDENTITIES)
            ),
        }
    )


# Exact type aliases preserve the established semantic representations.  The
# facade adds no provider-native mapping or looser caller-facing representation.
_DELEGATED_PUBLIC_NAMES = frozenset(
    {
        "ProviderSemanticStatus", "SettlementClass", "EvidenceFreshnessState",
        "ProviderEventEvidence", "ProviderSemanticObservation", "ProviderCoverageRecord",
        "CurrentSportyBetSemanticRegistry", "SportyBetSemanticRegistry",
    }
)


def __getattr__(name: str) -> Any:
    if name in _DELEGATED_PUBLIC_NAMES:
        return getattr(_implementation(), name)
    raise AttributeError(name)


def provider_policy(market_id: Any) -> Mapping[str, Any]:
    validate_provider_market_semantics_contract()
    return _implementation().provider_policy(market_id)


def replay_event_evidence(evidence: ProviderEventEvidence) -> ProviderEventEvidence:
    validate_provider_market_semantics_contract()
    return _implementation().replay_event_evidence(evidence)


def build_provider_market_semantics_registry(
    evidence: Sequence[ProviderEventEvidence], *, evaluation_time: Any, scan_cap: int = 20,
    scan_attempts: int | None = None,
) -> Any:
    """Build exact semantic readiness from already-captured evidence only."""
    validate_provider_market_semantics_contract()
    return _implementation().build_registry(
        evidence,
        evaluation_time=evaluation_time,
        scan_cap=scan_cap,
        scan_attempts=scan_attempts,
    )


def validate_provider_market_semantics_registry(
    value: Any,
) -> str:
    validate_provider_market_semantics_contract()
    try:
        return _implementation().validate_registry(value)
    except Exception as exc:
        raise ProviderMarketSemanticsError("delegated provider semantics replay failed") from exc


__all__ = [
    "EvidenceFreshnessState",
    "EXPECTED_CONTRACT_SHA256",
    "IMPLEMENTATION_ID",
    "IMPLEMENTATION_GIT_BLOB_SHA",
    "IMPLEMENTATION_POLICY_ID",
    "IMPLEMENTATION_SCHEMA_VERSION",
    "DELEGATED_SOURCE_CONTRACT_IDENTITIES",
    "POLICY_ID",
    "ProviderCoverageRecord",
    "ProviderEventEvidence",
    "ProviderMarketSemanticsError",
    "ProviderSemanticObservation",
    "ProviderSemanticStatus",
    "SCHEMA_VERSION",
    "SettlementClass",
    "build_provider_market_semantics_registry",
    "calculate_provider_market_semantics_contract_sha256",
    "canonical_json_bytes",
    "canonical_sha256",
    "provider_policy",
    "replay_event_evidence",
    "validate_provider_market_semantics_contract",
    "validate_provider_market_semantics_registry",
]
