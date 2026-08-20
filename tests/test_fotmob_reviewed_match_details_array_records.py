from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from domain.fixture_intelligence import IntelligenceCategory
from domain.fotmob_reviewed_match_details_array_records import (
    ArrayRecordMemberReview,
    ArrayRecordSetReviewDecision,
    ArrayRecordSetScope,
    ArrayReviewQualification,
    ArraySemanticRole,
    LineupStateReviewMapping,
    ReviewedArrayEvidenceStatus,
    ReviewedMatchDetailsArrayRecordsError,
    SourcePositionReviewMapping,
    build_reviewed_match_details_array_records,
    canonical_reviewed_match_details_array_records_bytes,
    revalidate_reviewed_match_details_array_records,
)
from domain.fotmob_reviewed_match_details_field_review import (
    FieldReviewDisposition,
    FotMobReviewedMatchDetailsFieldReviewError,
    MatchDetailsFieldReviewDecision,
)
from domain.fotmob_reviewed_match_details_structure import (
    JsonValueKind,
    assess_reviewed_match_details_structure,
    canonical_reviewed_match_details_structure_bytes,
)
from domain.fotmob_team_strength_fixture_intelligence import LineupState, PositionGroup, TeamSide


RAW_OBJECT = {
    "fixtureTeams": {
        "home": {"id": 10, "isHome": True, "lineupStatus": "confirmed"},
        "away": {"id": 20, "isHome": False, "lineupStatus": "confirmed"},
    },
    "lineups": {
        "home": {
            "starters": [{"id": 101, "teamId": 10, "isHome": True, "position": "GK"}],
            "bench": [{"id": 102, "teamId": 10, "isHome": True, "position": "FW"}],
            "unavailable": [],
        },
        "away": {
            "starters": [{"id": 201, "teamId": 20, "isHome": False, "position": "DF"}],
            "bench": [{"id": 202, "teamId": 20, "isHome": False, "position": "MF"}],
            "unavailable": [{"id": 203, "teamId": 20, "isHome": False, "position": "FW", "reason": "injury"}],
        },
    },
}


def _raw(value=RAW_OBJECT) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _pr53(raw: bytes):
    helper_path = Path(__file__).with_name("test_fotmob_reviewed_match_details_structure.py")
    spec = importlib.util.spec_from_file_location("_athena_pr53_array_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load PR53 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence, receipt, manifest = module._pr52(raw)
    assessment = assess_reviewed_match_details_structure(
        evidence=evidence,
        evidence_receipt_bytes=receipt,
        manifest_bytes=manifest,
        raw_bytes=raw,
    )
    assessment_bytes = canonical_reviewed_match_details_structure_bytes(assessment)
    return evidence, receipt, manifest, assessment, assessment_bytes


def _members(root: str, scope: ArrayRecordSetScope):
    values = [
        ArrayRecordMemberReview(ArraySemanticRole.PLAYER_ID, root + "/*/id", JsonValueKind.INTEGER),
        ArrayRecordMemberReview(ArraySemanticRole.TEAM_ID, root + "/*/teamId", JsonValueKind.INTEGER),
        ArrayRecordMemberReview(ArraySemanticRole.IS_HOME_TEAM, root + "/*/isHome", JsonValueKind.BOOLEAN),
        ArrayRecordMemberReview(ArraySemanticRole.SOURCE_POSITION, root + "/*/position", JsonValueKind.STRING),
    ]
    if scope is ArrayRecordSetScope.UNAVAILABLE:
        values.append(ArrayRecordMemberReview(ArraySemanticRole.UNAVAILABLE_REASON, root + "/*/reason", JsonValueKind.STRING))
    return tuple(values)


def _decisions(evidence, *, qualification=ArrayReviewQualification.QUALIFIED, complete=True, fresh_until=None, lineup_pointer=True):
    result = []
    for side, key, team_id in ((TeamSide.HOME, "home", 10), (TeamSide.AWAY, "away", 20)):
        for scope, array_key in (
            (ArrayRecordSetScope.STARTING_XI, "starters"),
            (ArrayRecordSetScope.BENCH, "bench"),
            (ArrayRecordSetScope.UNAVAILABLE, "unavailable"),
        ):
            root = f"/lineups/{key}/{array_key}"
            result.append(ArrayRecordSetReviewDecision(
                scope=scope,
                array_root_pointer=root,
                record_pointer_pattern=root + "/*",
                team_side=side,
                source_team_id=team_id,
                team_id_pointer=f"/fixtureTeams/{key}/id",
                team_id_kind=JsonValueKind.INTEGER,
                is_home_pointer=f"/fixtureTeams/{key}/isHome",
                lineup_state_pointer=f"/fixtureTeams/{key}/lineupStatus" if lineup_pointer else None,
                lineup_state_kind=JsonValueKind.STRING if lineup_pointer else None,
                member_reviews=_members(root, scope),
                qualification=qualification,
                completeness_attested=complete if qualification is ArrayReviewQualification.QUALIFIED else False,
                fresh_until=fresh_until or evidence.kickoff,
                notes="synthetic exact-observation array review",
            ))
    return tuple(result)


def build_case(raw=None, *, decisions=None, mappings=None, positions=None):
    raw = raw or _raw()
    chain = _pr53(raw)
    evidence = chain[0]
    reviewed_at = evidence.observed_at + dt.timedelta(seconds=1)
    classified_at = reviewed_at + dt.timedelta(seconds=1)
    decisions = decisions or _decisions(evidence)
    artifact = build_reviewed_match_details_array_records(
        evidence=evidence,
        evidence_receipt_bytes=chain[1],
        manifest_bytes=chain[2],
        raw_bytes=raw,
        assessment=chain[3],
        assessment_bytes=chain[4],
        decisions=decisions,
        lineup_state_mappings=mappings if mappings is not None else (LineupStateReviewMapping("confirmed", LineupState.CONFIRMED),),
        position_mappings=positions if positions is not None else (
            SourcePositionReviewMapping("DF", PositionGroup.DEF),
            SourcePositionReviewMapping("FW", PositionGroup.FWD),
            SourcePositionReviewMapping("GK", PositionGroup.GK),
            SourcePositionReviewMapping("MF", PositionGroup.MID),
        ),
        reviewed_at=reviewed_at,
        classified_at=classified_at,
        reviewer_reference="SYNTHETIC-ARRAY-REVIEW-001",
    )
    return artifact, chain, raw


def test_exact_pr52_pr53_array_review_extracts_identity_sorted_records_and_empty_completeness():
    artifact, _, _ = build_case()
    assert len(artifact.records) == 5
    assert tuple(record.provider_player_id for record in artifact.records) == (201, 202, 203, 101, 102)
    empty = next(item for item in artifact.completeness_receipts if item.team_side is TeamSide.HOME and item.scope is ArrayRecordSetScope.UNAVAILABLE)
    assert empty.record_count == 0
    assert empty.provider_player_ids == ()
    assert all(value is False for value in artifact.safety.values())
    assert canonical_reviewed_match_details_array_records_bytes(artifact).endswith(b"\n")


def test_raw_key_names_and_unobserved_patterns_never_self_authorize():
    chain = _pr53(_raw())
    bad_root = "/lineups/home/players"
    bad = dataclasses.replace(
        _decisions(chain[0])[0],
        array_root_pointer=bad_root,
        record_pointer_pattern=bad_root + "/*",
        member_reviews=_members(bad_root, ArrayRecordSetScope.STARTING_XI),
    )
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="array root"):
        build_case(decisions=(bad,) + _decisions(chain[0])[1:])


def test_pr54_wildcard_approval_remains_forbidden():
    with pytest.raises(FotMobReviewedMatchDetailsFieldReviewError, match="array wildcard"):
        MatchDetailsFieldReviewDecision(
            "/lineups/home/starters/*/id", JsonValueKind.INTEGER,
            FieldReviewDisposition.APPROVED, IntelligenceCategory.LINEUP, "player_id", "forbidden",
        )


def test_review_cannot_cross_raw_fixture_or_source_identity():
    artifact, chain, raw = build_case()
    artifact_bytes = canonical_reviewed_match_details_array_records_bytes(artifact)
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError):
        revalidate_reviewed_match_details_array_records(
            evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2],
            raw_bytes=raw.replace(b'"GK"', b'"GQ"'), assessment=chain[3], assessment_bytes=chain[4],
            artifact=artifact, artifact_bytes=artifact_bytes,
        )
    object.__setattr__(chain[0], "source_match_id", "9999")
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError):
        revalidate_reviewed_match_details_array_records(
            evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2],
            raw_bytes=raw, assessment=chain[3], assessment_bytes=chain[4],
            artifact=artifact, artifact_bytes=artifact_bytes,
        )


def test_array_index_is_provenance_not_identity_and_duplicate_player_fails_closed():
    value = json.loads(_raw())
    value["lineups"]["home"]["bench"][0]["id"] = 101
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="same provider player|duplicate"):
        build_case(raw=_raw(value))


def test_starter_unavailable_conflict_is_not_resolved():
    value = json.loads(_raw())
    value["lineups"]["home"]["unavailable"] = [{"id": 101, "teamId": 10, "isHome": True, "position": "GK", "reason": "injury"}]
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="contradictory reviewed scopes"):
        build_case(raw=_raw(value))


def test_team_side_and_provider_team_id_must_match_exact_raw_scalars():
    chain = _pr53(_raw())
    decisions = list(_decisions(chain[0]))
    decisions[0] = dataclasses.replace(decisions[0], source_team_id=999)
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="source team identity"):
        build_case(decisions=tuple(decisions))
    decisions = list(_decisions(chain[0]))
    decisions[0] = dataclasses.replace(decisions[0], team_side=TeamSide.AWAY)
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError):
        build_case(decisions=tuple(decisions))


def test_kind_and_coarse_position_are_review_outputs_not_extraction_parameters():
    parameters = inspect.signature(build_reviewed_match_details_array_records).parameters
    assert "record_kind" not in parameters
    assert "position_group" not in parameters
    artifact, _, _ = build_case(positions=())
    assert {record.source_position for record in artifact.records} == {"DF", "FW", "GK", "MF"}
    assert artifact.position_mappings == ()


def test_lineup_confirmation_is_not_inferred_from_time_or_array_presence():
    chain = _pr53(_raw())
    artifact, _, _ = build_case(
        decisions=_decisions(chain[0], lineup_pointer=False),
        mappings=(),
    )
    assert {record.lineup_state for record in artifact.records} == {LineupState.UNVERIFIED_LINEUP_STATE}


def test_absent_array_is_not_zero_but_exact_reviewed_empty_array_is_zero():
    value = json.loads(_raw())
    del value["lineups"]["home"]["unavailable"]
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="array root"):
        build_case(raw=_raw(value))
    artifact, _, _ = build_case()
    receipt = next(item for item in artifact.completeness_receipts if item.team_side is TeamSide.HOME and item.scope is ArrayRecordSetScope.UNAVAILABLE)
    assert receipt.record_count == 0


def test_incomplete_rejected_and_stale_arrays_do_not_claim_current_supported_completeness():
    chain = _pr53(_raw())
    incomplete, _, _ = build_case(decisions=_decisions(chain[0], complete=False))
    assert incomplete.completeness_receipts == ()
    rejected, _, _ = build_case(decisions=_decisions(chain[0], qualification=ArrayReviewQualification.REJECTED), positions=())
    assert rejected.records == ()
    assert rejected.completeness_receipts == ()
    classified_at = chain[0].observed_at + dt.timedelta(seconds=2)
    stale, _, _ = build_case(decisions=_decisions(chain[0], fresh_until=classified_at - dt.timedelta(seconds=1)))
    assert {record.evidence_status for record in stale.records} == {ReviewedArrayEvidenceStatus.STALE}


def test_post_kickoff_classification_and_freshness_before_observation_fail_closed():
    chain = _pr53(_raw())
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="fresh_until"):
        build_case(decisions=_decisions(chain[0], fresh_until=chain[0].observed_at - dt.timedelta(seconds=1)))
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError, match="prospective"):
        build_reviewed_match_details_array_records(
            evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2], raw_bytes=_raw(),
            assessment=chain[3], assessment_bytes=chain[4], decisions=_decisions(chain[0]),
            lineup_state_mappings=(LineupStateReviewMapping("confirmed", LineupState.CONFIRMED),),
            position_mappings=(), reviewed_at=chain[0].observed_at,
            classified_at=chain[0].kickoff, reviewer_reference="SYNTHETIC",
        )


def test_decision_order_cannot_change_artifact_or_canonical_bytes():
    chain = _pr53(_raw())
    first, _, _ = build_case(decisions=_decisions(chain[0]))
    second, _, _ = build_case(decisions=tuple(reversed(_decisions(chain[0]))))
    assert canonical_reviewed_match_details_array_records_bytes(first) == canonical_reviewed_match_details_array_records_bytes(second)


def test_artifact_and_exact_bytes_are_rebuilt_from_raw():
    artifact, chain, raw = build_case()
    exact = canonical_reviewed_match_details_array_records_bytes(artifact)
    assert revalidate_reviewed_match_details_array_records(
        evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2], raw_bytes=raw,
        assessment=chain[3], assessment_bytes=chain[4], artifact=artifact, artifact_bytes=exact,
    ) == artifact
    with pytest.raises(ReviewedMatchDetailsArrayRecordsError):
        revalidate_reviewed_match_details_array_records(
            evidence=chain[0], evidence_receipt_bytes=chain[1], manifest_bytes=chain[2], raw_bytes=raw,
            assessment=chain[3], assessment_bytes=chain[4], artifact=artifact, artifact_bytes=exact + b"\n",
        )


def test_production_array_boundary_has_no_network_bypass_probability_pricing_or_betting_imports():
    import domain.fotmob_reviewed_match_details_array_records as production

    tree = ast.parse(inspect.getsource(production))
    imported = {
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    forbidden = ("requests", "urllib", "httpx", "bypass", "advanced_scraper", "score_matrix", "probability", "pricing", "sportybet", "selection", "betting")
    assert not any(any(token in name.lower() for token in forbidden) for name in imported)
