from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from domain import sportradar_user_controlled_event_metadata as metadata
from domain import sportybet_event_local_time_basis as local_time
from domain import sportybet_official_time_semantics as terms
from domain import sportybet_sportradar_event_identity as bridge
from domain import sportybet_sportradar_kickoff_identity_promotion as promotion
from domain import sportybet_sportradar_kickoff_identity_promotion_verification as promotion_verify
from domain import sportybet_user_controlled_evidence as manual
from domain import sportybet_user_controlled_native_inventory as native

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
    "sportybet-sportradar-kickoff-identity-promotion-v1.json"
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
        "<!doctype html><html><body><h1>Terms &amp; Conditions</h1><p>"
        + terms.EXPECTED_STATEMENT
        + "</p></body></html>"
    ).encode("utf-8")


def _sportradar_raw(
    *,
    start_time: str = "2026-08-18T20:00:00Z",
    start_time_confirmed: bool | None = True,
    date_confirmed: bool | None = True,
    replaced_by: str | None = None,
    competition_name: str = "Official Example Competition",
    home_name: str = "Official Example Home",
    away_name: str = "Official Example Away",
) -> bytes:
    sport_event: dict[str, object] = {
        "id": "sr:sport_event:123",
        "start_time": start_time,
        "sport_event_context": {
            "sport": {"id": "sr:sport:1", "name": "Soccer"},
            "competition": {
                "id": "sr:competition:77",
                "name": competition_name,
            },
        },
        "competitors": [
            {"id": "sr:competitor:1001", "name": home_name, "qualifier": "home"},
            {"id": "sr:competitor:1002", "name": away_name, "qualifier": "away"},
        ],
    }
    if start_time_confirmed is not None:
        sport_event["start_time_confirmed"] = start_time_confirmed
    if date_confirmed is not None:
        sport_event["date_confirmed"] = date_confirmed
    if replaced_by is not None:
        sport_event["replaced_by"] = replaced_by
    payload = {
        "generated_at": "2026-08-18T17:04:30Z",
        "sport_event": sport_event,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_chain(
    tmp_path: Path,
    *,
    start_time: str = "2026-08-18T20:00:00Z",
    start_time_confirmed: bool | None = True,
    date_confirmed: bool | None = True,
    replaced_by: str | None = None,
    competition_name: str = "Official Example Competition",
    home_name: str = "Official Example Home",
    away_name: str = "Official Example Away",
):
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
    sportradar_raw = _sportradar_raw(
        start_time=start_time,
        start_time_confirmed=start_time_confirmed,
        date_confirmed=date_confirmed,
        replaced_by=replaced_by,
        competition_name=competition_name,
        home_name=home_name,
        away_name=away_name,
    )
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
    }


def _build(chain):
    return promotion.build_kickoff_identity_promotion(
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["event_raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["event_bridge"],
        sportradar_evidence=chain["sportradar_evidence"],
        sportradar_raw_response=chain["sportradar_raw"],
    )


def _revalidate(value, chain):
    return promotion_verify.revalidate_kickoff_identity_promotion(
        value,
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["event_raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["event_bridge"],
        sportradar_evidence=chain["sportradar_evidence"],
        sportradar_raw_response=chain["sportradar_raw"],
    )


def test_protocol_is_canonical_and_freezes_only_kickoff_promotion() -> None:
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
    assert payload["sportybet_year_promotion_authorized"] is True
    assert payload["sportybet_kickoff_utc_promotion_authorized"] is True
    assert payload["requires_start_time_confirmed_true"] is True
    assert payload["requires_date_confirmed_true"] is True
    assert payload["requires_replaced_by_null"] is True
    assert payload["current_calendar_inference_authorized"] is False
    assert payload["fotmob_input_authorized"] is False
    assert payload["subminute_provider_precision_rounding_authorized"] is False
    assert all(value is False for value in payload["safety"].values())


def test_exact_confirmed_provider_timestamp_promotes_year_and_full_utc(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    result = _build(chain)
    assert result.status == promotion.STATUS
    assert result.sportybet_event_id == "sr:match:123"
    assert result.sportradar_event_id == "sr:sport_event:123"
    assert result.kickoff_display == "18/08 Tuesday 20:00"
    assert result.partial_calendar_match_status == promotion.CALENDAR_MATCH_STATUS
    assert result.confirmation_status == promotion.CONFIRMATION_STATUS
    assert result.replacement_status == promotion.REPLACEMENT_STATUS
    assert result.sportybet_kickoff_year == 2026
    assert result.sportybet_kickoff_timezone == "GMT"
    assert result.sportybet_utc_offset_seconds == 0
    assert result.sportybet_kickoff_utc == dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)
    assert result.sportybet_year_promoted is True
    assert result.sportybet_kickoff_utc_promoted is True
    assert result.provider_event_kickoff_identity_promoted is True
    assert result.fixture_identity_promoted is False
    assert result.fotmob_fixture_reconciliation_authorized is False
    assert result.provider_quote_at is None
    assert result.provider_snapshot_id is None
    assert all(value is False for value in result.safety.values())
    assert _revalidate(result, chain) == result


def test_provider_subminute_precision_is_preserved_not_rounded(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path, start_time="2026-08-18T20:00:37.123456+00:00")
    result = _build(chain)
    assert result.sportradar_start_time == "2026-08-18T20:00:37.123456+00:00"
    assert result.sportybet_kickoff_utc == dt.datetime(
        2026, 8, 18, 20, 0, 37, 123456, tzinfo=UTC
    )
    assert result.provider_timestamp_subminute_precision_preserved is True


@pytest.mark.parametrize("confirmed", [False, None])
def test_start_time_must_be_explicitly_confirmed(tmp_path: Path, confirmed: bool | None) -> None:
    chain = _source_chain(tmp_path, start_time_confirmed=confirmed)
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="start_time_confirmed must be exact True",
    ):
        _build(chain)


@pytest.mark.parametrize("confirmed", [False, None])
def test_date_must_be_explicitly_confirmed(tmp_path: Path, confirmed: bool | None) -> None:
    chain = _source_chain(tmp_path, date_confirmed=confirmed)
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="date_confirmed must be exact True",
    ):
        _build(chain)


def test_replaced_event_fails_closed(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path, replaced_by="sr:sport_event:999")
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="replaced_by",
    ):
        _build(chain)


@pytest.mark.parametrize(
    "start_time",
    [
        "2026-08-19T20:00:00Z",
        "2026-08-18T20:01:00Z",
        "2026-09-18T20:00:00Z",
        "2025-08-18T20:00:00Z",
    ],
)
def test_any_partial_calendar_disagreement_fails_closed(tmp_path: Path, start_time: str) -> None:
    chain = _source_chain(tmp_path, start_time=start_time)
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="does not exactly match SportyBet GMT partial calendar",
    ):
        _build(chain)


def test_current_calendar_is_not_used_to_choose_the_year(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path, start_time="2020-08-18T20:00:00Z")
    result = _build(chain)
    assert result.sportybet_kickoff_year == 2020
    assert result.sportybet_kickoff_utc == dt.datetime(2020, 8, 18, 20, 0, tzinfo=UTC)


def test_official_names_are_preserved_but_do_not_claim_name_equivalence(tmp_path: Path) -> None:
    chain = _source_chain(
        tmp_path,
        competition_name="Provider Competition Label",
        home_name="Provider Home Label",
        away_name="Provider Away Label",
    )
    result = _build(chain)
    assert result.competition_display == "Example Country - Example League"
    assert result.home_display == "Example Home FC"
    assert result.away_display == "Example Away FC"
    assert result.sportradar_competition_name == "Provider Competition Label"
    assert result.sportradar_home_competitor_name == "Provider Home Label"
    assert result.sportradar_away_competitor_name == "Provider Away Label"
    assert result.fixture_identity_promoted is False
    assert result.fotmob_fixture_reconciliation_authorized is False


def test_canonical_output_is_deterministic(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    first = _build(chain)
    second = _build(chain)
    assert promotion.canonical_promotion_bytes(first) == promotion.canonical_promotion_bytes(second)
    assert promotion.promotion_sha256(first) == promotion.promotion_sha256(second)
