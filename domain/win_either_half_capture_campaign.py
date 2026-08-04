"""Deterministic Stage 5B3 prospective capture-campaign planning.

This module creates an immutable, provider-neutral schedule for collecting the
Stage 5B2 Win Either Half observation attempts. It never fetches odds, records
prices, selects a decision offset, or enables either market.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketId
from domain.model_status import MODEL_STATUS_REGISTRY, ModelStatus
from domain.win_either_half_prospective_replay import (
    validate_protocol_contract as validate_stage_5b2_protocol_contract,
)


SCHEMA_VERSION = 1
DATASET_NAME = "win-either-half-prospective-capture-campaign-v1"
PROTOCOL_DATASET_NAME = (
    "win-either-half-prospective-capture-campaign-protocol-v1"
)
DEFAULT_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "research-protocols"
    / "win-either-half-prospective-capture-campaign-v1.json"
)
DEFAULT_STAGE_5B2_PROTOCOL_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "research-protocols"
    / "win-either-half-prospective-replay-v1.json"
)

STAGE_5B2_PROTOCOL_DATASET_NAME = (
    "win-either-half-prospective-replay-protocol-v1"
)
FROZEN_CANDIDATE_OFFSETS_SECONDS = (
    86400,
    21600,
    10800,
    3600,
    1800,
    900,
)
ATTEMPT_WINDOW_SECONDS = 300
EXPECTED_TASKS_PER_FIXTURE = 12
MINIMUM_FIXTURES_FOR_INTERPRETATION = 100
PERMITTED_MARKETS = (
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
)
PERMITTED_SOURCE_STATUSES = (
    "QUALIFIED_FOR_HISTORICAL_RESEARCH",
    "QUALIFIED_FOR_PROSPECTIVE_REPLAY_ONLY",
)
PERMITTED_ATTEMPT_RESULTS = (
    "QUOTES_CAPTURED",
    "MARKET_UNAVAILABLE",
    "FIXTURE_UNAVAILABLE",
    "SOURCE_UNAVAILABLE",
    "CAPTURE_ERROR",
)
PERMITTED_QUOTE_OUTCOMES = ("YES", "NO")

CAMPAIGN_COMMITMENT_STATUS = "UNFROZEN_LOCAL_PLAN"
PROSPECTIVE_CLAIM_AUTHORIZED = False

FORBIDDEN_FIELDS = frozenset(
    {
        "acca_selection",
        "away_goals",
        "bet",
        "bet_decision",
        "bookmaker_odds",
        "calibrated_probability",
        "decision_label",
        "decimal_odds",
        "edge",
        "edge_pp",
        "expected_value",
        "fair_odds",
        "full_time_away_goals",
        "full_time_home_goals",
        "half_time_away_goals",
        "half_time_home_goals",
        "home_goals",
        "kelly",
        "kelly_stake",
        "label",
        "model_probability",
        "profit",
        "profitability",
        "settled_outcome",
        "stake",
        "target",
        "target_value",
    }
)

_FIXTURES_TOP_LEVEL_KEYS = frozenset({"schema_version", "fixtures"})
_FIXTURE_KEYS = frozenset({"fixture_identifier", "kickoff"})


class CaptureCampaignError(ValueError):
    """Raised when campaign evidence or configuration fails closed."""


class TaskState(str, Enum):
    PLANNED = "PLANNED"


@dataclass(frozen=True)
class SourceQualification:
    provider_identifier: str
    prospective_replay_status: str


@dataclass(frozen=True)
class CampaignTarget:
    source: str
    bookmaker_identifier: str
    capture_method: str


def build_campaign_target(
    *,
    source: Any,
    bookmaker_identifier: Any,
    capture_method: Any,
) -> CampaignTarget:
    return CampaignTarget(
        source=_require_non_empty_string(source, "source"),
        bookmaker_identifier=_require_non_empty_string(
            bookmaker_identifier,
            "bookmaker_identifier",
        ),
        capture_method=_require_non_empty_string(
            capture_method,
            "capture_method",
        ),
    )


@dataclass(frozen=True)
class CampaignFixture:
    fixture_identifier: str
    kickoff: datetime


@dataclass(frozen=True)
class CaptureTask:
    schema_version: int
    campaign_id: str
    task_id: str
    provider_identifier: str
    source: str
    bookmaker_identifier: str
    capture_method: str
    fixture_identifier: str
    market_id: MarketId
    line: None
    offset_seconds_before_kickoff: int
    scheduled_at: datetime
    capture_window_opens_at: datetime
    capture_window_closes_at: datetime
    task_state: TaskState

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "task_id": self.task_id,
            "provider_identifier": self.provider_identifier,
            "source": self.source,
            "bookmaker_identifier": self.bookmaker_identifier,
            "capture_method": self.capture_method,
            "fixture_identifier": self.fixture_identifier,
            "market_id": self.market_id.value,
            "line": None,
            "offset_seconds_before_kickoff": (
                self.offset_seconds_before_kickoff
            ),
            "scheduled_at": serialize_utc(self.scheduled_at),
            "capture_window_opens_at": serialize_utc(
                self.capture_window_opens_at
            ),
            "capture_window_closes_at": serialize_utc(
                self.capture_window_closes_at
            ),
            "task_state": self.task_state.value,
        }


@dataclass(frozen=True)
class CampaignPlan:
    campaign_id: str
    provider_identifier: str
    source_status: str
    source: str
    bookmaker_identifier: str
    capture_method: str
    anchor_at: datetime
    fixtures: tuple[CampaignFixture, ...]
    tasks: tuple[CaptureTask, ...]

    @property
    def interpretation_eligible(self) -> bool:
        return len(self.fixtures) >= MINIMUM_FIXTURES_FOR_INTERPRETATION

    @property
    def campaign_commitment_status(self) -> str:
        return CAMPAIGN_COMMITMENT_STATUS

    @property
    def prospective_claim_authorized(self) -> bool:
        return PROSPECTIVE_CLAIM_AUTHORIZED

    @property
    def commitment_deadline_at(self) -> datetime:
        return min(task.capture_window_opens_at for task in self.tasks)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureCampaignError(f"{label} must be a non-empty string")
    if value != value.strip():
        raise CaptureCampaignError(
            f"{label} must not contain leading or trailing whitespace"
        )
    return value


def parse_utc(value: Any, label: str) -> datetime:
    """Parse a timezone-aware timestamp and normalize it to UTC."""

    if isinstance(value, bool) or value is None:
        raise CaptureCampaignError(f"{label} must be a UTC timestamp")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text or text != value:
            raise CaptureCampaignError(
                f"{label} must not be blank or padded with whitespace"
            )
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise CaptureCampaignError(
                f"{label} is not a valid ISO-8601 timestamp"
            ) from error
    else:
        raise CaptureCampaignError(f"{label} must be a UTC timestamp")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CaptureCampaignError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def serialize_utc(value: datetime) -> str:
    normalized = parse_utc(value, "timestamp")
    text = normalized.isoformat(timespec="microseconds")
    if text.endswith(".000000+00:00"):
        text = text.replace(".000000+00:00", "Z")
    else:
        text = text.replace("+00:00", "Z")
    return text


def _walk_mapping_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized == "safety":
                continue
            yield normalized
            yield from _walk_mapping_keys(child)
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            yield from _walk_mapping_keys(child)


def assert_no_forbidden_fields(value: Any, label: str) -> None:
    found = sorted(FORBIDDEN_FIELDS.intersection(_walk_mapping_keys(value)))
    if found:
        raise CaptureCampaignError(
            f"{label} contains forbidden fields: {', '.join(found)}"
        )


def _require_schema_version(payload: Mapping[str, Any], label: str) -> None:
    version = payload.get("schema_version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        raise CaptureCampaignError(
            f"{label} schema_version must be exactly {SCHEMA_VERSION}"
        )


def load_source_qualification(
    payload: Mapping[str, Any],
) -> SourceQualification:
    """Validate the Stage 5B1 qualification subset required for planning."""

    if not isinstance(payload, Mapping):
        raise CaptureCampaignError(
            "Source qualification payload must be an object"
        )
    assert_no_forbidden_fields(payload, "Source qualification")
    _require_schema_version(payload, "Source qualification")

    dataset_name = payload.get("dataset_name")
    if dataset_name != "win-either-half-pricing-source-qualification-v1":
        raise CaptureCampaignError(
            "Source qualification dataset_name is not the Stage 5B1 report"
        )

    provider_identifier = _require_non_empty_string(
        payload.get("provider_identifier"),
        "provider_identifier",
    )

    qualification = payload.get("qualification")
    if not isinstance(qualification, Mapping):
        raise CaptureCampaignError(
            "Source qualification must contain a qualification object"
        )
    status = qualification.get("prospective_replay_status")
    if status not in PERMITTED_SOURCE_STATUSES:
        raise CaptureCampaignError(
            "prospective_replay_status is not permitted for Stage 5B3"
        )

    holdout = payload.get("holdout_governance")
    if not isinstance(holdout, Mapping):
        raise CaptureCampaignError(
            "Source qualification must contain holdout_governance"
        )
    if holdout.get("prospective_validation_required") is not True:
        raise CaptureCampaignError(
            "prospective_validation_required must be exactly true"
        )
    if holdout.get("production_approval_authorized") is not False:
        raise CaptureCampaignError(
            "production_approval_authorized must be exactly false"
        )

    market_statuses = payload.get("market_statuses")
    if not isinstance(market_statuses, Mapping):
        raise CaptureCampaignError(
            "Source qualification must contain market_statuses"
        )
    for market in PERMITTED_MARKETS:
        if market_statuses.get(market.value) != "DISABLED":
            raise CaptureCampaignError(
                f"{market.value} must remain DISABLED"
            )

    no_production = payload.get("no_production_approval")
    if not isinstance(no_production, str) or not no_production.strip():
        raise CaptureCampaignError(
            "Source qualification must state no production approval"
        )

    return SourceQualification(
        provider_identifier=provider_identifier,
        prospective_replay_status=status,
    )


def load_fixtures(payload: Mapping[str, Any]) -> tuple[CampaignFixture, ...]:
    """Load the exact Stage 5B2-compatible fixture catalog."""

    if not isinstance(payload, Mapping):
        raise CaptureCampaignError("Fixtures payload must be an object")
    assert_no_forbidden_fields(payload, "Fixtures")
    if set(payload) != _FIXTURES_TOP_LEVEL_KEYS:
        raise CaptureCampaignError(
            "Fixtures payload must contain exactly schema_version and fixtures"
        )
    _require_schema_version(payload, "Fixtures")

    records = payload.get("fixtures")
    if not isinstance(records, list):
        raise CaptureCampaignError("fixtures must be a list")
    if not records:
        raise CaptureCampaignError("fixtures must not be empty")

    fixtures: list[CampaignFixture] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise CaptureCampaignError(
                f"fixtures[{index}] must be an object"
            )
        if set(record) != _FIXTURE_KEYS:
            raise CaptureCampaignError(
                f"fixtures[{index}] has an unexpected schema"
            )
        fixture_identifier = _require_non_empty_string(
            record.get("fixture_identifier"),
            f"fixtures[{index}].fixture_identifier",
        )
        if fixture_identifier in seen:
            raise CaptureCampaignError(
                f"Duplicate fixture_identifier: {fixture_identifier}"
            )
        seen.add(fixture_identifier)
        kickoff = parse_utc(record.get("kickoff"), f"fixtures[{index}].kickoff")
        fixtures.append(
            CampaignFixture(
                fixture_identifier=fixture_identifier,
                kickoff=kickoff,
            )
        )

    return tuple(
        sorted(fixtures, key=lambda item: (item.kickoff, item.fixture_identifier))
    )


def validate_stage_5b2_protocol(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path = DEFAULT_STAGE_5B2_PROTOCOL_PATH,
) -> None:
    """Validate Stage 5B2 protocol using exact byte and Python contract verification."""

    try:
        validate_stage_5b2_protocol_contract(
            payload,
            raw_bytes,
            committed_path=committed_path,
        )
    except ValueError as error:
        raise CaptureCampaignError(
            f"Stage 5B2 protocol validation failed: {error}"
        ) from error


def validate_campaign_protocol(
    payload: Mapping[str, Any],
    raw_bytes: bytes,
    *,
    committed_path: Path = DEFAULT_PROTOCOL_PATH,
) -> None:
    """Validate Stage 5B3 protocol using exact byte and Python contract verification."""

    if not committed_path.is_file():
        raise CaptureCampaignError(
            f"Committed Stage 5B3 protocol is missing: {committed_path}"
        )

    committed_raw = committed_path.read_bytes()
    try:
        committed_payload = json.loads(committed_raw.decode("utf-8"))
    except Exception as error:
        raise CaptureCampaignError(
            "Committed Stage 5B3 protocol is invalid"
        ) from error

    if raw_bytes != committed_raw:
        raise CaptureCampaignError(
            "Supplied Stage 5B3 protocol bytes differ from committed protocol"
        )
    if payload != committed_payload:
        raise CaptureCampaignError(
            "Supplied Stage 5B3 protocol differs from committed protocol"
        )
    if committed_payload != build_expected_protocol_contract():
        raise CaptureCampaignError(
            "Committed Stage 5B3 protocol drifted from Python contract"
        )


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        value,
    ):
        raise CaptureCampaignError(f"{label} must be a full SHA-256")
    return value.lower()


def _campaign_identity_payload(
    *,
    provider_identifier: str,
    source_status: str,
    anchor_at: datetime,
    fixtures: Sequence[CampaignFixture],
    stage_5b2_protocol_sha256: str,
    campaign_protocol_sha256: str,
    source_qualification_sha256: str,
    target: CampaignTarget,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "provider_identifier": provider_identifier,
        "source_status": source_status,
        "source_qualification_sha256": validate_sha256(
            source_qualification_sha256, "source_qualification_sha256"
        ),
        "source": target.source,
        "bookmaker_identifier": target.bookmaker_identifier,
        "capture_method": target.capture_method,
        "anchor_at": serialize_utc(anchor_at),
        "candidate_offsets_seconds": list(
            FROZEN_CANDIDATE_OFFSETS_SECONDS
        ),
        "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
        "stage_5b2_protocol_sha256": validate_sha256(
            stage_5b2_protocol_sha256, "stage_5b2_protocol_sha256"
        ),
        "campaign_protocol_sha256": validate_sha256(
            campaign_protocol_sha256, "campaign_protocol_sha256"
        ),
        "fixtures": [
            {
                "fixture_identifier": fixture.fixture_identifier,
                "kickoff": serialize_utc(fixture.kickoff),
            }
            for fixture in fixtures
        ],
    }


def build_campaign_id(**kwargs: Any) -> str:
    digest = _sha256_hex(_canonical_json_bytes(_campaign_identity_payload(**kwargs)))
    return f"WEH-CAP-{digest[:24].upper()}"


def build_task_id(
    *,
    campaign_id: str,
    fixture_identifier: str,
    market_id: MarketId,
    offset_seconds_before_kickoff: int,
    scheduled_at: datetime,
    source: str,
    bookmaker_identifier: str,
    capture_method: str,
) -> str:
    payload = {
        "campaign_id": campaign_id,
        "fixture_identifier": fixture_identifier,
        "market_id": market_id.value,
        "offset_seconds_before_kickoff": offset_seconds_before_kickoff,
        "scheduled_at": serialize_utc(scheduled_at),
        "source": source,
        "bookmaker_identifier": bookmaker_identifier,
        "capture_method": capture_method,
    }
    digest = _sha256_hex(_canonical_json_bytes(payload))
    return f"WEH-TASK-{digest[:24].upper()}"


def build_campaign_plan(
    *,
    source_qualification: SourceQualification,
    target: CampaignTarget,
    fixtures: Sequence[CampaignFixture],
    anchor_at: datetime,
    stage_5b2_protocol_sha256: str,
    campaign_protocol_sha256: str,
    source_qualification_sha256: str,
) -> CampaignPlan:
    """Build all 12 immutable observation tasks for every fixture."""

    anchor = parse_utc(anchor_at, "anchor_at")
    validate_sha256(stage_5b2_protocol_sha256, "stage_5b2_protocol_sha256")
    validate_sha256(campaign_protocol_sha256, "campaign_protocol_sha256")
    validate_sha256(source_qualification_sha256, "source_qualification_sha256")

    normalized_fixtures = tuple(
        sorted(fixtures, key=lambda item: (item.kickoff, item.fixture_identifier))
    )
    if not normalized_fixtures:
        raise CaptureCampaignError("Campaign requires at least one fixture")

    for fixture in normalized_fixtures:
        earliest_scheduled = fixture.kickoff - timedelta(
            seconds=max(FROZEN_CANDIDATE_OFFSETS_SECONDS)
        )
        earliest_window_open = earliest_scheduled - timedelta(
            seconds=ATTEMPT_WINDOW_SECONDS
        )
        if earliest_window_open < anchor:
            raise CaptureCampaignError(
                "Campaign anchor is later than the first capture window for "
                f"fixture {fixture.fixture_identifier}"
            )

    campaign_id = build_campaign_id(
        provider_identifier=source_qualification.provider_identifier,
        source_status=source_qualification.prospective_replay_status,
        source_qualification_sha256=source_qualification_sha256,
        target=target,
        anchor_at=anchor,
        fixtures=normalized_fixtures,
        stage_5b2_protocol_sha256=stage_5b2_protocol_sha256,
        campaign_protocol_sha256=campaign_protocol_sha256,
    )

    tasks: list[CaptureTask] = []
    seen_task_ids: set[str] = set()
    for fixture in normalized_fixtures:
        for market in sorted(PERMITTED_MARKETS, key=lambda item: item.value):
            for offset in FROZEN_CANDIDATE_OFFSETS_SECONDS:
                scheduled_at = fixture.kickoff - timedelta(seconds=offset)
                opens_at = scheduled_at - timedelta(
                    seconds=ATTEMPT_WINDOW_SECONDS
                )
                closes_at = scheduled_at + timedelta(
                    seconds=ATTEMPT_WINDOW_SECONDS
                )
                if closes_at >= fixture.kickoff:
                    raise CaptureCampaignError(
                        "Capture window must close strictly before kickoff"
                    )
                task_id = build_task_id(
                    campaign_id=campaign_id,
                    fixture_identifier=fixture.fixture_identifier,
                    market_id=market,
                    offset_seconds_before_kickoff=offset,
                    scheduled_at=scheduled_at,
                    source=target.source,
                    bookmaker_identifier=target.bookmaker_identifier,
                    capture_method=target.capture_method,
                )
                if task_id in seen_task_ids:
                    raise CaptureCampaignError("Duplicate task identity")
                seen_task_ids.add(task_id)
                tasks.append(
                    CaptureTask(
                        schema_version=SCHEMA_VERSION,
                        campaign_id=campaign_id,
                        task_id=task_id,
                        provider_identifier=(
                            source_qualification.provider_identifier
                        ),
                        source=target.source,
                        bookmaker_identifier=target.bookmaker_identifier,
                        capture_method=target.capture_method,
                        fixture_identifier=fixture.fixture_identifier,
                        market_id=market,
                        line=None,
                        offset_seconds_before_kickoff=offset,
                        scheduled_at=scheduled_at,
                        capture_window_opens_at=opens_at,
                        capture_window_closes_at=closes_at,
                        task_state=TaskState.PLANNED,
                    )
                )

    ordered_tasks = tuple(
        sorted(
            tasks,
            key=lambda item: (
                item.scheduled_at,
                item.fixture_identifier,
                item.market_id.value,
                item.offset_seconds_before_kickoff,
                item.task_id,
            ),
        )
    )
    expected = len(normalized_fixtures) * EXPECTED_TASKS_PER_FIXTURE
    if len(ordered_tasks) != expected:
        raise CaptureCampaignError(
            f"Expected {expected} tasks, created {len(ordered_tasks)}"
        )

    return CampaignPlan(
        campaign_id=campaign_id,
        provider_identifier=source_qualification.provider_identifier,
        source_status=source_qualification.prospective_replay_status,
        source=target.source,
        bookmaker_identifier=target.bookmaker_identifier,
        capture_method=target.capture_method,
        anchor_at=anchor,
        fixtures=normalized_fixtures,
        tasks=ordered_tasks,
    )


def market_registry_snapshot() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market in sorted(MARKET_REGISTRY, key=lambda item: item.value):
        definition = MARKET_REGISTRY[market]
        rows.append(
            {
                "market_id": market.value,
                "family": definition.family.value,
                "display_name": definition.display_name,
                "supported_outcomes": [
                    outcome.value for outcome in definition.supported_outcomes
                ],
                "line_required": definition.line_required,
            }
        )
    return rows


def model_status_snapshot() -> dict[str, str]:
    return {
        market.value: MODEL_STATUS_REGISTRY[market].status.value
        for market in sorted(MODEL_STATUS_REGISTRY, key=lambda item: item.value)
    }


def assert_market_safety() -> None:
    if len(MARKET_REGISTRY) != 15:
        raise CaptureCampaignError(
            f"Expected 15 canonical markets, found {len(MARKET_REGISTRY)}"
        )
    for market in PERMITTED_MARKETS:
        if MODEL_STATUS_REGISTRY[market].status != ModelStatus.DISABLED:
            raise CaptureCampaignError(f"{market.value} must remain DISABLED")


def build_expected_protocol_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": PROTOCOL_DATASET_NAME,
        "upstream_stage_5b2": {
            "dataset_name": STAGE_5B2_PROTOCOL_DATASET_NAME,
            "candidate_offsets_seconds": list(
                FROZEN_CANDIDATE_OFFSETS_SECONDS
            ),
            "attempt_window_seconds": ATTEMPT_WINDOW_SECONDS,
            "expected_attempts_per_fixture": EXPECTED_TASKS_PER_FIXTURE,
            "minimum_fixtures_for_interpretation": (
                MINIMUM_FIXTURES_FOR_INTERPRETATION
            ),
            "selected_offset_seconds": None,
            "selection_authorized": False,
        },
        "source_qualification_contract": {
            "accepted_prospective_replay_statuses": list(
                PERMITTED_SOURCE_STATUSES
            ),
            "prospective_validation_required": True,
            "production_approval_authorized": False,
            "both_markets_must_remain_disabled": True,
        },
        "campaign_target_contract": {
            "source_required": True,
            "bookmaker_identifier_required": True,
            "capture_method_required": True,
            "constant_across_campaign": True,
            "included_in_campaign_identity": True,
            "included_in_task_identity": True,
        },
        "fixture_contract": {
            "schema_version": SCHEMA_VERSION,
            "required_fields": ["fixture_identifier", "kickoff"],
            "fixture_identifiers_unique": True,
            "kickoff_timezone": "UTC",
            "anchor_must_not_follow_first_window_open": True,
        },
        "commitment_contract": {
            "campaign_commitment_status": "UNFROZEN_LOCAL_PLAN",
            "prospective_claim_authorized": False,
            "local_anchor_is_not_trusted_creation_time_proof": True,
            "tracked_commitment_required_before_first_window": True,
        },
        "task_contract": {
            "task_state": TaskState.PLANNED.value,
            "markets": [market.value for market in PERMITTED_MARKETS],
            "line": None,
            "candidate_offsets_seconds": list(
                FROZEN_CANDIDATE_OFFSETS_SECONDS
            ),
            "capture_window_seconds_before_and_after_scheduled_at": (
                ATTEMPT_WINDOW_SECONDS
            ),
            "expected_attempt_results": list(PERMITTED_ATTEMPT_RESULTS),
            "expected_quote_outcomes": list(PERMITTED_QUOTE_OUTCOMES),
            "tasks_per_fixture": EXPECTED_TASKS_PER_FIXTURE,
            "deterministic_task_ids": True,
            "no_wall_clock_time_used": True,
            "source_frozen": True,
            "bookmaker_identifier_frozen": True,
            "capture_method_frozen": True,
        },
        "output_contract": {
            "tasks_jsonl": "capture-campaign-tasks-v1.jsonl",
            "summary_json": "capture-campaign-summary-v1.json",
            "manifest_json": "capture-campaign-manifest-v1.json",
            "all_outputs_ignored": True,
            "transactional_write_required": True,
            "selected_offset_seconds": None,
            "selection_authorized": False,
            "production_approval_authorized": False,
            "repository_output_policy": "DEFAULT_IGNORED_ROOT_OR_OUTSIDE_REPOSITORY",
            "symlink_outputs_forbidden": True,
            "campaign_commitment_status": "UNFROZEN_LOCAL_PLAN",
            "prospective_claim_authorized": False,
        },
        "forbidden_fields": sorted(FORBIDDEN_FIELDS),
        "safety": {
            "network_requests": False,
            "scraping": False,
            "browser_automation": False,
            "credential_use": False,
            "odds_collection": False,
            "provider_qualification": False,
            "offset_selection": False,
            "market_activation": False,
            "bet_decision": False,
        },
        "no_production_approval": True,
    }


def validate_full_git_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", value
    ):
        raise CaptureCampaignError(f"{label} must be a full Git SHA")
    return value.lower()
