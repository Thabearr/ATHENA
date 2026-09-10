"""Canonical football-probability contracts for ATHENA.

P1.2 separates model probability evidence from provider pricing and market
routing.  ``MarketProbabilityBundle`` contains only football probability
semantics, score-grid identity, specialist-model evidence and fail-closed
availability.  It cannot carry bookmaker odds, quote identities or a selected
market.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from domain.markets import MARKET_REGISTRY, MarketId, OutcomeId


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_MARKET_PROBABILITY_BUNDLE_V1"
PROBABILITY_SUM_TOLERANCE = 1e-12
SETTLEMENT_SUM_TOLERANCE = 1e-12
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "decimal_odds",
        "fair_decimal_odds",
        "implied_probability",
        "net_expected_value",
        "overround",
        "provider_event_id",
        "provider_market_id",
        "provider_observation_sha256",
        "provider_registry_sha256",
        "provider_semantic_status",
        "provider_specifier",
        "quote_identity_sha256",
        "recommended_market",
        "selected_market",
        "selected_selection",
    }
)
_FORBIDDEN_EVIDENCE_KEY_TOKENS = frozenset({"odds", "quote"})
_AUTHORITY_KEYS = (
    "production_probability",
    "pricing",
    "routing",
    "selection",
    "staking",
    "wager",
)
_OVERLAPPING_EVENT_MARKETS = frozenset(
    {MarketId.DOUBLE_CHANCE, MarketId.MATCH_RESULT_1UP, MarketId.MATCH_RESULT_2UP}
)
_SETTLEMENT_MARKETS = frozenset({MarketId.ASIAN_HANDICAP, MarketId.DRAW_NO_BET})
_SPECIALIST_MARKETS = frozenset(
    {
        MarketId.HOME_WIN_EITHER_HALF,
        MarketId.AWAY_WIN_EITHER_HALF,
        MarketId.MATCH_RESULT_1UP,
        MarketId.MATCH_RESULT_2UP,
    }
)
_SCORE_GRID_MARKETS = frozenset(set(MarketId) - {
    MarketId.HOME_WIN_EITHER_HALF,
    MarketId.AWAY_WIN_EITHER_HALF,
})


class MarketProbabilityError(ValueError):
    """Raised when canonical probability evidence is ambiguous or inconsistent."""


class ProbabilityAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"


class ProbabilityTopology(str, Enum):
    MUTUALLY_EXCLUSIVE_PARTITION = "MUTUALLY_EXCLUSIVE_PARTITION"
    OVERLAPPING_EVENTS = "OVERLAPPING_EVENTS"
    SETTLEMENT_DISTRIBUTIONS = "SETTLEMENT_DISTRIBUTIONS"


def _probability(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise MarketProbabilityError(f"{label} must be finite probability in [0, 1]")
    return float(value)


def _line(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise MarketProbabilityError(f"{label} must be finite numeric")
    result = float(value)
    return 0.0 if result == 0.0 else result


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise MarketProbabilityError(f"{label} must be non-empty exact text")
    return value


def _sha256(value: Any, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise MarketProbabilityError(f"{label} must be lowercase SHA-256 text")
    return value


def _authority() -> Mapping[str, bool]:
    return MappingProxyType({key: False for key in _AUTHORITY_KEYS})


def _reject_probability_boundary_escape(value: Any, path: str = "evidence") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if type(key) is not str or not key:
                raise MarketProbabilityError(f"{path} keys must be non-empty strings")
            lowered = key.lower()
            tokens = frozenset(re.split(r"[^a-z0-9]+", lowered))
            if lowered in _FORBIDDEN_EVIDENCE_KEYS or bool(
                tokens & _FORBIDDEN_EVIDENCE_KEY_TOKENS
            ):
                raise MarketProbabilityError(
                    f"{path}.{key} crosses probability/pricing-or-selection boundary"
                )
            _reject_probability_boundary_escape(item, f"{path}.{key}")
        return
    if type(value) in {list, tuple}:
        for index, item in enumerate(value):
            _reject_probability_boundary_escape(item, f"{path}[{index}]")


def _freeze_json(value: Any, label: str) -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise MarketProbabilityError(f"{label} contains non-finite float")
        return value
    if isinstance(value, Mapping):
        _reject_probability_boundary_escape(value, label)
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str or not key:
                raise MarketProbabilityError(f"{label} keys must be non-empty strings")
            frozen[key] = _freeze_json(item, f"{label}.{key}")
        return MappingProxyType(dict(sorted(frozen.items())))
    if type(value) in {list, tuple}:
        return tuple(_freeze_json(item, f"{label}[]") for item in value)
    raise MarketProbabilityError(
        f"{label} contains unsupported JSON value {type(value).__name__}"
    )


def _freeze_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MarketProbabilityError(f"{label} must be mapping")
    frozen = _freeze_json(value, label)
    if not isinstance(frozen, Mapping):
        raise MarketProbabilityError(f"{label} did not freeze as mapping")
    return frozen


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketProbabilityError("canonical probability serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MarketProbabilityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise MarketProbabilityError(f"non-finite JSON constant forbidden: {value}")


def _load_json(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise MarketProbabilityError("canonical probability input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarketProbabilityError("canonical probability JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise MarketProbabilityError("canonical probability JSON is invalid") from exc


@dataclass(frozen=True)
class EventProbability:
    outcome_id: OutcomeId
    probability: float
    line: float | None = None

    def __post_init__(self) -> None:
        if type(self.outcome_id) is not OutcomeId:
            raise MarketProbabilityError("event outcome_id must be exact OutcomeId")
        object.__setattr__(self, "probability", _probability(self.probability, "probability"))
        if self.line is not None:
            object.__setattr__(self, "line", _line(self.line, "event line"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id.value,
            "line": self.line,
            "probability": self.probability,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "EventProbability":
        if type(value) is not dict or set(value) != {"outcome_id", "line", "probability"}:
            raise MarketProbabilityError("EventProbability fields drifted")
        try:
            outcome = OutcomeId(value["outcome_id"])
        except (TypeError, ValueError) as exc:
            raise MarketProbabilityError("unknown canonical event outcome") from exc
        return cls(outcome_id=outcome, probability=value["probability"], line=value["line"])


@dataclass(frozen=True)
class SettlementProbabilityDistribution:
    outcome_id: OutcomeId
    full_win: float
    half_win: float
    push: float
    half_loss: float
    full_loss: float
    settlement_method: str
    line: float | None = None
    component_lines: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome_id not in {OutcomeId.HOME, OutcomeId.AWAY}:
            raise MarketProbabilityError("settlement outcome must be HOME or AWAY")
        values = []
        for field_name in ("full_win", "half_win", "push", "half_loss", "full_loss"):
            checked = _probability(getattr(self, field_name), field_name)
            object.__setattr__(self, field_name, checked)
            values.append(checked)
        if not math.isclose(
            math.fsum(values), 1.0, rel_tol=0.0, abs_tol=SETTLEMENT_SUM_TOLERANCE
        ):
            raise MarketProbabilityError("settlement probability mass must sum to 1")
        _text(self.settlement_method, "settlement_method")
        if self.line is None:
            if tuple(self.component_lines):
                raise MarketProbabilityError("component_lines require explicit line")
            object.__setattr__(self, "component_lines", ())
        else:
            object.__setattr__(self, "line", _line(self.line, "settlement line"))
            components = tuple(_line(item, "component line") for item in self.component_lines)
            object.__setattr__(self, "component_lines", components)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id.value,
            "full_win": self.full_win,
            "half_win": self.half_win,
            "push": self.push,
            "half_loss": self.half_loss,
            "full_loss": self.full_loss,
            "settlement_method": self.settlement_method,
            "line": self.line,
            "component_lines": list(self.component_lines),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SettlementProbabilityDistribution":
        required = {
            "outcome_id", "full_win", "half_win", "push", "half_loss",
            "full_loss", "settlement_method", "line", "component_lines",
        }
        if type(value) is not dict or set(value) != required:
            raise MarketProbabilityError("SettlementProbabilityDistribution fields drifted")
        try:
            outcome = OutcomeId(value["outcome_id"])
        except (TypeError, ValueError) as exc:
            raise MarketProbabilityError("unknown canonical settlement outcome") from exc
        if type(value["component_lines"]) is not list:
            raise MarketProbabilityError("component_lines must serialize as list")
        return cls(
            outcome_id=outcome,
            full_win=value["full_win"],
            half_win=value["half_win"],
            push=value["push"],
            half_loss=value["half_loss"],
            full_loss=value["full_loss"],
            settlement_method=value["settlement_method"],
            line=value["line"],
            component_lines=tuple(value["component_lines"]),
        )


@dataclass(frozen=True)
class SpecialistModelOutput:
    market_id: MarketId
    output_kind: str
    probability_method: str
    probability_input_namespace: str
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if type(self.market_id) is not MarketId or self.market_id not in _SPECIALIST_MARKETS:
            raise MarketProbabilityError("specialist output market is not canonical specialist market")
        _text(self.output_kind, "specialist output_kind")
        _text(self.probability_method, "specialist probability_method")
        _text(self.probability_input_namespace, "specialist probability_input_namespace")
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence, "specialist_evidence"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "output_kind": self.output_kind,
            "probability_method": self.probability_method,
            "probability_input_namespace": self.probability_input_namespace,
            "evidence": _thaw(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SpecialistModelOutput":
        required = {
            "market_id", "output_kind", "probability_method",
            "probability_input_namespace", "evidence",
        }
        if type(value) is not dict or set(value) != required or type(value["evidence"]) is not dict:
            raise MarketProbabilityError("SpecialistModelOutput fields drifted")
        try:
            market = MarketId(value["market_id"])
        except (TypeError, ValueError) as exc:
            raise MarketProbabilityError("unknown specialist market") from exc
        return cls(
            market_id=market,
            output_kind=value["output_kind"],
            probability_method=value["probability_method"],
            probability_input_namespace=value["probability_input_namespace"],
            evidence=value["evidence"],
        )


@dataclass(frozen=True)
class ScoreGridIdentity:
    sha256: str
    identity_method: str
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        _sha256(self.sha256, "score-grid SHA-256")
        _text(self.identity_method, "score-grid identity_method")
        object.__setattr__(self, "audit", _freeze_mapping(self.audit, "score_grid_audit"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "identity_method": self.identity_method,
            "audit": _thaw(self.audit),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ScoreGridIdentity":
        if type(value) is not dict or set(value) != {"sha256", "identity_method", "audit"}:
            raise MarketProbabilityError("ScoreGridIdentity fields drifted")
        if type(value["audit"]) is not dict:
            raise MarketProbabilityError("score-grid audit must serialize as object")
        return cls(
            sha256=value["sha256"],
            identity_method=value["identity_method"],
            audit=value["audit"],
        )


@dataclass(frozen=True)
class MarketProbabilityDistribution:
    market_id: MarketId
    availability: ProbabilityAvailability
    topology: ProbabilityTopology | None
    probability_method: str | None
    probability_input_namespace: str | None
    calibration_status: str | None
    event_probabilities: tuple[EventProbability, ...]
    settlement_distributions: tuple[SettlementProbabilityDistribution, ...]
    blocker_reason: str | None
    source_projection_sha256: str

    def __post_init__(self) -> None:
        if type(self.market_id) is not MarketId:
            raise MarketProbabilityError("market_id must be exact MarketId")
        if type(self.availability) is not ProbabilityAvailability:
            raise MarketProbabilityError("availability must be exact ProbabilityAvailability")
        _sha256(self.source_projection_sha256, "source_projection_sha256")
        if type(self.event_probabilities) is not tuple or any(
            type(item) is not EventProbability for item in self.event_probabilities
        ):
            raise MarketProbabilityError("event_probabilities must be exact tuple")
        if type(self.settlement_distributions) is not tuple or any(
            type(item) is not SettlementProbabilityDistribution
            for item in self.settlement_distributions
        ):
            raise MarketProbabilityError("settlement_distributions must be exact tuple")
        events = tuple(
            EventProbability(item.outcome_id, item.probability, item.line)
            for item in self.event_probabilities
        )
        settlements = tuple(
            SettlementProbabilityDistribution(
                outcome_id=item.outcome_id,
                full_win=item.full_win,
                half_win=item.half_win,
                push=item.push,
                half_loss=item.half_loss,
                full_loss=item.full_loss,
                settlement_method=item.settlement_method,
                line=item.line,
                component_lines=tuple(item.component_lines),
            )
            for item in self.settlement_distributions
        )

        if self.availability is ProbabilityAvailability.BLOCKED:
            if self.topology is not None or self.probability_method is not None:
                raise MarketProbabilityError("blocked market cannot claim topology/method")
            if self.probability_input_namespace is not None or events or settlements:
                raise MarketProbabilityError("blocked market cannot carry probability output")
            if type(self.blocker_reason) is not str or not self.blocker_reason.strip():
                raise MarketProbabilityError("blocked market requires blocker_reason")
        else:
            if type(self.topology) is not ProbabilityTopology:
                raise MarketProbabilityError("available market requires probability topology")
            _text(self.probability_method, "probability_method")
            _text(self.probability_input_namespace, "probability_input_namespace")
            _text(self.calibration_status, "calibration_status")
            if self.blocker_reason is not None:
                raise MarketProbabilityError("available market cannot carry blocker_reason")
            if bool(events) == bool(settlements):
                raise MarketProbabilityError("available market requires exactly one probability representation")
            self._validate_available(events, settlements)

        object.__setattr__(self, "event_probabilities", events)
        object.__setattr__(self, "settlement_distributions", settlements)

    def _validate_available(
        self,
        events: tuple[EventProbability, ...],
        settlements: tuple[SettlementProbabilityDistribution, ...],
    ) -> None:
        expected_outcomes = MARKET_REGISTRY[self.market_id].supported_outcomes
        if self.market_id in _SETTLEMENT_MARKETS:
            if self.topology is not ProbabilityTopology.SETTLEMENT_DISTRIBUTIONS or events:
                raise MarketProbabilityError("settlement market topology/representation mismatch")
            pairs = tuple((item.outcome_id, item.line) for item in settlements)
            if len(set(pairs)) != len(pairs):
                raise MarketProbabilityError("duplicate settlement outcome/line")
            if self.market_id is MarketId.DRAW_NO_BET:
                if pairs != ((OutcomeId.HOME, None), (OutcomeId.AWAY, None)):
                    raise MarketProbabilityError("DNB requires exact HOME/AWAY settlement order")
            else:
                home_lines = {item.line for item in settlements if item.outcome_id is OutcomeId.HOME}
                away_lines = {item.line for item in settlements if item.outcome_id is OutcomeId.AWAY}
                if not home_lines or None in home_lines or None in away_lines:
                    raise MarketProbabilityError("Asian Handicap requires explicit lines")
                if away_lines != {-float(line) for line in home_lines if line is not None}:
                    raise MarketProbabilityError("Asian Handicap HOME/AWAY line sets must be opposites")
            return

        if settlements:
            raise MarketProbabilityError("ordinary market cannot carry settlement distributions")
        if self.market_id is MarketId.TOTAL_GOALS:
            if self.topology is not ProbabilityTopology.MUTUALLY_EXCLUSIVE_PARTITION:
                raise MarketProbabilityError("Total Goals must be partition topology")
            self._validate_total_goals(events)
            return

        represented = tuple(item.outcome_id for item in events)
        if represented != expected_outcomes or any(item.line is not None for item in events):
            raise MarketProbabilityError("market event outcomes/order/line semantics drifted")
        if self.market_id in _OVERLAPPING_EVENT_MARKETS:
            if self.topology is not ProbabilityTopology.OVERLAPPING_EVENTS:
                raise MarketProbabilityError("overlapping market topology drifted")
        else:
            if self.topology is not ProbabilityTopology.MUTUALLY_EXCLUSIVE_PARTITION:
                raise MarketProbabilityError("ordinary partition topology drifted")
            if not math.isclose(
                math.fsum(item.probability for item in events),
                1.0,
                rel_tol=0.0,
                abs_tol=PROBABILITY_SUM_TOLERANCE,
            ):
                raise MarketProbabilityError("event probability partition must sum to 1")

    @staticmethod
    def _validate_total_goals(events: tuple[EventProbability, ...]) -> None:
        if not events:
            raise MarketProbabilityError("Total Goals requires at least one line")
        groups: dict[float, dict[OutcomeId, float]] = {}
        for item in events:
            if item.line is None or item.line < 0.0:
                raise MarketProbabilityError("Total Goals requires non-negative explicit lines")
            units = item.line * 2.0
            if units != float(round(units)) or round(units) % 2 != 1:
                raise MarketProbabilityError("Total Goals requires exact half-goal lines")
            bucket = groups.setdefault(item.line, {})
            if item.outcome_id in bucket:
                raise MarketProbabilityError("duplicate Total Goals outcome/line")
            bucket[item.outcome_id] = item.probability
        ordered = sorted(groups)
        previous_over: float | None = None
        previous_under: float | None = None
        for line in ordered:
            bucket = groups[line]
            if set(bucket) != {OutcomeId.OVER, OutcomeId.UNDER}:
                raise MarketProbabilityError("Total Goals line requires OVER and UNDER")
            if not math.isclose(
                math.fsum(bucket.values()), 1.0, rel_tol=0.0,
                abs_tol=PROBABILITY_SUM_TOLERANCE,
            ):
                raise MarketProbabilityError("Total Goals line probability mass must sum to 1")
            over = bucket[OutcomeId.OVER]
            under = bucket[OutcomeId.UNDER]
            if previous_over is not None and over > previous_over + PROBABILITY_SUM_TOLERANCE:
                raise MarketProbabilityError("Total Goals OVER probabilities must be monotone non-increasing")
            if previous_under is not None and under < previous_under - PROBABILITY_SUM_TOLERANCE:
                raise MarketProbabilityError("Total Goals UNDER probabilities must be monotone non-decreasing")
            previous_over, previous_under = over, under

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id.value,
            "availability": self.availability.value,
            "topology": None if self.topology is None else self.topology.value,
            "probability_method": self.probability_method,
            "probability_input_namespace": self.probability_input_namespace,
            "calibration_status": self.calibration_status,
            "event_probabilities": [item.to_dict() for item in self.event_probabilities],
            "settlement_distributions": [item.to_dict() for item in self.settlement_distributions],
            "blocker_reason": self.blocker_reason,
            "source_projection_sha256": self.source_projection_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "MarketProbabilityDistribution":
        required = {
            "market_id", "availability", "topology", "probability_method",
            "probability_input_namespace", "calibration_status", "event_probabilities",
            "settlement_distributions", "blocker_reason", "source_projection_sha256",
        }
        if type(value) is not dict or set(value) != required:
            raise MarketProbabilityError("MarketProbabilityDistribution fields drifted")
        if type(value["event_probabilities"]) is not list or type(value["settlement_distributions"]) is not list:
            raise MarketProbabilityError("probability collections must serialize as lists")
        try:
            market = MarketId(value["market_id"])
            availability = ProbabilityAvailability(value["availability"])
            topology = None if value["topology"] is None else ProbabilityTopology(value["topology"])
        except (TypeError, ValueError) as exc:
            raise MarketProbabilityError("probability distribution enum value drifted") from exc
        return cls(
            market_id=market,
            availability=availability,
            topology=topology,
            probability_method=value["probability_method"],
            probability_input_namespace=value["probability_input_namespace"],
            calibration_status=value["calibration_status"],
            event_probabilities=tuple(EventProbability.from_dict(item) for item in value["event_probabilities"]),
            settlement_distributions=tuple(
                SettlementProbabilityDistribution.from_dict(item)
                for item in value["settlement_distributions"]
            ),
            blocker_reason=value["blocker_reason"],
            source_projection_sha256=value["source_projection_sha256"],
        )


@dataclass(frozen=True)
class MarketProbabilityBundle:
    fixture_identity: str
    score_grid: ScoreGridIdentity | None
    markets: tuple[MarketProbabilityDistribution, ...]
    specialist_outputs: tuple[SpecialistModelOutput, ...]
    model_evidence: Mapping[str, Any] = field(default_factory=dict)
    authority: Mapping[str, bool] = field(default_factory=_authority)

    def __post_init__(self) -> None:
        _text(self.fixture_identity, "fixture_identity")
        if self.score_grid is not None and type(self.score_grid) is not ScoreGridIdentity:
            raise MarketProbabilityError("score_grid must be exact ScoreGridIdentity or None")
        if type(self.markets) is not tuple or any(
            type(item) is not MarketProbabilityDistribution for item in self.markets
        ):
            raise MarketProbabilityError("markets must be exact probability distribution tuple")
        if len(self.markets) != len(MarketId):
            raise MarketProbabilityError("bundle must contain exactly one row per canonical market")
        if tuple(item.market_id for item in self.markets) != tuple(MarketId):
            raise MarketProbabilityError("bundle market order must match canonical MarketId order")
        if type(self.specialist_outputs) is not tuple or any(
            type(item) is not SpecialistModelOutput for item in self.specialist_outputs
        ):
            raise MarketProbabilityError("specialist_outputs must be exact tuple")
        specialist_keys = tuple((item.market_id, item.output_kind) for item in self.specialist_outputs)
        if len(set(specialist_keys)) != len(specialist_keys):
            raise MarketProbabilityError("duplicate specialist output identity")
        by_market = {item.market_id: item for item in self.markets}
        specialist_markets = {item.market_id for item in self.specialist_outputs}
        for output in self.specialist_outputs:
            row = by_market[output.market_id]
            if row.availability is not ProbabilityAvailability.AVAILABLE:
                raise MarketProbabilityError("specialist output cannot attach to blocked market")
            if row.probability_method != output.probability_method:
                raise MarketProbabilityError("specialist output probability method drifted")
            if row.probability_input_namespace != output.probability_input_namespace:
                raise MarketProbabilityError("specialist output input namespace drifted")
        for market in _SPECIALIST_MARKETS:
            if by_market[market].availability is ProbabilityAvailability.AVAILABLE and market not in specialist_markets:
                raise MarketProbabilityError("available specialist market requires explicit specialist output")

        score_grid_required = any(
            row.availability is ProbabilityAvailability.AVAILABLE
            and row.market_id in _SCORE_GRID_MARKETS
            for row in self.markets
        )
        if score_grid_required and self.score_grid is None:
            raise MarketProbabilityError("score-grid-backed probability requires score-grid identity")
        if self.score_grid is not None:
            for output in self.specialist_outputs:
                value = output.evidence.get("score_matrix_sha256")
                if value is not None and value != self.score_grid.sha256:
                    raise MarketProbabilityError("specialist score-grid identity disagrees with bundle")

        evidence = _freeze_mapping(self.model_evidence, "model_evidence")
        if not isinstance(self.authority, Mapping) or set(self.authority) != set(_AUTHORITY_KEYS):
            raise MarketProbabilityError("probability authority keys drifted")
        if any(type(value) is not bool or value is not False for value in self.authority.values()):
            raise MarketProbabilityError("MarketProbabilityBundle cannot grant downstream authority")
        object.__setattr__(self, "model_evidence", evidence)
        object.__setattr__(self, "authority", _authority())

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    def market(self, market_id: MarketId) -> MarketProbabilityDistribution:
        if type(market_id) is not MarketId:
            raise MarketProbabilityError("market lookup requires exact MarketId")
        return self.markets[list(MarketId).index(market_id)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "fixture_identity": self.fixture_identity,
            "score_grid": None if self.score_grid is None else self.score_grid.to_dict(),
            "markets": [item.to_dict() for item in self.markets],
            "specialist_outputs": [item.to_dict() for item in self.specialist_outputs],
            "model_evidence": _thaw(self.model_evidence),
            "authority": dict(self.authority),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "MarketProbabilityBundle":
        required = {
            "schema_version", "policy_id", "fixture_identity", "score_grid",
            "markets", "specialist_outputs", "model_evidence", "authority",
        }
        if type(value) is not dict or set(value) != required:
            raise MarketProbabilityError("MarketProbabilityBundle fields drifted")
        if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise MarketProbabilityError("MarketProbabilityBundle schema version drifted")
        if value["policy_id"] != POLICY_ID:
            raise MarketProbabilityError("MarketProbabilityBundle policy identity drifted")
        if type(value["markets"]) is not list or type(value["specialist_outputs"]) is not list:
            raise MarketProbabilityError("bundle collections must serialize as lists")
        if type(value["model_evidence"]) is not dict or type(value["authority"]) is not dict:
            raise MarketProbabilityError("bundle evidence/authority must serialize as objects")
        score_grid = (
            None if value["score_grid"] is None
            else ScoreGridIdentity.from_dict(value["score_grid"])
        )
        return cls(
            fixture_identity=value["fixture_identity"],
            score_grid=score_grid,
            markets=tuple(MarketProbabilityDistribution.from_dict(item) for item in value["markets"]),
            specialist_outputs=tuple(SpecialistModelOutput.from_dict(item) for item in value["specialist_outputs"]),
            model_evidence=value["model_evidence"],
            authority=value["authority"],
        )

    @classmethod
    def from_canonical_bytes(cls, raw: bytes) -> "MarketProbabilityBundle":
        value = _load_json(raw)
        result = cls.from_dict(value)
        if canonical_json_bytes(result) != raw:
            raise MarketProbabilityError("MarketProbabilityBundle bytes are not canonical")
        return result


__all__ = [
    "EventProbability",
    "MarketProbabilityBundle",
    "MarketProbabilityDistribution",
    "MarketProbabilityError",
    "POLICY_ID",
    "ProbabilityAvailability",
    "ProbabilityTopology",
    "SCHEMA_VERSION",
    "ScoreGridIdentity",
    "SettlementProbabilityDistribution",
    "SpecialistModelOutput",
    "canonical_json_bytes",
    "canonical_sha256",
]
