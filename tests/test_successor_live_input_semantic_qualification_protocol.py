from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from domain.successor_live_input_semantic_qualification_protocol import (
    AGGREGATE_ROLE,
    ELO_INITIALIZATION_SEMANTICS,
    FATIGUE_PR31_SEMANTIC_EQUIVALENCE,
    LIVE_DATA_FRESHNESS_ROLE,
    NO_RESULT_STATE,
    PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA,
    PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA,
    PR69_HISTORICAL_REPLAY_BLOB_SHA,
    PR72_SUCCESSOR_PROTOCOL_BLOB_SHA,
    PR77_MAIN_SHA,
    PR77_ROBUSTNESS_RECEIPT_SHA256,
    PROTOCOL_ID,
    PROTOCOL_SCOPE,
    SUCCESSOR_CANDIDATE_SHA256,
    SemanticQualificationStatus,
    SuccessorLiveInputSemanticQualificationProtocolError,
    build_successor_live_input_semantic_qualification_protocol,
    canonical_successor_live_input_semantic_qualification_protocol_bytes,
    revalidate_successor_live_input_semantic_qualification_protocol,
    sha256_successor_live_input_semantic_qualification_protocol,
)


MODULE_PATH = Path("domain/successor_live_input_semantic_qualification_protocol.py")
PR31_PATH = Path("domain/fixture_model_features.py")
PR66_PATH = Path("domain/fotmob_reviewed_match_details_model_feature_handoff.py")
PR69_PATH = Path("domain/historical_model_feature_replay_candidate.py")
PR72_PATH = Path("domain/historical_expected_goals_successor_protocol.py")
PR77_RECEIPT_PATH = Path(
    "artifacts/research-manifests/"
    "historical-expected-goals-successor-robustness-real-corpus-receipt-v1.json"
)
EXPECTED_PROTOCOL_SHA256 = "a8716a9c2edae97dc5e2b904265cecc98254485f830673b341dd063883358177"
EXPECTED_PROTOCOL_SIZE = 4664


def _protocol():
    return build_successor_live_input_semantic_qualification_protocol()


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def test_exact_reviewed_ancestry_is_bound_to_checked_out_sources() -> None:
    protocol = _protocol()
    assert protocol.ancestry.repository_main_sha == PR77_MAIN_SHA
    assert _git_blob_sha(PR31_PATH) == PR31_FIXTURE_MODEL_FEATURES_BLOB_SHA
    assert _git_blob_sha(PR66_PATH) == PR66_MODEL_FEATURE_HANDOFF_BLOB_SHA
    assert _git_blob_sha(PR69_PATH) == PR69_HISTORICAL_REPLAY_BLOB_SHA
    assert _git_blob_sha(PR72_PATH) == PR72_SUCCESSOR_PROTOCOL_BLOB_SHA

    receipt_raw = PR77_RECEIPT_PATH.read_bytes()
    assert hashlib.sha256(receipt_raw).hexdigest() == PR77_ROBUSTNESS_RECEIPT_SHA256
    receipt = json.loads(receipt_raw)
    assert receipt["ancestry"]["successor_candidate_sha256"] == SUCCESSOR_CANDIDATE_SHA256
    assert receipt["evaluation"]["semantic_caveats"]["fatigue_pr31_semantic_equivalence"] == "UNPROVEN"
    assert receipt["evaluation"]["semantic_caveats"]["elo_initialization_semantics"] == ELO_INITIALIZATION_SEMANTICS


def test_protocol_identity_canonical_hash_and_size_are_frozen() -> None:
    protocol = _protocol()
    raw = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    assert protocol.schema_version == 1
    assert protocol.protocol_id == PROTOCOL_ID
    assert protocol.scope == PROTOCOL_SCOPE
    assert len(raw) == EXPECTED_PROTOCOL_SIZE
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_PROTOCOL_SHA256
    assert sha256_successor_live_input_semantic_qualification_protocol(protocol) == EXPECTED_PROTOCOL_SHA256
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert raw == (json.dumps(protocol.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def test_successor_predictor_set_order_and_transforms_are_exact() -> None:
    protocol = _protocol()
    assert protocol.successor_raw_feature_ids == (
        "home_elo",
        "away_elo",
        "home_form",
        "away_form",
        "fatigue",
    )
    assert [item.name for item in protocol.predictors] == [
        "intercept",
        "home_elo_centered_scaled",
        "away_elo_centered_scaled",
        "home_form_centered",
        "away_form_centered",
        "fatigue_raw",
    ]
    assert (protocol.predictors[1].center, protocol.predictors[1].scale) == (1500.0, 400.0)
    assert (protocol.predictors[2].center, protocol.predictors[2].scale) == (1500.0, 400.0)
    assert protocol.predictors[3].center == 0.5
    assert protocol.predictors[4].center == 0.5
    assert protocol.predictors[5].transform == "IDENTITY"
    assert all(item.source_feature_id != "live_data_freshness" for item in protocol.predictors)
    assert protocol.live_data_freshness_role == LIVE_DATA_FRESHNESS_ROLE


def test_historical_form_semantics_are_exact() -> None:
    form = _protocol().form_semantics
    assert form.chronology == "STRICTLY_PRIOR_FIXTURES_ORDERED_KICKOFF_DESCENDING"
    assert form.window_size == 5
    assert (form.win_points, form.draw_points, form.loss_points) == (3, 1, 0)
    assert (form.base, form.span, form.rounding_places) == (0.10, 0.85, 3)
    assert form.formula == "round(0.10+((points/(n*3))*0.85),3)"
    assert form.missing_history_behavior == "MISSING_PRIOR_HISTORY_NO_DEFAULT"


def test_historical_fatigue_semantics_are_exact_and_unproven_live() -> None:
    protocol = _protocol()
    fatigue = protocol.fatigue_semantics
    assert fatigue.chronology == "MOST_RECENT_STRICTLY_PRIOR_FIXTURE_PER_TEAM"
    assert fatigue.orientation == "HOME_REST_DAYS_MINUS_AWAY_REST_DAYS"
    assert fatigue.severe_threshold_days_exclusive == -2
    assert fatigue.mild_threshold_days_exclusive == 0
    assert (fatigue.severe_value, fatigue.mild_value, fatigue.neutral_value) == (0.30, 0.10, 0.0)
    assert fatigue.missing_history_behavior == "MISSING_PRIOR_HISTORY_NO_DEFAULT"
    assert protocol.fatigue_pr31_semantic_equivalence == FATIGUE_PR31_SEMANTIC_EQUIVALENCE == "UNPROVEN"


def test_historical_elo_semantics_are_exact_and_assumption_is_preserved() -> None:
    elo = _protocol().elo_semantics
    assert elo.chronology == "SOURCE_LOCAL_KICKOFF_ASC_PREMATCH_STATE_ONLY"
    assert elo.initial_overall_rating == 1500
    assert elo.home_advantage_points == 50
    assert elo.logistic_divisor == 400.0
    assert (elo.observed_score_win, elo.observed_score_draw, elo.observed_score_loss) == (1.0, 0.5, 0.0)
    assert elo.k_schedule == ((20, 32), (50, 24), (None, 16))
    assert elo.update_rule == "int(old_overall+K*(actual_score-expected_score))"
    assert elo.pre_match_feature_rule == "FEATURE_IS_CURRENT_OVERALL_RATING_BEFORE_TARGET_FIXTURE_UPDATE"
    assert elo.initialization_semantics == ELO_INITIALIZATION_SEMANTICS


def test_qualification_vocabulary_distinguishes_unavailable_provenance_and_mismatch() -> None:
    protocol = _protocol()
    assert protocol.qualification_statuses == tuple(item.value for item in SemanticQualificationStatus)
    assert set(protocol.qualification_statuses) == {
        "QUALIFIED_EXACT_SEMANTIC_EQUIVALENCE",
        "UNQUALIFIED_INSUFFICIENT_PROVENANCE",
        "UNQUALIFIED_DEFINITION_MISMATCH",
        "BLOCKED_SOURCE_FEATURE_UNAVAILABLE",
    }
    assert protocol.aggregate_role == AGGREGATE_ROLE
    assert "NEVER_MODEL_OR_PRODUCTION_AUTHORIZATION" in protocol.aggregate_role


def test_available_or_equal_numeric_value_never_implies_semantic_qualification() -> None:
    requirements = _protocol().evidence_requirements
    assert requirements.value_level_compatibility_required is True
    assert requirements.derivation_provenance_compatibility_required is True
    assert requirements.pr31_available_implies_qualified is False
    assert requirements.equal_numeric_value_implies_qualified is False
    assert requirements.qualification_requires_replayable_evidence_or_exact_reviewed_contract is True
    assert "PR31_AVAILABLE_STATUS_ONLY" in requirements.insufficient_proofs
    assert "SAME_CURRENT_VALUE" in requirements.insufficient_proofs
    assert "PROVIDER_LABEL_ELO_ONLY" in requirements.insufficient_proofs
    assert "FATIGUE_VALUE_MATCH_WITHOUT_DERIVATION_PROOF" in requirements.insufficient_proofs


def test_protocol_is_result_free_and_every_safety_flag_is_false() -> None:
    protocol = _protocol()
    assert protocol.no_result_state == NO_RESULT_STATE
    assert protocol.no_result_state == "PRE_REGISTERED_NOT_EXECUTED_NO_FEATURE_QUALIFIED"
    assert protocol.safety
    assert all(type(value) is bool and value is False for value in protocol.safety.values())
    for key in (
        "live_semantic_qualification_executed",
        "successor_live_inputs_qualified",
        "successor_candidate_approved",
        "expected_goals_transform_approved",
        "expected_goals_production_authorized",
        "score_matrix_authorized",
        "probability_inference_authorized",
        "pricing_authorized",
        "selection_authorized",
        "bet_authorized",
    ):
        assert protocol.safety[key] is False


def test_revalidator_accepts_only_exact_protocol_and_exact_bytes() -> None:
    protocol = _protocol()
    raw = canonical_successor_live_input_semantic_qualification_protocol_bytes(protocol)
    rebuilt = revalidate_successor_live_input_semantic_qualification_protocol(protocol=protocol, protocol_bytes=raw)
    assert rebuilt == protocol
    mutated = bytearray(raw)
    mutated[-2] = ord(" ") if mutated[-2] != ord(" ") else ord("\t")
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        revalidate_successor_live_input_semantic_qualification_protocol(protocol=protocol, protocol_bytes=bytes(mutated))
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        revalidate_successor_live_input_semantic_qualification_protocol(protocol=protocol, protocol_bytes=bytearray(raw))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository_main_sha", "f" * 40),
        ("pr31_fixture_model_features_blob_sha", "f" * 40),
        ("pr66_model_feature_handoff_blob_sha", "f" * 40),
        ("pr69_historical_replay_blob_sha", "f" * 40),
        ("pr72_successor_protocol_blob_sha", "f" * 40),
        ("successor_candidate_sha256", "f" * 64),
        ("pr77_robustness_receipt_sha256", "f" * 64),
    ],
)
def test_ancestry_mutations_fail_closed(field: str, value: str) -> None:
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(_protocol().ancestry, **{field: value})


@pytest.mark.parametrize(
    ("index", "changes"),
    [
        (1, {"center": 1499.0}),
        (1, {"scale": 800.0}),
        (2, {"scale": 800.0}),
        (3, {"center": 0.4}),
        (4, {"center": 0.4}),
        (5, {"transform": "VALUE_MINUS_CENTER", "center": 0.0}),
    ],
)
def test_predictor_transform_mutations_fail_closed(index: int, changes: dict[str, object]) -> None:
    protocol = _protocol()
    mutated_item = dataclasses.replace(protocol.predictors[index], **changes)
    mutated_predictors = list(protocol.predictors)
    mutated_predictors[index] = mutated_item
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, predictors=tuple(mutated_predictors))


def test_reordered_omitted_or_freshness_added_predictors_fail_closed() -> None:
    protocol = _protocol()
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, predictors=tuple(reversed(protocol.predictors)))
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, predictors=protocol.predictors[:-1])
    extra = dataclasses.replace(protocol.predictors[-1], name="freshness_raw", source_feature_id="fatigue")
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, predictors=protocol.predictors + (extra,))


@pytest.mark.parametrize(
    ("target", "changes"),
    [
        ("form_semantics", {"window_size": 4}),
        ("form_semantics", {"win_points": 2}),
        ("form_semantics", {"base": 0.0}),
        ("form_semantics", {"span": 1.0}),
        ("form_semantics", {"rounding_places": 4}),
        ("form_semantics", {"missing_history_behavior": "DEFAULT_ZERO"}),
        ("fatigue_semantics", {"severe_threshold_days_exclusive": -3}),
        ("fatigue_semantics", {"mild_threshold_days_exclusive": 1}),
        ("fatigue_semantics", {"orientation": "AWAY_REST_DAYS_MINUS_HOME_REST_DAYS"}),
        ("fatigue_semantics", {"missing_history_behavior": "DEFAULT_ZERO"}),
        ("elo_semantics", {"initial_overall_rating": 1400}),
        ("elo_semantics", {"home_advantage_points": 0}),
        ("elo_semantics", {"logistic_divisor": 800.0}),
        ("elo_semantics", {"k_schedule": ((20, 30), (50, 24), (None, 16))}),
        ("elo_semantics", {"update_rule": "round(old_overall+delta)"}),
        ("elo_semantics", {"pre_match_feature_rule": "POST_MATCH_RATING"}),
    ],
)
def test_historical_semantic_mutations_fail_closed(target: str, changes: dict[str, object]) -> None:
    protocol = _protocol()
    component = getattr(protocol, target)
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(component, **changes)


def test_safety_promotion_and_result_promotion_fail_closed() -> None:
    protocol = _protocol()
    promoted = dict(protocol.safety)
    promoted["successor_live_inputs_qualified"] = True
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, safety=promoted)
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, no_result_state="EXECUTED")
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(protocol, fatigue_pr31_semantic_equivalence="PROVEN")


def test_nan_in_protocol_components_is_rejected() -> None:
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(_protocol().predictors[1], scale=float("nan"))
    with pytest.raises(SuccessorLiveInputSemanticQualificationProtocolError):
        dataclasses.replace(_protocol().predictors[1], scale=float("inf"))


def test_module_has_only_inert_standard_library_imports() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "math",
        "types",
        "collections",
        "typing",
    }
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "requests",
        "httpx",
        "selenium",
        "playwright",
        "score_matrix",
        "match_analyst",
        "ml_engine",
        "pricing",
        "selection",
        "bookmaker",
    ):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source
