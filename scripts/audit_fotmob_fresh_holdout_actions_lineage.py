"""Read-only GitHub Actions lineage audit for the FotMob UTC-native xG fresh holdout.

The audit reads only GitHub metadata and evidence bytes already emitted by the reviewed
scheduled campaign. It never contacts a football provider, reruns a workflow, repairs a
Release, backfills a slot, or changes model/betting authority.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as activation
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import domain.fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage as failure_lineage
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


SCHEMA_VERSION = 1
AUDIT_ID = "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_ACTIONS_LINEAGE_AUDIT_V1"
WORKFLOW_NAME = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"
WORKFLOW_PATH = ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
CAMPAIGN_START_UTC = "2026-08-19T00:00:00Z"
FIRST_SLOT_UTC = "2026-08-19T00:07:00Z"
RUNNER_BLOB_SHA = "901ab137d6601a3485eac30da7e6bad7eeefa397"
MIRROR_BLOB_SHA = "ddabb6ae83cbe6c81c9264119a121a54715df960"
WORKFLOW_BLOB_SHA = "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
FAILURE_LINEAGE_BLOB_SHA = "2ae03405f63c0951eb61c4be0db1ba9dff318f21"
RUNNER_PATH = "domain/fotmob_utc_native_expected_goals_fresh_holdout_activation_runner.py"
MIRROR_PATH = "scripts/mirror_fotmob_fresh_holdout_release_receipt.py"
FAILURE_LINEAGE_PATH = (
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_failure_lineage.py"
)
CAMPAIGN_ORIGIN_RECOVERY_OPEN = "OPEN_GENESIS_PREFIX"
CAMPAIGN_ORIGIN_RECOVERY_CLOSED = "CLOSED_BY_COMPLETED_CAMPAIGN_EVIDENCE"
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_RE = re.compile(r"^(success|failure)-(\d{8}T\d{6}Z)-run-(\d+)\.tar\.gz$")
ALLOWED_CONTROL_EVENTS = frozenset(
    {
        "TICK_COMMITTED",
        "SCHEDULER_GAP_RANGE",
        "COUNT_ONLY_CLOSE_EVALUATION",
        "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
    }
)
SAFETY_KEYS = (
    "provider_network_acquisition_authorized",
    "provider_network_acquisition_performed_by_audit",
    "backfill_authorized",
    "model_approval_authorized",
    "production_authorized",
    "pricing_authorized",
    "selection_authorized",
    "bet_authorized",
)


class FreshHoldoutActionsLineageAuditError(RuntimeError):
    """Raised when GitHub lineage cannot be interpreted without guessing."""


class UnverifiedRunEvidenceError(RuntimeError):
    """Raised when one completed run lacks enough transport evidence to verify."""


def _error(message: str) -> FreshHoldoutActionsLineageAuditError:
    return FreshHoldoutActionsLineageAuditError(message)


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
        raise _error("audit canonical JSON serialization failed") from exc


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error(f"{label} must be non-empty bytes")
    duplicate = False

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicate
        out: dict[str, Any] = {}
        for key, value in values:
            if key in out:
                duplicate = True
            out[key] = value
        return out

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is malformed JSON") from exc
    if duplicate or type(value) is not dict:
        raise _error(f"{label} contains duplicate keys or is not an object")
    return value


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or value != value.strip() or not value.endswith("Z"):
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(f"{label} lacks timezone")
    return parsed.astimezone(dt.timezone.utc)


def _utc_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def verify_reviewed_dependencies(repository_root: Path | None = None) -> None:
    repo = (repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    for relative, digest, label in (
        (RUNNER_PATH, RUNNER_BLOB_SHA, "PR151 activation runner"),
        (MIRROR_PATH, MIRROR_BLOB_SHA, "PR168 receipt mirror"),
        (WORKFLOW_PATH, WORKFLOW_BLOB_SHA, "scheduled collection workflow"),
        (
            FAILURE_LINEAGE_PATH,
            FAILURE_LINEAGE_BLOB_SHA,
            "PR178 pre-acquisition failure lineage",
        ),
    ):
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            raise _error(f"{label} path is unavailable")
        if _blob_sha(path) != digest:
            raise _error(f"{label} blob changed")
    if activation.RUNNER_ID != "FOTMOB_UTC_NATIVE_XG_FRESH_HOLDOUT_ACTIVATION_RUNNER_V1":
        raise _error("reviewed runner identity changed")
    if control.HOLDOUT_START_UTC_TEXT != CAMPAIGN_START_UTC:
        raise _error("reviewed holdout origin changed")
    if control.CAPTURE_INTERVAL_MINUTES != 30 or control.CAPTURE_MINUTES_UTC != (7, 37):
        raise _error("reviewed schedule lattice changed")


def _slot_index(value: dt.datetime) -> int:
    first = _parse_utc(FIRST_SLOT_UTC, "first slot")
    value = value.astimezone(dt.timezone.utc)
    if value.second or value.microsecond or value.minute not in control.CAPTURE_MINUTES_UTC:
        raise _error("timestamp escaped reviewed exact :07/:37 boundary")
    seconds = int((value - first).total_seconds())
    step = control.CAPTURE_INTERVAL_MINUTES * 60
    if seconds < 0 or seconds % step:
        raise _error("timestamp escaped reviewed :07/:37 slot lattice")
    return seconds // step


def _slot_at(index: int) -> dt.datetime:
    if type(index) is not int or index < 0:
        raise _error("slot index must be non-negative integer")
    return _parse_utc(FIRST_SLOT_UTC, "first slot") + dt.timedelta(
        minutes=control.CAPTURE_INTERVAL_MINUTES * index
    )


def _validate_slot(value: Any, label: str) -> dt.datetime:
    parsed = _parse_utc(value, label)
    _slot_index(parsed)
    return parsed


def _canonical_rows(raw: bytes, label: str) -> tuple[dict[str, Any], ...]:
    if type(raw) is not bytes:
        raise _error(f"{label} must be exact bytes")
    if raw and not raw.endswith(b"\n"):
        raise _error(f"{label} contains torn final row")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        row = _parse_json(line, label)
        if _canonical(row) != line:
            raise _error(f"{label} contains non-canonical row")
        rows.append(row)
    return tuple(rows)


def _read_control_rows(
    extracted_root: Path, *, required: bool
) -> tuple[dict[str, Any], ...]:
    path = extracted_root / control.CONTROL_ROOT_RELATIVE / control.CONTROL_JOURNAL_FILENAME
    if not path.exists():
        if required:
            raise _error("durable archive is missing canonical control journal")
        return ()
    if not path.is_file() or path.is_symlink():
        raise _error("durable control journal is not a regular file")
    return _canonical_rows(path.read_bytes(), "control journal")


def validate_control_lineage(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[set[int], set[int]]:
    committed: set[int] = set()
    missing: set[int] = set()
    last_committed_index = -1
    last_gap_detected = -1
    for position, source in enumerate(rows):
        row = source if type(source) is dict else dict(source)
        event = row.get("event")
        if event not in ALLOWED_CONTROL_EVENTS:
            raise _error(
                f"control event {event!r} escaped reviewed vocabulary at row {position}"
            )
        if event == "TICK_COMMITTED":
            index = _slot_index(
                _validate_slot(row.get("scheduled_for_utc"), "committed slot")
            )
            if index <= last_committed_index or index in committed:
                raise _error("committed slots are duplicated or reordered")
            if index in missing:
                raise _error("committed slot appears inside a durable scheduler gap")
            if row.get("backfill_or_retrofill_performed") is not False:
                raise _error("committed tick changed no-backfill semantics")
            if row.get("nominal_schedule_time_used_as_observation_time") is not False:
                raise _error("committed tick used nominal schedule time as observation time")
            committed_at = _parse_utc(row.get("committed_at_utc"), "committed_at")
            if committed_at < _slot_at(index):
                raise _error("committed_at predates nominal scheduled slot")
            committed.add(index)
            last_committed_index = index
        elif event == "SCHEDULER_GAP_RANGE":
            if row.get("backfill_authorized") is not False:
                raise _error("scheduler gap changed backfill authority")
            detected = _slot_index(
                _validate_slot(
                    row.get("detected_at_scheduled_for_utc"), "gap detection slot"
                )
            )
            first = _slot_index(
                _validate_slot(row.get("first_missing_tick_utc"), "gap first slot")
            )
            last = _slot_index(
                _validate_slot(row.get("last_missing_tick_utc"), "gap last slot")
            )
            previous = row.get("previous_committed_tick_utc")
            expected_previous = None if last_committed_index < 0 else last_committed_index
            observed_previous = (
                None
                if previous is None
                else _slot_index(_validate_slot(previous, "gap previous committed slot"))
            )
            count = row.get("missing_tick_count")
            if (
                type(count) is not int
                or count < 1
                or last < first
                or count != last - first + 1
                or detected != last + 1
                or detected <= last_gap_detected
                or observed_previous != expected_previous
                or first != (0 if expected_previous is None else expected_previous + 1)
            ):
                raise _error(
                    "scheduler gap range/count/detection/lineage semantics changed"
                )
            gap_slots = set(range(first, last + 1))
            if gap_slots & committed:
                raise _error("scheduler gap overlaps an already committed slot")
            missing.update(gap_slots)
            last_gap_detected = detected
        elif event == "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED":
            if (
                row.get("tick_committed") is not False
                or row.get("backfill_authorized") is not False
            ):
                raise _error("uncommitted qualification failure changed authority")
        elif event == "COUNT_ONLY_CLOSE_EVALUATION":
            if row.get("outcome_or_performance_input_used") is not False:
                raise _error("count-only close evaluation used outcome/performance input")
    return committed, missing


def _asset_by_name(
    release: Mapping[str, Any], name: str
) -> Mapping[str, Any] | None:
    assets = release.get("assets")
    if type(assets) is not list:
        raise _error("GitHub Release assets payload is malformed")
    matches = [
        asset for asset in assets if type(asset) is dict and asset.get("name") == name
    ]
    if len(matches) > 1:
        raise _error(f"GitHub Release duplicated asset name {name}")
    return None if not matches else matches[0]


def _release_state(
    *,
    verified: Mapping[str, Any],
    release: Mapping[str, Any],
    download_release_asset: Callable[[int], bytes],
) -> str:
    archive = _asset_by_name(release, verified["artifact_name"])
    if archive is None or archive.get("state") != "uploaded":
        return "RELEASE_DURABILITY_UNVERIFIED"
    if (
        archive.get("size") != verified["archive_size_bytes"]
        or type(archive.get("id")) is not int
    ):
        return "RELEASE_DURABILITY_UNVERIFIED"
    try:
        release_archive = download_release_asset(archive["id"])
    except Exception:
        return "RELEASE_DURABILITY_UNVERIFIED"
    if (
        release_archive != verified["archive_bytes"]
        or hashlib.sha256(release_archive).hexdigest() != verified["archive_sha256"]
    ):
        return "RELEASE_DURABILITY_UNVERIFIED"

    sidecar = _asset_by_name(release, verified["receipt_name"])
    if sidecar is None:
        return "RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING"
    if (
        sidecar.get("state") != "uploaded"
        or sidecar.get("size") != verified["receipt_size_bytes"]
        or type(sidecar.get("id")) is not int
    ):
        return "RELEASE_DURABILITY_UNVERIFIED"
    try:
        release_receipt = download_release_asset(sidecar["id"])
    except Exception:
        return "RELEASE_DURABILITY_UNVERIFIED"
    if release_receipt != verified["receipt_bytes"]:
        return "RELEASE_DURABILITY_UNVERIFIED"
    return "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED"


def _extract_control_rows(
    archive_bytes: bytes,
    expected_sha256: str,
    *,
    require_control: bool,
) -> tuple[dict[str, Any], ...]:
    if hashlib.sha256(archive_bytes).hexdigest() != expected_sha256:
        raise _error("archive bytes changed before durable-state extraction")
    with tempfile.TemporaryDirectory(prefix="athena-fresh-holdout-audit-") as temporary:
        root = Path(temporary)
        archive_path = root / "evidence.tar.gz"
        archive_path.write_bytes(archive_bytes)
        activation.verify_and_extract_durable_state_archive(
            archive_path,
            repository_root=root,
            expected_sha256=expected_sha256,
        )
        return _read_control_rows(root, required=require_control)


def _run_is_collection_candidate(run: Mapping[str, Any]) -> bool:
    path = run.get("path")
    path_matches = type(path) is str and (
        path == WORKFLOW_PATH or path.startswith(WORKFLOW_PATH + "@")
    )
    return (
        run.get("name") == WORKFLOW_NAME
        and run.get("event") == "schedule"
        and run.get("head_branch") == "main"
        and path_matches
    )


def _candidate_artifact(
    artifacts_payload: Mapping[str, Any], run_id: int
) -> Mapping[str, Any]:
    artifacts = artifacts_payload.get("artifacts")
    if type(artifacts) is not list:
        raise UnverifiedRunEvidenceError("workflow artifacts payload is malformed")
    values = [
        item
        for item in artifacts
        if type(item) is dict
        and item.get("expired") is False
        and type(item.get("name")) is str
        and ARTIFACT_RE.fullmatch(item["name"]) is not None
        and item["name"].endswith(f"-run-{run_id}.tar.gz")
    ]
    if len(values) != 1:
        raise UnverifiedRunEvidenceError(
            "completed campaign run does not expose exactly one canonical unexpired artifact"
        )
    if type(values[0].get("id")) is not int:
        raise UnverifiedRunEvidenceError("Actions artifact id is invalid")
    return values[0]


def _is_exact_zero_artifact_payload(artifacts_payload: Mapping[str, Any]) -> bool:
    """Return true only for the exact transport shape admitted by PR178 proof."""

    return (
        type(artifacts_payload) is dict
        and type(artifacts_payload.get("artifacts")) is list
        and not artifacts_payload["artifacts"]
    )


def _normal_run_record(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": run.get("conclusion"),
        "evidence_state": "UNVERIFIED",
        "nominal_slot_utc": None,
        "tick_committed": None,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_CHECKED",
        "verification_error": None,
        "campaign_origin_recovery_state_before": None,
        "campaign_origin_recovery_state_after": None,
    }


def _validate_optional_rich_failure_receipt(
    receipt: Mapping[str, Any], nominal: dt.datetime
) -> None:
    if "schema_version" in receipt and receipt.get("schema_version") != 1:
        raise _error("failure receipt schema identity changed")
    if "runner_id" in receipt and receipt.get("runner_id") != activation.RUNNER_ID:
        raise _error("failure receipt runner identity changed")
    if "scheduled_for_utc" in receipt:
        if _validate_slot(receipt.get("scheduled_for_utc"), "failure scheduled_for") != nominal:
            raise _error("failure receipt scheduled_for disagrees with nominal slot")
    if "safety" in receipt:
        safety = receipt.get("safety")
        if (
            type(safety) is not dict
            or set(safety) != set(activation.SAFETY_KEYS)
            or any(value is not False for value in safety.values())
        ):
            raise _error("failure receipt downstream safety authority changed")


def audit_actions_lineage(
    *,
    repository: str,
    expected_main_sha: str,
    get_main_ref: Callable[[], Mapping[str, Any]],
    get_runs_page: Callable[[int, int], Mapping[str, Any]],
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_release: Callable[[str], Mapping[str, Any]],
    download_release_asset: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]] | None = None,
    verify_dependencies: bool = True,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Audit existing GitHub evidence without mutating GitHub or provider state."""
    if (
        type(repository) is not str
        or repository.count("/") != 1
        or repository != repository.strip()
    ):
        raise _error("repository must be exact owner/name")
    if type(expected_main_sha) is not str or SHA40_RE.fullmatch(expected_main_sha) is None:
        raise _error("expected_main_sha must be lowercase 40-hex")
    if verify_dependencies:
        verify_reviewed_dependencies(repository_root)

    main = get_main_ref()
    observed_main = (
        main.get("object", {}).get("sha")
        if type(main.get("object")) is dict
        else main.get("sha")
    )
    if observed_main != expected_main_sha:
        raise _error(
            f"current main {observed_main!r} differs from expected {expected_main_sha!r}"
        )

    campaign_start = _parse_utc(CAMPAIGN_START_UTC, "campaign start")
    runs: list[Mapping[str, Any]] = []
    page = 1
    per_page = 100
    while True:
        payload = get_runs_page(page, per_page)
        values = payload.get("workflow_runs")
        if type(values) is not list:
            raise _error("workflow runs response is malformed")
        if not values:
            break
        runs.extend(value for value in values if type(value) is dict)
        oldest: dt.datetime | None = None
        for value in values:
            if type(value) is dict and type(value.get("created_at")) is str:
                try:
                    timestamp = _parse_utc(value["created_at"], "run created_at")
                except FreshHoldoutActionsLineageAuditError:
                    continue
                oldest = timestamp if oldest is None or timestamp < oldest else oldest
        if len(values) < per_page or (oldest is not None and oldest < campaign_start):
            break
        page += 1
        if page > 100:
            raise _error("workflow run pagination exceeded reviewed bound")

    candidates: list[Mapping[str, Any]] = []
    for run in runs:
        if not _run_is_collection_candidate(run):
            continue
        created = _parse_utc(run.get("created_at"), "run created_at")
        run_id = run.get("id")
        if type(run_id) is not int or run_id < 1:
            raise _error("campaign run id is invalid")
        if created >= campaign_start:
            candidates.append(run)
    candidates.sort(
        key=lambda row: (
            _parse_utc(row["created_at"], "run created_at"),
            row["id"],
        )
    )

    records: list[dict[str, Any]] = []
    verified_by_slot: dict[int, dict[str, Any]] = {}
    journals_by_slot: dict[int, tuple[dict[str, Any], ...]] = {}
    unverified_completed = 0
    incomplete_runs = 0
    verified_failures = 0
    verified_preacquisition_control_failures = 0
    release_partial = False
    campaign_origin_recovery_state = CAMPAIGN_ORIGIN_RECOVERY_OPEN

    for run in candidates:
        record = _normal_run_record(run)
        record["campaign_origin_recovery_state_before"] = (
            campaign_origin_recovery_state
        )
        run_id = run["id"]
        if run.get("status") != "completed":
            incomplete_runs += 1
            record["evidence_state"] = "INCOMPLETE_NOT_EVIDENCE"
            record["campaign_origin_recovery_state_after"] = (
                campaign_origin_recovery_state
            )
            records.append(record)
            continue
        try:
            head_sha = run.get("head_sha")
            if type(head_sha) is not str or SHA40_RE.fullmatch(head_sha) is None:
                campaign_origin_recovery_state = CAMPAIGN_ORIGIN_RECOVERY_CLOSED
                raise UnverifiedRunEvidenceError(
                    "completed campaign run head_sha is not exact lowercase 40-hex"
                )
            recovery_was_open = (
                campaign_origin_recovery_state == CAMPAIGN_ORIGIN_RECOVERY_OPEN
            )
            # Pessimistically close before any completed-run transport read.
            # The same run may retain the open prefix only after exact PR178
            # zero-artifact proof succeeds; no exception may accidentally leave
            # later Genesis recovery open.
            campaign_origin_recovery_state = CAMPAIGN_ORIGIN_RECOVERY_CLOSED
            artifacts_payload = get_run_artifacts(run_id)
            zero_artifact_payload = _is_exact_zero_artifact_payload(
                artifacts_payload
            )
            if zero_artifact_payload:
                if not recovery_was_open:
                    raise _error(
                        "campaign-origin pre-acquisition recovery cannot classify "
                        f"run {run_id} after its chronological prefix closed"
                    )
                if get_run_jobs is None:
                    raise UnverifiedRunEvidenceError(
                        "zero-artifact pre-acquisition proof requires GitHub jobs metadata"
                    )
                try:
                    proved_preacquisition = (
                        failure_lineage._prove_preacquisition_control_failure(
                            run,
                            artifacts_payload,
                            get_run_jobs,
                        )
                    )
                except failure_lineage.FreshHoldoutFailureLineageError as exc:
                    raise _error(
                        "pre-acquisition control-failure proof failed for run "
                        f"{run_id}: {exc}"
                    ) from exc
                if not proved_preacquisition:
                    raise UnverifiedRunEvidenceError(
                        "zero-artifact run does not match exact reviewed "
                        "pre-acquisition failure shape"
                    )
                verified_preacquisition_control_failures += 1
                record["evidence_state"] = (
                    "VERIFIED_PREACQUISITION_CONTROL_FAILURE"
                )
                campaign_origin_recovery_state = CAMPAIGN_ORIGIN_RECOVERY_OPEN
                record["verification_error"] = None
                record["campaign_origin_recovery_state_after"] = (
                    campaign_origin_recovery_state
                )
                records.append(record)
                continue

            # Any other completed in-campaign run closes the Genesis prefix,
            # whether its canonical evidence later verifies or fails closed.
            artifact = _candidate_artifact(artifacts_payload, run_id)
            zip_bytes = download_artifact_zip(artifact["id"])
            zip_sha = mirror.verify_actions_artifact_zip_digest(
                zip_bytes, artifact.get("digest")
            )
            verified = mirror.verify_actions_artifact_bundle(
                run_id=run_id,
                artifact_name=artifact["name"],
                zip_bytes=zip_bytes,
            )
            verified["actions_artifact_zip_sha256"] = zip_sha
            receipt = _parse_json(verified["receipt_bytes"], "canonical tick receipt")
            nominal = _validate_slot(
                receipt.get("nominal_scheduled_for_utc"), "receipt nominal slot"
            )
            expected_schedule = "7 * * * *" if nominal.minute == 7 else "37 * * * *"
            if receipt.get("workflow_event_schedule") != expected_schedule:
                raise _error("canonical tick receipt cron identity changed")
            reconcile_outcome = receipt.get("failure_lineage_reconcile_outcome")
            if type(reconcile_outcome) is not str or not reconcile_outcome:
                raise _error("canonical tick receipt reconcile outcome is missing")
            run_created = _parse_utc(run.get("created_at"), "run created_at")
            if run_created < nominal:
                raise _error("workflow run created_at predates its proven nominal slot")
            slot_index = _slot_index(nominal)
            if slot_index in verified_by_slot:
                raise _error("multiple verified workflow runs map to one nominal slot")

            artifact_match = ARTIFACT_RE.fullmatch(artifact["name"])
            if artifact_match is None:
                raise _error("verified artifact name changed after verification")
            kind = artifact_match.group(1)
            tick_committed = receipt.get("tick_committed")

            if kind == "success":
                if (
                    receipt.get("schema_version") != 1
                    or receipt.get("runner_id") != activation.RUNNER_ID
                ):
                    raise _error("success receipt runner/schema identity changed")
                if _validate_slot(
                    receipt.get("scheduled_for_utc"), "success scheduled_for"
                ) != nominal:
                    raise _error("success receipt scheduled_for disagrees with nominal slot")
                safety = receipt.get("safety")
                if (
                    type(safety) is not dict
                    or set(safety) != set(activation.SAFETY_KEYS)
                    or any(value is not False for value in safety.values())
                ):
                    raise _error("success receipt downstream safety authority changed")
            else:
                _validate_optional_rich_failure_receipt(receipt, nominal)

            rows = _extract_control_rows(
                verified["archive_bytes"],
                verified["archive_sha256"],
                require_control=(kind == "success"),
            )
            committed, missing = validate_control_lineage(rows)
            unresolved_prior = set(range(slot_index)) - committed - missing
            if unresolved_prior and kind == "success":
                raise _error(
                    "verified success cumulative state leaves earlier nominal slots unresolved"
                )

            if kind == "success":
                if tick_committed is not True or slot_index not in committed:
                    raise _error("verified success run lacks matching committed control row")
                commit_rows = [
                    row
                    for row in rows
                    if row.get("event") == "TICK_COMMITTED"
                    and _slot_index(
                        _validate_slot(row.get("scheduled_for_utc"), "commit binding slot")
                    )
                    == slot_index
                ]
                if len(commit_rows) != 1:
                    raise _error("success slot does not have one exact committed row")
                commit_row = commit_rows[0]
                if (
                    commit_row.get("durable_release_tag") != verified["release_tag"]
                    or commit_row.get("durable_asset_name") != artifact["name"]
                ):
                    raise _error("success commit row durable identity disagrees with receipt")
            else:
                if tick_committed is not False or slot_index in committed:
                    raise _error("verified failure run became committed")
                verified_failures += 1

            try:
                release = get_release(verified["release_tag"])
                release_state = _release_state(
                    verified=verified,
                    release=release,
                    download_release_asset=download_release_asset,
                )
            except Exception:
                release_state = "RELEASE_DURABILITY_UNVERIFIED"
            if release_state != "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED":
                release_partial = True
            record.update(
                {
                    "evidence_state": (
                        "VERIFIED_ACTIONS_LINEAGE"
                        if kind == "success"
                        else "VERIFIED_UNCOMMITTED_ATTEMPT"
                    ),
                    "nominal_slot_utc": _utc_text(nominal),
                    "tick_committed": tick_committed,
                    "archive_name": artifact["name"],
                    "archive_sha256": verified["archive_sha256"],
                    "actions_artifact_zip_sha256": zip_sha,
                    "release_state": release_state,
                    "verification_error": None,
                }
            )
            verified_by_slot[slot_index] = record
            journals_by_slot[slot_index] = rows
        except UnverifiedRunEvidenceError as exc:
            unverified_completed += 1
            record["verification_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        except FreshHoldoutActionsLineageAuditError:
            raise
        except Exception as exc:
            unverified_completed += 1
            record["verification_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        record["campaign_origin_recovery_state_after"] = (
            campaign_origin_recovery_state
        )
        records.append(record)

    ordered_slots = sorted(journals_by_slot)
    previous: tuple[dict[str, Any], ...] = ()
    for index in ordered_slots:
        current = journals_by_slot[index]
        if len(current) < len(previous) or current[: len(previous)] != previous:
            raise _error(
                "verified cumulative control journal is not append-only across runs"
            )
        previous = current

    if ordered_slots:
        latest_slot = ordered_slots[-1]
        committed, missing = validate_control_lineage(journals_by_slot[latest_slot])
        latest_nominal = _slot_at(latest_slot)
    else:
        latest_slot = -1
        committed, missing = set(), set()
        latest_nominal = None

    failed_attempts = {
        index
        for index, record in verified_by_slot.items()
        if record.get("tick_committed") is False
    }
    slot_rows: list[dict[str, Any]] = []
    if latest_slot >= 0:
        for index in range(latest_slot + 1):
            run_record = verified_by_slot.get(index)
            if index in committed:
                state = "COMMITTED"
            elif index in missing:
                state = "DURABLY_RECORDED_MISSING"
            elif index in failed_attempts:
                state = "VERIFIED_UNCOMMITTED_ATTEMPT"
            else:
                state = "UNRESOLVED"
            slot_rows.append(
                {
                    "slot_utc": _utc_text(_slot_at(index)),
                    "state": state,
                    "run_id": None if run_record is None else run_record["run_id"],
                    "head_sha": None if run_record is None else run_record.get("head_sha"),
                }
            )

    first_record = verified_by_slot.get(0)
    if 0 in committed:
        first_status = "FIRST_SLOT_COMMITTED"
    elif 0 in missing:
        first_status = "FIRST_SLOT_DURABLY_RECORDED_MISSING"
    elif 0 in failed_attempts:
        first_status = "FIRST_SLOT_VERIFIED_UNCOMMITTED_ATTEMPT"
    else:
        first_status = "FIRST_SLOT_UNRESOLVED"

    unresolved_slots = sum(
        1 for row in slot_rows if row["state"] == "UNRESOLVED"
    )
    verified_completed = len(verified_by_slot)
    if (
        verified_completed == 0
        and verified_preacquisition_control_failures == 0
        and unverified_completed == 0
        and incomplete_runs == 0
    ):
        audit_state = "NO_COMPLETED_CAMPAIGN_EVIDENCE"
    elif (
        unverified_completed
        or incomplete_runs
        or release_partial
        or unresolved_slots
        or verified_completed == 0
    ):
        audit_state = "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"
    else:
        audit_state = "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN"

    result = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": AUDIT_ID,
        "audit_state": audit_state,
        "repository": repository,
        "expected_main_sha": expected_main_sha,
        "observed_main_sha": observed_main,
        "collection_workflow_name": WORKFLOW_NAME,
        "collection_workflow_path": WORKFLOW_PATH,
        "campaign_start_utc": CAMPAIGN_START_UTC,
        "first_nominal_slot_utc": FIRST_SLOT_UTC,
        "first_nominal_slot_status": first_status,
        "first_nominal_slot_run_id": None if first_record is None else first_record["run_id"],
        "first_nominal_slot_head_sha": (
            None if first_record is None else first_record.get("head_sha")
        ),
        "latest_verified_nominal_slot_utc": (
            None if latest_nominal is None else _utc_text(latest_nominal)
        ),
        "latest_verified_run_id": (
            None if latest_slot < 0 else verified_by_slot[latest_slot]["run_id"]
        ),
        "verified_completed_run_count": verified_completed,
        "verified_preacquisition_control_failure_count": (
            verified_preacquisition_control_failures
        ),
        "unverified_completed_run_count": unverified_completed,
        "incomplete_run_count": incomplete_runs,
        "verified_failure_count": verified_failures,
        "committed_slot_count": len(committed),
        "durably_recorded_missing_slot_count": len(missing),
        "unresolved_slot_count": unresolved_slots,
        "campaign_origin_recovery_state": campaign_origin_recovery_state,
        "runs": records,
        "slots": slot_rows,
        "safety": {key: False for key in SAFETY_KEYS},
    }
    _canonical(result)
    return result


def _gh_json(endpoint: str) -> dict[str, Any]:
    try:
        raw = subprocess.check_output(["gh", "api", endpoint])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _error(f"GitHub API request failed: {endpoint}") from exc
    return _parse_json(raw, f"GitHub API response {endpoint}")


def _gh_download(endpoint: str) -> bytes:
    try:
        return subprocess.check_output(
            ["gh", "api", "-H", "Accept: application/octet-stream", endpoint]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _error(f"GitHub binary download failed: {endpoint}") from exc


def _cli_audit(repository: str, expected_main_sha: str) -> dict[str, Any]:
    if not os.environ.get("GH_TOKEN"):
        raise _error("GH_TOKEN is required for GitHub-only lineage audit")

    def get_main_ref() -> Mapping[str, Any]:
        return _gh_json(f"/repos/{repository}/git/ref/heads/main")

    def get_runs_page(page: int, per_page: int) -> Mapping[str, Any]:
        return _gh_json(
            f"/repos/{repository}/actions/workflows/"
            f"fotmob-utc-native-xg-fresh-holdout.yml/runs?per_page={per_page}&page={page}"
        )

    def get_run_artifacts(run_id: int) -> Mapping[str, Any]:
        return _gh_json(f"/repos/{repository}/actions/runs/{run_id}/artifacts")

    def get_run_jobs(run_id: int) -> Mapping[str, Any]:
        return _gh_json(
            f"/repos/{repository}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
        )

    def download_artifact_zip(artifact_id: int) -> bytes:
        return _gh_download(f"/repos/{repository}/actions/artifacts/{artifact_id}/zip")

    def get_release(tag: str) -> Mapping[str, Any]:
        return _gh_json(f"/repos/{repository}/releases/tags/{tag}")

    def download_release_asset(asset_id: int) -> bytes:
        return _gh_download(f"/repos/{repository}/releases/assets/{asset_id}")

    return audit_actions_lineage(
        repository=repository,
        expected_main_sha=expected_main_sha,
        get_main_ref=get_main_ref,
        get_runs_page=get_runs_page,
        get_run_artifacts=get_run_artifacts,
        download_artifact_zip=download_artifact_zip,
        get_release=get_release,
        download_release_asset=download_release_asset,
        get_run_jobs=get_run_jobs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only GitHub Actions lineage audit for the FotMob UTC-native xG "
            "fresh holdout."
        )
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-main-sha", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = _cli_audit(args.repository, args.expected_main_sha)
        raw = _canonical(result)
        if args.output:
            output = Path(args.output)
            if output.exists() or output.is_symlink():
                raise _error("audit output is no-overwrite")
            with output.open("xb") as handle:
                handle.write(raw)
        print(raw.decode("utf-8"), end="")
        return 0
    except FreshHoldoutActionsLineageAuditError as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
