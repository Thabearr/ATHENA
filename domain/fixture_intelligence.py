import dataclasses
import enum
import datetime
import json
import hashlib
import re
import types
import pathlib
from typing import Any, Tuple, Dict, Optional, List

DATASET_NAME = 'athena-fixture-intelligence-snapshot-v1'
SCHEMA_VERSION = 1


class FixtureIntelligenceError(ValueError):
    pass


class IntelligenceCategory(enum.Enum):
    FIXTURE_CONTEXT = "FIXTURE_CONTEXT"
    FORM = "FORM"
    AVAILABILITY = "AVAILABILITY"
    LINEUP = "LINEUP"
    SCHEDULE_LOAD = "SCHEDULE_LOAD"
    PERFORMANCE = "PERFORMANCE"
    WEATHER = "WEATHER"
    VENUE = "VENUE"
    MATCH_CONTEXT = "MATCH_CONTEXT"
    OFFICIAL_NEWS = "OFFICIAL_NEWS"


class SourceRole(enum.Enum):
    PRIMARY_FOOTBALL_CONTEXT = "PRIMARY_FOOTBALL_CONTEXT"
    OFFICIAL_CORROBORATION = "OFFICIAL_CORROBORATION"
    WEATHER_CONTEXT = "WEATHER_CONTEXT"
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


class IntelligenceFactStatus(enum.Enum):
    SUPPORTED = "SUPPORTED"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNVERIFIED = "UNVERIFIED"

_REQUIRED_SAFETY_KEYS = frozenset({
    "network_acquisition_authorized",
    "scraping_authorized",
    "browser_automation_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "prospective_claim_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "bet_authorized"
})


def _check_json_value(val: Any) -> None:
    try:
        json.dumps(val, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as e:
        raise FixtureIntelligenceError(f"Invalid value for JSON serialization: {e}")

    def _check_keys(v: Any) -> None:
        if isinstance(v, dict):
            for k, child in v.items():
                if not isinstance(k, str):
                    raise FixtureIntelligenceError(f"Non-string dictionary key found: {k}")
                _check_keys(child)
        elif isinstance(v, (list, tuple)):
            for item in v:
                _check_keys(item)

    _check_keys(val)


def _freeze_value(val: Any) -> Any:
    if isinstance(val, dict):
        return types.MappingProxyType({k: _freeze_value(v) for k, v in val.items()})
    elif isinstance(val, (list, tuple)):
        return tuple(_freeze_value(v) for v in val)
    return val

def _thaw_value(val: Any) -> Any:
    if isinstance(val, types.MappingProxyType) or isinstance(val, dict):
        return {k: _thaw_value(v) for k, v in val.items()}
    elif isinstance(val, tuple) or isinstance(val, list):
        return [_thaw_value(v) for v in val]
    return val

def _require_utc(dt: Any, name: str) -> datetime.datetime:
    if not isinstance(dt, datetime.datetime):
        raise FixtureIntelligenceError(f"{name} must be a datetime")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise FixtureIntelligenceError(f"{name} must be timezone-aware")
    return dt.astimezone(datetime.timezone.utc)

def _validate_evidence_path(path: str) -> None:
    if not path or not isinstance(path, str):
        raise FixtureIntelligenceError("evidence_file_path must be a non-empty string")
    posix = pathlib.PurePosixPath(path)
    win = pathlib.PureWindowsPath(path)
    if posix.is_absolute() or win.is_absolute():
        raise FixtureIntelligenceError("evidence_file_path must be relative")
    if path.startswith('\\\\') or path.startswith('//'):
        raise FixtureIntelligenceError("UNC paths are not allowed")
    for part in posix.parts:
        if part == '..':
            raise FixtureIntelligenceError("evidence_file_path must not contain '..' components")
    for part in win.parts:
        if part == '..':
            raise FixtureIntelligenceError("evidence_file_path must not contain '..' components")

def _dt_to_iso(dt: datetime.datetime) -> str:
    iso = dt.isoformat()
    if dt.tzinfo == datetime.timezone.utc and not iso.endswith(('Z', '+00:00')):
        iso = iso.replace('+00:00', 'Z') if '+00:00' in iso else iso + 'Z'
    elif dt.tzinfo == datetime.timezone.utc and iso.endswith('+00:00'):
        iso = iso[:-6] + 'Z'
    return iso

def _fact_to_dict(fact) -> dict:
    return {
        "category": fact.category.value if isinstance(fact.category, IntelligenceCategory) else str(fact.category),
        "field": fact.field,
        "status": fact.status.value if isinstance(fact.status, IntelligenceFactStatus) else str(fact.status),
        "value": _thaw_value(fact.value),
        "source_provider": fact.source_provider,
        "source_role": fact.source_role.value if isinstance(fact.source_role, SourceRole) else str(fact.source_role),
        "source_reference": fact.source_reference,
        "observed_at": _dt_to_iso(fact.observed_at) if isinstance(fact.observed_at, datetime.datetime) else str(fact.observed_at),
        "evidence_file_path": fact.evidence_file_path,
        "evidence_sha256": fact.evidence_sha256,
        "notes": fact.notes
    }

def _fact_canonical_json_str(fact) -> str:
    d = _fact_to_dict(fact)
    return json.dumps(d, sort_keys=True, allow_nan=False, separators=(',', ':'))

def _derive_snapshot_summaries(facts: Tuple['FixtureIntelligenceFact', ...]) -> Tuple[Tuple['CategoryCoverage', ...], Tuple[Tuple[str, str], ...], Tuple[Tuple[str, str], ...]]:
    cov_dict = {cat: {"supported": 0, "stale": 0, "conflicted": 0, "unverified": 0, "has_any": False} for cat in IntelligenceCategory}

    unverified_set = set()
    supported_values_by_field = {}

    for f in facts:
        cat_v = f.category.value
        field_v = f.field

        cov_dict[f.category][f.status.value.lower()] += 1
        cov_dict[f.category]["has_any"] = True

        key = (cat_v, field_v)

        if f.status == IntelligenceFactStatus.UNVERIFIED:
            unverified_set.add(key)

        if f.status == IntelligenceFactStatus.SUPPORTED:
            val_str = json.dumps(_thaw_value(f.value), sort_keys=True, allow_nan=False, separators=(',', ':'))
            if key not in supported_values_by_field:
                supported_values_by_field[key] = set()
            supported_values_by_field[key].add(val_str)

    conflicted_set = set()
    for key, val_strs in supported_values_by_field.items():
        if len(val_strs) >= 2:
            conflicted_set.add(key)

    coverage_tuples = []
    for cat in IntelligenceCategory:
        d = cov_dict[cat]
        c_sum = d["supported"] + d["stale"] + d["conflicted"] + d["unverified"]
        has_any_evidence = (c_sum > 0)
        coverage_tuples.append(CategoryCoverage(
            category=cat,
            supported=d["supported"],
            stale=d["stale"],
            conflicted=d["conflicted"],
            unverified=d["unverified"],
            has_any_evidence=has_any_evidence
        ))

    sorted_coverage = tuple(sorted(coverage_tuples, key=lambda c: c.category.value))
    sorted_conflicted = tuple(sorted(conflicted_set))
    sorted_unverified = tuple(sorted(unverified_set))

    return sorted_coverage, sorted_conflicted, sorted_unverified


@dataclasses.dataclass(frozen=True)
class FixtureIntelligenceFact:
    category: IntelligenceCategory
    field: str
    status: IntelligenceFactStatus
    value: Any
    source_provider: str
    source_role: SourceRole
    source_reference: str
    observed_at: datetime.datetime
    evidence_file_path: str
    evidence_sha256: str
    notes: Optional[str] = None

    def __post_init__(self):
        try:
            if not isinstance(self.category, IntelligenceCategory):
                raise FixtureIntelligenceError('category must be IntelligenceCategory')
            if not isinstance(self.status, IntelligenceFactStatus):
                raise FixtureIntelligenceError('status must be IntelligenceFactStatus')
            if not isinstance(self.source_role, SourceRole):
                raise FixtureIntelligenceError('source_role must be SourceRole')

            if not self.field or not isinstance(self.field, str):
                raise FixtureIntelligenceError("field must be a non-empty string")
            if self.field != self.field.strip() or len(self.field) > 128:
                raise FixtureIntelligenceError("field must not have leading/trailing whitespace and max 128 chars")
            if not re.match(r'^[-a-zA-Z0-9_]+$', self.field):
                raise FixtureIntelligenceError("field must only contain alphanumeric, underscore, and hyphen characters")

            if not self.source_provider or not isinstance(self.source_provider, str):
                raise FixtureIntelligenceError("source_provider must be a non-empty string")
            if self.source_provider != self.source_provider.strip() or len(self.source_provider) > 128:
                raise FixtureIntelligenceError("source_provider must not have leading/trailing whitespace and max 128 chars")

            if not isinstance(self.source_reference, str):
                raise FixtureIntelligenceError("source_reference must be a string")
            if not self.source_reference or self.source_reference != self.source_reference.strip() or len(self.source_reference) > 512:
                raise FixtureIntelligenceError("source_reference must be a non-empty string without leading/trailing whitespace, max 512 chars")

            object.__setattr__(self, 'observed_at', _require_utc(self.observed_at, "observed_at"))

            _validate_evidence_path(self.evidence_file_path)

            if not self.evidence_sha256 or not isinstance(self.evidence_sha256, str) or not re.match(r'^[a-f0-9]{64}$', self.evidence_sha256):
                raise FixtureIntelligenceError("evidence_sha256 must be exactly 64 lowercase hex characters")

            if self.notes is not None:
                if not isinstance(self.notes, str) or len(self.notes) > 1024:
                    raise FixtureIntelligenceError("notes must be a string up to 1024 chars")

            _check_json_value(self.value)
            object.__setattr__(self, 'value', _freeze_value(self.value))

            if self.source_role == SourceRole.DISCOVERY_ONLY and self.status != IntelligenceFactStatus.UNVERIFIED:
                raise FixtureIntelligenceError(f'DISCOVERY_ONLY facts must have UNVERIFIED status, got {self.status!r}')

        except (TypeError, AttributeError) as e:
            raise FixtureIntelligenceError(f"Validation error: {e}")


@dataclasses.dataclass(frozen=True)
class CategoryCoverage:
    category: IntelligenceCategory
    supported: int
    stale: int
    conflicted: int
    unverified: int
    has_any_evidence: bool

    def __post_init__(self):
        try:
            if not isinstance(self.category, IntelligenceCategory):
                raise FixtureIntelligenceError("category must be IntelligenceCategory")
            if type(self.supported) is not int or self.supported < 0:
                raise FixtureIntelligenceError("supported must be non-negative int")
            if type(self.stale) is not int or self.stale < 0:
                raise FixtureIntelligenceError("stale must be non-negative int")
            if type(self.conflicted) is not int or self.conflicted < 0:
                raise FixtureIntelligenceError("conflicted must be non-negative int")
            if type(self.unverified) is not int or self.unverified < 0:
                raise FixtureIntelligenceError("unverified must be non-negative int")
            if type(self.has_any_evidence) is not bool:
                raise FixtureIntelligenceError("has_any_evidence must be bool")
            c_sum = self.supported + self.stale + self.conflicted + self.unverified
            expected_has_any = (c_sum > 0)
            if self.has_any_evidence != expected_has_any:
                raise FixtureIntelligenceError("has_any_evidence must agree with sum of counts > 0")
        except (TypeError, AttributeError) as e:
            raise FixtureIntelligenceError(f"Validation error: {e}")


@dataclasses.dataclass(frozen=True)
class FixtureIntelligenceSnapshot:
    schema_version: int
    dataset_name: str
    fixture_identifier: str
    kickoff: datetime.datetime
    as_of: datetime.datetime
    facts: Tuple[FixtureIntelligenceFact, ...]
    category_coverage: Tuple[CategoryCoverage, ...]
    conflicted_fields: Tuple[Tuple[str, str], ...]
    unverified_fields: Tuple[Tuple[str, str], ...]
    safety: Dict[str, bool]

    def __post_init__(self):
        try:
            if self.schema_version != SCHEMA_VERSION:
                raise FixtureIntelligenceError(f"schema_version must be {SCHEMA_VERSION}")
            if self.dataset_name != DATASET_NAME:
                raise FixtureIntelligenceError(f"dataset_name must be {DATASET_NAME}")

            if not self.fixture_identifier or not isinstance(self.fixture_identifier, str) or self.fixture_identifier != self.fixture_identifier.strip():
                raise FixtureIntelligenceError("fixture_identifier must be non-empty without leading/trailing whitespace")

            object.__setattr__(self, 'kickoff', _require_utc(self.kickoff, "kickoff"))
            object.__setattr__(self, 'as_of', _require_utc(self.as_of, "as_of"))

            if self.as_of >= self.kickoff:
                raise FixtureIntelligenceError("as_of must be strictly before kickoff")

            if not isinstance(self.facts, tuple):
                raise FixtureIntelligenceError("facts must be a tuple")
            for fact in self.facts:
                if not isinstance(fact, FixtureIntelligenceFact):
                    raise FixtureIntelligenceError("all facts must be FixtureIntelligenceFact")
                if fact.observed_at > self.as_of:
                    raise FixtureIntelligenceError("No fact may have observed_at strictly after as_of")

            if not isinstance(self.category_coverage, tuple):
                raise FixtureIntelligenceError("category_coverage must be a tuple")
            for cov in self.category_coverage:
                if not isinstance(cov, CategoryCoverage):
                    raise FixtureIntelligenceError("all category_coverage must be CategoryCoverage")

            sorted_facts = tuple(sorted(self.facts, key=lambda f: (f.category.value, f.field, f.source_provider, f.observed_at.isoformat(), f.evidence_sha256, _fact_canonical_json_str(f))))
            if self.facts != sorted_facts:
                raise FixtureIntelligenceError("facts must be sorted")

            derived_cov, derived_conf, derived_unv = _derive_snapshot_summaries(self.facts)

            if set(c.category for c in self.category_coverage) != set(IntelligenceCategory):
                raise FixtureIntelligenceError("category_coverage must have exactly one entry per category")

            if self.category_coverage != derived_cov:
                raise FixtureIntelligenceError("category_coverage does not match derived summaries")
            if self.conflicted_fields != derived_conf:
                raise FixtureIntelligenceError("conflicted_fields does not match derived summaries")
            if self.unverified_fields != derived_unv:
                raise FixtureIntelligenceError("unverified_fields does not match derived summaries")

            if set(self.safety.keys()) != _REQUIRED_SAFETY_KEYS:
                raise FixtureIntelligenceError("safety keys mismatch")
            for k, v in self.safety.items():
                if type(v) is not bool or v is not False:
                    raise FixtureIntelligenceError(f"safety[{k!r}] must be exactly bool False")

            object.__setattr__(self, 'safety', types.MappingProxyType(self.safety))

        except (TypeError, AttributeError) as e:
            raise FixtureIntelligenceError(f"Validation error: {e}")

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "fixture_identifier": self.fixture_identifier,
            "kickoff": _dt_to_iso(self.kickoff),
            "as_of": _dt_to_iso(self.as_of),
            "facts": [_fact_to_dict(f) for f in self.facts],
            "category_coverage": [
                {
                    "category": c.category.value,
                    "supported": c.supported,
                    "stale": c.stale,
                    "conflicted": c.conflicted,
                    "unverified": c.unverified,
                    "has_any_evidence": c.has_any_evidence
                } for c in self.category_coverage
            ],
            "conflicted_fields": [[c[0], c[1]] for c in self.conflicted_fields],
            "unverified_fields": [[u[0], u[1]] for u in self.unverified_fields],
            "safety": _thaw_value(self.safety)
        }


def build_snapshot(fixture_identifier: str, kickoff: datetime.datetime, as_of: datetime.datetime, raw_facts: List[FixtureIntelligenceFact]) -> FixtureIntelligenceSnapshot:
    as_of_utc = _require_utc(as_of, "as_of")
    kickoff_utc = _require_utc(kickoff, "kickoff")

    if as_of_utc >= kickoff_utc:
        raise FixtureIntelligenceError("as_of must be strictly before kickoff")

    valid_facts = []
    for f in raw_facts:
        if not isinstance(f, FixtureIntelligenceFact):
            raise FixtureIntelligenceError("all facts must be FixtureIntelligenceFact")
        if f.observed_at > as_of_utc:
            raise FixtureIntelligenceError("Fact observed_at cannot be after as_of")
        valid_facts.append(f)

    sorted_facts = tuple(sorted(valid_facts, key=lambda f: (f.category.value, f.field, f.source_provider, f.observed_at.isoformat(), f.evidence_sha256, _fact_canonical_json_str(f))))

    derived_cov, derived_conf, derived_unv = _derive_snapshot_summaries(sorted_facts)

    safety = {
        "network_acquisition_authorized": False,
        "scraping_authorized": False,
        "browser_automation_authorized": False,
        "pricing_authorized": False,
        "market_activation_authorized": False,
        "prospective_claim_authorized": False,
        "selection_authorized": False,
        "production_approval_authorized": False,
        "bet_authorized": False
    }

    return FixtureIntelligenceSnapshot(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        fixture_identifier=fixture_identifier,
        kickoff=kickoff_utc,
        as_of=as_of_utc,
        facts=sorted_facts,
        category_coverage=derived_cov,
        conflicted_fields=derived_conf,
        unverified_fields=derived_unv,
        safety=safety
    )


def snapshot_to_dict(snapshot: FixtureIntelligenceSnapshot) -> dict:
    return snapshot.to_dict()


def canonical_snapshot_bytes(snapshot: FixtureIntelligenceSnapshot) -> bytes:
    d = snapshot.to_dict()
    json_str = json.dumps(d, sort_keys=True, allow_nan=False, separators=(',', ':'))
    return (json_str + '\n').encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
