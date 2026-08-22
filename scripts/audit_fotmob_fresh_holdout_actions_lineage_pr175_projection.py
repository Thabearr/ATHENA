"""Project the reviewed lineage audit onto current collection dependencies.

The owner-only control workflow independently pins the current audit-engine
blob. PR175 changed the scheduled collection workflow identity, and GitHub's
Actions artifact archive endpoint requires the JSON media type while Release
asset downloads continue to require application/octet-stream. The later
pre-acquisition fallback repair changes only restore/schedule behavior in the
shared failure-lineage module; the audit's chronological Genesis policy remains
owned by the unchanged audit engine. This entrypoint projects both reviewed
runtime dependency identities before delegating to that engine.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
import subprocess

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


PRE_PR175_WORKFLOW_BLOB_SHA = "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
POST_PR175_WORKFLOW_BLOB_SHA = "d48b1ff823277445e3b496876caca6b01480ece9"
PRE_PREACQUISITION_FALLBACK_BLOB_SHA = "2ae03405f63c0951eb61c4be0db1ba9dff318f21"
POST_PREACQUISITION_FALLBACK_BLOB_SHA = "692e3fe778e43ae4157e10882158f5dae08cb096"
_ACTIONS_ARTIFACT_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/actions/artifacts/[1-9][0-9]*/zip$",
    re.ASCII,
)
_RELEASE_ASSET_RE = re.compile(
    r"^/repos/[^/]+/[^/]+/releases/assets/[1-9][0-9]*$",
    re.ASCII,
)


def _gh_download_compatible(endpoint: str) -> bytes:
    if type(endpoint) is not str:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "GitHub binary download endpoint must be an exact string"
        )
    if _ACTIONS_ARTIFACT_RE.fullmatch(endpoint):
        accept = "application/vnd.github+json"
    elif _RELEASE_ASSET_RE.fullmatch(endpoint):
        accept = "application/octet-stream"
    else:
        raise audit.FreshHoldoutActionsLineageAuditError(
            f"unsupported GitHub binary download endpoint: {endpoint}"
        )
    try:
        return subprocess.check_output(
            ["gh", "api", "-H", f"Accept: {accept}", endpoint]
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise audit.FreshHoldoutActionsLineageAuditError(
            f"GitHub binary download failed: {endpoint}"
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    if audit.WORKFLOW_BLOB_SHA != PRE_PR175_WORKFLOW_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine workflow pin drifted before PR175 projection"
        )
    if audit.FAILURE_LINEAGE_BLOB_SHA != PRE_PREACQUISITION_FALLBACK_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine failure-lineage pin drifted before fallback projection"
        )
    audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA
    audit.FAILURE_LINEAGE_BLOB_SHA = POST_PREACQUISITION_FALLBACK_BLOB_SHA
    audit._gh_download = _gh_download_compatible
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
