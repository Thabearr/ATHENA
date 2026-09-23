"""Strict, immutable contracts for the bounded FotMob source ingest lane."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping


class AthenaIngestContractError(ValueError):
    """The supplied ingest evidence does not match the reviewed contract."""


REQUEST_POLICY = "ATHENA_INGEST_REQUEST_V1"
UPDATE_POLICY = "ATHENA_CANONICAL_SOURCE_UPDATE_V1"
RECEIPT_POLICY = "ATHENA_INGEST_RECEIPT_V1"
REPLAY_POLICY = "ATHENA_INGEST_REPLAY_MANIFEST_V1"
REPLAY_RECEIPT_POLICY = "ATHENA_INGEST_OFFLINE_REPLAY_RECEIPT_V1"
READY = "CANONICAL_SOURCE_UPDATE_READY"
NOT_COMMITTED = "CANONICAL_SOURCE_UPDATE_NOT_COMMITTED"
FORBIDDEN_AUTHORITIES = (
    "fixture_selection_authority", "fixture_intelligence_authority",
    "model_feature_authority", "probability_authority", "pricing_authority",
    "market_routing_authority", "portfolio_authority", "share_code_authority",
    "login", "cookies", "wallet", "staking", "wager",
)


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                           sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise AthenaIngestContractError("canonical JSON serialization failed") from exc


def sha256_bytes(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise AthenaIngestContractError("hash input must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _fields(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise AthenaIngestContractError(f"{label} fields differ from the reviewed schema")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AthenaIngestContractError(f"{label} must be a lowercase SHA-256")
    return value


def validate_dates(dates: Any) -> tuple[str, ...]:
    if type(dates) not in (list, tuple) or not 1 <= len(dates) <= 7:
        raise AthenaIngestContractError("dates must contain 1 through 7 entries")
    result: list[str] = []
    for token in dates:
        if type(token) is not str or re.fullmatch(r"[0-9]{8}", token, re.ASCII) is None:
            raise AthenaIngestContractError("each date must be exact YYYYMMDD ASCII")
        try:
            datetime.strptime(token, "%Y%m%d")
        except ValueError as exc:
            raise AthenaIngestContractError(f"invalid Gregorian date: {token}") from exc
        if result and token <= result[-1]:
            raise AthenaIngestContractError("dates must be unique and strictly increasing")
        result.append(token)
    return tuple(result)


def parse_dates_input(value: Any) -> tuple[str, ...]:
    if type(value) is not str:
        raise AthenaIngestContractError("dates input must be text")
    return validate_dates(value.split(","))


@dataclass(frozen=True)
class AthenaIngestRequest:
    schema_version: int
    policy_id: str
    provider: str
    dates: tuple[str, ...]
    timezone: str
    ccode3: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1 or self.policy_id != REQUEST_POLICY:
            raise AthenaIngestContractError("ingest request schema/policy mismatch")
        if self.provider != "fotmob":
            raise AthenaIngestContractError("unsupported provider")
        if self.timezone != "UTC" or self.ccode3 != "NGA":
            raise AthenaIngestContractError("ingest timezone/country must be UTC/NGA")
        object.__setattr__(self, "dates", validate_dates(self.dates))

    @classmethod
    def from_mapping(cls, value: Any) -> "AthenaIngestRequest":
        data = _fields(value, set(cls.__dataclass_fields__), "ingest request")
        return cls(**data)

    @classmethod
    def for_dates(cls, dates: tuple[str, ...]) -> "AthenaIngestRequest":
        return cls(1, REQUEST_POLICY, "fotmob", dates, "UTC", "NGA")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"dates": list(self.dates)}

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes)


@dataclass(frozen=True)
class AthenaIngestSourceRecord:
    provider: str
    request_date: str
    timezone: str
    ccode3: str
    observed_at: str
    capture_relative_path: str
    manifest_sha256: str
    raw_sha256: str
    raw_size: int
    network_acquisition_performed: bool

    def __post_init__(self) -> None:
        if self.provider != "fotmob" or self.timezone != "UTC" or self.ccode3 != "NGA":
            raise AthenaIngestContractError("source record provider identity mismatch")
        validate_dates((self.request_date,))
        if type(self.observed_at) is not str or not self.observed_at.endswith("Z"):
            raise AthenaIngestContractError("source record observed_at must be UTC")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AthenaIngestContractError("source record observed_at is invalid") from exc
        path = self.capture_relative_path
        if (type(path) is not str or "\\" in path or ".." in path.split("/")
                or not path.startswith(f"sources/fotmob/{self.request_date}/")
                or len(path.split("/")) != 4 or not path.split("/")[-1]):
            raise AthenaIngestContractError("source record capture path is invalid")
        _sha(self.manifest_sha256, "manifest_sha256")
        _sha(self.raw_sha256, "raw_sha256")
        if type(self.raw_size) is not int or self.raw_size < 1:
            raise AthenaIngestContractError("source record raw_size is invalid")
        if self.network_acquisition_performed is not True:
            raise AthenaIngestContractError("source record requires acquired provenance")

    @classmethod
    def from_mapping(cls, value: Any) -> "AthenaIngestSourceRecord":
        return cls(**_fields(value, set(cls.__dataclass_fields__), "source record"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AthenaCanonicalStoreUpdate:
    schema_version: int
    policy_id: str
    request_sha256: str
    provider: str
    source_records: tuple[AthenaIngestSourceRecord, ...]
    source_record_count: int
    all_requested_dates_captured: bool
    commit_status: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1 or self.policy_id != UPDATE_POLICY:
            raise AthenaIngestContractError("canonical update schema/policy mismatch")
        _sha(self.request_sha256, "request_sha256")
        if self.provider != "fotmob" or type(self.source_records) is not tuple or any(
            not isinstance(item, AthenaIngestSourceRecord) for item in self.source_records
        ):
            raise AthenaIngestContractError("canonical update sources are invalid")
        if type(self.source_record_count) is not int or self.source_record_count != len(self.source_records):
            raise AthenaIngestContractError("canonical update source count mismatch")
        if type(self.all_requested_dates_captured) is not bool or self.commit_status not in (READY, NOT_COMMITTED):
            raise AthenaIngestContractError("canonical update commit state invalid")
        if (self.commit_status == READY) is not self.all_requested_dates_captured:
            raise AthenaIngestContractError("canonical update cannot claim partial commit")
        dates = [item.request_date for item in self.source_records]
        if dates != sorted(set(dates)):
            raise AthenaIngestContractError("canonical update source order invalid")

    @classmethod
    def from_mapping(cls, value: Any) -> "AthenaCanonicalStoreUpdate":
        data = dict(_fields(value, set(cls.__dataclass_fields__), "canonical update"))
        if type(data["source_records"]) is not list:
            raise AthenaIngestContractError("canonical update source_records must be a list")
        data["source_records"] = tuple(AthenaIngestSourceRecord.from_mapping(item) for item in data["source_records"])
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"source_records": [item.to_dict() for item in self.source_records]}

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes)


@dataclass(frozen=True)
class AthenaIngestReceipt:
    schema_version: int
    policy_id: str
    status: str
    failure_code: str | None
    request_sha256: str
    canonical_store_update_sha256: str
    canonical_store_update_committed: bool
    provider_request_count: int
    source_count: int
    authorities: dict[str, bool]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1 or self.policy_id != RECEIPT_POLICY:
            raise AthenaIngestContractError("ingest receipt schema/policy mismatch")
        if self.status not in ("SUCCESS", "FAILED") or (self.status == "SUCCESS") != (self.failure_code is None):
            raise AthenaIngestContractError("ingest receipt status/failure mismatch")
        if self.failure_code is not None and self.failure_code not in {
            "INVALID_REQUEST", "UNSUPPORTED_PROVIDER", "PROVIDER_ACQUISITION_FAILED",
            "SOURCE_CAPTURE_VALIDATION_FAILED", "ARTIFACT_PERSISTENCE_FAILED", "REPLAY_VALIDATION_FAILED",
        }:
            raise AthenaIngestContractError("ingest receipt failure code invalid")
        _sha(self.request_sha256, "request_sha256")
        _sha(self.canonical_store_update_sha256, "canonical_store_update_sha256")
        if type(self.canonical_store_update_committed) is not bool or self.canonical_store_update_committed != (self.status == "SUCCESS"):
            raise AthenaIngestContractError("ingest receipt commit status mismatch")
        if type(self.provider_request_count) is not int or not 0 <= self.provider_request_count <= 7:
            raise AthenaIngestContractError("ingest receipt provider count invalid")
        if type(self.source_count) is not int or not 0 <= self.source_count <= self.provider_request_count:
            raise AthenaIngestContractError("ingest receipt source count invalid")
        expected = {"provider_acquisition": self.provider_request_count > 0,
                    "raw_source_capture": self.source_count > 0,
                    "canonical_source_update": self.canonical_store_update_committed}
        expected.update({key: False for key in FORBIDDEN_AUTHORITIES})
        if type(self.authorities) is not dict or self.authorities != expected or any(type(v) is not bool for v in self.authorities.values()):
            raise AthenaIngestContractError("ingest receipt authority mismatch")

    @classmethod
    def from_mapping(cls, value: Any) -> "AthenaIngestReceipt":
        return cls(**_fields(value, set(cls.__dataclass_fields__), "ingest receipt"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @property
    def canonical_sha256(self) -> str:
        return sha256_bytes(self.canonical_bytes)


def receipt_authorities(*, provider_requests: int, source_count: int, committed: bool) -> dict[str, bool]:
    result = {"provider_acquisition": provider_requests > 0,
              "raw_source_capture": source_count > 0,
              "canonical_source_update": committed}
    result.update({key: False for key in FORBIDDEN_AUTHORITIES})
    return result


def strict_json_loads(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise AthenaIngestContractError("JSON source must be exact bytes")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise AthenaIngestContractError(f"duplicate JSON key: {key}")
            output[key] = value
        return output
    def reject_constant(value: str) -> None:
        raise AthenaIngestContractError(f"invalid JSON constant: {value}")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise AthenaIngestContractError("invalid canonical JSON") from exc
