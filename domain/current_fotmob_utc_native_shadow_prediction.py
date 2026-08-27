"""Bridge PR243 current fixture identity into the reviewed UTC-native shadow xG path.

This boundary is deliberately research/shadow-only.  It replays the exact
transparent data-matches response that produced a reviewed current fixture
bootstrap, re-runs the frozen PR243 policy, reconstructs the reviewed UTC-native
history ledger only from the exact PR119 bootstrap plus reviewed fresh
settlements, and delegates feature/rate construction to the existing PR149
fresh-holdout core.

It does not reinterpret provider home_form/away_form/Elo/fatigue scalars, does
not calculate market probabilities, does not create Phase-6 candidates, does
not inspect bookmaker prices, and grants no production/selection/BET authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any, Sequence

from domain.current_fotmob_fixture_review_policy import (
    POLICY_ID as PR243_POLICY_ID,
    build_current_fotmob_fixture_review_policy_result,
)
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
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
STATUS_READY = "CURRENT_REVIEWED_FOTMOB_UTC_NATIVE_SHADOW_PREDICTIONS_ISSUED"
NEXT_REQUIRED_BOUNDARY = (
    "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_"
    "FRESH_HOLDOUT_CONFIRMATION"
)

_SAFETY_KEYS = frozenset(
    {
        "fixture_identity_production_authorized",
        "utc_native_research_feature_construction_performed",
        "shadow_expected_goals_rate_construction_performed",
        "production_model_authorized",
        "score_matrix_authorized",
        "probability_authorized",
        "phase6_authorized",
        "pricing_authorized",
        "selection_authorized",
        "sportybet_execution_authorized",
        "bet_authorized",
    }
)


class CurrentUtcNativeShadowPredictionError(ValueError):
    """Raised when the current-to-shadow bridge cannot preserve exact ancestry."""


def _error(message: str) -> CurrentUtcNativeShadowPredictionError:
    return CurrentUtcNativeShadowPredictionError(message)


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise _error(f"{label} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
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
        raise _error(f"{label} must be exact SHA-256")
    return value


def _safety() -> Mapping[str, bool]:
    # These two booleans are factual execution state, not downstream authority.
    values = {key: False for key in sorted(_SAFETY_KEYS)}
    values["utc_native_research_feature_construction_performed"] = True
    values["shadow_expected_goals_rate_construction_performed"] = True
    return types.MappingProxyType(values)


def _validate_safety(value: Any) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != _SAFETY_KEYS:
        raise _error("safety keys mismatch")
    expected = dict(_safety())
    for key, item in value.items():
        if type(item) is not bool or item is not expected[key]:
            raise _error(f"safety[{key!r}] changed reviewed authority state")
    return _safety()


def _canonical(value: Any) -> bytes:
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
        raise _error("canonical shadow handoff serialization failed") from exc


def _fixture_id(value: str) -> int:
    if type(value) is not str or not value.startswith("FOTMOB:"):
        raise _error("bootstrap fixture identity escaped FOTMOB source scope")
    raw = value.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) < 1:
        raise _error("bootstrap fixture identity has invalid source match id")
    return int(raw)


class ShadowPredictionDisposition(str):
    SEALED_COMPLETE_CASE = "SEALED_COMPLETE_CASE"
    MISSING_REVIEWED_FEATURES = "MISSING_REVIEWED_FEATURES"
    OUTSIDE_REVIEWED_SEAL_WINDOW = "OUTSIDE_REVIEWED_SEAL_WINDOW"


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionRow:
    fixture_identifier: str
    kickoff_utc: dt.datetime
    provider_primary_id: int
    wrapper_id: int
    home_team_id: int
    away_team_id: int
    capture_observed_at: dt.datetime
    capture_manifest_sha256: str
    capture_raw_sha256: str
    disposition: str
    missing_feature_ids: tuple[str, ...]
    sealed_prediction: fresh.SealedFreshPrediction | None
    sealed_prediction_sha256: str | None

    def __post_init__(self) -> None:
        fixture_id = _fixture_id(self.fixture_identifier)
        for label in (
            "provider_primary_id",
            "wrapper_id",
            "home_team_id",
            "away_team_id",
        ):
            value = getattr(self, label)
            if type(value) is not int or value < 1:
                raise _error(f"{label} must be exact positive integer")
        if self.home_team_id == self.away_team_id:
            raise _error("shadow row cannot use one team twice")
        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        observed = _utc(self.capture_observed_at, "capture_observed_at")
        manifest_sha = _sha(self.capture_manifest_sha256, "capture_manifest_sha256")
        raw_sha = _sha(self.capture_raw_sha256, "capture_raw_sha256")
        allowed = {
            ShadowPredictionDisposition.SEALED_COMPLETE_CASE,
            ShadowPredictionDisposition.MISSING_REVIEWED_FEATURES,
            ShadowPredictionDisposition.OUTSIDE_REVIEWED_SEAL_WINDOW,
        }
        if self.disposition not in allowed:
            raise _error("shadow prediction disposition is invalid")
        if type(self.missing_feature_ids) is not tuple:
            raise _error("missing_feature_ids must be immutable tuple")
        if tuple(sorted(set(self.missing_feature_ids))) != self.missing_feature_ids:
            raise _error("missing_feature_ids must be sorted and unique")

        if self.disposition == ShadowPredictionDisposition.SEALED_COMPLETE_CASE:
            if self.missing_feature_ids or type(self.sealed_prediction) is not fresh.SealedFreshPrediction:
                raise _error("complete shadow row must carry exactly one sealed prediction")
            prediction = fresh.SealedFreshPrediction(**dataclasses.asdict(self.sealed_prediction))
            if prediction.fixture.fixture_id != fixture_id:
                raise _error("sealed prediction fixture differs from current bootstrap")
            if prediction.fixture.kickoff_utc != kickoff:
                raise _error("sealed prediction kickoff differs from current bootstrap")
            if (
                prediction.fixture.provider_primary_id != self.provider_primary_id
                or prediction.fixture.wrapper_id != self.wrapper_id
                or prediction.fixture.home_team_id != self.home_team_id
                or prediction.fixture.away_team_id != self.away_team_id
                or prediction.fixture.capture_observed_at != observed
                or prediction.fixture.capture_manifest_sha256 != manifest_sha
                or prediction.fixture.capture_raw_sha256 != raw_sha
            ):
                raise _error("sealed prediction source identity differs from current capture")
            expected_sha = fresh.sha256_sealed_fresh_prediction(prediction)
            if self.sealed_prediction_sha256 != expected_sha:
                raise _error("sealed_prediction_sha256 mismatch")
            object.__setattr__(self, "sealed_prediction", prediction)
        else:
            if self.sealed_prediction is not None or self.sealed_prediction_sha256 is not None:
                raise _error("non-sealed shadow row cannot carry a prediction")
            if self.disposition == ShadowPredictionDisposition.MISSING_REVIEWED_FEATURES:
                if not self.missing_feature_ids:
                    raise _error("missing-feature row must identify missing reviewed features")
            elif self.missing_feature_ids:
                raise _error("outside-window row cannot claim missing feature evaluation")

        object.__setattr__(self, "kickoff_utc", kickoff)
        object.__setattr__(self, "capture_observed_at", observed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_identifier": self.fixture_identifier,
            "kickoff_utc": self.kickoff_utc.isoformat().replace("+00:00", "Z"),
            "provider_primary_id": self.provider_primary_id,
            "wrapper_id": self.wrapper_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "capture_observed_at": self.capture_observed_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "capture_manifest_sha256": self.capture_manifest_sha256,
            "capture_raw_sha256": self.capture_raw_sha256,
            "disposition": self.disposition,
            "missing_feature_ids": list(self.missing_feature_ids),
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "sealed_prediction": (
                None if self.sealed_prediction is None else self.sealed_prediction.to_dict()
            ),
        }


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionHandoff:
    schema_version: int
    dataset_name: str
    status: str
    pr243_policy_id: str
    current_bootstrap_sha256: str
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    holdout_start_utc: dt.datetime
    legacy_bootstrap_sha256: str
    reviewed_fresh_settlement_count: int
    reviewed_fresh_legacy_update_count: int
    fixture_count: int
    sealed_complete_case_count: int
    missing_feature_count: int
    outside_seal_window_count: int
    rows: tuple[CurrentUtcNativeShadowPredictionRow, ...]
    next_required_boundary: str
    safety: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("shadow handoff schema mismatch")
        if self.status != STATUS_READY:
            raise _error("shadow handoff status mismatch")
        if self.pr243_policy_id != PR243_POLICY_ID:
            raise _error("PR243 policy identity mismatch")
        for label in (
            "current_bootstrap_sha256",
            "candidate_bundle_sha256",
            "review_bundle_sha256",
            "source_manifest_sha256",
            "source_raw_sha256",
            "legacy_bootstrap_sha256",
        ):
            _sha(getattr(self, label), label)
        holdout = _utc(self.holdout_start_utc, "holdout_start_utc")
        if holdout != control.holdout_start_utc():
            raise _error("shadow handoff must use exact reviewed holdout start")
        for label in (
            "reviewed_fresh_settlement_count",
            "reviewed_fresh_legacy_update_count",
            "fixture_count",
            "sealed_complete_case_count",
            "missing_feature_count",
            "outside_seal_window_count",
        ):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise _error(f"{label} must be exact non-negative integer")
        if type(self.rows) is not tuple or any(
            type(row) is not CurrentUtcNativeShadowPredictionRow for row in self.rows
        ):
            raise _error("shadow rows must be exact immutable row tuple")
        if self.fixture_count != len(self.rows):
            raise _error("fixture_count does not match rows")
        identifiers = tuple(row.fixture_identifier for row in self.rows)
        if len(identifiers) != len(set(identifiers)):
            raise _error("shadow rows contain duplicate fixture identity")
        if self.rows != tuple(
            sorted(self.rows, key=lambda row: (row.kickoff_utc, row.fixture_identifier))
        ):
            raise _error("shadow rows must preserve deterministic fixture ordering")
        counts = {
            ShadowPredictionDisposition.SEALED_COMPLETE_CASE: self.sealed_complete_case_count,
            ShadowPredictionDisposition.MISSING_REVIEWED_FEATURES: self.missing_feature_count,
            ShadowPredictionDisposition.OUTSIDE_REVIEWED_SEAL_WINDOW: self.outside_seal_window_count,
        }
        for disposition, expected in counts.items():
            if sum(row.disposition == disposition for row in self.rows) != expected:
                raise _error(f"{disposition} count mismatch")
        if sum(counts.values()) != self.fixture_count:
            raise _error("shadow disposition counts do not reconcile")
        if self.reviewed_fresh_legacy_update_count > self.reviewed_fresh_settlement_count:
            raise _error("legacy update count exceeds reviewed settlement count")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("shadow next boundary mismatch")
        object.__setattr__(self, "holdout_start_utc", holdout)
        object.__setattr__(self, "safety", _validate_safety(self.safety))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "pr243_policy_id": self.pr243_policy_id,
            "current_bootstrap_sha256": self.current_bootstrap_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "review_bundle_sha256": self.review_bundle_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_raw_sha256": self.source_raw_sha256,
            "holdout_start_utc": self.holdout_start_utc.isoformat().replace("+00:00", "Z"),
            "legacy_bootstrap_sha256": self.legacy_bootstrap_sha256,
            "reviewed_fresh_settlement_count": self.reviewed_fresh_settlement_count,
            "reviewed_fresh_legacy_update_count": self.reviewed_fresh_legacy_update_count,
            "fixture_count": self.fixture_count,
            "sealed_complete_case_count": self.sealed_complete_case_count,
            "missing_feature_count": self.missing_feature_count,
            "outside_seal_window_count": self.outside_seal_window_count,
            "rows": [row.to_dict() for row in self.rows],
            "next_required_boundary": self.next_required_boundary,
            "safety": dict(self.safety),
            "wager_placed": False,
        }


def _rebuild_history_ledger(
    legacy_bootstrap_projection_raw: bytes,
    reviewed_fresh_settlements: Sequence[fresh.SettledFreshPrediction],
) -> tuple[fresh.FreshHistoryLedger, int]:
    if type(legacy_bootstrap_projection_raw) is not bytes:
        raise _error("legacy_bootstrap_projection_raw must be exact bytes")
    if type(reviewed_fresh_settlements) is not tuple:
        raise _error("reviewed_fresh_settlements must be immutable tuple")
    try:
        ledger = fresh.build_fresh_history_ledger(legacy_bootstrap_projection_raw)
    except Exception as exc:
        raise _error("exact PR119 bootstrap projection failed reviewed replay") from exc

    seen: set[str] = set()
    updates = 0
    for settlement in reviewed_fresh_settlements:
        if type(settlement) is not fresh.SettledFreshPrediction:
            raise _error("reviewed_fresh_settlements contains invalid object")
        prediction_sha = fresh.sha256_sealed_fresh_prediction(settlement.prediction)
        if prediction_sha in seen:
            raise _error("reviewed_fresh_settlements contains duplicate prediction")
        seen.add(prediction_sha)
        if settlement.legacy_history_state_update is None:
            continue
        try:
            ledger = fresh.append_fresh_legacy_history_update(ledger, settlement)
        except Exception as exc:
            raise _error("reviewed fresh settlement failed exact history replay") from exc
        updates += 1
    return ledger, updates


def build_current_fotmob_utc_native_shadow_prediction_handoff(
    *,
    current_bootstrap: ReviewedFixtureIntelligenceBootstrap,
    source_raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
    legacy_bootstrap_projection_raw: bytes,
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...] = (),
) -> CurrentUtcNativeShadowPredictionHandoff:
    """Build exact research/shadow xG seals from a PR243 current bootstrap."""

    if type(current_bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
        raise _error("current_bootstrap must be exact ReviewedFixtureIntelligenceBootstrap")
    if type(source_raw_json) is not bytes or not source_raw_json:
        raise _error("source_raw_json must be non-empty exact bytes")
    if type(source_manifest) is not FotMobDataMatchesCaptureManifest:
        raise _error("source_manifest must be exact FotMobDataMatchesCaptureManifest")
    if source_manifest.network_acquisition_performed is not True:
        raise _error("current source manifest must prove transparent network acquisition")
    if hashlib.sha256(source_raw_json).hexdigest() != source_manifest.raw_sha256:
        raise _error("current source raw SHA differs from manifest")

    try:
        rebuilt_bootstrap = dataclasses.replace(current_bootstrap)
        bootstrap_raw = canonical_reviewed_fixture_intelligence_bootstrap_bytes(
            rebuilt_bootstrap
        )
    except Exception as exc:
        raise _error("current bootstrap failed exact reviewed revalidation") from exc
    if bootstrap_raw != canonical_reviewed_fixture_intelligence_bootstrap_bytes(
        current_bootstrap
    ):
        raise _error("current bootstrap differs from exact rebuild")

    try:
        candidate_bundle = build_fotmob_fixture_candidate_bundle(
            ((source_raw_json, source_manifest),)
        )
    except Exception as exc:
        raise _error("current source failed reviewed fixture-candidate replay") from exc
    candidate_sha = sha256_fotmob_fixture_candidate_bundle(candidate_bundle)
    if candidate_sha != current_bootstrap.candidate_bundle_sha256:
        raise _error("current source candidate bundle differs from reviewed bootstrap ancestry")

    try:
        policy = build_current_fotmob_fixture_review_policy_result(
            candidate_bundle,
            reviewed_at=current_bootstrap.admission_reviewed_at,
        )
    except Exception as exc:
        raise _error("current source failed frozen PR243 policy replay") from exc
    review_raw = canonical_fotmob_fixture_candidate_review_bundle_bytes(
        policy.review_bundle
    )
    review_sha = hashlib.sha256(review_raw).hexdigest()
    if review_sha != current_bootstrap.review_bundle_sha256:
        raise _error("PR243 review bundle differs from reviewed bootstrap ancestry")
    if policy.policy_approved_count != len(current_bootstrap.fixtures):
        raise _error("PR243 approval count differs from reviewed bootstrap fixtures")

    try:
        qualified = fresh.qualify_capture_fixtures(source_raw_json, source_manifest)
    except Exception as exc:
        raise _error("current source failed reviewed PR149 provider-native qualification") from exc
    by_fixture = {item.fixture_id: item for item in qualified}

    ledger, legacy_update_count = _rebuild_history_ledger(
        legacy_bootstrap_projection_raw,
        reviewed_fresh_settlements,
    )
    holdout_start = control.holdout_start_utc()

    rows: list[CurrentUtcNativeShadowPredictionRow] = []
    for identity in current_bootstrap.fixtures:
        source_id = _fixture_id(identity.fixture_identifier)
        capture_fixture = by_fixture.get(source_id)
        if capture_fixture is None:
            raise _error("reviewed bootstrap fixture is absent from provider-native replay")
        if capture_fixture.kickoff_utc != identity.kickoff:
            raise _error("provider-native kickoff differs from reviewed bootstrap kickoff")
        selected = fresh.select_earliest_qualifying_capture(
            (capture_fixture,),
            holdout_start=holdout_start,
        )
        if selected is None:
            rows.append(
                CurrentUtcNativeShadowPredictionRow(
                    fixture_identifier=identity.fixture_identifier,
                    kickoff_utc=identity.kickoff,
                    provider_primary_id=capture_fixture.provider_primary_id,
                    wrapper_id=capture_fixture.wrapper_id,
                    home_team_id=capture_fixture.home_team_id,
                    away_team_id=capture_fixture.away_team_id,
                    capture_observed_at=capture_fixture.capture_observed_at,
                    capture_manifest_sha256=capture_fixture.capture_manifest_sha256,
                    capture_raw_sha256=capture_fixture.capture_raw_sha256,
                    disposition=ShadowPredictionDisposition.OUTSIDE_REVIEWED_SEAL_WINDOW,
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
            raise _error("reviewed PR149 shadow prediction construction failed") from exc
        if assessment.disposition is fresh.PredictionDisposition.SEALED_COMPLETE_CASE:
            if assessment.sealed_prediction is None:
                raise _error("PR149 complete assessment lost sealed prediction")
            disposition = ShadowPredictionDisposition.SEALED_COMPLETE_CASE
            sealed = assessment.sealed_prediction
            sealed_sha = fresh.sha256_sealed_fresh_prediction(sealed)
            missing_ids: tuple[str, ...] = ()
        elif assessment.disposition is fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES:
            disposition = ShadowPredictionDisposition.MISSING_REVIEWED_FEATURES
            sealed = None
            sealed_sha = None
            missing_ids = assessment.missing_feature_ids
        else:
            raise _error("PR149 prediction disposition escaped reviewed vocabulary")
        rows.append(
            CurrentUtcNativeShadowPredictionRow(
                fixture_identifier=identity.fixture_identifier,
                kickoff_utc=identity.kickoff,
                provider_primary_id=selected.provider_primary_id,
                wrapper_id=selected.wrapper_id,
                home_team_id=selected.home_team_id,
                away_team_id=selected.away_team_id,
                capture_observed_at=selected.capture_observed_at,
                capture_manifest_sha256=selected.capture_manifest_sha256,
                capture_raw_sha256=selected.capture_raw_sha256,
                disposition=disposition,
                missing_feature_ids=missing_ids,
                sealed_prediction=sealed,
                sealed_prediction_sha256=sealed_sha,
            )
        )

    ordered = tuple(sorted(rows, key=lambda row: (row.kickoff_utc, row.fixture_identifier)))
    source_manifest_sha = hashlib.sha256(source_manifest.canonical_bytes()).hexdigest()
    return CurrentUtcNativeShadowPredictionHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS_READY,
        pr243_policy_id=PR243_POLICY_ID,
        current_bootstrap_sha256=hashlib.sha256(bootstrap_raw).hexdigest(),
        candidate_bundle_sha256=candidate_sha,
        review_bundle_sha256=review_sha,
        source_manifest_sha256=source_manifest_sha,
        source_raw_sha256=source_manifest.raw_sha256,
        holdout_start_utc=holdout_start,
        legacy_bootstrap_sha256=hashlib.sha256(legacy_bootstrap_projection_raw).hexdigest(),
        reviewed_fresh_settlement_count=len(reviewed_fresh_settlements),
        reviewed_fresh_legacy_update_count=legacy_update_count,
        fixture_count=len(ordered),
        sealed_complete_case_count=sum(
            row.disposition == ShadowPredictionDisposition.SEALED_COMPLETE_CASE
            for row in ordered
        ),
        missing_feature_count=sum(
            row.disposition == ShadowPredictionDisposition.MISSING_REVIEWED_FEATURES
            for row in ordered
        ),
        outside_seal_window_count=sum(
            row.disposition == ShadowPredictionDisposition.OUTSIDE_REVIEWED_SEAL_WINDOW
            for row in ordered
        ),
        rows=ordered,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        safety=_safety(),
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
    "NEXT_REQUIRED_BOUNDARY",
    "SCHEMA_VERSION",
    "STATUS_READY",
    "CurrentUtcNativeShadowPredictionError",
    "CurrentUtcNativeShadowPredictionHandoff",
    "CurrentUtcNativeShadowPredictionRow",
    "ShadowPredictionDisposition",
    "build_current_fotmob_utc_native_shadow_prediction_handoff",
    "canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes",
    "sha256_current_fotmob_utc_native_shadow_prediction_handoff",
]
