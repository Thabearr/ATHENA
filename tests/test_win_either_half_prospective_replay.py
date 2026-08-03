"""Test suite for Stage 5B2 Win Either Half prospective pricing observation replay."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import pytest

from domain.markets import MarketId, OutcomeId
from domain.win_either_half_prospective_replay import (
    SCHEMA_VERSION,
    PERMITTED_MARKETS,
    FROZEN_CANDIDATE_OFFSETS_SECONDS,
    ATTEMPT_WINDOW_SECONDS,
    MAXIMUM_QUOTE_AGE_SECONDS,
    EXPECTED_ATTEMPTS_PER_FIXTURE,
    AttemptResult,
    AvailabilityStatus,
    AvailabilityReason,
    ProspectiveFixture,
    ProviderSelectionMapping,
    ObservationAttempt,
    AttemptParseResult,
    ProspectiveQuote,
    QuoteParseResult,
    ValidatedSnapshot,
    ProspectiveReplayRow,
    AttemptIndex,
    canonical_record_bytes,
    canonical_record_sha256,
    assert_no_forbidden_fields,
    load_source_qualification,
    load_prospective_fixtures,
    load_provider_mappings,
    market_mapping_identity,
    expected_attempt_keys,
    parse_attempt,
    index_attempt_results,
    parse_quote,
    build_validated_snapshot,
    evaluate_expected_key,
    aggregate_replay,
)
from scripts.export_win_either_half_prospective_replay import (
    DEFAULT_PROTOCOL_PATH,
    OUTPUT_FILENAMES,
    build_outputs,
    commit_evidence_bundle,
    check_manifest,
    run,
)


@pytest.fixture
def base_kickoff() -> datetime:
    return datetime(2026, 9, 15, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_fixture(base_kickoff: datetime) -> ProspectiveFixture:
    return ProspectiveFixture(
        fixture_identifier="FIX_001",
        season="2026-27",
        competition_code="EPL",
        kickoff=base_kickoff,
        home_team_identifier="ARS",
        away_team_identifier="CHE",
        provider_event_identifier="EVT_100",
        expected_sources=("MOCK_PROSPECTIVE_API",),
    )


@pytest.fixture
def sample_fixtures_payload(base_kickoff: datetime) -> dict:
    return {
        "schema_version": 1,
        "fixtures": [
            {
                "fixture_identifier": "FIX_001",
                "season": "2026-27",
                "competition_code": "EPL",
                "fixture_kickoff": base_kickoff.isoformat(),
                "home_team_identifier": "ARS",
                "away_team_identifier": "CHE",
                "provider_event_identifier": "EVT_100",
                "expected_sources": ["MOCK_PROSPECTIVE_API"],
            }
        ],
    }


@pytest.fixture
def sample_qualification_payload() -> dict:
    return {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "prospective_replay_status": "QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE",
    }


@pytest.fixture
def sample_mappings_payload() -> dict:
    return {
        "schema_version": 1,
        "mappings": [
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
        ],
    }


def test_frozen_candidate_offsets_exact():
    assert FROZEN_CANDIDATE_OFFSETS_SECONDS == (86400, 21600, 10800, 3600, 1800, 900)
    assert EXPECTED_ATTEMPTS_PER_FIXTURE == 12


def test_expected_attempt_keys_cardinality(sample_fixture: ProspectiveFixture):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    keys = expected_attempt_keys(fixtures)
    assert len(keys) == 12
    # Exactly 2 markets x 6 offsets
    assert len([k for k in keys if k[1] == MarketId.HOME_WIN_EITHER_HALF]) == 6
    assert len([k for k in keys if k[1] == MarketId.AWAY_WIN_EITHER_HALF]) == 6


def test_missing_attempt_evaluates_unknown(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, 86400)
    attempt_index = index_attempt_results(())

    row, snap = evaluate_expected_key(
        key=key,
        fixture=sample_fixture,
        attempt_index=attempt_index,
        raw_quotes_for_key=(),
        parsed_quotes_for_key=(),
        mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
    )

    assert row.availability_status == AvailabilityStatus.UNKNOWN
    assert row.availability_reason == AvailabilityReason.NO_ATTEMPT_RECORD
    assert row.attempt_status == "MISSING"
    assert snap is None


def test_capture_error_evaluates_unknown_without_quotes(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
    base_kickoff: datetime,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    offset = 86400
    sched = base_kickoff - timedelta(seconds=offset)
    att_payload = {
        "schema_version": 1,
        "attempt_id": "ATT_01",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "source": "MOCK_PROSPECTIVE_API",
        "provider_identifier": "PROV_A",
        "bookmaker_identifier": "BK_1",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "offset_seconds_before_kickoff": offset,
        "scheduled_at": sched.isoformat(),
        "attempted_at": sched.isoformat(),
        "result": "CAPTURE_ERROR",
        "capture_method": "API_GET",
        "quote_snapshot_id": None,
        "line": None,
    }

    parsed = parse_attempt(
        att_payload,
        fixtures=fixtures,
        mapping_by_market=market_mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )
    assert parsed.record is not None

    key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, offset)
    attempt_index = index_attempt_results((parsed,))

    row, snap = evaluate_expected_key(
        key=key,
        fixture=sample_fixture,
        attempt_index=attempt_index,
        raw_quotes_for_key=(),
        parsed_quotes_for_key=(),
        mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
    )

    assert row.availability_status == AvailabilityStatus.UNKNOWN
    assert row.availability_reason == AvailabilityReason.CAPTURE_ERROR
    assert row.attempt_status == "PRESENT"
    assert snap is None


def test_capture_error_with_quotes_evaluates_invalid(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
    base_kickoff: datetime,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    offset = 86400
    sched = base_kickoff - timedelta(seconds=offset)
    att_payload = {
        "schema_version": 1,
        "attempt_id": "ATT_01",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "source": "MOCK_PROSPECTIVE_API",
        "provider_identifier": "PROV_A",
        "bookmaker_identifier": "BK_1",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "offset_seconds_before_kickoff": offset,
        "scheduled_at": sched.isoformat(),
        "attempted_at": sched.isoformat(),
        "result": "CAPTURE_ERROR",
        "capture_method": "API_GET",
        "quote_snapshot_id": None,
        "line": None,
    }

    parsed = parse_attempt(
        att_payload,
        fixtures=fixtures,
        mapping_by_market=market_mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )

    key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, offset)
    attempt_index = index_attempt_results((parsed,))

    # Spurious quote exists despite capture error
    raw_quote = {"quote_snapshot_id": "SNAP_X"}

    row, snap = evaluate_expected_key(
        key=key,
        fixture=sample_fixture,
        attempt_index=attempt_index,
        raw_quotes_for_key=(raw_quote,),
        parsed_quotes_for_key=(),
        mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
    )

    assert row.availability_status == AvailabilityStatus.INVALID
    assert row.availability_reason == AvailabilityReason.CONTRADICTORY_QUOTE_EVIDENCE


def test_explicit_unavailability_evaluates_unavailable(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
    base_kickoff: datetime,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    for res, exp_reason in [
        (AttemptResult.MARKET_UNAVAILABLE, AvailabilityReason.EXPLICIT_MARKET_UNAVAILABLE),
        (AttemptResult.FIXTURE_UNAVAILABLE, AvailabilityReason.EXPLICIT_FIXTURE_UNAVAILABLE),
        (AttemptResult.SOURCE_UNAVAILABLE, AvailabilityReason.EXPLICIT_SOURCE_UNAVAILABLE),
    ]:
        offset = 86400
        sched = base_kickoff - timedelta(seconds=offset)
        att_payload = {
            "schema_version": 1,
            "attempt_id": "ATT_01",
            "fixture_identifier": sample_fixture.fixture_identifier,
            "market_id": "HOME_WIN_EITHER_HALF",
            "source": "MOCK_PROSPECTIVE_API",
            "provider_identifier": "PROV_A",
            "bookmaker_identifier": "BK_1",
            "provider_event_identifier": "EVT_100",
            "provider_market_identifier": "MK_HOME_WEH",
            "offset_seconds_before_kickoff": offset,
            "scheduled_at": sched.isoformat(),
            "attempted_at": sched.isoformat(),
            "result": res.value,
            "capture_method": "API_GET",
            "quote_snapshot_id": None,
            "line": None,
        }

        parsed = parse_attempt(
            att_payload,
            fixtures=fixtures,
            mapping_by_market=market_mappings,
            qualified_provider_identifier="PROV_A",
            expected_source="MOCK_PROSPECTIVE_API",
        )

        key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, offset)
        attempt_index = index_attempt_results((parsed,))

        row, snap = evaluate_expected_key(
            key=key,
            fixture=sample_fixture,
            attempt_index=attempt_index,
            raw_quotes_for_key=(),
            parsed_quotes_for_key=(),
            mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
        )

        assert row.availability_status == AvailabilityStatus.UNAVAILABLE
        assert row.availability_reason == exp_reason


def test_quotes_captured_complete_valid_snapshot(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
    base_kickoff: datetime,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    offset = 3600
    sched = base_kickoff - timedelta(seconds=offset)
    snap_id = "SNAP_HOME_3600"

    att_payload = {
        "schema_version": 1,
        "attempt_id": "ATT_01",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "source": "MOCK_PROSPECTIVE_API",
        "provider_identifier": "PROV_A",
        "bookmaker_identifier": "BK_1",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "offset_seconds_before_kickoff": offset,
        "scheduled_at": sched.isoformat(),
        "attempted_at": sched.isoformat(),
        "result": "QUOTES_CAPTURED",
        "capture_method": "API_GET",
        "quote_snapshot_id": snap_id,
        "line": None,
    }

    obs_time = sched - timedelta(seconds=30)
    q_yes_payload = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "source": "MOCK_PROSPECTIVE_API",
        "bookmaker_identifier": "BK_1",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "outcome_id": "YES",
        "quote_snapshot_id": snap_id,
        "observed_at": obs_time.isoformat(),
        "fixture_kickoff": base_kickoff.isoformat(),
        "decimal_odds": "1.75",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "provider_selection_identifier": "SEL_HOME_YES",
        "line": None,
        "is_genuine": True,
    }
    q_no_payload = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "source": "MOCK_PROSPECTIVE_API",
        "bookmaker_identifier": "BK_1",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "outcome_id": "NO",
        "quote_snapshot_id": snap_id,
        "observed_at": obs_time.isoformat(),
        "fixture_kickoff": base_kickoff.isoformat(),
        "decimal_odds": "2.10",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "provider_selection_identifier": "SEL_HOME_NO",
        "line": None,
        "is_genuine": True,
    }

    parsed_att = parse_attempt(
        att_payload,
        fixtures=fixtures,
        mapping_by_market=market_mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )
    parsed_q_yes = parse_quote(
        q_yes_payload,
        fixtures=fixtures,
        mappings=mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )
    parsed_q_no = parse_quote(
        q_no_payload,
        fixtures=fixtures,
        mappings=mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )

    assert parsed_att.record is not None
    assert parsed_q_yes.record is not None
    assert parsed_q_no.record is not None

    key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, offset)
    attempt_index = index_attempt_results((parsed_att,))

    row, snap = evaluate_expected_key(
        key=key,
        fixture=sample_fixture,
        attempt_index=attempt_index,
        raw_quotes_for_key=(q_yes_payload, q_no_payload),
        parsed_quotes_for_key=(parsed_q_yes, parsed_q_no),
        mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
    )

    assert row.availability_status == AvailabilityStatus.AVAILABLE
    assert row.availability_reason == AvailabilityReason.COMPLETE_ELIGIBLE_SNAPSHOT
    assert row.validated_snapshot_count == 1
    assert snap is not None
    assert snap.quote_snapshot_id == snap_id
    assert snap.quote_age_seconds == 30


def test_quote_age_exceeded_evaluates_invalid(
    sample_fixture: ProspectiveFixture,
    sample_mappings_payload: dict,
    base_kickoff: datetime,
):
    fixtures = {sample_fixture.fixture_identifier: sample_fixture}
    mappings = load_provider_mappings(sample_mappings_payload, fixtures, "PROV_A")
    market_mappings = market_mapping_identity(mappings)

    offset = 3600
    sched = base_kickoff - timedelta(seconds=offset)
    snap_id = "SNAP_OLD"

    att_payload = {
        "schema_version": 1,
        "attempt_id": "ATT_01",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "source": "MOCK_PROSPECTIVE_API",
        "provider_identifier": "PROV_A",
        "bookmaker_identifier": "BK_1",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "offset_seconds_before_kickoff": offset,
        "scheduled_at": sched.isoformat(),
        "attempted_at": sched.isoformat(),
        "result": "QUOTES_CAPTURED",
        "capture_method": "API_GET",
        "quote_snapshot_id": snap_id,
        "line": None,
    }

    # Quote is 950s old (exceeds 900s max age)
    obs_time = sched - timedelta(seconds=950)
    q_yes_payload = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "source": "MOCK_PROSPECTIVE_API",
        "bookmaker_identifier": "BK_1",
        "fixture_identifier": sample_fixture.fixture_identifier,
        "market_id": "HOME_WIN_EITHER_HALF",
        "outcome_id": "YES",
        "quote_snapshot_id": snap_id,
        "observed_at": obs_time.isoformat(),
        "fixture_kickoff": base_kickoff.isoformat(),
        "decimal_odds": "1.75",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "provider_selection_identifier": "SEL_HOME_YES",
        "line": None,
        "is_genuine": True,
    }
    q_no_payload = dict(q_yes_payload, outcome_id="NO", provider_selection_identifier="SEL_HOME_NO")

    parsed_att = parse_attempt(
        att_payload,
        fixtures=fixtures,
        mapping_by_market=market_mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )
    parsed_q_yes = parse_quote(
        q_yes_payload,
        fixtures=fixtures,
        mappings=mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )
    parsed_q_no = parse_quote(
        q_no_payload,
        fixtures=fixtures,
        mappings=mappings,
        qualified_provider_identifier="PROV_A",
        expected_source="MOCK_PROSPECTIVE_API",
    )

    key = (sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF, offset)
    attempt_index = index_attempt_results((parsed_att,))

    row, snap = evaluate_expected_key(
        key=key,
        fixture=sample_fixture,
        attempt_index=attempt_index,
        raw_quotes_for_key=(q_yes_payload, q_no_payload),
        parsed_quotes_for_key=(parsed_q_yes, parsed_q_no),
        mapping=market_mappings[(sample_fixture.fixture_identifier, MarketId.HOME_WIN_EITHER_HALF)],
    )

    assert row.availability_status == AvailabilityStatus.INVALID
    assert row.availability_reason == AvailabilityReason.NO_COMPLETE_ELIGIBLE_SNAPSHOT


def test_forbidden_field_raises_error():
    bad_payload = {"expected_value": 0.05, "market_id": "HOME_WIN_EITHER_HALF"}
    with pytest.raises(ValueError, match="Forbidden field"):
        assert_no_forbidden_fields(bad_payload)


def test_full_pipeline_cli_and_check(tmp_path: Path, base_kickoff: datetime):
    # Setup complete valid inputs for 1 fixture
    source_qual = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "prospective_replay_status": "QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE",
    }
    fixtures = {
        "schema_version": 1,
        "fixtures": [
            {
                "fixture_identifier": "FIX_001",
                "season": "2026-27",
                "competition_code": "EPL",
                "fixture_kickoff": base_kickoff.isoformat(),
                "home_team_identifier": "ARS",
                "away_team_identifier": "CHE",
                "provider_event_identifier": "EVT_100",
                "expected_sources": ["MOCK_PROSPECTIVE_API"],
            }
        ],
    }
    mappings = {
        "schema_version": 1,
        "mappings": [
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
        ],
    }

    # Generate attempts for all 12 expected keys
    attempts_lines = []
    quotes_lines = []

    for m_id, m_str, m_code in [
        (MarketId.HOME_WIN_EITHER_HALF, "HOME_WIN_EITHER_HALF", "HOME"),
        (MarketId.AWAY_WIN_EITHER_HALF, "AWAY_WIN_EITHER_HALF", "AWAY"),
    ]:
        for off in FROZEN_CANDIDATE_OFFSETS_SECONDS:
            sched = base_kickoff - timedelta(seconds=off)
            snap_id = f"SNAP_{m_code}_{off}"
            att = {
                "schema_version": 1,
                "attempt_id": f"ATT_{m_code}_{off}",
                "fixture_identifier": "FIX_001",
                "market_id": m_str,
                "source": "MOCK_PROSPECTIVE_API",
                "provider_identifier": "PROV_A",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": f"MK_{m_code}_WEH",
                "offset_seconds_before_kickoff": off,
                "scheduled_at": sched.isoformat(),
                "attempted_at": sched.isoformat(),
                "result": "QUOTES_CAPTURED",
                "capture_method": "API_GET",
                "quote_snapshot_id": snap_id,
                "line": None,
            }
            attempts_lines.append(json.dumps(att))

            obs = sched - timedelta(seconds=10)
            q_yes = {
                "schema_version": 1,
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "fixture_identifier": "FIX_001",
                "market_id": m_str,
                "outcome_id": "YES",
                "quote_snapshot_id": snap_id,
                "observed_at": obs.isoformat(),
                "fixture_kickoff": base_kickoff.isoformat(),
                "decimal_odds": "1.80",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": f"MK_{m_code}_WEH",
                "provider_selection_identifier": f"SEL_{m_code}_YES",
                "line": None,
                "is_genuine": True,
            }
            q_no = {
                "schema_version": 1,
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "fixture_identifier": "FIX_001",
                "market_id": m_str,
                "outcome_id": "NO",
                "quote_snapshot_id": snap_id,
                "observed_at": obs.isoformat(),
                "fixture_kickoff": base_kickoff.isoformat(),
                "decimal_odds": "2.05",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": f"MK_{m_code}_WEH",
                "provider_selection_identifier": f"SEL_{m_code}_NO",
                "line": None,
                "is_genuine": True,
            }
            quotes_lines.append(json.dumps(q_yes))
            quotes_lines.append(json.dumps(q_no))

    qual_path = tmp_path / "qual.json"
    fix_path = tmp_path / "fix.json"
    map_path = tmp_path / "map.json"
    att_path = tmp_path / "attempts.jsonl"
    quo_path = tmp_path / "quotes.jsonl"

    qual_path.write_text(json.dumps(source_qual))
    fix_path.write_text(json.dumps(fixtures))
    map_path.write_text(json.dumps(mappings))
    att_path.write_text("\n".join(attempts_lines) + "\n")
    quo_path.write_text("\n".join(quotes_lines) + "\n")

    out_dir = tmp_path / "out"
    manifest_path = out_dir / "prospective-replay-manifest-v1.json"

    # Run exporter in manifest-output mode
    exit_code = run([
        "--source-qualification", str(qual_path),
        "--fixtures", str(fix_path),
        "--provider-mappings", str(map_path),
        "--attempts", str(att_path),
        "--quotes", str(quo_path),
        "--protocol", str(DEFAULT_PROTOCOL_PATH),
        "--manifest-output", str(manifest_path),
    ])
    assert exit_code == 0

    # Verify all 7 files were created
    for name, filename in OUTPUT_FILENAMES.items():
        assert (out_dir / filename).exists()

    # Run check mode
    check_code = run([
        "--source-qualification", str(qual_path),
        "--fixtures", str(fix_path),
        "--provider-mappings", str(map_path),
        "--attempts", str(att_path),
        "--quotes", str(quo_path),
        "--protocol", str(DEFAULT_PROTOCOL_PATH),
        "--check", str(manifest_path),
    ])
    assert check_code == 0


def test_permutation_invariance(tmp_path: Path, base_kickoff: datetime):
    # Setup inputs
    source_qual = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "prospective_replay_status": "QUALIFIED_PROSPECTIVE_REPLAY_ELIGIBLE",
    }
    fixtures = {
        "schema_version": 1,
        "fixtures": [
            {
                "fixture_identifier": "FIX_001",
                "season": "2026-27",
                "competition_code": "EPL",
                "fixture_kickoff": base_kickoff.isoformat(),
                "home_team_identifier": "ARS",
                "away_team_identifier": "CHE",
                "provider_event_identifier": "EVT_100",
                "expected_sources": ["MOCK_PROSPECTIVE_API"],
            }
        ],
    }
    mappings = {
        "schema_version": 1,
        "mappings": [
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_HOME_WEH",
                "provider_selection_identifier": "SEL_HOME_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "HOME_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_YES",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "YES",
                "line": None,
            },
            {
                "provider_identifier": "PROV_A",
                "source": "MOCK_PROSPECTIVE_API",
                "bookmaker_identifier": "BK_1",
                "provider_event_identifier": "EVT_100",
                "provider_market_identifier": "MK_AWAY_WEH",
                "provider_selection_identifier": "SEL_AWAY_NO",
                "fixture_identifier": "FIX_001",
                "market_id": "AWAY_WIN_EITHER_HALF",
                "outcome_id": "NO",
                "line": None,
            },
        ],
    }

    protocol_raw = DEFAULT_PROTOCOL_PATH.read_bytes()
    protocol_payload = json.loads(protocol_raw.decode("utf-8"))

    # Generate 1 attempt and 2 quotes
    sched = base_kickoff - timedelta(seconds=86400)
    snap_id = "SNAP_1"
    att = {
        "schema_version": 1,
        "attempt_id": "ATT_1",
        "fixture_identifier": "FIX_001",
        "market_id": "HOME_WIN_EITHER_HALF",
        "source": "MOCK_PROSPECTIVE_API",
        "provider_identifier": "PROV_A",
        "bookmaker_identifier": "BK_1",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "offset_seconds_before_kickoff": 86400,
        "scheduled_at": sched.isoformat(),
        "attempted_at": sched.isoformat(),
        "result": "QUOTES_CAPTURED",
        "capture_method": "API_GET",
        "quote_snapshot_id": snap_id,
        "line": None,
    }
    obs = sched - timedelta(seconds=10)
    q_yes = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "source": "MOCK_PROSPECTIVE_API",
        "bookmaker_identifier": "BK_1",
        "fixture_identifier": "FIX_001",
        "market_id": "HOME_WIN_EITHER_HALF",
        "outcome_id": "YES",
        "quote_snapshot_id": snap_id,
        "observed_at": obs.isoformat(),
        "fixture_kickoff": base_kickoff.isoformat(),
        "decimal_odds": "1.80",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "provider_selection_identifier": "SEL_HOME_YES",
        "line": None,
        "is_genuine": True,
    }
    q_no = {
        "schema_version": 1,
        "provider_identifier": "PROV_A",
        "source": "MOCK_PROSPECTIVE_API",
        "bookmaker_identifier": "BK_1",
        "fixture_identifier": "FIX_001",
        "market_id": "HOME_WIN_EITHER_HALF",
        "outcome_id": "NO",
        "quote_snapshot_id": snap_id,
        "observed_at": obs.isoformat(),
        "fixture_kickoff": base_kickoff.isoformat(),
        "decimal_odds": "2.05",
        "provider_event_identifier": "EVT_100",
        "provider_market_identifier": "MK_HOME_WEH",
        "provider_selection_identifier": "SEL_HOME_NO",
        "line": None,
        "is_genuine": True,
    }

    # Order 1: [q_yes, q_no]
    b1 = build_outputs(
        source_qualification_raw=json.dumps(source_qual).encode("utf-8"),
        source_qualification_payload=source_qual,
        fixtures_raw=json.dumps(fixtures).encode("utf-8"),
        fixtures_payload=fixtures,
        provider_mappings_raw=json.dumps(mappings).encode("utf-8"),
        provider_mappings_payload=mappings,
        attempts_raw=json.dumps(att).encode("utf-8"),
        raw_attempts=[att],
        quotes_raw=(json.dumps(q_yes) + "\n" + json.dumps(q_no)).encode("utf-8"),
        raw_quotes=[q_yes, q_no],
        protocol_raw=protocol_raw,
        protocol_payload=protocol_payload,
        source_qual_path=Path("q.json"),
        fixtures_path=Path("f.json"),
        mappings_path=Path("m.json"),
        attempts_path=Path("a.jsonl"),
        quotes_path=Path("q.jsonl"),
        protocol_path=DEFAULT_PROTOCOL_PATH,
    )

    # Order 2: [q_no, q_yes] (reversed)
    b2 = build_outputs(
        source_qualification_raw=json.dumps(source_qual).encode("utf-8"),
        source_qualification_payload=source_qual,
        fixtures_raw=json.dumps(fixtures).encode("utf-8"),
        fixtures_payload=fixtures,
        provider_mappings_raw=json.dumps(mappings).encode("utf-8"),
        provider_mappings_payload=mappings,
        attempts_raw=json.dumps(att).encode("utf-8"),
        raw_attempts=[att],
        quotes_raw=(json.dumps(q_no) + "\n" + json.dumps(q_yes)).encode("utf-8"),
        raw_quotes=[q_no, q_yes],
        protocol_raw=protocol_raw,
        protocol_payload=protocol_payload,
        source_qual_path=Path("q.json"),
        fixtures_path=Path("f.json"),
        mappings_path=Path("m.json"),
        attempts_path=Path("a.jsonl"),
        quotes_path=Path("q.jsonl"),
        protocol_path=DEFAULT_PROTOCOL_PATH,
    )

    # The 6 derived data outputs must be identical byte-for-byte
    for k in [
        "normalized_attempts",
        "valid_quotes",
        "rejected_quotes",
        "validated_snapshots",
        "evaluations",
        "summary",
    ]:
        assert b1.files[k] == b2.files[k], f"Mismatch in {k} across input permutations"
