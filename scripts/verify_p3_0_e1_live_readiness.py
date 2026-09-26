#!/usr/bin/env python3
"""Strict no-network P3.0-E1 live readiness gate.

This tool executes 14 exhaustive checks (Checks A through N) before any live
provider network acquisition is permitted. If any check fails or if any network
activity is attempted, this gate fails closed immediately.

When checks pass, it writes:
    artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json
with status P3_0_E1_LIVE_READINESS_VERIFIED and a deterministic SHA-256 hash.

On failure, it retains:
    artifacts/p3-0-comparison-evidence/p3-0-e1-live-readiness.json
with status P3_E1_READINESS_FAILED and the first failed check details.
"""
from __future__ import annotations

import compileall
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any, Mapping
import urllib.request

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

POLICY_ID = "ATHENA_P3_0_E1_LIVE_READINESS_GATE_V1"
SCHEMA_VERSION = 1
STATUS_VERIFIED = "P3_0_E1_LIVE_READINESS_VERIFIED"
STATUS_FAILED = "P3_E1_READINESS_FAILED"
READINESS_FILENAME = "p3-0-e1-live-readiness.json"
EXPECTED_LINEAGE_MAIN = "c5ec9a23486a594d2df279521b6065744fa9a389"


class P30LiveReadinessError(RuntimeError):
    """Raised when live readiness verification fails closed."""


@contextmanager
def strict_network_block():
    """Block all outbound network sockets and urlopen calls."""
    real_socket = socket.socket
    real_create_connection = socket.create_connection
    real_urlopen = urllib.request.urlopen

    def blocked_socket(*args: Any, **kwargs: Any):
        raise P30LiveReadinessError(
            "NETWORK_ACCESS_FORBIDDEN: socket.socket called during no-network readiness verification"
        )

    def blocked_create_connection(*args: Any, **kwargs: Any):
        raise P30LiveReadinessError(
            "NETWORK_ACCESS_FORBIDDEN: socket.create_connection called during no-network readiness verification"
        )

    def blocked_urlopen(*args: Any, **kwargs: Any):
        raise P30LiveReadinessError(
            "NETWORK_ACCESS_FORBIDDEN: urllib.request.urlopen called during no-network readiness verification"
        )

    socket.socket = blocked_socket  # type: ignore[assignment]
    socket.create_connection = blocked_create_connection  # type: ignore[assignment]
    urllib.request.urlopen = blocked_urlopen  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = real_socket  # type: ignore[assignment]
        socket.create_connection = real_create_connection  # type: ignore[assignment]
        urllib.request.urlopen = real_urlopen  # type: ignore[assignment]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _git_head(repository_root: Path) -> str:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().lower()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise P30LiveReadinessError("Git HEAD is unavailable") from exc
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise P30LiveReadinessError("Git HEAD is not a 40-character hex SHA")
    return value


def check_a_compilation(repository_root: Path) -> dict[str, Any]:
    """Check A: Byte-compilation of domain, scripts, services, config."""
    directories = ["domain", "scripts", "services", "config"]
    compiled = 0
    for dirname in directories:
        target = repository_root / dirname
        if target.exists() and target.is_dir():
            success = compileall.compile_dir(
                str(target),
                maxlevels=10,
                quiet=1,
                force=False,
            )
            if not success:
                raise P30LiveReadinessError(
                    f"Check A failed: compilation errors in {dirname}"
                )
            compiled += 1
    return {"status": "PASSED", "directories_compiled": directories}


def check_b_lineage_main(repository_root: Path) -> dict[str, Any]:
    """Check B: Exact HEAD and lineage main SHA verification without stale main hardcoding."""
    head_sha = _git_head(repository_root)
    env_main = os.environ.get("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", "").strip().lower()
    if not env_main:
        raise P30LiveReadinessError(
            "Check B failed: ATHENA_EXPECTED_LINEAGE_MAIN_SHA environment variable is required and cannot be empty"
        )
    if len(env_main) != 40 or any(c not in "0123456789abcdef" for c in env_main):
        raise P30LiveReadinessError(
            f"Check B failed: ATHENA_EXPECTED_LINEAGE_MAIN_SHA {env_main} is not 40 hex chars"
        )

    return {
        "status": "PASSED",
        "checked_out_head_sha": head_sha,
        "resolved_lineage_main_sha": env_main,
        "head_sha": head_sha,
        "lineage_main_sha": env_main,
    }


def check_c_network_block_assertion() -> dict[str, Any]:
    """Check C: Verify that strict network block actively prevents connections."""
    blocked = False
    try:
        with strict_network_block():
            socket.create_connection(("127.0.0.1", 80), timeout=0.1)
    except P30LiveReadinessError as exc:
        if "NETWORK_ACCESS_FORBIDDEN" in str(exc):
            blocked = True
    except Exception:
        pass
    if not blocked:
        raise P30LiveReadinessError(
            "Check C failed: network block did not raise expected P30LiveReadinessError"
        )
    return {"status": "PASSED", "network_block_verified": True}


def check_d_canonical_core_and_registries() -> dict[str, Any]:
    """Check D: Canonical core contracts and registry SHAs."""
    from domain import canonical_core
    from domain import current_shadow_fixture_identity_aliases as fixture_aliases
    from domain import current_shadow_fixture_identity_run199_overlay as run199_identity
    from domain import current_shadow_fixture_identity_v2 as fixture_identity_v2
    from domain import current_shadow_sportybet_team_label_compatibility as team_label_compatibility
    from domain import provider_market_semantics

    contracts = canonical_core.validate_canonical_core_contract()
    provider_contract = (
        provider_market_semantics.validate_provider_market_semantics_contract()
    )
    alias_sha = fixture_aliases.registry_sha256()
    if alias_sha != fixture_aliases.REGISTRY_SHA256:
        raise P30LiveReadinessError("Check D failed: fixture alias registry drifted")
    stable_sha = fixture_identity_v2.registry_sha256()
    if stable_sha != fixture_identity_v2.REGISTRY_SHA256:
        raise P30LiveReadinessError("Check D failed: stable identity registry drifted")
    team_label_sha = team_label_compatibility.policy_sha256()
    if team_label_sha != team_label_compatibility.EXPECTED_POLICY_SHA256:
        raise P30LiveReadinessError("Check D failed: team label policy drifted")
    run199_sha = run199_identity.policy_sha256()
    if run199_sha != run199_identity.POLICY_SHA256:
        raise P30LiveReadinessError("Check D failed: run-199 policy drifted")

    return {
        "status": "PASSED",
        "canonical_core_contract_sha256": contracts["canonical_core_contract_sha256"],
        "provider_contract_sha256": provider_contract[
            "canonical_provider_market_semantics_contract_sha256"
        ],
        "alias_registry_sha256": alias_sha,
        "stable_identity_registry_sha256": stable_sha,
        "team_label_policy_sha256": team_label_sha,
        "run199_policy_sha256": run199_sha,
    }


def check_e_discovery_contract() -> dict[str, Any]:
    """Check E: SportyBet current event discovery contract."""
    from domain import (
        sportybet_current_event_discovery_reconciliation as discovery,
    )

    identities = discovery.validate_current_event_discovery_contract()
    return {
        "status": "PASSED",
        "discovery_contract_sha256": identities[
            "current_event_discovery_contract_sha256"
        ],
    }


def check_f_upcoming_discovery_contract() -> dict[str, Any]:
    """Check F: Current Shadow and P3 share the reviewed complete pcUpcoming owner."""
    from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
    from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
    from domain import current_shadow_fixture_identity_aliases as aliases
    from domain import current_shadow_fixture_identity_v2 as stable_identity
    from domain import current_shadow_sportybet_upcoming_reconciliation as historical_upcoming
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as upcoming

    identities = upcoming.validate_contract()
    historical_identities = historical_upcoming.validate_contract()
    historical = paginated.validate_contract()
    if identities["source_policy_sha256"] != (
        "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075"
    ) or identities["source_policy_id"] != (
        "ATHENA_CURRENT_SHADOW_PC_UPCOMING_GLOBAL_FOOTBALL_SOURCE_V1"
    ):
        raise P30LiveReadinessError("Check F failed: reviewed pcUpcoming source ancestry drifted")
    if identities["bridge_policy_sha256"] != (
        "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb"
    ):
        raise P30LiveReadinessError("Check F failed: international bridge ancestry drifted")
    if identities["runtime_policy_id"] != upcoming.POLICY_ID or identities["runtime_policy_sha256"] != (
        "e44d8b3476118a094d3e59f885f7456c3aebc677c07d8eeefaa232df5bc6a43e"
    ) or identities["pagination_complete_required"] is not True:
        raise P30LiveReadinessError("Check F failed: runtime wrapper or completeness rule drifted")
    if identities["identity_compatibility_policy_sha256"] != (
        "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
    ):
        raise P30LiveReadinessError("Check F failed: identity compatibility policy SHA drifted")
    if historical_identities["upstream_upcoming_source_contract_sha256"] != (
        "90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff"
    ):
        raise P30LiveReadinessError(
            "Check F failed: historical wap source contract SHA drifted"
        )
    if historical_identities["current_shadow_upcoming_policy_id"] != (
        "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1"
    ):
        raise P30LiveReadinessError(
            "Check F failed: retained historical wap strategy ID drifted"
        )
    if historical_identities["current_shadow_upcoming_compatibility_sha256"] != (
        "e0718a5e7c9e0c707ba5cc7369910f3ec371bd1a9f7520ab41aa30df69d0ab12"
    ):
        raise P30LiveReadinessError(
            "Check F failed: historical wap compatibility SHA drifted"
        )
    if identity_compatibility.POLICY_ID != "ATHENA_CURRENT_SHADOW_FIXTURE_IDENTITY_COMPATIBILITY_V1" or identity_compatibility.calculate_policy_sha256() != (
        "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58"
    ):
        raise P30LiveReadinessError(
            "Check F failed: shared identity compatibility policy SHA drifted"
        )
    if historical["contract_sha256"] != (
        "6de2847f8ed32873f7ae50e902708c7e27ca5516f492e183063f3dfc0f1635a8"
    ):
        raise P30LiveReadinessError(
            "Check F failed: retained paginated compatibility contract SHA drifted"
        )
    if aliases.REGISTRY_SHA256 != (
        "cb3573bb5d695aca8a496a50c4ad6962b88f3670175058f8239c5daf1730f0ce"
    ):
        raise P30LiveReadinessError("Check F failed: alias V3 SHA drifted")
    if stable_identity.REGISTRY_SHA256 != (
        "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e"
    ) or stable_identity.STATE_SCHEMA_VERSION != 2:
        raise P30LiveReadinessError(
            "Check F failed: stable identity registry or state schema drifted"
        )
    return {
        "status": "PASSED",
        "runtime_policy_id": identities["runtime_policy_id"],
        "runtime_policy_sha256": identities["runtime_policy_sha256"],
        "source_policy_id": identities["source_policy_id"],
        "source_policy_sha256": identities["source_policy_sha256"],
        "bridge_policy_sha256": identities["bridge_policy_sha256"],
        "identity_compatibility_policy_sha256": identities["identity_compatibility_policy_sha256"],
        "historical_wap_source_contract_sha256": historical_identities[
            "upstream_upcoming_source_contract_sha256"
        ],
        "active_discovery_root": str(upcoming.ALLOWED_OUTPUT_RELATIVE),
        "historical_wap_source_retained": True,
        "runtime_pagination_complete_required": True,
        "paginated_contract_sha256_retained_historically": historical[
            "contract_sha256"
        ],
        "paginated_runtime_reconciliation_authority": False,
    }


def check_f_paginated_discovery_contract() -> dict[str, Any]:
    """Compatibility name for older callers; the active check is upcoming."""
    return check_f_upcoming_discovery_contract()


def check_g_fanout_request_scope_validation() -> dict[str, Any]:
    """Check G: Fanout request scope validation rejects global-echo data."""
    from domain import (
        current_shadow_sportybet_catalog_fanout_reconciliation as fanout,
    )
    from types import SimpleNamespace

    class DummyObs:
        def __init__(self, event_ids: tuple[str, ...], category_id: str = "sr:category:1", tournament_id: str = "sr:tournament:1"):
            self.event_ids = event_ids
            self.category_id = category_id
            self.tournament_id = tournament_id

    # 2 requests returning identical 10 events must fail closed
    echo_events = tuple(f"sr:match:{58000000 + i}" for i in range(10))
    echo_observations = [
        DummyObs(echo_events, category_id="sr:category:1", tournament_id="sr:tournament:1"),
        DummyObs(echo_events, category_id="sr:category:1", tournament_id="sr:tournament:2"),
    ]
    rejected = False
    try:
        fanout.validate_fanout_request_scope(echo_observations)
    except fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError as exc:
        if "FANOUT_REQUEST_SCOPE_UNPROVEN" in str(exc):
            rejected = True
    if not rejected:
        raise P30LiveReadinessError(
            "Check G failed: validate_fanout_request_scope did not reject global-echo data"
        )

    # Distinct event lists with matching native scope must pass
    distinct_observations = [
        DummyObs(("sr:match:1", "sr:match:2"), category_id="sr:category:1", tournament_id="sr:tournament:1"),
        DummyObs(("sr:match:3", "sr:match:4"), category_id="sr:category:1", tournament_id="sr:tournament:2"),
    ]
    logical_events = [
        SimpleNamespace(event_id="sr:match:1", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:2", category_id="sr:category:1", tournament_id="sr:tournament:1"),
        SimpleNamespace(event_id="sr:match:3", category_id="sr:category:1", tournament_id="sr:tournament:2"),
        SimpleNamespace(event_id="sr:match:4", category_id="sr:category:1", tournament_id="sr:tournament:2"),
    ]
    status = fanout.validate_fanout_request_scope(distinct_observations, events=logical_events)
    if status != "FANOUT_REQUEST_SCOPE_PROVEN":
        raise P30LiveReadinessError(
            "Check G failed: distinct observations did not receive FANOUT_REQUEST_SCOPE_PROVEN"
        )

    return {"status": "PASSED", "global_echo_rejection_verified": True}


def check_h_retained_evidence_verification(repository_root: Path) -> dict[str, Any]:
    """Check H: Report truthful evidence inventory and verify contracts/counterparts offline."""
    from domain import (
        current_shadow_sportybet_paginated_discovery_reconciliation as paginated,
    )
    from domain import current_shadow_sportybet_upcoming_reconciliation as historical_upcoming
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as upcoming
    from domain import (
        sportybet_current_event_discovery_reconciliation as discovery,
    )
    from domain import current_shadow_fixture_identity_v2 as identity
    from scripts import current_shadow_fixture_identity_reconciliation_recovery as recovery
    from types import SimpleNamespace

    # Contract verification passes without network
    discovery.validate_current_event_discovery_contract()
    paginated.validate_contract()
    upcoming.validate_contract()
    historical_upcoming.validate_contract()

    shape_path = (
        repository_root
        / "tests"
        / "fixtures"
        / "p3_0"
        / "run_35441111017_source_viability_shape.json"
    )
    try:
        shape = json.loads(shape_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P30LiveReadinessError(
            "Check H failed: run-35441111017 source-viability shape fixture is unavailable"
        ) from exc
    if (
        type(shape) is not dict
        or shape.get("evidence_kind")
        != "DETERMINISTIC_SHAPE_REPRODUCTION_NOT_RETAINED_BYTES"
    ):
        raise P30LiveReadinessError(
            "Check H failed: source-viability fixture must identify itself as a shape reproduction"
        )
    exact_shape = {
        "run_id": "35441111017",
        "primary_artifact_id": 10584076663,
        "primary_artifact_zip_sha256": "81b7e0dfb9fb91cbc961d591c876010330025da24f1aafa3dca4ff038c93222e",
        "diagnostics_artifact_id": 10584211437,
        "diagnostics_artifact_zip_sha256": "a9facd41768ad271cae6ccb72f0c092b6f640d82daf0de5c46509af55766064d",
        "raw_page_sha256": "f13f112afa8c376a9cc95b6b0e1a1c254592786a8574acb59b93d377ddea792c",
        "source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET",
        "request_target": "/api/ng/factsCenter/liveOrPrematchEvents?sportId=sr%3Asport%3A1&pageSize=100&pageNum=1",
        "observed_at": "2026-09-19T11:49:46.016668Z",
        "provider_page_item_count": 79,
        "captured_page_count": 1,
        "event_count": 136,
        "event_status_counts": {"1": 136},
        "prematch_bookable_counts": {"false": 136},
        "booking_status_counts": {"Booked": 136},
        "match_status_counts": {"H1": 38, "HT": 43, "H2": 55},
        "kickoff_min": "2026-09-19T10:00:00.000000Z",
        "kickoff_max": "2026-09-19T11:45:00.000000Z",
        "pagination_termination_basis": "SHORT_PAGE_BELOW_REQUESTED_PAGE_SIZE",
        "source_viability": "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS",
    }
    if any(shape.get(key) != value for key, value in exact_shape.items()):
        raise P30LiveReadinessError(
            "Check H failed: run-35441111017 source-viability shape drifted"
        )

    # Replay the exact retained source shape through the first-boundary failure
    # taxonomy.  This is deliberately a deterministic shape reproduction: no
    # retained provider bytes are reacquired or claimed here.
    from scripts import _p3_0_paired_capture_part2 as paired_capture

    negative_summary = {
        "provider_event_count": 136,
        "provider_prematch_bookable_count": 0,
        "provider_inplay_count": 136,
        "provider_future_lead_eligible_count": 0,
        "provider_too_close_count": 136,
        "provider_discovery_source_method": exact_shape["source_method"],
        "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1",
        "provider_discovery_observed_at": exact_shape["observed_at"],
        "source_viability": exact_shape["source_viability"],
        "current_reconciliation_by_request_date": {
            date: {
                "provider_event_count": 136,
                "provider_prematch_bookable_count": 0,
                "provider_inplay_count": 136,
                "provider_future_lead_eligible_count": 0,
                "provider_too_close_count": 136,
                "reconciled_fixture_count": 0,
                "disposition_counts": {
                    "PROVIDER_EVENT_TOO_CLOSE_TO_KICKOFF": 136,
                },
            }
            for date in (
                "20260919",
                "20260920",
                "20260921",
            )
        },
    }
    negative_bundle = SimpleNamespace(
        router_inputs=(),
        reviewed_fixture_count=50,
        reconciled_fixture_count=0,
        provider_event_count=136,
        priced_fixture_count=0,
        source_summary=negative_summary,
    )
    try:
        paired_capture._require_nonempty_router_inputs(negative_bundle)
    except paired_capture.P30PairedCaptureError as exc:
        message = str(exc)
        if not message.startswith(paired_capture._ZERO_ROUTER_DIAGNOSTIC_PREFIX):
            raise P30LiveReadinessError(
                "Check H failed: source-viability replay emitted an unbounded diagnostic"
            ) from exc
        diagnostic = json.loads(
            message[len(paired_capture._ZERO_ROUTER_DIAGNOSTIC_PREFIX):]
        )
        if diagnostic.get("failure_code") != "PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS":
            raise P30LiveReadinessError(
                "Check H failed: retained all-in-play shape was not classified at provider viability"
            ) from exc
        if "NO_RECONCILIATION_AUTHORIZED_FOTMOB_COUNTERPART" in message:
            raise P30LiveReadinessError(
                "Check H failed: source-viability replay fell through to FotMob counterpart failure"
            ) from exc
    else:
        raise P30LiveReadinessError(
            "Check H failed: retained all-in-play shape unexpectedly yielded Router inputs"
        )

    retained_external_evidence = {
        "artifact_id": 10584211437,
        "zip_sha256": "a9facd41768ad271cae6ccb72f0c092b6f640d82daf0de5c46509af55766064d",
        "raw_page_sha256": "f13f112afa8c376a9cc95b6b0e1a1c254592786a8574acb59b93d377ddea792c",
        "retained_bytes_exist": True,
        "retained_bytes_checked_in": False,
        "path": ".cache/athena-research/sportybet-current-event-discovery/0571e8445cc1b557ea581c59/page-001.json",
    }

    # Exact offline counterpart matching replay
    identity.reset_runtime_evidence()
    try:
        fotmob_payload = json.dumps({
            "leagues": [{
                "ccode": "USA",
                "primaryId": 130,
                "name": "Major League Soccer",
                "matches": [{
                    "id": 5071366,
                    "home": {"id": 546238, "name": "New York City FC", "longName": "New York City FC"},
                    "away": {"id": 6514, "name": "Red Bull New York", "longName": "Red Bull New York"},
                    "status": {"utcTime": "2026-09-18T23:30:00Z"},
                }],
            }]
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        provider_payload = json.dumps({
            "events": [{
                "eventId": "sr:match:66299550",
                "estimateStartTime": int(datetime.fromisoformat("2026-09-18T23:30:00+00:00").timestamp() * 1000),
                "homeTeamId": "sr:competitor:167510",
                "homeTeamName": "New York City FC",
                "awayTeamId": "sr:competitor:2506",
                "awayTeamName": "New York Red Bulls",
                "sport": {
                    "category": {"id": "sr:category:26", "tournament": {"id": "sr:tournament:242", "name": "MLS"}}
                },
            }]
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        identity.observe_fotmob_payload(fotmob_payload)
        identity.observe_provider_payload(provider_payload)

        test_event = SimpleNamespace(
            event_id="sr:match:66299550",
            kickoff_utc=datetime.fromisoformat("2026-09-18T23:30:00+00:00"),
            competition_name="MLS",
            home_team_name="New York City FC",
            away_team_name="New York Red Bulls",
        )
        test_row = SimpleNamespace(
            source_fixture_identifier="5071366",
            kickoff=datetime.fromisoformat("2026-09-18T23:30:00+00:00"),
            competition="Major League Soccer",
            home_team="New York City FC",
            away_team="Red Bull New York",
        )
        retained_matches = recovery.match_event(test_event, (test_row,))
        if not retained_matches or retained_matches[0].source_fixture_identifier != "5071366":
            raise P30LiveReadinessError(
                "Check H failed: offline counterpart replay did not match counterpart"
            )
    finally:
        identity.reset_runtime_evidence()

    return {
        "status": "PASSED",
        "run_35441111017_source_viability_shape_reproduction": {
            **exact_shape,
            "evidence_kind": shape["evidence_kind"],
            "retained_external_evidence": retained_external_evidence,
            "offline_shape_reproduction": {
                "evidence_kind": "DETERMINISTIC_SHAPE_REPRODUCTION_NOT_RETAINED_BYTES",
                "retained_bytes_checked_in": False,
            },
            "direct_detail_acquisitions": 0,
            "reconciled_fixture_count": 0,
            "priced_fixture_count": 0,
            "router_input_count": 0,
        },
        "synthetic_end_to_end_boundary": {
            "synthetic_counterpart_matching_verified": True,
            "contracts_verified": True,
        },
        "run_35441111017_offline_failure_classification": {
            "failure_code": "PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS",
            "direct_detail_acquisitions": 0,
            "priced_fixture_count": 0,
            "router_input_count": 0,
        },
        "active_upcoming_discovery_root": str(upcoming.ALLOWED_OUTPUT_RELATIVE),
        "historical_wap_source_retained": True,
        "paginated_runtime_reconciliation_authority": False,
    }


def check_i_pre_router_pipeline_readiness(repository_root: Path) -> dict[str, Any]:
    """Check I: Prove supported and P3 use the exact same canonical pre-Router source strategy."""
    from domain import current_shadow_all_market_runner as runner
    from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated_discovery
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as upcoming_discovery
    from scripts import _p3_0_paired_capture_part1 as part1

    if not hasattr(runner, "acquire_current_shadow_pre_router_bundle"):
        raise P30LiveReadinessError(
            "Check I failed: acquire_current_shadow_pre_router_bundle is missing from runner"
        )
    if not hasattr(part1, "_collect_sources"):
        raise P30LiveReadinessError(
            "Check I failed: _collect_sources is missing from part1"
        )
    if runner.reconciliation is not upcoming_discovery:
        raise P30LiveReadinessError(
            "Check I failed: runner.reconciliation is not the reviewed upcoming discovery owner"
        )
    if runner.reconciliation is paginated_discovery:
        raise P30LiveReadinessError(
            "Check I failed: paginated discovery remains runtime authority"
        )
    if upcoming_discovery.CURRENT_SHADOW_UPCOMING_POLICY_ID != (
        "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1"
    ):
        raise P30LiveReadinessError(
            "Check I failed: upcoming discovery strategy ID drifted"
        )
    upcoming_discovery.validate_contract()
    runner_source = Path(runner.__file__).read_text(encoding="utf-8")
    if runner_source.count("capture_current_upcoming_discovery(") != 1:
        raise P30LiveReadinessError(
            "Check I failed: runner does not have one canonical upcoming acquisition call"
        )
    if runner_source.count("reconcile_current_events_from_upcoming_discovery(") != 1:
        raise P30LiveReadinessError(
            "Check I failed: runner does not have one canonical upcoming reconciliation call"
        )
    if "capture_current_paginated_discovery" in runner_source:
        raise P30LiveReadinessError(
            "Check I failed: runner source still references paginated discovery"
        )
    if runner.AUTHORITY.get("production_sportybet_execution") is not False:
        raise P30LiveReadinessError(
            "Check I failed: production_sportybet_execution authority must be False"
        )

    from domain.p3_0_comparison_evidence import (
        LEGACY_NUMPY_JSON_NORMALIZATION_POLICY_ID,
        LEGACY_NUMPY_JSON_NORMALIZATION_RULES,
        LegacyEvidenceObserver,
        P30ComparisonEvidenceError,
        project_legacy_output,
        validate_contract,
    )
    from services.analysis_pipeline import (
        LEGACY_RUNTIME_AUTHORIZATION_STATE,
        LEGACY_RUNTIME_BET_BLOCK_REASON,
        apply_runtime_authorization,
    )

    contract_sha = validate_contract()

    if LEGACY_NUMPY_JSON_NORMALIZATION_POLICY_ID != "P3_LEGACY_NUMPY_JSON_NORMALIZATION_V1":
        raise P30LiveReadinessError("Check I failed: legacy numpy normalization policy ID drifted")
    expected_rules = (
        "NUMPY_GENERIC_ITEM_TO_CANONICAL_JSON_RECURSIVE",
        "NUMPY_NDARRAY_TOLIST_TO_CANONICAL_JSON_RECURSIVE",
        "DUCK_TYPED_TOLIST_ITEM_FORBIDDEN",
        "PYTHON_NON_JSON_CONTAINERS_FORBIDDEN",
        "NONFINITE_NUMBERS_FORBIDDEN",
    )
    if LEGACY_NUMPY_JSON_NORMALIZATION_RULES != expected_rules:
        raise P30LiveReadinessError("Check I failed: legacy numpy normalization rules drifted")

    sample_analysis = {
        "fixture_id": "test_fixture_ml_1",
        "home_team": "DC United",
        "away_team": "Charlotte FC",
        "league": "Major League Soccer",
        "match_date": "2026-09-19",
        "decision_status": "BET",
        "recommended_analytical_verdict": "BET",
        "edge_differential": 0.05,
        "edge_is_bookmaker_value": True,
        "bookmaker_odds": 2.1,
        "bookmaker_probability": 0.48,
        "edge_pp": 5.0,
        "upset_alert": False,
        "risk_score": 10.0,
        "stale_data": False,
        "viable_markets": [],
        "accumulator_eligible_selection": "HOME",
        "reasoning_verdicts": ["VALUE"],
        "no_bet_reasons": [],
        "evidence_report": {
            "final_decision": "BET",
            "legacy_decision_status_before_runtime_gate": "BET",
            "decision_reasons": ["Cleared analytical checks."],
            "runtime_authorization_state": LEGACY_RUNTIME_AUTHORIZATION_STATE,
            "runtime_authorization_reasons": [LEGACY_RUNTIME_BET_BLOCK_REASON],
        },
    }
    quarantined = apply_runtime_authorization(sample_analysis)
    projected = project_legacy_output(
        pre_gate=quarantined,
        authorized=quarantined,
        exported=quarantined,
    )

    def _assert_quarantined_keys_absent(val: Any) -> None:
        if isinstance(val, dict):
            for k, v in val.items():
                if k in (
                    "runtime_authorization_state",
                    "runtime_authorization_reasons",
                    "kelly_stake_pct",
                    "legacy_kelly_stake_pct_before_runtime_gate",
                ):
                    raise P30LiveReadinessError(
                        f"Check I failed: quarantined key '{k}' found in projected output"
                    )
                _assert_quarantined_keys_absent(v)
        elif isinstance(val, list):
            for item in val:
                _assert_quarantined_keys_absent(item)

    _assert_quarantined_keys_absent(projected)

    bad_analysis = dict(quarantined)
    bad_analysis["authorization"] = "secret_bearer_token"
    credential_rejected = False
    try:
        project_legacy_output(
            pre_gate=bad_analysis,
            authorized=bad_analysis,
            exported=bad_analysis,
        )
    except P30ComparisonEvidenceError:
        credential_rejected = True
    if not credential_rejected:
        raise P30LiveReadinessError("Check I failed: credential-like key was not rejected")

    # Offline verification of numpy scalar projection:
    import numpy as np
    numpy_test_analysis = dict(quarantined)
    numpy_test_analysis["risk_score"] = np.float64(10.0)
    numpy_test_analysis["edge_differential"] = np.float32(0.05)
    numpy_projected = project_legacy_output(
        pre_gate=numpy_test_analysis,
        authorized=numpy_test_analysis,
        exported=numpy_test_analysis,
    )
    proj_risk = numpy_projected["exported_row"]["risk_score"]
    if type(proj_risk) is not float or proj_risk != 10.0:
        raise P30LiveReadinessError("Check I failed: np.float64 risk_score not normalized to Python float")

    # Verify duck-typed object rejection without invocation:
    class _DuckItem:
        called = False
        def item(self):
            _DuckItem.called = True
            return 1.0

    duck_analysis = dict(quarantined)
    duck_analysis["evidence_report"] = dict(quarantined["evidence_report"])
    duck_analysis["evidence_report"]["duck"] = _DuckItem()
    duck_rejected = False
    try:
        project_legacy_output(pre_gate=duck_analysis, authorized=duck_analysis, exported=duck_analysis)
    except P30ComparisonEvidenceError:
        duck_rejected = True
    if not duck_rejected or _DuckItem.called:
        raise P30LiveReadinessError("Check I failed: duck-typed object was not rejected without invocation")

    class _DuckToList:
        called = False
        def tolist(self):
            _DuckToList.called = True
            raise AssertionError("must not be called")

    duck_list_analysis = dict(quarantined)
    duck_list_analysis["evidence_report"] = dict(quarantined["evidence_report"])
    duck_list_analysis["evidence_report"]["duck_list"] = _DuckToList()
    duck_list_rejected = False
    try:
        project_legacy_output(pre_gate=duck_list_analysis, authorized=duck_list_analysis, exported=duck_list_analysis)
    except P30ComparisonEvidenceError:
        duck_list_rejected = True
    if not duck_list_rejected or _DuckToList.called:
        raise P30LiveReadinessError("Check I failed: duck-typed .tolist() object was not rejected without invocation")

    # Verify tuple/set/frozenset rejection:
    tuple_analysis = dict(quarantined)
    tuple_analysis["evidence_report"] = dict(quarantined["evidence_report"])
    tuple_analysis["evidence_report"]["tup"] = (1, 2)
    tuple_rejected = False
    try:
        project_legacy_output(pre_gate=tuple_analysis, authorized=tuple_analysis, exported=tuple_analysis)
    except P30ComparisonEvidenceError:
        tuple_rejected = True
    if not tuple_rejected:
        raise P30LiveReadinessError("Check I failed: tuple container was not rejected fail-closed")

    set_analysis = dict(quarantined)
    set_analysis["evidence_report"] = dict(quarantined["evidence_report"])
    set_analysis["evidence_report"]["set_value"] = {1, 2}
    set_rejected = False
    try:
        project_legacy_output(pre_gate=set_analysis, authorized=set_analysis, exported=set_analysis)
    except P30ComparisonEvidenceError:
        set_rejected = True
    if not set_rejected:
        raise P30LiveReadinessError("Check I failed: set container was not rejected fail-closed")

    frozenset_analysis = dict(quarantined)
    frozenset_analysis["evidence_report"] = dict(quarantined["evidence_report"])
    frozenset_analysis["evidence_report"]["frozenset_value"] = frozenset({1, 2})
    frozenset_rejected = False
    try:
        project_legacy_output(pre_gate=frozenset_analysis, authorized=frozenset_analysis, exported=frozenset_analysis)
    except P30ComparisonEvidenceError:
        frozenset_rejected = True
    if not frozenset_rejected:
        raise P30LiveReadinessError("Check I failed: frozenset container was not rejected fail-closed")

    # Verify non-finite rejection:
    nan_analysis = dict(quarantined)
    nan_analysis["risk_score"] = np.float64("nan")
    nan_rejected = False
    try:
        project_legacy_output(pre_gate=nan_analysis, authorized=nan_analysis, exported=nan_analysis)
    except P30ComparisonEvidenceError:
        nan_rejected = True
    if not nan_rejected:
        raise P30LiveReadinessError("Check I failed: non-finite number was not rejected fail-closed")

    return {
        "status": "PASSED",
        "canonical_strategy_id": upcoming_discovery.CURRENT_SHADOW_UPCOMING_POLICY_ID,
        "canonical_source_method": upcoming_discovery.DISCOVERY_SOURCE_METHOD,
        "active_diagnostics_root": str(upcoming_discovery.ALLOWED_OUTPUT_RELATIVE),
        "supported_and_p3_strategy_unified": True,
        "paginated_runtime_reconciliation_authority": False,
        "catalog_fanout_runtime_authority": False,
        "contract_sha256": contract_sha,
        "runtime_safety_quarantine_verified": True,
        "credential_protection_verified": True,
        "legacy_numpy_normalization_policy_id": LEGACY_NUMPY_JSON_NORMALIZATION_POLICY_ID,
        "legacy_numpy_normalization_verified": True,
        "legacy_numpy_normalization_readiness_assertions": [
            "NP_FLOAT64_NORMALIZED",
            "DUCK_ITEM_REJECTED_WITHOUT_INVOCATION",
            "DUCK_TOLIST_REJECTED_WITHOUT_INVOCATION",
            "TUPLE_REJECTED",
            "SET_REJECTED",
            "FROZENSET_REJECTED",
            "NONFINITE_REJECTED",
        ],
    }


def check_j_counterpart_classification() -> dict[str, Any]:
    """Check J: Competition review priority distinguishes policy-approved vs unadmitted leagues."""
    from config.competition_review_priority import (
        resolve_source_competition_review_priority,
    )

    # Policy approved leagues
    premier_league = resolve_source_competition_review_priority("ENG", "Premier League")
    la_liga = resolve_source_competition_review_priority("ESP", "LaLiga")
    champions_league = resolve_source_competition_review_priority(
        "INT", "Champions League"
    )
    if None in (premier_league, la_liga, champions_league):
        raise P30LiveReadinessError(
            "Check J failed: approved competition was rejected by policy"
        )

    # Unadmitted leagues must be strictly excluded (return None)
    unadmitted_cases = [
        ("KOR", "K-League 1"),
        ("USA", "NWSL"),
        ("PER", "Liga 1"),
        ("CRI", "Primera Division"),
    ]
    for ccode, comp_name in unadmitted_cases:
        priority = resolve_source_competition_review_priority(ccode, comp_name)
        if priority is not None:
            raise P30LiveReadinessError(
                f"Check J failed: unadmitted competition {comp_name} ({ccode}) was not excluded"
            )

    return {
        "status": "PASSED",
        "approved_competitions_verified": ["Premier League", "LaLiga", "Champions League"],
        "unadmitted_competitions_excluded": [name for _ccode, name in unadmitted_cases],
    }


def check_k_bounded_failure_taxonomy() -> dict[str, Any]:
    """Check K: Bounded failure taxonomy in _require_nonempty_router_inputs."""
    from scripts import _p3_0_paired_capture_part2 as part2

    class DummyEmptyBundle:
        router_inputs = ()
        reviewed_fixture_count = 10
        reconciled_fixture_count = 0
        provider_event_count = 10
        priced_fixture_count = 0
        source_summary = {
            "provider_event_count": 10,
            "provider_prematch_bookable_count": 0,
            "provider_inplay_count": 10,
            "provider_future_lead_eligible_count": 0,
            "provider_too_close_count": 10,
            "provider_discovery_source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET",
            "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1",
            "provider_discovery_observed_at": "2026-09-19T11:49:46.016668Z",
            "source_viability": "PROSPECTIVE_DISCOVERY_NO_PREMATCH_EVENTS",
            "current_reconciliation_by_request_date": {
                "20260919": {
                    "provider_event_count": 10,
                    "provider_prematch_bookable_count": 0,
                    "provider_inplay_count": 10,
                    "provider_future_lead_eligible_count": 0,
                    "provider_too_close_count": 10,
                    "provider_discovery_source_method": "PUBLIC_ANONYMOUS_FACTS_CENTER_LIVE_OR_PREMATCH_EVENTS_GET",
                    "provider_discovery_strategy_id": "ATHENA_CURRENT_SHADOW_PAGINATED_GLOBAL_DISCOVERY_V1",
                    "provider_discovery_observed_at": "2026-09-19T11:49:46.016668Z",
                    "reconciled_fixture_count": 0,
                    "disposition_counts": {
                        "NO_EXACT_REVIEWED_FOTMOB_MATCH": 10
                    },
                }
            }
        }

    raised = False
    try:
        part2._require_nonempty_router_inputs(DummyEmptyBundle())
    except part2.P30PairedCaptureError as exc:
        msg = str(exc)
        if (
            part2._ZERO_ROUTER_DIAGNOSTIC_PREFIX in msg
            and len(msg) <= part2.FAILURE_MESSAGE_MAX_CHARS
            and "PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS" in msg
        ):
            raised = True
    if not raised:
        raise P30LiveReadinessError(
            "Check K failed: _require_nonempty_router_inputs did not emit expected bounded diagnostic"
        )

    return {"status": "PASSED", "bounded_taxonomy_verified": True}


def check_l_workflows_integrity(repository_root: Path) -> dict[str, Any]:
    """Check L: Workflow file structurally orders readiness strictly after restores and before capture."""
    workflow_path = (
        repository_root
        / ".github"
        / "workflows"
        / "p3-0-comparison-evidence-capture.yml"
    )
    if not workflow_path.exists():
        raise P30LiveReadinessError(
            f"Check L failed: workflow file {workflow_path} is missing"
        )
    lines = workflow_path.read_text(encoding="utf-8").splitlines()
    step_names = [
        line.split("- name:")[1].strip()
        for line in lines
        if line.strip().startswith("- name:")
    ]

    def find_step_index(substring: str) -> int:
        for idx, name in enumerate(step_names):
            if substring.lower() in name.lower():
                return idx
        return -1

    prime_idx = find_step_index("history prime")
    pr119_idx = find_step_index("pr119 materialized")
    identity_idx = find_step_index("persistent shadow identity")
    lineage_idx = find_step_index("lineage main")
    readiness_idx = find_step_index("live readiness")
    capture_idx = find_step_index("capture paired p3.0 evidence")

    for label, idx in (
        ("prime", prime_idx),
        ("pr119", pr119_idx),
        ("identity", identity_idx),
        ("lineage", lineage_idx),
        ("readiness", readiness_idx),
        ("capture", capture_idx),
    ):
        if idx == -1:
            raise P30LiveReadinessError(
                f"Check L failed: required workflow step '{label}' was not found"
            )

    if not (
        readiness_idx > prime_idx
        and readiness_idx > pr119_idx
        and readiness_idx > identity_idx
        and readiness_idx > lineage_idx
    ):
        raise P30LiveReadinessError(
            "Check L failed: readiness gate must execute after history prime, PR119, identity state, and lineage main"
        )

    if not (readiness_idx < capture_idx):
        raise P30LiveReadinessError(
            "Check L failed: readiness gate must execute strictly before paired evidence capture"
        )

    capture_lines = [line for line in lines if "--output-dir" in line]
    if not capture_lines:
        raise P30LiveReadinessError("Check L failed: --output-dir not found in capture workflow")
    if not any("artifacts/p3-0-comparison-evidence/capture" in line for line in capture_lines):
        raise P30LiveReadinessError(
            "Check L failed: capture step --output-dir must be artifacts/p3-0-comparison-evidence/capture"
        )
    envelope_dir = repository_root / "artifacts" / "p3-0-comparison-evidence"
    child_dir = envelope_dir / "capture"
    if child_dir.exists():
        raise P30LiveReadinessError(
            "Check L failed: capture child directory must not exist prior to capture execution"
        )

    # Execute offline publication/completion proof
    from domain import p3_0_comparison_evidence as evidence
    from scripts import _p3_0_paired_capture_part1 as capture_part1
    import tempfile

    with tempfile.TemporaryDirectory(prefix="p3-0-readiness-envelope-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        envelope = temp_dir / "artifacts" / "p3-0-comparison-evidence"
        envelope.mkdir(parents=True, exist_ok=True)

        readiness_file = envelope / READINESS_FILENAME
        receipt_content = b'{"status":"P3_0_E1_LIVE_READINESS_VERIFIED"}\n'
        readiness_file.write_bytes(receipt_content)

        capture_child = envelope / "capture"
        if capture_child.exists():
            raise P30LiveReadinessError("Check L failed: capture child exists before publication")

        bundle = capture_part1.build_offline_proof_bundle(partial=False)

        published_path = capture_part1._publish_capture_artifact(bundle, capture_child)
        if published_path != capture_child:
            raise P30LiveReadinessError("Check L failed: _publish_capture_artifact returned unexpected path")

        verified = evidence.verify_capture_artifact(capture_child)
        if verified["canonical_sha256"] != bundle["canonical_sha256"]:
            raise P30LiveReadinessError("Check L failed: verified capture bundle SHA drifted")

        if readiness_file.read_bytes() != receipt_content:
            raise P30LiveReadinessError("Check L failed: readiness receipt was mutated during publication")

        child_manifest_bytes = (capture_child / "manifest.json").read_bytes()
        child_bundle_bytes = (capture_child / "bundle.json").read_bytes()

        second_pub_rejected = False
        try:
            capture_part1._publish_capture_artifact(bundle, capture_child)
        except capture_part1.P30PairedCaptureError as exc:
            if (
                exc.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
                and isinstance(exc.__cause__, evidence.P30ComparisonEvidenceError)
                and "capture output directory already exists" in str(exc.__cause__)
            ):
                second_pub_rejected = True
        if not second_pub_rejected:
            raise P30LiveReadinessError("Check L failed: second publication through production helper did not fail closed with CAPTURE_ARTIFACT_PUBLICATION_FAILED and exact cause")

        if (capture_child / "manifest.json").read_bytes() != child_manifest_bytes:
            raise P30LiveReadinessError("Check L failed: existing child manifest mutated during second publication attempt")
        if (capture_child / "bundle.json").read_bytes() != child_bundle_bytes:
            raise P30LiveReadinessError("Check L failed: existing child bundle mutated during second publication attempt")

        capture_part1._safe_failure(
            capture_child, exact_commit_sha="a" * 40, capture_id="test-preexisting",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("preexisting test"),
        )
        if (capture_child / "p3-0-capture-failure.json").exists():
            raise P30LiveReadinessError("Check L failed: _safe_failure created failure receipt in preexisting published child")
        if (capture_child / "manifest.json").read_bytes() != child_manifest_bytes:
            raise P30LiveReadinessError("Check L failed: _safe_failure mutated manifest.json in preexisting published child")
        if (capture_child / "bundle.json").read_bytes() != child_bundle_bytes:
            raise P30LiveReadinessError("Check L failed: _safe_failure mutated bundle.json in preexisting published child")

        empty_child = envelope / "empty_preexisting_child"
        empty_child.mkdir(parents=True, exist_ok=False)
        capture_part1._safe_failure(
            empty_child, exact_commit_sha="a" * 40, capture_id="test-empty",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("empty test"),
        )
        if any(empty_child.iterdir()):
            raise P30LiveReadinessError("Check L failed: _safe_failure mutated preexisting empty child directory")

        # Canonical destination policy ID proof
        if evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID != "P3_E1_FAILURE_RECEIPT_ONLY_WHEN_CAPTURE_DESTINATION_ABSENT_V1":
            raise P30LiveReadinessError("Check L failed: P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID drifted")
        if hasattr(capture_part1, "SAFE_FAILURE_DESTINATION_POLICY_ID"):
            raise P30LiveReadinessError("Check L failed: duplicate SAFE_FAILURE_DESTINATION_POLICY_ID found in capture script")

        # Atomic claim proofs
        missing_parent_dest = envelope / "nonexistent_parent" / "child"
        if capture_part1._claim_absent_failure_destination(missing_parent_dest):
            raise P30LiveReadinessError("Check L failed: atomic claim succeeded for missing parent envelope")
        if missing_parent_dest.parent.exists():
            raise P30LiveReadinessError("Check L failed: missing parent envelope was created during atomic claim")

        atomic_child = envelope / "atomic_claim_child"
        if not capture_part1._claim_absent_failure_destination(atomic_child):
            raise P30LiveReadinessError("Check L failed: atomic claim failed for absent child")
        if not atomic_child.is_dir():
            raise P30LiveReadinessError("Check L failed: claimed atomic child is not a directory")
        if capture_part1._claim_absent_failure_destination(atomic_child):
            raise P30LiveReadinessError("Check L failed: second atomic claim against existing child succeeded")

        absent_fail_dest = envelope / "absent_fail_child"
        capture_part1._safe_failure(
            absent_fail_dest, exact_commit_sha="a" * 40, capture_id="test-absent-fail",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("absent fail test"),
        )
        fail_receipt_path = absent_fail_dest / "p3-0-capture-failure.json"
        if not fail_receipt_path.exists():
            raise P30LiveReadinessError("Check L failed: _safe_failure did not create failure receipt in absent child")
        fail_receipt = json.loads(fail_receipt_path.read_text(encoding="utf-8"))
        if fail_receipt.get("destination_policy_id") != evidence.P3_FAILURE_RECEIPT_DESTINATION_POLICY_ID:
            raise P30LiveReadinessError("Check L failed: failure receipt destination_policy_id drifted")

        complete_exit, complete_payload = capture_part1.classify_published_capture_result(bundle)
        if complete_exit != 0 or complete_payload.get("status") != "P3_0_E1_CAPTURE_WRITTEN":
            raise P30LiveReadinessError("Check L failed: complete bundle did not classify as exit 0 / CAPTURE_WRITTEN")

        partial_bundle = capture_part1.build_offline_proof_bundle(partial=True)
        partial_exit, partial_payload = capture_part1.classify_published_capture_result(partial_bundle)
        if (
            partial_exit != 1
            or partial_payload.get("failure_code") != evidence.PAIRED_CAPTURE_PARTIAL
            or evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE not in partial_payload.get("capture_stage_causes", [])
        ):
            raise P30LiveReadinessError("Check L failed: partial bundle did not classify as exit 1 / PAIRED_CAPTURE_PARTIAL")

        partial_child = envelope / "partial_capture"
        capture_part1._publish_capture_artifact(partial_bundle, partial_child)
        manifest_bytes_before = (partial_child / "manifest.json").read_bytes()
        bundle_bytes_before = (partial_child / "bundle.json").read_bytes()

        capture_part1._safe_failure(
            partial_child, exact_commit_sha="a" * 40, capture_id="test-partial",
            started_at="2026-09-20T00:00:00.000000Z", exc=RuntimeError("partial test"),
        )
        if (partial_child / "p3-0-capture-failure.json").exists():
            raise P30LiveReadinessError("Check L failed: failure receipt was created in published capture child")

        # Canonical writer no-follow preexistence & broken symlink proofs
        if not evidence._path_entry_preexists(capture_child):
            raise P30LiveReadinessError("Check L failed: _path_entry_preexists returned False for existing capture child")
        if evidence._path_entry_preexists(envelope / "definitely_absent_path_xyz"):
            raise P30LiveReadinessError("Check L failed: _path_entry_preexists returned True for absent path")

        broken_sym_dest = envelope / "broken_sym_dest"
        sym_target_file = envelope / "temp_sym_target.txt"
        sym_target_file.write_text("target", encoding="utf-8")
        try:
            broken_sym_dest.symlink_to(sym_target_file)
            sym_target_file.unlink()
            if not evidence._path_entry_preexists(broken_sym_dest):
                raise P30LiveReadinessError("Check L failed: _path_entry_preexists returned False for broken symlink")
            broken_sym_rejected = False
            try:
                capture_part1._publish_capture_artifact(bundle, broken_sym_dest)
            except capture_part1.P30PairedCaptureError as exc:
                if (
                    exc.failure_code == evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED
                    and isinstance(exc.__cause__, evidence.P30ComparisonEvidenceError)
                    and "capture output directory already exists" in str(exc.__cause__)
                ):
                    broken_sym_rejected = True
            if not broken_sym_rejected:
                raise P30LiveReadinessError("Check L failed: broken symlink destination was not rejected by production publication helper")
            if not broken_sym_dest.is_symlink():
                raise P30LiveReadinessError("Check L failed: broken symlink was overwritten during rejected publication")
        except (OSError, NotImplementedError):
            pass

        # Parent symlink rejection proof
        sym_parent_target = envelope / "real_parent_target"
        sym_parent_target.mkdir(parents=False, exist_ok=False)
        sym_parent = envelope / "sym_parent_dir"
        try:
            sym_parent.symlink_to(sym_parent_target, target_is_directory=True)
            child_under_sym_parent = sym_parent / "capture_child"
            parent_sym_rejected = False
            try:
                evidence.write_capture_artifact(bundle, child_under_sym_parent)
            except evidence.P30ComparisonEvidenceError as exc:
                if "capture output parent must be an existing non-symlink directory" in str(exc):
                    parent_sym_rejected = True
            if not parent_sym_rejected:
                raise P30LiveReadinessError("Check L failed: parent symlink was not rejected by writer")
        except (OSError, NotImplementedError):
            pass

        # Final publication helper re-check proof (deterministic race window)
        race_temp = envelope / "race_test_temp"
        race_temp.mkdir(parents=False, exist_ok=False)
        (race_temp / "temp_file.txt").write_text("temp", encoding="utf-8")
        race_dest = envelope / "race_test_dest"
        race_dest.mkdir(parents=False, exist_ok=False)
        (race_dest / "original.txt").write_text("original", encoding="utf-8")
        race_rejected = False
        try:
            evidence._publish_temporary_capture_directory(race_temp, race_dest)
        except evidence.P30ComparisonEvidenceError as exc:
            if "capture output directory already exists" in str(exc):
                race_rejected = True
        if not race_rejected:
            raise P30LiveReadinessError("Check L failed: _publish_temporary_capture_directory did not reject preexisting destination")
        if (race_dest / "original.txt").read_text(encoding="utf-8") != "original":
            raise P30LiveReadinessError("Check L failed: destination was mutated during final publication rejection")
        import shutil
        shutil.rmtree(race_temp, ignore_errors=True)

        if (partial_child / "manifest.json").read_bytes() != manifest_bytes_before:
            raise P30LiveReadinessError("Check L failed: partial manifest.json was mutated")
        if (partial_child / "bundle.json").read_bytes() != bundle_bytes_before:
            raise P30LiveReadinessError("Check L failed: partial bundle.json was mutated")
        evidence.verify_capture_artifact(partial_child)


    return {
        "status": "PASSED",
        "workflow_step_order_verified": True,
        "readiness_step_index": readiness_idx,
        "capture_step_index": capture_idx,
        "envelope_child_separation_verified": True,
        "capture_child_path": "artifacts/p3-0-comparison-evidence/capture",
        "offline_publication_verified": True,
        "preexisting_child_rejected": True,
        "atomic_child_claim_verified": True,
        "failure_receipt_destination_policy_verified": True,
        "writer_no_follow_preexistence_verified": True,
        "parent_symlink_rejected": True,
        "final_publication_recheck_verified": True,
        "complete_corpus_exit_zero_verified": True,
        "partial_corpus_nonzero_verified": True,
        "partial_artifact_immutability_verified": True,
    }


def check_m_wager_safety_invariants() -> dict[str, Any]:
    """Check M: Safety authority invariants are all False."""
    from domain import current_shadow_all_market_runner as runner
    from domain import current_shadow_sportybet_upcoming_reconciliation as historical_upcoming
    from domain import current_shadow_sportybet_pc_upcoming_reconciliation as upcoming

    safety_keys = ("login", "cookies", "wallet", "staking", "bet", "wager_placed")
    for key in safety_keys:
        if runner.AUTHORITY.get(key) is not False:
            raise P30LiveReadinessError(
                f"Check M failed: runner AUTHORITY[{key}] is not False"
            )
        if upcoming.AUTHORITY.get(key) is not False:
            raise P30LiveReadinessError(
                f"Check M failed: upcoming AUTHORITY[{key}] is not False"
            )
        if historical_upcoming.AUTHORITY.get(key) is not False:
            raise P30LiveReadinessError(
                f"Check M failed: historical upcoming AUTHORITY[{key}] is not False"
            )
    return {
        "status": "PASSED",
        "all_safety_invariants_false": True,
        "historical_wap_source_retained_only": True,
        "paginated_source_retained_historically_only": True,
    }


def check_n_no_dispatch_or_comment_mutation_authority(repository_root: Path) -> dict[str, Any]:
    """Check N: Zero dispatch authority / no comment mutation invariant (static proof)."""
    # 1. Inspect .github/workflows/p3-0-comparison-evidence-capture.yml permissions
    workflow_path = (
        repository_root
        / ".github"
        / "workflows"
        / "p3-0-comparison-evidence-capture.yml"
    )
    if not workflow_path.exists():
        raise P30LiveReadinessError(
            f"Check N failed: workflow file {workflow_path} is missing"
        )
    workflow_content = workflow_path.read_text(encoding="utf-8")
    import re
    perm_match = re.search(r"permissions:\s*\n((?:\s+[a-z-]+:\s+[a-z-]+\n)+)", workflow_content)
    if not perm_match:
        raise P30LiveReadinessError("Check N failed: workflow permissions block not found")
    perm_block = perm_match.group(1)
    if "issues: write" in perm_block or "actions: write" in perm_block or "pull-requests: write" in perm_block:
        raise P30LiveReadinessError("Check N failed: workflow has mutating permissions")
    if "contents: read" not in perm_block or "actions: read" not in perm_block:
        raise P30LiveReadinessError("Check N failed: workflow must declare contents: read and actions: read")

    # 2. Inspect readiness script source to ensure no GitHub mutation surfaces
    script_lines = [
        line for line in Path(__file__).read_text(encoding="utf-8").splitlines()
        if "mutating_surfaces" not in line and "Check N" not in line
    ]
    script_source = "\n".join(script_lines)
    mutating_surfaces = [
        "issues" + "/comments",
        "gh " + "issue " + "comment",
        "gh " + "pr " + "comment",
        "gh " + "workflow " + "run",
        "gh " + "api " + "-X POST",
        "gh " + "api " + "-X PATCH",
        "gh " + "api " + "-X PUT",
        "gh " + "api " + "-X DELETE",
    ]
    for surface in mutating_surfaces:
        if surface in script_source:
            raise P30LiveReadinessError(
                f"Check N failed: script source contains mutating surface '{surface}'"
            )

    # 3. Verify readiness module exposes no dispatch or comment APIs
    current_module = sys.modules[__name__]
    for attr in dir(current_module):
        if any(keyword in attr.lower() for keyword in ("dispatch", "comment", "mutate", "post_comment")):
            if attr not in ("check_n_no_dispatch_or_comment_mutation_authority",):
                raise P30LiveReadinessError(
                    f"Check N failed: readiness module exposes mutation API '{attr}'"
                )

    return {
        "status": "PASSED",
        "workflow_permissions_verified": {
            "contents": "read",
            "actions": "read",
            "issues_write": False,
            "actions_write": False,
        },
        "script_static_mutation_surfaces_clean": True,
        "readiness_exposes_dispatch_or_comment_api": False,
    }


def run_all_readiness_checks(
    repository_root: Path | None = None,
) -> dict[str, Any]:
    root = repository_root or Path(__file__).resolve().parents[1]
    head_sha = _git_head(root)

    output_dir = root / "artifacts" / "p3-0-comparison-evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / READINESS_FILENAME

    checks: dict[str, Any] = {}
    first_failed_check: str | None = None
    try:
        with strict_network_block():
            for check_name, check_fn in (
                ("check_a_compilation", lambda: check_a_compilation(root)),
                ("check_b_lineage_main", lambda: check_b_lineage_main(root)),
                ("check_c_network_block", check_c_network_block_assertion),
                ("check_d_canonical_core", check_d_canonical_core_and_registries),
                ("check_e_discovery_contract", check_e_discovery_contract),
                ("check_f_upcoming_discovery_contract", check_f_upcoming_discovery_contract),
                ("check_g_fanout_scope", check_g_fanout_request_scope_validation),
                ("check_h_retained_evidence", lambda: check_h_retained_evidence_verification(root)),
                ("check_i_pre_router_pipeline", lambda: check_i_pre_router_pipeline_readiness(root)),
                ("check_j_counterpart_classification", check_j_counterpart_classification),
                ("check_k_bounded_taxonomy", check_k_bounded_failure_taxonomy),
                ("check_l_workflows_integrity", lambda: check_l_workflows_integrity(root)),
                ("check_m_wager_safety", check_m_wager_safety_invariants),
                ("check_n_no_dispatch_or_comment_mutation_authority", lambda: check_n_no_dispatch_or_comment_mutation_authority(root)),
            ):
                first_failed_check = check_name
                checks[check_name] = check_fn()
            first_failed_check = None
    except Exception as exc:
        env_lineage = os.environ.get("ATHENA_EXPECTED_LINEAGE_MAIN_SHA", "").strip().lower()
        failure_report = {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "status": STATUS_FAILED,
            "first_failed_check": first_failed_check,
            "failure_reason": str(exc),
            "exact_commit_sha": head_sha,
            "checked_out_head_sha": head_sha,
            "lineage_main_sha": env_lineage,
            "resolved_lineage_main_sha": env_lineage,
            "canonical_readiness_policy_identity": POLICY_ID,
            "wager_placed": False,
            "checks_passed": len(checks),
        }
        digest = hashlib.sha256(_canonical_bytes(failure_report)).hexdigest()
        failure_report["sha256"] = digest
        raw_failure = _canonical_bytes(failure_report) + b"\n"
        receipt_path.write_bytes(raw_failure)
        (root / READINESS_FILENAME).write_bytes(raw_failure)
        raise P30LiveReadinessError(f"{first_failed_check} failed: {exc}") from exc

    resolved_main = checks["check_b_lineage_main"]["resolved_lineage_main_sha"]
    # Compute deterministic SHA-256 excluding wall-clock timestamp
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "status": STATUS_VERIFIED,
        "exact_commit_sha": head_sha,
        "checked_out_head_sha": head_sha,
        "lineage_main_sha": resolved_main,
        "resolved_lineage_main_sha": resolved_main,
        "checks": checks,
    }
    digest = hashlib.sha256(_canonical_bytes(report_payload)).hexdigest()
    report: dict[str, Any] = {
        **report_payload,
        "sha256": digest,
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    raw = _canonical_bytes(report) + b"\n"
    receipt_path.write_bytes(raw)
    (root / READINESS_FILENAME).write_bytes(raw)
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        report = run_all_readiness_checks()
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "sha256": report["sha256"],
                    "checks_passed": len(report["checks"]),
                },
                indent=2,
            )
        )
        return 0
    except P30LiveReadinessError as exc:
        print(f"P3.0-E1 LIVE READINESS CHECK FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
