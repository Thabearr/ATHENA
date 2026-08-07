import dataclasses
import enum
import datetime
import json
import hashlib
import re
import math
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


def _check_json_value(val: Any) -> None:
    # Attempt strict JSON serialization to ensure no NaN/Inf, non-string keys, unsupported objects
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
        # field validation
        if not self.field or not isinstance(self.field, str):
            raise FixtureIntelligenceError("field must be a non-empty string")
        if self.field != self.field.strip() or len(self.field) > 128:
            raise FixtureIntelligenceError("field must not have leading/trailing whitespace and max 128 chars")
        if not re.match(r'^[-a-zA-Z0-9_]+$', self.field):
            raise FixtureIntelligenceError("field must only contain alphanumeric, underscore, and hyphen characters")
        
        # source_provider validation
        if not self.source_provider or not isinstance(self.source_provider, str):
            raise FixtureIntelligenceError("source_provider must be a non-empty string")
        if self.source_provider != self.source_provider.strip() or len(self.source_provider) > 128:
            raise FixtureIntelligenceError("source_provider must not have leading/trailing whitespace and max 128 chars")
            
        # source_reference validation
        if not self.source_reference or not isinstance(self.source_reference, str) or len(self.source_reference) > 512:
            raise FixtureIntelligenceError("source_reference must be a non-empty string, max 512 chars")
            
        # observed_at validation
        if not isinstance(self.observed_at, datetime.datetime):
            raise FixtureIntelligenceError("observed_at must be a datetime")
        if self.observed_at.tzinfo is None or self.observed_at.tzinfo.utcoffset(self.observed_at) is None:
            raise FixtureIntelligenceError("observed_at must be timezone-aware")
            
        # normalize to UTC (by replacing tzinfo if offset is 0, or converting)
        object.__setattr__(self, 'observed_at', self.observed_at.astimezone(datetime.timezone.utc))

        # evidence_file_path validation
        if not self.evidence_file_path or not isinstance(self.evidence_file_path, str):
            raise FixtureIntelligenceError("evidence_file_path must be a non-empty string")
        if self.evidence_file_path.startswith('/') or self.evidence_file_path.startswith('\\'):
            raise FixtureIntelligenceError("evidence_file_path must be relative")
        if '..' in self.evidence_file_path.split('/') or '..' in self.evidence_file_path.split('\\'):
            raise FixtureIntelligenceError("evidence_file_path must not contain '..' components")
            
        # evidence_sha256 validation
        if not self.evidence_sha256 or not isinstance(self.evidence_sha256, str) or not re.match(r'^[a-f0-9]{64}$', self.evidence_sha256):
            raise FixtureIntelligenceError("evidence_sha256 must be exactly 64 lowercase hex characters")
            
        # notes validation
        if self.notes is not None:
            if not isinstance(self.notes, str) or len(self.notes) > 1024:
                raise FixtureIntelligenceError("notes must be a string up to 1024 chars")
                
        # value validation
        _check_json_value(self.value)
        
        # logical validation
        if self.source_role == SourceRole.DISCOVERY_ONLY and self.status == IntelligenceFactStatus.SUPPORTED:
            raise FixtureIntelligenceError("DISCOVERY_ONLY source role cannot have SUPPORTED status")


@dataclasses.dataclass(frozen=True)
class CategoryCoverage:
    category: IntelligenceCategory
    supported: int
    stale: int
    conflicted: int
    unverified: int
    has_any_evidence: bool


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
        if self.schema_version != SCHEMA_VERSION:
            raise FixtureIntelligenceError(f"schema_version must be {SCHEMA_VERSION}")
        if self.dataset_name != DATASET_NAME:
            raise FixtureIntelligenceError(f"dataset_name must be {DATASET_NAME}")
            
        if not self.fixture_identifier or not isinstance(self.fixture_identifier, str) or self.fixture_identifier != self.fixture_identifier.strip():
            raise FixtureIntelligenceError("fixture_identifier must be non-empty without leading/trailing whitespace")
            
        if not isinstance(self.kickoff, datetime.datetime) or self.kickoff.tzinfo is None or self.kickoff.tzinfo.utcoffset(self.kickoff) is None:
            raise FixtureIntelligenceError("kickoff must be timezone-aware")
        object.__setattr__(self, 'kickoff', self.kickoff.astimezone(datetime.timezone.utc))
        
        if not isinstance(self.as_of, datetime.datetime) or self.as_of.tzinfo is None or self.as_of.tzinfo.utcoffset(self.as_of) is None:
            raise FixtureIntelligenceError("as_of must be timezone-aware")
        object.__setattr__(self, 'as_of', self.as_of.astimezone(datetime.timezone.utc))
        
        if self.as_of >= self.kickoff:
            raise FixtureIntelligenceError("as_of must be strictly before kickoff")
            
        for fact in self.facts:
            if fact.observed_at > self.as_of:
                raise FixtureIntelligenceError("No fact may have observed_at strictly after as_of")
                
        # Assert facts are sorted
        sorted_facts = tuple(sorted(self.facts, key=lambda f: (f.category.value, f.field, f.source_provider, f.observed_at.isoformat(), f.evidence_sha256)))
        if self.facts != sorted_facts:
            raise FixtureIntelligenceError("facts must be sorted")
            
        # Assert category_coverage is sorted by category.value
        sorted_cov = tuple(sorted(self.category_coverage, key=lambda c: c.category.value))
        if self.category_coverage != sorted_cov:
            raise FixtureIntelligenceError("category_coverage must be sorted by category.value")
            
        # Assert conflicted_fields and unverified_fields are sorted
        if self.conflicted_fields != tuple(sorted(self.conflicted_fields)):
            raise FixtureIntelligenceError("conflicted_fields must be sorted")
        if self.unverified_fields != tuple(sorted(self.unverified_fields)):
            raise FixtureIntelligenceError("unverified_fields must be sorted")
            
        # Validate safety dict
        expected_safety_keys = {
            "network_acquisition_authorized",
            "scraping_authorized",
            "browser_automation_authorized",
            "pricing_authorized",
            "market_activation_authorized",
            "prospective_claim_authorized",
            "selection_authorized",
            "production_approval_authorized",
            "bet_authorized"
        }
        if set(self.safety.keys()) != expected_safety_keys:
            raise FixtureIntelligenceError("safety must contain exactly the required keys")
        if any(val is True for val in self.safety.values()):
            raise FixtureIntelligenceError("safety values must all be False")


def build_snapshot(fixture_identifier: str, kickoff: datetime.datetime, as_of: datetime.datetime, raw_facts: List[FixtureIntelligenceFact]) -> FixtureIntelligenceSnapshot:
    # 1. Validations on inputs (dates)
    if as_of.tzinfo is None:
        raise FixtureIntelligenceError("as_of must be timezone-aware")
    if kickoff.tzinfo is None:
        raise FixtureIntelligenceError("kickoff must be timezone-aware")
    as_of_utc = as_of.astimezone(datetime.timezone.utc)
    kickoff_utc = kickoff.astimezone(datetime.timezone.utc)
    
    if as_of_utc >= kickoff_utc:
        raise FixtureIntelligenceError("as_of must be strictly before kickoff")
        
    valid_facts = []
    for f in raw_facts:
        if f.observed_at > as_of_utc:
            raise FixtureIntelligenceError("Fact observed_at cannot be after as_of")
        valid_facts.append(f)
        
    # Sort facts
    sorted_facts = tuple(sorted(valid_facts, key=lambda f: (f.category.value, f.field, f.source_provider, f.observed_at.isoformat(), f.evidence_sha256)))
    
    # Compute coverage, conflicts, unverified
    cov_dict = {cat: {"supported": 0, "stale": 0, "conflicted": 0, "unverified": 0, "has_any": False} for cat in IntelligenceCategory}
    
    unverified_set = set()
    supported_values_by_field = {} # (category.value, field) -> list of json strings
    
    for f in sorted_facts:
        cat_v = f.category.value
        field_v = f.field
        
        # update coverage
        cov_dict[f.category][f.status.value.lower()] += 1
        cov_dict[f.category]["has_any"] = True
        
        key = (cat_v, field_v)
        
        if f.status == IntelligenceFactStatus.UNVERIFIED:
            unverified_set.add(key)
            
        if f.status == IntelligenceFactStatus.SUPPORTED:
            val_str = json.dumps(f.value, sort_keys=True, allow_nan=False, separators=(',', ':'))
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
        coverage_tuples.append(CategoryCoverage(
            category=cat,
            supported=d["supported"],
            stale=d["stale"],
            conflicted=d["conflicted"],
            unverified=d["unverified"],
            has_any_evidence=d["has_any"]
        ))
    
    sorted_coverage = tuple(sorted(coverage_tuples, key=lambda c: c.category.value))
    sorted_conflicted = tuple(sorted(conflicted_set))
    sorted_unverified = tuple(sorted(unverified_set))
    
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
        category_coverage=sorted_coverage,
        conflicted_fields=sorted_conflicted,
        unverified_fields=sorted_unverified,
        safety=safety
    )


def _dt_to_iso(dt: datetime.datetime) -> str:
    iso = dt.isoformat()
    if dt.tzinfo == datetime.timezone.utc and not iso.endswith(('Z', '+00:00')):
        iso = iso.replace('+00:00', 'Z') if '+00:00' in iso else iso + 'Z'
    elif dt.tzinfo == datetime.timezone.utc and iso.endswith('+00:00'):
        # Normalize +00:00 to Z or keep it as is, both are fine, let's use Z to be safe or +00:00. The test might be flexible, but strict json requires string
        pass
    # We will just rely on isoformat() being valid. 
    # For determinism, let's force +00:00 to Z if we want
    if iso.endswith('+00:00'):
        iso = iso[:-6] + 'Z'
    return iso


def snapshot_to_dict(snapshot: FixtureIntelligenceSnapshot) -> dict:
    return {
        "schema_version": snapshot.schema_version,
        "dataset_name": snapshot.dataset_name,
        "fixture_identifier": snapshot.fixture_identifier,
        "kickoff": _dt_to_iso(snapshot.kickoff),
        "as_of": _dt_to_iso(snapshot.as_of),
        "facts": [
            {
                "category": f.category.value,
                "field": f.field,
                "status": f.status.value,
                "value": f.value,
                "source_provider": f.source_provider,
                "source_role": f.source_role.value,
                "source_reference": f.source_reference,
                "observed_at": _dt_to_iso(f.observed_at),
                "evidence_file_path": f.evidence_file_path,
                "evidence_sha256": f.evidence_sha256,
                "notes": f.notes
            } for f in snapshot.facts
        ],
        "category_coverage": [
            {
                "category": c.category.value,
                "supported": c.supported,
                "stale": c.stale,
                "conflicted": c.conflicted,
                "unverified": c.unverified,
                "has_any_evidence": c.has_any_evidence
            } for c in snapshot.category_coverage
        ],
        "conflicted_fields": [[c[0], c[1]] for c in snapshot.conflicted_fields],
        "unverified_fields": [[u[0], u[1]] for u in snapshot.unverified_fields],
        "safety": dict(snapshot.safety)
    }


def canonical_snapshot_bytes(snapshot: FixtureIntelligenceSnapshot) -> bytes:
    d = snapshot_to_dict(snapshot)
    json_str = json.dumps(d, sort_keys=True, allow_nan=False, separators=(',', ':'))
    return (json_str + '\n').encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
