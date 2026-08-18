from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as pr148
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control


UTC = dt.timezone.utc


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    state = repo / control.CONTROL_ROOT_RELATIVE
    state.mkdir(parents=True, exist_ok=True)
    return repo, state


def _capture(
    tmp_path: Path,
    request_date: str,
    observed_at: dt.datetime,
) -> runner.CaptureEvidence:
    raw = json.dumps(
        {"leagues": [], "request_test_date": request_date},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    response = capture_contract.CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json",
        content_length=len(raw),
        body=raw,
        observed_at=observed_at,
        network_acquisition_performed=True,
    )
    manifest = capture_contract.build_data_matches_capture_manifest(
        response,
        request_date=request_date,
        timezone=control.REQUEST_TIMEZONE,
        ccode3=control.REQUEST_CCODE3,
    )
    directory = tmp_path / f"capture-{request_date}-{observed_at.hour}-{observed_at.minute}-{observed_at.second}"
    directory.mkdir(parents=True, exist_ok=True)
    return runner.CaptureEvidence(directory, raw, manifest)


def _fake_sealed_prediction(
    fixture_id: int,
    kickoff_utc: dt.datetime,
    observed_at: dt.datetime,
    provider_primary_id: int = 99999,
) -> fresh.SealedFreshPrediction:
    fixture = fresh.QualifiedCaptureFixture(
        fixture_id=fixture_id,
        provider_primary_id=provider_primary_id,
        wrapper_id=1000 + fixture_id,
        home_team_id=1,
        away_team_id=2,
        kickoff_utc=kickoff_utc,
        capture_observed_at=observed_at,
        capture_manifest_sha256="a" * 64,
        capture_raw_sha256="b" * 64,
    )
    features = {
        "home_elo": 1500.0,
        "away_elo": 1500.0,
        "home_form": 0.5,
        "away_form": 0.5,
        "fatigue": 0.0,
    }
    rates = fresh._rates_from_features(features)
    return fresh.SealedFreshPrediction(
        schema_version=1,
        implementation_state=fresh.IMPLEMENTATION_STATE,
        protocol_sha256=pr148.PROTOCOL_SHA256,
        holdout_start_utc=control.holdout_start_utc(),
        fixture=fixture,
        bootstrap_projection_sha256=fresh.BOOTSTRAP_PROJECTION_SHA256,
        history_prefix_sha256="c" * 64,
        history_prefix_count=100,
        feature_projection_sha256="d" * 64,
        features=features,
        rates=rates,
        safety={key: False for key in fresh.SAFETY_KEYS},
    )


# --- GENERAL RECEIPT & STATE ROOT TESTS ---


def test_activation_receipt_pins_merged_control_and_grants_no_downstream_authority() -> None:
    receipt = runner.activation_runner_receipt()
    assert receipt["reviewed_control"] == {
        "pr150_merge_sha": "50684a85cd528d491be812ed77d2c744855aba84",
        "pr150_merge_utc": "2026-08-18T04:55:12Z",
        "control_blob_sha": "60865e35a92e28bb0d4360223dea42b8933bb706",
    }
    assert receipt["runtime"]["network_requires_explicit_execute_flag"] is True
    assert receipt["runtime"]["settlement_precedes_prediction_construction_within_tick"] is True
    assert receipt["runtime"]["actual_capture_observed_at_authoritative"] is True
    assert receipt["runtime"]["nominal_schedule_time_is_observation_time"] is False
    assert receipt["runtime"]["scheduler_gap_backfill_authorized"] is False
    assert receipt["runtime"]["duplicate_committed_tick_network_replay_authorized"] is False
    assert all(value is False for value in receipt["safety"].values())


def test_state_root_is_exact_and_rejects_traversal(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    assert runner.validate_state_root(
        Path(control.CONTROL_ROOT_RELATIVE), repository_root=repo
    ) == state
    with pytest.raises(runner.FreshHoldoutActivationError, match="exact reviewed"):
        runner.validate_state_root(Path(".cache/elsewhere"), repository_root=repo)
    with pytest.raises(runner.FreshHoldoutActivationError, match="traversal"):
        runner.validate_state_root(Path("../outside"), repository_root=repo)


def test_prestart_tick_commits_without_network_and_duplicate_does_not_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    calls: list[str] = []

    def forbidden_capture(request_date: str, *, repository_root: Path):
        calls.append(request_date)
        raise AssertionError("network must not be called pre-start")

    scheduled = dt.datetime(2026, 8, 18, 23, 37, tzinfo=UTC)
    receipt = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"synthetic-test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260818T233700Z-run-1.tar.gz",
        execute_live_network=False,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=forbidden_capture,
        clock=lambda: scheduled + dt.timedelta(minutes=1),
    )
    assert receipt["phase"] == control.ControlPhase.PRE_START.value
    assert receipt["network_request_count"] == 0
    assert calls == []

    duplicate = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"synthetic-test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260818T233700Z-run-2.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=forbidden_capture,
        clock=lambda: scheduled + dt.timedelta(minutes=2),
    )
    assert duplicate["disposition"] == "ALREADY_COMMITTED_NO_NETWORK_REPLAY"
    assert duplicate["network_acquisition_performed"] is False
    assert calls == []


def test_active_tick_requires_explicit_live_network_authorization(
    tmp_path: Path,
) -> None:
    repo, _state = _repo(tmp_path)
    with pytest.raises(
        runner.FreshHoldoutActivationError,
        match="explicit live-network authorization",
    ):
        runner.execute_collection_tick(
            scheduled_for=dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC),
            bootstrap_projection_raw=b"x",
            durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
            durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
            execute_live_network=False,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
        )


def test_active_tick_requests_three_provider_dates_and_journals_actual_observed_at(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())

    scheduled = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)
    calls: list[str] = []

    def capture_one(request_date: str, *, repository_root: Path):
        assert repository_root == repo
        calls.append(request_date)
        offset = {"20260818": 1, "20260819": 2, "20260820": 3}[request_date]
        return _capture(
            tmp_path,
            request_date,
            scheduled + dt.timedelta(minutes=offset),
        )

    receipt = runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T000700Z-run-42.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: scheduled + dt.timedelta(minutes=4),
    )
    assert calls == ["20260818", "20260819", "20260820"]
    assert receipt["network_request_count"] == 3
    assert receipt["network_acquisition_performed"] is True
    rows = [
        json.loads(line)
        for line in (state / control.CAPTURE_INDEX_FILENAME).read_text().splitlines()
    ]
    assert [row["request_date"] for row in rows] == calls
    assert [row["observed_at"] for row in rows] == [
        "2026-08-19T00:08:00.000000Z",
        "2026-08-19T00:09:00.000000Z",
        "2026-08-19T00:10:00.000000Z",
    ]


def test_live_capture_cannot_backdate_nominal_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    scheduled = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)

    def capture_one(request_date: str, *, repository_root: Path):
        return _capture(
            tmp_path,
            request_date,
            scheduled - dt.timedelta(seconds=1),
        )

    with pytest.raises(runner.FreshHoldoutActivationError, match="predates nominal"):
        runner.execute_collection_tick(
            scheduled_for=scheduled,
            bootstrap_projection_raw=b"x",
            durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
            durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
            execute_live_network=True,
            state_root=Path(control.CONTROL_ROOT_RELATIVE),
            repository_root=repo,
            capture_one=capture_one,
        )


def test_scheduler_gap_is_journaled_and_not_backfilled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    counter = 0
    current_tick = [dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)]

    def capture_one(request_date: str, *, repository_root: Path):
        nonlocal counter
        counter += 1
        return _capture(
            tmp_path,
            request_date,
            current_tick[0] + dt.timedelta(minutes=((counter - 1) % 3) + 1),
        )

    first = current_tick[0]
    runner.execute_collection_tick(
        scheduled_for=first,
        bootstrap_projection_raw=b"x",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: first + dt.timedelta(minutes=5),
    )
    second = dt.datetime(2026, 8, 19, 1, 7, tzinfo=UTC)
    current_tick[0] = second
    runner.execute_collection_tick(
        scheduled_for=second,
        bootstrap_projection_raw=b"x",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T010700Z-run-2.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=capture_one,
        clock=lambda: second + dt.timedelta(minutes=5),
    )
    control_rows = [
        json.loads(line)
        for line in (state / control.CONTROL_JOURNAL_FILENAME).read_text().splitlines()
    ]
    gaps = [row for row in control_rows if row["event"] == "SCHEDULER_GAP_RANGE"]
    assert len(gaps) == 1
    assert gaps[0]["first_missing_tick_utc"] == "2026-08-19T00:37:00.000000Z"
    assert gaps[0]["last_missing_tick_utc"] == "2026-08-19T00:37:00.000000Z"
    assert gaps[0]["missing_tick_count"] == 1
    assert gaps[0]["backfill_authorized"] is False


# --- BLOCKER A: SETTLEMENT ENUM VOCABULARY & EXECUTION TESTS ---


def test_settlement_disposition_exact_enum_and_branch_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    scheduled = dt.datetime(2026, 8, 19, 4, 7, tzinfo=UTC)
    pred_observed = dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)
    kickoff = dt.datetime(2026, 8, 19, 2, 7, tzinfo=UTC)

    # Pre-populate 3 sealed predictions in the journal
    pred1 = _fake_sealed_prediction(101, kickoff, pred_observed)
    pred2 = _fake_sealed_prediction(102, kickoff, pred_observed)
    pred3 = _fake_sealed_prediction(103, kickoff, pred_observed)

    pred_rows = [
        runner._prediction_row(
            fresh.FreshPredictionAssessment(
                disposition=fresh.PredictionDisposition.SEALED_COMPLETE_CASE,
                fixture=p.fixture,
                missing_feature_ids=(),
                sealed_prediction=p,
            ),
            "tag",
            "asset",
        )
        for p in (pred1, pred2, pred3)
    ]
    for row in pred_rows:
        runner._append(state / control.PREDICTION_JOURNAL_FILENAME, row)

    fake_cap = _capture(tmp_path, "20260819", scheduled + dt.timedelta(minutes=1))
    monkeypatch.setattr(runner, "_pair", lambda _pred, _caps, _qual: (fake_cap, fake_cap))

    # Mock settle_sealed_prediction to return 3 distinct PR149 SettlementDisposition members
    def mock_settle(prediction, **kwargs):
        fid = prediction.fixture.fixture_id
        if fid == 101:
            settled = fresh.SettledFreshPrediction(
                prediction=prediction,
                home_goals=2,
                away_goals=1,
                settlement_observed_at=scheduled + dt.timedelta(minutes=2),
                settlement_evidence_sha256="e" * 64,
                ordinary_ft_first_raw_sha256="f" * 64,
                ordinary_ft_second_raw_sha256="1" * 64,
                ordinary_ft_first_manifest_sha256="2" * 64,
                ordinary_ft_second_manifest_sha256="3" * 64,
                legacy_history_state_update=None,
            )
            return fresh.FreshSettlementAssessment(
                disposition=fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT,
                prediction=prediction,
                detail="settled ordinary FT",
                settled_prediction=settled,
            )
        elif fid == 102:
            return fresh.FreshSettlementAssessment(
                disposition=fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT,
                prediction=prediction,
                detail="kickoff drift observed",
                settled_prediction=None,
            )
        elif fid == 103:
            return fresh.FreshSettlementAssessment(
                disposition=fresh.SettlementDisposition.EXCLUDED_NOT_REVIEWED_ORDINARY_FT,
                prediction=prediction,
                detail="not reviewed ordinary FT",
                settled_prediction=None,
            )
        raise AssertionError(f"unexpected fixture {fid}")

    monkeypatch.setattr(fresh, "settle_sealed_prediction", mock_settle)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())

    runner.execute_collection_tick(
        scheduled_for=scheduled,
        bootstrap_projection_raw=b"test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W34",
        durable_asset_name="success-20260819T000700Z-run-1.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=lambda req_date, **kw: _capture(tmp_path, req_date, scheduled + dt.timedelta(minutes=1)),
    )

    settlement_rows = runner._rows(state / control.SETTLEMENT_JOURNAL_FILENAME)
    assert len(settlement_rows) == 2

    # Verify settlement parser re-evaluates exact vocabulary cleanly
    settled_map, terminal = runner._settlement_state(settlement_rows)
    assert 101 in settled_map
    assert 101 in terminal
    assert 102 in terminal
    assert 103 not in terminal


# --- BLOCKER B: SELECTED-CLOSE POPULATION & SETTLEMENT SEMANTICS TESTS ---


def test_selected_close_population_and_settlement_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, state = _repo(tmp_path)
    selected_close_boundary = dt.datetime(2026, 9, 16, 0, 0, tzinfo=UTC)
    tick_at_close = dt.datetime(2026, 9, 16, 0, 7, tzinfo=UTC)

    # 1. Prediction 1: kickoff 1 second before close (valid population member)
    # 2. Prediction 2: kickoff exactly at close (outside population)
    # 3. Prediction 3: kickoff 1 second after close (outside population)
    p_before = _fake_sealed_prediction(201, selected_close_boundary - dt.timedelta(seconds=1), selected_close_boundary - dt.timedelta(hours=2))
    p_exact = _fake_sealed_prediction(202, selected_close_boundary, selected_close_boundary - dt.timedelta(hours=2))
    p_after = _fake_sealed_prediction(203, selected_close_boundary + dt.timedelta(seconds=1), selected_close_boundary - dt.timedelta(hours=2))

    for p in (p_before, p_exact, p_after):
        row = runner._prediction_row(
            fresh.FreshPredictionAssessment(
                disposition=fresh.PredictionDisposition.SEALED_COMPLETE_CASE,
                fixture=p.fixture,
                missing_feature_ids=(),
                sealed_prediction=p,
            ),
            "tag",
            "asset",
        )
        runner._append(state / control.PREDICTION_JOURNAL_FILENAME, row)

    # Mock close state to simulate selected close reached at selected_close_boundary
    fake_close_state = control.CloseControlState(
        evaluated_boundary_utc=selected_close_boundary,
        decision=fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value,
        selected_close_utc=selected_close_boundary,
        coverage_sha256="0" * 64,
        _token=control._CLOSE_STATE_TOKEN,
    )
    monkeypatch.setattr(runner, "_close_state", lambda *_args, **_kwargs: fake_close_state)
    monkeypatch.setattr(runner, "_ledger", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runner, "_qualify", lambda _evidence: ())
    monkeypatch.setattr(runner, "_pair", lambda _pred, _caps, _qual: None)

    # Run tick exactly at tick_at_close
    runner.execute_collection_tick(
        scheduled_for=tick_at_close,
        bootstrap_projection_raw=b"test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W37",
        durable_asset_name="success-20260916T000700Z-run-1.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=lambda req_date, **kw: _capture(tmp_path, req_date, tick_at_close + dt.timedelta(minutes=1)),
    )

    rows = runner._rows(state / control.SETTLEMENT_JOURNAL_FILENAME)
    # At selected close: p_exact (202) and p_after (203) MUST be excluded immediately
    assert len(rows) == 2
    fids = {r["fixture_id"] for r in rows}
    assert fids == {202, 203}
    for r in rows:
        assert r["disposition"] == "EXCLUDED_OUTSIDE_SELECTED_CLOSE"

    # p_before (201) MUST NOT be marked EXCLUDED_OUTSIDE_SELECTED_CLOSE!
    assert 201 not in fids

    # Next: run tick at tick_at_close + 24h (tail end) without settlement
    tail_end = tick_at_close + dt.timedelta(hours=24)
    fake_close_state_tail = control.CloseControlState(
        evaluated_boundary_utc=selected_close_boundary,
        decision=fresh.HoldoutBoundaryDecision.CLOSE_COUNT_ONLY_COVERAGE_QUALIFIED.value,
        selected_close_utc=selected_close_boundary,
        coverage_sha256="0" * 64,
        _token=control._CLOSE_STATE_TOKEN,
    )
    monkeypatch.setattr(runner, "_close_state", lambda *_args, **_kwargs: fake_close_state_tail)

    runner.execute_collection_tick(
        scheduled_for=tail_end,
        bootstrap_projection_raw=b"test-bootstrap",
        durable_release_tag="athena-fresh-holdout-evidence-2026-W37",
        durable_asset_name="success-20260917T000700Z-run-2.tar.gz",
        execute_live_network=True,
        state_root=Path(control.CONTROL_ROOT_RELATIVE),
        repository_root=repo,
        capture_one=lambda req_date, **kw: _capture(tmp_path, req_date, tail_end + dt.timedelta(minutes=1)),
    )

    all_rows = runner._rows(state / control.SETTLEMENT_JOURNAL_FILENAME)
    assert len(all_rows) == 3
    p201_rows = [r for r in all_rows if r["fixture_id"] == 201]
    assert len(p201_rows) == 1
    assert p201_rows[0]["disposition"] == "UNRESOLVED_AT_SETTLEMENT_TAIL"


# --- BLOCKER C: AUTHORITATIVE PREDECESSOR RESTORE TESTS ---


def _make_success_zip(state_root: Path, run_id: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            for item in sorted(state_root.rglob("*")):
                if item.is_file():
                    arcname = str(item.relative_to(state_root.parent.parent.parent)).replace("\\", "/")
                    tar.add(item, arcname=arcname)
        tar_bytes = tar_buf.getvalue()
        tar_sha = hashlib.sha256(tar_bytes).hexdigest()
        tar_name = f"success-20260819T000700Z-run-{run_id}.tar.gz"
        zf.writestr(tar_name, tar_bytes)
        receipt = {
            "schema_version": 1,
            "runner_id": runner.RUNNER_ID,
            "durable_asset_name": tar_name,
            "durable_asset_sha256": tar_sha,
            "durable_asset_size_bytes": len(tar_bytes),
        }
        zf.writestr("fresh-holdout-tick-receipt.json", json.dumps(receipt))
    return buf.getvalue()


def test_restore_predecessor_durable_state_valid_newest(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    runner._checkpoint(
        state / control.CHECKPOINT_FILENAME,
        {
            "schema_version": 1,
            "runner_id": runner.RUNNER_ID,
            "last_committed_scheduled_for_utc": "2026-08-19T00:07:00.000000Z",
            "phase": "PREDICTION_AND_SETTLEMENT_COLLECTION",
            "capture_count": 3,
            "prediction_count": 5,
            "settled_or_terminal_count": 0,
            "control_event_count": 1,
            "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
            "durable_asset_name": "success-20260819T000700Z-run-10.tar.gz",
        },
    )
    zip_bytes = _make_success_zip(state, 10)
    zip_sha = hashlib.sha256(zip_bytes).hexdigest()

    prior_runs = [{"id": 10, "conclusion": "success"}]
    art_meta = {
        "artifacts": [
            {
                "id": 1001,
                "name": "success-20260819T000700Z-run-10.tar.gz",
                "digest": f"sha256:{zip_sha}",
                "expired": False,
            }
        ]
    }

    dest_repo, _dest_state = _repo(tmp_path / "dest")
    last_committed = runner.restore_predecessor_durable_state(
        prior_runs=prior_runs,
        current_run_id=11,
        get_run_artifacts=lambda _rid: art_meta,
        download_artifact_zip=lambda _aid: zip_bytes,
        repository_root=dest_repo,
    )
    assert last_committed == dt.datetime(2026, 8, 19, 0, 7, tzinfo=UTC)


def test_restore_predecessor_durable_state_missing_artifact_fails_closed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    prior_runs = [{"id": 20, "conclusion": "success"}]
    art_meta = {"artifacts": []}

    with pytest.raises(runner.FreshHoldoutActivationError, match="must have exactly one success artifact"):
        runner.restore_predecessor_durable_state(
            prior_runs=prior_runs,
            current_run_id=21,
            get_run_artifacts=lambda _rid: art_meta,
            download_artifact_zip=lambda _aid: b"",
            repository_root=repo,
        )


def test_restore_predecessor_corrupt_newest_fails_closed_even_if_older_valid(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    prior_runs = [
        {"id": 30, "conclusion": "success"},
        {"id": 20, "conclusion": "success"},
    ]

    def mock_get_artifacts(run_id: int):
        if run_id == 30:
            return {"artifacts": []}
        raise AssertionError("Must NOT query older runs when newest fails!")

    with pytest.raises(runner.FreshHoldoutActivationError, match="must have exactly one success artifact, found 0"):
        runner.restore_predecessor_durable_state(
            prior_runs=prior_runs,
            current_run_id=31,
            get_run_artifacts=mock_get_artifacts,
            download_artifact_zip=lambda _aid: b"",
            repository_root=repo,
        )


def test_restore_predecessor_zip_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    prior_runs = [{"id": 40, "conclusion": "success"}]
    art_meta = {
        "artifacts": [
            {
                "id": 4001,
                "name": "success-test.tar.gz",
                "digest": "sha256:" + "0" * 64,
                "expired": False,
            }
        ]
    }

    with pytest.raises(runner.FreshHoldoutActivationError, match="artifact zip digest mismatch"):
        runner.restore_predecessor_durable_state(
            prior_runs=prior_runs,
            current_run_id=41,
            get_run_artifacts=lambda _rid: art_meta,
            download_artifact_zip=lambda _aid: b"some-zip-bytes",
            repository_root=repo,
        )


def test_restore_predecessor_multiple_success_tars_in_zip_fails_closed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("success-1.tar.gz", b"x")
        zf.writestr("success-2.tar.gz", b"y")
    zip_bytes = buf.getvalue()

    prior_runs = [{"id": 50, "conclusion": "success"}]
    art_meta = {
        "artifacts": [
            {
                "id": 5001,
                "name": "success-test.tar.gz",
                "expired": False,
            }
        ]
    }

    with pytest.raises(runner.FreshHoldoutActivationError, match="must contain exactly one success tar archive"):
        runner.restore_predecessor_durable_state(
            prior_runs=prior_runs,
            current_run_id=51,
            get_run_artifacts=lambda _rid: art_meta,
            download_artifact_zip=lambda _aid: zip_bytes,
            repository_root=repo,
        )


# --- SCHEDULE AMBIGUITY TESTS ---


def test_resolve_nominal_schedule_slot_delayed_07_past_37() -> None:
    last_committed = dt.datetime(2026, 8, 19, 0, 37, 0, tzinfo=UTC)
    created = dt.datetime(2026, 8, 19, 1, 40, 0, tzinfo=UTC)
    nominal, nominal_iso, _, _, _ = runner.resolve_nominal_schedule_slot(
        "7 * * * *", created, last_committed_utc=last_committed
    )
    assert nominal == dt.datetime(2026, 8, 19, 1, 7, 0, tzinfo=UTC)
    assert nominal_iso == "2026-08-19T01:07:00.000000Z"


def test_resolve_nominal_schedule_slot_delayed_37_past_next_07() -> None:
    last_committed = dt.datetime(2026, 8, 19, 0, 7, 0, tzinfo=UTC)
    created = dt.datetime(2026, 8, 19, 1, 10, 0, tzinfo=UTC)
    nominal, nominal_iso, _, _, _ = runner.resolve_nominal_schedule_slot(
        "37 * * * *", created, last_committed_utc=last_committed
    )
    assert nominal == dt.datetime(2026, 8, 19, 0, 37, 0, tzinfo=UTC)
    assert nominal_iso == "2026-08-19T00:37:00.000000Z"


def test_resolve_nominal_schedule_slot_ambiguous_more_than_one_hour_fails_closed() -> None:
    last_committed = dt.datetime(2026, 8, 19, 10, 37, 0, tzinfo=UTC)
    created = dt.datetime(2026, 8, 19, 12, 10, 0, tzinfo=UTC)
    with pytest.raises(runner.FreshHoldoutActivationError, match="ambiguous schedule occurrence"):
        runner.resolve_nominal_schedule_slot(
            "7 * * * *", created, last_committed_utc=last_committed
        )


def test_resolve_nominal_schedule_slot_genesis_derives_exact_slot() -> None:
    created = dt.datetime(2026, 8, 19, 0, 7, 15, tzinfo=UTC)
    nominal, nominal_iso, _, _, _ = runner.resolve_nominal_schedule_slot("7 * * * *", created, last_committed_utc=None)
    assert nominal == dt.datetime(2026, 8, 19, 0, 7, 0, tzinfo=UTC)
    assert nominal_iso == "2026-08-19T00:07:00.000000Z"


# --- ARCHIVE INTEGRITY & MEMBER SAFETY TESTS ---


def test_verify_and_extract_archive_rejects_symlinks_and_hardlinks(tmp_path: Path) -> None:
    repo, _state = _repo(tmp_path)
    tar_path = tmp_path / "bad-symlink.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        ti = tarfile.TarInfo(name=".cache/athena-research/fotmob-utc-native-xg-fresh-holdout/link")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"
        tar.addfile(ti)

    with pytest.raises(runner.FreshHoldoutActivationError, match="special archive member"):
        runner.verify_and_extract_durable_state_archive(tar_path, repository_root=repo)


def test_verify_and_extract_archive_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    repo, _state = _repo(tmp_path)
    tar_path = tmp_path / "bad-traversal.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        ti = tarfile.TarInfo(name=".cache/../../escape.txt")
        ti.size = 4
        tar.addfile(ti, fileobj=Path(__file__).open("rb"))

    with pytest.raises(runner.FreshHoldoutActivationError, match="forbidden archive member path"):
        runner.verify_and_extract_durable_state_archive(tar_path, repository_root=repo)


def test_verify_and_extract_archive_verifies_sha256_digest(tmp_path: Path) -> None:
    repo, _state = _repo(tmp_path)
    tar_path = tmp_path / "valid.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        pass

    with pytest.raises(runner.FreshHoldoutActivationError, match="archive SHA-256 digest mismatch"):
        runner.verify_and_extract_durable_state_archive(
            tar_path, repository_root=repo, expected_sha256="0" * 64
        )


# --- ZERO PYPI & WORKFLOW SPECIFICATION TESTS ---


def test_activation_runner_runtime_path_has_zero_external_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    runtime_files = [
        "domain/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py",
        "scripts/run_fotmob_utc_native_xg_fresh_holdout_tick.py",
        "domain/fotmob_data_matches_capture.py",
        "scripts/capture_fotmob_data_matches.py",
        "domain/fotmob_data_matches_ordinary_ft_finished_score_adapter.py",
        "domain/fotmob_utc_native_expected_goals_fresh_holdout.py",
        "domain/fotmob_utc_native_expected_goals_fresh_holdout_collection_control.py",
        "scripts/qualify_fotmob_historical_source_history_completeness_materialization.py",
    ]
    stdlib_modules = set(sys.stdlib_module_names) | {"zoneinfo"}
    external = set()

    for rel in runtime_files:
        path = repo_root / rel
        assert path.is_file()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0]
                    if root_pkg not in stdlib_modules and root_pkg not in ("domain", "scripts"):
                        external.add((rel, root_pkg))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg not in stdlib_modules and root_pkg not in ("domain", "scripts"):
                        external.add((rel, root_pkg))

    assert external == set()


def test_workflow_installs_no_pypi_packages() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workflow = repo_root / ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
    assert workflow.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "pip install" not in text
    assert "requirements.txt" not in text
    assert "cache: pip" not in text
    assert "cancel-in-progress: false" in text
    assert "actions: read" in text
    assert "contents: write" in text
    assert "workflow_dispatch:" not in text
    assert "--execute-live-network" in text
    assert "athena-fresh-holdout-bootstrap-v1" in text
    assert "success_asset" in text
    assert "failure_asset" in text
    assert "retention-days: 90" in text
