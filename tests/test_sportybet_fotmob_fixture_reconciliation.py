from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from domain import sportybet_fotmob_fixture_reconciliation as bridge
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput


OBSERVED = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
IMPORTED = dt.datetime(2026, 8, 18, 12, 1, tzinfo=dt.timezone.utc)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
RAW = b'''<!doctype html><html><body>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="Total Goals" data-outcome-name="Over 2.5" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=18&outcomeId=12&odds=1.85&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main&specifier=total%3D2.5">Over 2.5</a>
</body></html>'''
KICKOFF = dt.datetime(2026, 8, 25, 19, 0, tzinfo=dt.timezone.utc)


def _inventory(tmp_path: Path) -> native.SportyBetUserControlledNativeInventory:
    repo = tmp_path / "repo"
    repo.mkdir()
    evidence, _ = manual.store_user_controlled_evidence(
        RAW,
        source_url=DETAIL_URL,
        observed_at_user_attested=OBSERVED,
        imported_at_utc=IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    return native.build_inventory_from_evidence(
        evidence,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )


def _identity(tmp_path: Path) -> bridge.SportyBetUserAttestedEventIdentity:
    return bridge.build_user_attested_event_identity(
        _inventory(tmp_path),
        competition_displayed="England Premier League",
        home_participant_displayed="Newcastle",
        away_participant_displayed="Liverpool",
        kickoff_displayed="25/08 Monday 20:00",
        kickoff_utc_user_attested="2026-08-25T19:00:00.000000Z",
    )


def _fixture(
    fixture_id: str = "59745856",
    *,
    home: str = "Newcastle",
    away: str = "Liverpool",
    competition: str = "England Premier League",
    kickoff: dt.datetime = KICKOFF,
    capture_hash: str = "a" * 64,
    candidate_hash: str = "b" * 64,
    evidence_hash: str = "c" * 64,
) -> FotMobReviewedFixtureCatalogInput:
    return FotMobReviewedFixtureCatalogInput(
        source_capture_manifest_sha256=capture_hash,
        candidate_sha256=candidate_hash,
        source_fixture_identifier=fixture_id,
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=kickoff,
        source_reference=(
            "FotMob /api/data/matches capture manifest sha256:" + capture_hash
        ),
        reviewed_at=dt.datetime(2026, 8, 18, 10, 0, tzinfo=dt.timezone.utc),
        evidence_file_path=f"captures/{fixture_id}.json",
        evidence_sha256=evidence_hash,
        reviewer_reference="review:test",
        notes="",
    )


def test_exact_home_away_competition_and_kickoff_yields_candidate(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    fixture = _fixture()
    result = bridge.build_exact_reconciliation_candidate(identity, (fixture,))
    assert result.disposition is bridge.ReconciliationDisposition.EXACT_MATCH_CANDIDATE_USER_ATTESTED
    assert result.exact_match_count == 1
    assert result.matched_fixture is not None
    assert result.matched_fixture.source_fixture_identifier == "59745856"
    assert result.matched_fixture.home_team == "Newcastle"
    assert result.matched_fixture.away_team == "Liverpool"
    assert result.matching_basis == bridge.MATCHING_BASIS
    assert result.sportybet_identity_authority == bridge.IDENTITY_AUTHORITY
    assert all(value is False for value in result.safety.values())
    assert result.safety["fixture_reconciliation_authorized"] is False
    assert result.safety["pricing_authorized"] is False
    assert result.safety["slip_construction_authorized"] is False
    assert result.safety["bet_authorized"] is False


def test_reversed_home_away_is_never_accepted(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    result = bridge.build_exact_reconciliation_candidate(
        identity,
        (_fixture(home="Liverpool", away="Newcastle"),),
    )
    assert result.disposition is bridge.ReconciliationDisposition.NO_EXACT_MATCH
    assert result.exact_match_count == 0
    assert result.matched_fixture is None


def test_names_are_not_fuzzy_or_alias_matched(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    result = bridge.build_exact_reconciliation_candidate(
        identity,
        (_fixture(home="Newcastle United"),),
    )
    assert result.disposition is bridge.ReconciliationDisposition.NO_EXACT_MATCH


def test_competition_mismatch_fails_closed(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    result = bridge.build_exact_reconciliation_candidate(
        identity,
        (_fixture(competition="England EFL Cup"),),
    )
    assert result.disposition is bridge.ReconciliationDisposition.NO_EXACT_MATCH


def test_kickoff_mismatch_fails_closed(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    result = bridge.build_exact_reconciliation_candidate(
        identity,
        (_fixture(kickoff=KICKOFF + dt.timedelta(minutes=1)),),
    )
    assert result.disposition is bridge.ReconciliationDisposition.NO_EXACT_MATCH


def test_multiple_exact_matches_are_ambiguous_and_no_fixture_is_chosen(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    first = _fixture("59745856")
    second = _fixture(
        "59745857",
        capture_hash="d" * 64,
        candidate_hash="e" * 64,
        evidence_hash="f" * 64,
    )
    result = bridge.build_exact_reconciliation_candidate(identity, (first, second))
    assert result.disposition is bridge.ReconciliationDisposition.AMBIGUOUS_EXACT_MATCH
    assert result.exact_match_count == 2
    assert result.matched_fixture is None
    assert result.safety["fixture_reconciliation_authorized"] is False


def test_fixture_population_order_does_not_change_hash_or_candidate(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    match = _fixture("59745856")
    other = _fixture(
        "59745857",
        home="Arsenal",
        away="Chelsea",
        capture_hash="d" * 64,
        candidate_hash="e" * 64,
        evidence_hash="f" * 64,
    )
    first = bridge.build_exact_reconciliation_candidate(identity, (match, other))
    second = bridge.build_exact_reconciliation_candidate(identity, (other, match))
    assert first.to_dict() == second.to_dict()
    assert bridge.reconciliation_candidate_sha256(first) == bridge.reconciliation_candidate_sha256(second)


def test_duplicate_fotmob_source_fixture_identity_is_rejected(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    first = _fixture("59745856")
    duplicate = _fixture(
        "59745856",
        home="Arsenal",
        away="Chelsea",
        capture_hash="d" * 64,
        candidate_hash="e" * 64,
        evidence_hash="f" * 64,
    )
    with pytest.raises(bridge.SportyBetFotMobReconciliationError, match="duplicate FotMob"):
        bridge.build_exact_reconciliation_candidate(identity, (first, duplicate))


def test_non_reviewed_fixture_input_is_rejected(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    with pytest.raises(bridge.SportyBetFotMobReconciliationError, match="non-reviewed"):
        bridge.build_exact_reconciliation_candidate(identity, ({"fixture": "fake"},))  # type: ignore[arg-type]


def test_identity_is_bound_to_exact_pr154_inventory_and_source_url(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    identity = bridge.build_user_attested_event_identity(
        inventory,
        competition_displayed="England Premier League",
        home_participant_displayed="Newcastle",
        away_participant_displayed="Liverpool",
        kickoff_displayed="25/08 Monday 20:00",
        kickoff_utc_user_attested="2026-08-25T19:00:00.000000Z",
    )
    assert identity.source_evidence_id == inventory.source_evidence_id
    assert identity.source_inventory_sha256 == native.inventory_sha256(inventory)
    assert identity.source_raw_sha256 == inventory.source_raw_sha256
    assert identity.source_url == DETAIL_URL
    assert identity.event_id == "sr:match:123"
    assert identity.sport_id == "sr:sport:1"
    assert identity.identity_authority == bridge.IDENTITY_AUTHORITY
    assert all(value is False for value in identity.safety.values())


def test_current_lite_event_machine_metadata_remains_unproven(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    event = inventory.events[0]
    assert event.competition_id is None
    assert event.competition_name is None
    assert event.home_participant_id is None
    assert event.home_participant_name is None
    assert event.away_participant_id is None
    assert event.away_participant_name is None
    assert event.kickoff is None
    identity = bridge.build_user_attested_event_identity(
        inventory,
        competition_displayed="England Premier League",
        home_participant_displayed="Newcastle",
        away_participant_displayed="Liverpool",
        kickoff_displayed="25/08 Monday 20:00",
        kickoff_utc_user_attested="2026-08-25T19:00:00.000000Z",
    )
    assert identity.identity_authority == "USER_ATTESTED_FROM_REVIEWED_SPORTYBET_PAGE"
    assert identity.safety["fixture_reconciliation_authorized"] is False


def test_noncanonical_user_attested_kickoff_is_rejected(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    with pytest.raises(bridge.SportyBetFotMobReconciliationError, match="canonical UTC"):
        bridge.build_user_attested_event_identity(
            inventory,
            competition_displayed="England Premier League",
            home_participant_displayed="Newcastle",
            away_participant_displayed="Liverpool",
            kickoff_displayed="25/08 Monday 20:00",
            kickoff_utc_user_attested="2026-08-25T19:00:00Z",
        )


def test_surrounding_whitespace_in_identity_fields_is_rejected(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path)
    with pytest.raises(bridge.SportyBetFotMobReconciliationError, match="surrounding whitespace"):
        bridge.build_user_attested_event_identity(
            inventory,
            competition_displayed=" England Premier League",
            home_participant_displayed="Newcastle",
            away_participant_displayed="Liverpool",
            kickoff_displayed="25/08 Monday 20:00",
            kickoff_utc_user_attested="2026-08-25T19:00:00.000000Z",
        )


def test_identity_and_reconciliation_canonical_bytes_are_stable(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    candidate = bridge.build_exact_reconciliation_candidate(identity, (_fixture(),))
    identity_bytes = bridge.canonical_event_identity_bytes(identity)
    candidate_bytes = bridge.canonical_reconciliation_candidate_bytes(candidate)
    assert identity_bytes.endswith(b"\n")
    assert candidate_bytes.endswith(b"\n")
    assert bridge.event_identity_sha256(identity) == bridge.event_identity_sha256(identity)
    assert bridge.reconciliation_candidate_sha256(candidate) == bridge.reconciliation_candidate_sha256(candidate)


def test_candidate_mutation_cannot_promote_authority(tmp_path: Path) -> None:
    identity = _identity(tmp_path)
    candidate = bridge.build_exact_reconciliation_candidate(identity, (_fixture(),))
    forged_safety = dict(candidate.safety)
    forged_safety["fixture_reconciliation_authorized"] = True
    with pytest.raises(bridge.SportyBetFotMobReconciliationError, match="must be exact bool False"):
        dataclasses.replace(candidate, safety=forged_safety)
