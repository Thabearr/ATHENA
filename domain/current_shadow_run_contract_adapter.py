"""One-way compatibility adapter from Current Shadow into canonical run contracts.

The adapter preserves legacy request/receipt evidence while refusing to invent
resolved dates, selected legs, stage history, delivery verification, or authority.
It performs no provider acquisition and invokes no Current Shadow runner.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from domain.run_contracts import (
    AuthorityManifest,
    RunContractError,
    RunReceipt,
    RunRequest,
    RunStage,
)


CURRENT_REQUEST_SCHEMA_VERSION = 1
CURRENT_REQUEST_DATASET = "athena-current-shadow-request-policy-v1"
CURRENT_RECEIPT_SCHEMA_VERSION = 1
CURRENT_RECEIPT_DATASET = "athena-current-shadow-all-market-runner-v1"
CURRENT_STAGE_SEQUENCE = (
    "STARTED",
    "CURRENT_FOTMOB_SOURCE",
    "SPORTYBET_DISCOVERY_RECONCILIATION",
    "CURRENT_DURABLE_FRESH_HISTORY",
    "PRICE_ALL_ROUTER",
    "PORTFOLIO",
    "SHARE_CODE_CREATE_RELOAD",
    "COMPLETE",
)
_RISKY_LEGACY_AUTHORITY_KEYS = (
    "production_model",
    "production_probability",
    "phase6",
    "production_price_all",
    "production_market_router",
    "production_portfolio",
    "production_selection",
    "production_sportybet_execution",
    "login",
    "cookies",
    "wallet",
    "staking",
    "bet",
    "wager_placed",
)
_TOP_LEVEL_SAFETY_KEYS = (
    "sportybet_login_used",
    "sportybet_cookie_used",
    "sportybet_wallet_used",
    "stake_submitted",
    "wager_placed",
)
_COUNT_FIELDS = (
    "reviewed_fixture_count",
    "reconciled_fixture_count",
    "provider_event_count",
    "priced_fixture_count",
    "router_selected_count",
    "router_no_bet_count",
    "selected_leg_count",
    "reserve_leg_count",
)


class CurrentShadowRunContractAdapterError(RunContractError):
    """Raised when Current Shadow evidence cannot be mapped without guessing."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentShadowRunContractAdapterError(f"{label} must be mapping")
    return value


def _exact_false(value: Any, label: str) -> None:
    if value is not False:
        raise CurrentShadowRunContractAdapterError(f"{label} must be exact false")


def _parse_legacy_date(value: Any) -> date:
    if type(value) is not str or len(value) != 8 or not value.isascii() or not value.isdigit():
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow fixture dates must be exact YYYYMMDD text"
        )
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow fixture date is not a real date"
        ) from exc
    if parsed.strftime("%Y%m%d") != value:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow fixture date is not canonical YYYYMMDD"
        )
    return parsed


def _parse_utc(value: Any, label: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise CurrentShadowRunContractAdapterError(f"{label} must be exact UTC text ending Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CurrentShadowRunContractAdapterError(f"{label} is invalid ISO-8601 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentShadowRunContractAdapterError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_request_policy(value: Any) -> Mapping[str, Any]:
    policy = _mapping(value, "Current Shadow request policy")
    if (
        policy.get("schema_version") != CURRENT_REQUEST_SCHEMA_VERSION
        or policy.get("dataset_name") != CURRENT_REQUEST_DATASET
    ):
        raise CurrentShadowRunContractAdapterError("Current Shadow request-policy identity drifted")
    if "fixture_dates" not in policy or "fixture_scope" not in policy:
        raise CurrentShadowRunContractAdapterError("Current Shadow request policy lacks date fields")
    _exact_false(policy.get("wager_placed"), "Current Shadow request-policy wager_placed")
    authority = _mapping(policy.get("authority"), "Current Shadow request-policy authority")
    _exact_false(authority.get("bet"), "Current Shadow request-policy bet authority")
    _exact_false(authority.get("wager_placed"), "Current Shadow request-policy wager result")
    return policy


def _validated_resolved_dates(values: Sequence[date] | None) -> tuple[date, ...] | None:
    if values is None:
        return None
    items = tuple(values)
    if any(type(item) is not date for item in items):
        raise CurrentShadowRunContractAdapterError("resolved_dates must contain exact date values")
    if len(set(items)) != len(items):
        raise CurrentShadowRunContractAdapterError("resolved_dates must be unique")
    return tuple(sorted(items))


def adapt_current_shadow_request(
    *,
    target_size: int,
    request_policy: Mapping[str, Any],
    resolved_dates: Sequence[date] | None = None,
) -> RunRequest:
    """Map a resolved Current Shadow request without interpreting relative scopes."""

    policy = _validate_request_policy(request_policy)
    supplied = _validated_resolved_dates(resolved_dates)
    legacy_dates = policy["fixture_dates"]
    if legacy_dates is None:
        if supplied is None:
            raise CurrentShadowRunContractAdapterError(
                "legacy fixture_scope is not a concrete date; resolved_dates are required"
            )
        concrete = supplied
    else:
        if type(legacy_dates) is not list or not legacy_dates:
            raise CurrentShadowRunContractAdapterError(
                "Current Shadow explicit fixture_dates must be a non-empty list"
            )
        parsed = tuple(_parse_legacy_date(item) for item in legacy_dates)
        if len(set(parsed)) != len(parsed) or tuple(sorted(parsed)) != parsed:
            raise CurrentShadowRunContractAdapterError(
                "Current Shadow explicit fixture_dates must be sorted and unique"
            )
        if supplied is not None and supplied != parsed:
            raise CurrentShadowRunContractAdapterError(
                "resolved_dates contradict Current Shadow explicit fixture_dates"
            )
        concrete = parsed

    return RunRequest(
        dates=concrete,
        target_legs=target_size,
        target_total_odds=None,
        bookie="sportybet",
        mode="research_shadow",
        authority_profile="SHADOW",
        create_share_code=True,
        place_wager=False,
    )


def _validated_legacy_authority(receipt: Mapping[str, Any]) -> Mapping[str, bool]:
    authority = _mapping(receipt.get("authority"), "Current Shadow receipt authority")
    for key in _RISKY_LEGACY_AUTHORITY_KEYS:
        _exact_false(authority.get(key), f"Current Shadow authority {key}")
    checked: dict[str, bool] = {}
    for key, value in authority.items():
        if type(key) is not str or not key or type(value) is not bool:
            raise CurrentShadowRunContractAdapterError(
                "Current Shadow receipt authority must contain string->bool entries"
            )
        checked[key] = value
    return checked


def _legacy_counts(receipt: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in _COUNT_FIELDS:
        value = receipt.get(key)
        if type(value) is not int or value < 0:
            raise CurrentShadowRunContractAdapterError(f"Current Shadow {key} is invalid")
        counts[key] = value
    if counts["router_selected_count"] + counts["router_no_bet_count"] > counts["priced_fixture_count"]:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow router counts exceed priced fixtures"
        )
    return counts


def _selected_legs(receipt: Mapping[str, Any], expected_count: int) -> tuple[Mapping[str, Any], ...]:
    final = receipt.get("final_selected_legs")
    if type(final) is not list:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow final_selected_legs must be list"
        )
    portfolio = receipt.get("portfolio")
    portfolio_legs: Any = None
    if portfolio is not None:
        portfolio_map = _mapping(portfolio, "Current Shadow portfolio")
        portfolio_legs = portfolio_map.get("selected_legs")
        if type(portfolio_legs) is not list:
            raise CurrentShadowRunContractAdapterError(
                "Current Shadow portfolio selected_legs must be list"
            )

    if final:
        chosen = final
    elif portfolio_legs:
        chosen = portfolio_legs
    elif expected_count == 0:
        chosen = []
    else:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow selected_leg_count is positive but concrete selected legs are absent"
        )
    if len(chosen) != expected_count:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow selected_leg_count differs from concrete selected legs"
        )
    if any(not isinstance(item, Mapping) for item in chosen):
        raise CurrentShadowRunContractAdapterError("Current Shadow selected legs must be mappings")
    return tuple(chosen)


def _share_code_result(receipt: Mapping[str, Any]) -> Mapping[str, Any] | None:
    legacy = receipt.get("share_code_receipt")
    code = receipt.get("shareCode")
    url = receipt.get("shareURL")
    if legacy is None and code is None and url is None:
        return None
    if legacy is None:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow share-code exposure lacks verification receipt"
        )
    legacy = _mapping(legacy, "Current Shadow share-code receipt")
    if (code is None) != (url is None):
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow share code and URL must be exposed together"
        )
    if code is not None and (type(code) is not str or not code):
        raise CurrentShadowRunContractAdapterError("Current Shadow share code is invalid")
    if url is not None and (type(url) is not str or not url):
        raise CurrentShadowRunContractAdapterError("Current Shadow share URL is invalid")
    return {
        "verified": code is not None and url is not None,
        "share_code": code,
        "share_url": url,
        "legacy_receipt": dict(legacy),
    }


def _checkpoint_stage(
    payload: Mapping[str, Any],
    *,
    request: RunRequest,
    exact_commit_sha: str,
    source: str,
) -> RunStage:
    value = _mapping(payload, f"Current Shadow {source} checkpoint")
    if value.get("dataset_name") != CURRENT_RECEIPT_DATASET or value.get("schema_version") != 1:
        raise CurrentShadowRunContractAdapterError(
            f"Current Shadow {source} checkpoint identity drifted"
        )
    stage = value.get("stage")
    if stage not in CURRENT_STAGE_SEQUENCE:
        raise CurrentShadowRunContractAdapterError(
            f"Current Shadow {source} checkpoint stage drifted"
        )
    if value.get("stage_index") != CURRENT_STAGE_SEQUENCE.index(stage):
        raise CurrentShadowRunContractAdapterError(
            f"Current Shadow {source} checkpoint stage index drifted"
        )
    if value.get("exact_commit_sha") != exact_commit_sha:
        raise CurrentShadowRunContractAdapterError(
            f"Current Shadow {source} checkpoint commit does not match receipt"
        )
    if value.get("requested_target_size") != request.target_legs:
        raise CurrentShadowRunContractAdapterError(
            f"Current Shadow {source} checkpoint target does not match request"
        )
    _exact_false(value.get("wager_placed"), f"Current Shadow {source} checkpoint wager_placed")
    observed = _parse_utc(value.get("observed_at"), f"Current Shadow {source} observed_at")
    if source == "progress":
        progress_status = value.get("progress_status")
        if type(progress_status) is not str or not progress_status:
            raise CurrentShadowRunContractAdapterError(
                "Current Shadow progress checkpoint lacks progress_status"
            )
        raw_counts = _mapping(value.get("counts"), "Current Shadow progress counts")
        stage_counts: dict[str, int] = {}
        for key, item in raw_counts.items():
            if type(key) is not str or type(item) is not int or item < 0:
                raise CurrentShadowRunContractAdapterError(
                    "Current Shadow progress counts are invalid"
                )
            stage_counts[key] = item
        status = progress_status
    else:
        stage_counts = {}
        status = "CHECKPOINTED"
    return RunStage(
        stage=stage,
        status=status,
        observed_at=observed,
        counts=stage_counts,
        evidence={"legacy_checkpoint_source": source, "legacy_payload": dict(value)},
    )


def adapt_current_shadow_receipt(
    *,
    request: RunRequest,
    receipt_payload: Mapping[str, Any],
    request_policy: Mapping[str, Any],
    stage_payload: Mapping[str, Any] | None = None,
    progress_payload: Mapping[str, Any] | None = None,
) -> RunReceipt:
    """Map a terminal Current Shadow receipt while preserving all legacy evidence."""

    if type(request) is not RunRequest:
        raise CurrentShadowRunContractAdapterError("request must be exact canonical RunRequest")
    if request.authority_profile != "SHADOW" or request.mode != "research_shadow":
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow receipt requires SHADOW/research_shadow RunRequest"
        )
    policy = _validate_request_policy(request_policy)
    receipt = _mapping(receipt_payload, "Current Shadow receipt")
    if (
        receipt.get("schema_version") != CURRENT_RECEIPT_SCHEMA_VERSION
        or receipt.get("dataset_name") != CURRENT_RECEIPT_DATASET
    ):
        raise CurrentShadowRunContractAdapterError("Current Shadow receipt identity drifted")
    if receipt.get("requested_target_size") != request.target_legs:
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow receipt target differs from canonical RunRequest"
        )
    for key in _TOP_LEVEL_SAFETY_KEYS:
        _exact_false(receipt.get(key), f"Current Shadow receipt {key}")

    legacy_authority = _validated_legacy_authority(receipt)
    counts = _legacy_counts(receipt)
    legs = _selected_legs(receipt, counts["selected_leg_count"])
    shortfall = receipt.get("shortfall")
    if type(shortfall) is not int or shortfall < 0:
        raise CurrentShadowRunContractAdapterError("Current Shadow shortfall is invalid")
    if shortfall != request.target_legs - len(legs):
        raise CurrentShadowRunContractAdapterError(
            "Current Shadow shortfall is not truthful for canonical target_legs"
        )

    exact_commit_sha = receipt.get("exact_commit_sha")
    if type(exact_commit_sha) is not str:
        raise CurrentShadowRunContractAdapterError("Current Shadow exact_commit_sha is invalid")
    stages: list[RunStage] = []
    if stage_payload is not None:
        stages.append(
            _checkpoint_stage(
                stage_payload,
                request=request,
                exact_commit_sha=exact_commit_sha,
                source="stage",
            )
        )
    if progress_payload is not None:
        stages.append(
            _checkpoint_stage(
                progress_payload,
                request=request,
                exact_commit_sha=exact_commit_sha,
                source="progress",
            )
        )

    manifest = AuthorityManifest(
        authority_profile="SHADOW",
        mode="research_shadow",
        provider_acquisition=legacy_authority.get("research_shadow_source_acquisition") is True,
        share_code_generation=legacy_authority.get("research_anonymous_share_code_generation") is True,
        login=False,
        cookies=False,
        wallet=False,
        staking=False,
        wager=False,
        additional_capabilities=legacy_authority,
    )
    share_result = _share_code_result(receipt)
    evidence = {
        "legacy_current_shadow": {
            "adapter_policy": "ONE_WAY_NO_INFERENCE_V1",
            "legacy_stage_history_complete": False,
            "request_policy": dict(policy),
            "receipt": dict(receipt),
            "latest_stage_checkpoint": None if stage_payload is None else dict(stage_payload),
            "latest_progress_checkpoint": None if progress_payload is None else dict(progress_payload),
        }
    }
    canonical_counts = dict(counts)
    canonical_counts["target_legs"] = request.target_legs
    canonical_counts["shortfall"] = shortfall

    return RunReceipt(
        status=receipt.get("status"),
        observed_at=_parse_utc(receipt.get("observed_at"), "Current Shadow receipt observed_at"),
        exact_commit_sha=exact_commit_sha,
        request=request,
        stages=tuple(stages),
        counts=canonical_counts,
        selected_legs=legs,
        shortfall=shortfall,
        share_code_result=share_result,
        authority_manifest=manifest,
        evidence=evidence,
        wager_placed=False,
    )


def adapt_current_shadow_run(
    *,
    target_size: int,
    request_policy: Mapping[str, Any],
    receipt_payload: Mapping[str, Any],
    resolved_dates: Sequence[date] | None = None,
    stage_payload: Mapping[str, Any] | None = None,
    progress_payload: Mapping[str, Any] | None = None,
) -> RunReceipt:
    """Convenience composition of the one-way request and receipt adapters."""

    request = adapt_current_shadow_request(
        target_size=target_size,
        request_policy=request_policy,
        resolved_dates=resolved_dates,
    )
    return adapt_current_shadow_receipt(
        request=request,
        receipt_payload=receipt_payload,
        request_policy=request_policy,
        stage_payload=stage_payload,
        progress_payload=progress_payload,
    )


__all__ = [
    "CURRENT_RECEIPT_DATASET",
    "CURRENT_REQUEST_DATASET",
    "CURRENT_STAGE_SEQUENCE",
    "CurrentShadowRunContractAdapterError",
    "adapt_current_shadow_receipt",
    "adapt_current_shadow_request",
    "adapt_current_shadow_run",
]
