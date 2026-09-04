from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain import current_shadow_fixture_identity_v2 as identity
from domain import current_shadow_sportybet_catalog_fanout_reconciliation as fanout


def _record(number: int) -> dict[str, object]:
    return {
        "source_fixture_identifier": str(910000 + number),
        "provider_event_id": f"sr:match:{99100000 + number}",
        "evidence_marker": number,
    }


@pytest.fixture(autouse=True)
def _clean_identity_state():
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)
    yield
    identity.reset_runtime_evidence()
    identity.configure_persistent_state(None)


def test_append_only_replay_serializes_ephemeral_rebuild_with_retained_state(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    source = SimpleNamespace(_fotmob_captures=(), _fanout_directory=None)
    fanout._bind_identity_state(source)
    retained_sha = source._fixture_stable_identity_state_sha256
    retained_snapshot = fanout._copy_identity_state(
        source._fixture_stable_identity_state_snapshot
    )

    identity._evidence_records.append(_record(2))
    current_sha = identity.state_sha256()
    assert current_sha != retained_sha

    rebuilt = SimpleNamespace()

    def fake_verify(value):
        assert value is source
        assert fanout._serialized_identity_state_sha256(rebuilt) == retained_sha
        return rebuilt

    monkeypatch.setattr(
        fanout.legacy,
        "verify_current_event_discovery_reconciliation_bundle",
        fake_verify,
    )

    checked = fanout.verify_current_event_discovery_reconciliation_bundle(source)

    assert checked is rebuilt
    assert checked._fixture_stable_identity_state_sha256 == retained_sha
    assert checked._fixture_stable_identity_state_snapshot == retained_snapshot
    assert fanout._serialized_identity_state_sha256(SimpleNamespace()) == current_sha


def test_replay_serialization_scope_restores_current_state_after_failure(monkeypatch):
    identity._evidence_records[:] = [_record(1)]
    source = SimpleNamespace(_fotmob_captures=(), _fanout_directory=None)
    fanout._bind_identity_state(source)
    retained_sha = source._fixture_stable_identity_state_sha256

    identity._evidence_records.append(_record(2))
    current_sha = identity.state_sha256()
    assert current_sha != retained_sha

    def fail_verify(_value):
        assert fanout._serialized_identity_state_sha256(SimpleNamespace()) == retained_sha
        raise fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError(
            "synthetic replay failure"
        )

    monkeypatch.setattr(
        fanout.legacy,
        "verify_current_event_discovery_reconciliation_bundle",
        fail_verify,
    )

    with pytest.raises(
        fanout.CurrentShadowSportyBetCatalogFanoutReconciliationError,
        match="synthetic replay failure",
    ):
        fanout.verify_current_event_discovery_reconciliation_bundle(source)

    assert fanout._serialized_identity_state_sha256(SimpleNamespace()) == current_sha


def test_retained_replay_fix_adds_no_authority():
    authority = fanout._identity_state_snapshot()["authority"]
    assert authority["production_model"] is False
    assert authority["pricing"] is False
    assert authority["selection"] is False
    assert authority["bet"] is False
    assert authority["wager_placed"] is False
