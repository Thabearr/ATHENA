"""Separate current-research feature issuance from durable reviewed settlements.

This module never constructs or extends FreshHistoryLedger. A detached result,
caller hash, warehouse row or feature mapping is not a source input.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

from domain import current_fotmob_latest_durable_fresh_history as latest
from domain import current_fotmob_utc_native_current_asof_xg as asof
from domain import current_fotmob_utc_native_shadow_prediction as shadow
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from domain import fotmob_utc_native_expected_goals_fresh_holdout_calibration_competition_protocol as protocol
from domain import fotmob_utc_native_successor_feature_construction_qualification as math_contract


CONTRACT = {
    "version": 1,
    "purpose": "CURRENT_SHADOW_RESEARCH_ONLY",
    "source": "LATEST_APPLICABLE_DURABLE_REVIEWED_SETTLEMENTS",
    "identity": "EXACT_FOTMOB_PRIMARY_ID_AND_TEAM_ID_NO_CROSS_COMPETITION",
    "temporal": "PRIOR_KICKOFF_AND_RESULT_OBSERVED_BY_CURRENT_CAPTURE",
    "minimum_matches_per_team": 1,
    "form": "REVIEWED_LAST_5_POINTS_0_10_PLUS_0_85_FRACTION_ROUND_3",
    "fatigue": "REVIEWED_INTEGER_REST_DAYS_HOME_MINUS_AWAY_0_30_0_10_0",
    "elo": "UNCHANGED_FROZEN_LEDGER_ELO",
    "conflicts": "REJECT_DUPLICATE_FIXTURE_IDS_AND_INVALID_ROWS",
    "legacy_history_mutation": False,
}


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


# Independently reviewed version identity, not derived as the expected value.
CONTRACT_SHA256 = "a3c60b068e95946cdbf6c8b9715994ee04e26736474512fc01c76e979d804d10"
COMPLETE = "CURRENT_NONLEGACY_RESEARCH_FEATURES_COMPLETE"


class CurrentNonlegacyHistoryError(ValueError):
    def __init__(self, message, coverage_status="IDENTITY_UNPROVEN"):
        super().__init__(message)
        self.coverage_status = coverage_status


def verify_contract():
    if hashlib.sha256(_canonical(CONTRACT)).hexdigest() != CONTRACT_SHA256:
        raise CurrentNonlegacyHistoryError("current nonlegacy history contract drift")


def _project(settlements, target):
    """Internal math only. Public issuance first replays the complete source."""
    histories = {target.home_team_id: [], target.away_team_id: []}
    evidence = []
    seen = set()
    for original in settlements:
        if type(original) is not fresh.SettledFreshPrediction:
            raise CurrentNonlegacyHistoryError("unreviewed settlement type")
        row = dataclasses.replace(original)
        fixture = row.prediction.fixture
        if fixture.fixture_id in seen:
            raise CurrentNonlegacyHistoryError("duplicate/conflicting fixture history", "CONFLICTED_HISTORY")
        seen.add(fixture.fixture_id)
        if fixture.fixture_id == target.fixture_id:
            raise CurrentNonlegacyHistoryError("target appears in its own history")
        if fixture.provider_primary_id != target.provider_primary_id:
            continue
        if not {fixture.home_team_id, fixture.away_team_id}.intersection(histories):
            continue
        if (fixture.kickoff_utc >= target.kickoff_utc
                or row.settlement_observed_at > target.capture_observed_at
                or fixture.kickoff_utc >= target.capture_observed_at):
            raise CurrentNonlegacyHistoryError("STALE_OR_ASOF_INVALID_HISTORY", "STALE_OR_ASOF_INVALID_HISTORY")
        for team, gf, ga in (
            (fixture.home_team_id, row.home_goals, row.away_goals),
            (fixture.away_team_id, row.away_goals, row.home_goals),
        ):
            if team in histories:
                histories[team].append((fixture.kickoff_utc, gf, ga))
        evidence.append({
            "fixture_id": fixture.fixture_id,
            "competition_id": fixture.provider_primary_id,
            "home_team_id": fixture.home_team_id,
            "away_team_id": fixture.away_team_id,
            "kickoff": fresh._utc_text(fixture.kickoff_utc),
            "observed_at": fresh._utc_text(row.settlement_observed_at),
            "home_goals": row.home_goals, "away_goals": row.away_goals,
            "settlement_sha256": row.settlement_evidence_sha256,
            "raw_sha256s": [row.ordinary_ft_first_raw_sha256, row.ordinary_ft_second_raw_sha256],
            "manifest_sha256s": [row.ordinary_ft_first_manifest_sha256, row.ordinary_ft_second_manifest_sha256],
        })
    coverage = []
    for team, rows in histories.items():
        rows.sort()
        if len({item[0] for item in rows}) != len(rows):
            raise CurrentNonlegacyHistoryError("conflicting same-team kickoff", "CONFLICTED_HISTORY")
        coverage.append({
            "competition_id": target.provider_primary_id, "team_id": team,
            "history_row_count": len(rows),
            "earliest_qualified_kickoff": fresh._utc_text(rows[0][0]) if rows else None,
            "latest_qualified_kickoff": fresh._utc_text(rows[-1][0]) if rows else None,
            "history_as_of": fresh._utc_text(target.capture_observed_at),
            "coverage_status": "SUFFICIENT_REVIEWED_HISTORY" if rows else "NO_REVIEWED_HISTORY",
            "missing_reason": None if rows else "NO_SETTLED_EXACT_TEAM_COMPETITION_RESULT",
            "complete_competition_history_claimed": False,
        })
    home, away = histories[target.home_team_id], histories[target.away_team_id]
    features = {}
    for name, rows in (("home_form", home), ("away_form", away)):
        _, value = math_contract._form_value(rows)
        if value is not None:
            features[name] = value
    _, fatigue, *_ = math_contract._fatigue_value(target.kickoff_utc, home, away)
    if fatigue is not None:
        features["fatigue"] = fatigue
    evidence.sort(key=lambda item: (item["kickoff"], item["fixture_id"]))
    return features, coverage, evidence


def build_current_nonlegacy_features(history, fixture_identity):
    """Replay source ancestry; derive features and rates without accepting values.

The returned canonical bytes are a diagnostic receipt, not a reusable authority
token. Inference calls this builder again; no detached-receipt intake exists.
"""
    verify_contract()
    if type(history) is not latest.CurrentLatestDurableFreshHistoryHandoff:
        raise CurrentNonlegacyHistoryError("IDENTITY_UNPROVEN: exact current history required")
    source = dataclasses.replace(history)
    # The copy above already replays the complete source. Serialize that copy,
    # rather than performing a second identical deep reconstruction here.
    history_sha = hashlib.sha256(latest._canonical(source.to_dict())).hexdigest()
    rows = [r for r in source.shadow_handoff.rows if r.fixture_identifier == fixture_identity]
    if len(rows) != 1:
        raise CurrentNonlegacyHistoryError("IDENTITY_UNPROVEN: target not unique")
    target = rows[0].fixture
    if target.provider_primary_id in protocol.LEGACY_PRIMARY_IDS:
        return None
    features, coverage, evidence = _project(
        source.shadow_handoff.source_bundle.reviewed_fresh_settlements, target
    )
    ledger, _ = shadow._history_ledger(source.shadow_handoff.source_bundle)
    original = asof.build_current_asof_xg_assessment(
        history_ledger=ledger, selected_capture=target,
        fixture_review_policy_id=source.shadow_handoff.fixture_review_policy_id,
    )
    rates = {}
    if set(features) == {"home_form", "away_form", "fatigue"}:
        features.update({key: original.features[key] for key in ("home_elo", "away_elo")})
        rates = fresh._rates_from_features(features)
    receipt = {
        "contract": CONTRACT, "contract_sha256": CONTRACT_SHA256,
        "fixture_identity": fixture_identity,
        "history_sha256": history_sha,
        "frozen_elo_projection_sha256": original.feature_projection_sha256,
        "status": COMPLETE if rates else "INSUFFICIENT_REVIEWED_HISTORY",
        "coverage": coverage, "evidence": evidence, "features": features, "rates": rates,
        "authority": {key: False for key in (
            "production", "production_probability", "bet", "wallet", "staking",
            "wager_placed", "sealed_holdout", "backfill", "pricing", "selection",
        )},
    }
    return _canonical(receipt)
