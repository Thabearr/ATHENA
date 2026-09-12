"""Hardened P3.0-E1 evidence contract implementation.

This module has evidence authority only. It validates explicit projections,
proves deterministic lineage, and writes immutable artifacts. It never acquires
providers, computes football probabilities, prices markets, routes selections,
optimizes a portfolio, creates a share code, or grants MAIN authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import tempfile
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_P3_0_COMPARISON_EVIDENCE_V1"
AS_OF_PROOF_POLICY_ID = "P3_0_SINGLE_PROSPECTIVE_CAPTURE_WINDOW_LINEAGE_V1"
PRICE_OUTPUT_KIND = "P2_1_SHADOW_COMPATIBILITY_PRICE_ALL_CANONICAL_OWNER_GUARDED_V1"
ROUTER_OUTPUT_KIND = "P2_1_SHADOW_COMPATIBILITY_ROUTER_CANONICAL_OWNER_GUARDED_V1"
SHADOW_PRICE_DATASET_NAME = "athena-current-shadow-all-market-price-all-router-v2"

JOIN_STATES = frozenset({
    "EXACT_SAME_FIXTURE_PROVEN", "LEGACY_ONLY", "CANONICAL_ONLY",
    "IDENTITY_AMBIGUOUS", "KICKOFF_MISMATCH", "COMPETITION_MISMATCH",
    "AS_OF_NOT_PROVEN", "EVIDENCE_INCOMPLETE",
})
COMPLETENESS_STATES = frozenset(
    {"P3_0_CAPTURE_COMPLETE", "P3_0_CAPTURE_PARTIAL", "P3_0_CAPTURE_UNUSABLE"}
)
FIXTURE_IDENTITY_KEYS = frozenset({
    "fixture_identity", "fixture_identity_policy", "home_team", "away_team",
    "home_source_id", "away_source_id", "competition_identity",
    "competition_name", "kickoff", "fixture_source", "fixture_source_event_id",
    "fixture_source_observed_at", "fixture_source_artifact_sha256",
    "fixture_source_manifest_sha256",
})
TIMING_KEYS = frozenset({
    "legacy_evidence_observed_at", "legacy_evaluation_time",
    "probability_evaluation_time", "provider_quote_observed_at",
    "canonical_price_all_evaluation_time", "canonical_router_evaluation_time",
    "kickoff_time",
})
CANONICAL_AUTHORITY_KEYS = frozenset({
    "canonical_core_policy_id", "canonical_core_contract_sha256",
    "authority_manifest_sha256", "registry_canonical_sha256",
    "authority_profile", "resolved_components",
})
EXPECTED_COMPONENTS = {
    "provider_market_semantics": "domain.provider_market_semantics",
    "price_all_and_de_vig": "domain.price_all",
    "market_router": "domain.market_router_canonical_adapter",
    "portfolio_optimizer": "domain.portfolio_optimizer",
    "delivery_share_code_transport": "domain.sportybet_share_code",
}
EXPECTED_CANONICAL_CORE_POLICY_ID = "ATHENA_SHARED_CANONICAL_CORE_V1"
EXPECTED_CANONICAL_CORE_CONTRACT_SHA256 = "af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a"
EXPECTED_PROVIDER_SEMANTICS_CONTRACT_SHA256 = "737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830"
EXPECTED_PROVIDER_REGISTRY_POLICY_ID = "PRB_EXACT_CURRENT_SPORTYBET_SEMANTIC_POLICIES_V1"
EXPECTED_COMPONENT_IDENTITIES = {
    "provider_market_semantics": ("737a463bd26a5333a45fe50aef21fd3b4a76ec3395041e56f3a105f32bd0f830", "46eaf64b6704e1b7b47123a9a182346e0403cbe6"),
    "price_all_and_de_vig": ("30481bc9ebf442f0e664bcd14d2c6cd18026a42a35083d143db6366837b3d425", "cf7214a6103d91a2974e3eb00c705f65c841d458"),
    "market_router": ("85b4b5c712154f7d4708eb53e9cadfcb7c65dc21bdb12cd94cf1b8cd48795e32", "3011b65fcd62e5ae91fcede967b8cba4f85cdda7"),
    "portfolio_optimizer": ("916247c4a891e3c0a2b8205b9d33000987471a54107f2b3d508c8e5ab1e9a99c", "d600d5d88baf5628df23441a9216c2fc68352e45"),
    "delivery_share_code_transport": ("ac73deca0834187480c656482a78f9048381fe2f07abacfe10b84d30c73502cb", "28c44656915607315e0227f54bcff7cc7af103c7"),
}
REQUIRED_CANONICAL_RESPONSIBILITIES = frozenset(EXPECTED_COMPONENTS)

_LEGACY_INPUT_FIELDS = frozenset({
    "fixture_id", "home_team", "away_team", "home_id", "away_id",
    "match_date", "data_source", "is_knockout", "current_home_form",
    "current_away_form", "current_form_observed_at", "bookmaker_odds",
    "home_pre_elo", "away_pre_elo",
})
_LEGACY_ANALYSIS_FIELDS = frozenset({
    "decision_status", "legacy_decision_status_before_runtime_gate",
    "recommended_analytical_verdict", "edge_differential",
    "edge_is_bookmaker_value", "bookmaker_odds", "bookmaker_probability",
    "edge_pp", "upset_alert", "risk_score", "stale_data",
    "viable_markets", "accumulator_eligible_selection", "reasoning_verdicts",
    "no_bet_reasons", "evidence_report", "runtime_authorization_state",
    "runtime_authorization_reasons",
})
_LEGACY_EXPORTED_FIELDS = frozenset({
    "fixture_id", "fixture", "home_team", "away_team", "league", "match_date",
    "decision_status", "legacy_decision_status_before_runtime_gate",
    "runtime_authorization_state", "runtime_authorization_reasons", "upset_alert",
    "risk_score", "stale_data", "edge", "edge_is_bookmaker_value",
    "bookmaker_odds", "bookmaker_probability", "edge_pp",
    "verdict", "viable_markets", "accumulator_eligible_selection",
    "no_bet_reasons", "evidence_report", "source",
})

_FORBIDDEN_EXACT_KEYS = frozenset({
    "authorization", "proxy_authorization", "bearer", "password", "passwd",
    "secret", "api_key", "apikey", "access_token", "refresh_token",
    "session", "session_id", "sessionid", "cookie", "cookies", "cookie_value",
    "set_cookie", "wallet", "wallet_id", "account_balance", "stake_amount",
    "wager_amount", "share_code", "sharecode", "share_url", "shareurl",
})
_FORBIDDEN_TOKENS = frozenset({
    "authorization", "bearer", "password", "passwd", "secret", "token",
    "cookie", "session", "wallet", "wager", "staking",
})
_ALLOWED_FALSE_SAFETY_KEYS = frozenset({
    "bet", "cookies", "login", "main_authority", "portfolio",
    "provider_acquisition", "share_code_generation", "share_code_invoked",
    "share_code_operation", "sportybet_cookie_used", "sportybet_login_used",
    "sportybet_wallet_used", "stake", "stake_submitted", "staking", "wallet",
    "wager", "wager_placed",
})
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CAPTURE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


class P30ComparisonEvidenceError(ValueError):
    """Raised when evidence cannot be represented safely and exactly."""


def _utc_iso(value: Any, label: str) -> tuple[str, datetime]:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise P30ComparisonEvidenceError(f"{label} must be exact non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P30ComparisonEvidenceError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise P30ComparisonEvidenceError(f"{label} must be timezone-aware")
    parsed = parsed.astimezone(timezone.utc)
    canonical = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return canonical, parsed


def _sha40(value: Any, label: str) -> str:
    if type(value) is not str or _HEX40.fullmatch(value) is None:
        raise P30ComparisonEvidenceError(f"{label} must be lowercase 40-hex Git SHA")
    return value


def _sha64(value: Any, label: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise P30ComparisonEvidenceError(f"{label} must be lowercase 64-hex SHA-256")
    return value


def _tokenize_key(key: str) -> tuple[str, ...]:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).casefold().replace("-", "_")
    return tuple(token for token in re.split(r"[^a-z0-9]+", snake) if token)


def _reject_sensitive_key(key: str, location: str, value: Any = None) -> None:
    normalized = key.casefold().replace("-", "_")
    forbidden = normalized in _FORBIDDEN_EXACT_KEYS or any(
        token in _FORBIDDEN_TOKENS for token in _tokenize_key(key)
    )
    if forbidden and value is False and normalized in _ALLOWED_FALSE_SAFETY_KEYS:
        return
    if forbidden:
        raise P30ComparisonEvidenceError(f"sensitive evidence key is forbidden at {location}")


def _validate_json_value(value: Any, location: str = "$") -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise P30ComparisonEvidenceError(f"non-finite number at {location}")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{location}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise P30ComparisonEvidenceError(f"non-string JSON key at {location}")
            _reject_sensitive_key(key, f"{location}.{key}", item)
            _validate_json_value(item, f"{location}.{key}")
        return
    raise P30ComparisonEvidenceError(f"non-JSON value at {location}: {type(value).__name__}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise P30ComparisonEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_bytes(raw: bytes) -> Any:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                P30ComparisonEvidenceError(f"non-finite JSON constant: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P30ComparisonEvidenceError("invalid UTF-8 canonical JSON") from exc
    _validate_json_value(value)
    return value


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    try:
        return (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8") + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise P30ComparisonEvidenceError("value is not canonically serializable") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _compact_sha256(value: Any) -> str:
    _validate_json_value(value)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _plain_mapping(value: Mapping[str, Any] | None, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise P30ComparisonEvidenceError(f"{label} must be a plain JSON object or null")
    _validate_json_value(value, label)
    return load_json_bytes(canonical_json_bytes(value))


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    if set(value) != expected:
        raise P30ComparisonEvidenceError(
            f"{label} keys drifted; missing={sorted(expected-set(value))}, "
            f"unexpected={sorted(set(value)-expected)}"
        )


def _quarantine_legacy_value(value: Any, location: str) -> Any:
    if type(value) is dict:
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"kelly_stake_pct", "legacy_kelly_stake_pct_before_runtime_gate"}:
                continue
            _reject_sensitive_key(key, f"{location}.{key}", item)
            result[key] = _quarantine_legacy_value(item, f"{location}.{key}")
        return result
    if type(value) is list:
        return [_quarantine_legacy_value(item, f"{location}[]") for item in value]
    _validate_json_value(value, location)
    return value


def _project_allowed(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise P30ComparisonEvidenceError(f"{label} must be a plain JSON object")
    projected = {key: _quarantine_legacy_value(value[key], f"{label}.{key}") for key in sorted(set(value) & allowed)}
    _validate_json_value(projected, label)
    return load_json_bytes(canonical_json_bytes(projected))


def project_legacy_input(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _project_allowed(value, _LEGACY_INPUT_FIELDS, "legacy_input")
    for key in ("fixture_id", "home_team", "away_team", "match_date"):
        if key not in item or item[key] in (None, ""):
            raise P30ComparisonEvidenceError(f"legacy_input.{key} is required")
    return item


def _project_legacy_analysis(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    item = _project_allowed(value, _LEGACY_ANALYSIS_FIELDS, label)
    if "decision_status" not in item or type(item["decision_status"]) is not str:
        raise P30ComparisonEvidenceError(f"{label}.decision_status is required")
    if "evidence_report" not in item or type(item["evidence_report"]) is not dict:
        raise P30ComparisonEvidenceError(f"{label}.evidence_report is required")
    return item


def project_legacy_output(
    pre_gate: Mapping[str, Any], authorized: Mapping[str, Any], exported: Mapping[str, Any]
) -> dict[str, Any]:
    row = _project_allowed(exported, _LEGACY_EXPORTED_FIELDS, "legacy_exported_row")
    for key in ("fixture_id", "decision_status"):
        if key not in row or row[key] in (None, ""):
            raise P30ComparisonEvidenceError(f"legacy_exported_row.{key} is required")
    return {
        "legacy_analysis_before_runtime_gate": _project_legacy_analysis(pre_gate, "legacy_pre_gate"),
        "authorized_analysis": _project_legacy_analysis(authorized, "legacy_authorized"),
        "exported_row": row,
    }


class LegacyEvidenceObserver:
    """Default-off copy-only observer for AnalysisPipeline."""
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._observations: list[dict[str, Any]] = []

    def __call__(self, fixture_context: Mapping[str, Any], pre_gate: Mapping[str, Any],
                 authorized: Mapping[str, Any], exported: Mapping[str, Any]) -> None:
        now = self._clock()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise P30ComparisonEvidenceError("legacy observer clock must be timezone-aware")
        self._observations.append({
            "observed_at": now.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "legacy_input": project_legacy_input(dict(fixture_context)),
            "legacy_output": project_legacy_output(dict(pre_gate), dict(authorized), dict(exported)),
        })

    def observations(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(load_json_bytes(canonical_json_bytes(item)) for item in self._observations)



# Internal cumulative export for the next implementation slice.
__all__ = tuple(name for name in globals() if not name.startswith("__"))
