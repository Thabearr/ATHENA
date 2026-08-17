from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = (
    ROOT
    / ".github"
    / "workflows"
    / "execute-fotmob-utc-native-expected-goals-model-validation.yml"
)
DOC_PATH = ROOT / "docs" / "fotmob_utc_native_expected_goals_model_validation_execution.md"


def _text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict:
    value = yaml.safe_load(_text())
    assert isinstance(value, dict)
    return value


def test_execution_workflow_is_only_the_reviewed_owner_comment_lane() -> None:
    parsed = _workflow()
    assert parsed["name"] == (
        "Execute Reviewed FotMob UTC-Native Expected-Goals Model Validation"
    )
    assert set(parsed["jobs"]) == {"execute"}
    text = _text()
    assert "workflow_dispatch" not in text
    assert "github.event.issue.number == 145" in text
    assert "github.event.comment.user.login == 'Thabearr'" in text
    assert "/athena-run-fotmob-utc-native-expected-goals-validation" in text
    assert (
        "confirm: EXECUTE_REVIEWED_21129_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION"
        in text
    )
    assert "cancel-in-progress: false" in text


def test_execution_workflow_has_spent_attempt_current_main_and_upstream_guards() -> None:
    text = _text()
    for marker in (
        "Expected-goals execution-control PR must already be merged and closed.",
        "Current ${repository.default_branch}=",
        "ATHENA_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_ATTEMPT",
        "ATTEMPT_STARTED_NO_RESULT_YET",
        "automatic replay is forbidden and requires reviewed reconciliation.",
        "Exact successful V2 feature-qualification result receipt is missing or changed.",
        "upstreamResultCommentId = 5311318782",
        "run-id: 31990121181",
        "main-sha: cd67be14f6a4f09484d18a57de360b8a5d4c51d7",
        "EXECUTION_COMPLETED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_EVIDENCE_PRESERVED_V2",
    ):
        assert marker in text


def test_execution_workflow_permissions_are_minimal_for_durable_receipts() -> None:
    assert _workflow()["jobs"]["execute"]["permissions"] == {
        "actions": "read",
        "contents": "read",
        "issues": "write",
        "pull-requests": "read",
    }


def test_execution_workflow_pins_reviewed_validator_and_transitive_dependencies() -> None:
    text = _text()
    pins = {
        "domain/fotmob_utc_native_expected_goals_model_validation.py": "0421506b9e6e398c3469bb69196ef8fcad04f2a5",
        "domain/fotmob_utc_native_expected_goals_model_validation_source_bound.py": "89cbe2e948c4f69339c89df00db0282e14b955e8",
        "scripts/validate_fotmob_utc_native_expected_goals_model.py": "d3dddecbd66b79887aef547abcd048f40a57e2a8",
        "domain/fotmob_utc_native_expected_goals_model_validation_protocol.py": "1780330c4d0ab9140f0b2f6c776dfe79073ca7f8",
        "domain/historical_expected_goals_successor_robustness_evaluator.py": "28e33a625c02c7f005232d6c5d05d6a0a52397b7",
        "domain/historical_expected_goals_component_validation.py": "cc75af78cb6af4e3b7ebed5c3569384f2f809bf5",
    }
    for path, sha in pins.items():
        assert f"HEAD:{path}" in text
        assert sha in text


def test_execution_workflow_uses_no_mutable_external_python_package_install() -> None:
    text = _text()
    assert "pip install" not in text
    assert "pip install --upgrade" not in text
    assert "cache: pip" not in text
    assert "cache-dependency-path" not in text
    assert "requirements.txt" not in text
    assert "external_python_package_install_performed': False" in text


def test_execution_workflow_pins_exact_v2_artifact_and_offline_cli() -> None:
    text = _text()
    for marker in (
        "artifactId = 9275052993",
        "fotmob-utc-native-feature-qualification-v2-31990121181",
        "23349191",
        "sha256:f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
        "headSha: 'cd67be14f6a4f09484d18a57de360b8a5d4c51d7'",
        "EXPECTED_SHA256: f69ffad8f47faadb3ec743c96efa35fb6f4b43776a7650cf0414fb40455d29eb",
        "python -m scripts.validate_fotmob_utc_native_expected_goals_model",
        "--predictions-output fotmob-utc-native-xg-validation-predictions.ndjson",
        "--receipt-output fotmob-utc-native-xg-validation-receipt.json",
        "network_performed_by_model_validator': False",
    ):
        assert marker in text


def test_execution_workflow_verifies_exact_population_and_result_contract() -> None:
    text = _text()
    for marker in (
        "complete_case_count') != 21129",
        "dropped_incomplete_count') != 197",
        "4c017b9e43ab9e2f231e88187339a3960c5fdfbd087f21ba92ca8855576219a9",
        "4361cd60976170bd14442502025160d9b3aa97717fb94afc1b68eee9b88c429f",
        "4910b5db577bd87fd4bed4e24f3b1e00dff85d58f23e7ea8558cfba0aa5efd59",
        "f4d713a739feeac90c166f5125dd80ab7e3063598f9ad0187f07d10b88e5bcdc",
        "HISTORICAL_FIXED_COEFFICIENT_TRANSFER",
        "allowed_states = {evaluator.STRONG_STATE, evaluator.WEAK_STATE}",
        "receipt.get('next_required_boundary') != evaluator.NEXT_REQUIRED_BOUNDARY",
        "automatic_model_approval') is not False",
        "research_training_executed') is not True",
        "BLOCKED_PROJECTION_DOES_NOT_CARRY_COMPETITION_IDENTITY",
        "known_pr77_machine_precision_canonicalization_gap_cleared",
        "cross_runtime_bit_identity_claimed",
        "one or more downstream authority flags changed",
    ):
        assert marker in text


def test_execution_workflow_verifies_predictions_and_nine_quarter_jackknife() -> None:
    text = _text()
    for quarter, count in (
        ("2024-Q3", 626),
        ("2024-Q4", 1017),
        ("2025-Q1", 1073),
        ("2025-Q2", 755),
        ("2025-Q3", 599),
        ("2025-Q4", 1020),
        ("2026-Q1", 1097),
        ("2026-Q2", 721),
        ("2026-Q3", 40),
    ):
        assert f"('{quarter}', {count})" in text
    assert "prediction NDJSON does not contain exactly 6,948 rows" in text
    assert "'EVALUATION_A': 3471" in text
    assert "'EVALUATION_B_TERMINAL': 3477" in text
    assert "set(row.get('predictions', {})) != set(evaluator.MODEL_IDS)" in text


def test_execution_workflow_preserves_evidence_even_on_failure() -> None:
    steps = _workflow()["jobs"]["execute"]["steps"]
    names = [step["name"] for step in steps]
    execute_index = names.index("Execute exact offline source-bound expected-goals validation")
    package_index = names.index("Package immutable expected-goals validation evidence")
    upload_index = names.index("Upload expected-goals validation evidence even on failure")
    verify_index = names.index("Verify exact expected-goals validation result")
    assert execute_index < package_index < upload_index < verify_index
    assert steps[package_index]["if"] == "always()"
    assert steps[upload_index]["if"] == "always()"
    assert steps[verify_index]["if"] == "always()"
    text = _text()
    assert "EXECUTION_NOT_QUALIFIED_REVIEW_MODEL_VALIDATION_ARTIFACT_BEFORE_ANY_RETRY" in text
    assert "fotmob-utc-native-expected-goals-validation-${{ github.run_id }}" in text
    assert "retention-days: 30" in text
    assert "No ScoreMatrix, probability, pricing, selection, production, or BET authority" in text


def test_execution_workflow_external_actions_are_immutable_commit_pins() -> None:
    text = _text()
    pins = {
        "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/github-script": "f28e40c7f34bde8b3046d885e986cb6290c5673b",
        "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    }
    for action, sha in pins.items():
        assert f"{action}@{sha}" in text
        assert f"{action}@v" not in text


def test_execution_documentation_keeps_merge_execution_and_authority_separate() -> None:
    docs = DOC_PATH.read_text(encoding="utf-8")
    assert "PR #145 review and merge do not execute the study" in docs
    assert "Once the attempt marker exists, the attempt is spent" in docs
    assert "No PyPI or other external Python package installation is performed" in docs
    assert "REVIEW_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_RESULT" in docs
    assert "No ScoreMatrix, probability, pricing, selection, production, or BET authority" in docs
