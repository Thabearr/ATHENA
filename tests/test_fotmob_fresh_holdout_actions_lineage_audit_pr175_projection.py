from pathlib import Path

import pytest
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
AUDIT_SCRIPT = Path("scripts/audit_fotmob_fresh_holdout_actions_lineage.py")


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
        "d48b1ff823277445e3b496876caca6b01480ece9"
    )


def test_control_workflow_verifies_current_collection_and_projection_blobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert "d48b1ff823277445e3b496876caca6b01480ece9" in text
    assert _git_blob_sha(PROJECTION_SCRIPT) in text
    assert _git_blob_sha(AUDIT_SCRIPT) in text
    assert "2ae03405f63c0951eb61c4be0db1ba9dff318f21" in text
    assert "audit_fotmob_fresh_holdout_actions_lineage_pr175_projection.py" in text


def test_projection_delegates_to_current_engine_with_compatible_binary_transport():
    text = PROJECTION_SCRIPT.read_text(encoding="utf-8")
    assert "current reviewed engine" in text
    assert "unchanged audit engine" not in text
    assert "byte-for-byte pinned" not in text
    assert "audit.WORKFLOW_BLOB_SHA = POST_PR175_WORKFLOW_BLOB_SHA" in text
    assert "audit._gh_download = _gh_download_compatible" in text
    assert "audit.main(argv)" in text
    assert "application/vnd.github+json" in text
    assert "application/octet-stream" in text
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


def test_transport_uses_json_media_type_for_actions_artifact_zip(monkeypatch):
    calls = []

    def fake_check_output(args):
        calls.append(args)
        return b"artifact-zip"

    monkeypatch.setattr(projection.subprocess, "check_output", fake_check_output)
    endpoint = "/repos/Thabearr/ATHENA/actions/artifacts/9366326461/zip"
    assert projection._gh_download_compatible(endpoint) == b"artifact-zip"
    assert calls == [[
        "gh", "api", "-H", "Accept: application/vnd.github+json", endpoint
    ]]


def test_transport_keeps_octet_stream_for_release_asset(monkeypatch):
    calls = []

    def fake_check_output(args):
        calls.append(args)
        return b"release-asset"

    monkeypatch.setattr(projection.subprocess, "check_output", fake_check_output)
    endpoint = "/repos/Thabearr/ATHENA/releases/assets/123456789"
    assert projection._gh_download_compatible(endpoint) == b"release-asset"
    assert calls == [[
        "gh", "api", "-H", "Accept: application/octet-stream", endpoint
    ]]


def test_transport_rejects_unreviewed_binary_endpoint():
    with pytest.raises(
        audit.FreshHoldoutActionsLineageAuditError,
        match="unsupported GitHub binary download endpoint",
    ):
        projection._gh_download_compatible(
            "/repos/Thabearr/ATHENA/actions/runs/32256052482/logs"
        )


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
