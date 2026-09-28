"""Fail-closed offline audit for the P4.4L international identity bridge."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import os
import re
from pathlib import Path
import subprocess
from unittest.mock import patch
from typing import Any

import domain.fotmob_fixture_candidates as candidate_module
import domain.current_fotmob_fixture_review_policy as review_policy
from domain.fotmob_data_matches_capture import (
    DATASET_NAME as CAPTURE_DATASET_NAME,
    SCHEMA_VERSION as CAPTURE_SCHEMA_VERSION,
)
from domain.fotmob_fixture_candidate_review import FixtureCandidateReviewDisposition
from domain.fotmob_fixture_candidates import (
    DATASET_NAME as CANDIDATE_DATASET_NAME,
    SCHEMA_VERSION as CANDIDATE_SCHEMA_VERSION,
    SOURCE_NAME,
    FixtureCandidateReviewStatus,
    FotMobFixtureCandidate,
    FotMobFixtureCandidateBundle,
    FotMobFixtureCandidateSource,
)
from domain.ingest_contracts import canonical_json_bytes, strict_json_loads
from domain import current_shadow_fotmob_international_source_identity as identity
from scripts import audit_p4_3_workflow_retirement_ledger as retirement
from scripts import audit_p4_4g_current_fotmob_canonical_only_workflow as p44g
from scripts import audit_p4_workflow_evolution_ledger as evolution
from config.competition_review_priority import (
    CompetitionScope,
    INTERNATIONAL_COMPETITION_REVIEW_PRIORITY,
)


BASE_MAIN = "b17e97dbea043d45d47db9ad2011354fe4682baf"
P44L_REVIEWED_HEAD = "51e480540654ee9cc3ed4076c8c3edc73e48e056"
P44L_MERGE_COMMIT = "6b39648cac4e9924c0809d60dddc9c5d5660ad77"
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
P44L_HISTORICAL_SOURCE_IDENTITIES = {
    "domain/current_shadow_fotmob_international_source_identity.py": {
        "git_blob_sha1": "9d8b3f3fd3b2f7eb95296496f7d0bf681e0a0666",
        "source_sha256": "057f7841c4f2f7a12ce17c8a38d47d2839c968673d3cade9c36634c2bc7f9207",
    },
    "domain/current_fotmob_fixture_review_policy.py": {
        "git_blob_sha1": "857ccdba7bfb70b7c91c856adfb9a4d0d1f17a52",
        "source_sha256": "80a5f917ad0da9664c564486e832594eedcca19c3067eb946100b194448f2165",
    },
}
P44H_RECEIPT_SHA256 = "0000a5978268909dd07330d59079bc4d7f8d32c0fee161653a4a19eea9b97c64"
P44I_RECEIPT_SHA256 = "d6f65a382c4ef23318a81261e48b8e717f768864a6e1e5baed61af3c11351a7c"
P44J_RECEIPT_SHA256 = "335a22e5c73a397d5f3b24605d16a7b9f1220ce831fc378cedd17f4dd1a7ef49"
P44L_PRIOR_ARCHITECTURE = {
    "workflow_tree_sha1": WORKFLOW_TREE_SHA1,
    "workflow_count": WORKFLOW_COUNT,
    "workflow_evolution_ledger_sha256": EVOLUTION_SHA256,
    "workflow_evolution_transition_count": EVOLUTION_TRANSITION_COUNT,
    "p4_3_retirement_ledger_sha256": RETIREMENT_SHA256,
    "p4_3_retirement_count": RETIREMENT_COUNT,
    "prior_p4_4_receipts": {
        "p4_4h": P44H_RECEIPT_SHA256,
        "p4_4i": P44I_RECEIPT_SHA256,
        "p4_4j": P44J_RECEIPT_SHA256,
    },
}
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


def _commit_object_available(commit: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True
    ).returncode == 0


def _blob_object_available(blob: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{blob}^{{blob}}"], capture_output=True
    ).returncode == 0


def _require_trusted_current_ci_context() -> None:
    """Bind shallow historical checks to this repository's current PR/push event."""
    try:
        event_name = os.environ.get("GITHUB_EVENT_NAME")
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ValueError("GITHUB_EVENT_PATH is missing")
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        if type(event) is not dict:
            raise ValueError("GitHub event must be an object")
        repository = event.get("repository")
        if type(repository) is not dict or repository.get("full_name") != "Thabearr/ATHENA":
            raise ValueError("GitHub repository identity differs")
        if os.environ.get("GITHUB_REPOSITORY") not in (None, "Thabearr/ATHENA"):
            raise ValueError("GITHUB_REPOSITORY differs")
        head = _git("rev-parse", "HEAD").decode("ascii").strip()
        github_sha = os.environ.get("GITHUB_SHA", "")
        if not re.fullmatch(r"[0-9a-f]{40}", github_sha) or head != github_sha:
            raise ValueError("checked-out HEAD differs from GITHUB_SHA")

        if event_name == "pull_request":
            pull_request = event.get("pull_request")
            if type(pull_request) is not dict:
                raise ValueError("pull_request event is malformed")
            base = pull_request.get("base")
            pr_head = pull_request.get("head")
            if type(base) is not dict or type(pr_head) is not dict:
                raise ValueError("pull_request base/head metadata is malformed")
            if (
                base.get("ref") != "main"
                or not re.fullmatch(r"[0-9a-f]{40}", str(base.get("sha", "")))
                or not re.fullmatch(r"[0-9a-f]{40}", str(pr_head.get("sha", "")))
            ):
                raise ValueError("pull_request base/head identity is malformed")
            return

        if event_name == "push":
            if (
                os.environ.get("GITHUB_REF") != "refs/heads/main"
                or event.get("ref") != "refs/heads/main"
                or event.get("after") != github_sha
                or event.get("deleted") is True
                or repository.get("default_branch") != "main"
            ):
                raise ValueError("main push event identity differs")
            return

        raise ValueError("event is neither pull_request nor push")
    except (OSError, json.JSONDecodeError, UnicodeError, ValueError, P44LReviewError) as exc:
        raise P44LReviewError(
            "P4.4L historical audit lacks a trusted current repository PR/push binding"
        ) from exc


def _verify_historical_review_ancestry(*, trusted_current_ci: bool) -> None:
    """Authenticate the immutable P4.4L merge, not the current main tip."""
    if _commit_object_available(P44L_MERGE_COMMIT):
        parents = _git("show", "-s", "--format=%P", P44L_MERGE_COMMIT).decode("ascii").split()
        if parents != [BASE_MAIN, P44L_REVIEWED_HEAD]:
            raise P44LReviewError("P4.4L merge commit does not bind its exact reviewed base/head")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", P44L_MERGE_COMMIT, "HEAD"],
            capture_output=True,
        )
        if ancestor.returncode != 0:
            raise P44LReviewError("P4.4L reviewed merge is not an ancestor of current HEAD")
        return
    if not trusted_current_ci:
        raise P44LReviewError(
            "P4.4L merge object is unavailable outside trusted shallow CI"
        )
    if _commit_object_available(P44L_REVIEWED_HEAD):
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", P44L_REVIEWED_HEAD, "HEAD"],
            capture_output=True,
        )
        if ancestor.returncode != 0:
            raise P44LReviewError("P4.4L reviewed head is not an ancestor of current HEAD")


def _verify_historical_changed_paths(*, trusted_current_ci: bool) -> None:
    if not all(_commit_object_available(ref) for ref in (BASE_MAIN, P44L_REVIEWED_HEAD)):
        if trusted_current_ci:
            return
        raise P44LReviewError(
            "P4.4L base/reviewed-head objects are unavailable outside trusted CI"
        )
    paths = set(
        _git("diff", "--name-only", f"{BASE_MAIN}...{P44L_REVIEWED_HEAD}")
        .decode("utf-8")
        .splitlines()
    )
    if paths != EXPECTED_CHANGED_PATHS:
        raise P44LReviewError("P4.4L historical changed-file scope differs from exact envelope")


def _verify_historical_workflow_tree(*, trusted_current_ci: bool) -> None:
    checked = False
    for ref in (P44L_REVIEWED_HEAD, P44L_MERGE_COMMIT):
        if _commit_object_available(ref):
            tree = _git("rev-parse", f"{ref}:.github/workflows").decode("ascii").strip()
            if tree != WORKFLOW_TREE_SHA1:
                raise P44LReviewError(f"P4.4L historical workflow tree differs at {ref}")
            checked = True
    if not checked:
        if not trusted_current_ci:
            raise P44LReviewError(
                "P4.4L historical workflow tree is unavailable outside trusted CI"
            )
        historical = p44g._load_json(p44g.SNAPSHOT_PATH)
        if historical.get("current_workflow_tree_sha1") != WORKFLOW_TREE_SHA1:
            raise P44LReviewError("immutable P4.4G checkpoint does not bind P4.4L workflow tree")


def _verify_historical_source_identity(
    path: str, expected: dict[str, str], *, trusted_current_ci: bool, receipt: dict[str, Any]
) -> None:
    """Validate source bytes at the P4.4L checkpoint, never current HEAD as a proxy."""
    if _commit_object_available(P44L_REVIEWED_HEAD):
        actual = _source_identity(path, P44L_REVIEWED_HEAD)
    elif _blob_object_available(expected["git_blob_sha1"]):
        actual = evolution.source_identity(
            _git("cat-file", "-p", expected["git_blob_sha1"])
        )
    elif trusted_current_ci:
        if receipt.get("source_identity", {}).get(path) == expected:
            return
        raise P44LReviewError(f"P4.4L receipt does not authenticate historical source: {path}")
    else:
        raise P44LReviewError(
            f"P4.4L historical source object is unavailable outside trusted CI: {path}"
        )
    if actual != expected:
        raise P44LReviewError(f"P4.4L historical source identity differs: {path}")


def _verify_historical_evolution_prefix(
    current_ledger: dict[str, Any], historical_snapshot: dict[str, Any]
) -> None:
    transitions = historical_snapshot.get("transitions")
    current_transitions = current_ledger.get("transitions")
    if (
        historical_snapshot.get("canonical_sha256") != EVOLUTION_SHA256
        or evolution.canonical_sha256(historical_snapshot) != EVOLUTION_SHA256
        or not isinstance(transitions, list)
        or len(transitions) != EVOLUTION_TRANSITION_COUNT
    ):
        raise P44LReviewError("immutable P4.4L six-transition checkpoint identity differs")
    if (
        not isinstance(current_transitions, list)
        or len(current_transitions) < EVOLUTION_TRANSITION_COUNT
        or current_transitions[:EVOLUTION_TRANSITION_COUNT] != transitions
    ):
        raise P44LReviewError("current workflow evolution does not preserve the exact P4.4L prefix")


def _verify_current_workflow_state(current_ledger: dict[str, Any]) -> None:
    observed_tree = _git("rev-parse", "HEAD:.github/workflows").decode("ascii").strip()
    paths = _git("ls-tree", "-r", "--name-only", "HEAD", ".github/workflows").decode("utf-8").splitlines()
    observed_count = sum(path.endswith((".yml", ".yaml")) for path in paths)
    if observed_tree != current_ledger.get("current_workflow_tree_sha1"):
        raise P44LReviewError("current workflow tree differs from current cumulative evolution ledger")
    if observed_count != current_ledger.get("current_live_workflow_count"):
        raise P44LReviewError("current workflow count differs from current cumulative evolution ledger")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "canonical_sha256"}
    return _sha256(canonical_json_bytes(body))


def _source_identity(path: str, ref: str = "HEAD") -> dict[str, str]:
    # Hash the committed blob bytes rather than checkout bytes: Windows may
    # materialize CRLF while hosted Linux checkouts use LF for the same blob.
    raw = _git("show", f"{ref}:{path}")
    blob = _git("rev-parse", f"{ref}:{path}").decode("ascii").strip()
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
    current_evolution = evolution.validate_current_state()
    current_retirement = retirement.validate_retirement_history()
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
        "workflow_evolution_ledger_sha256": current_evolution.get("canonical_sha256"),
        "workflow_evolution_transition_count": len(current_evolution.get("transitions", [])),
        "p4_3_retirement_ledger_sha256": current_retirement.get("canonical_sha256"),
        "p4_3_retirement_count": current_retirement.get("current_retired_workflow_count"),
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
    if payload.get("cross_path_identity_conflict_rule") != (
        "FAIL_CLOSED_WHEN_KNOWN_P4_4L_PRIMARY_ID_CONFLICTS_WITH_EXISTING_SOURCE_NAME_RESOLUTION"
    ) or payload.get("unknown_primary_id_preserves_existing_reviewed_source_name_path") is not True or payload.get(
        "observed_unqualified_primary_id_cannot_be_reclassified_by_source_name"
    ) is not True:
        raise P44LReviewError("cross-path identity conflict semantics are not policy-bound")
    if (
        identity.InternationalSourceCoverageState.__members__.get(
            "OBSERVED_IDENTITY_NOT_HIERARCHY_QUALIFIED"
        )
        is not identity.InternationalSourceCoverageState.OBSERVED_IDENTITY_NOT_HIERARCHY_QUALIFIED
    ):
        raise P44LReviewError("observed-unqualified coverage enum member is undefined")
    enum_references = re.findall(
        r"InternationalSourceCoverageState\.([A-Z][A-Z0-9_]*)",
        inspect.getsource(identity),
    )
    if any(
        member_name not in identity.InternationalSourceCoverageState.__members__
        for member_name in enum_references
    ):
        raise P44LReviewError("international identity policy references an undefined enum member")
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
    required_shadow_guard = "if policy_id == SHADOW_POLICY_ID:"
    if (
        required_shadow_guard not in policy_source
        or "resolve_current_shadow_international_source_priority(" not in policy_source
        or "reviewed_current_fotmob_international_source_identity(" not in policy_source
        or "observed_unqualified_current_fotmob_international_source_identity(" not in policy_source
    ):
        raise P44LReviewError("Shadow-only fallback or current exact source path drifted")
    _validate_cross_path_identity_behavior()
    tests_source = (root / "tests/test_current_fotmob_fixture_review_policy.py").read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_shadow_mixed_club_and_international_card_admits_each_through_own_path",
        "test_pure_club_source_resolution_retains_existing_reviewed_note_semantics",
        "test_production_builder_never_invokes_shadow_international_resolver",
        "test_known_looking_international_label_without_qualified_primary_id_stays_unreviewed",
        "test_shadow_rejects_conflicting_reviewed_name_and_p4_4l_primary_id",
        "test_shadow_rejects_observed_unqualified_id_reclassified_by_source_name",
        "test_unknown_p44l_primary_id_preserves_existing_uefa_club_source_name_path",
    ):
        if f"def {test_name}(" not in tests_source:
            raise P44LReviewError("required mixed/pure-scope or production-isolation regression missing")


def _identity_contract_fixture_bundle(
    specs: tuple[tuple[int, int, int, str, str], ...] | None = None,
) -> FotMobFixtureCandidateBundle:
    observed = dt.datetime(2026, 8, 27, 7, 0, tzinfo=dt.timezone.utc)
    raw = b'{"offline_identity_contract":true}\n'
    raw_sha = _sha256(raw)
    specs = specs or (
        (88041, 500, 9806, "Champions League", "INT"),
        (88042, 500, 13287, "Champions League", "INT"),
        (88043, 500, 700001, "Champions League", "INT"),
        (88044, 47, 47, "Premier League", "ENG"),
        (88045, 500, 9807, "Renamed presentation metadata", "INT"),
    )
    source = FotMobFixtureCandidateSource(
        source_capture_dataset_name=CAPTURE_DATASET_NAME,
        source_capture_schema_version=CAPTURE_SCHEMA_VERSION,
        source_capture_manifest_sha256="1" * 64,
        source_raw_sha256=raw_sha,
        source_raw_size=len(raw),
        source_observed_at=observed,
        request_date="20260827",
        timezone="UTC",
        ccode3="NGA",
        schema_assessment_sha256="2" * 64,
        candidate_count=len(specs),
    )
    candidates = tuple(
        sorted(
            (
                FotMobFixtureCandidate(
                    review_status=FixtureCandidateReviewStatus.UNREVIEWED,
                    source=SOURCE_NAME,
                    source_match_id=match_id,
                    source_league_id=league_id,
                    source_competition_primary_id=primary_id,
                    source_competition_name=competition_name,
                    source_competition_ccode=ccode,
                    home_source_team_id=1000 + match_id,
                    home_name=f"Home {match_id}",
                    home_long_name=f"Home {match_id}",
                    away_source_team_id=2000 + match_id,
                    away_name=f"Away {match_id}",
                    away_long_name=f"Away {match_id}",
                    kickoff_utc=dt.datetime(2026, 8, 27, 15, 0, tzinfo=dt.timezone.utc),
                    source_capture_manifest_sha256=source.source_capture_manifest_sha256,
                    source_raw_sha256=raw_sha,
                    source_request_date=source.request_date,
                    source_observed_at=observed,
                )
                for match_id, league_id, primary_id, competition_name, ccode in specs
            ),
            key=candidate_module._candidate_sort_key,
        )
    )
    duplicate_count, fixture_conflicts = candidate_module._make_fixture_observations(
        candidates
    )
    team_conflicts = candidate_module._make_team_conflicts(candidates)
    competition_conflicts = candidate_module._make_competition_conflicts(candidates)
    return FotMobFixtureCandidateBundle(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        dataset_name=CANDIDATE_DATASET_NAME,
        sources=(source,),
        candidate_count=len(candidates),
        candidates=candidates,
        duplicate_source_match_id_count=duplicate_count,
        fixture_identity_conflict_count=len(fixture_conflicts),
        fixture_identity_conflicts=fixture_conflicts,
        team_identity_conflict_count=len(team_conflicts),
        team_identity_conflicts=team_conflicts,
        competition_identity_conflict_count=len(competition_conflicts),
        competition_identity_conflicts=competition_conflicts,
        safety=candidate_module._default_safety(),
    )


def _validate_cross_path_identity_behavior() -> None:
    reviewed_at = dt.datetime(2026, 8, 27, 7, 5, tzinfo=dt.timezone.utc)
    cases = (
        ((88041, 500, 9806, "Champions League", "INT"), False),
        ((88042, 500, 13287, "Champions League", "INT"), False),
        ((88043, 500, 700001, "Champions League", "INT"), True),
        ((88044, 47, 47, "Premier League", "ENG"), True),
    )
    for (match_id, league_id, primary_id, name, ccode), expected_approval in cases:
        result = review_policy.build_current_shadow_fotmob_fixture_review_policy_result(
            _identity_contract_fixture_bundle(
                ((match_id, league_id, primary_id, name, ccode),)
            ),
            reviewed_at=reviewed_at,
        )
        if result.policy_approved_count != int(expected_approval):
            raise P44LReviewError(
                f"Current Shadow cross-path identity behavior drift for {ccode}:{primary_id}"
            )

    mixed = review_policy.build_current_shadow_fotmob_fixture_review_policy_result(
        _identity_contract_fixture_bundle(
            (
                (88044, 47, 47, "Premier League", "ENG"),
                (88045, 500, 9807, "Renamed presentation metadata", "INT"),
            )
        ),
        reviewed_at=reviewed_at,
    )
    if mixed.policy_approved_count != 2:
        raise P44LReviewError("valid mixed club/international source card was suppressed")

    def unexpected(**kwargs: Any) -> None:
        raise P44LReviewError("production PR243 invoked the Shadow international bridge")

    with patch.object(
        review_policy,
        "resolve_current_shadow_international_source_priority",
        unexpected,
    ), patch.object(
        review_policy,
        "reviewed_current_fotmob_international_source_identity",
        unexpected,
    ), patch.object(
        review_policy,
        "observed_unqualified_current_fotmob_international_source_identity",
        unexpected,
    ):
        production = review_policy.build_current_fotmob_fixture_review_policy_result(
            _identity_contract_fixture_bundle(
                ((88043, 500, 700001, "Champions League", "INT"),)
            ),
            reviewed_at=reviewed_at,
        )
    if production.policy_approved_count != 1:
        raise P44LReviewError("production source-name path changed under P4.4L")


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
            "cross_path_identity_conflict_rule": policy_payload[
                "cross_path_identity_conflict_rule"
            ],
            "unknown_primary_id_preserves_existing_reviewed_source_name_path": (
                policy_payload[
                    "unknown_primary_id_preserves_existing_reviewed_source_name_path"
                ]
            ),
            "observed_unqualified_primary_id_cannot_be_reclassified_by_source_name": (
                policy_payload[
                    "observed_unqualified_primary_id_cannot_be_reclassified_by_source_name"
                ]
            ),
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
        # This field is a frozen historical observation made at P4.4L.  Later
        # workflow-evolution transitions must not rewrite that receipt.
        "prior_architecture": P44L_PRIOR_ARCHITECTURE,
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
            path: dict(identity)
            for path, identity in P44L_HISTORICAL_SOURCE_IDENTITIES.items()
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
        trusted_current_ci = os.environ.get("GITHUB_EVENT_NAME") is not None
        if trusted_current_ci:
            _require_trusted_current_ci_context()
        _verify_historical_review_ancestry(trusted_current_ci=trusted_current_ci)
        _verify_historical_changed_paths(trusted_current_ci=trusted_current_ci)
        _verify_historical_workflow_tree(trusted_current_ci=trusted_current_ci)

        # P4.4L's six-transition evolution and three-retirement observations
        # remain historical receipt facts. Current state is independently
        # validated against the cumulative governance ledgers.
        p44g.audit(check_live=False)
        historical_snapshot = p44g._load_json(p44g.SNAPSHOT_PATH)
        current_ledger = evolution.validate_current_state()
        _verify_historical_evolution_prefix(current_ledger, historical_snapshot)
        _verify_current_workflow_state(current_ledger)
        retirement_state = retirement.validate_retirement_history()
        if retirement_state.get("current_retired_workflow_count", 0) < RETIREMENT_COUNT:
            raise P44LReviewError(
                "current retirement history no longer includes the three historical P4.4L retirements"
            )

        for path, expected_identity in P44L_HISTORICAL_SOURCE_IDENTITIES.items():
            _verify_historical_source_identity(
                path,
                expected_identity,
                trusted_current_ci=trusted_current_ci,
                receipt=receipt,
            )
        if any(path.startswith(".github/workflows/") for path in EXPECTED_CHANGED_PATHS):
            raise P44LReviewError("P4.4L historical changed-file envelope unexpectedly includes workflow YAML")
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
