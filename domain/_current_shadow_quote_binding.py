"""Replayable current-source context and exact PR-B quote issuance.

PR D originally admitted the reviewed PR253 mapped-quote bundle as its fixture
bridge.  PR E keeps that path for compatibility and adds the actual current
runner path: exact PR251 current-event reconciliation + retained event-detail
source evidence.  The new path does not fabricate a PR252 mapping identity;
those legacy-only identities are explicitly ``None`` while the exact current
reconciliation SHA remains mandatory.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from domain import current_all_market_shadow_probability_settlement as prc
from domain import current_direct_provider_live_quote_mapping_consumption as current_quotes
from domain import current_sportybet_semantic_registry as prb
from domain import sportybet_current_event_discovery_reconciliation as current_reconciliation
from domain import sportybet_live_event_quote_evidence as live
from domain.current_fotmob_latest_durable_fresh_history import CurrentLatestDurableFreshHistoryHandoff
from domain.markets import MarketId, OutcomeId
from domain._current_shadow_price_core import SOURCE_CONTEXT_POLICY_ID, ShadowPriceError, _canonical_bytes, _sha256
from domain._current_shadow_price_records import ShadowExactQuote, _issue_shadow_exact_quote

LEGACY_PR253_FIXTURE_BRIDGE = "LEGACY_PR253_FIXTURE_BRIDGE"
CURRENT_RECONCILIATION_DIRECT = "CURRENT_RECONCILIATION_DIRECT"
CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID = (
    "PRC_CURRENT_SCAN_PLUS_PR251_CURRENT_RECONCILIATION_PLUS_PRB_REPLAY_V1"
)


@dataclass(frozen=True, init=False)
class CurrentShadowPriceContext:
    fixture_identity: str
    provider_event_id: str
    evaluation_time: datetime
    scan: prc.CurrentAllMarketShadowFixtureScan
    prc_scan_sha256: str
    provider_registry: prb.CurrentSportyBetSemanticRegistry
    provider_registry_sha256: str
    provider_inventory: live.SportyBetLiveEventQuoteInventory
    source_raw_sha256: str
    source_manifest_sha256: str
    source_inventory_sha256: str
    fixture_reconciliation_sha256: str
    current_mapping_rebind_sha256: str | None
    bridge_bundle_sha256: str | None
    source_context_mode: str
    source_context_policy_id: str
    _bridge_bundle: current_quotes.CurrentDirectProviderMappedQuoteBundle | None
    _current_reconciliation_bundle: current_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle | None
    _event_evidence: prb.ProviderEventEvidence
    _complete_current_history: CurrentLatestDurableFreshHistoryHandoff

    def __init__(self, *_a: Any, **_k: Any) -> None:
        raise ShadowPriceError("CurrentShadowPriceContext is builder-only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identity": self.fixture_identity,
            "provider_event_id": self.provider_event_id,
            "evaluation_time": self.evaluation_time.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "prc_scan_sha256": self.prc_scan_sha256,
            "provider_registry_sha256": self.provider_registry_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_inventory_sha256": self.source_inventory_sha256,
            "fixture_reconciliation_sha256": self.fixture_reconciliation_sha256,
            "current_mapping_rebind_sha256": self.current_mapping_rebind_sha256,
            "bridge_bundle_sha256": self.bridge_bundle_sha256,
            "source_context_mode": self.source_context_mode,
            "source_context_policy_id": self.source_context_policy_id,
            "wager_placed": False,
        }

    @property
    def canonical_sha256(self) -> str:
        return _sha256(self.to_dict())


def _set(obj: Any, values: Mapping[str, Any]) -> Any:
    for key, value in values.items():
        object.__setattr__(obj, key, value)
    return obj


def _utc(value: Any) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ShadowPriceError("evaluation_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _kickoff(value: str | None) -> datetime | None:
    if value is None:
        return None
    if type(value) is not str or not value.endswith("Z"):
        raise ShadowPriceError("PR-C kickoff identity is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ShadowPriceError("PR-C kickoff identity is invalid") from exc


def _compose(
    *,
    complete_current_history: CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    evidence: prb.ProviderEventEvidence,
    evaluation: datetime,
    fixture_reconciliation_sha256: str,
    current_mapping_rebind_sha256: str | None,
    bridge_bundle_sha256: str | None,
    source_context_mode: str,
    source_context_policy_id: str,
    bridge_bundle: current_quotes.CurrentDirectProviderMappedQuoteBundle | None,
    reconciliation_bundle: current_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle | None,
) -> CurrentShadowPriceContext:
    try:
        checked_evidence = prb.replay_event_evidence(evidence)
        registry = prb.build_registry((checked_evidence,), evaluation_time=evaluation, scan_cap=1, scan_attempts=1)
        scan = prc.scan_current_fixture_all_markets(
            complete_current_history=complete_current_history,
            fixture_identity=fixture_identity,
            provider_semantic_registry=registry,
        )
    except Exception as exc:
        raise ShadowPriceError("current PR-B/PR-C source composition failed") from exc
    inventory = checked_evidence.inventory
    scan_kickoff = _kickoff(scan.kickoff_utc_iso)
    if scan_kickoff is not None and scan_kickoff != inventory.kickoff_utc:
        raise ShadowPriceError("PR-C and SportyBet fixture kickoff differ")
    value = object.__new__(CurrentShadowPriceContext)
    return _set(value, {
        "fixture_identity": fixture_identity,
        "provider_event_id": inventory.event_id,
        "evaluation_time": evaluation,
        "scan": scan,
        "prc_scan_sha256": _sha256(scan.to_dict()),
        "provider_registry": registry,
        "provider_registry_sha256": registry.canonical_sha256,
        "provider_inventory": inventory,
        "source_raw_sha256": inventory.source_raw_sha256,
        "source_manifest_sha256": inventory.source_manifest_sha256,
        "source_inventory_sha256": inventory.canonical_sha256,
        "fixture_reconciliation_sha256": fixture_reconciliation_sha256,
        "current_mapping_rebind_sha256": current_mapping_rebind_sha256,
        "bridge_bundle_sha256": bridge_bundle_sha256,
        "source_context_mode": source_context_mode,
        "source_context_policy_id": source_context_policy_id,
        "_bridge_bundle": bridge_bundle,
        "_current_reconciliation_bundle": reconciliation_bundle,
        "_event_evidence": checked_evidence,
        "_complete_current_history": complete_current_history,
    })


def build_current_shadow_price_context(
    *,
    complete_current_history: CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    provider_event_evidence: prb.ProviderEventEvidence,
    fixture_quote_bridge: current_quotes.CurrentDirectProviderMappedQuoteBundle,
) -> CurrentShadowPriceContext:
    """Compatibility path: compose from replayable PR151, PR253 and PR-B sources."""
    if type(complete_current_history) is not CurrentLatestDurableFreshHistoryHandoff:
        raise ShadowPriceError("complete_current_history type mismatch")
    if type(fixture_identity) is not str or not fixture_identity.strip():
        raise ShadowPriceError("fixture_identity must be non-empty")
    if type(provider_event_evidence) is not prb.ProviderEventEvidence:
        raise ShadowPriceError("provider_event_evidence type mismatch")
    if type(fixture_quote_bridge) is not current_quotes.CurrentDirectProviderMappedQuoteBundle:
        raise ShadowPriceError("fixture_quote_bridge type mismatch")
    try:
        bridge = current_quotes.verify_current_direct_provider_mapped_quote_bundle(fixture_quote_bridge)
    except current_quotes.CurrentDirectProviderLiveQuoteMappingConsumptionError as exc:
        raise ShadowPriceError("fixture bridge source replay failed") from exc
    if bridge.proof_mode != current_quotes.LIVE_CURRENT:
        raise ShadowPriceError("current Shadow pricing requires LIVE_CURRENT fixture bridge")
    if bridge.fixture_id != fixture_identity:
        raise ShadowPriceError("fixture bridge does not match requested PR-C fixture")
    try:
        evidence = prb.replay_event_evidence(provider_event_evidence)
    except prb.CurrentSportyBetSemanticRegistryError as exc:
        raise ShadowPriceError("PR-B provider event replay failed") from exc
    inventory = evidence.inventory
    if (
        bridge.event_id,
        bridge.current_inventory_sha256,
        bridge.current_manifest_sha256,
        bridge.current_raw_sha256,
        bridge.kickoff_utc,
    ) != (
        inventory.event_id,
        inventory.canonical_sha256,
        inventory.source_manifest_sha256,
        inventory.source_raw_sha256,
        inventory.kickoff_utc,
    ):
        raise ShadowPriceError("fixture bridge and replayed PR-B event ancestry differ")
    return _compose(
        complete_current_history=complete_current_history,
        fixture_identity=fixture_identity,
        evidence=evidence,
        evaluation=_utc(bridge.evaluation_time),
        fixture_reconciliation_sha256=bridge.source_current_reconciliation_sha256,
        current_mapping_rebind_sha256=bridge.current_mapping_rebind_sha256,
        bridge_bundle_sha256=bridge.canonical_sha256,
        source_context_mode=LEGACY_PR253_FIXTURE_BRIDGE,
        source_context_policy_id=SOURCE_CONTEXT_POLICY_ID,
        bridge_bundle=bridge,
        reconciliation_bundle=None,
    )


def build_current_shadow_price_context_from_reconciliation(
    *,
    complete_current_history: CurrentLatestDurableFreshHistoryHandoff,
    fixture_identity: str,
    provider_event_id: str,
    current_reconciliation_bundle: current_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle,
) -> CurrentShadowPriceContext:
    """Current runner path from exact PR251 reconciliation + retained PR-B evidence."""
    if type(complete_current_history) is not CurrentLatestDurableFreshHistoryHandoff:
        raise ShadowPriceError("complete_current_history type mismatch")
    if type(fixture_identity) is not str or not fixture_identity.strip():
        raise ShadowPriceError("fixture_identity must be non-empty")
    if type(provider_event_id) is not str or not provider_event_id.strip():
        raise ShadowPriceError("provider_event_id must be non-empty")
    if type(current_reconciliation_bundle) is not current_reconciliation.SportyBetCurrentEventDiscoveryReconciliationBundle:
        raise ShadowPriceError("current_reconciliation_bundle type mismatch")
    try:
        reconciled = current_reconciliation.verify_current_event_discovery_reconciliation_bundle(
            current_reconciliation_bundle
        )
    except current_reconciliation.SportyBetCurrentEventDiscoveryError as exc:
        raise ShadowPriceError("current reconciliation source replay failed") from exc
    rows = [
        row for row in reconciled.rows
        if row.event_id == provider_event_id
        and row.matched_fotmob_fixture_id == fixture_identity
    ]
    if len(rows) != 1 or rows[0].fixture_reconciliation_authorized is not True:
        raise ShadowPriceError("requested fixture/event lacks one exact current reconciliation")
    row = rows[0]
    detail_dirs = dict(reconciled._detail_directories)
    directory = detail_dirs.get(provider_event_id)
    if directory is None:
        raise ShadowPriceError("current reconciliation omitted retained event-detail evidence")
    try:
        evidence = prb.load_provider_event_evidence(
            Path(directory),
            repository_root=reconciled._repository_root,
            fixture_identity=provider_event_id,
            fixture_identity_basis="PR251_UNIQUE_EXACT_CURRENT_PROVIDER_RECONCILIATION",
        )
    except prb.CurrentSportyBetSemanticRegistryError as exc:
        raise ShadowPriceError("PR-B provider event evidence replay failed") from exc
    inventory = evidence.inventory
    if (
        inventory.home_team_name != row.home_team_name
        or inventory.away_team_name != row.away_team_name
        or inventory.kickoff_utc != row.kickoff_utc
        or inventory.observed_at != row.direct_event_observed_at
        or inventory.source_manifest_sha256 != row.direct_event_manifest_sha256
        or inventory.canonical_sha256 != row.direct_event_inventory_sha256
        or inventory.source_raw_sha256 != row.direct_event_raw_sha256
    ):
        raise ShadowPriceError("reconciled event row differs from retained exact provider evidence")
    return _compose(
        complete_current_history=complete_current_history,
        fixture_identity=fixture_identity,
        evidence=evidence,
        evaluation=_utc(reconciled.evaluation_time),
        fixture_reconciliation_sha256=reconciled.canonical_sha256,
        current_mapping_rebind_sha256=None,
        bridge_bundle_sha256=None,
        source_context_mode=CURRENT_RECONCILIATION_DIRECT,
        source_context_policy_id=CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID,
        bridge_bundle=None,
        reconciliation_bundle=reconciled,
    )


def verify_current_shadow_price_context(value: Any) -> CurrentShadowPriceContext:
    if type(value) is not CurrentShadowPriceContext:
        raise ShadowPriceError("value must be exact CurrentShadowPriceContext")
    if value.source_context_mode == LEGACY_PR253_FIXTURE_BRIDGE:
        if value._bridge_bundle is None:
            raise ShadowPriceError("legacy context omitted retained fixture bridge")
        rebuilt = build_current_shadow_price_context(
            complete_current_history=value._complete_current_history,
            fixture_identity=value.fixture_identity,
            provider_event_evidence=value._event_evidence,
            fixture_quote_bridge=value._bridge_bundle,
        )
    elif value.source_context_mode == CURRENT_RECONCILIATION_DIRECT:
        if value._current_reconciliation_bundle is None:
            raise ShadowPriceError("direct current context omitted retained reconciliation")
        rebuilt = build_current_shadow_price_context_from_reconciliation(
            complete_current_history=value._complete_current_history,
            fixture_identity=value.fixture_identity,
            provider_event_id=value.provider_event_id,
            current_reconciliation_bundle=value._current_reconciliation_bundle,
        )
    else:
        raise ShadowPriceError("unknown current Shadow source-context mode")
    if _canonical_bytes(value.to_dict()) != _canonical_bytes(rebuilt.to_dict()):
        raise ShadowPriceError("current Shadow price context differs on source replay")
    return rebuilt


def _canonical_line(obs: prb.ProviderSemanticObservation) -> float | None:
    if obs.line is None:
        return None
    try:
        line = float(obs.line)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShadowPriceError("provider line is invalid") from exc
    if obs.canonical_market_id is MarketId.ASIAN_HANDICAP and obs.canonical_outcome_id is OutcomeId.AWAY:
        return -line
    return line


def build_current_shadow_exact_quotes(context: CurrentShadowPriceContext) -> tuple[ShadowExactQuote, ...]:
    """Issue complete exact current quote rows from typed PR-B observations."""
    if type(context) is not CurrentShadowPriceContext:
        raise ShadowPriceError("context type mismatch")
    checked = verify_current_shadow_price_context(context)
    inventory = checked.provider_inventory
    by_native = {selection.selection_identity: selection for selection in inventory.selections}
    if len(by_native) != len(inventory.selections):
        raise ShadowPriceError("provider inventory native identities are not unique")
    output: list[ShadowExactQuote] = []
    for coverage in checked.provider_registry.coverage:
        if coverage.provider_status not in {
            prb.ProviderSemanticStatus.SUPPORTED,
            prb.ProviderSemanticStatus.SUPPORTED_WITH_EXACT_LINE_POLICY,
        }:
            continue
        for observation in coverage.observations:
            if (
                observation.provider_event_id != checked.provider_event_id
                or observation.bookable is not True
                or observation.evidence_freshness is not prb.EvidenceFreshnessState.CURRENT
                or observation.line_analytically_eligible is not True
            ):
                continue
            if (
                observation.source_event_detail_raw_sha256,
                observation.source_manifest_sha256,
                observation.source_inventory_sha256,
            ) != (
                checked.source_raw_sha256,
                checked.source_manifest_sha256,
                checked.source_inventory_sha256,
            ):
                raise ShadowPriceError("PR-B observation ancestry differs from context")
            selected = by_native.get((
                observation.provider_event_id,
                observation.provider_market_id,
                observation.provider_specifier,
                observation.provider_outcome_id,
            ))
            if (
                selected is None
                or selected.market_name != observation.provider_market_name
                or selected.outcome_name != observation.provider_outcome_name
                or selected.bookable is not True
            ):
                raise ShadowPriceError("PR-B observation differs from exact provider selection")
            output.append(_issue_shadow_exact_quote(
                fixture_identity=checked.fixture_identity,
                provider_event_id=checked.provider_event_id,
                market_id=observation.canonical_market_id,
                outcome_id=observation.canonical_outcome_id,
                line=_canonical_line(observation),
                provider_line=observation.line,
                provider_market_id=selected.market_id,
                provider_market_name=selected.market_name,
                provider_specifier=selected.specifier,
                provider_outcome_id=selected.outcome_id,
                provider_outcome_name=selected.outcome_name,
                odds_raw=selected.odds_raw,
                decimal_odds=selected.odds_decimal,
                observed_at=inventory.observed_at,
                kickoff_utc=inventory.kickoff_utc,
                source_raw_sha256=checked.source_raw_sha256,
                source_manifest_sha256=checked.source_manifest_sha256,
                source_inventory_sha256=checked.source_inventory_sha256,
                provider_semantic_status=coverage.provider_status.value,
                provider_registry_sha256=checked.provider_registry_sha256,
                provider_observation_sha256=_sha256(observation.to_dict()),
                fixture_reconciliation_sha256=checked.fixture_reconciliation_sha256,
                current_mapping_rebind_sha256=checked.current_mapping_rebind_sha256,
                bridge_bundle_sha256=checked.bridge_bundle_sha256,
                bookable=True,
            ))
    ordered = tuple(sorted(
        output,
        key=lambda item: (
            item.market_id.value,
            item.outcome_id.value,
            -1.0 if item.line is None else item.line,
            item.provider_market_id,
            item.provider_specifier or "",
            item.provider_outcome_id,
        ),
    ))
    if len({item.identity_sha256 for item in ordered}) != len(ordered):
        raise ShadowPriceError("duplicate current Shadow quote identity")
    return ordered


__all__ = [
    "CURRENT_RECONCILIATION_DIRECT",
    "CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID",
    "CurrentShadowPriceContext",
    "LEGACY_PR253_FIXTURE_BRIDGE",
    "build_current_shadow_exact_quotes",
    "build_current_shadow_price_context",
    "build_current_shadow_price_context_from_reconciliation",
    "verify_current_shadow_price_context",
]
