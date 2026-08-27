"""Canonical ATHENA accumulator-to-SportyBet execution boundary.

This module is deliberately an orchestration layer.  It does not create a
probability, calibrate a model, price a quote, route a market, or optimize a
portfolio itself.  It replays the already-reviewed Phase 6/7/8/9 boundaries,
adapts the resulting provider-bound leg to the semantic SportyBet contract,
and refuses to return a code unless the provider create/reload payloads prove
the same human-readable selections.

The public builders are source-issued only:

* Phase 6 candidates are re-issued from an exact calibration artifact and row;
* SportyBet quotes are re-issued from the exact reviewed mapping and verified
  user-controlled native evidence;
* Fixture State v2 is built from one exact pre-match intelligence snapshot;
* the Phase 9 fixture input is issued by replaying the full-UTC receipt.

The anonymous SportyBet share operation is not a wager operation.  No login,
cookie, wallet, stake, or bet authority is introduced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

from domain import sportybet_fotmob_full_utc_reconciliation as reconciliation
from domain import sportybet_fotmob_full_utc_reconciliation_receipt as reconciliation_receipt
from domain import sportybet_user_controlled_native_inventory as source_inventory
from domain._accumulator_optimizer_contracts import (
    AccumulatorOptimizerError,
    validate_accumulator_optimizer_contract,
)
from domain._forward_calibration_fit import ForwardCalibrationArtifact
from domain._forward_calibration_projection import CalibrationVectorRow
from domain._price_all_contracts import (
    CalibratedValueCandidate,
    PriceAllError,
    SportyBetExactQuote,
    validate_price_all_contract,
)
from domain.accumulator_optimizer import (
    AccumulatorFixtureInput,
    AccumulatorOptimization,
    PortfolioLeg,
    optimize_accumulator,
)
from domain.fixture_intelligence import (
    FixtureIntelligenceSnapshot,
    canonical_snapshot_bytes,
    sha256_bytes,
)
from domain.fixture_state_v2 import (
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FixtureStateV2Snapshot,
    build_fixture_state_v2_snapshot,
)
from domain.markets import MarketId, OutcomeId
from domain.pricing import DEFAULT_MAX_QUOTE_AGE_SECONDS
from domain.sportybet_reviewed_canonical_market_mapping import (
    MappedSportyBetCanonicalSelection,
    SportyBetReviewedCanonicalMarketMapping,
    canonical_mapping_sha256,
)
from scripts import sportybet_semantic_share_bridge as semantic_bridge


CANONICAL_ACCUMULATOR_EXECUTION_DATASET = (
    "athena_canonical_accumulator_sportybet_execution"
)
CANONICAL_ACCUMULATOR_EXECUTION_SCHEMA_VERSION = 1
CANONICAL_ACCUMULATOR_EXECUTION_CONTRACT_VERSION = 1
SEMANTIC_INTENT_SCHEMA = "athena-sportybet-semantic-intent-v1"
SEMANTIC_ROUNDTRIP_POLICY_ID = (
    "SEMANTIC_INTENT_CREATE_RELOAD_EXACT_PROVIDER_SELECTION_V1"
)
SOURCE_REPLAY_POLICY_ID = (
    "REPLAY_INTELLIGENCE_MAPPING_EVIDENCE_RECONCILIATION_BEFORE_EXECUTION_V1"
)
COUNT_INVARIANT_POLICY_ID = (
    "ROUTER_OPTIMIZER_INTENT_CREATE_RELOAD_COUNTS_EXACT_OR_NO_CODE_V1"
)
SHORTFALL_POLICY_ID = (
    "REQUESTED_FOLD_COUNT_IS_TARGET_NO_FORCED_REPLACEMENT_OR_PADDING_V1"
)
FRESHNESS_POLICY_ID = "SOURCE_EVIDENCE_OBSERVED_AT_MAX_900S_PREMATCH_BOOKABLE_V1"
SEMANTIC_NATIVE_ROUNDTRIP_SOURCE_BINDING_POLICY_ID = (
    "CREATE_RELOAD_NATIVE_ROWS_MUST_MATCH_SOURCE_QUOTE_AND_SEMANTIC_INTENT_V1"
)
MINIMUM_LEAD_SECONDS_DEFAULT = 120
REAL_CURRENT_CANONICAL_EXECUTION_STATUS = (
    "NOT_RUN_VERIFIED_CURRENT_SPORTYBET_EXECUTION_CORPUS_UNAVAILABLE"
)

AUTHORITY_FLAGS = MappingProxyType(
    {
        "canonical_orchestration": True,
        "semantic_intent_adaptation": True,
        "anonymous_share_code_generation": True,
        "price_all_authority_delegated": True,
        "market_router_authority_delegated": True,
        "accumulator_optimizer_authority_delegated": True,
        "legacy_accumulator_engine_authority": False,
        "model_authority": False,
        "probability_authority": False,
        "calibration_authority": False,
        "pricing_authority": False,
        "selection_authority": False,
        "accumulator_authority": False,
        "production_approval": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CanonicalAccumulatorExecutionError(ValueError):
    """Raised when canonical orchestration cannot prove an exact boundary."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalAccumulatorExecutionError(
            "canonical accumulator serialization failed"
        ) from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc(value: datetime, label: str = "evaluation_time") -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalAccumulatorExecutionError(
            f"{label} must be timezone-aware"
        )
    return value.astimezone(timezone.utc)


def _exact_sha(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise CanonicalAccumulatorExecutionError(f"{label} must be a SHA-256")
    return value


def _semantic_name_key(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    return "".join(char.lower() for char in ascii_text if char.isalnum())


def _quote_sha(quote: SportyBetExactQuote) -> str:
    return _sha(quote.to_dict())


def canonical_execution_contract_payload(
    *,
    price_all_contract_sha256: str,
    market_router_contract_sha256: str,
    accumulator_optimizer_contract_sha256: str,
    canonical_market_semantics_sha256: str,
) -> dict[str, Any]:
    """Return the frozen dependency/policy payload for this boundary."""
    return {
        "dataset": CANONICAL_ACCUMULATOR_EXECUTION_DATASET,
        "schema_version": CANONICAL_ACCUMULATOR_EXECUTION_SCHEMA_VERSION,
        "price_all_contract_sha256": price_all_contract_sha256,
        "market_router_contract_sha256": market_router_contract_sha256,
        "accumulator_optimizer_contract_sha256": accumulator_optimizer_contract_sha256,
        "canonical_market_semantics_sha256": canonical_market_semantics_sha256,
        "fixture_state_field_registry_sha256": FIXTURE_STATE_FIELD_REGISTRY_SHA256,
        "sportybet_reconciliation_dataset": reconciliation.DATASET_NAME,
        "sportybet_reconciliation_schema_version": reconciliation.SCHEMA_VERSION,
        "sportybet_reconciliation_receipt_dataset": reconciliation_receipt.DATASET_NAME,
        "sportybet_reconciliation_receipt_schema_version": reconciliation_receipt.SCHEMA_VERSION,
        "sportybet_source_inventory_dataset": source_inventory.DATASET_NAME,
        "sportybet_source_inventory_schema_version": source_inventory.SCHEMA_VERSION,
        "semantic_intent_schema": SEMANTIC_INTENT_SCHEMA,
        "semantic_roundtrip_policy_id": SEMANTIC_ROUNDTRIP_POLICY_ID,
        "source_replay_policy_id": SOURCE_REPLAY_POLICY_ID,
        "count_invariant_policy_id": COUNT_INVARIANT_POLICY_ID,
        "shortfall_policy_id": SHORTFALL_POLICY_ID,
        "freshness_policy_id": FRESHNESS_POLICY_ID,
        "semantic_native_roundtrip_source_binding_policy_id": (
            SEMANTIC_NATIVE_ROUNDTRIP_SOURCE_BINDING_POLICY_ID
        ),
        "max_quote_age_seconds": DEFAULT_MAX_QUOTE_AGE_SECONDS,
        "minimum_lead_seconds_default": MINIMUM_LEAD_SECONDS_DEFAULT,
        "authority_flags": dict(AUTHORITY_FLAGS),
        "real_current_execution_status": REAL_CURRENT_CANONICAL_EXECUTION_STATUS,
    }


def calculate_canonical_execution_contract_sha256(
    *,
    price_all_contract_sha256: str,
    market_router_contract_sha256: str,
    accumulator_optimizer_contract_sha256: str,
    canonical_market_semantics_sha256: str,
    version: int = CANONICAL_ACCUMULATOR_EXECUTION_CONTRACT_VERSION,
) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {
                "version": version,
                "semantics": canonical_execution_contract_payload(
                    price_all_contract_sha256=price_all_contract_sha256,
                    market_router_contract_sha256=market_router_contract_sha256,
                    accumulator_optimizer_contract_sha256=accumulator_optimizer_contract_sha256,
                    canonical_market_semantics_sha256=canonical_market_semantics_sha256,
                ),
            }
        )
    ).hexdigest()


# Filled from the exact payload after the first implementation checkpoint.
EXPECTED_CANONICAL_EXECUTION_CONTRACT_SHA256_BY_VERSION: Mapping[int, str] = {
    1: "e4619cfa17e8e6adabd93317e4c76a34d0d82d5ac7ea66b5775f78130542f3d1",
}


def validate_canonical_execution_contract() -> Mapping[str, str]:
    price = validate_price_all_contract()
    optimizer = validate_accumulator_optimizer_contract()
    if optimizer["market_router_contract_sha256"] != (
        "0e4486527b060109852ab56dd76774b2d150cf8326875e44537a3bce2dc656bf"
    ):
        raise CanonicalAccumulatorExecutionError("Market Router dependency identity drifted")
    if FIXTURE_STATE_FIELD_REGISTRY_SHA256 != (
        "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a"
    ):
        raise CanonicalAccumulatorExecutionError("Fixture State v2 dependency identity drifted")
    actual = calculate_canonical_execution_contract_sha256(
        price_all_contract_sha256=price["price_all_contract_sha256"],
        market_router_contract_sha256=optimizer["market_router_contract_sha256"],
        accumulator_optimizer_contract_sha256=optimizer[
            "accumulator_optimizer_contract_sha256"
        ],
        canonical_market_semantics_sha256=price["canonical_market_semantics_sha256"],
    )
    expected = EXPECTED_CANONICAL_EXECUTION_CONTRACT_SHA256_BY_VERSION.get(
        CANONICAL_ACCUMULATOR_EXECUTION_CONTRACT_VERSION
    )
    if expected is None or actual != expected:
        raise CanonicalAccumulatorExecutionError(
            "canonical accumulator execution contract drift"
        )
    return MappingProxyType(
        {
            "price_all_contract_sha256": price["price_all_contract_sha256"],
            "market_router_contract_sha256": optimizer[
                "market_router_contract_sha256"
            ],
            "accumulator_optimizer_contract_sha256": optimizer[
                "accumulator_optimizer_contract_sha256"
            ],
            "canonical_market_semantics_sha256": price[
                "canonical_market_semantics_sha256"
            ],
            "canonical_execution_contract_sha256": actual,
        }
    )


@dataclass(frozen=True, init=False)
class CanonicalPhase6CandidateInput:
    """Builder-issued Phase 6 artifact/row binding for one candidate."""

    artifact: ForwardCalibrationArtifact
    row: CalibrationVectorRow
    fixture_id: str
    sportybet_event_id: str
    outcome_id: OutcomeId
    strategy: str
    candidate: CalibratedValueCandidate

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalAccumulatorExecutionError(
            "Phase 6 candidate input is builder-only; use from_phase6_calibration()"
        )

    @classmethod
    def from_phase6_calibration(
        cls,
        artifact: ForwardCalibrationArtifact,
        row: CalibrationVectorRow,
        *,
        fixture_id: str,
        sportybet_event_id: str,
        outcome_id: OutcomeId,
        strategy: str = "HIERARCHICAL",
    ) -> "CanonicalPhase6CandidateInput":
        if type(artifact) is not ForwardCalibrationArtifact or type(row) is not CalibrationVectorRow:
            raise CanonicalAccumulatorExecutionError(
                "exact Phase 6 artifact and calibration row are required"
            )
        if type(outcome_id) is not OutcomeId:
            raise CanonicalAccumulatorExecutionError("outcome_id must be canonical")
        try:
            candidate = CalibratedValueCandidate.from_phase6_calibration(
                artifact,
                row,
                fixture_id=fixture_id,
                sportybet_event_id=sportybet_event_id,
                outcome_id=outcome_id,
                strategy=strategy,
            )
        except (PriceAllError, TypeError, ValueError) as exc:
            raise CanonicalAccumulatorExecutionError(
                "Phase 6 candidate issuance failed closed"
            ) from exc
        result = object.__new__(cls)
        values = {
            "artifact": artifact,
            "row": row,
            "fixture_id": fixture_id,
            "sportybet_event_id": sportybet_event_id,
            "outcome_id": outcome_id,
            "strategy": candidate.calibration_strategy,
            "candidate": candidate,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result


def _reissue_phase6_candidate(
    request: CanonicalPhase6CandidateInput,
) -> CalibratedValueCandidate:
    if type(request) is not CanonicalPhase6CandidateInput:
        raise CanonicalAccumulatorExecutionError(
            "phase6_inputs must contain exact canonical Phase 6 bindings"
        )
    try:
        candidate = CalibratedValueCandidate.from_phase6_calibration(
            request.artifact,
            request.row,
            fixture_id=request.fixture_id,
            sportybet_event_id=request.sportybet_event_id,
            outcome_id=request.outcome_id,
            strategy=request.strategy,
        )
    except (PriceAllError, TypeError, ValueError) as exc:
        raise CanonicalAccumulatorExecutionError(
            "Phase 6 candidate could not be re-issued from exact artifact ancestry"
        ) from exc
    if candidate.to_dict() != request.candidate.to_dict():
        raise CanonicalAccumulatorExecutionError(
            "Phase 6 candidate payload differs from its exact artifact/row issuance"
        )
    return candidate


def _inventory_from_source(
    evidence_directory: Path,
    allowed_evidence_root: Path,
) -> source_inventory.SportyBetUserControlledNativeInventory:
    try:
        inventory = source_inventory.build_inventory_from_evidence(
            evidence_directory,
            allowed_root=allowed_evidence_root,
        )
        if type(inventory) is not source_inventory.SportyBetUserControlledNativeInventory:
            raise CanonicalAccumulatorExecutionError(
                "source evidence did not issue exact SportyBet native inventory"
            )
        source_inventory.inventory_sha256(inventory)
    except (source_inventory.SportyBetUserInventoryError, TypeError, ValueError) as exc:
        raise CanonicalAccumulatorExecutionError(
            "verified SportyBet source evidence replay failed"
        ) from exc
    return inventory


def _same_dict(left: Any, right: Any) -> bool:
    try:
        return _canonical_bytes(left) == _canonical_bytes(right)
    except CanonicalAccumulatorExecutionError:
        return False


def _mapped_for_candidate(
    mapping: SportyBetReviewedCanonicalMarketMapping,
    candidate: CalibratedValueCandidate,
) -> MappedSportyBetCanonicalSelection:
    rows = tuple(
        row
        for row in mapping.mapped_selections
        if row.canonical_market_id is candidate.market_id
        and row.canonical_outcome_id is candidate.outcome_id
        and row.canonical_line == candidate.line
    )
    if len(rows) != 1:
        raise CanonicalAccumulatorExecutionError(
            "canonical candidate does not have one exact reviewed SportyBet semantic mapping"
        )
    return rows[0]


def _derive_quotes(
    mapping: SportyBetReviewedCanonicalMarketMapping,
    inventory: source_inventory.SportyBetUserControlledNativeInventory,
    *,
    evidence_directory: Path,
    allowed_evidence_root: Path,
) -> tuple[SportyBetExactQuote, ...]:
    inventory_sha = source_inventory.inventory_sha256(inventory)
    if inventory_sha != mapping.source_native_inventory_sha256:
        raise CanonicalAccumulatorExecutionError(
            "reviewed mapping is not bound to the exact current source inventory"
        )
    rows = tuple(mapping.mapped_selections)
    provider_identities = tuple(
        (
            row.event_id,
            row.provider_market_id,
            row.provider_specifier,
            row.provider_outcome_id,
        )
        for row in rows
    )
    if len(provider_identities) != len(set(provider_identities)):
        raise CanonicalAccumulatorExecutionError(
            "reviewed mapping contains duplicate provider selection identities"
        )
    quotes: list[SportyBetExactQuote] = []
    try:
        for row in rows:
            quote = SportyBetExactQuote.from_reviewed_mapping(
                mapping,
                provider_selection_sha256=row.provider_selection_sha256,
                evidence_directory=evidence_directory,
                allowed_evidence_root=allowed_evidence_root,
            )
            if quote.mapping_evidence_sha256 != canonical_mapping_sha256(mapping):
                raise CanonicalAccumulatorExecutionError(
                    "source-issued quote mapping ancestry differs from exact mapping"
                )
            quotes.append(quote)
    except (PriceAllError, TypeError, ValueError) as exc:
        raise CanonicalAccumulatorExecutionError(
            "source-issued SportyBet quote derivation failed closed"
        ) from exc
    return tuple(sorted(quotes, key=_quote_sha))


@dataclass(frozen=True, init=False)
class CanonicalAccumulatorFixtureInput:
    """One source-bound fixture ready for the existing Phase 9 optimizer."""

    intelligence_snapshot: FixtureIntelligenceSnapshot
    fixture_state: FixtureStateV2Snapshot
    optimizer_input: AccumulatorFixtureInput
    mapping: SportyBetReviewedCanonicalMarketMapping
    source_bundle: reconciliation_receipt.FullUtcReconciliationSourceBundle
    evidence_directory: Path
    allowed_evidence_root: Path
    receipt_directory: Path
    repository_root: Path
    source_snapshot_sha256: str
    mapping_sha256: str
    source_native_inventory_sha256: str

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise CanonicalAccumulatorExecutionError(
            "canonical fixture input is builder-only; use from_source_replayed_receipt()"
        )

    @classmethod
    def from_source_replayed_receipt(
        cls,
        *,
        intelligence_snapshot: FixtureIntelligenceSnapshot,
        phase6_inputs: tuple[CanonicalPhase6CandidateInput, ...],
        mapping: SportyBetReviewedCanonicalMarketMapping,
        evidence_directory: Path,
        allowed_evidence_root: Path,
        receipt_directory: Path,
        source_bundle: reconciliation_receipt.FullUtcReconciliationSourceBundle,
        repository_root: Path,
    ) -> "CanonicalAccumulatorFixtureInput":
        if type(intelligence_snapshot) is not FixtureIntelligenceSnapshot:
            raise CanonicalAccumulatorExecutionError(
                "intelligence_snapshot must be exact FixtureIntelligenceSnapshot"
            )
        if type(phase6_inputs) is not tuple:
            raise CanonicalAccumulatorExecutionError(
                "phase6_inputs must be an exact tuple"
            )
        if type(mapping) is not SportyBetReviewedCanonicalMarketMapping:
            raise CanonicalAccumulatorExecutionError(
                "mapping must be exact reviewed SportyBet canonical mapping"
            )
        if type(source_bundle) is not reconciliation_receipt.FullUtcReconciliationSourceBundle:
            raise CanonicalAccumulatorExecutionError(
                "source_bundle must be exact full-UTC reconciliation source bundle"
            )
        for label, value in (
            ("evidence_directory", evidence_directory),
            ("allowed_evidence_root", allowed_evidence_root),
            ("receipt_directory", receipt_directory),
            ("repository_root", repository_root),
        ):
            if not isinstance(value, Path):
                raise CanonicalAccumulatorExecutionError(f"{label} must be a Path")

        inventory = _inventory_from_source(evidence_directory, allowed_evidence_root)
        if type(source_bundle.event_inventory) is not source_inventory.SportyBetUserControlledNativeInventory:
            raise CanonicalAccumulatorExecutionError(
                "full-UTC source bundle must carry exact reviewed native inventory"
            )
        if not _same_dict(source_bundle.event_inventory.to_dict(), inventory.to_dict()):
            raise CanonicalAccumulatorExecutionError(
                "full-UTC source bundle inventory differs from current evidence replay"
            )
        inventory_sha = source_inventory.inventory_sha256(inventory)
        if inventory_sha != mapping.source_native_inventory_sha256:
            raise CanonicalAccumulatorExecutionError(
                "reviewed mapping does not bind current exact native inventory"
            )
        if (
            mapping.sportybet_event_id != inventory.source_event_id
            or mapping.sportybet_sport_id != inventory.source_sport_id
            or mapping.source_event_evidence_id != inventory.source_evidence_id
        ):
            raise CanonicalAccumulatorExecutionError(
                "mapping/source inventory event ancestry differs"
            )

        try:
            fixture_state = build_fixture_state_v2_snapshot(intelligence_snapshot)
        except (TypeError, ValueError) as exc:
            raise CanonicalAccumulatorExecutionError(
                "Fixture State v2 could not be built from exact intelligence snapshot"
            ) from exc

        candidates = tuple(_reissue_phase6_candidate(item) for item in phase6_inputs)
        if len({item.candidate_id for item in candidates}) != len(candidates):
            raise CanonicalAccumulatorExecutionError(
                "re-issued Phase 6 candidate identities must be unique"
            )
        if any(
            item.fixture_id != intelligence_snapshot.fixture_identifier
            or item.fixture_id != mapping.matched_fotmob_fixture_id
            or item.sportybet_event_id != mapping.sportybet_event_id
            for item in candidates
        ):
            raise CanonicalAccumulatorExecutionError(
                "Phase 6 candidate identity does not bind the exact fixture/mapping"
            )
        if (
            fixture_state.fixture_identifier != intelligence_snapshot.fixture_identifier
            or fixture_state.kickoff != intelligence_snapshot.kickoff
        ):
            raise CanonicalAccumulatorExecutionError(
                "Fixture State identity does not bind the exact intelligence snapshot"
            )

        for candidate in candidates:
            _mapped_for_candidate(mapping, candidate)
        quotes = _derive_quotes(
            mapping,
            inventory,
            evidence_directory=evidence_directory,
            allowed_evidence_root=allowed_evidence_root,
        )
        try:
            optimizer_input = AccumulatorFixtureInput.from_source_replayed_receipt(
                candidates=candidates,
                quotes=quotes,
                fixture_state=fixture_state,
                receipt_directory=receipt_directory,
                source_bundle=source_bundle,
                repository_root=repository_root,
            )
        except (AccumulatorOptimizerError, TypeError, ValueError) as exc:
            raise CanonicalAccumulatorExecutionError(
                "Phase 9 fixture input source replay failed"
            ) from exc

        exact_reconciliation_sha = _sha_reconciliation(optimizer_input.reconciliation)
        if mapping.source_reconciliation_receipt_sha256 != exact_reconciliation_sha:
            raise CanonicalAccumulatorExecutionError(
                "reviewed mapping does not bind exact source-replayed reconciliation"
            )
        source_snapshot_sha = sha256_bytes(canonical_snapshot_bytes(intelligence_snapshot))
        mapping_sha = canonical_mapping_sha256(mapping)
        result = object.__new__(cls)
        values = {
            "intelligence_snapshot": intelligence_snapshot,
            "fixture_state": fixture_state,
            "optimizer_input": optimizer_input,
            "mapping": mapping,
            "source_bundle": source_bundle,
            "evidence_directory": evidence_directory,
            "allowed_evidence_root": allowed_evidence_root,
            "receipt_directory": receipt_directory,
            "repository_root": repository_root,
            "source_snapshot_sha256": source_snapshot_sha,
            "mapping_sha256": mapping_sha,
            "source_native_inventory_sha256": inventory_sha,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result


def _sha_reconciliation(
    value: reconciliation.SportyBetFotMobFullUtcReconciliation,
) -> str:
    return hashlib.sha256(reconciliation.canonical_reconciliation_bytes(value)).hexdigest()


@dataclass(frozen=True)
class SemanticIntentRecord:
    """Auditable semantic adapter output; native IDs are intentionally absent."""

    leg_id: str
    fixture_id: str
    router_decision_sha256: str
    optimizer_id: str
    reconciliation_sha256: str
    mapping_sha256: str
    source_native_inventory_sha256: str
    source_snapshot_sha256: str
    evidence_snapshot_sha256: str
    provider_event_id: str
    expected_home_team: str
    expected_away_team: str
    provider_market_name: str
    provider_outcome_name: str
    provider_specifier: str | None
    quote_identity_sha256: str
    expected_decimal_odds: float

    def to_bridge_intent(self) -> dict[str, Any]:
        """Return only fields accepted by the semantic SportyBet gate."""
        result: dict[str, Any] = {
            "eventId": self.provider_event_id,
            "homeTeamName": self.expected_home_team,
            "awayTeamName": self.expected_away_team,
            "marketName": self.provider_market_name,
            "outcomeName": self.provider_outcome_name,
            "specifier": self.provider_specifier,
        }
        # Native marketId/outcomeId and caller odds are deliberately not
        # present.  The semantic bridge derives those from the live event.
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "leg_id": self.leg_id,
            "fixture_id": self.fixture_id,
            "router_decision_sha256": self.router_decision_sha256,
            "optimizer_id": self.optimizer_id,
            "reconciliation_sha256": self.reconciliation_sha256,
            "mapping_sha256": self.mapping_sha256,
            "source_native_inventory_sha256": self.source_native_inventory_sha256,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "evidence_snapshot_sha256": self.evidence_snapshot_sha256,
            "provider_event_id": self.provider_event_id,
            "expected_home_team": self.expected_home_team,
            "expected_away_team": self.expected_away_team,
            "provider_market_name": self.provider_market_name,
            "provider_outcome_name": self.provider_outcome_name,
            "provider_specifier": self.provider_specifier,
            "quote_identity_sha256": self.quote_identity_sha256,
            "expected_decimal_odds": self.expected_decimal_odds,
            "bridge_intent": self.to_bridge_intent(),
        }


def _wrapper_by_fixture(
    fixture_inputs: Sequence[CanonicalAccumulatorFixtureInput],
) -> dict[str, CanonicalAccumulatorFixtureInput]:
    result: dict[str, CanonicalAccumulatorFixtureInput] = {}
    for item in fixture_inputs:
        if type(item) is not CanonicalAccumulatorFixtureInput:
            raise CanonicalAccumulatorExecutionError(
                "fixture_inputs must contain exact canonical fixture inputs"
            )
        key = item.fixture_state.fixture_identifier
        if key in result:
            raise CanonicalAccumulatorExecutionError("duplicate canonical fixture identity")
        result[key] = item
    return result


def _selected_opportunity_or_fail(leg: PortfolioLeg, audit: Any) -> Any:
    if audit.router_decision_sha256 != leg.router_decision_sha256:
        raise CanonicalAccumulatorExecutionError(
            "Portfolio leg Router ancestry does not match its route audit"
        )
    decision = audit.router_decision
    if decision.canonical_sha256 != leg.router_decision_sha256:
        raise CanonicalAccumulatorExecutionError(
            "Router decision identity is not the exact selected-leg identity"
        )
    if decision.decision_status.value != "SELECTED" or not audit.portfolio_admitted:
        raise CanonicalAccumulatorExecutionError(
            "Optimizer leg is not backed by an admitted Router selection"
        )
    opportunity = decision.selected_opportunity
    if opportunity is None or opportunity.opportunity_id != leg.selected_opportunity_id:
        raise CanonicalAccumulatorExecutionError(
            "Optimizer leg selected opportunity ancestry drifted"
        )
    if (
        opportunity.fixture_id != leg.fixture_id
        or opportunity.sportybet_event_id != leg.sportybet_event_id
        or opportunity.market_id is not leg.market_id
        or opportunity.outcome_id is not leg.outcome_id
        or opportunity.line != leg.line
        or opportunity.quote_identity_sha256 != leg.quote_identity_sha256
    ):
        raise CanonicalAccumulatorExecutionError(
            "Router opportunity semantics differ from Optimizer leg"
        )
    return opportunity


def _quote_by_identity(
    item: CanonicalAccumulatorFixtureInput,
    quote_identity_sha256: str,
) -> SportyBetExactQuote:
    matches = tuple(
        quote
        for quote in item.optimizer_input.quotes
        if _quote_sha(quote) == quote_identity_sha256
    )
    if len(matches) != 1:
        raise CanonicalAccumulatorExecutionError(
            "Optimizer leg quote identity is absent or ambiguous in source-issued quotes"
        )
    return matches[0]


def _selected_quote(
    item: CanonicalAccumulatorFixtureInput,
    leg: PortfolioLeg,
) -> SportyBetExactQuote:
    quote = _quote_by_identity(item, leg.quote_identity_sha256)
    if (
        quote.fixture_id != leg.fixture_id
        or quote.event_id != leg.sportybet_event_id
        or quote.canonical_market_id is not leg.market_id
        or quote.canonical_outcome_id is not leg.outcome_id
        or quote.canonical_line != leg.line
        or quote.source != "SportyBet"
        or quote.provider_snapshot_id is not None
        or quote.source_native_inventory_sha256 != item.source_native_inventory_sha256
        or quote.fixture_reconciliation_sha256 != item.optimizer_input.reconciliation_receipt_sha256
        or quote.mapping_evidence_sha256 != item.mapping_sha256
    ):
        raise CanonicalAccumulatorExecutionError(
            "Optimizer leg quote does not bind exact current provider ancestry"
        )
    return quote


def adapt_optimization_to_semantic_intents(
    optimization: AccumulatorOptimization,
    fixture_inputs: tuple[CanonicalAccumulatorFixtureInput, ...],
) -> tuple[SemanticIntentRecord, ...]:
    """Adapt only final Router/Optimizer-qualified legs to semantic intent."""
    if type(optimization) is not AccumulatorOptimization:
        raise CanonicalAccumulatorExecutionError("optimization must be exact Phase 9 result")
    if type(fixture_inputs) is not tuple:
        raise CanonicalAccumulatorExecutionError("fixture_inputs must be an exact tuple")
    wrappers = _wrapper_by_fixture(fixture_inputs)
    audits = {audit.fixture_id: audit for audit in optimization.route_audits}
    if len(audits) != len(optimization.route_audits):
        raise CanonicalAccumulatorExecutionError("duplicate Router route audit fixture")
    if len(optimization.selected_legs) != len(set(leg.fixture_id for leg in optimization.selected_legs)):
        raise CanonicalAccumulatorExecutionError("Optimizer selected duplicate fixture")

    records: list[SemanticIntentRecord] = []
    for leg in optimization.selected_legs:
        item = wrappers.get(leg.fixture_id)
        audit = audits.get(leg.fixture_id)
        if item is None or audit is None:
            raise CanonicalAccumulatorExecutionError(
                "Optimizer leg has no exact source fixture or Router audit"
            )
        opportunity = _selected_opportunity_or_fail(leg, audit)
        quote = _selected_quote(item, leg)
        candidate_ids = {
            variant.candidate_id for variant in opportunity.variants
        }
        candidate_matches = tuple(
            candidate
            for candidate in item.optimizer_input.candidates
            if candidate.candidate_id in candidate_ids
            if candidate.market_id is leg.market_id
            and candidate.outcome_id is leg.outcome_id
            and candidate.line == leg.line
        )
        if not candidate_matches:
            raise CanonicalAccumulatorExecutionError(
                "Optimizer leg has no exact Phase 6 candidate ancestry"
            )
        mapped = _mapped_for_candidate(item.mapping, candidate_matches[0])
        if (
            mapped.event_id != leg.sportybet_event_id
            or not mapped.provider_market_name
            or not mapped.provider_selection_label
            or mapped.bookmaker_equivalence_authorized is not True
            or mapped.canonical_market_mapping_authorized is not True
            or mapped.fresh_price_authorized is not False
        ):
            raise CanonicalAccumulatorExecutionError(
                "final leg lacks one reviewed provider semantic mapping"
            )
        if quote.provider_market_id != mapped.provider_market_id or quote.provider_outcome_id != mapped.provider_outcome_id:
            raise CanonicalAccumulatorExecutionError(
                "selected quote/provider mapping native identity drifted"
            )
        if opportunity.quote_identity_sha256 != _quote_sha(quote):
            raise CanonicalAccumulatorExecutionError(
                "selected opportunity quote ancestry differs from source-issued quote"
            )
        reconciliation_value = item.optimizer_input.reconciliation
        records.append(
            SemanticIntentRecord(
                leg_id=leg.leg_id,
                fixture_id=leg.fixture_id,
                router_decision_sha256=leg.router_decision_sha256,
                optimizer_id=optimization.optimization_id,
                reconciliation_sha256=item.optimizer_input.reconciliation_receipt_sha256,
                mapping_sha256=item.mapping_sha256,
                source_native_inventory_sha256=item.source_native_inventory_sha256,
                source_snapshot_sha256=item.source_snapshot_sha256,
                evidence_snapshot_sha256=quote.evidence_snapshot_sha256,
                provider_event_id=leg.sportybet_event_id,
                expected_home_team=reconciliation_value.home_display,
                expected_away_team=reconciliation_value.away_display,
                provider_market_name=mapped.provider_market_name,
                provider_outcome_name=mapped.provider_selection_label,
                provider_specifier=mapped.provider_specifier,
                quote_identity_sha256=_quote_sha(quote),
                expected_decimal_odds=quote.decimal_odds,
            )
        )
    return tuple(sorted(records, key=lambda item: (item.fixture_id, item.leg_id)))


def _replay_and_verify_fixture_sources(
    item: CanonicalAccumulatorFixtureInput,
    *,
    now: datetime,
    required_quote_identity_sha256: str,
    minimum_lead_seconds: int,
) -> None:
    """Replay all source bytes immediately before semantic provider execution."""
    current_inventory = _inventory_from_source(
        item.evidence_directory,
        item.allowed_evidence_root,
    )
    current_inventory_sha = source_inventory.inventory_sha256(current_inventory)
    if current_inventory_sha != item.source_native_inventory_sha256:
        raise CanonicalAccumulatorExecutionError(
            "SportyBet source evidence changed after Phase 9 qualification"
        )
    if not _same_dict(current_inventory.to_dict(), item.source_bundle.event_inventory.to_dict()):
        raise CanonicalAccumulatorExecutionError(
            "current SportyBet evidence differs from full-UTC source bundle"
        )
    try:
        rebuilt = reconciliation_receipt.verify_reconciliation_receipt_directory(
            item.receipt_directory,
            source_bundle=item.source_bundle,
            repository_root=item.repository_root,
        )
    except reconciliation_receipt.SportyBetFotMobFullUtcReconciliationReceiptError as exc:
        raise CanonicalAccumulatorExecutionError(
            "full-UTC reconciliation replay failed immediately before execution"
        ) from exc
    rebuilt_sha = _sha_reconciliation(rebuilt)
    if rebuilt_sha != item.optimizer_input.reconciliation_receipt_sha256:
        raise CanonicalAccumulatorExecutionError(
            "full-UTC reconciliation changed after Phase 9 qualification"
        )
    if (
        rebuilt.disposition
        is not reconciliation.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
        or rebuilt.fixture_reconciliation_authorized is not True
        or rebuilt.matched_fixture is None
        or rebuilt.sportybet_event_id != item.mapping.sportybet_event_id
        or rebuilt.matched_fixture.source_fixture_identifier != item.fixture_state.fixture_identifier
    ):
        raise CanonicalAccumulatorExecutionError(
            "current reconciliation is not the exact authorized fixture exposure"
        )
    if now + timedelta(seconds=minimum_lead_seconds) >= rebuilt.sportybet_kickoff_utc:
        raise CanonicalAccumulatorExecutionError(
            "selected fixture is live or too close to kickoff for safe execution"
        )
    current_quotes = _derive_quotes(
        item.mapping,
        current_inventory,
        evidence_directory=item.evidence_directory,
        allowed_evidence_root=item.allowed_evidence_root,
    )
    stored_by_hash = {_quote_sha(quote): quote for quote in item.optimizer_input.quotes}
    current_by_hash = {_quote_sha(quote): quote for quote in current_quotes}
    if set(stored_by_hash) != set(current_by_hash):
        raise CanonicalAccumulatorExecutionError(
            "source-issued SportyBet quote ancestry changed after qualification"
        )
    current_quote = current_by_hash.get(required_quote_identity_sha256)
    if current_quote is None:
        raise CanonicalAccumulatorExecutionError(
            "selected source-issued quote is absent from current evidence replay"
        )
    stored_quote = _quote_by_identity(item, required_quote_identity_sha256)
    if stored_quote.provider_snapshot_id is not None or current_quote.provider_snapshot_id is not None:
        raise CanonicalAccumulatorExecutionError(
            "unproven provider snapshot identity cannot authorize execution"
        )
    age = (now - current_quote.observed_at.astimezone(timezone.utc)).total_seconds()
    if not math.isfinite(age) or age < 0 or age > DEFAULT_MAX_QUOTE_AGE_SECONDS:
        raise CanonicalAccumulatorExecutionError(
            "source-qualified SportyBet evidence is not fresh at execution time"
        )


def _validate_final_freshness_and_bookability_ancestry(
    intents: Sequence[SemanticIntentRecord],
    fixture_inputs: tuple[CanonicalAccumulatorFixtureInput, ...],
    *,
    now: datetime,
    minimum_lead_seconds: int,
) -> None:
    wrappers = _wrapper_by_fixture(fixture_inputs)
    for intent in intents:
        item = wrappers.get(intent.fixture_id)
        if item is None:
            raise CanonicalAccumulatorExecutionError(
                "semantic intent has no source-bound fixture"
            )
        _replay_and_verify_fixture_sources(
            item,
            now=now,
            required_quote_identity_sha256=intent.quote_identity_sha256,
            minimum_lead_seconds=minimum_lead_seconds,
        )
        quote = _quote_by_identity(item, intent.quote_identity_sha256)
        if quote.evidence_snapshot_sha256 != intent.evidence_snapshot_sha256:
            raise CanonicalAccumulatorExecutionError(
                "semantic intent quote evidence identity drifted"
            )
        if not math.isclose(
            quote.decimal_odds,
            intent.expected_decimal_odds,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise CanonicalAccumulatorExecutionError(
                "semantic intent quote price differs from source-issued quote"
            )


def _validate_optimization_ancestry(
    optimization: AccumulatorOptimization,
    fixture_inputs: tuple[CanonicalAccumulatorFixtureInput, ...],
    *,
    contract_identities: Mapping[str, str],
) -> tuple[int, int, tuple[str, ...]]:
    wrappers = _wrapper_by_fixture(fixture_inputs)
    audit_fixture_ids = [audit.fixture_id for audit in optimization.route_audits]
    if (
        len(audit_fixture_ids) != len(wrappers)
        or len(audit_fixture_ids) != len(set(audit_fixture_ids))
        or set(audit_fixture_ids) != set(wrappers)
    ):
        raise CanonicalAccumulatorExecutionError(
            "Router audit count/fixture ancestry does not equal canonical fixture universe"
        )
    if optimization.accumulator_optimizer_contract_sha256 != contract_identities[
        "accumulator_optimizer_contract_sha256"
    ]:
        raise CanonicalAccumulatorExecutionError(
            "Optimizer result contract identity drifted"
        )
    if optimization.market_router_contract_sha256 != contract_identities[
        "market_router_contract_sha256"
    ]:
        raise CanonicalAccumulatorExecutionError("Optimizer Router dependency drifted")
    if optimization.requested_target_size < 1:
        raise CanonicalAccumulatorExecutionError("Optimizer target identity is invalid")
    if len(optimization.selected_legs) > optimization.requested_target_size:
        raise CanonicalAccumulatorExecutionError(
            "Optimizer qualified leg count exceeds its requested target"
        )
    selected_fixture_ids: set[str] = set()
    router_ids: list[str] = []
    for leg in optimization.selected_legs:
        if leg.fixture_id in selected_fixture_ids:
            raise CanonicalAccumulatorExecutionError("Optimizer selected duplicate fixture")
        selected_fixture_ids.add(leg.fixture_id)
        item = wrappers.get(leg.fixture_id)
        if item is None:
            raise CanonicalAccumulatorExecutionError(
                "Optimizer selected fixture is outside canonical source universe"
            )
        if leg.reconciliation_sha256 != item.optimizer_input.reconciliation_receipt_sha256:
            raise CanonicalAccumulatorExecutionError(
                "Optimizer leg reconciliation ancestry drifted"
            )
        if leg.sportybet_event_id != item.mapping.sportybet_event_id:
            raise CanonicalAccumulatorExecutionError("Optimizer provider event identity drifted")
        audit = next(
            (row for row in optimization.route_audits if row.fixture_id == leg.fixture_id),
            None,
        )
        if audit is None:
            raise CanonicalAccumulatorExecutionError("Optimizer leg Router audit is absent")
        _selected_opportunity_or_fail(leg, audit)
        _selected_quote(item, leg)
        router_ids.append(leg.router_decision_sha256)
    # The Router may qualify a larger admitted pool than the Optimizer can
    # place under its joint exposure caps.  The count invariant is therefore
    # about the exact legs that crossed the Optimizer boundary, not every
    # Router-qualified reserve leg.  Each selected leg was already checked
    # above against its own admitted Router audit.
    route_selected_count = len(optimization.selected_legs)
    router_pool_count = sum(
        1
        for audit in optimization.route_audits
        if audit.router_decision_status == "SELECTED"
        and audit.selected_opportunity_id is not None
    )
    if route_selected_count != len(optimization.selected_legs):
        raise CanonicalAccumulatorExecutionError(
            "Router selected leg count does not equal Optimizer qualified leg count"
        )
    if optimization.shortfall != max(
        0, optimization.requested_target_size - len(optimization.selected_legs)
    ):
        raise CanonicalAccumulatorExecutionError("Optimizer shortfall identity drifted")
    return route_selected_count, router_pool_count, tuple(sorted(router_ids))


@dataclass(frozen=True)
class CanonicalAccumulatorExecution:
    contract_sha256: str
    evaluation_time: datetime
    requested_fold_count: int
    final_qualified_fold_count: int
    status: str
    shortfall: int
    router_selected_leg_count: int
    router_selection_pool_count: int
    optimizer_qualified_leg_count: int
    semantic_intent_count: int
    sportybet_create_selection_count: int
    sportybet_reload_selection_count: int
    selected_legs: tuple[Mapping[str, Any], ...]
    router_decision_ids: tuple[str, ...]
    optimizer_id: str
    optimizer_contract_sha256: str
    fixture_ancestry: tuple[Mapping[str, Any], ...]
    semantic_receipt: Mapping[str, Any] | None
    share_code: str | None
    share_url: str | None
    combined_odds: str | float | None
    wager_placed: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "athena-canonical-accumulator-sportybet-execution-v1",
            "contract_sha256": self.contract_sha256,
            "evaluation_time": _iso(self.evaluation_time),
            "requested_fold_count": self.requested_fold_count,
            "final_qualified_fold_count": self.final_qualified_fold_count,
            "status": self.status,
            "shortfall": self.shortfall,
            "router_selected_leg_count": self.router_selected_leg_count,
            "router_selection_pool_count": self.router_selection_pool_count,
            "optimizer_qualified_leg_count": self.optimizer_qualified_leg_count,
            "semantic_intent_count": self.semantic_intent_count,
            "sportybet_create_selection_count": self.sportybet_create_selection_count,
            "sportybet_reload_selection_count": self.sportybet_reload_selection_count,
            "selected_legs": [dict(item) for item in self.selected_legs],
            "router_decision_ids": list(self.router_decision_ids),
            "optimizer_id": self.optimizer_id,
            "optimizer_contract_sha256": self.optimizer_contract_sha256,
            "fixture_ancestry": [dict(item) for item in self.fixture_ancestry],
            "semantic_receipt": (
                None if self.semantic_receipt is None else dict(self.semantic_receipt)
            ),
            "shareCode": self.share_code,
            "shareURL": self.share_url,
            "combined_odds": self.combined_odds,
            "wager_placed": False,
            "authority_flags": dict(AUTHORITY_FLAGS),
            "error": self.error,
        }

    @property
    def canonical_sha256(self) -> str:
        return _sha(self.to_dict())


def _fixture_ancestry(
    item: CanonicalAccumulatorFixtureInput,
    *,
    optimizer: AccumulatorOptimization,
) -> dict[str, Any]:
    return {
        "fixture_id": item.fixture_state.fixture_identifier,
        "intelligence_snapshot_sha256": item.source_snapshot_sha256,
        "fixture_state_sha256": item.fixture_state.canonical_sha256,
        "fixture_state_source_snapshot_sha256": item.fixture_state.source_snapshot_sha256,
        "fixture_state_field_evidence": [
            {
                "field_id": resolution.field_id.value,
                "status": resolution.status.value,
                "evidence": [fact.evidence_sha256 for fact in resolution.evidence],
            }
            for resolution in item.fixture_state.fields
            if resolution.evidence
        ],
        "source_reconciliation_sha256": item.optimizer_input.reconciliation_receipt_sha256,
        "source_reconciliation_identifier": item.optimizer_input.reconciliation_receipt_identifier,
        "source_native_inventory_sha256": item.source_native_inventory_sha256,
        "source_event_evidence_id": item.mapping.source_event_evidence_id,
        "source_evidence_manifest_sha256": sorted(
            {
                quote.source_evidence_manifest_sha256
                for quote in item.optimizer_input.quotes
            }
        ),
        "canonical_mapping_sha256": item.mapping_sha256,
        "candidate_ids": [candidate.candidate_id for candidate in item.optimizer_input.candidates],
        "candidate_ancestry": [
            candidate.to_dict()
            for candidate in sorted(
                item.optimizer_input.candidates,
                key=lambda value: value.candidate_id,
            )
        ],
        "quote_ancestry": [
            quote.to_dict()
            for quote in sorted(
                item.optimizer_input.quotes,
                key=_quote_sha,
            )
        ],
        "quote_identity_sha256": sorted(
            _quote_sha(quote) for quote in item.optimizer_input.quotes
        ),
        "optimizer_id": optimizer.optimization_id,
    }


def _selected_leg_payload(
    leg: PortfolioLeg,
    intent: SemanticIntentRecord,
) -> dict[str, Any]:
    return {
        "optimizer_leg": leg.to_dict(),
        "semantic_intent": intent.to_dict(),
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    if not isinstance(path, Path) or not path.name:
        raise CanonicalAccumulatorExecutionError("artifact path is invalid")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_bytes(dict(payload)) + b"\n"
    fd, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return path


def write_canonical_execution_artifact(
    result: CanonicalAccumulatorExecution,
    output_dir: Path,
    *,
    filename: str = "canonical-accumulator-execution.json",
) -> Path:
    if type(result) is not CanonicalAccumulatorExecution:
        raise CanonicalAccumulatorExecutionError("result must be exact canonical execution result")
    if not isinstance(output_dir, Path) or not filename or Path(filename).name != filename:
        raise CanonicalAccumulatorExecutionError("output artifact path is invalid")
    return _atomic_write_json(output_dir / filename, result.to_dict())


def write_canonical_execution_failure_artifact(
    *,
    output_dir: Path,
    contract_sha256: str,
    evaluation_time: datetime,
    requested_fold_count: int,
    error: str,
) -> dict[str, Any]:
    """Persist a safe no-code artifact when the runner fails before a result.

    The artifact contains no provider credentials or raw responses.  It is
    intentionally a separate, explicit failure status rather than a partial
    booking-code receipt.
    """
    payload = {
        "schema": "athena-canonical-accumulator-sportybet-execution-v1",
        "contract_sha256": contract_sha256,
        "evaluation_time": _iso(evaluation_time),
        "requested_fold_count": requested_fold_count,
        "final_qualified_fold_count": 0,
        "status": "NO_CODE_EXECUTION_ERROR",
        "shortfall": requested_fold_count,
        "router_selected_leg_count": 0,
        "router_selection_pool_count": 0,
        "optimizer_qualified_leg_count": 0,
        "semantic_intent_count": 0,
        "sportybet_create_selection_count": 0,
        "sportybet_reload_selection_count": 0,
        "selected_legs": [],
        "router_decision_ids": [],
        "optimizer_id": "",
        "optimizer_contract_sha256": "",
        "fixture_ancestry": [],
        "semantic_receipt": None,
        "shareCode": None,
        "shareURL": None,
        "combined_odds": None,
        "wager_placed": False,
        "authority_flags": dict(AUTHORITY_FLAGS),
        "error": error[:1000],
    }
    _atomic_write_json(output_dir / "canonical-accumulator-execution.json", payload)
    return payload


def execute_canonical_accumulator(
    fixture_inputs: tuple[CanonicalAccumulatorFixtureInput, ...],
    *,
    target_size: int,
    output_dir: Path,
    evaluation_time: datetime | None = None,
    minimum_lead_seconds: int = MINIMUM_LEAD_SECONDS_DEFAULT,
    delay_seconds: float = 0.25,
) -> CanonicalAccumulatorExecution:
    """Run the only reviewed selection-to-SportyBet code path.

    ``evaluation_time`` controls deterministic evaluation in tests and replay;
    it never supplies quote time, provider snapshot identity, odds, or native
    IDs.  Those are re-derived from source evidence and the live semantic gate.
    """
    identities = validate_canonical_execution_contract()
    if type(fixture_inputs) is not tuple:
        raise CanonicalAccumulatorExecutionError("fixture_inputs must be an exact tuple")
    if isinstance(target_size, bool) or not isinstance(target_size, int) or target_size < 1:
        raise CanonicalAccumulatorExecutionError("target_size must be a positive integer")
    now = _utc(evaluation_time or datetime.now(timezone.utc))
    if type(minimum_lead_seconds) is not int or minimum_lead_seconds < 0:
        raise CanonicalAccumulatorExecutionError("minimum_lead_seconds must be non-negative int")
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not math.isfinite(float(delay_seconds)) or delay_seconds < 0:
        raise CanonicalAccumulatorExecutionError("delay_seconds must be finite and non-negative")
    wrappers = _wrapper_by_fixture(fixture_inputs)
    if not wrappers:
        raise CanonicalAccumulatorExecutionError("canonical fixture universe must not be empty")
    try:
        optimization = optimize_accumulator(
            tuple(item.optimizer_input for item in fixture_inputs),
            target_size=target_size,
            evaluation_time=now,
        )
    except (AccumulatorOptimizerError, TypeError, ValueError) as exc:
        raise CanonicalAccumulatorExecutionError(
            "canonical execution could not complete exact Router/Optimizer replay"
        ) from exc

    router_count, router_pool_count, router_ids = _validate_optimization_ancestry(
        optimization,
        fixture_inputs,
        contract_identities=identities,
    )
    ancestry = tuple(
        _fixture_ancestry(item, optimizer=optimization)
        for item in sorted(fixture_inputs, key=lambda value: value.fixture_state.fixture_identifier)
    )
    selected_count = len(optimization.selected_legs)
    if selected_count < target_size:
        result = CanonicalAccumulatorExecution(
            contract_sha256=identities["canonical_execution_contract_sha256"],
            evaluation_time=now,
            requested_fold_count=target_size,
            final_qualified_fold_count=selected_count,
            status="NO_CODE_SHORTFALL",
            shortfall=target_size - selected_count,
            router_selected_leg_count=router_count,
            router_selection_pool_count=router_pool_count,
            optimizer_qualified_leg_count=selected_count,
            semantic_intent_count=0,
            sportybet_create_selection_count=0,
            sportybet_reload_selection_count=0,
            selected_legs=tuple(
                {"optimizer_leg": leg.to_dict()}
                for leg in optimization.selected_legs
            ),
            router_decision_ids=router_ids,
            optimizer_id=optimization.optimization_id,
            optimizer_contract_sha256=optimization.accumulator_optimizer_contract_sha256,
            fixture_ancestry=ancestry,
            semantic_receipt=None,
            share_code=None,
            share_url=None,
            combined_odds=None,
            wager_placed=False,
        )
        write_canonical_execution_artifact(result, output_dir)
        return result

    intents = adapt_optimization_to_semantic_intents(
        optimization,
        fixture_inputs,
    )
    if router_count != selected_count or selected_count != len(intents):
        raise CanonicalAccumulatorExecutionError(
            "Router/Optimizer/semantic-intent count invariant failed"
        )
    # This is the final local freshness/evidence gate.  The semantic bridge
    # then independently fetches current provider events and proves pre-match,
    # active, exact human-readable semantics before deriving native IDs.
    _validate_final_freshness_and_bookability_ancestry(
        intents,
        fixture_inputs,
        now=now,
        minimum_lead_seconds=minimum_lead_seconds,
    )
    try:
        semantic_receipt = semantic_bridge.create_semantic_share_code(
            intents=tuple(intent.to_bridge_intent() for intent in intents),
            output_dir=output_dir / "sportybet",
            minimum_lead_seconds=minimum_lead_seconds,
            delay_seconds=float(delay_seconds),
        )
    except (
        semantic_bridge.SportyBetSemanticShareError,
        semantic_bridge.transport.SportyBetDirectShareError,
        TypeError,
        ValueError,
    ) as exc:
        raise CanonicalAccumulatorExecutionError(
            "semantic SportyBet create/reload gate failed closed"
        ) from exc
    if type(semantic_receipt) is not dict:
        raise CanonicalAccumulatorExecutionError("semantic bridge receipt must be an object")
    expected_count = len(intents)
    for field in (
        "semantic_intent_count",
        "semantic_resolution_count",
        "provider_create_selection_count",
        "provider_reload_selection_count",
    ):
        if semantic_receipt.get(field) != expected_count:
            raise CanonicalAccumulatorExecutionError(
                f"semantic/provider count invariant failed for {field}"
            )
    if semantic_receipt.get("exact_roundtrip_selection_identity_verified") is not True:
        raise CanonicalAccumulatorExecutionError("provider native round-trip was not verified")
    if semantic_receipt.get("semantic_roundtrip_verified") is not True:
        raise CanonicalAccumulatorExecutionError(
            "provider semantic round-trip was not verified"
        )
    if semantic_receipt.get("wager_placed") is not False:
        raise CanonicalAccumulatorExecutionError("wager_placed must remain false")
    verification = semantic_receipt.get("semantic_roundtrip_verification")
    if type(verification) is not list or len(verification) != expected_count:
        raise CanonicalAccumulatorExecutionError(
            "semantic round-trip verification count drifted"
        )
    verified_by_event = {row.get("eventId"): row for row in verification if type(row) is dict}
    if len(verified_by_event) != expected_count:
        raise CanonicalAccumulatorExecutionError(
            "semantic round-trip verification event identities are not unique"
        )
    for intent in intents:
        row = verified_by_event.get(intent.provider_event_id)
        if row is None or row.get("exact_semantic_match") is not True:
            raise CanonicalAccumulatorExecutionError(
                "provider semantic round-trip differs from final semantic intent"
            )
        expected = row.get("expected")
        if type(expected) is not dict:
            raise CanonicalAccumulatorExecutionError(
                "provider semantic round-trip omitted expected semantic row"
            )
        item = wrappers.get(intent.fixture_id)
        if item is None:
            raise CanonicalAccumulatorExecutionError(
                "semantic round-trip fixture is outside canonical source ancestry"
            )
        quote = _quote_by_identity(item, intent.quote_identity_sha256)
        if (
            expected.get("homeTeamName") != intent.expected_home_team
            or expected.get("awayTeamName") != intent.expected_away_team
            or expected.get("marketName") != intent.provider_market_name
            or expected.get("outcomeName") != intent.provider_outcome_name
            or expected.get("specifier") != intent.provider_specifier
            or expected.get("marketId") != quote.provider_market_id
            or expected.get("outcomeId") != quote.provider_outcome_id
        ):
            raise CanonicalAccumulatorExecutionError(
                "provider semantic round-trip expected row differs from adapter intent"
            )
        create = row.get("create")
        reload = row.get("reload")
        if type(create) is not dict or type(reload) is not dict:
            raise CanonicalAccumulatorExecutionError(
                "provider semantic round-trip omitted create/reload rows"
            )
        for label, accepted in (("create", create), ("reload", reload)):
            if (
                accepted.get("eventId") != intent.provider_event_id
                or _semantic_name_key(str(accepted.get("homeTeamName", "")))
                != _semantic_name_key(intent.expected_home_team)
                or _semantic_name_key(str(accepted.get("awayTeamName", "")))
                != _semantic_name_key(intent.expected_away_team)
                or str(accepted.get("marketName", "")).casefold()
                != intent.provider_market_name.casefold()
                or str(accepted.get("outcomeName", "")).casefold()
                != intent.provider_outcome_name.casefold()
                or accepted.get("specifier") != intent.provider_specifier
                or accepted.get("marketId") != quote.provider_market_id
                or accepted.get("outcomeId") != quote.provider_outcome_id
            ):
                raise CanonicalAccumulatorExecutionError(
                    f"provider {label} round-trip semantics differ from source-bound intent"
                )
            try:
                accepted_odds = float(accepted["odds"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CanonicalAccumulatorExecutionError(
                    f"provider {label} round-trip odds are invalid"
                ) from exc
            if not math.isfinite(accepted_odds) or not math.isclose(
                accepted_odds,
                intent.expected_decimal_odds,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise CanonicalAccumulatorExecutionError(
                    f"provider {label} round-trip odds differ from source quote"
                )
    if not isinstance(semantic_receipt.get("shareCode"), str) or not isinstance(semantic_receipt.get("shareURL"), str):
        raise CanonicalAccumulatorExecutionError("semantic bridge did not return a verified share code")
    intents_by_leg_id = {intent.leg_id: intent for intent in intents}
    if len(intents_by_leg_id) != len(intents) or set(intents_by_leg_id) != {
        leg.leg_id for leg in optimization.selected_legs
    }:
        raise CanonicalAccumulatorExecutionError(
            "semantic intent leg identities differ from Optimizer selected legs"
        )
    selected_payload = tuple(
        _selected_leg_payload(leg, intents_by_leg_id[leg.leg_id])
        for leg in optimization.selected_legs
    )
    result = CanonicalAccumulatorExecution(
        contract_sha256=identities["canonical_execution_contract_sha256"],
        evaluation_time=now,
        requested_fold_count=target_size,
        final_qualified_fold_count=selected_count,
        status="CODE_VERIFIED",
        shortfall=0,
        router_selected_leg_count=router_count,
        router_selection_pool_count=router_pool_count,
        optimizer_qualified_leg_count=selected_count,
        semantic_intent_count=expected_count,
        sportybet_create_selection_count=semantic_receipt[
            "provider_create_selection_count"
        ],
        sportybet_reload_selection_count=semantic_receipt[
            "provider_reload_selection_count"
        ],
        selected_legs=selected_payload,
        router_decision_ids=router_ids,
        optimizer_id=optimization.optimization_id,
        optimizer_contract_sha256=optimization.accumulator_optimizer_contract_sha256,
        fixture_ancestry=ancestry,
        semantic_receipt=semantic_receipt,
        share_code=semantic_receipt["shareCode"],
        share_url=semantic_receipt["shareURL"],
        combined_odds=semantic_receipt.get("combined_odds"),
        wager_placed=False,
    )
    write_canonical_execution_artifact(result, output_dir)
    return result


__all__ = [name for name in globals() if not name.startswith("_")]
