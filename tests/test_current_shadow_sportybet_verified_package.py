from __future__ import annotations

import pytest

from domain import current_shadow_sportybet_share_code as low_level
from domain import current_shadow_sportybet_verified_package as package
from domain import current_shadow_sportybet_verified_share_code as verified_share
from tests.test_current_shadow_sportybet_field_trial import _decision


def _verified_source(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    history, mapping, _inventory, evaluation, decision = _decision(
        tmp_path,
        monkeypatch,
    )
    source = package.build_verified_research_decision_source(
        complete_current_history=history,
        current_mapping_rebind=mapping,
        evaluation_time=evaluation,
    )
    return history, mapping, evaluation, decision, source


def test_verified_decision_source_is_builder_only_and_replays_exact_current_sources(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _history, _mapping, evaluation, decision, source = _verified_source(
        tmp_path,
        monkeypatch,
    )
    assert source.decision.to_dict() == decision.to_dict()
    assert source.decision_sha256 == decision.canonical_sha256
    assert source.evaluation_time == evaluation
    assert package.AUTHORITY["research_shadow_execution_input"] is True
    assert package.AUTHORITY["production_selection"] is False
    assert package.AUTHORITY["bet"] is False
    assert source.to_dict()["wager_placed"] is False
    assert (
        package.verify_verified_research_decision_source(source).to_dict()
        == source.to_dict()
    )

    with pytest.raises(
        package.CurrentShadowVerifiedPackageError,
        match="builder-only",
    ):
        package.VerifiedResearchDecisionSource()


def test_tampered_verified_decision_receipt_fails_exact_source_replay(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, source = _verified_source(tmp_path, monkeypatch)
    object.__setattr__(source, "decision_sha256", "f" * 64)
    with pytest.raises(
        package.CurrentShadowVerifiedPackageError,
        match="differs from exact source replay",
    ):
        package.verify_verified_research_decision_source(source)


def test_verified_portfolio_package_rebuilds_every_retained_decision_source(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, evaluation, _decision_value, source = _verified_source(
        tmp_path,
        monkeypatch,
    )
    verified = package.build_verified_research_shadow_portfolio(
        (source,),
        target_size=1,
        evaluation_time=evaluation,
    )
    assert len(verified.decisions) == 1
    assert verified.portfolio_sha256 == verified.portfolio.canonical_sha256
    assert verified.portfolio.selected_legs
    assert verified.authority["exact_research_portfolio_source_replay"] is True
    assert verified.authority["production_sportybet_execution"] is False
    assert verified.to_dict()["wager_placed"] is False
    assert (
        package.verify_verified_research_shadow_portfolio(verified).to_dict()
        == verified.to_dict()
    )

    with pytest.raises(
        package.CurrentShadowVerifiedPackageError,
        match="builder-only",
    ):
        package.VerifiedResearchShadowPortfolio()


def test_canonical_share_entry_point_verifies_source_package_before_network_transport(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, evaluation, _decision_value, source = _verified_source(
        tmp_path,
        monkeypatch,
    )
    verified = package.build_verified_research_shadow_portfolio(
        (source,),
        target_size=1,
        evaluation_time=evaluation,
    )
    expected = low_level.ResearchShadowShareCodeReceipt(
        status=low_level.STATUS_NO_QUALIFIED_LEGS,
        observed_at=evaluation,
        portfolio_sha256=verified.portfolio.canonical_sha256,
        requested_target_size=1,
        portfolio_shortfall=1,
        selected_leg_count=0,
        reasons=("TEST_CANONICAL_WRAPPER",),
        semantic_resolution_receipt_sha256=None,
        transport_receipt_sha256=None,
        share_code=None,
        share_url=None,
        combined_odds=None,
    )
    calls = {"transport": 0}

    def fake_transport(**kwargs):
        calls["transport"] += 1
        assert kwargs["portfolio"].to_dict() == verified.portfolio.to_dict()
        assert tuple(item.to_dict() for item in kwargs["source_decisions"]) == tuple(
            item.to_dict() for item in verified.decisions
        )
        return expected

    monkeypatch.setattr(
        verified_share.transport,
        "create_current_shadow_sportybet_share_code",
        fake_transport,
    )
    result = verified_share.create_verified_current_shadow_sportybet_share_code(
        verified_portfolio=verified,
        output_dir=tmp_path / "verified-share",
        delay_seconds=0,
    )
    assert result is expected
    assert calls["transport"] == 1


def test_tampered_verified_portfolio_never_reaches_network_transport(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    *_prefix, evaluation, _decision_value, source = _verified_source(
        tmp_path,
        monkeypatch,
    )
    verified = package.build_verified_research_shadow_portfolio(
        (source,),
        target_size=1,
        evaluation_time=evaluation,
    )
    object.__setattr__(verified, "portfolio_sha256", "e" * 64)
    calls = {"transport": 0}

    def transport_should_not_run(**_kwargs):
        calls["transport"] += 1
        raise AssertionError("transport must not run after source-package tampering")

    monkeypatch.setattr(
        verified_share.transport,
        "create_current_shadow_sportybet_share_code",
        transport_should_not_run,
    )
    with pytest.raises(
        verified_share.CurrentShadowVerifiedShareCodeError,
        match="retained-source replay",
    ):
        verified_share.create_verified_current_shadow_sportybet_share_code(
            verified_portfolio=verified,
            output_dir=tmp_path / "verified-share",
            delay_seconds=0,
        )
    assert calls["transport"] == 0
