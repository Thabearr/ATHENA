from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportybet_event_local_time_basis as local
from domain import sportybet_fotmob_partial_calendar_reconciliation as partial
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput


UTC = dt.timezone.utc
EVENT_OBSERVED = dt.datetime(2026, 8, 18, 17, 0, tzinfo=UTC)
EVENT_IMPORTED = dt.datetime(2026, 8, 18, 17, 1, tzinfo=UTC)
TERMS_OBSERVED = dt.datetime(2026, 8, 18, 16, 55, tzinfo=UTC)
TERMS_IMPORTED = dt.datetime(2026, 8, 18, 16, 56, tzinfo=UTC)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
PROTOCOL = Path(
    "artifacts/research-protocols/"
    "sportybet-fotmob-partial-calendar-reconciliation-v1.json"
)


def _event_raw() -> bytes:
    return b'''<!doctype html><html><body>
<div>Please turn JavaScript on in browser</div>
<a>Register</a><a>Log In</a><a>Cashout</a><a>Betslip(0)</a><a>Back</a><a>Refresh</a>
<h1>Example Country - Example League</h1>
<div class="date">18/08 Tuesday</div><div class="time">20:00</div>
<div class="home">Example Home FC</div><div class="away">Example Away FC</div>
<a data-active="true" data-market-name="1X2" data-outcome-name="Home" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=1&odds=2.05&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Home</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Draw" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=2&odds=3.20&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Draw</a>
<a data-active="true" data-market-name="1X2" data-outcome-name="Away" href="/ng/lite/preMatch/detail?eventId=sr%3Amatch%3A123&marketId=1&outcomeId=3&odds=3.70&productId=3&sportId=sr%3Asport%3A1&marketGroupsName=Main">Away</a>
</body></html>'''


def _terms_raw() -> bytes:
    return (
        "<!doctype html><html><body><p>"
        + terms.EXPECTED_STATEMENT
        + "</p></body></html>"
    ).encode("utf-8")


def _sportybet_chain(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    event_raw = _event_raw()
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        event_raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=EVENT_OBSERVED,
        imported_at_utc=EVENT_IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    terms_raw = _terms_raw()
    qualification = terms.build_qualification(
        terms_raw,
        source_url=terms.SOURCE_URL,
        observed_at_user_attested=TERMS_OBSERVED,
        imported_at_utc=TERMS_IMPORTED,
        attestation=terms.ATTESTATION,
    )
    time_basis = local.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    return time_basis, manifest, inventory, event_raw, qualification, terms_raw


def _fixture(
    fixture_id: int,
    kickoff: dt.datetime,
    *,
    home: str = "Example Home FC",
    away: str = "Example Away FC",
    competition: str = "Example Country - Example League",
) -> FotMobReviewedFixtureCatalogInput:
    capture_sha = f"{fixture_id % 16:x}" * 64
    candidate_sha = f"{(fixture_id + 1) % 16:x}" * 64
    evidence_sha = f"{(fixture_id + 2) % 16:x}" * 64
    return FotMobReviewedFixtureCatalogInput(
        source_capture_manifest_sha256=capture_sha,
        candidate_sha256=candidate_sha,
        source_fixture_identifier=str(fixture_id),
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=kickoff,
        source_reference=(
            "FotMob /api/data/matches capture manifest sha256:" + capture_sha
        ),
        reviewed_at=dt.datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        evidence_file_path=f"evidence/{fixture_id}.json",
        evidence_sha256=evidence_sha,
        reviewer_reference="test-reviewed",
        notes="",
    )


def _build(tmp_path: Path, fixtures):
    chain = _sportybet_chain(tmp_path)
    time_basis, manifest, inventory, event_raw, qualification, terms_raw = chain
    result = partial.build_partial_calendar_reconciliation_candidate(
        time_basis=time_basis,
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
        fixtures=fixtures,
    )
    return result, chain


def test_protocol_is_canonical_and_all_downstream_authority_is_false() -> None:
    raw = PROTOCOL.read_bytes()
    payload = json.loads(raw)
    canonical = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert raw == canonical
    assert payload["schema_version"] == 1
    assert payload["requires_exact_pr158_rederivation"] is True
    assert payload["sportybet_year_capability"] == "UNPROVEN"
    assert payload["sportybet_kickoff_utc_capability"] == "UNPROVEN"
    assert payload["fotmob_kickoff_seconds_policy"] == (
        "REQUIRE_EXACT_ZERO_SECONDS_AND_MICROSECONDS"
    )
    assert payload["matching_basis"] == partial.MATCHING_BASIS
    assert payload["network_acquisition_authorized"] is False
    assert all(value is False for value in payload["safety"].values())


def test_unique_exact_partial_match_remains_year_unproven(tmp_path: Path) -> None:
    # 18 August 2037 is also Tuesday. The FotMob year can be observed on the
    # matched candidate but must never be promoted into SportyBet evidence.
    fixture = _fixture(1001, dt.datetime(2037, 8, 18, 20, 0, tzinfo=UTC))
    result, _ = _build(tmp_path, [fixture])
    assert result.disposition is (
        partial.PartialCalendarDisposition.UNIQUE_EXACT_PARTIAL_CALENDAR_MATCH_CANDIDATE_YEAR_UNPROVEN
    )
    assert result.exact_match_count == 1
    assert result.matched_fixture is not None
    assert result.matched_fixture.source_fixture_identifier == "1001"
    assert result.matched_fixture.fotmob_year == 2037
    assert result.sportybet_kickoff_year is None
    assert result.sportybet_kickoff_utc is None
    assert result.sportybet_year_proven is False
    assert result.safety["fixture_reconciliation_authorized"] is False
    assert result.safety["booking_code_authorized"] is False
    assert result.safety["bet_authorized"] is False


def test_two_different_years_with_same_partial_identity_are_ambiguous(tmp_path: Path) -> None:
    fixtures = [
        _fixture(1001, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
        _fixture(1002, dt.datetime(2037, 8, 18, 20, 0, tzinfo=UTC)),
    ]
    result, _ = _build(tmp_path, fixtures)
    assert result.disposition is (
        partial.PartialCalendarDisposition.AMBIGUOUS_EXACT_PARTIAL_CALENDAR_MATCH
    )
    assert result.exact_match_count == 2
    assert result.matched_fixture is None
    assert result.sportybet_year_proven is False


@pytest.mark.parametrize(
    "fixture",
    [
        _fixture(
            1101,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            home="example Home FC",
        ),
        _fixture(
            1102,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            home="Example Away FC",
            away="Example Home FC",
        ),
        _fixture(
            1103,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            competition="Example League",
        ),
        _fixture(1104, dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC)),
        _fixture(1105, dt.datetime(2026, 8, 19, 20, 0, tzinfo=UTC)),
        _fixture(1106, dt.datetime(2026, 8, 18, 20, 0, 30, tzinfo=UTC)),
        _fixture(1107, dt.datetime(2026, 8, 18, 20, 0, 0, 1, tzinfo=UTC)),
    ],
)
def test_no_fuzzy_reversal_tolerance_or_rounding(
    tmp_path: Path,
    fixture: FotMobReviewedFixtureCatalogInput,
) -> None:
    result, _ = _build(tmp_path, [fixture])
    assert result.disposition is (
        partial.PartialCalendarDisposition.NO_EXACT_PARTIAL_CALENDAR_MATCH
    )
    assert result.exact_match_count == 0
    assert result.matched_fixture is None


def test_nonmatching_rows_do_not_create_ambiguity(tmp_path: Path) -> None:
    fixtures = [
        _fixture(1201, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
        _fixture(
            1202,
            dt.datetime(2037, 8, 18, 20, 0, tzinfo=UTC),
            away="Other Away FC",
        ),
    ]
    result, _ = _build(tmp_path, fixtures)
    assert result.exact_match_count == 1
    assert result.matched_fixture is not None
    assert result.matched_fixture.source_fixture_identifier == "1201"


def test_duplicate_fotmob_source_fixture_ids_fail_closed(tmp_path: Path) -> None:
    fixtures = [
        _fixture(1301, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
        _fixture(1301, dt.datetime(2037, 8, 18, 20, 0, tzinfo=UTC)),
    ]
    with pytest.raises(
        partial.SportyBetFotMobPartialCalendarError,
        match="duplicate FotMob source_fixture_identifier",
    ):
        _build(tmp_path, fixtures)


def test_nonreviewed_fotmob_input_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(
        partial.SportyBetFotMobPartialCalendarError,
        match="non-reviewed FotMob",
    ):
        _build(tmp_path, [object()])


def test_supplied_pr158_forgery_is_rederived_and_rejected(tmp_path: Path) -> None:
    time_basis, manifest, inventory, event_raw, qualification, terms_raw = (
        _sportybet_chain(tmp_path)
    )
    forged = dataclasses.replace(time_basis, home_display="Forged Home FC")
    fixture = _fixture(1401, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    with pytest.raises(
        partial.SportyBetFotMobPartialCalendarError,
        match="not the exact deterministic derivative",
    ):
        partial.build_partial_calendar_reconciliation_candidate(
            time_basis=forged,
            event_manifest=manifest,
            event_inventory=inventory,
            event_raw_html=event_raw,
            terms_qualification=qualification,
            terms_raw_html=terms_raw,
            fixtures=[fixture],
        )


def test_candidate_canonicalization_and_population_hash_are_order_deterministic(
    tmp_path: Path,
) -> None:
    a = _fixture(1501, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    b = _fixture(
        1502,
        dt.datetime(2026, 8, 19, 20, 0, tzinfo=UTC),
        home="Other Home",
        away="Other Away",
    )
    result, _ = _build(tmp_path, [b, a])
    assert partial.fotmob_population_sha256([a, b]) == partial.fotmob_population_sha256([b, a])
    payload = partial.canonical_candidate_bytes(result)
    assert payload.endswith(b"\n")
    assert partial.candidate_sha256(result) == partial.candidate_sha256(result)
    parsed = json.loads(payload)
    assert parsed["sportybet_kickoff_year"] is None
    assert parsed["sportybet_kickoff_utc"] is None
    assert parsed["sportybet_year_proven"] is False
    assert all(value is False for value in parsed["safety"].values())


def test_output_cannot_promote_year_utc_or_downstream_authority(tmp_path: Path) -> None:
    fixture = _fixture(1601, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    result, _ = _build(tmp_path, [fixture])
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(result, sportybet_year_proven=True)
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(result, sportybet_kickoff_year=2026)
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(result, sportybet_kickoff_utc="2026-08-18T20:00:00.000000Z")
    promoted = dict(result.safety)
    promoted["fixture_reconciliation_authorized"] = True
    with pytest.raises(partial.SportyBetFotMobPartialCalendarError):
        dataclasses.replace(result, safety=promoted)
