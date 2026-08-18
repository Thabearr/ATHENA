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


def _terms_raw() -> bytes:
    return (
        "<!doctype html><html><body><p>"
        + terms.EXPECTED_STATEMENT
        + "</p></body></html>"
    ).encode("utf-8")


def _sportradar_raw() -> bytes:
    payload = {
        "generated_at": "2026-08-18T17:04:30Z",
        "sport_event": {
            "id": "sr:sport_event:123",
            "start_time": "2026-08-18T20:00:00Z",
            "start_time_confirmed": True,
            "date_confirmed": True,
            "sport_event_context": {
                "sport": {"id": "sr:sport:1", "name": "Soccer"},
                "competition": {
                    "id": "sr:competition:77",
                    "name": "Different Official Competition Label",
                },
            },
            "competitors": [
                {
                    "id": "sr:competitor:1001",
                    "name": "Different Official Home Label",
                    "qualifier": "home",
                },
                {
                    "id": "sr:competitor:1002",
                    "name": "Different Official Away Label",
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


def _chain(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    event_raw = _event_raw()
    event_dir, manifest = manual.store_user_controlled_evidence(
        event_raw,
        source_url=DETAIL_URL,
        observed_at_user_attested=dt.datetime(2026, 8, 18, 17, 0, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 17, 1, tzinfo=UTC),
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
        observed_at_user_attested=dt.datetime(2026, 8, 18, 16, 55, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 16, 56, tzinfo=UTC),
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
    sportradar_raw = _sportradar_raw()
    sportradar_evidence = metadata.build_event_metadata_evidence(
        sportradar_raw,
        source_url=SPORTRADAR_URL,
        observed_at_user_attested=dt.datetime(2026, 8, 18, 17, 5, tzinfo=UTC),
        imported_at_utc=dt.datetime(2026, 8, 18, 17, 6, tzinfo=UTC),
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
    *,
    home: str = "Example Home FC",
    away: str = "Example Away FC",
    competition: str = "Example Country - Example League",
    kickoff: dt.datetime = dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
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
        source_reference="FotMob /api/data/matches capture manifest sha256:" + capture_sha,
        reviewed_at=dt.datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        evidence_file_path=f"evidence/{fixture_id}.json",
        evidence_sha256=evidence_sha,
        reviewer_reference="hardening-reviewed",
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


def _verify(value, chain, fixtures):
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


def test_sportradar_labels_are_not_silently_used_as_fotmob_aliases(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    official_label_fixture = _fixture(
        3001,
        home="Different Official Home Label",
        away="Different Official Away Label",
        competition="Different Official Competition Label",
    )
    result = _build(chain, [official_label_fixture])
    assert result.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert result.fixture_reconciliation_authorized is False


def test_hash_shaped_final_artifact_forgery_is_rejected_by_source_aware_verifier(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    fixture = _fixture(3002)
    result = _build(chain, [fixture])
    forged = dataclasses.replace(result, source_event_raw_sha256="e" * 64)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain, [fixture])


def test_matched_fotmob_lineage_forgery_is_rejected_by_source_aware_verifier(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    fixture = _fixture(3003)
    result = _build(chain, [fixture])
    assert result.matched_fixture is not None
    forged_match = dataclasses.replace(result.matched_fixture, evidence_sha256="d" * 64)
    forged = dataclasses.replace(result, matched_fixture=forged_match)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain, [fixture])


def test_different_fotmob_population_cannot_reuse_prior_authorized_result(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    exact = _fixture(3004)
    result = _build(chain, [exact])
    replacement_population = [
        _fixture(
            3005,
            kickoff=dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC),
        )
    ]
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(result, chain, replacement_population)


def test_raw_sportybet_tampering_is_rejected_before_fixture_authority(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    fixture = _fixture(3006)
    tampered = chain["event_raw"] + b"<!--tamper-->"
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        full.build_full_utc_reconciliation(
            kickoff_promotion=chain["kickoff_promotion"],
            event_time_basis=chain["time_basis"],
            event_manifest=chain["manifest"],
            event_inventory=chain["inventory"],
            event_raw_html=tampered,
            terms_qualification=chain["qualification"],
            terms_raw_html=chain["terms_raw"],
            event_bridge=chain["event_bridge"],
            sportradar_evidence=chain["sportradar_evidence"],
            sportradar_raw_response=chain["sportradar_raw"],
            fixtures=[fixture],
        )


def test_authorized_result_cannot_enable_any_non_fixture_safety_capability(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    result = _build(chain, [_fixture(3007)])
    assert result.fixture_reconciliation_authorized is True
    for key in result.safety:
        if key == "fixture_reconciliation_authorized":
            continue
        forged_safety = dict(result.safety)
        forged_safety[key] = True
        with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
            dataclasses.replace(result, safety=forged_safety)
