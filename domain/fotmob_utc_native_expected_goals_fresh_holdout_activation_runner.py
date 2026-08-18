"""Live research-only runner for the reviewed FotMob fresh-xG holdout."""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import types
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import domain.fotmob_data_matches_capture as capture_contract
import domain.fotmob_data_matches_ordinary_ft_finished_score_adapter as score_adapter
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import scripts.capture_fotmob_data_matches as capture_script

SCHEMA_VERSION = 1
RUNNER_ID = "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_ACTIVATION_RUNNER_V1"
RUNNER_STATE = "ACTIVATED_REVIEWED_FRESH_HOLDOUT_COLLECTION_RUNNER_RESEARCH_ONLY"
NEXT_REQUIRED_BOUNDARY = "REVIEW_FRESH_HOLDOUT_COLLECTION_EVIDENCE_AND_CONFIRMATION_RESULT"
PR150_MERGE_SHA = "50684a85cd528d491be812ed77d2c744855aba84"
PR150_MERGE_UTC_TEXT = "2026-08-18T04:55:12Z"
PR150_CONTROL_BLOB_SHA = "60865e35a92e28bb0d4360223dea42b8933bb706"
PR149_IMPLEMENTATION_BLOB_SHA = "5dabab12d5205d384fd3904cda0e68661ef90791"
CAPTURE_SCRIPT_BLOB_SHA = "10b8858ab62f2708bd564d578a627c43718e5a12"
CAPTURE_CONTRACT_BLOB_SHA = "ca2149395de868104666620173b55a880b10c729"
ORDINARY_FT_ADAPTER_BLOB_SHA = "868563206e09010fce74b4ba7954028930baad54"
PR119_EXECUTOR_BLOB_SHA = "2409676b4993a25024e2e8554e84e3525e7c5e6e"
WORKING_CAPTURE_DIRECTORY = "working-captures"
WORKING_CAPTURE_LIMIT_PER_DATE = 4
SAFETY_KEYS = tuple(sorted(fresh.SAFETY_KEYS))


class FreshHoldoutActivationError(RuntimeError):
    pass


def _error(message: str) -> FreshHoldoutActivationError:
    return FreshHoldoutActivationError(message)


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
        raise _error("canonical activation serialization failed") from exc


def _utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error(f"{label} must be timezone-aware")
    return value.astimezone(dt.timezone.utc)


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z") or value != value.strip():
        raise _error(f"{label} must be exact UTC Z text")
    try:
        return _utc(dt.datetime.fromisoformat(value[:-1] + "+00:00"), label)
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc


def _utc_text(value: dt.datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise _error(f"{label} must be lowercase SHA-256")
    return value


def _blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _safety() -> Mapping[str, bool]:
    return types.MappingProxyType({key: False for key in SAFETY_KEYS})


def verify_reviewed_activation_dependencies() -> None:
    control.verify_reviewed_implementation()
    pins = (
        (Path(control.__file__), PR150_CONTROL_BLOB_SHA, "PR150 control"),
        (Path(fresh.__file__), PR149_IMPLEMENTATION_BLOB_SHA, "PR149 core"),
        (Path(capture_script.__file__), CAPTURE_SCRIPT_BLOB_SHA, "capture script"),
        (Path(capture_contract.__file__), CAPTURE_CONTRACT_BLOB_SHA, "capture contract"),
        (Path(score_adapter.__file__), ORDINARY_FT_ADAPTER_BLOB_SHA, "ordinary-FT adapter"),
    )
    for path, expected, label in pins:
        try:
            actual = _blob(path)
        except OSError as exc:
            raise _error(f"could not inspect {label}") from exc
        if actual != expected:
            raise _error(f"{label} blob changed")
    if control.NEXT_REQUIRED_BOUNDARY != (
        "ACTIVATE_REVIEWED_FRESH_HOLDOUT_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_"
        "COLLECTION_RUNNER"
    ):
        raise _error("PR150 next boundary changed")
    receipt = control.collection_control_receipt()
    if (
        receipt["activation"]["fresh_holdout_collection_started"] is not False
        or receipt["activation"]["network_acquisition_performed"] is not False
        or any(receipt["safety"].values())
    ):
        raise _error("PR150 authority state changed")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_state_root(path: Path, *, repository_root: Path | None = None) -> Path:
    repo = (repository_root or _repo_root()).resolve(strict=True)
    expected = repo / control.CONTROL_ROOT_RELATIVE
    supplied = Path(path)
    if ".." in supplied.parts:
        raise _error("state root must not contain traversal")
    absolute = supplied if supplied.is_absolute() else repo / supplied
    if absolute.resolve(strict=False) != expected.resolve(strict=False):
        raise _error("state root must be the exact reviewed research state root")
    current = repo
    for part in absolute.relative_to(repo).parts:
        current = current / part
        if current.is_symlink():
            raise _error("state root contains a forbidden symlink")
    if absolute.exists() and not absolute.is_dir():
        raise _error("state root must be a directory")
    absolute.mkdir(parents=True, exist_ok=True)
    return absolute


def _fsync_dir(path: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _regular(path: Path) -> None:
    if path.is_symlink():
        raise _error(f"{path.name} must not be a symlink")
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise _error(f"{path.name} must be a regular file")


def _append(path: Path, row: Mapping[str, Any]) -> None:
    _regular(path)
    raw = _canonical(dict(row))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _rows(path: Path) -> tuple[dict[str, Any], ...]:
    _regular(path)
    if not path.exists():
        return ()
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise _error(f"{path.name} has a torn row")
    out: list[dict[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error(f"{path.name} contains malformed JSON") from exc
        if type(value) is not dict or _canonical(value) != line:
            raise _error(f"{path.name} contains non-canonical evidence")
        out.append(value)
    return tuple(out)


def _checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    _regular(path)
    raw = _canonical(dict(value))
    tmp = path.with_name(f".{path.name}.tmp")
    if tmp.exists() or tmp.is_symlink():
        raise _error("checkpoint temporary path already exists")
    with tmp.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _fixture(value: Any) -> fresh.QualifiedCaptureFixture:
    if type(value) is not dict:
        raise _error("fixture evidence must be an object")
    try:
        return fresh.QualifiedCaptureFixture(
            fixture_id=value["fixture_id"],
            provider_primary_id=value["provider_primary_id"],
            wrapper_id=value["wrapper_id"],
            home_team_id=value["home_team_id"],
            away_team_id=value["away_team_id"],
            kickoff_utc=_parse_utc(value["kickoff_utc"], "fixture kickoff"),
            capture_observed_at=_parse_utc(
                value["capture_observed_at"], "fixture observed_at"
            ),
            capture_manifest_sha256=value["capture_manifest_sha256"],
            capture_raw_sha256=value["capture_raw_sha256"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("fixture evidence keys changed") from exc


def _sealed(value: Any) -> fresh.SealedFreshPrediction:
    if type(value) is not dict:
        raise _error("sealed prediction evidence must be an object")
    try:
        return fresh.SealedFreshPrediction(
            schema_version=value["schema_version"],
            implementation_state=value["implementation_state"],
            protocol_sha256=value["protocol_sha256"],
            holdout_start_utc=_parse_utc(value["holdout_start_utc"], "holdout start"),
            fixture=_fixture(value["fixture"]),
            bootstrap_projection_sha256=value["bootstrap_projection_sha256"],
            history_prefix_sha256=value["history_prefix_sha256"],
            history_prefix_count=value["history_prefix_count"],
            feature_projection_sha256=value["feature_projection_sha256"],
            features=value["features"],
            rates=value["rates"],
            safety=value["safety"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("sealed prediction evidence keys changed") from exc


def _history(value: Any) -> fresh.FreshHistoryResult:
    if type(value) is not dict:
        raise _error("history evidence must be an object")
    try:
        return fresh.FreshHistoryResult(
            fixture_identifier=value["fixture_identifier"],
            home_team_id=value["home_team_id"],
            away_team_id=value["away_team_id"],
            kickoff_utc=_parse_utc(value["kickoff_utc"], "history kickoff"),
            home_goals=value["home_goals"],
            away_goals=value["away_goals"],
            observed_at=_parse_utc(value["observed_at"], "history observed_at"),
            evidence_sha256=value["evidence_sha256"],
            evidence_reference=value["evidence_reference"],
            provider_primary_id=value["provider_primary_id"],
            source_kind=value["source_kind"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("history evidence keys changed") from exc


def _history_dict(value: fresh.FreshHistoryResult) -> dict[str, Any]:
    return {
        "fixture_identifier": value.fixture_identifier,
        "home_team_id": value.home_team_id,
        "away_team_id": value.away_team_id,
        "kickoff_utc": _utc_text(value.kickoff_utc),
        "home_goals": value.home_goals,
        "away_goals": value.away_goals,
        "observed_at": _utc_text(value.observed_at),
        "evidence_sha256": value.evidence_sha256,
        "evidence_reference": value.evidence_reference,
        "provider_primary_id": value.provider_primary_id,
        "source_kind": value.source_kind,
    }


def _settled_dict(value: fresh.SettledFreshPrediction) -> dict[str, Any]:
    return {
        "prediction": value.prediction.to_dict(),
        "home_goals": value.home_goals,
        "away_goals": value.away_goals,
        "settlement_observed_at": _utc_text(value.settlement_observed_at),
        "settlement_evidence_sha256": value.settlement_evidence_sha256,
        "ordinary_ft_first_raw_sha256": value.ordinary_ft_first_raw_sha256,
        "ordinary_ft_second_raw_sha256": value.ordinary_ft_second_raw_sha256,
        "ordinary_ft_first_manifest_sha256": value.ordinary_ft_first_manifest_sha256,
        "ordinary_ft_second_manifest_sha256": value.ordinary_ft_second_manifest_sha256,
        "legacy_history_state_update": (
            None
            if value.legacy_history_state_update is None
            else _history_dict(value.legacy_history_state_update)
        ),
    }


def _settled(value: Any) -> fresh.SettledFreshPrediction:
    if type(value) is not dict:
        raise _error("settlement evidence must be an object")
    try:
        update = value["legacy_history_state_update"]
        return fresh.SettledFreshPrediction(
            prediction=_sealed(value["prediction"]),
            home_goals=value["home_goals"],
            away_goals=value["away_goals"],
            settlement_observed_at=_parse_utc(
                value["settlement_observed_at"], "settlement observed_at"
            ),
            settlement_evidence_sha256=value["settlement_evidence_sha256"],
            ordinary_ft_first_raw_sha256=value["ordinary_ft_first_raw_sha256"],
            ordinary_ft_second_raw_sha256=value["ordinary_ft_second_raw_sha256"],
            ordinary_ft_first_manifest_sha256=value["ordinary_ft_first_manifest_sha256"],
            ordinary_ft_second_manifest_sha256=value["ordinary_ft_second_manifest_sha256"],
            legacy_history_state_update=None if update is None else _history(update),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("settlement evidence keys changed") from exc


@dataclasses.dataclass(frozen=True)
class CaptureEvidence:
    capture_directory: Path
    raw_json: bytes
    manifest: capture_contract.FotMobDataMatchesCaptureManifest

    def __post_init__(self) -> None:
        if Path(self.capture_directory).is_symlink():
            raise _error("capture directory must not be a symlink")
        if type(self.raw_json) is not bytes or not self.raw_json:
            raise _error("capture body must be non-empty exact bytes")
        if type(self.manifest) is not capture_contract.FotMobDataMatchesCaptureManifest:
            raise _error("capture manifest type changed")
        if self.manifest.network_acquisition_performed is not True:
            raise _error("capture must prove live network acquisition")
        if hashlib.sha256(self.raw_json).hexdigest() != self.manifest.raw_sha256:
            raise _error("capture raw hash changed")


def _live_capture(request_date: str, *, repository_root: Path) -> CaptureEvidence:
    response = capture_script.fetch_fotmob_data_matches(
        request_date=request_date,
        timezone=control.REQUEST_TIMEZONE,
        ccode3=control.REQUEST_CCODE3,
    )
    directory, manifest = capture_script.write_data_matches_capture_directory(
        response,
        request_date=request_date,
        timezone=control.REQUEST_TIMEZONE,
        ccode3=control.REQUEST_CCODE3,
        repository_root=repository_root,
    )
    return CaptureEvidence(
        directory,
        (directory / capture_contract.RAW_FILENAME).read_bytes(),
        manifest,
    )


def _manifest_sha(evidence: CaptureEvidence) -> str:
    return capture_contract.sha256_data_matches_capture_manifest(evidence.manifest)


def _qualify(evidence: CaptureEvidence) -> tuple[fresh.QualifiedCaptureFixture, ...]:
    try:
        return fresh.qualify_capture_fixtures(evidence.raw_json, evidence.manifest)
    except Exception as exc:
        raise _error("reviewed fresh capture qualification failed") from exc


def _capture_id(evidence: CaptureEvidence) -> str:
    return capture_contract.capture_identifier(
        request_date=evidence.manifest.request_date,
        timezone=evidence.manifest.timezone,
        ccode3=evidence.manifest.ccode3,
        observed_at=evidence.manifest.observed_at,
        raw_sha256=evidence.manifest.raw_sha256,
    )


def _stage(evidence: CaptureEvidence, working: Path) -> None:
    date_root = working / evidence.manifest.request_date
    if date_root.is_symlink():
        raise _error("working capture date path is a symlink")
    date_root.mkdir(parents=True, exist_ok=True)
    target = date_root / _capture_id(evidence)
    if target.exists() or target.is_symlink():
        raise _error("working capture already exists")
    target.mkdir()
    for name, raw in (
        (capture_contract.RAW_FILENAME, evidence.raw_json),
        (
            capture_contract.MANIFEST_FILENAME,
            capture_contract.canonical_data_matches_capture_manifest_bytes(
                evidence.manifest
            ),
        ),
    ):
        with (target / name).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    _fsync_dir(target)
    _fsync_dir(date_root)


def _working(working: Path) -> tuple[CaptureEvidence, ...]:
    if not working.exists():
        return ()
    if working.is_symlink() or not working.is_dir():
        raise _error("working capture root is invalid")
    out: list[CaptureEvidence] = []
    for date_root in sorted(working.iterdir()):
        if date_root.is_symlink() or not date_root.is_dir():
            raise _error("working capture date entry is invalid")
        for directory in sorted(date_root.iterdir()):
            try:
                manifest = capture_contract.verify_data_matches_capture_directory(
                    directory,
                    allowed_root=working,
                    require_network_acquisition_performed=True,
                )
            except Exception as exc:
                raise _error("working capture verification failed") from exc
            out.append(
                CaptureEvidence(
                    directory,
                    (directory / capture_contract.RAW_FILENAME).read_bytes(),
                    manifest,
                )
            )
    return tuple(sorted(out, key=lambda x: (x.manifest.observed_at, _manifest_sha(x))))


def _prune(working: Path) -> None:
    if not working.exists():
        return
    for date_root in list(working.iterdir()):
        captures: list[tuple[dt.datetime, Path]] = []
        for directory in date_root.iterdir():
            manifest = capture_contract.verify_data_matches_capture_directory(
                directory, allowed_root=working
            )
            captures.append((manifest.observed_at, directory))
        captures.sort()
        for _observed, directory in captures[:-WORKING_CAPTURE_LIMIT_PER_DATE]:
            if directory.is_symlink():
                raise _error("refusing to prune symlink")
            shutil.rmtree(directory)


def _prediction_state(
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[int, fresh.SealedFreshPrediction], set[int]]:
    sealed: dict[int, fresh.SealedFreshPrediction] = {}
    processed: set[int] = set()
    for row in rows:
        fixture_id = row.get("fixture_id")
        if type(fixture_id) is not int or fixture_id < 1 or fixture_id in processed:
            raise _error("prediction journal fixture identity invalid/duplicated")
        disposition = row.get("disposition")
        if disposition == fresh.PredictionDisposition.SEALED_COMPLETE_CASE.value:
            prediction = _sealed(row.get("prediction"))
            if (
                prediction.fixture.fixture_id != fixture_id
                or row.get("prediction_sha256")
                != fresh.sha256_sealed_fresh_prediction(prediction)
            ):
                raise _error("prediction journal seal identity changed")
            sealed[fixture_id] = prediction
        elif disposition == fresh.PredictionDisposition.MISSING_REVIEWED_FEATURES.value:
            if _fixture(row.get("selected_fixture")).fixture_id != fixture_id:
                raise _error("missing-feature fixture identity changed")
        else:
            raise _error("prediction disposition escaped reviewed vocabulary")
        processed.add(fixture_id)
    return sealed, processed


def _settlement_state(
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[int, fresh.SettledFreshPrediction], set[int]]:
    settled: dict[int, fresh.SettledFreshPrediction] = {}
    terminal: set[int] = set()
    allowed_terminal = {
        fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT.value,
        "EXCLUDED_OUTSIDE_SELECTED_CLOSE",
        "UNRESOLVED_AT_SETTLEMENT_TAIL",
    }
    for row in rows:
        fixture_id = row.get("fixture_id")
        if type(fixture_id) is not int or fixture_id < 1 or fixture_id in terminal:
            raise _error("settlement journal fixture identity invalid/duplicated")
        disposition = row.get("disposition")
        if disposition == fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT.value:
            value = _settled(row.get("settled_prediction"))
            if value.prediction.fixture.fixture_id != fixture_id:
                raise _error("settlement prediction identity changed")
            settled[fixture_id] = value
        elif disposition not in allowed_terminal or row.get("settled_prediction") is not None:
            raise _error("settlement disposition escaped activation vocabulary")
        terminal.add(fixture_id)
    return settled, terminal


def _identity_state(
    rows: Sequence[dict[str, Any]],
) -> tuple[dict[int, list[fresh.QualifiedCaptureFixture]], set[tuple[int, str]]]:
    out: dict[int, list[fresh.QualifiedCaptureFixture]] = defaultdict(list)
    keys: set[tuple[int, str]] = set()
    for row in rows:
        fixture_id = row.get("fixture_id")
        manifest_sha = _sha(row.get("capture_manifest_sha256"), "identity manifest")
        key = (fixture_id, manifest_sha)
        if type(fixture_id) is not int or fixture_id < 1 or key in keys:
            raise _error("post-seal identity journal invalid/duplicated")
        observation = _fixture(row.get("observation"))
        if (
            observation.fixture_id != fixture_id
            or observation.capture_manifest_sha256 != manifest_sha
        ):
            raise _error("post-seal identity observation changed")
        out[fixture_id].append(observation)
        keys.add(key)
    return dict(out), keys


def _ledger(
    bootstrap_raw: bytes, settlement_rows: Sequence[dict[str, Any]]
) -> fresh.FreshHistoryLedger:
    try:
        ledger = fresh.build_fresh_history_ledger(bootstrap_raw)
    except Exception as exc:
        raise _error("exact PR119 bootstrap failed validation") from exc
    updates = [
        _settled(row["settled_prediction"])
        for row in settlement_rows
        if row.get("disposition")
        == fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT.value
        and row.get("settled_prediction", {}).get("legacy_history_state_update") is not None
    ]
    updates.sort(
        key=lambda x: (
            x.settlement_observed_at,
            x.prediction.fixture.kickoff_utc,
            x.prediction.fixture.fixture_id,
        )
    )
    for value in updates:
        try:
            ledger = fresh.append_fresh_legacy_history_update(ledger, value)
        except Exception as exc:
            raise _error("fresh legacy history replay failed") from exc
    return ledger


def _close_state(
    predictions: Sequence[fresh.SealedFreshPrediction],
    control_rows: Sequence[dict[str, Any]],
    scheduled: dt.datetime,
    path: Path,
) -> control.CloseControlState | None:
    records = [
        row for row in control_rows if row.get("event") == "COUNT_ONLY_CLOSE_EVALUATION"
    ]
    parsed: list[tuple[dt.datetime, dict[str, Any]]] = []
    for row in records:
        parsed.append(
            (_parse_utc(row["evaluated_boundary_utc"], "close boundary"), row)
        )
    parsed.sort(key=lambda item: item[0])
    if len({boundary for boundary, _row in parsed}) != len(parsed):
        raise _error("close journal duplicated a boundary")
    selected_records = [
        (boundary, row)
        for boundary, row in parsed
        if row.get("selected_close_utc") is not None
    ]
    if selected_records and selected_records[0] != parsed[-1]:
        raise _error("close journal contains evaluation after selected close")
    required = control.required_close_evaluation_boundary(scheduled)
    if required is None:
        if parsed:
            raise _error("premature close evaluation exists")
        return None
    if selected_records:
        boundary, row = selected_records[0]
        state = control.evaluate_close_control_state(predictions, boundary=boundary)
        if state.to_dict() != {
            "evaluated_boundary_utc": row["evaluated_boundary_utc"],
            "decision": row["decision"],
            "selected_close_utc": row["selected_close_utc"],
            "coverage_sha256": row["coverage_sha256"],
        }:
            raise _error("selected close failed deterministic revalidation")
        return state
    if parsed and parsed[-1][0] == required:
        boundary, row = parsed[-1]
        state = control.evaluate_close_control_state(predictions, boundary=boundary)
        if state.to_dict() != {
            "evaluated_boundary_utc": row["evaluated_boundary_utc"],
            "decision": row["decision"],
            "selected_close_utc": row["selected_close_utc"],
            "coverage_sha256": row["coverage_sha256"],
        }:
            raise _error("open close failed deterministic revalidation")
        return state
    if parsed and parsed[-1][0] > required:
        raise _error("close journal contains future state")
    state = control.evaluate_close_control_state(predictions, boundary=required)
    _append(
        path,
        {
            "schema_version": 1,
            "event": "COUNT_ONLY_CLOSE_EVALUATION",
            **state.to_dict(),
            "outcome_or_performance_input_used": False,
        },
    )
    return state


def _slot_index(value: dt.datetime) -> int | None:
    first = control.holdout_start_utc() + dt.timedelta(
        minutes=control.CAPTURE_MINUTES_UTC[0]
    )
    if value < first:
        return None
    seconds = (value - first).total_seconds()
    step = control.CAPTURE_INTERVAL_MINUTES * 60
    if seconds % step:
        raise _error("scheduled tick escaped reviewed slot lattice")
    return int(seconds // step)


def _committed(rows: Sequence[dict[str, Any]], scheduled: dt.datetime) -> bool:
    text = _utc_text(scheduled)
    return any(
        row.get("event") == "TICK_COMMITTED"
        and row.get("scheduled_for_utc") == text
        for row in rows
    )


def _gap(rows: Sequence[dict[str, Any]], scheduled: dt.datetime, path: Path) -> None:
    current = _slot_index(scheduled)
    if current is None:
        return
    committed: list[tuple[int, dt.datetime]] = []
    for row in rows:
        if row.get("event") != "TICK_COMMITTED":
            continue
        tick = _parse_utc(row["scheduled_for_utc"], "committed tick")
        index = _slot_index(tick)
        if index is not None:
            committed.append((index, tick))
    if committed:
        committed.sort()
        last_index, last_tick = committed[-1]
        if current <= last_index:
            if current < last_index:
                raise _error("tick moved backward behind durable state")
            return
        first_missing = last_index + 1
    else:
        last_tick = None
        first_missing = 0
    last_missing = current - 1
    if last_missing < first_missing:
        return
    origin = control.holdout_start_utc() + dt.timedelta(
        minutes=control.CAPTURE_MINUTES_UTC[0]
    )
    step = dt.timedelta(minutes=control.CAPTURE_INTERVAL_MINUTES)
    _append(
        path,
        {
            "schema_version": 1,
            "event": "SCHEDULER_GAP_RANGE",
            "detected_at_scheduled_for_utc": _utc_text(scheduled),
            "previous_committed_tick_utc": (
                None if last_tick is None else _utc_text(last_tick)
            ),
            "first_missing_tick_utc": _utc_text(origin + first_missing * step),
            "last_missing_tick_utc": _utc_text(origin + last_missing * step),
            "missing_tick_count": last_missing - first_missing + 1,
            "backfill_authorized": False,
        },
    )


def _post_seal(
    sealed: Mapping[int, fresh.SealedFreshPrediction],
    observations: Sequence[fresh.QualifiedCaptureFixture],
    path: Path,
    keys: set[tuple[int, str]],
) -> None:
    for observation in sorted(
        observations,
        key=lambda x: (x.capture_observed_at, x.fixture_id, x.capture_manifest_sha256),
    ):
        prediction = sealed.get(observation.fixture_id)
        key = (observation.fixture_id, observation.capture_manifest_sha256)
        if (
            prediction is None
            or observation.capture_observed_at <= prediction.fixture.capture_observed_at
            or key in keys
        ):
            continue
        _append(
            path,
            {
                "schema_version": 1,
                "fixture_id": observation.fixture_id,
                "capture_manifest_sha256": observation.capture_manifest_sha256,
                "observation": observation.to_dict(),
            },
        )
        keys.add(key)


def _pair(
    prediction: fresh.SealedFreshPrediction,
    captures: Sequence[CaptureEvidence],
    qualified: dict[str, tuple[fresh.QualifiedCaptureFixture, ...]],
) -> tuple[CaptureEvidence, CaptureEvidence] | None:
    date = prediction.fixture.kickoff_utc.strftime("%Y%m%d")
    candidates: list[CaptureEvidence] = []
    for evidence in captures:
        if evidence.manifest.request_date != date or evidence.manifest.observed_at <= prediction.fixture.kickoff_utc:
            continue
        sha = _manifest_sha(evidence)
        rows = qualified.get(sha)
        if rows is None:
            rows = _qualify(evidence)
            qualified[sha] = rows
        if any(row.fixture_id == prediction.fixture.fixture_id for row in rows):
            candidates.append(evidence)
    candidates.sort(key=lambda x: (x.manifest.observed_at, _manifest_sha(x)))
    if len(candidates) < 2:
        return None
    latest = candidates[-1]
    for prior in reversed(candidates[:-1]):
        if (
            (latest.manifest.observed_at - prior.manifest.observed_at).total_seconds()
            >= score_adapter.MINIMUM_REPEAT_SEPARATION_SECONDS
            and latest.manifest.raw_sha256 != prior.manifest.raw_sha256
            and _manifest_sha(latest) != _manifest_sha(prior)
        ):
            return prior, latest
    return None


def _prediction_row(
    assessment: fresh.FreshPredictionAssessment, tag: str, asset: str
) -> dict[str, Any]:
    sealed = assessment.sealed_prediction
    return {
        "schema_version": 1,
        "fixture_id": assessment.fixture.fixture_id,
        "disposition": assessment.disposition.value,
        "prediction_sha256": (
            None if sealed is None else fresh.sha256_sealed_fresh_prediction(sealed)
        ),
        "prediction": None if sealed is None else sealed.to_dict(),
        "selected_fixture": None if sealed is not None else assessment.fixture.to_dict(),
        "missing_feature_ids": list(assessment.missing_feature_ids),
        "durable_release_tag": tag,
        "durable_asset_name": asset,
    }


def _settlement_row(
    assessment: fresh.FreshSettlementAssessment, tag: str, asset: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fixture_id": assessment.prediction.fixture.fixture_id,
        "disposition": assessment.disposition.value,
        "detail": assessment.detail,
        "prediction_sha256": fresh.sha256_sealed_fresh_prediction(
            assessment.prediction
        ),
        "settled_prediction": (
            None
            if assessment.settled_prediction is None
            else _settled_dict(assessment.settled_prediction)
        ),
        "durable_release_tag": tag,
        "durable_asset_name": asset,
    }


def _terminal_row(
    prediction: fresh.SealedFreshPrediction,
    disposition: str,
    detail: str,
    tag: str,
    asset: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fixture_id": prediction.fixture.fixture_id,
        "disposition": disposition,
        "detail": detail,
        "prediction_sha256": fresh.sha256_sealed_fresh_prediction(prediction),
        "settled_prediction": None,
        "durable_release_tag": tag,
        "durable_asset_name": asset,
    }


def execute_collection_tick(
    *,
    scheduled_for: dt.datetime,
    bootstrap_projection_raw: bytes,
    durable_release_tag: str,
    durable_asset_name: str,
    execute_live_network: bool,
    state_root: Path = Path(control.CONTROL_ROOT_RELATIVE),
    repository_root: Path | None = None,
    capture_one: Callable[..., CaptureEvidence] = _live_capture,
    clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
) -> dict[str, Any]:
    """Execute one exact nominal :07/:37 tick; success still requires release upload."""
    verify_reviewed_activation_dependencies()
    repo = (repository_root or _repo_root()).resolve(strict=True)
    root = validate_state_root(state_root, repository_root=repo)
    scheduled = _utc(scheduled_for, "scheduled_for")
    if (
        scheduled.second
        or scheduled.microsecond
        or scheduled.minute not in control.CAPTURE_MINUTES_UTC
    ):
        raise _error("scheduled_for escaped PR150 :07/:37 slot identity")
    if type(execute_live_network) is not bool:
        raise _error("execute_live_network must be exact bool")
    if (
        type(durable_release_tag) is not str
        or not durable_release_tag.startswith("athena-fresh-holdout-evidence-")
    ):
        raise _error("durable release tag is invalid")
    if (
        type(durable_asset_name) is not str
        or not durable_asset_name.startswith("success-")
        or not durable_asset_name.endswith(".tar.gz")
    ):
        raise _error("durable success asset name is invalid")

    paths = {
        "capture": root / control.CAPTURE_INDEX_FILENAME,
        "prediction": root / control.PREDICTION_JOURNAL_FILENAME,
        "identity": root / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
        "settlement": root / control.SETTLEMENT_JOURNAL_FILENAME,
        "control": root / control.CONTROL_JOURNAL_FILENAME,
        "checkpoint": root / control.CHECKPOINT_FILENAME,
    }
    capture_rows = _rows(paths["capture"])
    prediction_rows = _rows(paths["prediction"])
    identity_rows = _rows(paths["identity"])
    settlement_rows = _rows(paths["settlement"])
    control_rows = _rows(paths["control"])
    if paths["checkpoint"].exists():
        _regular(paths["checkpoint"])
        try:
            json.loads(paths["checkpoint"].read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("checkpoint JSON is malformed") from exc

    if _committed(control_rows, scheduled):
        return {
            "schema_version": 1,
            "runner_id": RUNNER_ID,
            "runner_state": RUNNER_STATE,
            "scheduled_for_utc": _utc_text(scheduled),
            "disposition": "ALREADY_COMMITTED_NO_NETWORK_REPLAY",
            "network_acquisition_performed": False,
            "network_request_count": 0,
            "fresh_holdout_collection_started_by_this_run": False,
            "durable_release_tag": durable_release_tag,
            "durable_asset_name": durable_asset_name,
            "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
            "safety": dict(_safety()),
        }

    sealed, processed = _prediction_state(prediction_rows)
    _settled_map, terminal = _settlement_state(settlement_rows)
    identity_map, identity_keys = _identity_state(identity_rows)
    capture_keys = {
        _sha(row.get("manifest_sha256"), "capture manifest") for row in capture_rows
    }
    if len(capture_keys) != len(capture_rows):
        raise _error("capture index duplicated a manifest")

    predictions = tuple(value for _key, value in sorted(sealed.items()))
    close_state = _close_state(predictions, control_rows, scheduled, paths["control"])
    plan = control.build_collection_tick_plan(scheduled, close_state=close_state)
    _gap(control_rows, scheduled, paths["control"])
    if plan.request_dates and execute_live_network is not True:
        raise _error("active tick requires explicit live-network authorization")
    if type(bootstrap_projection_raw) is not bytes:
        raise _error("bootstrap projection must be exact bytes")
    ledger = _ledger(bootstrap_projection_raw, settlement_rows)

    working = root / WORKING_CAPTURE_DIRECTORY
    existing = _working(working)
    current: list[CaptureEvidence] = []
    current_qualified: list[fresh.QualifiedCaptureFixture] = []
    qualified: dict[str, tuple[fresh.QualifiedCaptureFixture, ...]] = {}
    errors: list[str] = []
    for request_date in plan.request_dates:
        try:
            evidence = capture_one(request_date, repository_root=repo)
            if type(evidence) is not CaptureEvidence:
                raise _error("capture_one returned unexpected type")
            if (
                evidence.manifest.request_date != request_date
                or evidence.manifest.timezone != control.REQUEST_TIMEZONE
                or evidence.manifest.ccode3 != control.REQUEST_CCODE3
            ):
                raise _error("live capture request identity changed")
            if evidence.manifest.observed_at < scheduled:
                raise _error("live capture observed_at predates nominal slot")
            sha = _manifest_sha(evidence)
            if sha in capture_keys:
                raise _error("new capture duplicates durable lineage")
            _stage(evidence, working)
            rows = _qualify(evidence)
            qualified[sha] = rows
            current.append(evidence)
            current_qualified.extend(rows)
        except Exception as exc:
            errors.append(f"{request_date}:{type(exc).__name__}:{str(exc)[:240]}")
    if errors:
        raise _error("one or more reviewed live captures failed: " + " | ".join(errors))

    for evidence in current:
        sha = _manifest_sha(evidence)
        _append(
            paths["capture"],
            {
                "schema_version": 1,
                "request_date": evidence.manifest.request_date,
                "timezone": evidence.manifest.timezone,
                "ccode3": evidence.manifest.ccode3,
                "observed_at": _utc_text(evidence.manifest.observed_at),
                "raw_sha256": evidence.manifest.raw_sha256,
                "raw_size": evidence.manifest.raw_size,
                "manifest_sha256": sha,
                "working_capture_relative": (
                    f"{WORKING_CAPTURE_DIRECTORY}/{evidence.manifest.request_date}/"
                    f"{_capture_id(evidence)}"
                ),
                "durable_release_tag": durable_release_tag,
                "durable_asset_name": durable_asset_name,
                "network_acquisition_performed": True,
            },
        )
        capture_keys.add(sha)

    _post_seal(sealed, current_qualified, paths["identity"], identity_keys)
    identity_map, identity_keys = _identity_state(_rows(paths["identity"]))
    all_captures = tuple(existing) + tuple(current)

    for fixture_id, prediction in sorted(sealed.items()):
        if fixture_id in terminal:
            continue
        pair = _pair(prediction, all_captures, qualified)
        if pair is None:
            continue
        first, second = pair
        try:
            assessment = fresh.settle_sealed_prediction(
                prediction,
                history_ledger=ledger,
                post_seal_observations=tuple(identity_map.get(fixture_id, ())),
                first_raw_json=first.raw_json,
                first_manifest=first.manifest,
                second_raw_json=second.raw_json,
                second_manifest=second.manifest,
            )
        except Exception as exc:
            raise _error(f"settlement of fixture {fixture_id} failed") from exc
        if assessment.disposition is fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT:
            if assessment.settled_prediction is None:
                raise _error("settlement missing settled record")
            _append(
                paths["settlement"],
                _settlement_row(
                    assessment,
                    durable_release_tag,
                    durable_asset_name,
                ),
            )
            terminal.add(fixture_id)
            if assessment.settled_prediction.legacy_history_state_update is not None:
                ledger = fresh.append_fresh_legacy_history_update(
                    ledger, assessment.settled_prediction
                )
        elif (
            assessment.disposition
            is fresh.SettlementDisposition.EXCLUDED_PROVIDER_IDENTITY_OR_KICKOFF_DRIFT
        ):
            _append(
                paths["settlement"],
                _terminal_row(
                    prediction,
                    assessment.disposition.value,
                    assessment.notes or "provider identity or kickoff drift observed",
                    durable_release_tag,
                    durable_asset_name,
                ),
            )
            terminal.add(fixture_id)
        elif (
            assessment.disposition
            is fresh.SettlementDisposition.EXCLUDED_NOT_REVIEWED_ORDINARY_FT
        ):
            pass
        else:
            raise _error("settlement disposition escaped reviewed vocabulary")

    # BLOCKER B: Exact Selected-Close Population Semantics
    if close_state is not None and close_state.selected_close_utc is not None:
        # At selected_close_utc itself: any sealed fixture with kickoff >= selected_close_utc
        # is outside the population and becomes EXCLUDED_OUTSIDE_SELECTED_CLOSE immediately.
        if scheduled >= close_state.selected_close_utc:
            for fixture_id, prediction in sorted(sealed.items()):
                if fixture_id in terminal:
                    continue
                if prediction.fixture.kickoff_utc >= close_state.selected_close_utc:
                    _append(
                        paths["settlement"],
                        _terminal_row(
                            prediction,
                            "EXCLUDED_OUTSIDE_SELECTED_CLOSE",
                            "sealed kickoff is not left-of the selected close boundary",
                            durable_release_tag,
                            durable_asset_name,
                        ),
                    )
                    terminal.add(fixture_id)

        # At selected_close_utc + 24h: any still-unresolved legitimate pre-close member
        # becomes UNRESOLVED_AT_SETTLEMENT_TAIL.
        if scheduled >= close_state.selected_close_utc + dt.timedelta(hours=24):
            for fixture_id, prediction in sorted(sealed.items()):
                if fixture_id in terminal:
                    continue
                _append(
                    paths["settlement"],
                    _terminal_row(
                        prediction,
                        "UNRESOLVED_AT_SETTLEMENT_TAIL",
                        "no reviewed stable ordinary-FT settlement was qualified before tail end",
                        durable_release_tag,
                        durable_asset_name,
                    ),
                )
                terminal.add(fixture_id)

    if plan.prediction_sealing_authorized:
        grouped: dict[int, list[fresh.QualifiedCaptureFixture]] = defaultdict(list)
        for observation in current_qualified:
            if observation.fixture_id not in processed:
                grouped[observation.fixture_id].append(observation)
        for fixture_id in sorted(grouped):
            observations = tuple(
                sorted(
                    grouped[fixture_id],
                    key=lambda x: (x.capture_observed_at, x.capture_manifest_sha256),
                )
            )
            selected = fresh.select_earliest_qualifying_capture(
                observations, holdout_start=control.holdout_start_utc()
            )
            if selected is None:
                continue
            assessment = fresh.build_fresh_prediction_assessment(
                history_ledger=ledger,
                selected_capture=selected,
                holdout_start=control.holdout_start_utc(),
            )
            _append(
                paths["prediction"],
                _prediction_row(
                    assessment, durable_release_tag, durable_asset_name
                ),
            )
            processed.add(fixture_id)
            if assessment.sealed_prediction is not None:
                sealed[fixture_id] = assessment.sealed_prediction
        _post_seal(sealed, current_qualified, paths["identity"], identity_keys)

    if plan.phase is control.ControlPhase.COLLECTION_COMPLETE:
        for fixture_id, prediction in sorted(sealed.items()):
            if fixture_id in terminal:
                continue
            _append(
                paths["settlement"],
                _terminal_row(
                    prediction,
                    "UNRESOLVED_AT_SETTLEMENT_TAIL",
                    "no reviewed stable ordinary-FT settlement was qualified before tail end",
                    durable_release_tag,
                    durable_asset_name,
                ),
            )
            terminal.add(fixture_id)

    _prune(working)

    committed_at = _utc(clock(), "tick completion time")
    final_sealed, _processed = _prediction_state(_rows(paths["prediction"]))
    _settled_final, final_terminal = _settlement_state(_rows(paths["settlement"]))
    _append(
        paths["control"],
        {
            "schema_version": 1,
            "event": "TICK_COMMITTED",
            "scheduled_for_utc": _utc_text(scheduled),
            "phase": plan.phase.value,
            "committed_at_utc": _utc_text(committed_at),
            "request_dates": list(plan.request_dates),
            "network_request_count": len(current),
            "network_acquisition_performed": bool(current),
            "durable_release_tag": durable_release_tag,
            "durable_asset_name": durable_asset_name,
            "nominal_schedule_time_used_as_observation_time": False,
            "backfill_or_retrofill_performed": False,
            "outcome_or_performance_input_used_for_close": False,
        },
    )
    _checkpoint(
        paths["checkpoint"],
        {
            "schema_version": 1,
            "runner_id": RUNNER_ID,
            "last_committed_scheduled_for_utc": _utc_text(scheduled),
            "phase": plan.phase.value,
            "capture_count": len(_rows(paths["capture"])),
            "prediction_count": len(final_sealed),
            "settled_or_terminal_count": len(final_terminal),
            "control_event_count": len(_rows(paths["control"])),
            "durable_release_tag": durable_release_tag,
            "durable_asset_name": durable_asset_name,
        },
    )
    return {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "runner_state": RUNNER_STATE,
        "scheduled_for_utc": _utc_text(scheduled),
        "phase": plan.phase.value,
        "committed_at_utc": _utc_text(committed_at),
        "request_dates": list(plan.request_dates),
        "network_request_count": len(current),
        "network_acquisition_performed": bool(current),
        "fresh_holdout_collection_started_by_this_run": plan.phase
        == control.ControlPhase.PREDICTION_AND_SETTLEMENT_COLLECTION,
        "durable_release_tag": durable_release_tag,
        "durable_asset_name": durable_asset_name,
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


def resolve_nominal_schedule_slot(
    schedule_expr: str,
    created_at: dt.datetime,
    *,
    last_committed_utc: dt.datetime | None = None,
) -> tuple[dt.datetime, str, str, str, str]:
    """Derive exact nominal schedule slot and release/asset targets from trigger and time.

    Fails closed if the cron occurrence identity is ambiguous relative to the predecessor.
    """
    if type(schedule_expr) is not str or schedule_expr not in (
        "7 * * * *",
        "37 * * * *",
    ):
        raise _error(f"unexpected schedule cron expression: {schedule_expr!r}")
    created_utc = _utc(created_at, "created_at")
    expected_minute = 7 if schedule_expr == "7 * * * *" else 37

    # Find nominal candidate slot corresponding to created_utc
    if created_utc.minute >= expected_minute:
        candidate = created_utc.replace(minute=expected_minute, second=0, microsecond=0)
    else:
        candidate = (created_utc - dt.timedelta(hours=1)).replace(
            minute=expected_minute, second=0, microsecond=0
        )

    # Validate occurrence ambiguity
    if last_committed_utc is not None:
        last_utc = _utc(last_committed_utc, "last_committed_utc")
        if candidate <= last_utc:
            raise _error(
                f"derived nominal slot {candidate.isoformat()} is not after last committed slot {last_utc.isoformat()}"
            )
        # Check if more than one occurrence of this expression elapsed between last_committed and created_utc
        earlier_candidate = candidate - dt.timedelta(hours=1)
        if earlier_candidate > last_utc:
            raise _error(
                f"ambiguous schedule occurrence: multiple candidate slots ({earlier_candidate.isoformat()}, {candidate.isoformat()}) "
                f"occurred between last committed {last_utc.isoformat()} and trigger {created_utc.isoformat()}"
            )

    nominal = candidate
    nominal_iso = _utc_text(nominal)
    nominal_compact = nominal.strftime("%Y%m%dT%H%M%SZ")
    iso_year, iso_week, _ = nominal.isocalendar()
    release_tag = f"athena-fresh-holdout-evidence-{iso_year}-W{iso_week:02d}"
    success_asset_prefix = f"success-{nominal_compact}-run-"
    failure_asset_prefix = f"failure-{nominal_compact}-run-"
    return nominal, nominal_iso, release_tag, success_asset_prefix, failure_asset_prefix


def verify_and_extract_durable_state_archive(
    archive_path: Path,
    *,
    repository_root: Path | None = None,
    expected_sha256: str | None = None,
) -> None:
    """Verify archive integrity, member safety, and extract into state root."""
    repo = (repository_root or _repo_root()).resolve(strict=True)
    archive = Path(archive_path).resolve(strict=True)
    if archive.is_symlink() or not archive.is_file():
        raise _error("archive must be a regular non-symlink file")
    raw = archive.read_bytes()
    if not raw:
        raise _error("archive must be non-empty")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if type(expected_sha256) is not str or len(expected_sha256) != 64:
            raise _error("expected_sha256 must be a 64-char lowercase hex digest")
        if actual_sha != expected_sha256.lower():
            raise _error(
                f"archive SHA-256 digest mismatch: expected {expected_sha256}, got {actual_sha}"
            )

    import tarfile

    seen_names: set[str] = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name in seen_names:
                raise _error(f"duplicate archive member: {member.name}")
            seen_names.add(member.name)
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts:
                raise _error(f"forbidden archive member path: {member.name}")
            if (
                member.issym()
                or member.islnk()
                or member.ischr()
                or member.isblk()
                or member.isfifo()
                or member.isdev()
            ):
                raise _error(f"forbidden special archive member: {member.name}")
            if not member.name.startswith(
                (".cache/", "fresh-holdout-tick-receipt.json")
            ):
                raise _error(f"unexpected archive member root: {member.name}")
        tar.extractall(path=repo)

    state_root = repo / control.CONTROL_ROOT_RELATIVE
    if state_root.exists():
        paths = {
            "capture": state_root / control.CAPTURE_INDEX_FILENAME,
            "prediction": state_root / control.PREDICTION_JOURNAL_FILENAME,
            "identity": state_root / control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
            "settlement": state_root / control.SETTLEMENT_JOURNAL_FILENAME,
            "control": state_root / control.CONTROL_JOURNAL_FILENAME,
            "checkpoint": state_root / control.CHECKPOINT_FILENAME,
        }
        for name, path in paths.items():
            if path.exists():
                _regular(path)
                _rows(path)
        if paths["checkpoint"].exists():
            try:
                cp = json.loads(paths["checkpoint"].read_bytes())
                if type(cp) is not dict or cp.get("schema_version") != 1:
                    raise _error("checkpoint schema version invalid")
            except Exception as exc:
                raise _error("checkpoint JSON validation failed") from exc


def restore_predecessor_durable_state(
    *,
    prior_runs: Sequence[Mapping[str, Any]],
    current_run_id: int,
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    repository_root: Path | None = None,
) -> dt.datetime | None:
    """Restore authoritative state from the sole newest predecessor, or initialize Genesis.

    Returns last_committed_scheduled_for_utc (or None for Genesis).
    Fails closed on any ambiguity or validation failure.
    """
    repo = (repository_root or _repo_root()).resolve(strict=True)
    state_root = repo / control.CONTROL_ROOT_RELATIVE
    state_root.mkdir(parents=True, exist_ok=True)

    successful_prior = [
        r for r in prior_runs
        if r.get("id") != current_run_id and r.get("conclusion") == "success"
    ]
    successful_prior.sort(key=lambda r: int(r["id"]), reverse=True)

    if not successful_prior:
        return None

    newest = successful_prior[0]
    newest_id = int(newest["id"])

    try:
        art_data = get_run_artifacts(newest_id)
    except Exception as exc:
        raise _error(f"failed to fetch artifacts for newest predecessor run {newest_id}") from exc

    if type(art_data) is not dict or "artifacts" not in art_data or type(art_data["artifacts"]) is not list:
        raise _error(f"malformed artifact metadata for newest predecessor run {newest_id}")

    success_arts = [
        a for a in art_data["artifacts"]
        if type(a) is dict
        and type(a.get("name")) is str
        and a["name"].startswith("success-")
        and not a.get("expired", False)
    ]

    if len(success_arts) != 1:
        raise _error(
            f"newest predecessor run {newest_id} must have exactly one success artifact, found {len(success_arts)}"
        )

    art = success_arts[0]
    art_id = art.get("id")
    if type(art_id) is not int:
        raise _error(f"invalid artifact id in newest predecessor run {newest_id}")

    try:
        zip_bytes = download_artifact_zip(art_id)
    except Exception as exc:
        raise _error(f"failed to download artifact {art_id} for newest predecessor run {newest_id}") from exc

    if not zip_bytes:
        raise _error(f"downloaded empty artifact zip for newest predecessor run {newest_id}")

    expected_zip_digest = art.get("digest")
    if expected_zip_digest is not None and type(expected_zip_digest) is str:
        expected_hex = expected_zip_digest.split(":")[-1].lower()
        if len(expected_hex) == 64:
            actual_hex = hashlib.sha256(zip_bytes).hexdigest()
            if actual_hex != expected_hex:
                raise _error(
                    f"artifact zip digest mismatch for run {newest_id}: expected {expected_hex}, got {actual_hex}"
                )

    import io
    import tempfile
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except Exception as exc:
        raise _error(f"malformed zip archive from newest predecessor run {newest_id}") from exc

    tar_names = [
        name for name in zf.namelist()
        if name.startswith("success-") and name.endswith(".tar.gz")
    ]
    if len(tar_names) != 1:
        raise _error(
            f"artifact zip for run {newest_id} must contain exactly one success tar archive, found {len(tar_names)}"
        )

    tar_member = tar_names[0]
    tar_bytes = zf.read(tar_member)

    expected_tar_sha = None
    if "fresh-holdout-tick-receipt.json" in zf.namelist():
        try:
            receipt_data = json.loads(zf.read("fresh-holdout-tick-receipt.json"))
            if type(receipt_data) is dict and type(receipt_data.get("durable_asset_sha256")) is str:
                expected_tar_sha = receipt_data["durable_asset_sha256"]
        except Exception:
            pass

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp_tar:
        tmp_tar.write(tar_bytes)
        tmp_tar_path = Path(tmp_tar.name)

    try:
        verify_and_extract_durable_state_archive(
            tmp_tar_path,
            repository_root=repo,
            expected_sha256=expected_tar_sha,
        )
    finally:
        if tmp_tar_path.exists():
            tmp_tar_path.unlink()

    checkpoint_path = state_root / control.CHECKPOINT_FILENAME
    if not checkpoint_path.is_file():
        raise _error(f"predecessor state extracted from run {newest_id} is missing checkpoint.json")

    try:
        cp = json.loads(checkpoint_path.read_bytes())
        last_committed_text = cp["last_committed_scheduled_for_utc"]
        return _parse_utc(last_committed_text, "checkpoint last_committed_scheduled_for_utc")
    except Exception as exc:
        raise _error("failed to parse checkpoint from extracted predecessor state") from exc


def activation_runner_receipt() -> dict[str, Any]:
    verify_reviewed_activation_dependencies()
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_id": RUNNER_ID,
        "runner_state": RUNNER_STATE,
        "reviewed_control": {
            "pr150_merge_sha": PR150_MERGE_SHA,
            "pr150_merge_utc": PR150_MERGE_UTC_TEXT,
            "control_blob_sha": PR150_CONTROL_BLOB_SHA,
        },
        "pins": {
            "pr149_core_blob_sha": PR149_IMPLEMENTATION_BLOB_SHA,
            "capture_script_blob_sha": CAPTURE_SCRIPT_BLOB_SHA,
            "capture_contract_blob_sha": CAPTURE_CONTRACT_BLOB_SHA,
            "ordinary_ft_adapter_blob_sha": ORDINARY_FT_ADAPTER_BLOB_SHA,
            "pr119_executor_blob_sha": PR119_EXECUTOR_BLOB_SHA,
        },
        "runtime": {
            "network_requires_explicit_execute_flag": True,
            "settlement_precedes_prediction_construction_within_tick": True,
            "actual_capture_observed_at_authoritative": True,
            "nominal_schedule_time_is_observation_time": False,
            "scheduler_gap_backfill_authorized": False,
            "duplicate_committed_tick_network_replay_authorized": False,
            "working_capture_ring_per_request_date": WORKING_CAPTURE_LIMIT_PER_DATE,
            "release_upload_is_separate_required_durability_step": True,
        },
        "bootstrap": {
            "sha256": fresh.BOOTSTRAP_PROJECTION_SHA256,
            "size_bytes": fresh.BOOTSTRAP_PROJECTION_SIZE,
            "row_count": fresh.BOOTSTRAP_PROJECTION_ROWS,
        },
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": dict(_safety()),
    }


__all__ = [
    "CAPTURE_CONTRACT_BLOB_SHA",
    "CAPTURE_SCRIPT_BLOB_SHA",
    "CaptureEvidence",
    "FreshHoldoutActivationError",
    "NEXT_REQUIRED_BOUNDARY",
    "ORDINARY_FT_ADAPTER_BLOB_SHA",
    "PR119_EXECUTOR_BLOB_SHA",
    "PR149_IMPLEMENTATION_BLOB_SHA",
    "PR150_CONTROL_BLOB_SHA",
    "PR150_MERGE_SHA",
    "PR150_MERGE_UTC_TEXT",
    "RUNNER_ID",
    "RUNNER_STATE",
    "SAFETY_KEYS",
    "WORKING_CAPTURE_LIMIT_PER_DATE",
    "activation_runner_receipt",
    "execute_collection_tick",
    "resolve_nominal_schedule_slot",
    "restore_predecessor_durable_state",
    "validate_state_root",
    "verify_and_extract_durable_state_archive",
    "verify_reviewed_activation_dependencies",
]
