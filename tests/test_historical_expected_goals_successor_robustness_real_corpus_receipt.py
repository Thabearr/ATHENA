"""Canonical evidence checks for the frozen PR75 real-corpus robustness execution receipt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "historical-expected-goals-successor-robustness-real-corpus-receipt-v1.json"
)
RECEIPT_SHA256 = "db90e0cbb1452a3267c346a190d5936d3576f20a935798e7a2b66e6c5f5c5b14"
EVALUATION_SHA256 = "3ff465edef9c4abd2f0d4dfcb4f776fea64103c0dc26941f44d2b09ba2e4066b"
SUCCESSOR_CANDIDATE_SHA256 = "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def _receipt() -> tuple[dict[str, object], bytes]:
    raw = RECEIPT_PATH.read_bytes()
    return json.loads(raw), raw


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    receipt, raw = _receipt()

    assert raw == _canonical_bytes(receipt)
    assert hashlib.sha256(raw).hexdigest() == RECEIPT_SHA256
    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == (
        "athena-historical-expected-goals-successor-robustness-real-corpus-receipt-v1"
    )
    assert receipt["scope"] == (
        "POST_HOC_PR74_ROBUSTNESS_EXECUTION_RECEIPT_RESEARCH_ONLY"
    )


def test_receipt_pins_exact_evaluation_identity_and_source_ancestry() -> None:
    receipt, _ = _receipt()
    evaluation = receipt["evaluation"]
    ancestry = receipt["ancestry"]
    source = receipt["source"]

    assert evaluation["canonical_sha256"] == EVALUATION_SHA256
    assert evaluation["canonical_size"] == 15_974
    assert evaluation["provenance"] == "SOURCE_BOUND_FULL_PR69_TO_PR75_REPLAY"
    assert source == {
        "corpus_sha256": "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0",
        "file_count": 66,
        "fixture_count": 21_226,
        "pr69_canonical_sha256": "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3",
        "pr69_canonical_size": 39_952_730,
        "total_bytes": 10_006_877,
    }
    assert ancestry["pr74_receipt_sha256"] == (
        "fd8b53b0429227f7595072156b6e06824e88ea53ae7c08807cac47b0a9821d32"
    )
    assert ancestry["successor_candidate_sha256"] == SUCCESSOR_CANDIDATE_SHA256
    assert ancestry["successor_candidate_size"] == 19_956
    assert (
        ancestry["pr75_protocol_id"],
        ancestry["pr75_protocol_sha256"],
        ancestry["pr75_protocol_size"],
    ) == (
        "HISTORICAL_EXPECTED_GOALS_SUCCESSOR_ROBUSTNESS_PROTOCOL_V1",
        "eaa2fd1f906f0a18c39f972d919a0393569c85dc8ad6038cbed10819fd2c0774",
        5_468,
    )


def test_receipt_preserves_exact_execution_transport() -> None:
    receipt, _ = _receipt()
    transport = receipt["execution_transport"]

    assert receipt["repository_main_sha"] == "02de50766e54cc362aeab3ff819c267c0dbab2f4"
    assert transport["workflow_run_id"] == 31750880150
    assert transport["workflow_job_id"] == 94616111481
    assert transport["disposable_branch"] == "research/pr76-real-robustness-20260813"
    assert transport["disposable_head_sha"] == "cbc0c50557d769dbb07ace8c7ad4dbcb7c88d52d"
    assert transport["artifact_id"] == 9200925635
    assert transport["artifact_zip_sha256"] == (
        "2eb664d288867250ac1822d400a231c6b937ced98d6b1302ea185143da5f44ed"
    )
    assert transport["runner_os"] == "Microsoft Windows Server 2025"
    assert transport["runner_image"] == "windows-2025-vs2026"
    assert transport["python_version"] == "3.12.10"
    assert transport["full_source_bound_revalidation_succeeded"] is True
    assert transport["main_unchanged_after_execution"] is True


def test_paired_nll_robustness_is_frozen_exactly() -> None:
    receipt, _ = _receipt()
    evaluation = receipt["evaluation"]
    paired = evaluation["paired_nll"]
    interpretation = evaluation["interpretation"]

    assert paired["full_estimate"] == -0.03694662075991243
    assert paired["jackknife_se"] == 0.004510654720214589
    assert paired["interval_lower"] == -0.045787504011533024
    assert paired["interval_upper"] == -0.028105737508291838
    assert paired["cluster_count"] == 22
    assert len(paired["leave_one_league_out"]) == 11
    assert len(paired["leave_one_season_out"]) == 2
    assert all(item["candidate_minus_elo_mean_nll"] < 0 for item in paired["leave_one_league_out"])
    assert all(item["candidate_minus_elo_mean_nll"] < 0 for item in paired["leave_one_season_out"])
    assert interpretation["paired_elo_interval_upper_below_zero"] is True
    assert interpretation["all_leave_one_league_out_deltas_negative"] is True
    assert interpretation["both_leave_one_season_out_deltas_negative"] is True


def test_same_fixture_calibration_frozen_summary_beats_elo() -> None:
    receipt, _ = _receipt()
    evaluation = receipt["evaluation"]
    summaries = evaluation["calibration_summaries"]
    deltas = evaluation["calibration_successor_minus_elo"]
    interpretation = evaluation["interpretation"]

    assert summaries["successor_home"]["wace"] == 0.05400574445723991
    assert summaries["elo_home"]["wace"] == 0.17873040706939
    assert summaries["successor_home"]["wsce"] == 0.006452547672985946
    assert summaries["elo_home"]["wsce"] == 0.06374291150237581
    assert summaries["successor_away"]["wace"] == 0.04955633485504618
    assert summaries["elo_away"]["wace"] == 0.10568318122555406
    assert summaries["successor_away"]["wsce"] == 0.004728965840436059
    assert summaries["elo_away"]["wsce"] == 0.023870877820877004
    assert deltas["home_wace"] < 0
    assert deltas["home_wsce"] < 0
    assert deltas["away_wace"] < 0
    assert deltas["away_wsce"] < 0
    assert interpretation["successor_lower_home_wace_than_same_fixture_elo"] is True
    assert interpretation["successor_lower_home_wsce_than_same_fixture_elo"] is True
    assert interpretation["successor_lower_away_wace_than_same_fixture_elo"] is True
    assert interpretation["successor_lower_away_wsce_than_same_fixture_elo"] is True


def test_fatigue_ablation_stability_and_safety_remain_research_only() -> None:
    receipt, _ = _receipt()
    evaluation = receipt["evaluation"]
    no_fatigue = evaluation["no_fatigue"]
    interpretation = evaluation["interpretation"]
    refits = evaluation["leave_one_training_season_refits"]

    assert no_fatigue["full_successor_mean_joint_nll"] == 2.9171103768278988
    assert no_fatigue["no_fatigue_mean_joint_nll"] == 2.9172918076940935
    assert no_fatigue["no_fatigue_minus_full_nll"] == 0.0001814308661947095
    assert interpretation["no_fatigue_ablation_better_than_full"] is False
    assert interpretation["home_fatigue_sign_stable_across_training_season_omissions"] is True
    assert interpretation["away_fatigue_sign_stable_across_training_season_omissions"] is True
    assert all(item["home_fatigue_coefficient"] > 0 for item in refits)
    assert all(item["away_fatigue_coefficient"] < 0 for item in refits)
    assert evaluation["semantic_caveats"]["fatigue_pr31_semantic_equivalence"] == "UNPROVEN"
    assert evaluation["semantic_caveats"]["historical_freshness_regime_reconstructed"] is False
    assert all(value is False for value in evaluation["safety"].values())
    assert receipt["tracked_repository_changes_caused_by_evaluation"] is False
