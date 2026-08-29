"""One current research/shadow ATHENA runner for all eligible SportyBet markets.

Public callers provide only a target size and output directory.  The runner
acquires reviewed current FotMob evidence, replays complete PR151 history,
discovers/reconciles current SportyBet events, runs PR-C -> PR-D Price-all ->
PR-D Router -> PR-E Portfolio, and finally performs anonymous fresh semantic
create/reload verification when at least one legal leg survives.

This is research/shadow only.  It does not weaken the production Phase-6 gate,
accept provider-native IDs or odds from callers, log in, touch a wallet, submit
a stake, or place a wager.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import MappingProxyType
from typing import Any, Mapping

from domain import current_fotmob_latest_durable_fresh_history as latest_history
from domain import current_shadow_all_market_portfolio as portfolio_module
from domain import current_shadow_all_market_price_all as price_module
from domain import current_shadow_all_market_router as router_module
from domain import current_shadow_all_market_share_code as share_module
from domain import sportybet_current_event_discovery_reconciliation as reconciliation
from domain._current_shadow_price_core import ShadowPriceError
from domain.fotmob_data_matches_capture import (
    RAW_FILENAME,
    verify_data_matches_capture_directory,
)
from scripts import issue_current_fotmob_reviewed_source as current_fotmob_source

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-all-market-runner-v1"
STATUS_CODE_VERIFIED = "RESEARCH_SHADOW_CODE_VERIFIED"
STATUS_CODE_VERIFIED_WITH_SHORTFALL = "RESEARCH_SHADOW_CODE_VERIFIED_WITH_SHORTFALL"
STATUS_NO_BET = "RESEARCH_NO_CODE_NO_BET"
STATUS_INSUFFICIENT_SUPPORTED_MARKETS = "RESEARCH_NO_CODE_INSUFFICIENT_SUPPORTED_MARKETS"
STATUS_REPRICE_REQUIRED = "RESEARCH_NO_CODE_REPRICE_REQUIRED"
STATUS_PROVIDER_CHANGED = "RESEARCH_NO_CODE_PROVIDER_CHANGED"
STATUS_SOURCE_INCOMPLETE = "RESEARCH_NO_CODE_SOURCE_INCOMPLETE"

PR119_BOOTSTRAP_ASSET_SHA256 = "e5b78163a5eb68000b9a60dda97f04cac2a970f9cf2aaf588233151e586be8c2"
PR119_BOOTSTRAP_ENV = "ATHENA_PR119_BOOTSTRAP_PATH"
EXPECTED_MAIN_ENV = "ATHENA_EXPECTED_MAIN_SHA"

AUTHORITY = MappingProxyType({
    "research_shadow_current_runner": True,
    "research_shadow_source_acquisition": True,
    "research_shadow_probability_consumption": True,
    "research_shadow_price_all": True,
    "research_shadow_market_routing": True,
    "research_shadow_portfolio": True,
    "research_shadow_shortfall": True,
    "research_anonymous_share_code_generation": True,
    "provider_create_reload_verification": True,
    "production_model": False,
    "production_probability": False,
    "phase6": False,
    "production_price_all": False,
    "production_market_router": False,
    "production_portfolio": False,
    "production_selection": False,
    "production_sportybet_execution": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})

_ALLOWED_STATUSES = frozenset({
    STATUS_CODE_VERIFIED,
    STATUS_CODE_VERIFIED_WITH_SHORTFALL,
    STATUS_NO_BET,
    STATUS_INSUFFICIENT_SUPPORTED_MARKETS,
    STATUS_REPRICE_REQUIRED,
    STATUS_PROVIDER_CHANGED,
    STATUS_SOURCE_INCOMPLETE,
})


class CurrentShadowAllMarketRunnerError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CurrentShadowAllMarketRunnerError("canonical serialization failed") from exc


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _git_head(repository_root: Path) -> str:
    override = os.environ.get(EXPECTED_MAIN_ENV)
    if override:
        value = override.strip().lower()
    else:
        try:
            value = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repository_root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip().lower()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise CurrentShadowAllMarketRunnerError("exact repository commit SHA is unavailable") from exc
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise CurrentShadowAllMarketRunnerError("expected main SHA is invalid")
    return value


def _legacy_bootstrap_bytes() -> bytes:
    raw_path = os.environ.get(PR119_BOOTSTRAP_ENV)
    if not raw_path:
        raise CurrentShadowAllMarketRunnerError(
            f"{PR119_BOOTSTRAP_ENV} is required; workflow restores the fixed PR119 release asset"
        )
    path = Path(raw_path)
    if path.is_symlink() or not path.is_file():
        raise CurrentShadowAllMarketRunnerError("PR119 bootstrap asset path is unavailable")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PR119_BOOTSTRAP_ASSET_SHA256:
        raise CurrentShadowAllMarketRunnerError("PR119 bootstrap release asset SHA-256 mismatch")
    return raw


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _canonical(dict(payload))
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        handle.write(raw)
        temporary = Path(handle.name)
    os.replace(temporary, path)


@dataclass(frozen=True)
class CurrentShadowRunnerSourceBundle:
    router_inputs: tuple[portfolio_module.ShadowPortfolioRouterInput, ...]
    reviewed_fixture_count: int
    reconciled_fixture_count: int
    provider_event_count: int
    priced_fixture_count: int
    router_selected_count: int
    router_no_bet_count: int
    source_summary: Mapping[str, Any]


@dataclass(frozen=True)
class CurrentShadowAllMarketRunReceipt:
    status: str
    observed_at: datetime
    exact_commit_sha: str
    requested_target_size: int
    reviewed_fixture_count: int
    reconciled_fixture_count: int
    provider_event_count: int
    priced_fixture_count: int
    router_selected_count: int
    router_no_bet_count: int
    source_summary: Mapping[str, Any]
    portfolio: Mapping[str, Any] | None
    portfolio_sha256: str | None
    selected_leg_count: int
    reserve_leg_count: int
    shortfall: int
    share_code_receipt: Mapping[str, Any] | None
    share_code: str | None
    share_url: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUSES:
            raise CurrentShadowAllMarketRunnerError("runner status escaped reviewed vocabulary")
        if type(self.requested_target_size) is not int or not 1 <= self.requested_target_size <= 50:
            raise CurrentShadowAllMarketRunnerError("requested_target_size is invalid")
        if type(self.reasons) is not tuple or tuple(sorted(set(self.reasons))) != self.reasons:
            raise CurrentShadowAllMarketRunnerError("reasons must be sorted unique tuple")
        verified = self.status in {STATUS_CODE_VERIFIED, STATUS_CODE_VERIFIED_WITH_SHORTFALL}
        if verified != (self.share_code is not None and self.share_url is not None):
            raise CurrentShadowAllMarketRunnerError("share-code exposure does not match verified terminal state")
        if self.status == STATUS_CODE_VERIFIED and self.shortfall != 0:
            raise CurrentShadowAllMarketRunnerError("fully verified code cannot carry shortfall")
        if self.status == STATUS_CODE_VERIFIED_WITH_SHORTFALL and self.shortfall <= 0:
            raise CurrentShadowAllMarketRunnerError("shortfall verified status requires positive shortfall")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "dataset_name": DATASET_NAME,
            "status": self.status,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "exact_commit_sha": self.exact_commit_sha,
            "requested_target_size": self.requested_target_size,
            "reviewed_fixture_count": self.reviewed_fixture_count,
            "reconciled_fixture_count": self.reconciled_fixture_count,
            "provider_event_count": self.provider_event_count,
            "priced_fixture_count": self.priced_fixture_count,
            "router_selected_count": self.router_selected_count,
            "router_no_bet_count": self.router_no_bet_count,
            "source_summary": dict(self.source_summary),
            "portfolio": None if self.portfolio is None else dict(self.portfolio),
            "portfolio_sha256": self.portfolio_sha256,
            "selected_leg_count": self.selected_leg_count,
            "reserve_leg_count": self.reserve_leg_count,
            "shortfall": self.shortfall,
            "share_code_receipt": None if self.share_code_receipt is None else dict(self.share_code_receipt),
            "shareCode": self.share_code,
            "shareURL": self.share_url,
            "reasons": list(self.reasons),
            "authority": dict(AUTHORITY),
            "sportybet_login_used": False,
            "sportybet_cookie_used": False,
            "sportybet_wallet_used": False,
            "stake_submitted": False,
            "wager_placed": False,
        }


def _source_capture(execution: current_fotmob_source.CurrentFotMobReviewedSourceExecution, repository_root: Path):
    capture_root = repository_root / current_fotmob_source.DATA_MATCHES_CAPTURE_ROOT
    manifest = verify_data_matches_capture_directory(
        execution.source_capture_directory,
        allowed_root=capture_root,
        require_network_acquisition_performed=True,
    )
    raw_path = execution.source_capture_directory / RAW_FILENAME
    if raw_path.is_symlink() or not raw_path.is_file():
        raise CurrentShadowAllMarketRunnerError("current FotMob raw capture disappeared")
    raw = raw_path.read_bytes()
    return raw, manifest


def _acquire_router_inputs(*, repository_root: Path, exact_commit_sha: str) -> CurrentShadowRunnerSourceBundle:
    request_date = _now().strftime("%Y%m%d")
    execution = current_fotmob_source.issue_current_fotmob_reviewed_source(
        request_date=request_date,
        timezone="UTC",
        ccode3="NGA",
        execute_live_network=True,
        repository_root=repository_root,
    )
    raw, manifest = _source_capture(execution, repository_root)
    admission = execution.bootstrap.verified_artifact.admission
    captures = ((raw, manifest),)
    current_events = reconciliation.discover_and_reconcile_current_events(
        repository_root=repository_root,
        fotmob_admission_value=admission,
        fotmob_captures=captures,
        execute_live_network=True,
    )
    legacy_bootstrap = _legacy_bootstrap_bytes()
    history = latest_history.build_current_fotmob_latest_durable_fresh_history_handoff(
        current_bootstrap=execution.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=legacy_bootstrap,
        expected_main_sha=exact_commit_sha,
        repository_root=repository_root,
    )

    inputs: list[portfolio_module.ShadowPortfolioRouterInput] = []
    selected = 0
    no_bet = 0
    priced = 0
    for row in current_events.matched_rows:
        if row.matched_fotmob_fixture_id is None:
            continue
        fixture_identity = f"FOTMOB:{row.matched_fotmob_fixture_id}"
        context = price_module.build_current_shadow_price_context_from_reconciliation(
            complete_current_history=history,
            fixture_identity=fixture_identity,
            provider_event_id=row.event_id,
            current_reconciliation_bundle=current_events,
        )
        priced_bundle = price_module.price_all_shadow_fixture(context)
        decision = router_module.route_shadow_price_results(priced_bundle)
        priced += 1
        if decision.status.value == "SELECTED":
            selected += 1
        else:
            no_bet += 1
        inputs.append(portfolio_module.build_shadow_portfolio_router_input(
            price_all_bundle=priced_bundle,
            router_decision=decision,
        ))
    summary = MappingProxyType({
        "current_fotmob": execution.summary(),
        "complete_current_history_sha256": latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff(history),
        "current_reconciliation_sha256": current_events.canonical_sha256,
        "current_reconciliation_contract_sha256": current_events.contract_sha256,
        "matched_provider_event_ids": [row.event_id for row in current_events.matched_rows],
        "wager_placed": False,
    })
    return CurrentShadowRunnerSourceBundle(
        router_inputs=tuple(inputs),
        reviewed_fixture_count=len(execution.bootstrap.fixtures),
        reconciled_fixture_count=len(current_events.matched_rows),
        provider_event_count=len(current_events.rows),
        priced_fixture_count=priced,
        router_selected_count=selected,
        router_no_bet_count=no_bet,
        source_summary=summary,
    )


def _receipt(
    *,
    status: str,
    exact_commit_sha: str,
    target_size: int,
    sources: CurrentShadowRunnerSourceBundle | None,
    portfolio: portfolio_module.ShadowPortfolioOptimization | None,
    share_receipt: share_module.ShadowAllMarketShareCodeReceipt | None,
    reasons: tuple[str, ...],
) -> CurrentShadowAllMarketRunReceipt:
    return CurrentShadowAllMarketRunReceipt(
        status=status,
        observed_at=_now(),
        exact_commit_sha=exact_commit_sha,
        requested_target_size=target_size,
        reviewed_fixture_count=0 if sources is None else sources.reviewed_fixture_count,
        reconciled_fixture_count=0 if sources is None else sources.reconciled_fixture_count,
        provider_event_count=0 if sources is None else sources.provider_event_count,
        priced_fixture_count=0 if sources is None else sources.priced_fixture_count,
        router_selected_count=0 if sources is None else sources.router_selected_count,
        router_no_bet_count=0 if sources is None else sources.router_no_bet_count,
        source_summary=MappingProxyType({}) if sources is None else sources.source_summary,
        portfolio=None if portfolio is None else portfolio.to_dict(),
        portfolio_sha256=None if portfolio is None else portfolio.canonical_sha256,
        selected_leg_count=0 if portfolio is None else len(portfolio.selected_legs),
        reserve_leg_count=0 if portfolio is None else len(portfolio.reserve_legs),
        shortfall=target_size if portfolio is None else portfolio.shortfall,
        share_code_receipt=None if share_receipt is None else share_receipt.to_dict(),
        share_code=None if share_receipt is None else share_receipt.share_code,
        share_url=None if share_receipt is None else share_receipt.share_url,
        reasons=tuple(sorted(set(reasons))),
    )


def execute_current_shadow_all_market(
    *, target_size: int, output_dir: Path,
) -> CurrentShadowAllMarketRunReceipt:
    if type(target_size) is not int or not 1 <= target_size <= 50:
        raise CurrentShadowAllMarketRunnerError("target_size must be an integer from 1 through 50")
    if not isinstance(output_dir, Path):
        raise CurrentShadowAllMarketRunnerError("output_dir must be Path")
    repository_root = Path(__file__).resolve().parents[1]
    exact_commit_sha = _git_head(repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources: CurrentShadowRunnerSourceBundle | None = None
    portfolio: portfolio_module.ShadowPortfolioOptimization | None = None
    share_receipt: share_module.ShadowAllMarketShareCodeReceipt | None = None
    try:
        sources = _acquire_router_inputs(repository_root=repository_root, exact_commit_sha=exact_commit_sha)
        if sources.reconciled_fixture_count == 0:
            result = _receipt(
                status=STATUS_INSUFFICIENT_SUPPORTED_MARKETS,
                exact_commit_sha=exact_commit_sha,
                target_size=target_size,
                sources=sources,
                portfolio=None,
                share_receipt=None,
                reasons=("NO_EXACT_CURRENT_FOTMOB_SPORTYBET_RECONCILIATED_FIXTURES",),
            )
        elif sources.router_inputs and sources.router_selected_count == 0:
            result = _receipt(
                status=STATUS_NO_BET,
                exact_commit_sha=exact_commit_sha,
                target_size=target_size,
                sources=sources,
                portfolio=None,
                share_receipt=None,
                reasons=("ALL_RECONCILED_FIXTURES_ROUTER_NO_BET",),
            )
        else:
            portfolio = portfolio_module.optimize_shadow_portfolio(
                sources.router_inputs,
                target_size=target_size,
                evaluation_time=_now(),
            )
            if not portfolio.selected_legs:
                blocked_reasons = {
                    reason
                    for reserve in portfolio.reserve_legs
                    for reason in reserve.reserve_reasons
                }
                stale = bool(blocked_reasons & {"PORTFOLIO_TIME_STALE", "TOO_CLOSE_TO_KICKOFF"})
                result = _receipt(
                    status=STATUS_REPRICE_REQUIRED if stale else STATUS_INSUFFICIENT_SUPPORTED_MARKETS,
                    exact_commit_sha=exact_commit_sha,
                    target_size=target_size,
                    sources=sources,
                    portfolio=portfolio,
                    share_receipt=None,
                    reasons=tuple(sorted(blocked_reasons or {"NO_PORTFOLIO_LEGS_SURVIVED_FROZEN_CONSTRAINTS"})),
                )
            else:
                share_receipt = share_module.create_verified_shadow_all_market_share_code(
                    portfolio=portfolio,
                    output_dir=output_dir / "provider-verification",
                )
                mapped_status = {
                    share_module.STATUS_CODE_VERIFIED: STATUS_CODE_VERIFIED,
                    share_module.STATUS_CODE_VERIFIED_WITH_SHORTFALL: STATUS_CODE_VERIFIED_WITH_SHORTFALL,
                    share_module.STATUS_REPRICE_REQUIRED: STATUS_REPRICE_REQUIRED,
                    share_module.STATUS_PROVIDER_CHANGED: STATUS_PROVIDER_CHANGED,
                }[share_receipt.status]
                result = _receipt(
                    status=mapped_status,
                    exact_commit_sha=exact_commit_sha,
                    target_size=target_size,
                    sources=sources,
                    portfolio=portfolio,
                    share_receipt=share_receipt,
                    reasons=share_receipt.reasons,
                )
    except (
        CurrentShadowAllMarketRunnerError,
        current_fotmob_source.CurrentFotMobReviewedSourceError,
        latest_history.CurrentLatestDurableFreshHistoryError,
        reconciliation.SportyBetCurrentEventDiscoveryError,
        portfolio_module.CurrentShadowPortfolioError,
        share_module.CurrentShadowAllMarketShareCodeError,
        ShadowPriceError,
    ) as exc:
        result = _receipt(
            status=STATUS_SOURCE_INCOMPLETE,
            exact_commit_sha=exact_commit_sha,
            target_size=target_size,
            sources=sources,
            portfolio=portfolio,
            share_receipt=share_receipt,
            reasons=(f"SOURCE_CHAIN_FAILED:{type(exc).__name__}:{exc}",),
        )
    _write(output_dir / "current-shadow-all-market-run-receipt.json", result.to_dict())
    return result


__all__ = [
    "AUTHORITY",
    "CurrentShadowAllMarketRunReceipt",
    "CurrentShadowAllMarketRunnerError",
    "CurrentShadowRunnerSourceBundle",
    "STATUS_CODE_VERIFIED",
    "STATUS_CODE_VERIFIED_WITH_SHORTFALL",
    "STATUS_INSUFFICIENT_SUPPORTED_MARKETS",
    "STATUS_NO_BET",
    "STATUS_PROVIDER_CHANGED",
    "STATUS_REPRICE_REQUIRED",
    "STATUS_SOURCE_INCOMPLETE",
    "execute_current_shadow_all_market",
]
