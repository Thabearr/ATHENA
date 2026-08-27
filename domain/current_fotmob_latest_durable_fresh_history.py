"""Bind a PR244 current replay to the latest applicable durable PR151 history.

The lower PR245 archive proof verifies one cumulative PR151 success artifact but
intentionally cannot say it is the latest state that existed before a current
FotMob observation.  This module closes that exact gap by projecting the already
reviewed full GitHub Actions lineage audit as-of the source observation.

Production access is fixed to the ATHENA repository and reviewed PR151 workflow.
The callback-based helper is private and exists only so deterministic tests can
supply recorded GitHub metadata/bytes.  No caller-supplied run list, workflow,
or preselected archive becomes selection authority.

Even a complete current history prefix does not authorize the UTC-native model
for production, ScoreMatrix, probabilities, Phase 6, pricing, selection,
SportyBet execution, or BET.  Those remain separate reviewed boundaries.
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
        match = prefix._SUCCESS_ARTIFACT_RE.fullmatch(self.artifact_name)
        if match is None or int(match.group(2)) != self.run_id:
            raise _error("success receipt artifact identity changed")
        _sha(self.actions_artifact_zip_sha256, "actions artifact ZIP SHA-256")
        if self.release_state != "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED":
            raise _error("success receipt evidence lacks exact long-lived durability")
        receipt = _parse_object(self.receipt_bytes, "success tick receipt")
        if set(receipt) != terminal_replay.TERMINAL_RECEIPT_KEYS:
            raise _error("success tick receipt key set changed")
        if receipt.get("workflow_run_id") != self.run_id:
            raise _error("success tick receipt workflow run id changed")
        if receipt.get("durable_asset_name") != self.artifact_name:
            raise _error("success tick receipt durable asset changed")
        if receipt.get("tick_exit_code") != 0 or receipt.get("tick_committed") is not True:
            raise _error("success tick receipt lost committed zero-exit semantics")
        nominal = _utc(receipt.get("nominal_scheduled_for_utc"), "success nominal slot")
        scheduled = _utc(receipt.get("scheduled_for_utc"), "success runner slot")
        if nominal != scheduled:
            raise _error("success receipt nominal and runner slots differ")
        if nominal.strftime("%Y%m%dT%H%M%SZ") != match.group(1):
            raise _error("success receipt nominal slot differs from artifact name")
        committed_at = _utc(receipt.get("committed_at_utc"), "success committed_at")
        if committed_at < nominal:
            raise _error("success committed_at predates nominal slot")

    @property
    def receipt(self) -> dict[str, Any]:
        return _parse_object(self.receipt_bytes, "success tick receipt")

    @property
    def nominal_scheduled_for_utc(self) -> dt.datetime:
        return _utc(self.receipt["nominal_scheduled_for_utc"], "success nominal slot")

    @property
    def committed_at_utc(self) -> dt.datetime:
        return _utc(self.receipt["committed_at_utc"], "success committed_at")

    @property
    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.receipt_bytes).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "artifact_name": self.artifact_name,
            "actions_artifact_zip_sha256": self.actions_artifact_zip_sha256,
            "release_state": self.release_state,
            "receipt_sha256": self.receipt_sha256,
            "nominal_scheduled_for_utc": _utc_text(self.nominal_scheduled_for_utc),
            "committed_at_utc": _utc_text(self.committed_at_utc),
        }


@dataclasses.dataclass(frozen=True)
class CurrentLatestDurableFreshHistorySourceBundle:
    audit_result_bytes: bytes
    success_receipts: tuple[VerifiedPr151SuccessReceiptEvidence, ...]
    selected_prefix: prefix.CurrentDurableFreshHistoryPrefixHandoff

    def __post_init__(self) -> None:
        audit = _parse_object(self.audit_result_bytes, "Actions lineage audit result")
        if audit.get("schema_version") != lineage_audit.SCHEMA_VERSION:
            raise _error("Actions lineage audit schema changed")
        if audit.get("audit_id") != lineage_audit.AUDIT_ID:
            raise _error("Actions lineage audit identity changed")
        if audit.get("repository") != REPOSITORY:
            raise _error("Actions lineage audit repository changed")
        expected_main = audit.get("expected_main_sha")
        observed_main = audit.get("observed_main_sha")
        if expected_main != observed_main:
            raise _error("Actions lineage audit no longer binds exact main")
        safety = audit.get("safety")
        if (
            type(safety) is not dict
            or set(safety) != set(lineage_audit.SAFETY_KEYS)
            or any(type(item) is not bool or item is not False for item in safety.values())
        ):
            raise _error("Actions lineage audit changed safety authority")
        runs = audit.get("runs")
        if type(runs) is not list:
            raise _error("Actions lineage audit runs payload changed shape")
        if type(self.success_receipts) is not tuple:
            raise _error("success_receipts must be immutable tuple")
        receipts = tuple(dataclasses.replace(item) for item in self.success_receipts)
        if len({item.run_id for item in receipts}) != len(receipts):
            raise _error("success receipt evidence duplicated workflow run")
        by_run = {item.run_id: item for item in receipts}

        audited_successes: dict[int, Mapping[str, Any]] = {}
        for value in runs:
            if type(value) is not dict:
                raise _error("Actions lineage run record changed shape")
            if value.get("evidence_state") == "VERIFIED_ACTIONS_LINEAGE":
                run_id = value.get("run_id")
                if type(run_id) is not int or run_id < 1:
                    raise _error("verified success run id changed shape")
                audited_successes[run_id] = value
        if set(by_run) != set(audited_successes):
            raise _error("success receipt evidence does not cover every audited success run")
        for run_id, record in audited_successes.items():
            evidence = by_run[run_id]
            if record.get("archive_name") != evidence.artifact_name:
                raise _error("success receipt archive differs from audited run")
            if record.get("actions_artifact_zip_sha256") != evidence.actions_artifact_zip_sha256:
                raise _error("success receipt ZIP digest differs from audited run")
            if record.get("release_state") != evidence.release_state:
                raise _error("success receipt release state differs from audited run")
            created_at = _utc(record.get("created_at"), "success run created_at")
            if evidence.committed_at_utc < created_at:
                raise _error("success committed_at predates GitHub run creation")

        if type(self.selected_prefix) is not prefix.CurrentDurableFreshHistoryPrefixHandoff:
            raise _error("selected_prefix type mismatch")
        selected = dataclasses.replace(self.selected_prefix)
        source_observed = selected.source_bundle.source_observed_at

        # An unverified completed run that already existed before the source
        # observation could hide a committed prefix.  Refuse to guess.  Incomplete
        # runs and verified failures are not committed durable states and therefore
        # do not displace the last proven success prefix.
        for record in runs:
            created = _utc(record.get("created_at"), "audit run created_at")
            if (
                created <= source_observed
                and record.get("evidence_state") == "UNVERIFIED"
                and record.get("conclusion") is not None
            ):
                raise _error(
                    "unverified completed PR151 run could affect current as-of history"
                )

        applicable = [
            item for item in receipts if item.committed_at_utc <= source_observed
        ]
        if not applicable:
            raise _error("no verified committed PR151 success prefix existed before source observation")
        applicable.sort(key=lambda item: (item.committed_at_utc, item.run_id))
        latest_commit = applicable[-1].committed_at_utc
        tied = [item for item in applicable if item.committed_at_utc == latest_commit]
        if len(tied) != 1:
            raise _error("latest applicable PR151 success commit is ambiguous")
        latest = tied[0]

        if selected.source_bundle.workflow_run_id != latest.run_id:
            raise _error("selected durable prefix is not latest applicable success run")
        if selected.source_bundle.artifact_name != latest.artifact_name:
            raise _error("selected durable prefix archive is not latest applicable success")
        if selected.artifact_zip_sha256 != latest.actions_artifact_zip_sha256:
            raise _error("selected durable prefix ZIP digest differs from latest applicable success")
        if selected.receipt_sha256 != latest.receipt_sha256:
            raise _error("selected durable prefix receipt differs from latest applicable success")
        if selected.committed_at_utc != latest.committed_at_utc:
            raise _error("selected durable prefix commit time differs from latest applicable success")
        if selected.latest_applicable_success_selection_proven is not False:
            raise _error("lower archive proof unexpectedly acquired selection authority")
        if selected.current_fresh_history_prefix_complete is not False:
            raise _error("lower archive proof unexpectedly acquired current completeness")

        object.__setattr__(self, "success_receipts", receipts)
        object.__setattr__(self, "selected_prefix", selected)

    @property
    def audit_result(self) -> dict[str, Any]:
        return _parse_object(self.audit_result_bytes, "Actions lineage audit result")

    @property
    def selected_success_receipt(self) -> VerifiedPr151SuccessReceiptEvidence:
        run_id = self.selected_prefix.source_bundle.workflow_run_id
        matches = [item for item in self.success_receipts if item.run_id == run_id]
        if len(matches) != 1:
            raise _error("selected success receipt disappeared")
        return matches[0]


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
            "audit_result_sha256": hashlib.sha256(self.source_bundle.audit_result_bytes).hexdigest(),
            "expected_main_sha": audit["expected_main_sha"],
            "source_observed_at_utc": _utc_text(
                self.selected_prefix.source_bundle.source_observed_at
            ),
            "selected_workflow_run_id": selected_receipt.run_id,
            "selected_artifact_name": selected_receipt.artifact_name,
            "selected_actions_artifact_zip_sha256": selected_receipt.actions_artifact_zip_sha256,
            "selected_receipt_sha256": selected_receipt.receipt_sha256,
            "selected_nominal_scheduled_for_utc": _utc_text(
                selected_receipt.nominal_scheduled_for_utc
            ),
            "selected_committed_at_utc": _utc_text(selected_receipt.committed_at_utc),
            "selected_prefix_sha256": prefix.sha256_current_fotmob_durable_fresh_history_prefix_handoff(
                self.selected_prefix
            ),
            "shadow_handoff_sha256": self.selected_prefix.to_dict()["shadow_handoff_sha256"],
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
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_release: Callable[[str], Mapping[str, Any]],
    download_release_asset: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
    repository_root: Path | None = None,
    verify_audit_dependencies: bool = True,
) -> CurrentLatestDurableFreshHistoryHandoff:
    artifact_payload_cache: dict[int, Mapping[str, Any]] = {}
    artifact_zip_cache: dict[int, bytes] = {}

    def cached_artifacts(run_id: int) -> Mapping[str, Any]:
        if run_id not in artifact_payload_cache:
            artifact_payload_cache[run_id] = get_run_artifacts(run_id)
        return artifact_payload_cache[run_id]

    def cached_download(artifact_id: int) -> bytes:
        if artifact_id not in artifact_zip_cache:
            artifact_zip_cache[artifact_id] = download_artifact_zip(artifact_id)
        return artifact_zip_cache[artifact_id]

    try:
        audit = lineage_audit.audit_actions_lineage(
            repository=REPOSITORY,
            expected_main_sha=expected_main_sha,
            get_main_ref=get_main_ref,
            get_runs_page=get_runs_page,
            get_run_artifacts=cached_artifacts,
            download_artifact_zip=cached_download,
            get_release=get_release,
            download_release_asset=download_release_asset,
            get_run_jobs=get_run_jobs,
            verify_dependencies=verify_audit_dependencies,
            repository_root=repository_root,
        )
    except Exception as exc:
        raise _error("reviewed full PR151 Actions lineage audit failed") from exc
    audit_raw = _canonical(audit)

    receipts: list[VerifiedPr151SuccessReceiptEvidence] = []
    selected_candidates: list[
        tuple[VerifiedPr151SuccessReceiptEvidence, Mapping[str, Any], bytes, str]
    ] = []
    source_observed = getattr(source_manifest, "observed_at", None)
    if type(source_observed) is not dt.datetime or source_observed.tzinfo is None or source_observed.utcoffset() is None:
        raise _error("current source manifest lost observed_at authority")
    source_observed = source_observed.astimezone(dt.timezone.utc)

    for record in audit.get("runs", []):
        if type(record) is not dict or record.get("evidence_state") != "VERIFIED_ACTIONS_LINEAGE":
            continue
        run_id = record.get("run_id")
        if type(run_id) is not int or run_id < 1:
            raise _error("audited success run id changed shape")
        try:
            artifact = lineage_audit._candidate_artifact(cached_artifacts(run_id), run_id)
            zip_bytes = cached_download(artifact["id"])
            zip_sha = mirror.verify_actions_artifact_zip_digest(zip_bytes, artifact.get("digest"))
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
        evidence = VerifiedPr151SuccessReceiptEvidence(
            run_id=run_id,
            artifact_name=str(artifact["name"]),
            actions_artifact_zip_sha256=zip_sha,
            release_state=str(record.get("release_state")),
            receipt_bytes=verified["receipt_bytes"],
        )
        created_at = _utc(record.get("created_at"), "success run created_at")
        if evidence.committed_at_utc < created_at:
            raise _error("success committed_at predates GitHub run creation")
        receipts.append(evidence)
        if evidence.committed_at_utc <= source_observed:
            selected_candidates.append((evidence, artifact, zip_bytes, str(artifact.get("digest"))))

    # Refuse any completed-but-unverified run that existed by the source
    # observation; it might hide a committed success prefix.
    for record in audit.get("runs", []):
        if type(record) is not dict:
            raise _error("Actions lineage audit run record changed shape")
        created_at = _utc(record.get("created_at"), "audit run created_at")
        if (
            created_at <= source_observed
            and record.get("evidence_state") == "UNVERIFIED"
            and record.get("conclusion") is not None
        ):
            raise _error("unverified completed PR151 run could affect current as-of history")

    if not selected_candidates:
        raise _error("no verified committed PR151 success prefix existed before source observation")
    selected_candidates.sort(key=lambda item: (item[0].committed_at_utc, item[0].run_id))
    latest_commit = selected_candidates[-1][0].committed_at_utc
    latest_candidates = [
        item for item in selected_candidates if item[0].committed_at_utc == latest_commit
    ]
    if len(latest_candidates) != 1:
        raise _error("latest applicable PR151 success commit is ambiguous")
    selected_receipt, selected_artifact, selected_zip, selected_digest = latest_candidates[0]
    if selected_receipt.release_state != "RELEASE_ARCHIVE_AND_RECEIPT_VERIFIED":
        raise _error("latest applicable PR151 success lacks long-lived archive+receipt durability")

    try:
        selected_prefix = prefix.build_current_fotmob_durable_fresh_history_prefix_handoff(
            current_bootstrap=current_bootstrap,
            source_raw_json=source_raw_json,
            source_manifest=source_manifest,
            legacy_bootstrap_projection_raw=legacy_bootstrap_projection_raw,
            workflow_run_id=selected_receipt.run_id,
            artifact_name=selected_receipt.artifact_name,
            artifact_zip_bytes=selected_zip,
            artifact_zip_metadata_digest=selected_digest,
        )
    except Exception as exc:
        raise _error("latest applicable success failed exact cumulative prefix replay") from exc

    source = CurrentLatestDurableFreshHistorySourceBundle(
        audit_result_bytes=audit_raw,
        success_receipts=tuple(receipts),
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
    """Production GitHub-only latest-prefix issuer for the fixed ATHENA campaign."""
    if not os.environ.get("GH_TOKEN"):
        raise _error("GH_TOKEN is required for fixed GitHub PR151 lineage acquisition")

    def get_main_ref() -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/git/ref/heads/main")

    def get_runs_page(page: int, per_page: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(
            f"/repos/{REPOSITORY}/actions/workflows/"
            f"fotmob-utc-native-xg-fresh-holdout.yml/runs?per_page={per_page}&page={page}"
        )

    def get_run_artifacts(run_id: int) -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts")

    def download_artifact_zip(artifact_id: int) -> bytes:
        return lineage_audit._gh_download(
            f"/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
        )

    def get_release(tag: str) -> Mapping[str, Any]:
        return lineage_audit._gh_json(f"/repos/{REPOSITORY}/releases/tags/{tag}")

    def download_release_asset(asset_id: int) -> bytes:
        return lineage_audit._gh_download(f"/repos/{REPOSITORY}/releases/assets/{asset_id}")

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
        get_run_artifacts=get_run_artifacts,
        download_artifact_zip=download_artifact_zip,
        get_release=get_release,
        download_release_asset=download_release_asset,
        get_run_jobs=get_run_jobs,
        repository_root=repository_root,
        verify_audit_dependencies=True,
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
    "VerifiedPr151SuccessReceiptEvidence",
    "build_current_fotmob_latest_durable_fresh_history_handoff",
    "canonical_current_fotmob_latest_durable_fresh_history_handoff_bytes",
    "sha256_current_fotmob_latest_durable_fresh_history_handoff",
]
