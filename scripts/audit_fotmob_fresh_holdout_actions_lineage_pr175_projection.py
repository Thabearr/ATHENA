"""Pin the lineage audit to the post-PR175 workflow and compatible GitHub transport.

The reviewed PR170 audit engine remains byte-for-byte pinned. PR175 changed the
scheduled collection workflow identity, and GitHub's Actions artifact archive
endpoint now requires the JSON media type while release-asset binary downloads
continue to require application/octet-stream. This compatibility entrypoint
updates only those reviewed integration boundaries before delegating to the
unchanged audit engine.
"""

from __future__ import annotations

from collections.abc import Sequence
import re
import subprocess

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


PRE_PR175_WORKFLOW_BLOB_SHA = "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
POST_PR175_WORKFLOW_BLOB_SHA = "1ff52e32ade3422ca1605bc4546dc8d0813ec316"
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
    audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA
    audit._gh_download = _gh_download_compatible
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
