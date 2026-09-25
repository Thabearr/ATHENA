"""Fail-closed offline audit for the P4.4L international identity bridge."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
from typing import Any

from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from domain import current_shadow_fotmob_international_source_identity as identity
from config.competition_review_priority import (
    CompetitionScope,
    INTERNATIONAL_COMPETITION_REVIEW_PRIORITY,
)


BASE_MAIN = "b17e97dbea043d45d47db9ad2011354fe4682baf"
POLICY_ID = identity.POLICY_ID
RECEIPT_PATH = Path(
    "artifacts/architecture/p4_4l_current_shadow_international_source_hierarchy_v1.json"
)
EXPECTED_CHANGED_PATHS = {
    "artifacts/architecture/p4_4l_current_shadow_international_source_hierarchy_v1.json",
    "domain/current_fotmob_fixture_review_policy.py",
    "domain/current_shadow_fotmob_international_source_identity.py",
    "scripts/audit_p4_4l_current_shadow_international_source_hierarchy.py",
    "tests/test_current_fotmob_fixture_review_policy.py",
    "tests/test_current_shadow_fotmob_international_source_identity.py",
    "tests/test_p4_4l_current_shadow_international_source_hierarchy.py",
}
EXPECTED_ACTIVE_KEYS = {
    ("INT", 9806),
    ("INT", 9807),
    ("INT", 9808),
    ("INT", 9821),
    ("INT", 10608),
    ("INT", 114),
    ("INT", 10437),
    ("INT", 9833),
}
EXPECTED_UNQUALIFIED_KEYS = {("INT", 13287)}
WORKFLOW_TREE_SHA1 = "d58f71b9ac653c8762f1d9b18eede15755ee1a76"
WORKFLOW_COUNT = 38
EVOLUTION_SHA256 = "b9ee60aa5cfa63080159cae839ca82b5662fdfbfe70a91055392a1728ed05f7a"
EVOLUTION_TRANSITION_COUNT = 6
RETIREMENT_SHA256 = "afa4a082f5225d83ca1ab32aab396b02bedf6f43dc57b6467a4187a720a0d56a"
RETIREMENT_COUNT = 3
P44H_RECEIPT_SHA256 = "0000a5978268909dd07330d59079bc4d7f8d32c0fee161653a4a19eea9b97c64"
P44I_RECEIPT_SHA256 = "d6f65a382c4ef23318a81261e48b8e717f768864a6e1e5baed61af3c11351a7c"
P44J_RECEIPT_SHA256 = "335a22e5c73a397d5f3b24605d16a7b9f1220ce831fc378cedd17f4dd1a7ef49"
PRIMARY_ID_QUALIFICATION_PATH = (
    "artifacts/research-manifests/"
    "fotmob-primary-id-competition-mapping-qualification-v1.json"
)


class P44LReviewError(AssertionError):
    """P4.4L policy, evidence receipt, or live ancestry failed validation."""


def _git(*args: str) -> bytes:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise P44LReviewError(
            f"git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return _sha256(canonical_json_bytes(body))


def _source_identity(path: str) -> dict[str, str]:
    # Hash the committed blob bytes rather than checkout bytes: Windows may
    # materialize CRLF while hosted Linux checkouts use LF for the same blob.
    raw = _git("show", f"HEAD:{path}")
    blob = _git("rev-parse", f"HEAD:{path}").decode("ascii").strip()
    return {"git_blob_sha1": blob, "source_sha256": _sha256(raw)}


def _current_architecture_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    # Hosted pull_request checkouts are intentionally shallow and may not have
    # BASE_MAIN's commit object.  The current checked-out merge/head tree is
    # available and must still equal the frozen reviewed workflow identity.
    workflows_tree = _git("rev-parse", "HEAD:.github/workflows").decode(
        "ascii"
    ).strip()
    workflow_paths = _git(
        "ls-tree", "-r", "--name-only", "HEAD", ".github/workflows"
    ).decode("utf-8").splitlines()
    evolution = json.loads(
        (root / "artifacts/architecture/p4_workflow_evolution_ledger_v1.json").read_text(
            encoding="utf-8"
        )
    )
    retirement = json.loads(
        (root / "artifacts/architecture/p4_3_workflow_retirement_ledger_v1.json").read_text(
            encoding="utf-8"
        )
    )
    prior_receipts = {}
    for label, path in (
        ("p4_4h", "artifacts/architecture/p4_4h_current_shadow_canonical_run_migration_review_v1.json"),
        ("p4_4i", "artifacts/architecture/p4_4i_shadow_supervisor_failure_evidence_v1.json"),
        ("p4_4j", "artifacts/architecture/p4_4j_shadow_selected_source_issuer_network_control_v1.json"),
    ):
        value = json.loads((root / path).read_text(encoding="utf-8"))
        prior_receipts[label] = value.get("canonical_sha256")
    return {
        "workflow_tree_sha1": workflows_tree,
        "workflow_count": len(workflow_paths),
        "workflow_evolution_ledger_sha256": evolution.get("canonical_sha256"),
        "workflow_evolution_transition_count": len(evolution.get("transitions", [])),
        "p4_3_retirement_ledger_sha256": retirement.get("canonical_sha256"),
        "p4_3_retirement_count": len(retirement.get("retirements", [])),
        "prior_p4_4_receipts": prior_receipts,
    }


def _tracked_capture_file_count() -> int:
    paths = _git("ls-files", "artifacts").decode("utf-8").splitlines()
    return sum(
        path.replace("\\", "/").rsplit("/", 1)[-1] in {"response.json", "manifest.json"}
        for path in paths
    )


def _validate_policy() -> None:
    if identity.international_source_identity_policy_sha256() != identity.PINNED_POLICY_SHA256:
        raise P44LReviewError("international identity policy SHA-256 drift")
    hierarchy_entries = tuple(INTERNATIONAL_COMPETITION_REVIEW_PRIORITY)
    coverage = identity.international_hierarchy_coverage_table()
    expected_hierarchy = {
        (entry.canonical_name, entry.priority_band, entry.rank, entry.kind, entry.scope)
        for entry in hierarchy_entries
    }
    actual_hierarchy = {
        (row.canonical_name, row.priority_band, row.priority_rank, row.competition_kind, row.scope)
        for row in coverage
    }
    if (
        len(coverage) != len(hierarchy_entries)
        or len(expected_hierarchy) != len(hierarchy_entries)
        or actual_hierarchy != expected_hierarchy
        or any(row.scope is not CompetitionScope.INTERNATIONAL for row in coverage)
        or {row.priority_band for row in coverage}
        != {"INT-S", "INT-A", "INT-B", "INT-C", "INT-D", "INT-E", "INT-F", "INT-G"}
    ):
        raise P44LReviewError("full canonical INT-S..INT-G hierarchy coverage drift")
    active = {
        (item.source_competition_ccode, item.source_competition_primary_id)
        for item in identity.REVIEWED_CURRENT_SOURCE_IDENTITIES
    }
    if active != EXPECTED_ACTIVE_KEYS or len(active) != len(identity.REVIEWED_CURRENT_SOURCE_IDENTITIES):
        raise P44LReviewError("active exact international source identity set drift")
    observed = {item.key for item in identity.OBSERVED_UNQUALIFIED_SOURCE_IDENTITIES}
    if observed != EXPECTED_UNQUALIFIED_KEYS:
        raise P44LReviewError("observed-but-unqualified identity set drift")
    payload = identity.international_source_identity_policy_payload()
    authority = payload.get("authority")
    if not isinstance(authority, dict) or any(
        type(value) is not bool or value is not False for value in authority.values()
    ):
        raise P44LReviewError("international identity policy authority expanded")
    for key in active | observed:
        if type(key[0]) is not str or key[0] != "INT" or type(key[1]) is not int:
            raise P44LReviewError("international mapping key is malformed")
    for item in identity.REVIEWED_CURRENT_SOURCE_IDENTITIES:
        entry = identity.resolve_current_shadow_international_source_priority(
            source_competition_ccode=item.source_competition_ccode,
            source_competition_primary_id=item.source_competition_primary_id,
        )
        if (
            entry is None
            or entry.scope is not CompetitionScope.INTERNATIONAL
            or entry.canonical_name != item.canonical_name
            or entry.priority_band != item.priority_band
            or entry.rank != item.priority_rank
            or entry.kind is not item.competition_kind
        ):
            raise P44LReviewError("active provider key maps outside its exact hierarchy target")
    for ccode, primary_id in active | observed:
        if identity.resolve_current_shadow_international_source_priority(
            source_competition_ccode="NGA",
            source_competition_primary_id=primary_id,
        ) is not None:
            raise P44LReviewError("wrong ccode resolves to an international hierarchy entry")
        if ccode != "INT" and identity.resolve_current_shadow_international_source_priority(
            source_competition_ccode=ccode,
            source_competition_primary_id=primary_id,
        ) is not None:
            raise P44LReviewError("wrong ccode resolves to an international hierarchy entry")
    if identity.resolve_current_shadow_international_source_priority(
        source_competition_ccode="INT", source_competition_primary_id=True
    ) is not None:
        raise P44LReviewError("boolean primaryId was accepted as an integer identity")
    resolver_parameters = tuple(
        inspect.signature(
            identity.resolve_current_shadow_international_source_priority
        ).parameters
    )
    if resolver_parameters != (
        "source_competition_ccode",
        "source_competition_primary_id",
    ):
        raise P44LReviewError("international resolver accepts identity-unsafe arguments")
    identity_source = inspect.getsource(identity)
    if any(token in identity_source for token in ("normalize_league_name", "league_id=")):
        raise P44LReviewError("display names or wrapper IDs became resolver authority")
    root = Path(__file__).resolve().parents[1]
    policy_source = (root / "domain/current_fotmob_fixture_review_policy.py").read_text(
        encoding="utf-8"
    )
    required_shadow_guard = "priority is None and policy_id == SHADOW_POLICY_ID"
    if (
        required_shadow_guard not in policy_source
        or "resolve_current_shadow_international_source_priority(" not in policy_source
        or "reviewed_current_fotmob_international_source_identity(" not in policy_source
    ):
        raise P44LReviewError("Shadow-only fallback or current exact source path drifted")
    tests_source = (root / "tests/test_current_fotmob_fixture_review_policy.py").read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_shadow_mixed_club_and_international_card_admits_each_through_own_path",
        "test_pure_club_source_resolution_retains_existing_reviewed_note_semantics",
        "test_production_builder_never_invokes_shadow_international_resolver",
        "test_known_looking_international_label_without_qualified_primary_id_stays_unreviewed",
    ):
        if f"def {test_name}(" not in tests_source:
            raise P44LReviewError("required mixed/pure-scope or production-isolation regression missing")


def expected_receipt() -> dict[str, Any]:
    _validate_policy()
    root = Path(__file__).resolve().parents[1]
    qualifier = json.loads((root / PRIMARY_ID_QUALIFICATION_PATH).read_text(encoding="utf-8"))
    qualifier_records = qualifier.get("records", [])
    if (
        len(qualifier_records) != 11
        or any(item.get("competition_class") != "DOMESTIC_LEAGUE" for item in qualifier_records)
        or any("INT" in item.get("observed_country_codes", []) for item in qualifier_records)
    ):
        raise P44LReviewError("historical primary-ID qualification inventory changed")
    policy_payload = identity.international_source_identity_policy_payload()
    tracked_capture_count = _tracked_capture_file_count()
    if tracked_capture_count != 0:
        raise P44LReviewError("raw provider capture files must not be committed")
    value: dict[str, Any] = {
        "schema_version": 1,
        "policy_id": "ATHENA_P4_4L_CURRENT_SHADOW_INTERNATIONAL_SOURCE_HIERARCHY_V1",
        "repository_base_main_sha": BASE_MAIN,
        "policy": {
            "policy_id": identity.POLICY_ID,
            "policy_sha256": identity.international_source_identity_policy_sha256(),
            "identity_semantics": policy_payload["identity_semantics"],
            "coverage": policy_payload["coverage"],
            "observed_unqualified_identities": policy_payload[
                "observed_unqualified_identities"
            ],
        },
        "evidence_inventory": {
            "p4_4k_capture": policy_payload["p4_4k_evidence"],
            "checked_in_primary_id_qualification": {
                "path": PRIMARY_ID_QUALIFICATION_PATH,
                "file_sha256": _sha256(
                    _git("show", f"HEAD:{PRIMARY_ID_QUALIFICATION_PATH}")
                ),
                "qualified_record_count": len(qualifier_records),
                "record_competition_classes": sorted(
                    {item.get("competition_class") for item in qualifier_records}
                ),
                "international_source_identity_count": 0,
                "referenced_actions_artifact_id": qualifier.get("source_evidence", {}).get(
                    "artifact_id"
                ),
                "referenced_actions_artifact_sha256": qualifier.get(
                    "source_evidence", {}
                ).get("artifact_sha256"),
            },
            "checked_in_raw_current_capture_count": tracked_capture_count,
            "other_int_source_class_claims_added": False,
        },
        "p4_4k_offline_replay": {
            "artifact_zip_sha256_verified": identity.P4_4K_ARTIFACT_SHA256,
            "capture_manifest_sha256_verified": identity.P4_4K_CAPTURE_MANIFEST_SHA256,
            "capture_raw_sha256_verified": identity.P4_4K_CAPTURE_RAW_SHA256,
            "network_acquisition_performed_in_prior_capture": True,
            "request_date": identity.P4_4K_REQUEST_DATE,
            "source_timezone": "UTC",
            "policy_evaluated_at": "2026-09-25T12:47:40.976783Z",
            "total_candidate_count": 102,
            "total_international_candidate_count": 44,
            "active_mapped_international_candidate_count": 42,
            "source_unqualified_international_candidate_count": 2,
            "source_unqualified_primary_ids": [13287],
            "six_senior_family_candidate_count": 30,
            "six_senior_family_lead_eligible_count": 23,
            "six_senior_family_lead_excluded_count": 7,
            "candidate_counts_by_primary_id": {
                "114": 2,
                "9806": 2,
                "9807": 4,
                "9808": 2,
                "9821": 6,
                "9833": 2,
                "10437": 10,
                "10608": 14,
                "13287": 2,
            },
            "lead_eligible_counts_by_primary_id": {
                "114": 1,
                "9806": 2,
                "9807": 4,
                "9808": 2,
                "9821": 2,
                "9833": 0,
                "10437": 10,
                "10608": 12,
                "13287": 0,
            },
            "active_mapped_candidate_count": 42,
            "current_shadow_policy_approved_count": 33,
            "current_shadow_policy_lead_excluded_count": 9,
            "current_shadow_policy_pr41_blocked_count": 0,
            "current_shadow_policy_stale_source_excluded_count": 0,
            "current_shadow_policy_request_date_excluded_count": 0,
            "source_admission_only_no_downstream_model_execution": True,
        },
        "scope_semantics": {
            "existing_club_resolution_path_unchanged": True,
            "mixed_club_international_source_card_supported": True,
            "pure_club_behavior_unchanged": True,
            "pure_international_current_source_review_supported": True,
            "international_break_mode_introduced": False,
            "calendar_switching_introduced": False,
            "club_international_rank_mixing_introduced": False,
            "display_name_identity_authority": False,
            "league_wrapper_identity_authority": False,
            "historical_international_mapping_qualified": False,
            "production_source_authority_expanded": False,
            "model_authority_expanded": False,
            "pricing_authority_expanded": False,
            "router_authority_expanded": False,
            "portfolio_authority_expanded": False,
            "selection_authority_expanded": False,
            "sportybet_execution_authority_expanded": False,
            "betting_authority_expanded": False,
            "wager_placed": False,
        },
        "prior_architecture": _current_architecture_identity(),
        "implementation_scope": {
            "provider_acquisition": False,
            "provider_request_count": 0,
            "canonical_run_dispatch": False,
            "current_shadow_dispatch": False,
            "live_proof": False,
            "live_retry": False,
            "share_code_action": False,
            "wager_action": False,
            "workflow_yaml_changed": False,
            "workflow_evolution_transition_added": False,
            "model_pricing_router_portfolio_semantics_changed": False,
            "fresh_holdout_or_p3_0_behavior_changed": False,
        },
        "source_identity": {
            path: _source_identity(path)
            for path in (
                "domain/current_shadow_fotmob_international_source_identity.py",
                "domain/current_fotmob_fixture_review_policy.py",
            )
        },
        "review_governance": {
            "source_review_counter_while_unmerged": "4/5",
            "source_review_counter_if_merged": "5/5",
            "mandatory_source_reread_after_merge": True,
            "p4_4_overall_complete": False,
            "architecture_checkpoint_e_complete": False,
            "next_live_proof_authorized": False,
        },
    }
    value["canonical_sha256"] = _canonical_sha(value)
    return value


def _validate_receipt(value: Any) -> dict[str, Any]:
    expected = expected_receipt()
    if type(value) is not dict:
        raise P44LReviewError("P4.4L receipt differs from deterministic expected evidence")
    mismatched_fields = sorted(
        key
        for key in set(value) | set(expected)
        if value.get(key) != expected.get(key)
    )
    if mismatched_fields:
        raise P44LReviewError(
            "P4.4L receipt differs from deterministic expected evidence: "
            + ", ".join(mismatched_fields)
        )
    if value.get("canonical_sha256") != _canonical_sha(value):
        raise P44LReviewError("P4.4L canonical receipt SHA-256 mismatch")
    architecture = value["prior_architecture"]
    if (
        architecture["workflow_tree_sha1"] != WORKFLOW_TREE_SHA1
        or architecture["workflow_count"] != WORKFLOW_COUNT
        or architecture["workflow_evolution_ledger_sha256"] != EVOLUTION_SHA256
        or architecture["workflow_evolution_transition_count"]
        != EVOLUTION_TRANSITION_COUNT
        or architecture["p4_3_retirement_ledger_sha256"] != RETIREMENT_SHA256
        or architecture["p4_3_retirement_count"] != RETIREMENT_COUNT
        or architecture["prior_p4_4_receipts"]
        != {"p4_4h": P44H_RECEIPT_SHA256, "p4_4i": P44I_RECEIPT_SHA256, "p4_4j": P44J_RECEIPT_SHA256}
    ):
        raise P44LReviewError("prior architecture identity drift")
    return value


def write_expected_receipt() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    value = expected_receipt()
    body = canonical_json_bytes(value)
    (root / RECEIPT_PATH).write_bytes(body)
    return value


def audit(*, check_live: bool = False) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    try:
        value = strict_json_loads((root / RECEIPT_PATH).read_bytes())
    except (OSError, ValueError, TypeError) as exc:
        raise P44LReviewError("P4.4L receipt is missing or invalid JSON") from exc
    receipt = _validate_receipt(value)
    if check_live:
        main = _git("rev-parse", "origin/main").decode("ascii").strip()
        if main != BASE_MAIN:
            raise P44LReviewError("authoritative main moved from the P4.4L base")
        head = _git("rev-parse", "HEAD").decode("ascii").strip()
        _git("merge-base", "--is-ancestor", BASE_MAIN, head)
        paths = set(
            _git("diff", "--name-only", f"{BASE_MAIN}...HEAD")
            .decode("utf-8")
            .splitlines()
        )
        if paths != EXPECTED_CHANGED_PATHS:
            raise P44LReviewError("P4.4L changed-file scope differs from exact envelope")
        architecture = _current_architecture_identity()
        if (
            architecture["workflow_tree_sha1"] != WORKFLOW_TREE_SHA1
            or architecture["workflow_count"] != WORKFLOW_COUNT
        ):
            raise P44LReviewError("workflow tree/count changed during P4.4L")
        if any(path.startswith(".github/workflows/") for path in paths):
            raise P44LReviewError("workflow YAML changed during P4.4L")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write canonical expected receipt")
    parser.add_argument("--check-live", action="store_true", help="validate current branch ancestry and scope")
    args = parser.parse_args()
    if args.write:
        receipt = write_expected_receipt()
    else:
        receipt = audit(check_live=args.check_live)
    print(
        "P4.4L international hierarchy audit: PASS "
        f"receipt={receipt['canonical_sha256']} "
        f"policy={receipt['policy']['policy_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
