"""Canonical source-controlled component authority registry (P1.7).

The registry replaces filename/version-number authority with exact typed records.
A record binds one semantic responsibility/regime to a component identity,
contract hash, source artifact identity, profile eligibility and promotion state.

Registration is not production promotion.  MAIN resolution is fail-closed unless
an exact champion record is explicitly APPROVED_FOR_MAIN with main_authority=True.
Research challengers are SHADOW-only.  Registry data is loaded from a reviewed,
source-controlled JSON file; this module exposes no runtime mutation or write
path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_COMPONENT_AUTHORITY_REGISTRY_V1"
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "architecture"
    / "component-authority-registry-v1.json"
)
EXPECTED_REGISTRY_CONTRACT_SHA256 = (
    "c3389e9aca42dccebf965abad06ea44f65c849d8fa3d1b5620d83987fd880e53"
)

MAIN = "MAIN"
SHADOW = "SHADOW"
AUTHORITY_PROFILES = (MAIN, SHADOW)

CHAMPION = "CHAMPION"
RESEARCH_CHALLENGER = "RESEARCH_CHALLENGER"
ROLES = (CHAMPION, RESEARCH_CHALLENGER)

REGISTERED_CHAMPION = "REGISTERED_CHAMPION"
REGISTERED_CHALLENGER = "REGISTERED_CHALLENGER"
SHADOW_EVALUATION = "SHADOW_EVALUATION"
PROSPECTIVE_WALK_FORWARD_EVIDENCE = "PROSPECTIVE_WALK_FORWARD_EVIDENCE"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
APPROVED_FOR_MAIN = "APPROVED_FOR_MAIN"
PROMOTION_STATES = (
    REGISTERED_CHAMPION,
    REGISTERED_CHALLENGER,
    SHADOW_EVALUATION,
    PROSPECTIVE_WALK_FORWARD_EVIDENCE,
    REVIEW_REQUIRED,
    APPROVED_FOR_MAIN,
)

RESPONSIBILITY_IDS = (
    "fixture_identity",
    "source_evidence_and_lineage",
    "fixture_state_schema",
    "provider_market_semantics",
    "provider_quote_identity_and_freshness",
    "settlement_semantics",
    "request_date_and_target_semantics",
    "champion_feature_interface",
    "champion_probability_interface",
    "calibration_interface",
    "market_projection",
    "price_all_and_de_vig",
    "market_router",
    "portfolio_optimizer",
    "delivery_share_code_transport",
    "run_receipt_and_observability",
)

_COMPONENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.ASCII)
_REGIME_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_:-]*$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_GIT_BLOB_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)

_RECORD_FIELDS = (
    "responsibility_id",
    "regime_id",
    "component_id",
    "contract_sha256",
    "artifact_git_blob_sha",
    "role",
    "allowed_profiles",
    "promotion_state",
    "main_authority",
    "compatible_schema_versions",
)
_ALIAS_FIELDS = ("alias_id", "target_component_id")
_TOP_LEVEL_FIELDS = (
    "schema_version",
    "policy_id",
    "registry_contract_sha256",
    "source_controlled_writes_only",
    "runtime_mutation_allowed",
    "records",
    "aliases",
)
_CHALLENGER_STATES = frozenset(
    {
        REGISTERED_CHALLENGER,
        SHADOW_EVALUATION,
        PROSPECTIVE_WALK_FORWARD_EVIDENCE,
        REVIEW_REQUIRED,
    }
)
_CHAMPION_STATES = frozenset({REGISTERED_CHAMPION, APPROVED_FOR_MAIN})


class ComponentAuthorityRegistryError(ValueError):
    """Registry state is ambiguous, incompatible, unknown or unauthorized."""


def _exact_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ComponentAuthorityRegistryError(f"{label} must be non-empty exact text")
    return value


def _exact_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ComponentAuthorityRegistryError(f"{label} must be exact bool")
    return value


def _canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ComponentAuthorityRegistryError("canonical registry serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "record_fields": list(_RECORD_FIELDS),
        "alias_fields": list(_ALIAS_FIELDS),
        "authority_profiles": list(AUTHORITY_PROFILES),
        "roles": list(ROLES),
        "promotion_states": list(PROMOTION_STATES),
        "main_resolution_requires": "APPROVED_FOR_MAIN_AND_MAIN_AUTHORITY",
        "challenger_profile": "SHADOW_ONLY",
        "runtime_mutation_allowed": False,
        "source_controlled_writes_only": True,
    }


def calculate_registry_contract_sha256() -> str:
    return canonical_sha256(_contract_payload())


def validate_registry_contract() -> str:
    actual = calculate_registry_contract_sha256()
    if actual != EXPECTED_REGISTRY_CONTRACT_SHA256:
        raise ComponentAuthorityRegistryError("component authority registry contract drifted")
    return actual


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComponentAuthorityRegistryError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ComponentAuthorityRegistryError(f"non-finite JSON constant is forbidden: {value}")


def _load_json(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise ComponentAuthorityRegistryError("registry JSON input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ComponentAuthorityRegistryError("registry JSON is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ComponentAuthorityRegistryError("registry JSON is invalid") from exc


def _profiles(value: Any) -> tuple[str, ...]:
    if type(value) not in {list, tuple} or not value:
        raise ComponentAuthorityRegistryError("allowed_profiles must be non-empty list/tuple")
    items = tuple(value)
    if any(type(item) is not str or item not in AUTHORITY_PROFILES for item in items):
        raise ComponentAuthorityRegistryError("allowed_profiles escaped MAIN/SHADOW vocabulary")
    normalized = tuple(sorted(set(items)))
    if len(normalized) != len(items) or normalized != items:
        raise ComponentAuthorityRegistryError("allowed_profiles must be sorted unique")
    return normalized


def _schema_versions(value: Any) -> tuple[int, ...]:
    if type(value) not in {list, tuple} or not value:
        raise ComponentAuthorityRegistryError(
            "compatible_schema_versions must be non-empty list/tuple"
        )
    items = tuple(value)
    if any(type(item) is not int or item <= 0 for item in items):
        raise ComponentAuthorityRegistryError(
            "compatible_schema_versions must contain positive exact integers"
        )
    normalized = tuple(sorted(set(items)))
    if len(normalized) != len(items) or normalized != items:
        raise ComponentAuthorityRegistryError(
            "compatible_schema_versions must be sorted unique"
        )
    return normalized


@dataclass(frozen=True)
class ComponentAuthorityRecord:
    responsibility_id: str
    regime_id: str
    component_id: str
    contract_sha256: str
    artifact_git_blob_sha: str
    role: str
    allowed_profiles: tuple[str, ...]
    promotion_state: str
    main_authority: bool
    compatible_schema_versions: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.responsibility_id not in RESPONSIBILITY_IDS:
            raise ComponentAuthorityRegistryError("unknown semantic responsibility")
        if (
            type(self.regime_id) is not str
            or _REGIME_ID_RE.fullmatch(self.regime_id) is None
        ):
            raise ComponentAuthorityRegistryError("regime_id must be canonical uppercase identity")
        if (
            type(self.component_id) is not str
            or _COMPONENT_ID_RE.fullmatch(self.component_id) is None
        ):
            raise ComponentAuthorityRegistryError("component_id must be canonical module identity")
        if (
            type(self.contract_sha256) is not str
            or _SHA256_RE.fullmatch(self.contract_sha256) is None
        ):
            raise ComponentAuthorityRegistryError("contract_sha256 must be lowercase SHA-256")
        if (
            type(self.artifact_git_blob_sha) is not str
            or _GIT_BLOB_RE.fullmatch(self.artifact_git_blob_sha) is None
        ):
            raise ComponentAuthorityRegistryError(
                "artifact_git_blob_sha must be exact lowercase Git blob SHA"
            )
        if self.role not in ROLES:
            raise ComponentAuthorityRegistryError("component role escaped champion/challenger vocabulary")
        object.__setattr__(self, "allowed_profiles", _profiles(self.allowed_profiles))
        object.__setattr__(
            self,
            "compatible_schema_versions",
            _schema_versions(self.compatible_schema_versions),
        )
        if self.promotion_state not in PROMOTION_STATES:
            raise ComponentAuthorityRegistryError("promotion_state escaped reviewed vocabulary")
        _exact_bool(self.main_authority, "main_authority")

        if self.role == RESEARCH_CHALLENGER:
            if self.allowed_profiles != (SHADOW,):
                raise ComponentAuthorityRegistryError(
                    "research challengers must remain SHADOW-only"
                )
            if self.main_authority is not False:
                raise ComponentAuthorityRegistryError(
                    "research challenger cannot have MAIN authority"
                )
            if self.promotion_state not in _CHALLENGER_STATES:
                raise ComponentAuthorityRegistryError(
                    "research challenger promotion state is not research-only"
                )
        else:
            if self.promotion_state not in _CHAMPION_STATES:
                raise ComponentAuthorityRegistryError(
                    "champion promotion state is incompatible with champion role"
                )

        if self.main_authority:
            if self.role != CHAMPION:
                raise ComponentAuthorityRegistryError("MAIN authority requires champion role")
            if self.promotion_state != APPROVED_FOR_MAIN:
                raise ComponentAuthorityRegistryError(
                    "MAIN authority requires APPROVED_FOR_MAIN promotion state"
                )
            if MAIN not in self.allowed_profiles:
                raise ComponentAuthorityRegistryError(
                    "MAIN authority requires MAIN profile eligibility"
                )
        elif self.promotion_state == APPROVED_FOR_MAIN:
            raise ComponentAuthorityRegistryError(
                "APPROVED_FOR_MAIN requires explicit main_authority=true"
            )

    @classmethod
    def from_dict(cls, value: Any) -> "ComponentAuthorityRecord":
        if type(value) is not dict or tuple(value.keys()) != _RECORD_FIELDS:
            raise ComponentAuthorityRegistryError("component authority record fields drifted")
        return cls(
            responsibility_id=value["responsibility_id"],
            regime_id=value["regime_id"],
            component_id=value["component_id"],
            contract_sha256=value["contract_sha256"],
            artifact_git_blob_sha=value["artifact_git_blob_sha"],
            role=value["role"],
            allowed_profiles=tuple(value["allowed_profiles"]) if type(value["allowed_profiles"]) is list else value["allowed_profiles"],
            promotion_state=value["promotion_state"],
            main_authority=value["main_authority"],
            compatible_schema_versions=(
                tuple(value["compatible_schema_versions"])
                if type(value["compatible_schema_versions"]) is list
                else value["compatible_schema_versions"]
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "responsibility_id": self.responsibility_id,
            "regime_id": self.regime_id,
            "component_id": self.component_id,
            "contract_sha256": self.contract_sha256,
            "artifact_git_blob_sha": self.artifact_git_blob_sha,
            "role": self.role,
            "allowed_profiles": list(self.allowed_profiles),
            "promotion_state": self.promotion_state,
            "main_authority": self.main_authority,
            "compatible_schema_versions": list(self.compatible_schema_versions),
        }


@dataclass(frozen=True)
class ComponentAuthorityAlias:
    alias_id: str
    target_component_id: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.alias_id, "alias_id"),
            (self.target_component_id, "target_component_id"),
        ):
            if type(value) is not str or _COMPONENT_ID_RE.fullmatch(value) is None:
                raise ComponentAuthorityRegistryError(f"{label} must be canonical component identity")
        if self.alias_id == self.target_component_id:
            raise ComponentAuthorityRegistryError("component alias cannot target itself")

    @classmethod
    def from_dict(cls, value: Any) -> "ComponentAuthorityAlias":
        if type(value) is not dict or tuple(value.keys()) != _ALIAS_FIELDS:
            raise ComponentAuthorityRegistryError("component alias fields drifted")
        return cls(
            alias_id=value["alias_id"],
            target_component_id=value["target_component_id"],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "alias_id": self.alias_id,
            "target_component_id": self.target_component_id,
        }


@dataclass(frozen=True)
class ComponentAuthorityRegistry:
    records: tuple[ComponentAuthorityRecord, ...]
    aliases: tuple[ComponentAuthorityAlias, ...] = ()
    source_controlled_writes_only: bool = True
    runtime_mutation_allowed: bool = False
    _by_component: Mapping[str, ComponentAuthorityRecord] = field(
        init=False, repr=False, compare=False
    )
    _alias_targets: Mapping[str, str] = field(init=False, repr=False, compare=False)
    _champions: Mapping[tuple[str, str], ComponentAuthorityRecord] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        validate_registry_contract()
        _exact_bool(self.source_controlled_writes_only, "source_controlled_writes_only")
        _exact_bool(self.runtime_mutation_allowed, "runtime_mutation_allowed")
        if self.source_controlled_writes_only is not True:
            raise ComponentAuthorityRegistryError("registry writes must remain source-controlled")
        if self.runtime_mutation_allowed is not False:
            raise ComponentAuthorityRegistryError("runtime registry mutation is forbidden")

        records = tuple(self.records)
        if any(type(item) is not ComponentAuthorityRecord for item in records):
            raise ComponentAuthorityRegistryError(
                "registry records must contain exact ComponentAuthorityRecord values"
            )
        records = tuple(
            sorted(
                records,
                key=lambda item: (
                    item.responsibility_id,
                    item.regime_id,
                    item.role,
                    item.component_id,
                ),
            )
        )
        by_component: dict[str, ComponentAuthorityRecord] = {}
        champions: dict[tuple[str, str], ComponentAuthorityRecord] = {}
        for record in records:
            if record.component_id in by_component:
                raise ComponentAuthorityRegistryError("duplicate component identity in registry")
            by_component[record.component_id] = record
            if record.role == CHAMPION:
                key = (record.responsibility_id, record.regime_id)
                if key in champions:
                    raise ComponentAuthorityRegistryError(
                        "ambiguous champion state for responsibility/regime"
                    )
                champions[key] = record

        aliases = tuple(self.aliases)
        if any(type(item) is not ComponentAuthorityAlias for item in aliases):
            raise ComponentAuthorityRegistryError(
                "registry aliases must contain exact ComponentAuthorityAlias values"
            )
        aliases = tuple(sorted(aliases, key=lambda item: item.alias_id))
        alias_targets: dict[str, str] = {}
        for alias in aliases:
            if alias.alias_id in by_component or alias.alias_id in alias_targets:
                raise ComponentAuthorityRegistryError("duplicate or shadowing component alias")
            if alias.target_component_id not in by_component:
                raise ComponentAuthorityRegistryError("component alias targets unknown identity")
            alias_targets[alias.alias_id] = alias.target_component_id

        object.__setattr__(self, "records", records)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "_by_component", MappingProxyType(by_component))
        object.__setattr__(self, "_alias_targets", MappingProxyType(alias_targets))
        object.__setattr__(self, "_champions", MappingProxyType(champions))

    @classmethod
    def from_dict(cls, value: Any) -> "ComponentAuthorityRegistry":
        if type(value) is not dict or tuple(value.keys()) != _TOP_LEVEL_FIELDS:
            raise ComponentAuthorityRegistryError("component authority registry fields drifted")
        if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise ComponentAuthorityRegistryError("component authority registry schema drifted")
        if value["policy_id"] != POLICY_ID:
            raise ComponentAuthorityRegistryError("component authority registry policy drifted")
        if value["registry_contract_sha256"] != EXPECTED_REGISTRY_CONTRACT_SHA256:
            raise ComponentAuthorityRegistryError("registry contract identity drifted")
        if type(value["records"]) is not list or type(value["aliases"]) is not list:
            raise ComponentAuthorityRegistryError("registry records/aliases must serialize as lists")
        return cls(
            records=tuple(ComponentAuthorityRecord.from_dict(item) for item in value["records"]),
            aliases=tuple(ComponentAuthorityAlias.from_dict(item) for item in value["aliases"]),
            source_controlled_writes_only=value["source_controlled_writes_only"],
            runtime_mutation_allowed=value["runtime_mutation_allowed"],
        )

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "ComponentAuthorityRegistry":
        return cls.from_dict(_load_json(raw))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "registry_contract_sha256": EXPECTED_REGISTRY_CONTRACT_SHA256,
            "source_controlled_writes_only": self.source_controlled_writes_only,
            "runtime_mutation_allowed": self.runtime_mutation_allowed,
            "records": [item.to_dict() for item in self.records],
            "aliases": [item.to_dict() for item in self.aliases],
        }

    @property
    def canonical_sha256(self) -> str:
        return canonical_sha256(self)

    def resolve_component(self, component_or_alias_id: str) -> ComponentAuthorityRecord:
        component_id = _exact_text(component_or_alias_id, "component identity")
        if component_id in self._alias_targets:
            component_id = self._alias_targets[component_id]
        record = self._by_component.get(component_id)
        if record is None:
            raise ComponentAuthorityRegistryError("unknown component identity")
        return record

    def resolve_champion(
        self,
        responsibility_id: str,
        regime_id: str,
        *,
        profile: str,
        required_schema_version: int,
    ) -> ComponentAuthorityRecord:
        if responsibility_id not in RESPONSIBILITY_IDS:
            raise ComponentAuthorityRegistryError("unknown semantic responsibility")
        if type(regime_id) is not str or _REGIME_ID_RE.fullmatch(regime_id) is None:
            raise ComponentAuthorityRegistryError("regime_id must be canonical uppercase identity")
        if profile not in AUTHORITY_PROFILES:
            raise ComponentAuthorityRegistryError("profile escaped MAIN/SHADOW vocabulary")
        if type(required_schema_version) is not int or required_schema_version <= 0:
            raise ComponentAuthorityRegistryError("required_schema_version must be positive exact int")
        record = self._champions.get((responsibility_id, regime_id))
        if record is None:
            raise ComponentAuthorityRegistryError("no champion registered for responsibility/regime")
        if profile not in record.allowed_profiles:
            raise ComponentAuthorityRegistryError("champion is not eligible for requested profile")
        if required_schema_version not in record.compatible_schema_versions:
            raise ComponentAuthorityRegistryError("champion schema is incompatible with request")
        if profile == MAIN and (
            record.main_authority is not True
            or record.promotion_state != APPROVED_FOR_MAIN
        ):
            raise ComponentAuthorityRegistryError(
                "MAIN resolution requires explicit APPROVED_FOR_MAIN authority"
            )
        return record

    def resolve_research_challengers(
        self,
        responsibility_id: str,
        regime_id: str,
        *,
        profile: str,
        required_schema_version: int,
    ) -> tuple[ComponentAuthorityRecord, ...]:
        if profile != SHADOW:
            raise ComponentAuthorityRegistryError("research challengers are SHADOW-only")
        if responsibility_id not in RESPONSIBILITY_IDS:
            raise ComponentAuthorityRegistryError("unknown semantic responsibility")
        if type(regime_id) is not str or _REGIME_ID_RE.fullmatch(regime_id) is None:
            raise ComponentAuthorityRegistryError("regime_id must be canonical uppercase identity")
        if type(required_schema_version) is not int or required_schema_version <= 0:
            raise ComponentAuthorityRegistryError("required_schema_version must be positive exact int")
        return tuple(
            item
            for item in self.records
            if item.responsibility_id == responsibility_id
            and item.regime_id == regime_id
            and item.role == RESEARCH_CHALLENGER
            and required_schema_version in item.compatible_schema_versions
        )


def load_default_registry() -> ComponentAuthorityRegistry:
    """Load the sole source-controlled P1.7 authority registry.

    There is intentionally no environment override, runtime write path, experiment
    callback or auto-promotion hook.  Changing authority requires a normal source
    change reviewed through the repository.
    """
    try:
        raw = DEFAULT_REGISTRY_PATH.read_bytes()
    except OSError as exc:
        raise ComponentAuthorityRegistryError(
            "source-controlled component authority registry is unavailable"
        ) from exc
    return ComponentAuthorityRegistry.from_json_bytes(raw)


__all__ = [
    "APPROVED_FOR_MAIN",
    "AUTHORITY_PROFILES",
    "CHAMPION",
    "ComponentAuthorityAlias",
    "ComponentAuthorityRecord",
    "ComponentAuthorityRegistry",
    "ComponentAuthorityRegistryError",
    "DEFAULT_REGISTRY_PATH",
    "EXPECTED_REGISTRY_CONTRACT_SHA256",
    "MAIN",
    "POLICY_ID",
    "PROSPECTIVE_WALK_FORWARD_EVIDENCE",
    "REGISTERED_CHALLENGER",
    "REGISTERED_CHAMPION",
    "RESEARCH_CHALLENGER",
    "RESPONSIBILITY_IDS",
    "REVIEW_REQUIRED",
    "SCHEMA_VERSION",
    "SHADOW",
    "SHADOW_EVALUATION",
    "calculate_registry_contract_sha256",
    "canonical_sha256",
    "load_default_registry",
    "validate_registry_contract",
]
