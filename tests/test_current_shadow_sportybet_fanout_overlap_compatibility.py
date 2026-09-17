from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout

UTC = timezone.utc
OBSERVED = datetime(2026, 9, 17, 16, 27, 30, tzinfo=UTC)
EVENT_ID = "sr:match:73806008"


def test_overlap_policy_identity_is_evidence_pinned_in_shadow_contract():
    identity = fanout.validate_contract()
    assert fanout.FANOUT_OVERLAP_COMPATIBILITY_POLICY_ID == (
        "ATHENA_CURRENT_SHADOW_EXACT_CROSS_OBSERVATION_EVENT_OVERLAP_V1"
    )
    assert fanout.FANOUT_OVERLAP_EVIDENCE_WORKFLOW_RUN_ID == 35246536029
    assert fanout.FANOUT_OVERLAP_EVIDENCE_ARTIFACT_ID == 10508071809
    assert fanout.FANOUT_OVERLAP_EVIDENCE_ARTIFACT_SHA256 == (
        "019b749eeb82a0e27d99726b08a6832d7823ecc9a17fd75ff576537841101924"
    )
    assert fanout.EXPECTED_CONTRACT_SHA256 == (
        "d0a623b8915795e87c0d0d1b4d44a4a218fde09f95249c08c8f423d57abe661f"
    )
    assert fanout.calculate_contract_sha256() == fanout.EXPECTED_CONTRACT_SHA256
    assert identity["fanout_overlap_compatibility_policy_id"] == (
        fanout.FANOUT_OVERLAP_COMPATIBILITY_POLICY_ID
    )
    assert identity["fanout_overlap_evidence_workflow_run_id"] == 35246536029
    assert identity["fanout_overlap_evidence_artifact_id"] == 10508071809
    assert identity["fanout_overlap_evidence_artifact_sha256"] == (
        fanout.FANOUT_OVERLAP_EVIDENCE_ARTIFACT_SHA256
    )


def _raw(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _catalog():
    return _raw({
        "bizCode": 10000,
        "data": [{
            "id": fanout.FOOTBALL_SPORT_ID,
            "name": "Football",
            "categories": [{
                "id": "sr:category:951",
                "name": "Reviewed Category",
                "tournaments": [
                    {"id": "sr:tournament:20162", "name": "League A", "eventSize": 1},
                    {"id": "sr:tournament:20163", "name": "League B", "eventSize": 1},
                ],
            }],
        }],
    })


def _event(*, away_team="Away"):
    return {
        "eventId": EVENT_ID,
        "sportId": fanout.FOOTBALL_SPORT_ID,
        "homeTeamName": "Home",
        "awayTeamName": away_team,
        "tournamentName": "Shared League",
        "estimateStartTime": 1790000000000,
        "bookingStatus": "Open",
        "status": 0,
        "matchStatus": "Not started",
    }


def _install_network(monkeypatch, *, conflicting_second=False):
    catalog = _catalog()
    first = _raw({"bizCode": 10000, "trace": "first", "data": [_event()]})
    second = _raw({
        "bizCode": 10000,
        "trace": "second",
        "data": [_event(away_team="Different Away" if conflicting_second else "Away")],
    })

    def fake_get(target):
        if target == fanout.catalog_request_target():
            return catalog, OBSERVED
        if "tournamentId=sr%3Atournament%3A20162" in target:
            return first, OBSERVED
        if "tournamentId=sr%3Atournament%3A20163" in target:
            return second, OBSERVED + timedelta(seconds=1)
        raise AssertionError(target)

    monkeypatch.setattr(fanout, "_network_get", fake_get)
    monkeypatch.setattr(fanout.fixture_identity_v2, "observe_provider_payload", lambda _raw: None)
    monkeypatch.setattr(fanout.time, "time", lambda: OBSERVED.timestamp() - 1)


def test_exact_event_overlap_across_distinct_fanout_observations_is_replayable(
    monkeypatch, tmp_path
):
    _install_network(monkeypatch)
    frozen_snapshot_type = fanout.base.CurrentShadowSportyBetCatalogFanoutSnapshot

    directory, snapshot = fanout.capture_current_catalog_fanout_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )

    assert fanout.base.CurrentShadowSportyBetCatalogFanoutSnapshot is frozen_snapshot_type
    assert type(snapshot) is fanout.CurrentShadowSportyBetCatalogFanoutSnapshot
    assert len(snapshot.observations) == 2
    assert len(snapshot.events) == 1
    assert [observation.event_ids for observation in snapshot.observations] == [
        (EVENT_ID,),
        (EVENT_ID,),
    ]
    assert snapshot.events[0].event_id == EVENT_ID
    assert snapshot.events[0].source_raw_sha256 == snapshot.observations[1].raw_sha256
    assert snapshot.events[0].source_observed_at == snapshot.observations[1].observed_at

    replayed = fanout.verify_current_catalog_fanout_discovery(
        directory,
        repository_root=tmp_path,
    )
    assert replayed.to_dict() == snapshot.to_dict()
    assert fanout.base.CurrentShadowSportyBetCatalogFanoutSnapshot is frozen_snapshot_type


def test_overlap_compatibility_is_builder_and_raw_replay_scoped(monkeypatch, tmp_path):
    _install_network(monkeypatch)
    _, snapshot = fanout.capture_current_catalog_fanout_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="builder/replay scoped",
    ):
        dataclasses.replace(snapshot)


def test_conflicting_duplicate_event_identity_still_fails_closed(monkeypatch, tmp_path):
    _install_network(monkeypatch, conflicting_second=True)

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="conflicting duplicate provider event identity",
    ):
        fanout.capture_current_catalog_fanout_discovery(
            repository_root=tmp_path,
            execute_live_network=True,
        )


def test_overlap_does_not_relax_manifest_identity_coverage(monkeypatch, tmp_path):
    _install_network(monkeypatch)
    directory, _ = fanout.capture_current_catalog_fanout_discovery(
        repository_root=tmp_path,
        execute_live_network=True,
    )

    manifest_path = directory / fanout.MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["observations"][0]["event_ids"] = ["sr:match:99999999"]
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="observation/event identity coverage mismatch",
    ):
        fanout.verify_current_catalog_fanout_discovery(
            directory,
            repository_root=tmp_path,
        )
