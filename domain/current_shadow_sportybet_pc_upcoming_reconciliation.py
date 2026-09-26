"""Runtime reconciliation wrapper for the reviewed global pcUpcoming source.

This module is the only current Current Shadow/P3 discovery owner.  The source
contract remains owned by ``current_shadow_sportybet_pc_upcoming_discovery``;
this wrapper adds complete-pagination, identity, reconciliation, and direct
event-confirmation authority without creating another HTTP implementation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping, Sequence

from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_upcoming_reconciliation as legacy
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import sportybet_current_event_discovery_reconciliation as reviewed
from domain import sportybet_live_event_quote_evidence as live
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest

POLICY_ID = "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
STATUS = "CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_VERIFIED"
STRATEGY_ID = POLICY_ID
CURRENT_SHADOW_UPCOMING_POLICY_ID = POLICY_ID
DISCOVERY_SOURCE_METHOD = source.SOURCE_METHOD
UPCOMING_PATH = source.SOURCE_PATH
UPSTREAM_SOURCE_POLICY_ID = source.POLICY_ID
UPSTREAM_SOURCE_POLICY_SHA256 = "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
UPSTREAM_SOURCE_RECEIPT_SHA256 = "8dde6427c296d966ff8d7f4cdec33e57a8c4210e8ecdb37071af68b0ca75bb34"
BRIDGE_POLICY_ID = bridge.POLICY_ID
BRIDGE_POLICY_SHA256 = "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
BRIDGE_RECEIPT_SHA256 = "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2"
V2_REGISTRY_SHA256 = "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
IDENTITY_COMPATIBILITY_SHA256 = "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
DIRECT_EVENT_CONTRACT_SHA256 = live.EXPECTED_CONTRACT_SHA256
MAX_SOURCE_AGE_SECONDS = legacy.MAX_SOURCE_AGE_SECONDS
MINIMUM_LEAD_SECONDS = legacy.MINIMUM_LEAD_SECONDS
MAX_PAGES = source.MAX_PAGES
PAGE_SIZE = source.PAGE_SIZE
EVIDENCE_ROOT = source.EVIDENCE_ROOT
ALLOWED_OUTPUT_RELATIVE = EVIDENCE_ROOT
INCOMPLETE_PAGINATION_STATE = "PC_UPCOMING_RUNTIME_PAGINATION_INCOMPLETE"
PROSPECTIVE_DISCOVERY_ELIGIBLE = legacy.PROSPECTIVE_DISCOVERY_ELIGIBLE
PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS = legacy.PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS
PcUpcomingDiscoveryManifest = source.PcUpcomingDiscoveryManifest

AUTHORITY = MappingProxyType({
    "research_shadow_provider_acquisition": True,
    "p3_pre_router_provider_acquisition": True,
    "fixture_reconciliation": True,
    "direct_event_confirmation": True,
    "model": False,
    "pricing": False,
    "router": False,
    "portfolio": False,
    "production_main": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class PcUpcomingRuntimeReconciliationError(ValueError):
    """Raised when the runtime wrapper cannot prove a complete safe source."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _policy_payload() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "status": STATUS,
        "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
        "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
        "source_receipt_sha256": UPSTREAM_SOURCE_RECEIPT_SHA256,
        "bridge_policy_id": BRIDGE_POLICY_ID,
        "bridge_policy_sha256": BRIDGE_POLICY_SHA256,
        "bridge_receipt_sha256": BRIDGE_RECEIPT_SHA256,
        "v2_semantic_registry_sha256": V2_REGISTRY_SHA256,
        "identity_compatibility_sha256": IDENTITY_COMPATIBILITY_SHA256,
        "source_method": DISCOVERY_SOURCE_METHOD,
        "source_path": UPCOMING_PATH,
        "fixed_query": {
            "sportId": source.FOOTBALL_SPORT_ID,
            "marketId": source.MARKET_ID,
            "pageSize": source.PAGE_SIZE,
            "todayGames": source.TODAY_GAMES,
            "timeline": source.TIMELINE_HOURS,
            "pageNum": "CONTIGUOUS_1_THROUGH_CEIL_PROVIDER_TOTAL_NUM_OVER_PAGE_SIZE",
            "_t": "RESPONSE_SCOPED_NONCE",
        },
        "runtime_pagination": {
            "required": True,
            "pagination_complete_exact_true": True,
            "captured_event_count_equals_provider_total_num": True,
            "required_page_count": "CEIL_PROVIDER_TOTAL_NUM_OVER_100",
            "max_pages": MAX_PAGES,
            "partial_capture_provider_absence_authority": False,
        },
        "identity_observation_order": [
            "EXACT_PROVIDER_RAW_PAGE_BYTES",
            "RAW_ANCESTRY_BOUND_ATHENA_PROVIDER_IDENTITY_PROJECTION",
        ],
        "provider_identity_source_ancestry": "EXACT_PC_UPCOMING_PAGE_RAW_SHA256",
        "direct_event_contract_sha256": DIRECT_EVENT_CONTRACT_SHA256,
        "reconciliation": {
            "kickoff": "EXACT_FULL_UTC",
            "orientation": "EXACT_HOME_AWAY",
            "international_bridge": "EXACT_REVIEWED_PROVIDER_FAMILY_ONLY",
            "no_fallback_source": True,
        },
        "authority": dict(AUTHORITY),
    }


def calculate_policy_sha256() -> str:
    return hashlib.sha256(_canonical(_policy_payload())).hexdigest()


PINNED_POLICY_SHA256 = "5721d136035205aa48b9b214343e4816bcbf1e986d72e940a26010d4f792a3a9"
EXPECTED_CONTRACT_SHA256 = PINNED_POLICY_SHA256
CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 = PINNED_POLICY_SHA256


def validate_contract() -> Mapping[str, Any]:
    if source.POLICY_ID != UPSTREAM_SOURCE_POLICY_ID or source.calculate_policy_sha256() != UPSTREAM_SOURCE_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("PR #405 pcUpcoming source policy ancestry drifted")
    if bridge.POLICY_ID != BRIDGE_POLICY_ID or bridge.calculate_policy_sha256() != BRIDGE_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("PR #406 international bridge ancestry drifted")
    if fixture_identity_v2.registry_sha256() != V2_REGISTRY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("V2 semantic identity registry pin drifted")
    if identity_compatibility.calculate_policy_sha256() != IDENTITY_COMPATIBILITY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("identity compatibility policy pin drifted")
    if calculate_policy_sha256() != PINNED_POLICY_SHA256:
        raise PcUpcomingRuntimeReconciliationError("pcUpcoming runtime wrapper policy SHA drifted")
    for key, value in AUTHORITY.items():
        if type(value) is not bool:
            raise PcUpcomingRuntimeReconciliationError(f"authority value {key} is not boolean")
    return MappingProxyType({
        "runtime_policy_id": POLICY_ID,
        "runtime_policy_sha256": PINNED_POLICY_SHA256,
        "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
        "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
        "bridge_policy_id": BRIDGE_POLICY_ID,
        "bridge_policy_sha256": BRIDGE_POLICY_SHA256,
        "v2_semantic_registry_sha256": V2_REGISTRY_SHA256,
        "identity_compatibility_policy_sha256": IDENTITY_COMPATIBILITY_SHA256,
        "source_method": DISCOVERY_SOURCE_METHOD,
        "source_path": UPCOMING_PATH,
        "pagination_complete_required": True,
    })


def _require_complete(manifest: source.PcUpcomingDiscoveryManifest) -> None:
    required_pages = max(1, (manifest.provider_total_num + PAGE_SIZE - 1) // PAGE_SIZE)
    if (
        manifest.pagination_complete is not True
        or manifest.captured_event_count != manifest.provider_total_num
        or manifest.captured_page_count != required_pages
        or tuple(page.page_num for page in manifest.pages) != tuple(range(1, required_pages + 1))
        or required_pages > MAX_PAGES
    ):
        raise PcUpcomingRuntimeReconciliationError(INCOMPLETE_PAGINATION_STATE)


def capture_current_pc_upcoming_discovery(
    *, repository_root: str | Path, execute_live_network: bool
) -> tuple[Path, source.PcUpcomingDiscoveryManifest]:
    """Use the PR #405 source owner verbatim, then require complete runtime scope."""
    validate_contract()
    manifest = source.capture_current_pc_upcoming_discovery(
        repository_root=repository_root, execute_live_network=execute_live_network
    )
    _require_complete(manifest)
    return Path(repository_root) / EVIDENCE_ROOT, manifest


def capture_current_upcoming_discovery(
    *, repository_root: str | Path, execute_live_network: bool
) -> tuple[Path, source.PcUpcomingDiscoveryManifest]:
    """Runner-compatible module seam; source remains the reviewed pcUpcoming owner."""
    return capture_current_pc_upcoming_discovery(
        repository_root=repository_root, execute_live_network=execute_live_network
    )


def verify_current_pc_upcoming_discovery(
    *, repository_root: str | Path, manifest: Mapping[str, Any] | None = None
) -> source.PcUpcomingDiscoveryManifest:
    validate_contract()
    rebuilt = source.verify_current_pc_upcoming_discovery(
        repository_root=repository_root, manifest=manifest
    )
    _require_complete(rebuilt)
    return rebuilt


def prospective_discovery_assessment(
    manifest: source.PcUpcomingDiscoveryManifest, *, evaluation_time: datetime
) -> Mapping[str, Any]:
    _require_complete(manifest)
    evaluation = evaluation_time.astimezone(timezone.utc)
    events = manifest.events
    prematch = sum(item.prematch_bookable_observed is True for item in events)
    inplay = sum(item.event_status in (1, "1") for item in events)
    future = sum(item.prematch_bookable_observed is True and
                 (item.kickoff_utc - evaluation).total_seconds() > MINIMUM_LEAD_SECONDS
                 for item in events)
    too_close = sum((item.kickoff_utc - evaluation).total_seconds() <= MINIMUM_LEAD_SECONDS
                    for item in events)
    verdict = PROSPECTIVE_DISCOVERY_ELIGIBLE if future else PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS
    return MappingProxyType({
        "provider_event_count": manifest.captured_event_count,
        "provider_total_num": manifest.provider_total_num,
        "provider_prematch_bookable_count": prematch,
        "provider_inplay_count": inplay,
        "provider_future_lead_eligible_count": future,
        "provider_too_close_count": too_close,
        "provider_discovery_source_method": DISCOVERY_SOURCE_METHOD,
        "provider_discovery_strategy_id": STRATEGY_ID,
        "provider_discovery_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_first_observed_at": manifest.first_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_last_observed_at": manifest.last_observed_at.isoformat().replace("+00:00", "Z"),
        "provider_discovery_pagination_complete": True,
        "source_viability": verdict,
        "captured_page_count": manifest.captured_page_count,
    })


@dataclass(frozen=True, init=False)
class CurrentShadowPcUpcomingReconciliationBundle:
    _legacy_bundle: Any
    manifest: source.PcUpcomingDiscoveryManifest
    repository_root: Path

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PcUpcomingRuntimeReconciliationError("runtime reconciliation bundles are builder-only")

    @property
    def rows(self):
        return self._legacy_bundle.rows

    @property
    def matched_rows(self):
        return self._legacy_bundle.matched_rows

    @property
    def contract_sha256(self) -> str:
        return PINNED_POLICY_SHA256

    @property
    def canonical_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "dataset_name": "athena-current-shadow-pc-upcoming-runtime-reconciliation-v1",
            "status": STATUS,
            "runtime_policy_id": POLICY_ID,
            "runtime_policy_sha256": PINNED_POLICY_SHA256,
            "source_policy_id": UPSTREAM_SOURCE_POLICY_ID,
            "source_policy_sha256": UPSTREAM_SOURCE_POLICY_SHA256,
            "manifest_sha256": self.manifest.canonical_sha256,
            "provider_total_num": self.manifest.provider_total_num,
            "captured_event_count": self.manifest.captured_event_count,
            "captured_page_count": self.manifest.captured_page_count,
            "pagination_complete": self.manifest.pagination_complete,
            "reconciliation": self._legacy_bundle.to_dict(),
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._legacy_bundle, name)


def _provider_events(manifest: source.PcUpcomingDiscoveryManifest) -> tuple[reviewed.SportyBetDiscoveredEvent, ...]:
    return tuple(reviewed.SportyBetDiscoveredEvent(
        event_id=event.event_id,
        home_team_name=event.home_team_name,
        away_team_name=event.away_team_name,
        competition_name=event.tournament_name,
        competition_basis="EXACT_NATIVE_CATEGORY_TOURNAMENT_ANCESTRY",
        kickoff_utc=event.kickoff_utc,
        booking_status=event.booking_status,
        event_status=event.event_status,
        match_status=event.match_status,
        prematch_bookable_observed=event.prematch_bookable_observed,
        source_page_num=event.source_page_num,
        source_raw_sha256=event.source_raw_sha256,
        source_observed_at=event.source_observed_at,
    ) for event in manifest.events)


def _identity_scope(
    captures: Sequence[Any], raw_pages: Sequence[bytes], manifest: source.PcUpcomingDiscoveryManifest
) -> None:
    try:
        identity_compatibility.begin_identity_scope(
            captures,
            provider_raw_bytes=tuple(raw_pages),
            provider_identity_projection_bytes=(source.provider_identity_projection_bytes(manifest),),
        )
    except Exception as exc:
        raise PcUpcomingRuntimeReconciliationError("raw pages and ancestry-bound provider projection failed identity observation") from exc


def _read_pages(repository_root: Path, manifest: source.PcUpcomingDiscoveryManifest) -> tuple[bytes, ...]:
    root = repository_root / EVIDENCE_ROOT
    rows: list[bytes] = []
    for page in manifest.pages:
        relative = f"pages/page-{page.page_num:03d}.raw.json"
        raw = (root / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != page.raw_sha256:
            raise PcUpcomingRuntimeReconciliationError("provider raw page changed after manifest verification")
        rows.append(raw)
    return tuple(rows)


def _provisional_details(repository: Path, manifest: source.PcUpcomingDiscoveryManifest,
                         admission: Any, *, execute_live_network: bool,
                         retained_details: Mapping[str, Path] | None = None) -> dict[str, Path]:
    reviewed_rows = reviewed._reviewed_rows(admission)
    events = tuple(legacy._project_event_labels(item) for item in _provider_events(manifest))
    provisional: dict[str, tuple[str, tuple[Any, ...]]] = {}
    for event in events:
        if not event.prematch_bookable_observed or event.competition_name is None:
            provisional[event.event_id] = ("NO_MATCH", ())
            continue
        matches = legacy._match_current_shadow_event(event, reviewed_rows)
        provisional[event.event_id] = ("UNIQUE" if len(matches) == 1 else "AMBIGUOUS" if matches else "NO_MATCH", matches)
    targets = Counter(matches[0].source_fixture_identifier for state, matches in provisional.values() if state == "UNIQUE")
    expected = {event_id for event_id, (state, matches) in provisional.items()
                if state == "UNIQUE" and targets[matches[0].source_fixture_identifier] == 1}
    if retained_details is not None:
        if set(retained_details) != expected:
            raise PcUpcomingRuntimeReconciliationError("retained direct detail set differs from exact provider candidates")
        return {key: Path(value) for key, value in retained_details.items()}
    details: dict[str, Path] = {}
    for event_id in sorted(expected):
        if execute_live_network is True:
            directory, _detail_manifest = live.capture_live_event_quote_evidence(
                event_id=event_id, repository_root=repository, execute_live_network=True
            )
            live_inventory = legacy.tolerant_inventory.build_shadow_live_event_quote_inventory(
                directory, repository_root=repository
            )
            if live_inventory.event_id != event_id:
                raise PcUpcomingRuntimeReconciliationError("direct event detail identity changed")
            details[event_id] = directory
        else:
            path = repository / live.ALLOWED_OUTPUT_RELATIVE / event_id.replace(":", "-")
            if not path.is_dir():
                raise PcUpcomingRuntimeReconciliationError(f"direct event-detail evidence missing for {event_id}")
            details[event_id] = path
    return details


def _validate_direct_native_ancestry(
    repository: Path,
    manifest: source.PcUpcomingDiscoveryManifest,
    detail_directories: Mapping[str, Path],
) -> None:
    """If direct detail repeats native category ancestry, require exact agreement."""
    event_by_id = {event.event_id: event for event in manifest.events}
    for event_id, directory in detail_directories.items():
        raw_path = Path(directory) / live.RAW_FILENAME
        try:
            raw = raw_path.read_bytes()
            payload = live.strict_json_loads(raw)
            detail = live._event_object(payload, event_id)
        except Exception as exc:
            raise PcUpcomingRuntimeReconciliationError(
                f"direct event-detail raw replay failed for {event_id}"
            ) from exc
        event = event_by_id.get(event_id)
        if event is None:
            raise PcUpcomingRuntimeReconciliationError("direct event ID is absent from pcUpcoming manifest")
        sport = detail.get("sport") if type(detail) is dict else None
        category = sport.get("category") if type(sport) is dict else None
        tournament = category.get("tournament") if type(category) is dict else None
        observations = (
            (category, "id", event.category_id),
            (category, "name", event.category_name),
            (tournament, "id", event.tournament_id),
            (tournament, "name", event.tournament_name),
        )
        for parent, field, expected in observations:
            if type(parent) is dict and field in parent and parent[field] != expected:
                raise PcUpcomingRuntimeReconciliationError(
                    f"direct event native {field} conflicts with pcUpcoming ancestry for {event_id}"
                )
        for field, expected in (("categoryId", event.category_id), ("tournamentId", event.tournament_id)):
            if field in detail and detail[field] != expected:
                raise PcUpcomingRuntimeReconciliationError(
                    f"direct event native {field} conflicts with pcUpcoming ancestry for {event_id}"
                )


def _build(
    *, repository_root: Path, manifest: source.PcUpcomingDiscoveryManifest,
    admission: Any, captures: tuple[tuple[bytes, FotMobDataMatchesCaptureManifest], ...],
    execute_live_network: bool, retained_details: Mapping[str, Path] | None = None,
    evaluation_time: datetime | None = None,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    _require_complete(manifest)
    raw_pages = _read_pages(repository_root, manifest)
    _identity_scope(captures, raw_pages, manifest)
    details = _provisional_details(repository_root, manifest, admission,
                                   execute_live_network=execute_live_network,
                                   retained_details=retained_details)
    _validate_direct_native_ancestry(repository_root, manifest, details)
    # Reuse the already-reviewed reconciliation row builder after adapting only
    # the event interface. Provider-native ancestry was observed above first.
    fake_discovery = SimpleNamespace(
        canonical_sha256=manifest.canonical_sha256,
        events=_provider_events(manifest),
    )
    rebuilt = legacy._build_bundle(
        repository_root=repository_root,
        discovery_directory=repository_root / EVIDENCE_ROOT,
        discovery=fake_discovery,
        admission=admission,
        captures=captures,
        detail_directories=details,
        evaluation_time=reviewed._now_utc() if evaluation_time is None else evaluation_time,
    )
    snapshot = legacy._identity_state_snapshot()
    object.__setattr__(rebuilt, "_fixture_stable_identity_state_sha256", legacy._identity_state_sha256(snapshot))
    object.__setattr__(rebuilt, "_fixture_stable_identity_state_snapshot", snapshot)
    object.__setattr__(rebuilt, "contract_sha256", PINNED_POLICY_SHA256)
    object.__setattr__(rebuilt, "dataset_name", "athena-current-shadow-pc-upcoming-runtime-reconciliation-v1")
    object.__setattr__(rebuilt, "status", STATUS)
    bundle = object.__new__(CurrentShadowPcUpcomingReconciliationBundle)
    object.__setattr__(bundle, "_legacy_bundle", rebuilt)
    object.__setattr__(bundle, "manifest", manifest)
    object.__setattr__(bundle, "repository_root", repository_root)
    return bundle


def reconcile_current_events_from_pc_upcoming_discovery(
    *, repository_root: str | Path, discovery_evidence_directory: str | Path,
    fotmob_admission_value: Any, fotmob_captures: Sequence[Any],
    execute_live_network: bool,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    validate_contract()
    repository = Path(repository_root).resolve(strict=True)
    expected_dir = repository / EVIDENCE_ROOT
    if Path(discovery_evidence_directory).resolve(strict=True) != expected_dir.resolve(strict=True):
        raise PcUpcomingRuntimeReconciliationError("runtime discovery directory is not the reviewed pcUpcoming evidence root")
    manifest = verify_current_pc_upcoming_discovery(repository_root=repository)
    try:
        captures = reviewed._materialize_fotmob_captures(fotmob_captures)
        admission = reviewed._rederive_exact_fotmob_admission(fotmob_admission_value, captures)
    except reviewed.SportyBetCurrentEventDiscoveryError as exc:
        raise PcUpcomingRuntimeReconciliationError(str(exc)) from exc
    return _build(repository_root=repository, manifest=manifest, admission=admission,
                  captures=captures, execute_live_network=execute_live_network)


def reconcile_current_events_from_upcoming_discovery(**kwargs: Any) -> CurrentShadowPcUpcomingReconciliationBundle:
    """Runner-compatible alias retained while the active owner changes."""
    return reconcile_current_events_from_pc_upcoming_discovery(**kwargs)


def discover_and_reconcile_current_events(
    *, repository_root: str | Path, fotmob_admission_value: Any,
    fotmob_captures: Sequence[Any], execute_live_network: bool,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    if execute_live_network is not True:
        raise PcUpcomingRuntimeReconciliationError("live runtime capture requires exact execute_live_network=True")
    directory, _manifest = capture_current_pc_upcoming_discovery(
        repository_root=repository_root, execute_live_network=True
    )
    return reconcile_current_events_from_pc_upcoming_discovery(
        repository_root=repository_root, discovery_evidence_directory=directory,
        fotmob_admission_value=fotmob_admission_value, fotmob_captures=fotmob_captures,
        execute_live_network=True,
    )


def verify_current_pc_upcoming_reconciliation_bundle(
    value: CurrentShadowPcUpcomingReconciliationBundle,
) -> CurrentShadowPcUpcomingReconciliationBundle:
    if type(value) is not CurrentShadowPcUpcomingReconciliationBundle:
        raise PcUpcomingRuntimeReconciliationError("value must be exact pcUpcoming runtime bundle")
    validate_contract()
    retained_state = getattr(value._legacy_bundle, "_fixture_stable_identity_state_snapshot", None)
    retained_sha = getattr(value._legacy_bundle, "_fixture_stable_identity_state_sha256", None)
    if type(retained_state) is not dict or legacy._identity_state_sha256(retained_state) != retained_sha:
        raise PcUpcomingRuntimeReconciliationError("identity-state replay ancestry is missing or changed")
    manifest = verify_current_pc_upcoming_discovery(repository_root=value.repository_root,
                                                    manifest=value.manifest.to_dict())
    details = dict(value._legacy_bundle._detail_directories)
    captures = reviewed._materialize_fotmob_captures(value._legacy_bundle._fotmob_captures)
    admission = reviewed._rederive_exact_fotmob_admission(value._legacy_bundle._fotmob_admission, captures)
    rebuilt = _build(repository_root=value.repository_root, manifest=manifest,
                     admission=admission, captures=captures,
                     execute_live_network=False, retained_details=details,
                     evaluation_time=value._legacy_bundle.evaluation_time)
    if _canonical(value.to_dict()) != _canonical(rebuilt.to_dict()):
        raise PcUpcomingRuntimeReconciliationError("pcUpcoming reconciliation differs from exact offline replay")
    legacy._verify_identity_state_append_only_extension(retained_state, legacy._identity_state_snapshot())
    object.__setattr__(rebuilt._legacy_bundle, "_fixture_stable_identity_state_sha256", retained_sha)
    object.__setattr__(rebuilt._legacy_bundle, "_fixture_stable_identity_state_snapshot", retained_state)
    return rebuilt


def verify_current_event_discovery_reconciliation_bundle(value: CurrentShadowPcUpcomingReconciliationBundle):
    return verify_current_pc_upcoming_reconciliation_bundle(value)


__all__ = [
    "AUTHORITY", "CurrentShadowPcUpcomingReconciliationBundle", "DISCOVERY_SOURCE_METHOD",
    "CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256", "CURRENT_SHADOW_UPCOMING_POLICY_ID",
    "ALLOWED_OUTPUT_RELATIVE", "EVIDENCE_ROOT", "EXPECTED_CONTRACT_SHA256", "INCOMPLETE_PAGINATION_STATE",
    "MAX_PAGES", "MINIMUM_LEAD_SECONDS", "PcUpcomingDiscoveryManifest",
    "PINNED_POLICY_SHA256", "POLICY_ID", "PROSPECTIVE_DISCOVERY_ELIGIBLE",
    "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS", "STATUS", "STRATEGY_ID", "UPCOMING_PATH",
    "PcUpcomingRuntimeReconciliationError", "calculate_policy_sha256", "capture_current_pc_upcoming_discovery",
    "capture_current_upcoming_discovery", "discover_and_reconcile_current_events", "prospective_discovery_assessment",
    "reconcile_current_events_from_pc_upcoming_discovery", "reconcile_current_events_from_upcoming_discovery",
    "validate_contract", "verify_current_event_discovery_reconciliation_bundle",
    "verify_current_pc_upcoming_discovery", "verify_current_pc_upcoming_reconciliation_bundle",
]
