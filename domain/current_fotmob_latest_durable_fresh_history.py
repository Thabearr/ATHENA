"""Bind PR244 current replay to the latest applicable durable PR151 history.

The lower PR245 archive proof verifies one cumulative PR151 success artifact but
intentionally cannot say it is the latest state that existed before a current
FotMob observation. This module closes that exact gap by replaying the reviewed
PR174 audit through its PR175/ambiguity-recovery compatibility projection over
an immutable snapshot of every GitHub read consumed by that audit.

The GitHub snapshot is evidence, not a cryptographic statement by GitHub about
JSON response authenticity. Independent Actions artifact SHA-256 metadata and
the reviewed release/archive commitments remain the byte-level anchors for the
cumulative state artifacts themselves.

Even a complete current history prefix does not authorize the UTC-native model
for production, ScoreMatrix, probabilities, Phase 6, pricing, selection,
SportyBet execution, or BET. Those remain separate reviewed boundaries.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import types
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import domain.current_fotmob_durable_fresh_history_prefix as prefix
import scripts.audit_fotmob_fresh_holdout_actions_lineage as lineage_audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as pr175_projection
import scripts.audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection as recovery_projection
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror
import scripts.replay_fotmob_utc_native_xg_fresh_holdout_confirmation as terminal_replay

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-fotmob-latest-durable-fresh-history-v1"
STATUS = "VERIFIED_COMPLETE_CURRENT_PR151_DURABLE_HISTORY_PREFIX"
NEXT_REQUIRED_BOUNDARY = (
    "CURRENT_UTC_NATIVE_MODEL_PRODUCTION_AUTHORITY_REQUIRES_REVIEWED_FRESH_HOLDOUT_CONFIRMATION"
)
REPOSITORY = "Thabearr/ATHENA"
SOURCE_SCOPE = (
    "FULL_REVIEWED_PR151_GITHUB_ACTIONS_LINEAGE_AS_OF_CURRENT_FOTMOB_OBSERVATION"
)

RAW_AUDIT_BLOB_SHA = "e3cdb18845403d92f94933f68c2bd06e55660de0"
PR175_PROJECTION_BLOB_SHA = "522b99260137fbeea1914495b3aaa368961ba455"
SCHEDULE_RECOVERY_PROJECTION_BLOB_SHA = "dc4e8de2bf16ca923e39aafe14b665edd50efeff"

_ALLOWED_RELEASE_STATES = frozenset(
    {
        "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED",
        "RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING",
        "RELEASE_DURABILITY_UNVERIFIED",
    }
)
_EVIDENCE_STATE = {
    "full_reviewed_actions_lineage_audited": True,
    "latest_applicable_success_selection_proven": True,
    "complete_current_fresh_history_prefix": True,
    "complete_current_history_shadow_replay": True,
}
_DOWNSTREAM_AUTHORITY_KEYS = frozenset(
    {
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


class CurrentLatestDurableFreshHistoryError(ValueError):
    """Raised when latest-applicable durable history cannot be proven exactly."""


class _RecordedGitHubReadError(RuntimeError):
    """Deterministic replay form of one GitHub read failure."""


def _error(message: str) -> CurrentLatestDurableFreshHistoryError:
    return CurrentLatestDurableFreshHistoryError(message)


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


def _parse_object(raw: bytes, label: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw:
        raise _error(f"{label} must be non-empty exact bytes")
    try:
        value = json.loads(raw, object_pairs_hook=terminal_replay._no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} is malformed JSON") from exc
    if type(value) is not dict or _canonical(value) != raw:
        raise _error(f"{label} must be canonical compact sorted-key JSON")
    return value


def _canonical_mapping(value: Any, label: str) -> bytes:
    if not isinstance(value, Mapping):
        raise _error(f"{label} must be a mapping")
    return _canonical(dict(value))


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


def _sha(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error(f"{label} must be exact lowercase SHA-256")
    return value


def _sha40(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _error(f"{label} must be exact lowercase 40-hex SHA")
    return value


def _blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _evidence() -> Mapping[str, bool]:
    return types.MappingProxyType(dict(_EVIDENCE_STATE))


def _authority() -> Mapping[str, bool]:
    return types.MappingProxyType(
        {key: False for key in sorted(_DOWNSTREAM_AUTHORITY_KEYS)}
    )


def _validate_boolean_map(
    value: Any,
    *,
    expected: Mapping[str, bool],
    label: str,
) -> Mapping[str, bool]:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise _error(f"{label} keys mismatch")
    for key, item in value.items():
        if type(item) is not bool or item is not expected[key]:
            raise _error(f"{label}[{key!r}] changed reviewed state")
    return types.MappingProxyType(dict(expected))


def _verify_current_projected_audit_dependencies(
    repository_root: Path | None = None,
) -> None:
    """Verify the reviewed current projection without leaving mutated audit pins."""
    repo = (repository_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    pins = (
        (
            repo / "scripts/audit_fotmob_fresh_holdout_actions_lineage.py",
            RAW_AUDIT_BLOB_SHA,
            "PR174 audit engine",
        ),
        (
            repo / "scripts/audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py",
            PR175_PROJECTION_BLOB_SHA,
            "PR175 audit projection",
        ),
        (
            repo
            / "scripts/audit_fotmob_fresh_holdout_actions_lineage_schedule_recovery_projection.py",
            SCHEDULE_RECOVERY_PROJECTION_BLOB_SHA,
            "schedule-recovery audit projection",
        ),
    )
    for path, expected, label in pins:
        if not path.is_file() or path.is_symlink():
            raise _error(f"{label} path is unavailable")
        if _blob(path) != expected:
            raise _error(f"{label} blob changed")

    if lineage_audit.WORKFLOW_BLOB_SHA != pr175_projection.PRE_PR175_WORKFLOW_BLOB_SHA:
        raise _error("raw audit workflow pin changed before current projection")
    if (
        lineage_audit.FAILURE_LINEAGE_BLOB_SHA
        != pr175_projection.PRE_PREACQUISITION_FALLBACK_BLOB_SHA
    ):
        raise _error("raw audit failure-lineage pin changed before current projection")
    try:
        recovery_projection._verify_projection_dependencies()
    except Exception as exc:
        raise _error("schedule-recovery projection dependencies changed") from exc

    old_workflow = lineage_audit.WORKFLOW_BLOB_SHA
    old_failure = lineage_audit.FAILURE_LINEAGE_BLOB_SHA
    try:
        lineage_audit.WORKFLOW_BLOB_SHA = (
            recovery_projection.POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
        )
        lineage_audit.FAILURE_LINEAGE_BLOB_SHA = (
            pr175_projection.POST_PREACQUISITION_FALLBACK_BLOB_SHA
        )
        lineage_audit.verify_reviewed_dependencies(repo)
    except Exception as exc:
        raise _error("projected current Actions-lineage dependencies failed review") from exc
    finally:
        lineage_audit.WORKFLOW_BLOB_SHA = old_workflow
        lineage_audit.FAILURE_LINEAGE_BLOB_SHA = old_failure


def _run_reviewed_projected_audit(
    *,
    expected_main_sha: str,
    get_main_ref: Callable[[], Mapping[str, Any]],
    get_runs_page: Callable[[int, int], Mapping[str, Any]],
    get_run_by_id: Callable[[int], Mapping[str, Any]],
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_release: Callable[[str], Mapping[str, Any]],
    download_release_asset: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
    repository_root: Path | None = None,
) -> dict[str, Any]:
    _sha40(expected_main_sha, "expected_main_sha")
    _verify_current_projected_audit_dependencies(repository_root)
    try:
        return recovery_projection._audit_actions_lineage_compatible(
            repository=REPOSITORY,
            expected_main_sha=expected_main_sha,
            get_main_ref=get_main_ref,
            get_runs_page=get_runs_page,
            get_run_by_id=get_run_by_id,
            get_run_artifacts=get_run_artifacts,
            download_artifact_zip=download_artifact_zip,
            get_release=get_release,
            download_release_asset=download_release_asset,
            get_run_jobs=get_run_jobs,
            verify_dependencies=False,
            repository_root=repository_root,
        )
    except Exception as exc:
        raise _error("reviewed projected PR151 Actions lineage audit failed") from exc


@dataclasses.dataclass(frozen=True)
class GitHubReadSnapshot:
    key: str
    payload_kind: str
    succeeded: bool
    payload: bytes

    def __post_init__(self) -> None:
        if type(self.key) is not str or not self.key or self.key != self.key.strip():
            raise _error("GitHub read snapshot key must be exact non-empty text")
        if self.payload_kind not in {"json", "binary"}:
            raise _error("GitHub read snapshot payload_kind changed")
        if type(self.succeeded) is not bool:
            raise _error("GitHub read snapshot succeeded must be exact bool")
        if type(self.payload) is not bytes or not self.payload:
            raise _error("GitHub read snapshot payload must be non-empty exact bytes")
        if self.succeeded:
            if self.payload_kind == "json":
                _parse_object(self.payload, f"GitHub read {self.key}")
        else:
            failure = _parse_object(self.payload, f"GitHub read failure {self.key}")
            if set(failure) != {"error_type", "message"}:
                raise _error("GitHub read failure payload schema changed")
            if any(type(failure[key]) is not str for key in failure):
                raise _error("GitHub read failure payload values must be text")

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


class _ReadRecorder:
    def __init__(self) -> None:
        self._reads: dict[str, GitHubReadSnapshot] = {}

    def _existing(self, key: str, kind: str) -> GitHubReadSnapshot | None:
        value = self._reads.get(key)
        if value is not None and value.payload_kind != kind:
            raise _error("one GitHub read key changed payload kind")
        return value

    @staticmethod
    def _raise_failure(value: GitHubReadSnapshot) -> None:
        failure = _parse_object(value.payload, f"GitHub read failure {value.key}")
        raise _RecordedGitHubReadError(
            f"{value.key}:{failure['error_type']}:{failure['message']}"
        )

    def json(self, key: str, reader: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
        existing = self._existing(key, "json")
        if existing is not None:
            if not existing.succeeded:
                self._raise_failure(existing)
            return _parse_object(existing.payload, f"GitHub read {key}")
        try:
            raw = _canonical_mapping(reader(), f"GitHub read {key}")
            snapshot = GitHubReadSnapshot(key, "json", True, raw)
        except Exception as exc:
            failure = _canonical(
                {"error_type": type(exc).__name__, "message": str(exc)[:500]}
            )
            snapshot = GitHubReadSnapshot(key, "json", False, failure)
            self._reads[key] = snapshot
            self._raise_failure(snapshot)
        self._reads[key] = snapshot
        return _parse_object(raw, f"GitHub read {key}")

    def binary(self, key: str, reader: Callable[[], bytes]) -> bytes:
        existing = self._existing(key, "binary")
        if existing is not None:
            if not existing.succeeded:
                self._raise_failure(existing)
            return existing.payload
        try:
            raw = reader()
            if type(raw) is not bytes or not raw:
                raise _error(f"GitHub binary read {key} returned empty/non-bytes payload")
            snapshot = GitHubReadSnapshot(key, "binary", True, raw)
        except Exception as exc:
            failure = _canonical(
                {"error_type": type(exc).__name__, "message": str(exc)[:500]}
            )
            snapshot = GitHubReadSnapshot(key, "binary", False, failure)
            self._reads[key] = snapshot
            self._raise_failure(snapshot)
        self._reads[key] = snapshot
        return raw

    def freeze(self) -> tuple[GitHubReadSnapshot, ...]:
        return tuple(self._reads[key] for key in sorted(self._reads))


class _SnapshotReaders:
    def __init__(self, reads: tuple[GitHubReadSnapshot, ...]) -> None:
        self._by_key = {item.key: item for item in reads}
        self.used: set[str] = set()

    def _read(self, key: str, kind: str) -> GitHubReadSnapshot:
        value = self._by_key.get(key)
        if value is None:
            raise _RecordedGitHubReadError(f"missing captured GitHub read: {key}")
        if value.payload_kind != kind:
            raise _RecordedGitHubReadError(f"captured GitHub read kind changed: {key}")
        self.used.add(key)
        if not value.succeeded:
            _ReadRecorder._raise_failure(value)
        return value

    def json(self, key: str) -> Mapping[str, Any]:
        value = self._read(key, "json")
        return _parse_object(value.payload, f"GitHub read {key}")

    def binary(self, key: str) -> bytes:
        return self._read(key, "binary").payload


@dataclasses.dataclass(frozen=True)
class GitHubActionsLineageEvidenceBundle:
    expected_main_sha: str
    reads: tuple[GitHubReadSnapshot, ...]
    audit_result_bytes: bytes

    def __post_init__(self) -> None:
        _sha40(self.expected_main_sha, "evidence expected_main_sha")
        if type(self.reads) is not tuple or not self.reads:
            raise _error("GitHub evidence reads must be non-empty immutable tuple")
        reads = tuple(dataclasses.replace(item) for item in self.reads)
        keys = [item.key for item in reads]
        if len(set(keys)) != len(keys) or tuple(sorted(keys)) != tuple(keys):
            raise _error("GitHub evidence read keys must be unique and sorted")
        audit = _parse_object(self.audit_result_bytes, "captured Actions lineage audit")
        if audit.get("schema_version") != lineage_audit.SCHEMA_VERSION:
            raise _error("captured Actions lineage audit schema changed")
        if audit.get("audit_id") != lineage_audit.AUDIT_ID:
            raise _error("captured Actions lineage audit identity changed")
        if audit.get("repository") != REPOSITORY:
            raise _error("captured Actions lineage audit repository changed")
        if audit.get("expected_main_sha") != self.expected_main_sha:
            raise _error("captured Actions lineage audit expected main changed")
        if audit.get("observed_main_sha") != self.expected_main_sha:
            raise _error("captured Actions lineage audit observed main changed")
        safety = audit.get("safety")
        if (
            type(safety) is not dict
            or set(safety) != set(lineage_audit.SAFETY_KEYS)
            or any(type(item) is not bool or item is not False for item in safety.values())
        ):
            raise _error("captured Actions lineage audit changed safety authority")

        replay, used = _replay_audit_from_evidence(
            expected_main_sha=self.expected_main_sha,
            reads=reads,
        )
        if _canonical(replay) != self.audit_result_bytes:
            raise _error("captured GitHub reads do not reproduce the exact lineage audit")
        if used != set(keys):
            raise _error("captured GitHub evidence contains reads outside exact audit replay")
        object.__setattr__(self, "reads", reads)

    @property
    def audit_result(self) -> dict[str, Any]:
        return _parse_object(self.audit_result_bytes, "captured Actions lineage audit")

    def _lookup(self, key: str, kind: str) -> GitHubReadSnapshot:
        matches = [item for item in self.reads if item.key == key]
        if len(matches) != 1 or matches[0].payload_kind != kind:
            raise _error(f"captured GitHub evidence lacks exact {key}")
        value = matches[0]
        if not value.succeeded:
            _ReadRecorder._raise_failure(value)
        return value

    def json(self, key: str) -> Mapping[str, Any]:
        value = self._lookup(key, "json")
        return _parse_object(value.payload, f"GitHub evidence {key}")

    def binary(self, key: str) -> bytes:
        return self._lookup(key, "binary").payload

    @property
    def inventory_sha256(self) -> str:
        descriptor = {
            "expected_main_sha": self.expected_main_sha,
            "audit_result_sha256": hashlib.sha256(self.audit_result_bytes).hexdigest(),
            "reads": [
                {
                    "key": item.key,
                    "payload_kind": item.payload_kind,
                    "succeeded": item.succeeded,
                    "payload_sha256": item.payload_sha256,
                    "payload_size": len(item.payload),
                }
                for item in self.reads
            ],
        }
        return hashlib.sha256(_canonical(descriptor)).hexdigest()


def _replay_audit_from_evidence(
    *,
    expected_main_sha: str,
    reads: tuple[GitHubReadSnapshot, ...],
) -> tuple[dict[str, Any], set[str]]:
    source = _SnapshotReaders(reads)
    result = _run_reviewed_projected_audit(
        expected_main_sha=expected_main_sha,
        get_main_ref=lambda: source.json("main_ref"),
        get_runs_page=lambda page, per_page: source.json(
            f"runs:{page}:{per_page}"
        ),
        get_run_by_id=lambda run_id: source.json(f"run:{run_id}"),
        get_run_artifacts=lambda run_id: source.json(f"artifacts:{run_id}"),
        download_artifact_zip=lambda artifact_id: source.binary(
            f"artifact_zip:{artifact_id}"
        ),
        get_release=lambda tag: source.json(f"release:{tag}"),
        download_release_asset=lambda asset_id: source.binary(
            f"release_asset:{asset_id}"
        ),
        get_run_jobs=lambda run_id: source.json(f"jobs:{run_id}"),
    )
    return result, source.used


@dataclasses.dataclass(frozen=True)
class VerifiedPr151SuccessReceiptEvidence:
    run_id: int
    artifact_name: str
    actions_artifact_zip_sha256: str
    release_state: str
    receipt_bytes: bytes

    def __post_init__(self) -> None:
        if type(self.run_id) is not int or self.run_id < 1:
            raise _error("success receipt run_id must be exact positive integer")
        if type(self.artifact_name) is not str:
            raise _error("success receipt artifact_name must be exact text")
        _sha(self.actions_artifact_zip_sha256, "actions artifact ZIP SHA-256")
        if self.release_state not in _ALLOWED_RELEASE_STATES:
            raise _error("success receipt release state escaped reviewed audit vocabulary")
        receipt = _parse_object(self.receipt_bytes, "success tick receipt")
        committed_at = _utc(receipt.get("committed_at_utc"), "success committed_at")
        try:
            exact, nominal, exact_committed = prefix._exact_receipt(
                self.receipt_bytes,
                run_id=self.run_id,
                artifact_name=self.artifact_name,
                source_observed_at=committed_at,
            )
        except Exception as exc:
            raise _error("success tick receipt failed exact PR151 receipt replay") from exc
        if exact != receipt or exact_committed != committed_at:
            raise _error("success tick receipt exact replay changed")
        object.__setattr__(self, "_nominal", nominal)
        object.__setattr__(self, "_committed", committed_at)

    @property
    def receipt(self) -> dict[str, Any]:
        return _parse_object(self.receipt_bytes, "success tick receipt")

    @property
    def nominal_scheduled_for_utc(self) -> dt.datetime:
        return self._nominal

    @property
    def committed_at_utc(self) -> dt.datetime:
        return self._committed

    @property
    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.receipt_bytes).hexdigest()


def _success_materials(
    evidence: GitHubActionsLineageEvidenceBundle,
) -> tuple[
    tuple[
        VerifiedPr151SuccessReceiptEvidence,
        Mapping[str, Any],
        bytes,
        str,
    ],
    ...,
]:
    values: list[
        tuple[VerifiedPr151SuccessReceiptEvidence, Mapping[str, Any], bytes, str]
    ] = []
    for record in evidence.audit_result.get("runs", []):
        if type(record) is not dict:
            raise _error("Actions lineage run record changed shape")
        if record.get("evidence_state") != "VERIFIED_ACTIONS_LINEAGE":
            continue
        run_id = record.get("run_id")
        if type(run_id) is not int or run_id < 1:
            raise _error("audited success run id changed shape")
        try:
            artifacts = evidence.json(f"artifacts:{run_id}")
            artifact = lineage_audit._candidate_artifact(artifacts, run_id)
            artifact_id = artifact.get("id")
            if type(artifact_id) is not int or artifact_id < 1:
                raise _error("audited success artifact id changed")
            zip_bytes = evidence.binary(f"artifact_zip:{artifact_id}")
            zip_sha = mirror.verify_actions_artifact_zip_digest(
                zip_bytes, artifact.get("digest")
            )
            verified = mirror.verify_actions_artifact_bundle(
                run_id=run_id,
                artifact_name=artifact["name"],
                zip_bytes=zip_bytes,
            )
        except Exception as exc:
            raise _error(f"audited success run {run_id} failed exact artifact replay") from exc
        if record.get("archive_name") != artifact.get("name"):
            raise _error("audited success archive changed during latest selection")
        if record.get("actions_artifact_zip_sha256") != zip_sha:
            raise _error("audited success ZIP digest changed during latest selection")
        success = VerifiedPr151SuccessReceiptEvidence(
            run_id=run_id,
            artifact_name=str(artifact["name"]),
            actions_artifact_zip_sha256=zip_sha,
            release_state=str(record.get("release_state")),
            receipt_bytes=verified["receipt_bytes"],
        )
        created_at = _utc(record.get("created_at"), "success run created_at")
        if success.committed_at_utc < created_at:
            raise _error("success committed_at predates GitHub run creation")
        values.append((success, artifact, zip_bytes, str(artifact.get("digest"))))
    return tuple(values)


def _select_latest_material(
    *,
    evidence: GitHubActionsLineageEvidenceBundle,
    source_observed_at: dt.datetime,
) -> tuple[
    VerifiedPr151SuccessReceiptEvidence,
    Mapping[str, Any],
    bytes,
    str,
]:
    source_utc = source_observed_at.astimezone(dt.timezone.utc)
    audit = evidence.audit_result
    for record in audit.get("runs", []):
        if type(record) is not dict:
            raise _error("Actions lineage run record changed shape")
        created_at = _utc(record.get("created_at"), "audit run created_at")
        if (
            created_at <= source_utc
            and record.get("evidence_state") == "UNVERIFIED"
            and record.get("conclusion") is not None
        ):
            raise _error("unverified completed PR151 run could affect current as-of history")

    applicable = [
        value
        for value in _success_materials(evidence)
        if value[0].committed_at_utc <= source_utc
    ]
    if not applicable:
        raise _error("no verified committed PR151 success prefix existed before source observation")
    applicable.sort(key=lambda value: (value[0].committed_at_utc, value[0].run_id))
    latest_commit = applicable[-1][0].committed_at_utc
    tied = [value for value in applicable if value[0].committed_at_utc == latest_commit]
    if len(tied) != 1:
        raise _error("latest applicable PR151 success commit is ambiguous")
    selected = tied[0]
    if selected[0].release_state != "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED":
        raise _error(
            "latest applicable PR151 success lacks long-lived archive+receipt durability"
        )
    return selected


@dataclasses.dataclass(frozen=True)
class CurrentLatestDurableFreshHistorySourceBundle:
    github_evidence: GitHubActionsLineageEvidenceBundle
    selected_prefix: prefix.CurrentDurableFreshHistoryPrefixHandoff

    def __post_init__(self) -> None:
        if type(self.github_evidence) is not GitHubActionsLineageEvidenceBundle:
            raise _error("github_evidence type mismatch")
        evidence = dataclasses.replace(self.github_evidence)
        if type(self.selected_prefix) is not prefix.CurrentDurableFreshHistoryPrefixHandoff:
            raise _error("selected_prefix type mismatch")
        selected = dataclasses.replace(self.selected_prefix)
        chosen, artifact, zip_bytes, metadata_digest = _select_latest_material(
            evidence=evidence,
            source_observed_at=selected.source_bundle.source_observed_at,
        )
        if selected.source_bundle.workflow_run_id != chosen.run_id:
            raise _error("selected durable prefix is not latest applicable success run")
        if selected.source_bundle.artifact_name != chosen.artifact_name:
            raise _error("selected durable prefix archive is not latest applicable success")
        if selected.artifact_zip_sha256 != chosen.actions_artifact_zip_sha256:
            raise _error("selected durable prefix ZIP digest differs from latest applicable success")
        if selected.receipt_sha256 != chosen.receipt_sha256:
            raise _error("selected durable prefix receipt differs from latest applicable success")
        if selected.committed_at_utc != chosen.committed_at_utc:
            raise _error("selected durable prefix commit time differs from latest applicable success")
        if selected.source_bundle.artifact_zip_bytes != zip_bytes:
            raise _error("selected durable prefix ZIP bytes differ from captured GitHub evidence")
        if selected.source_bundle.artifact_zip_metadata_digest != metadata_digest:
            raise _error("selected durable prefix GitHub artifact digest metadata changed")
        if artifact.get("name") != chosen.artifact_name:
            raise _error("selected artifact metadata identity changed")
        if selected.latest_applicable_success_selection_proven is not False:
            raise _error("lower archive proof unexpectedly acquired selection authority")
        if selected.current_fresh_history_prefix_complete is not False:
            raise _error("lower archive proof unexpectedly acquired current completeness")
        object.__setattr__(self, "github_evidence", evidence)
        object.__setattr__(self, "selected_prefix", selected)

    @property
    def audit_result(self) -> dict[str, Any]:
        return self.github_evidence.audit_result

    @property
    def selected_success_receipt(self) -> VerifiedPr151SuccessReceiptEvidence:
        return _select_latest_material(
            evidence=self.github_evidence,
            source_observed_at=self.selected_prefix.source_bundle.source_observed_at,
        )[0]


@dataclasses.dataclass(frozen=True)
class CurrentLatestDurableFreshHistoryHandoff:
    schema_version: int
    dataset_name: str
    status: str
    source_bundle: CurrentLatestDurableFreshHistorySourceBundle
    latest_applicable_success_selection_proven: bool
    current_fresh_history_prefix_complete: bool
    next_required_boundary: str
    evidence: Mapping[str, bool]
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.dataset_name != DATASET_NAME:
            raise _error("handoff schema mismatch")
        if self.status != STATUS:
            raise _error("handoff status mismatch")
        if type(self.source_bundle) is not CurrentLatestDurableFreshHistorySourceBundle:
            raise _error("source_bundle type mismatch")
        source = dataclasses.replace(self.source_bundle)
        if self.latest_applicable_success_selection_proven is not True:
            raise _error("latest-applicable success selection proof was lost")
        if self.current_fresh_history_prefix_complete is not True:
            raise _error("complete current fresh-history proof was lost")
        if self.next_required_boundary != NEXT_REQUIRED_BOUNDARY:
            raise _error("next boundary mismatch")
        evidence = _validate_boolean_map(
            self.evidence,
            expected=_evidence(),
            label="evidence",
        )
        authority = _validate_boolean_map(
            self.authority,
            expected=_authority(),
            label="authority",
        )
        object.__setattr__(self, "source_bundle", source)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "authority", authority)

    @property
    def selected_prefix(self) -> prefix.CurrentDurableFreshHistoryPrefixHandoff:
        return self.source_bundle.selected_prefix

    @property
    def shadow_handoff(self):
        return self.selected_prefix.shadow_handoff

    def to_dict(self) -> dict[str, Any]:
        audit = self.source_bundle.audit_result
        selected_receipt = self.source_bundle.selected_success_receipt
        return {
            "schema_version": self.schema_version,
            "dataset_name": self.dataset_name,
            "status": self.status,
            "source_scope": SOURCE_SCOPE,
            "repository": REPOSITORY,
            "audit_id": audit["audit_id"],
            "audit_result_sha256": hashlib.sha256(
                self.source_bundle.github_evidence.audit_result_bytes
            ).hexdigest(),
            "github_inventory_snapshot_sha256": (
                self.source_bundle.github_evidence.inventory_sha256
            ),
            "expected_main_sha": audit["expected_main_sha"],
            "source_observed_at_utc": _utc_text(
                self.selected_prefix.source_bundle.source_observed_at
            ),
            "selected_workflow_run_id": selected_receipt.run_id,
            "selected_artifact_name": selected_receipt.artifact_name,
            "selected_actions_artifact_zip_sha256": (
                selected_receipt.actions_artifact_zip_sha256
            ),
            "selected_receipt_sha256": selected_receipt.receipt_sha256,
            "selected_nominal_scheduled_for_utc": _utc_text(
                selected_receipt.nominal_scheduled_for_utc
            ),
            "selected_committed_at_utc": _utc_text(
                selected_receipt.committed_at_utc
            ),
            "selected_prefix_sha256": (
                prefix.sha256_current_fotmob_durable_fresh_history_prefix_handoff(
                    self.selected_prefix
                )
            ),
            "shadow_handoff_sha256": self.selected_prefix.to_dict()[
                "shadow_handoff_sha256"
            ],
            "latest_applicable_success_selection_proven": True,
            "current_fresh_history_prefix_complete": True,
            "next_required_boundary": self.next_required_boundary,
            "evidence": dict(self.evidence),
            "authority": dict(self.authority),
            "wager_placed": False,
        }


def _build_with_readers(
    *,
    current_bootstrap: Any,
    source_raw_json: bytes,
    source_manifest: Any,
    legacy_bootstrap_projection_raw: bytes,
    expected_main_sha: str,
    get_main_ref: Callable[[], Mapping[str, Any]],
    get_runs_page: Callable[[int, int], Mapping[str, Any]],
    get_run_by_id: Callable[[int], Mapping[str, Any]],
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_release: Callable[[str], Mapping[str, Any]],
    download_release_asset: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
    repository_root: Path | None = None,
) -> CurrentLatestDurableFreshHistoryHandoff:
    recorder = _ReadRecorder()

    audit = _run_reviewed_projected_audit(
        expected_main_sha=expected_main_sha,
        get_main_ref=lambda: recorder.json("main_ref", get_main_ref),
        get_runs_page=lambda page, per_page: recorder.json(
            f"runs:{page}:{per_page}", lambda: get_runs_page(page, per_page)
        ),
        get_run_by_id=lambda run_id: recorder.json(
            f"run:{run_id}", lambda: get_run_by_id(run_id)
        ),
        get_run_artifacts=lambda run_id: recorder.json(
            f"artifacts:{run_id}", lambda: get_run_artifacts(run_id)
        ),
        download_artifact_zip=lambda artifact_id: recorder.binary(
            f"artifact_zip:{artifact_id}", lambda: download_artifact_zip(artifact_id)
        ),
        get_release=lambda tag: recorder.json(
            f"release:{tag}", lambda: get_release(tag)
        ),
        download_release_asset=lambda asset_id: recorder.binary(
            f"release_asset:{asset_id}", lambda: download_release_asset(asset_id)
        ),
        get_run_jobs=lambda run_id: recorder.json(
            f"jobs:{run_id}", lambda: get_run_jobs(run_id)
        ),
        repository_root=repository_root,
    )
    github_evidence = GitHubActionsLineageEvidenceBundle(
        expected_main_sha=expected_main_sha,
        reads=recorder.freeze(),
        audit_result_bytes=_canonical(audit),
    )

    observed = getattr(source_manifest, "observed_at", None)
    if type(observed) is not dt.datetime or observed.tzinfo is None or observed.utcoffset() is None:
        raise _error("current source manifest lost observed_at authority")
    chosen, _artifact, zip_bytes, metadata_digest = _select_latest_material(
        evidence=github_evidence,
        source_observed_at=observed,
    )
    try:
        selected_prefix = prefix.build_current_fotmob_durable_fresh_history_prefix_handoff(
            current_bootstrap=current_bootstrap,
            source_raw_json=source_raw_json,
            source_manifest=source_manifest,
            legacy_bootstrap_projection_raw=legacy_bootstrap_projection_raw,
            workflow_run_id=chosen.run_id,
            artifact_name=chosen.artifact_name,
            artifact_zip_bytes=zip_bytes,
            artifact_zip_metadata_digest=metadata_digest,
        )
    except Exception as exc:
        raise _error("latest applicable success failed exact cumulative prefix replay") from exc

    source = CurrentLatestDurableFreshHistorySourceBundle(
        github_evidence=github_evidence,
        selected_prefix=selected_prefix,
    )
    return CurrentLatestDurableFreshHistoryHandoff(
        schema_version=SCHEMA_VERSION,
        dataset_name=DATASET_NAME,
        status=STATUS,
        source_bundle=source,
        latest_applicable_success_selection_proven=True,
        current_fresh_history_prefix_complete=True,
        next_required_boundary=NEXT_REQUIRED_BOUNDARY,
        evidence=_evidence(),
        authority=_authority(),
    )


def build_current_fotmob_latest_durable_fresh_history_handoff(
    *,
    current_bootstrap: Any,
    source_raw_json: bytes,
    source_manifest: Any,
    legacy_bootstrap_projection_raw: bytes,
    expected_main_sha: str,
    repository_root: Path | None = None,
) -> CurrentLatestDurableFreshHistoryHandoff:
    """Fixed read-only GitHub issuer for the reviewed ATHENA PR151 campaign."""
    if not os.environ.get("GH_TOKEN"):
        raise _error("GH_TOKEN is required for fixed GitHub PR151 lineage acquisition")

    def get_main_ref() -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/git/ref/heads/main")

    def get_runs_page(page: int, per_page: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(
            f"/repos/{REPOSITORY}/actions/workflows/"
            f"fotmob-utc-native-xg-fresh-holdout.yml/runs?per_page={per_page}&page={page}"
        )

    def get_run_by_id(run_id: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/actions/runs/{run_id}")

    def get_run_artifacts(run_id: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts")

    def download_artifact_zip(artifact_id: int) -> bytes:
        return pr175_projection._gh_download_compatible(
            f"/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
        )

    def get_release(tag: str) -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/releases/tags/{tag}")

    def download_release_asset(asset_id: int) -> bytes:
        return pr175_projection._gh_download_compatible(
            f"/repos/{REPOSITORY}/releases/assets/{asset_id}"
        )

    def get_run_jobs(run_id: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(
            f"/repos/{REPOSITORY}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
        )

    return _build_with_readers(
        current_bootstrap=current_bootstrap,
        source_raw_json=source_raw_json,
        source_manifest=source_manifest,
        legacy_bootstrap_projection_raw=legacy_bootstrap_projection_raw,
        expected_main_sha=expected_main_sha,
        get_main_ref=get_main_ref,
        get_runs_page=get_runs_page,
        get_run_by_id=get_run_by_id,
        get_run_artifacts=get_run_artifacts,
        download_artifact_zip=download_artifact_zip,
        get_release=get_release,
        download_release_asset=download_release_asset,
        get_run_jobs=get_run_jobs,
        repository_root=repository_root,
    )


def canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(value: Any) -> bytes:
    if type(value) is not CurrentLatestDurableFreshHistoryHandoff:
        raise _error("value must be exact CurrentLatestDurableFreshHistoryHandoff")
    return _canonical(dataclasses.replace(value).to_dict())


def sha256_current_fotmob_latest_durable_fresh_history_handoff(value: Any) -> str:
    return hashlib.sha256(
        canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes(value)
    ).hexdigest()


__all__ = [
    "DATASET_NAME",
    "NEXT_REQUIRED_BOUNDARY",
    "REPOSITORY",
    "SCHEMA_VERSION",
    "SOURCE_SCOPE",
    "STATUS",
    "CurrentLatestDurableFreshHistoryError",
    "CurrentLatestDurableFreshHistoryHandoff",
    "GitHubActionsLineageEvidenceBundle",
    "VerifiedPr151SuccessReceiptEvidence",
    "build_current_fotmob_latest_durable_fresh_history_handoff",
    "canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes",
    "sha256_current_fotmob_latest_durable_fresh_history_handoff",
]
