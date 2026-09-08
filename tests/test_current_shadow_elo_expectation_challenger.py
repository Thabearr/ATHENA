import copy
import hashlib
from pathlib import Path
import pytest
from domain import current_shadow_elo_expectation_challenger as subject
from domain import fotmob_utc_native_successor_feature_construction_qualification as frozen

def row(identity, kickoff, home, away, hg, ag):
    return {"source_namespace": frozen.SOURCE_NAMESPACE, "fixture_identifier": identity, "kickoff_utc": kickoff,
        "home_team_identifier": home, "away_team_identifier": away, "home_goals": hg, "away_goals": ag,
        "evidence_sha256": hashlib.sha256(identity.encode()).hexdigest(), "evidence_reference": f"reviewed:{identity}"}

@pytest.fixture
def cohort():
    return [row("1", "2026-01-01T12:00:00Z", "10", "20", 1, 0), row("2", "2026-01-02T12:00:00Z", "30", "40", 0, 0),
            row("3", "2026-01-08T12:00:00Z", "20", "10", 2, 1), row("4", "2026-01-09T12:00:00Z", "30", "10", 0, 3)]

def projection(rows): return frozen.construct_utc_native_feature_projection(rows)[0]

def test_exact_reproduction_complements_separation_and_authority(cohort):
    report = subject.compare_elo_replays(rows=cohort, expected_baseline_projection_raw=projection(cohort))
    subject.validate_report(report)
    assert report["aggregate"]["baseline_exact_reproduction"] is True
    assert all(abs(i["challenger"]["expected_score_mass"] - 1) <= subject.COMPLEMENT_TOLERANCE for i in report["fixtures"])
    assert report["baseline_id"] != report["challenger_id"]
    assert all(v is False for v in report["authority"].values()) and report["wager_placed"] is False

def test_only_expected_pair_semantics_changes_initially(cohort):
    first = subject.compare_elo_replays(rows=cohort, expected_baseline_projection_raw=projection(cohort))["fixtures"][0]
    assert first["baseline"]["home_elo"] == first["challenger"]["home_elo"] == 1500
    assert first["baseline"]["home_expected_score"] == first["challenger"]["home_expected_score"]
    assert first["baseline"]["away_expected_score"] != first["challenger"]["away_expected_score"]

def test_identity_changes_and_reordering_canonicalizes(cohort):
    original = subject.compare_elo_replays(rows=cohort, expected_baseline_projection_raw=projection(cohort))
    reordered = subject.compare_elo_replays(rows=reversed(cohort), expected_baseline_projection_raw=projection(cohort))
    assert original["comparison_sha256"] == reordered["comparison_sha256"]
    changed = copy.deepcopy(cohort); changed[0]["home_goals"] = 0
    revised = subject.compare_elo_replays(rows=changed, expected_baseline_projection_raw=projection(changed))
    assert original["source_history_sha256"] != revised["source_history_sha256"]
    assert original["terminal_state_sha256"]["challenger"] != revised["terminal_state_sha256"]["challenger"]

def test_missing_malformed_and_nonreproducing_inputs_fail_closed(cohort):
    with pytest.raises(subject.EloExpectationChallengerError, match="BASELINE_REPRODUCTION_FAILED"):
        subject.compare_elo_replays(rows=cohort, expected_baseline_projection_raw=projection(cohort) + b" ")
    with pytest.raises(subject.EloExpectationChallengerError, match="missing historical evidence"):
        subject.compare_elo_replays(rows=[], expected_baseline_projection_raw=b"x")
    bad = copy.deepcopy(cohort); bad[0]["home_goals"] = float("nan")
    with pytest.raises(subject.EloExpectationChallengerError): subject.compare_elo_replays(rows=bad, expected_baseline_projection_raw=b"x")

def test_provider_values_cannot_enter_model_and_absence_synthesizes_nothing(cohort):
    assert "odds" not in subject.compare_elo_replays.__annotations__
    with pytest.raises(subject.EloExpectationChallengerError):
        subject.compare_elo_replays(rows=cohort, expected_baseline_projection_raw=b"")

def test_frozen_baseline_blob_is_unchanged():
    raw = Path(frozen.__file__).read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == subject.FROZEN_CONSTRUCTOR_BLOB_SHA
