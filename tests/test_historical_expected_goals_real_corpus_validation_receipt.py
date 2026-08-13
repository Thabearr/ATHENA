from __future__ import annotations

import hashlib
import json
from pathlib import Path


RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "historical-expected-goals-real-corpus-validation-receipt-v1.json"
)
EXPECTED_RECEIPT_SHA256 = "9680b108ac308df5f9d58f18ddacbb8ce1cda8e8806232519d4d327aea2d6da0"
EXPECTED_SOURCE_CORPUS_SHA256 = "c273b4bff2b611e95248133340ff84803ce238814d5dfa7ded5f39fd3d6e25a0"
EXPECTED_PR70_VALIDATION_SHA256 = "c13287a28ac1ffc1bfc02b1ea283c34840a7a00eb14ec13cac39ca67c14ab5e5"
EXPECTED_SEASONS = {
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
    "2025-26",
}
EXPECTED_LEAGUES = {"B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1"}
EXPECTED_SAFETY_KEYS = {
    "historical_component_validation_approved",
    "expected_goals_transform_approved",
    "probability_inference_authorized",
    "score_matrix_authorized",
    "probability_adjustment_authorized",
    "calibration_for_production_authorized",
    "pricing_authorized",
    "market_activation_authorized",
    "selection_authorized",
    "production_approval_authorized",
    "bet_authorized",
}


def _load() -> tuple[bytes, dict]:
    raw = RECEIPT_PATH.read_bytes()
    return raw, json.loads(raw)


def test_receipt_is_exact_canonical_json_with_reviewed_ancestry() -> None:
    raw, receipt = _load()
    assert raw.endswith(b"\n")
    canonical = (
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert raw == canonical
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_RECEIPT_SHA256

    assert receipt["schema_version"] == 1
    assert receipt["dataset_name"] == "athena-historical-expected-goals-real-corpus-validation-receipt-v1"
    assert receipt["scope"] == "RETROSPECTIVE_REAL_CORPUS_EXECUTION_RECEIPT_RESEARCH_ONLY"

    execution = receipt["execution"]
    assert execution == {
        "pr69_revalidator_succeeded": True,
        "pr70_revalidator_succeeded": True,
        "repository_head": "d507c0ca6515cfa5ffbda6c26f388ec64e5c2f5f",
        "research_branch_head": "04b7a3443bf4d5b43dc47b3f3afe333e15c51fb2",
        "source_receipt_matched_pr69": True,
        "workflow_job_id": 94392777855,
        "workflow_run_id": 31683073429,
    }

    source = receipt["source"]
    assert source["source_file_count"] == 66
    assert source["source_total_bytes"] == 10_006_877
    assert source["fixture_count"] == 21_226
    assert source["source_corpus_sha256"] == EXPECTED_SOURCE_CORPUS_SHA256
    assert source["pr69_canonical_sha256"] == "b44166b9543a8f436e62a644efc5316ad12fcc260a4c2c5908ad112928bedfe3"
    assert source["pr69_canonical_size"] == 39_952_730

    validation = receipt["validation"]
    assert validation["pr70_validation_sha256"] == EXPECTED_PR70_VALIDATION_SHA256
    assert validation["pr70_canonical_size"] == 20_902
    assert validation["target_pr68_transform_id"] == "LEGACY_MATCH_ANALYST_POISSON_RATE_HEURISTIC_V1"
    assert validation["target_pr68_transform_spec_sha256"] == "e7a5959eef21be51a45e79da1aa174b164504223ed45774d32b23eb073b3716c"
    assert validation["validation_spec_id"] == "HISTORICAL_EXPECTED_GOALS_COMPONENT_VALIDATION_SPEC_V1"
    assert validation["validation_spec_sha256"] == "3e4380fa5456e212bbdc422d0b1310ba8a8daf792a38666796f349e096378ce1"
    assert validation["historical_freshness_regime_reconstructed"] is False


def test_both_components_beat_both_baselines_across_every_recorded_season_and_league() -> None:
    _, receipt = _load()
    for key, component_name in (("form", "FORM_COMPONENT"), ("elo_fallback", "ELO_FALLBACK_COMPONENT")):
        component = receipt["components"][key]
        assert component["component"] == component_name
        assert component["metrics"]["fixture_count"] == 21_033

        for benchmark_key in ("constant_baseline", "rolling_league_baseline"):
            benchmark = component[benchmark_key]
            assert benchmark["paired_fixture_count"] == 21_033
            assert benchmark["result"] == "BETTER"
            assert benchmark["candidate_minus_baseline_nll"] == (
                benchmark["candidate_mean_joint_nll"] - benchmark["baseline_mean_joint_nll"]
            )
            assert benchmark["candidate_minus_baseline_nll"] < 0.0

        seasons = component["season_breakdown"]
        leagues = component["league_breakdown"]
        assert {row[0] for row in seasons} == EXPECTED_SEASONS
        assert {row[0] for row in leagues} == EXPECTED_LEAGUES
        assert sum(row[1] for row in seasons) == 21_033
        assert sum(row[1] for row in leagues) == 21_033
        assert all(row[4] < 0.0 and row[6] < 0.0 for row in seasons)
        assert all(row[4] < 0.0 and row[6] < 0.0 for row in leagues)


def test_elo_is_descriptively_stronger_but_receipt_preserves_calibration_warning() -> None:
    _, receipt = _load()
    form = receipt["components"]["form"]
    elo = receipt["components"]["elo_fallback"]

    assert receipt["head_to_head"] == {
        "form_minus_elo_mean_joint_nll": 0.016446544284006492,
        "interpretation": "POSITIVE_MEANS_ELO_LOWER_NLL",
    }
    assert form["metrics"]["mean_joint_poisson_nll"] > elo["metrics"]["mean_joint_poisson_nll"]
    assert elo["constant_baseline"]["candidate_minus_baseline_nll"] < form["constant_baseline"]["candidate_minus_baseline_nll"]
    assert elo["rolling_league_baseline"]["candidate_minus_baseline_nll"] < form["rolling_league_baseline"]["candidate_minus_baseline_nll"]

    # The broad predictive signal is not calibration approval.  The populated
    # high-rate Elo buckets materially underpredict observed scoring.
    elo_home_high = next(row for row in elo["calibration"]["home"] if row[0:2] == [1.5, 2.0])
    elo_away_high = next(row for row in elo["calibration"]["away"] if row[0:2] == [1.5, 2.0])
    assert elo_home_high[2] == 6_533
    assert elo_home_high[5] == -0.4490093372110824
    assert elo_away_high[2] == 1_770
    assert elo_away_high[5] == -0.4963830508474576


def test_receipt_never_grants_model_probability_pricing_selection_or_betting_authority() -> None:
    _, receipt = _load()
    assert set(receipt["safety"]) == EXPECTED_SAFETY_KEYS
    assert all(value is False for value in receipt["safety"].values())

    serialized = json.dumps(receipt, sort_keys=True)
    for forbidden in (
        '"expected_goals_transform_approved": true',
        '"probability_inference_authorized": true',
        '"pricing_authorized": true',
        '"selection_authorized": true',
        '"bet_authorized": true',
    ):
        assert forbidden not in serialized
