from pathlib import Path

import yaml

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as projection


WORKFLOW = Path(
    ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
)
COLLECTION_WORKFLOW = Path(
    ".github/workflows/fotmob-utc-native-xg-fresh-holdout.yml"
)
PROJECTION_SCRIPT = Path(
    "scripts/audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py"
)


def _git_blob_sha(path: Path) -> str:
    import hashlib

    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def test_projection_pins_exact_pre_and_post_pr175_collection_workflow_blobs():
    assert projection.PRE_PR175_WORKFLOW_BLOB_SHA == audit.WORKFLOW_BLOB_SHA
    assert projection.POST_PR175_WORKFLOW_BLOB_SHA == _git_blob_sha(COLLECTION_WORKFLOW)
    assert projection.PRE_PR175_WORKFLOW_BLOB_SHA == (
        "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd"
    )
    assert projection.POST_PR175_WORKFLOW_BLOB_SHA == (
        "4e1a7c47f47a0d2b89363191340dc5918c4b154e"
    )


def test_control_workflow_verifies_current_collection_and_projection_blobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert "4e1a7c47f47a0d2b89363191340dc5918c4b154e" in text
    assert _git_blob_sha(PROJECTION_SCRIPT) == (
        "adaaaab0b8eef212c198066b9c75e04b4acd7d30"
    )
    assert "adaaaab0b8eef212c198066b9c75e04b4acd7d30" in text
    assert "aaf8dbe8534dfc10b707d34511fd4327dc81850e" in text
    assert "audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py" in text


def test_projection_changes_only_reviewed_workflow_dependency_identity():
    text = PROJECTION_SCRIPT.read_text(encoding="utf-8")
    assert "audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA" in text
    assert "audit.main(argv)" in text
    for forbidden in (
        "requests.",
        "urllib",
        "curl ",
        "wget ",
        "rerun",
        "backfill_authorized = True",
        "pricing_authorized = True",
        "selection_authorized = True",
        "bet_authorized = True",
    ):
        assert forbidden not in text


def test_audit_control_permissions_remain_read_only_except_issue_result_comment():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "actions: read" in text
    assert "contents: read" in text
    assert "pull-requests: read" in text
    assert "issues: write" in text
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "provider-network-acquisition-performed-by-audit: false" in text
    assert "backfill-authorized: false" in text
    assert "pricing-authorized: false" in text
    assert "selection-authorized: false" in text
    assert "bet-authorized: false" in text
