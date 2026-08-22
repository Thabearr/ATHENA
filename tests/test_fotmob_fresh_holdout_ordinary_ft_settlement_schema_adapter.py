from __future__ import annotations

import datetime as dt
import json

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_fresh_holdout_capture_qualification_adapter as live_capture_adapter
import domain.fotmob_fresh_holdout_ordinary_ft_settlement_schema_adapter as adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import scripts.run_fotmob_utc_native_xg_fresh_holdout_tick as tick_cli


UTC = dt.timezone.utc
REQUEST_DATE = "20260822"
KICKOFF = "2026-08-22T18:45:00.000Z"
KICKOFF_MS = 1787424300000
FIRST_OBSERVED = dt.datetime(2026, 8, 22, 18, 45, 30, tzinfo=UTC)
SECOND_OBSERVED = dt.datetime(2026, 8, 22, 19, 1, 58, tzinfo=UTC)


def _raw(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest(raw: bytes, observed_at: dt.datetime):
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
        network_acquisition_performed=True,
    )
    return capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=REQUEST_DATE,
        timezone="UTC",
        ccode3="NGA",
    )


def _payload(
    *,
    finished: bool,
    started: bool,
    home_name: str = "Genoa",
    include_live_time: bool = True,
) -> dict:
    status = {
        "utcTime": KICKOFF,
        "halfs": {
            "firstHalfStarted": "22.08.2026 20:46:54",
            "firstExtraHalfStarted": "22.08.2026 22:20:00",
            "secondExtraHalfStarted": "22.08.2026 22:35:00",
        },
        "periodLength": 45,
        "started": started,
        "cancelled": False,
        "finished": finished,
    }
    if started:
        status.update(
            {
                "ongoing": not finished,
                "scoreStr": "0 - 0" if not finished else "2 - 1",
                "numberOfAwayRedCards": 0,
                "numberOfHomeRedCards": 0,
            }
        )
    if include_live_time:
        status["liveTime"] = {
            "short": "16‎’‎" if not finished else "FT",
            "shortKey": "",
            "long": "15:04" if not finished else "90:00",
            "longKey": "",
            "maxTime": 45 if not finished else 90,
            "basePeriod": 45 if not finished else 90,
            "addedTime": 0,
        }
    if finished:
        status.update(
            {
                "awarded": False,
                "reason": {
                    "short": "FT",
                    "shortKey": "fulltime_short",
                    "long": "Full-Time",
                    "longKey": "finished",
                },
            }
        )
        status["halfs"]["secondHalfStarted"] = "22.08.2026 21:48:00"

    return {
        "date": REQUEST_DATE,
        "leagues": [
            {
                "ccode": "ITA",
                "id": 55,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {
                            "id": 9875,
                            "longName": "Napoli",
                            "name": "Napoli",
                            "redCards": 0,
                            "score": 1 if finished else 0,
                        },
                        "eliminatedTeamId": None,
                        "home": {
                            "id": 10233,
                            "longName": home_name,
                            "name": home_name,
                            "redCards": 0,
                            "score": 2 if finished else 0,
                        },
                        "id": 5749644,
                        "leagueId": 55,
                        "status": status,
                        "statusId": 6 if finished else 2,
                        "time": "22.08.2026 18:45",
                        "timeTS": KICKOFF_MS,
                        "tournamentStage": "",
                    }
                ],
                "name": "Serie A",
                "primaryId": 55,
                "simpleLeague": False,
            }
        ],
    }


def _pair(*, finished: bool):
    first_raw = _raw(_payload(finished=finished, started=finished))
    second_raw = _raw(
        _payload(
            finished=finished,
            started=True,
            home_name="Genoa CFC",
        )
    )
    return (
        first_raw,
        _manifest(first_raw, FIRST_OBSERVED),
        second_raw,
        _manifest(second_raw, SECOND_OBSERVED),
    )


def test_receipt_binds_observed_failure_and_grants_no_authority() -> None:
    receipt = adapter.adapter_receipt()
    assert receipt["source_workflow_run_id"] == 32592483626
    assert receipt["source_actions_artifact_id"] == 9480687035
    assert receipt["source_fixture_id"] == 5749644
    assert receipt["reviewed_extra_halfs_keys"] == [
        "firstExtraHalfStarted",
        "secondExtraHalfStarted",
    ]
    assert receipt["compatibility_projection_is_validation_only"] is True
    assert receipt["ordinary_ft_adapter_consumes_original_network_bytes"] is True
    assert receipt["network_acquisition_performed"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_frozen_score_adapter_reproduces_extra_halfs_structural_failure() -> None:
    first_raw, first_manifest, second_raw, second_manifest = _pair(finished=False)
    with pytest.raises(
        score_adapter.FotMobDataMatchesOrdinaryFtFinishedScoreAdapterError
    ) as exc_info:
        score_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(
            first_raw,
            first_manifest,
            second_raw,
            second_manifest,
        )
    assert exc_info.value.status is score_adapter.AdapterPairStatus.BLOCKED_STRUCTURAL_REVALIDATION


def test_live_pair_reaches_normal_no_finished_score_disposition_with_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_raw, first_manifest, second_raw, second_manifest = _pair(finished=False)
    monkeypatch.setattr(
        score_adapter,
        "pr89",
        adapter.build_pr89_settlement_compatibility_proxy(),
    )
    result = score_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.pair_status is score_adapter.AdapterPairStatus.NO_QUALIFIED_ORDINARY_FT_SCORES
    assert result.qualified_count == 0
    assert result.terminal_candidate_union_count == 0
    assert result.first_raw_sha256 == first_manifest.raw_sha256
    assert result.second_raw_sha256 == second_manifest.raw_sha256


def test_finished_pair_keeps_frozen_score_semantics_and_original_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_raw, first_manifest, second_raw, second_manifest = _pair(finished=True)
    monkeypatch.setattr(
        score_adapter,
        "pr89",
        adapter.build_pr89_settlement_compatibility_proxy(),
    )
    result = score_adapter.adapt_fotmob_data_matches_ordinary_ft_finished_scores(
        first_raw,
        first_manifest,
        second_raw,
        second_manifest,
    )
    assert result.pair_status is score_adapter.AdapterPairStatus.QUALIFIED_WITH_ORDINARY_FT_SCORES
    assert result.qualified_count == 1
    score = result.qualified_scores[0]
    assert (score.fixture_id, score.home_score, score.away_score) == (5749644, 2, 1)
    assert score.first_raw_sha256 == first_manifest.raw_sha256
    assert score.second_raw_sha256 == second_manifest.raw_sha256
    assert score.first_manifest_sha256 == capture_contract.sha256_data_matches_capture_manifest(first_manifest)
    assert score.second_manifest_sha256 == capture_contract.sha256_data_matches_capture_manifest(second_manifest)


def test_unreviewed_or_non_string_extra_halfs_still_fail_closed() -> None:
    payload = _payload(finished=False, started=False)
    payload["leagues"][0]["matches"][0]["status"]["halfs"][
        "thirdExtraHalfStarted"
    ] = "22.08.2026 22:50:00"
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutOrdinaryFtSettlementSchemaAdapterError,
        match="reviewed fresh-capture compatibility qualification failed",
    ):
        adapter.assess_eliminated_team_id_value_domain_for_settlement(
            raw,
            _manifest(raw, FIRST_OBSERVED),
        )

    payload = _payload(finished=False, started=False)
    payload["leagues"][0]["matches"][0]["status"]["halfs"][
        "firstExtraHalfStarted"
    ] = None
    raw = _raw(payload)
    with pytest.raises(
        adapter.FreshHoldoutOrdinaryFtSettlementSchemaAdapterError,
        match="reviewed fresh-capture compatibility qualification failed",
    ):
        adapter.assess_eliminated_team_id_value_domain_for_settlement(
            raw,
            _manifest(raw, FIRST_OBSERVED),
        )


def test_dependency_pin_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "ORDINARY_FT_ADAPTER_BLOB_SHA", "0" * 40)
    with pytest.raises(
        adapter.FreshHoldoutOrdinaryFtSettlementSchemaAdapterError,
        match="frozen ordinary-FT adapter implementation blob changed",
    ):
        adapter.verify_reviewed_dependencies()


def test_cli_scopes_both_adapters_and_restores_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_qualifier = fresh.qualify_capture_fixtures
    original_score_pr89 = score_adapter.pr89
    seen = {}

    def fake_execute(**kwargs):
        seen["qualifier"] = fresh.qualify_capture_fixtures
        seen["score_pr89"] = score_adapter.pr89
        seen["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(tick_cli.runner, "execute_collection_tick", fake_execute)
    result = tick_cli._execute_collection_tick_with_reviewed_adapter(probe="value")
    assert result == {"ok": True}
    assert seen["qualifier"] is live_capture_adapter.qualify_capture_fixtures
    assert isinstance(
        seen["score_pr89"], adapter.ReviewedPr89SettlementCompatibilityProxy
    )
    assert seen["kwargs"] == {"probe": "value"}
    assert fresh.qualify_capture_fixtures is original_qualifier
    assert score_adapter.pr89 is original_score_pr89


def test_cli_restores_both_adapters_when_tick_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_qualifier = fresh.qualify_capture_fixtures
    original_score_pr89 = score_adapter.pr89

    def fail_execute(**_kwargs):
        assert fresh.qualify_capture_fixtures is live_capture_adapter.qualify_capture_fixtures
        assert isinstance(
            score_adapter.pr89, adapter.ReviewedPr89SettlementCompatibilityProxy
        )
        raise RuntimeError("synthetic tick failure")

    monkeypatch.setattr(tick_cli.runner, "execute_collection_tick", fail_execute)
    with pytest.raises(RuntimeError, match="synthetic tick failure"):
        tick_cli._execute_collection_tick_with_reviewed_adapter()
    assert fresh.qualify_capture_fixtures is original_qualifier
    assert score_adapter.pr89 is original_score_pr89
