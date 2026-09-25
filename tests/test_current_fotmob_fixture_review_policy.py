from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import inspect

import pytest

import domain.fotmob_fixture_candidates as candidate_module
import domain.current_shadow_fotmob_international_source_identity as international_identity
import domain.current_fotmob_fixture_review_policy as review_policy_module
from domain.current_fotmob_fixture_review_policy import (
    DEFAULT_MAX_SOURCE_AGE_SECONDS,
    DEFAULT_MINIMUM_LEAD_SECONDS,
    POLICY_ID,
    REVIEWER_REFERENCE,
    SHADOW_MINIMUM_LEAD_SECONDS,
    SHADOW_POLICY_ID,
    SHADOW_REVIEWER_REFERENCE,
    CurrentFotMobFixtureReviewPolicyError,
    build_current_fotmob_fixture_review_policy_result,
    build_current_shadow_fotmob_fixture_review_policy_result,
    canonical_current_fotmob_fixture_review_policy_result_bytes,
)
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION,
)
from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition
from domain.fotmob_fixture_candidates import (
    DATASET_NAME as CANDIDATE_DATASET_NAME,
    SCHEMA_VERSION as CANDIDATE_SCHEMA_VERSION,
    SOURCE_NAME,
    FixtureCandidateReviewStatus,
    FotMobFixtureCandidate,
    FotMobFixtureCandidateBundle,
    FotMobFixtureCandidateSource,
)


UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
REVIEWED = dt.datetime(2026, 8, 27, 7, 5, tzinfo=UTC)
RAW = b'{"leagues":[]}\n'
RAW_SHA = hashlib.sha256(RAW).hexdigest()


def _source(candidate_count: int) -> FotMobFixtureCandidateSource:
    return FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256=RAW_SHA,
        source_raw_size=len(RAW),
        source_observed_at=OBSERVED,
        request_date="20260827",
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256="2" * 64,
        candidate_count=candidate_count,
    )


def _candidate(
    source: FotMobFixtureCandidateSource,
    *,
    match_id: int,
    league_id: int = 10,
    primary_id: int | None = None,
    competition_name: str = "Premier League",
    competition_ccode: str = "ENG",
    home_id: int = 101,
    home_name: str = "Home FC",
    away_id: int = 202,
    away_name: str = "Away FC",
    kickoff: dt.datetime | None = None,
) -> FotMobFixtureCandidate:
    return FotMobFixtureCandidate(
        review_status=FixtureCandidateReviewStatus.UNREVIEWED,
        source=SOURCE_NAME,
        source_match_id=match_id,
        source_league_id=league_id,
        source_competition_primary_id=(
            league_id if primary_id is None else primary_id
        ),
        source_competition_name=competition_name,
        source_competition_ccode=competition_ccode,
        home_source_team_id=home_id,
        home_name=home_name,
        home_long_name=home_name,
        away_source_team_id=away_id,
        away_name=away_name,
        away_long_name=away_name,
        kickoff_utc=kickoff or dt.datetime(2026, 8, 27, 15, 0, tzinfo=UTC),
        source_capture_manifest_sha256=source.source_capture_manifest_sha256,
        source_raw_sha256=source.source_raw_sha256,
        source_request_date=source.request_date,
        source_observed_at=source.source_observed_at,
    )


def _bundle(candidates: tuple[FotMobFixtureCandidate, ...]) -> FotMobFixtureCandidateBundle:
    source = _source(len(candidates))
    normalized = tuple(
        _candidate(
            source,
            match_id=item.source_match_id,
            league_id=item.source_league_id,
            primary_id=item.source_competition_primary_id,
            competition_name=item.source_competition_name,
            competition_ccode=item.source_competition_ccode,
            home_id=item.home_source_team_id,
            home_name=item.home_name,
            away_id=item.away_source_team_id,
            away_name=item.away_name,
            kickoff=item.kickoff_utc,
        )
        for item in candidates
    )
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(normalized)
    team_conflicts = candidate_module._make_team_conflicts(normalized)
    competition_conflicts = candidate_module._make_competition_conflicts(normalized)
    return FotMobFixtureCandidateBundle(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dataset_name=CANDIDATE_DATASET_NAME,
        sources=(source,),
        candidate_count=len(normalized),
        candidates=normalized,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=candidate_module._default_safety(),
    )


def _seed_candidate(**kwargs) -> FotMobFixtureCandidate:
    source = _source(1)
    return _candidate(source, match_id=kwargs.pop("match_id", 1001), **kwargs)


def test_reviewed_production_bounds_are_pinned_and_not_parameters() -> None:
    assert DEFAULT_MINIMUM_LEAD_SECONDS == 3600
    assert DEFAULT_MAX_SOURCE_AGE_SECONDS == 900
    parameters = inspect.signature(
        build_current_fotmob_fixture_review_policy_result
    ).parameters
    assert "minimum_lead_seconds" not in parameters
    assert "max_source_age_seconds" not in parameters


def test_exact_reviewed_source_competition_is_policy_approved() -> None:
    bundle = _bundle((_seed_candidate(),))
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.policy_id == POLICY_ID
    assert result.minimum_lead_seconds == DEFAULT_MINIMUM_LEAD_SECONDS
    assert result.max_source_age_seconds == DEFAULT_MAX_SOURCE_AGE_SECONDS
    assert result.exact_competition_identity_count == 1
    assert result.pr41_blocked_count == 0
    assert result.stale_source_excluded_count == 0
    assert result.request_date_excluded_count == 0
    assert result.lead_window_excluded_count == 0
    assert result.policy_approved_count == 1
    assert result.review_bundle.approved_count == 1
    decision = result.review_bundle.decisions[0]
    assert decision.disposition is FixtureCandidateReviewDisposition.APPROVED
    assert decision.reviewer_reference == REVIEWER_REFERENCE
    assert decision.reviewed_at == REVIEWED
    assert POLICY_ID in decision.notes
    assert "canonical=Premier League" in decision.notes
    assert "minimum_lead_seconds=3600" in decision.notes
    assert "max_source_age_seconds=900" in decision.notes
    assert "source_request_date=20260827" in decision.notes
    assert "source_timezone=UTC" in decision.notes
    assert all(value is False for value in result.safety.values())


def test_current_shadow_v2_accepts_exactly_1800_seconds() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                kickoff=REVIEWED + dt.timedelta(seconds=SHADOW_MINIMUM_LEAD_SECONDS),
            ),
        )
    )
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.policy_id == SHADOW_POLICY_ID
    assert result.minimum_lead_seconds == SHADOW_MINIMUM_LEAD_SECONDS
    assert result.max_source_age_seconds == DEFAULT_MAX_SOURCE_AGE_SECONDS
    assert result.lead_window_excluded_count == 0
    assert result.policy_approved_count == 1
    assert result.review_bundle.decisions[0].reviewer_reference == (
        SHADOW_REVIEWER_REFERENCE
    )
    assert SHADOW_POLICY_ID in result.review_bundle.decisions[0].notes
    assert "minimum_lead_seconds=1800" in result.review_bundle.decisions[0].notes
    assert all(value is False for value in result.safety.values())


def test_current_shadow_v2_rejects_1799_seconds() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                kickoff=REVIEWED + dt.timedelta(seconds=SHADOW_MINIMUM_LEAD_SECONDS - 1),
            ),
        )
    )
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.policy_id == SHADOW_POLICY_ID
    assert result.lead_window_excluded_count == 1
    assert result.policy_approved_count == 0
    assert result.review_bundle.unreviewed_count == 1


@pytest.mark.parametrize(
    ("primary_id", "canonical", "band", "kind"),
    [
        (9806, "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9807, "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9808, "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (9821, "Nations League", "INT-D", "INTERNATIONAL_NATIONS_LEAGUE"),
        (
            10608,
            "Continental Championship Qualification",
            "INT-C",
            "INTERNATIONAL_QUALIFIER",
        ),
        (114, "International Friendly", "INT-F", "INTERNATIONAL_FRIENDLY"),
        (10437, "Youth / Olympic International", "INT-G", "INTERNATIONAL_YOUTH"),
        (9833, "Youth / Olympic International", "INT-G", "INTERNATIONAL_YOUTH"),
    ],
)
def test_p44l_exact_international_primary_id_is_shadow_only(
    primary_id, canonical, band, kind
) -> None:
    candidate = _seed_candidate(
        match_id=primary_id,
        league_id=900000 + primary_id,
        primary_id=primary_id,
        competition_name="Renamed source presentation metadata",
        competition_ccode="INT",
        kickoff=REVIEWED + dt.timedelta(seconds=SHADOW_MINIMUM_LEAD_SECONDS),
    )
    bundle = _bundle((candidate,))

    shadow = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    assert shadow.exact_competition_identity_count == 1
    assert shadow.policy_approved_count == 1
    note = shadow.review_bundle.decisions[0].notes
    assert "Current Shadow international source identity" in note
    assert "source_competition_ccode=INT" in note
    assert f"source_competition_primary_id={primary_id}" in note
    assert f"canonical={canonical}" in note
    assert f"priority_band={band}" in note
    assert f"competition_kind={kind}" in note
    assert "source_display_name_metadata=Renamed source presentation metadata" in note
    assert "source_identity_policy_id=ATHENA_CURRENT_SHADOW_FOTMOB_INTERNATIONAL_SOURCE_HIERARCHY_V1" in note
    assert "review_policy_id=ATHENA_CURRENT_SHADOW_FOTMOB_FIXTURE_IDENTITY_POLICY_V2" in note
    assert "minimum_lead_seconds=1800" in note
    assert "max_source_age_seconds=900" in note
    assert "source_request_date=20260827" in note
    assert "source_timezone=UTC" in note
    assert all(value is False for value in shadow.safety.values())

    production = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    assert production.exact_competition_identity_count == 0
    assert production.policy_approved_count == 0


def test_shadow_mixed_club_and_international_card_admits_each_through_own_path() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                match_id=88001,
                league_id=47,
                primary_id=47,
                competition_name="Premier League",
                competition_ccode="ENG",
                kickoff=REVIEWED + dt.timedelta(seconds=1800),
            ),
            _seed_candidate(
                match_id=88002,
                league_id=920741,
                primary_id=9806,
                competition_name="Presentation wrapper changed",
                competition_ccode="INT",
                kickoff=REVIEWED + dt.timedelta(seconds=1800),
            ),
        )
    )
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    assert result.policy_approved_count == 2
    by_match = {
        decision.source_match_id: decision.notes
        for decision in result.review_bundle.decisions
    }
    assert "exact reviewed source competition ENG:Premier League" in by_match[88001]
    assert "Current Shadow international source identity" in by_match[88002]
    assert "source_competition_primary_id=9806" in by_match[88002]
    assert international_identity.resolve_current_shadow_international_source_priority(
        source_competition_ccode="INT",
        source_competition_primary_id=9806,
    ).priority_band == "INT-D"


def test_pure_club_source_resolution_retains_existing_reviewed_note_semantics() -> None:
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        _bundle((_seed_candidate(match_id=88003),)),
        reviewed_at=REVIEWED,
    )
    assert result.policy_approved_count == 1
    assert result.review_bundle.decisions[0].notes == (
        "ATHENA_CURRENT_SHADOW_FOTMOB_FIXTURE_IDENTITY_POLICY_V2; exact reviewed "
        "source competition ENG:Premier League; canonical=Premier League; rank=10; "
        "minimum_lead_seconds=1800; max_source_age_seconds=900; "
        "source_request_date=20260827; source_timezone=UTC"
    )


def test_existing_uefa_club_source_name_path_precedes_international_fallback() -> None:
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        _bundle(
            (
                _seed_candidate(
                    match_id=88004,
                    league_id=500,
                    primary_id=9806,
                    competition_name="Champions League",
                    competition_ccode="INT",
                    kickoff=REVIEWED + dt.timedelta(seconds=1800),
                ),
            )
        ),
        reviewed_at=REVIEWED,
    )
    assert result.policy_approved_count == 1
    note = result.review_bundle.decisions[0].notes
    assert "exact reviewed source competition INT:Champions League" in note
    assert "canonical=UEFA Champions League" in note
    assert "Current Shadow international source identity" not in note


def test_production_builder_never_invokes_shadow_international_resolver(monkeypatch) -> None:
    def unexpected(**kwargs):
        raise AssertionError("production PR243 invoked the P4.4L Shadow-only bridge")

    monkeypatch.setattr(
        review_policy_module,
        "resolve_current_shadow_international_source_priority",
        unexpected,
    )
    monkeypatch.setattr(
        review_policy_module,
        "reviewed_current_fotmob_international_source_identity",
        unexpected,
    )
    bundle = _bundle(
        (
            _seed_candidate(
                match_id=88005,
                league_id=777,
                primary_id=9806,
                competition_name="Renamed international metadata",
                competition_ccode="INT",
                kickoff=REVIEWED + dt.timedelta(seconds=3600),
            ),
        )
    )
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    assert result.exact_competition_identity_count == 0
    assert result.policy_approved_count == 0


def test_legacy_pr243_accepts_exactly_3600_seconds() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                kickoff=REVIEWED + dt.timedelta(seconds=DEFAULT_MINIMUM_LEAD_SECONDS),
            ),
        )
    )
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.policy_id == POLICY_ID
    assert result.minimum_lead_seconds == DEFAULT_MINIMUM_LEAD_SECONDS
    assert result.lead_window_excluded_count == 0
    assert result.policy_approved_count == 1


def test_unreviewed_source_competition_remains_unreviewed() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                competition_name="Unknown Regional League",
                competition_ccode="ZZZ",
            ),
        )
    )
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.exact_competition_identity_count == 0
    assert result.policy_approved_count == 0
    assert result.review_bundle.decision_count == 0
    assert result.review_bundle.unreviewed_count == 1


def test_stale_source_remains_unreviewed_without_claiming_provider_freshness() -> None:
    bundle = _bundle((_seed_candidate(),))
    reviewed = OBSERVED + dt.timedelta(seconds=DEFAULT_MAX_SOURCE_AGE_SECONDS + 1)
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=reviewed,
    )

    assert result.exact_competition_identity_count == 1
    assert result.stale_source_excluded_count == 1
    assert result.policy_approved_count == 0
    assert result.review_bundle.unreviewed_count == 1


def test_source_age_exactly_900_seconds_remains_eligible() -> None:
    bundle = _bundle((_seed_candidate(),))
    reviewed = OBSERVED + dt.timedelta(seconds=DEFAULT_MAX_SOURCE_AGE_SECONDS)
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=reviewed,
    )

    assert result.stale_source_excluded_count == 0
    assert result.policy_approved_count == 1


def test_source_date_spillover_remains_unreviewed() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                kickoff=dt.datetime(2026, 8, 28, 0, 30, tzinfo=UTC),
            ),
        )
    )
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.exact_competition_identity_count == 1
    assert result.request_date_excluded_count == 1
    assert result.policy_approved_count == 0
    assert result.review_bundle.unreviewed_count == 1


def test_fixture_inside_frozen_minimum_lead_window_remains_unreviewed() -> None:
    bundle = _bundle(
        (
            _seed_candidate(
                kickoff=REVIEWED + dt.timedelta(minutes=30),
            ),
        )
    )
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.exact_competition_identity_count == 1
    assert result.lead_window_excluded_count == 1
    assert result.policy_approved_count == 0
    assert result.review_bundle.unreviewed_count == 1


def test_pr41_identity_conflict_remains_blocked_not_approved() -> None:
    first = _seed_candidate(match_id=1001, home_id=777, home_name="Alpha FC")
    second = _seed_candidate(
        match_id=1002,
        home_id=777,
        home_name="Alpha FC Women",
        away_id=303,
        away_name="Other FC",
    )
    bundle = _bundle((first, second))
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.exact_competition_identity_count == 2
    assert result.pr41_blocked_count == 2
    assert result.policy_approved_count == 0
    assert result.review_bundle.blocked_candidate_count == 2
    assert result.review_bundle.decision_count == 0


def test_source_observation_after_policy_time_fails_closed() -> None:
    bundle = _bundle((_seed_candidate(),))
    with pytest.raises(
        CurrentFotMobFixtureReviewPolicyError,
        match="source observation is after",
    ):
        build_current_fotmob_fixture_review_policy_result(
            bundle,
            reviewed_at=OBSERVED - dt.timedelta(seconds=1),
        )


def test_policy_result_bytes_are_deterministic() -> None:
    bundle = _bundle((_seed_candidate(),))
    first = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    second = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    assert canonical_current_fotmob_fixture_review_policy_result_bytes(first) == (
        canonical_current_fotmob_fixture_review_policy_result_bytes(second)
    )


def test_result_count_tampering_fails_closed() -> None:
    bundle = _bundle((_seed_candidate(),))
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    with pytest.raises(CurrentFotMobFixtureReviewPolicyError, match="counts do not reconcile"):
        dataclasses.replace(result, stale_source_excluded_count=1)


def test_result_cannot_relabel_weaker_policy_bounds() -> None:
    bundle = _bundle((_seed_candidate(),))
    result = build_current_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )
    with pytest.raises(CurrentFotMobFixtureReviewPolicyError, match="frozen PR243"):
        dataclasses.replace(result, minimum_lead_seconds=0)
    with pytest.raises(CurrentFotMobFixtureReviewPolicyError, match="frozen PR243"):
        dataclasses.replace(result, max_source_age_seconds=3600)


def test_shadow_policy_identity_and_bound_fail_closed() -> None:
    bundle = _bundle((_seed_candidate(),))
    result = build_current_shadow_fotmob_fixture_review_policy_result(
        bundle,
        reviewed_at=REVIEWED,
    )

    assert result.policy_id == SHADOW_POLICY_ID
    assert result.review_bundle.decisions[0].reviewer_reference == (
        SHADOW_REVIEWER_REFERENCE
    )
    with pytest.raises(
        CurrentFotMobFixtureReviewPolicyError,
        match="frozen current Shadow",
    ):
        dataclasses.replace(result, minimum_lead_seconds=DEFAULT_MINIMUM_LEAD_SECONDS)
    with pytest.raises(CurrentFotMobFixtureReviewPolicyError, match="policy_id mismatch"):
        dataclasses.replace(result, policy_id="UNKNOWN_CURRENT_POLICY")
