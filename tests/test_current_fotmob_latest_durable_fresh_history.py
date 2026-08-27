from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

import domain.current_fotmob_latest_durable_fresh_history as latest
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import scripts.audit_fotmob_fresh_holdout_actions_lineage as lineage_audit
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
from domain.current_fotmob_latest_durable_fresh_history import (
    DATASET_NAME,
    NEXT_REQUIRED_BOUNDARY,
    REPOSITORY,
    STATUS,
    CurrentLatestDurableFreshHistoryError,
    CurrentLatestDurableFreshHistoryHandoff,
    CurrentLatestDurableFreshHistorySourceBundle,
    GitHubActionsLineageEvidenceBundle,
    VerifiedPr151SuccessReceiptEvidence,
    canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes,
)

UTC = dt.timezone.utc
EXPECTED_MAIN = "b" * 40


def _load_prefix_helpers():
    path = Path(__file__).with_name(
        "test_current_fotmob_durable_fresh_history_prefix.py"
    )
    spec = importlib.util.spec_from_file_location("_athena_pr245_prefix_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _synthetic_success_artifact(
    *,
    artifact_id: int,
    run_id: int,
    nominal: dt.datetime,
    committed_at: dt.datetime,
    release_state: str = "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
) -> tuple[dict, bytes, dict]:
    name = f"success-{nominal.strftime('%Y%m%dT%H%M%SZ')}-run-{run_id}.tar.gz"
    archive_bytes = f"synthetic-pr151-state:{run_id}".encode("utf-8")
    receipt = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "runner_state": runner.RUNNER_STATE,
        "scheduled_for_utc": _utc_text(nominal),
        "phase": control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "fresh_holdout_collection_started_by_this_run": True,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W35",
        "durable_asset_name": name,
        "next_required_boundary": runner.NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in runner.SAFETY_KEYS},
        "workflow_run_id": run_id,
        "workflow_event_schedule": (
            "7 * * * *" if nominal.minute == 7 else "37 * * * *"
        ),
        "nominal_scheduled_for_utc": _utc_text(nominal),
        "durable_asset_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "durable_asset_size_bytes": len(archive_bytes),
        "tick_exit_code": 0,
        "tick_committed": True,
        "failure_lineage_reconcile_outcome": "skipped",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(name, archive_bytes)
        bundle.writestr("fresh-holdout-tick-receipt.json", _canonical(receipt))
    zip_bytes = buffer.getvalue()
    artifact = {
        "id": artifact_id,
        "name": name,
        "expired": False,
        "digest": f"sha256:{hashlib.sha256(zip_bytes).hexdigest()}",
    }
    run = {
        "id": run_id,
        "created_at": _utc_text(nominal + dt.timedelta(minutes=1)),
        "status": "completed",
        "conclusion": "success",
        "test_evidence_state": "VERIFIED_ACTIONS_LINEAGE",
        "test_release_state": release_state,
    }
    return artifact, zip_bytes, run


def _selected_run_material(
    lower,
    *,
    artifact_id: int = 7001,
    release_state: str = "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
):
    artifact = {
        "id": artifact_id,
        "name": lower.source_bundle.artifact_name,
        "expired": False,
        "digest": lower.source_bundle.artifact_zip_metadata_digest,
    }
    run = {
        "id": lower.source_bundle.workflow_run_id,
        "created_at": _utc_text(lower.nominal_scheduled_for_utc + dt.timedelta(minutes=1)),
        "status": "completed",
        "conclusion": "success",
        "test_evidence_state": "VERIFIED_ACTIONS_LINEAGE",
        "test_release_state": release_state,
    }
    return artifact, lower.source_bundle.artifact_zip_bytes, run


def _unverified_run(*, run_id: int, created_at: dt.datetime) -> dict:
    return {
        "id": run_id,
        "created_at": _utc_text(created_at),
        "status": "completed",
        "conclusion": "failure",
        "test_evidence_state": "UNVERIFIED",
        "test_release_state": "NOT_CHECKED",
    }


def _fake_projected_audit(
    *,
    expected_main_sha,
    get_main_ref,
    get_runs_page,
    get_run_artifacts,
    download_artifact_zip,
    get_release,
    download_release_asset,
    get_run_jobs,
    repository_root=None,
):
    del get_release, download_release_asset, get_run_jobs, repository_root
    main = get_main_ref()
    observed = (
        main.get("object", {}).get("sha")
        if type(main.get("object")) is dict
        else main.get("sha")
    )
    assert observed == expected_main_sha
    page = get_runs_page(1, 100)
    runs = page["workflow_runs"]
    records: list[dict] = []
    for run in runs:
        state = run["test_evidence_state"]
        if state == "VERIFIED_ACTIONS_LINEAGE":
            artifact = lineage_audit._candidate_artifact(
                get_run_artifacts(run["id"]), run["id"]
            )
            zip_bytes = download_artifact_zip(artifact["id"])
            zip_sha = mirror.verify_actions_artifact_zip_digest(
                zip_bytes, artifact["digest"]
            )
            mirror.verify_actions_artifact_bundle(
                run_id=run["id"],
                artifact_name=artifact["name"],
                zip_bytes=zip_bytes,
            )
            records.append(
                {
                    "run_id": run["id"],
                    "created_at": run["created_at"],
                    "conclusion": run["conclusion"],
                    "evidence_state": state,
                    "archive_name": artifact["name"],
                    "actions_artifact_zip_sha256": zip_sha,
                    "release_state": run["test_release_state"],
                }
            )
        else:
            records.append(
                {
                    "run_id": run["id"],
                    "created_at": run["created_at"],
                    "conclusion": run["conclusion"],
                    "evidence_state": state,
                    "archive_name": None,
                    "actions_artifact_zip_sha256": None,
                    "release_state": run["test_release_state"],
                }
            )
    return {
        "schema_version": lineage_audit.SCHEMA_VERSION,
        "audit_id": lineage_audit.AUDIT_ID,
        "repository": REPOSITORY,
        "expected_main_sha": expected_main_sha,
        "observed_main_sha": observed,
        "runs": records,
        "safety": {key: False for key in lineage_audit.SAFETY_KEYS},
    }


def _wrapped_fake_projected_audit(**kwargs):
    """Mirror production's projected-audit error normalization in deterministic tests."""
    try:
        return _fake_projected_audit(**kwargs)
    except CurrentLatestDurableFreshHistoryError:
        raise
    except Exception as exc:
        raise CurrentLatestDurableFreshHistoryError(
            "reviewed projected PR151 Actions lineage audit failed"
        ) from exc


def _readers(*, runs: list[dict], artifacts: dict[int, dict], zips: dict[int, bytes]):
    return {
        "get_main_ref": lambda: {"sha": EXPECTED_MAIN},
        "get_runs_page": lambda page, per_page: (
            {"workflow_runs": list(runs)}
            if (page, per_page) == (1, 100)
            else {"workflow_runs": []}
        ),
        "get_run_artifacts": lambda run_id: {"artifacts": [artifacts[run_id]]},
        "download_artifact_zip": lambda artifact_id: zips[artifact_id],
        "get_release": lambda _tag: {},
        "download_release_asset": lambda _asset_id: b"unused",
        "get_run_jobs": lambda _run_id: {"jobs": []},
    }


def _lower(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed_at: dt.datetime | None = None,
):
    helpers = _load_prefix_helpers()
    if observed_at is not None:
        monkeypatch.setattr(helpers, "SOURCE_OBSERVED", observed_at)
        monkeypatch.setattr(
            helpers,
            "SOURCE_ISSUED",
            observed_at + dt.timedelta(minutes=5),
        )
    return helpers._handoff(tmp_path, monkeypatch)


def _github_evidence(
    monkeypatch: pytest.MonkeyPatch,
    *,
    runs: list[dict],
    artifacts: dict[int, dict],
    zips: dict[int, bytes],
) -> GitHubActionsLineageEvidenceBundle:
    monkeypatch.setattr(
        latest,
        "_run_reviewed_projected_audit",
        _wrapped_fake_projected_audit,
    )
    readers = _readers(runs=runs, artifacts=artifacts, zips=zips)
    recorder = latest._ReadRecorder()
    audit = latest._run_reviewed_projected_audit(
        expected_main_sha=EXPECTED_MAIN,
        get_main_ref=lambda: recorder.json("main_ref", readers["get_main_ref"]),
        get_runs_page=lambda page, per_page: recorder.json(
            f"runs:{page}:{per_page}",
            lambda: readers["get_runs_page"](page, per_page),
        ),
        get_run_artifacts=lambda run_id: recorder.json(
            f"artifacts:{run_id}",
            lambda: readers["get_run_artifacts"](run_id),
        ),
        download_artifact_zip=lambda artifact_id: recorder.binary(
            f"artifact_zip:{artifact_id}",
            lambda: readers["download_artifact_zip"](artifact_id),
        ),
        get_release=lambda tag: recorder.json(
            f"release:{tag}", lambda: readers["get_release"](tag)
        ),
        download_release_asset=lambda asset_id: recorder.binary(
            f"release_asset:{asset_id}",
            lambda: readers["download_release_asset"](asset_id),
        ),
        get_run_jobs=lambda run_id: recorder.json(
            f"jobs:{run_id}", lambda: readers["get_run_jobs"](run_id)
        ),
    )
    return GitHubActionsLineageEvidenceBundle(
        expected_main_sha=EXPECTED_MAIN,
        reads=recorder.freeze(),
        audit_result_bytes=_canonical(audit),
    )


def _source_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed_at: dt.datetime | None = None,
    extra_materials: tuple[tuple[dict, bytes, dict], ...] = (),
    selected_release_state: str = "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
    extra_runs: tuple[dict, ...] = (),
):
    lower, *_rest = _lower(tmp_path, monkeypatch, observed_at=observed_at)
    selected_artifact, selected_zip, selected_run = _selected_run_material(
        lower, release_state=selected_release_state
    )
    runs = [selected_run]
    artifacts = {selected_run["id"]: selected_artifact}
    zips = {selected_artifact["id"]: selected_zip}
    for artifact, zip_bytes, run in extra_materials:
        runs.append(run)
        artifacts[run["id"]] = artifact
        zips[artifact["id"]] = zip_bytes
    runs.extend(extra_runs)
    evidence = _github_evidence(
        monkeypatch,
        runs=runs,
        artifacts=artifacts,
        zips=zips,
    )
    return (
        CurrentLatestDurableFreshHistorySourceBundle(
            github_evidence=evidence,
            selected_prefix=lower,
        ),
        lower,
        evidence,
    )


def _handoff(source: CurrentLatestDurableFreshHistorySourceBundle):
    return CurrentLatestDurableFreshHistoryHandoff(
        schema_version=1,
        dataset_name=DATASET_NAME,
        status=STATUS,
        source_bundle=source,
        latest_applicable_success_selection_proven=True,
        current_fresh_history_prefix_complete=True,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        evidence={
            "full_reviewed_actions_lineage_audited": True,
            "latest_applicable_success_selection_proven": True,
            "complete_current_fresh_history_prefix": True,
            "complete_current_history_shadow_replay": True,
        },
        authority={
            "production_model": False,
            "score_matrix": False,
            "probability": False,
            "phase6": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "bet": False,
        },
    )


def test_complete_current_history_is_replay_bound_without_model_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, lower, evidence = _source_bundle(tmp_path, monkeypatch)
    handoff = _handoff(source)
    assert handoff.selected_prefix == lower
    assert handoff.current_fresh_history_prefix_complete is True
    assert not any(handoff.authority.values())
    payload = handoff.to_dict()
    assert payload["github_inventory_snapshot_sha256"] == evidence.inventory_sha256
    assert payload["authority"]["phase6"] is False
    assert payload["authority"]["sportybet_execution"] is False
    assert payload["wager_placed"] is False
    raw = canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(handoff)
    assert lower.source_bundle.artifact_zip_bytes not in raw
    assert lower.source_bundle.source_raw_json not in raw
    assert evidence.reads[0].payload not in raw


def test_detached_audit_result_relabeling_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, _lower_value, evidence = _source_bundle(tmp_path, monkeypatch)
    altered = evidence.audit_result
    altered["runs"] = []
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match="do not reproduce the exact lineage audit",
    ):
        dataclasses.replace(evidence, audit_result_bytes=_canonical(altered))


def test_run_inventory_snapshot_tampering_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, _lower_value, evidence = _source_bundle(tmp_path, monkeypatch)
    changed = []
    for item in evidence.reads:
        if item.key == "runs:1:100":
            payload = json.loads(item.payload)
            payload["workflow_runs"] = []
            item = dataclasses.replace(item, payload=_canonical(payload))
        changed.append(item)
    with pytest.raises(CurrentLatestDurableFreshHistoryError):
        dataclasses.replace(evidence, reads=tuple(changed))


def test_artifact_zip_tampering_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, _lower_value, evidence = _source_bundle(tmp_path, monkeypatch)
    changed = []
    for item in evidence.reads:
        if item.key.startswith("artifact_zip:"):
            item = dataclasses.replace(item, payload=item.payload + b"tamper")
        changed.append(item)
    with pytest.raises(CurrentLatestDurableFreshHistoryError):
        dataclasses.replace(evidence, reads=tuple(changed))


@pytest.mark.parametrize("field", ["runner_state", "safety"])
def test_success_receipt_requires_exact_pr151_runner_contract(field: str) -> None:
    artifact, zip_bytes, _run = _synthetic_success_artifact(
        artifact_id=9001,
        run_id=90001,
        nominal=dt.datetime(2026, 8, 27, 6, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 6, 10, tzinfo=UTC),
    )
    verified = mirror.verify_actions_artifact_bundle(
        run_id=90001,
        artifact_name=artifact["name"],
        zip_bytes=zip_bytes,
    )
    receipt = json.loads(verified["receipt_bytes"])
    if field == "runner_state":
        receipt[field] = "RELABELLED"
    else:
        receipt[field][next(iter(receipt[field]))] = True
    with pytest.raises(CurrentLatestDurableFreshHistoryError, match="exact PR151"):
        VerifiedPr151SuccessReceiptEvidence(
            run_id=90001,
            artifact_name=artifact["name"],
            actions_artifact_zip_sha256=hashlib.sha256(zip_bytes).hexdigest(),
            release_state="RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
            receipt_bytes=_canonical(receipt),
        )


def test_future_success_commit_does_not_displace_as_of_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    future = _synthetic_success_artifact(
        artifact_id=9002,
        run_id=90002,
        nominal=dt.datetime(2026, 8, 27, 7, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 7, 10, tzinfo=UTC),
    )
    source, lower, _evidence_value = _source_bundle(
        tmp_path,
        monkeypatch,
        observed_at=dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC),
        extra_materials=(future,),
    )
    assert source.selected_prefix == lower


def test_stale_selected_prefix_is_rejected_when_newer_success_already_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newer = _synthetic_success_artifact(
        artifact_id=9003,
        run_id=90003,
        nominal=dt.datetime(2026, 8, 27, 7, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 7, 10, tzinfo=UTC),
    )
    lower, *_rest = _lower(
        tmp_path,
        monkeypatch,
        observed_at=dt.datetime(2026, 8, 27, 7, 30, tzinfo=UTC),
    )
    selected_artifact, selected_zip, selected_run = _selected_run_material(lower)
    extra_artifact, extra_zip, extra_run = newer
    evidence = _github_evidence(
        monkeypatch,
        runs=[selected_run, extra_run],
        artifacts={
            selected_run["id"]: selected_artifact,
            extra_run["id"]: extra_artifact,
        },
        zips={selected_artifact["id"]: selected_zip, extra_artifact["id"]: extra_zip},
    )
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match="not latest applicable success run",
    ):
        CurrentLatestDurableFreshHistorySourceBundle(
            github_evidence=evidence,
            selected_prefix=lower,
        )


def test_unverified_completed_run_before_source_observation_blocks_current_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match="unverified completed PR151 run",
    ):
        _source_bundle(
            tmp_path,
            monkeypatch,
            extra_runs=(
                _unverified_run(
                    run_id=88888,
                    created_at=dt.datetime(2026, 8, 27, 6, 50, tzinfo=UTC),
                ),
            ),
        )


def test_partial_durability_on_older_success_does_not_block_fully_durable_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = _synthetic_success_artifact(
        artifact_id=9004,
        run_id=90004,
        nominal=dt.datetime(2026, 8, 27, 6, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 6, 10, tzinfo=UTC),
        release_state="RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING",
    )
    source, lower, _evidence_value = _source_bundle(
        tmp_path,
        monkeypatch,
        extra_materials=(older,),
    )
    assert source.selected_prefix == lower


def test_partial_durability_on_selected_latest_success_blocks_current_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match=r"lacks long-lived archive\+receipt durability",
    ):
        _source_bundle(
            tmp_path,
            monkeypatch,
            selected_release_state="RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING",
        )


def test_complete_current_history_authority_cannot_be_switched_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _lower_value, _evidence_value = _source_bundle(tmp_path, monkeypatch)
    handoff = _handoff(source)
    changed = dict(handoff.authority)
    changed["phase6"] = True
    with pytest.raises(CurrentLatestDurableFreshHistoryError, match="authority"):
        dataclasses.replace(handoff, authority=changed)


def test_current_projected_audit_dependency_chain_is_reviewed() -> None:
    latest._verify_current_projected_audit_dependencies()


def test_production_source_is_fixed_and_private_reader_helper_is_not_exported() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = (
        repository / "domain/current_fotmob_latest_durable_fresh_history.py"
    ).read_text(encoding="utf-8")
    assert 'REPOSITORY = "Thabearr/ATHENA"' in source
    assert "fotmob-utc-native-xg-fresh-holdout.yml/runs" in source
    namespace: dict[str, object] = {}
    exec(compile(source, "latest-history-source", "exec"), namespace)
    assert "_build_with_readers" not in namespace["__all__"]
    assert "GitHubReadSnapshot" not in namespace["__all__"]
