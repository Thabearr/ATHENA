from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest
import yaml

import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit


MAIN_SHA = "a" * 40
HEAD_1 = "1" * 40
HEAD_2 = "2" * 40
RELEASE_TAG = "athena-fresh-holdout-evidence-2026-W34"


def canonical(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def committed(slot):
    return {
        "backfill_or_retrofill_performed": False,
        "committed_at_utc": slot,
        "event": "TICK_COMMITTED",
        "nominal_schedule_time_used_as_observation_time": False,
        "schema_version": 1,
        "scheduled_for_utc": slot,
    }


def gap(first, last, detected, count, previous=None):
    return {
        "backfill_authorized": False,
        "detected_at_scheduled_for_utc": detected,
        "event": "SCHEDULER_GAP_RANGE",
        "first_missing_tick_utc": first,
        "last_missing_tick_utc": last,
        "missing_tick_count": count,
        "previous_committed_tick_utc": previous,
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
        if rows:
            info = tarfile.TarInfo(member)
            info.size = len(body)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(body))
        else:
            root = tarfile.TarInfo(
                ".cache/athena-research/fotmob-utc-native-xg-fresh-holdout"
            )
            root.type = tarfile.DIRTYPE
            root.mode = 0o700
            tar.addfile(root)
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
    materialized = []
    for source in rows:
        row = dict(source)
        if row.get("event") == "TICK_COMMITTED" and row.get("scheduled_for_utc") == slot:
            row["durable_release_tag"] = RELEASE_TAG
            row["durable_asset_name"] = name
        materialized.append(row)
    archive = archive_bytes(materialized)
    minute = int(slot[14:16])
    receipt = {
        "durable_asset_name": name,
        "durable_asset_sha256": hashlib.sha256(archive).hexdigest(),
        "durable_asset_size_bytes": len(archive),
        "durable_release_tag": RELEASE_TAG,
        "failure_lineage_reconcile_outcome": "skipped" if success else "success",
        "nominal_scheduled_for_utc": slot,
        "tick_committed": success,
        "tick_exit_code": 0 if success else 1,
        "workflow_event_schedule": (
            "7 * * * *" if minute == 7 else "37 * * * *"
        ),
        "workflow_run_id": run_id,
    }
    if success:
        receipt.update(
            {
                "runner_id": audit.activation.RUNNER_ID,
                "safety": {
                    key: False for key in audit.activation.SAFETY_KEYS
                },
                "scheduled_for_utc": slot,
                "schema_version": 1,
            }
        )
    receipt_raw = canonical(receipt)
    zipped = io.BytesIO()
    with zipfile.ZipFile(
        zipped, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
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


def replace_receipt(bundle, mutate):
    with zipfile.ZipFile(io.BytesIO(bundle["zip"]), "r") as source:
        receipt = json.loads(source.read("fresh-holdout-tick-receipt.json"))
    mutate(receipt)
    receipt_raw = canonical(receipt)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(bundle["artifact_name"], bundle["archive"])
        zf.writestr("fresh-holdout-tick-receipt.json", receipt_raw)
    bundle["receipt"] = receipt_raw
    bundle["zip"] = out.getvalue()
    bundle["zip_digest"] = (
        "sha256:" + hashlib.sha256(bundle["zip"]).hexdigest()
    )


def run(
    run_id,
    created_at,
    *,
    head_sha,
    status="completed",
    conclusion="success",
):
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
        self.digest_mismatch = digest_mismatch
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
                    receipt_bytes += b"x"
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
        return self.bundles[artifact_id - 5000]["zip"]

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
    bundle = evidence_bundle(
        101,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(101, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {101: bundle},
        )
    )
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
    result = do_audit(
        FakeGitHub(
            [run(102, "2026-08-19T00:38:00Z", head_sha=HEAD_2)],
            {102: evidence_bundle(102, "2026-08-19T00:37:00Z", rows=rows)},
        )
    )
    assert result["first_nominal_slot_status"] == (
        "FIRST_SLOT_DURABLY_RECORDED_MISSING"
    )
    assert result["first_nominal_slot_run_id"] is None
    assert result["first_nominal_slot_head_sha"] is None


def test_minimal_first_slot_failure_is_verified_uncommitted_attempt():
    bundle = evidence_bundle(
        103,
        "2026-08-19T00:07:00Z",
        success=False,
        rows=(),
    )
    result = do_audit(
        FakeGitHub(
            [
                run(
                    103,
                    "2026-08-19T00:08:00Z",
                    head_sha=HEAD_1,
                    conclusion="failure",
                )
            ],
            {103: bundle},
        )
    )
    assert result["first_nominal_slot_status"] == (
        "FIRST_SLOT_VERIFIED_UNCOMMITTED_ATTEMPT"
    )
    assert result["verified_failure_count"] == 1


def test_failure_then_gap_makes_durable_missing_but_keeps_failed_run_visible():
    first = evidence_bundle(
        104,
        "2026-08-19T00:07:00Z",
        success=False,
        rows=(),
    )
    later_rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        committed("2026-08-19T00:37:00Z"),
    ]
    result = do_audit(
        FakeGitHub(
            [
                run(
                    104,
                    "2026-08-19T00:08:00Z",
                    head_sha=HEAD_1,
                    conclusion="failure",
                ),
                run(105, "2026-08-19T00:38:00Z", head_sha=HEAD_2),
            ],
            {
                104: first,
                105: evidence_bundle(
                    105, "2026-08-19T00:37:00Z", rows=later_rows
                ),
            },
        )
    )
    assert result["first_nominal_slot_status"] == (
        "FIRST_SLOT_DURABLY_RECORDED_MISSING"
    )
    assert result["first_nominal_slot_run_id"] == 104
    assert any(
        row["run_id"] == 104 and row["tick_committed"] is False
        for row in result["runs"]
    )


def test_failure_archive_may_preserve_qualification_failure_control_evidence():
    bundle = evidence_bundle(
        106,
        "2026-08-19T00:07:00Z",
        success=False,
        rows=[failure_event()],
    )
    result = do_audit(
        FakeGitHub(
            [
                run(
                    106,
                    "2026-08-19T00:08:00Z",
                    head_sha=HEAD_1,
                    conclusion="failure",
                )
            ],
            {106: bundle},
        )
    )
    assert result["verified_failure_count"] == 1


def test_expanding_repeated_gap_ranges_match_producer_semantics():
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


def test_gap_after_commit_must_bind_previous_committed_anchor():
    rows = [
        committed("2026-08-19T00:07:00Z"),
        gap(
            "2026-08-19T00:37:00Z",
            "2026-08-19T00:37:00Z",
            "2026-08-19T01:07:00Z",
            1,
            previous="2026-08-19T00:07:00Z",
        ),
        committed("2026-08-19T01:07:00Z"),
    ]
    committed_slots, missing_slots = audit.validate_control_lineage(rows)
    assert committed_slots == {0, 2}
    assert missing_slots == {1}


def test_commit_inside_prior_gap_fails_closed():
    rows = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            1,
        ),
        committed("2026-08-19T00:07:00Z"),
    ]
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(rows)


def test_duplicate_committed_row_fails_closed():
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(
            [
                committed("2026-08-19T00:07:00Z"),
                committed("2026-08-19T00:07:00Z"),
            ]
        )


def test_malformed_gap_count_and_reversed_detection_fail_closed():
    bad = [
        gap(
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:07:00Z",
            "2026-08-19T00:37:00Z",
            2,
        ),
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
        audit.validate_control_lineage([bad[0]])
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(bad[1:])


def test_unknown_control_event_fails_closed():
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        audit.validate_control_lineage(
            [{"schema_version": 1, "event": "MAGIC_BACKFILL"}]
        )


def test_artifact_digest_mismatch_is_partial_never_verified():
    bundle = evidence_bundle(
        109,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(109, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {109: bundle},
            digest_mismatch=True,
        )
    )
    assert result["verified_completed_run_count"] == 0
    assert result["unverified_completed_run_count"] == 1
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_receipt_archive_hash_mismatch_is_never_verified():
    bundle = evidence_bundle(
        110,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    with zipfile.ZipFile(io.BytesIO(bundle["zip"]), "r") as source:
        receipt = source.read("fresh-holdout-tick-receipt.json")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(bundle["artifact_name"], bundle["archive"] + b"tamper")
        zf.writestr("fresh-holdout-tick-receipt.json", receipt)
    bundle["zip"] = out.getvalue()
    bundle["zip_digest"] = (
        "sha256:" + hashlib.sha256(bundle["zip"]).hexdigest()
    )
    result = do_audit(
        FakeGitHub(
            [run(110, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {110: bundle},
        )
    )
    assert result["verified_completed_run_count"] == 0
    assert result["unverified_completed_run_count"] == 1


def test_release_archive_mismatch_is_partial_durability():
    bundle = evidence_bundle(
        111,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(111, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {111: bundle},
            release_mismatch=True,
        )
    )
    assert result["runs"][0]["release_state"] == (
        "RELEASE_DURABILITY_UNVERIFIED"
    )
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_missing_release_sidecar_is_reported_without_repair():
    bundle = evidence_bundle(
        112,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(112, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {112: bundle},
            sidecars=False,
        )
    )
    assert result["runs"][0]["release_state"] == (
        "RELEASE_ARCHIVE_VERIFIED_RECEIPT_MISSING"
    )
    assert result["audit_state"] == "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"


def test_release_sidecar_byte_mismatch_is_partial_durability():
    bundle = evidence_bundle(
        113,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(113, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {113: bundle},
            sidecar_mismatch=True,
        )
    )
    assert result["runs"][0]["release_state"] == (
        "RELEASE_DURABILITY_UNVERIFIED"
    )


def test_wrong_current_main_blocks_before_evidence_read():
    fake = FakeGitHub([], {})
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
            "created_at": (
                f"2026-08-19T{(i // 60) % 24:02d}:{i % 60:02d}:00Z"
            ),
            "status": "completed",
            "conclusion": "success",
        }
        for i in range(120)
    ]
    fake = FakeGitHub(runs, {})
    result = do_audit(fake)
    assert len(fake.page_calls) == 2
    assert result["audit_state"] == "NO_COMPLETED_CAMPAIGN_EVIDENCE"


def test_in_progress_run_is_not_evidence_and_makes_audit_partial():
    fake = FakeGitHub(
        [
            run(
                114,
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


def test_two_verified_runs_for_same_nominal_slot_fail_closed():
    one = evidence_bundle(
        115,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    two = evidence_bundle(
        116,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(
            FakeGitHub(
                [
                    run(115, "2026-08-19T00:08:00Z", head_sha=HEAD_1),
                    run(116, "2026-08-19T00:09:00Z", head_sha=HEAD_2),
                ],
                {115: one, 116: two},
            )
        )


def test_later_success_cannot_leave_an_earlier_slot_unresolved():
    bundle = evidence_bundle(
        117,
        "2026-08-19T00:37:00Z",
        rows=[committed("2026-08-19T00:37:00Z")],
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(
            FakeGitHub(
                [run(117, "2026-08-19T00:38:00Z", head_sha=HEAD_2)],
                {117: bundle},
            )
        )


def test_run_created_at_cannot_predate_proven_nominal_slot():
    bundle = evidence_bundle(
        118,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(
            FakeGitHub(
                [run(118, "2026-08-19T00:06:59Z", head_sha=HEAD_1)],
                {118: bundle},
            )
        )


def test_success_receipt_runner_schema_schedule_and_safety_are_bound():
    mutators = [
        lambda value: value.__setitem__("runner_id", "OTHER"),
        lambda value: value.__setitem__("schema_version", 2),
        lambda value: value.__setitem__("workflow_event_schedule", "37 * * * *"),
        lambda value: value["safety"].__setitem__(
            next(iter(value["safety"])), True
        ),
    ]
    for offset, mutate in enumerate(mutators):
        run_id = 120 + offset
        bundle = evidence_bundle(
            run_id,
            "2026-08-19T00:07:00Z",
            rows=[committed("2026-08-19T00:07:00Z")],
        )
        replace_receipt(bundle, mutate)
        with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
            do_audit(
                FakeGitHub(
                    [
                        run(
                            run_id,
                            "2026-08-19T00:08:00Z",
                            head_sha=HEAD_1,
                        )
                    ],
                    {run_id: bundle},
                )
            )


def test_failure_optional_rich_fields_fail_closed_if_present_and_wrong():
    bundle = evidence_bundle(
        124,
        "2026-08-19T00:07:00Z",
        success=False,
        rows=(),
    )
    replace_receipt(bundle, lambda value: value.__setitem__("runner_id", "OTHER"))
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(
            FakeGitHub(
                [
                    run(
                        124,
                        "2026-08-19T00:08:00Z",
                        head_sha=HEAD_1,
                        conclusion="failure",
                    )
                ],
                {124: bundle},
            )
        )


def test_success_commit_row_must_bind_release_and_asset_identity():
    slot = "2026-08-19T00:07:00Z"
    bundle = evidence_bundle(125, slot, rows=[committed(slot)])
    with zipfile.ZipFile(io.BytesIO(bundle["zip"]), "r") as source:
        receipt = source.read("fresh-holdout-tick-receipt.json")
    bad_row = committed(slot)
    bad_row["durable_release_tag"] = RELEASE_TAG
    bad_row["durable_asset_name"] = "success-20260819T000700Z-run-999.tar.gz"
    bad_archive = archive_bytes([bad_row])
    receipt_value = json.loads(receipt)
    receipt_value["durable_asset_sha256"] = hashlib.sha256(bad_archive).hexdigest()
    receipt_value["durable_asset_size_bytes"] = len(bad_archive)
    bad_receipt = canonical(receipt_value)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(bundle["artifact_name"], bad_archive)
        zf.writestr("fresh-holdout-tick-receipt.json", bad_receipt)
    bundle["archive"] = bad_archive
    bundle["receipt"] = bad_receipt
    bundle["zip"] = out.getvalue()
    bundle["zip_digest"] = "sha256:" + hashlib.sha256(bundle["zip"]).hexdigest()
    with pytest.raises(audit.FreshHoldoutActionsLineageAuditError):
        do_audit(
            FakeGitHub(
                [run(125, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
                {125: bundle},
            )
        )


def test_every_output_safety_authority_is_false():
    bundle = evidence_bundle(
        130,
        "2026-08-19T00:07:00Z",
        rows=[committed("2026-08-19T00:07:00Z")],
    )
    result = do_audit(
        FakeGitHub(
            [run(130, "2026-08-19T00:08:00Z", head_sha=HEAD_1)],
            {130: bundle},
        )
    )
    assert result["safety"]
    assert not any(result["safety"].values())


def test_workflow_parses_as_yaml():
    text = Path(
        ".github/workflows/audit-fotmob-utc-native-xg-fresh-holdout-lineage.yml"
    ).read_text()
    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert "jobs" in parsed and "audit" in parsed["jobs"]


def test_workflow_is_owner_only_read_only_exact_and_immutable_pinned():
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
    for pin in (
        "11d5960a326750d5838078e36cf38b85af677262",
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "ea165f8d65b6e75b540449e92b4886f43607fa02",
        "f28e40c7f34bde8b3046d885e986cb6290c5673b",
        "901ab137d6601a3485eac30da7e6bad7eeefa397",
        "ddabb6ae83cbe6c81c9264119a121a54715df960",
        "2310d2253b00b8ddd995d7a28e0d67e6ea9381dd",
        "aaf8dbe8534dfc10b707d34511fd4327dc81850e",
    ):
        assert pin in text
    assert "fotmob.com" not in text.lower()
    assert "sportybet" not in text.lower()
    assert "sportradar" not in text.lower()
    assert "ATHENA FRESH-HOLDOUT LINEAGE AUDIT" in text
    assert "issue_number: 170" in text
