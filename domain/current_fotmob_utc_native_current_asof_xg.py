"""Research-only current-as-of UTC-native xG inference for Current Shadow.

The frozen PR149 fresh-holdout seal remains unchanged: it may only seal captures
inside its reviewed 24h-to-60m window. Current Shadow deliberately reviews
fixtures with a different prospective horizon. This module reuses the same
reviewed UTC-native feature constructor and frozen xG rate math without minting
a ``SealedFreshPrediction`` outside that holdout window.

Inputs are exact reviewed PR149 history-ledger rows plus one exact qualified
current FotMob capture. When that narrower history cannot construct form/fatigue,
Current Shadow may use the separately verified paired-campaign research history.
Neither path grants production, pricing, selection, SportyBet or BET authority.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import os
from types import MappingProxyType
from typing import Any, Mapping

from domain import current_fotmob_fixture_review_policy as fixture_policy
from domain import current_shadow_paired_fotmob_history as paired_history
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import fotmob_utc_native_successor_feature_construction_qualification as utc_features


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-utc-native-current-asof-xg-v1"
STATUS = "RESEARCH_ONLY_CURRENT_AS_OF_XG"
COMPLETE = "CURRENT_AS_OF_RESEARCH_XG_COMPLETE"
MISSING_REVIEWED_FEATURES = "CURRENT_AS_OF_RESEARCH_XG_MISSING_REVIEWED_FEATURES"

_AUTHORITY = MappingProxyType(
    {
        "production_model": False,
        "production_probability": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CurrentAsOfXGError(ValueError):
    pass


class CurrentAsOfXGDisposition(str, enum.Enum):
    COMPLETE = COMPLETE
    MISSING_REVIEWED_FEATURES = MISSING_REVIEWED_FEATURES


def _error(message: str) -> CurrentAsOfXGError:
    return CurrentAsOfXGError(message)


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
        raise _error("canonical serialization failed") from exc


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be exact timezone-aware datetime")
    try:
        return value.astimezone(dt.timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(f"{label} is invalid") from exc


def _utc_text(value: dt.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _minimum_lead_seconds(policy_id: str) -> int:
    if policy_id == fixture_policy.SHADOW_POLICY_ID:
        return fixture_policy.SHADOW_MINIMUM_LEAD_SECONDS
    if policy_id == fixture_policy.POLICY_ID:
        return fixture_policy.DEFAULT_MINIMUM_LEAD_SECONDS
    raise _error("fixture review policy is not an exact reviewed current policy")


@dataclasses.dataclass(frozen=True)
class CurrentAsOfXGAssessment:
    schema_version: int
    dataset_name: str
    status: str
    disposition: CurrentAsOfXGDisposition
    fixture: fresh.QualifiedCaptureFixture
    fixture_review_policy_id: str
    history_prefix_sha256: str
    history_prefix_count: int
    feature_projection_sha256: str
    missing_feature_ids: tuple[str, ...]
    features: Mapping[str, float]
    rates: Mapping[str, float]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("assessment schema mismatch")
        if self.status != STATUS:
            raise _error("assessment status mismatch")
        if type(self.fixture) is not fresh.QualifiedCaptureFixture:
            raise _error("assessment fixture type mismatch")
        fixture = dataclasses.replace(self.fixture)
        _minimum_lead_seconds(self.fixture_review_policy_id)
        for value, label in (
            (self.history_prefix_sha256, "history_prefix_sha256"),
            (self.feature_projection_sha256, "feature_projection_sha256"),
        ):
            if (
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise _error(f"{label} must be exact lowercase SHA-256")
        if type(self.history_prefix_count) is not int or self.history_prefix_count < 0:
            raise _error("history_prefix_count must be exact non-negative integer")
        if (
            type(self.missing_feature_ids) is not tuple
            or tuple(sorted(set(self.missing_feature_ids))) != self.missing_feature_ids
        ):
            raise _error("missing_feature_ids must be sorted unique tuple")
        features = dict(self.features)
        rates = dict(self.rates)
        if self.disposition is CurrentAsOfXGDisposition.COMPLETE:
            if self.missing_feature_ids or set(features) != set(fresh._FEATURE_IDS):
                raise _error("complete current-as-of assessment feature contract changed")
            if set(rates) != {
                "native_home",
                "native_away",
                "elo_only_home",
                "elo_only_away",
                "calibrated_home",
                "calibrated_away",
            }:
                raise _error("complete current-as-of assessment rate contract changed")
            expected_rates = fresh._rates_from_features(features)
            if rates != expected_rates:
                raise _error("current-as-of rates differ from frozen xG rate math")
        else:
            if not self.missing_feature_ids or rates:
                raise _error("missing-feature current-as-of assessment changed")
        authority = dict(self.authority)
        if authority != dict(_AUTHORITY):
            raise _error("current-as-of authority changed")
        object.__setattr__(self, "fixture", fixture)
        object.__setattr__(self, "features", MappingProxyType(features))
        object.__setattr__(self, "rates", MappingProxyType(rates))
        object.__setattr__(self, "authority", MappingProxyType(authority))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "disposition": self.disposition.value,
            "fixture": self.fixture.to_dict(),
            "fixture_review_policy_id": self.fixture_review_policy_id,
            "history_prefix_sha256": self.history_prefix_sha256,
            "history_prefix_count": self.history_prefix_count,
            "feature_projection_sha256": self.feature_projection_sha256,
            "missing_feature_ids": list(self.missing_feature_ids),
            "features": dict(self.features),
            "rates": dict(self.rates),
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def _paired_fallback(
    *,
    prefix: tuple[fresh.FreshHistoryResult, ...],
    capture: fresh.QualifiedCaptureFixture,
    narrow_history_sha256: str,
) -> CurrentAsOfXGAssessment | None:
    if not os.environ.get(paired_history.ARTIFACT_ENV, ""):
        return None
    try:
        paired = paired_history.build_current_features_from_paired_history(
            history_prefix=prefix,
            selected_capture=capture,
        )
    except paired_history.CurrentShadowPairedHistoryError as exc:
        raise _error("paired current-history research fallback failed") from exc
    if paired.missing_feature_ids:
        return None
    values = dict(paired.features)
    combined_history_sha = hashlib.sha256(
        _canonical(
            {
                "narrow_history_prefix_sha256": narrow_history_sha256,
                "paired_history_identity_sha256": paired.history_identity_sha256,
                "paired_history_policy_id": paired_history.POLICY_ID,
            }
        )
    ).hexdigest()
    return CurrentAsOfXGAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS,
        disposition=CurrentAsOfXGDisposition.COMPLETE,
        fixture=capture,
        fixture_review_policy_id=fixture_policy.SHADOW_POLICY_ID,
        history_prefix_sha256=combined_history_sha,
        history_prefix_count=paired.history_row_count,
        feature_projection_sha256=paired.feature_projection_sha256,
        missing_feature_ids=(),
        features=values,
        rates=fresh._rates_from_features(values),
        authority=_AUTHORITY,
    )


def build_current_asof_xg_assessment(
    *,
    history_ledger: fresh.FreshHistoryLedger,
    selected_capture: fresh.QualifiedCaptureFixture,
    fixture_review_policy_id: str,
) -> CurrentAsOfXGAssessment:
    """Build current-as-of research xG without minting a fresh-holdout seal."""

    fresh.verify_reviewed_dependencies()
    if type(history_ledger) is not fresh.FreshHistoryLedger:
        raise _error("history_ledger must be exact FreshHistoryLedger")
    if history_ledger.bootstrap_projection_sha256 != fresh.BOOTSTRAP_PROJECTION_SHA256:
        raise _error("history ledger bootstrap identity changed")
    if type(selected_capture) is not fresh.QualifiedCaptureFixture:
        raise _error("selected_capture must be exact QualifiedCaptureFixture")
    capture = dataclasses.replace(selected_capture)
    minimum_lead = _minimum_lead_seconds(fixture_review_policy_id)
    lead = (capture.kickoff_utc - capture.capture_observed_at).total_seconds()
    if not math.isfinite(lead) or lead < minimum_lead:
        raise _error("current capture is outside the reviewed Current Shadow prospective lead")

    prefix = fresh._history_prefix(history_ledger.rows, target=capture)
    prefix_raw = fresh._constructor_prefix_bytes(prefix)
    target_row = {
        "source_namespace": fresh.SOURCE_NAMESPACE,
        "fixture_identifier": str(capture.fixture_id),
        "kickoff_utc": _utc_text(capture.kickoff_utc),
        "home_team_identifier": str(capture.home_team_id),
        "away_team_identifier": str(capture.away_team_id),
        "home_goals": 0,
        "away_goals": 0,
        "evidence_sha256": capture.capture_raw_sha256,
        "evidence_reference": (
            f"current-shadow-asof-capture:{capture.capture_manifest_sha256}:"
            f"{capture.fixture_id}"
        ),
    }
    constructor_rows = [item.constructor_row() for item in prefix]
    constructor_rows.append(target_row)
    try:
        projection_raw, _summary = utc_features.construct_utc_native_feature_projection(
            constructor_rows
        )
    except Exception as exc:
        raise _error("reviewed UTC-native feature constructor failed") from exc

    target_value: dict[str, Any] | None = None
    for line in projection_raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise _error("reviewed feature projection contains torn row")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("reviewed feature projection contains malformed row") from exc
        if line != fresh._canonical(value):
            raise _error("reviewed feature projection row is not canonical")
        if value.get("fixture_identifier") == str(capture.fixture_id):
            if target_value is not None:
                raise _error("reviewed feature projection duplicated target fixture")
            target_value = value
    if target_value is None:
        raise _error("reviewed feature projection omitted target fixture")

    if (
        target_value.get("source_namespace") != fresh.SOURCE_NAMESPACE
        or target_value.get("fixture_identifier") != str(capture.fixture_id)
        or target_value.get("home_team_identifier") != str(capture.home_team_id)
        or target_value.get("away_team_identifier") != str(capture.away_team_id)
        or fresh._parse_utc(target_value.get("kickoff_utc"), "projected target kickoff")
        != capture.kickoff_utc
    ):
        raise _error("reviewed feature projection target identity changed")
    freshness = target_value.get("historical_live_data_freshness")
    if (
        type(freshness) is not dict
        or freshness.get("status") != utc_features.HISTORICAL_FRESHNESS_STATUS
        or freshness.get("value") is not None
    ):
        raise _error("reviewed feature projection freshness semantics changed")

    values: dict[str, float] = {}
    missing: list[str] = []
    for key in ("home_elo", "away_elo"):
        is_missing, value = fresh._validated_target_feature(
            target_value,
            key,
            allowed_statuses=fresh._ELO_STATUSES,
            missing_allowed=False,
        )
        if is_missing or value is None:
            raise _error("reviewed Elo unexpectedly became missing")
        values[key] = value
    for key in ("home_form", "away_form", "fatigue"):
        is_missing, value = fresh._validated_target_feature(
            target_value,
            key,
            allowed_statuses=frozenset({fresh._FORM_STATUS}),
            missing_allowed=True,
        )
        if is_missing:
            missing.append(key)
        else:
            assert value is not None
            values[key] = value

    history_sha = hashlib.sha256(prefix_raw).hexdigest()
    projection_sha = hashlib.sha256(projection_raw).hexdigest()
    if missing:
        paired = _paired_fallback(
            prefix=prefix,
            capture=capture,
            narrow_history_sha256=history_sha,
        )
        if paired is not None:
            if paired.fixture_review_policy_id != fixture_review_policy_id:
                paired = dataclasses.replace(
                    paired,
                    fixture_review_policy_id=fixture_review_policy_id,
                )
            return paired
        return CurrentAsOfXGAssessment(
            schema_version=SCHEMA_VERSION,
            dataset_name=DATASET_NAME,
            status=STATUS,
            disposition=CurrentAsOfXGDisposition.MISSING_REVIEWED_FEATURES,
            fixture=capture,
            fixture_review_policy_id=fixture_review_policy_id,
            history_prefix_sha256=history_sha,
            history_prefix_count=len(prefix),
            feature_projection_sha256=projection_sha,
            missing_feature_ids=tuple(sorted(missing)),
            features=values,
            rates={},
            authority=_AUTHORITY,
        )

    rates = fresh._rates_from_features(values)
    return CurrentAsOfXGAssessment(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS,
        disposition=CurrentAsOfXGDisposition.COMPLETE,
        fixture=capture,
        fixture_review_policy_id=fixture_review_policy_id,
        history_prefix_sha256=history_sha,
        history_prefix_count=len(prefix),
        feature_projection_sha256=projection_sha,
        missing_feature_ids=(),
        features=values,
        rates=rates,
        authority=_AUTHORITY,
    )


__all__ = [
    "COMPLETE",
    "DATASET_NAME",
    "MISSING_REVIEWED_FEATURES",
    "SCHEMA_VERSION",
    "STATUS",
    "CurrentAsOfXGAssessment",
    "CurrentAsOfXGDisposition",
    "CurrentAsOfXGError",
    "build_current_asof_xg_assessment",
]
