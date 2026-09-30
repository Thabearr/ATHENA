from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path
import re
import subprocess
import pytest

from typer.testing import CliRunner

import build_acca as cli
from domain.run_contracts import AuthorityManifest, RunReceipt, RunRequest, canonical_json_bytes
from scripts import audit_p4_1_cli_consolidation as audit
from services.athena_run_request_parser import (
    AthenaRunRequestParseError,
    parse_explicit_request,
    parse_shorthand_request,
)
from services.athena_run_service import AthenaRunService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXED_NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
FIXED_OBSERVED_AT = datetime(2026, 9, 22, 12, 30, 0, 123456, tzinfo=timezone.utc)
FIXED_COMMIT = "a" * 40


def _request_for_explicit() -> RunRequest:
    return parse_explicit_request(
        days="tomorrow,thursday",
        target_legs=25,
        bookie="sportybet",
        profile="shadow",
        create_share_code=True,
        now=FIXED_NOW,
    )


def _receipt(request: RunRequest) -> RunReceipt:
    manifest = AthenaRunService.authority_manifest_for(request)
    return RunReceipt(
        status="NO_BET",
        observed_at=FIXED_OBSERVED_AT,
        exact_commit_sha=FIXED_COMMIT,
        request=request,
        stages=(),
        counts={"selected_leg_count": 0},
        selected_legs=(),
        shortfall=request.target_legs,
        share_code_result=None,
        authority_manifest=manifest,
        evidence={"synthetic_test_receipt": True},
        wager_placed=False,
    )


class _FakeService:
    def __init__(self, events: list[tuple[str, object]] | None = None) -> None:
        self.events = events if events is not None else []
        self.calls: list[tuple[RunRequest, Path]] = []
        self.receipts: list[RunReceipt] = []

    @staticmethod
    def authority_manifest_for(request: RunRequest) -> AuthorityManifest:
        return AthenaRunService.authority_manifest_for(request)

    def run(self, request: RunRequest, *, output_root: Path) -> RunReceipt:
        self.events.append(("run", request))
        self.calls.append((request, output_root))
        receipt = _receipt(request)
        self.receipts.append(receipt)
        return receipt


def _install_console_spy(monkeypatch, events: list[tuple[str, object]]) -> None:
    def record_print(*args, **kwargs):
        events.append(("print", (args, kwargs)))

    monkeypatch.setattr(cli.console, "print", record_print)


def test_explicit_run_command_resolves_request_and_prints_summary_before_service(
    monkeypatch, tmp_path
):
    events: list[tuple[str, object]] = []
    _install_console_spy(monkeypatch, events)
    service = _FakeService(events)
    monkeypatch.setattr(cli, "AthenaRunService", lambda: service)
    monkeypatch.setattr(
        cli,
        "parse_explicit_request",
        lambda **kwargs: parse_explicit_request(**kwargs, now=FIXED_NOW),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            "--days",
            "tomorrow,thursday",
            "--target-legs",
            "25",
            "--bookie",
            "sportybet",
            "--profile",
            "shadow",
            "--output-dir",
            str(tmp_path),
        ],
    )

    expected = _request_for_explicit()
    assert result.exit_code == 0, (result.exception, result.output)
    assert len(service.calls) == 1
    assert service.calls[0] == (expected, tmp_path)
    assert type(service.receipts[0]) is RunReceipt

    run_index = next(index for index, (kind, _) in enumerate(events) if kind == "run")
    summary_lines = [
        "Resolved ATHENA request (before execution):",
        "  timezone: Africa/Lagos",
        "  dates: 2026-09-23, 2026-09-24",
        "  target_legs: 25",
        "  target_total_odds: None",
        "  bookie: sportybet",
        "  mode: research_shadow",
        "  authority_profile: SHADOW",
        "  create_share_code: True",
        "  place_wager: False",
        "  provider_acquisition: True",
        "  share_code_generation: True",
        "  login: False",
        "  cookies: False",
        "  wallet: False",
        "  staking: False",
        "  wager: False",
    ]
    prior_prints = [
        args[0][0]
        for kind, args in events[:run_index]
        if kind == "print"
    ]
    assert prior_prints == summary_lines
    assert all(kind == "print" for kind, _ in events[run_index + 1 :])


def test_explicit_main_cli_preserves_legacy_no_delivery_compatibility(monkeypatch, tmp_path):
    service = _FakeService()
    monkeypatch.setattr(cli, "AthenaRunService", lambda: service)
    monkeypatch.setattr(
        cli,
        "parse_explicit_request",
        lambda **kwargs: parse_explicit_request(**kwargs, now=FIXED_NOW),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "run", "--days", "tomorrow", "--target-legs", "1", "--bookie", "sportybet",
            "--profile", "main", "--output-dir", str(tmp_path),
        ],
    )

    assert result.exit_code == 0, (result.exception, result.output)
    assert len(service.calls) == 1
    assert service.calls[0][0].authority_profile == "MAIN"
    assert service.calls[0][0].create_share_code is False


def test_shorthand_calls_the_same_request_execution_and_service_path(monkeypatch):
    events: list[tuple[str, object]] = []
    _install_console_spy(monkeypatch, events)
    service = _FakeService(events)
    monkeypatch.setattr(cli, "AthenaRunService", lambda: service)
    monkeypatch.setattr(
        cli,
        "parse_shorthand_request",
        lambda **kwargs: parse_shorthand_request(**kwargs, now=FIXED_NOW),
    )

    cli.main(["tomorrow-thursday", "25acca", "sportybet"])

    expected = parse_shorthand_request(
        date_scope="tomorrow-thursday",
        acca_token="25acca",
        bookie="sportybet",
        now=FIXED_NOW,
    )
    assert len(service.calls) == 1
    assert service.calls[0][0] == expected
    assert expected.dates == (date(2026, 9, 23), date(2026, 9, 24))
    assert expected.target_legs == 25
    assert expected.target_total_odds is None
    assert expected.authority_profile == "SHADOW"
    assert expected.mode == "research_shadow"
    assert [kind for kind, _ in events].count("run") == 1
    assert events[0][0] == "print"
    assert events[0][1][0][0] == "Resolved ATHENA request (before execution):"


def test_setup_console_entrypoint_uses_thin_main():
    setup_source = (REPOSITORY_ROOT / "setup.py").read_text(encoding="utf-8")
    assert re.search(r"athena\s*=\s*build_acca:main", setup_source)


def _build_acca_tree() -> ast.Module:
    source = (REPOSITORY_ROOT / "build_acca.py").read_text(encoding="utf-8")
    return ast.parse(source)


def test_build_acca_has_no_forbidden_direct_imports_or_legacy_builder():
    tree = _build_acca_tree()
    forbidden_prefixes = (
        "database.database",
        "workers.fotmob_advanced_scraper",
        "workers.openfootball_loader",
        "providers",
        "services.statistics_service",
        "services.team_form_service",
        "services.analysis_pipeline",
        "services.kelly_calculator",
        "intelligence",
        "engine.risk_engine",
        "engine.market_selector",
        "services.legacy_acca_builder_compat",
    )
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not [
        name
        for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    ]
    assert not any(
        isinstance(node, ast.ClassDef) and node.name == "AccaBuilder"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "AccaBuilder"
        for node in ast.walk(tree)
    )


def test_build_acca_constructs_no_legacy_business_or_provider_objects():
    forbidden_constructor_names = {
        "Database",
        "FotMobAdvancedScraper",
        "OpenFootballLoader",
        "StatisticsService",
        "TeamFormService",
        "FormEngine",
        "MotivationEngine",
        "WeatherEngine",
        "FatigueEngine",
        "InjuryEngine",
        "RefereeEngine",
        "RiskEngine",
        "MatchAnalyst",
        "AnalysisPipeline",
        "AccumulatorEngine",
        "AccaFilter",
        "KellyCalculator",
        "Backtester",
        "MarketSelector",
    }
    calls = [
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(_build_acca_tree())
        if isinstance(node, ast.Call)
        and (isinstance(node.func, ast.Name) or isinstance(node.func, ast.Attribute))
    ]
    assert not (forbidden_constructor_names & set(calls))


def test_receipt_renderer_emits_exact_canonical_receipt_only(monkeypatch):
    request = _request_for_explicit()
    receipt = _receipt(request)
    emitted = []
    monkeypatch.setattr(cli.console, "print", lambda *args, **kwargs: emitted.append((args, kwargs)))

    cli.render_receipt(receipt)

    assert emitted == [
        ((canonical_json_bytes(receipt).decode("utf-8"),), {"markup": False})
    ]
    rendered_payload = emitted[0][0][0]
    assert rendered_payload == canonical_json_bytes(receipt).decode("utf-8")
    assert "selected_leg_count" in rendered_payload
    assert "wager_placed" in rendered_payload


def test_cli_has_no_staking_language_or_sensitive_authority_options():
    source = (REPOSITORY_ROOT / "build_acca.py").read_text(encoding="utf-8")
    forbidden_ui_phrases = (
        "READY FOR BETTING",
        "Kelly Stake Size",
        "bankroll",
        "betting slip",
        "stake recommendation",
        "diversification",
        "KellyCalculator",
    )
    lowered = source.casefold()
    assert not [phrase for phrase in forbidden_ui_phrases if phrase.casefold() in lowered]
    forbidden_option = re.compile(
        r"--(?:wager|place-wager|stake|login|wallet|cookie|cookies|provider-id|"
        r"preselected-leg|probability|kelly|bet)(?:[=\s\"']|$)",
        re.IGNORECASE,
    )
    assert forbidden_option.search(source) is None


def _reachable_local_modules(root_module: str) -> set[str]:
    """Follow repository-local Python imports from the supported CLI root."""
    modules: set[str] = set()
    pending = [root_module]
    while pending:
        module = pending.pop()
        if module in modules:
            continue
        modules.add(module)
        relative = Path(*module.split("."))
        module_file = REPOSITORY_ROOT / relative.with_suffix(".py")
        package_file = REPOSITORY_ROOT / relative / "__init__.py"
        source_file = module_file if module_file.is_file() else package_file
        if not source_file.is_file():
            continue
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported_names: list[str] = []
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)
                imported_names.extend(f"{node.module}.{alias.name}" for alias in node.names)
            for imported in imported_names:
                candidate = Path(*imported.split("."))
                if (REPOSITORY_ROOT / candidate.with_suffix(".py")).is_file() or (
                    REPOSITORY_ROOT / candidate / "__init__.py"
                ).is_file():
                    pending.append(imported)
    return modules


def test_canonical_cli_import_closure_cannot_reach_legacy_builder_compat():
    reachable = _reachable_local_modules("build_acca")
    assert "services.legacy_acca_builder_compat" not in reachable
    proof = audit._fresh_cli_import_proof()
    assert proof == {
        "thin_main_callable": True,
        "legacy_builder_compat_imported": False,
        "network_attempt_count": 0,
    }


def test_only_run_command_is_exposed_and_legacy_backtest_is_unavailable():
    registered_names = {command.name for command in cli.app.registered_commands}
    assert registered_names == {"run"}
    result = CliRunner().invoke(cli.app, ["backtest"])
    assert result.exit_code != 0
    assert "backtest" not in registered_names
    assert "generate" not in registered_names
    assert "quick" not in registered_names


def test_cli_has_no_new_delivery_option_and_compatibility_default_is_localized():
    help_result = CliRunner().invoke(cli.app, ["run", "--help"])
    assert help_result.exit_code == 0
    assert "--create-share-code" not in help_result.output
    assert "--delivery" not in help_result.output
    assert cli._legacy_cli_create_share_code_default("main") is False
    assert cli._legacy_cli_create_share_code_default("shadow") is True
    with pytest.raises(AthenaRunRequestParseError, match="profile must be exactly"):
        cli._legacy_cli_create_share_code_default("SHADOW")


def test_invalid_explicit_cli_profile_fails_before_service_or_side_effect(monkeypatch, tmp_path):
    service = _FakeService()
    monkeypatch.setattr(cli, "AthenaRunService", lambda: service)
    monkeypatch.setattr(
        cli,
        "parse_explicit_request",
        lambda **kwargs: parse_explicit_request(**kwargs, now=FIXED_NOW),
    )
    result = CliRunner().invoke(
        cli.app,
        [
            "run", "--days", "tomorrow", "--target-legs", "1", "--bookie", "sportybet",
            "--profile", "SHADOW", "--output-dir", str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert not service.calls


def test_hosted_offline_service_proof_and_committed_receipt_integrity():
    proof = audit.run_offline_proof()

    assert proof["explicit_command"] == (
        "athena run --days tomorrow,thursday --target-legs 25 "
        "--bookie sportybet --profile shadow"
    )
    assert proof["explicit_request"]["dates"] == ["2026-09-22", "2026-09-24"]
    assert proof["shorthand_command"] == "athena tomorrow-thursday 25acca sportybet"
    assert proof["shorthand_target_legs"] == 25
    assert proof["shorthand_target_total_odds"] is None
    assert proof["idempotent_replay"] is True
    assert proof["synthetic_executor_call_count"] == 2
    assert proof["request_persisted_before_executor"] is True
    assert proof["receipt_persisted_canonically"] is True
    assert proof["network_attempt_count"] == 0
    assert proof["real_shadow_supervisor_invoked"] is False
    assert proof["real_current_shadow_triggered"] is False
    assert proof["real_provider_acquisition"] is False
    assert proof["wager_placed"] is False
    assert proof["main_disposition"] == "MAIN_PHASE6_AUTHORITY_REQUIRED"
    assert proof["target_total_odds_status"] == "TARGET_TOTAL_ODDS_NOT_SUPPORTED"
    assert proof["target_total_odds_executor_call_count"] == 0
    assert proof["wat_utc_unrepresentable_status"] == "SHADOW_DATE_POLICY_UNREPRESENTABLE"
    assert proof["wat_utc_requested_date_preserved"] == "2026-09-28"
    timeout_proof = proof["shadow_timeout_budget_proof"]
    assert timeout_proof["reviewed_inner_supervisor_seconds"] == 75 * 60
    assert timeout_proof["outer_timeout_argument_present"] is False
    assert timeout_proof["outer_equal_timeout_present"] is False
    assert timeout_proof["inner_timeout_receipt_finalization_preserved"] is True
    assert timeout_proof["partial_progress_preserved"] is True
    assert timeout_proof["counts"]["reviewed_fixture_count"] == 3
    assert timeout_proof["counts"]["reconciled_fixture_count"] == 2
    assert timeout_proof["counts"]["provider_event_count"] == 2
    assert timeout_proof["counts"]["priced_fixture_count"] == 0
    assert timeout_proof["selected_leg_count"] == 0
    assert timeout_proof["shortfall"] == 2
    assert timeout_proof["share_code_result_present"] is False
    assert timeout_proof["wager_placed"] is False
    assert timeout_proof["network_attempt_count"] == 0

    receipt = audit.verify_committed_receipt()
    unsigned = dict(receipt)
    stored_sha256 = unsigned.pop("canonical_sha256")
    assert audit.canonical_sha256(unsigned) == stored_sha256
    assert receipt["p4_1_cli_exit_gate_satisfied"] is True
    assert receipt["workflow_adoption_completed"] is False
    assert receipt["workflow_consolidation_claimed"] is False
    assert receipt["shadow_timeout_budget_proof"] == timeout_proof
    assert receipt["offline_synthetic_request_receipt_proof"] == proof


def test_p41_historical_receipt_is_exact_and_current_check_classifies_source_movement():
    committed = audit.verify_committed_receipt()
    assert committed["canonical_sha256"] == audit.HISTORICAL_RECEIPT_CANONICAL_SHA256
    assert {
        field: committed[field]
        for field in audit.HISTORICAL_SOURCE_IDENTITY_FIELDS
    } == audit.HISTORICAL_SOURCE_IDENTITY_VALUES

    result = audit.check_current_compatibility()
    assert result["result"] == "SKIP_SOURCE_MOVED"
    assert result["policy_id"] == "ATHENA_P4_1_CLI_CONSOLIDATION_V1"
    assert result["historical_integrity"] == "PASS"
    assert result["current_behavioral_compatibility"] == "PASS"
    assert result["historical_receipt_canonical_sha256"] == (
        "268933433aaab84cb2533840f2e01eba96ec5906e796c9eced2032e1d6706208"
    )
    assert set(result["moved_source_fields"]) == {
        "build_acca_source_sha256",
        "parser_source_sha256",
        "service_source_sha256",
    }
    assert set(result["current_source_identities"]) == set(audit.CURRENT_SOURCE_PATHS)


def test_p41_current_comparison_fails_on_non_source_receipt_drift():
    committed = audit.verify_committed_receipt()
    identities = audit._current_source_identities()
    current = audit.build_receipt()
    current["provider_acquisition"] = True

    with pytest.raises(
        audit.P4_1AuditError,
        match="non-source P4.1 receipt fields drifted: provider_acquisition",
    ):
        audit._compare_historical_and_current_receipts(committed, current, identities)


def test_p41_committed_receipt_with_a_new_valid_self_hash_still_fails_historical_pin(tmp_path: Path):
    tampered = dict(audit.verify_committed_receipt())
    tampered["p4_1_cli_exit_gate_satisfied"] = False
    unsigned = dict(tampered)
    unsigned.pop("canonical_sha256")
    tampered["canonical_sha256"] = audit.canonical_sha256(unsigned)
    candidate = tmp_path / "p4_1_tampered.json"
    candidate.write_bytes(canonical_json_bytes(tampered))

    with pytest.raises(
        audit.P4_1AuditError,
        match="historical receipt canonical identity changed",
    ):
        audit.verify_committed_receipt(candidate)


def test_p41_current_source_identity_rejects_uncommitted_semantic_mutation(tmp_path: Path):
    repository_root = tmp_path / "source identity repo"
    repository_root.mkdir()
    for relative_path in audit.CURRENT_SOURCE_PATHS.values():
        source_path = repository_root.joinpath(*relative_path.split("/"))
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"# reviewed source identity fixture\n")

    subprocess.run(["git", "init", "-q", str(repository_root)], check=True)
    subprocess.run(
        ["git", "-C", str(repository_root), "config", "user.name", "P4.1 test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository_root), "config", "user.email", "p41-test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository_root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repository_root), "commit", "-q", "-m", "source identity fixture"],
        check=True,
    )

    clean = audit._current_source_identities(repository_root)
    assert set(clean) == set(audit.CURRENT_SOURCE_PATHS)
    assert all(
        identity["git_blob_sha1"] == identity["filtered_worktree_git_blob_sha1"]
        for identity in clean.values()
    )

    changed_source = repository_root / "build_acca.py"
    changed_source.write_bytes(b"# uncommitted semantic source mutation\n")
    with pytest.raises(
        audit.P4_1AuditError,
        match="current tracked source identity failed for build_acca.py",
    ):
        audit._current_source_identities(repository_root)
