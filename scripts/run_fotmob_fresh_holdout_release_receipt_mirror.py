"""Operational entrypoint for the reviewed fresh-holdout receipt mirror.

GitHub's Actions artifact archive endpoint requires a JSON media type even though
its successful response redirects to ZIP bytes. The frozen mirror implementation
uses ``application/octet-stream`` for every binary endpoint because release assets
require that media type. This entrypoint changes only the Actions-artifact ZIP
transport; release-asset downloads continue through the frozen implementation.
"""
from __future__ import annotations

import re
import subprocess

import scripts.mirror_fotmob_fresh_holdout_release_receipt as mirror


ACTIONS_ARTIFACT_ZIP_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/actions/artifacts/[1-9][0-9]*/zip$"
)
_ORIGINAL_GH_DOWNLOAD = mirror._gh_download


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


def _install_reviewed_actions_artifact_transport() -> None:
    current = mirror._gh_download
    if current is _reviewed_gh_download:
        return
    if current is not _ORIGINAL_GH_DOWNLOAD:
        raise mirror.FreshHoldoutReleaseReceiptMirrorError(
            "release-receipt mirror download hook changed before transport installation"
        )
    mirror._gh_download = _reviewed_gh_download


def main(argv: list[str] | None = None) -> int:
    _install_reviewed_actions_artifact_transport()
    return mirror.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
