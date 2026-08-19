from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


MAIN_SHA = "a" * 40
HEAD_1 = "1" * 40
HEAD_2 = "2" * 40


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def committed(slot):
    return {
        "backfill_or_retrofill_performed": False,
        "committed_at_utc": slot,
        "event": "TICK_COMMITTED",
        "nominal_schedule_time_used_as_observation_time": False,
        "schema_version": 1,
        "scheduled_for_utc": slot,
    }


def gap(first, last, detected, count):
    return {
        "backfill_authorized": False,
        "detected_at_scheduled_for_utc": detected,
        "event": "SCHEDULER_GAP_RANGE",
        "first_missing_tick_utc": first,
        "last_missing_tick_utc": last,
        "missing_tick_count": count,
        "previous_committed_tick_utc": None,
        "schema_version": 1,
    }


def failure_event():
    return {
        "backfill_authorized": False,
        "event": "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED",
        "schema_version": 1,
        "tick_committed": False,
    }


def archive_bytes(rows):
    body = b"".join(canonical(row) for row in rows)
    member = (
        ".cache/athena-research/fotmob-utc-native-xg-fresh-holdout/"
        "control-journal.ndjson"
    )
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        info = tarfile.TarInfo(member)
        info.size = len(body)
        info.mode = 0o600
        tar.addfile(info, io.BytesIO(body))
    return raw.getvalue()


def evidence_bundle(run_id, slot, *, success=True, rows=()):
    compact = (
        slot[0:4]
        + slot[5:7]
        + slot[8:10]
        + "T"
        + slot[11:13]
        + slot[14:16]
        + slot[17:19]
        + "Z"
    )
    kind = "success" if success else "failure"
    name = f"{kind}-{compact}-run-{run_id}.tar.gz"
    archive = archive_bytes(rows)
    receipt = {
        "durable_asset_name": name,
        "durable_asset_sha256": hashlib.sha256(archive).hexdigest(),
        "durable_asset_size_bytes": len(archive),
        "durable_release_tag": "athena-fresh-holdout-evidence-2026-W34",
        "nominal_scheduled_for_utc": slot,
        "tick_committed": success,
        "tick_exit_code": 0 if success else 1,
        "workflow_run_id": run_id,
    }
    receipt_raw = canonical(receipt)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, archive)
        zf.writestr("fresh-holdout-tick-receipt.json", receipt_raw)
    zip_raw = zipped.getvalue()
    return {
        "artifact_name": name,
        "archive": archive,
        "receipt": receipt_raw,
        "zip": zip_raw,
        "zip_digest": "sha256:" + hashlib.sha256(zip_raw).hexdigest(),
    }


def run(run_id, created_at, *, head_sha, status="completed", conclusion="success"):
    return {
        "id": run_id,
        "name": audit.WORKFLOW_NAME,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": head_sha,
        "path": audit.WORKFLOW_PATH + "@refs/heads/main",
        "created_at": created_at,
        "status": status,
        "conclusion": conclusion,
    }


class FakeGitHub:
    def __init__(
        self,
        runs,
        bundles,
        *,
        sidecars=True,
        release_mismatch=False,
        digest_mismatch=False,
        sidecar_mismatch=False,
    ):
        self.runs = list(runs)
        self.bundles = dict(bundles)
        self.sidecars = sidecars
        self.release_mismatch = release_mismatch
        self.digest_mismatch = digest_mismatch
        self.sidecar_mismatch = sidecar_mismatch
        self.page_calls = []
        self.release_bytes = {}
        self.release_assets = {}
        next_id = 10000
        for run_id, bundle in self.bundles.items():
            archive_id = next_id
            next_id += 1
            receipt_id = next_id
            next_id += 1
            archive = bundle["archive"]
            if release_mismatch and run_id == max(self.bundles):
                archive = archive + b"x"
            self.release_bytes[archive_id] = archive
            assets = [
                {
                    "id": archive_id,
                    "name": bundle["artifact_name"],
                    "size": len(bundle["archive"]),
                    "state": "uploaded",
                }
            ]
            if sidecars:
                receipt_bytes = bundle["receipt"]
                if sidecar_mismatch and run_id == max(self.bundles):
                    receipt_bytes = receipt_bytes + b"x"
                self.release_bytes[receipt_id] = receipt_bytes
                assets.append(
                    {
                        "id": receipt_id,
                        "name": bundle["artifact_name"] + ".receipt.json",
                        "size": len(bundle["receipt"]),
                        "state": "uploaded",
                    }
                )
            self.release_assets[run_id] = assets

    def main_ref(self):
        return {"object": {"sha": MAIN_SHA}}

    def runs_page(self, page, per_page):
        self.page_calls.append((page, per_page))
        start = (page - 1) * per_page
        return {"workflow_runs": self.runs[start : start + per_page]}

    def artifacts(self, run_id):
        bundle = self.bundles[run_id]
        digest = bundle["zip_digest"]
        if self.digest_mismatch and run_id == max(self.bundles):
            digest = "sha256:" + "0" * 64
        return {
            "artifacts": [
                {
                    "id": run_id + 5000,
                    "name": bundle["artifact_name"],
                    "expired": False,
                    "digest": digest,
                }
            ]
        }

    def artifact_zip(self, artifact_id):
        run_id = artifact_id - 5000
        return self.bundles[run_id]["zip"]

    def release(self, tag):
        assets = []
        for values in self.release_assets.values():
            assets.extend(values)
        return {"tag_name": tag, "assets": assets}

    def release_asset(self, asset_id):
        return self.release_bytes[asset_id]


def do_audit(fake):
    return audit.audit_actions_lineage(
        repository="Thabearr/ATHENA",
        expected_main_sha=MAIN_SHA,
        get_main_ref=fake.main_ref,
        get_runs_page=fake.runs_page,
        get_run_artifacts=fake.artifacts,
        download_artifact_zip=fake.artifact_zip,
        get_release=fake.release,
        download_release_asset=fake.release_asset,
        verify_dependencies=False,
    )


def test_first_slot_success_is_committed_with_exact_run_identity():
    b = evidence_bundle(
        101,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(101, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {101: b},
    )
    result = do_audit(fake)
    assert result["first_nominal_slot_status"] == "FIRST_SLOT_COMMITTED"
    assert result["first_nominal_slot_run_id"] == 101
    assert result["first_nominal_slot_head_sha"] == HEAD_1
    assert result["audit_state"] == "VERIFIED_COMPLETE_TO_LATEST_OBSERVED_RUN"


def test_later_gap_proves_first_slot_missing_without_inventing_run():
    rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        committed("2026-08-19T00:37:00Z"),
    ]
    b = evidence_bundle(102, "2026-08-19T00:37:00Z", rows=rows)
    fake = FakeGitHub(
        [run(102, "2026-08-19T00:38:00Z", head_sha=HEAD_2)],
        {102: b},
    )
    result = do_audit(fake)
    assert result["first_nominal_slot_status"] == "FIRST_SLOT_DURABLY_RECORDED_MISSING"
    assert result["first_nominal_slot_run_id"] is None
    assert result["first_nominal_slot_head_sha"] is None


def test_verified_first_slot_failure_remains_uncommitted_until_gap_witness():
    b = evidence_bundle(
        103,
        "2026-08-19T00:07:00Z",
        success=False,
        rows=[failure_event()],
    )
    fake = FakeGitHub(
        [run(103, "2026-08-19T00:08:00Z", head_sha=HEAD_1, conclusion="failure")],
        {103: b},
    )
    result = do_audit(fake)
    assert result["first_nominal_slot_status"] == "FIRST_SLOT_VERIFIED_UNCOMMITTED_ATTEMPT"
    assert result["verified_failure_count"] == 1


def test_failure_then_gap_makes_durable_missing_authoritative_but_keeps_failed_run():
    b1 = evidence_bundle(104, "2026-08-19T00:07:00Z", success=False, rows=[failure_event()])
    rows2 = [
        failure_event(),
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        committed("2026-08-19T00:37:00Z"),
    ]
    b2 = evidence_bundle(105, "2026-08-19T00:37:00Z", rows=rows2)
    fake = FakeGitHub(
        [
            run(104, "2026-08-19T00:08:00Z", head_sha=HEAD_1, conclusion="failure"),
            run(105, "2026-08-19T00:38:00Z", head_sha=HEAD_2),
        ],
        {104: b1, 105: b2},
    )
    result = do_audit(fake)
    assert result["first_nominal_slot_status"] == "FIRST_SLOT_DURABLY_RECORDED_MISSING"
    assert result["first_nominal_slot_run_id"] == 104
    assert any(r["run_id"] == 104 and r["tick_committed"] is False for r in result["runs"])


def test_expanding_repeated_gap_ranges_are_consistent_not_contradictory():
    rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            "2026-08-19T01:07:00Z",
            2,
        ),
    ]
    committed_slots, missing_slots = audit.validate_control_lineage(rows)
    assert committed_slots == set()
    assert missing_slots == {0, 1}


def test_commit_inside_prior_gap_fails_closed():
    rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        committed("2026-08-19T00:07:00Z"),
        committed("2026-08-19T00:37:00Z"),
    ]
    b = evidence_bundle(106, "2026-08-19T00:37:00Z", rows=rows)
    fake = FakeGitHub(
        [run(106, "2026-08-19T00:38:00Z", head_sha=HEAD_2)],
        {106: b},
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(fake)


def test_two_verified_runs_for_same_nominal_slot_fail_closed():
    b1 = evidence_bundle(
        107,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    b2 = evidence_bundle(
        108,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [
            run(107, "2026-08-19T00:08:00Z", head_sha=HEAD_1),
            run(108, "2026-08-19T00:09:00Z", head_sha=HEAD_2),
        ],
        {107: b1, 108: b2},
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(fake)


def test_duplicate_committed_control_row_fails_closed():
    rows = [
        committed("2026-08-19T00:07:00Z"),
        committed("2026-08-19T00:07:00Z"),
    ]
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(rows)


@pytest.mark.parametrize(
    "row",
    [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            2,
        ),
        gap(
            "2026-08-19T00:37:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T01:07:00Z",
            1,
        ),
    ],
)
def test_malformed_gap_range_or_count_fails_closed(row):
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage([row])


def test_gap_detection_must_advance_in_append_order():
    rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            "2026-08-19T01:07:00Z",
            2,
        ),
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
    ]
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(rows)


def test_artifact_digest_mismatch_is_partial_never_verified():
    b = evidence_bundle(
        109,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(109, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {109: b},
        digest_mismatch=True,
    )
    result = do_audit(fake)
    assert result["verified_completed_run_count"] == 0
    assert result["unverified_completed_run_count"] == 1
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_receipt_archive_hash_mismatch_never_becomes_verified():
    b = evidence_bundle(
        115,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    with zipfile.ZipFile(io.BytesIO(b["zip"]), "r") as source:
        receipt = source.read("fresh-holdout-tick-receipt.json")
    changed_archive = b["archive"] + b"tamper"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(b["artifact_name"], changed_archive)
        zf.writestr("fresh-holdout-tick-receipt.json", receipt)
    b["zip"] = out.getvalue()
    b["zip_digest"] = "sha256:" + hashlib.sha256(b["zip"]).hexdigest()
    fake = FakeGitHub(
        [run(115, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {115: b},
    )
    result = do_audit(fake)
    assert result["verified_completed_run_count"] == 0
    assert result["unverified_completed_run_count"] == 1


def test_release_sidecar_byte_mismatch_is_partial_durability():
    b = evidence_bundle(
        116,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(116, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {116: b},
        sidecar_mismatch=True,
    )
    result = do_audit(fake)
    assert result["runs"][0]["release_state"] == "RELEASE_DURABILITY_UNVERIFIED"
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_release_archive_mismatch_is_reported_as_partial_durability():
    b = evidence_bundle(
        110,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(110, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {110: b},
        release_mismatch=True,
    )
    result = do_audit(fake)
    assert result["runs"][0]["release_state"] == "RELEASE_DURABILITY_UNVERIFIED"
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_missing_release_sidecar_is_reported_without_repair():
    b = evidence_bundle(
        111,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(111, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {111: b},
        sidecars=False,
    )
    result = do_audit(fake)
    assert result["runs"][0]["release_state"] == "RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING"
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_wrong_current_main_blocks_before_evidence_read():
    b = evidence_bundle(
        112,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(112, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {112: b},
    )
    fake.main_ref = lambda: {"object": {"sha": "b" * 40}}
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(fake)


def test_more_than_one_hundred_runs_are_paginated():
    runs = [
        {
            "id": 2000 + i,
            "name": "irrelevant",
            "event": "schedule",
            "head_branch": "main",
            "head_sha": HEAD_1,
            "path": "other.yml",
            "created_at": f"2026-08-19T{(i // 60) % 24:02d}:{i % 60:02d}:00Z",
            "status": "completed",
            "conclusion": "success",
        }
        for i in range(120)
    ]
    fake = FakeGitHub(runs, {})
    result = do_audit(fake)
    assert len(fake.page_calls) == 2
    assert result["audit_state"] == "NO_COMPLETED_CAMPAIGN_EVIDENCE"


def test_in_progress_run_is_not_committed_evidence_and_makes_audit_partial():
    fake = FakeGitHub(
        [
            run(
                113,
                "2026-08-19T00:08:00Z",
                head_sha=HEAD_1,
                status="in_progress",
                conclusion=None,
            )
        ],
        {},
    )
    result = do_audit(fake)
    assert result["verified_completed_run_count"] == 0
    assert result["incomplete_run_count"] == 1
    assert result["runs"][0]["evidence_state"] == "INCOMPLETE_NOT_EVIDENCE"
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_unknown_control_event_fails_closed():
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage([{"schema_version": 1, "event": "MAGIC_BACKFILL"}])


def test_every_safety_authority_is_false():
    b = evidence_bundle(
        114,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    fake = FakeGitHub(
        [run(114, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
        {114: b},
    )
    result = do_audit(fake)
    assert result["safety"]
    assert not any(result["safety"].values())


def test_workflow_is_owner_only_exact_command_read_only_and_immutable_pinned():
    text = Path(
        ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
    ).read_text()
    assert "github.event.issue.number == 170" in text
    assert "github.event.comment.user.login == github.repository_owner" in text
    assert "READ_ONLY_ACTIONS_LINEAGE_AUDIT" in text
    assert "([0-9a-f]{40})" in text
    assert "actions: read" in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    assert "rerun" not in text.lower()
    assert "11d5960a326750d5838078e36cf38b85af677262" in text
    assert "a26af69be951a213d495a4c3e4e4022e16d87065" in text
    assert "ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "f28e40c7f34bde8b3046d885e986cb6290c5673b" in text
    assert "fotmob.com" not in text.lower()
    assert "sportybet" not in text.lower()
    assert "sportradar" not in text.lower()
    result_heading = "ATHENA FRESH-HOLDOUT LINEAGE AUDIT"
    assert result_heading in text
    assert not result_heading.startswith("/athena-audit-fresh-holdout-lineage")
