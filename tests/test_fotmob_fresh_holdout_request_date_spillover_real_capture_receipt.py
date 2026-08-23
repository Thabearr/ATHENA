from __future__ import annotations

import domain.fotmob_fresh_holdout_request_date_spillover_adapter as adapter


def test_preserved_spillover_evidence_identity_is_exact() -> None:
    receipt = adapter.adapter_receipt()
    assert receipt["source_actions_artifact_name"] == (
        "failure-20260823T013700Z-run-32612280129.tar.gz"
    )
    assert receipt["source_archive_sha256"] == (
        "359524b3477da9fc46a60dde41a0a2179631d735e1de4bfce7cea6fb1c6aa60c"
    )
    assert receipt["source_capture_observed_at"] == "2026-08-23T02:13:12.040926Z"
    assert receipt["source_capture_raw_sha256"] == (
        "445bc09a013fabf3bd953e2980ee54bee6e1fb8ab50f4686ab2de67bea02c023"
    )
    assert receipt["source_capture_manifest_sha256"] == (
        "7b763b0e55126529f1fd4879a2fe0170215ee3f467a28caad538ef77c8b561a8"
    )
    assert receipt["source_spillover_kickoffs"] == [
        "2026-08-22T23:07:00.000Z",
        "2026-08-22T23:30:00.000Z",
    ]
