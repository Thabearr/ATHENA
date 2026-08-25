from __future__ import annotations

import dataclasses
import datetime
import hashlib
import math
import socket
import urllib.request
from unittest.mock import patch

import pytest

import domain.fixture_state_v2 as fixture_state_v2

from domain.fixture_intelligence import (
    DATASET_NAME as INTELLIGENCE_DATASET_NAME,
    SCHEMA_VERSION as INTELLIGENCE_SCHEMA_VERSION,
    FixtureIntelligenceError,
    FixtureIntelligenceFact,
    IntelligenceCategory,
    IntelligenceFactStatus,
    SourceRole,
    build_snapshot,
    canonical_snapshot_bytes,
    sha256_bytes,
)
from domain.fixture_model_features import (
    ModelFeatureId,
    build_model_feature_snapshot,
)
from domain.fixture_state_v2 import (
    DATASET_NAME,
    EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION,
    FIXTURE_STATE_FIELD_REGISTRY,
    FIXTURE_STATE_FIELD_REGISTRY_SHA256,
    FIXTURE_STATE_FIELD_REGISTRY_VERSION,
    SCHEMA_VERSION,
    FixtureStateBlocker,
    FixtureStateEvidenceIdentity,
    FixtureStateFieldFamily,
    FixtureStateFieldId,
    FixtureStateFieldResolution,
    FixtureStateImplementationState,
    FixtureStateObservationMode,
    FixtureStateOfficialCorroboration,
    FixtureStateSourceClass,
    FixtureStateStatus,
    FixtureStateV2Error,
    FixtureStateV2Snapshot,
    FixtureStateValueType,
    build_fixture_state_v2_snapshot,
    canonical_fixture_state_v2_bytes,
    evaluate_required_fields,
    sha256_fixture_state_v2,
)


UTC = datetime.timezone.utc
KICKOFF = datetime.datetime(2026, 9, 5, 15, 0, tzinfo=UTC)
AS_OF = datetime.datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
OBSERVED = datetime.datetime(2026, 9, 5, 11, 30, tzinfo=UTC)
LEGACY_BINDINGS = {
    ModelFeatureId.HOME_FORM: (IntelligenceCategory.FORM, "home_form", 0.72),
    ModelFeatureId.AWAY_FORM: (IntelligenceCategory.FORM, "away_form", 0.61),
    ModelFeatureId.HOME_ELO: (IntelligenceCategory.PERFORMANCE, "home_elo", 1612),
    ModelFeatureId.AWAY_ELO: (IntelligenceCategory.PERFORMANCE, "away_elo", 1548),
    ModelFeatureId.FATIGUE: (IntelligenceCategory.SCHEDULE_LOAD, "fatigue", 0.23),
    ModelFeatureId.LIVE_DATA_FRESHNESS: (
        IntelligenceCategory.FIXTURE_CONTEXT,
        "live_data_freshness",
        0.95,
    ),
}


def _fact(
    category: IntelligenceCategory,
    field: str,
    value,
    *,
    status: IntelligenceFactStatus = IntelligenceFactStatus.SUPPORTED,
    observed_at: datetime.datetime = OBSERVED,
    marker: str = "a",
) -> FixtureIntelligenceFact:
    return FixtureIntelligenceFact(
        category=category,
        field=field,
        status=status,
        value=value,
        source_provider="PRESERVED_TEST_SOURCE",
        source_role=SourceRole.VERIFIED_EXTERNAL,
        source_reference=f"preserved:test:{category.value}:{field}:{marker}",
        observed_at=observed_at,
        evidence_file_path=f"evidence/test/{marker}.json",
        evidence_sha256=marker * 64,
        notes="Preserved test evidence only.",
    )


def _intelligence(*facts: FixtureIntelligenceFact, fixture: str = "fixture-229"):
    return build_snapshot(fixture, KICKOFF, AS_OF, list(facts))


def _state(*facts: FixtureIntelligenceFact, fixture: str = "fixture-229"):
    return build_fixture_state_v2_snapshot(_intelligence(*facts, fixture=fixture))


def _field(snapshot, field_id: FixtureStateFieldId):
    return snapshot.field_index[field_id]


def _evidence(
    *,
    field: str = "home_form",
    category: IntelligenceCategory = IntelligenceCategory.FORM,
) -> FixtureStateEvidenceIdentity:
    return FixtureStateEvidenceIdentity(
        category=category,
        field=field,
        fact_status=IntelligenceFactStatus.SUPPORTED,
        source_role=SourceRole.VERIFIED_EXTERNAL,
        observed_at=OBSERVED,
        evidence_sha256="e" * 64,
        source_provider="PRESERVED_TEST_SOURCE",
        source_reference="preserved:test:evidence",
    )


def _all_legacy_facts(
    status: IntelligenceFactStatus = IntelligenceFactStatus.SUPPORTED,
):
    return tuple(
        _fact(category, field, value, status=status, marker=str(index % 10))
        for index, (category, field, value) in enumerate(LEGACY_BINDINGS.values())
    )


def test_canonical_serialization_and_sha_are_deterministic() -> None:
    facts = _all_legacy_facts()
    first = _state(*facts)
    second = _state(*reversed(facts))

    assert canonical_fixture_state_v2_bytes(first) == canonical_fixture_state_v2_bytes(second)
    assert sha256_fixture_state_v2(first) == sha256_fixture_state_v2(second)
    assert first.canonical_sha256 == second.canonical_sha256
    assert hashlib.sha256(canonical_fixture_state_v2_bytes(first)).hexdigest() == first.canonical_sha256


def test_mutable_caller_input_cannot_mutate_snapshot_identity() -> None:
    weather = {"temperature_c": 18.0, "condition": "RAIN"}
    fact = _fact(IntelligenceCategory.WEATHER, "weather", weather)
    snapshot = _state(fact)
    before = snapshot.canonical_sha256

    weather["temperature_c"] = 99.0
    weather["condition"] = "CLEAR"

    assert snapshot.canonical_sha256 == before
    assert _field(snapshot, FixtureStateFieldId.WEATHER).status is FixtureStateStatus.MISSING


def test_future_source_fact_cannot_activate_unreviewed_field() -> None:
    weather = _fact(
        IntelligenceCategory.WEATHER,
        "weather",
        {"temperature_c": 18.0, "condition": "RAIN"},
    )

    resolution = _field(_state(weather), FixtureStateFieldId.WEATHER)

    assert resolution.status is FixtureStateStatus.MISSING
    assert resolution.value is None
    assert resolution.evidence == ()


def test_as_of_must_be_strictly_before_kickoff() -> None:
    with pytest.raises(FixtureIntelligenceError, match="strictly before kickoff"):
        build_snapshot("fixture-229", KICKOFF, KICKOFF, [])


def test_evidence_after_as_of_is_rejected_before_state_build() -> None:
    future = _fact(
        IntelligenceCategory.FORM,
        "home_form",
        0.7,
        observed_at=AS_OF + datetime.timedelta(seconds=1),
    )

    with pytest.raises(FixtureIntelligenceError, match="after as_of"):
        _intelligence(future)


def test_post_match_evidence_cannot_enter_pre_match_state() -> None:
    post_match = _fact(
        IntelligenceCategory.MATCH_CONTEXT,
        "post_match_result",
        "HOME_WIN",
        observed_at=KICKOFF + datetime.timedelta(hours=2),
    )

    with pytest.raises(FixtureIntelligenceError, match="after as_of"):
        _intelligence(post_match)


def test_registry_is_complete_unique_and_every_field_has_one_resolution() -> None:
    snapshot = _state()
    registry_ids = tuple(item.field_id for item in FIXTURE_STATE_FIELD_REGISTRY)
    resolution_ids = tuple(item.field_id for item in snapshot.fields)

    assert len(registry_ids) == len(FixtureStateFieldId) == 37
    assert len(set(registry_ids)) == len(registry_ids)
    assert resolution_ids == tuple(sorted(FixtureStateFieldId, key=lambda item: item.value))
    assert all(item.status in FixtureStateStatus for item in snapshot.fields)


def test_missing_numeric_and_categorical_context_remain_null_without_defaults() -> None:
    snapshot = _state()

    for field_id in (
        FixtureStateFieldId.HOME_ELO,
        FixtureStateFieldId.HOME_FORM,
        FixtureStateFieldId.FATIGUE,
        FixtureStateFieldId.VENUE,
        FixtureStateFieldId.HOME_LINEUP_STATE,
    ):
        resolution = _field(snapshot, field_id)
        assert resolution.status is FixtureStateStatus.MISSING
        assert resolution.value is None
        assert resolution.evidence == ()


@pytest.mark.parametrize(
    ("status", "expected_blocker"),
    (
        (IntelligenceFactStatus.STALE, FixtureStateBlocker.STALE_EVIDENCE_PRESENT),
        (
            IntelligenceFactStatus.UNVERIFIED,
            FixtureStateBlocker.UNVERIFIED_EVIDENCE_PRESENT,
        ),
    ),
)
def test_stale_and_unverified_evidence_are_blocked_and_retained(
    status: IntelligenceFactStatus,
    expected_blocker: FixtureStateBlocker,
) -> None:
    fact = _fact(IntelligenceCategory.FORM, "home_form", 0.7, status=status)
    resolution = _field(_state(fact), FixtureStateFieldId.HOME_FORM)

    assert resolution.status is FixtureStateStatus.BLOCKED
    assert resolution.value is None
    assert expected_blocker in resolution.blockers
    assert FixtureStateBlocker.NO_SUPPORTED_EVIDENCE in resolution.blockers
    assert resolution.evidence_sha256s == ("a" * 64,)


def test_conflicting_evidence_is_blocked_and_retains_both_identities() -> None:
    first = _fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="a")
    second = _fact(IntelligenceCategory.FORM, "home_form", 0.8, marker="b")
    resolution = _field(_state(first, second), FixtureStateFieldId.HOME_FORM)

    assert resolution.status is FixtureStateStatus.BLOCKED
    assert resolution.blockers == (FixtureStateBlocker.CONFLICTED_EVIDENCE,)
    assert resolution.evidence_sha256s == ("a" * 64, "b" * 64)


def test_invalid_supported_value_is_blocked_not_disguised_as_missing() -> None:
    invalid = _fact(IntelligenceCategory.PERFORMANCE, "home_elo", "not-a-number")
    resolution = _field(_state(invalid), FixtureStateFieldId.HOME_ELO)

    assert resolution.status is FixtureStateStatus.BLOCKED
    assert resolution.blockers == (FixtureStateBlocker.INVALID_SUPPORTED_VALUE,)
    assert resolution.evidence_sha256s == ("a" * 64,)


def test_available_resolution_requires_supported_evidence_identity() -> None:
    with pytest.raises(FixtureStateV2Error, match="supported evidence identity"):
        FixtureStateFieldResolution(
            field_id=FixtureStateFieldId.HOME_FORM,
            status=FixtureStateStatus.AVAILABLE,
            value=0.7,
            blockers=(),
            evidence=(),
        )


def test_future_tactical_field_rejects_manual_available_from_form_evidence() -> None:
    with pytest.raises(FixtureStateV2Error, match="no currently approved"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_TACTICAL_IDENTITY,
            FixtureStateStatus.AVAILABLE,
            "LOW_EVENT",
            (),
            (_evidence(),),
        )


def test_mapped_field_rejects_wrong_evidence_category() -> None:
    with pytest.raises(FixtureStateV2Error, match="registered source binding"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_FORM,
            FixtureStateStatus.AVAILABLE,
            0.7,
            (),
            (_evidence(category=IntelligenceCategory.LINEUP),),
        )


def test_mapped_field_rejects_wrong_evidence_field() -> None:
    with pytest.raises(FixtureStateV2Error, match="registered source binding"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_FORM,
            FixtureStateStatus.AVAILABLE,
            0.7,
            (),
            (_evidence(field="away_form"),),
        )


def test_snapshot_direct_construction_cannot_forge_bound_upstream_evidence() -> None:
    upstream = _intelligence()
    built = build_fixture_state_v2_snapshot(upstream)
    forged_home_form = FixtureStateFieldResolution(
        FixtureStateFieldId.HOME_FORM,
        FixtureStateStatus.AVAILABLE,
        0.7,
        (),
        (_evidence(),),
    )
    forged_fields = tuple(
        forged_home_form if item.field_id is FixtureStateFieldId.HOME_FORM else item
        for item in built.fields
    )

    with pytest.raises(FixtureStateV2Error, match="builder-only"):
        FixtureStateV2Snapshot(
            schema_version=built.schema_version,
            dataset_name=built.dataset_name,
            field_registry_version=built.field_registry_version,
            field_registry_sha256=built.field_registry_sha256,
            fixture_identifier=built.fixture_identifier,
            kickoff=built.kickoff,
            as_of=built.as_of,
            source_snapshot_dataset_name=built.source_snapshot_dataset_name,
            source_snapshot_schema_version=built.source_snapshot_schema_version,
            source_snapshot_sha256=built.source_snapshot_sha256,
            fields=forged_fields,
            safety=built.safety,
        )

    assert _field(built, FixtureStateFieldId.HOME_FORM).status is FixtureStateStatus.MISSING
    eligibility = evaluate_required_fields(
        built,
        (FixtureStateFieldId.HOME_FORM,),
    )
    assert eligibility.usable is False
    assert eligibility.missing_field_ids == (FixtureStateFieldId.HOME_FORM,)


def test_matching_but_absent_evidence_cannot_be_injected_after_construction() -> None:
    built = _state()
    forged_home_form = FixtureStateFieldResolution(
        FixtureStateFieldId.HOME_FORM,
        FixtureStateStatus.AVAILABLE,
        0.7,
        (),
        (_evidence(),),
    )
    forged_fields = tuple(
        forged_home_form if item.field_id is FixtureStateFieldId.HOME_FORM else item
        for item in built.fields
    )

    with pytest.raises(FixtureStateV2Error, match="builder-only"):
        dataclasses.replace(built, fields=forged_fields)

    assert evaluate_required_fields(
        built,
        (FixtureStateFieldId.HOME_FORM,),
    ).usable is False


@pytest.mark.parametrize(
    ("field_id", "value"),
    (
        (FixtureStateFieldId.HOME_ATTACK_STRENGTH, 1.1),
        (FixtureStateFieldId.HOME_MANAGER_REGIME_IDENTITY, "regime-1"),
        (FixtureStateFieldId.HOME_LINEUP_STATE, "predicted"),
        (FixtureStateFieldId.HOME_TRAVEL_CONTEXT, {"distance_km": 100.0}),
        (FixtureStateFieldId.WEATHER, {"condition": "RAIN"}),
        (FixtureStateFieldId.VENUE, "venue-1"),
        (FixtureStateFieldId.REFEREE, "referee-1"),
        (FixtureStateFieldId.COMPETITION_STAGE, "ROUND_1"),
    ),
)
def test_future_field_rejects_manual_available_even_with_supported_evidence(
    field_id: FixtureStateFieldId,
    value,
) -> None:
    with pytest.raises(FixtureStateV2Error, match="no currently approved"):
        FixtureStateFieldResolution(
            field_id,
            FixtureStateStatus.AVAILABLE,
            value,
            (),
            (_evidence(),),
        )


@pytest.mark.parametrize("value", (math.nan, math.inf, -math.inf))
def test_nan_and_infinity_are_rejected(value: float) -> None:
    with pytest.raises(FixtureStateV2Error, match="NaN or Infinity"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_FORM,
            FixtureStateStatus.AVAILABLE,
            value,
            (),
            (_evidence(),),
        )


def test_unsupported_value_types_are_rejected() -> None:
    with pytest.raises(FixtureStateV2Error, match="numeric scalar"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_FORM,
            FixtureStateStatus.AVAILABLE,
            [0.7],
            (),
            (_evidence(),),
        )
    with pytest.raises(FixtureStateV2Error, match="exact boolean"):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_LINEUP_CONFIRMED,
            FixtureStateStatus.AVAILABLE,
            1,
            (),
            (_evidence(field="home_lineup_confirmed", category=IntelligenceCategory.LINEUP),),
        )


@pytest.mark.parametrize(
    "value",
    (
        (("b", 1), ("a", 2)),
        (("a", 1), ("a", 2)),
        (("nested", {"forbidden": True}),),
    ),
)
def test_duplicate_unordered_or_nested_structures_fail_closed(value) -> None:
    with pytest.raises(FixtureStateV2Error):
        FixtureStateFieldResolution(
            FixtureStateFieldId.HOME_AVAILABILITY_STATE,
            FixtureStateStatus.AVAILABLE,
            value,
            (),
            (_evidence(field="home_availability_state", category=IntelligenceCategory.AVAILABILITY),),
        )


def test_source_snapshot_identity_is_exactly_sha_bound() -> None:
    intelligence = _intelligence(
        _fact(IntelligenceCategory.FORM, "home_form", 0.7)
    )
    state = build_fixture_state_v2_snapshot(intelligence)
    expected = sha256_bytes(canonical_snapshot_bytes(intelligence))

    assert state.source_snapshot_dataset_name == INTELLIGENCE_DATASET_NAME
    assert state.source_snapshot_schema_version == INTELLIGENCE_SCHEMA_VERSION
    assert state.source_snapshot_sha256 == expected
    with pytest.raises(FixtureStateV2Error, match="builder-only"):
        dataclasses.replace(state, source_snapshot_sha256="f" * 64)


def test_altering_upstream_snapshot_changes_v2_source_identity() -> None:
    first = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="a"))
    second = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="b"))

    assert first.source_snapshot_sha256 != second.source_snapshot_sha256
    assert first.canonical_sha256 != second.canonical_sha256


@pytest.mark.parametrize(
    "intelligence_status",
    (
        IntelligenceFactStatus.SUPPORTED,
        IntelligenceFactStatus.STALE,
        None,
    ),
)
def test_legacy_six_status_value_and_evidence_semantics_match_v1(
    intelligence_status,
) -> None:
    facts = () if intelligence_status is None else _all_legacy_facts(intelligence_status)
    intelligence = _intelligence(*facts)
    v1 = build_model_feature_snapshot(intelligence)
    v2 = build_fixture_state_v2_snapshot(intelligence)
    v1_index = {item.feature_id: item for item in v1.features}

    for feature_id in ModelFeatureId:
        v1_resolution = v1_index[feature_id]
        v2_resolution = _field(v2, FixtureStateFieldId(feature_id.value))
        assert v2_resolution.status.value == v1_resolution.status.value
        assert v2_resolution.value == v1_resolution.value
        assert v2_resolution.evidence_sha256s == v1_resolution.evidence_sha256s
        assert tuple(item.value for item in v2_resolution.blockers) == tuple(
            item.value for item in v1_resolution.blockers
        )


def test_legacy_six_conflict_and_invalid_value_match_v1_blocking() -> None:
    facts = (
        _fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="a"),
        _fact(IntelligenceCategory.FORM, "home_form", 0.8, marker="b"),
        _fact(IntelligenceCategory.PERFORMANCE, "home_elo", "invalid", marker="c"),
    )
    intelligence = _intelligence(*facts)
    v1 = build_model_feature_snapshot(intelligence)
    v2 = build_fixture_state_v2_snapshot(intelligence)
    v1_index = {item.feature_id: item for item in v1.features}

    for feature_id in (ModelFeatureId.HOME_FORM, ModelFeatureId.HOME_ELO):
        left = v1_index[feature_id]
        right = _field(v2, FixtureStateFieldId(feature_id.value))
        assert right.status.value == left.status.value == "BLOCKED"
        assert tuple(item.value for item in right.blockers) == tuple(
            item.value for item in left.blockers
        )


def test_tactical_slots_never_default_or_activate_from_team_names() -> None:
    facts = (
        _fact(IntelligenceCategory.FIXTURE_CONTEXT, "home_team", "Getafe"),
        _fact(IntelligenceCategory.FIXTURE_CONTEXT, "away_team", "Racing"),
    )
    snapshot = _state(*facts, fixture="Getafe-v-Racing")

    for field_id in (
        FixtureStateFieldId.HOME_TACTICAL_IDENTITY,
        FixtureStateFieldId.AWAY_TACTICAL_IDENTITY,
        FixtureStateFieldId.HOME_MANAGER_REGIME_IDENTITY,
        FixtureStateFieldId.AWAY_MANAGER_REGIME_IDENTITY,
    ):
        resolution = _field(snapshot, field_id)
        assert resolution.status is FixtureStateStatus.MISSING
        assert resolution.value is None


def test_pr197_lineup_sentinel_cannot_activate_v2_lineup_or_availability() -> None:
    pr197_sentinel = _fact(
        IntelligenceCategory.LINEUP,
        "source_lineup_type",
        "predicted",
        marker="1",
    )
    snapshot = _state(pr197_sentinel)

    for field_id in (
        FixtureStateFieldId.HOME_AVAILABILITY_STATE,
        FixtureStateFieldId.AWAY_AVAILABILITY_STATE,
        FixtureStateFieldId.HOME_LINEUP_STATE,
        FixtureStateFieldId.AWAY_LINEUP_STATE,
        FixtureStateFieldId.HOME_LINEUP_CONFIRMED,
        FixtureStateFieldId.AWAY_LINEUP_CONFIRMED,
        FixtureStateFieldId.HOME_LINEUP_FRESHNESS,
        FixtureStateFieldId.AWAY_LINEUP_FRESHNESS,
    ):
        resolution = _field(snapshot, field_id)
        assert resolution.status is FixtureStateStatus.MISSING
        assert resolution.value is None
        assert resolution.evidence == ()


def test_exact_unavailable_counts_do_not_manufacture_generic_v2_states() -> None:
    snapshot = _state(
        _fact(
            IntelligenceCategory.AVAILABILITY,
            "home_unavailable_player_count",
            1.0,
            marker="1",
        ),
        _fact(
            IntelligenceCategory.AVAILABILITY,
            "away_unavailable_player_count",
            5.0,
            marker="5",
        ),
        _fact(
            IntelligenceCategory.LINEUP,
            "home_lineup_state",
            "UNVERIFIED_LINEUP_STATE",
            status=IntelligenceFactStatus.UNVERIFIED,
            marker="2",
        ),
        _fact(
            IntelligenceCategory.LINEUP,
            "away_lineup_state",
            "UNVERIFIED_LINEUP_STATE",
            status=IntelligenceFactStatus.UNVERIFIED,
            marker="3",
        ),
    )

    for field_id in (
        FixtureStateFieldId.HOME_AVAILABILITY_STATE,
        FixtureStateFieldId.AWAY_AVAILABILITY_STATE,
        FixtureStateFieldId.HOME_LINEUP_STATE,
        FixtureStateFieldId.AWAY_LINEUP_STATE,
        FixtureStateFieldId.HOME_LINEUP_CONFIRMED,
        FixtureStateFieldId.AWAY_LINEUP_CONFIRMED,
        FixtureStateFieldId.HOME_LINEUP_FRESHNESS,
        FixtureStateFieldId.AWAY_LINEUP_FRESHNESS,
    ):
        assert _field(snapshot, field_id).status is FixtureStateStatus.MISSING


def test_required_field_evaluation_reports_missing_blocked_and_exact_success() -> None:
    facts = (
        _fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="a"),
        _fact(
            IntelligenceCategory.PERFORMANCE,
            "home_elo",
            1600,
            status=IntelligenceFactStatus.STALE,
            marker="b",
        ),
    )
    snapshot = _state(*facts)

    missing = evaluate_required_fields(snapshot, (FixtureStateFieldId.VENUE,))
    blocked = evaluate_required_fields(snapshot, (FixtureStateFieldId.HOME_ELO,))
    available = evaluate_required_fields(snapshot, (FixtureStateFieldId.HOME_FORM,))
    mixed = evaluate_required_fields(
        snapshot,
        (
            FixtureStateFieldId.HOME_FORM,
            FixtureStateFieldId.HOME_ELO,
            FixtureStateFieldId.VENUE,
        ),
    )

    assert missing.usable is False and missing.missing_field_ids == (FixtureStateFieldId.VENUE,)
    assert blocked.usable is False and blocked.blocked_field_ids == (FixtureStateFieldId.HOME_ELO,)
    assert available.usable is True
    assert available.available_field_ids == (FixtureStateFieldId.HOME_FORM,)
    assert mixed.usable is False
    assert mixed.available_field_ids == (FixtureStateFieldId.HOME_FORM,)
    assert mixed.blocked_field_ids == (FixtureStateFieldId.HOME_ELO,)
    assert mixed.missing_field_ids == (FixtureStateFieldId.VENUE,)


def test_requirement_evaluation_rejects_duplicates() -> None:
    snapshot = _state()
    with pytest.raises(FixtureStateV2Error, match="duplicates"):
        evaluate_required_fields(
            snapshot,
            (FixtureStateFieldId.HOME_FORM, FixtureStateFieldId.HOME_FORM),
        )


def test_coverage_counts_and_ids_are_deterministic() -> None:
    snapshot = _state(
        _fact(IntelligenceCategory.FORM, "home_form", 0.7, marker="a"),
        _fact(
            IntelligenceCategory.PERFORMANCE,
            "home_elo",
            1600,
            status=IntelligenceFactStatus.STALE,
            marker="b",
        ),
    )
    coverage = snapshot.coverage

    assert coverage.total_registered_fields == 37
    assert coverage.available_count == 1
    assert coverage.blocked_count == 1
    assert coverage.missing_count == 35
    assert coverage.available_ids == (FixtureStateFieldId.HOME_FORM,)
    assert coverage.blocked_ids == (FixtureStateFieldId.HOME_ELO,)
    assert coverage.available_count + coverage.missing_count + coverage.blocked_count == 37
    assert snapshot.to_dict()["coverage"] == coverage.to_dict()


def test_no_odds_prices_or_bookmaker_probabilities_enter_registry_or_state() -> None:
    forbidden_tokens = ("odds", "price", "bookmaker", "implied_probability")
    assert not any(
        token in definition.field_id.value
        for definition in FIXTURE_STATE_FIELD_REGISTRY
        for token in forbidden_tokens
    )
    snapshot = _state(
        _fact(IntelligenceCategory.FIXTURE_CONTEXT, "bookmaker_odds", 2.1)
    )
    assert all(
        evidence.field != "bookmaker_odds"
        for resolution in snapshot.fields
        for evidence in resolution.evidence
    )


def test_all_authority_flags_are_explicit_false() -> None:
    snapshot = _state()
    assert snapshot.safety
    assert set(snapshot.safety.values()) == {False}
    assert {
        "network_acquisition_authorized",
        "provider_acquisition_authorized",
        "probability_inference_authorized",
        "probability_adjustment_authorized",
        "model_promotion_authorized",
        "calibration_authorized",
        "bookmaker_pricing_authorized",
        "market_activation_authorized",
        "selection_authorized",
        "accumulator_authorized",
        "production_approval_authorized",
        "bet_authorized",
    } == set(snapshot.safety)


def test_builder_performs_no_network_or_provider_acquisition() -> None:
    intelligence = _intelligence(
        _fact(IntelligenceCategory.FORM, "home_form", 0.7)
    )
    with patch.object(socket, "create_connection", side_effect=AssertionError("network")), patch.object(
        urllib.request,
        "urlopen",
        side_effect=AssertionError("network"),
    ):
        snapshot = build_fixture_state_v2_snapshot(intelligence)

    assert _field(snapshot, FixtureStateFieldId.HOME_FORM).status is FixtureStateStatus.AVAILABLE


def test_registry_documents_type_source_derivation_and_expectation_for_every_field() -> None:
    serialized = [item.to_dict() for item in FIXTURE_STATE_FIELD_REGISTRY]
    assert all(item["family"] for item in serialized)
    assert all(item["value_type"] in {value.value for value in FixtureStateValueType} for item in serialized)
    assert all(item["derivation"] for item in serialized)
    assert all(item["availability_expectation"] for item in serialized)
    assert all(item["source_plan"]["preferred_source_class"] for item in serialized)
    assert all(item["source_plan"]["observation_mode"] for item in serialized)
    assert all(type(item["source_plan"]["currently_reviewed_path_exists"]) is bool for item in serialized)
    assert all(item["source_plan"]["implementation_state"] for item in serialized)
    assert all(item["source_plan"]["future_work_required"] for item in serialized)
    assert DATASET_NAME == "athena-fixture-state-v2"
    assert SCHEMA_VERSION == 2


def test_source_strategy_is_explicit_and_does_not_claim_preference_as_coverage() -> None:
    by_id = {item.field_id: item.source_plan for item in FIXTURE_STATE_FIELD_REGISTRY}

    assert by_id[FixtureStateFieldId.HOME_FORM].preferred_source_class is FixtureStateSourceClass.FOTMOB_PRIMARY
    assert by_id[FixtureStateFieldId.HOME_FORM].implementation_state is FixtureStateImplementationState.CURRENTLY_MAPPABLE
    assert by_id[FixtureStateFieldId.HOME_ATTACK_STRENGTH].preferred_source_class is FixtureStateSourceClass.ATHENA_DERIVED
    assert by_id[FixtureStateFieldId.HOME_ATTACK_STRENGTH].observation_mode is FixtureStateObservationMode.ATHENA_DERIVED
    assert by_id[FixtureStateFieldId.HOME_ATTACK_STRENGTH].currently_reviewed_path_exists is False
    assert by_id[FixtureStateFieldId.HOME_TACTICAL_IDENTITY].preferred_source_class is FixtureStateSourceClass.ATHENA_DERIVED
    assert by_id[FixtureStateFieldId.HOME_TACTICAL_IDENTITY].implementation_state is FixtureStateImplementationState.FUTURE_DERIVED
    assert by_id[FixtureStateFieldId.WEATHER].preferred_source_class is FixtureStateSourceClass.SPECIALIST_EXTERNAL
    assert by_id[FixtureStateFieldId.WEATHER].currently_reviewed_path_exists is False
    assert by_id[FixtureStateFieldId.WEATHER].implementation_state is FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED
    assert by_id[FixtureStateFieldId.HOME_LINEUP_STATE].implementation_state is FixtureStateImplementationState.PARTIALLY_PROVEN_PENDING_V2_ADAPTER
    assert by_id[FixtureStateFieldId.HOME_LINEUP_STATE].currently_reviewed_path_exists is False
    assert by_id[FixtureStateFieldId.HOME_LINEUP_STATE].official_corroboration is FixtureStateOfficialCorroboration.MAY_BE_REQUIRED_BY_FUTURE_POLICY

    mapped_ids = {
        item.field_id
        for item in FIXTURE_STATE_FIELD_REGISTRY
        if item.source_category is not None
    }
    assert mapped_ids == {
        FixtureStateFieldId.HOME_FORM,
        FixtureStateFieldId.AWAY_FORM,
        FixtureStateFieldId.HOME_ELO,
        FixtureStateFieldId.AWAY_ELO,
        FixtureStateFieldId.FATIGUE,
        FixtureStateFieldId.LIVE_DATA_FRESHNESS,
    }


def test_discovery_only_evidence_cannot_create_available_state() -> None:
    discovery = dataclasses.replace(
        _fact(
            IntelligenceCategory.FORM,
            "home_form",
            0.8,
            status=IntelligenceFactStatus.UNVERIFIED,
        ),
        source_role=SourceRole.DISCOVERY_ONLY,
    )

    resolution = _field(_state(discovery), FixtureStateFieldId.HOME_FORM)

    assert resolution.status is FixtureStateStatus.BLOCKED
    assert resolution.value is None
    assert resolution.blockers == (
        FixtureStateBlocker.NO_SUPPORTED_EVIDENCE,
        FixtureStateBlocker.UNVERIFIED_EVIDENCE_PRESENT,
    )
    assert resolution.evidence[0].source_role is SourceRole.DISCOVERY_ONLY


def test_source_coverage_registry_is_deterministic_but_not_state_identity() -> None:
    first = [item.to_dict() for item in FIXTURE_STATE_FIELD_REGISTRY]
    second = [item.to_dict() for item in reversed(tuple(reversed(FIXTURE_STATE_FIELD_REGISTRY)))]
    assert first == second
    assert len(first) == len(FixtureStateFieldId) == 37

    snapshot = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))
    before_sha = snapshot.canonical_sha256
    before_identity_bytes = canonical_fixture_state_v2_bytes(snapshot)
    before_coverage = snapshot.to_dict()["source_coverage"]
    changed_registry = tuple(
        dataclasses.replace(
            definition,
            source_plan=dataclasses.replace(
                definition.source_plan,
                currently_reviewed_path_exists=True,
                implementation_state=FixtureStateImplementationState.FUTURE_SOURCE_REQUIRED,
                future_work_required="Changed backlog wording outside state identity.",
            ),
        )
        if definition.field_id is FixtureStateFieldId.HOME_LINEUP_STATE
        else definition
        for definition in FIXTURE_STATE_FIELD_REGISTRY
    )

    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY",
        changed_registry,
    ):
        rebuilt = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))
        assert snapshot.canonical_sha256 == before_sha
        assert canonical_fixture_state_v2_bytes(snapshot) == before_identity_bytes
        assert rebuilt.canonical_sha256 == before_sha
        assert rebuilt.field_registry_sha256 == snapshot.field_registry_sha256
        assert snapshot.to_dict()["source_coverage"] != before_coverage


def _registry_with_changed_home_form_family():
    return tuple(
        dataclasses.replace(
            definition,
            family=FixtureStateFieldFamily.CONTEXT,
        )
        if definition.field_id is FixtureStateFieldId.HOME_FORM
        else definition
        for definition in FIXTURE_STATE_FIELD_REGISTRY
    )


def test_live_stable_registry_mutation_cannot_rewrite_existing_snapshot() -> None:
    snapshot = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))
    before_sha = snapshot.canonical_sha256
    before_bytes = canonical_fixture_state_v2_bytes(snapshot)
    changed_registry = _registry_with_changed_home_form_family()

    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY",
        changed_registry,
    ):
        assert snapshot.canonical_sha256 == before_sha
        assert canonical_fixture_state_v2_bytes(snapshot) == before_bytes
        with pytest.raises(FixtureStateV2Error, match="independently pinned"):
            _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))


def test_would_be_live_sha_cannot_bypass_independent_v1_pin() -> None:
    changed_registry = _registry_with_changed_home_form_family()
    would_be_sha256 = fixture_state_v2._field_registry_sha256(
        changed_registry,
        FIXTURE_STATE_FIELD_REGISTRY_VERSION,
    )

    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY",
        changed_registry,
    ), patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY_SHA256",
        would_be_sha256,
    ):
        with pytest.raises(FixtureStateV2Error, match="independently pinned"):
            _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))


def test_unknown_registry_version_without_independent_pin_fails_closed() -> None:
    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY_VERSION",
        FIXTURE_STATE_FIELD_REGISTRY_VERSION + 1,
    ):
        with pytest.raises(FixtureStateV2Error, match="no independently pinned"):
            _state()


def test_deliberate_stable_registry_change_requires_new_version_and_pinned_identity() -> None:
    upstream_fact = _fact(IntelligenceCategory.FORM, "home_form", 0.7)
    original = _state(upstream_fact)
    changed_registry = _registry_with_changed_home_form_family()
    next_version = FIXTURE_STATE_FIELD_REGISTRY_VERSION + 1
    next_sha256 = (
        "d2d01cfd42fa82bc053511e513122958d96fef772ebf3fd6e45ccb29e15f88d1"
    )
    assert (
        fixture_state_v2._field_registry_sha256(changed_registry, next_version)
        == next_sha256
    )
    reviewed_pins = {
        **EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION,
        next_version: next_sha256,
    }

    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY",
        changed_registry,
    ), patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY_VERSION",
        next_version,
    ), patch.object(
        fixture_state_v2,
        "EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION",
        reviewed_pins,
    ):
        changed = _state(upstream_fact)

    assert changed.field_registry_version == next_version
    assert changed.field_registry_sha256 == next_sha256
    assert changed.canonical_sha256 != original.canonical_sha256
    assert original.field_registry_version == FIXTURE_STATE_FIELD_REGISTRY_VERSION
    assert original.field_registry_sha256 == FIXTURE_STATE_FIELD_REGISTRY_SHA256


def test_frozen_field_registry_identity_is_deterministic() -> None:
    expected = fixture_state_v2._field_registry_sha256(
        FIXTURE_STATE_FIELD_REGISTRY,
        FIXTURE_STATE_FIELD_REGISTRY_VERSION,
    )
    first = _state()
    second = _state()

    assert EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION == {
        1: "330e81a3fd8dc88c8fee98544d7f63e9d429c43c5d32ca761da5227e34de588a"
    }
    assert expected == FIXTURE_STATE_FIELD_REGISTRY_SHA256
    assert first.field_registry_version == second.field_registry_version == 1
    assert first.field_registry_sha256 == second.field_registry_sha256 == expected


def test_existing_resolution_serialization_ignores_live_definition_lookup() -> None:
    snapshot = _state(_fact(IntelligenceCategory.FORM, "home_form", 0.7))
    home_form = _field(snapshot, FixtureStateFieldId.HOME_FORM)
    before_resolution = home_form.to_dict()
    before_bytes = canonical_fixture_state_v2_bytes(snapshot)
    before_sha256 = snapshot.canonical_sha256
    changed_lookup = dict(fixture_state_v2._DEFINITION_BY_ID)
    changed_lookup[FixtureStateFieldId.HOME_FORM] = dataclasses.replace(
        changed_lookup[FixtureStateFieldId.HOME_FORM],
        value_type=FixtureStateValueType.STRUCTURED_RECORD,
    )

    with patch.object(fixture_state_v2, "_DEFINITION_BY_ID", changed_lookup):
        assert home_form.to_dict() == before_resolution
        assert canonical_fixture_state_v2_bytes(snapshot) == before_bytes
        assert snapshot.canonical_sha256 == before_sha256


def test_existing_structured_resolution_serialization_is_self_contained() -> None:
    next_version = FIXTURE_STATE_FIELD_REGISTRY_VERSION + 1
    changed_registry = tuple(
        dataclasses.replace(
            definition,
            value_type=FixtureStateValueType.STRUCTURED_RECORD,
        )
        if definition.field_id is FixtureStateFieldId.HOME_FORM
        else definition
        for definition in FIXTURE_STATE_FIELD_REGISTRY
    )
    changed_lookup = {
        definition.field_id: definition for definition in changed_registry
    }
    next_sha256 = (
        "b3b1e6ac33661cc4ef82a9753c71647a30323c382d611e50186454f133e0dc31"
    )
    assert (
        fixture_state_v2._field_registry_sha256(changed_registry, next_version)
        == next_sha256
    )
    reviewed_pins = {
        **EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION,
        next_version: next_sha256,
    }
    structured_fact = _fact(
        IntelligenceCategory.FORM,
        "home_form",
        {"form_id": "preserved-form", "sample_size": 5},
    )

    with patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY",
        changed_registry,
    ), patch.object(
        fixture_state_v2,
        "_DEFINITION_BY_ID",
        changed_lookup,
    ), patch.object(
        fixture_state_v2,
        "FIXTURE_STATE_FIELD_REGISTRY_VERSION",
        next_version,
    ), patch.object(
        fixture_state_v2,
        "EXPECTED_FIXTURE_STATE_FIELD_REGISTRY_SHA256_BY_VERSION",
        reviewed_pins,
    ):
        snapshot = _state(structured_fact)
        before_resolution = _field(
            snapshot,
            FixtureStateFieldId.HOME_FORM,
        ).to_dict()
        before_bytes = canonical_fixture_state_v2_bytes(snapshot)
        before_sha256 = snapshot.canonical_sha256

    assert before_resolution["value"] == {
        "form_id": "preserved-form",
        "sample_size": 5.0,
    }
    assert (
        _field(snapshot, FixtureStateFieldId.HOME_FORM).to_dict()
        == before_resolution
    )
    assert canonical_fixture_state_v2_bytes(snapshot) == before_bytes
    assert snapshot.canonical_sha256 == before_sha256
