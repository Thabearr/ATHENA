"""Replay one terminal PR151 durable state into the frozen PR167 evaluator.

This boundary is deliberately offline. It verifies exact durable archive/receipt
bytes already emitted by the reviewed scheduled runner, reconstructs its append-only
state, re-proves the result-free close decision, and only then invokes PR167.

The source scope here is the PR151 durable state artifact itself. This module does
not claim to re-download or re-derive every historical FotMob raw capture. It performs
no provider acquisition, model/calibration fitting, pricing, selection, or BET action.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_confirmation_evaluator as evaluator


SCHEMA_VERSION = 1
REPLAY_ID = "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_CONFIRMATION_SOURCE_REPLAY_V1"
REPLAY_STATE = "IMPLEMENTED_OFFLINE_PR151_DURABLE_STATE_REPLAY_NOT_PRODUCTION_APPROVED"
SOURCE_SCOPE = "PR151_DURABLE_STATE_ARCHIVE_AND_CANONICAL_TICK_RECEIPT"
NEXT_REQUIRED_BOUNDARY = "REVIEW_SOURCE_REPLAYED_FRESH_HOLDOUT_CONFIRMATION_RESULT"

PR151_RUNNER_BLOB_SHA = "901ab137d6601a3485eac30da7e6bad7eeefa397"
PR167_EVALUATOR_BLOB_SHA = "1f07292e66254ece0de25dc70e10964502a3839a"

ARTIFACT_RE = re.compile(r"^success-(\d{8}T\d{6}Z)-run-(\d+)\.tar\.gz$")
RELEASE_TAG_RE = re.compile(r"^athena-fresh-holdout-evidence-\d{4}-W\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "runner_id",
        "runner_state",
        "scheduled_for_utc",
        "phase",
        "committed_at_utc",
        "request_dates",
        "network_request_count",
        "network_acquisition_performed",
        "fresh_holdout_collection_started_by_this_run",
        "durable_release_tag",
        "durable_asset_name",
        "next_required_boundary",
        "safety",
        "workflow_run_id",
        "workflow_event_schedule",
        "nominal_scheduled_for_utc",
        "durable_asset_sha256",
        "durable_asset_size_bytes",
        "tick_exit_code",
        "tick_committed",
        "failure_lineage_reconcile_outcome",
    }
)


class FreshHoldoutConfirmationSourceReplayError(RuntimeError):
    """Raised when durable-state source replay cannot be proven exactly."""


def _error(message: str) -> FreshHoldoutConfirmationSourceReplayError:
    return FreshHoldoutConfirmationSourceReplayError(message)


def _canonical(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical JSON serialization failed") from exc


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _error(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_object(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error(f"{label} must be non-empty exact bytes")
    try:
        value = json.loads(raw, object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is malformed JSON") from exc
    if type(value) is not dict or _canonical(value) != raw:
        raise _error(f"{label} must be canonical compact sorted-key JSON")
    return value


def _sha256_text(value: Any, label: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise _error(f"{label} must be lowercase SHA-256")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise _error(f"{label} must be an exact positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise _error(f"{label} must be an exact non-negative integer")
    return value


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _scheduled_utc(value: Any, label: str) -> dt.datetime:
    parsed = _utc(value, label)
    if (
        parsed.second
        or parsed.microsecond
        or parsed.minute not in control.CAPTURE_MINUTES_UTC
    ):
        raise _error(f"{label} escaped reviewed :07/:37 schedule lattice")
    return parsed


def _utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies() -> None:
    """Re-prove the frozen collection and evaluation implementations."""
    try:
        if _blob(Path(runner.__file__)) != PR151_RUNNER_BLOB_SHA:
            raise _error("PR151 activation runner implementation blob changed")
        if _blob(Path(evaluator.__file__)) != PR167_EVALUATOR_BLOB_SHA:
            raise _error("PR167 confirmation evaluator implementation blob changed")
    except OSError as exc:
        raise _error("could not inspect reviewed dependency blobs") from exc
    runner.verify_reviewed_activation_dependencies()
    evaluator.verify_reviewed_dependencies()
    receipt = evaluator.implementation_receipt()
    if any(receipt["safety"].values()):
        raise _error("frozen evaluator downstream authority changed")


def _read_exact_regular(path: Path, label: str) -> bytes:
    value = Path(path)
    if value.is_symlink() or not value.is_file():
        raise _error(f"{label} must be a regular non-symlink file")
    raw = value.read_bytes()
    if not raw:
        raise _error(f"{label} must be non-empty")
    return raw


def _require_exact_runner_receipt(
    receipt: Mapping[str, Any],
    *,
    archive_name: str,
    compact: str,
    run_id: int,
) -> dt.datetime:
    if set(receipt) != TERMINAL_RECEIPT_KEYS:
        raise _error("tick receipt key set changed from exact terminal workflow schema")
    if receipt.get("schema_version") != 1:
        raise _error("tick receipt schema version changed")
    if receipt.get("runner_id") != runner.RUNNER_ID:
        raise _error("tick receipt runner_id changed")
    if receipt.get("runner_state") != runner.RUNNER_STATE:
        raise _error("tick receipt runner_state changed")
    if receipt.get("phase") != control.ControlPhase.COLLECTION_COMPLETE.value:
        raise _error("terminal tick receipt must prove COLLECTION_COMPLETE")

    nominal = _scheduled_utc(
        receipt.get("nominal_scheduled_for_utc"), "nominal scheduled time"
    )
    scheduled = _scheduled_utc(receipt.get("scheduled_for_utc"), "runner scheduled time")
    if nominal != scheduled:
        raise _error("receipt nominal slot disagrees with runner scheduled slot")
    if nominal.strftime("%Y%m%dT%H%M%SZ") != compact:
        raise _error("success archive nominal slot disagrees with tick receipt")
    receipt_committed_at = _utc(receipt.get("committed_at_utc"), "receipt committed_at")
    if receipt_committed_at < nominal:
        raise _error("receipt committed_at predates nominal scheduled slot")

    schedule_expr = receipt.get("workflow_event_schedule")
    expected_expr = "7 * * * *" if nominal.minute == 7 else "37 * * * *"
    if schedule_expr != expected_expr:
        raise _error("workflow cron identity disagrees with nominal slot")
    if receipt.get("workflow_run_id") != run_id:
        raise _error("tick receipt workflow_run_id changed")

    if receipt.get("durable_asset_name") != archive_name:
        raise _error("tick receipt durable asset name changed")
    release_tag = receipt.get("durable_release_tag")
    if type(release_tag) is not str or RELEASE_TAG_RE.fullmatch(release_tag) is None:
        raise _error("tick receipt durable release tag is invalid")
    if receipt.get("request_dates") != []:
        raise _error("COLLECTION_COMPLETE receipt unexpectedly carries request dates")

    if _non_negative_int(receipt.get("network_request_count"), "network request count") != 0:
        raise _error("COLLECTION_COMPLETE receipt unexpectedly records network requests")
    if receipt.get("network_acquisition_performed") is not False:
        raise _error("COLLECTION_COMPLETE receipt unexpectedly records provider acquisition")
    if receipt.get("fresh_holdout_collection_started_by_this_run") is not False:
        raise _error("terminal receipt unexpectedly claims fresh collection started this run")
    if receipt.get("next_required_boundary") != runner.NEXT_REQUIRED_BOUNDARY:
        raise _error("tick receipt next boundary changed")
    if receipt.get("failure_lineage_reconcile_outcome") != "skipped":
        raise _error("successful terminal receipt changed failure-lineage reconcile outcome")

    safety = receipt.get("safety")
    if type(safety) is not dict or set(safety) != set(runner.SAFETY_KEYS):
        raise _error("tick receipt safety vocabulary changed")
    if any(value is not False for value in safety.values()):
        raise _error("tick receipt changed downstream safety authority")

    if receipt.get("tick_exit_code") != 0 or receipt.get("tick_committed") is not True:
        raise _error("terminal replay requires a committed zero-exit success tick")
    return nominal


def _verify_final_receipt(
    *, archive_path: Path, receipt_path: Path
) -> tuple[dict[str, Any], bytes, bytes]:
    archive_raw = _read_exact_regular(archive_path, "durable archive")
    receipt_raw = _read_exact_regular(receipt_path, "tick receipt")
    receipt = _canonical_object(receipt_raw, "tick receipt")

    archive_name = Path(archive_path).name
    match = ARTIFACT_RE.fullmatch(archive_name)
    if match is None:
        raise _error("terminal replay requires a canonical success archive name")
    compact, run_text = match.groups()
    run_id = _positive_int(receipt.get("workflow_run_id"), "workflow_run_id")
    if int(run_text) != run_id:
        raise _error("success archive run id disagrees with tick receipt")
    _require_exact_runner_receipt(
        receipt,
        archive_name=archive_name,
        compact=compact,
        run_id=run_id,
    )

    expected_sha = _sha256_text(
        receipt.get("durable_asset_sha256"), "durable archive digest"
    )
    expected_size = _positive_int(
        receipt.get("durable_asset_size_bytes"), "durable archive size"
    )
    if hashlib.sha256(archive_raw).hexdigest() != expected_sha:
        raise _error("durable archive bytes disagree with tick receipt SHA-256")
    if len(archive_raw) != expected_size:
        raise _error("durable archive bytes disagree with tick receipt size")
    return receipt, archive_raw, receipt_raw


def _state_paths(root: Path) -> dict[str, Path]:
    return {
        "capture": root / control.CAPTURE_INDEX_FILENAME,
        "prediction": root / control.PREDICTION_JOURNAL_FILENAME,
        "identity": root / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
        "settlement": root / control.SETTLEMENT_JOURNAL_FILENAME,
        "control": root / control.CONTROL_JOURNAL_FILENAME,
        "checkpoint": root / control.CHECKPOINT_FILENAME,
    }


def _rows(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        return runner._rows(path)
    except Exception as exc:
        raise _error(f"{path.name} failed canonical journal replay") from exc


def _prediction_assessments(
    prediction_rows: Sequence[dict[str, Any]],
) -> tuple[fresh.FreshPredictionAssessment, ...]:
    try:
        sealed, processed = runner._prediction_state(prediction_rows)
    except Exception as exc:
        raise _error("prediction journal failed reviewed PR151 replay") from exc
    if len(processed) != len(prediction_rows):
        raise _error("prediction journal processed population changed")

    assessments: list[fresh.FreshPredictionAssessment] = []
    for row in prediction_rows:
        if row.get("schema_version") != 1:
            raise _error("prediction journal schema version changed")
        fixture_id = row.get("fixture_id")
        if type(fixture_id) is not int or fixture_id < 1:
            raise _error("prediction journal fixture id is invalid")
        missing = row.get("missing_feature_ids")
        if type(missing) is not list or any(type(value) is not str for value in missing):
            raise _error("prediction journal missing_feature_ids changed shape")
        disposition = row.get("disposition")
        try:
            if disposition == fresh.PredictionDisposition.SEALED_COMPLETE_CASE.value:
                prediction = sealed.get(fixture_id)
                if prediction is None:
                    raise _error("sealed prediction disappeared during replay")
                if row.get("selected_fixture") is not None or missing:
                    raise _error("sealed prediction row carries contradictory missing evidence")
                assessment = fresh.FreshPredictionAssessment(
                    disposition=fresh.PredictionDisposition.SEALED_COMPLETE_CASE,
                    fixture=prediction.fixture,
                    missing_feature_ids=(),
                    sealed_prediction=prediction,
                )
            elif disposition == fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES.value:
                if row.get("prediction") is not None or row.get("prediction_sha256") is not None:
                    raise _error("missing-feature row carries a sealed prediction")
                fixture = runner._fixture(row.get("selected_fixture"))
                if fixture.fixture_id != fixture_id:
                    raise _error("missing-feature fixture identity changed")
                assessment = fresh.FreshPredictionAssessment(
                    disposition=fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES,
                    fixture=fixture,
                    missing_feature_ids=tuple(missing),
                    sealed_prediction=None,
                )
            else:
                raise _error("prediction disposition escaped reviewed vocabulary")
        except FreshHoldoutConfirmationSourceReplayError:
            raise
        except Exception as exc:
            raise _error("prediction assessment reconstruction failed") from exc
        assessments.append(assessment)
    assessments.sort(key=lambda value: (value.fixture.kickoff_utc, value.fixture.fixture_id))
    return tuple(assessments)


def _terminal_records(
    settlement_rows: Sequence[dict[str, Any]],
) -> tuple[evaluator.TerminalSettlementRecord, ...]:
    try:
        _settled, terminal_ids = runner._settlement_state(settlement_rows)
    except Exception as exc:
        raise _error("settlement journal failed reviewed PR151 replay") from exc
    if len(terminal_ids) != len(settlement_rows):
        raise _error("settlement terminal population changed")

    records: list[evaluator.TerminalSettlementRecord] = []
    for row in settlement_rows:
        if row.get("schema_version") != 1:
            raise _error("settlement journal schema version changed")
        fixture_id = row.get("fixture_id")
        if type(fixture_id) is not int or fixture_id < 1:
            raise _error("settlement journal fixture id is invalid")
        try:
            disposition = evaluator.TerminalDisposition(row.get("disposition"))
        except (TypeError, ValueError) as exc:
            raise _error("settlement disposition escaped evaluator terminal vocabulary") from exc
        settled_prediction = None
        if disposition is evaluator.TerminalDisposition.SETTLED_REVIEWED_ORDINARY_FT:
            try:
                settled_prediction = runner._settled(row.get("settled_prediction"))
            except Exception as exc:
                raise _error("settled prediction reconstruction failed") from exc
        elif row.get("settled_prediction") is not None:
            raise _error("excluded/unresolved terminal row carries settlement payload")
        records.append(
            evaluator.TerminalSettlementRecord(
                fixture_id=fixture_id,
                disposition=disposition,
                settled_prediction=settled_prediction,
            )
        )
    records.sort(key=lambda value: value.fixture_id)
    return tuple(records)


def _selected_close(
    control_rows: Sequence[dict[str, Any]],
    sealed: Sequence[fresh.SealedFreshPrediction],
) -> dt.datetime:
    close_rows: list[tuple[int, dt.datetime, dict[str, Any]]] = []
    for index, row in enumerate(control_rows):
        if row.get("event") != "COUNT_ONLY_CLOSE_EVALUATION":
            continue
        boundary = _utc(row.get("evaluated_boundary_utc"), "close evaluation boundary")
        if boundary.time() != dt.time.min:
            raise _error("stored close evaluation escaped exact UTC midnight")
        if close_rows and boundary <= close_rows[-1][1]:
            raise _error("count-only close journal is duplicated or out of order")
        close_rows.append((index, boundary, row))
    selected = [item for item in close_rows if item[2].get("selected_close_utc") is not None]
    if len(selected) != 1:
        raise _error("terminal state must contain exactly one selected count-only close")
    selected_index, selected_close, selected_row = selected[0]
    if close_rows[-1][0] != selected_index:
        raise _error("count-only close evaluation exists after selected close")
    if selected_row.get("outcome_or_performance_input_used") is not False:
        raise _error("stored selected close does not prove outcome-independent decision")
    stored_selected = _utc(selected_row.get("selected_close_utc"), "selected close")
    if stored_selected != selected_close:
        raise _error("stored selected close differs from evaluated boundary")
    try:
        revalidated = control.evaluate_close_control_state(tuple(sealed), boundary=selected_close)
    except Exception as exc:
        raise _error("stored selected close failed frozen count-only replay") from exc
    expected = {
        "evaluated_boundary_utc": selected_row.get("evaluated_boundary_utc"),
        "decision": selected_row.get("decision"),
        "selected_close_utc": selected_row.get("selected_close_utc"),
        "coverage_sha256": selected_row.get("coverage_sha256"),
    }
    if revalidated.to_dict() != expected:
        raise _error("stored selected close disagrees with frozen count-only replay")
    return selected_close


def _final_commit(
    control_rows: Sequence[dict[str, Any]],
    *,
    selected_close: dt.datetime,
    receipt: Mapping[str, Any],
) -> tuple[dt.datetime, dt.datetime]:
    previous: dt.datetime | None = None
    commits: list[tuple[int, dt.datetime, dt.datetime, dict[str, Any]]] = []
    for index, row in enumerate(control_rows):
        event = row.get("event")
        if event == "SCHEDULER_GAP_RANGE" and row.get("backfill_authorized") is not False:
            raise _error("scheduler gap row changed backfill authority")
        if event != "TICK_COMMITTED":
            continue
        scheduled = _scheduled_utc(row.get("scheduled_for_utc"), "committed scheduled time")
        committed_at = _utc(row.get("committed_at_utc"), "committed_at")
        if committed_at < scheduled:
            raise _error("committed_at predates nominal scheduled slot")
        if previous is not None and scheduled <= previous:
            raise _error("committed tick journal is duplicated or out of order")
        previous = scheduled
        commits.append((index, scheduled, committed_at, row))
    if not commits:
        raise _error("terminal archive contains no committed collection tick")
    index, scheduled, committed_at, row = commits[-1]
    if index != len(control_rows) - 1:
        raise _error("terminal TICK_COMMITTED must be the final control journal row")
    if row.get("phase") != control.ControlPhase.COLLECTION_COMPLETE.value:
        raise _error("terminal replay requires final COLLECTION_COMPLETE tick")
    tail_end = selected_close + dt.timedelta(hours=24)
    if scheduled < tail_end or committed_at < tail_end:
        raise _error("terminal archive predates selected-close settlement tail")

    nominal = _scheduled_utc(receipt.get("nominal_scheduled_for_utc"), "receipt nominal time")
    if nominal != scheduled:
        raise _error("final receipt nominal slot disagrees with latest committed state")
    receipt_committed_at = _utc(receipt.get("committed_at_utc"), "receipt committed_at")
    if receipt_committed_at != committed_at:
        raise _error("final receipt committed_at disagrees with latest committed state")
    if row.get("durable_asset_name") != receipt.get("durable_asset_name"):
        raise _error("latest committed tick durable asset disagrees with receipt")
    if row.get("durable_release_tag") != receipt.get("durable_release_tag"):
        raise _error("latest committed tick release tag disagrees with receipt")
    return scheduled, committed_at


def _verify_terminal_state(
    *,
    root: Path,
    receipt: Mapping[str, Any],
) -> tuple[
    tuple[fresh.FreshPredictionAssessment, ...],
    tuple[evaluator.TerminalSettlementRecord, ...],
    dt.datetime,
    dt.datetime,
    dict[str, int],
]:
    paths = _state_paths(root)
    prediction_rows = _rows(paths["prediction"])
    settlement_rows = _rows(paths["settlement"])
    capture_rows = _rows(paths["capture"])
    identity_rows = _rows(paths["identity"])
    control_rows = _rows(paths["control"])
    if not paths["checkpoint"].is_file() or paths["checkpoint"].is_symlink():
        raise _error("terminal archive must contain a regular checkpoint")
    checkpoint = _canonical_object(paths["checkpoint"].read_bytes(), "checkpoint")

    assessments = _prediction_assessments(prediction_rows)
    sealed = tuple(
        value.sealed_prediction
        for value in assessments
        if value.sealed_prediction is not None
    )
    terminals = _terminal_records(settlement_rows)
    selected_close = _selected_close(
        control_rows,
        tuple(value for value in sealed if value is not None),
    )
    latest_scheduled, evaluated_at = _final_commit(
        control_rows,
        selected_close=selected_close,
        receipt=receipt,
    )

    try:
        sealed_map, _processed = runner._prediction_state(prediction_rows)
        _settled_map, terminal_ids = runner._settlement_state(settlement_rows)
    except Exception as exc:
        raise _error("checkpoint population replay failed") from exc
    expected_checkpoint = {
        "schema_version": 1,
        "runner_id": runner.RUNNER_ID,
        "last_committed_scheduled_for_utc": _utc_text(latest_scheduled),
        "phase": control.ControlPhase.COLLECTION_COMPLETE.value,
        "capture_count": len(capture_rows),
        "prediction_count": len(sealed_map),
        "settled_or_terminal_count": len(terminal_ids),
        "control_event_count": len(control_rows),
        "durable_release_tag": receipt.get("durable_release_tag"),
        "durable_asset_name": receipt.get("durable_asset_name"),
    }
    if checkpoint != expected_checkpoint:
        raise _error("checkpoint disagrees with exact append-only terminal journals")

    counts = {
        "capture_rows": len(capture_rows),
        "prediction_assessment_rows": len(prediction_rows),
        "sealed_complete_cases": len(sealed_map),
        "identity_rows": len(identity_rows),
        "terminal_rows": len(settlement_rows),
        "control_rows": len(control_rows),
    }
    return assessments, terminals, selected_close, evaluated_at, counts


def replay_fresh_holdout_confirmation(
    *,
    archive_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    """Replay one terminal cumulative PR151 state into PR167, fully offline."""
    verify_reviewed_dependencies()
    receipt, archive_raw, receipt_raw = _verify_final_receipt(
        archive_path=Path(archive_path), receipt_path=Path(receipt_path)
    )
    archive_sha = hashlib.sha256(archive_raw).hexdigest()
    receipt_sha = hashlib.sha256(receipt_raw).hexdigest()

    with tempfile.TemporaryDirectory(prefix="athena-fresh-holdout-replay-") as tmp:
        repo = Path(tmp)
        try:
            runner.verify_and_extract_durable_state_archive(
                Path(archive_path),
                repository_root=repo,
                expected_sha256=archive_sha,
            )
        except Exception as exc:
            raise _error("durable state archive failed reviewed PR151 verification") from exc
        root = repo / control.CONTROL_ROOT_RELATIVE
        if not root.is_dir() or root.is_symlink():
            raise _error("durable archive did not materialize exact reviewed state root")
        assessments, terminals, selected_close, evaluated_at, counts = _verify_terminal_state(
            root=root,
            receipt=receipt,
        )

    try:
        result = evaluator.evaluate_fresh_holdout_confirmation(
            prediction_assessments=assessments,
            terminal_records=terminals,
            selected_close_utc=selected_close,
            evaluated_at_utc=evaluated_at,
        )
    except evaluator.FreshHoldoutConfirmationEvaluatorError as exc:
        raise _error("PR167 frozen confirmation evaluation rejected durable-state replay") from exc
    safety = result.get("safety")
    if type(safety) is not dict or any(value is not False for value in safety.values()):
        raise _error("durable-state replay changed downstream evaluator authority")

    result_sha = evaluator.sha256_fresh_holdout_confirmation_result(result)
    return {
        "schema_version": SCHEMA_VERSION,
        "replay_id": REPLAY_ID,
        "replay_state": REPLAY_STATE,
        "source_scope": SOURCE_SCOPE,
        "workflow_run_id": receipt["workflow_run_id"],
        "nominal_scheduled_for_utc": receipt["nominal_scheduled_for_utc"],
        "durable_release_tag": receipt["durable_release_tag"],
        "durable_asset_name": receipt["durable_asset_name"],
        "durable_archive_sha256": archive_sha,
        "durable_archive_size_bytes": len(archive_raw),
        "tick_receipt_sha256": receipt_sha,
        "tick_receipt_size_bytes": len(receipt_raw),
        "selected_close_utc": _utc_text(selected_close),
        "evaluated_at_utc": _utc_text(evaluated_at),
        "source_counts": counts,
        "confirmation_result": result,
        "confirmation_result_sha256": result_sha,
        "durable_state_journals_replayed": True,
        "provider_raw_capture_rederivation_performed": False,
        "network_acquisition_performed": False,
        "model_or_calibration_refit_performed": False,
        "automatic_successor_approval": False,
        "pricing_authorized": False,
        "selection_authorized": False,
        "bet_authorized": False,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(safety),
    }


def canonical_source_replay_result_bytes(value: Mapping[str, Any]) -> bytes:
    if not isinstance(value, Mapping):
        raise _error("source replay result must be a mapping")
    return _canonical(dict(value))


def sha256_source_replay_result(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_source_replay_result_bytes(value)).hexdigest()


def _write_new(path: Path, raw: bytes) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise _error("output path already exists; source replay is no-overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline PR151 durable-state replay for frozen fresh-holdout confirmation."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = replay_fresh_holdout_confirmation(
            archive_path=args.archive,
            receipt_path=args.receipt,
        )
        raw = canonical_source_replay_result_bytes(result)
        if args.output is not None:
            _write_new(args.output, raw)
        print(raw.decode("utf-8"), end="")
        return 0
    except (FreshHoldoutConfirmationSourceReplayError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FreshHoldoutConfirmationSourceReplayError",
    "NEXT_REQUIRED_BOUNDARY",
    "REPLAY_ID",
    "REPLAY_STATE",
    "SOURCE_SCOPE",
    "canonical_source_replay_result_bytes",
    "replay_fresh_holdout_confirmation",
    "sha256_source_replay_result",
    "verify_reviewed_dependencies",
]
