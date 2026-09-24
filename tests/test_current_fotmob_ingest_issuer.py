from __future__ import annotations

from datetime import datetime, timezone
import ast
import hashlib
import json
from pathlib import Path

import pytest

from domain.current_fotmob_fixture_review_policy import (
    canonical_current_fotmob_fixture_review_policy_result_bytes,
)
from domain.fotmob_data_matches_capture import CapturedFotMobDataMatchesResponse
from domain.ingest_contracts import AthenaCanonicalStoreUpdate, strict_json_loads
from scripts.capture_fotmob_data_matches import ALLOWED_OUTPUT_RELATIVE
from scripts.issue_current_fotmob_reviewed_source import (
    build_verified_current_fotmob_bootstrap_from_capture,
)
from services import current_fotmob_ingest_issuer as issuer
from services.athena_ingest_service import ARTIFACT_RELATIVE, RECEIPT_NAME


COMMIT = "a" * 40
REQUEST_DATE = "20260924"
OBSERVED_AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
ISSUED_AT = datetime(2026, 9, 24, 8, 5, tzinfo=timezone.utc)
CODE_STATE = {"evidence_git_head_sha": COMMIT, "tracked_worktree_clean": True}


def _fotmob_bytes(request_date: str = REQUEST_DATE) -> bytes:
    date_value = datetime.strptime(request_date, "%Y%m%d")
    kickoff = date_value.replace(hour=15, tzinfo=timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    body = {
        "leagues": [{
            "ccode": "ENG", "id": 47, "internalRank": 1,
            "matches": [{
                "away": {"id": 202, "score": 0, "name": "Away FC", "longName": "Away FC"},
                "eliminatedTeamId": None,
                "home": {"id": 101, "score": 0, "name": "Home FC", "longName": "Home FC"},
                "id": 1001, "leagueId": 47,
                "status": {
                    "utcTime": kickoff,
                    "halfs": {"firstHalfStarted": ""},
                    "periodLength": 45, "started": False,
                    "cancelled": False, "finished": False,
                },
                "statusId": 1,
                "time": date_value.replace(hour=15).strftime("%d.%m.%Y 15:00"),
                "timeTS": int(datetime.fromisoformat(kickoff[:-1] + "+00:00").timestamp() * 1000),
                "tournamentStage": "",
            }],
            "name": "Premier League", "primaryId": 47, "simpleLeague": False,
        }],
        "date": request_date,
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _response(request_date: str = REQUEST_DATE) -> CapturedFotMobDataMatchesResponse:
    raw = _fotmob_bytes(request_date)
    return CapturedFotMobDataMatchesResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        content_length=len(raw),
        body=raw,
        observed_at=OBSERVED_AT,
        network_acquisition_performed=True,
    )


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    return root


def _issue(
    repository: Path,
    acquire,
    *,
    request_date: str = REQUEST_DATE,
    **kwargs,
):
    clock = kwargs.pop("clock", lambda: ISSUED_AT)
    git_head_provider = kwargs.pop("git_head_provider", lambda _repo: COMMIT)
    return issuer.issue_current_reviewed_fotmob_via_canonical_ingest(
        request_date,
        repository_root=repository,
        expected_git_sha=COMMIT,
        expected_git_ref="refs/heads/main",
        execute_live_network=True,
        acquisition_callable=acquire,
        git_head_provider=git_head_provider,
        clock=clock,
        code_state=CODE_STATE,
        **kwargs,
    )


def test_success_path_uses_one_canonical_request_and_produces_pr243_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repo(tmp_path)
    calls: list[tuple[str, str, str]] = []
    sequence: list[str] = []

    def acquire(*, request_date: str, timezone: str, ccode3: str):
        sequence.append("acquisition")
        calls.append((request_date, timezone, ccode3))
        return _response(request_date)

    def clock():
        sequence.append("clock")
        return ISSUED_AT

    def forbidden(*args, **kwargs):
        pytest.fail("projection attempted another provider transport request")

    monkeypatch.setattr("scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches", forbidden)
    monkeypatch.setattr("scripts.issue_current_fotmob_reviewed_source.fetch_fotmob_data_matches", forbidden)
    result = _issue(repository, acquire, clock=clock)
    request = strict_json_loads((repository / ARTIFACT_RELATIVE / "resolved-ingest-request.json").read_bytes())
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(
        (repository / ARTIFACT_RELATIVE / "canonical-store-update.json").read_bytes()
    ))
    assert calls == [(REQUEST_DATE, "UTC", "NGA")]
    assert sequence == ["acquisition", "clock"]
    assert request == {
        "schema_version": 1,
        "policy_id": "ATHENA_INGEST_REQUEST_V1",
        "provider": "fotmob",
        "dates": [REQUEST_DATE],
        "timezone": "UTC",
        "ccode3": "NGA",
    }
    assert result.ingest_receipt.status == "SUCCESS"
    assert result.ingest_receipt.exact_commit_sha == COMMIT
    assert result.ingest_receipt.stage == "COMPLETED"
    assert result.ingest_receipt.request_sha256 is not None
    assert result.ingest_receipt.canonical_store_update_committed is True
    assert update.commit_status == "CANONICAL_SOURCE_UPDATE_READY"
    assert update.source_record_count == 1
    assert result.ingest_receipt.provider_request_count == 1
    assert result.ingest_receipt.source_count == 1
    assert result.compatibility_result.receipt["provider_request_count_by_adapter"] == 0
    assert result.compatibility_result.receipt["source_raw_sha256"] == result.execution.source_raw_sha256
    assert result.compatibility_result.receipt["source_capture_manifest_sha256"] == result.execution.source_capture_manifest_sha256
    assert result.compatibility_result.receipt["original_ingest_exact_commit_sha"] == COMMIT
    assert result.execution.summary()["wager_placed"] is False
    assert (repository / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes() == result.ingest_receipt.canonical_bytes


def test_same_exact_capture_has_direct_pr243_semantic_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repo(tmp_path)
    calls = 0

    def acquire(*, request_date: str, timezone: str, ccode3: str):
        nonlocal calls
        calls += 1
        return _response(request_date)

    projected = _issue(repository, acquire)
    update = AthenaCanonicalStoreUpdate.from_mapping(strict_json_loads(
        (repository / ARTIFACT_RELATIVE / "canonical-store-update.json").read_bytes()
    ))
    assert len(update.source_records) == 1
    source = update.source_records[0]
    direct_root = repository / ALLOWED_OUTPUT_RELATIVE / REQUEST_DATE
    direct_capture = direct_root / next(iter(direct_root.iterdir())).name
    direct = build_verified_current_fotmob_bootstrap_from_capture(
        direct_capture,
        issued_at=ISSUED_AT,
        repository_root=repository,
        code_state=CODE_STATE,
    )
    compatibility = projected.compatibility_result
    receipt = compatibility.receipt
    summary = direct.summary()
    assert calls == 1
    assert source.raw_sha256 == direct.source_raw_sha256 == receipt["source_raw_sha256"]
    assert source.manifest_sha256 == direct.source_capture_manifest_sha256 == receipt["source_capture_manifest_sha256"]
    assert receipt["policy_result_sha256"] == hashlib.sha256(
        canonical_current_fotmob_fixture_review_policy_result_bytes(direct.policy_result)
    ).hexdigest()
    assert receipt["handoff_sha256"] == summary["handoff_sha256"]
    assert receipt["bootstrap_sha256"] == direct.verified_bootstrap.bootstrap_sha256
    assert receipt["verified_bootstrap_receipt_sha256"] == hashlib.sha256(
        direct.verified_bootstrap_receipt_bytes
    ).hexdigest()
    assert receipt["fixture_identifiers"] == summary["fixture_identifiers"]
    assert receipt["approved_count"] == direct.policy_result.policy_approved_count
    assert receipt["minimum_lead_seconds"] == direct.policy_result.minimum_lead_seconds == 3600
    assert receipt["max_source_age_seconds"] == direct.policy_result.max_source_age_seconds == 900
    assert receipt["pr243_authority"] == summary["authority"]
    assert summary["wager_placed"] is False

    from scripts import issue_current_fotmob_reviewed_source_via_ingest as workflow_cli

    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    calls_to_issuer = []

    def reviewed_issuer(request_date, **kwargs):
        calls_to_issuer.append((request_date, kwargs))
        return projected

    monkeypatch.setattr(
        workflow_cli,
        "issue_current_reviewed_fotmob_via_canonical_ingest",
        reviewed_issuer,
    )
    output = repository / "workflow-facing-execution.json"
    assert workflow_cli.main([
        "--date", REQUEST_DATE, "--execute-live-network", "--output", str(output)
    ]) == 0
    workflow_summary = json.loads(output.read_text(encoding="utf-8"))
    canonical_summary = projected.execution.summary()
    assert calls_to_issuer == [(
        REQUEST_DATE,
        {
            "repository_root": Path(workflow_cli.__file__).resolve().parents[1],
            "expected_git_sha": COMMIT,
            "expected_git_ref": "refs/heads/main",
            "execute_live_network": True,
        },
    )]
    assert workflow_summary == canonical_summary
    assert {
        key: value for key, value in workflow_summary.items()
        if key != "source_capture_directory"
    } == {
        key: value for key, value in summary.items()
        if key != "source_capture_directory"
    }
    assert calls == 1


@pytest.mark.parametrize(
    ("overrides", "date"),
    [
        ({"execute_live_network": False}, REQUEST_DATE),
        ({"timezone": "Africa/Lagos"}, REQUEST_DATE),
        ({"ccode3": "GHA"}, REQUEST_DATE),
        ({}, "20260230"),
        ({"expected_git_ref": "refs/heads/feature"}, REQUEST_DATE),
        ({"expected_git_sha": "ABCDEF"}, REQUEST_DATE),
    ],
)
def test_invalid_preconditions_never_acquire(
    tmp_path: Path, overrides: dict, date: str,
) -> None:
    repository = _repo(tmp_path)
    calls = 0

    def acquire(**kwargs):
        nonlocal calls
        calls += 1
        return _response(kwargs["request_date"])

    args = {
        "request_date": date,
        "repository_root": repository,
        "expected_git_sha": COMMIT,
        "expected_git_ref": "refs/heads/main",
        "execute_live_network": True,
        "acquisition_callable": acquire,
        "git_head_provider": lambda _repo: COMMIT,
        "clock": lambda: ISSUED_AT,
        "code_state": CODE_STATE,
    }
    args.update(overrides)
    with pytest.raises(issuer.CurrentFotMobIngestIssuerError):
        issuer.issue_current_reviewed_fotmob_via_canonical_ingest(**args)
    assert calls == 0
    assert not (repository / ARTIFACT_RELATIVE).exists()


def test_actual_head_mismatch_stops_before_acquisition(tmp_path: Path) -> None:
    repository = _repo(tmp_path)
    calls = 0

    def acquire(**kwargs):
        nonlocal calls
        calls += 1
        return _response(kwargs["request_date"])

    with pytest.raises(issuer.CurrentFotMobIngestIssuerError, match="HEAD differs"):
        issuer.issue_current_reviewed_fotmob_via_canonical_ingest(
            REQUEST_DATE,
            repository_root=repository,
            expected_git_sha=COMMIT,
            expected_git_ref="refs/heads/main",
            execute_live_network=True,
            acquisition_callable=acquire,
            git_head_provider=lambda _repo: "b" * 40,
        )
    assert calls == 0
    assert not (repository / ARTIFACT_RELATIVE).exists()


@pytest.mark.parametrize("root_state", ["file", "nonempty", "symlink"])
def test_unsafe_or_stale_artifact_root_stops_before_acquisition(
    tmp_path: Path, root_state: str,
) -> None:
    repository = _repo(tmp_path)
    artifact_root = repository / ARTIFACT_RELATIVE
    artifact_root.parent.mkdir(parents=True)
    if root_state == "file":
        artifact_root.write_bytes(b"not a directory")
    elif root_state == "nonempty":
        artifact_root.mkdir()
        (artifact_root / "old-receipt.json").write_bytes(b"old")
    else:
        target = repository / "outside"
        target.mkdir()
        try:
            artifact_root.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlink creation is unavailable")
    calls = 0

    def acquire(**kwargs):
        nonlocal calls
        calls += 1
        return _response(kwargs["request_date"])

    with pytest.raises(issuer.CurrentFotMobIngestIssuerError):
        _issue(repository, acquire)
    assert calls == 0


def test_failed_ingest_receipt_is_preserved_and_projection_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repo(tmp_path)
    calls = 0

    def fail(*, request_date: str, timezone: str, ccode3: str):
        nonlocal calls
        calls += 1
        raise RuntimeError("deterministic offline failure")

    monkeypatch.setattr(
        issuer,
        "project_current_reviewed_fotmob_source_from_ingest_artifact",
        lambda *args, **kwargs: pytest.fail("projection must not follow failed ingest"),
    )
    with pytest.raises(issuer.CurrentFotMobIngestIssuerFailure) as raised:
        _issue(repository, fail)
    assert calls == 1
    assert raised.value.ingest_receipt.failure_code == "PROVIDER_ACQUISITION_FAILED"
    artifact_receipt = strict_json_loads((repository / ARTIFACT_RELATIVE / RECEIPT_NAME).read_bytes())
    assert artifact_receipt == raised.value.ingest_receipt.to_dict()
    assert artifact_receipt["provider_request_count"] == 1
    assert artifact_receipt["canonical_store_update_committed"] is False


def test_no_policy_override_parameters_and_no_direct_transport_imports() -> None:
    import inspect

    signature = inspect.signature(issuer.issue_current_reviewed_fotmob_via_canonical_ingest)
    assert "minimum_lead_seconds" not in signature.parameters
    assert "max_source_age_seconds" not in signature.parameters
    tree = ast.parse(Path(issuer.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            referenced.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert "fetch_fotmob_data_matches" not in imported | referenced
    assert "write_data_matches_capture_directory" not in imported | referenced


def test_downstream_authority_remains_outside_issuer_scope(tmp_path: Path) -> None:
    repository = _repo(tmp_path)
    result = _issue(
        repository,
        lambda *, request_date, timezone, ccode3: _response(request_date),
    )
    compat = result.compatibility_result.receipt
    assert result.ingest_receipt.authorities["provider_acquisition"] is True
    assert result.ingest_receipt.authorities["raw_source_capture"] is True
    assert result.ingest_receipt.authorities["canonical_source_update"] is True
    for field in (
        "fixture_intelligence_fact_authority", "fixture_intelligence_snapshot_authority",
        "model_feature_authority", "probability_authority", "pricing_authority",
        "routing_authority", "portfolio_authority", "share_code_authority",
        "login", "cookies", "wallet", "staking", "wager", "backfill_authority",
    ):
        assert compat[field] is False
    assert compat["provider_request_count_by_adapter"] == 0
    assert result.execution.summary()["wager_placed"] is False
