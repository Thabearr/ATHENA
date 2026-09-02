"""Operational entrypoint for the reviewed fresh-holdout receipt mirror.

GitHub's Actions artifact archive endpoint requires a JSON media type even though
its successful response redirects to ZIP bytes. The frozen mirror implementation
uses ``application/octet-stream`` for every binary endpoint because release assets
require that media type. This entrypoint changes only the Actions-artifact ZIP
transport and recognizes reviewed zero-acquisition paths.

For prospective continuity ``workflow_dispatch`` runs it independently replays the
immutable run-name/source-watchdog provenance before mirroring the same canonical
receipt schema. Release-asset downloads and the frozen archive/receipt verifier stay
unchanged.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import domain.fotmob_fresh_holdout_continuity as continuity
import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as schedule_recovery
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


ACTIONS_ARTIFACT_ZIP_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/actions/artifacts/[1-9][0-9]*/zip$"
)
CONTINUITY_RUN_NAME_RE = re.compile(
    r"^ATHENA fresh-holdout workflow_dispatch "
    r"source=([1-9][0-9]*) "
    r"target=([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z) "
    r"cron=(7 \* \* \* \*|37 \* \* \* \*) "
    r"confirm=(PROSPECTIVE_ONLY_NO_BACKFILL_V1)$"
)
_ORIGINAL_GH_DOWNLOAD = mirror._gh_download
_ORIGINAL_MIRROR_RUN = mirror.mirror_run


def _reviewed_gh_download(endpoint: str) -> bytes:
    if type(endpoint) is not str or endpoint != endpoint.strip():
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "GitHub binary download endpoint must be exact text"
        )
    if "/actions/artifacts/" not in endpoint:
        return _ORIGINAL_GH_DOWNLOAD(endpoint)
    if ACTIONS_ARTIFACT_ZIP_RE.fullmatch(endpoint) is None:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "Actions artifact download escaped reviewed ZIP endpoint"
        )
    try:
        return subprocess.check_output(
            [
                "gh",
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                endpoint,
            ]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            f"GitHub Actions artifact ZIP download failed: {endpoint}"
        ) from exc


def _validate_reviewed_collection_run(run: dict, *, run_id: int) -> str:
    event = run.get("event")
    if event not in {"schedule", "workflow_dispatch"} or run.get("status") != "completed":
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "receipt mirroring requires one completed reviewed collection run"
        )
    if run.get("workflow_id") != continuity.PRIMARY_WORKFLOW_ID:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow run id escaped reviewed collection workflow"
        )
    if event == "schedule" and run.get("name") != continuity.PRIMARY_SCHEDULE_RUN_NAME:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "scheduled workflow run-name escaped reviewed collection workflow"
        )
    if run.get("head_branch") != "main":
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "collection run did not execute from default main"
        )
    path = run.get("path")
    if type(path) is not str or not path.startswith(mirror.WORKFLOW_PATH):
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow run path escaped reviewed collection workflow"
        )
    if run.get("id") != run_id:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow run metadata is not bound to requested run_id"
        )
    return event


def _continuity_plan_from_run(*, repository: str, run: dict) -> continuity.ContinuityPlan:
    title = run.get("display_title")
    match = CONTINUITY_RUN_NAME_RE.fullmatch(title) if type(title) is str else None
    if match is None:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "continuity workflow_dispatch run-name escaped reviewed provenance grammar"
        )
    source_run_id = int(match.group(1))
    target_slot = match.group(2)
    target_cron = match.group(3)
    confirmation = match.group(4)
    run_id = mirror._positive_int(run.get("id"), "continuity run id")
    head_sha = run.get("head_sha")

    source = mirror._gh_json(f"/repos/{repository}/actions/runs/{source_run_id}")
    jobs = mirror._gh_json(
        f"/repos/{repository}/actions/runs/{source_run_id}/jobs?per_page=100"
    )
    try:
        continuity.validate_watchdog_source_jobs(
            jobs,
            expected_run_id=source_run_id,
            expected_main_sha=head_sha,
        )
        plan = continuity.validate_continuity_dispatch(
            watchdog_run=source,
            dispatch_run=run,
            source_watchdog_run_id=source_run_id,
            current_main_sha=head_sha,
            requested_target_slot=target_slot,
            requested_target_cron=target_cron,
            confirmation=confirmation,
        )
    except continuity.FreshHoldoutContinuityError as exc:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "continuity workflow_dispatch provenance replay failed"
        ) from exc
    if run_id < 1:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "continuity run id must remain positive"
        )
    return plan


def _mirror_continuity_artifact(
    *,
    repository: str,
    run_id: int,
    artifacts: dict,
    plan: continuity.ContinuityPlan,
) -> dict:
    values = artifacts.get("artifacts")
    if type(values) is not list:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow artifacts payload is malformed"
        )
    candidates = [
        value
        for value in values
        if type(value) is dict
        and type(value.get("name")) is str
        and mirror.ARTIFACT_RE.fullmatch(value["name"]) is not None
        and value["name"].endswith(f"-run-{run_id}.tar.gz")
        and value.get("expired") is False
    ]
    if len(candidates) != 1:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "completed continuity run must expose exactly one unexpired evidence artifact"
        )
    artifact = candidates[0]
    artifact_id = mirror._positive_int(artifact.get("id"), "Actions artifact id")
    artifact_name = artifact["name"]
    zip_bytes = _reviewed_gh_download(
        f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    )
    artifact_zip_sha = mirror.verify_actions_artifact_zip_digest(
        zip_bytes,
        artifact.get("digest"),
    )
    verified = mirror.verify_actions_artifact_bundle(
        run_id=run_id,
        artifact_name=artifact_name,
        zip_bytes=zip_bytes,
    )
    verified["actions_artifact_zip_sha256"] = artifact_zip_sha

    receipt = mirror._parse_canonical_json(
        verified["receipt_bytes"], "continuity tick receipt"
    )
    if receipt.get("workflow_event_schedule") != plan.target_cron:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "continuity receipt logical cron identity changed"
        )
    if mirror._parse_nominal(receipt.get("nominal_scheduled_for_utc")) != plan.target_slot:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "continuity receipt nominal slot differs from source-bound target"
        )

    tag = verified["release_tag"]
    release = mirror._release_for(repository, tag)

    def download_release_asset(asset_id: int) -> bytes:
        return _ORIGINAL_GH_DOWNLOAD(
            f"/repos/{repository}/releases/assets/{asset_id}"
        )

    def upload_receipt(name: str, raw: bytes) -> None:
        with tempfile.TemporaryDirectory(prefix="athena-release-receipt-") as temporary:
            path = Path(temporary) / name
            path.write_bytes(raw)
            try:
                subprocess.check_call(
                    ["gh", "release", "upload", tag, str(path), "--repo", repository]
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise mirror.FreshHoldoutReleaseReceiptMirrorError(
                    "GitHub release receipt upload failed"
                ) from exc

    result = mirror.verify_release_archive_and_receipt(
        verified=verified,
        release=release,
        download_release_asset=download_release_asset,
        upload_receipt=upload_receipt,
        reload_release=lambda: mirror._release_for(repository, tag),
    )
    return {
        **result,
        "source_event": "workflow_dispatch",
        "continuity_target_slot": plan.target_slot_text,
        "continuity_target_cron": plan.target_cron,
        "continuity_provenance_replayed": True,
    }


def _reviewed_mirror_run(*, repository: str, run_id: int) -> dict:
    """Mirror evidence runs or prove exact reviewed zero-artifact no-op paths."""
    if (
        type(repository) is not str
        or repository.count("/") != 1
        or repository != repository.strip()
    ):
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "repository must be exact owner/name text"
        )
    run_id = mirror._positive_int(run_id, "run_id")

    run = mirror._gh_json(f"/repos/{repository}/actions/runs/{run_id}")
    event = _validate_reviewed_collection_run(run, run_id=run_id)
    artifacts = mirror._gh_json(f"/repos/{repository}/actions/runs/{run_id}/artifacts")
    values = artifacts.get("artifacts")
    if type(values) is not list:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow artifacts payload is malformed"
        )

    if event == "workflow_dispatch":
        plan = _continuity_plan_from_run(repository=repository, run=run)
        if values:
            return _mirror_continuity_artifact(
                repository=repository,
                run_id=run_id,
                artifacts=artifacts,
                plan=plan,
            )
    elif values:
        return _ORIGINAL_MIRROR_RUN(repository=repository, run_id=run_id)

    def get_run_jobs(requested_run_id: int) -> dict:
        if requested_run_id != run_id:
            raise mirror.FreshHoldoutReleaseReceiptMirrorError(
                "no-acquisition proof requested jobs for a different run"
            )
        return mirror._gh_json(
            f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"
        )

    try:
        if event == "workflow_dispatch":
            proven = schedule_recovery._prove_continuity_duplicate_no_acquisition_success(
                run,
                artifacts,
                get_run_jobs,
            )
            disposition = "VERIFIED_CONTINUITY_ALREADY_ATTEMPTED_NO_MIRROR_REQUIRED"
        else:
            proven = schedule_recovery._prove_ambiguous_no_acquisition_success(
                run,
                artifacts,
                get_run_jobs,
            )
            disposition = "VERIFIED_AMBIGUOUS_NO_ACQUISITION_NO_MIRROR_REQUIRED"
    except schedule_recovery.FreshHoldoutFailureLineageError as exc:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "could not prove reviewed zero-artifact no-acquisition source run"
        ) from exc

    if not proven:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "zero-artifact collection run is not a proven reviewed no-acquisition success"
        )

    return {
        "schema_version": 1,
        "run_id": run_id,
        "disposition": disposition,
        "actions_artifact_count": 0,
        "receipt_mirror_required": False,
        "release_asset_written": False,
        "provider_network_acquisition_performed": False,
        "model_or_betting_authority_changed": False,
    }


def _install_reviewed_actions_artifact_transport() -> None:
    current = mirror._gh_download
    if current is _reviewed_gh_download:
        return
    if current is not _ORIGINAL_GH_DOWNLOAD:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "release-receipt mirror download hook changed before transport installation"
        )
    mirror._gh_download = _reviewed_gh_download


def _install_reviewed_no_acquisition_compatibility() -> None:
    current = mirror.mirror_run
    if current is _reviewed_mirror_run:
        return
    if current is not _ORIGINAL_MIRROR_RUN:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "release-receipt mirror run hook changed before compatibility installation"
        )
    mirror.mirror_run = _reviewed_mirror_run


def main(argv: list[str] | None = None) -> int:
    _install_reviewed_actions_artifact_transport()
    _install_reviewed_no_acquisition_compatibility()
    return mirror.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
