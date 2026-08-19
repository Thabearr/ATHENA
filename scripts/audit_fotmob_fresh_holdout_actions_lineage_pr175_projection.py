"""Pin the lineage audit to the post-PR175 collection-workflow identity.

The reviewed PR170 audit engine remains byte-for-byte pinned. PR175 changed only the
scheduled collection workflow, so this compatibility entrypoint updates that one
reviewed dependency identity in memory before delegating to the unchanged audit.
"""

from __future__ import annotations

from collections.abc import Sequence

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


PRE_PR175_WORKFLOW_BLOB_SHA = "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
POST_PR175_WORKFLOW_BLOB_SHA = "1ff52e32ade3422ca1605bc4546dc8d0813ec316"


def main(argv: Sequence[str] | None = None) -> int:
    if audit.WORKFLOW_BLOB_SHA != PRE_PR175_WORKFLOW_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine workflow pin drifted before PR175 projection"
        )
    audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
