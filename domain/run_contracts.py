"""Canonical immutable orchestration contracts for ATHENA.

P1.1 establishes the unversioned RunRequest/RunReceipt boundary before any
command surface is migrated.  This module is intentionally pure: it imports no
provider, model, pricing, router, portfolio, Current Shadow, login, wallet,
staking, or wager implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CANONICAL_RUN_CONTRACT_V1"
REQUEST_CONTRACT = "RunRequest"
RECEIPT_CONTRACT = "RunReceipt"
AUTHORITY_PROFILE_IDS = frozenset({"MAIN", "SHADOW"})
MIN_TARGET_LEGS = 1
MAX_TARGET_LEGS = 50
MIN_SELECTED_DATES = 1
MAX_SELECTED_DATES = 7
_ADAPTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.ASCII)
_REQUIRED_AUTHORITY_CAPABILITIES = (
    "provider_acquisition",
    "share_code_generation",
    "login",
    "cookies",
    "wallet",
    "staking",
    "wager",
)
_SENSITIVE_CAPABILITIES = ("login", "cookies", "wallet", "staking", "wager")
_ADDITIONAL_DENIED_TRUE_NAMES = frozenset(
    {
        "phase6",
        "place_wager",
        "sportybet_execution",
        "stake_submitted",
        "wager_placed",
    }
)
_ADDITIONAL_DENIED_TRUE_TOKENS = frozenset(
    {"bet", "cookie", "cookies", "login", "stake", "staking", "wager", "wallet"}
)


class RunContractError(ValueError):
    """Raised when a canonical run contract fails closed."""


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RunContractError(f"{label} must be non-empty exact text")
    return value


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RunContractError(f"{label} must be exact bool")
    return value


def _exact_schema(value: Any, label: str) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise RunContractError(f"{label} schema version drifted")


def _sha40(value: Any, label: str) -> str:
    if type(value) is not str:
        raise RunContractError(f"{label} must be exact Git SHA text")
    lowered = value.lower()
    if len(lowered) != 40 or any(ch not in "0123456789abcdef" for ch in lowered):
        raise RunContractError(f"{label} must be exact 40-character Git SHA")
    return lowered


def _utc(value: Any, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise RunContractError(f"{label} must be timezone-aware datetime")
    try:
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RunContractError(f"{label} is invalid") from exc


def _iso(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_iso(value: Any, label: str) -> datetime:
    text = _exact_text(value, label)
    if not text.endswith("Z"):
        raise RunContractError(f"{label} must be canonical UTC text ending Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise RunContractError(f"{label} is not valid ISO-8601 UTC") from exc
    checked = _utc(parsed, label)
    if _iso(checked) != text:
        raise RunContractError(f"{label} is not canonical microsecond UTC text")
    return checked


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise RunContractError("target_total_odds must be positive finite Decimal or None")
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        text = "0"
    return text


def _parse_decimal_text(value: Any) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or not value or value != value.strip():
        raise RunContractError("target_total_odds must be canonical decimal text or null")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RunContractError("target_total_odds is invalid decimal text") from exc
    if _decimal_text(parsed) != value:
        raise RunContractError("target_total_odds is not canonical decimal text")
    return parsed


def _freeze_json(value: Any, label: str = "value") -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise RunContractError(f"{label} contains non-finite float")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str or not key:
                raise RunContractError(f"{label} mapping keys must be non-empty strings")
            frozen[key] = _freeze_json(item, f"{label}.{key}")
        return MappingProxyType(dict(sorted(frozen.items())))
    if type(value) in {list, tuple}:
        return tuple(_freeze_json(item, f"{label}[]") for item in value)
    raise RunContractError(f"{label} contains unsupported JSON value {type(value).__name__}")


def _freeze_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RunContractError(f"{label} must be mapping")
    frozen = _freeze_json(value, label)
    if not isinstance(frozen, Mapping):
        raise RunContractError(f"{label} did not freeze as mapping")
    return frozen


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
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
        raise RunContractError("canonical run-contract serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_constant(value: str) -> None:
    raise RunContractError(f"non-finite JSON constant is forbidden: {value}")


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RunContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_canonical_json(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise RunContractError("canonical JSON input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunContractError("canonical JSON is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise RunContractError("canonical JSON is invalid") from exc
    return value


@dataclass(frozen=True)
class AuthorityManifest:
    """Per-run side-effect permission manifest.

    The capability vocabulary comes from the architecture specification. P1.1
    can describe reviewed acquisition/share-code research, but cannot grant
    credential, wallet, staking, or wager authority in either execution profile.
    """

    authority_profile: str
    mode: str
    provider_acquisition: bool
    share_code_generation: bool
    login: bool = False
    cookies: bool = False
    wallet: bool = False
    staking: bool = False
    wager: bool = False
    additional_capabilities: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.authority_profile not in AUTHORITY_PROFILE_IDS:
            raise RunContractError("authority_profile escaped MAIN/SHADOW vocabulary")
        _exact_text(self.mode, "mode")
        for key in _REQUIRED_AUTHORITY_CAPABILITIES:
            _exact_bool(getattr(self, key), key)
        if any(getattr(self, key) is not False for key in _SENSITIVE_CAPABILITIES):
            raise RunContractError(
                "P1.1 cannot grant login/cookies/wallet/staking/wager authority"
            )
        if not isinstance(self.additional_capabilities, Mapping):
            raise RunContractError("additional_capabilities must be mapping")
        checked: dict[str, bool] = {}
        for key, value in self.additional_capabilities.items():
            _exact_text(key, "additional capability name")
            checked_value = _exact_bool(value, f"additional capability {key}")
            if key in _REQUIRED_AUTHORITY_CAPABILITIES:
                if checked_value is not getattr(self, key):
                    raise RunContractError(
                        f"additional capability {key} contradicts canonical capability"
                    )
            elif checked_value is True:
                tokens = frozenset(key.split("_"))
                if (
                    key.startswith("production_")
                    or key in _ADDITIONAL_DENIED_TRUE_NAMES
                    or bool(tokens & _ADDITIONAL_DENIED_TRUE_TOKENS)
                ):
                    raise RunContractError(
                        f"additional capability {key} cannot grant production/sensitive authority"
                    )
            checked[key] = checked_value
        object.__setattr__(
            self,
            "additional_capabilities",
            MappingProxyType(dict(sorted(checked.items()))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_profile": self.authority_profile,
            "mode": self.mode,
            "capabilities": {
                key: getattr(self, key) for key in _REQUIRED_AUTHORITY_CAPABILITIES
            },
            "additional_capabilities": dict(self.additional_capabilities),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AuthorityManifest":
        if type(value) is not dict or set(value) != {
            "authority_profile", "mode", "capabilities", "additional_capabilities"
        }:
            raise RunContractError("AuthorityManifest fields drifted")
        capabilities = value["capabilities"]
        if type(capabilities) is not dict or set(capabilities) != set(_REQUIRED_AUTHORITY_CAPABILITIES):
            raise RunContractError("AuthorityManifest capability fields drifted")
        additional = value["additional_capabilities"]
        if type(additional) is not dict:
            raise RunContractError("AuthorityManifest additional capabilities must be object")
        return cls(
            authority_profile=value["authority_profile"],
            mode=value["mode"],
            additional_capabilities=additional,
            **capabilities,
        )


@dataclass(frozen=True)
class RunRequest:
    """Resolved orchestration request; no relative day tokens survive this boundary."""

    dates: tuple[date, ...]
    target_legs: int
    target_total_odds: Decimal | None
    bookie: str
    mode: str
    authority_profile: str
    create_share_code: bool
    place_wager: bool = False

    def __post_init__(self) -> None:
        try:
            items = tuple(self.dates)
        except TypeError as exc:
            raise RunContractError("RunRequest dates must be iterable concrete dates") from exc
        if not MIN_SELECTED_DATES <= len(items) <= MAX_SELECTED_DATES:
            raise RunContractError("RunRequest must contain one through seven concrete dates")
        if any(type(item) is not date for item in items):
            raise RunContractError("RunRequest dates must be exact datetime.date values")
        if len(set(items)) != len(items):
            raise RunContractError("RunRequest dates must be unique")
        object.__setattr__(self, "dates", tuple(sorted(items)))
        if type(self.target_legs) is not int or not MIN_TARGET_LEGS <= self.target_legs <= MAX_TARGET_LEGS:
            raise RunContractError("target_legs must be exact integer from 1 through 50")
        _decimal_text(self.target_total_odds)
        bookie = _exact_text(self.bookie, "bookie")
        if _ADAPTER_ID_RE.fullmatch(bookie) is None:
            raise RunContractError("bookie must be lowercase delivery-adapter identifier")
        _exact_text(self.mode, "mode")
        if self.authority_profile not in AUTHORITY_PROFILE_IDS:
            raise RunContractError("authority_profile escaped MAIN/SHADOW vocabulary")
        _exact_bool(self.create_share_code, "create_share_code")
        _exact_bool(self.place_wager, "place_wager")
        if self.place_wager is not False:
            raise RunContractError("P1.1 RunRequest cannot request wager placement")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "contract": REQUEST_CONTRACT,
            "dates": [item.isoformat() for item in self.dates],
            "target_legs": self.target_legs,
            "target_total_odds": _decimal_text(self.target_total_odds),
            "bookie": self.bookie,
            "mode": self.mode,
            "authority_profile": self.authority_profile,
            "create_share_code": self.create_share_code,
            "place_wager": self.place_wager,
        }

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    @classmethod
    def from_dict(cls, value: Any) -> "RunRequest":
        required = {
            "schema_version", "policy_id", "contract", "dates", "target_legs",
            "target_total_odds", "bookie", "mode", "authority_profile",
            "create_share_code", "place_wager",
        }
        if type(value) is not dict or set(value) != required:
            raise RunContractError("RunRequest fields drifted")
        _exact_schema(value["schema_version"], "RunRequest")
        if value["policy_id"] != POLICY_ID or value["contract"] != REQUEST_CONTRACT:
            raise RunContractError("RunRequest contract identity drifted")
        raw_dates = value["dates"]
        if type(raw_dates) is not list:
            raise RunContractError("RunRequest dates must serialize as list")
        parsed_dates: list[date] = []
        for text in raw_dates:
            if type(text) is not str:
                raise RunContractError("RunRequest date text must be exact string")
            try:
                parsed = date.fromisoformat(text)
            except ValueError as exc:
                raise RunContractError("RunRequest date is not valid YYYY-MM-DD") from exc
            if parsed.isoformat() != text:
                raise RunContractError("RunRequest date is not canonical YYYY-MM-DD")
            parsed_dates.append(parsed)
        request = cls(
            dates=tuple(parsed_dates),
            target_legs=value["target_legs"],
            target_total_odds=_parse_decimal_text(value["target_total_odds"]),
            bookie=value["bookie"],
            mode=value["mode"],
            authority_profile=value["authority_profile"],
            create_share_code=value["create_share_code"],
            place_wager=value["place_wager"],
        )
        if request.to_dict() != value:
            raise RunContractError("RunRequest is not in canonical normalized form")
        return request

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "RunRequest":
        value = _load_canonical_json(raw)
        request = cls.from_dict(value)
        if canonical_json_bytes(request) != raw:
            raise RunContractError("RunRequest JSON bytes are not canonical")
        return request


@dataclass(frozen=True)
class RunStage:
    """One stage checkpoint carried by a canonical RunReceipt."""

    stage: str
    status: str
    observed_at: datetime | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _exact_text(self.stage, "stage")
        _exact_text(self.status, "stage status")
        if self.observed_at is not None:
            object.__setattr__(self, "observed_at", _utc(self.observed_at, "stage observed_at"))
        if not isinstance(self.counts, Mapping):
            raise RunContractError("stage counts must be mapping")
        counts: dict[str, int] = {}
        for key, value in self.counts.items():
            _exact_text(key, "stage count name")
            if type(value) is not int or value < 0:
                raise RunContractError(f"stage count {key} must be non-negative exact int")
            counts[key] = value
        object.__setattr__(self, "counts", MappingProxyType(dict(sorted(counts.items()))))
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence, "stage evidence"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "observed_at": None if self.observed_at is None else _iso(self.observed_at),
            "counts": dict(self.counts),
            "evidence": _thaw_json(self.evidence),
        }

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    @classmethod
    def from_dict(cls, value: Any) -> "RunStage":
        if type(value) is not dict or set(value) != {
            "stage", "status", "observed_at", "counts", "evidence"
        }:
            raise RunContractError("RunStage fields drifted")
        observed = None if value["observed_at"] is None else _parse_iso(value["observed_at"], "stage observed_at")
        return cls(
            stage=value["stage"],
            status=value["status"],
            observed_at=observed,
            counts=value["counts"],
            evidence=value["evidence"],
        )


@dataclass(frozen=True)
class RunReceipt:
    """Durable canonical result of one resolved RunRequest."""

    status: str
    observed_at: datetime
    exact_commit_sha: str
    request: RunRequest
    stages: tuple[RunStage, ...]
    counts: Mapping[str, int]
    selected_legs: tuple[Mapping[str, Any], ...]
    shortfall: int
    share_code_result: Mapping[str, Any] | None
    authority_manifest: AuthorityManifest
    evidence: Mapping[str, Any] = field(default_factory=dict)
    wager_placed: bool = False

    def __post_init__(self) -> None:
        _exact_text(self.status, "receipt status")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "receipt observed_at"))
        object.__setattr__(self, "exact_commit_sha", _sha40(self.exact_commit_sha, "exact_commit_sha"))
        if type(self.request) is not RunRequest:
            raise RunContractError("request must be exact RunRequest")
        try:
            stages = tuple(self.stages)
        except TypeError as exc:
            raise RunContractError("stages must be iterable RunStage values") from exc
        if any(type(stage) is not RunStage for stage in stages):
            raise RunContractError("stages must contain exact RunStage values")
        object.__setattr__(self, "stages", stages)
        if not isinstance(self.counts, Mapping):
            raise RunContractError("receipt counts must be mapping")
        counts: dict[str, int] = {}
        for key, value in self.counts.items():
            _exact_text(key, "receipt count name")
            if type(value) is not int or value < 0:
                raise RunContractError(f"receipt count {key} must be non-negative exact int")
            counts[key] = value
        if "selected_leg_count" not in counts:
            raise RunContractError("receipt counts must include selected_leg_count")
        object.__setattr__(self, "counts", MappingProxyType(dict(sorted(counts.items()))))
        try:
            legs = tuple(self.selected_legs)
        except TypeError as exc:
            raise RunContractError("selected_legs must be iterable mappings") from exc
        frozen_legs: list[Mapping[str, Any]] = []
        for index, leg in enumerate(legs):
            frozen_legs.append(_freeze_mapping(leg, f"selected_legs[{index}]"))
        object.__setattr__(self, "selected_legs", tuple(frozen_legs))
        if counts["selected_leg_count"] != len(frozen_legs):
            raise RunContractError("selected_leg_count differs from selected_legs")
        if type(self.shortfall) is not int or self.shortfall < 0:
            raise RunContractError("shortfall must be non-negative exact int")
        expected_shortfall = self.request.target_legs - len(frozen_legs)
        if self.shortfall != expected_shortfall:
            raise RunContractError("shortfall must equal target_legs minus selected_leg_count")
        if self.share_code_result is not None:
            if self.request.create_share_code is not True:
                raise RunContractError("share_code_result contradicts disabled request delivery flag")
            object.__setattr__(
                self,
                "share_code_result",
                _freeze_mapping(self.share_code_result, "share_code_result"),
            )
        if type(self.authority_manifest) is not AuthorityManifest:
            raise RunContractError("authority_manifest must be exact AuthorityManifest")
        if (
            self.authority_manifest.authority_profile != self.request.authority_profile
            or self.authority_manifest.mode != self.request.mode
        ):
            raise RunContractError("authority manifest does not match RunRequest profile/mode")
        if self.share_code_result is not None and self.authority_manifest.share_code_generation is not True:
            raise RunContractError("share_code_result lacks share-code generation authority")
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence, "receipt evidence"))
        _exact_bool(self.wager_placed, "wager_placed")
        if self.wager_placed is not False or self.authority_manifest.wager is not False:
            raise RunContractError("P1.1 RunReceipt cannot carry wager authority or wager result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "contract": RECEIPT_CONTRACT,
            "status": self.status,
            "observed_at": _iso(self.observed_at),
            "exact_commit_sha": self.exact_commit_sha,
            "request": self.request.to_dict(),
            "stages": [stage.to_dict() for stage in self.stages],
            "stage_digests": [stage.canonical_sha256 for stage in self.stages],
            "counts": dict(self.counts),
            "selected_legs": [_thaw_json(leg) for leg in self.selected_legs],
            "shortfall": self.shortfall,
            "share_code_result": None if self.share_code_result is None else _thaw_json(self.share_code_result),
            "authority_manifest": self.authority_manifest.to_dict(),
            "evidence": _thaw_json(self.evidence),
            "wager_placed": self.wager_placed,
        }

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    @classmethod
    def from_dict(cls, value: Any) -> "RunReceipt":
        required = {
            "schema_version", "policy_id", "contract", "status", "observed_at",
            "exact_commit_sha", "request", "stages", "stage_digests", "counts", "selected_legs",
            "shortfall", "share_code_result", "authority_manifest", "evidence",
            "wager_placed",
        }
        if type(value) is not dict or set(value) != required:
            raise RunContractError("RunReceipt fields drifted")
        _exact_schema(value["schema_version"], "RunReceipt")
        if value["policy_id"] != POLICY_ID or value["contract"] != RECEIPT_CONTRACT:
            raise RunContractError("RunReceipt contract identity drifted")
        if (
            type(value["stages"]) is not list
            or type(value["stage_digests"]) is not list
            or type(value["selected_legs"]) is not list
        ):
            raise RunContractError("RunReceipt stages/stage_digests/selected_legs must serialize as lists")
        stages = tuple(RunStage.from_dict(item) for item in value["stages"])
        expected_stage_digests = [stage.canonical_sha256 for stage in stages]
        if value["stage_digests"] != expected_stage_digests:
            raise RunContractError("RunReceipt stage digests do not match canonical stages")
        receipt = cls(
            status=value["status"],
            observed_at=_parse_iso(value["observed_at"], "receipt observed_at"),
            exact_commit_sha=value["exact_commit_sha"],
            request=RunRequest.from_dict(value["request"]),
            stages=stages,
            counts=value["counts"],
            selected_legs=tuple(value["selected_legs"]),
            shortfall=value["shortfall"],
            share_code_result=value["share_code_result"],
            authority_manifest=AuthorityManifest.from_dict(value["authority_manifest"]),
            evidence=value["evidence"],
            wager_placed=value["wager_placed"],
        )
        if receipt.to_dict() != value:
            raise RunContractError("RunReceipt is not in canonical normalized form")
        return receipt

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "RunReceipt":
        value = _load_canonical_json(raw)
        receipt = cls.from_dict(value)
        if canonical_json_bytes(receipt) != raw:
            raise RunContractError("RunReceipt JSON bytes are not canonical")
        return receipt


__all__ = [
    "AUTHORITY_PROFILE_IDS",
    "AuthorityManifest",
    "MAX_SELECTED_DATES",
    "MAX_TARGET_LEGS",
    "MIN_SELECTED_DATES",
    "MIN_TARGET_LEGS",
    "POLICY_ID",
    "RECEIPT_CONTRACT",
    "REQUEST_CONTRACT",
    "RunContractError",
    "RunReceipt",
    "RunRequest",
    "RunStage",
    "SCHEMA_VERSION",
    "canonical_json_bytes",
    "canonical_sha256",
]
