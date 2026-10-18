"""Additive E3 source projection regressions for Checkpoint E."""

import hashlib

import pytest

from scripts import audit_checkpoint_e_workflows as audit


def test_pass1_v284_v300_sources_use_exact_predecessor_projection():
    expected = {
        "domain/current_shadow_all_market_runner.py": "b21a9d8a24ac60def6d76e7111ae8a473e9f1a8c",
        "domain/current_shadow_sportybet_pc_upcoming_discovery.py": "fa2069a2ea1201a93a84b5ce3856f9d9574dea71",
        "domain/reviewed_fixture_catalog_admission_source_replay.py": "b2fd258fa89afc492da35cbbe242b15203040759",
        "domain/sportybet_live_event_quote_evidence.py": "096d54fe7493f6d81cdf3c4af7c4a9333c75fadc",
        "scripts/execute_current_shadow_request.py": "52519a5f32cc0d8c130ea053fde5647b751e3fc0",
        "scripts/issue_current_fotmob_reviewed_source.py": "b50689971ee20cb6800145317a0e9fcb3486f40f",
        "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py": "fc772ced8b8c1d0d433179fcc04765ed1b273438",
        "scripts/audit_p4_4f_current_fotmob_exact_lane_caller_migration.py": "74dc0f87592bf956ab649070d9059075e2645989",
        "scripts/audit_p4_4g_current_fotmob_canonical_only_workflow.py": "0884f6837db4c27745f67601574a2a9f20e97df2",
        "scripts/audit_p4_4h_current_shadow_canonical_run_migration_review.py": "ab0f2261e0a30a165b5e48ee9643feda8e4273ab",
        "scripts/audit_port_01_source_identity_parity.py": "ef19eedecff06268f5c2c2c1b6372d240ff39df3",
        "scripts/execute_current_shadow_daily.py": "c2ea5eb021fd7ce72bfd5447458468f75a28a101",
        "tests/test_issue_current_fotmob_reviewed_source.py": "4fa54db086b2689b1dd7a60ae12c64f50c8eec75",
        "tests/test_p4_4h_current_shadow_canonical_run_migration_review.py": "204a756c040bc00c36fd676449f970537209e0cf",
        "tests/portability/test_port_01_source_identity_parity.py": "1bf0d561db831866c322a4c30fa9bc06cd4e844e",
        "tests/test_p3_0_canonical_pre_router_pipeline.py": "be7a93f2b7788b7cdb011a4567788018d6e67bfa",
    }
    value = audit.base_input()
    assert {path: value["files"][path]["git_blob_sha1"] for path in expected} == expected


@pytest.mark.parametrize("path", [
    "domain/current_shadow_all_market_runner.py",
    "domain/current_shadow_sportybet_pc_upcoming_discovery.py",
])
def test_pass1_v284_rejects_tampered_predecessor(monkeypatch, path):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2

    original = a2.read_authenticated_cross_contract_predecessor

    def tampered(candidate):
        raw = original(candidate)
        return raw + b"# tampered predecessor\n" if candidate == path else raw

    monkeypatch.setattr(a2, "read_authenticated_cross_contract_predecessor", tampered)
    with pytest.raises(ValueError, match="Pass-1 V284/V300 source predecessor/successor identity drift"):
        audit.base_input()


def test_pass1_v300_rejects_tampered_predecessor(monkeypatch):
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2

    original = a2.read_authenticated_pass_a_source_predecessors
    path = "scripts/audit_p4_4e_current_fotmob_ingest_issuer.py"

    def tampered():
        predecessors = dict(original())
        predecessors[path] += b"# tampered predecessor\n"
        return predecessors

    monkeypatch.setattr(a2, "read_authenticated_pass_a_source_predecessors", tampered)
    with pytest.raises(ValueError, match="Pass-1 V284/V300 source predecessor/successor identity drift"):
        audit.base_input()


def test_pass1_v2_compat_predecessor_tampering_rejected(monkeypatch):
    from scripts import audit_core_01d_checkpoint_e_completion_v2 as pass_a_v2

    original = pass_a_v2.authenticate_pass_a_e3_compat_predecessors
    path = "tests/portability/test_port_01_source_identity_parity.py"

    def tampered(a2, latest):
        predecessors = dict(original(a2, latest))
        predecessors[path] = "0" * 40
        return predecessors

    monkeypatch.setattr(pass_a_v2, "authenticate_pass_a_e3_compat_predecessors", tampered)
    with pytest.raises(ValueError, match="Pass-1 Pass-A V2 source predecessor identity drift"):
        audit.base_input()


def test_pass1_runner_rejects_current_mode_drift(monkeypatch):
    path = "domain/current_shadow_all_market_runner.py"
    original = audit.git_inventory

    def wrong_mode():
        current = original()
        current[path] = {"mode": "120000", "git_blob_sha1": current[path]["git_blob_sha1"]}
        return current

    monkeypatch.setattr(audit, "git_inventory", wrong_mode)
    with pytest.raises(ValueError, match="Pass-1 V284/V300 source predecessor/successor identity drift"):
        audit.base_input()


def test_historical_matrix_scan_rejects_unapproved_source_path():
    with pytest.raises(ValueError, match="unapproved source predecessor"):
        audit.build_matrix(
            {"files": {}, "scan_paths": []},
            {},
            {"scripts/unrelated.py": b"unapproved"},
        )


def test_historical_matrix_scan_rejects_wrong_predecessor_blob():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2

    path = next(iter(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS))
    raw = b"not the immutable predecessor"
    with pytest.raises(ValueError, match="differs from the immutable source inventory"):
        audit.build_matrix(
            {
                "files": {path: {"mode": "100644", "git_blob_sha1": "0" * 40}},
                "scan_paths": [path],
            },
            {},
            {path: raw},
        )


def test_historical_matrix_scan_rejects_authenticated_path_outside_scan_inventory():
    from scripts import audit_core_01d_ci_offline_transport_boundary as a2

    path = next(iter(a2.E3_CROSS_CONTRACT_SOURCE_FORWARD_PATHS))
    with pytest.raises(ValueError, match="outside the immutable source inventory"):
        audit.build_matrix({"files": {}, "scan_paths": []}, {}, {path: b"bytes"})
