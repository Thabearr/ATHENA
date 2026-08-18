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
    repo = tmp_path / "sportybet"
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


def _epoch_ms(value: dt.datetime) -> int:
    return int(value.astimezone(UTC).timestamp() * 1000)


def _fotmob_match(
    match_id: int,
    *,
    home: str = "Example Home FC",
    away: str = "Example Away FC",
    competition_kickoff: dt.datetime = dt.datetime(2026, 8, 18, 20, 0, tzinfo=UTC),
    league_id: int = 77,
) -> dict:
    kickoff = competition_kickoff.astimezone(UTC)
    utc_time = kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "away": {"id": 2000 + match_id, "score": 0, "name": away, "longName": away},
        "eliminatedTeamId": None,
        "home": {"id": 1000 + match_id, "score": 0, "name": home, "longName": home},
        "id": match_id,
        "leagueId": league_id,
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


def _fotmob_capture(
    matches: list[dict],
    *,
    competition: str = "Example Country - Example League",
    observed_second: int = 0,
):
    payload = {
        "leagues": [
            {
                "ccode": "NGA",
                "id": 77,
                "internalRank": 1,
                "matches": matches,
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
        observed_at=dt.datetime(2026, 8, 18, 9, 0, observed_second, tzinfo=UTC),
        network_acquisition_performed=True,
    )
    manifest = build_data_matches_capture_manifest(
        response,
        request_date="20260818",
        timezone="UTC",
        ccode3="NGA",
    )
    return raw, manifest


def _fotmob_admission(
    tmp_path: Path,
    *,
    matches: list[dict] | None = None,
    competition: str = "Example Country - Example League",
    disposition: ReviewedFixtureCatalogAdmissionDisposition = (
        ReviewedFixtureCatalogAdmissionDisposition.ADMITTED
    ),
):
    capture = _fotmob_capture(
        matches or [_fotmob_match(2001)],
        competition=competition,
    )
    candidate_bundle = build_fotmob_fixture_candidate_bundle((capture,))
    decisions = tuple(
        FotMobFixtureCandidateReviewDecision(
            source_capture_manifest_sha256=candidate.source_capture_manifest_sha256,
            source_match_id=candidate.source_match_id,
            candidate_sha256=sha256_fotmob_fixture_candidate(candidate),
            disposition=FixtureCandidateReviewDisposition.APPROVED,
            reviewed_at=dt.datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
            reviewer_reference="operator:full-utc-fixture-review",
            notes="explicit reviewed FotMob fixture identity",
        )
        for candidate in candidate_bundle.candidates
    )
    review_bundle = build_fotmob_fixture_candidate_review_bundle(
        candidate_bundle,
        decisions,
    )
    handoff = build_fotmob_fixture_catalog_handoff(candidate_bundle, review_bundle)
    raw = capture[0]
    for item in handoff.catalog_inputs:
        evidence_path = tmp_path / item.evidence_file_path
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_bytes(raw)
    input_path = tmp_path / "reviewed-fotmob.jsonl"
    input_path.write_bytes(handoff.catalog_input_jsonl_bytes)
    result = compile_fixture_catalog(
        input_path=input_path,
        evidence_root=tmp_path,
        as_of=dt.datetime(2026, 8, 18, 11, 0, tzinfo=UTC),
        minimum_lead_seconds=3600,
        code_state={
            "evidence_git_head_sha": "a" * 40,
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
        disposition=disposition,
        reviewed_at=dt.datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
        reviewer_reference="operator:full-utc-catalog-admission",
        notes="catalog-level identity admission",
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


def _revalidate(value, chain, admission, captures):
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


def test_protocol_is_canonical_and_requires_both_source_replays() -> None:
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
    assert payload["requires_admitted_fotmob_catalog"] is True
    assert payload["requires_fotmob_candidate_replay_from_raw_captures"] is True
    assert payload["requires_fotmob_review_replay"] is True
    assert payload["requires_exact_fotmob_handoff_rebuild"] is True
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


def test_unique_exact_source_replayed_match_authorizes_fixture_only(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(tmp_path)
    result = _build(chain, admission, captures)
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
    assert result.source_fotmob_admission_sha256 == (
        full.fotmob_admission.sha256_reviewed_fixture_catalog_admission(admission)
    )
    assert _revalidate(result, chain, admission, captures) == result


@pytest.mark.parametrize(
    ("matches", "competition"),
    [
        ([_fotmob_match(2101, home="example Home FC")], "Example Country - Example League"),
        (
            [_fotmob_match(2102, home="Example Away FC", away="Example Home FC")],
            "Example Country - Example League",
        ),
        ([_fotmob_match(2103)], "Example League"),
        (
            [
                _fotmob_match(
                    2104,
                    competition_kickoff=dt.datetime(2026, 8, 18, 20, 0, 1, tzinfo=UTC),
                )
            ],
            "Example Country - Example League",
        ),
    ],
)
def test_no_fuzzy_reversal_alias_or_kickoff_tolerance(
    tmp_path: Path,
    matches: list[dict],
    competition: str,
) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(
        tmp_path,
        matches=matches,
        competition=competition,
    )
    result = _build(chain, admission, captures)
    assert result.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert result.exact_match_count == 0
    assert result.matched_fixture is None
    assert result.fixture_reconciliation_authorized is False
    assert all(value is False for value in result.safety.values())


def test_multiple_exact_admitted_rows_are_ambiguous_and_choose_none(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(
        tmp_path,
        matches=[_fotmob_match(2201), _fotmob_match(2202)],
    )
    result = _build(chain, admission, captures)
    assert result.disposition is (
        full.FullUtcReconciliationDisposition.AMBIGUOUS_EXACT_FULL_UTC_MATCH
    )
    assert result.exact_match_count == 2
    assert result.matched_fixture is None
    assert result.fixture_reconciliation_authorized is False
    assert all(value is False for value in result.safety.values())


def test_rejected_fotmob_catalog_cannot_supply_fixture_authority(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(
        tmp_path,
        disposition=ReviewedFixtureCatalogAdmissionDisposition.REJECTED,
    )
    with pytest.raises(
        full.SportyBetFotMobFullUtcReconciliationError,
        match="exact ADMITTED disposition",
    ):
        _build(chain, admission, captures)


def test_provider_subminute_precision_requires_exact_fotmob_instant(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path, start_time="2026-08-18T20:00:37.123000Z")
    admission, captures = _fotmob_admission(
        tmp_path,
        matches=[
            _fotmob_match(
                2401,
                competition_kickoff=dt.datetime(
                    2026, 8, 18, 20, 0, 37, 123000, tzinfo=UTC
                ),
            )
        ],
    )
    exact = _build(chain, admission, captures)
    assert exact.fixture_reconciliation_authorized is True

    other_path = tmp_path / "micro-mismatch"
    other_path.mkdir()
    precise_chain = _source_chain(
        other_path,
        start_time="2026-08-18T20:00:37.123456Z",
    )
    mismatch_admission, mismatch_captures = _fotmob_admission(
        other_path,
        matches=[
            _fotmob_match(
                2402,
                competition_kickoff=dt.datetime(
                    2026, 8, 18, 20, 0, 37, 123000, tzinfo=UTC
                ),
            )
        ],
    )
    no_match = _build(precise_chain, mismatch_admission, mismatch_captures)
    assert no_match.disposition is full.FullUtcReconciliationDisposition.NO_EXACT_FULL_UTC_MATCH
    assert no_match.fixture_reconciliation_authorized is False


def test_forged_pr162_promotion_is_rederived_and_rejected(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(tmp_path)
    forged = dataclasses.replace(
        chain["kickoff_promotion"],
        source_event_raw_sha256="f" * 64,
    )
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
            fotmob_admission_value=admission,
            fotmob_captures=captures,
        )


def test_different_raw_fotmob_capture_cannot_reuse_admission(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, _ = _fotmob_admission(tmp_path)
    different_capture = _fotmob_capture([_fotmob_match(2601, home="Fabricated Home")])
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        _build(chain, admission, (different_capture,))


def test_no_match_cannot_be_manually_promoted_to_fixture_authority(tmp_path: Path) -> None:
    chain = _source_chain(tmp_path)
    admission, captures = _fotmob_admission(
        tmp_path,
        matches=[
            _fotmob_match(
                2701,
                competition_kickoff=dt.datetime(2026, 8, 18, 20, 1, tzinfo=UTC),
            )
        ],
    )
    result = _build(chain, admission, captures)
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        dataclasses.replace(result, fixture_reconciliation_authorized=True)
    forged_safety = dict(result.safety)
    forged_safety["fixture_reconciliation_authorized"] = True
    with pytest.raises(full.SportyBetFotMobFullUtcReconciliationError):
        dataclasses.replace(result, safety=forged_safety)
