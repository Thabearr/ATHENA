from __future__ import annotations

import dataclasses
import datetime as dt
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

import scripts.audit_fotmob_fresh_holdout_actions_lineage as lineage_audit
from domain.current_fotmob_latest_durable_fresh_history import (
    DATASET_NAME,
    NEXT_REQUIRED_BOUNDARY,
    REPOSITORY,
    STATUS,
    CurrentLatestDurableFreshHistoryError,
    CurrentLatestDurableFreshHistoryHandoff,
    CurrentLatestDurableFreshHistorySourceBundle,
    VerifiedPr151SuccessReceiptEvidence,
    canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes,
)

UTC = dt.timezone.utc


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


def _selected_receipt(prefix_handoff) -> VerifiedPr151SuccessReceiptEvidence:
    with zipfile.ZipFile(
        Path("/dev/null") if False else __import__("io").BytesIO(
            prefix_handoff.source_bundle.artifact_zip_bytes
        ),
        "r",
    ) as archive:
        receipt = archive.read("fresh-holdout-tick-receipt.json")
    return VerifiedPr151SuccessReceiptEvidence(
        run_id=prefix_handoff.source_bundle.workflow_run_id,
        artifact_name=prefix_handoff.source_bundle.artifact_name,
        actions_artifact_zip_sha256=prefix_handoff.artifact_zip_sha256,
        release_state="RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
        receipt_bytes=receipt,
    )


def _synthetic_success_receipt(
    *,
    run_id: int,
    nominal: dt.datetime,
    committed_at: dt.datetime,
    zip_sha: str,
) -> VerifiedPr151SuccessReceiptEvidence:
    name = f"success-{nominal.strftime('%Y%m%dT%H%M%SZ')}-run-{run_id}.tar.gz"
    receipt = {
        "schema_version": 1,
        "runner_id": "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_ACTIVATION_RUNNER_V1",
        "runner_state": "ACTIVATED_PROSPECTIVE_COLLECTION_RESEARCH_ONLY",
        "scheduled_for_utc": nominal.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "phase": "PREDICTION_AND_SETTLEMENT_COLLECTION",
        "committed_at_utc": committed_at.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "request_dates": [],
        "network_request_count": 0,
        "network_acquisition_performed": False,
        "fresh_holdout_collection_started_by_this_run": True,
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W35",
        "durable_asset_name": name,
        "next_required_boundary": "RUN_PROSPECTIVE_COLLECTION_UNTIL_FROZEN_COUNT_ONLY_CLOSE_RULE_FIRES",
        "safety": {
            "provider_network_acquisition_authorized": False,
            "model_approval_authorized": False,
            "score_matrix_authorized": False,
            "probability_authorized": False,
            "pricing_authorized": False,
            "selection_authorized": False,
            "bet_authorized": False,
        },
        "workflow_run_id": run_id,
        "workflow_event_schedule": "7 * * * *" if nominal.minute == 7 else "37 * * * *",
        "nominal_scheduled_for_utc": nominal.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "durable_asset_sha256": "a" * 64,
        "durable_asset_size_bytes": 1,
        "tick_exit_code": 0,
        "tick_committed": True,
        "failure_lineage_reconcile_outcome": "skipped",
    }
    return VerifiedPr151SuccessReceiptEvidence(
        run_id=run_id,
        artifact_name=name,
        actions_artifact_zip_sha256=zip_sha,
        release_state="RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
        receipt_bytes=_canonical(receipt),
    )


def _audit_bytes(*, expected_main: str, records: list[dict]) -> bytes:
    return _canonical(
        {
            "schema_version": lineage_audit.SCHEMA_VERSION,
            "audit_id": lineage_audit.AUDIT_ID,
            "repository": REPOSITORY,
            "expected_main_sha": expected_main,
            "observed_main_sha": expected_main,
            "runs": records,
            "safety": {key: False for key in lineage_audit.SAFETY_KEYS},
        }
    )


def _success_record(evidence: VerifiedPr151SuccessReceiptEvidence, *, created_at: dt.datetime):
    return {
        "run_id": evidence.run_id,
        "created_at": created_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "conclusion": "success",
        "evidence_state": "VERIFIED_ACTIONS_LINEAGE",
        "archive_name": evidence.artifact_name,
        "actions_artifact_zip_sha256": evidence.actions_artifact_zip_sha256,
        "release_state": evidence.release_state,
    }


def _bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed_at: dt.datetime | None = None,
    extra_receipts: tuple[VerifiedPr151SuccessReceiptEvidence, ...] = (),
    extra_records: tuple[dict, ...] = (),
):
    helpers = _load_prefix_helpers()
    if observed_at is not None:
        monkeypatch.setattr(helpers, "SOURCE_OBSERVED", observed_at)
        monkeypatch.setattr(
            helpers,
            "SOURCE_ISSUED",
            observed_at + dt.timedelta(minutes=5),
        )
    lower, *_rest = helpers._handoff(tmp_path, monkeypatch)
    selected = _selected_receipt(lower)
    records = [
        _success_record(
            selected,
            created_at=selected.nominal_scheduled_for_utc + dt.timedelta(minutes=1),
        ),
        *extra_records,
    ]
    receipts = (selected, *extra_receipts)
    audit_raw = _audit_bytes(expected_main="b" * 40, records=records)
    source = CurrentLatestDurableFreshHistorySourceBundle(
        audit_result_bytes=audit_raw,
        success_receipts=receipts,
        selected_prefix=lower,
    )
    return source, lower, selected


def test_complete_current_history_wraps_latest_applicable_prefix_without_model_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, lower, _selected = _bundle(tmp_path, monkeypatch)
    handoff = CurrentLatestDurableFreshHistoryHandoff(
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
    assert handoff.selected_prefix == lower
    assert handoff.current_fresh_history_prefix_complete is True
    assert handoff.latest_applicable_success_selection_proven is True
    assert not any(handoff.authority.values())
    payload = handoff.to_dict()
    assert payload["current_fresh_history_prefix_complete"] is True
    assert payload["authority"]["phase6"] is False
    assert payload["authority"]["sportybet_execution"] is False
    assert payload["wager_placed"] is False
    raw = canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(handoff)
    assert lower.source_bundle.artifact_zip_bytes not in raw
    assert lower.source_bundle.source_raw_json not in raw


def test_future_success_commit_does_not_displace_as_of_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_time = dt.datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
    future = _synthetic_success_receipt(
        run_id=99999,
        nominal=dt.datetime(2026, 8, 27, 7, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 7, 10, tzinfo=UTC),
        zip_sha="c" * 64,
    )
    source, lower, _selected = _bundle(
        tmp_path,
        monkeypatch,
        observed_at=source_time,
        extra_receipts=(future,),
        extra_records=(
            _success_record(
                future,
                created_at=dt.datetime(2026, 8, 27, 7, 8, tzinfo=UTC),
            ),
        ),
    )
    assert source.selected_prefix == lower


def test_stale_selected_prefix_is_rejected_when_newer_success_was_already_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_time = dt.datetime(2026, 8, 27, 7, 30, tzinfo=UTC)
    newer = _synthetic_success_receipt(
        run_id=99998,
        nominal=dt.datetime(2026, 8, 27, 7, 7, tzinfo=UTC),
        committed_at=dt.datetime(2026, 8, 27, 7, 10, tzinfo=UTC),
        zip_sha="d" * 64,
    )
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match="not latest applicable success run",
    ):
        _bundle(
            tmp_path,
            monkeypatch,
            observed_at=source_time,
            extra_receipts=(newer,),
            extra_records=(
                _success_record(
                    newer,
                    created_at=dt.datetime(2026, 8, 27, 7, 8, tzinfo=UTC),
                ),
            ),
        )


def test_unverified_completed_run_before_source_observation_blocks_current_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unverified = {
        "run_id": 88888,
        "created_at": "2026-08-27T06:50:00Z",
        "conclusion": "failure",
        "evidence_state": "UNVERIFIED",
        "archive_name": None,
        "actions_artifact_zip_sha256": None,
        "release_state": "NOT_CHECKED",
    }
    with pytest.raises(
        CurrentLatestDurableFreshHistoryError,
        match="unverified completed PR151 run",
    ):
        _bundle(
            tmp_path,
            monkeypatch,
            extra_records=(unverified,),
        )


def test_complete_current_history_authority_cannot_be_switched_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _lower, _selected = _bundle(tmp_path, monkeypatch)
    handoff = CurrentLatestDurableFreshHistoryHandoff(
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
    changed = dict(handoff.authority)
    changed["phase6"] = True
    with pytest.raises(CurrentLatestDurableFreshHistoryError, match="authority"):
        dataclasses.replace(handoff, authority=changed)


def test_production_source_is_fixed_to_athena_and_private_reader_helper_is_not_exported() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = (
        repository / "domain/current_fotmob_latest_durable_fresh_history.py"
    ).read_text(encoding="utf-8")
    assert 'REPOSITORY = "Thabearr/ATHENA"' in source
    assert "fotmob-utc-native-xg-fresh-holdout.yml/runs" in source
    namespace: dict[str, object] = {}
    exec(compile(source, "latest-history-source", "exec"), namespace)
    assert "_build_with_readers" not in namespace["__all__"]
