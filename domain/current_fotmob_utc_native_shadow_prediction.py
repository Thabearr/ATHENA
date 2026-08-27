"""Compose PR243 current fixture identity with the reviewed UTC-native shadow path.

This is a research/shadow boundary only. It replays the exact transparent
`/api/data/matches` response behind a current PR243 bootstrap, re-runs PR243,
reconstructs UTC-native history only from exact PR119 bootstrap bytes plus
reviewed fresh settlements, then delegates all feature/xG construction to the
existing PR149 fresh-holdout implementation.

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
STATUS_READY = "CURRENT_REVIEWED_FOTMOB_UTC_NATIVE_SHADOW_PREDICTIONS_ISSUED"
NEXT_REQUIRED_BOUNDARY = (
    "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_"
    "FRESH_HOLDOUT_CONFIRMATION"
)

SEALED_COMPLETE_CASE = "SEALED_COMPLETE_CASE"
MISSING_REVIEWED_FEATURES = "MISSING_REVIEWED_FEATURES"
OUTSIDE_REVIEWED_SEAL_WINDOW = "OUTSIDE_REVIEWED_SEAL_WINDOW"
_DISPOSITIONS = frozenset(
    {SEALED_COMPLETE_CASE, MISSING_REVIEWED_FEATURES, OUTSIDE_REVIEWED_SEAL_WINDOW}
)

_AUTHORITY_KEYS = frozenset(
    {
        "reviewed_current_fixture_identity",
        "utc_native_research_feature_construction",
        "shadow_expected_goals_rates",
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
    """Raised when exact reviewed ancestry cannot be preserved."""


def _error(message: str) -> CurrentUtcNativeShadowPredictionError:
    return CurrentUtcNativeShadowPredictionError(message)


def _utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
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
    if type(fixture_identifier) is not str or not fixture_identifier.startswith("FOTMOB:"):
        raise _error("fixture identity escaped exact FOTMOB source scope")
    raw = fixture_identifier.removeprefix("FOTMOB:")
    if not raw.isdigit() or int(raw) < 1:
        raise _error("fixture identity has invalid FotMob source id")
    return int(raw)


def _authority() -> Mapping[str, bool]:
    values = {key: False for key in sorted(_AUTHORITY_KEYS)}
    values["reviewed_current_fixture_identity"] = True
    values["utc_native_research_feature_construction"] = True
    values["shadow_expected_goals_rates"] = True
    return types.MappingProxyType(values)


def _validate_authority(value: Any) -> Mapping[str, bool]:
    expected = dict(_authority())
    if not isinstance(value, Mapping) or set(value) != _AUTHORITY_KEYS:
        raise _error("authority keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not expected[key]:
            raise _error(f"authority[{key!r}] changed reviewed state")
    return _authority()


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
        source_id = _source_id(self.fixture_identifier)
        for label in ("provider_primary_id", "wrapper_id", "home_team_id", "away_team_id"):
            value = getattr(self, label)
            if type(value) is not int or value < 1:
                raise _error(f"{label} must be exact positive integer")
        if self.home_team_id == self.away_team_id:
            raise _error("one team cannot occupy both fixture sides")
        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        observed = _utc(self.capture_observed_at, "capture_observed_at")
        _sha(self.capture_manifest_sha256, "capture_manifest_sha256")
        _sha(self.capture_raw_sha256, "capture_raw_sha256")
        if self.disposition not in _DISPOSITIONS:
            raise _error("prediction disposition escaped reviewed vocabulary")
        if type(self.missing_feature_ids) is not tuple or tuple(
            sorted(set(self.missing_feature_ids))
        ) != self.missing_feature_ids:
            raise _error("missing_feature_ids must be sorted unique tuple")

        if self.disposition == SEALED_COMPLETE_CASE:
            if self.missing_feature_ids or type(self.sealed_prediction) is not fresh.SealedFreshPrediction:
                raise _error("complete row must carry exactly one sealed prediction")
            prediction = dataclasses.replace(self.sealed_prediction)
            fixture = prediction.fixture
            if (
                fixture.fixture_id != source_id
                or fixture.kickoff_utc != kickoff
                or fixture.provider_primary_id != self.provider_primary_id
                or fixture.wrapper_id != self.wrapper_id
                or fixture.home_team_id != self.home_team_id
                or fixture.away_team_id != self.away_team_id
                or fixture.capture_observed_at != observed
                or fixture.capture_manifest_sha256 != self.capture_manifest_sha256
                or fixture.capture_raw_sha256 != self.capture_raw_sha256
            ):
                raise _error("sealed prediction differs from exact current source identity")
            expected_sha = fresh.sha256_sealed_fresh_prediction(prediction)
            if self.sealed_prediction_sha256 != expected_sha:
                raise _error("sealed_prediction_sha256 mismatch")
            object.__setattr__(self, "sealed_prediction", prediction)
        else:
            if self.sealed_prediction is not None or self.sealed_prediction_sha256 is not None:
                raise _error("blocked row cannot carry sealed prediction")
            if self.disposition == MISSING_REVIEWED_FEATURES and not self.missing_feature_ids:
                raise _error("missing-feature row must preserve missing feature IDs")
            if self.disposition == OUTSIDE_REVIEWED_SEAL_WINDOW and self.missing_feature_ids:
                raise _error("outside-window row cannot claim feature evaluation")

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
            "capture_observed_at": self.capture_observed_at.isoformat().replace("+00:00", "Z"),
            "capture_manifest_sha256": self.capture_manifest_sha256,
            "capture_raw_sha256": self.capture_raw_sha256,
            "disposition": self.disposition,
            "missing_feature_ids": list(self.missing_feature_ids),
            "sealed_prediction_sha256": self.sealed_prediction_sha256,
            "sealed_prediction": None if self.sealed_prediction is None else self.sealed_prediction.to_dict(),
        }


@dataclasses.dataclass(frozen=True)
class CurrentUtcNativeShadowPredictionHandoff:
    schema_version: int
    dataset_name: str
    status: str
    current_bootstrap_sha256: str
    candidate_bundle_sha256: str
    review_bundle_sha256: str
    source_manifest_sha256: str
    source_raw_sha256: str
    holdout_start_utc: dt.datetime
    legacy_bootstrap_sha256: str
    reviewed_fresh_settlement_count: int
    reviewed_fresh_legacy_update_count: int
    rows: tuple[CurrentUtcNativeShadowPredictionRow, ...]
    next_required_boundary: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("handoff schema mismatch")
        if self.status != STATUS_READY:
            raise _error("handoff status mismatch")
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
            raise _error("handoff holdout start differs from reviewed collection control")
        for label in ("reviewed_fresh_settlement_count", "reviewed_fresh_legacy_update_count"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise _error(f"{label} must be exact non-negative integer")
        if self.reviewed_fresh_legacy_update_count > self.reviewed_fresh_settlement_count:
            raise _error("fresh legacy update count exceeds settlement count")
        if type(self.rows) is not tuple or not self.rows or any(
            type(row) is not CurrentUtcNativeShadowPredictionRow for row in self.rows
        ):
            raise _error("rows must be non-empty exact immutable row tuple")
        if self.rows != tuple(sorted(self.rows, key=lambda row: (row.kickoff_utc, row.fixture_identifier))):
            raise _error("rows must preserve deterministic fixture ordering")
        identifiers = tuple(row.fixture_identifier for row in self.rows)
        if len(identifiers) != len(set(identifiers)):
            raise _error("rows contain duplicate fixture identity")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary mismatch")
        object.__setattr__(self, "holdout_start_utc", holdout)
        object.__setattr__(self, "authority", _validate_authority(self.authority))

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
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def _history_ledger(
    legacy_bootstrap_projection_raw: bytes,
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...],
) -> tuple[fresh.FreshHistoryLedger, int]:
    if type(legacy_bootstrap_projection_raw) is not bytes:
        raise _error("legacy bootstrap projection must be exact bytes")
    if type(reviewed_fresh_settlements) is not tuple:
        raise _error("reviewed fresh settlements must be immutable tuple")
    try:
        ledger = fresh.build_fresh_history_ledger(legacy_bootstrap_projection_raw)
    except Exception as exc:
        raise _error("exact PR119 bootstrap failed reviewed replay") from exc

    seen: set[str] = set()
    update_count = 0
    for settlement in reviewed_fresh_settlements:
        if type(settlement) is not fresh.SettledFreshPrediction:
            raise _error("fresh settlement tuple contains invalid object")
        prediction_sha = fresh.sha256_sealed_fresh_prediction(settlement.prediction)
        if prediction_sha in seen:
            raise _error("fresh settlement tuple contains duplicate prediction")
        seen.add(prediction_sha)
        if settlement.legacy_history_state_update is None:
            continue
        try:
            ledger = fresh.append_fresh_legacy_history_update(ledger, settlement)
        except Exception as exc:
            raise _error("fresh settlement failed reviewed history replay") from exc
        update_count += 1
    return ledger, update_count


def build_current_fotmob_utc_native_shadow_prediction_handoff(
    *,
    current_bootstrap: ReviewedFixtureIntelligenceBootstrap,
    source_raw_json: bytes,
    source_manifest: FotMobDataMatchesCaptureManifest,
    legacy_bootstrap_projection_raw: bytes,
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...] = (),
) -> CurrentUtcNativeShadowPredictionHandoff:
    """Issue research/shadow UTC-native xG seals for exact current PR243 fixtures."""
    if type(current_bootstrap) is not ReviewedFixtureIntelligenceBootstrap:
        raise _error("current_bootstrap must be exact ReviewedFixtureIntelligenceBootstrap")
    if type(source_raw_json) is not bytes or not source_raw_json:
        raise _error("source_raw_json must be non-empty exact bytes")
    if type(source_manifest) is not FotMobDataMatchesCaptureManifest:
        raise _error("source_manifest must be exact FotMobDataMatchesCaptureManifest")
    if source_manifest.network_acquisition_performed is not True:
        raise _error("source manifest must prove transparent network acquisition")
    if hashlib.sha256(source_raw_json).hexdigest() != source_manifest.raw_sha256:
        raise _error("source raw SHA differs from reviewed manifest")

    try:
        rebuilt_bootstrap = dataclasses.replace(current_bootstrap)
        bootstrap_raw = canonical_reviewed_fixture_intelligence_bootstrap_bytes(rebuilt_bootstrap)
        if bootstrap_raw != canonical_reviewed_fixture_intelligence_bootstrap_bytes(current_bootstrap):
            raise _error("current bootstrap differs from exact rebuild")
    except CurrentUtcNativeShadowPredictionError:
        raise
    except Exception as exc:
        raise _error("current bootstrap failed exact reviewed revalidation") from exc

    try:
        candidates = build_fotmob_fixture_candidate_bundle(((source_raw_json, source_manifest),))
    except Exception as exc:
        raise _error("source failed reviewed fixture-candidate replay") from exc
    candidate_sha = sha256_fotmob_fixture_candidate_bundle(candidates)
    if candidate_sha != current_bootstrap.candidate_bundle_sha256:
        raise _error("source candidate bundle differs from current bootstrap ancestry")

    try:
        policy = build_current_fotmob_fixture_review_policy_result(
            candidates,
            reviewed_at=current_bootstrap.admission_reviewed_at,
        )
    except Exception as exc:
        raise _error("source failed frozen PR243 policy replay") from exc
    review_sha = hashlib.sha256(
        canonical_fotmob_fixture_candidate_review_bundle_bytes(policy.review_bundle)
    ).hexdigest()
    if review_sha != current_bootstrap.review_bundle_sha256:
        raise _error("PR243 review bundle differs from current bootstrap ancestry")
    if policy.policy_approved_count != len(current_bootstrap.fixtures):
        raise _error("PR243 approval count differs from current bootstrap fixture count")

    try:
        qualified = fresh.qualify_capture_fixtures(source_raw_json, source_manifest)
    except Exception as exc:
        raise _error("source failed reviewed PR149 provider-native qualification") from exc
    by_id = {fixture.fixture_id: fixture for fixture in qualified}
    if len(by_id) != len(qualified):
        raise _error("provider-native replay returned duplicate fixture IDs")

    ledger, update_count = _history_ledger(
        legacy_bootstrap_projection_raw,
        reviewed_fresh_settlements,
    )
    holdout_start = control.holdout_start_utc()

    rows: list[CurrentUtcNativeShadowPredictionRow] = []
    for identity in current_bootstrap.fixtures:
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
                    kickoff_utc=identity.kickoff,
                    provider_primary_id=capture.provider_primary_id,
                    wrapper_id=capture.wrapper_id,
                    home_team_id=capture.home_team_id,
                    away_team_id=capture.away_team_id,
                    capture_observed_at=capture.capture_observed_at,
                    capture_manifest_sha256=capture.capture_manifest_sha256,
                    capture_raw_sha256=capture.capture_raw_sha256,
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
                kickoff_utc=identity.kickoff,
                provider_primary_id=selected.provider_primary_id,
                wrapper_id=selected.wrapper_id,
                home_team_id=selected.home_team_id,
                away_team_id=selected.away_team_id,
                capture_observed_at=selected.capture_observed_at,
                capture_manifest_sha256=selected.capture_manifest_sha256,
                capture_raw_sha256=selected.capture_raw_sha256,
                disposition=disposition,
                missing_feature_ids=missing,
                sealed_prediction=prediction,
                sealed_prediction_sha256=prediction_sha,
            )
        )

    ordered = tuple(sorted(rows, key=lambda row: (row.kickoff_utc, row.fixture_identifier)))
    return CurrentUtcNativeShadowPredictionHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS_READY,
        current_bootstrap_sha256=hashlib.sha256(bootstrap_raw).hexdigest(),
        candidate_bundle_sha256=candidate_sha,
        review_bundle_sha256=review_sha,
        source_manifest_sha256=sha256_data_matches_capture_manifest(source_manifest),
        source_raw_sha256=source_manifest.raw_sha256,
        holdout_start_utc=holdout_start,
        legacy_bootstrap_sha256=hashlib.sha256(legacy_bootstrap_projection_raw).hexdigest(),
        reviewed_fresh_settlement_count=len(reviewed_fresh_settlements),
        reviewed_fresh_legacy_update_count=update_count,
        rows=ordered,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        authority=_authority(),
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
    "CurrentUtcNativeShadowPredictionError",
    "CurrentUtcNativeShadowPredictionHandoff",
    "CurrentUtcNativeShadowPredictionRow",
    "build_current_fotmob_utc_native_shadow_prediction_handoff",
    "canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes",
    "sha256_current_fotmob_utc_native_shadow_prediction_handoff",
]
