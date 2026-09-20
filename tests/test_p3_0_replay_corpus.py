import copy
import socket
from datetime import date, timedelta

import pytest

from domain import p3_0_replay_corpus as replay


MAIN_SHA = "e4c028d08b19f2a3b46d85b490a4c6ea4fcd790a"


def candidate(**updates):
    value = {
        "candidate_id": "candidate-1",
        "source_id": "source-1",
        "source_artifact_or_file": "artifact:1",
        "fixture_identity": "FOTMOB:1",
        "provider_event_id": "sr:match:1",
        "home_team": "Alpha",
        "away_team": "Beta",
        "competition": "League",
        "kickoff_utc": "2026-09-20T12:00:00Z",
        "source_observed_at": "2026-09-20T10:00:00Z",
        "market_families": ["MATCH_RESULT"],
        "duplicate": False,
        "identity_proven": True,
        "temporal_lineage_proven": True,
        "contract_current": True,
        "canonical_lineage_proven": True,
        "exact_quote_proven": True,
        "legacy_lineage_proven": True,
        "failed_requirement_detail": None,
        "offline_repairability": "NOT_REQUIRED_REPLAY_COMPLETE",
        "hashes": {
            "canonical_lineage_sha256": "a" * 64,
            "legacy_lineage_sha256": "b" * 64,
            "quote_identity_sha256": "c" * 64,
            "source_manifest_sha256": "d" * 64,
        },
    }
    value.update(updates)
    return value


def audit(candidates):
    return replay.build_source_audit(
        repository_main_sha=MAIN_SHA,
        source_inventory=[
            {
                "source_id": "source-1",
                "source_class": "TEST",
                "candidate_count": len(candidates),
            }
        ],
        candidates=candidates,
    )


def excluded(flag, expected):
    row = candidate(
        **{
            flag: False,
            "failed_requirement_detail": f"missing {flag}",
            "offline_repairability": "MISSING_SOURCE_CANNOT_BE_FABRICATED",
        }
    )
    assert replay.classify_candidate(row) == expected


def test_source_audit_is_deterministic():
    assert audit([candidate()]) == audit([candidate()])


def test_complete_row_is_admitted():
    result = audit([candidate()])
    assert result["classification_counts"][replay.REPLAY_COMPLETE] == 1
    assert result["replay_complete_count"] == 1
    assert result["exact_quote_identities"] == ["c" * 64]


def test_verified_in_bundle_quote_binding_is_projected_without_fabricated_hash():
    row = candidate()
    del row["hashes"]["quote_identity_sha256"]
    row["hashes"]["quote_identity_binding"] = "VERIFIED_INSIDE_BUNDLE:" + "a" * 64
    result = audit([row])
    assert result["exact_quote_identities"] == []
    assert result["exact_quote_bindings"] == [
        "VERIFIED_INSIDE_BUNDLE:" + "a" * 64
    ]


def test_missing_legacy_lineage_is_rejected():
    excluded("legacy_lineage_proven", replay.REPLAY_UNAVAILABLE_LEGACY_LINEAGE)


def test_missing_canonical_lineage_is_rejected():
    excluded("canonical_lineage_proven", replay.REPLAY_UNAVAILABLE_CANONICAL_LINEAGE)


def test_missing_exact_quote_is_rejected():
    excluded("exact_quote_proven", replay.REPLAY_UNAVAILABLE_EXACT_QUOTE)


def test_identity_unproven_is_rejected():
    excluded("identity_proven", replay.REPLAY_IDENTITY_UNPROVEN)


def test_temporal_lineage_unproven_is_rejected():
    excluded("temporal_lineage_proven", replay.REPLAY_TEMPORAL_LINEAGE_UNPROVEN)


def test_contract_drift_is_rejected():
    excluded("contract_current", replay.REPLAY_CONTRACT_DRIFT)


def test_duplicate_is_excluded():
    row = candidate(
        duplicate=True,
        failed_requirement_detail="duplicate fixture/as-of state",
        offline_repairability="DUPLICATE_EXCLUDED",
    )
    assert replay.classify_candidate(row) == replay.REPLAY_DUPLICATE_EXCLUDED


def test_artifact_digest_tampering_is_rejected():
    result = audit([candidate()])
    tampered = copy.deepcopy(result)
    tampered["candidates"][0]["hashes"]["source_manifest_sha256"] = "0" * 64
    with pytest.raises(replay.ReplayCorpusError, match="canonical_sha256 mismatch"):
        replay.validate_source_audit(tampered)


def test_quote_cross_fixture_swap_is_identity_unproven():
    row = candidate(
        identity_proven=False,
        failed_requirement_detail="quote fixture identity differs from replay fixture",
        offline_repairability="WRONG_FIXTURE_CANNOT_BE_REBOUND",
    )
    assert replay.classify_candidate(row) == replay.REPLAY_IDENTITY_UNPROVEN


def test_later_quote_is_temporal_unproven():
    row = candidate(
        temporal_lineage_proven=False,
        failed_requirement_detail="quote observed after kickoff",
        offline_repairability="LATER_QUOTE_CANNOT_BE_BACKDATED",
    )
    assert replay.classify_candidate(row) == replay.REPLAY_TEMPORAL_LINEAGE_UNPROVEN


def test_builder_never_uses_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", blocked)
    assert audit([candidate()])["network_used"] is False


def test_builder_does_not_mutate_source_file(tmp_path):
    source = tmp_path / "source.json"
    source.write_bytes(b'{"immutable":true}\n')
    before = source.read_bytes()
    audit([candidate()])
    assert source.read_bytes() == before


def test_replay_order_independence():
    first = candidate(candidate_id="a", fixture_identity="FOTMOB:1")
    second = candidate(candidate_id="b", fixture_identity="FOTMOB:2")
    assert audit([first, second]) == audit([second, first])


def test_byte_identical_audit_serialization():
    first = replay.canonical_json_bytes(audit([candidate()]))
    second = replay.canonical_json_bytes(audit([candidate()]))
    assert first == second
    assert first.endswith(b"\n")


def test_one_week_gate_requires_and_accepts_full_diversity():
    rows = []
    start = date(2026, 9, 14)
    for index in range(10):
        rows.append(
            candidate(
                candidate_id=f"week-{index}",
                fixture_identity=f"FOTMOB:{index}",
                competition=f"League {index % 3}",
                kickoff_utc=(
                    start + timedelta(days=index % 7)
                ).isoformat()
                + "T12:00:00Z",
                market_families=[f"FAMILY_{index % 3}"],
            )
        )
    result = audit(rows)
    assert result["acceptance_gates"]["ONE_WEEK_REPLAY"]["satisfied"] is True
    assert result["acceptance_gates"]["accepted_gate"] == "ONE_WEEK_REPLAY"
    assert result["status"] == "REPLAY_CORPUS_READY"


def test_sufficiently_large_gate_accepts_non_contiguous_corpus():
    rows = []
    for index in range(25):
        first_date = index < 13
        rows.append(
            candidate(
                candidate_id=f"large-{index}",
                fixture_identity=f"FOTMOB:{index}",
                competition=("League 0" if first_date else f"League {1 + index % 2}"),
                kickoff_utc=("2026-09-01" if first_date else "2026-09-20")
                + "T12:00:00Z",
                market_families=[
                    f"FAMILY_{index % 3}" if first_date else f"FAMILY_{3 + index % 2}"
                ],
            )
        )
    result = audit(rows)
    assert result["acceptance_gates"]["ONE_WEEK_REPLAY"]["satisfied"] is False
    assert result["acceptance_gates"]["SUFFICIENTLY_LARGE_REPLAY"]["satisfied"] is True
    assert result["acceptance_gates"]["accepted_gate"] == "SUFFICIENTLY_LARGE_REPLAY"


def test_source_gap_is_exact_and_all_authority_flags_remain_false():
    result = audit([candidate(legacy_lineage_proven=False,
                              failed_requirement_detail="legacy missing")])
    assert result["status"] == replay.SOURCE_GAP_STATUS
    assert result["source_gap"]["code"] == replay.SOURCE_GAP_STATUS
    for field in (
        "provider_acquisition",
        "network_used",
        "portfolio_invoked",
        "share_code_invoked",
        "login",
        "cookies",
        "wallet",
        "staking",
        "bet",
        "wager_placed",
        "main_authority",
        "selection_authority",
        "promotion_authority",
    ):
        assert result[field] is False
