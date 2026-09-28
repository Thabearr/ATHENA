"""Offline integrity and coverage tests for the frozen BASE-00 snapshot."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import socket
import urllib.request
from collections import Counter
from pathlib import Path

import pytest

from scripts import audit_product_baseline_v1 as audit


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / audit.BASELINE_JSON
MARKDOWN_PATH = ROOT / audit.BASELINE_MARKDOWN


def load_baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def reseal(data: dict) -> dict:
    data.pop("canonical_sha256", None)
    data["canonical_sha256"] = audit.sha256_bytes(audit.canonical_bytes(data))
    return data


def errors_for(data: dict) -> list[str]:
    return audit.validate_baseline(data, ROOT, verify_receipts=False)


def test_baseline_json_schema_and_canonical_hash_validate():
    data = load_baseline()
    assert data["schema_version"] == 1
    assert data["baseline_id"] == "ATHENA_PRODUCT_BASELINE_V1"
    assert data["policy_id"] == "ATHENA_PRODUCT_BASELINE_POLICY_V1"
    assert errors_for(data) == []


def test_stable_ids_are_unique_in_each_namespace_and_ascii_safe():
    data = load_baseline()
    collections = [
        (data["entrypoints"], "entrypoint_id"), (data["workflows"], "workflow_id"),
        (data["capabilities"], "capability_id"), (data["product_debt"], "debt_id"),
        (data["unresolved_gates"], "gate_id"), (data["platform_debt"], "platform_debt_id"),
    ]
    for records, field in collections:
        ids = [record[field] for record in records]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(r"[A-Z0-9_-]+", value) for value in ids)


def test_duplicate_baseline_ids_fail_validation():
    data = load_baseline()
    data["capabilities"][1]["capability_id"] = data["capabilities"][0]["capability_id"]
    reseal(data)
    assert any("duplicate IDs in capabilities" in error for error in errors_for(data))


def test_unknown_evidence_id_fails_validation():
    data = load_baseline()
    data["capabilities"][0]["evidence_ids"] = ["EVID-NOT-REAL"]
    reseal(data)
    assert any("unknown evidence ID" in error for error in errors_for(data))


def test_capability_without_evidence_or_blocker_fails_validation():
    data = load_baseline()
    item = data["capabilities"][0]
    item["evidence_ids"] = []
    item["blocker_or_reason"] = ""
    reseal(data)
    assert any("lacks evidence or blocked reason" in error for error in errors_for(data))


def test_unknown_enum_fails_validation():
    data = load_baseline()
    data["capabilities"][0]["state"] = "MAGICALLY_AVAILABLE"
    reseal(data)
    assert any("unknown capability state" in error for error in errors_for(data))


def test_malformed_sha_fails_validation():
    data = load_baseline()
    data["evidence_anchors"][0]["file_sha256"] = "not-a-sha"
    reseal(data)
    assert any("malformed SHA-256 field" in error for error in errors_for(data))


def test_source_paths_reject_absolute_and_traversal_forms():
    for value in ("C:/private/file", "C:\\private\\file", "../secret", "a/../../b", "/absolute/file", "a\\b"):
        with pytest.raises(ValueError):
            audit.relative_path(value)
    assert audit.relative_path("docs/product/athena_product_baseline_v1.md") == "docs/product/athena_product_baseline_v1.md"


def test_source_identity_hash_is_stable_across_windows_and_linux_line_endings(tmp_path):
    lf = tmp_path / "source-lf.py"
    crlf = tmp_path / "source-crlf.py"
    lf.write_bytes(b"first line\nsecond line\n")
    crlf.write_bytes(b"first line\r\nsecond line\r\n")
    assert audit.normalized_source_sha256(lf) == audit.normalized_source_sha256(crlf)


def test_repository_identity_and_postmerge_evidence_are_exact():
    data = load_baseline()
    assert data["repository"] == "Thabearr/ATHENA"
    assert data["baseline_source_commit_sha"] == "eae938a268707f07db3da2d551ea589782902b1c"
    assert data["baseline_source_tree_sha"] == "c00e98b0a4b2d5c5f211e6c4f929a08b8e79639b"
    tests, catalog = data["postmerge_gates"]
    assert (tests["gate_id"], tests["run_id"], tests["head_sha"], tests["status"], tests["conclusion"], tests["required_jobs"]) == ("EVID-POSTMERGE-TESTS", 36344862612, data["baseline_source_commit_sha"], "completed", "success", "all successful")
    assert (catalog["gate_id"], catalog["run_id"], catalog["head_sha"], catalog["status"], catalog["conclusion"]) == ("EVID-POSTMERGE-CATALOG", 36344862576, data["baseline_source_commit_sha"], "completed", "success")


def test_entrypoint_inventory_traces_legacy_and_canonical_surfaces():
    data = load_baseline()
    entries = data["entrypoints"]
    api = [e for e in entries if e["source_path"] == "api/server.py"]
    triggers = {e["symbol_or_trigger"] for e in api}
    for route in ("GET /", "mount /ui", "GET /api/status", "GET /api/leagues", "GET /api/fixtures", "POST /api/generate"):
        assert route in triggers
    generate = next(e for e in api if e["symbol_or_trigger"] == "POST /api/generate")
    assert generate["current_classification"] == "RETAINED_COMPATIBILITY"
    assert "from services.legacy_acca_builder_compat import AccaBuilder" in (ROOT / "api/server.py").read_text(encoding="utf-8")
    assert any(e["symbol_or_trigger"] in {"GET /api/leagues", "GET /api/fixtures"} and e["external_side_effects"] != "NONE" for e in api)
    paths = {e["source_path"] for e in entries}
    assert {"run_desktop.py", "services/athena_run_service.py", ".github/workflows/athena-run.yml", ".github/workflows/current-shadow-all-market.yml"} <= paths
    assert {"POST /api/export", "POST /api/export_code"} <= {e["symbol_or_trigger"] for e in entries if e["source_path"] == "api/export.py"}
    issue_surface = next(w for w in data["workflows"] if w["path"] == ".github/workflows/current-shadow-all-market.yml")
    assert "issue_comment" in issue_surface["trigger_kinds"] and "/athena-shadow " in issue_surface["issue_comment_guard"]


def test_workflow_inventory_includes_current_and_legacy_workflows():
    data = load_baseline()
    workflows = {w["path"]: w for w in data["workflows"]}
    canonical = workflows[".github/workflows/athena-run.yml"]
    legacy = workflows[".github/workflows/current-shadow-all-market.yml"]
    assert "schedule" in canonical["trigger_kinds"] and "workflow_dispatch" in canonical["trigger_kinds"]
    assert "profile" in canonical["workflow_dispatch_inputs"]
    assert canonical["artifact_names_or_roles"] == ["athena-run-${{ github.run_id }}"]
    assert canonical["retirement_eligibility"] is False
    assert "issue_comment" in legacy["trigger_kinds"]
    assert legacy["email_notification"] in {"YES", "CONDITIONAL"}
    assert legacy["retirement_eligibility"] is False
    assert len(workflows) == 38


def test_legacy_http_shell_and_static_ui_debts_are_frozen():
    data = load_baseline()
    debt_ids = {x["debt_id"] for x in data["product_debt"]}
    required = {
        "DEBT-LEGACY-ACCA-BUILDER-API", "DEBT-UI-STATIC-ENGINE-ONLINE", "DEBT-UI-FULLPROOF-LANGUAGE",
        "DEBT-UI-UNSUPPORTED-STAKE-RISK", "DEBT-UI-LONG-BLOCKING-RUN", "DEBT-SHELL-FIXED-PORT",
        "DEBT-API-WILDCARD-CORS", "DEBT-SHELL-UNTRUSTED-RESPONDER", "DEBT-INSTALLED-RUNTIME-GIT",
        "DEBT-REPO-RELATIVE-RESOURCES", "DEBT-WINDOWS-CANONICAL-BYTES", "DEBT-WORKFLOW-DUPLICATION",
        "DEBT-SCHEDULED-SHADOW-OWNERSHIP", "DEBT-PERSISTENT-IDENTITY-ANCESTRY", "DEBT-NOTIFICATION-EMAIL-OWNERSHIP",
        "DEBT-ISSUE-COMMENT-COMPAT", "DEBT-LAGOS-UTC-DATE-PARITY", "DEBT-SHADOW-DELIVERY-COUPLING",
        "DEBT-AUTHORIZATION-PREFLIGHT",
    }
    assert required <= debt_ids
    assert all(x["evidence_ids"] for x in data["product_debt"])
    static_assertions = {x["assertion_id"]: x["result"] for x in data["source_snapshot"]["reproduction"]["assertions"]}
    assert static_assertions["ASSERT-API-LEGACY-ACCA"] == "PASS"
    assert static_assertions["ASSERT-API-WILDCARD-CORS"] == "PASS"
    assert static_assertions["ASSERT-UI-PRODUCT-CLAIMS"] == "PASS"


def test_required_capabilities_and_authority_states_are_explicit():
    data = load_baseline()
    ids = {c["capability_id"] for c in data["capabilities"]}
    expected = {
        "CAP-OFFLINE-REPLAY", "CAP-PROVIDER-ACQUISITION", "CAP-FIXTURE-BROWSING", "CAP-SHADOW-ANALYSIS",
        "CAP-SHADOW-DELIVERY", "CAP-SHADOW-NO-DELIVERY", "CAP-MAIN-LIVE-ANALYSIS", "CAP-MAIN-DELIVERY",
        "CAP-EMAIL-NOTIFICATION", "CAP-HISTORY-VIEW", "CAP-EXPORT", "CAP-BACKUP-RESTORE",
        "CAP-DESKTOP-INSTALLED", "CAP-WINDOWS-QUALIFICATION", "CAP-LINUX-QUALIFICATION",
        "CAP-SCHEDULED-RUN", "CAP-ISSUE-COMMENT", "CAP-WAGER", "CAP-ACCOUNT-ACCESS",
    }
    assert expected <= ids
    assert all(type(c["owner_approval_required"]) is bool for c in data["capabilities"])
    assert {c["capability_id"]: c["state"] for c in data["capabilities"]}["CAP-WAGER"] == "NOT_AUTHORIZED"


def test_required_unresolved_gates_are_present():
    data = load_baseline()
    ids = {g["gate_id"] for g in data["unresolved_gates"]}
    assert {
        "GATE-AUTH-01", "GATE-PORT-01", "GATE-PORT-02", "GATE-P4_4-CLEAN-SUCCESSOR",
        "GATE-P4_4-CALLER-MIGRATION", "GATE-CHECKPOINT-E", "GATE-APP-01", "GATE-DATA-01",
        "GATE-RUN-01-02", "GATE-UX-01", "GATE-PKG-WINDOWS", "GATE-PKG-LINUX", "GATE-REL",
    } <= ids


def test_latest_run_is_exactly_authorization_noncompliant_and_hash_anchored():
    data = load_baseline()
    run = data["latest_live_evidence"]
    assert run["run_id"] == 36345657852 and run["attempt"] == 1
    assert run["head_sha"] == data["baseline_source_commit_sha"]
    assert run["artifact_id"] == 10940728036 and run["artifact_name"] == "athena-run-36345657852"
    assert run["artifact_sha256"] == "f0618654b49fcd7a6a2df95260025b6c655da5aefb477102696a812e9930b18a"
    assert run["request_sha256"] == "0142610f7c9fd1eec15b00da8ca13ecf4d2efc107b6b6d60e6e32e0841aaf3c4"
    assert run["run_receipt_sha256"] == "a8ce4f163432ebead90ee649c7297115acba0a852ceeac2beeb5ef0bdc0d4b6d"
    assert run["inner_current_shadow_receipt_sha256"] == "80ce47a0965562cffd11d8dbd847740fbf57e36b8f1b173020827ea19a18b258"
    assert run["stabilization_receipt_sha256"] == "a16860bd03f03a99087f030ed91474a57233ef3e619a36a20494c615bb15e1c7"
    assert run["source_manifest_canonical_sha256"] == "fb5412845dbed85d00396ea8f11a9343e1145dc4cba07664d54be69b260b449f"
    assert run["classification"] == "POST_P4_4S_INTERNAL_SUCCESS_AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT"
    assert run["delivery"]["owner_authorized_share_code_action"] is False
    assert run["delivery"]["share_code_operation_attempted"] is True
    assert run["request"]["create_share_code"] is True and run["request"]["place_wager"] is False
    assert run["source_capture"]["attempt_count"] == 1 and run["source_capture"]["accepted_attempt_index"] == 1
    assert run["source_capture"]["page_event_counts"] == [100, 100, 23]
    assert run["safety"] == {"bet": False, "cookies": False, "login": False, "place_wager": False, "staking": False, "wager_placed": False, "wallet": False}
    assert run["delivery"]["raw_code_or_url_stored"] is False


def test_baseline_contains_p44r_p44s_and_reread_anchors_without_rewriting_history():
    data = load_baseline()
    anchors = {x["evidence_id"]: x for x in data["evidence_anchors"]}
    assert anchors["EVID-P4-4R-INVENTORY"]["file_sha256"] == "f811c43a292b40565a2db61f412bf0f0abb390dddda9b0383ade7d1804a619bd"
    assert anchors["EVID-P4-4R-RECEIPT"]["canonical_sha256"] == "90e2d7e984609ded80c9113a05453628bebadfcb3cede7fc95b9696931016552"
    assert anchors["EVID-P4-4S-RECEIPT"]["canonical_sha256"] == "0907272a20b439e6874ee3b3fa399a488e8dd3c9a6e428dafa2aa53202c513c3"
    assert anchors["EVID-P4-4S-CONTEXT-SOURCE-BEFORE"]["sha256"] == "2706d8e1b689be153cf6b0de545cfed00f7ee953707a7094f70e6df1344557de"
    assert anchors["EVID-P4-4S-CONTEXT-SOURCE-AFTER"]["sha256"] == "689193a9b9f50229b38e7a024189f6aaa9a5c85235e5575895bb398a535e76ff"
    assert anchors["EVID-P4-4S-ADAPTER-SOURCE-BEFORE"]["sha256"] == "777ab4b88ae0c761f17e96d6904e74e94b61deffaf50a51861dcb8162a47cc71"
    assert anchors["EVID-P4-4S-ADAPTER-SOURCE-AFTER"]["sha256"] == "bf1a9acff635a378f81bafa73f8274a4b9806e34d8d7c3ca13bad1729e205ce2"
    assert data["historical_receipt_immutability"] and len(data["historical_receipt_immutability"]) == 3
    assert audit.validate_baseline(data, ROOT, verify_receipts=True) == []


def test_no_actual_share_code_url_or_secret_material_is_stored():
    data = load_baseline()
    serialized = json.dumps(data, sort_keys=True)
    lowered_keys = set()
    def collect_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                lowered_keys.add(key.lower())
                collect_keys(item)
        elif isinstance(value, list):
            for item in value:
                collect_keys(item)
    collect_keys(data)
    forbidden = {"share_code_value", "share_code_url", "sharecode", "shareurl", "access_token", "raw_cookie"}
    assert not (lowered_keys & forbidden)
    assert data["latest_live_evidence"]["delivery"]["raw_code_or_url_stored"] is False
    assert not re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._-]{16,}|AKIA[0-9A-Z]{16})", serialized)
    # The local UI API origin is source evidence; no share URL/code is included.
    assert "share_code_value" not in serialized and "share_code_url" not in serialized


def test_governance_and_supersession_are_frozen():
    data = load_baseline()
    gov = data["governance"]
    assert gov["source_review_counter"] == "0/5"
    assert gov["mandatory_5_of_5_reread_completed"] is True
    assert gov["p4_4"] == gov["architecture_checkpoint_e"] == "INCOMPLETE"
    assert gov["clean_canonical_shadow_successor_proof"] == "INCOMPLETE"
    assert gov["next_live_proof"] == gov["caller_migration"] == gov["workflow_retirement"] == "NOT_AUTHORIZED"
    assert data["next_mission"] == "AUTH-01A"
    assert data["next_mission_status"] == "NOT_STARTED_NOT_AUTHORIZED_BY_BASE_00"
    assert next(x for x in data["superseded_plans"] if x["plan_id"] == "PLAN-P4_4T-STANDALONE")["status"] == "SUPERSEDED_BY_AUTH_01_SERIES"


def test_markdown_and_json_agree_on_critical_identity_and_governance():
    data = load_baseline()
    markdown = MARKDOWN_PATH.read_text(encoding="utf-8")
    for exact in (data["baseline_id"], data["policy_id"], data["baseline_source_commit_sha"], data["baseline_source_tree_sha"], "SOURCE_REVIEW_COUNTER", "AUTH-01A", "INCOMPLETE", "SUPERSEDED_BY_AUTH_01_SERIES"):
        assert exact in markdown
    assert "This is not clean successor proof" in markdown
    assert "not authorized by BASE-00" in markdown


def test_audit_runs_with_network_denied(monkeypatch, capsys):
    def denied(*args, **kwargs):
        raise AssertionError("network attempted during BASE-00 audit")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    assert audit.main([]) == 0
    output = capsys.readouterr().out
    assert '"network": "NOT_USED"' in output


def test_audit_module_does_not_import_runtime_or_provider_modules():
    tree = ast.parse((ROOT / "scripts/audit_product_baseline_v1.py").read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden_prefixes = ("api", "domain", "services", "workers")
    assert not any(name == prefix or name.startswith(prefix + ".") for name in imports for prefix in forbidden_prefixes)


def test_snapshot_audit_is_future_safe_when_runtime_source_is_not_present(tmp_path):
    data = load_baseline()
    assert audit.validate_baseline(data, tmp_path, verify_receipts=False) == []
    result, details = audit.exact_head_reproduction(data, tmp_path)
    assert result == "SKIP_SOURCE_MOVED"
    assert details


def test_exact_head_reproduction_passes_on_frozen_checkout():
    data = load_baseline()
    assert all(item["hash_kind"] == "LF_NORMALIZED_SOURCE_SHA256" for item in data["source_snapshot"]["files"])
    assert audit.exact_head_reproduction(data, ROOT) == ("PASS", [])


def test_pr_review_binding_records_creation_identity_without_rewriting_source_base(tmp_path):
    json_path = tmp_path / audit.BASELINE_JSON
    json_path.parent.mkdir(parents=True)
    (tmp_path / audit.BASELINE_MARKDOWN).parent.mkdir(parents=True)
    unbound = load_baseline()
    unbound["implementation_review"] = {"pull_request_number": None, "head_sha_at_pr_creation": None, "state_at_capture": "NOT_CREATED_AT_BASELINE_FREEZE"}
    json_path.write_text(json.dumps(reseal(unbound), sort_keys=True, indent=2)+"\n", encoding="utf-8")
    bound = audit.bind_review(tmp_path, 413, "a" * 40)
    assert bound["baseline_source_commit_sha"] == "eae938a268707f07db3da2d551ea589782902b1c"
    assert bound["baseline_source_tree_sha"] == "c00e98b0a4b2d5c5f211e6c4f929a08b8e79639b"
    assert bound["implementation_review"] == {
        "pull_request_number": 413,
        "head_sha_at_pr_creation": "a" * 40,
        "state_at_capture": "OPEN_UNMERGED_AT_REVIEW_BIND",
    }
    assert audit.validate_baseline(bound, tmp_path, verify_receipts=False) == []
    assert "PR head when first opened" in (tmp_path / audit.BASELINE_MARKDOWN).read_text(encoding="utf-8")


def test_historical_run_is_not_misclassified_as_clean_or_migration_authority():
    data = load_baseline()
    run = data["latest_live_evidence"]
    assert "AUTHORIZATION_NONCOMPLIANT_SHARE_CODE_SIDE_EFFECT" in run["classification"]
    assert "not clean successor" in run["interpretation"].lower()
    assert data["governance"]["caller_migration"] == "NOT_AUTHORIZED"
    assert data["governance"]["workflow_retirement"] == "NOT_AUTHORIZED"


def test_required_source_documents_are_classed_without_inventing_repo_paths():
    data = load_baseline()
    docs = {d["source_document_id"]: d for d in data["source_documents"]}
    assert docs["SRC-ARCH-REMEDIATION-MASTER-V2"]["identity_class"] == "OWNER_SUPPLIED_HASH_REPORTED"
    assert docs["SRC-SIX-DOCUMENT-BLUEPRINT"]["identity_class"] == "OWNER_SUPPLIED_HASH_REPORTED"
    assert docs["SRC-PRODUCT-IMPLEMENTATION-MASTER-V1"]["identity_class"] == "OWNER_SUPPLIED_HASH_REPORTED"
    assert all(d["repository_file"] is None for d in docs.values())
    assert all(re.fullmatch(r"[0-9a-f]{64}", d["sha256"]) for d in docs.values())


def test_entrypoint_inventory_count_by_classification_is_deterministic():
    data = load_baseline()
    counts = Counter(e["current_classification"] for e in data["entrypoints"])
    assert sum(counts.values()) == 107
    assert counts == Counter({"RETAINED_COMPATIBILITY": 46, "DIAGNOSTIC_RESEARCH_ONLY": 46, "CANONICAL_SUPPORTED": 8, "UNKNOWN": 7})
