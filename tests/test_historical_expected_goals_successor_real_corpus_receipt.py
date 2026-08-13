"""Canonical evidence checks for the frozen PR73 real-corpus execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = (
    REPOSITORY_ROOT
    / "artifacts"
    / "research-manifests"
    / "historical-expected-goals-successor-real-corpus-receipt-v1.json"
)
RECEIPT_SHA256 = "fd8b53b0429227f7595072156b6e06824e88ea53ae7c08807cac47b0a9821d32"
CANDIDATE_SHA256 = "1fe9ff5f0963355bb98ae93d205a5ea3cb9aa53592601a7b06ff4000f6091660"


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


def _comparisons(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {record["benchmark_id"]: record for record in records}


def test_receipt_is_exact_canonical_frozen_evidence() -> None:
    receipt, raw = _receipt()

    assert raw == _canonical_bytes(receipt)
    assert hashlib.sha256(raw).hexdigest() == RECEIPT_SHA256
    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == (
        "athena-historical-expected-goals-successor-real-corpus-receipt-v1"
    )
    assert receipt["scope"] == (
        "RETROSPECTIVE_CHRONOLOGICAL_SUCCESSOR_EXECUTION_RECEIPT_RESEARCH_ONLY"
    )


def test_receipt_embeds_the_exact_revalidated_pr73_candidate() -> None:
    receipt, _ = _receipt()
    candidate = receipt["candidate"]
    candidate_bytes = _canonical_bytes(candidate)

    assert hashlib.sha256(candidate_bytes).hexdigest() == CANDIDATE_SHA256
    assert len(candidate_bytes) == 19_956
    assert receipt["successor_candidate_sha256"] == CANDIDATE_SHA256
    assert receipt["successor_candidate_size"] == 19_956
    assert receipt["full_candidate_revalidation_succeeded"] is True


def test_receipt_preserves_exact_ancestry_and_crlf_provenance() -> None:
    receipt, _ = _receipt()

    assert receipt["repository_head"] == "9cce5fedef64919d8b9dc1c0f0fd2358dbd6bdb4"
    assert (receipt["source_file_count"], receipt["source_total_bytes"], receipt["source_fixture_count"]) == (66, 10_006_877, 21_226)
    assert receipt["source_corpus_sha256"] == "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
    assert (receipt["pr69_canonical_sha256"], receipt["pr69_canonical_size"]) == ("b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3", 39_952_730)
    assert receipt["pr70_validation_sha256"] == "c13287a28ac1ffc1bfc02b1ea283c34840a7a00eb14ec13cac39ca67c14ab5e5"
    assert receipt["pr71_receipt_sha256"] == "9680b108ac308df5f9d58f18ddacbb8ce1cda8e8806232519d4d327aea2d6da0"
    assert receipt["pr71_receipt_git_blob_oid"] == "d33097e128534588609d15c41ba25620254a6ac8"
    assert receipt["pr71_canonical_git_blob_bytes_used"] is True
    assert receipt["pr71_worktree_newline_conversion_observed"] is True
    assert receipt["pr71_worktree_converted_bytes_used_as_evidence"] is False
    assert (receipt["pr72_protocol_id"], receipt["pr72_protocol_sha256"], receipt["pr72_protocol_size"]) == ("HISTORICAL_EXPECTED_GOALS_SUCCESSOR_PROTOCOL_V1", "d1471dc1cd238b704f3df388e00413dd43a84b4e2d8a2e4700c67c8647996cbf", 4_726)


def test_split_coefficients_and_comparisons_are_the_frozen_result() -> None:
    receipt, _ = _receipt()
    fit = receipt["candidate"]["fit_evaluation"]
    assert fit["training_fixture_count"] == 14_130
    assert fit["training_season_counts"] == {"2020-21": 3517, "2021-22": 3566, "2022-23": 3536, "2023-24": 3511}
    assert fit["evaluation_fixture_count"] == 6_903
    assert fit["evaluation_season_counts"] == {"2024-25": 3468, "2025-26": 3435}
    assert fit["home_fit"]["coefficients"] == [0.394404544376, 0.892777950622, -0.837026702225, 0.147004464963, -0.064780063421, 0.098533203861]
    assert fit["away_fit"]["coefficients"] == [0.22497652413, -0.739617173734, 0.902201743673, -0.13631341715, 0.201174538524, -0.252063395175]
    assert fit["home_fit"]["newton_updates"] == fit["away_fit"]["newton_updates"] == 5
    comparisons = _comparisons(fit["comparisons"])
    assert set(comparisons) == {"PR68_FORM_COMPONENT", "PR68_ELO_FALLBACK_COMPONENT", "PR68_FROZEN_CONSTANT_BASELINE", "STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE"}
    assert all(record["candidate_minus_benchmark_nll"] < 0 and record["result"] == "BETTER" for record in comparisons.values())
    for season in fit["season_breakdown"]:
        assert season["group_key"] in {"2024-25", "2025-26"}
        assert all(record["candidate_minus_benchmark_nll"] < 0 for record in season["comparisons"])


def test_all_evaluation_leagues_beat_elo_and_rolling_without_combining_leagues() -> None:
    receipt, _ = _receipt()
    leagues = receipt["candidate"]["fit_evaluation"]["league_breakdown"]
    assert {record["group_key"] for record in leagues} == {"B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"}
    for league in leagues:
        comparisons = _comparisons(league["comparisons"])
        assert comparisons["PR68_ELO_FALLBACK_COMPONENT"]["candidate_minus_benchmark_nll"] < 0
        assert comparisons["STRICT_PREMATCH_ROLLING_IDENTITY_LEAGUE_BASELINE"]["candidate_minus_benchmark_nll"] < 0


def test_calibration_and_fatigue_caveats_remain_observable() -> None:
    receipt, _ = _receipt()
    candidate = receipt["candidate"]
    fit = candidate["fit_evaluation"]
    assert sum(bin_["count"] for bin_ in fit["home_calibration"]) == 6_903
    assert sum(bin_["count"] for bin_ in fit["away_calibration"]) == 6_903
    assert fit["home_calibration"][-2]["calibration_error"] > 0
    assert fit["home_calibration"][-1]["calibration_error"] > 0
    assert fit["away_calibration"][-2]["calibration_error"] > 0
    assert fit["away_calibration"][-1]["calibration_error"] > 0
    assert fit["home_fit"]["coefficients"][-1] > 0
    assert fit["away_fit"]["coefficients"][-1] < 0
    assert candidate["elo_initialization_semantics"] == "1500_REPLAY_INITIAL_STATE_ASSUMPTION_NOT_OBSERVED_EVIDENCE"
    assert candidate["fatigue_pr31_semantic_equivalence"] == "UNPROVEN"
    assert candidate["historical_freshness_regime_reconstructed"] is False
    assert all(value is False for value in candidate["safety"].values())
    assert receipt["tracked_repository_changes_caused_by_execution"] is False
