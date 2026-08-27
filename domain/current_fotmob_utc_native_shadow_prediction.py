"""Compose PR243 current fixture identity with the reviewed UTC-native shadow path.

This is a research/replay boundary only. It replays the exact transparent
`/api/data/matches` response behind a current PR243 bootstrap, re-runs PR243,
reconstructs UTC-native history from the exact PR119 bootstrap bytes plus the
reviewed fresh settlements supplied to this call, and delegates all feature/xG
construction to the existing PR149 fresh-holdout implementation.

Important: this module does not prove that the supplied fresh-settlement tuple is
the complete active PR151 durable history prefix. Therefore a derived row is a
deterministic shadow replay of the supplied reviewed inputs, not a claim that it
is the complete current campaign state. The next reviewed boundary must bind an
exact cumulative PR151 success archive + canonical tick receipt and prove the
complete committed fresh-history prefix before current-shadow completeness can
be claimed.

Provider scalar form/Elo/fatigue fields are never treated as successor inputs.
No score matrix, market probability, Phase 6 candidate, price, selection,
SportyBet execution, or BET authority is granted here.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

from domain.current_fotmob_fixture_review_policy import (
    POLICY_ID as PR243_POLICY_ID,
    build_current_fotmob_fixture_review_policy_result,
)
from domain.fotmob_data_matches_capture import (
    FotMobDataMatchesCaptureManifest,
    sha256_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import (
    canonical_fotmob_fixture_candidate_review_bundle_bytes,
)
from domain.fotmob_fixture_candidates import (
    build_fotmob_fixture_candidate_bundle,
    sha256_fotmob_fixture_candidate_bundle,
)
from domain.reviewed_fixture_intelligence_bootstrap import (
    ReviewedFixtureIntelligenceBootstrap,
    canonical_reviewed_fixture_intelligence_bootstrap_bytes,
)
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-utc-native-shadow-prediction-v1"
STATUS_REPLAYED = "CURRENT_REVIEWED_FOTMOB_UTC_NATIVE_SHADOW_REPLAY_DERIVED"
# Kept as a compatibility alias for callers that imported the original symbol.
# The value itself no longer claims that current-history completeness is ready.
STATUS_READY = STATUS_REPLAYED
NEXT_REQUIRED_BOUNDARY = "CURRENT_DURABLE_FRESH_HISTORY_PREFIX_BINDING_REQUIRED"

SEALED_COMPLETE_CASE = "SEALED_COMPLETE_CASE"
MISSING_REVIEWED_FEATURES = "MISSING_REVIEWED_FEATURES"
OUTSIDE_REVIEWED_SEAL_WINDOW = "OUTSIDE_REVIEWED_SEAL_WINDOW"
_DISPOSITIONS = frozenset(
    {SEALED_COMPLETE_CASE, MISSING_REVIEWED_FEATURES, OUTSIDE_REVIEWED_SEAL_WINDOW}
)

_RESEARCH_EVIDENCE_STATE = {
    "reviewed_current_fixture_identity": True,
    "supplied_reviewed_history_inputs_replayed": True,
    "utc_native_research_feature_construction": True,
    "shadow_expected_goals_rates": True,
    "complete_current_fresh_history_prefix": False,
}
_DOWNSTREAM_AUTHORITY_KEYS = frozenset(
    {
        "production_model",
        "score_matrix",
        "probability",
        "phase6",
        "pricing",
        "selection",
        "sportybet_execution",
        "bet",
    }
)


class CurrentUtcNativeShadowPredictionError(ValueError):
    """Raised when exact reviewed replay ancestry cannot be preserved."""


def _error(message: str) -> CurrentUtcNativeShadowPredictionError:
    return CurrentUtcNativeShadowPredictionError(message)


def _utc(value: Any, label: str) -> dt.datetime:
    if (
        not isinstance(value, dt.datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise _error(f"{label} must be timezone-aware datetime")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise _error(f"{label} must be exact lowercase SHA-256")
    return value


def _source_id(fixture_identifier: str) -> int:
    if (
        type(fixture_identifier) is not str
        or not fixture_identifier.startswith("FOTMOB:")
    ):
        raise _error("fixture identity escaped exact FOTMOB source scope")
    raw = fixture_identifier.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) < 1:
        raise _error("fixture identity has invalid FotMob source id")
    return int(raw)


def _research_evidence() -> Mapping[str, bool]:
    return types.MappingProxyType(dict(_RESEARCH_EVIDENCE_STATE))


def _downstream_authority() -> Mapping[str, bool]:
    return types.MappingProxyType(
        {key: False for key in sorted(_DOWNSTREAM_AUTHORITY_KEYS)}
    )


def _validate_boolean_map(
    value: Any,
    *,
    expected: Mapping[str, bool],
    label: str,
) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise _error(f"{label} keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not expected[key]:
            raise _error(f"{label}[{key!r}] changed reviewed state")
    return types.MappingProxyType(dict(expected))


def _canonical(payload: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionSourceBundle:
    """Exact supplied inputs needed to re-prove every detached replay claim.

    `reviewed_fresh_settlements` is validated as reviewed PR149 settlement
    objects, but this object deliberately does not claim that the tuple is the
    complete active PR151 durable settlement prefix.
    """

    current_bootstrap: ReviewedFixtureIntelligenceBootstrap
    source_raw_json: bytes
    source_manifest: FotMobDataMatchesCaptureManifest
    legacy_bootstrap_projection_raw: bytes
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...]

    def __post_init__(self) -> None:
        if type(self.current_bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
            raise _error(
                "current_bootstrap must be exact ReviewedFixtureIntelligenceBootstrap"
            )
        try:
            bootstrap = dataclasses.replace(self.current_bootstrap)
            canonical_reviewed_fixture_intelligence_bootstrap_bytes(bootstrap)
        except Exception as exc:
            raise _error("current bootstrap failed exact reviewed revalidation") from exc
        if type(self.source_raw_json) is not bytes or not self.source_raw_json:
            raise _error("source_raw_json must be non-empty exact bytes")
        if type(self.source_manifest) is not FotMobDataMatchesCaptureManifest:
            raise _error("source_manifest must be exact FotMobDataMatchesCaptureManifest")
        manifest = dataclasses.replace(self.source_manifest)
        if manifest.network_acquisition_performed is not True:
            raise _error("source manifest must prove transparent network acquisition")
        if hashlib.sha256(self.source_raw_json).hexdigest() != manifest.raw_sha256:
            raise _error("source raw SHA differs from reviewed manifest")
        if type(self.legacy_bootstrap_projection_raw) is not bytes:
            raise _error("legacy bootstrap projection must be exact bytes")
        if type(self.reviewed_fresh_settlements) is not tuple:
            raise _error("reviewed fresh settlements must be immutable tuple")

        seen: set[str] = set()
        settlements: list[fresh.SettledFreshPrediction] = []
        for settlement in self.reviewed_fresh_settlements:
            if type(settlement) is not fresh.SettledFreshPrediction:
                raise _error("fresh settlement tuple contains invalid object")
            rebuilt = dataclasses.replace(settlement)
            prediction_sha = fresh.sha256_sealed_fresh_prediction(rebuilt.prediction)
            if prediction_sha in seen:
                raise _error("fresh settlement tuple contains duplicate prediction")
            seen.add(prediction_sha)
            settlements.append(rebuilt)
        try:
            fresh.build_fresh_history_ledger(self.legacy_bootstrap_projection_raw)
        except Exception as exc:
            raise _error("exact PR119 bootstrap failed reviewed replay") from exc

        object.__setattr__(self, "current_bootstrap", bootstrap)
        object.__setattr__(self, "source_manifest", manifest)
        object.__setattr__(self, "reviewed_fresh_settlements", tuple(settlements))

    @property
    def current_bootstrap_sha256(self) -> str:
        return hashlib.sha256(
            canonical_reviewed_fixture_intelligence_bootstrap_bytes(
                self.current_bootstrap
            )
        ).hexdigest()

    @property
    def source_manifest_sha256(self) -> str:
        return sha256_data_matches_capture_manifest(self.source_manifest)

    @property
    def source_raw_sha256(self) -> str:
        return self.source_manifest.raw_sha256

    @property
    def legacy_bootstrap_sha256(self) -> str:
        return hashlib.sha256(self.legacy_bootstrap_projection_raw).hexdigest()


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionRow:
    fixture_identifier: str
    fixture: fresh.QualifiedCaptureFixture
    disposition: str
    missing_feature_ids: tuple[str, ...]
    sealed_prediction: fresh.SealedFreshPrediction | None
    sealed_prediction_sha256: str | None

    def __post_init__(self) -> None:
        source_id = _source_id(self.fixture_identifier)
        if type(self.fixture) is not fresh.QualifiedCaptureFixture:
            raise _error("row fixture must be exact QualifiedCaptureFixture")
        fixture = dataclasses.replace(self.fixture)
        if fixture.fixture_id != source_id:
            raise _error("row fixture identity differs from fixture_identifier")
        if self.disposition not in _DISPOSITIONS:
            raise _error("prediction disposition escaped reviewed vocabulary")
        if type(self.missing_feature_ids) is not tuple or tuple(
            sorted(set(self.missing_feature_ids))
        ) != self.missing_feature_ids:
            raise _error("missing_feature_ids must be sorted unique tuple")

        if self.disposition == SEALED_COMPLETE_CASE:
            if (
                self.missing_feature_ids
                or type(self.sealed_prediction) is not fresh.SealedFreshPrediction
            ):
                raise _error("complete row must carry exactly one sealed prediction")
            prediction = dataclasses.replace(self.sealed_prediction)
            if prediction.fixture != fixture:
                raise _error("sealed prediction differs from exact current source fixture")
            expected_sha = fresh.sha256_sealed_fresh_prediction(prediction)
            if self.sealed_prediction_sha256 != expected_sha:
                raise _error("sealed_prediction_sha256 mismatch")
            object.__setattr__(self, "sealed_prediction", prediction)
        else:
            if (
                self.sealed_prediction is not None
                or self.sealed_prediction_sha256 is not None
            ):
                raise _error("blocked row cannot carry sealed prediction")
            if (
                self.disposition == MISSING_REVIEWED_FEATURES
                and not self.missing_feature_ids
            ):
                raise _error("missing-feature row must preserve missing feature IDs")
            if (
                self.disposition == OUTSIDE_REVIEWED_SEAL_WINDOW
                and self.missing_feature_ids
            ):
                raise _error("outside-window row cannot claim feature evaluation")
        object.__setattr__(self, "fixture", fixture)

    @property
    def kickoff_utc(self) -> dt.datetime:
        return self.fixture.kickoff_utc

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "fixture": self.fixture.to_dict(),
            "disposition": self.disposition,
            "missing_feature_ids": list(self.missing_feature_ids),
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "sealed_prediction": (
                None
                if self.sealed_prediction is None
                else self.sealed_prediction.to_dict()
            ),
        }


@dataclasses.dataclass(frozen=True)
class _DerivedShadowState:
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    fresh_legacy_update_count: int
    rows: tuple[CurrentUtcNativeShadowPredictionRow, ...]

    def __post_init__(self) -> None:
        _sha(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _sha(self.review_bundle_sha256, "review_bundle_sha256")
        if (
            type(self.fresh_legacy_update_count) is not int
            or self.fresh_legacy_update_count < 0
        ):
            raise _error("fresh_legacy_update_count must be exact non-negative integer")
        if type(self.rows) is not tuple or not self.rows or any(
            type(row) is not CurrentUtcNativeShadowPredictionRow for row in self.rows
        ):
            raise _error("derived rows must be non-empty exact immutable tuple")


def _history_ledger(
    source_bundle: CurrentUtcNativeShadowPredictionSourceBundle,
) -> tuple[fresh.FreshHistoryLedger, int]:
    try:
        ledger = fresh.build_fresh_history_ledger(
            source_bundle.legacy_bootstrap_projection_raw
        )
    except Exception as exc:
        raise _error("exact PR119 bootstrap failed reviewed replay") from exc
    update_count = 0
    for settlement in source_bundle.reviewed_fresh_settlements:
        if settlement.legacy_history_state_update is None:
            continue
        try:
            ledger = fresh.append_fresh_legacy_history_update(ledger, settlement)
        except Exception as exc:
            raise _error("fresh settlement failed reviewed history replay") from exc
        update_count += 1
    return ledger, update_count


def _derive_shadow_state(
    source_bundle: CurrentUtcNativeShadowPredictionSourceBundle,
) -> _DerivedShadowState:
    if type(source_bundle) is not CurrentUtcNativeShadowPredictionSourceBundle:
        raise _error("source_bundle type mismatch")
    source = dataclasses.replace(source_bundle)
    bootstrap = source.current_bootstrap

    try:
        candidates = build_fotmob_fixture_candidate_bundle(
            ((source.source_raw_json, source.source_manifest),)
        )
    except Exception as exc:
        raise _error("source failed reviewed fixture-candidate replay") from exc
    candidate_sha = sha256_fotmob_fixture_candidate_bundle(candidates)
    if candidate_sha != bootstrap.candidate_bundle_sha256:
        raise _error("source candidate bundle differs from current bootstrap ancestry")

    try:
        policy = build_current_fotmob_fixture_review_policy_result(
            candidates,
            reviewed_at=bootstrap.admission_reviewed_at,
        )
    except Exception as exc:
        raise _error("source failed frozen PR243 policy replay") from exc
    review_sha = hashlib.sha256(
        canonical_fotmob_fixture_candidate_review_bundle_bytes(policy.review_bundle)
    ).hexdigest()
    if review_sha != bootstrap.review_bundle_sha256:
        raise _error("PR243 review bundle differs from current bootstrap ancestry")
    if policy.policy_approved_count != len(bootstrap.fixtures):
        raise _error("PR243 approval count differs from current bootstrap fixture count")

    try:
        qualified = fresh.qualify_capture_fixtures(
            source.source_raw_json,
            source.source_manifest,
        )
    except Exception as exc:
        raise _error("source failed reviewed PR149 provider-native qualification") from exc
    by_id = {fixture.fixture_id: fixture for fixture in qualified}
    if len(by_id) != len(qualified):
        raise _error("provider-native replay returned duplicate fixture IDs")

    ledger, update_count = _history_ledger(source)
    holdout_start = control.holdout_start_utc()
    rows: list[CurrentUtcNativeShadowPredictionRow] = []

    for identity in bootstrap.fixtures:
        source_id = _source_id(identity.fixture_identifier)
        capture = by_id.get(source_id)
        if capture is None:
            raise _error("bootstrapped fixture absent from provider-native replay")
        if capture.kickoff_utc != identity.kickoff:
            raise _error("provider-native kickoff differs from current bootstrap")
        selected = fresh.select_earliest_qualifying_capture(
            (capture,), holdout_start=holdout_start
        )
        if selected is None:
            rows.append(
                CurrentUtcNativeShadowPredictionRow(
                    fixture_identifier=identity.fixture_identifier,
                    fixture=capture,
                    disposition=OUTSIDE_REVIEWED_SEAL_WINDOW,
                    missing_feature_ids=(),
                    sealed_prediction=None,
                    sealed_prediction_sha256=None,
                )
            )
            continue

        try:
            assessment = fresh.build_fresh_prediction_assessment(
                history_ledger=ledger,
                selected_capture=selected,
                holdout_start=holdout_start,
            )
        except Exception as exc:
            raise _error("PR149 prediction construction failed reviewed replay") from exc

        if assessment.disposition is fresh.PredictionDisposition.SEALED_COMPLETE_CASE:
            if assessment.sealed_prediction is None:
                raise _error("complete PR149 assessment lost sealed prediction")
            disposition = SEALED_COMPLETE_CASE
            prediction = assessment.sealed_prediction
            prediction_sha = fresh.sha256_sealed_fresh_prediction(prediction)
            missing = ()
        elif assessment.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES:
            disposition = MISSING_REVIEWED_FEATURES
            prediction = None
            prediction_sha = None
            missing = assessment.missing_feature_ids
        else:
            raise _error("PR149 assessment escaped reviewed disposition vocabulary")

        rows.append(
            CurrentUtcNativeShadowPredictionRow(
                fixture_identifier=identity.fixture_identifier,
                fixture=selected,
                disposition=disposition,
                missing_feature_ids=missing,
                sealed_prediction=prediction,
                sealed_prediction_sha256=prediction_sha,
            )
        )

    ordered = tuple(
        sorted(rows, key=lambda row: (row.kickoff_utc, row.fixture_identifier))
    )
    return _DerivedShadowState(
        candidate_bundle_sha256=candidate_sha,
        review_bundle_sha256=review_sha,
        fresh_legacy_update_count=update_count,
        rows=ordered,
    )


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionHandoff:
    schema_version: int
    dataset_name: str
    status: str
    source_bundle: CurrentUtcNativeShadowPredictionSourceBundle
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    reviewed_fresh_legacy_update_count: int
    rows: tuple[CurrentUtcNativeShadowPredictionRow, ...]
    next_required_boundary: str
    research_evidence: Mapping[str, bool]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("handoff schema mismatch")
        if self.status != STATUS_REPLAYED:
            raise _error("handoff status mismatch")
        if type(self.source_bundle) is not CurrentUtcNativeShadowPredictionSourceBundle:
            raise _error("handoff source_bundle type mismatch")
        source = dataclasses.replace(self.source_bundle)
        derived = _derive_shadow_state(source)
        if self.candidate_bundle_sha256 != derived.candidate_bundle_sha256:
            raise _error("candidate_bundle_sha256 differs from exact source replay")
        if self.review_bundle_sha256 != derived.review_bundle_sha256:
            raise _error("review_bundle_sha256 differs from exact PR243 replay")
        if self.reviewed_fresh_legacy_update_count != derived.fresh_legacy_update_count:
            raise _error("fresh legacy update count differs from exact history replay")
        if self.rows != derived.rows:
            raise _error("shadow rows differ from exact deterministic reconstruction")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary mismatch")
        research = _validate_boolean_map(
            self.research_evidence,
            expected=_research_evidence(),
            label="research_evidence",
        )
        authority = _validate_boolean_map(
            self.authority,
            expected=_downstream_authority(),
            label="authority",
        )
        object.__setattr__(self, "source_bundle", source)
        object.__setattr__(self, "research_evidence", research)
        object.__setattr__(self, "authority", authority)

    @property
    def current_bootstrap_sha256(self) -> str:
        return self.source_bundle.current_bootstrap_sha256

    @property
    def source_manifest_sha256(self) -> str:
        return self.source_bundle.source_manifest_sha256

    @property
    def source_raw_sha256(self) -> str:
        return self.source_bundle.source_raw_sha256

    @property
    def legacy_bootstrap_sha256(self) -> str:
        return self.source_bundle.legacy_bootstrap_sha256

    @property
    def reviewed_fresh_settlement_count(self) -> int:
        return len(self.source_bundle.reviewed_fresh_settlements)

    @property
    def holdout_start_utc(self) -> dt.datetime:
        return control.holdout_start_utc()

    @property
    def current_fresh_history_prefix_complete(self) -> bool:
        return False

    @property
    def fixture_count(self) -> int:
        return len(self.rows)

    @property
    def sealed_complete_case_count(self) -> int:
        return sum(row.disposition == SEALED_COMPLETE_CASE for row in self.rows)

    @property
    def missing_feature_count(self) -> int:
        return sum(row.disposition == MISSING_REVIEWED_FEATURES for row in self.rows)

    @property
    def outside_seal_window_count(self) -> int:
        return sum(row.disposition == OUTSIDE_REVIEWED_SEAL_WINDOW for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "pr243_policy_id": PR243_POLICY_ID,
            "current_bootstrap_sha256": self.current_bootstrap_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "holdout_start_utc": self.holdout_start_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "legacy_bootstrap_sha256": self.legacy_bootstrap_sha256,
            "reviewed_fresh_settlement_count": self.reviewed_fresh_settlement_count,
            "reviewed_fresh_legacy_update_count": self.reviewed_fresh_legacy_update_count,
            "current_fresh_history_prefix_complete": (
                self.current_fresh_history_prefix_complete
            ),
            "fixture_count": self.fixture_count,
            "sealed_complete_case_count": self.sealed_complete_case_count,
            "missing_feature_count": self.missing_feature_count,
            "outside_seal_window_count": self.outside_seal_window_count,
            "rows": [row.to_dict() for row in self.rows],
            "next_required_boundary": self.next_required_boundary,
            "research_evidence": dict(self.research_evidence),
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def build_current_fotmob_utc_native_shadow_prediction_handoff(
    *,
    current_bootstrap: ReviewedFixtureIntelligenceBootstrap,
    source_raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
    legacy_bootstrap_projection_raw: bytes,
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...] = (),
) -> CurrentUtcNativeShadowPredictionHandoff:
    """Derive a deterministic shadow replay from exact supplied reviewed inputs.

    This function validates each supplied fresh settlement, but it does not prove
    that the tuple is the complete active PR151 durable prefix. Callers must not
    treat a returned `SEALED_COMPLETE_CASE` as a complete-current-history claim.
    """
    source = CurrentUtcNativeShadowPredictionSourceBundle(
        current_bootstrap=current_bootstrap,
        source_raw_json=source_raw_json,
        source_manifest=source_manifest,
        legacy_bootstrap_projection_raw=legacy_bootstrap_projection_raw,
        reviewed_fresh_settlements=reviewed_fresh_settlements,
    )
    derived = _derive_shadow_state(source)
    return CurrentUtcNativeShadowPredictionHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS_REPLAYED,
        source_bundle=source,
        candidate_bundle_sha256=derived.candidate_bundle_sha256,
        review_bundle_sha256=derived.review_bundle_sha256,
        reviewed_fresh_legacy_update_count=derived.fresh_legacy_update_count,
        rows=derived.rows,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        research_evidence=_research_evidence(),
        authority=_downstream_authority(),
    )


def canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes(
    value: Any,
) -> bytes:
    if type(value) is not CurrentUtcNativeShadowPredictionHandoff:
        raise _error("value must be exact CurrentUtcNativeShadowPredictionHandoff")
    return _canonical(dataclasses.replace(value).to_dict())


def sha256_current_fotmob_utc_native_shadow_prediction_handoff(value: Any) -> str:
    return hashlib.sha256(
        canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "MISSING_REVIEWED_FEATURES",
    "NEXT_REQUIRED_BOUNDARY",
    "OUTSIDE_REVIEWED_SEAL_WINDOW",
    "SCHEMA_VERSION",
    "SEALED_COMPLETE_CASE",
    "STATUS_READY",
    "STATUS_REPLAYED",
    "CurrentUtcNativeShadowPredictionError",
    "CurrentUtcNativeShadowPredictionHandoff",
    "CurrentUtcNativeShadowPredictionRow",
    "CurrentUtcNativeShadowPredictionSourceBundle",
    "build_current_fotmob_utc_native_shadow_prediction_handoff",
    "canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes",
    "sha256_current_fotmob_utc_native_shadow_prediction_handoff",
]
