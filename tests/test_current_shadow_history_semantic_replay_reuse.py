from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import current_shadow_history_semantic_replay_reuse as reuse


_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64


@dataclasses.dataclass(frozen=True)
class _Prediction:
    fixture_id: int
    seal_sha256: str


@dataclasses.dataclass(frozen=True)
class _Update:
    fixture_identifier: str
    evidence_sha256: str


@dataclasses.dataclass(frozen=True)
class _Settlement:
    prediction: _Prediction
    home_goals: int
    away_goals: int
    settlement_evidence_sha256: str
    legacy_history_state_update: _Update | None


@dataclasses.dataclass(frozen=True)
class _Ledger:
    history_identity: tuple[object, ...]


@dataclasses.dataclass(frozen=True)
class _Derived:
    current_bootstrap_sha256: str
    ledger: _Ledger


@dataclasses.dataclass(frozen=True)
class _Source:
    current_sha: str
    manifest_sha: str
    raw_sha: str
    legacy_bootstrap_projection_raw: bytes
    reviewed_fresh_settlements: tuple[_Settlement, ...]

    @property
    def current_bootstrap_sha256(self) -> str:
        return self.current_sha

    @property
    def source_manifest_sha256(self) -> str:
        return self.manifest_sha

    @property
    def source_raw_sha256(self) -> str:
        return self.raw_sha


def _shadow(*, fail_current_sha: str | None = None):
    calls = {"derive": 0, "ledger": 0}
    shadow = SimpleNamespace()
    shadow.CurrentUtcNativeShadowPredictionSourceBundle = _Source
    shadow.fresh = SimpleNamespace(SettledFreshPrediction=_Settlement)

    def history_ledger(source: _Source):
        calls["ledger"] += 1
        return (
            _Ledger(
                history_identity=(
                    source.legacy_bootstrap_projection_raw,
                    source.reviewed_fresh_settlements,
                )
            ),
            len(source.reviewed_fresh_settlements),
        )

    def derive(source: _Source):
        calls["derive"] += 1
        if source.current_sha == fail_current_sha:
            raise RuntimeError("derive failed")
        ledger, _count = shadow._history_ledger(source)
        return _Derived(source.current_sha, ledger)

    shadow._history_ledger = history_ledger
    shadow._derive_shadow_state = derive
    return shadow, calls, history_ledger, derive


def _settlement(*, evidence_sha: str = _SHA_D) -> _Settlement:
    return _Settlement(
        prediction=_Prediction(fixture_id=42, seal_sha256=_SHA_C),
        home_goals=2,
        away_goals=1,
        settlement_evidence_sha256=evidence_sha,
        legacy_history_state_update=_Update(
            fixture_identifier="42",
            evidence_sha256=evidence_sha,
        ),
    )


def _source(
    *,
    current_sha: str = _SHA_A,
    raw_sha: str = _SHA_C,
    settlement: _Settlement | None = None,
) -> _Source:
    return _Source(
        current_sha=current_sha,
        manifest_sha=_SHA_B,
        raw_sha=raw_sha,
        legacy_bootstrap_projection_raw=b"exact-pr119-bootstrap\n",
        reviewed_fresh_settlements=(settlement or _settlement(),),
    )


def test_equivalent_dataclass_copies_reuse_exact_derive_and_history_ledger(
    tmp_path: Path,
) -> None:
    shadow, calls, original_ledger, original_derive = _shadow()
    diagnostic = tmp_path / "semantic-reuse.json"
    hooks = reuse.install(shadow, diagnostic_path=diagnostic)
    try:
        first = shadow._derive_shadow_state(_source())
        second = shadow._derive_shadow_state(_source())

        assert first is second
        assert calls == {"derive": 1, "ledger": 1}
        assert hooks.stats.to_dict() == {
            "derive_authoritative_executed": 1,
            "derive_reused": 1,
            "history_ledger_authoritative_executed": 1,
            "history_ledger_reused": 0,
            "uncacheable_fallbacks": 0,
            "failures_not_cached": 0,
        }
        payload = json.loads(diagnostic.read_text(encoding="utf-8"))
        assert payload["last_operation"] == "DERIVE_REUSED"
        assert payload["derive_cache_entries"] == 1
        assert payload["history_ledger_cache_entries"] == 1
        assert payload["evidence_authority"] is False
        assert payload["model_authority"] is False
        assert payload["pricing_authority"] is False
        assert payload["selection_authority"] is False
        assert payload["execution_authority"] is False
        assert payload["bet_authority"] is False
        assert payload["wager_placed"] is False
    finally:
        reuse.restore(shadow, hooks)

    assert shadow._history_ledger is original_ledger
    assert shadow._derive_shadow_state is original_derive


def test_date_specific_derive_reuses_only_date_invariant_history() -> None:
    shadow, calls, _original_ledger, _original_derive = _shadow()
    hooks = reuse.install(shadow)
    try:
        first = shadow._derive_shadow_state(_source(current_sha=_SHA_A))
        second = shadow._derive_shadow_state(_source(current_sha=_SHA_E))

        assert first is not second
        assert first.ledger is second.ledger
        assert calls == {"derive": 2, "ledger": 1}
        assert hooks.stats.to_dict()["history_ledger_reused"] == 1
        assert hooks.stats.to_dict()["derive_authoritative_executed"] == 2
    finally:
        reuse.restore(shadow, hooks)


def test_any_settlement_content_drift_forces_authoritative_replay() -> None:
    shadow, calls, _original_ledger, _original_derive = _shadow()
    hooks = reuse.install(shadow)
    try:
        first = shadow._derive_shadow_state(_source(settlement=_settlement()))
        changed = shadow._derive_shadow_state(
            _source(settlement=_settlement(evidence_sha=_SHA_E))
        )

        assert first is not changed
        assert first.ledger is not changed.ledger
        assert calls == {"derive": 2, "ledger": 2}
        assert hooks.stats.to_dict()["derive_reused"] == 0
        assert hooks.stats.to_dict()["history_ledger_reused"] == 0
    finally:
        reuse.restore(shadow, hooks)


def test_current_capture_drift_never_reuses_derive_but_can_reuse_history() -> None:
    shadow, calls, _original_ledger, _original_derive = _shadow()
    hooks = reuse.install(shadow)
    try:
        first = shadow._derive_shadow_state(_source(raw_sha=_SHA_C))
        changed = shadow._derive_shadow_state(_source(raw_sha=_SHA_D))

        assert first is not changed
        assert first.ledger is changed.ledger
        assert calls == {"derive": 2, "ledger": 1}
        assert hooks.stats.to_dict()["history_ledger_reused"] == 1
    finally:
        reuse.restore(shadow, hooks)


def test_failed_derive_is_never_cached() -> None:
    shadow, calls, _original_ledger, _original_derive = _shadow(
        fail_current_sha=_SHA_A
    )
    hooks = reuse.install(shadow)
    try:
        with pytest.raises(RuntimeError, match="derive failed"):
            shadow._derive_shadow_state(_source())
        with pytest.raises(RuntimeError, match="derive failed"):
            shadow._derive_shadow_state(_source())

        assert calls["derive"] == 2
        assert hooks.stats.to_dict()["derive_authoritative_executed"] == 0
        assert hooks.stats.to_dict()["derive_reused"] == 0
        assert hooks.stats.to_dict()["failures_not_cached"] == 2
    finally:
        reuse.restore(shadow, hooks)


def test_three_day_shape_executes_one_history_ledger_for_equal_history() -> None:
    shadow, calls, _original_ledger, _original_derive = _shadow()
    hooks = reuse.install(shadow)
    try:
        for current_sha in (_SHA_A, _SHA_D, _SHA_E):
            shadow._derive_shadow_state(_source(current_sha=current_sha))
            shadow._derive_shadow_state(_source(current_sha=current_sha))

        assert calls == {"derive": 3, "ledger": 1}
        stats = hooks.stats.to_dict()
        assert stats["derive_authoritative_executed"] == 3
        assert stats["derive_reused"] == 3
        assert stats["history_ledger_authoritative_executed"] == 1
        assert stats["history_ledger_reused"] == 2
    finally:
        reuse.restore(shadow, hooks)
