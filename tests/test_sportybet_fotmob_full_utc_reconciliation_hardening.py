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
from domain.fixture_catalog import compile_fixture_catalog, sha256_bytes
from domain.fotmob_data_matches_capture import (
    CapturedFotMobDataMatchesResponse,
    build_data_matches_capture_manifest,
)
from domain.fotmob_fixture_candidate_review import (
    FixtureCandidateReviewDisposition,
    FotMobFixtureCandidateReviewDecision,
    build_fotmob_fixture_candidate_review_bundle,
    sha256_fotmob_fixture_candidate,
)
from domain.fotmob_fixture_candidates import build_fotmob_fixture_candidate_bundle
from domain.fotmob_fixture_catalog_handoff import (
    build_fotmob_fixture_catalog_handoff,
    sha256_fotmob_fixture_catalog_handoff,
)
from domain.reviewed_fixture_catalog_admission import (
    REVIEWED_SOURCE_CAPABILITY,
    ReviewedFixtureCatalogAdmissionDecision,
    ReviewedFixtureCatalogAdmissionDisposition,
    build_reviewed_fixture_catalog_admission,
    sha256_reviewed_source_capability,
)
from domain.source_capabilities import CapabilityAvailability, SOURCE_CAPABILITY_REGISTRY

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
    repo = tmp_path / "sportybet"
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


def _epoch_ms(value: dt.datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _match(
    match_id: int,
    *,
    home: str = "Example Home FC",
    away: str = "Example Away FC",
    kickoff: dt.datetime = dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
) -> dict:
    kickoff = kickoff.astimezone(UTC)
    utc_time = kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "away": {"id": 2000 + match_id, "score": 0, "name": away, "longName": away},
        "eliminatedTeamId": None,
        "home": {"id": 1000 + match_id, "score": 0, "name": home, "longName": home},
        "id": match_id,
        "leagueId": 77,
        "status": {
            "utcTime": utc_time,
            "halfs": {"firstHalfStarted": ""},
            "periodLength": 45,
            "started": False,
            "cancelled": False,
            "finished": False,
        },
        "statusId": 1,
        "time": kickoff.strftime("%d.%m.%Y %H:%M"),
        "timeTS": _epoch_ms(kickoff),
        "tournamentStage": "",
    }


def _capture(
    *,
    match: dict | None = None,
    competition: str = "Example Country - Example League",
):
    payload = {
        "leagues": [
            {
                "ccode": "NGA",
                "id": 77,
                "internalRank": 1,
                "matches": [match or _match(3001)],
                "name": competition,
                "primaryId": 77,
                "simpleLeague": False,
            }
        ],
        "date": "20260818",
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=dt.datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date="20260818",
        timezone="UTC",
        ccode3="NGA",
    )
    return raw, manifest


def _admission(
    tmp_path: Path,
    *,
    match: dict | None = None,
    competition: str = "Example Country - Example League",
):
    capture = _capture(match=match, competition=competition)
    candidate_bundle = build_fotmob_fixture_candidate_bundle((capture,))
    candidate = candidate_bundle.candidates[0]
    review = build_fotmob_fixture_candidate_review_bundle(
        candidate_bundle,
        (
            FotMobFixtureCandidateReviewDecision(
                source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
                source_match_id=candidate.source_match_id,
                candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
                disposition=FixtureCandidateReviewDisposition.APPROVED,
                reviewed_at=dt.datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
                reviewer_reference="operator:hardening-fixture-review",
                notes="explicit source-backed review",
            ),
        ),
    )
    handoff = build_fotmob_fixture_catalog_handoff(candidate_bundle, review)
    raw = capture[0]
    for item in handoff.catalog_inputs:
        evidence_path = tmp_path / item.evidence_file_path
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(raw)
    input_path = tmp_path / "hardening-reviewed.jsonl"
    input_path.write_bytes(handoff.catalog_input_jsonl_bytes)
    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=tmp_path,
        as_of=dt.datetime(2026, 8, 18, 11, 0, tzinfo=UTC),
        minimum_lead_seconds=3600,
        code_state={
            "evidence_git_head_sha": "b" * 40,
            "tracked_worktree_clean": True,
        },
    )
    decision = ReviewedFixtureCatalogAdmissionDecision(
        candidate_bundle_sha256=handoff.candidate_bundle_sha256,
        review_bundle_sha256=handoff.review_bundle_sha256,
        handoff_sha256=sha256_fotmob_fixture_catalog_handoff(handoff),
        catalog_sha256=sha256_bytes(result.catalog_bytes),
        manifest_sha256=sha256_bytes(result.manifest_bytes),
        source_capability=REVIEWED_SOURCE_CAPABILITY,
        source_capability_sha256=sha256_reviewed_source_capability(),
        disposition=ReviewedFixtureCatalogAdmissionDisposition.ADMITTED,
        reviewed_at=dt.datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        reviewer_reference="operator:hardening-catalog-admission",
        notes="catalog-level admission",
    )
    admission = build_reviewed_fixture_catalog_admission(handoff, result, decision)
    return admission, (capture,)


def _build(chain, admission, captures):
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
        fotmob_admission_value=admission,
        fotmob_captures=captures,
    )


def _verify(value, chain, admission, captures):
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
        fotmob_admission_value=admission,
        fotmob_captures=captures,
    )


def test_sportradar_labels_are_not_silently_used_as_fotmob_aliases(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(
        tmp_path,
        match=_match(
            3001,
            home="Different Official Home Label",
            away="Different Official Away Label",
        ),
        competition="Different Official Competition Label",
    )
    result = _build(chain, admission, captures)
    assert result.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert result.fixture_reconciliation_authorized is False


def test_hash_shaped_final_artifact_forgery_is_rejected_by_source_aware_verifier(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    result = _build(chain, admission, captures)
    forged = dataclasses.replace(result, source_event_raw_sha256="e" * 64)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain, admission, captures)


def test_matched_fotmob_lineage_forgery_is_rejected_by_source_aware_verifier(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    result = _build(chain, admission, captures)
    assert result.matched_fixture is not None
    forged_hash = "f" * 64
    assert result.matched_fixture.evidence_sha256 != forged_hash
    forged_match = dataclasses.replace(result.matched_fixture, evidence_sha256=forged_hash)
    forged = dataclasses.replace(result, matched_fixture=forged_match)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain, admission, captures)


def test_hash_shaped_fotmob_admission_lineage_forgery_is_rejected(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    result = _build(chain, admission, captures)
    forged = dataclasses.replace(result, source_fotmob_admission_sha256="c" * 64)
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="not the exact deterministic derivative",
    ):
        _verify(forged, chain, admission, captures)


def test_different_raw_capture_cannot_reuse_prior_admission_or_authorized_result(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    result = _build(chain, admission, captures)
    different_capture = _capture(match=_match(3999, home="Fabricated Home"))
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        _verify(result, chain, admission, (different_capture,))


def test_raw_sportybet_tampering_is_rejected_before_fixture_authority(tmp_path: Path) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
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
            fotmob_admission_value=admission,
            fotmob_captures=captures,
        )


def test_current_reviewed_source_capability_revocation_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    current = SOURCE_CAPABILITY_REGISTRY[REVIEWED_SOURCE_CAPABILITY]
    monkeypatch.setitem(
        SOURCE_CAPABILITY_REGISTRY,
        REVIEWED_SOURCE_CAPABILITY,
        dataclasses.replace(
            current,
            reliable_fixture_identity=CapabilityAvailability.UNKNOWN,
        ),
    )
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="identity-only PR #44 profile",
    ):
        _build(chain, admission, captures)


def test_authorized_result_cannot_enable_any_non_fixture_safety_capability(
    tmp_path: Path,
) -> None:
    chain = _chain(tmp_path)
    admission, captures = _admission(tmp_path)
    result = _build(chain, admission, captures)
    assert result.fixture_reconciliation_authorized is True
    for key in result.safety:
        if key == "fixture_reconciliation_authorized":
            continue
        forged_safety = dict(result.safety)
        forged_safety[key] = True
        with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
            dataclasses.replace(result, safety=forged_safety)
