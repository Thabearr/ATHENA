from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain.current_fotmob_utc_native_shadow_prediction import (
    MISSING_REVIEWED_FEATURES,
    NEXT_REQUIRED_BOUNDARY,
    OUTSIDE_REVIEWED_SEAL_WINDOW,
    SEALED_COMPLETE_CASE,
    STATUS_REPLAYED,
    CurrentUtcNativeShadowPredictionError,
    build_current_fotmob_utc_native_shadow_prediction_handoff,
    canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes,
)
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from scripts.capture_fotmob_data_matches import write_data_matches_capture_directory
from scripts.issue_current_fotmob_reviewed_source import (
    build_verified_current_fotmob_bootstrap_from_capture,
)

UTC = dt.timezone.utc
OBSERVED = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
ISSUED = dt.datetime(2026, 8, 27, 7, 5, tzinfo=UTC)
KICKOFF = dt.datetime(2026, 8, 27, 15, 0, tzinfo=UTC)


def _epoch_ms(value: dt.datetime) -> int:
    epoch = dt.datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _raw(*, fixture_id: int = 1001, kickoff: dt.datetime = KICKOFF) -> bytes:
    kickoff_text = kickoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    payload = {
        "leagues": [
            {
                "ccode": "ENG",
                "id": 47,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 202,
                            "score": 0,
                            "name": "Away FC",
                            "longName": "Away FC",
                        },
                        "eliminatedTeamId": None,
                        "home": {
                            "id": 101,
                            "score": 0,
                            "name": "Home FC",
                            "longName": "Home FC",
                        },
                        "id": fixture_id,
                        "leagueId": 47,
                        "status": {
                            "utcTime": kickoff_text,
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
                ],
                "name": "Premier League",
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
        "date": kickoff.strftime("%Y%m%d"),
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _current(
    tmp_path: Path,
    *,
    observed: dt.datetime = OBSERVED,
    issued: dt.datetime = ISSUED,
    fixture_id: int = 1001,
    kickoff: dt.datetime = KICKOFF,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = _raw(fixture_id=fixture_id, kickoff=kickoff)
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=observed,
        network_acquisition_performed=True,
    )
    directory, manifest = write_data_matches_capture_directory(
        response,
        request_date=kickoff.strftime("%Y%m%d"),
        timezone="UTC",
        ccode3="NGA",
        repository_root=tmp_path,
    )
    execution = build_verified_current_fotmob_bootstrap_from_capture(
        directory,
        issued_at=issued,
        repository_root=tmp_path,
        code_state={
            "evidence_git_head_sha": "a" * 40,
            "tracked_worktree_clean": True,
        },
    )
    return execution, raw, manifest


def _bootstrap_row(
    fixture_id: int,
    home: int,
    away: int,
    kickoff: dt.datetime,
    observed: dt.datetime,
    home_goals: int,
    away_goals: int,
) -> dict[str, object]:
    return {
        "source_namespace": fresh.SOURCE_NAMESPACE,
        "fixture_identifier": str(fixture_id),
        "source_local_kickoff": kickoff.replace(tzinfo=None).isoformat(),
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "home_team_identifier": str(home),
        "away_team_identifier": str(away),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "evidence_sha256": hashlib.sha256(
            f"bootstrap:{fixture_id}".encode()
        ).hexdigest(),
        "evidence_reference": f"synthetic-reviewed-bootstrap:{fixture_id}",
    }


def _history(monkeypatch: pytest.MonkeyPatch, *, include_away: bool = True) -> bytes:
    rows = [
        _bootstrap_row(
            6001,
            101,
            303,
            dt.datetime(2026, 8, 25, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 25, 20, 0, tzinfo=UTC),
            2,
            0,
        )
    ]
    if include_away:
        rows.append(
            _bootstrap_row(
                6002,
                202,
                404,
                dt.datetime(2026, 8, 25, 19, 0, tzinfo=UTC),
                dt.datetime(2026, 8, 25, 21, 0, tzinfo=UTC),
                1,
                1,
            )
        )
    raw = b"".join(fresh._canonical(row) for row in rows)
    monkeypatch.setattr(
        fresh,
        "BOOTSTRAP_PROJECTION_SHA256",
        hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_SIZE", len(raw))
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_ROWS", len(rows))
    return raw


def _handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_away: bool = True,
):
    execution, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch, include_away=include_away)
    handoff = build_current_fotmob_utc_native_shadow_prediction_handoff(
        current_bootstrap=execution.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=history,
    )
    return handoff, execution, raw, manifest, history


def test_supplied_reviewed_inputs_reach_exact_utc_native_shadow_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)

    assert handoff.status == STATUS_REPLAYED
    assert handoff.fixture_count == 1
    assert handoff.sealed_complete_case_count == 1
    assert handoff.missing_feature_count == 0
    assert handoff.outside_seal_window_count == 0
    row = handoff.rows[0]
    assert row.fixture_identifier == "FOTMOB:1001"
    assert row.disposition == SEALED_COMPLETE_CASE
    assert row.sealed_prediction is not None
    assert row.fixture == row.sealed_prediction.fixture
    assert row.fixture.fixture_id == 1001
    assert row.fixture.provider_primary_id == 47
    assert row.fixture.wrapper_id == 47
    assert row.fixture.home_team_id == 101
    assert row.fixture.away_team_id == 202
    assert row.sealed_prediction_sha256 == fresh.sha256_sealed_fresh_prediction(
        row.sealed_prediction
    )
    assert handoff.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert NEXT_REQUIRED_BOUNDARY == "CURRENT_DURABLE_FRESH_HISTORY_PREFIX_BINDING_REQUIRED"

    assert handoff.current_fresh_history_prefix_complete is False
    assert handoff.research_evidence == {
        "reviewed_current_fixture_identity": True,
        "supplied_reviewed_history_inputs_replayed": True,
        "utc_native_research_feature_construction": True,
        "shadow_expected_goals_rates": True,
        "complete_current_fresh_history_prefix": False,
    }
    assert handoff.authority == {
        "production_model": False,
        "score_matrix": False,
        "probability": False,
        "phase6": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
    }
    payload = handoff.to_dict()
    assert payload["current_fresh_history_prefix_complete"] is False
    assert payload["wager_placed"] is False
    assert not any(handoff.authority.values())


def test_empty_fresh_settlement_tuple_never_claims_current_history_completeness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    assert handoff.reviewed_fresh_settlement_count == 0
    assert handoff.current_fresh_history_prefix_complete is False
    assert handoff.research_evidence["complete_current_fresh_history_prefix"] is False
    assert handoff.next_required_boundary == NEXT_REQUIRED_BOUNDARY


def test_missing_utc_native_history_remains_explicit_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch, include_away=False)
    row = handoff.rows[0]
    assert row.disposition == MISSING_REVIEWED_FEATURES
    assert "away_form" in row.missing_feature_ids
    assert row.sealed_prediction is None
    assert handoff.missing_feature_count == 1
    assert handoff.current_fresh_history_prefix_complete is False


def test_pr243_capture_outside_24h_seal_window_is_not_retrofilled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = dt.datetime(2026, 8, 26, 7, 0, tzinfo=UTC)
    issued = observed + dt.timedelta(minutes=5)
    execution, raw, manifest = _current(tmp_path, observed=observed, issued=issued)
    history = _history(monkeypatch)
    handoff = build_current_fotmob_utc_native_shadow_prediction_handoff(
        current_bootstrap=execution.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=history,
    )
    row = handoff.rows[0]
    assert row.disposition == OUTSIDE_REVIEWED_SEAL_WINDOW
    assert row.sealed_prediction is None
    assert row.missing_feature_ids == ()
    assert handoff.outside_seal_window_count == 1


def test_source_raw_tampering_fails_before_shadow_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    with pytest.raises(CurrentUtcNativeShadowPredictionError, match="raw SHA"):
        build_current_fotmob_utc_native_shadow_prediction_handoff(
            current_bootstrap=execution.bootstrap,
            source_raw_json=raw + b" ",
            source_manifest=manifest,
            legacy_bootstrap_projection_raw=history,
        )


def test_source_bundle_raw_replacement_cannot_create_relabelled_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, _execution, raw, _manifest, _history_bytes = _handoff(
        tmp_path,
        monkeypatch,
    )
    with pytest.raises(CurrentUtcNativeShadowPredictionError, match="raw SHA"):
        dataclasses.replace(handoff.source_bundle, source_raw_json=raw + b" ")


def test_bootstrap_cannot_be_bound_to_different_current_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, raw, manifest = _current(tmp_path / "one", fixture_id=1001)
    second, _raw2, _manifest2 = _current(tmp_path / "two", fixture_id=1002)
    history = _history(monkeypatch)
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="candidate bundle differs",
    ):
        build_current_fotmob_utc_native_shadow_prediction_handoff(
            current_bootstrap=second.bootstrap,
            source_raw_json=raw,
            source_manifest=manifest,
            legacy_bootstrap_projection_raw=history,
        )
    assert first.bootstrap != second.bootstrap


def test_exact_pr119_bootstrap_bytes_are_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    with pytest.raises(CurrentUtcNativeShadowPredictionError, match="PR119 bootstrap"):
        build_current_fotmob_utc_native_shadow_prediction_handoff(
            current_bootstrap=execution.bootstrap,
            source_raw_json=raw,
            source_manifest=manifest,
            legacy_bootstrap_projection_raw=history + b"{}\n",
        )


def test_detached_candidate_sha_cannot_be_relabelled_after_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    replacement = "f" * 64
    assert replacement != handoff.candidate_bundle_sha256
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="candidate_bundle_sha256 differs",
    ):
        dataclasses.replace(handoff, candidate_bundle_sha256=replacement)


def test_detached_review_sha_cannot_be_relabelled_after_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    replacement = "e" * 64
    assert replacement != handoff.review_bundle_sha256
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="review_bundle_sha256 differs",
    ):
        dataclasses.replace(handoff, review_bundle_sha256=replacement)


def test_detached_history_update_count_cannot_be_relabelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    assert handoff.reviewed_fresh_legacy_update_count == 0
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="fresh legacy update count differs",
    ):
        dataclasses.replace(handoff, reviewed_fresh_legacy_update_count=1)


def test_detached_row_cannot_be_relabelled_after_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    original = handoff.rows[0]
    tampered = dataclasses.replace(
        original,
        disposition=MISSING_REVIEWED_FEATURES,
        missing_feature_ids=("away_form",),
        sealed_prediction=None,
        sealed_prediction_sha256=None,
    )
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="shadow rows differ",
    ):
        dataclasses.replace(handoff, rows=(tampered,))


def test_current_history_completeness_claim_cannot_be_switched_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    changed = dict(handoff.research_evidence)
    changed["complete_current_fresh_history_prefix"] = True
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="research_evidence.*changed reviewed state",
    ):
        dataclasses.replace(handoff, research_evidence=changed)


def test_research_evidence_cannot_be_downgraded_or_relabelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    changed = dict(handoff.research_evidence)
    changed["shadow_expected_goals_rates"] = False
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="research_evidence.*changed reviewed state",
    ):
        dataclasses.replace(handoff, research_evidence=changed)


@pytest.mark.parametrize("key", ["phase6", "selection", "sportybet_execution", "bet"])
def test_downstream_authority_cannot_be_switched_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    changed = dict(handoff.authority)
    changed[key] = True
    with pytest.raises(
        CurrentUtcNativeShadowPredictionError,
        match="authority.*changed reviewed state",
    ):
        dataclasses.replace(handoff, authority=changed)


def test_shadow_handoff_is_canonical_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    first = build_current_fotmob_utc_native_shadow_prediction_handoff(
        current_bootstrap=execution.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=history,
    )
    second = build_current_fotmob_utc_native_shadow_prediction_handoff(
        current_bootstrap=execution.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=history,
    )
    first_bytes = canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes(
        first
    )
    second_bytes = canonical_current_fotmob_utc_native_shadow_prediction_handoff_bytes(
        second
    )
    assert first_bytes == second_bytes
    assert b"Home FC" not in first_bytes
    assert b"synthetic-reviewed-bootstrap" not in first_bytes
    assert history not in first_bytes
    decoded = json.loads(first_bytes)
    assert decoded["current_fresh_history_prefix_complete"] is False
    assert decoded["next_required_boundary"] == NEXT_REQUIRED_BOUNDARY


def test_bridge_source_contains_no_provider_scalar_or_phase6_shortcut() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = (
        repository / "domain/current_fotmob_utc_native_shadow_prediction.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "fixture_extended",
        "current_home_form",
        "current_away_form",
        "fotmob_reviewed_match_details_model_feature_handoff",
        "CalibratedValueCandidate",
        "sportybet_semantic_share_bridge",
    ):
        assert forbidden not in source
