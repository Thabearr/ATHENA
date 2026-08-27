from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
from domain.current_fotmob_durable_fresh_history_prefix import (
    NEXT_REQUIRED_BOUNDARY,
    STATUS,
    CurrentDurableFreshHistoryPrefixError,
    build_current_fotmob_durable_fresh_history_prefix_handoff,
    canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes,
)
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from scripts.capture_fotmob_data_matches import write_data_matches_capture_directory
from scripts.issue_current_fotmob_reviewed_source import (
    build_verified_current_fotmob_bootstrap_from_capture,
)

UTC = dt.timezone.utc
SOURCE_OBSERVED = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
SOURCE_ISSUED = dt.datetime(2026, 8, 27, 7, 5, tzinfo=UTC)
KICKOFF = dt.datetime(2026, 8, 27, 15, 0, tzinfo=UTC)
PREFIX_NOMINAL = dt.datetime(2026, 8, 27, 6, 37, tzinfo=UTC)
PREFIX_COMMITTED = dt.datetime(2026, 8, 27, 6, 40, tzinfo=UTC)
RUN_ID = 12345
ARTIFACT_NAME = "success-20260827T063700Z-run-12345.tar.gz"


def _canonical(value) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _utc_text(value: dt.datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _epoch_ms(value: dt.datetime) -> int:
    epoch = dt.datetime(1970, 1, 1, tzinfo=UTC)
    delta = value - epoch
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def _raw() -> bytes:
    kickoff_text = KICKOFF.isoformat(timespec="milliseconds").replace("+00:00", "Z")
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
                        "id": 1001,
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
                        "time": KICKOFF.strftime("%d.%m.%Y %H:%M"),
                        "timeTS": _epoch_ms(KICKOFF),
                        "tournamentStage": "",
                    }
                ],
                "name": "Premier League",
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
        "date": KICKOFF.strftime("%Y%m%d"),
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _current(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = _raw()
    response = CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=SOURCE_OBSERVED,
        network_acquisition_performed=True,
    )
    directory, manifest = write_data_matches_capture_directory(
        response,
        request_date=KICKOFF.strftime("%Y%m%d"),
        timezone="UTC",
        ccode3="NGA",
        repository_root=tmp_path,
    )
    execution = build_verified_current_fotmob_bootstrap_from_capture(
        directory,
        issued_at=SOURCE_ISSUED,
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


def _history(monkeypatch: pytest.MonkeyPatch) -> bytes:
    rows = [
        _bootstrap_row(
            6001,
            101,
            303,
            dt.datetime(2026, 8, 25, 18, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 25, 20, 0, tzinfo=UTC),
            2,
            0,
        ),
        _bootstrap_row(
            6002,
            202,
            404,
            dt.datetime(2026, 8, 25, 19, 0, tzinfo=UTC),
            dt.datetime(2026, 8, 25, 21, 0, tzinfo=UTC),
            1,
            1,
        ),
    ]
    raw = b"".join(fresh._canonical(row) for row in rows)
    monkeypatch.setattr(
        fresh,
        "BOOTSTRAP_PROJECTION_SHA256",
        hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_SIZE", len(raw))
    monkeypatch.setattr(fresh, "BOOTSTRAP_PROJECTION_ROWS", len(rows))
    return raw


def _state_archive(*, committed_at: dt.datetime = PREFIX_COMMITTED) -> tuple[bytes, bytes]:
    state_root = Path(control.CONTROL_ROOT_RELATIVE)
    control_row = {
        "schema_version": 1,
        "event": "TICK_COMMITTED",
        "scheduled_for_utc": _utc_text(PREFIX_NOMINAL),
        "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W35",
        "durable_asset_name": ARTIFACT_NAME,
        "nominal_schedule_time_used_as_observation_time": False,
        "backfill_or_retrofill_performed": False,
        "outcome_or_performance_input_used_for_close": False,
    }
    checkpoint = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "last_committed_scheduled_for_utc": _utc_text(PREFIX_NOMINAL),
        "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
        "capture_count": 0,
        "prediction_count": 0,
        "settled_or_terminal_count": 0,
        "control_event_count": 1,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W35",
        "durable_asset_name": ARTIFACT_NAME,
    }
    files = {
        state_root / control.CAPTURE_INDEX_FILENAME: b"",
        state_root / control.PREDICTION_JOURNAL_FILENAME: b"",
        state_root / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME: b"",
        state_root / control.SETTLEMENT_JOURNAL_FILENAME: b"",
        state_root / control.CONTROL_JOURNAL_FILENAME: _canonical(control_row),
        state_root / control.CHECKPOINT_FILENAME: _canonical(checkpoint),
    }

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        directories = set()
        for path in files:
            current = path.parent
            while str(current) not in (".", ""):
                directories.add(current.as_posix())
                current = current.parent
        for name in sorted(directories, key=lambda item: (item.count("/"), item)):
            info = tarfile.TarInfo(name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o700
            tar.addfile(info)
        for path, raw in sorted(files.items(), key=lambda item: item[0].as_posix()):
            info = tarfile.TarInfo(path.as_posix())
            info.size = len(raw)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(raw))
    archive = tar_buffer.getvalue()

    receipt = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "runner_state": runner.RUNNER_STATE,
        "scheduled_for_utc": _utc_text(PREFIX_NOMINAL),
        "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "fresh_holdout_collection_started_by_this_run": True,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W35",
        "durable_asset_name": ARTIFACT_NAME,
        "next_required_boundary": runner.NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in runner.SAFETY_KEYS},
        "workflow_run_id": RUN_ID,
        "workflow_event_schedule": "37 * * * *",
        "nominal_scheduled_for_utc": _utc_text(PREFIX_NOMINAL),
        "durable_asset_sha256": hashlib.sha256(archive).hexdigest(),
        "durable_asset_size_bytes": len(archive),
        "tick_exit_code": 0,
        "tick_committed": True,
        "failure_lineage_reconcile_outcome": "skipped",
    }
    return archive, _canonical(receipt)


def _artifact_zip(*, committed_at: dt.datetime = PREFIX_COMMITTED):
    archive, receipt = _state_archive(committed_at=committed_at)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive_zip:
        archive_zip.writestr(ARTIFACT_NAME, archive)
        archive_zip.writestr("fresh-holdout-tick-receipt.json", receipt)
    raw = buffer.getvalue()
    return raw, f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    current, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    artifact_zip, metadata_digest = _artifact_zip()
    handoff = build_current_fotmob_durable_fresh_history_prefix_handoff(
        current_bootstrap=current.bootstrap,
        source_raw_json=raw,
        source_manifest=manifest,
        legacy_bootstrap_projection_raw=history,
        workflow_run_id=RUN_ID,
        artifact_name=ARTIFACT_NAME,
        artifact_zip_bytes=artifact_zip,
        artifact_zip_metadata_digest=metadata_digest,
    )
    return handoff, current, raw, manifest, history, artifact_zip, metadata_digest


def test_success_archive_replays_exact_cumulative_prefix_without_current_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    assert handoff.status == STATUS
    assert handoff.nominal_scheduled_for_utc == PREFIX_NOMINAL
    assert handoff.committed_at_utc == PREFIX_COMMITTED
    assert handoff.reviewed_fresh_settlement_count == 0
    assert handoff.reviewed_legacy_update_count == 0
    assert handoff.shadow_handoff.fixture_count == 1
    assert handoff.shadow_handoff.sealed_complete_case_count == 1
    assert handoff.latest_applicable_success_selection_proven is False
    assert handoff.current_fresh_history_prefix_complete is False
    assert handoff.next_required_boundary == NEXT_REQUIRED_BOUNDARY
    assert not any(handoff.authority.values())
    payload = handoff.to_dict()
    assert payload["latest_applicable_success_selection_proven"] is False
    assert payload["current_fresh_history_prefix_complete"] is False
    assert payload["wager_placed"] is False


def test_archive_committed_after_current_source_observation_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    artifact_zip, metadata_digest = _artifact_zip(
        committed_at=SOURCE_OBSERVED + dt.timedelta(minutes=1)
    )
    with pytest.raises(
        CurrentDurableFreshHistoryPrefixError,
        match="committed after the current source observation",
    ):
        build_current_fotmob_durable_fresh_history_prefix_handoff(
            current_bootstrap=current.bootstrap,
            source_raw_json=raw,
            source_manifest=manifest,
            legacy_bootstrap_projection_raw=history,
            workflow_run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            artifact_zip_bytes=artifact_zip,
            artifact_zip_metadata_digest=metadata_digest,
        )


def test_actions_zip_digest_tampering_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, raw, manifest = _current(tmp_path)
    history = _history(monkeypatch)
    artifact_zip, _metadata_digest = _artifact_zip()
    with pytest.raises(CurrentDurableFreshHistoryPrefixError, match="PR168"):
        build_current_fotmob_durable_fresh_history_prefix_handoff(
            current_bootstrap=current.bootstrap,
            source_raw_json=raw,
            source_manifest=manifest,
            legacy_bootstrap_projection_raw=history,
            workflow_run_id=RUN_ID,
            artifact_name=ARTIFACT_NAME,
            artifact_zip_bytes=artifact_zip,
            artifact_zip_metadata_digest="sha256:" + "0" * 64,
        )


def test_detached_prefix_digest_cannot_be_relabelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    replacement = "f" * 64
    assert replacement != handoff.archive_sha256
    with pytest.raises(CurrentDurableFreshHistoryPrefixError, match="archive_sha256"):
        dataclasses.replace(handoff, archive_sha256=replacement)


def test_archive_proof_cannot_switch_on_complete_current_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    with pytest.raises(
        CurrentDurableFreshHistoryPrefixError,
        match="cannot claim complete current history",
    ):
        dataclasses.replace(handoff, current_fresh_history_prefix_complete=True)


def test_archive_proof_cannot_switch_on_downstream_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, *_rest = _handoff(tmp_path, monkeypatch)
    changed = dict(handoff.authority)
    changed["phase6"] = True
    with pytest.raises(CurrentDurableFreshHistoryPrefixError, match="authority"):
        dataclasses.replace(handoff, authority=changed)


def test_canonical_output_is_deterministic_and_does_not_embed_source_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handoff, _current_value, source_raw, _manifest, history, artifact_zip, _digest = _handoff(
        tmp_path,
        monkeypatch,
    )
    first = canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes(handoff)
    second = canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes(
        dataclasses.replace(handoff)
    )
    assert first == second
    assert source_raw not in first
    assert history not in first
    assert artifact_zip not in first
    decoded = json.loads(first)
    assert decoded["next_required_boundary"] == NEXT_REQUIRED_BOUNDARY
    assert decoded["current_fresh_history_prefix_complete"] is False
