from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout


def _record(number: int) -> dict[str, object]:
    return {
        "source_fixture_identifier": str(900000 + number),
        "provider_event_id": f"sr:match:{99000000 + number}",
        "evidence_marker": number,
    }


@pytest.fixture(autouse=True)
def _clean_identity_state():
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    yield
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)


def _verified_bundle(monkeypatch):
    bundle = SimpleNamespace(
        _fotmob_captures=(),
        _fanout_directory=None,
    )
    fanout._bind_identity_state(bundle)
    monkeypatch.setattr(
        fanout.legacy,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: value,
    )
    return bundle


def _learned_record() -> dict[str, object]:
    return {
        "source_fixture_identifier": "5204254",
        "provider_event_id": "sr:match:69343126",
        "source_ccode": "KAZ",
        "source_primary_competition_id": 225,
        "provider_category_id": "sr:category:278",
        "provider_tournament_id": "sr:tournament:682",
        "home_source_team_id": 990001,
        "home_provider_competitor_id": "sr:competitor:990001",
        "away_source_team_id": 990002,
        "away_provider_competitor_id": "sr:competitor:990002",
    }


def _document(payload: dict[str, object]) -> dict[str, object]:
    return {
        "payload": payload,
        "state_sha256": hashlib.sha256(identity._canonical(payload)).hexdigest(),
    }


def _legacy_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy_id": identity.POLICY_ID,
        "matching_basis": identity.MATCHING_BASIS,
        "seed_registry_sha256": identity._LEGACY_V1_FULL_REGISTRY_SHA256,
        "learned_team_identities": [
            [990001, "sr:competitor:990001"],
            [990002, "sr:competitor:990002"],
        ],
        "learned_competition_identities": [
            ["KAZ", 225, "sr:category:278", "sr:tournament:682"],
        ],
        "evidence_records": [_learned_record()],
        "authority": identity._state_authority(),
    }


def _write_document(path, payload: dict[str, object]) -> None:
    path.write_bytes(identity._canonical(_document(payload)) + b"\n")


def test_retained_bundle_replays_after_exact_append_only_identity_evidence(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    bundle = _verified_bundle(monkeypatch)
    retained_sha = bundle._fixture_stable_identity_state_sha256

    identity._evidence_records.append(_record(2))

    assert identity.state_sha256() != retained_sha
    assert fanout.verify_current_event_discovery_reconciliation_bundle(bundle) is bundle


def test_retained_bundle_replay_rejects_removed_retained_evidence(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    bundle = _verified_bundle(monkeypatch)

    identity._evidence_records[:] = [_record(2)]

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="not an append-only extension",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)


def test_same_worker_persistent_state_survives_reset_for_retained_replay(
    monkeypatch, tmp_path
):
    state_path = tmp_path / identity.STATE_FILENAME
    fanout_directory = tmp_path / "fanout"
    fanout_directory.mkdir()
    identity.configure_persistent_state(state_path)
    identity._evidence_records[:] = [_record(1)]
    identity._persist_state()
    source = SimpleNamespace(
        _fotmob_captures=(),
        _fanout_directory=fanout_directory,
    )
    fanout._bind_identity_state(source)
    retained_sha = source._fixture_stable_identity_state_sha256

    identity.reset_runtime_evidence()
    monkeypatch.setenv("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH", str(state_path))
    monkeypatch.setattr(
        fanout.legacy,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: value,
    )

    assert fanout.verify_current_event_discovery_reconciliation_bundle(source) is source
    assert identity.state_sha256() == retained_sha


def test_retained_bundle_replay_fails_after_reset_without_persistent_state(
    monkeypatch, tmp_path
):
    state_path = tmp_path / identity.STATE_FILENAME
    fanout_directory = tmp_path / "fanout"
    fanout_directory.mkdir()
    identity.configure_persistent_state(state_path)
    identity._evidence_records[:] = [_record(1)]
    identity._persist_state()
    source = SimpleNamespace(
        _fotmob_captures=(),
        _fanout_directory=fanout_directory,
    )
    fanout._bind_identity_state(source)

    state_path.unlink()
    identity.reset_runtime_evidence()
    monkeypatch.setenv("ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH", str(state_path))
    monkeypatch.setattr(
        fanout.legacy,
        "verify_current_event_discovery_reconciliation_bundle",
        lambda value: value,
    )

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="not an append-only extension",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(source)


def test_p3_hosted_workflow_configures_only_trusted_shadow_identity_state_before_capture():
    root = Path(__file__).resolve().parents[1]
    text = (
        root / ".github" / "workflows" / "p3-0-comparison-evidence-capture.yml"
    ).read_text(encoding="utf-8")
    restore_marker = "      - name: Restore prior persistent Shadow identity state\n"
    capture_marker = "      - name: Capture paired P3.0 evidence through Router only\n"
    restore_start = text.index(restore_marker)
    capture_start = text.index(capture_marker)
    restore_step = text[restore_start:capture_start]

    assert restore_start < capture_start
    assert "ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH" in restore_step
    assert "current-shadow-fixture-identity-v2-state.json" in restore_step
    assert "current-shadow-all-market.yml/runs?status=success" in restore_step
    assert 'select(.head_branch == "main")' in restore_step
    assert "current-shadow-all-market-request" in restore_step
    assert "No trusted-main Shadow identity state restored" in restore_step
    for forbidden in (
        "schedule:",
        "issue_comment:",
        "send_current_shadow_email",
        "share-code",
        "login",
        "cookies",
        "wallet",
        "staking",
        "wager",
    ):
        assert forbidden not in text


def test_retained_bundle_replay_rejects_policy_or_seed_ancestry_drift(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    bundle = _verified_bundle(monkeypatch)
    snapshot = dict(bundle._fixture_stable_identity_state_snapshot)
    snapshot["policy_id"] = "UNREVIEWED_POLICY"
    bundle._fixture_stable_identity_state_snapshot = snapshot
    bundle._fixture_stable_identity_state_sha256 = fanout._identity_state_sha256(snapshot)

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="changed retained policy ancestry",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)


def test_retained_bundle_replay_rejects_missing_exact_snapshot(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    bundle = _verified_bundle(monkeypatch)
    del bundle._fixture_stable_identity_state_snapshot

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="snapshot is unavailable",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)


def test_retained_bundle_replay_rejects_snapshot_hash_drift(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    bundle = _verified_bundle(monkeypatch)
    bundle._fixture_stable_identity_state_snapshot["evidence_records"].append(_record(2))

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="snapshot hash drifted",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)


def test_append_only_identity_replay_adds_no_authority():
    authority = fanout._identity_state_snapshot()["authority"]
    assert authority["production_model"] is False
    assert authority["pricing"] is False
    assert authority["selection"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False


def test_exact_reviewed_v1_state_migrates_to_v2_without_losing_learned_facts(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    legacy = _legacy_payload()
    _write_document(state_path, legacy)

    identity.configure_persistent_state(state_path)

    migrated = json.loads(state_path.read_text(encoding="utf-8"))
    payload = migrated["payload"]
    assert payload["schema_version"] == 2
    assert payload["seed_registry_sha256"] == identity.SEED_REGISTRY_SHA256
    assert payload["alias_registry_ancestry"] == [
        identity._REVIEWED_ALIAS_V1,
        identity._REVIEWED_ALIAS_V2,
        identity._REVIEWED_ALIAS_V3,
    ]
    for key in (
        "learned_team_identities", "learned_competition_identities", "evidence_records", "authority"
    ):
        assert payload[key] == legacy[key]
    assert migrated["state_sha256"] == identity.state_sha256()


def test_v1_migration_is_deterministic_and_idempotent(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    _write_document(first, _legacy_payload())
    _write_document(second, _legacy_payload())

    identity.configure_persistent_state(first)
    first_document = json.loads(first.read_text(encoding="utf-8"))
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(second)
    second_document = json.loads(second.read_text(encoding="utf-8"))
    assert first_document == second_document

    identity.reset_runtime_evidence()
    identity.configure_persistent_state(second)
    assert json.loads(second.read_text(encoding="utf-8")) == second_document


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda payload: payload.__setitem__("seed_registry_sha256", "0" * 64), "seed registry drifted"),
        (lambda payload: payload.__setitem__("policy_id", "UNREVIEWED"), "policy drifted"),
        (lambda payload: payload.__setitem__("matching_basis", "UNREVIEWED"), "policy drifted"),
        (lambda payload: payload.__setitem__("authority", {}), "authority drifted"),
        (lambda payload: payload.__setitem__("evidence_records", []), "lacks evidence"),
        (lambda payload: payload.__setitem__("learned_team_identities", [[1773, "sr:competitor:990001"]]), "conflicts or lacks evidence"),
    ],
)
def test_invalid_v1_migration_fails_closed_and_is_atomic(tmp_path, mutator, match):
    state_path = tmp_path / identity.STATE_FILENAME
    payload = _legacy_payload()
    mutator(payload)
    _write_document(state_path, payload)
    before_file, before_state = state_path.read_bytes(), identity._state_payload()

    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError, match=match):
        identity.configure_persistent_state(state_path)

    assert identity._state_payload() == before_state
    assert state_path.read_bytes() == before_file


def test_legacy_state_hash_corruption_fails_before_migration(tmp_path):
    state_path = tmp_path / identity.STATE_FILENAME
    document = _document(_legacy_payload())
    document["state_sha256"] = "0" * 64
    state_path.write_bytes(identity._canonical(document) + b"\n")
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError, match="hash mismatch"):
        identity.configure_persistent_state(state_path)


def test_legacy_migration_rejects_future_current_seed_drift_before_loading(tmp_path, monkeypatch):
    state_path = tmp_path / identity.STATE_FILENAME
    _write_document(state_path, _legacy_payload())
    before_file, before_state = state_path.read_bytes(), identity._state_payload()
    monkeypatch.setattr(identity, "SEED_REGISTRY_SHA256", "0" * 64)

    with pytest.raises(
        identity.CurrentShadowFixtureIdentityStateError,
        match="reviewed migration seed ancestry drifted",
    ):
        identity.configure_persistent_state(state_path)

    assert state_path.read_bytes() == before_file
    monkeypatch.setattr(
        identity, "SEED_REGISTRY_SHA256", identity._LEGACY_V1_SEED_REGISTRY_SHA256
    )
    assert identity._state_payload() == before_state


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("alias_registry_ancestry"),
        lambda payload: payload.__setitem__("alias_registry_ancestry", []),
        lambda payload: payload.__setitem__("seed_registry_sha256", "0" * 64),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [identity._REVIEWED_ALIAS_V1]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V1]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [identity._REVIEWED_ALIAS_V1, identity._REVIEWED_ALIAS_V1]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V2]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [{**identity._REVIEWED_ALIAS_V2, "unexpected": True}]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [identity._REVIEWED_ALIAS_V1, {"policy_id": "UNKNOWN", "registry_sha256": "1" * 64}]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [{"policy_id": identity._REVIEWED_ALIAS_V1["policy_id"], "registry_sha256": identity._REVIEWED_ALIAS_V2["registry_sha256"]}]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [{"policy_id": identity._REVIEWED_ALIAS_V2["policy_id"], "registry_sha256": identity._REVIEWED_ALIAS_V1["registry_sha256"]}]),
        lambda payload: payload.__setitem__("alias_registry_ancestry", [{"policy_id": "UNKNOWN", "registry_sha256": "1" * 64}]),
        lambda payload: payload.__setitem__("authority", {}),
    ],
)
def test_native_v2_rejects_malformed_or_unreviewed_ancestry(tmp_path, mutator):
    state_path = tmp_path / identity.STATE_FILENAME
    payload = identity._state_payload()
    mutator(payload)
    _write_document(state_path, payload)
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError):
        identity.configure_persistent_state(state_path)


def test_native_v2_accepts_fresh_and_migrated_reviewed_ancestry(tmp_path):
    fresh_path = tmp_path / "fresh.json"
    _write_document(fresh_path, identity._state_payload())
    identity.configure_persistent_state(fresh_path)
    assert identity._state_payload()["alias_registry_ancestry"] == [identity._REVIEWED_ALIAS_V3]

    migrated_path = tmp_path / "migrated.json"
    migrated = identity._state_payload()
    migrated["alias_registry_ancestry"] = [
        dict(identity._REVIEWED_ALIAS_V1),
        dict(identity._REVIEWED_ALIAS_V2),
        dict(identity._REVIEWED_ALIAS_V3),
    ]
    _write_document(migrated_path, migrated)
    identity.configure_persistent_state(migrated_path)
    assert identity._state_payload()["alias_registry_ancestry"] == migrated["alias_registry_ancestry"]


@pytest.mark.parametrize(
    "historical_ancestry, expected_ancestry",
    [
        ([identity._REVIEWED_ALIAS_V2], [identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V3]),
        ([identity._REVIEWED_ALIAS_V1, identity._REVIEWED_ALIAS_V2], [identity._REVIEWED_ALIAS_V1, identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V3]),
    ],
)
def test_historical_v2_alias_ancestry_is_atomically_extended_to_v3(tmp_path, historical_ancestry, expected_ancestry):
    state_path = tmp_path / identity.STATE_FILENAME
    payload = identity._state_payload()
    payload["alias_registry_ancestry"] = [dict(row) for row in historical_ancestry]
    _write_document(state_path, payload)
    identity.configure_persistent_state(state_path)
    persisted = json.loads(state_path.read_text(encoding="utf-8"))["payload"]
    assert persisted["alias_registry_ancestry"] == expected_ancestry


@pytest.mark.parametrize(
    "ancestry",
    [
        [identity._REVIEWED_ALIAS_V1, identity._REVIEWED_ALIAS_V3],
        [identity._REVIEWED_ALIAS_V3, identity._REVIEWED_ALIAS_V2],
        [identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V2, identity._REVIEWED_ALIAS_V3],
    ],
)
def test_v3_ancestry_rejects_skips_reversal_and_duplicates_atomically(tmp_path, ancestry):
    state_path = tmp_path / identity.STATE_FILENAME
    payload = identity._state_payload()
    payload["alias_registry_ancestry"] = [dict(row) for row in ancestry]
    _write_document(state_path, payload)
    before = state_path.read_bytes()
    with pytest.raises(identity.CurrentShadowFixtureIdentityStateError):
        identity.configure_persistent_state(state_path)
    assert state_path.read_bytes() == before


def test_reviewed_historical_seed_identity_equals_current_only_for_this_transition():
    assert identity.SEED_REGISTRY_SHA256 == identity.seed_registry_sha256()
    assert identity._LEGACY_V1_SEED_REGISTRY_SHA256 == identity.SEED_REGISTRY_SHA256
    descriptor = identity.registry_payload()["reviewed_alias_registry_transition"]
    assert descriptor["source_seed_registry_sha256"] == identity._LEGACY_V1_SEED_REGISTRY_SHA256
    assert descriptor["target_seed_registry_sha256"] == identity.SEED_REGISTRY_SHA256
    assert descriptor["source_state_schema_version"] == 1
    assert descriptor["target_state_schema_version"] == 2


def test_retained_alias_ancestry_is_ordered_reviewed_prefix(monkeypatch):
    bundle = _verified_bundle(monkeypatch)
    retained = bundle._fixture_stable_identity_state_snapshot
    retained["alias_registry_ancestry"] = [
        dict(identity._REVIEWED_ALIAS_V1), dict(identity._REVIEWED_ALIAS_V2)
    ]
    bundle._fixture_stable_identity_state_sha256 = fanout._identity_state_sha256(retained)
    identity._alias_registry_ancestry[:] = [
        dict(identity._REVIEWED_ALIAS_V1),
        dict(identity._REVIEWED_ALIAS_V2),
        dict(identity._REVIEWED_ALIAS_V3),
    ]
    assert fanout.verify_current_event_discovery_reconciliation_bundle(bundle) is bundle

    identity._alias_registry_ancestry[:] = [
        dict(identity._REVIEWED_ALIAS_V3), dict(identity._REVIEWED_ALIAS_V2)
    ]
    with pytest.raises(fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)


@pytest.mark.parametrize(
    "current_ancestry",
    [
        [identity._REVIEWED_ALIAS_V1, {"policy_id": "UNKNOWN", "registry_sha256": "1" * 64}, identity._REVIEWED_ALIAS_V3],
        [{"policy_id": identity._REVIEWED_ALIAS_V1["policy_id"], "registry_sha256": identity._REVIEWED_ALIAS_V3["registry_sha256"]}, identity._REVIEWED_ALIAS_V3],
    ],
)
def test_retained_replay_rejects_unknown_or_cross_paired_alias_ancestry(monkeypatch, current_ancestry):
    bundle = _verified_bundle(monkeypatch)
    retained = bundle._fixture_stable_identity_state_snapshot
    retained["alias_registry_ancestry"] = [
        dict(identity._REVIEWED_ALIAS_V1), dict(identity._REVIEWED_ALIAS_V2)
    ]
    bundle._fixture_stable_identity_state_sha256 = fanout._identity_state_sha256(retained)
    identity._alias_registry_ancestry[:] = [dict(row) for row in current_ancestry]

    with pytest.raises(fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError):
        fanout.verify_current_event_discovery_reconciliation_bundle(bundle)
