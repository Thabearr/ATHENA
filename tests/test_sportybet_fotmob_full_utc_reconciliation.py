from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_fotmob_full_utc_reconciliation as full
from domain import sportybet_fotmob_full_utc_reconciliation_verification as full_verify
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_kickoff_identity_promotion as promotion
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native
from domain.fotmob_fixture_candidate_review import FotMobReviewedFixtureCatalogInput

UTC = dt.timezone.utc
EVENT_OBSERVED = dt.datetime(2026, 8, 18, 17, 0, tzinfo=UTC)
EVENT_IMPORTED = dt.datetime(2026, 8, 18, 17, 1, tzinfo=UTC)
TERMS_OBSERVED = dt.datetime(2026, 8, 18, 16, 55, tzinfo=UTC)
TERMS_IMPORTED = dt.datetime(2026, 8, 18, 16, 56, tzinfo=UTC)
SPORTRADAR_OBSERVED = dt.datetime(2026, 8, 18, 17, 5, tzinfo=UTC)
SPORTRADAR_IMPORTED = dt.datetime(2026, 8, 18, 17, 6, tzinfo=UTC)
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
SPORTRADAR_URL = (
    "https://api.sportradar.com/soccer/trial/v4/en/"
    "sport_events/sr:sport_event:123/summary.json"
)
PROTOCOL = Path(
    "artifacts/research-protocols/"
    "sportybet-fotmob-full-utc-reconciliation-v1.json"
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


def _sportradar_raw(*, start_time: str = "2026-08-18T20:00:00Z") -> bytes:
    payload = {
        "generated_at": "2026-08-18T17:04:30Z",
        "sport_event": {
            "id": "sr:sport_event:123",
            "start_time": start_time,
            "start_time_confirmed": True,
            "date_confirmed": True,
            "sport_event_context": {
                "sport": {"id": "sr:sport:1", "name": "Soccer"},
                "competition": {
                    "id": "sr:competition:77",
                    "name": "Official Example Competition",
                },
            },
            "competitors": [
                {
                    "id": "sr:competitor:1001",
                    "name": "Official Example Home",
                    "qualifier": "home",
                },
                {
                    "id": "sr:competitor:1002",
                    "name": "Official Example Away",
                    "qualifier": "away",
                },
            ],
        },
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_chain(tmp_path: Path, *, start_time: str = "2026-08-18T20:00:00Z"):
    repo = tmp_path / "repo"
    repo.mkdir()
    event_raw = _event_raw()
    event_dir, manifest = manual.store_user_controlled_evidence(
        event_raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=EVENT_OBSERVED,
        imported_at_utc=EVENT_IMPORTED,
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        event_dir,
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
    time_basis = local_time.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    event_bridge = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=event_raw,
    )
    sportradar_raw = _sportradar_raw(start_time=start_time)
    sportradar_evidence = metadata.build_event_metadata_evidence(
        sportradar_raw,
        source_url=SPORTRADAR_URL,
        observed_at_user_attested=SPORTRADAR_OBSERVED,
        imported_at_utc=SPORTRADAR_IMPORTED,
        attestation=metadata.ATTESTATION,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=event_raw,
    )
    kickoff_promotion = promotion.build_kickoff_identity_promotion(
        event_time_basis=time_basis,
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=event_raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
        event_bridge=event_bridge,
        sportradar_evidence=sportradar_evidence,
        sportradar_raw_response=sportradar_raw,
    )
    return {
        "manifest": manifest,
        "inventory": inventory,
        "event_raw": event_raw,
        "qualification": qualification,
        "terms_raw": terms_raw,
        "time_basis": time_basis,
        "event_bridge": event_bridge,
        "sportradar_raw": sportradar_raw,
        "sportradar_evidence": sportradar_evidence,
        "kickoff_promotion": kickoff_promotion,
    }


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


def _build(chain, fixtures):
    return full.build_full_utc_reconciliation(
        kickoff_promotion=chain["kickoff_promotion"],
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["event_raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["event_bridge"],
        sportradar_evidence=chain["sportradar_evidence"],
        sportradar_raw_response=chain["sportradar_raw"],
        fixtures=fixtures,
    )


def _revalidate(value, chain, fixtures):
    return full_verify.revalidate_full_utc_reconciliation(
        value,
        kickoff_promotion=chain["kickoff_promotion"],
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["event_raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["event_bridge"],
        sportradar_evidence=chain["sportradar_evidence"],
        sportradar_raw_response=chain["sportradar_raw"],
        fixtures=fixtures,
    )


def test_protocol_is_canonical_and_authorizes_only_unique_fixture_reconciliation() -> None:
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
    assert payload["requires_exact_pr162_rederivation"] is True
    assert payload["exact_matching_fields"] == [
        "home",
        "away",
        "competition",
        "kickoff_utc",
    ]
    assert payload["fixture_reconciliation_authorization"] == (
        "TRUE_ONLY_FOR_UNIQUE_EXACT_MATCH"
    )
    assert payload["fuzzy_matching_authorized"] is False
    assert payload["home_away_reversal_authorized"] is False
    assert payload["kickoff_rounding_authorized"] is False
    assert payload["kickoff_tolerance_authorized"] is False
    assert payload["network_acquisition_authorized"] is False
    assert all(value is False for value in payload["non_fixture_downstream_safety"].values())


def test_unique_exact_full_utc_match_authorizes_fixture_reconciliation_only(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    fixture = _fixture(2001, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    result = _build(chain, [fixture])
    assert result.disposition is (
        full.FullUtcReconciliationDisposition.UNIQUE_EXACT_FULL_UTC_MATCH_RECONCILED
    )
    assert result.exact_match_count == 1
    assert result.matched_fixture is not None
    assert result.matched_fixture.source_fixture_identifier == "2001"
    assert result.fixture_reconciliation_authorized is True
    assert result.safety["fixture_reconciliation_authorized"] is True
    assert all(
        value is False
        for key, value in result.safety.items()
        if key != "fixture_reconciliation_authorized"
    )
    assert result.sportybet_kickoff_utc == dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)
    assert _revalidate(result, chain, [fixture]) == result


@pytest.mark.parametrize(
    "fixture",
    [
        _fixture(
            2101,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            home="example Home FC",
        ),
        _fixture(
            2102,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            home="Example Away FC",
            away="Example Home FC",
        ),
        _fixture(
            2103,
            dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
            competition="Example League",
        ),
        _fixture(2104, dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC)),
        _fixture(2105, dt.datetime(2026, 8, 18, 20, 0, 1, tzinfo=UTC)),
        _fixture(2106, dt.datetime(2026, 8, 18, 20, 0, 0, 1, tzinfo=UTC)),
    ],
)
def test_no_fuzzy_reversal_rounding_or_tolerance(
    tmp_path: Path,
    fixture: FotMobReviewedFixtureCatalogInput,
) -> None:
    chain = _source_chain(tmp_path)
    result = _build(chain, [fixture])
    assert result.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert result.exact_match_count == 0
    assert result.matched_fixture is None
    assert result.fixture_reconciliation_authorized is False
    assert all(value is False for value in result.safety.values())


def test_multiple_exact_rows_are_ambiguous_and_choose_none(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    fixtures = [
        _fixture(2201, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
        _fixture(2202, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
    ]
    result = _build(chain, fixtures)
    assert result.disposition is (
        full.FullUtcReconciliationDisposition.AMBIGUOUS_EXACT_FULL_UTC_MATCH
    )
    assert result.exact_match_count == 2
    assert result.matched_fixture is None
    assert result.fixture_reconciliation_authorized is False
    assert all(value is False for value in result.safety.values())


def test_duplicate_fotmob_source_ids_fail_closed(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    fixtures = [
        _fixture(2301, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)),
        _fixture(2301, dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC)),
    ]
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="duplicate FotMob source_fixture_identifier",
    ):
        _build(chain, fixtures)


def test_nonreviewed_fotmob_input_fails_closed(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="non-reviewed FotMob",
    ):
        _build(chain, [object()])


def test_empty_fotmob_population_fails_closed(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="at least one reviewed FotMob fixture",
    ):
        _build(chain, [])


def test_exact_subminute_provider_precision_must_match_fotmob_exactly(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path, start_time="2026-08-18T20:00:37.123456Z")
    exact = _fixture(
        2401,
        dt.datetime(2026, 8, 18, 20, 0, 37, 123456, tzinfo=UTC),
    )
    result = _build(chain, [exact])
    assert result.fixture_reconciliation_authorized is True
    assert result.matched_fixture is not None
    nearby = _fixture(
        2402,
        dt.datetime(2026, 8, 18, 20, 0, 37, 123455, tzinfo=UTC),
    )
    no_match = _build(chain, [nearby])
    assert no_match.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert no_match.fixture_reconciliation_authorized is False


def test_fotmob_population_hash_and_result_are_order_deterministic(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    a = _fixture(2501, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    b = _fixture(
        2502,
        dt.datetime(2026, 8, 19, 20, 0, tzinfo=UTC),
        home="Other Home",
        away="Other Away",
    )
    first = _build(chain, [b, a])
    second = _build(chain, [a, b])
    assert full.fotmob_population_sha256([a, b]) == full.fotmob_population_sha256([b, a])
    assert full.canonical_reconciliation_bytes(first) == full.canonical_reconciliation_bytes(second)
    assert full.reconciliation_sha256(first) == full.reconciliation_sha256(second)


def test_forged_pr162_promotion_is_rederived_and_rejected(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    forged = dataclasses.replace(
        chain["kickoff_promotion"],
        source_event_raw_sha256="f" * 64,
    )
    fixture = _fixture(2601, dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC))
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        full.build_full_utc_reconciliation(
            kickoff_promotion=forged,
            event_time_basis=chain["time_basis"],
            event_manifest=chain["manifest"],
            event_inventory=chain["inventory"],
            event_raw_html=chain["event_raw"],
            terms_qualification=chain["qualification"],
            terms_raw_html=chain["terms_raw"],
            event_bridge=chain["event_bridge"],
            sportradar_evidence=chain["sportradar_evidence"],
            sportradar_raw_response=chain["sportradar_raw"],
            fixtures=[fixture],
        )


def test_no_match_cannot_be_manually_promoted_to_fixture_authority(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    fixture = _fixture(2701, dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC))
    result = _build(chain, [fixture])
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        dataclasses.replace(result, fixture_reconciliation_authorized=True)
    forged_safety = dict(result.safety)
    forged_safety["fixture_reconciliation_authorized"] = True
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        dataclasses.replace(result, safety=forged_safety)
