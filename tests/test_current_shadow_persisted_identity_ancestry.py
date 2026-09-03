from __future__ import annotations

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
