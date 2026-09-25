from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re

import pytest

from domain import current_shadow_fixture_date_request as legacy_dates
from domain.current_shadow_run_contract_adapter import adapt_current_shadow_request
from services.athena_run_request_parser import parse_explicit_request
from services.athena_run_workflow_request import resolve_workflow_request
from domain.ingest_contracts import canonical_json_bytes
from scripts import audit_p4_4h_current_shadow_canonical_run_migration_review as audit
from scripts import audit_p4_workflow_evolution_ledger as evolution


def test_review_receipt_is_source_bound_and_live_audit_passes() -> None:
    value = audit.audit(check_live=True)
    assert value["repository_base_main_sha"] == audit.BASE_MAIN
    assert value["p4_4g_receipt_sha256"] == audit.P44G_RECEIPT_SHA256
    assert value["p4_workflow_evolution_ledger_sha256"] == audit.EVOLUTION_SHA256
    assert value["p4_3_retirement_ledger_sha256"] == audit.RETIREMENT_SHA256
    assert value["workflow_tree_sha1"] == audit.WORKFLOW_TREE
    assert value["workflow_count"] == 38
    assert value["review_execution"]["provider_request_count_during_pr"] == 0
    assert value["review_execution"]["workflow_dispatch_during_pr"] is False


def test_valid_explicit_shadow_request_pairs_are_exact() -> None:
    parity = audit._request_parity()
    valid = parity["valid_request_pairs"]
    assert {row["case"] for row in valid} == {
        "workflow_dispatch_target_1",
        "workflow_dispatch_target_50",
        "workflow_dispatch_today_normal_0900z",
        "workflow_dispatch_today_2259z",
        "workflow_dispatch_three_day_scope_expanded_to_explicit_dates",
        "workflow_dispatch_explicit_seven_day_horizon",
    }
    assert all(row["parity"] is True for row in valid)
    assert all(row["canonical_intent"]["authority_profile"] == "SHADOW" for row in valid)
    assert all(row["canonical_intent"]["mode"] == "research_shadow" for row in valid)
    assert all(row["canonical_intent"]["place_wager"] is False for row in valid)
    assert all(row["canonical_intent"]["create_share_code"] is True for row in valid)


def test_scheduled_shadow_is_not_owned_by_current_canonical_schedule() -> None:
    schedule = resolve_workflow_request(
        event_name="schedule", now=datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
    )
    assert schedule.authority_profile == "MAIN"
    assert schedule.mode == "main_application"
    assert audit._request_parity()["schedule_mapping"]["classification"] == (
        "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE"
    )


def test_utc_lagos_boundary_is_recorded_without_date_shift() -> None:
    boundary = datetime(2026, 9, 24, 23, tzinfo=timezone.utc)
    canonical_today = parse_explicit_request(
        days="today", target_legs=20, bookie="sportybet", profile="shadow", now=boundary
    )
    assert canonical_today.dates == (date(2026, 9, 25),)
    legacy_today = legacy_dates.validate_fixture_dates(
        ("20260924",), current_utc=boundary
    )
    assert legacy_today == ("20260924",)
    with pytest.raises(ValueError):
        parse_explicit_request(
            days="2026-09-24", target_legs=20, bookie="sportybet", profile="shadow", now=boundary
        )
    result = audit._request_parity()
    assert result["boundary_explicit_date"]["date_shift_performed"] is False
    assert result["boundary_explicit_date"]["classification"] == (
        "UNREPRESENTABLE_WITH_CURRENT_CANONICAL_WORKFLOW_REQUEST_SURFACE"
    )


def test_legacy_unsorted_dates_are_normalized_by_existing_policy_not_rejected() -> None:
    # Current source and its existing tests deliberately sort unique dates.
    assert legacy_dates.parse_fixture_dates_text("20260926,20260924") == (
        "20260924",
        "20260926",
    )
    assert audit._request_parity()["legacy_explicit_input_normalization"][
        "unsorted_unique_dates"
    ] == "ACCEPTED_AND_SORTED_BY_EXISTING_LEGACY_POLICY"
    assert audit._request_parity()["legacy_explicit_input_normalization"][
        "unsorted_unique_dates_classification"
    ] == "REPRESENTABLE_ONLY_WITH_EXPLICIT_DATE_PRESERVATION"


def test_invalid_legacy_request_matrix_is_frozen_as_policy_rejection() -> None:
    cases = audit._request_parity()["invalid_request_cases"]
    assert {row["case"] for row in cases} == {
        "target_below_minimum_0",
        "target_above_maximum_51",
        "duplicate_explicit_date",
        "malformed_explicit_date",
        "more_than_seven_explicit_dates",
        "date_before_utc_today_or_after_utc_plus_6",
    }
    assert all(row["classification"] == "INVALID_BY_EXISTING_LEGACY_POLICY" for row in cases)


@pytest.mark.parametrize(
    "raw",
    [
        "20260924,20260924",
        "20260924,not-a-date",
        "20260924,20260925,20260926,20260927,20260928,20260929,20260930,20261001",
    ],
)
def test_legacy_invalid_date_forms_fail_closed(raw: str) -> None:
    with pytest.raises(legacy_dates.CurrentShadowFixtureDateRequestError):
        parsed = legacy_dates.parse_fixture_dates_text(raw)
        legacy_dates.validate_fixture_dates(parsed, current_utc=datetime(2026, 9, 24, 9, tzinfo=timezone.utc))


def test_legacy_out_of_horizon_dates_fail_closed() -> None:
    with pytest.raises(legacy_dates.CurrentShadowFixtureDateRequestError):
        legacy_dates.validate_fixture_dates(
            ("20260923",), current_utc=datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
        )


def test_explicit_seven_day_horizon_and_target_bounds() -> None:
    now = datetime(2026, 9, 24, 22, 59, tzinfo=timezone.utc)
    seven = tuple(date(2026, 9, 24) + timedelta(days=i) for i in range(7))
    legacy = legacy_dates.validate_fixture_dates(
        tuple(d.strftime("%Y%m%d") for d in seven), current_utc=now
    )
    canonical = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={
            "days": ",".join(d.isoformat() for d in seven),
            "target_legs": "20",
            "target_total_odds": "",
            "bookie": "sportybet",
            "profile": "shadow",
        },
        now=now,
    )
    assert tuple(d.strftime("%Y%m%d") for d in canonical.dates) == legacy
    for target in (0, 51):
        with pytest.raises(ValueError):
            resolve_workflow_request(
                event_name="workflow_dispatch",
                dispatch_inputs={
                    "days": "today",
                    "target_legs": str(target),
                    "target_total_odds": "",
                    "bookie": "sportybet",
                    "profile": "shadow",
                },
                now=now,
            )
        with pytest.raises(ValueError):
            adapt_current_shadow_request(
                target_size=target,
                request_policy=audit._request_policy("today", ["20260924"]),
            )


def test_seven_day_horizon_diverges_at_utc_lagos_midnight() -> None:
    boundary = datetime(2026, 9, 24, 23, tzinfo=timezone.utc)
    utc_legacy_window = tuple(
        (date(2026, 9, 24) + timedelta(days=i)).strftime("%Y%m%d")
        for i in range(7)
    )
    assert utc_legacy_window[-1] == "20260930"
    assert legacy_dates.validate_fixture_dates(
        utc_legacy_window, current_utc=boundary
    ) == utc_legacy_window
    with pytest.raises(ValueError):
        parse_explicit_request(
            days=",".join(f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in utc_legacy_window),
            target_legs=20,
            bookie="sportybet",
            profile="shadow",
            now=boundary,
        )
    canonical_lagos_window = tuple((date(2026, 9, 25) + timedelta(days=i)).strftime("%Y%m%d") for i in range(7))
    with pytest.raises(legacy_dates.CurrentShadowFixtureDateRequestError):
        legacy_dates.validate_fixture_dates(canonical_lagos_window, current_utc=boundary)


def test_comment_grammar_is_exact_and_not_broadened() -> None:
    workflow = Path(audit.CURRENT_SHADOW).read_text(encoding="utf-8")
    scope = re.compile(r"/athena-shadow target=([0-9]+) scope=(today|three-day)")
    dates = re.compile(r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})")
    assert scope.fullmatch("/athena-shadow target=20 scope=today")
    assert scope.fullmatch("/athena-shadow target=50 scope=three-day")
    assert dates.fullmatch("/athena-shadow target=1 dates=20260924")
    assert dates.fullmatch("/athena-shadow target=50 dates=20260924,20260925,20260926,20260927,20260928,20260929,20260930")
    zero_target = scope.fullmatch("/athena-shadow target=0 scope=today")
    assert zero_target and not 1 <= int(zero_target.group(1)) <= 50
    assert not scope.fullmatch("/athena-shadow target=20 scope=tomorrow")
    assert not dates.fullmatch("/athena-shadow target=20 dates=2026-09-24")
    assert "r\"/athena-shadow target=([0-9]+) scope=(today|three-day)\"" in workflow
    assert "r\"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})\"" in workflow


@pytest.mark.parametrize(
    ("command", "expected_scope", "date_text"),
    [
        ("/athena-shadow target=20 scope=today", "today", "20260924"),
        ("/athena-shadow target=20 scope=three-day", "three-day", "20260924,20260925,20260926"),
        ("/athena-shadow target=20 dates=20260924,20260925", "today", "20260924,20260925"),
    ],
)
def test_issue_comment_forms_map_offline_without_changing_calendar_dates(
    command: str, expected_scope: str, date_text: str
) -> None:
    scope_match = re.fullmatch(
        r"/athena-shadow target=([0-9]+) scope=(today|three-day)", command
    )
    dates_match = re.fullmatch(
        r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})",
        command,
    )
    if scope_match:
        target = int(scope_match.group(1))
        scope = scope_match.group(2)
        selected = tuple(date(2026, 9, 24) + timedelta(days=i) for i in range(1 if scope == "today" else 3))
        policy = audit._request_policy(scope, None)
        legacy = adapt_current_shadow_request(
            target_size=target, request_policy=policy, resolved_dates=selected
        )
    else:
        assert dates_match
        target = int(dates_match.group(1))
        selected_text = tuple(dates_match.group(2).split(","))
        selected = legacy_dates.validate_fixture_dates(
            selected_text, current_utc=datetime(2026, 9, 24, 9, tzinfo=timezone.utc)
        )
        scope = "today"
        legacy = adapt_current_shadow_request(
            target_size=target,
            request_policy=audit._request_policy(scope, list(selected)),
        )
    canonical = resolve_workflow_request(
        event_name="workflow_dispatch",
        dispatch_inputs={
            "days": ",".join(f"{item[:4]}-{item[4:6]}-{item[6:]}" for item in date_text.split(",")),
            "target_legs": str(target),
            "target_total_odds": "",
            "bookie": "sportybet",
            "profile": "shadow",
        },
        now=datetime(2026, 9, 24, 9, tzinfo=timezone.utc),
    )
    assert scope == expected_scope
    assert legacy.canonical_sha256 == canonical.canonical_sha256


def test_canonical_service_shadow_owner_is_reviewed_supervisor_without_execution() -> None:
    from services.athena_run_service import AthenaRunService

    executor = AthenaRunService()._executors[("SHADOW", "research_shadow", "sportybet")]
    assert type(executor).__name__ == "_ShadowSupervisorExecutor"
    source = Path("services/athena_run_service.py").read_text(encoding="utf-8")
    assert "Do not add a second timeout here" in source
    assert "adapt_current_shadow_receipt" in source
    assert "wager_placed is not False" in source
    assert audit._request_parity()["request_semantics_are_not_inferred_from_shared_supervisor"] is True


def test_p4_3a_blockers_remain_open_and_authority_does_not_expand() -> None:
    receipt = audit.expected_receipt()
    assert len(receipt["blocker_review"]) == 5
    assert all(item["migration_authorized"] is False for item in receipt["blocker_review"])
    assert all(item["retirement_authorized"] is False for item in receipt["blocker_review"])
    assert receipt["migration_dispositions"]["current_shadow_workflow_retirement_authorized"] is False
    assert receipt["review_execution"]["wager_placed"] is False
    assert receipt["review_execution"]["architecture_checkpoint_e_complete"] is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repository_base_main_sha", "0" * 40),
        ("workflow_yaml_changed", True),
        ("provider_request_count_during_pr", 1),
        ("current_shadow_caller_migration_authorized", True),
        ("current_shadow_workflow_retirement_authorized", True),
        ("provider_acquisition_authority_changed", True),
        ("model_authority_changed", True),
        ("pricing_authority_changed", True),
        ("router_authority_changed", True),
        ("portfolio_authority_changed", True),
        ("selection_authority_changed", True),
        ("share_code_authority_changed", True),
        ("account_authority_changed", True),
        ("login_authority_changed", True),
        ("cookies_authority_changed", True),
        ("wallet_authority_changed", True),
        ("staking_authority_changed", True),
        ("wager_authority_changed", True),
        ("betting_authority_changed", True),
    ],
)
def test_self_rehashed_top_level_mutations_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, replacement
) -> None:
    mutated = copy.deepcopy(audit.expected_receipt())
    if field in {"workflow_yaml_changed", "provider_request_count_during_pr"}:
        mutated["review_execution"][field] = replacement
    else:
        mutated["migration_dispositions"][field] = replacement
    mutated["canonical_sha256"] = audit._canonical_sha(mutated)
    path = tmp_path / "receipt.json"
    path.write_bytes(canonical_json_bytes(mutated))
    monkeypatch.setattr(audit, "RECEIPT_PATH", path)
    with pytest.raises(audit.P44HReviewError):
        audit.audit(check_live=False)


def test_no_review_path_executes_shadow_provider_email_or_share_transport() -> None:
    # P4.4H imports only pure date/request contracts and audits files. It never
    # calls the supervisor, source clients, mail transport, or share-code APIs.
    source = Path("scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py").read_text(encoding="utf-8")
    forbidden = ("subprocess.run([sys.executable", "fetch_fotmob", "smtplib.SMTP(", "create_share_code(")
    assert all(token not in source for token in forbidden)
    assert audit.expected_receipt()["review_execution"]["provider_request_count_during_pr"] == 0


def test_persistent_history_consumers_are_frozen_without_removal() -> None:
    receipt = audit.expected_receipt()
    durable = receipt["legacy_capabilities"]["durable_evidence"]
    assert [row["path"] for row in durable["history_consumers"]] == [
        audit.CURRENT_SHADOW,
        audit.ATHENA_RUN,
        ".github/workflows/p3-0-comparison-evidence-capture.yml",
    ]
    assert all(row["artifact"] == "current-shadow-all-market-request" for row in durable["history_consumers"])
    assert durable["history_consumers"][0]["run_filter"] == "no head_branch filter; skip GITHUB_RUN_ID"
    assert durable["history_consumers"][1]["run_filter"] == "no head_branch filter; skip GITHUB_RUN_ID"
    assert durable["history_consumers"][2]["run_filter"] == "head_branch == main"
    assert durable["identity_state_filename"] == "current-shadow-fixture-identity-v2-state.json"
    assert "tests/test_current_shadow_persisted_identity_ancestry.py" in durable["dependent_tests"]


def test_receipt_artifact_matches_exact_expected_bytes() -> None:
    value = audit._read_canonical(audit.RECEIPT_PATH)
    assert value == audit.expected_receipt()
