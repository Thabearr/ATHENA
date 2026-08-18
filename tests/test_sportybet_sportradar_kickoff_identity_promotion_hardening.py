from __future__ import annotations

import dataclasses
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
DETAIL_URL = (
    "https://www.sportybet.com/ng/lite/preMatch/detail?"
    "eventId=sr%3Amatch%3A123&marketGroupsName=Main&sportId=sr%3Asport%3A1"
)
SPORTRADAR_URL = (
    "https://api.sportradar.com/soccer/trial/v4/en/"
    "sport_events/sr:sport_event:123/summary.json"
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


def _chain(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = _event_raw()
    evidence_dir, manifest = manual.store_user_controlled_evidence(
        raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=dt.datetime(2026, 8, 18, 17, 0, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 17, 1, tzinfo=UTC),
        attestation=manual.ATTESTATION,
        repository_root=repo,
    )
    inventory = native.build_inventory_from_evidence(
        evidence_dir,
        allowed_root=repo / manual.ALLOWED_OUTPUT_RELATIVE,
    )
    terms_raw = (
        "<!doctype html><html><body><p>" + terms.EXPECTED_STATEMENT + "</p></body></html>"
    ).encode()
    qualification = terms.build_qualification(
        terms_raw,
        source_url=terms.SOURCE_URL,
        observed_at_user_attested=dt.datetime(2026, 8, 18, 16, 55, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 16, 56, tzinfo=UTC),
        attestation=terms.ATTESTATION,
    )
    time_basis = local_time.build_event_local_time_basis(
        event_manifest=manifest,
        event_inventory=inventory,
        event_raw_html=raw,
        terms_qualification=qualification,
        terms_raw_html=terms_raw,
    )
    event_bridge = bridge.build_sportradar_event_identity_bridge(
        manifest=manifest,
        inventory=inventory,
        raw_html=raw,
    )
    response = json.dumps(
        {
            "sport_event": {
                "id": "sr:sport_event:123",
                "start_time": "2026-08-18T21:00:00+01:00",
                "start_time_confirmed": True,
                "date_confirmed": True,
                "sport_event_context": {
                    "sport": {"id": "sr:sport:1", "name": "Soccer"},
                    "competition": {
                        "id": "sr:competition:77",
                        "name": "Official Competition",
                    },
                },
                "competitors": [
                    {"id": "sr:competitor:1001", "name": "Official Home", "qualifier": "home"},
                    {"id": "sr:competitor:1002", "name": "Official Away", "qualifier": "away"},
                ],
            }
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    evidence = metadata.build_event_metadata_evidence(
        response,
        source_url=SPORTRADAR_URL,
        observed_at_user_attested=dt.datetime(2026, 8, 18, 17, 5, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 17, 6, tzinfo=UTC),
        attestation=metadata.ATTESTATION,
        event_bridge=event_bridge,
        sportybet_manifest=manifest,
        sportybet_inventory=inventory,
        sportybet_raw_html=raw,
    )
    return {
        "manifest": manifest,
        "inventory": inventory,
        "raw": raw,
        "qualification": qualification,
        "terms_raw": terms_raw,
        "time_basis": time_basis,
        "bridge": event_bridge,
        "response": response,
        "evidence": evidence,
    }


def _build(chain):
    return promotion.build_kickoff_identity_promotion(
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["bridge"],
        sportradar_evidence=chain["evidence"],
        sportradar_raw_response=chain["response"],
    )


def _verify(value, chain):
    return promotion_verify.revalidate_kickoff_identity_promotion(
        value,
        event_time_basis=chain["time_basis"],
        event_manifest=chain["manifest"],
        event_inventory=chain["inventory"],
        event_raw_html=chain["raw"],
        terms_qualification=chain["qualification"],
        terms_raw_html=chain["terms_raw"],
        event_bridge=chain["bridge"],
        sportradar_evidence=chain["evidence"],
        sportradar_raw_response=chain["response"],
    )


def test_non_utc_provider_offset_is_normalized_before_exact_gmt_comparison(tmp_path: Path) -> None:
    result = _build(_chain(tmp_path))
    assert result.sportradar_start_time == "2026-08-18T21:00:00+01:00"
    assert result.sportradar_start_time_utc_normalized == "2026-08-18T20:00:00.000000Z"
    assert result.sportybet_kickoff_utc == dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC)


def test_forged_time_basis_is_rejected_by_exact_source_rederivation(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["time_basis"] = dataclasses.replace(
        chain["time_basis"],
        competition_display="Different Visible Competition",
    )
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="exact deterministic derivative",
    ):
        _build(chain)


def test_hash_shaped_forged_bridge_lineage_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["bridge"] = dataclasses.replace(
        chain["bridge"],
        source_event_candidate_sha256="0" * 64,
    )
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="exact deterministic derivative",
    ):
        _build(chain)


def test_hash_shaped_forged_metadata_lineage_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["evidence"] = dataclasses.replace(chain["evidence"], raw_sha256="0" * 64)
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="exact deterministic derivative",
    ):
        _build(chain)


def test_raw_sportradar_response_tampering_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["response"] = chain["response"].replace(
        b"Official Competition", b"Tampered Competition"
    )
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="exact deterministic derivative",
    ):
        _build(chain)


def test_raw_sportybet_source_tampering_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["raw"] = chain["raw"].replace(b"Example Home FC", b"Tampered Home FC")
    with pytest.raises(promotion.SportyBetSportradarKickoffIdentityPromotionError):
        _build(chain)


def test_terms_source_tampering_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    chain["terms_raw"] = chain["terms_raw"].replace(b"GMT", b"UTC")
    with pytest.raises(promotion.SportyBetSportradarKickoffIdentityPromotionError):
        _build(chain)


def test_hash_shaped_forged_promotion_fails_consumption_time_revalidation(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    result = _build(chain)
    forged = dataclasses.replace(result, source_metadata_evidence_sha256="0" * 64)
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain)


def test_serialized_promotion_does_not_gain_fotmob_or_betting_authority(tmp_path: Path) -> None:
    payload = json.loads(promotion.canonical_promotion_bytes(_build(_chain(tmp_path))))
    assert payload["fixture_identity_promoted"] is False
    assert payload["fotmob_fixture_reconciliation_authorized"] is False
    assert payload["provider_quote_at"] is None
    assert payload["provider_snapshot_id"] is None
    assert all(value is False for value in payload["safety"].values())


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("fixture_identity_promoted", True),
        ("fotmob_fixture_reconciliation_authorized", True),
    ],
)
def test_downstream_promotion_flags_cannot_be_enabled(
    tmp_path: Path, field_name: str, value: bool
) -> None:
    result = _build(_chain(tmp_path))
    with pytest.raises(promotion.SportyBetSportradarKickoffIdentityPromotionError):
        dataclasses.replace(result, **{field_name: value})


def test_any_safety_authority_true_is_rejected(tmp_path: Path) -> None:
    result = _build(_chain(tmp_path))
    safety = dict(result.safety)
    safety["pricing_authorized"] = True
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="must be exact bool False",
    ):
        dataclasses.replace(result, safety=safety)


def test_event_source_url_must_bind_promoted_event_identity(tmp_path: Path) -> None:
    result = _build(_chain(tmp_path))
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="event source URL does not match",
    ):
        dataclasses.replace(result, sportybet_event_id="sr:match:124")


def test_structural_official_ids_remain_canonical(tmp_path: Path) -> None:
    result = _build(_chain(tmp_path))
    with pytest.raises(
        promotion.SportyBetSportradarKickoffIdentityPromotionError,
        match="sportradar_competition_id is invalid",
    ):
        dataclasses.replace(result, sportradar_competition_id="competition-77")


def test_verifier_accepts_exact_unmodified_promotion(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    result = _build(chain)
    verified = _verify(result, chain)
    assert promotion.canonical_promotion_bytes(verified) == promotion.canonical_promotion_bytes(result)
