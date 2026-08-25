"""Operational entrypoint for the reviewed fresh-holdout receipt mirror.

GitHub's Actions artifact archive endpoint requires a JSON media type even though
its successful response redirects to ZIP bytes. The frozen mirror implementation
uses ``application/octet-stream`` for every binary endpoint because release assets
require that media type. This entrypoint changes only the Actions-artifact ZIP
transport and recognizes the exact reviewed PR #226 ambiguous-no-acquisition
success path. Release-asset downloads continue through the frozen implementation.
"""
from __future__ import annotations

import re
import subprocess

import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as schedule_recovery
import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


ACTIONS_ARTIFACT_ZIP_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/actions/artifacts/[1-9][0-9]*/zip$"
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


def _validate_reviewed_collection_run(run: dict, *, run_id: int) -> None:
    if run.get("name") != mirror.WORKFLOW_NAME:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow run name escaped reviewed collection workflow"
        )
    if run.get("event") != "schedule" or run.get("status") != "completed":
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "receipt mirroring requires one completed scheduled collection run"
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


def _reviewed_mirror_run(*, repository: str, run_id: int) -> dict:
    """Mirror normal evidence runs or prove the exact zero-artifact no-op path."""
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
    _validate_reviewed_collection_run(run, run_id=run_id)
    artifacts = mirror._gh_json(f"/repos/{repository}/actions/runs/{run_id}/artifacts")
    values = artifacts.get("artifacts")
    if type(values) is not list:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "workflow artifacts payload is malformed"
        )

    if values:
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
        proven = schedule_recovery._prove_ambiguous_no_acquisition_success(
            run,
            artifacts,
            get_run_jobs,
        )
    except schedule_recovery.FreshHoldoutFailureLineageError as exc:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "could not prove zero-artifact ambiguous no-acquisition source run"
        ) from exc

    if not proven:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "zero-artifact collection run is not a proven ambiguous no-acquisition success"
        )

    return {
        "schema_version": 1,
        "run_id": run_id,
        "disposition": "VERIFIED_AMBIGUOUS_NO_ACQUISITION_NO_MIRROR_REQUIRED",
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
            "release-receipt mirror run hook changed before no-acquisition installation"
        )
    mirror.mirror_run = _reviewed_mirror_run


def main(argv: list[str] | None = None) -> int:
    _install_reviewed_actions_artifact_transport()
    _install_reviewed_no_acquisition_compatibility()
    return mirror.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
