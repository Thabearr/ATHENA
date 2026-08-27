"""Verify a cumulative PR151 success archive as an exact fresh-history prefix.

This module is intentionally only the archive-proof half of the current-history
boundary.  It proves that one reviewed PR151 success Actions artifact contains a
canonical tick receipt, an exact cumulative durable state archive, a checkpoint
consistent with every append-only journal, and an exact tuple of reviewed settled
predictions that can be replayed through PR244.

It does NOT by itself prove that the supplied success artifact is the latest
committed success state applicable to the current FotMob source observation.  A
separate latest-applicable selection proof must be attached before any caller may
claim complete-current-history state.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import tempfile
import types
from collections.abc import Mapping
from typing import Any

import domain.current_fotmob_utc_native_shadow_prediction as shadow
import domain.fotmob_utc_native_expected_goals_fresh_holdout as fresh
import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as runner
import domain.fotmob_utc_native_expected_goals_fresh_holdout_collection_control as control
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
import scripts.replay_fotmob_utc_native_xg_fresh_holdout_confirmation as terminal_replay

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-durable-fresh-history-prefix-v1"
STATUS = "VERIFIED_PR151_CUMULATIVE_SUCCESS_PREFIX_NOT_LATEST_APPLICABLE"
NEXT_REQUIRED_BOUNDARY = "LATEST_APPLICABLE_PR151_SUCCESS_PREFIX_SELECTION_REQUIRED"
SOURCE_SCOPE = "PR151_CUMULATIVE_SUCCESS_ACTIONS_ARTIFACT_AND_CANONICAL_TICK_RECEIPT"

_SUCCESS_ARTIFACT_RE = re.compile(r"^success-(\d{8}T\d{6}Z)-run-(\d+)\.tar\.gz$")
_DOWNSTREAM_AUTHORITY_KEYS = frozenset(
    {
        "complete_current_fresh_history",
        "production_model",
        "score_matrix",
        "probability",
        "phase6",
        "pricing",
        "selection",
        "sportybet_execution",
        "bet",
    }
)


class CurrentDurableFreshHistoryPrefixError(ValueError):
    """Raised when one cumulative success prefix cannot be re-proved exactly."""


def _error(message: str) -> CurrentDurableFreshHistoryPrefixError:
    return CurrentDurableFreshHistoryPrefixError(message)


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
        raise _error("canonical serialization failed") from exc


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


def _utc_text(value: dt.datetime) -> str:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error("timestamp must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _false_authority() -> Mapping[str, bool]:
    return types.MappingProxyType(
        {key: False for key in sorted(_DOWNSTREAM_AUTHORITY_KEYS)}
    )


def _validate_false_authority(value: Any) -> Mapping[str, bool]:
    expected = _false_authority()
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise _error("authority keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not False:
            raise _error(f"authority[{key!r}] changed reviewed state")
    return expected


def _exact_receipt(
    raw: bytes,
    *,
    run_id: int,
    artifact_name: str,
    source_observed_at: dt.datetime,
) -> tuple[dict[str, Any], dt.datetime, dt.datetime]:
    try:
        receipt = json.loads(raw, object_pairs_hook=terminal_replay._no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("tick receipt is malformed JSON") from exc
    if type(receipt) is not dict or _canonical(receipt) != raw:
        raise _error("tick receipt must be canonical compact sorted-key JSON")
    if set(receipt) != terminal_replay.TERMINAL_RECEIPT_KEYS:
        raise _error("tick receipt key set changed from reviewed PR151 workflow schema")

    match = _SUCCESS_ARTIFACT_RE.fullmatch(artifact_name)
    if match is None or int(match.group(2)) != run_id:
        raise _error("success artifact identity disagrees with workflow run")
    compact = match.group(1)

    if receipt.get("schema_version") != 1:
        raise _error("tick receipt schema version changed")
    if receipt.get("runner_id") != runner.RUNNER_ID:
        raise _error("tick receipt runner id changed")
    if receipt.get("runner_state") != runner.RUNNER_STATE:
        raise _error("tick receipt runner state changed")
    if receipt.get("workflow_run_id") != run_id:
        raise _error("tick receipt workflow run id changed")
    if receipt.get("durable_asset_name") != artifact_name:
        raise _error("tick receipt durable asset name changed")
    if receipt.get("tick_exit_code") != 0 or receipt.get("tick_committed") is not True:
        raise _error("success prefix requires a committed zero-exit tick")
    if receipt.get("failure_lineage_reconcile_outcome") != "skipped":
        raise _error("success prefix changed failure-lineage reconcile outcome")
    if receipt.get("next_required_boundary") != runner.NEXT_REQUIRED_BOUNDARY:
        raise _error("tick receipt next boundary changed")

    safety = receipt.get("safety")
    if type(safety) is not dict or set(safety) != set(runner.SAFETY_KEYS):
        raise _error("tick receipt safety vocabulary changed")
    if any(type(item) is not bool or item is not False for item in safety.values()):
        raise _error("tick receipt changed downstream authority")

    nominal = _utc(receipt.get("nominal_scheduled_for_utc"), "nominal scheduled time")
    scheduled = _utc(receipt.get("scheduled_for_utc"), "runner scheduled time")
    if nominal != scheduled:
        raise _error("tick receipt nominal and runner scheduled times differ")
    if nominal.second or nominal.microsecond or nominal.minute not in control.CAPTURE_MINUTES_UTC:
        raise _error("tick receipt scheduled time escaped reviewed :07/:37 lattice")
    if nominal.strftime("%Y%m%dT%H%M%SZ") != compact:
        raise _error("success artifact nominal slot disagrees with tick receipt")
    expected_cron = "7 * * * *" if nominal.minute == 7 else "37 * * * *"
    if receipt.get("workflow_event_schedule") != expected_cron:
        raise _error("tick receipt cron identity changed")

    committed_at = _utc(receipt.get("committed_at_utc"), "receipt committed_at")
    if committed_at < nominal:
        raise _error("tick receipt committed_at predates nominal schedule")
    source_utc = source_observed_at.astimezone(dt.timezone.utc)
    if committed_at > source_utc:
        raise _error("durable prefix was committed after the current source observation")
    return receipt, nominal, committed_at


def _checkpoint(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=terminal_replay._no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error("checkpoint is malformed JSON") from exc
    expected_keys = {
        "schema_version",
        "runner_id",
        "last_committed_scheduled_for_utc",
        "phase",
        "capture_count",
        "prediction_count",
        "settled_or_terminal_count",
        "control_event_count",
        "durable_release_tag",
        "durable_asset_name",
    }
    if type(value) is not dict or set(value) != expected_keys or _canonical(value) != raw:
        raise _error("checkpoint changed exact canonical schema")
    if value.get("schema_version") != 1 or value.get("runner_id") != runner.RUNNER_ID:
        raise _error("checkpoint runner identity changed")
    return value


def _read_state_rows(root: Path, name: str) -> tuple[dict[str, Any], ...]:
    path = root / name
    try:
        return runner._rows(path)
    except Exception as exc:
        raise _error(f"{name} failed canonical PR151 replay") from exc


@dataclasses.dataclass(frozen=True)
class CurrentDurableFreshHistoryPrefixSourceBundle:
    current_bootstrap: Any
    source_raw_json: bytes
    source_manifest: Any
    legacy_bootstrap_projection_raw: bytes
    workflow_run_id: int
    artifact_name: str
    artifact_zip_bytes: bytes
    artifact_zip_metadata_digest: str

    def __post_init__(self) -> None:
        if type(self.workflow_run_id) is not int or self.workflow_run_id < 1:
            raise _error("workflow_run_id must be exact positive integer")
        if type(self.artifact_name) is not str or _SUCCESS_ARTIFACT_RE.fullmatch(self.artifact_name) is None:
            raise _error("artifact_name must be canonical PR151 success asset name")
        if type(self.artifact_zip_bytes) is not bytes or not self.artifact_zip_bytes:
            raise _error("artifact_zip_bytes must be non-empty exact bytes")
        if type(self.artifact_zip_metadata_digest) is not str:
            raise _error("artifact_zip_metadata_digest must be exact text")
        if type(self.source_raw_json) is not bytes or not self.source_raw_json:
            raise _error("source_raw_json must be non-empty exact bytes")
        if type(self.legacy_bootstrap_projection_raw) is not bytes:
            raise _error("legacy bootstrap projection must be exact bytes")
        # PR244 remains the reviewed exact-type/source-ancestry verifier for the
        # current bootstrap/raw/manifest/PR119 inputs.  The durable layer never
        # creates a parallel FotMob authority.
        try:
            shadow.build_current_fotmob_utc_native_shadow_prediction_handoff(
                current_bootstrap=self.current_bootstrap,
                source_raw_json=self.source_raw_json,
                source_manifest=self.source_manifest,
                legacy_bootstrap_projection_raw=self.legacy_bootstrap_projection_raw,
                reviewed_fresh_settlements=(),
            )
        except Exception as exc:
            raise _error("current PR244 source ancestry failed exact replay") from exc

    @property
    def source_observed_at(self) -> dt.datetime:
        value = getattr(self.source_manifest, "observed_at", None)
        if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
            raise _error("current source manifest lost observed_at authority")
        return value.astimezone(dt.timezone.utc)


@dataclasses.dataclass(frozen=True)
class _DerivedPrefix:
    artifact_zip_sha256: str
    archive_sha256: str
    archive_size_bytes: int
    receipt_sha256: str
    nominal_scheduled_for_utc: dt.datetime
    committed_at_utc: dt.datetime
    checkpoint_sha256: str
    settlement_journal_sha256: str
    settlement_journal_row_count: int
    reviewed_fresh_settlements: tuple[fresh.SettledFreshPrediction, ...]
    reviewed_legacy_update_count: int
    shadow_handoff: shadow.CurrentUtcNativeShadowPredictionHandoff


def _derive(source: CurrentDurableFreshHistoryPrefixSourceBundle) -> _DerivedPrefix:
    try:
        zip_sha = mirror.verify_actions_artifact_zip_digest(
            source.artifact_zip_bytes,
            source.artifact_zip_metadata_digest,
        )
        verified = mirror.verify_actions_artifact_bundle(
            run_id=source.workflow_run_id,
            artifact_name=source.artifact_name,
            zip_bytes=source.artifact_zip_bytes,
        )
    except Exception as exc:
        raise _error("PR168 Actions artifact/receipt commitment verification failed") from exc

    receipt, nominal, committed_at = _exact_receipt(
        verified["receipt_bytes"],
        run_id=source.workflow_run_id,
        artifact_name=source.artifact_name,
        source_observed_at=source.source_observed_at,
    )

    archive_raw = verified["archive_bytes"]
    if _sha(archive_raw) != verified["archive_sha256"]:
        raise _error("verified archive digest changed after PR168 replay")

    with tempfile.TemporaryDirectory(prefix="athena-pr245-") as directory:
        repo = Path(directory)
        archive_path = repo / source.artifact_name
        archive_path.write_bytes(archive_raw)
        try:
            runner.verify_and_extract_durable_state_archive(
                archive_path,
                repository_root=repo,
                expected_sha256=verified["archive_sha256"],
            )
        except Exception as exc:
            raise _error("PR151 durable archive failed hardened extraction/replay") from exc

        state_root = repo / control.CONTROL_ROOT_RELATIVE
        checkpoint_path = state_root / control.CHECKPOINT_FILENAME
        if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
            raise _error("cumulative success prefix is missing checkpoint")
        checkpoint_raw = checkpoint_path.read_bytes()
        cp = _checkpoint(checkpoint_raw)

        capture_rows = _read_state_rows(state_root, control.CAPTURE_INDEX_FILENAME)
        prediction_rows = _read_state_rows(state_root, control.PREDICTION_JOURNAL_FILENAME)
        identity_rows = _read_state_rows(state_root, control.POST_SEAL_IDENTITY_JOURNAL_FILENAME)
        settlement_rows = _read_state_rows(state_root, control.SETTLEMENT_JOURNAL_FILENAME)
        control_rows = _read_state_rows(state_root, control.CONTROL_JOURNAL_FILENAME)

        try:
            sealed, processed = runner._prediction_state(prediction_rows)
            _identity_map, _identity_keys = runner._identity_state(identity_rows)
            _settled_map, terminal = runner._settlement_state(settlement_rows)
        except Exception as exc:
            raise _error("cumulative PR151 journal state failed reviewed replay") from exc
        if len(processed) != len(prediction_rows):
            raise _error("prediction journal processed population changed")

        committed_rows = [row for row in control_rows if row.get("event") == "TICK_COMMITTED"]
        if not committed_rows:
            raise _error("success prefix contains no committed tick lineage")
        scheduled_values: list[tuple[dt.datetime, dict[str, Any]]] = []
        for row in committed_rows:
            scheduled_values.append(
                (_utc(row.get("scheduled_for_utc"), "committed scheduled_for"), row)
            )
        if len({item[0] for item in scheduled_values}) != len(scheduled_values):
            raise _error("control journal duplicated committed schedule slot")
        scheduled_values.sort(key=lambda item: item[0])
        latest_scheduled, latest = scheduled_values[-1]
        if latest_scheduled != nominal:
            raise _error("success receipt is not the latest committed state inside its cumulative archive")
        if _utc(latest.get("committed_at_utc"), "latest committed_at") != committed_at:
            raise _error("latest committed control row disagrees with tick receipt")
        if latest.get("phase") != receipt.get("phase"):
            raise _error("latest committed phase disagrees with tick receipt")
        if latest.get("durable_release_tag") != receipt.get("durable_release_tag"):
            raise _error("latest committed release tag disagrees with tick receipt")
        if latest.get("durable_asset_name") != source.artifact_name:
            raise _error("latest committed durable asset disagrees with tick receipt")

        if _utc(cp.get("last_committed_scheduled_for_utc"), "checkpoint last committed") != nominal:
            raise _error("checkpoint does not point at success receipt commit")
        if cp.get("phase") != receipt.get("phase"):
            raise _error("checkpoint phase disagrees with success receipt")
        if cp.get("durable_release_tag") != receipt.get("durable_release_tag"):
            raise _error("checkpoint release tag disagrees with success receipt")
        if cp.get("durable_asset_name") != source.artifact_name:
            raise _error("checkpoint durable asset disagrees with success receipt")
        if cp.get("capture_count") != len(capture_rows):
            raise _error("checkpoint capture_count disagrees with cumulative journal")
        if cp.get("prediction_count") != len(sealed):
            raise _error("checkpoint prediction_count disagrees with cumulative journal")
        if cp.get("settled_or_terminal_count") != len(terminal):
            raise _error("checkpoint settled_or_terminal_count disagrees with journal")
        if cp.get("control_event_count") != len(control_rows):
            raise _error("checkpoint control_event_count disagrees with cumulative journal")

        settlement_path = state_root / control.SETTLEMENT_JOURNAL_FILENAME
        settlement_raw = settlement_path.read_bytes() if settlement_path.exists() else b""
        settlements: list[fresh.SettledFreshPrediction] = []
        for row in settlement_rows:
            if row.get("disposition") != fresh.SettlementDisposition.SETTLED_REVIEWED_ORDINARY_FT.value:
                continue
            try:
                settled = runner._settled(row.get("settled_prediction"))
            except Exception as exc:
                raise _error("reviewed settlement row failed exact reconstruction") from exc
            if settled.settlement_observed_at > committed_at:
                raise _error("settlement observation occurs after durable prefix commit")
            settlements.append(settled)
        settlements.sort(
            key=lambda item: (
                item.settlement_observed_at,
                item.prediction.fixture.kickoff_utc,
                item.prediction.fixture.fixture_id,
            )
        )
        legacy_count = sum(item.legacy_history_state_update is not None for item in settlements)

        try:
            replay = shadow.build_current_fotmob_utc_native_shadow_prediction_handoff(
                current_bootstrap=source.current_bootstrap,
                source_raw_json=source.source_raw_json,
                source_manifest=source.source_manifest,
                legacy_bootstrap_projection_raw=source.legacy_bootstrap_projection_raw,
                reviewed_fresh_settlements=tuple(settlements),
            )
        except Exception as exc:
            raise _error("complete durable prefix failed PR244 shadow replay") from exc

        return _DerivedPrefix(
            artifact_zip_sha256=zip_sha,
            archive_sha256=verified["archive_sha256"],
            archive_size_bytes=verified["archive_size_bytes"],
            receipt_sha256=_sha(verified["receipt_bytes"]),
            nominal_scheduled_for_utc=nominal,
            committed_at_utc=committed_at,
            checkpoint_sha256=_sha(checkpoint_raw),
            settlement_journal_sha256=_sha(settlement_raw),
            settlement_journal_row_count=len(settlement_rows),
            reviewed_fresh_settlements=tuple(settlements),
            reviewed_legacy_update_count=legacy_count,
            shadow_handoff=replay,
        )


@dataclasses.dataclass(frozen=True)
class CurrentDurableFreshHistoryPrefixHandoff:
    schema_version: int
    dataset_name: str
    status: str
    source_bundle: CurrentDurableFreshHistoryPrefixSourceBundle
    artifact_zip_sha256: str
    archive_sha256: str
    archive_size_bytes: int
    receipt_sha256: str
    nominal_scheduled_for_utc: dt.datetime
    committed_at_utc: dt.datetime
    checkpoint_sha256: str
    settlement_journal_sha256: str
    settlement_journal_row_count: int
    reviewed_fresh_settlement_count: int
    reviewed_legacy_update_count: int
    shadow_handoff: shadow.CurrentUtcNativeShadowPredictionHandoff
    latest_applicable_success_selection_proven: bool
    current_fresh_history_prefix_complete: bool
    next_required_boundary: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("handoff schema mismatch")
        if self.status != STATUS:
            raise _error("handoff status mismatch")
        if type(self.source_bundle) is not CurrentDurableFreshHistoryPrefixSourceBundle:
            raise _error("source_bundle type mismatch")
        derived = _derive(dataclasses.replace(self.source_bundle))
        checks = {
            "artifact_zip_sha256": derived.artifact_zip_sha256,
            "archive_sha256": derived.archive_sha256,
            "archive_size_bytes": derived.archive_size_bytes,
            "receipt_sha256": derived.receipt_sha256,
            "nominal_scheduled_for_utc": derived.nominal_scheduled_for_utc,
            "committed_at_utc": derived.committed_at_utc,
            "checkpoint_sha256": derived.checkpoint_sha256,
            "settlement_journal_sha256": derived.settlement_journal_sha256,
            "settlement_journal_row_count": derived.settlement_journal_row_count,
            "reviewed_fresh_settlement_count": len(derived.reviewed_fresh_settlements),
            "reviewed_legacy_update_count": derived.reviewed_legacy_update_count,
            "shadow_handoff": derived.shadow_handoff,
        }
        for name, expected in checks.items():
            if getattr(self, name) != expected:
                raise _error(f"{name} differs from exact durable-prefix replay")
        if self.latest_applicable_success_selection_proven is not False:
            raise _error("archive proof cannot claim latest-applicable selection")
        if self.current_fresh_history_prefix_complete is not False:
            raise _error("archive proof cannot claim complete current history")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary mismatch")
        object.__setattr__(self, "authority", _validate_false_authority(self.authority))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "source_scope": SOURCE_SCOPE,
            "workflow_run_id": self.source_bundle.workflow_run_id,
            "artifact_name": self.source_bundle.artifact_name,
            "artifact_zip_sha256": self.artifact_zip_sha256,
            "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes,
            "receipt_sha256": self.receipt_sha256,
            "nominal_scheduled_for_utc": _utc_text(self.nominal_scheduled_for_utc),
            "committed_at_utc": _utc_text(self.committed_at_utc),
            "source_observed_at_utc": _utc_text(self.source_bundle.source_observed_at),
            "checkpoint_sha256": self.checkpoint_sha256,
            "settlement_journal_sha256": self.settlement_journal_sha256,
            "settlement_journal_row_count": self.settlement_journal_row_count,
            "reviewed_fresh_settlement_count": self.reviewed_fresh_settlement_count,
            "reviewed_legacy_update_count": self.reviewed_legacy_update_count,
            "shadow_handoff_sha256": shadow.sha256_current_fotmob_utc_native_shadow_prediction_handoff(
                self.shadow_handoff
            ),
            "latest_applicable_success_selection_proven": False,
            "current_fresh_history_prefix_complete": False,
            "next_required_boundary": self.next_required_boundary,
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def build_current_fotmob_durable_fresh_history_prefix_handoff(
    *,
    current_bootstrap: Any,
    source_raw_json: bytes,
    source_manifest: Any,
    legacy_bootstrap_projection_raw: bytes,
    workflow_run_id: int,
    artifact_name: str,
    artifact_zip_bytes: bytes,
    artifact_zip_metadata_digest: str,
) -> CurrentDurableFreshHistoryPrefixHandoff:
    source = CurrentDurableFreshHistoryPrefixSourceBundle(
        current_bootstrap=current_bootstrap,
        source_raw_json=source_raw_json,
        source_manifest=source_manifest,
        legacy_bootstrap_projection_raw=legacy_bootstrap_projection_raw,
        workflow_run_id=workflow_run_id,
        artifact_name=artifact_name,
        artifact_zip_bytes=artifact_zip_bytes,
        artifact_zip_metadata_digest=artifact_zip_metadata_digest,
    )
    derived = _derive(source)
    return CurrentDurableFreshHistoryPrefixHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS,
        source_bundle=source,
        artifact_zip_sha256=derived.artifact_zip_sha256,
        archive_sha256=derived.archive_sha256,
        archive_size_bytes=derived.archive_size_bytes,
        receipt_sha256=derived.receipt_sha256,
        nominal_scheduled_for_utc=derived.nominal_scheduled_for_utc,
        committed_at_utc=derived.committed_at_utc,
        checkpoint_sha256=derived.checkpoint_sha256,
        settlement_journal_sha256=derived.settlement_journal_sha256,
        settlement_journal_row_count=derived.settlement_journal_row_count,
        reviewed_fresh_settlement_count=len(derived.reviewed_fresh_settlements),
        reviewed_legacy_update_count=derived.reviewed_legacy_update_count,
        shadow_handoff=derived.shadow_handoff,
        latest_applicable_success_selection_proven=False,
        current_fresh_history_prefix_complete=False,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        authority=_false_authority(),
    )


def canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes(value: Any) -> bytes:
    if type(value) is not CurrentDurableFreshHistoryPrefixHandoff:
        raise _error("value must be exact CurrentDurableFreshHistoryPrefixHandoff")
    return _canonical(dataclasses.replace(value).to_dict())


def sha256_current_fotmob_durable_fresh_history_prefix_handoff(value: Any) -> str:
    return _sha(canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes(value))


__all__ = [
    "DATASET_NAME",
    "NEXT_REQUIRED_BOUNDARY",
    "SCHEMA_VERSION",
    "SOURCE_SCOPE",
    "STATUS",
    "CurrentDurableFreshHistoryPrefixError",
    "CurrentDurableFreshHistoryPrefixHandoff",
    "CurrentDurableFreshHistoryPrefixSourceBundle",
    "build_current_fotmob_durable_fresh_history_prefix_handoff",
    "canonical_current_fotmob_durable_fresh_history_prefix_handoff_bytes",
    "sha256_current_fotmob_durable_fresh_history_prefix_handoff",
]
