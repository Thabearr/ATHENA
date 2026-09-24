from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from domain.current_fotmob_fixture_review_policy import (
    canonical_current_fotmob_fixture_review_policy_result_bytes,
)
from services.current_fotmob_ingest_compatibility import (
    COMPATIBILITY_POLICY_ID,
    CurrentFotMobIngestCompatibilityError,
    project_current_reviewed_fotmob_source_from_ingest_artifact,
    verify_current_fotmob_ingest_compatibility_receipt,
)
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.ingest_contracts import AthenaIngestRequest, canonical_json_bytes, sha256_bytes, strict_json_loads
from scripts.capture_fotmob_data_matches import ALLOWED_OUTPUT_RELATIVE
from scripts.issue_current_fotmob_reviewed_source import build_verified_current_fotmob_bootstrap_from_capture
from services.athena_ingest_service import (
    RECEIPT_NAME,
    REPLAY_NAME,
    REQUEST_NAME,
    UPDATE_NAME,
    execute_ingest_request,
)


UTC = timezone.utc
REQUEST_DATE = "20260924"
OBSERVED_AT = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
ISSUED_AT = datetime(2026, 9, 24, 8, 5, tzinfo=UTC)
CODE_STATE = {"evidence_git_head_sha": "a" * 40, "tracked_worktree_clean": True}


def _epoch_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1000)


def _fotmob_bytes(request_date: str = REQUEST_DATE) -> bytes:
    date_value = datetime.strptime(request_date, "%Y%m%d")
    kickoff = date_value.replace(hour=15, tzinfo=UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    display_time = date_value.replace(hour=15).strftime("%d.%m.%Y 15:00")
    body = {
        "leagues": [
            {
                "ccode": "ENG",
                "id": 47,
                "internalRank": 1,
                "matches": [
                    {
                        "away": {"id": 202, "score": 0, "name": "Away FC", "longName": "Away FC"},
                        "eliminatedTeamId": None,
                        "home": {"id": 101, "score": 0, "name": "Home FC", "longName": "Home FC"},
                        "id": 1001,
                        "leagueId": 47,
                        "status": {
                            "utcTime": kickoff,
                            "halfs": {"firstHalfStarted": ""},
                            "periodLength": 45,
                            "started": False,
                            "cancelled": False,
                            "finished": False,
                        },
                        "statusId": 1,
                        "time": display_time,
                        "timeTS": _epoch_ms(kickoff),
                        "tournamentStage": "",
                    }
                ],
                "name": "Premier League",
                "primaryId": 47,
                "simpleLeague": False,
            }
        ],
        "date": request_date,
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    return root


def _build_artifact(
    tmp_path: Path,
    *,
    dates: tuple[str, ...] = (REQUEST_DATE,),
    fail_acquisition: bool = False,
) -> tuple[Path, Path, dict[str, int]]:
    repository = _repository(tmp_path)
    calls = {"count": 0}

    def acquire(*, request_date: str, timezone: str, ccode3: str):
        calls["count"] += 1
        assert request_date in dates
        assert timezone == "UTC"
        assert ccode3 == "NGA"
        if fail_acquisition:
            raise RuntimeError("deterministic synthetic provider failure")
        raw = _fotmob_bytes(request_date)
        return CapturedFotMobDataMatchesResponse(
            status=200,
            content_type="application/json; charset=utf-8",
            content_length=len(raw),
            body=raw,
            observed_at=OBSERVED_AT,
            network_acquisition_performed=True,
        )

    receipt = execute_ingest_request(
        AthenaIngestRequest.for_dates(dates),
        repository_root=repository,
        exact_commit_sha="a" * 40,
        acquisition_callable=acquire,
    )
    assert receipt.status == ("FAILED" if fail_acquisition else "SUCCESS")
    artifact = repository / "artifacts" / "athena-ingest-workflow"
    date_root = repository / ALLOWED_OUTPUT_RELATIVE / dates[0]
    direct_capture = date_root / next(item.name for item in date_root.iterdir()) if date_root.exists() else date_root
    return artifact, direct_capture, calls


def _project(artifact: Path, repository: Path):
    return project_current_reviewed_fotmob_source_from_ingest_artifact(
        artifact,
        issued_at=ISSUED_AT,
        repository_root=repository,
        code_state=CODE_STATE,
    )


def _read(path: Path) -> bytes:
    return path.read_bytes()


def _write_mapping(path: Path, mapping: dict) -> None:
    path.write_bytes(canonical_json_bytes(mapping))


def test_canonical_ingest_capture_has_exact_pr243_semantic_parity(tmp_path: Path, monkeypatch) -> None:
    artifact, direct_capture, calls = _build_artifact(tmp_path)
    repository = tmp_path / "repo"

    def forbidden(*args, **kwargs):
        raise AssertionError("compatibility adapter attempted provider acquisition")

    monkeypatch.setattr("scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches", forbidden)
    monkeypatch.setattr("scripts.issue_current_fotmob_reviewed_source.fetch_fotmob_data_matches", forbidden)
    adapter_result = _project(artifact, repository)
    direct = build_verified_current_fotmob_bootstrap_from_capture(
        direct_capture,
        issued_at=ISSUED_AT,
        repository_root=repository,
        code_state=CODE_STATE,
    )

    assert calls["count"] == 1  # one synthetic ingest acquisition; adapter adds none
    assert adapter_result.receipt["policy_id"] == COMPATIBILITY_POLICY_ID
    assert adapter_result.receipt["provider_request_count_by_adapter"] == 0
    assert adapter_result.receipt["source_raw_sha256"] == direct.source_raw_sha256
    assert adapter_result.receipt["source_capture_manifest_sha256"] == direct.source_capture_manifest_sha256
    assert adapter_result.receipt["policy_result_sha256"] == hashlib.sha256(
        canonical_current_fotmob_fixture_review_policy_result_bytes(direct.policy_result)
    ).hexdigest()
    assert adapter_result.receipt["handoff_sha256"] == direct.summary()["handoff_sha256"]
    assert adapter_result.receipt["bootstrap_sha256"] == direct.verified_bootstrap.bootstrap_sha256
    assert adapter_result.receipt["verified_bootstrap_receipt_sha256"] == hashlib.sha256(
        direct.verified_bootstrap_receipt_bytes
    ).hexdigest()
    assert adapter_result.receipt["fixture_identifiers"] == direct.summary()["fixture_identifiers"]
    assert adapter_result.receipt["approved_count"] == direct.policy_result.policy_approved_count == 1
    assert adapter_result.receipt["minimum_lead_seconds"] == direct.policy_result.minimum_lead_seconds
    assert adapter_result.receipt["max_source_age_seconds"] == direct.policy_result.max_source_age_seconds
    assert adapter_result.receipt["pr243_authority"] == direct.summary()["authority"]
    assert direct.summary()["wager_placed"] is False
    source = next((artifact / "sources" / "fotmob" / REQUEST_DATE).iterdir())
    assert source == adapter_result.execution.source_capture_directory.resolve()
    assert (source / "response.json").read_bytes() == direct.source_capture_directory.joinpath("response.json").read_bytes()
    assert (source / "manifest.json").read_bytes() == direct.source_capture_directory.joinpath("manifest.json").read_bytes()

    verified = verify_current_fotmob_ingest_compatibility_receipt(
        adapter_result.receipt_bytes,
        artifact,
        repository_root=repository,
        code_state=CODE_STATE,
    )
    assert verified.receipt_bytes == adapter_result.receipt_bytes


def test_compatibility_semantic_receipt_does_not_bind_local_paths(tmp_path: Path) -> None:
    left_artifact, _left_capture, _left_calls = _build_artifact(tmp_path / "left")
    right_artifact, _right_capture, _right_calls = _build_artifact(tmp_path / "right")
    left = _project(left_artifact, tmp_path / "left" / "repo")
    right = _project(right_artifact, tmp_path / "right" / "repo")
    assert left.receipt_bytes == right.receipt_bytes


def test_adapter_rejects_naive_issued_at_and_never_calls_network(tmp_path: Path, monkeypatch) -> None:
    artifact, _capture, calls = _build_artifact(tmp_path)
    monkeypatch.setattr(
        "scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches",
        lambda **kwargs: pytest.fail("provider acquisition reached"),
    )
    with pytest.raises(CurrentFotMobIngestCompatibilityError, match="timezone-aware"):
        project_current_reviewed_fotmob_source_from_ingest_artifact(
            artifact,
            issued_at=datetime(2026, 9, 24, 8, 5),
            repository_root=tmp_path / "repo",
            code_state=CODE_STATE,
        )
    assert calls["count"] == 1


@pytest.mark.parametrize("filename", [REQUEST_NAME, UPDATE_NAME, RECEIPT_NAME, REPLAY_NAME])
def test_noncanonical_or_mutated_top_level_artifacts_fail_closed(tmp_path: Path, filename: str) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    path = artifact / filename
    raw = path.read_bytes()
    if filename == REPLAY_NAME:
        mapping = strict_json_loads(raw)
        mapping["source_count"] = 2
        _write_mapping(path, mapping)
    elif filename == REQUEST_NAME:
        path.write_bytes(raw + b" ")
    elif filename == UPDATE_NAME:
        mapping = strict_json_loads(raw)
        mapping["source_records"][0]["request_date"] = "20260925"
        _write_mapping(path, mapping)
    else:
        mapping = strict_json_loads(raw)
        mapping["request_sha256"] = "f" * 64
        _write_mapping(path, mapping)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


@pytest.mark.parametrize("target", ["response.json", "manifest.json"])
def test_source_byte_mutations_fail_closed(tmp_path: Path, target: str) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    source = next((artifact / "sources" / "fotmob" / REQUEST_DATE).iterdir())
    path = source / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_two_date_request_is_rejected(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(
        tmp_path, dates=("20260924", "20260925")
    )
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_failed_or_partial_ingest_is_rejected(tmp_path: Path) -> None:
    artifact, _capture, calls = _build_artifact(tmp_path, fail_acquisition=True)
    assert calls["count"] == 1
    receipt = strict_json_loads((artifact / RECEIPT_NAME).read_bytes())
    assert receipt["status"] == "FAILED"
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_not_committed_update_and_zero_source_are_rejected(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    path = artifact / UPDATE_NAME
    update = strict_json_loads(path.read_bytes())
    update["source_records"] = []
    update["source_record_count"] = 0
    update["all_requested_dates_captured"] = False
    update["commit_status"] = "CANONICAL_SOURCE_UPDATE_NOT_COMMITTED"
    update["canonical_sha256"] = sha256_bytes(
        canonical_json_bytes({key: value for key, value in update.items() if key != "canonical_sha256"})
    )
    _write_mapping(path, update)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_request_source_date_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    path = artifact / UPDATE_NAME
    update = strict_json_loads(path.read_bytes())
    update["source_records"][0]["request_date"] = "20260925"
    update["canonical_sha256"] = sha256_bytes(
        canonical_json_bytes({key: value for key, value in update.items() if key != "canonical_sha256"})
    )
    _write_mapping(path, update)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


@pytest.mark.parametrize("field", ["request_sha256", "canonical_store_update_sha256"])
def test_rebound_ingest_receipt_hash_mutations_fail_closed(tmp_path: Path, field: str) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    path = artifact / RECEIPT_NAME
    receipt = strict_json_loads(path.read_bytes())
    receipt[field] = "f" * 64
    receipt["canonical_sha256"] = sha256_bytes(
        canonical_json_bytes({key: value for key, value in receipt.items() if key != "canonical_sha256"})
    )
    _write_mapping(path, receipt)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_missing_source_file_fails_closed(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    source = next((artifact / "sources" / "fotmob" / REQUEST_DATE).iterdir())
    (source / "response.json").unlink()
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    request_path = artifact / REQUEST_NAME
    raw = request_path.read_text(encoding="utf-8")
    request_path.write_text(raw.replace('"provider":"fotmob"', '"provider":"fotmob","provider":"fotmob"', 1), encoding="utf-8")
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


@pytest.mark.parametrize(
    ("field", "value"),
    [("dates", []), ("provider", "FotMob"), ("timezone", "Africa/Lagos"), ("ccode3", "ENG")],
)
def test_out_of_scope_request_mutations_fail_closed(tmp_path: Path, field: str, value) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    path = artifact / REQUEST_NAME
    request = strict_json_loads(path.read_bytes())
    request[field] = value
    request["canonical_sha256"] = sha256_bytes(
        canonical_json_bytes({key: item for key, item in request.items() if key != "canonical_sha256"})
    )
    _write_mapping(path, request)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")


def test_compatibility_receipt_semantic_rehash_still_fails(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    result = _project(artifact, tmp_path / "repo")
    receipt = strict_json_loads(result.receipt_bytes)
    receipt["wager"] = True
    receipt["canonical_sha256"] = sha256_bytes(canonical_json_bytes({k: v for k, v in receipt.items() if k != "canonical_sha256"}))
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        verify_current_fotmob_ingest_compatibility_receipt(
            canonical_json_bytes(receipt),
            artifact,
            repository_root=tmp_path / "repo",
            code_state=CODE_STATE,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_acquisition_performed_by_adapter", True),
        ("source_bytes_copied_by_adapter", True),
        ("source_bytes_rewritten_by_adapter", True),
        ("full_legacy_request_contract_equivalence_claimed", True),
        ("noncanonical_timezone_or_ccode3_supported", True),
        ("legacy_workflow_retirement_authorized", True),
        ("fixture_intelligence_fact_authority", True),
        ("fixture_intelligence_snapshot_authority", True),
        ("model_feature_authority", True),
        ("probability_authority", True),
        ("pricing_authority", True),
        ("routing_authority", True),
        ("portfolio_authority", True),
        ("share_code_authority", True),
        ("login", True),
        ("cookies", True),
        ("wallet", True),
        ("staking", True),
        ("wager", True),
        ("backfill_authority", True),
    ],
)
def test_compatibility_receipt_authority_mutations_fail_even_when_rehashed(
    tmp_path: Path, field: str, value: bool
) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    result = _project(artifact, tmp_path / "repo")
    receipt = strict_json_loads(result.receipt_bytes)
    receipt[field] = value
    receipt["canonical_sha256"] = sha256_bytes(
        canonical_json_bytes({key: item for key, item in receipt.items() if key != "canonical_sha256"})
    )
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        verify_current_fotmob_ingest_compatibility_receipt(
            canonical_json_bytes(receipt), artifact, repository_root=tmp_path / "repo", code_state=CODE_STATE
        )


@pytest.mark.parametrize("issued_at", [None, "2026-09-24T08:05:00Z"])
def test_invalid_issued_at_values_fail_closed(tmp_path: Path, issued_at) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        project_current_reviewed_fotmob_source_from_ingest_artifact(
            artifact, issued_at=issued_at, repository_root=tmp_path / "repo", code_state=CODE_STATE
        )


def test_capture_path_traversal_and_symlink_fail_closed(tmp_path: Path) -> None:
    artifact, _capture, _calls = _build_artifact(tmp_path)
    update_path = artifact / UPDATE_NAME
    update = strict_json_loads(update_path.read_bytes())
    update["source_records"][0]["capture_relative_path"] = "sources/fotmob/20260924/../../escape"
    update["canonical_sha256"] = sha256_bytes(canonical_json_bytes({k: v for k, v in update.items() if k != "canonical_sha256"}))
    _write_mapping(update_path, update)
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(artifact, tmp_path / "repo")

    symlink_root = tmp_path / "symlink-artifact"
    try:
        symlink_root.symlink_to(artifact, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this Windows host")
    with pytest.raises(CurrentFotMobIngestCompatibilityError):
        _project(symlink_root, tmp_path / "repo")
