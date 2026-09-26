#!/usr/bin/env python3
"""Offline, fail-closed audit for the P4.4N team-label shape contract."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from domain import current_shadow_all_market_runner as runner
from domain import current_shadow_fixture_identity_compatibility as identity_compatibility
from domain import current_shadow_fixture_identity_v2 as identity_v2
from domain import current_shadow_sportybet_international_provider_family_bridge as bridge
from domain import current_shadow_sportybet_pc_upcoming_discovery as source
from domain import current_shadow_sportybet_pc_upcoming_reconciliation as runtime
from domain import current_shadow_sportybet_team_label_compatibility as team_labels
from domain import current_shadow_sportybet_upcoming_reconciliation as wap
from domain import current_shadow_sportybet_paginated_discovery_reconciliation as paginated
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout
from domain.fotmob_data_matches_capture import FotMobDataMatchesCaptureManifest
from scripts import verify_p3_0_e1_live_readiness as p3


RECEIPT_PATH = Path("artifacts/architecture/p4_4n_sportybet_team_label_shape_compatibility_v1.json")
P44M_RECEIPT_PATH = Path("artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json")
P44M_WORKFLOW_PATH = Path(".github/workflows/athena-run.yml")
POLICY_ID = "ATHENA_P4_4N_SPORTYBET_TEAM_LABEL_SHAPE_COMPATIBILITY_V1"
BASE_MAIN_SHA = "85f3ddca3142b93f1719bc32f72a44587e59c578"
OLD_VALUES = {
    "team_label": "6ec1d805263cddb7d4a4cf8338a611a7b66b22dd12db665db1614b3baa799f14",
    "identity_compatibility": "dbef6539dd7c5d1c1589debe8daca9378ea2e0c0bb32acf3315a0d1a005c2b58",
    "runtime_wrapper": "e44d8b3476118a094d3e59f885f7456c3aebc677c07d8eeefaa232df5bc6a43e",
    "wap_compatibility": "e0718a5e7c9e0c707ba5cc7369910f3ec371bd1a9f7520ab41aa30df69d0ab12",
    "paginated": "6de2847f8ed32873f7ae50e902708c7e27ca5516f492e183063f3dfc0f1635a8",
    "fanout": "2d8c1f7b533eea104c1951a9a1f963c4cd85933252aa44da7dbeb447528ad0a0",
    "source": "63799058bec00abefb8d9b2ec9ba6dcad0c6e4775a54f17b07c0018e543ec075",
    "bridge": "7db676111a9be06f63fd207815837d53699d6bf1a98364fc2163046cd1c0a4bb",
    "v2": "fc64fb0c2df3cee4f425158c48cfaada6757ba01e1759dd5b976ca899f85421e",
    "v2_seed": "7fe662fc91a80daabf1e774ddd5c8ecdb5215eaf63adb03822b3fb05f872df79",
    "wap_source": "90c14bd68ed6e8205c16fedfa815d120c53f2af1a3a8f362eee2702a4223b9ff",
}
NEW_VALUES = {
    "team_label": "0c382ec8b12d802879a51b766daae8f655dd5b371509653e56a13190a85c6c7b",
    "identity_compatibility": "2fdbb8165262f6e633ee48276aea57c9235699272235798e1cef12fdc714ae04",
    "runtime_wrapper": "fd203fc4b857bb3c5faa22536e87e1bc214cd4fdcf79ec5b6c4c681cd9d0cf73",
    "wap_compatibility": "dd1b4366ef2cf4d1e12359c42fbff5cbae8bef60cc06ca40589ec0e8a157f943",
    "paginated": "7373a05c25466206aa3a67bc53b219e8d2841f432fda13db2dc0808b40b47238",
    "fanout": "c1ce52d8c441a6a38aee08c05413d579f0f18a497e56eb7833faf1fbc60c622f",
}
HISTORICAL_RECEIPTS = {
    "artifacts/architecture/post_p4_4l_international_provider_family_bridge_v1.json": (
        "8e4c9af2993d7a0a3698176f17b4f73e99177003139d45f7e98d40dfa80fa495",
        "34c183b5274e9e2c3320b5a8d75a123b7ebed2405aa55cdfb1af7d59c2613aa2",
    ),
    "artifacts/architecture/post_p4_4l_pc_upcoming_runtime_migration_v1.json": (
        "1e4e302cff57719beca3db3402cc19526bae7bc056515c0b399473855ed14f30",
        "09bbbb0842b0f92c214d5e868ec3fe5e2d047f9de7b5c3e6d620bc147092f6f3",
    ),
    "artifacts/architecture/p4_4m_athena_run_pc_upcoming_evidence_preservation_v1.json": (
        "88c7c1423b81251515da0ca145fbbfd26040df4966da10b5a5d322aaf44aacb3",
        "8202845b28abcea6ff8ea0ffb279a924b09ca7b2e5ab1d1918c957b757f345cf",
    ),
}


class P44NError(AssertionError):
    """Raised when P4.4N lineage or bounded projection semantics drift."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise P44NError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise P44NError(f"required P4.4N evidence is unavailable: {path}") from exc
    _require(type(value) is dict, f"receipt must be an object: {path}")
    return value


def _receipt(root: Path) -> dict[str, Any]:
    value = _read_json(root / RECEIPT_PATH)
    embedded = value.get("canonical_sha256")
    semantic = dict(value)
    semantic.pop("canonical_sha256", None)
    actual = hashlib.sha256(_canonical(semantic)).hexdigest()
    _require(type(embedded) is str and embedded == actual, "P4.4N receipt canonical SHA mismatch")
    _require(value.get("schema_version") == 1 and value.get("policy_id") == POLICY_ID, "P4.4N receipt schema or policy identity drifted")
    _require(value.get("repository") == "Thabearr/ATHENA" and value.get("base_main_sha") == BASE_MAIN_SHA, "P4.4N base/repository identity drifted")
    _require(value.get("source_review_counter_while_unmerged") == "4/5" and value.get("source_review_counter_if_merged") == "5/5" and value.get("mandatory_source_reread_after_merge") is True, "source-review hard-stop lineage drifted")
    _require(value.get("failed_successor_proof_run") == 36229731847 and value.get("failed_successor_proof_artifact") == 10901662346, "failed successor proof evidence identity drifted")
    _require(value.get("run_evidence_comment_id") == 5844630119 and value.get("offline_diagnosis_comment_id") == 5844716336 and value.get("p4_4m_merge_comment_id") == 5845591665 and value.get("p4_4n_boundary_comment_id") == 5845627259, "issue evidence ancestry drifted")
    _require(value.get("shape_evidence_source") == "PRIOR_RETAINED_V5_EVIDENCE_ONLY" and value.get("failed_run_exact_raw_shape_known") is False, "failed run was incorrectly promoted to shape evidence")
    _require(value.get("historical_evidence_examples") == 6 and value.get("historical_evidence_captures") == 5 and value.get("historical_distinct_raw_labels") == 3, "historical evidence count drifted")
    _require(value.get("admitted_shape") == "EXACTLY_ONE_TRAILING_ASCII_U_0020_ONLY", "admitted shape broadened")
    for key in ("generic_strip", "leading_whitespace", "multiple_trailing_spaces", "non_ascii_boundary_whitespace", "control_whitespace"):
        _require(value.get(key) is False, f"unsafe normalization authority enabled: {key}")
    _require(value.get("provider_acquisition") == 0 and value.get("workflow_dispatch") == 0 and value.get("live_retry") == 0 and value.get("share_code_actions") == 0 and value.get("wager_actions") == 0, "P4.4N implementation is not offline")
    _require(value.get("account_wager_authority_changed") is False and value.get("successor_proof_complete") is False and value.get("next_live_proof_authorized") is False and value.get("p4_4_complete") is False and value.get("architecture_checkpoint_e_complete") is False, "P4.4N receipt overclaims authority or completion")
    return value


def _verify_pins(receipt: dict[str, Any]) -> None:
    team = receipt["team_label_policy"]
    _require(team == {
        "before": {"schema_version": 5, "policy_id": "ATHENA_CURRENT_SHADOW_EXACT_PROVIDER_TRAILING_SPACE_LABEL_COMPATIBILITY_V5", "sha256": OLD_VALUES["team_label"]},
        "after": {"schema_version": 6, "policy_id": "ATHENA_CURRENT_SHADOW_EXACT_ONE_TRAILING_ASCII_SPACE_LABEL_COMPATIBILITY_V6", "sha256": NEW_VALUES["team_label"]},
    }, "team-label policy lineage drifted")
    pairs = (
        ("identity_compatibility_sha256_before", "identity_compatibility_sha256_after", "identity_compatibility"),
        ("retained_wap_compatibility_sha256_before", "retained_wap_compatibility_sha256_after", "wap_compatibility"),
        ("retained_paginated_contract_sha256_before", "retained_paginated_contract_sha256_after", "paginated"),
        ("retained_fanout_contract_sha256_before", "retained_fanout_contract_sha256_after", "fanout"),
    )
    for before_key, after_key, name in pairs:
        _require(receipt.get(before_key) == OLD_VALUES[name] and receipt.get(after_key) == NEW_VALUES[name], f"{name} before/after lineage drifted")
    runtime_row = receipt.get("runtime_wrapper")
    _require(runtime_row == {"policy_id": "ATHENA_CURRENT_SHADOW_PC_UPCOMING_DISCOVERY_RECONCILIATION_V1", "sha256_before": OLD_VALUES["runtime_wrapper"], "sha256_after": NEW_VALUES["runtime_wrapper"]}, "runtime wrapper lineage drifted")
    for name, before_key, after_key in (
        ("source", "pc_upcoming_source_sha256_before", "pc_upcoming_source_sha256_after"),
        ("bridge", "international_bridge_sha256_before", "international_bridge_sha256_after"),
        ("v2", "v2_semantic_registry_sha256_before", "v2_semantic_registry_sha256_after"),
        ("v2_seed", "v2_seed_registry_sha256_before", "v2_seed_registry_sha256_after"),
    ):
        _require(receipt.get(before_key) == OLD_VALUES[name] and receipt.get(after_key) == OLD_VALUES[name], f"unchanged {name} identity drifted")
    _require(receipt.get("retained_wap_upstream_source_contract_sha256_before") == OLD_VALUES["wap_source"] == receipt.get("retained_wap_upstream_source_contract_sha256_after"), "retained WAP upstream source contract changed")

    _require(team_labels.SCHEMA_VERSION == 6 and team_labels.POLICY_ID == team["after"]["policy_id"] and team_labels.EXPECTED_POLICY_SHA256 == NEW_VALUES["team_label"] == team_labels.policy_sha256(), "current V6 team-label policy differs from receipt")
    _require(identity_compatibility.POLICY_ID == "ATHENA_CURRENT_SHADOW_FIXTURE_IDENTITY_COMPATIBILITY_V1" and identity_compatibility.EXPECTED_POLICY_SHA256 == NEW_VALUES["identity_compatibility"] == identity_compatibility.calculate_policy_sha256(), "identity compatibility does not bind V6")
    compatibility_payload = identity_compatibility._policy_payload()
    _require(compatibility_payload.get("team_label_policy_id") == team_labels.POLICY_ID and compatibility_payload.get("team_label_policy_sha256") == NEW_VALUES["team_label"], "identity compatibility ancestry is stale")
    _require(runtime.POLICY_ID == runtime_row["policy_id"] and runtime.PINNED_POLICY_SHA256 == NEW_VALUES["runtime_wrapper"] == runtime.calculate_policy_sha256(), "runtime wrapper does not bind new identity compatibility")
    _require(runtime.IDENTITY_COMPATIBILITY_SHA256 == NEW_VALUES["identity_compatibility"], "runtime identity compatibility pin is stale")
    _require(source.PINNED_POLICY_SHA256 == OLD_VALUES["source"] == source.calculate_policy_sha256(), "pcUpcoming source policy changed")
    _require(bridge.PINNED_POLICY_SHA256 == OLD_VALUES["bridge"] == bridge.calculate_policy_sha256(), "international bridge policy changed")
    _require(identity_v2.REGISTRY_SHA256 == OLD_VALUES["v2"] == identity_v2.registry_sha256() and identity_v2.SEED_REGISTRY_SHA256 == OLD_VALUES["v2_seed"] == identity_v2.seed_registry_sha256() and identity_v2.STATE_SCHEMA_VERSION == 2, "V2 identity registry or state changed")
    _require(wap.UPSTREAM_UPCOMING_SOURCE_CONTRACT_SHA256 == OLD_VALUES["wap_source"] and wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256 == NEW_VALUES["wap_compatibility"] == wap.calculate_current_shadow_upcoming_compatibility_sha256(), "retained WAP current contract lineage drifted")
    _require(wap.CURRENT_SHADOW_UPCOMING_POLICY_ID == "ATHENA_CURRENT_SHADOW_UPCOMING_DISCOVERY_V1", "retained WAP source identity was rewritten")
    _require(paginated.EXPECTED_CONTRACT_SHA256 == NEW_VALUES["paginated"] == paginated.calculate_contract_sha256(), "retained paginated current contract lineage drifted")
    _require(fanout.EXPECTED_CONTRACT_SHA256 == NEW_VALUES["fanout"] == fanout.calculate_contract_sha256(), "retained fanout current contract lineage drifted")
    _require(runner.reconciliation is runtime and runner.upcoming_discovery is runtime, "Current Shadow runtime owner changed")
    p3_current = p3.check_f_upcoming_discovery_contract()
    _require(p3_current.get("runtime_policy_id") == runtime.POLICY_ID and p3_current.get("runtime_policy_sha256") == NEW_VALUES["runtime_wrapper"], "P3 source owner or runtime pins changed")
    _require(receipt.get("runtime_source_owner") == {"before": runtime.POLICY_ID, "after": runtime.POLICY_ID, "changed": False} and receipt.get("p3_source_owner") == {"before": runtime.POLICY_ID, "after": runtime.POLICY_ID, "changed": False}, "source owner continuity drifted")


def _verify_history_and_workflow(root: Path, receipt: dict[str, Any]) -> None:
    history = receipt.get("historical_receipts")
    _require(type(history) is dict and set(history) == set(HISTORICAL_RECEIPTS), "historical receipt inventory drifted")
    for relative, (raw_sha, canonical_sha) in HISTORICAL_RECEIPTS.items():
        path = root / relative
        try:
            # Git stores the immutable receipt with LF newlines. Windows
            # checkouts may expand those to CRLF, so normalize only line
            # endings before comparing the pinned repository-byte SHA.
            raw = path.read_bytes().replace(b"\r\n", b"\n")
            parsed = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise P44NError(f"immutable historical receipt is unavailable: {relative}") from exc
        _require(hashlib.sha256(raw).hexdigest() == raw_sha and history[relative] == {"raw_sha256": raw_sha, "canonical_sha256": canonical_sha}, f"historical receipt bytes changed: {relative}")
        _require(parsed.get("canonical_sha256") == canonical_sha, f"historical receipt canonical identity changed: {relative}")
        if relative.endswith("post_p4_4l_pc_upcoming_runtime_migration_v1.json"):
            _require(parsed.get("paginated_runtime_authority") is False and parsed.get("fanout_runtime_authority") is False, "historical non-runtime-source authority record drifted")
    p44m = _read_json(root / P44M_RECEIPT_PATH)
    workflow_identity = p44m.get("workflow_after_identity", {})
    workflow_path = root / P44M_WORKFLOW_PATH
    try:
        workflow_sha = hashlib.sha256(workflow_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError as exc:
        raise P44NError("P4.4M workflow is unavailable") from exc
    _require(workflow_sha == receipt.get("p4_4m_workflow_sha256_unchanged") == workflow_identity.get("source_sha256"), "P4.4M workflow bytes changed")
    _require(receipt.get("workflow_count") == 38 and receipt.get("workflow_retirement_count") == 3, "workflow/retirement census changed")
    from scripts import audit_p4_workflow_evolution_ledger as evolution
    from scripts import audit_p4_3_workflow_retirement_ledger as retirement
    live_state = evolution.validate_current_state()
    retired_state = retirement.validate_retirement_history()
    _require(live_state.get("current_live_workflow_count") == 38 and retired_state.get("current_retired_workflow_count") == 3, "workflow evolution/retirement census drifted")


def _verify_shape() -> None:
    _require(len(team_labels.REVIEWED_PROJECTIONS) == 6, "historical evidence rows changed")
    rows = [asdict(row) for row in team_labels.REVIEWED_PROJECTIONS]
    row_sha = hashlib.sha256(_canonical(rows)).hexdigest()
    _require(row_sha == "03d97a88d1e7ecf2f2b79ecb02728c79df2154046656c84896c58f62ae871fbd", "historical evidence row values or ancestry changed")
    _require(len({row["evidence_workflow_run_id"] for row in rows}) == 5, "historical evidence capture count changed")
    _require(len({row["raw_source_label"] for row in rows}) == 3, "historical distinct raw-label count changed")
    for row in rows:
        _require(team_labels.project_team_label(event_id=row["event_id"], field=row["field"], value=row["raw_source_label"]) == row["projected_label"], "retained historical projection no longer passes")
    _require(team_labels.project_team_label(event_id="sr:match:99999999991", field="homeTeamName", value="Example Athletic ") == "Example Athletic", "novel event one-space shape was rejected")
    _require(team_labels.project_team_label(event_id="sr:match:99999999991", field="awayTeamName", value="Example Athletic") == "Example Athletic", "already-trimmed novel event label changed")
    invalid = (
        " Team", "Team  ", "Team   ", "Team\t", "Team\n", "Team\r",
        "Team\u00a0", "Team\u2009", "Team\u3000", "\u00a0Team",
        "Team\u00a0 ", " Team ", " ", "", "Team\x01", "Team\x7f",
    )
    for value in invalid:
        try:
            team_labels.project_team_label(event_id="sr:match:99999999991", field="homeTeamName", value=value)
        except team_labels.CurrentShadowSportyBetTeamLabelCompatibilityError:
            continue
        raise P44NError(f"unsupported whitespace input was accepted: {value!r}")
    for field, value in (("teamName", "Team"), ("homeTeamName", None), ("awayTeamName", 4), ("homeTeamName", "x" * 301)):
        try:
            team_labels.project_team_label(event_id="sr:match:99999999991", field=field, value=value)
        except team_labels.CurrentShadowSportyBetTeamLabelCompatibilityError:
            continue
        raise P44NError("invalid field/source bounds were accepted")
    policy = team_labels.policy_payload()["rules"]
    _require(policy.get("event_bound_allowlist_required") is False and policy.get("raw_source_bytes_remain_authoritative") is True and policy.get("raw_source_sha_ancestry_required") is True, "event allowlist or raw evidence ancestry semantics drifted")
    _require(all(value is False for key, value in policy.items() if key.endswith("authority") or key in {"generic_strip", "leading_whitespace", "multiple_trailing_spaces", "trailing_non_ascii_whitespace", "tabs_or_control_whitespace"}), "team-label policy granted unrelated authority")
    _require(team_labels.AUTHORITY["source_schema_compatibility"] is True and all(value is False for key, value in team_labels.AUTHORITY.items() if key != "source_schema_compatibility"), "team-label authority broadened")


def audit(repository_root: str | Path = ".") -> dict[str, Any]:
    root = Path(repository_root)
    receipt = _receipt(root)
    _verify_pins(receipt)
    _verify_history_and_workflow(root, receipt)
    _verify_shape()
    doc = (root / "docs/current_shadow_sportybet_reviewed_trailing_space_labels.md").read_text(encoding="utf-8")
    section = doc.split("## P4.4N", 1)[-1]
    for phrase in ("exact new raw label is unknown", "not evidence that its label had one trailing ASCII space", "Generic trimming remains forbidden", "No provider acquisition, retry, or live workflow"):
        _require(phrase in section, "P4.4N chronology/limitation documentation is incomplete")
    return {
        "status": "PASSED",
        "policy_id": POLICY_ID,
        "receipt_sha256": receipt["canonical_sha256"],
        "team_label_policy_sha256": team_labels.EXPECTED_POLICY_SHA256,
        "identity_compatibility_sha256": identity_compatibility.EXPECTED_POLICY_SHA256,
        "runtime_wrapper_sha256": runtime.PINNED_POLICY_SHA256,
        "retained_wap_compatibility_sha256": wap.CURRENT_SHADOW_UPCOMING_COMPATIBILITY_SHA256,
        "historical_evidence_examples": 6,
        "historical_evidence_captures": 5,
        "admitted_shape": "EXACTLY_ONE_TRAILING_ASCII_U_0020_ONLY",
        "provider_acquisition": 0,
        "workflow_dispatch": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
