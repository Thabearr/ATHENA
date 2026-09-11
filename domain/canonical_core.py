"""Pure P2.0 composition boundary for ATHENA's registered canonical stages."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping, Sequence

from domain import component_authority_registry as _authority
from domain import market_router_canonical_adapter as _router
from domain import portfolio_optimizer as _portfolio
from domain import price_all as _price_all
from domain import provider_market_semantics as _provider_semantics
from domain import run_contracts as _run_contracts
from domain import sportybet_share_code as _share_code


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_SHARED_CANONICAL_CORE_V1"
CURRENT_SPORTYBET_PROVIDER = "CURRENT_SPORTYBET_PROVIDER"
CANONICAL_RESPONSIBILITIES = (
    "provider_market_semantics",
    "price_all_and_de_vig",
    "market_router",
    "portfolio_optimizer",
    "delivery_share_code_transport",
)


class CanonicalCoreError(ValueError):
    """A profile, registry record, or canonical component is not trustworthy."""


def canonical_json_bytes(value: Any) -> bytes:
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
        raise CanonicalCoreError("canonical core serialization failed") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "registry_policy_id": _authority.POLICY_ID,
        "run_contract_policy_id": _run_contracts.POLICY_ID,
        "responsibilities": list(CANONICAL_RESPONSIBILITIES),
        "profile_manifest_required": "domain.run_contracts.AuthorityManifest",
        "provider_acquisition": False,
        "model_inference": False,
        "orchestration": False,
        "runtime_registry_mutation": False,
        "public_registry_source": "component_authority_registry.load_default_registry",
        "main_promotion": False,
    }


def calculate_canonical_core_contract_sha256() -> str:
    return canonical_sha256(_contract_payload())


EXPECTED_CONTRACT_SHA256 = "af4a73f8852893e7391ae85bac092105d305fa5b9e77af273809fcdcb3dc4c4a"


def validate_canonical_core_contract() -> Mapping[str, str]:
    actual = calculate_canonical_core_contract_sha256()
    if actual != EXPECTED_CONTRACT_SHA256:
        raise CanonicalCoreError("canonical core contract drifted")
    if _authority.validate_registry_contract() != _authority.EXPECTED_REGISTRY_CONTRACT_SHA256:
        raise CanonicalCoreError("component authority registry contract drifted")
    return {
        "canonical_core_contract_sha256": actual,
        "component_authority_registry_contract_sha256": _authority.EXPECTED_REGISTRY_CONTRACT_SHA256,
    }


def _git_blob_sha(module: Any) -> str:
    path = getattr(module, "__file__", None)
    if type(path) is not str or not path.endswith(".py"):
        raise CanonicalCoreError("canonical component has no source artifact")
    source_path = Path(path).resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        relative_path = source_path.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise CanonicalCoreError("canonical component source is outside repository") from exc
    # A registry record pins a Git *blob*, whose identity uses Git's checked-in
    # content filters rather than the workstation's CRLF representation.  This
    # is deliberately source-only verification; no module discovery or network
    # operation is involved.  Missing Git/filter state fails closed.
    try:
        completed = subprocess.run(
            [
                "git", "-C", str(repository_root), "hash-object", "--path",
                relative_path, "--filters", str(source_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanonicalCoreError("canonical component Git blob verification failed") from exc
    digest = completed.stdout.strip()
    if completed.returncode != 0 or len(digest) != 40 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise CanonicalCoreError("canonical component Git blob verification failed")
    return digest


def _provider_identity() -> str:
    return _provider_semantics.validate_provider_market_semantics_contract()[
        "canonical_provider_market_semantics_contract_sha256"
    ]


def _price_identity() -> str:
    return _price_all.validate_price_all_contract()["implementation_contract_sha256"]


def _router_identity() -> str:
    return _router.validate_canonical_market_router_contract()[
        "canonical_market_router_contract_sha256"
    ]


def _portfolio_identity() -> str:
    return _portfolio.validate_portfolio_contract()["canonical_portfolio_contract_sha256"]


def _share_code_identity() -> str:
    return _share_code.validate_share_code_contract()[
        "canonical_share_code_contract_sha256"
    ]


_COMPONENT_SPECS: Mapping[str, tuple[str, Any, Callable[[], str]]] = {
    "provider_market_semantics": (
        "domain.provider_market_semantics", _provider_semantics, _provider_identity
    ),
    "price_all_and_de_vig": ("domain.price_all", _price_all, _price_identity),
    "market_router": (
        "domain.market_router_canonical_adapter", _router, _router_identity
    ),
    "portfolio_optimizer": ("domain.portfolio_optimizer", _portfolio, _portfolio_identity),
    "delivery_share_code_transport": (
        "domain.sportybet_share_code", _share_code, _share_code_identity
    ),
}


@dataclass(frozen=True, init=False)
class CanonicalCoreBindings:
    """Builder-only immutable proof of five exact profile-authorized owners."""

    schema_version: int
    policy_id: str
    regime_id: str
    authority_profile: str
    share_code_generation: bool
    authority_manifest_sha256: str
    registry_canonical_sha256: str
    records: tuple[_authority.ComponentAuthorityRecord, ...]
    canonical_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalCoreError("CanonicalCoreBindings is builder-only")

    @classmethod
    def _create(
        cls,
        *,
        regime_id: str,
        authority_profile: str,
        share_code_generation: bool,
        authority_manifest_sha256: str,
        registry_canonical_sha256: str,
        records: Sequence[_authority.ComponentAuthorityRecord],
    ) -> "CanonicalCoreBindings":
        value = object.__new__(cls)
        ordered = tuple(
            sorted(records, key=lambda item: CANONICAL_RESPONSIBILITIES.index(item.responsibility_id))
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "regime_id": regime_id,
            "authority_profile": authority_profile,
            "share_code_generation": share_code_generation,
            "authority_manifest_sha256": authority_manifest_sha256,
            "registry_canonical_sha256": registry_canonical_sha256,
            "records": [item.to_dict() for item in ordered],
        }
        for key, item in {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "regime_id": regime_id,
            "authority_profile": authority_profile,
            "share_code_generation": share_code_generation,
            "authority_manifest_sha256": authority_manifest_sha256,
            "registry_canonical_sha256": registry_canonical_sha256,
            "records": ordered,
            "canonical_sha256": canonical_sha256(payload),
        }.items():
            object.__setattr__(value, key, item)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "regime_id": self.regime_id,
            "authority_profile": self.authority_profile,
            "share_code_generation": self.share_code_generation,
            "authority_manifest_sha256": self.authority_manifest_sha256,
            "registry_canonical_sha256": self.registry_canonical_sha256,
            "records": [item.to_dict() for item in self.records],
            "canonical_sha256": self.canonical_sha256,
        }

    def record_for(self, responsibility_id: str) -> _authority.ComponentAuthorityRecord:
        if responsibility_id not in CANONICAL_RESPONSIBILITIES:
            raise CanonicalCoreError("unknown canonical core responsibility")
        for record in self.records:
            if record.responsibility_id == responsibility_id:
                return record
        raise CanonicalCoreError("canonical core record is missing")

    def build_provider_semantics(
        self, evidence: Sequence[_provider_semantics.ProviderEventEvidence], *, evaluation_time: Any,
        scan_cap: int = 20, scan_attempts: int | None = None,
    ) -> _provider_semantics.ProviderMarketSemanticsRegistry:
        self.record_for("provider_market_semantics")
        return _provider_semantics.build_provider_market_semantics_registry(
            evidence, evaluation_time=evaluation_time, scan_cap=scan_cap, scan_attempts=scan_attempts
        )

    def price_all_as_of(self, candidates: Iterable[Any], source_bundle: Any, *, evaluation_time: Any,
                         max_quote_age_seconds: int = _price_all.DEFAULT_MAX_QUOTE_AGE_SECONDS,
                         minimum_lead_seconds: int = _price_all.DEFAULT_MINIMUM_LEAD_SECONDS) -> _price_all.PriceAllEvaluation:
        self.record_for("price_all_and_de_vig")
        return _price_all.price_all_as_of(candidates, source_bundle, evaluation_time=evaluation_time,
                                          max_quote_age_seconds=max_quote_age_seconds,
                                          minimum_lead_seconds=minimum_lead_seconds)

    def route_as_of(self, evaluation: _price_all.PriceAllEvaluation, *, fixture_state: Any,
                     evaluation_time: Any) -> _router.RouterDecision:
        self.record_for("market_router")
        return _router.route(evaluation, fixture_state=fixture_state, evaluation_time=evaluation_time)

    def optimize_portfolio_as_of(self, decisions: Iterable[_router.RouterDecision], *, target_legs: int,
                                 evaluation_time: Any) -> _portfolio.SelectedPortfolio:
        self.record_for("portfolio_optimizer")
        return _portfolio.optimize_portfolio_as_of(decisions, target_legs=target_legs,
                                                    evaluation_time=evaluation_time)

    def create_share_code_as_of(self, portfolio: _portfolio.SelectedPortfolio,
                                bindings: Sequence[_share_code.SportyBetProviderBinding], *, output_dir: Path,
                                evaluation_time: Any, semantic_resolver: _share_code.SemanticResolver,
                                roundtrip_transport: _share_code.RoundtripTransport,
                                delay_seconds: float = 0.0) -> _share_code.VerifiedShareCode | _share_code.ShareCodeFailure:
        self.record_for("delivery_share_code_transport")
        if self.share_code_generation is not True:
            raise CanonicalCoreError("AuthorityManifest does not permit share-code generation")
        return _share_code.create_verified_share_code_as_of(
            portfolio, bindings, output_dir=output_dir, evaluation_time=evaluation_time,
            semantic_resolver=semantic_resolver, roundtrip_transport=roundtrip_transport,
            delay_seconds=delay_seconds,
        )


def _validate_record(
    record: _authority.ComponentAuthorityRecord, responsibility_id: str,
) -> None:
    expected_component_id, module, identity = _COMPONENT_SPECS[responsibility_id]
    if record.component_id != expected_component_id:
        raise CanonicalCoreError("registry component identity differs from reviewed canonical owner")
    if record.contract_sha256 != identity():
        raise CanonicalCoreError("registry component contract identity drifted")
    if record.artifact_git_blob_sha != _git_blob_sha(module):
        raise CanonicalCoreError("registry component source artifact identity drifted")


def _resolve_canonical_core_with_registry_for_test(
    authority_manifest: _run_contracts.AuthorityManifest,
    *,
    regime_id: str = CURRENT_SPORTYBET_PROVIDER,
    required_schema_version: int = SCHEMA_VERSION,
    registry: _authority.ComponentAuthorityRegistry,
) -> CanonicalCoreBindings:
    """Test-only structural resolver for deliberately synthetic registry states.

    This private helper is not an authority entrypoint.  The public resolver
    below always reloads the reviewed, source-controlled registry.
    """
    validate_canonical_core_contract()
    if type(authority_manifest) is not _run_contracts.AuthorityManifest:
        raise CanonicalCoreError("exact AuthorityManifest is required")
    if authority_manifest.provider_acquisition is not False:
        raise CanonicalCoreError("shared canonical core cannot acquire providers")
    if type(regime_id) is not str or not regime_id:
        raise CanonicalCoreError("regime_id must be exact non-empty text")
    if type(required_schema_version) is not int or required_schema_version <= 0:
        raise CanonicalCoreError("required_schema_version must be positive exact int")
    if type(registry) is not _authority.ComponentAuthorityRegistry:
        raise CanonicalCoreError("exact ComponentAuthorityRegistry is required")
    if registry.runtime_mutation_allowed is not False:
        raise CanonicalCoreError("runtime registry mutation is forbidden")
    records = []
    try:
        for responsibility_id in CANONICAL_RESPONSIBILITIES:
            record = registry.resolve_champion(
                responsibility_id, regime_id,
                profile=authority_manifest.authority_profile,
                required_schema_version=required_schema_version,
            )
            _validate_record(record, responsibility_id)
            records.append(record)
    except _authority.ComponentAuthorityRegistryError as exc:
        raise CanonicalCoreError("canonical champion resolution failed closed") from exc
    return CanonicalCoreBindings._create(
        regime_id=regime_id,
        authority_profile=authority_manifest.authority_profile,
        share_code_generation=authority_manifest.share_code_generation,
        authority_manifest_sha256=_run_contracts.canonical_sha256(authority_manifest),
        registry_canonical_sha256=registry.canonical_sha256,
        records=records,
    )


def resolve_canonical_core(
    authority_manifest: _run_contracts.AuthorityManifest,
    *,
    regime_id: str = CURRENT_SPORTYBET_PROVIDER,
    required_schema_version: int = SCHEMA_VERSION,
) -> CanonicalCoreBindings:
    """Resolve only the reviewed source-controlled canonical champions.

    A caller cannot supply an in-memory registry to this public authority
    boundary.  Promotion therefore requires a reviewed source change to the
    default registry rather than a runtime object injection.
    """
    return _resolve_canonical_core_with_registry_for_test(
        authority_manifest,
        regime_id=regime_id,
        required_schema_version=required_schema_version,
        registry=_authority.load_default_registry(),
    )


__all__ = [
    "CANONICAL_RESPONSIBILITIES",
    "CURRENT_SPORTYBET_PROVIDER",
    "CanonicalCoreBindings",
    "CanonicalCoreError",
    "EXPECTED_CONTRACT_SHA256",
    "POLICY_ID",
    "SCHEMA_VERSION",
    "calculate_canonical_core_contract_sha256",
    "canonical_json_bytes",
    "canonical_sha256",
    "resolve_canonical_core",
    "validate_canonical_core_contract",
]
