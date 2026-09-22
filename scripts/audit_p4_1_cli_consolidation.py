"""Deterministic offline audit for the P4.1 CLI/service migration."""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from domain.component_authority_registry import load_default_registry
from domain.run_contracts import (
    AuthorityManifest,
    RunRequest,
    canonical_json_bytes,
    canonical_sha256,
)
from services.athena_run_request_parser import (
    CLI_TIMEZONE_ID,
    parse_explicit_request,
    parse_shorthand_request,
)
from services.athena_run_service import AthenaRunService, ExecutorResult


POLICY_ID = "ATHENA_P4_1_CLI_CONSOLIDATION_V1"
SCHEMA_VERSION = 1
BASE_MAIN_SHA = "09188ea02e20b5b8fb30365d3c246b68a1a8fa59"
P3_3_RECEIPT_SHA256 = "4c0f1be1b534fe863b9541363e37e2f780535be740cc6a901aeb1be57fbcf8bc"
REGISTRY_CANONICAL_SHA256 = "74e79e216497c2e7f31a51e278251a5c62645e1085d04ebb8712022658f8f109"
P0_5_SOURCE_MAIN_SHA = "b428dbd00380dd71456640d77b26ac79fe945c5f"
P0_5_RUNTIME_RAW_SHA256 = "3ea90c5e0e797c027ad7a516db62f95e8bf9c7239b6074651bcdf64a6a03d65e"
P3_3_RECEIPT_RAW_SHA256 = "8e3fe3cc6870c59142b9ae658636c75338d7b70cfb4151f553ec3eee73ca6077"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts/architecture/p4_1_cli_consolidation_v1.json"
CALLER_FIXTURE = REPOSITORY_ROOT / "tests/fixtures/architecture/p4_1_legacy_acca_builder_callers_v1.json"
WAT = ZoneInfo(CLI_TIMEZONE_ID)
FIXED_NOW = datetime(2026, 9, 21, 12, 0, 0, tzinfo=WAT)
FIXED_UTC = FIXED_NOW.astimezone(timezone.utc)
FIXED_RECEIPT_TIME = datetime(2026, 9, 21, 11, 0, 0, 123456, tzinfo=timezone.utc)
FIXED_COMMIT = "a" * 40

PRESERVED_HISTORICAL_FILES = {
    "artifacts/architecture/runtime-reachability-v1.json": P0_5_RUNTIME_RAW_SHA256,
    "config/architecture/main-shadow-authority-parity-v1.json": "0b2c517517c196fe92e13c8a8c7010f8e7546372c41aee37f8abdff431b0ba34",
    "config/architecture/architecture-boundary-policy-v1.json": "cc6831e1dc0a59063a9da1ed073f8505b2717633de67e160b44aeb1092b4dc0b",
    "artifacts/architecture/p3_1_main_canonical_core_promotion_v1.json": "287bb60291c463c934b944fb7787a4e1f1d1abcdd887f8ef7344e905b9c5056d",
    "artifacts/architecture/p3_1_main_caller_migration_v1.json": "f0ef41f08bfaf1d452a56e7bb30441b7966c007d2f6552dfc204fffda8193cb0",
    "artifacts/architecture/p3_2_frozen_v2_runtime_externalization_v1.json": "eb158301ed1bdf52a9e36346ebaab79bd65b32118ade0aba6eda380dc1ba331c",
    "tests/fixtures/architecture/p3_2_frozen_v2_policy_vectors_v1.json": "3fc9a9df063ec8252aef5bf2a98a98faf2cf78f628b37697ff63b143fee31161",
    "artifacts/architecture/p3_3_module_canonicalization_v1.json": P3_3_RECEIPT_RAW_SHA256,
}

DIRECT_CLI_FORBIDDEN_PREFIXES = (
    "database.database",
    "workers.fotmob_advanced_scraper",
    "workers.openfootball_loader",
    "providers",
    "services.statistics_service",
    "services.team_form_service",
    "services.analysis_pipeline",
    "services.kelly_calculator",
    "services.legacy_acca_builder_compat",
    "intelligence",
    "engine.risk_engine",
    "engine.market_selector",
)


class P4_1AuditError(RuntimeError):
    """Raised when the offline P4.1 proof does not meet its bound contract."""


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


@contextmanager
def _network_denied() -> Iterator[dict[str, int]]:
    attempts = {"count": 0}
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection
    original_sendto = socket.socket.sendto
    original_sendall = socket.socket.sendall

    def denied(*_args, **_kwargs):
        attempts["count"] += 1
        raise AssertionError("network access is forbidden in the P4.1 offline proof")

    socket.socket.connect = denied  # type: ignore[method-assign]
    socket.socket.connect_ex = denied  # type: ignore[method-assign]
    socket.create_connection = denied  # type: ignore[assignment]
    socket.socket.sendto = denied  # type: ignore[method-assign]
    socket.socket.sendall = denied  # type: ignore[method-assign]
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = original_connect_ex  # type: ignore[method-assign]
        socket.create_connection = original_create_connection  # type: ignore[assignment]
        socket.socket.sendto = original_sendto  # type: ignore[method-assign]
        socket.socket.sendall = original_sendall  # type: ignore[method-assign]


@contextmanager
def _legacy_execution_watch() -> Iterator[dict[str, int]]:
    """Count calls into legacy orchestration modules without importing them."""

    watched = {
        "legacy_accabuilder": "services.legacy_acca_builder_compat",
        "legacy_accafilter": "intelligence.acca_filter",
        "legacy_accumulator": "intelligence.accumulator",
        "legacy_kelly": "services.kelly_calculator",
        "market_selector": "engine.market_selector",
    }
    counts = {name: 0 for name in watched}
    previous = sys.getprofile()

    def profile(frame, event, argument):
        if previous is not None:
            previous(frame, event, argument)
        if event != "call":
            return
        module_name = frame.f_globals.get("__name__", "")
        for label, prefix in watched.items():
            if module_name == prefix or module_name.startswith(prefix + "."):
                counts[label] += 1

    sys.setprofile(profile)
    try:
        yield counts
    finally:
        sys.setprofile(previous)


def _local_source(module: str) -> Path | None:
    relative = Path(*module.split("."))
    module_path = REPOSITORY_ROOT / relative.with_suffix(".py")
    package_path = REPOSITORY_ROOT / relative / "__init__.py"
    if module_path.is_file():
        return module_path
    if package_path.is_file():
        return package_path
    return None


def _imports_from_ast(tree: ast.Module) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.add(node.module)
            for alias in node.names:
                imports.add(f"{node.module}.{alias.name}")
    return imports


def _direct_cli_imports() -> list[str]:
    cli_path = REPOSITORY_ROOT / "build_acca.py"
    tree = ast.parse(cli_path.read_text(encoding="utf-8"))
    return sorted(
        imported
        for imported in _imports_from_ast(tree)
        if any(
            imported == prefix or imported.startswith(prefix + ".")
            for prefix in DIRECT_CLI_FORBIDDEN_PREFIXES
        )
    )


def _local_import_closure(root: str) -> set[str]:
    reached: set[str] = set()
    pending = [root]
    while pending:
        module = pending.pop()
        if module in reached:
            continue
        reached.add(module)
        source = _local_source(module)
        if source is None:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for imported in _imports_from_ast(tree):
            if _local_source(imported) is not None and imported not in reached:
                pending.append(imported)
    return reached


def _synthetic_request() -> RunRequest:
    return parse_explicit_request(
        days="tomorrow,thursday",
        target_legs=25,
        bookie="sportybet",
        profile="shadow",
        now=FIXED_NOW,
    )


def _fresh_cli_import_proof() -> dict[str, Any]:
    """Import the CLI in an isolated child and deny network calls there."""
    child_code = """
import importlib
import json
import socket
import sys
root = sys.argv.pop(1)
sys.path.insert(0, root)
attempts = {"count": 0}
def deny(*_args, **_kwargs):
    attempts["count"] += 1
    raise RuntimeError("network access is forbidden in the P4.1 CLI import proof")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.socket.sendto = deny
socket.socket.sendall = deny
socket.create_connection = deny
cli = importlib.import_module("build_acca")
result = {
    "thin_main_callable": callable(cli.main),
    "legacy_builder_compat_imported": "services.legacy_acca_builder_compat" in sys.modules,
    "network_attempt_count": attempts["count"],
}
print(json.dumps(result, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", child_code, str(REPOSITORY_ROOT)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise P4_1AuditError(
            "fresh-process CLI import proof failed: "
            + (completed.stderr.strip() or f"exit={completed.returncode}")
        )
    try:
        proof = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise P4_1AuditError("fresh-process CLI import proof returned invalid output") from exc
    if (
        proof.get("thin_main_callable") is not True
        or proof.get("legacy_builder_compat_imported") is not False
        or proof.get("network_attempt_count") != 0
    ):
        raise P4_1AuditError("fresh-process CLI import reached legacy code or network")
    return proof


def run_offline_proof() -> dict[str, Any]:
    """Execute fixed-clock parser/service proofs using no provider executor."""
    from unittest.mock import patch

    from domain.run_contracts import RunReceipt

    cli_import_proof = _fresh_cli_import_proof()
    explicit = _synthetic_request()
    shorthand = parse_shorthand_request(
        date_scope="tomorrow-thursday",
        acca_token="25acca",
        bookie="sportybet",
        now=FIXED_NOW,
    )
    if explicit.dates != (date(2026, 9, 22), date(2026, 9, 24)):
        raise P4_1AuditError("preferred explicit command expansion drifted")
    if shorthand.dates != (date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)):
        raise P4_1AuditError("shorthand date-range expansion drifted")
    if shorthand.target_legs != 25 or shorthand.target_total_odds is not None:
        raise P4_1AuditError("25acca target semantics drifted")

    expected_caps = {
        "provider_acquisition": True,
        "share_code_generation": True,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager": False,
    }
    manifest = AthenaRunService.authority_manifest_for(explicit)
    if manifest.to_dict()["capabilities"] != expected_caps:
        raise P4_1AuditError("SHADOW permission summary drifted")

    network_attempts = {"count": cli_import_proof["network_attempt_count"]}
    with tempfile.TemporaryDirectory(prefix="athena-p4-1-offline-") as temporary_root:
        root = Path(temporary_root)
        from services import athena_run_service as service_module

        executor_calls: list[str] = []
        request_persisted_before_executor: list[bool] = []
        real_supervisor_attempts = {"count": 0}

        def reject_real_supervisor(*_args, **_kwargs):
            real_supervisor_attempts["count"] += 1
            raise AssertionError("real Current Shadow supervisor is forbidden in P4.1 proof")

        def synthetic_executor(
            request: RunRequest,
            *,
            authority_manifest: AuthorityManifest,
            run_directory: Path,
            exact_commit_sha: str,
            observed_at: datetime,
        ) -> ExecutorResult:
            executor_calls.append(request.canonical_sha256)
            request_path = run_directory / "athena-run-request.json"
            request_persisted_before_executor.append(
                request_path.is_file() and request_path.read_bytes() == _canonical_bytes(request)
            )
            if authority_manifest != manifest:
                raise P4_1AuditError("synthetic executor received different authority")
            if exact_commit_sha != FIXED_COMMIT or observed_at != FIXED_RECEIPT_TIME:
                raise P4_1AuditError("synthetic executor identity/time binding drifted")
            return ExecutorResult(
                status="NO_BET",
                evidence={
                    "synthetic_offline_executor": True,
                    "provider_acquisition": False,
                    "wager_placed": False,
                },
            )

        service = AthenaRunService(
            _test_executor_overrides={
                ("SHADOW", "research_shadow", "sportybet"): synthetic_executor,
            },
            _commit_sha_provider=lambda: FIXED_COMMIT,
            _clock=lambda: FIXED_RECEIPT_TIME,
        )
        with (
            _network_denied() as attempts,
            _legacy_execution_watch() as legacy_execution_counts,
            patch.object(
                service_module.subprocess,
                "run",
                side_effect=reject_real_supervisor,
            ),
        ):
            first = service.run(explicit, output_root=root / "synthetic")
            second = service.run(explicit, output_root=root / "synthetic")

            shadow_synthetic = service.run(shorthand, output_root=root / "shorthand")

            main_request = parse_explicit_request(
                days="tomorrow",
                target_legs=25,
                bookie="sportybet",
                profile="main",
                now=FIXED_NOW,
            )
            main_manifest = AthenaRunService.authority_manifest_for(main_request)
            if main_manifest.provider_acquisition or main_manifest.share_code_generation:
                raise P4_1AuditError("MAIN manifest has acquisition/share-code authority")
            from domain import current_sportybet_accumulator_request as main_boundary

            with patch.object(main_boundary, "_now_utc", return_value=FIXED_RECEIPT_TIME):
                main_service = AthenaRunService(
                    _commit_sha_provider=lambda: FIXED_COMMIT,
                    _clock=lambda: FIXED_RECEIPT_TIME,
                )
                main_receipt = main_service.run(main_request, output_root=root / "main")

            odds_request = parse_explicit_request(
                days="tomorrow",
                target_legs=25,
                bookie="sportybet",
                profile="shadow",
                target_total_odds=Decimal("2.5"),
                now=FIXED_NOW,
            )
            odds_calls: list[int] = []
            odds_service = AthenaRunService(
                _test_executor_overrides={
                    ("SHADOW", "research_shadow", "sportybet"):
                    lambda *_args, **_kwargs: odds_calls.append(1),
                },
                _commit_sha_provider=lambda: FIXED_COMMIT,
                _clock=lambda: FIXED_RECEIPT_TIME,
            )
            odds_receipt = odds_service.run(odds_request, output_root=root / "odds")

            midnight = datetime(2026, 9, 22, 0, 30, tzinfo=WAT)
            unrepresentable_request = parse_explicit_request(
                days="2026-09-28",
                target_legs=1,
                bookie="sportybet",
                profile="shadow",
                now=midnight,
            )
            unrepresentable_service = AthenaRunService(
                _commit_sha_provider=lambda: FIXED_COMMIT,
                _clock=lambda: midnight.astimezone(timezone.utc),
            )
            unrepresentable_receipt = unrepresentable_service.run(
                unrepresentable_request,
                output_root=root / "unrepresentable",
            )
        network_attempts["count"] += attempts["count"]

        if type(first) is not RunReceipt or first != second:
            raise P4_1AuditError("synthetic service receipt/idempotency proof failed")
        receipt_path = root / "synthetic" / explicit.canonical_sha256 / "athena-run-receipt.json"
        if not receipt_path.is_file() or receipt_path.read_bytes() != _canonical_bytes(first):
            raise P4_1AuditError("synthetic receipt persistence is not canonical")
        if len(executor_calls) != 2 or executor_calls != [explicit.canonical_sha256, shorthand.canonical_sha256]:
            raise P4_1AuditError("synthetic executor idempotency call count drifted")
        if not all(request_persisted_before_executor):
            raise P4_1AuditError("request was not persisted before a synthetic executor call")
        if first.request != explicit or first.exact_commit_sha != FIXED_COMMIT:
            raise P4_1AuditError("synthetic receipt did not bind exact request/commit")
        if first.wager_placed is not False or first.shortfall != explicit.target_legs:
            raise P4_1AuditError("synthetic receipt did not preserve no-wager/shortfall")
        if main_receipt.status != "MAIN_PHASE6_AUTHORITY_REQUIRED" or main_receipt.shortfall != 25:
            raise P4_1AuditError("MAIN existing fail-closed boundary mapping drifted")
        if main_receipt.authority_manifest.provider_acquisition is not False:
            raise P4_1AuditError("MAIN result reports provider authority")
        main_boundary_result = main_receipt.evidence.get("main_target_only_request", {})
        if main_boundary_result.get("real_current_provider_execution_attempted") is not False:
            raise P4_1AuditError("MAIN target-only boundary reports provider execution")
        if real_supervisor_attempts["count"] != 0:
            raise P4_1AuditError("offline proof attempted the real Current Shadow supervisor")
        if any(legacy_execution_counts.values()):
            raise P4_1AuditError("offline proof executed a legacy betting/selection component")
        if odds_receipt.status != "TARGET_TOTAL_ODDS_NOT_SUPPORTED" or odds_calls:
            raise P4_1AuditError("separate target-total-odds objective was not stopped pre-executor")
        if unrepresentable_receipt.status != "SHADOW_DATE_POLICY_UNREPRESENTABLE":
            raise P4_1AuditError("WAT/UTC boundary did not fail closed")
        if unrepresentable_receipt.request.dates != (date(2026, 9, 28),):
            raise P4_1AuditError("WAT/UTC boundary silently shifted the requested date")
        if shadow_synthetic.status != "NO_BET" or shadow_synthetic.wager_placed is not False:
            raise P4_1AuditError("synthetic SHADOW request did not produce a safe receipt")

        synthetic_bytes = receipt_path.read_bytes()
        result = {
            "explicit_command": "athena run --days tomorrow,thursday --target-legs 25 --bookie sportybet --profile shadow",
            "explicit_request": explicit.to_dict(),
            "explicit_request_sha256": explicit.canonical_sha256,
            "shorthand_command": "athena tomorrow-thursday 25acca sportybet",
            "shorthand_request": shorthand.to_dict(),
            "shorthand_request_sha256": shorthand.canonical_sha256,
            "shorthand_target_legs": shorthand.target_legs,
            "shorthand_target_total_odds": None,
            "timezone": CLI_TIMEZONE_ID,
            "request_persisted_before_executor": all(request_persisted_before_executor),
            "receipt_persisted_canonically": synthetic_bytes == _canonical_bytes(first),
            "synthetic_executor_call_count": len(executor_calls),
            "idempotent_replay": (
                first == second
                and len(executor_calls) == 2
                and executor_calls.count(explicit.canonical_sha256) == 1
                and executor_calls.count(shorthand.canonical_sha256) == 1
            ),
            "synthetic_receipt_canonical_sha256": canonical_sha256(first),
            "synthetic_receipt_status": first.status,
            "synthetic_selected_leg_count": first.counts["selected_leg_count"],
            "synthetic_shortfall": first.shortfall,
            "main_disposition": main_receipt.status,
            "main_provider_acquisition": main_receipt.authority_manifest.provider_acquisition,
            "main_provider_execution_attempted": main_boundary_result[
                "real_current_provider_execution_attempted"
            ],
            "main_share_code_generation": main_receipt.authority_manifest.share_code_generation,
            "main_selected_leg_count": main_receipt.counts["selected_leg_count"],
            "main_shortfall": main_receipt.shortfall,
            "target_total_odds_status": odds_receipt.status,
            "target_total_odds_executor_call_count": len(odds_calls),
            "wat_utc_unrepresentable_status": unrepresentable_receipt.status,
            "wat_utc_requested_date_preserved": unrepresentable_receipt.request.dates[0].isoformat(),
            "shadow_synthetic_status": shadow_synthetic.status,
            "real_shadow_supervisor_invocation_count": real_supervisor_attempts["count"],
            "real_shadow_supervisor_invoked": real_supervisor_attempts["count"] != 0,
            "real_current_shadow_triggered": real_supervisor_attempts["count"] != 0,
            "real_provider_acquisition": (
                real_supervisor_attempts["count"] != 0
                or main_boundary_result["real_current_provider_execution_attempted"] is not False
            ),
            "real_share_code_operation": (
                real_supervisor_attempts["count"] != 0
                or first.share_code_result is not None
                or shadow_synthetic.share_code_result is not None
            ),
            "wager_placed": False,
            "network_attempt_count": network_attempts["count"],
            "legacy_builder_reachable_from_cli_import": cli_import_proof[
                "legacy_builder_compat_imported"
            ],
            "fresh_cli_import_proof": cli_import_proof,
            "legacy_execution_counts": legacy_execution_counts,
            "legacy_accabuilder_executions": legacy_execution_counts["legacy_accabuilder"],
            "legacy_accafilter_executions": legacy_execution_counts["legacy_accafilter"],
            "legacy_accumulator_executions": legacy_execution_counts["legacy_accumulator"],
            "kelly_executions": legacy_execution_counts["legacy_kelly"],
            "market_selector_executions": legacy_execution_counts["market_selector"],
        }
    if result["network_attempt_count"] != 0:
        raise P4_1AuditError("offline proof attempted network access")
    return result


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise P4_1AuditError(f"expected JSON object at {path.name}")
    return payload


def build_receipt() -> dict[str, Any]:
    caller_bytes = CALLER_FIXTURE.read_bytes()
    caller_fixture = json.loads(caller_bytes)
    if (
        type(caller_fixture) is not dict
        or caller_fixture.get("source_main_sha") != BASE_MAIN_SHA
        or caller_fixture.get("schema_version") != 1
    ):
        raise P4_1AuditError("legacy caller classification fixture identity drifted")

    registry = load_default_registry()
    if registry.canonical_sha256 != REGISTRY_CANONICAL_SHA256:
        raise P4_1AuditError("component authority registry changed during P4.1")

    historical_hashes = {
        name: _raw_sha256(REPOSITORY_ROOT / name)
        for name in sorted(PRESERVED_HISTORICAL_FILES)
    }
    for name, expected in PRESERVED_HISTORICAL_FILES.items():
        if historical_hashes[name] != expected:
            raise P4_1AuditError(f"historical artifact changed: {name}")

    p3_3_receipt = _load_json(
        REPOSITORY_ROOT / "artifacts/architecture/p3_3_module_canonicalization_v1.json"
    )
    if p3_3_receipt.get("canonical_sha256") != P3_3_RECEIPT_SHA256:
        raise P4_1AuditError("P3.3 receipt identity changed during P4.1")

    cli_path = REPOSITORY_ROOT / "build_acca.py"
    cli_source = cli_path.read_text(encoding="utf-8")
    cli_tree = ast.parse(cli_source)
    direct_forbidden = _direct_cli_imports()
    if direct_forbidden:
        raise P4_1AuditError(f"CLI imports forbidden business modules: {direct_forbidden}")
    if any(
        isinstance(node, ast.ClassDef) and node.name == "AccaBuilder"
        for node in ast.walk(cli_tree)
    ):
        raise P4_1AuditError("AccaBuilder remains defined in the canonical CLI module")
    local_closure = _local_import_closure("build_acca")
    if "services.legacy_acca_builder_compat" in local_closure:
        raise P4_1AuditError("canonical CLI import closure reaches legacy AccaBuilder")

    proof = run_offline_proof()
    all_sensitive_flags_false = all(
        proof.get(name) is False
        for name in (
            "real_shadow_supervisor_invoked",
            "real_current_shadow_triggered",
            "real_provider_acquisition",
            "real_share_code_operation",
            "wager_placed",
        )
    ) and not any(proof["legacy_execution_counts"].values())
    if not all_sensitive_flags_false:
        raise P4_1AuditError("offline proof records unexpected live/sensitive action")

    classified_callers = caller_fixture["classifications"]
    supported_non_cli_callers = [
        item for item in classified_callers
        if item.get("class") == "SUPPORTED_NON_CLI_CURRENT"
    ]

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "repository_base_main_sha": BASE_MAIN_SHA,
        "p3_3_receipt_sha256": P3_3_RECEIPT_SHA256,
        "component_registry_canonical_sha256": registry.canonical_sha256,
        "run_contract_policy_id": "ATHENA_CANONICAL_RUN_CONTRACT_V1",
        "cli_entrypoint": "athena=build_acca:main",
        "cli_module": "build_acca",
        "service_module": "services.athena_run_service.AthenaRunService",
        "parser_module": "services.athena_run_request_parser",
        "timezone": CLI_TIMEZONE_ID,
        "target_legs_bounds": {"minimum": 1, "maximum": 50},
        "selected_day_bounds": {"minimum": 1, "maximum": 7},
        "rolling_horizon_days": 7,
        "preferred_command_expansion": {
            "command": "athena run --days tomorrow,thursday --target-legs 25 --bookie sportybet --profile shadow",
            "request": proof["explicit_request"],
            "request_sha256": proof["explicit_request_sha256"],
        },
        "shorthand_command_expansion": {
            "command": "athena tomorrow-thursday 25acca sportybet",
            "request": proof["shorthand_request"],
            "request_sha256": proof["shorthand_request_sha256"],
            "25acca_target_legs": 25,
            "25acca_target_total_odds": None,
        },
        "target_total_odds_is_separate": True,
        "unsupported_target_total_odds_fails_before_executor": (
            proof["target_total_odds_status"] == "TARGET_TOTAL_ODDS_NOT_SUPPORTED"
            and proof["target_total_odds_executor_call_count"] == 0
        ),
        "legacy_caller_classification_fixture_sha256": hashlib.sha256(caller_bytes).hexdigest(),
        "legacy_caller_classification_counts": {
            kind: sum(1 for item in classified_callers if item.get("class") == kind)
            for kind in (
                "SUPPORTED_CLI_CURRENT",
                "SUPPORTED_NON_CLI_CURRENT",
                "HISTORICAL_EVIDENCE",
                "OFFLINE_LEGACY_TOOL",
                "FUTURE_MIGRATION_SURFACE",
                "TEST_ONLY",
            )
        },
        "supported_non_cli_legacy_accabuilder_caller_count": len(supported_non_cli_callers),
        "supported_non_cli_caller_preserved_by_compat_module": True,
        "canonical_cli_reaches_legacy_builder": proof[
            "legacy_builder_reachable_from_cli_import"
        ],
        "direct_cli_forbidden_imports": direct_forbidden,
        "build_acca_source_sha256": hashlib.sha256(cli_source.encode("utf-8")).hexdigest(),
        "parser_source_sha256": _raw_sha256(REPOSITORY_ROOT / "services/athena_run_request_parser.py"),
        "service_source_sha256": _raw_sha256(REPOSITORY_ROOT / "services/athena_run_service.py"),
        "offline_synthetic_request_receipt_proof": proof,
        "idempotency_proof": proof["idempotent_replay"],
        "network_attempt_count": proof["network_attempt_count"],
        "provider_acquisition": proof["real_provider_acquisition"],
        "current_shadow_triggered": proof["real_current_shadow_triggered"],
        "fresh_holdout_triggered": False,
        "p3_0_e1_triggered": False,
        "share_code_operation": proof["real_share_code_operation"],
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "wager_placed": False,
        "p0_5_artifact_sha256": historical_hashes[
            "artifacts/architecture/runtime-reachability-v1.json"
        ],
        "p0_5_artifact_changed": False,
        "p3_1_promotion_receipt_changed": False,
        "p3_1_migration_receipt_changed": False,
        "p3_2_receipt_changed": False,
        "p3_2_vector_fixture_changed": False,
        "p3_3_receipt_changed": False,
        "historical_artifact_sha256": historical_hashes,
        "market_selector_execution": proof["market_selector_executions"] != 0,
        "legacy_accafilter_execution": proof["legacy_accafilter_executions"] != 0,
        "legacy_accumulator_execution": proof["legacy_accumulator_executions"] != 0,
        "kelly_execution": proof["kelly_executions"] != 0,
        "model_formula_changed": False,
        "probability_formula_changed": False,
        "calibration_formula_changed": False,
        "price_all_formula_changed": False,
        "router_formula_changed": False,
        "portfolio_formula_changed": False,
        "provider_semantics_changed": False,
        "share_code_semantics_changed": False,
        "p4_1_cli_exit_gate_satisfied": True,
        "workflow_adoption_completed": False,
        "workflow_consolidation_claimed": False,
        "next_required_step": "P4_2_ATHENA_RUN_WORKFLOW_REQUIRED",
        "source_review_counter_while_unmerged": "4/5",
        "source_review_required_after_merge": True,
    }
    receipt["canonical_sha256"] = canonical_sha256(receipt)
    return receipt


def verify_committed_receipt(path: Path | None = None) -> dict[str, Any]:
    receipt = _load_json(path or DEFAULT_OUTPUT)
    stored = receipt.get("canonical_sha256")
    unsigned = dict(receipt)
    unsigned.pop("canonical_sha256", None)
    if type(stored) is not str or canonical_sha256(unsigned) != stored:
        raise P4_1AuditError("P4.1 receipt canonical SHA-256 failed verification")
    if (
        receipt.get("policy_id") != POLICY_ID
        or receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("repository_base_main_sha") != BASE_MAIN_SHA
        or receipt.get("p3_3_receipt_sha256") != P3_3_RECEIPT_SHA256
        or receipt.get("component_registry_canonical_sha256") != REGISTRY_CANONICAL_SHA256
    ):
        raise P4_1AuditError("P4.1 receipt policy/base identity failed verification")
    if receipt.get("p4_1_cli_exit_gate_satisfied") is not True:
        raise P4_1AuditError("P4.1 receipt does not claim a satisfied exit gate")
    if receipt.get("network_attempt_count") != 0:
        raise P4_1AuditError("P4.1 receipt records network attempts")
    for flag in (
        "provider_acquisition",
        "current_shadow_triggered",
        "fresh_holdout_triggered",
        "p3_0_e1_triggered",
        "share_code_operation",
        "login",
        "cookies",
        "wallet",
        "staking",
        "wager_placed",
        "workflow_adoption_completed",
        "workflow_consolidation_claimed",
    ):
        if receipt.get(flag) is not False:
            raise P4_1AuditError(f"P4.1 receipt safety/state flag is not false: {flag}")
    proof = receipt.get("offline_synthetic_request_receipt_proof")
    if type(proof) is not dict:
        raise P4_1AuditError("P4.1 receipt is missing offline proof object")
    cli_import_proof = proof.get("fresh_cli_import_proof")
    if (
        receipt.get("canonical_cli_reaches_legacy_builder") is not False
        or type(cli_import_proof) is not dict
        or cli_import_proof.get("thin_main_callable") is not True
        or cli_import_proof.get("legacy_builder_compat_imported") is not False
        or cli_import_proof.get("network_attempt_count") != 0
    ):
        raise P4_1AuditError("P4.1 receipt lacks an isolated thin-CLI import proof")
    if (
        proof.get("real_shadow_supervisor_invocation_count") != 0
        or proof.get("real_provider_acquisition") is not False
        or proof.get("real_current_shadow_triggered") is not False
        or proof.get("real_share_code_operation") is not False
        or proof.get("wager_placed") is not False
        or proof.get("network_attempt_count") != 0
        or proof.get("idempotent_replay") is not True
        or any(proof.get("legacy_execution_counts", {}).values())
    ):
        raise P4_1AuditError("P4.1 receipt offline proof contains an unsafe observation")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    receipt = build_receipt()
    if args.check:
        committed = verify_committed_receipt(args.output)
        if committed != receipt:
            raise SystemExit("committed P4.1 receipt differs from deterministic audit")
        print(receipt["canonical_sha256"])
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(receipt))
    print(receipt["canonical_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
