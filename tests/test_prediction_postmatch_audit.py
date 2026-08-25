from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import socket
import urllib.request
from unittest.mock import patch

import pytest

from domain.markets import MarketId, OutcomeId
from domain.prediction_postmatch_audit import (
    AUTHORITATIVE_BASE_SHA,
    AttributionFactor,
    DecisionQuality,
    DeclaredSettlementSummary,
    EvidenceAuthority,
    EvidenceAvailability,
    EvidencedValue,
    FieldTrialLeg,
    ImportIdentity,
    MarketCandidate,
    PostMatchAttribution,
    PostMatchSettlementRecord,
    PreMatchDecisionRecord,
    PredictionFieldTrial,
    PredictionPostMatchAuditError,
    ReconstructionStatus,
    SettlementOutcome,
    SettlementSummary,
    SourceEvidence,
    VerificationState,
    build_prediction_field_trial_from_import,
    canonical_prediction_field_trial_bytes,
    default_safety,
    missing_value,
    unknown_value,
)
from scripts.import_prediction_field_trial import (
    PredictionFieldTrialImportError,
    import_field_trial,
    strict_json_loads,
)


SOURCE_ID = "preserved-source-1"


def _available(value, source_id: str = SOURCE_ID) -> EvidencedValue:
    return EvidencedValue(EvidenceAvailability.AVAILABLE, value, (source_id,))


def _source(
    source_id: str = SOURCE_ID,
    *,
    authority: EvidenceAuthority = EvidenceAuthority.PRESERVED_ARTIFACT,
    verification: VerificationState = VerificationState.VERIFIED,
    reference: str = "artifacts/preserved-source.json",
) -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        authority=authority,
        reference=reference,
        content_sha256=unknown_value(),
        observed_at=unknown_value(),
        verification_state=verification,
        notes="Exact source identity retained for the test audit record.",
    )


def _candidate(
    *,
    candidate_id: str = "candidate-over-1.5",
    probability: EvidencedValue | None = None,
    bookmaker_price: EvidencedValue | None = None,
    outcome_id: OutcomeId = OutcomeId.OVER,
    line: float = 1.5,
) -> MarketCandidate:
    return MarketCandidate(
        candidate_id=candidate_id,
        market_id=MarketId.TOTAL_GOALS,
        outcome_id=outcome_id,
        line=line,
        model_probability=probability or _available(0.72),
        fair_price=missing_value(SOURCE_ID),
        risk_uncertainty=unknown_value(SOURCE_ID),
        original_rank=_available(1),
        original_score=unknown_value(SOURCE_ID),
        bookmaker_source=unknown_value(SOURCE_ID),
        exact_bookmaker_mapping=unknown_value(SOURCE_ID),
        bookmaker_price=bookmaker_price or missing_value(SOURCE_ID),
        quote_observed_at=missing_value(SOURCE_ID),
        quote_identity=missing_value(SOURCE_ID),
        reason_not_selected=missing_value(SOURCE_ID),
        pre_match_evidence_references=(SOURCE_ID,),
    )


def _pre_match(
    *,
    fixture_identity: EvidencedValue | None = None,
    candidates: tuple[MarketCandidate, ...] | None = None,
    selected_candidate_id: EvidencedValue | None = None,
    counterfactual_candidate_ids: EvidencedValue | None = None,
) -> PreMatchDecisionRecord:
    candidates = candidates or (_candidate(),)
    return PreMatchDecisionRecord(
        record_key="preserved-leg-1",
        fixture_identity=fixture_identity or _available("fixture-123"),
        home_team=_available("Home FC"),
        away_team=_available("Away FC"),
        competition=_available("Test Competition"),
        kickoff_time=_available("2026-08-22T15:00:00Z"),
        source_fixture_identifiers=_available({"provider": "fixture-123"}),
        generated_at=_available("2026-08-22T10:00:00Z"),
        athena_version=_available("preserved-athena-version"),
        athena_commit=_available(AUTHORITATIVE_BASE_SHA),
        model_identity=_available("preserved-model-identity"),
        pre_match_evidence_references=(SOURCE_ID,),
        model_raw_outputs=_available({"source_probability": 0.72}),
        score_distribution_model_identifiers=unknown_value(SOURCE_ID),
        eligible_candidates_status=EvidenceAvailability.AVAILABLE,
        eligible_market_candidates=candidates,
        selected_candidate_id=selected_candidate_id or _available(candidates[0].candidate_id),
        candidate_ranking=_available([candidate.candidate_id for candidate in candidates]),
        counterfactual_candidate_ids=counterfactual_candidate_ids or missing_value(SOURCE_ID),
    )


def _settlement(outcome: SettlementOutcome = SettlementOutcome.LOST) -> PostMatchSettlementRecord:
    refs = () if outcome is SettlementOutcome.UNKNOWN else (SOURCE_ID,)
    return PostMatchSettlementRecord(
        final_home_score=unknown_value(SOURCE_ID),
        final_away_score=unknown_value(SOURCE_ID),
        regulation_score_semantics=unknown_value(SOURCE_ID),
        result_source=unknown_value(SOURCE_ID),
        observed_at=unknown_value(SOURCE_ID),
        source_evidence_reference=unknown_value(SOURCE_ID),
        settlement_outcome=outcome,
        settlement_evidence_references=refs,
    )


def _unknown_attribution() -> PostMatchAttribution:
    return PostMatchAttribution(
        primary_factor=AttributionFactor.UNKNOWN,
        contributing_factors=(),
        decision_quality=DecisionQuality.UNKNOWN,
        evidence_references=(),
        observation_source_identity=unknown_value(),
        explanatory_notes=unknown_value(),
        verification_state=VerificationState.UNKNOWN,
    )


def _verified_attribution(
    factor: AttributionFactor = AttributionFactor.DATA_ERROR,
) -> PostMatchAttribution:
    return PostMatchAttribution(
        primary_factor=factor,
        contributing_factors=(),
        decision_quality=DecisionQuality.UNKNOWN,
        evidence_references=(SOURCE_ID,),
        observation_source_identity=_available("preserved-source-observation"),
        explanatory_notes=_available("The preserved evidence supports this attribution."),
        verification_state=VerificationState.VERIFIED,
    )


def _leg(
    *,
    pre_match: PreMatchDecisionRecord | None = None,
    settlement: PostMatchSettlementRecord | None = None,
    attribution: PostMatchAttribution | None = None,
) -> FieldTrialLeg:
    return FieldTrialLeg(
        pre_match_decision=pre_match or _pre_match(),
        post_match_settlement=settlement or _settlement(),
        post_match_attribution=attribution or _unknown_attribution(),
    )


def _trial(
    *,
    legs: tuple[FieldTrialLeg, ...] | None = None,
    declared_leg_count: int = 1,
    reconstruction_status: ReconstructionStatus = ReconstructionStatus.COMPLETE,
    sources: tuple[SourceEvidence, ...] | None = None,
) -> PredictionFieldTrial:
    legs = legs if legs is not None else (_leg(),)
    summary = SettlementSummary.from_legs(legs)
    if summary.total != declared_leg_count:
        summary = SettlementSummary(0, 0, 0, 0, 0, declared_leg_count)
    return PredictionFieldTrial(
        trial_key="TEST_PREDICTION_FIELD_TRIAL",
        declared_leg_count=declared_leg_count,
        reconstruction_status=reconstruction_status,
        declared_settlement_summary=DeclaredSettlementSummary(
            status=EvidenceAvailability.AVAILABLE,
            summary=summary,
            evidence_references=(SOURCE_ID,),
            verification_state=VerificationState.VERIFIED,
        ),
        source_evidence=sources or (_source(),),
        diagnostic_notes=(),
        creation_import_identity=ImportIdentity(
            importer_id="athena-prediction-field-trial-importer-v1",
            base_commit_sha=AUTHORITATIVE_BASE_SHA,
            source_repository_path="evidence/test-field-trial.json",
            source_sha256="a" * 64,
            source_size=1,
        ),
        legs=legs,
        safety=default_safety(),
    )


def _summary_import_payload() -> dict:
    missing = {"status": "UNKNOWN", "value": None, "evidence_references": []}
    return {
        "schema_version": 1,
        "dataset_name": "athena-prediction-field-trial-import-v1",
        "trial_key": "SUMMARY_ONLY_TEST_FIELD_TRIAL",
        "declared_leg_count": 20,
        "declared_settlement_summary": {
            "status": "AVAILABLE",
            "counts": {
                "WON": 17,
                "LOST": 3,
                "VOID": 0,
                "PARTIAL_WIN": 0,
                "PARTIAL_LOSS": 0,
                "UNKNOWN": 0,
            },
            "evidence_references": ["summary-source"],
            "verification_state": "UNVERIFIED",
        },
        "source_evidence": [
            {
                "source_id": "summary-source",
                "authority": "USER_REPORTED",
                "reference": "local planning summary",
                "content_sha256": missing,
                "observed_at": missing,
                "verification_state": "UNVERIFIED",
                "notes": "Aggregate counts only; no exact legs.",
            }
        ],
        "diagnostic_notes": [],
        "legs": [],
        "safety": dict(default_safety()),
    }


def _write_source(repository: Path, payload: dict) -> Path:
    path = repository / "evidence" / "field-trial.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def test_canonical_serialization_is_deterministic() -> None:
    first = _trial()
    second = dataclasses.replace(first)

    assert canonical_prediction_field_trial_bytes(first) == canonical_prediction_field_trial_bytes(second)
    assert first.canonical_sha256 == second.canonical_sha256


def test_same_pre_match_decision_has_same_identity() -> None:
    first = _pre_match()
    second = dataclasses.replace(first)

    assert first.content_sha256 == second.content_sha256
    assert _leg(pre_match=first).leg_identity == _leg(pre_match=second).leg_identity


def test_adding_settlement_cannot_mutate_pre_match_identity() -> None:
    pre_match = _pre_match()
    lost = _leg(pre_match=pre_match, settlement=_settlement(SettlementOutcome.LOST))
    won = _leg(pre_match=pre_match, settlement=_settlement(SettlementOutcome.WON))

    assert lost.leg_identity == won.leg_identity == pre_match.content_sha256


def test_adding_attribution_cannot_mutate_pre_match_identity() -> None:
    pre_match = _pre_match()
    unknown = _leg(pre_match=pre_match, attribution=_unknown_attribution())
    attributed = _leg(pre_match=pre_match, attribution=_verified_attribution())

    assert unknown.leg_identity == attributed.leg_identity == pre_match.content_sha256


def test_missing_bookmaker_price_stays_missing() -> None:
    candidate = _candidate(bookmaker_price=missing_value(SOURCE_ID))

    serialized = candidate.to_dict()["bookmaker_price"]
    assert serialized == {
        "status": "MISSING",
        "value": None,
        "evidence_references": [SOURCE_ID],
    }


def test_missing_model_probability_stays_missing() -> None:
    candidate = _candidate(probability=missing_value(SOURCE_ID))

    serialized = candidate.to_dict()["model_probability"]
    assert serialized["status"] == "MISSING"
    assert serialized["value"] is None


def test_missing_fixture_identity_cannot_be_guessed() -> None:
    pre_match = _pre_match(fixture_identity=missing_value(SOURCE_ID))

    serialized = pre_match.to_dict()["fixture_identity"]
    assert serialized["status"] == "MISSING"
    assert serialized["value"] is None


def test_unknown_market_id_fails_closed() -> None:
    with pytest.raises(PredictionPostMatchAuditError, match="Unknown market"):
        dataclasses.replace(_candidate(), market_id="NOT_A_MARKET")


def test_counterfactuals_must_exist_in_preserved_pre_match_candidates() -> None:
    with pytest.raises(PredictionPostMatchAuditError, match="preserved pre-match"):
        _pre_match(counterfactual_candidate_ids=_available(["manufactured-after-result"]))


def test_post_match_namespace_rejects_counterfactual_injection() -> None:
    settlement = _settlement().to_dict()
    settlement["counterfactual_candidate_ids"] = ["manufactured-after-result"]
    leg = {
        "pre_match_decision": _pre_match()._content_dict(),
        "post_match_settlement": settlement,
        "post_match_attribution": _unknown_attribution().to_dict(),
    }
    payload = _summary_import_payload()
    payload["declared_leg_count"] = 1
    payload["declared_settlement_summary"]["counts"] = {
        "WON": 0,
        "LOST": 1,
        "VOID": 0,
        "PARTIAL_WIN": 0,
        "PARTIAL_LOSS": 0,
        "UNKNOWN": 0,
    }
    payload["legs"] = [leg]

    with pytest.raises(PredictionPostMatchAuditError, match="keys do not match"):
        build_prediction_field_trial_from_import(
            payload,
            source_repository_path="evidence/test.json",
            source_sha256="b" * 64,
            source_size=1,
        )


def test_lost_does_not_imply_model_error() -> None:
    leg = _leg(settlement=_settlement(SettlementOutcome.LOST))

    assert leg.post_match_attribution.primary_factor is AttributionFactor.UNKNOWN
    assert leg.post_match_attribution.decision_quality is DecisionQuality.UNKNOWN


def test_won_does_not_imply_good_decision() -> None:
    leg = _leg(settlement=_settlement(SettlementOutcome.WON))

    assert leg.post_match_attribution.primary_factor is AttributionFactor.UNKNOWN
    assert leg.post_match_attribution.decision_quality is DecisionQuality.UNKNOWN


def test_unproven_attribution_can_remain_unknown() -> None:
    attribution = _unknown_attribution()

    assert attribution.primary_factor is AttributionFactor.UNKNOWN
    assert attribution.verification_state is VerificationState.UNKNOWN


def test_user_reported_fact_cannot_be_silently_upgraded_to_verified() -> None:
    with pytest.raises(PredictionPostMatchAuditError, match="USER_REPORTED"):
        _source(
            authority=EvidenceAuthority.USER_REPORTED,
            verification=VerificationState.VERIFIED,
        )

    user_source = _source(
        authority=EvidenceAuthority.USER_REPORTED,
        verification=VerificationState.UNVERIFIED,
    )
    with pytest.raises(PredictionPostMatchAuditError, match="VERIFIED source evidence"):
        _trial(sources=(user_source,))


def test_unverified_penalty_report_cannot_be_irreducible_variance() -> None:
    with pytest.raises(PredictionPostMatchAuditError, match="verified event evidence"):
        dataclasses.replace(
            _verified_attribution(AttributionFactor.IRREDUCIBLE_VARIANCE),
            verification_state=VerificationState.UNVERIFIED,
        )


def test_conflicting_source_identity_is_surfaced() -> None:
    first = _source(reference="first-preserved-source.json")
    second = _source(reference="conflicting-preserved-source.json")

    with pytest.raises(PredictionPostMatchAuditError, match="conflicting or duplicate"):
        _trial(sources=(first, second))


def test_import_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    source = _write_source(tmp_path, _summary_import_payload())
    output = tmp_path / "artifacts" / "prediction-field-trials" / "trial.json"

    first = import_field_trial(source=source, output=output, repository_root=tmp_path)
    first_bytes = output.read_bytes()
    second = import_field_trial(source=source, output=output, repository_root=tmp_path)

    assert first["status"] == "AUDIT_ARTIFACT_CREATED"
    assert second["status"] == "IDENTICAL_REIMPORT_NOOP"
    assert output.read_bytes() == first_bytes
    assert first["canonical_sha256"] == second["canonical_sha256"]


def test_different_identity_cannot_overwrite_existing_artifact(tmp_path: Path) -> None:
    payload = _summary_import_payload()
    source = _write_source(tmp_path, payload)
    output = tmp_path / "artifacts" / "prediction-field-trials" / "trial.json"
    import_field_trial(source=source, output=output, repository_root=tmp_path)
    original = output.read_bytes()
    payload["source_evidence"][0]["notes"] = "Different preserved bytes."
    _write_source(tmp_path, payload)

    with pytest.raises(PredictionFieldTrialImportError, match="refusing to overwrite"):
        import_field_trial(source=source, output=output, repository_root=tmp_path)
    assert output.read_bytes() == original


def test_trial_leg_counts_reconcile() -> None:
    trial = _trial()

    assert trial.declared_leg_count == trial.reconstructed_leg_count + trial.unresolved_leg_count


def test_complete_is_impossible_with_unresolved_legs() -> None:
    with pytest.raises(PredictionPostMatchAuditError, match="reconstruction_status must be PARTIAL"):
        _trial(
            declared_leg_count=2,
            reconstruction_status=ReconstructionStatus.COMPLETE,
        )


def test_import_performs_no_network_calls(tmp_path: Path) -> None:
    source = _write_source(tmp_path, _summary_import_payload())
    output = tmp_path / "artifacts" / "prediction-field-trials" / "trial.json"

    with patch.object(socket, "create_connection", side_effect=AssertionError("network")), patch.object(
        urllib.request,
        "urlopen",
        side_effect=AssertionError("network"),
    ):
        receipt = import_field_trial(
            source=source,
            output=output,
            repository_root=tmp_path,
        )

    assert receipt["network_requests_performed"] is False


def test_ledger_grants_no_model_pricing_selection_router_or_bet_authority() -> None:
    trial = _trial()

    assert trial.safety == {
        "bet_authority_granted": False,
        "market_selection_authority_granted": False,
        "model_authority_granted": False,
        "pricing_authority_granted": False,
        "production_state_mutation_authorized": False,
        "value_router_authority_granted": False,
    }


def test_duplicate_json_keys_and_non_finite_constants_are_rejected() -> None:
    with pytest.raises(PredictionFieldTrialImportError, match="duplicate JSON key"):
        strict_json_loads(b'{"schema_version":1,"schema_version":1}')
    with pytest.raises(PredictionFieldTrialImportError, match="invalid JSON constant"):
        strict_json_loads(b'{"value":NaN}')


def test_summary_only_reconstruction_preserves_counts_without_fabricating_legs() -> None:
    payload = _summary_import_payload()
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    trial = build_prediction_field_trial_from_import(
        payload,
        source_repository_path="evidence/summary.json",
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_size=len(raw),
    )

    assert trial.reconstruction_status is ReconstructionStatus.SUMMARY_ONLY
    assert trial.declared_leg_count == 20
    assert trial.reconstructed_leg_count == 0
    assert trial.unresolved_leg_count == 20
    assert trial.declared_settlement_summary.summary == SettlementSummary(17, 3, 0, 0, 0, 0)
    assert trial.legs == ()


def test_committed_first_trial_artifact_exactly_replays_its_source() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = repository / "evidence" / "prediction-field-trials" / "first-proper-20-leg-athena-field-trial-summary.json"
    artifact = repository / "artifacts" / "prediction-field-trials" / "first-proper-20-leg-athena-field-trial-v1.json"
    raw = source.read_bytes()
    payload = strict_json_loads(raw)
    trial = build_prediction_field_trial_from_import(
        payload,
        source_repository_path=source.relative_to(repository).as_posix(),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        source_size=len(raw),
    )

    assert canonical_prediction_field_trial_bytes(trial) == artifact.read_bytes()
    assert trial.reconstruction_status is ReconstructionStatus.SUMMARY_ONLY
    assert trial.legs == ()
